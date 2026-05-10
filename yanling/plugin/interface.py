"""插件接口定义."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from yanling.bus.bus import EventBus
from yanling.bus.event import Event


class Plugin(ABC):
    """插件基类 — 所有插件都继承此类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """插件唯一标识。"""

    @property
    def version(self) -> str:
        return "0.1.0"

    @abstractmethod
    async def on_load(self, bus: EventBus, kernel: Any) -> None:
        """加载时初始化 — 注册适配器、订阅事件。"""

    async def on_unload(self) -> None:
        """卸载时清理。"""

    async def on_event(self, event: Event) -> None:
        """事件处理（可选覆盖）。"""


class PerceptionPlugin(Plugin):
    """感知插件 — 提供感知适配器。"""

    @abstractmethod
    async def on_load(self, bus: EventBus, kernel: Any) -> None:
        """加载时注册感知适配器。"""
