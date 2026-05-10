"""边界控制测试。"""

from yanling.core.types import Action
from yanling.kernel.boundary import (
    BoundaryControl,
    RateLimitRule,
    ScopeRule,
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
        # 前 5 次应通过
        for _ in range(5):
            result = rule.check(action)
            assert not result.denied

    def test_deny_exceed_limit(self):
        rule = RateLimitRule(max_per_minute=2, max_per_hour=100)
        action = Action(type="test", target="x", params={})
        assert not rule.check(action).denied
        assert not rule.check(action).denied
        assert rule.check(action).denied  # 第三次应被限


class TestBoundaryControl:
    def test_check_all_rules(self):
        bc = BoundaryControl(rules=[
            ScopeRule(allowed_types=["notify"]),
        ])
        ok_action = Action(type="notify", target="x", params={})
        assert not bc.check(ok_action).denied

        bad_action = Action(type="delete", target="x", params={})
        assert bc.check(bad_action).denied
