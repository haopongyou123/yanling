"""LLM 自动降级适配器 — 多 provider 链式降级."""

from __future__ import annotations

import asyncio
import logging

from yanling.adapters.llm.base import LLMAdapter, LLMMessage, LLMResponse
from yanling.core.errors import LLMError

log = logging.getLogger("yanling.llm.fallback")


class FallbackAdapter(LLMAdapter):
    """自动降级适配器 — 按优先级列表依次尝试，失败时自动切到下一个。"""

    def __init__(self, providers: list[LLMAdapter]):
        if not providers:
            raise ValueError("至少需要一个 LLM provider")
        self._providers = providers
        self._current_idx = 0
        self._fallback_history: list[dict] = []

    @property
    def model_name(self) -> str:
        return self._providers[self._current_idx].model_name

    @property
    def provider(self) -> str:
        return f"fallback({self._providers[self._current_idx].provider})"

    @property
    def current_provider(self) -> LLMAdapter:
        return self._providers[self._current_idx]

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        last_error = None

        # 从当前 provider 开始尝试
        for i in range(len(self._providers)):
            idx = (self._current_idx + i) % len(self._providers)
            provider = self._providers[idx]

            try:
                response = await asyncio.wait_for(
                    provider.chat(
                        messages=messages, temperature=temperature,
                        max_tokens=max_tokens, **kwargs,
                    ),
                    timeout=getattr(provider, "_timeout", 120.0) + 5.0,
                )
                # 成功: 更新当前位置
                if idx != self._current_idx:
                    log.info("LLM 降级: %s → %s",
                              self._providers[self._current_idx].provider,
                              provider.provider)
                    self._fallback_history.append({
                        "from": self._providers[self._current_idx].provider,
                        "to": provider.provider,
                        "timestamp": __import__("time").time(),
                    })
                    self._current_idx = idx
                return response
            except LLMError as e:
                last_error = e
                log.warning("LLM [%s] 失败, 尝试下一个: %s", provider.provider, e)
                continue

        raise LLMError(f"所有 LLM provider 均失败, 最后错误: {last_error}")

    async def is_available(self) -> bool:
        for p in self._providers:
            if await p.is_available():
                return True
        return False

    def reset(self):
        """重置到首选 provider。"""
        self._current_idx = 0
        log.info("LLM 降级已重置到首选 provider")

    @property
    def fallback_count(self) -> int:
        return len(self._fallback_history)
