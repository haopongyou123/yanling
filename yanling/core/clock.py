"""时钟服务 — 心跳与调度."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Tick:
    """心跳脉冲。"""
    number: int
    timestamp: float
    interval: float


class Clock:
    """心跳时钟 — 以固定间隔发出 Tick 脉冲。"""

    def __init__(self, interval: float = 30.0):
        self.interval = interval
        self._tick_number = 0
        self._start_time: float = 0.0
        self._listeners: list[Callable[[Tick], None]] = []
        self._running = False

    def on_tick(self, listener: Callable[[Tick], None]):
        """注册 tick 监听器。"""
        self._listeners.append(listener)

    def start(self):
        self._running = True
        self._tick_number = 0
        self._start_time = time.time()

    def stop(self):
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def uptime(self) -> float:
        if self._start_time == 0:
            return 0.0
        return time.time() - self._start_time

    async def next_tick(self) -> Tick:
        """等待并返回下一个 Tick。"""
        self._tick_number += 1
        tick = Tick(
            number=self._tick_number,
            timestamp=time.time(),
            interval=self.interval,
        )
        for listener in self._listeners:
            listener(tick)
        return tick

    async def __aiter__(self):
        self.start()
        return self

    async def __anext__(self) -> Tick:
        if not self._running:
            raise StopAsyncIteration
        tick = await self.next_tick()
        await asyncio.sleep(self.interval)
        return tick
