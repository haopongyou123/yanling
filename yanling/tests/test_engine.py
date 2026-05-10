"""引擎集成测试。"""

import asyncio

import pytest

from yanling.adapters.storage.json_file import JsonFileStorage
from yanling.kernel.action import Action, ActionAdapter, ActionResult, ActionSystem
from yanling.kernel.boundary import BoundaryControl, ScopeRule
from yanling.kernel.engine import YanLingEngine
from yanling.kernel.memory import MemorySystem
from yanling.kernel.perception import Percept, PerceptionAdapter, PerceptionSystem


class EchoActionAdapter(ActionAdapter):
    @property
    def name(self) -> str:
        return "echo"

    async def execute(self, action: Action) -> ActionResult:
        return ActionResult(action_id=action.id, success=True, output=action.params)

    async def validate(self, action: Action) -> bool:
        return True


class SimplePerceptionAdapter(PerceptionAdapter):
    def __init__(self):
        self._count = 0

    @property
    def name(self) -> str:
        return "simple"

    async def poll(self) -> list[Percept]:
        self._count += 1
        if self._count <= 2:
            return [Percept(source="simple", type="test", data={"tick": self._count})]
        return []


class MockLLM:
    """模拟 LLM，返回固定 JSON 决策。"""
    @property
    def model_name(self) -> str:
        return "mock"
    @property
    def provider(self) -> str:
        return "mock"

    async def chat(self, messages, **kwargs):
        from yanling.adapters.llm.base import LLMResponse
        return LLMResponse(
            content='{"decisions": [{"intent": "ACT", "reason": "测试", "actions": [{"type": "echo", "target": "echo", "params": {"msg": "hello"}}], "confidence": 0.9}]}',
            model="mock",
        )

    async def is_available(self):
        return True


@pytest.mark.asyncio
async def test_engine_basic_loop():
    """验证引擎基础循环：感知→认知→行动 链路通顺。"""
    from yanling.kernel.cognition import CognitiveEngine

    storage = JsonFileStorage("/tmp/yanling_test_memory")
    perception = PerceptionSystem()
    perception.register(SimplePerceptionAdapter())

    cognition = CognitiveEngine(MockLLM())

    action_sys = ActionSystem()
    action_sys.register(EchoActionAdapter())

    memory = MemorySystem(storage)
    boundary = BoundaryControl(rules=[ScopeRule(allowed_types=["echo"])])

    engine = YanLingEngine(
        perception=perception,
        cognition=cognition,
        action=action_sys,
        memory=memory,
        boundary=boundary,
    )

    await engine.start()
    await asyncio.sleep(0.5)
    await engine.stop()

    assert engine.lifecycle.state.value == "stopped"
