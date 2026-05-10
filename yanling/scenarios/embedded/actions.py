"""嵌入式场景的行动适配器 — 告警、日志、控制。"""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime

from yanling.core.types import Action, ActionResult
from yanling.kernel.action import ActionAdapter

log = logging.getLogger("yanling.scenario.embedded.action")


class AlertLogger(ActionAdapter):
    """告警日志适配器 — 记录告警到内存和可选文件。"""

    def __init__(self, max_history: int = 100):
        self._history: deque[dict] = deque(maxlen=max_history)
        self._alert_count = 0

    @property
    def name(self) -> str:
        return "alert_logger"

    @property
    def alert_count(self) -> int:
        return self._alert_count

    async def execute(self, action: Action) -> ActionResult:
        self._alert_count += 1
        record = {
            "id": self._alert_count,
            "action_id": action.id,
            "type": action.type,
            "params": action.params,
            "timestamp": time.time(),
            "time_str": datetime.now().strftime("%H:%M:%S"),
        }
        self._history.append(record)
        log.warning("⚠ 告警 [#%d] %s: %s", self._alert_count, action.params.get("level", "info"),
                     action.params.get("message", ""))
        return ActionResult(action_id=action.id, success=True, output=record)

    async def validate(self, action: Action) -> bool:
        return True

    def recent(self, n: int = 10) -> list[dict]:
        return list(self._history)[-n:]


class SystemLog(ActionAdapter):
    """系统日志适配器 — 记录常规操作日志。"""

    def __init__(self):
        self._entries: list[dict] = []

    @property
    def name(self) -> str:
        return "system_log"

    async def execute(self, action: Action) -> ActionResult:
        entry = {
            "action_id": action.id,
            "message": action.params.get("message", ""),
            "level": action.params.get("level", "info"),
            "timestamp": time.time(),
        }
        self._entries.append(entry)
        log.info("[log] %s", action.params.get("message", ""))
        return ActionResult(action_id=action.id, success=True, output=entry)

    async def validate(self, action: Action) -> bool:
        return True

    def summary(self) -> dict:
        return {"total_entries": len(self._entries)}


class DeviceControl(ActionAdapter):
    """设备控制适配器 — 模拟执行控制指令（调节、重启等）。"""

    def __init__(self):
        self._commands: list[dict] = []

    @property
    def name(self) -> str:
        return "device_control"

    async def execute(self, action: Action) -> ActionResult:
        cmd = {"command": action.type, "params": action.params, "timestamp": time.time()}
        self._commands.append(cmd)
        log.info("[控制] 执行 %s: %s", action.type, action.params)
        return ActionResult(action_id=action.id, success=True, output=cmd)

    async def validate(self, action: Action) -> bool:
        valid = ["adjust", "restart", "calibrate", "shutdown"]
        return action.params.get("command") in valid
