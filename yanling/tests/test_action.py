"""行动系统测试。"""

import pytest

from yanling.kernel.action import Action, ActionAdapter, ActionResult, ActionSystem


class DummyAdapter(ActionAdapter):
    @property
    def name(self) -> str:
        return "dummy"

    async def execute(self, action: Action) -> ActionResult:
        return ActionResult(action_id=action.id, success=True, output="dummy_ok")

    async def validate(self, action: Action) -> bool:
        return True


class FailAdapter(ActionAdapter):
    @property
    def name(self) -> str:
        return "fail"

    async def execute(self, action: Action) -> ActionResult:
        raise RuntimeError("模拟失败")

    async def validate(self, action: Action) -> bool:
        return True


class TestActionSystem:
    @pytest.mark.asyncio
    async def test_execute_success(self):
        sys = ActionSystem()
        sys.register(DummyAdapter())
        result = await sys.execute(Action(type="test", target="dummy", params={}))
        assert result.success
        assert result.output == "dummy_ok"

    @pytest.mark.asyncio
    async def test_execute_adapter_not_found(self):
        sys = ActionSystem()
        result = await sys.execute(Action(type="test", target="nonexistent", params={}))
        assert not result.success
        assert "未找到" in result.error

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        sys = ActionSystem()
        sys.register(FailAdapter())
        result = await sys.execute(Action(type="test", target="fail", params={}))
        assert not result.success

    @pytest.mark.asyncio
    async def test_execute_all_priority(self):
        sys = ActionSystem()
        sys.register(DummyAdapter())
        results = await sys.execute_all([
            Action(type="a", target="dummy", params={}, priority=1),
            Action(type="b", target="dummy", params={}, priority=10),
        ])
        assert len(results) == 2
