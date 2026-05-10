"""感知系统测试。"""

import pytest

from yanling.kernel.perception import PerceptionSystem, TimerAdapter


class TestTimerAdapter:
    def test_name(self):
        t = TimerAdapter()
        assert t.name == "timer"

    @pytest.mark.asyncio
    async def test_poll(self):
        t = TimerAdapter()
        result = await t.poll()
        assert len(result) == 1
        assert result[0].type == "tick"
        assert result[0].data["count"] == 1


class TestPerceptionSystem:
    @pytest.mark.asyncio
    async def test_register_and_collect(self):
        sys = PerceptionSystem()
        sys.register(TimerAdapter())
        result = await sys.collect()
        assert len(result) == 1
        assert result[0].source == "timer"

    @pytest.mark.asyncio
    async def test_collect_empty(self):
        sys = PerceptionSystem()
        result = await sys.collect()
        assert result == []
