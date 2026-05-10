"""模拟传感器 — 产生温度、振动、压力数据，偶尔出现异常。"""

from __future__ import annotations

import logging
import math
import random
import time

from yanling.core.types import Percept
from yanling.kernel.perception import PerceptionAdapter

log = logging.getLogger("yanling.scenario.embedded.sensor")


class SensorConfig:
    """传感器参数配置。"""

    def __init__(
        self,
        name: str,
        normal_mean: float = 50.0,
        normal_std: float = 5.0,
        anomaly_rate: float = 0.1,
        anomaly_scale: float = 3.0,
        warning_high: float = 65.0,
        warning_low: float = 35.0,
        critical_high: float = 80.0,
        critical_low: float = 20.0,
    ):
        self.name = name
        self.normal_mean = normal_mean
        self.normal_std = normal_std
        self.anomaly_rate = anomaly_rate
        self.anomaly_scale = anomaly_scale
        self.warning_high = warning_high
        self.warning_low = warning_low
        self.critical_high = critical_high
        self.critical_low = critical_low


# 默认传感器配置
DEFAULT_SENSORS = [
    SensorConfig("temperature", normal_mean=45.0, normal_std=3.0,
                  warning_high=55.0, warning_low=35.0,
                  critical_high=65.0, critical_low=25.0),
    SensorConfig("vibration", normal_mean=5.0, normal_std=1.0,
                  warning_high=8.0, warning_low=2.0,
                  critical_high=12.0, critical_low=0.5, anomaly_rate=0.05),
    SensorConfig("pressure", normal_mean=100.0, normal_std=5.0,
                  warning_high=115.0, warning_low=85.0,
                  critical_high=130.0, critical_low=70.0),
]


class SimulatedSensorAdapter(PerceptionAdapter):
    """模拟传感器适配器 — 产生带噪声的传感器读数。"""

    def __init__(self, sensors: list[SensorConfig] | None = None):
        self._sensors = sensors or DEFAULT_SENSORS
        self._count = 0
        self._anomaly_log: list[dict] = []

    @property
    def name(self) -> str:
        return "sensor_array"

    @property
    def anomaly_count(self) -> int:
        return len(self._anomaly_log)

    async def poll(self) -> list[Percept]:
        self._count += 1
        percepts = []

        for sensor in self._sensors:
            reading = self._generate_reading(sensor)
            alert_level = self._classify(reading, sensor)

            if alert_level != "normal":
                self._anomaly_log.append({
                    "sensor": sensor.name,
                    "value": round(reading, 2),
                    "level": alert_level,
                    "tick": self._count,
                })

            percepts.append(Percept(
                source=f"sensor.{sensor.name}",
                type=f"sensor_reading.{alert_level}",
                data={
                    "sensor": sensor.name,
                    "value": round(reading, 2),
                    "alert": alert_level,
                    "timestamp": time.time(),
                },
            ))

        return percepts

    def _generate_reading(self, sensor: SensorConfig) -> float:
        base = random.gauss(sensor.normal_mean, sensor.normal_std)
        if random.random() < sensor.anomaly_rate:
            # 异常：方向随机偏移
            direction = 1 if random.random() > 0.5 else -1
            base += direction * sensor.normal_std * sensor.anomaly_scale
        # 缓慢漂移
        drift = math.sin(self._count * 0.1) * 0.5
        return base + drift

    def _classify(self, value: float, sensor: SensorConfig) -> str:
        if value >= sensor.critical_high or value <= sensor.critical_low:
            return "critical"
        if value >= sensor.warning_high or value <= sensor.warning_low:
            return "warning"
        return "normal"

    def recent_anomalies(self, n: int = 5) -> list[dict]:
        return self._anomaly_log[-n:]
