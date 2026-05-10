"""健康指标测试。"""

import time

from yanling.kernel.stats import EngineStats, TickMetrics


class TestEngineStats:
    def test_empty_snapshot(self):
        stats = EngineStats()
        s = stats.snapshot()
        assert s["status"] == "idle"
        assert s["total_ticks"] == 0

    def test_record_ticks(self):
        stats = EngineStats(window=10)
        for i in range(5):
            stats.record_tick(TickMetrics(
                tick_id=i, percepts=2, decisions=1, actions=1,
                success_rate=1.0, latency=0.1,
            ))
        s = stats.snapshot()
        assert s["total_ticks"] == 5
        assert s["avg_success_rate"] == 1.0
        assert s["status"] == "running"

    def test_success_rate_calculation(self):
        stats = EngineStats()
        stats.record_tick(TickMetrics(1, 2, 1, 2, 0.5, 0.1))
        stats.record_tick(TickMetrics(2, 2, 1, 2, 1.0, 0.2))
        stats.record_tick(TickMetrics(3, 2, 1, 2, 0.0, 0.3))
        s = stats.snapshot()
        assert s["avg_success_rate"] == 0.5

    def test_uptime(self):
        stats = EngineStats()
        time.sleep(0.01)
        assert stats.uptime > 0.01
