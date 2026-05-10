"""存储适配器抽象基类."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class StorageAdapter(ABC):
    """持久化存储适配器接口。"""

    @abstractmethod
    async def read(self, key: str) -> Any | None:
        ...

    @abstractmethod
    async def write(self, key: str, value: Any) -> bool:
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        ...

    @abstractmethod
    async def list_keys(self, prefix: str = "") -> list[str]:
        ...
