"""引擎全局注册表 — 允许 Web 面板访问运行中的引擎实例。"""
from __future__ import annotations

import threading

from yanling.kernel.engine import YanLingEngine

_engine: YanLingEngine | None = None
_lock = threading.Lock()


def register(engine: YanLingEngine) -> None:
    global _engine
    with _lock:
        _engine = engine


def get() -> YanLingEngine | None:
    with _lock:
        return _engine


def unregister() -> None:
    global _engine
    with _lock:
        _engine = None
