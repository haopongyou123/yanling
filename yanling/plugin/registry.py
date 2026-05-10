"""插件注册表 — 管理已知插件的元数据。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("yanling.plugin.registry")


class PluginInfo:
    """插件元信息。"""

    def __init__(
        self,
        name: str,
        module_path: str,
        class_name: str,
        version: str = "0.1.0",
        description: str = "",
        enabled: bool = True,
    ):
        self.name = name
        self.module_path = module_path
        self.class_name = class_name
        self.version = version
        self.description = description
        self.enabled = enabled

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "module_path": self.module_path,
            "class_name": self.class_name,
            "version": self.version,
            "description": self.description,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PluginInfo:
        return cls(**data)


class PluginRegistry:
    """插件注册表 — 管理插件元数据。"""

    def __init__(self, config_path: str | Path | None = None):
        self._plugins: dict[str, PluginInfo] = {}
        self._config_path = Path(config_path) if config_path else Path.home() / ".yanling" / "plugins.json"

    def register(self, info: PluginInfo):
        self._plugins[info.name] = info
        log.info("插件已注册: %s (%s)", info.name, info.module_path)

    def unregister(self, name: str):
        self._plugins.pop(name, None)

    def get(self, name: str) -> PluginInfo | None:
        return self._plugins.get(name)

    def list(self, enabled_only: bool = False) -> list[PluginInfo]:
        plugins = list(self._plugins.values())
        if enabled_only:
            plugins = [p for p in plugins if p.enabled]
        return plugins

    async def save(self):
        data = [info.to_dict() for info in self._plugins.values()]
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def load(self):
        if not self._config_path.exists():
            return
        data = json.loads(self._config_path.read_text(encoding="utf-8"))
        for item in data:
            info = PluginInfo.from_dict(item)
            self._plugins[info.name] = info
