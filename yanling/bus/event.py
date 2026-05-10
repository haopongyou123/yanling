"""事件类型定义."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Event:
    """总线事件。"""
    type: str
    data: dict = field(default_factory=dict)
    source: str = ""


# 内建事件类型常量
TICK_START = "tick.start"
TICK_END = "tick.end"
PERCEPT_RECEIVED = "percept.received"
DECISION_MADE = "decision.made"
ACTION_EXECUTED = "action.executed"
EVOLUTION_STEP = "evolution.step"
BOUNDARY_VIOLATION = "boundary.violation"
