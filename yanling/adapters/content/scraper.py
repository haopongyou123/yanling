"""平台数据采集器 — 从各发布平台拉取文章统计数据.

信息护城河核心: 每一篇文章的阅读/点赞/评论数据都是独有资产。
日积月累形成平台无法复制的效果数据集。

支持平台:
  - 掘金 (juejin): 公开 API, 无需认证
  - 知乎 (zhihu): 待接入
  - 头条 (toutiao): 待接入
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.request import urlopen, Request

from yanling.adapters.content.feedback import FeedbackCollector
from yanling.core.types import Percept
from yanling.kernel.perception import PerceptionAdapter

log = logging.getLogger("yanling.content.scraper")

PUBLISHED_FILE = Path(os.path.expanduser("~/.yanling/content/published.jsonl"))


# ─── 数据结构 ──────────────────────────────────────────────

@dataclass
class PublishedArticle:
    """已发布文章的记录。"""
    article_id: str
    platform: str                    # juejin | zhihu | toutiao
    date: str                        # YYYY-MM-DD
    title: str = ""
    url: str = ""
    topics: list[str] = field(default_factory=list)
    timestamp: float = 0.0
    # 拉取到的统计数据
    stats: dict = field(default_factory=dict)
    stats_updated_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "article_id": self.article_id,
            "platform": self.platform,
            "date": self.date,
            "title": self.title,
            "url": self.url,
            "topics": self.topics,
            "timestamp": self.timestamp or time.time(),
            "stats": self.stats,
            "stats_updated_at": self.stats_updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PublishedArticle:
        return cls(
            article_id=d["article_id"],
            platform=d["platform"],
            date=d.get("date", ""),
            title=d.get("title", ""),
            url=d.get("url", ""),
            topics=d.get("topics", []),
            timestamp=d.get("timestamp", 0),
            stats=d.get("stats", {}),
            stats_updated_at=d.get("stats_updated_at", 0),
        )


# ─── 已发布文章追踪器 ────────────────────────────────────

class PublishedTracker:
    """管理已发布文章的记录。"""

    def __init__(self, filepath: str | Path = PUBLISHED_FILE):
        self._filepath = Path(filepath)
        self._articles: list[PublishedArticle] = []

    def load(self):
        """从文件加载已发布文章列表。"""
        self._articles = []
        if not self._filepath.exists():
            return
        try:
            for line in self._filepath.read_text().strip().splitlines():
                if line.strip():
                    self._articles.append(
                        PublishedArticle.from_dict(json.loads(line))
                    )
            log.info("已加载 %d 条发布记录", len(self._articles))
        except Exception as e:
            log.warning("发布记录加载失败: %s", e)

    def save(self):
        """持久化到文件。"""
        self._filepath.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._filepath, "w", encoding="utf-8") as f:
                for a in self._articles:
                    f.write(json.dumps(a.to_dict(), ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("发布记录保存失败: %s", e)

    def add(self, article: PublishedArticle):
        """添加一条发布记录。"""
        # 去重
        for i, a in enumerate(self._articles):
            if a.article_id == article.article_id and a.platform == article.platform:
                self._articles[i] = article
                return
        self._articles.append(article)

    def update_stats(self, article_id: str, platform: str, stats: dict):
        """更新文章统计数据。"""
        for a in self._articles:
            if a.article_id == article_id and a.platform == platform:
                a.stats = stats
                a.stats_updated_at = time.time()
                return

    def get_unscraped(self, min_age_hours: float = 1) -> list[PublishedArticle]:
        """获取需要拉取统计的文章（从未拉取或数据过期）。"""
        now = time.time()
        return [
            a for a in self._articles
            if a.platform == "juejin"
            and (not a.stats or now - a.stats_updated_at > min_age_hours * 3600)
        ]

    @property
    def articles(self) -> list[PublishedArticle]:
        return list(self._articles)

    @property
    def count(self) -> int:
        return len(self._articles)


# ─── 掘金 API ────────────────────────────────────────────

JUJIN_QUERY_LIST = "https://api.juejin.cn/content_api/v1/article/query_list"
JUJIN_USER_GET = "https://api.juejin.cn/user_api/v1/user/get"

# 从环境变量读取掘金用户 ID
_JUJIN_USER_ID: str = os.environ.get("JUJIN_USER_ID", "")

def _discover_user_id_from_cookie() -> str:
    """尝试从 掘金 cookie 文件自动发现 user_id。"""
    global _JUJIN_USER_ID
    if _JUJIN_USER_ID:
        return _JUJIN_USER_ID
    try:
        cookie_path = os.path.expanduser("~/.claude/cookies/juejin.json")
        if not os.path.exists(cookie_path):
            return ""
        import json
        data = json.loads(open(cookie_path).read())
        cookies = {c["name"]: c["value"] for c in data.get("cookies", [])}
        session = cookies.get("sessionid", "")
        if not session:
            return ""
        from urllib.request import Request, urlopen
        req = Request(
            f"{JUJIN_USER_GET}",
            headers={
                "Cookie": f"sessionid={session}",
                "User-Agent": "Mozilla/5.0",
            },
        )
        with urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
        if result.get("err_no") == 0:
            uid = result["data"].get("user_id", "")
            if uid:
                _JUJIN_USER_ID = uid
                return uid
    except Exception:
        pass
    return ""


async def _fetch_juejin_all_stats(user_id: str | None = None) -> dict[str, dict] | None:
    """从掘金公开 API 拉取所有文章的统计数据 (query_list).

    返回 {article_id: {views, likes, comments, collects}} 映射表。
    此接口无需登录，一次请求返回全部文章。
    """
    uid = user_id or _JUJIN_USER_ID
    if not uid:
        return None

    try:
        payload = json.dumps({
            "user_id": uid, "sort_type": 2, "cursor": "0",
        }).encode()
        req = Request(
            JUJIN_QUERY_LIST,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                ),
            },
        )
        loop = asyncio.get_event_loop()

        def _do():
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())

        result = await loop.run_in_executor(None, _do)
        if result.get("err_no") != 0:
            log.debug("掘金 query_list 返回异常: %s", result.get("err_msg", ""))
            return None

        articles = result.get("data", [])
        stats_map: dict[str, dict] = {}
        for item in articles:
            info = item.get("article_info", {})
            aid = info.get("article_id", "")
            if aid:
                stats_map[aid] = {
                    "views": info.get("view_count", 0),
                    "likes": info.get("digg_count", 0),
                    "comments": info.get("comment_count", 0),
                    "collects": info.get("collect_count", 0),
                }
        log.info("掘金 API 采集到 %d 篇文章数据", len(stats_map))
        return stats_map

    except Exception as e:
        log.debug("掘金 query_list 请求失败: %s", e)
        return None


async def _fetch_juejin_user_total(user_id: str | None = None) -> dict | None:
    """获取掘金用户总数据（累计阅读/点赞）。"""
    uid = user_id or _JUJIN_USER_ID
    if not uid:
        return None
    try:
        req = Request(
            f"{JUJIN_USER_GET}?user_id={uid}",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                ),
            },
        )
        loop = asyncio.get_event_loop()

        def _do():
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())

        result = await loop.run_in_executor(None, _do)
        if result.get("err_no") == 0:
            d = result["data"]
            return {
                "views": d.get("got_view_count", 0),
                "likes": d.get("got_digg_count", 0),
                "followers": d.get("follower_count", 0),
                "level": d.get("level", 0),
            }
    except Exception as e:
        log.debug("掘金 user_get 请求失败: %s", e)
    return None


def set_juejin_user_id(user_id: str):
    """运行时设置掘金用户 ID。"""
    global _JUJIN_USER_ID
    _JUJIN_USER_ID = user_id
    log.info("掘金用户 ID 已设为: %s", user_id)


# ─── 平台统计采集适配器 ──────────────────────────────────

class PlatformStatsScraper(PerceptionAdapter):
    """平台统计采集器 — 定期拉取已发布文章的统计数据。

    作为 PerceptionAdapter 接入引擎主循环，每次 poll 时：
      1. 检查需要拉取统计的文章（从未拉取或过期的）
      2. 批量拉取掘金等平台的公开数据
      3. 产出一组 content.stats 感知 → 进入世界模型
      4. 同步到 FeedbackCollector
    """

    def __init__(
        self,
        tracker: PublishedTracker | None = None,
        feedback: FeedbackCollector | None = None,
        batch_size: int = 5,
        scrape_interval_ticks: int = 30,
    ):
        self._tracker = tracker or PublishedTracker()
        self._feedback = feedback
        self._batch_size = batch_size
        self._interval = scrape_interval_ticks
        self._tick = 0

    @property
    def name(self) -> str:
        return "platform_scraper"

    async def start(self):
        self._tracker.load()
        log.info(
            "平台采集器已启动: %d 篇文章待追踪",
            self._tracker.count,
        )

    async def stop(self):
        self._tracker.save()

    def bind_feedback(self, feedback: FeedbackCollector):
        """绑定反馈收集器。"""
        self._feedback = feedback

    def record_publish(self, article: PublishedArticle):
        """记录一条新发布。"""
        self._tracker.add(article)
        self._tracker.save()

    # ─── 感知轮询 ────────────────────────────────────────

    async def poll(self) -> list[Percept]:
        self._tick += 1
        if self._tick % self._interval != 0:
            return []

        percepts: list[Percept] = []

        # ── 掘金批量采集 ────────────────────────────────────
        juejin_articles = [a for a in self._tracker.articles if a.platform == "juejin"]
        # 也尝试从环境变量或已配置的用户 ID 采集所有文章
        if _JUJIN_USER_ID:
            stats_map = await _fetch_juejin_all_stats()
            if stats_map:
                for article in self._tracker.articles:
                    aid = article.article_id
                    if aid in stats_map:
                        stats = stats_map[aid]
                        self._tracker.update_stats(aid, article.platform, stats)

                        percepts.append(Percept(
                            source=self.name,
                            type="content.stats",
                            data={
                                "article_id": aid,
                                "platform": article.platform,
                                "date": article.date,
                                **stats,
                            },
                            confidence=0.9,
                        ))

                        if self._feedback:
                            for metric, value in stats.items():
                                for topic in (article.topics or ["general"]):
                                    self._feedback.record_feedback(
                                        date=article.date,
                                        topic=topic,
                                        metric=metric,
                                        value=float(value),
                                        source=f"platform:{article.platform}",
                                    )

                # 用户总数据（每 5 次采集产出一条汇总）
                if self._tick % (self._interval * 5) == 0:
                    user_total = await _fetch_juejin_user_total()
                    if user_total:
                        percepts.append(Percept(
                            source=self.name,
                            type="content.author_stats",
                            data={"platform": "juejin", **user_total},
                            confidence=0.8,
                        ))
                        log.info("掘金累计数据: views=%s, likes=%s", user_total.get("views"), user_total.get("likes"))

        # ── 逐篇采集（用于 query_list 没覆盖到的文章）────
        unscraped = self._tracker.get_unscraped(min_age_hours=0.5)
        for article in unscraped:
            if article.article_id in {a.article_id for a in self._tracker.articles if a.stats}:
                continue  # 已经通过批量采集获取到数据
            if article.platform == "juejin":
                # 单篇 detail API 可能会有变更，走 query_list 为主
                log.debug("跳过单篇采集 [%s]，等待下次批量", article.article_id)

        # 保存更新
        self._tracker.save()

        return percepts
