"""内容管道适配器测试。"""

import json
import tempfile
from pathlib import Path

import pytest

from yanling.adapters.content.feedback import FeedbackCollector, FeedbackEntry
from yanling.adapters.content.monitor import ContentMonitor
from yanling.adapters.content.optimizer import ContentStrategyOptimizer
from yanling.adapters.content.scraper import PublishedArticle, PublishedTracker, PlatformStatsScraper
from yanling.kernel.evolution import ImprovementProposal


def _fake_content(date: str, topics: list[str] | None = None) -> dict:
    """生成模拟内容数据。"""
    topics = topics or ["AI", "融资"]
    return {
        "date": date,
        "created_at": f"{date}T12:00:00",
        "content": {
            "titles": [f"AI 大模型投资新趋势 {i}" for i in range(3)],
            "opening": "今日科技圈聚焦..." * 10,
            "items": [
                {"title": f"AI 创业新闻 {i}", "summary": "详情..."}
                for i in range(5)
            ],
            "tags": [f"#{t}" for t in topics],
        },
    }


class TestContentMonitor:
    @pytest.mark.asyncio
    async def test_detect_new_content(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monitor = ContentMonitor(data_dir)
        await monitor.start()
        # start 后写入文件，模拟"新发布"
        (data_dir / "2026-05-14.json").write_text(
            json.dumps(_fake_content("2026-05-14"), ensure_ascii=False),
            encoding="utf-8",
        )
        ps = await monitor.poll()
        assert len(ps) >= 1
        published = [p for p in ps if p.type == "content.published"]
        assert len(published) == 1
        assert published[0].data["title_count"] == 3

    @pytest.mark.asyncio
    async def test_no_duplicate(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monitor = ContentMonitor(data_dir)
        await monitor.start()
        fpath = data_dir / "2026-05-14.json"
        fpath.write_text(
            json.dumps(_fake_content("2026-05-14"), ensure_ascii=False),
            encoding="utf-8",
        )
        await monitor.poll()
        # 第二次 poll 不应产出同样文件
        ps2 = await monitor.poll()
        new_published = [p for p in ps2 if p.type == "content.published"]
        assert len(new_published) == 0

    @pytest.mark.asyncio
    async def test_topic_summary(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monitor = ContentMonitor(data_dir)
        await monitor.start()
        for d in ("2026-05-10", "2026-05-11"):
            (data_dir / f"{d}.json").write_text(
                json.dumps(_fake_content(d, topics=["AI"]), ensure_ascii=False),
                encoding="utf-8",
            )
        await monitor.poll()
        assert any("AI" in k for k in monitor.topic_distribution)


class TestFeedbackCollector:
    @pytest.mark.asyncio
    async def test_record_and_poll(self, tmp_path):
        collector = FeedbackCollector(tmp_path)
        await collector.start()
        collector.record_feedback("2026-05-14", "AI", "views", 1500)
        ps = await collector.poll()
        feedback = [p for p in ps if p.type == "content.feedback"]
        assert len(feedback) >= 1
        assert feedback[0].data["value"] == 1500

    @pytest.mark.asyncio
    async def test_topic_statistics(self, tmp_path):
        collector = FeedbackCollector(tmp_path)
        await collector.start()
        collector.record_feedback("2026-05-14", "AI", "score", 8.0)
        collector.record_feedback("2026-05-14", "Robot", "score", 6.0)
        stats = collector.topic_statistics()
        assert stats["topic_count"] == 2
        assert stats["best_topic"] == "AI"

    def test_persistence(self, tmp_path):
        collector = FeedbackCollector(tmp_path)
        import asyncio
        asyncio.run(collector.start())
        collector.record_feedback("2026-05-14", "AI", "likes", 42)
        # 新实例应加载已存数据
        collector2 = FeedbackCollector(tmp_path)
        asyncio.run(collector2.start())
        assert len(collector2.entries) == 1


class TestContentStrategyOptimizer:
    def test_generate_without_data(self):
        optimizer = ContentStrategyOptimizer(cooldown_ticks=0)
        props = optimizer.generate_proposals(current_tick=1)
        assert props == []

    def test_feed_to_evolution(self):
        from yanling.kernel.evolution import EvolutionEngine
        from yanling.kernel.memory import MemorySystem
        from yanling.adapters.storage.json_file import JsonFileStorage
        from yanling.adapters.llm.base import LLMResponse
        import tempfile

        class MockLLM:
            @property
            def model_name(self): return "mock"
            @property
            def provider(self): return "mock"
            async def chat(self, messages, **kw): return LLMResponse(content="{}", model="mock")
            async def is_available(self): return True

        storage = JsonFileStorage(tempfile.mkdtemp())
        memory = MemorySystem(storage)
        llm = MockLLM()
        from yanling.kernel.cognition import CognitiveEngine
        cognition = CognitiveEngine(llm)
        evo = EvolutionEngine(memory, llm, cognition)

        optimizer = ContentStrategyOptimizer(evolution=evo, cooldown_ticks=0)
        optimizer.feed_to_evolution([
            ImprovementProposal(
                area="system_prompt",
                title="测试提案",
                description="测试",
                trigger="test",
                confidence=0.8,
                estimated_impact="medium",
            )
        ])
        assert len(evo.proposals) == 1

    def test_topic_gap_proposal(self):
        import tempfile
        collector = FeedbackCollector(tempfile.mkdtemp())
        import asyncio
        asyncio.run(collector.start())
        collector.record_feedback("2026-05-14", "AI", "score", 9.0)
        collector.record_feedback("2026-05-14", "Robot", "score", 2.0)

        optimizer = ContentStrategyOptimizer(
            feedback_collector=collector,
            cooldown_ticks=0,
        )
        props = optimizer.generate_proposals(current_tick=1)
        # 差距 = 7.0 > 1.0，应产生提案
        assert any(p.title == "内容主题表现分化 — 建议聚焦优质主题" for p in props)


class TestPublishedTracker:
    def test_add_and_persist(self, tmp_path):
        pf = tmp_path / "published.jsonl"
        tracker = PublishedTracker(pf)
        tracker.add(PublishedArticle(
            article_id="test123", platform="juejin",
            date="2026-05-14", title="Test", topics=["AI"],
        ))
        tracker.save()
        assert tracker.count == 1

        tracker2 = PublishedTracker(pf)
        tracker2.load()
        assert tracker2.count == 1
        assert tracker2.articles[0].article_id == "test123"

    def test_update_stats(self):
        import tempfile
        tracker = PublishedTracker(tempfile.mkdtemp() + "/p.json")
        tracker.add(PublishedArticle(article_id="a1", platform="juejin", date="2026-05-14"))
        tracker.update_stats("a1", "juejin", {"views": 100, "likes": 5})
        assert tracker.articles[0].stats["views"] == 100

    def test_dedup(self):
        import tempfile
        tracker = PublishedTracker(tempfile.mkdtemp() + "/p.json")
        tracker.add(PublishedArticle(article_id="a1", platform="juejin", date="2026-05-14"))
        tracker.add(PublishedArticle(article_id="a1", platform="juejin", date="2026-05-14"))
        assert tracker.count == 1


class TestPlatformStatsScraper:
    @pytest.mark.asyncio
    async def test_noop_without_user_id(self):
        import tempfile
        tracker = PublishedTracker(tempfile.mkdtemp() + "/p.json")
        tracker.add(PublishedArticle(article_id="a1", platform="juejin", date="2026-05-14"))
        scraper = PlatformStatsScraper(tracker=tracker, scrape_interval_ticks=1)
        await scraper.start()
        ps = await scraper.poll()
        assert len(ps) == 0  # 没有 user_id 时不采集
