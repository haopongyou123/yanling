"""规则认知引擎测试。"""

import pytest

from yanling.core.types import Action, Intent, Percept
from yanling.kernel.rule_cognition import (
    Rule,
    RuleCognitiveEngine,
    make_alert_rules,
    make_heartbeat_rule,
)


class TestRuleCognitiveEngine:
    @pytest.mark.asyncio
    async def test_no_percepts_returns_sleep(self):
        engine = RuleCognitiveEngine()
        result = await engine.reason([])
        assert result.decisions[0].intent == Intent.SLEEP

    @pytest.mark.asyncio
    async def test_rule_match(self):
        engine = RuleCognitiveEngine()
        engine.add_rule(Rule(
            name="test_rule",
            match=lambda ps: any(p.type == "alert" for p in ps),
            actions=[Action(type="log", target="syslog", params={"msg": "matched"})],
        ))

        result = await engine.reason([Percept(source="s", type="alert", data={})])
        assert result.decisions[0].intent == Intent.ACT
        assert len(result.decisions[0].actions) == 1

    @pytest.mark.asyncio
    async def test_no_match_returns_sleep(self):
        engine = RuleCognitiveEngine()
        engine.add_rule(Rule(
            name="never_match",
            match=lambda ps: False,
        ))
        result = await engine.reason([Percept(source="s", type="test", data={})])
        assert result.decisions[0].intent == Intent.SLEEP

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        engine = RuleCognitiveEngine()
        results = []

        engine.add_rule(Rule(name="low", priority=1, match=lambda ps: True,
                              actions=[Action(type="log", target="x", params={"level": "low"})]))
        engine.add_rule(Rule(name="high", priority=100, match=lambda ps: True,
                              actions=[Action(type="alert", target="x", params={"level": "high"})]))

        result = await engine.reason([Percept(source="s", type="t", data={})])
        # 高优先级规则应先匹配
        assert result.decisions[0].reason == "规则匹配: high"

    def test_dynamic_actions(self):
        """验证 callable actions 可以基于感知数据动态生成行动。"""
        call_count = 0

        def action_fn(ps):
            nonlocal call_count
            call_count += 1
            return [Action(type="test", target="x", params={"count": call_count})]

        engine = RuleCognitiveEngine()
        engine.add_rule(Rule(name="dynamic", match=lambda ps: True, actions=action_fn))

        import asyncio
        result = asyncio.run(engine.reason([Percept(source="s", type="t", data={})]))
        assert len(result.decisions[0].actions) == 1


class TestMakeAlertRules:
    def test_critical_rule_matches_critical_percept(self):
        rules = make_alert_rules(["temperature"])
        critical_rule = [r for r in rules if r.name == "temperature_critical"][0]
        assert critical_rule.priority == 100

    def test_warning_rule_matches_warning_percept(self):
        rules = make_alert_rules(["vibration"])
        warning_rule = [r for r in rules if r.name == "vibration_warning"][0]
        assert warning_rule.priority == 50

    def test_heartbeat_rule_ticks(self):
        """验证心跳规则按间隔触发。"""
        rule = make_heartbeat_rule(interval_ticks=2)
        ps = [Percept(source="s", type="t", data={})]

        # match 函数内含 tick 计数器
        assert rule.match(ps) is False  # tick 1
        assert rule.match(ps) is True   # tick 2
        assert rule.match(ps) is False  # tick 3
        assert rule.match(ps) is True   # tick 4
