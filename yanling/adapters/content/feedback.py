"""内容反馈收集器 — 采集内容发布后的效果反馈.

反馈来源 (层级扩展):
  L0 — 文件系统: feedback.jsonl 手动输入
  L1 — 平台 API: 掘金阅读量/点赞, 知乎赞同等 (待接入)
  L2 — 飞书机器人: 用户主动反馈 (待接入)
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yanling.core.types import Percept
from yanling.kernel.perception import PerceptionAdapter

log = logging.getLogger("yanling.content.feedback")

DEFAULT_FEEDBACK_DIR = Path(os.path.expanduser("~/.yanling/content"))


@dataclass
class FeedbackEntry:
    """单条反馈记录。"""
    date: str                         # 关联的内容日期 (YYYY-MM-DD)
    source: str                       # 反馈来源 (manual | juejin | zhihu | feishu)
    topic: str                        # 主题分类
    metric: str                       # 指标名 (views | likes | shares | score)
    value: float                      # 指标值
    timestamp: float = 0.0            # 记录时间

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "source": self.source,
            "topic": self.topic,
            "metric": self.metric,
            "value": self.value,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> FeedbackEntry:
        return cls(
            date=d["date"],
            source=d["source"],
            topic=d["topic"],
            metric=d["metric"],
            value=d["value"],
            timestamp=d.get("timestamp", 0),
        )


class FeedbackCollector(PerceptionAdapter):
    """内容反馈收集器 — 采集并产出反馈感知数据。

    支持文件级持久化，每次 poll 产出新的反馈条目作为 Percept。
    """

    def __init__(self, feedback_dir: str | Path = DEFAULT_FEEDBACK_DIR):
        self._feedback_dir = Path(feedback_dir)
        self._feedback_file = self._feedback_dir / "feedback.jsonl"
        self._seen_entries: set[int] = set()  # hash of seen entries
        self._entries: list[FeedbackEntry] = []
        self._last_topic_stats: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "content_feedback"

    async def start(self):
        self._feedback_dir.mkdir(parents=True, exist_ok=True)
        # 加载已有反馈
        if self._feedback_file.exists():
            try:
                for line in self._feedback_file.read_text().strip().splitlines():
                    if line.strip():
                        entry = FeedbackEntry.from_dict(json.loads(line))
                        self._entries.append(entry)
                        self._seen_entries.add(hash((entry.date, entry.topic, entry.metric, entry.timestamp)))
                log.info("反馈收集器已加载 %d 条历史反馈", len(self._entries))
            except Exception as e:
                log.warning("反馈文件加载失败: %s", e)

    async def poll(self) -> list[Percept]:
        """产出未读反馈感知。"""
        percepts: list[Percept] = []

        # 计算自上次 poll 以来的新条目
        new_entries = [
            e for e in self._entries
            if hash((e.date, e.topic, e.metric, e.timestamp)) not in self._seen_entries
        ]
        # 标记所有当前条目为已读
        for e in self._entries:
            self._seen_entries.add(hash((e.date, e.topic, e.metric, e.timestamp)))

        for entry in new_entries[:10]:  # 限制单次输出
            percepts.append(Percept(
                source=self.name,
                type="content.feedback",
                data={
                    "date": entry.date,
                    "topic": entry.topic,
                    "metric": entry.metric,
                    "value": entry.value,
                    "source": entry.source,
                },
                confidence=0.8,
            ))

        # 定期产出主题统计感知
        stats = self.topic_statistics()
        if stats and stats != self._last_topic_stats:
            percepts.append(Percept(
                source=self.name,
                type="content.feedback_stats",
                data=stats,
                confidence=0.7,
            ))
            self._last_topic_stats = stats

        return percepts

    # ─── 公共接口 ─────────────────────────────────────────

    def record_feedback(
        self,
        date: str,
        topic: str,
        metric: str,
        value: float,
        source: str = "manual",
    ) -> FeedbackEntry:
        """记录一条反馈。"""
        entry = FeedbackEntry(
            date=date,
            source=source,
            topic=topic,
            metric=metric,
            value=value,
        )
        self._entries.append(entry)
        self._append_to_file(entry)
        return entry

    def record_batch(self, entries: list[FeedbackEntry]):
        """批量记录反馈。"""
        for e in entries:
            self._entries.append(e)
            self._append_to_file(e)

    def topic_statistics(self) -> dict[str, Any]:
        """按主题汇总统计。"""
        if not self._entries:
            return {}

        by_topic: dict[str, list[float]] = defaultdict(list)
        by_topic_views: dict[str, list[float]] = defaultdict(list)
        for e in self._entries:
            by_topic[e.topic].append(e.value)
            if e.metric == "views":
                by_topic_views[e.topic].append(e.value)

        topic_scores = {}
        for topic, values in by_topic.items():
            topic_scores[topic] = {
                "avg": round(sum(values) / len(values), 2),
                "count": len(values),
                "views": round(sum(by_topic_views.get(topic, []))),
            }

        sorted_topics = sorted(
            topic_scores.items(),
            key=lambda x: x[1]["avg"],
            reverse=True,
        )

        return {
            "total_entries": len(self._entries),
            "topic_count": len(topic_scores),
            "best_topic": sorted_topics[0][0] if sorted_topics else "",
            "best_score": sorted_topics[0][1]["avg"] if sorted_topics else 0,
            "topics": topic_scores,
        }

    @property
    def entries(self) -> list[FeedbackEntry]:
        return list(self._entries)

    # ─── 内部 ─────────────────────────────────────────────

    def _append_to_file(self, entry: FeedbackEntry):
        """追加记录到文件。"""
        try:
            with open(self._feedback_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("反馈写入失败: %s", e)
