"""内容发布监视器 — 感知 auto-content/ 发布的数据文件.

作为 PerceptionAdapter 接入衍灵引擎主循环:
  1. 扫描 auto-content/data/*.json 获取新发布的内容
  2. 提取主题、标签、标题结构等特征
  3. 产出 Percept → 进入世界模型 → 形成模式关联
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yanling.core.types import Percept
from yanling.kernel.perception import PerceptionAdapter

log = logging.getLogger("yanling.content.monitor")

# 默认数据路径
DEFAULT_DATA_DIR = Path(os.path.expanduser("~/auto-content/data"))


def _extract_topics(titles: list[str]) -> list[str]:
    """从标题中提取主题关键词。"""
    topics: list[str] = []
    # 常见科技主题模式
    patterns = [
        r"AI|人工智能|大模型|LLM|智能",
        r"融资|估值|IPO|上市|投资|收购",
        r"机器人|具身智能|无人驾驶",
        r"芯片|半导体|GPU|算力",
        r"新能源|电动|光伏|储能",
        r"出海|全球化|海外|跨境",
        r"开源|开发者|代码|编程",
        r"电商|直播|社交|内容",
    ]
    for title in titles:
        for pat in patterns:
            if re.search(pat, title, re.IGNORECASE):
                topics.append(pat.strip("|"))
                break
    return topics


class ContentMonitor(PerceptionAdapter):
    """内容发布监视器 — 检测新发布并生成感知。"""

    def __init__(self, data_dir: str | Path = DEFAULT_DATA_DIR):
        self._data_dir = Path(data_dir)
        self._seen_files: dict[str, float] = {}  # path → mtime
        self._last_topic_summary: dict[str, Any] = {}
        self._topic_history: dict[str, int] = {}  # topic → count (累积)

    @property
    def name(self) -> str:
        return "content_monitor"

    async def start(self):
        """初始化时加载已存在的文件列表。"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        for fpath in sorted(self._data_dir.glob("20*.json")):
            try:
                mtime = fpath.stat().st_mtime
                self._seen_files[str(fpath)] = mtime
            except OSError:
                pass
        log.info("内容监视器已加载 %d 个历史文件", len(self._seen_files))

    async def poll(self) -> list[Percept]:
        """检查新发布，产出感知数据。"""
        percepts: list[Percept] = []
        new_files: list[Path] = []

        for fpath in sorted(self._data_dir.glob("20*.json")):
            if fpath.name.startswith("20") and fpath.suffix == ".json":
                try:
                    mtime = fpath.stat().st_mtime
                    last = self._seen_files.get(str(fpath), 0)
                    if mtime > last:
                        new_files.append(fpath)
                        self._seen_files[str(fpath)] = mtime
                except OSError:
                    continue

        if not new_files:
            return percepts

        for fpath in new_files:
            content_data = self._read_content_file(fpath)
            if content_data is None:
                continue

            # 产出内容发布感知
            percepts.append(self._make_published_percept(content_data))

            # 更新主题历史
            for topic in content_data.get("topics", []):
                self._topic_history[topic] = self._topic_history.get(topic, 0) + 1

        # 如果有新内容，产出主题汇总感知
        if self._topic_history:
            sorted_topics = sorted(
                self._topic_history.items(), key=lambda x: -x[1]
            )[:5]
            topic_summary = {
                "top_topics": [t for t, _ in sorted_topics],
                "total_articles": sum(
                    1 for p in percepts
                    if p.type == "content.published"
                ),
                "topic_diversity": len(self._topic_history),
            }
            if topic_summary != self._last_topic_summary:
                percepts.append(Percept(
                    source=self.name,
                    type="content.topic_summary",
                    data=topic_summary,
                    confidence=0.7,
                ))
                self._last_topic_summary = topic_summary

        return percepts

    def _read_content_file(self, fpath: Path) -> dict | None:
        """读取并解析内容数据文件。"""
        try:
            raw = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("内容文件解析失败 %s: %s", fpath.name, e)
            return None

        content = raw.get("content") or raw
        items = content.get("items", [])
        titles = content.get("titles", [])
        tags = content.get("tags", [])
        opening = content.get("opening", "")

        topics = _extract_topics(titles or [it.get("title", "") for it in items])

        return {
            "date": raw.get("date", fpath.stem),
            "created_at": raw.get("created_at", ""),
            "title_count": len(titles),
            "item_count": len(items),
            "topics": topics,
            "tags": tags,
            "opening_length": len(opening),
            "source_file": fpath.name,
        }

    def _make_published_percept(self, data: dict) -> Percept:
        """构建内容发布感知。"""
        return Percept(
            source=self.name,
            type="content.published",
            data={
                "date": data["date"],
                "title_count": data["title_count"],
                "item_count": data["item_count"],
                "topics": data["topics"],
                "tags": data["tags"],
                "opening_length": data["opening_length"],
            },
            confidence=0.9,
        )

    @property
    def topic_distribution(self) -> dict[str, int]:
        """当前主题分布。"""
        return dict(self._topic_history)

    @property
    def total_detected(self) -> int:
        """检测到的发布总数。"""
        return sum(1 for v in self._seen_files.values() if v > 0)


class ContentSummaryAdapter(PerceptionAdapter):
    """内容主题汇总适配器 — 定期产出主题分布感知。

    与 ContentMonitor 配合使用，ContentMonitor 负责检测新发布，
    本适配器定期产出主题趋势分析。
    """

    def __init__(self, monitor: ContentMonitor, interval_ticks: int = 10):
        self._monitor = monitor
        self._interval = interval_ticks
        self._tick = 0

    @property
    def name(self) -> str:
        return "content_summary"

    async def poll(self) -> list[Percept]:
        self._tick += 1
        if self._tick % self._interval != 0:
            return []

        dist = self._monitor.topic_distribution
        if not dist:
            return []

        sorted_topics = sorted(dist.items(), key=lambda x: -x[1])[:5]
        return [
            Percept(
                source=self.name,
                type="content.trend",
                data={
                    "top_topics": [t for t, _ in sorted_topics],
                    "total": sum(dist.values()),
                    "diversity": len(dist),
                },
                confidence=0.6,
            )
        ]
