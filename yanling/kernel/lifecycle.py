"""生命周期管理 — 启动/停止/重启。"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

log = logging.getLogger("yanling.lifecycle")


class State(Enum):
    INIT = "init"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class Lifecycle:
    """生命周期状态机。"""

    def __init__(self):
        self._state = State.INIT
        self._lock = asyncio.Lock()

    @property
    def state(self) -> State:
        return self._state

    async def transition(self, target: State) -> bool:
        async with self._lock:
            transitions = {
                State.INIT: [State.STARTING],
                State.STARTING: [State.RUNNING, State.ERROR],
                State.RUNNING: [State.STOPPING, State.ERROR],
                State.STOPPING: [State.STOPPED, State.ERROR],
                State.ERROR: [State.STARTING, State.STOPPED],
            }
            if target not in transitions.get(self._state, []):
                log.warning("非法状态转换: %s → %s", self._state.value, target.value)
                return False
            self._state = target
            log.info("状态: %s", target.value)
            return True
