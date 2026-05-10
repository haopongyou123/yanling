"""DeepSeek API 适配器 — 通过 AI Proxy (localhost:4000) 连接。"""

from __future__ import annotations

import logging

import httpx

from yanling.adapters.llm.base import LLMAdapter, LLMMessage, LLMResponse
from yanling.core.errors import LLMError

log = logging.getLogger("yanling.llm.deepseek")


class DeepSeekAdapter(LLMAdapter):
    """DeepSeek Anthropic 兼容 API 适配器。"""

    def __init__(
        self,
        base_url: str = "http://localhost:4000/v1/messages",
        model: str = "deepseek-v4-flash",
        api_key: str = "",
        timeout: float = 120.0,
    ):
        self._base_url = base_url
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "deepseek"

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        system_prompt = ""
        chat_messages = []

        for m in messages:
            if m.role == "system":
                system_prompt += m.content + "\n"
            else:
                chat_messages.append({"role": m.role, "content": m.content})

        body = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
        }
        if system_prompt.strip():
            body["system"] = system_prompt.strip()

        try:
            resp = await self._client.post(
                self._base_url,
                json=body,
                headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01"},
            )
            resp.raise_for_status()
            data = resp.json()

            content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text", "")

            usage = data.get("usage", {})
            tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

            return LLMResponse(
                content=content,
                model=data.get("model", self._model),
                tokens_used=tokens_used,
                finish_reason=data.get("stop_reason", "stop"),
                raw=data,
            )
        except httpx.HTTPStatusError as e:
            log.error("DeepSeek API HTTP %s: %s", e.response.status_code, e.response.text[:200])
            raise LLMError(f"HTTP {e.response.status_code}: {e.response.text[:200]}") from e
        except httpx.RequestError as e:
            log.error("DeepSeek API 请求失败: %s", e)
            raise LLMError(f"请求失败: {e}") from e

    async def close(self):
        await self._client.aclose()

    async def is_available(self) -> bool:
        try:
            # 从 base_url 推导健康检查地址
            base = self._base_url.replace("/v1/messages", "/v1/models")
            resp = await self._client.get(base, timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False
