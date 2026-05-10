"""健康指标 — 引擎运行时状态收集。"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TickMetrics:
    """单次 tick 的指标快照。"""
    tick_id: int
    percepts: int
    decisions: int
    actions: int
    success_rate: float
    latency: float
    tokens: int = 0
    error: str | None = None


class EngineStats:
    """引擎运行时指标收集器。"""

    def __init__(self, window: int = 100, stats_dir: str | Path | None = None):
        self.window = window
        self._ticks: deque[TickMetrics] = deque(maxlen=window)
        self._start_time = time.time()
        self._stats_dir = Path(stats_dir) if stats_dir else None

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time

    def record_tick(self, metrics: TickMetrics):
        self._ticks.append(metrics)

    def snapshot(self) -> dict:
        """返回当前状态快照。"""
        recent = list(self._ticks)
        total = len(recent)
        if total == 0:
            return {
                "uptime": round(self.uptime, 1),
                "total_ticks": 0,
                "status": "idle",
                "avg_success_rate": 0.0,
                "avg_latency": 0.0,
                "total_errors": 0,
                "ticks_per_sec": 0.0,
                "last_tick": None,
            }

        success_rates = [t.success_rate for t in recent if t.success_rate >= 0]
        latencies = [t.latency for t in recent]
        errors = [t for t in recent if t.error]

        avg_success = sum(success_rates) / len(success_rates) if success_rates else 0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        return {
            "uptime": round(self.uptime, 1),
            "total_ticks": total,
            "status": "running",
            "ticks_per_sec": round(total / self.uptime, 3) if self.uptime > 0 else 0,
            "avg_success_rate": round(avg_success, 3),
            "avg_latency": round(avg_latency, 3),
            "total_errors": len(errors),
            "last_tick": {
                "id": recent[-1].tick_id,
                "percepts": recent[-1].percepts,
                "actions": recent[-1].actions,
                "latency": round(recent[-1].latency, 3),
            } if recent else None,
        }

    async def persist(self):
        if not self._stats_dir:
            return
        self._stats_dir.mkdir(parents=True, exist_ok=True)
        path = self._stats_dir / "stats.json"
        path.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2))
