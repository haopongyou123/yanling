"""Web 面板测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from yanling.core.config import Config
from yanling.kernel.engine import YanLingEngine
from yanling.kernel.stats import TickMetrics
from yanling.web.dashboard import app
from yanling.web.registry import register, unregister


@pytest.fixture(autouse=True)
def cleanup_registry():
    """每个测试后清理引擎注册表。"""
    yield
    unregister()


@pytest.mark.asyncio
async def test_empty_state():
    """没有引擎注册时，所有页面正常返回空状态。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert "已停止" in r.text or "stopped" in r.text

        r = await client.get("/memory")
        assert r.status_code == 200

        r = await client.get("/evolution")
        assert r.status_code == 200

        r = await client.get("/api/status")
        assert r.json()["running"] is False

        r = await client.get("/api/stats")
        assert r.json()["status"] == "idle"

        r = await client.get("/api/summary")
        assert r.json()["running"] is False


@pytest.mark.asyncio
async def test_with_engine():
    """引擎注册后，页面展示引擎状态。"""
    engine = _make_mock_engine(tick_count=42)
    register(engine)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert "42" in r.text  # tick count visible

        r = await client.get("/api/status")
        data = r.json()
        assert data["running"] is True
        assert data["tick"] == 42


@pytest.mark.asyncio
async def test_stats_endpoint():
    """指标 API 返回正确值。"""
    engine = _make_mock_engine()
    engine.stats.record_tick(TickMetrics(1, 3, 2, 2, 1.0, 0.1))
    engine.stats.record_tick(TickMetrics(2, 3, 2, 2, 0.5, 0.2))
    register(engine)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/stats")
        data = r.json()
        assert data["total_ticks"] == 2
        assert data["avg_success_rate"] == 0.75
        assert data["last_tick"]["id"] == 2

        r = await client.get("/api/summary")
        data = r.json()
        assert data["tick_count"] == 0  # mock 引擎无 _tick_count


@pytest.mark.asyncio
async def test_memory_and_evolution_pages():
    """记忆和进化页面在有/无引擎时都能渲染。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 无引擎
        r = await client.get("/memory")
        assert "工作记忆" in r.text or "为空" in r.text
        assert r.status_code == 200

        r = await client.get("/evolution")
        assert "进化" in r.text or "未启用" in r.text
        assert r.status_code == 200

    # 有引擎
    engine = _make_mock_engine()
    register(engine)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/memory")
        assert r.status_code == 200

        r = await client.get("/evolution")
        assert r.status_code == 200


def _make_mock_engine(tick_count: int = 0) -> YanLingEngine:
    """创建简化引擎用于测试。"""
    engine = YanLingEngine(config=Config())
    engine._tick_count = tick_count
    return engine
