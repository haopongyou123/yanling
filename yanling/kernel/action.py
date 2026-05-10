"""行动系统 — 统一输出抽象."""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod

from yanling.core.types import Action, ActionResult

log = logging.getLogger("yanling.action")


class ActionAdapter(ABC):
    """行动适配器接口。任何输出目标都实现此接口。"""

    @abstractmethod
    async def execute(self, action: Action) -> ActionResult:
        """执行一个行动。"""
        ...

    @abstractmethod
    async def validate(self, action: Action) -> bool:
        """验证行动参数是否合法。"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    async def start(self):
        """适配器启动初始化（可选）。"""

    async def stop(self):
        """适配器停止清理（可选）。"""


class ActionSystem:
    """行动系统 — 管理行动适配器并执行行动。"""

    def __init__(self):
        self._adapters: dict[str, ActionAdapter] = {}

    def register(self, adapter: ActionAdapter):
        self._adapters[adapter.name] = adapter
        log.info("行动适配器已注册: %s", adapter.name)

    def unregister(self, name: str):
        self._adapters.pop(name, None)

    async def start_all(self):
        for a in self._adapters.values():
            await a.start()

    async def stop_all(self):
        for a in self._adapters.values():
            await a.stop()

    async def execute(self, action: Action) -> ActionResult:
        """执行单个行动。"""
        if not action.id:
            action.id = str(uuid.uuid4())

        adapter = self._adapters.get(action.target)
        if not adapter:
            return ActionResult(
                action_id=action.id,
                success=False,
                error=f"适配器未找到: {action.target}",
            )

        if not await adapter.validate(action):
            return ActionResult(
                action_id=action.id,
                success=False,
                error=f"行动验证失败: {action}",
            )

        start = time.time()
        try:
            result = await adapter.execute(action)
            result.duration = time.time() - start
            return result
        except Exception as e:
            elapsed = time.time() - start
            log.error("行动执行失败 [%s/%s]: %s", action.target, action.type, e)
            return ActionResult(
                action_id=action.id,
                success=False,
                error=str(e),
                duration=elapsed,
            )

    async def execute_all(self, actions: list[Action]) -> list[ActionResult]:
        """按优先级执行多个行动。"""
        sorted_actions = sorted(actions, key=lambda a: a.priority, reverse=True)
        results = []
        for action in sorted_actions:
            results.append(await self.execute(action))
        return results
