"""感知系统 — 统一输入抽象."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from yanling.core.types import Percept

log = logging.getLogger("yanling.perception")


class PerceptionAdapter(ABC):
    """感知适配器接口。任何外部输入源都实现此接口。"""

    @abstractmethod
    async def poll(self) -> list[Percept]:
        """拉取当前感知数据。返回 0 到多个 Percept。"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    async def start(self):
        """适配器启动时的初始化（可选覆盖）。"""

    async def stop(self):
        """适配器停止时的清理（可选覆盖）。"""


class TimerAdapter(PerceptionAdapter):
    """最简单的感知适配器：定时发出 tick 信号。"""

    def __init__(self, interval: float = 30.0):
        self._interval = interval
        self._count = 0

    @property
    def name(self) -> str:
        return "timer"

    async def poll(self) -> list[Percept]:
        self._count += 1
        return [
            Percept(
                source="timer",
                type="tick",
                data={"count": self._count, "interval": self._interval},
            )
        ]


class PerceptionSystem:
    """感知系统 — 管理多个感知适配器并收集感知数据。"""

    def __init__(self):
        self._adapters: dict[str, PerceptionAdapter] = {}

    def register(self, adapter: PerceptionAdapter):
        """注册一个感知适配器。"""
        self._adapters[adapter.name] = adapter
        log.info("感知适配器已注册: %s", adapter.name)

    def unregister(self, name: str):
        self._adapters.pop(name, None)

    async def start_all(self):
        for a in self._adapters.values():
            await a.start()

    async def stop_all(self):
        for a in self._adapters.values():
            await a.stop()

    async def collect(self) -> list[Percept]:
        """从所有注册的适配器收集感知数据。"""
        percepts: list[Percept] = []
        for name, adapter in self._adapters.items():
            try:
                result = await adapter.poll()
                percepts.extend(result)
            except Exception as e:
                log.warning("感知适配器 %s 拉取失败: %s", name, e)
        return percepts
