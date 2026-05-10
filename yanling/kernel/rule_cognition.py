"""规则认知引擎 — 无需 LLM 的规则驱动决策，用于本地/离线场景。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from yanling.core.types import (
    Action,
    CognitionResult,
    Decision,
    Intent,
    Percept,
)

log = logging.getLogger("yanling.cognition.rule")


@dataclass
class Rule:
    """决策规则 — 条件匹配 + 行动产出。"""
    name: str
    match: Callable[[list[Percept]], bool]  # 匹配函数
    intent: Intent = Intent.ACT
    actions: list[Action] | Callable[[list[Percept]], list[Action]] | None = None
    confidence: float = 0.8
    priority: int = 0


class RuleCognitiveEngine:
    """规则驱动认知引擎 — 按优先级匹配规则，产出决策。"""

    def __init__(self):
        self._rules: list[Rule] = []
        self._last_match: str | None = None

    def add_rule(self, rule: Rule):
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, name: str):
        self._rules = [r for r in self._rules if r.name != name]

    async def reason(
        self,
        percepts: list[Percept],
        context: dict | None = None,
    ) -> CognitionResult:
        start = time.time()

        if not percepts:
            return CognitionResult(
                decisions=[Decision(intent=Intent.SLEEP, reason="无感知输入")],
                duration=time.time() - start,
            )

        for rule in self._rules:
            if rule.match(percepts):
                self._last_match = rule.name

                actions = rule.actions(percepts) if callable(rule.actions) else (rule.actions or [])

                log.info("规则匹配 [%s]: %d 个行动", rule.name, len(actions))
                return CognitionResult(
                    decisions=[Decision(
                        intent=rule.intent,
                        reason=f"规则匹配: {rule.name}",
                        actions=actions,
                        confidence=rule.confidence,
                    )],
                    duration=time.time() - start,
                )

        # 无规则匹配
        return CognitionResult(
            decisions=[Decision(intent=Intent.SLEEP, reason="无匹配规则")],
            duration=time.time() - start,
        )


# ─── 预定义规则工厂 ────────────────────────────────────────

def make_alert_rules(sensor_names: list[str] | None = None) -> list[Rule]:
    """创建传感器告警规则。"""
    sensor_names = sensor_names or ["temperature", "vibration", "pressure"]

    rules = []

    for sname in sensor_names:
        # 严重告警规则
        rules.append(Rule(
            name=f"{sname}_critical",
            priority=100,
            match=lambda ps, n=sname: any(
                p.source == f"sensor.{n}" and p.type == "sensor_reading.critical"
                for p in ps
            ),
            actions=lambda ps, n=sname: [
                Action(
                    type="alert",
                    target="alert_logger",
                    params={
                        "level": "critical",
                        "message": f"{n} 严重异常: {next((p.data.get('value') for p in ps if p.source == f'sensor.{n}'), '?')}",
                        "sensor": n,
                    },
                    priority=100,
                ),
                Action(
                    type="adjust",
                    target="device_control",
                    params={"command": "calibrate", "sensor": n},
                    priority=50,
                ),
            ],
        ))

        # 警告规则
        rules.append(Rule(
            name=f"{sname}_warning",
            priority=50,
            match=lambda ps, n=sname: any(
                p.source == f"sensor.{n}" and p.type == "sensor_reading.warning"
                for p in ps
            ),
            actions=lambda ps, n=sname: [
                Action(
                    type="alert",
                    target="alert_logger",
                    params={
                        "level": "warning",
                        "message": f"{n} 超出正常范围: {next((p.data.get('value') for p in ps if p.source == f'sensor.{n}'), '?')}",
                        "sensor": n,
                    },
                    priority=30,
                ),
            ],
        ))

    return rules


def make_heartbeat_rule(interval_ticks: int = 5) -> Rule:
    """心跳日志规则。"""
    _counter: dict = {"tick": 0}

    def _match(ps: list[Percept]) -> bool:
        _counter["tick"] += 1
        return _counter["tick"] % interval_ticks == 0

    return Rule(
        name="heartbeat",
        priority=1,
        match=_match,
        actions=[
            Action(
                type="log",
                target="system_log",
                params={"message": "系统运行正常", "level": "info"},
            ),
        ],
    )
