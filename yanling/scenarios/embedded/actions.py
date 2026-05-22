"""嵌入式场景的行动适配器 — 告警、日志、控制、修复。"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from collections import deque
from datetime import datetime

from yanling.core.types import Action, ActionResult
from yanling.kernel.action import ActionAdapter

log = logging.getLogger("yanling.scenario.embedded.action")

# ── 行动脚本路径 ──
ACTIONS_SCRIPT = "/home/toto/auto-content/scripts/yanling_actions.py"
HEAL_SCRIPT = "/home/toto/auto-content/scripts/yanling_heal_loop.py"


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


class HealExecutor(ActionAdapter):
    """修复执行适配器 — 调用 yanling_actions.py 执行修复操作。

    支持的动作类型:
      - "system_restart": 重启服务
      - "system_check": 检查状态
      - "git_sync": 同步代码
      - "heal_loop": 执行完整修复闭环
    """

    def __init__(self):
        self._history: deque[dict] = deque(maxlen=50)

    @property
    def name(self) -> str:
        return "heal_executor"

    async def execute(self, action: Action) -> ActionResult:
        action_type = action.type
        params = action.params
        target = params.get("target", "")

        log.info("[修复] 执行 %s: target=%s", action_type, target)

        if action_type == "system_restart":
            # 重启服务: 映射到 yanling_actions
            action_map = {
                "yuanding_go": "restart_yuanding_go",
                "ai_proxy": "restart_ai_proxy",
                "yanling": "restart_yanling_kernel",
                "dengta_ai_proxy": "restart_dengta_ai_proxy",
                "dengta_zhangbu": "restart_dengta_zhangbu",
            }
            aid = action_map.get(target)
            if not aid:
                return ActionResult(action_id=action.id, success=False,
                                    output={"error": f"未知目标: {target}"})
            r = await self._run_action(aid)
            return ActionResult(action_id=action.id, success=r["success"], output=r)

        elif action_type == "system_check":
            check_map = {
                "yuanding_disk": "check_yuanding_disk",
                "dengta_disk": "check_dengta_disk",
                "pipeline": "check_pipeline_status",
            }
            aid = check_map.get(target)
            if not aid:
                return ActionResult(action_id=action.id, success=False,
                                    output={"error": f"未知检查: {target}"})
            r = await self._run_action(aid)
            return ActionResult(action_id=action.id, success=r["success"], output=r)

        elif action_type == "git_sync":
            # git pull 走审批流程
            r = await self._run_action("sync_git_pull")
            return ActionResult(action_id=action.id, success=r["success"], output=r)

        elif action_type == "heal_loop":
            # 执行完整修复闭环
            r = await self._run_heal_loop()
            return ActionResult(action_id=action.id, success=r, output={})

        elif action_type == "approve_action":
            # 批准待审批操作 (人类操作，衍灵仅记录)
            return ActionResult(action_id=action.id, success=True,
                                output={"note": "操作需人类在黑板上审批"})

        return ActionResult(action_id=action.id, success=False,
                            output={"error": f"未知动作类型: {action_type}"})

    async def _run_action(self, action_id: str) -> dict:
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", ACTIONS_SCRIPT, "execute", action_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode().strip()[:500]
            error = stderr.decode().strip()[:200]
            success = proc.returncode == 0
            result = {"success": success, "output": output, "error": error}
            self._history.append({"action_id": action_id, **result})
            return result
        except asyncio.TimeoutError:
            return {"success": False, "output": "", "error": "超时"}
        except Exception as e:
            return {"success": False, "output": "", "error": str(e)}

    async def _run_heal_loop(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", HEAL_SCRIPT,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=60)
            return proc.returncode == 0
        except:
            return False

    async def validate(self, action: Action) -> bool:
        return action.type in ("system_restart", "system_check", "git_sync",
                               "heal_loop", "approve_action")

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
