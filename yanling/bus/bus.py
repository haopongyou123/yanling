"""事件总线 — 发布/订阅 (Pub/Sub)."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

from yanling.bus.event import Event

Handler = Callable[[Event], Coroutine[Any, Any, None]]


class Subscription:
    """订阅句柄，用于取消订阅。"""

    def __init__(self, bus: EventBus, event_type: str, handler: Handler):
        self._bus = bus
        self._event_type = event_type
        self._handler = handler

    def unsubscribe(self):
        self._bus._unsubscribe(self._event_type, self._handler)


class EventBus:
    """异步事件总线，支持通配符订阅和中间件。"""

    def __init__(self):
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._middleware: list[Callable[[Event], Event]] = []
        self._log = logging.getLogger("yanling.bus")

    def subscribe(self, event_type: str, handler: Handler) -> Subscription:
        """订阅事件。event_type 支持通配符后缀 `*`。"""
        self._handlers[event_type].append(handler)
        return Subscription(self, event_type, handler)

    def _unsubscribe(self, event_type: str, handler: Handler):
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def use(self, middleware: Callable[[Event], Event]):
        """注册中间件（在分发前转换事件）。"""
        self._middleware.append(middleware)

    async def publish(self, event: Event):
        """发布事件到所有匹配的订阅者。"""
        for mw in self._middleware:
            event = mw(event)

        matched_types = set()
        for et in self._handlers:
            if et.endswith("*"):
                if event.type.startswith(et.rstrip("*")):
                    matched_types.add(et)
            elif et == event.type:
                matched_types.add(et)

        for et in matched_types:
            for handler in self._handlers[et]:
                try:
                    await handler(event)
                except Exception as e:
                    self._log.error("事件处理出错 [%s]: %s", et, e)
