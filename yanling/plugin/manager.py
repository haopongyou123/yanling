"""插件管理器 — 动态加载/卸载运行时插件."""

from __future__ import annotations

import importlib
import logging
import traceback
from typing import Any

from yanling.bus.bus import EventBus
from yanling.plugin.interface import Plugin
from yanling.plugin.registry import PluginInfo, PluginRegistry

log = logging.getLogger("yanling.plugin.manager")


class PluginManager:
    """插件管理器 — 加载/卸载/生命周期管理。"""

    def __init__(self, registry: PluginRegistry, bus: EventBus):
        self.registry = registry
        self.bus = bus
        self._instances: dict[str, Plugin] = {}
        self._kernel_ref: Any = None

    def bind_kernel(self, kernel: Any):
        """绑定内核实例（供插件 on_load 使用）。"""
        self._kernel_ref = kernel

    async def load_all(self, enabled_only: bool = True):
        """加载所有已注册的插件。"""
        for info in self.registry.list(enabled_only=enabled_only):
            try:
                await self.load(info)
            except Exception as e:
                log.error("加载插件 %s 失败: %s", info.name, e)

    async def load(self, info: PluginInfo) -> Plugin | None:
        """加载单个插件。"""
        if info.name in self._instances:
            log.warning("插件 %s 已加载", info.name)
            return self._instances[info.name]

        try:
            module = importlib.import_module(info.module_path)
            cls = getattr(module, info.class_name)
            instance = cls()

            # 生命周期钩子
            await instance.on_load(self.bus, self._kernel_ref)

            # 订阅事件
            self.bus.subscribe(f"plugin.{info.name}.*", instance.on_event)

            self._instances[info.name] = instance
            log.info("插件已加载: %s v%s", info.name, info.version)
            return instance
        except Exception as e:
            log.error("加载插件 %s 异常: %s\n%s", info.name, e, traceback.format_exc())
            return None

    async def unload(self, name: str):
        """卸载单个插件。"""
        instance = self._instances.pop(name, None)
        if instance:
            await instance.on_unload()
            log.info("插件已卸载: %s", name)

    async def unload_all(self):
        """卸载所有插件。"""
        names = list(self._instances.keys())
        for name in names:
            await self.unload(name)

    def get(self, name: str) -> Plugin | None:
        return self._instances.get(name)

    def list_loaded(self) -> list[str]:
        return list(self._instances.keys())
