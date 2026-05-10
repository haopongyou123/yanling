"""进化引擎测试."""

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
from yanling.kernel.evolution import EvolutionEngine, PerformanceTracker, StrategySnapshot
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

        # 触发深度进化
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
