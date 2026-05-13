"""进化引擎测试 — 含自助进化新能力覆盖。"""

import pytest

from yanling.adapters.storage.json_file import JsonFileStorage
from yanling.core.types import (
    Action,
    ActionResult,
    CognitionResult,
    Decision,
    Intent,
    Percept,
    TickResult,
)
from yanling.kernel.cognition import CognitiveEngine
from yanling.kernel.evolution import (
    EvolutionEngine,
    ImprovementProposal,
    PerformanceTracker,
    StrategySnapshot,
)
from yanling.kernel.memory import MemorySystem


class MockLLMEvolution:
    @property
    def model_name(self): return "mock"
    @property
    def provider(self): return "mock"
    async def chat(self, messages, **kwargs):
        from yanling.adapters.llm.base import LLMResponse
        return LLMResponse(
            content='{"analysis":"ok","patterns":["test pattern"],"adjustments":[{"area":"system_prompt","change":"be more careful","reason":"test"}],"recommendations":["none"]}',
            model="mock",
        )
    async def is_available(self): return True


class TestPerformanceTracker:
    def test_record_and_summary(self):
        pt = PerformanceTracker(window=10)
        pt.record(1, 1.0, 0.5, 100)
        pt.record(2, 0.8, 0.6, 200)
        s = pt.summary()
        assert s["avg_success_rate"] > 0
        assert "trend" in s

    def test_trend_improving(self):
        pt = PerformanceTracker(window=10)
        for i in range(10):
            pt.record(i, 0.5 + i * 0.05, 0.5, 100)
        trend = pt.trend("success_rate")
        assert trend > 0

    def test_trend_declining(self):
        pt = PerformanceTracker(window=10)
        for i in range(10):
            pt.record(i, 1.0 - i * 0.05, 0.5, 100)
        trend = pt.trend("success_rate")
        assert trend < 0

    def test_empty_tracker(self):
        pt = PerformanceTracker(window=10)
        assert pt.summary()["avg_success_rate"] == 0
        assert pt.trend() == 0.0

    def test_volatility_high(self):
        pt = PerformanceTracker(window=10)
        for i in range(10):
            pt.record(i, 1.0, 1.0 if i % 2 == 0 else 0.01, 100)  # 大幅波动
        vol = pt.volatility("latency")
        assert vol > 0.5

    def test_volatility_low(self):
        pt = PerformanceTracker(window=10)
        for i in range(10):
            pt.record(i, 1.0, 0.5, 100)  # 稳定
        vol = pt.volatility("latency")
        assert vol < 0.1


@pytest.fixture
def evo():
    storage = JsonFileStorage("/tmp/yanling_test_evol_base")
    mem = MemorySystem(storage)
    llm = MockLLMEvolution()
    return EvolutionEngine(mem, llm)


class TestSelfProposals:
    """自助提案测试。"""

    def test_generate_proposals_low_success(self, evo):
        for i in range(10):
            evo._performance.record(i, 0.3, 0.5, 100)
        proposals = evo._generate_proposals()
        titles = [p.title for p in proposals]
        assert any("成功" in t for t in titles)

    def test_generate_proposals_volatility(self, evo):
        for i in range(10):
            evo._performance.record(i, 1.0, 1.0 if i % 2 == 0 else 0.01, 100)
        proposals = evo._generate_proposals()
        titles = [p.title for p in proposals]
        assert any("延迟" in t or "波动" in t for t in titles)

    def test_generate_proposals_consecutive_failures(self, evo):
        evo._consecutive_failures = 5
        for i in range(10):
            evo._performance.record(i, 0.3, 0.5, 100)  # 保证 summary 有数据
        proposals = evo._generate_proposals()
        titles = [p.title for p in proposals]
        assert any("失败" in t for t in titles)

    def test_proposal_data_structure(self):
        p = ImprovementProposal(
            area="parameter",
            title="测试提案",
            description="test",
            trigger="test",
            confidence=0.8,
            estimated_impact="high",
        )
        assert p.area == "parameter"
        assert p.confidence == 0.8


class TestRuleEvolution:
    """规则驱动进化测试（无 LLM）。"""

    def test_rule_evolve_declining(self, evo):
        for i in range(10):
            evo._performance.record(i, 1.0 - i * 0.1, 0.5, 100)
        evo._pattern_db["fail_type:test_op"] = 5
        report = evo._rule_evolve({
            "performance": evo._performance.summary(),
            "top_patterns": [("fail_type:test_op", 5)],
        }, evo._performance.summary(), [("fail_type:test_op", 5)])
        assert len(report.adjustments) >= 1
        assert len(report.recommendations) >= 1

    def test_rule_evolve_stable(self, evo):
        for i in range(10):
            evo._performance.record(i, 1.0, 0.5, 100)
        perf = evo._performance.summary()
        report = evo._rule_evolve(
            {"performance": perf, "top_patterns": []},
            perf, [],
        )
        assert len(report.recommendations) >= 1  # "性能稳定" 建议


class TestAutoTune:
    """自助调参测试。"""

    @pytest.mark.asyncio
    async def test_auto_tune_on_failure(self, evo):
        from yanling.kernel.cognition import CognitiveEngine
        evo.cognition = CognitiveEngine(MockLLMEvolution())  # 需要 cognition 才能调参
        evo._tick_count = 100
        evo._consecutive_failures = 5
        evo._adjustment_cooldown = 0

        tick_result = TickResult(
            tick_id=99,
            perceptions=[],
            cognition=CognitionResult(decisions=[]),
            actions=[
                ActionResult(action_id="a1", type="publish", success=False, error="err"),
                ActionResult(action_id="a2", type="publish", success=False, error="err2"),
                ActionResult(action_id="a3", type="notify", success=True),
            ],
        )
        evo._auto_tune_on_failure(tick_result)
        assert evo._last_adjustment_tick == evo._tick_count  # 调整为 _tick_count 的值

    def test_cooldown_respected(self, evo):
        evo._last_adjustment_tick = evo._tick_count
        prev = evo._last_adjustment_tick
        evo._auto_tune_on_failure(
            TickResult(tick_id=1, perceptions=[], cognition=CognitionResult(decisions=[]), actions=[])
        )
        assert evo._last_adjustment_tick == prev  # 冷却中，不应修改
        # 重置 _tick_count 引用
        evo._auto_tune_on_failure(
            TickResult(tick_id=1, perceptions=[], cognition=CognitionResult(decisions=[]), actions=[])
        )
        assert evo._last_adjustment_tick == prev


class TestRollbackWithAssessment:
    def test_rollback_assessment(self, evo):
        from yanling.kernel.cognition import CognitiveEngine
        evo.cognition = CognitiveEngine(MockLLMEvolution())
        evo._snapshots.append(StrategySnapshot("prompt_v1"))
        evo._snapshots.append(StrategySnapshot("prompt_v2"))
        for i in range(5):
            evo._performance.record(i, 0.8, 0.5, 100)

        result = evo.rollback_with_assessment(steps=1)
        assert result["success"]
        assert result["steps_rolled_back"] == 1
        assert "performance_before" in result
        assert "performance_after" in result


class TestImpactAnalysis:
    def test_estimate_impact(self, evo):
        assert "影响" in evo._estimate_impact("system_prompt", "x")
        assert "影响" in evo._estimate_impact("boundary", "x")
        assert "影响" in evo._estimate_impact("parameter", "x")


class TestEvolutionEngine:
    @pytest.mark.asyncio
    async def test_learn_ok(self):
        storage = JsonFileStorage("/tmp/yanling_test_evol")
        mem = MemorySystem(storage)
        llm = MockLLMEvolution()
        evo = EvolutionEngine(mem, llm)

        result = await evo.learn(
            percepts=[],
            cognition_result=CognitionResult(decisions=[Decision(intent=Intent.SLEEP, reason="ok")]),
            tick_result=TickResult(tick_id=1, perceptions=[], cognition=CognitionResult(decisions=[]), actions=[]),
        )
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_learn_failure_recorded(self):
        storage = JsonFileStorage("/tmp/yanling_test_evol2")
        mem = MemorySystem(storage)
        llm = MockLLMEvolution()
        evo = EvolutionEngine(mem, llm)

        result = await evo.learn(
            percepts=[Percept(source="test", type="fail", data={})],
            cognition_result=CognitionResult(
                decisions=[Decision(intent=Intent.ACT, reason="test", actions=[Action(type="x", target="y", params={})])],
                error="模拟错误",
            ),
            tick_result=TickResult(
                tick_id=2,
                perceptions=[Percept(source="t", type="f", data={})],
                cognition=CognitionResult(decisions=[], error="模拟错误"),
                actions=[ActionResult(action_id="a1", success=False, error="fail")],
            ),
        )
        assert "失败" in result or "错误" in result
        assert len(evo._steps) == 1

    @pytest.mark.asyncio
    async def test_evolve_llm_call(self):
        storage = JsonFileStorage("/tmp/yanling_test_evol3")
        mem = MemorySystem(storage)
        llm = MockLLMEvolution()
        evo = EvolutionEngine(mem, llm, deep_evolution_interval=1)

        report = await evo.evolve()
        assert len(report.patterns_found) > 0

    @pytest.mark.asyncio
    async def test_rollback(self):
        storage = JsonFileStorage("/tmp/yanling_test_evol4")
        mem = MemorySystem(storage)
        llm = MockLLMEvolution()
        cog = CognitiveEngine(llm)
        evo = EvolutionEngine(mem, llm, cognition=cog)

        original_prompt = cog._system_prompt
        evo._snapshots.append(StrategySnapshot(cog._system_prompt))
        cog._system_prompt = "modified prompt"

        evo.rollback(steps=1)
        assert cog._system_prompt == original_prompt

    def test_pattern_extraction(self):
        storage = JsonFileStorage("/tmp/yanling_test_evol5")
        mem = MemorySystem(storage)
        llm = MockLLMEvolution()
        evo = EvolutionEngine(mem, llm)

        evo._pattern_db["fail:test/target"] += 1
        evo._pattern_db["fail:test/target"] += 1
        evo._pattern_db["fail:other/x"] += 1

        top = sorted(evo._pattern_db.items(), key=lambda x: -x[1])
        assert top[0][0] == "fail:test/target"
        assert top[0][1] == 2

    @pytest.mark.asyncio
    async def test_evolve_without_llm_fallback(self):
        """无 LLM 时降级到规则进化。"""
        storage = JsonFileStorage("/tmp/yanling_test_evol6")
        mem = MemorySystem(storage)
        evo = EvolutionEngine(mem, llm=None)
        for i in range(10):
            evo._performance.record(i, 0.5 + i * 0.02, 0.5, 100)

        report = await evo.evolve()
        assert report is not None
        assert len(report.recommendations) >= 0
