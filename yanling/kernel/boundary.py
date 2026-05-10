"""边界控制 — 安全约束与权限管理."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import deque

from yanling.core.types import Action, BoundCheckResult

log = logging.getLogger("yanling.boundary")


class BoundaryRule(ABC):
    """边界规则接口。"""

    @abstractmethod
    def check(self, action: Action) -> BoundCheckResult:
        """检查行动是否合规。返回 denied=True 表示违规。"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


class RateLimitRule(BoundaryRule):
    """速率限制规则 — 令牌桶算法。"""

    def __init__(self, max_per_minute: int = 10, max_per_hour: int = 200):
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self._timestamps_minute: deque[float] = deque()
        self._timestamps_hour: deque[float] = deque()

    @property
    def name(self) -> str:
        return "rate_limit"

    def check(self, action: Action) -> BoundCheckResult:
        now = time.time()
        self._cleanup(now)

        if len(self._timestamps_minute) >= self.max_per_minute:
            return BoundCheckResult(denied=True, reason="超过每分钟速率限制", rule_name=self.name)
        if len(self._timestamps_hour) >= self.max_per_hour:
            return BoundCheckResult(denied=True, reason="超过每小时速率限制", rule_name=self.name)

        self._timestamps_minute.append(now)
        self._timestamps_hour.append(now)
        return BoundCheckResult(denied=False)

    def _cleanup(self, now: float):
        while self._timestamps_minute and now - self._timestamps_minute[0] > 60:
            self._timestamps_minute.popleft()
        while self._timestamps_hour and now - self._timestamps_hour[0] > 3600:
            self._timestamps_hour.popleft()

    async def wait_if_needed(self):
        """阻塞直到有配额。"""
        while True:
            now = time.time()
            self._cleanup(now)
            if len(self._timestamps_minute) < self.max_per_minute:
                return
            await asyncio.sleep(1.0)


class ScopeRule(BoundaryRule):
    """操作范围限制。"""

    def __init__(self, allowed_types: list[str] | None = None):
        self.allowed_types = set(allowed_types or ["notify", "store", "analyze"])

    @property
    def name(self) -> str:
        return "scope"

    def check(self, action: Action) -> BoundCheckResult:
        if action.type not in self.allowed_types:
            return BoundCheckResult(
                denied=True,
                reason=f"不允许的行动类型: {action.type} (允许: {self.allowed_types})",
                rule_name=self.name,
            )
        return BoundCheckResult(denied=False)


class TimeWindowRule(BoundaryRule):
    """时间窗口限制。"""

    def __init__(self, start_hour: int = 6, end_hour: int = 23):
        self.start_hour = start_hour
        self.end_hour = end_hour

    @property
    def name(self) -> str:
        return "time_window"

    def check(self, action: Action) -> BoundCheckResult:
        import datetime
        h = datetime.datetime.now().hour
        if h < self.start_hour or h >= self.end_hour:
            return BoundCheckResult(
                denied=True,
                reason=f"当前时间 {h}:00 不在运行窗口 ({self.start_hour}:00-{self.end_hour}:00)",
                rule_name=self.name,
            )
        return BoundCheckResult(denied=False)


class BoundaryControl:
    """边界控制器 — 组合多个边界规则。"""

    def __init__(self, rules: list[BoundaryRule] | None = None):
        self._rules = rules or [
            RateLimitRule(),
            ScopeRule(),
            TimeWindowRule(),
        ]

    def add_rule(self, rule: BoundaryRule):
        self._rules.append(rule)

    @classmethod
    def from_profile(cls, profile_path: str) -> BoundaryControl:
        """从 YAML 边界策略文件加载规则。"""
        import yaml
        with open(profile_path) as f:
            data = yaml.safe_load(f)

        rules: list[BoundaryRule] = []
        b = data.get("boundaries", {}) if data else {}

        # ScopeRule
        scope = b.get("scope", {})
        if scope.get("allowed_types"):
            rules.append(ScopeRule(allowed_types=scope["allowed_types"]))

        # RateLimitRule
        rate = b.get("rate_limit", {})
        rules.append(RateLimitRule(
            max_per_minute=rate.get("max_per_minute", 10),
            max_per_hour=rate.get("max_per_hour", 200),
        ))

        # TimeWindowRule
        tw = b.get("time_window", {})
        rules.append(TimeWindowRule(
            start_hour=tw.get("start_hour", 0),
            end_hour=tw.get("end_hour", 24),
        ))

        log.info("从 %s 加载边界策略: %d 条规则", profile_path, len(rules))
        return cls(rules=rules)

    def check(self, action: Action) -> BoundCheckResult:
        """检查行动是否在所有规则范围内。"""
        for rule in self._rules:
            result = rule.check(action)
            if result.denied:
                log.warning("边界违规 [%s]: %s", rule.name, result.reason)
                return result
        return BoundCheckResult(denied=False)

    async def throttle(self):
        """平滑节流 — 等待速率配额。"""
        for rule in self._rules:
            if isinstance(rule, RateLimitRule):
                await rule.wait_if_needed()
