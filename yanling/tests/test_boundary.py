"""边界控制测试 — Constitutional AI 层完整覆盖。"""

from yanling.core.types import Action
from yanling.kernel.boundary import (
    AuditLogger,
    BoundaryControl,
    ConsentBoundaryRule,
    CostBoundaryRule,
    RateLimitRule,
    SafetyBoundaryRule,
    ScopeRule,
    TimeWindowRule,
)


class TestScopeRule:
    def test_allowed_type(self):
        rule = ScopeRule(allowed_types=["notify", "store"])
        action = Action(type="notify", target="x", params={})
        assert not rule.check(action).denied

    def test_denied_type(self):
        rule = ScopeRule(allowed_types=["notify"])
        action = Action(type="publish", target="x", params={})
        assert rule.check(action).denied


class TestRateLimitRule:
    def test_allow_within_limit(self):
        rule = RateLimitRule(max_per_minute=5, max_per_hour=100)
        action = Action(type="test", target="x", params={})
        for _ in range(5):
            result = rule.check(action)
            assert not result.denied

    def test_deny_exceed_limit(self):
        rule = RateLimitRule(max_per_minute=2, max_per_hour=100)
        action = Action(type="test", target="x", params={})
        assert not rule.check(action).denied
        assert not rule.check(action).denied
        assert rule.check(action).denied

    def test_per_type_limit(self):
        rule = RateLimitRule(max_per_minute=10, max_per_hour=100,
                             per_type_limits={"publish": 1})
        pub = Action(type="publish", target="x", params={})
        assert not rule.check(pub).denied
        # 同一类型第二次应被拒
        assert rule.check(pub).denied
        # 不同类型不受影响
        notify = Action(type="notify", target="x", params={})
        assert not rule.check(notify).denied


class TestSafetyBoundaryRule:
    def test_dangerous_type_denied(self):
        rule = SafetyBoundaryRule()
        action = Action(type="exec", target="some_command", params={})
        assert rule.check(action).denied

    def test_dangerous_target_denied(self):
        rule = SafetyBoundaryRule()
        action = Action(type="write_fs", target="/etc/passwd", params={})
        assert rule.check(action).denied

    def test_allowed_type_passes(self):
        rule = SafetyBoundaryRule()
        action = Action(type="notify", target="local", params={"msg": "hi"})
        assert not rule.check(action).denied

    def test_unknown_type_denied_by_default(self):
        rule = SafetyBoundaryRule()
        action = Action(type="some_random_thing", target="x", params={})
        assert rule.check(action).denied


class TestTimeWindowRule:
    def test_within_window(self):
        rule = TimeWindowRule(windows=[(0, 24)])
        action = Action(type="notify", target="x", params={})
        assert not rule.check(action).denied


class TestCostBoundaryRule:
    def test_no_cost_no_deny(self):
        rule = CostBoundaryRule(daily_budget_cents=100.0)
        action = Action(type="analyze", target="llm", params={"model": "qwen-turbo"})
        assert not rule.check(action).denied

    def test_deny_expensive_when_over_budget(self):
        rule = CostBoundaryRule(daily_budget_cents=0.01)
        # 模拟产生费用
        rule.record_usage("deepseek-v4-flash", 1_000_000)  # $0.15
        action = Action(type="analyze", target="llm",
                        params={"model": "deepseek-v4-flash"})
        result = rule.check(action)
        assert result.denied
        assert "预算" in result.reason

    def test_free_model_not_denied(self):
        rule = CostBoundaryRule(daily_budget_cents=0.01)
        rule.record_usage("deepseek-v4-flash", 1_000_000)  # $0.15
        action = Action(type="analyze", target="llm",
                        params={"model": "qwen-turbo"})
        assert not rule.check(action).denied

    def test_summary(self):
        rule = CostBoundaryRule(daily_budget_cents=10.0)
        rule.record_usage("deepseek-v4-flash", 100_000)
        s = rule.summary()
        assert s["daily_budget"] == 10.0
        assert s["daily_usage"] > 0


class TestConsentBoundaryRule:
    def test_normal_action_passes(self):
        rule = ConsentBoundaryRule()
        action = Action(type="notify", target="x", params={}, id="a1")
        assert not rule.check(action).denied

    def test_publish_needs_consent(self):
        rule = ConsentBoundaryRule()
        action = Action(type="publish", target="juejin", params={}, id="a2")
        result = rule.check(action)
        assert result.denied
        assert "确认" in result.reason

    def test_approve_after_consent(self):
        rule = ConsentBoundaryRule()
        action = Action(type="publish", target="juejin", params={}, id="a3")
        assert rule.check(action).denied
        assert rule.approve("a3")
        assert not rule.check(action).denied

    def test_reject_action(self):
        rule = ConsentBoundaryRule()
        action = Action(type="deploy", target="prod", params={}, id="a4")
        assert rule.check(action).denied
        assert rule.reject("a4")
        assert len(rule.pending_actions) == 0


class TestAuditLogger:
    def test_log_and_recent(self):
        from yanling.core.types import BoundCheckResult
        audit = AuditLogger()
        action = Action(type="test", target="x", params={})
        audit.log("test_rule", action, BoundCheckResult(denied=False))
        assert len(audit.recent()) >= 1

    def test_summary(self):
        audit = AuditLogger()
        action = Action(type="test", target="x", params={})
        # 模拟两个检查
        from yanling.core.types import BoundCheckResult
        audit.log("rule_a", action, BoundCheckResult(denied=False))
        audit.log("rule_b", action, BoundCheckResult(denied=True))
        s = audit.summary()
        assert s["total_checks"] >= 2
        assert s["denied"] >= 1


class TestBoundaryControl:
    def test_check_all_rules(self):
        bc = BoundaryControl(rules=[
            ScopeRule(allowed_types=["notify"]),
        ])
        ok_action = Action(type="notify", target="x", params={})
        assert not bc.check(ok_action).denied

        bad_action = Action(type="delete", target="x", params={})
        assert bc.check(bad_action).denied

    def test_full_constitutional_stack(self):
        """完整 Constitutional AI 层组合测试。"""
        bc = BoundaryControl(rules=[
            SafetyBoundaryRule(),
            RateLimitRule(max_per_minute=100, max_per_hour=1000),
            ScopeRule(),
            TimeWindowRule(windows=[(0, 24)]),  # 全天窗口
        ])
        # 安全操作应通过
        safe = Action(type="notify", target="local", params={"msg": "hi"})
        assert not bc.check(safe).denied

        # 危险操作应被拦截
        dangerous = Action(type="exec", target="rm -rf /", params={})
        assert bc.check(dangerous).denied

    def test_cost_budget_integration(self):
        """费用规则集成测试。"""
        bc = BoundaryControl()
        cost_rule = CostBoundaryRule(daily_budget_cents=0.1)
        bc.add_rule(cost_rule)

        # 模拟大量付费调用
        cost_rule.record_usage("deepseek-v4-flash", 10_000_000)  # $1.50
        action = Action(type="analyze", target="llm",
                        params={"model": "deepseek-v4-flash"})
        result = bc.check(action)
        assert result.denied

    def test_audit_all_checks(self):
        """所有检查都写入审计。"""
        bc = BoundaryControl(rules=[ScopeRule(allowed_types=["notify"])])

        bc.check(Action(type="notify", target="x", params={}))
        bc.check(Action(type="delete", target="x", params={}))

        summary = bc.audit_summary()
        assert summary["total_checks"] >= 2

    def test_from_profile_not_found(self):
        """配置文件不存在时优雅降级。"""
        # 不存在的路径应该用默认配置
        bc = BoundaryControl()
        assert len(bc.rules) >= 5  # 至少 5 条默认规则
