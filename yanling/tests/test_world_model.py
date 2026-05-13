"""世界模型测试。"""

import pytest

from yanling.core.types import Percept
from yanling.kernel.world_model import (
    AnomalyReport,
    Correlation,
    StatePrediction,
    StateSnapshot,
    WorldModel,
    WorldModelAdapter,
)


def make_percept(type_: str, source: str = "sensor", **data) -> Percept:
    return Percept(source=source, type=type_, data=data)


class TestStateSnapshot:
    def test_from_percepts(self):
        ps = [
            make_percept("system.status", cpu_pct=45.0, mem_pct=60.0),
            make_percept("device.status", online=True),
        ]
        snap = StateSnapshot.from_percepts(tick_id=1, percepts=ps)
        assert snap.tick_id == 1
        assert len(snap.events) == 2
        assert snap.events[0]["cpu_pct"] == 45.0
        assert snap.events[1]["online"] is True

    def test_empty_percepts(self):
        snap = StateSnapshot.from_percepts(tick_id=5, percepts=[])
        assert snap.tick_id == 5
        assert snap.events == []


class TestWorldModel:
    def test_observe_and_history(self):
        model = WorldModel(window_size=10)
        model.observe(1, [
            make_percept("system.status", cpu_pct=50),
            make_percept("device.status", online=True),
        ])
        assert model._total_ticks_seen == 1
        assert len(model._history) == 1

    def test_event_timeline(self):
        model = WorldModel()
        model.observe(1, [make_percept("alert.cpu")])
        model.observe(2, [make_percept("action.respond")])
        assert len(model._event_timeline) == 2

    def test_correlations(self):
        model = WorldModel()
        for tick in range(10):
            percepts = [make_percept("tick")]
            if tick % 3 == 0:
                percepts.append(make_percept("alert.cpu"))
            if tick > 0 and (tick - 1) % 3 == 0:
                percepts.append(make_percept("action.scale"))
            model.observe(tick, percepts)

        corrs = model.get_correlations(min_count=1)
        assert len(corrs) >= 1

    def test_anomaly_detection_zscore(self):
        model = WorldModel()
        # 建立基线：cpu_pct 接近 50
        for i in range(20):
            model.observe(i, [make_percept("system.status", cpu_pct=50.0 + i * 0.1)])

        # 异常值
        report = model.detect_anomalies(21, [
            make_percept("system.status", cpu_pct=99.0),
        ])
        assert len(report.anomalies) >= 1
        assert any(a["severity"] == "critical" for a in report.anomalies)

    def test_no_anomaly_when_baseline_small(self):
        model = WorldModel()
        model.observe(1, [make_percept("system.status", cpu_pct=99.0)])
        report = model.detect_anomalies(2, [
            make_percept("system.status", cpu_pct=99.0),
        ])
        # 数据点少于 3 个，不检测
        assert len(report.anomalies) == 0

    def test_prediction_with_correlations(self):
        model = WorldModel()
        # 建立模式：alert.cpu → action.scale
        for tick in range(20):
            ps = [make_percept("tick")]
            if tick % 4 == 2:
                ps.append(make_percept("alert.cpu"))
            if tick % 4 == 3:
                ps.append(make_percept("action.scale"))
            model.observe(tick, ps)

        pred = model.predict_next(21, [make_percept("alert.cpu")])
        assert len(pred.predicted_event_types) > 0

    def test_prediction_no_data(self):
        model = WorldModel()
        pred = model.predict_next(1, [make_percept("unknown")])
        assert pred.predicted_event_types == []

    def test_summary(self):
        model = WorldModel()
        for i in range(5):
            model.observe(i, [make_percept("tick")])
        s = model.summary()
        assert s["total_ticks"] == 5
        assert s["history_size"] == 5

    def test_metric_baseline_tracking(self):
        model = WorldModel()
        for i in range(10):
            model.observe(i, [
                make_percept("system.status", cpu_pct=float(40 + i), mem_pct=60.0),
            ])
        assert len(model._metric_baselines) >= 2  # cpu + mem


class TestWorldModelAdapter:
    @pytest.mark.asyncio
    async def test_poll_returns_before_threshold(self):
        model = WorldModel()
        adapter = WorldModelAdapter(model, check_interval=5)
        ps = await adapter.poll()
        # tick_count = 1, 不是 5 的倍数
        assert len(ps) == 0

    @pytest.mark.asyncio
    async def test_poll_with_data(self):
        model = WorldModel()
        for i in range(20):
            model.observe(i, [
                make_percept("tick"),
                make_percept("system.status", cpu_pct=50.0),
            ])

        adapter = WorldModelAdapter(model, check_interval=1)
        # 强制输出
        adapter._tick_count = 5
        ps = await adapter.poll()
        assert len(ps) >= 1


class TestDataClasses:
    def test_correlation(self):
        c = Correlation(
            antecedent="a", consequent="b", count=5,
            probability=0.8, avg_gap_ticks=2.0,
        )
        assert c.antecedent == "a"
        assert c.probability == 0.8

    def test_anomaly_report(self):
        r = AnomalyReport(
            timestamp=100.0, tick_id=5,
            anomalies=[{"metric": "cpu_pct", "value": 95, "z_score": 3.0}],
            confidence=0.7,
        )
        assert len(r.anomalies) == 1

    def test_state_prediction(self):
        p = StatePrediction(
            predicted_event_types=["alert", "action"],
            probability=0.6, horizon_ticks=5, based_on_patterns=3,
        )
        assert "alert" in p.predicted_event_types
