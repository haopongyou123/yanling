"""总线中间件."""

from __future__ import annotations

import time
from typing import Any

from yanling.bus.event import Event


def timestamp_middleware(event: Event) -> Event:
    """为事件添加时间戳。"""
    event.data.setdefault("_ts", time.time())
    return event


def logging_middleware(logger: Any = None) -> Any:
    """创建日志中间件。"""
    if logger is None:
        import logging
        logger = logging.getLogger("yanling.bus")

    def _mw(event: Event) -> Event:
        logger.debug("事件: %s %s", event.type, event.data)
        return event

    return _mw
