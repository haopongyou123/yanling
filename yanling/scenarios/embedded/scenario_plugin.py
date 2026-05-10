"""嵌入式场景插件 — 注册传感器和行动适配器。"""

from __future__ import annotations

import logging

from yanling.bus.bus import EventBus
from yanling.plugin.interface import Plugin
from yanling.scenarios.embedded.actions import AlertLogger, DeviceControl, SystemLog
from yanling.scenarios.embedded.sensor import SimulatedSensorAdapter

log = logging.getLogger("yanling.scenario.embedded.plugin")


class EmbeddedMonitorPlugin(Plugin):
    """嵌入式监控插件 — 注册传感器感知和告警行动适配器。"""

    @property
    def name(self) -> str:
        return "embedded_monitor"

    @property
    def version(self) -> str:
        return "0.1.0"

    async def on_load(self, bus: EventBus, kernel) -> None:
        if not kernel:
            log.warning("未绑定内核，跳过适配器注册")
            return

        # 注册感知适配器
        sensor = SimulatedSensorAdapter()
        kernel.perception.register(sensor)

        # 注册行动适配器
        kernel.action_sys.register(AlertLogger())
        kernel.action_sys.register(SystemLog())
        kernel.action_sys.register(DeviceControl())

        # 保存引用
        self.sensor = sensor
        log.info("嵌入式监控插件已加载: 传感器 + 告警/日志/控制适配器")
