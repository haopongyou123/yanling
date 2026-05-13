"""边界控制 — Constitutional AI 层.

安全约束、权限管理、费用控制、审计日志。
将"价值观定义 + 行为红线 + 安全保证"作为衍灵的核心基础设施。
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from yanling.core.types import Action, BoundCheckResult

log = logging.getLogger("yanling.boundary")


# ─── 审计条目 ──────────────────────────────────────────────

@dataclass
class AuditEntry:
    """审计日志条目。"""
    timestamp: float
    rule: str
    action_type: str
    action_target: str
    action_id: str
    denied: bool
    reason: str
    metadata: dict = field(default_factory=dict)


# ─── 规则接口 ──────────────────────────────────────────────

class BoundaryRule(ABC):
    """边界规则接口。"""

    @abstractmethod
    def check(self, action: Action) -> BoundCheckResult:
        """检查行动是否合规。返回 denied=True 表示违规。"""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    def category(self) -> str:
        """规则分类：economic | safety | scope | consent | audit."""
        return "general"


# ═══════════════════════════════════════════════════════════
# 经济安全规则
# ═══════════════════════════════════════════════════════════

class CostBoundaryRule(BoundaryRule):
    """费用预算控制 — 按日/月预算限制 API 调用费用。

    费用第一原则的代码落地：任何节点不得在可用免费/本地模型的
    情况下主动调用付费 API。
    """

    def __init__(
        self,
        daily_budget_cents: float = 10.0,    # 日预算（美分）
        monthly_budget_cents: float = 200.0,  # 月预算（美分）
        cost_per_token: dict[str, float] | None = None,
        warn_threshold: float = 0.8,           # 预算 80% 时告警
    ):
        self.daily_budget = daily_budget_cents
        self.monthly_budget = monthly_budget_cents
        self.warn_threshold = warn_threshold

        # 模型费用映射（美元 / 1M tokens）
        self._cost_map = cost_per_token or {
            "deepseek-v4-flash": 0.15,
            "deepseek-v4-pro": 0.35,
            "deepseek-reasoner": 2.00,
            "deepseek-chat": 0.15,
        }
        self._daily_spend: deque[tuple[float, float]] = deque()  # (timestamp, cost)
        self._warned_daily = False
        self._warned_monthly = False
        self._total_spend = 0.0
        self._month_reset_day = datetime.datetime.now().day

    @property
    def name(self) -> str:
        return "cost_budget"

    @property
    def category(self) -> str:
        return "economic"

    def record_usage(self, model: str, tokens: int):
        """记录一次 API 调用费用。"""
        cost_per_m = self._cost_map.get(model, 0.15)
        cost = cost_per_m * tokens / 1_000_000
        now = time.time()
        self._daily_spend.append((now, cost))
        self._total_spend += cost

        # 检查月重置
        today = datetime.datetime.now().day
        if today != self._month_reset_day:
            self._daily_spend.clear()
            self._total_spend = 0.0
            self._month_reset_day = today
            self._warned_daily = False
            self._warned_monthly = False

    def check(self, action: Action) -> BoundCheckResult:
        now = time.time()

        # 清理超过 24h 的记录
        while self._daily_spend and now - self._daily_spend[0][0] > 86400:
            self._daily_spend.popleft()

        daily_total = sum(c for _, c in self._daily_spend)

        # 日预算检查
        if daily_total >= self.daily_budget:
            if not self._warned_daily:
                self._warned_daily = True
                log.warning("日预算耗尽: $%.4f / $%.4f", daily_total, self.daily_budget)
            # 只拦截付费模型调用
            model = action.params.get("model", "")
            if model and model not in ("qwen-turbo", "qwen-plus") and "free" not in model:
                return BoundCheckResult(
                    denied=True,
                    reason=f"日预算已超 ($ {daily_total:.4f} / ${self.daily_budget:.4f})",
                    rule_name=self.name,
                )

        # 预算告警
        ratio = daily_total / self.daily_budget if self.daily_budget > 0 else 0
        if ratio >= self.warn_threshold and not self._warned_daily:
            self._warned_daily = True
            log.warning("日预算使用已达 %.0f%% ($%.4f)", ratio * 100, daily_total)

        return BoundCheckResult(denied=False)

    @property
    def daily_usage(self) -> float:
        now = time.time()
        while self._daily_spend and now - self._daily_spend[0][0] > 86400:
            self._daily_spend.popleft()
        return sum(c for _, c in self._daily_spend)

    @property
    def budget_ratio(self) -> float:
        d = self.daily_usage
        return d / self.daily_budget if self.daily_budget > 0 else 0

    def summary(self) -> dict:
        return {
            "daily_usage": round(self.daily_usage, 4),
            "daily_budget": self.daily_budget,
            "daily_ratio": round(self.budget_ratio, 3),
            "monthly_budget": self.monthly_budget,
            "total_all_time": round(self._total_spend, 4),
            "warned": self._warned_daily,
        }


# ═══════════════════════════════════════════════════════════
# 安全红线规则
# ═══════════════════════════════════════════════════════════

class SafetyBoundaryRule(BoundaryRule):
    """安全红线 — 定义绝对不允许的操作。

    这些是硬红线，不可绕过。对应 Constitutional AI 的
    "核心价值观层"。
    """

    DANGEROUS_TYPES: set[str] = {
        "exec",        # 任意命令执行
        "rm",          # 删除操作
        "shutdown",    # 关机
        "reboot",      # 重启
        "kill",        # 杀进程
    }

    DANGEROUS_TARGETS: set[str] = {
        "/etc", "/usr", "/boot", "/dev", "/proc",
    }

    REQUIRES_CONSENT: set[str] = {
        "deploy",      # 部署
        "publish",     # 发布
        "write_fs",    # 写文件系统
        "modify_fw",   # 修改防火墙
    }

    def __init__(
        self,
        dangerous_types: set[str] | None = None,
        dangerous_targets: set[str] | None = None,
        requires_consent: set[str] | None = None,
        allow_categories: set[str] | None = None,
    ):
        self._dangerous_types = dangerous_types or self.DANGEROUS_TYPES.copy()
        self._dangerous_targets = dangerous_targets or self.DANGEROUS_TARGETS.copy()
        self._requires_consent = requires_consent or self.REQUIRES_CONSENT.copy()
        self._allow_categories = allow_categories or {"notify", "store", "analyze", "read_fs", "timer"}

    @property
    def name(self) -> str:
        return "safety"

    @property
    def category(self) -> str:
        return "safety"

    def check(self, action: Action) -> BoundCheckResult:
        # 硬红线：危险类型
        if action.type in self._dangerous_types:
            return BoundCheckResult(
                denied=True,
                reason=f"安全红线禁止的操作类型: {action.type}",
                rule_name=self.name,
            )

        # 硬红线：危险路径
        target = action.target or ""
        for dangerous in self._dangerous_targets:
            if target.startswith(dangerous) or dangerous in target:
                return BoundCheckResult(
                    denied=True,
                    reason=f"安全红线禁止的目标: {target}",
                    rule_name=self.name,
                )

        # 白名单模式：不在允许列表且不需要同意的，拒绝
        if (
            self._allow_categories
            and action.type not in self._allow_categories
            and action.type not in self._requires_consent
        ):
            return BoundCheckResult(
                denied=True,
                reason=f"不允许的操作类型: {action.type} (白名单: {self._allow_categories})",
                rule_name=self.name,
            )

        return BoundCheckResult(denied=False)


# ═══════════════════════════════════════════════════════════
# 知情同意规则
# ═══════════════════════════════════════════════════════════

class ConsentBoundaryRule(BoundaryRule):
    """知情同意 — 高风险操作需显式确认。

    对应 Constitutional AI 的"人类监督层"：
    - 任何写操作、发布操作、费用变更需用户确认
    - 未经确认的操作要么拒绝，要么推迟到确认
    """

    def __init__(self):
        self._pending: dict[str, Action] = {}
        self._pre_approved: set[str] = set()

    @property
    def name(self) -> str:
        return "consent"

    @property
    def category(self) -> str:
        return "consent"

    def check(self, action: Action) -> BoundCheckResult:
        # 已预先批准的操作跳过
        if action.id in self._pre_approved:
            return BoundCheckResult(denied=False)

        # 需要同意的操作类型
        consent_types = {
            "publish", "deploy", "write_fs", "modify_fw",
            "exec_command", "install", "delete", "batch",
        }
        if action.type in consent_types:
            self._pending[action.id] = action
            return BoundCheckResult(
                denied=True,
                reason=f"操作 {action.type}({action.target}) 需要用户确认",
                rule_name=self.name,
            )

        return BoundCheckResult(denied=False)

    def approve(self, action_id: str) -> bool:
        """批准操作。"""
        if action_id in self._pending:
            self._pre_approved.add(action_id)
            del self._pending[action_id]
            return True
        return False

    def reject(self, action_id: str) -> bool:
        """拒绝操作。"""
        return bool(self._pending.pop(action_id, None))

    @property
    def pending_actions(self) -> list[dict]:
        return [
            {"id": aid, "type": a.type, "target": a.target, "params": a.params}
            for aid, a in self._pending.items()
        ]


# ═══════════════════════════════════════════════════════════
# 速率与时间规则（已有增强版）
# ═══════════════════════════════════════════════════════════

class RateLimitRule(BoundaryRule):
    """速率限制 — 令牌桶算法（增强版：支持按类型分级）。"""

    def __init__(
        self,
        max_per_minute: int = 10,
        max_per_hour: int = 200,
        per_type_limits: dict[str, int] | None = None,
    ):
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self._per_type_limits = per_type_limits or {
            "publish": 2,      # 发布操作每分钟最多 2 次
            "notify": 5,       # 通知每分钟最多 5 次
        }
        self._global_minute: deque[float] = deque()
        self._global_hour: deque[float] = deque()
        self._type_counts: dict[str, deque[float]] = {}

    @property
    def name(self) -> str:
        return "rate_limit"

    def check(self, action: Action) -> BoundCheckResult:
        now = time.time()
        self._cleanup(now)

        # 全局速率
        if len(self._global_minute) >= self.max_per_minute:
            return BoundCheckResult(
                denied=True, reason="超过全局每分钟速率限制", rule_name=self.name)
        if len(self._global_hour) >= self.max_per_hour:
            return BoundCheckResult(
                denied=True, reason="超过全局每小时速率限制", rule_name=self.name)

        # 按类型速率
        type_limit = self._per_type_limits.get(action.type, 0)
        if type_limit > 0:
            type_deque = self._type_counts.setdefault(action.type, deque())
            while type_deque and now - type_deque[0] > 60:
                type_deque.popleft()
            if len(type_deque) >= type_limit:
                return BoundCheckResult(
                    denied=True,
                    reason=f"操作 {action.type} 超过每分钟 {type_limit} 次限制",
                    rule_name=self.name,
                )
            type_deque.append(now)

        self._global_minute.append(now)
        self._global_hour.append(now)
        return BoundCheckResult(denied=False)

    def _cleanup(self, now: float):
        while self._global_minute and now - self._global_minute[0] > 60:
            self._global_minute.popleft()
        while self._global_hour and now - self._global_hour[0] > 3600:
            self._global_hour.popleft()

    async def wait_if_needed(self):
        while True:
            now = time.time()
            self._cleanup(now)
            if len(self._global_minute) < self.max_per_minute:
                return
            await asyncio.sleep(1.0)


class ScopeRule(BoundaryRule):
    """操作范围限制（支持节点角色感知）。"""

    def __init__(self, allowed_types: list[str] | None = None):
        self.allowed_types = set(allowed_types or [
            "notify", "store", "analyze", "read_fs", "timer", "report",
        ])

    @property
    def name(self) -> str:
        return "scope"

    def check(self, action: Action) -> BoundCheckResult:
        if action.type not in self.allowed_types:
            return BoundCheckResult(
                denied=True,
                reason=f"不允许的操作类型: {action.type} (允许: {self.allowed_types})",
                rule_name=self.name,
            )
        return BoundCheckResult(denied=False)


class TimeWindowRule(BoundaryRule):
    """时间窗口限制（支持多窗口）。"""

    def __init__(self, windows: list[tuple[int, int]] | None = None):
        self.windows = windows or [(6, 23)]  # 默认 6:00-23:00

    @property
    def name(self) -> str:
        return "time_window"

    def _in_window(self, h: int) -> bool:
        return any(start <= h < end for start, end in self.windows)

    def check(self, action: Action) -> BoundCheckResult:
        h = datetime.datetime.now().hour
        if not self._in_window(h):
            windows_str = ", ".join(f"{s}:00-{e}:00" for s, e in self.windows)
            return BoundCheckResult(
                denied=True,
                reason=f"当前时间 {h}:00 不在运行窗口 ({windows_str})",
                rule_name=self.name,
            )
        return BoundCheckResult(denied=False)


# ═══════════════════════════════════════════════════════════
# 审计日志
# ═══════════════════════════════════════════════════════════

class AuditLogger:
    """审计日志 — 记录所有边界检查结果。

    持久化到 CSV / JSONL，支持查询和报告生成。
    """

    def __init__(self, log_dir: str = ""):
        if not log_dir:
            log_dir = os.environ.get("YANLING_BOUNDARY_LOG", "")
        if not log_dir:
            log_dir = os.path.join(
                os.environ.get("YANLING_STORAGE_PATH", os.path.expanduser("~/.yanling")),
                "audit",
            )
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._entries: list[AuditEntry] = []
        self._csv_writer = None
        self._csv_file = None
        self._daily_rotate()

    def _daily_rotate(self):
        today = datetime.datetime.now().strftime("%Y%m%d")
        csv_path = self._log_dir / f"audit_{today}.csv"
        try:
            self._csv_file = open(csv_path, "a", newline="")  # noqa: SIM115
            self._csv_writer = csv.writer(self._csv_file)
            if self._csv_file.tell() == 0:
                self._csv_writer.writerow([
                    "timestamp", "rule", "action_type", "action_target",
                    "action_id", "denied", "reason",
                ])
        except OSError as e:
            log.warning("审计 CSV 写入失败: %s", e)
            self._csv_writer = None

    def log(self, rule: str, action: Action, result: BoundCheckResult, meta: dict | None = None):
        entry = AuditEntry(
            timestamp=time.time(),
            rule=rule,
            action_type=action.type,
            action_target=action.target,
            action_id=action.id,
            denied=result.denied,
            reason=result.reason,
            metadata=meta or {},
        )
        self._entries.append(entry)

        # CSV 持久化
        if self._csv_writer:
            try:
                self._csv_writer.writerow([
                    entry.timestamp, entry.rule, entry.action_type,
                    entry.action_target, entry.action_id, entry.denied,
                    entry.reason,
                ])
                self._csv_file.flush()
            except OSError as e:
                log.warning("审计 CSV 写入失败: %s", e)

        # 保留内存中最近 1000 条
        if len(self._entries) > 1000:
            self._entries = self._entries[-500:]

    def recent(self, n: int = 50) -> list[AuditEntry]:
        return self._entries[-n:]

    def summary(self, since: float = 0) -> dict:
        filtered = [e for e in self._entries if e.timestamp >= since]
        total = len(filtered)
        denied = sum(1 for e in filtered if e.denied)
        by_rule: dict[str, int] = {}
        for e in filtered:
            by_rule[e.rule] = by_rule.get(e.rule, 0) + 1
        return {
            "total_checks": total,
            "denied": denied,
            "allowed": total - denied,
            "by_rule": by_rule,
            "deny_rate": round(denied / total, 3) if total > 0 else 0,
        }

    def close(self):
        if self._csv_file:
            self._csv_file.close()
            self._csv_file = None


# ═══════════════════════════════════════════════════════════
# 边界控制器 — 主入口
# ═══════════════════════════════════════════════════════════

class BoundaryControl:
    """边界控制器 — 组合所有规则 + 审计日志。

    Constitutional AI 的"审判层"：所有行动经过所有规则检查，
    任何一条规则拒绝则行动被拦截，所有结果写入审计日志。
    """

    def __init__(
        self,
        rules: list[BoundaryRule] | None = None,
        audit: AuditLogger | None = None,
    ):
        self._rules = rules or [
            SafetyBoundaryRule(),
            RateLimitRule(),
            ScopeRule(),
            TimeWindowRule(),
            CostBoundaryRule(),
        ]
        self._audit = audit or AuditLogger()

    @property
    def audit(self) -> AuditLogger:
        return self._audit

    @property
    def rules(self) -> list[BoundaryRule]:
        return list(self._rules)

    def add_rule(self, rule: BoundaryRule):
        self._rules.append(rule)

    @classmethod
    def from_profile(cls, profile_path: str) -> BoundaryControl:
        """从 YAML 边界策略文件加载完整 Constitution 配置。"""
        try:
            import yaml
        except ImportError:
            log.warning("yaml 模块不可用，使用默认规则")
            return cls()

        with open(profile_path) as f:
            data = yaml.safe_load(f)

        rules: list[BoundaryRule] = []
        b = data.get("boundaries", {}) if data else {}

        # 安全红线
        safety = b.get("safety", {})
        safety_rules = SafetyBoundaryRule(
            dangerous_types=set(safety.get("dangerous_types", [])),
            dangerous_targets=set(safety.get("dangerous_targets", [])),
            requires_consent=set(safety.get("requires_consent", [])),
            allow_categories=set(safety.get("allow_categories", [])),
        ) if safety.get("enabled", True) else None

        # 操作范围
        scope = b.get("scope", {})
        scope_rule = ScopeRule(
            allowed_types=scope.get("allowed_types", None),
        ) if scope.get("enabled", True) else None

        # 速率限制
        rate = b.get("rate_limit", {})
        rate_rule = RateLimitRule(
            max_per_minute=rate.get("max_per_minute", 10),
            max_per_hour=rate.get("max_per_hour", 200),
            per_type_limits=rate.get("per_type_limits", None),
        ) if rate.get("enabled", True) else None

        # 时间窗口
        tw = b.get("time_window", {})
        windows_raw = tw.get("windows", None)
        windows = (
            [(w["start"], w["end"]) for w in windows_raw] if windows_raw else None
        )
        tw_rule = TimeWindowRule(windows=windows) if tw.get("enabled", True) else None

        # 费用预算
        cost = b.get("cost", {})
        cost_rule = CostBoundaryRule(
            daily_budget_cents=cost.get("daily_budget_cents", 10.0),
            monthly_budget_cents=cost.get("monthly_budget_cents", 200.0),
            cost_per_token=cost.get("cost_per_token", None),
            warn_threshold=cost.get("warn_threshold", 0.8),
        ) if cost.get("enabled", True) else None

        for rule in (safety_rules, scope_rule, rate_rule, tw_rule, cost_rule):
            if rule is not None:
                rules.append(rule)

        # 知情同意
        consent = b.get("consent", {})
        if consent.get("enabled", True):
            rules.append(ConsentBoundaryRule())

        log.info("从 %s 加载边界策略: %d 条规则", profile_path, len(rules))
        return cls(rules=rules)

    def check(self, action: Action) -> BoundCheckResult:
        """检查行动是否在所有规则范围内 + 审计。"""
        for rule in self._rules:
            try:
                result = rule.check(action)
                self._audit.log(rule.name, action, result, {
                    "category": getattr(rule, "category", "general"),
                })
                if result.denied:
                    log.info("边界违规 [%s]: %s", rule.name, result.reason)
                    return result
            except Exception as e:
                log.error("边界规则 %s 执行异常: %s", rule.name, e)
                # 规则异常时默认拒绝（安全优先）
                err_result = BoundCheckResult(
                    denied=True,
                    reason=f"规则 {rule.name} 异常: {e}",
                    rule_name=rule.name,
                )
                self._audit.log(rule.name, action, err_result, {"error": str(e)})
                return err_result

        return BoundCheckResult(denied=False)

    async def throttle(self):
        """平滑节流。"""
        for rule in self._rules:
            if isinstance(rule, RateLimitRule):
                await rule.wait_if_needed()

    def get_pending_consent(self) -> list[dict]:
        """获取待审批操作列表。"""
        for rule in self._rules:
            if isinstance(rule, ConsentBoundaryRule):
                return rule.pending_actions
        return []

    def approve_action(self, action_id: str) -> bool:
        """批准待审批操作。"""
        for rule in self._rules:
            if isinstance(rule, ConsentBoundaryRule):
                return rule.approve(action_id)
        return False

    def reject_action(self, action_id: str) -> bool:
        """拒绝待审批操作。"""
        for rule in self._rules:
            if isinstance(rule, ConsentBoundaryRule):
                return rule.reject(action_id)
        return False

    def cost_summary(self) -> dict | None:
        """获取费用摘要（如果有 CostBoundaryRule）。"""
        for rule in self._rules:
            if isinstance(rule, CostBoundaryRule):
                return rule.summary()
        return None

    def audit_summary(self) -> dict:
        return self._audit.summary(since=time.time() - 3600)
