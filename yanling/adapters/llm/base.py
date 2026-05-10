"""LLM 适配器抽象基类."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    """LLM 调用响应。"""
    content: str
    model: str
    tokens_used: int = 0
    finish_reason: str = "stop"
    raw: Any = None
    error: str | None = None


@dataclass
class LLMMessage:
    """消息结构。"""
    role: str        # system / user / assistant
    content: str


class LLMAdapter(ABC):
    """LLM 适配器抽象基类。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        """释放底层连接资源。子类可重写。"""
        return

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """检查后端是否可达。"""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @property
    @abstractmethod
    def provider(self) -> str:
        ...
