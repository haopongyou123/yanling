"""核心基础组件测试。"""

import pytest

from yanling.core.clock import Clock
from yanling.core.config import Config
from yanling.core.types import Action, Decision, Intent, Percept


class TestTypes:
    """核心类型测试。"""

    def test_percept_default_timestamp(self):
        p = Percept(source="test", type="ping", data={})
        assert p.timestamp > 0

    def test_action_default_id(self):
        a = Action(type="notify", target="console", params={"msg": "hello"})
        assert a.id == ""  # id 由引擎生成

    def test_decision_intent(self):
        d = Decision(intent=Intent.ANALYZE, reason="测试")
        assert d.intent == Intent.ANALYZE
        assert d.confidence == 0.0  # 默认值


class TestConfig:
    """配置测试。"""

    def test_default_config(self):
        cfg = Config()
        assert cfg.get("kernel", "tick_interval") == 30
        assert cfg.get("llm", "provider") == "deepseek"

    def test_config_get_default(self):
        cfg = Config()
        assert cfg.get("nonexistent", default="fallback") == "fallback"

    def test_schema_validation_type_mismatch(self):
        data = {"kernel": {"tick_interval": "not_an_int"}}
        cfg = Config(data)
        warns = cfg.warnings
        assert any("tick_interval" in w.path for w in warns)

    def test_schema_validation_unknown_field(self):
        data = {"kernel": {"nonexistent_field": 123}}
        cfg = Config(data)
        warns = cfg.warnings
        assert any("未知" in w.message for w in warns)

    def test_yaml_load_nonexistent(self):
        cfg = Config.from_yaml("/tmp/nonexistent_file.yml")
        assert cfg.get("kernel", "tick_interval") == 30


class TestClock:
    """时钟测试。"""

    @pytest.mark.asyncio
    async def test_clock_tick(self):
        clock = Clock(interval=0.01)
        clock.start()
        tick = await clock.next_tick()
        assert tick.number == 1
        assert tick.interval == 0.01
        assert tick.timestamp > 0
        clock.stop()
