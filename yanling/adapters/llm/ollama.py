"""Ollama 本地模型适配器."""

from __future__ import annotations

import logging

import httpx

from yanling.adapters.llm.base import LLMAdapter, LLMMessage, LLMResponse
from yanling.core.errors import LLMError

log = logging.getLogger("yanling.llm.ollama")


class OllamaAdapter(LLMAdapter):
    """Ollama 本地模型适配器 (127.0.0.1:11434)。"""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "gemma4:e4b",
        timeout: float = 120.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return f"ollama({self._model})"

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
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            resp = await self._client.post(f"{self._base_url}/api/chat", json=body)
            resp.raise_for_status()
            data = resp.json()

            message = data.get("message", {})
            content = message.get("content", "")

            tokens_used = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)

            return LLMResponse(
                content=content,
                model=data.get("model", self._model),
                tokens_used=tokens_used,
                finish_reason="stop" if data.get("done") else "length",
                raw=data,
            )
        except httpx.TimeoutException:
            raise LLMError(f"Ollama 请求超时 ({self._timeout}s)") from None
        except Exception as e:
            log.error("Ollama 调用失败: %s", e)
            raise LLMError(f"Ollama 失败: {e}") from e

    async def close(self):
        await self._client.aclose()

    async def is_available(self) -> bool:
        try:
            resp = await self._client.get(f"{self._base_url}/api/tags", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False
