"""异常与重试策略."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class YanLingError(Exception):
    """衍灵基础异常。"""


class BoundaryViolation(YanLingError):
    """边界违规 — 操作被安全边界拦截。"""


class LLMError(YanLingError):
    """LLM 调用异常。"""


class AdapterError(YanLingError):
    """适配器异常。"""


class ConfigurationError(YanLingError):
    """配置错误。"""


async def retry_with_backoff(
    func: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
) -> T:
    """指数退避重试。

    Args:
        func: 异步待重试函数
        max_retries: 最大重试次数
        base_delay: 初始延迟（秒）
        max_delay: 最大延迟（秒）
        jitter: 是否添加随机抖动
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except YanLingError as e:
            if attempt == max_retries:
                raise
            last_exc = e
            delay = min(base_delay * (2 ** attempt), max_delay)
            if jitter:
                delay *= 0.5 + random.random() * 0.5
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]
