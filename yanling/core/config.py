"""配置管理 — 支持环境变量 + YAML 文件两种来源 + schema 校验."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("yanling.config")


# ─── 配置 Schema ────────────────────────────────────────────

CONFIG_SCHEMA: dict[str, dict[str, type]] = {
    "kernel": {
        "tick_interval": (int, float),
        "max_idle_ticks": int,
        "working_memory_size": int,
    },
    "llm": {
        "provider": str,
        "model": str,
        "temperature": (int, float),
        "max_tokens": int,
        "fallback": bool,
        "fallback_order": list,
        "base_url": str,
        "api_key": str,
    },
    "memory": {
        "short_term_capacity": int,
        "short_term_ttl": (int, float),
        "storage": str,
        "storage_path": str,
    },
    "plugins": {
        "auto_load": bool,
        "config_path": str,
        "paths": list,
    },
    "boundaries": {
        "rate_per_minute": (int, float),
        "rate_per_hour": (int, float),
        "cost_per_day": (int, float),
        "max_action_timeout": (int, float),
        "allowed_action_types": list,
    },
}


# ─── 默认配置 ───────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "kernel": {
        "tick_interval": 30,
        "max_idle_ticks": 100,
        "working_memory_size": 10,
    },
    "llm": {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "temperature": 0.7,
        "max_tokens": 4096,
        "fallback": True,
        "fallback_order": ["deepseek", "openrouter", "omix"],
        "base_url": os.environ.get("ANTHROPIC_BASE_URL", ""),
        "api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
    },
    "memory": {
        "short_term_capacity": 100,
        "short_term_ttl": 3600,
        "storage": "json_file",
        "storage_path": str(Path.home() / ".yanling" / "memory"),
    },
    "plugins": {
        "auto_load": True,
        "config_path": "",
        "paths": ["./scenarios/", "./plugins/"],
    },
    "boundaries": {
        "rate_per_minute": 10,
        "rate_per_hour": 200,
        "cost_per_day": 1.0,
        "max_action_timeout": 60,
        "allowed_action_types": ["notify", "store", "analyze"],
    },
}


# ─── 配置对象 ───────────────────────────────────────────────

class ValidationWarning:
    """配置校验警告。"""
    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message

    def __str__(self) -> str:
        return f"[{self.path}] {self.message}"


class Config:
    """配置对象，支持 dict 式访问、schema 校验、环境变量覆盖。"""

    def __init__(self, data: dict | None = None):
        self._data = data or DEFAULT_CONFIG.copy()
        self._warnings: list[ValidationWarning] = []
        self._apply_env_overrides()
        self._validate()

    def _apply_env_overrides(self):
        env_map = {
            "YANLING_TICK_INTERVAL": ("kernel", "tick_interval"),
            "YANLING_LLM_PROVIDER": ("llm", "provider"),
            "YANLING_LLM_MODEL": ("llm", "model"),
            "YANLING_STORAGE_PATH": ("memory", "storage_path"),
            "YANLING_RATE_PER_MINUTE": ("boundaries", "rate_per_minute"),
            "YANLING_RATE_PER_HOUR": ("boundaries", "rate_per_hour"),
            "YANLING_MAX_ACTION_TIMEOUT": ("boundaries", "max_action_timeout"),
        }
        for env_key, (section, key) in env_map.items():
            val = os.environ.get(env_key)
            if val is not None:
                try:
                    val = int(val)
                except ValueError:
                    pass
                self._data.setdefault(section, {})[key] = val

    def _validate(self):
        """校验配置是否符合 schema，产生警告但不阻断。"""
        self._warnings.clear()
        for section, keys in CONFIG_SCHEMA.items():
            section_data = self._data.get(section, {})
            for key, expected_type in keys.items():
                val = section_data.get(key)
                if val is None:
                    continue
                if not isinstance(val, expected_type):
                    expected_name = "/".join(t.__name__ for t in expected_type) if isinstance(expected_type, tuple) else expected_type.__name__
                    self._warnings.append(ValidationWarning(
                        f"{section}.{key}",
                        f"期望类型 {expected_name}, 实际 {type(val).__name__} = {val!r}",
                    ))
            # 警告未知字段
            for key in section_data:
                if key not in keys:
                    self._warnings.append(ValidationWarning(
                        f"{section}.{key}",
                        "未知配置字段，将被忽略",
                    ))

    @property
    def warnings(self) -> list[ValidationWarning]:
        return list(self._warnings)

    def get(self, *keys: str, default: Any = None) -> Any:
        """按路径链取值: cfg.get("kernel", "tick_interval")"""
        cur = self._data
        for k in keys:
            if isinstance(cur, dict):
                cur = cur.get(k)
                if cur is None:
                    return default
            else:
                return default
        return cur

    @property
    def raw(self) -> dict:
        return self._data

    @classmethod
    def from_yaml(cls, path: str | Path) -> Config:
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            import yaml
            with open(p) as f:
                data = yaml.safe_load(f) or {}
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            cfg = cls(merged)
            cfg._warnings.append(ValidationWarning("yaml", f"已加载: {path}"))
            return cfg
        except Exception as e:
            cfg = cls()
            cfg._warnings.append(ValidationWarning("yaml", f"加载失败 ({e}), 使用默认配置"))
            return cfg

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        path = path or os.environ.get("YANLING_CONFIG")
        if path:
            return cls.from_yaml(path)
        return cls()
