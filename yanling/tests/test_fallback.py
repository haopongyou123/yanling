"""LLM 降级适配器测试."""

import pytest

from yanling.adapters.llm.base import LLMAdapter, LLMMessage, LLMResponse
from yanling.adapters.llm.fallback import FallbackAdapter
from yanling.core.errors import LLMError


class MockOKAdapter(LLMAdapter):
    @property
    def model_name(self): return "mock-ok"
    @property
    def provider(self): return "mock-ok"
    async def chat(self, messages, **kwargs):
        return LLMResponse(content="ok", model="mock-ok")
    async def is_available(self): return True


class MockFailAdapter(LLMAdapter):
    @property
    def model_name(self): return "mock-fail"
    @property
    def provider(self): return "mock-fail"
    async def chat(self, messages, **kwargs):
        raise LLMError("模拟失败")
    async def is_available(self): return False


class TestFallbackAdapter:
    @pytest.mark.asyncio
    async def test_use_first_provider(self):
        fb = FallbackAdapter([MockOKAdapter(), MockOKAdapter()])
        resp = await fb.chat([LLMMessage(role="user", content="hi")])
        assert resp.content == "ok"

    @pytest.mark.asyncio
    async def test_fallback_on_failure(self):
        fb = FallbackAdapter([MockFailAdapter(), MockOKAdapter()])
        resp = await fb.chat([LLMMessage(role="user", content="hi")])
        assert resp.content == "ok"
        assert fb.fallback_count == 1

    @pytest.mark.asyncio
    async def test_all_fail(self):
        fb = FallbackAdapter([MockFailAdapter(), MockFailAdapter()])
        with pytest.raises(LLMError):
            await fb.chat([LLMMessage(role="user", content="hi")])

    @pytest.mark.asyncio
    async def test_is_available(self):
        fb = FallbackAdapter([MockFailAdapter(), MockOKAdapter()])
        assert await fb.is_available() is True

    @pytest.mark.asyncio
    async def test_reset(self):
        fb = FallbackAdapter([MockFailAdapter(), MockOKAdapter()])
        # 触发降级
        await fb.chat([LLMMessage(role="user", content="hi")])
        assert fb.current_provider.provider == "mock-ok"
        fb.reset()
        assert fb.current_provider.provider == "mock-fail"
