"""世界模型 — 状态追踪 + 事件关联 + 简单因果推理.

衍灵的世界模型模块，构建系统的内部表征：
- 状态历史：滑动窗口追踪系统状态变化
- 事件关联：检测事件之间的共现关系
- 异常检测：基于历史基线的状态偏离判断
- 状态预测：基于历史模式预测下一个最可能的状态

这不引入复杂 ML，而是基于统计的轻量实现。
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from yanling.core.types import Percept
from yanling.kernel.perception import PerceptionAdapter

log = logging.getLogger("yanling.world_model")


# ─── 数据结构 ──────────────────────────────────────────────

@dataclass
class StateSnapshot:
    """系统在某一时刻的快照。"""
    timestamp: float
    tick_id: int
    events: list[dict]                   # [{type, source, key_metric}]

    @classmethod
    def from_percepts(cls, tick_id: int, percepts: list[Percept]) -> StateSnapshot:
        """从一组感知数据创建快照。"""
        events = []
        for p in percepts:
            entry = {
                "type": p.type,
                "source": p.source,
                "timestamp": p.timestamp,
            }
            # 提取关键数值指标
            for key in ("cpu_pct", "mem_pct", "disk_pct", "online",
                        "total_devices", "success_rate", "latency",
                        "temperature", "humidity"):
                if key in p.data:
                    entry[key] = p.data[key]
            events.append(entry)
        return cls(
            timestamp=time.time(),
            tick_id=tick_id,
            events=events,
        )


@dataclass
class Correlation:
    """两个事件类型之间的关联。"""
    antecedent: str                # 前件事件类型
    consequent: str                # 后件事件类型
    count: int = 0                 # 共现次数
    window_ticks: int = 5          # 关联窗口（tick 数）
    probability: float = 0.0       # P(consequent | antecedent)
    avg_gap_ticks: float = 0.0     # 平均间隔 tick 数


@dataclass
class AnomalyReport:
    """异常检测报告。"""
    timestamp: float
    tick_id: int
    anomalies: list[dict] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class StatePrediction:
    """状态预测结果。"""
    predicted_event_types: list[str]    # 最可能的下一个事件类型
    probability: float                  # 最高概率
    horizon_ticks: int = 5              # 预测窗口
    based_on_patterns: int = 0          # 基于的模式数量


# ─── 世界模型 ──────────────────────────────────────────────

class WorldModel:
    """世界模型 — 轻量系统状态表征与推理。

    使用方式:
        model = WorldModel(window_size=100)
        model.observe(tick_id=1, percepts=[...])
        model.observe(tick_id=2, percepts=[...])
        ...
        correlations = model.get_correlations(min_count=3)
        anomalies = model.detect_anomalies(tick_id=10, percepts=[...])
        prediction = model.predict_next(tick_id=10, percepts=[...])
    """

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self._history: deque[StateSnapshot] = deque(maxlen=window_size)
        self._correlations: dict[tuple[str, str], Correlation] = {}
        self._event_timeline: deque[tuple[int, str, str]] = deque(maxlen=500)  # (tick, type, source)
        self._metric_baselines: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=50)
        )
        self._total_ticks_seen = 0

    # ─── 观察 ──────────────────────────────────────────────

    def observe(self, tick_id: int, percepts: list[Percept]):
        """观察一组感知数据，更新世界模型。"""
        self._total_ticks_seen += 1
        snapshot = StateSnapshot.from_percepts(tick_id, percepts)
        self._history.append(snapshot)

        # 更新事件时间线
        for p in percepts:
            self._event_timeline.append((tick_id, p.type, p.source))

        # 提取数值指标并更新基线
        for p in percepts:
            for key in ("cpu_pct", "mem_pct", "disk_pct", "latency"):
                if key in p.data and isinstance(p.data[key], (int, float)):
                    self._metric_baselines[f"{p.source}/{key}"].append(p.data[key])

        # 更新关联表
        self._update_correlations(tick_id)

    def _update_correlations(self, current_tick: int):
        """更新事件关联统计。"""
        recent = list(self._event_timeline)
        if len(recent) < 2:
            return

        # 获取当前 tick 的事件类型
        current_events = {t[1] for t in recent if t[0] == current_tick}
        # 获取前 N tick 的事件类型
        prior_events: dict[str, int] = defaultdict(int)
        for tick, etype, _ in recent:
            if 0 < current_tick - tick <= 5:  # 前 5 tick 内
                prior_events[etype] += 1

        for cur_type in current_events:
            for prior_type, count in prior_events.items():
                if prior_type == cur_type:
                    continue
                key = (prior_type, cur_type)
                if key not in self._correlations:
                    self._correlations[key] = Correlation(
                        antecedent=prior_type,
                        consequent=cur_type,
                        window_ticks=5,
                    )
                corr = self._correlations[key]
                corr.count += count

        # 更新概率
        for key, corr in list(self._correlations.items()):
            total_antecedent = sum(
                1 for t in self._event_timeline if t[1] == corr.antecedent
            )
            if total_antecedent > 0:
                corr.probability = corr.count / total_antecedent

    # ─── 异常检测 ──────────────────────────────────────────

    def detect_anomalies(self, tick_id: int, percepts: list[Percept]) -> AnomalyReport:
        """基于历史基线检测异常。"""
        anomalies: list[dict] = []

        for p in percepts:
            for key in ("cpu_pct", "mem_pct", "disk_pct", "latency"):
                if key not in p.data or not isinstance(p.data[key], (int, float)):
                    continue
                baseline_key = f"{p.source}/{key}"
                values = list(self._metric_baselines.get(baseline_key, []))
                if len(values) < 3:
                    continue
                current = p.data[key]
                avg = sum(values) / len(values)
                variance = sum((v - avg) ** 2 for v in values) / len(values)
                std = math.sqrt(variance) if variance > 0 else 0.001

                # Z-score 异常检测
                z_score = abs(current - avg) / std
                if z_score > 2.5:
                    anomalies.append({
                        "metric": baseline_key,
                        "value": current,
                        "baseline_mean": round(avg, 3),
                        "z_score": round(z_score, 2),
                        "severity": "warning" if z_score < 4 else "critical",
                    })

        return AnomalyReport(
            timestamp=time.time(),
            tick_id=tick_id,
            anomalies=anomalies,
            confidence=0.7 if anomalies else 0.0,
        )

    # ─── 预测 ──────────────────────────────────────────────

    def predict_next(
        self,
        tick_id: int,
        percepts: list[Percept],
        horizon: int = 5,
    ) -> StatePrediction:
        """基于历史模式预测接下来最可能的事件。"""
        current_types = {p.type for p in percepts}
        candidates: dict[str, float] = defaultdict(float)

        for key, corr in self._correlations.items():
            if corr.antecedent in current_types and corr.count >= 2:
                candidates[corr.consequent] += corr.probability

        if not candidates:
            return StatePrediction(
                predicted_event_types=[],
                probability=0.0,
                horizon_ticks=horizon,
                based_on_patterns=0,
            )

        # 排序并取 top-k
        sorted_candidates = sorted(candidates.items(), key=lambda x: -x[1])
        total = sum(c for _, c in sorted_candidates)
        normalized = [(t, c / total) for t, c in sorted_candidates]

        return StatePrediction(
            predicted_event_types=[t for t, _ in normalized[:3]],
            probability=normalized[0][1] if normalized else 0.0,
            horizon_ticks=horizon,
            based_on_patterns=len(self._correlations),
        )

    # ─── 查询 ──────────────────────────────────────────────

    def get_correlations(self, min_count: int = 2) -> list[Correlation]:
        """获取显著的事件关联。"""
        return sorted(
            [c for c in self._correlations.values() if c.count >= min_count],
            key=lambda x: -x.count,
        )

    def get_recent_states(self, n: int = 10) -> list[StateSnapshot]:
        """获取最近的 N 个状态快照。"""
        return list(self._history)[-n:]

    def summary(self) -> dict:
        """世界模型摘要。"""
        return {
            "total_ticks": self._total_ticks_seen,
            "history_size": len(self._history),
            "correlations_tracked": len(self._correlations),
            "significant_correlations": sum(
                1 for c in self._correlations.values() if c.count >= 3
            ),
            "metric_baselines": {
                k: {
                    "mean": round(sum(v) / len(v), 2) if v else 0,
                    "count": len(v),
                }
                for k, v in self._metric_baselines.items()
            },
            "last_tick": self._history[-1].tick_id if self._history else 0,
        }


# ─── 世界模型感知适配器 ──────────────────────────────────

class WorldModelAdapter(PerceptionAdapter):
    """世界模型感知适配器 — 注入世界模型上下文到感知流。

    在每个 tick，世界模型适配器检查异常和预测，作为额外的感知
    注入到认知引擎，使决策者获得"对这个世界的理解"而非孤立事件。
    """

    def __init__(self, model: WorldModel, check_interval: int = 5):
        self.model = model
        self._check_interval = check_interval
        self._tick_count = 0

    @property
    def name(self) -> str:
        return "world_model"

    async def poll(self) -> list[Percept]:
        """产出世界模型感知：异常检测 + 预测 + 摘要。"""
        self._tick_count += 1
        percepts: list[Percept] = []

        if self._tick_count % self._check_interval != 0:
            return percepts

        # 不使用最新 percepts（由 collect 提供），这里只输出世界模型的状态
        summary = self.model.summary()
        correlations = self.model.get_correlations(min_count=3)

        # 关联感知
        if correlations:
            top = correlations[:3]
            percepts.append(Percept(
                source="world_model",
                type="wm.correlations",
                data={
                    "count": len(correlations),
                    "top": [
                        {
                            "antecedent": c.antecedent,
                            "consequent": c.consequent,
                            "probability": round(c.probability, 2),
                            "count": c.count,
                        }
                        for c in top
                    ],
                },
                confidence=0.6,
            ))

        # 摘要感知（避免每次 tick 都输出）
        if summary["history_size"] >= 10:
            percepts.append(Percept(
                source="world_model",
                type="wm.summary",
                data={
                    "total_ticks": summary["total_ticks"],
                    "correlations": summary["correlations_tracked"],
                    "metric_baselines": summary["metric_baselines"],
                },
                confidence=0.8,
            ))

        return percepts
