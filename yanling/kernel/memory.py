"""记忆系统 — 分层记忆结构."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from yanling.adapters.storage.base import StorageAdapter
from yanling.core.types import TickResult

log = logging.getLogger("yanling.memory")


@dataclass
class MemoryEntry:
    """单条记忆。"""
    key: str
    content: Any
    type: str  # experience | pattern | knowledge | evolution
    timestamp: float = 0.0
    importance: float = 0.5  # [0, 1]
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class WorkingMemory:
    """工作记忆 — 当前 tick 上下文，容量有限。"""

    def __init__(self, capacity: int = 10):
        self.capacity = capacity
        self._data: OrderedDict[str, Any] = OrderedDict()

    def set(self, key: str, value: Any):
        self._data[key] = value
        if len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def clear(self):
        self._data.clear()

    def snapshot(self) -> dict:
        return dict(self._data)


class ShortTermMemory:
    """短期记忆 — 最近 N 条记录的 LRU 缓存。"""

    def __init__(self, capacity: int = 100, ttl: float = 3600):
        self.capacity = capacity
        self.ttl = ttl
        self._entries: list[MemoryEntry] = []

    def add(self, entry: MemoryEntry):
        self._entries.append(entry)
        self._prune()

    def _prune(self):
        now = time.time()
        self._entries = [e for e in self._entries if now - e.timestamp < self.ttl]
        if len(self._entries) > self.capacity:
            self._entries = self._entries[-self.capacity:]

    def recent(self, n: int = 10) -> list[MemoryEntry]:
        return self._entries[-n:]

    def query(self, type: str | None = None, tag: str | None = None) -> list[MemoryEntry]:
        results = self._entries
        if type:
            results = [e for e in results if e.type == type]
        if tag:
            results = [e for e in results if tag in e.tags]
        return results

    def clear(self):
        self._entries.clear()


class LongTermMemory:
    """长期记忆 — 持久化的重要知识。"""

    def __init__(self, storage: StorageAdapter):
        self._storage = storage
        self._entries: list[MemoryEntry] = []

    async def load(self):
        data = await self._storage.read("long_term_memory")
        if data:
            self._entries = [MemoryEntry(**item) for item in data]

    async def save(self):
        data = [
            {"key": e.key, "content": e.content, "type": e.type,
             "timestamp": e.timestamp, "importance": e.importance, "tags": e.tags}
            for e in self._entries
        ]
        await self._storage.write("long_term_memory", data)

    def add(self, entry: MemoryEntry):
        self._entries.append(entry)
        self._entries.sort(key=lambda e: e.importance, reverse=True)

    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """简单的关键词搜索。"""
        results = []
        for e in self._entries:
            if query in str(e.content):
                results.append(e)
        return sorted(results, key=lambda e: e.importance, reverse=True)[:top_k]

    def important(self, threshold: float = 0.7) -> list[MemoryEntry]:
        return [e for e in self._entries if e.importance >= threshold]


class MemorySystem:
    """统一记忆系统入口。"""

    def __init__(self, storage: StorageAdapter, config: dict | None = None):
        config = config or {}
        self.working = WorkingMemory(capacity=config.get("working_memory_size", 10))
        self.short_term = ShortTermMemory(
            capacity=config.get("short_term_capacity", 100),
            ttl=config.get("short_term_ttl", 3600),
        )
        self.long_term = LongTermMemory(storage)
        self._storage = storage
        self._checkpoint_interval = config.get("checkpoint_interval", 50)
        self._tick_since_checkpoint = 0

    @property
    def recent_short_term(self) -> list[MemoryEntry]:
        return self.short_term.recent(10)

    @property
    def important_long_term(self) -> list[MemoryEntry]:
        return self.long_term.important(0.6)

    @property
    def working_snapshot(self) -> dict:
        return self.working.snapshot()

    async def initialize(self):
        await self.long_term.load()
        log.info("记忆系统已初始化，长期记忆条目: %d", len(self.long_term._entries))

    async def remember_tick(self, tick_result: TickResult):
        """记录一次 tick 到所有记忆层。"""
        self.working.set(f"tick_{tick_result.tick_id}", tick_result)

        self.short_term.add(MemoryEntry(
            key=f"tick_{tick_result.tick_id}",
            content={
                "perceptions": len(tick_result.perceptions),
                "decisions": [d.intent.name for d in tick_result.cognition.decisions],
                "actions_success": sum(1 for a in tick_result.actions if a.success),
                "actions_fail": sum(1 for a in tick_result.actions if not a.success),
                "duration": tick_result.duration,
            },
            type="tick",
            importance=0.3,
            tags=[d.intent.name.lower() for d in tick_result.cognition.decisions],
        ))

        has_failure = any(not a.success for a in tick_result.actions)
        has_error = tick_result.error is not None
        if has_failure or has_error:
            self.long_term.add(MemoryEntry(
                key=f"tick_{tick_result.tick_id}_failure",
                content={
                    "tick_id": tick_result.tick_id,
                    "percept_count": len(tick_result.perceptions),
                    "decisions": [
                        {"intent": d.intent.name, "reason": d.reason[:100]}
                        for d in tick_result.cognition.decisions
                    ],
                    "action_results": [
                        {"type": a.type, "success": a.success, "error": str(a.error)[:100]}
                        for a in tick_result.actions
                    ],
                    "error": tick_result.error,
                    "duration": tick_result.duration,
                },
                type="experience",
                importance=0.8 if has_error else 0.6,
                tags=["failure", "error"] if has_error else ["failure"],
            ))

        self._tick_since_checkpoint += 1
        if self._tick_since_checkpoint >= self._checkpoint_interval:
            await self.checkpoint()

    async def checkpoint(self):
        """持久化 checkpoint — 保存长期记忆。"""
        await self.long_term.save()
        self._tick_since_checkpoint = 0
        log.debug("记忆 checkpoint 已保存")

    async def recall_context(self) -> dict:
        """构建当前上下文的轻量摘要（防止上下文爆炸）。"""
        # 工作记忆：只取最近 3 条的摘要，避免全量序列化
        raw = self.working.snapshot()
        working_summary = {}
        for k, v in list(raw.items())[-3:]:
            if hasattr(v, "tick_id"):
                working_summary[k] = {
                    "tick_id": v.tick_id,
                    "percepts": [p.source for p in getattr(v, "perceptions", [])],
                    "actions": [
                        {"type": a.type, "success": a.success}
                        for a in getattr(v, "actions", [])
                    ],
                    "error": getattr(v, "error", None),
                }
            else:
                working_summary[k] = str(v)[:100]

        return {
            "working": working_summary,
            "short_term_recent": [
                {"key": e.key, "type": e.type, "importance": e.importance,
                 "content_preview": str(e.content)[:100]}
                for e in self.short_term.recent(5)
            ],
            "long_term_important": [
                {"key": e.key, "type": e.type, "content": str(e.content)[:200]}
                for e in self.long_term.important(0.7)
            ],
        }
