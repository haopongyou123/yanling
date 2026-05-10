"""oMLX 本地模型适配器."""

from __future__ import annotations

import logging

import httpx

from yanling.adapters.llm.base import LLMAdapter, LLMMessage, LLMResponse
from yanling.core.errors import LLMError

log = logging.getLogger("yanling.llm.omix")


class OmixAdapter(LLMAdapter):
    """oMLX 本地模型适配器 (127.0.0.1:8000)。"""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000/v1/chat/completions",
        model: str = "qwen3.5-9b-mlx-4bit",
        timeout: float = 120.0,
    ):
        self._base_url = base_url
        self._model = model
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "omix"

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        body = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            resp = await self._client.post(self._base_url, json=body)
            resp.raise_for_status()
            data = resp.json()

            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            content = msg.get("content", "")

            usage = data.get("usage", {})
            tokens_used = usage.get("total_tokens", 0)

            return LLMResponse(
                content=content,
                model=data.get("model", self._model),
                tokens_used=tokens_used,
                finish_reason=choice.get("finish_reason", "stop"),
                raw=data,
            )
        except Exception as e:
            log.error("oMLX 调用失败: %s", e)
            raise LLMError(f"oMLX 失败: {e}") from e

    async def close(self):
        await self._client.aclose()

    async def is_available(self) -> bool:
        try:
            resp = await self._client.get("http://127.0.0.1:8000/v1/models", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False
