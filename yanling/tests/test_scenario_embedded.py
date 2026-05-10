"""嵌入式场景组件测试。"""

import pytest

from yanling.core.types import Action
from yanling.scenarios.embedded.actions import AlertLogger, DeviceControl, SystemLog
from yanling.scenarios.embedded.sensor import SensorConfig, SimulatedSensorAdapter


class TestSimulatedSensor:
    @pytest.mark.asyncio
    async def test_poll_returns_percepts(self):
        sensor = SimulatedSensorAdapter()
        result = await sensor.poll()
        assert len(result) == 3  # 3 个默认传感器
        assert all(p.source.startswith("sensor.") for p in result)
        assert all("value" in p.data for p in result)

    @pytest.mark.asyncio
    async def test_anomaly_detection(self):
        """验证极端值被正确分类。"""
        config = SensorConfig("test", normal_mean=50, normal_std=1,
                               anomaly_rate=1.0, anomaly_scale=50,
                               critical_high=70)
        sensor = SimulatedSensorAdapter([config])
        found_critical = False
        for _ in range(50):
            result = await sensor.poll()
            for p in result:
                if p.type == "sensor_reading.critical":
                    found_critical = True
        assert found_critical

    def test_anomaly_count(self):
        sensor = SimulatedSensorAdapter()
        assert sensor.anomaly_count >= 0


class TestAlertLogger:
    def test_execute(self):
        logger = AlertLogger()
        import asyncio
        result = asyncio.run(logger.execute(
            Action(type="alert", target="alert_logger",
                   params={"level": "warning", "message": "测试告警"})
        ))
        assert result.success
        assert logger.alert_count == 1

    def test_recent(self):
        logger = AlertLogger(max_history=5)
        import asyncio
        for i in range(3):
            asyncio.run(logger.execute(
                Action(type="alert", target="alert_logger",
                       params={"level": "info", "message": f"msg{i}"})
            ))
        assert len(logger.recent(2)) == 2
        assert len(logger.recent(10)) == 3


class TestSystemLog:
    def test_execute_and_summary(self):
        log = SystemLog()
        import asyncio
        asyncio.run(log.execute(
            Action(type="log", target="system_log",
                   params={"message": "test", "level": "info"})
        ))
        assert log.summary()["total_entries"] == 1


class TestDeviceControl:
    def test_valid_command(self):
        ctrl = DeviceControl()
        import asyncio
        result = asyncio.run(ctrl.execute(
            Action(type="adjust", target="device_control",
                   params={"command": "calibrate"})
        ))
        assert result.success

    def test_validate(self):
        ctrl = DeviceControl()
        import asyncio
        assert asyncio.run(ctrl.validate(
            Action(type="x", target="y", params={"command": "calibrate"})
        ))
        assert not asyncio.run(ctrl.validate(
            Action(type="x", target="y", params={"command": "invalid"})
        ))
