"""插件系统测试."""

import pytest

from yanling.bus.bus import EventBus
from yanling.bus.event import Event
from yanling.plugin.interface import Plugin
from yanling.plugin.manager import PluginManager
from yanling.plugin.registry import PluginInfo, PluginRegistry


class DummyPlugin(Plugin):
    @property
    def name(self) -> str:
        return "dummy"

    async def on_load(self, bus, kernel):
        self.loaded = True
        self.bus = bus
        self.events = []

    async def on_event(self, event: Event):
        self.events.append(event)


class TestPluginInfo:
    def test_create_and_serialize(self):
        info = PluginInfo("test", "module.path", "TestPlugin", "1.0.0", "测试插件")
        d = info.to_dict()
        assert d["name"] == "test"
        assert d["version"] == "1.0.0"

        info2 = PluginInfo.from_dict(d)
        assert info2.name == "test"
        assert info2.module_path == "module.path"


class TestPluginRegistry:
    def test_register_and_list(self):
        r = PluginRegistry()
        info = PluginInfo("p1", "mod.a", "PA")
        r.register(info)
        assert r.get("p1") is info
        assert len(r.list()) == 1

    def test_enabled_filter(self):
        r = PluginRegistry()
        r.register(PluginInfo("a", "m", "A", enabled=True))
        r.register(PluginInfo("b", "m", "B", enabled=False))
        assert len(r.list(enabled_only=True)) == 1

    def test_unregister(self):
        r = PluginRegistry()
        info = PluginInfo("p", "m", "P")
        r.register(info)
        r.unregister("p")
        assert r.get("p") is None


class TestPluginManager:
    @pytest.mark.asyncio
    async def test_load_unload(self):
        bus = EventBus()
        r = PluginRegistry()
        r.register(PluginInfo("dummy", "yanling.tests.test_plugin", "DummyPlugin"))
        mgr = PluginManager(r, bus)

        await mgr.load_all()
        assert "dummy" in mgr.list_loaded()
        assert mgr.get("dummy").loaded

        await mgr.unload("dummy")
        assert "dummy" not in mgr.list_loaded()

    @pytest.mark.asyncio
    async def test_load_nonexistent(self):
        bus = EventBus()
        r = PluginRegistry()
        r.register(PluginInfo("bad", "nonexistent.module", "BadPlugin"))
        mgr = PluginManager(r, bus)

        result = await mgr.load(r.get("bad"))
        assert result is None

    @pytest.mark.asyncio
    async def test_event_dispatch(self):
        bus = EventBus()
        r = PluginRegistry()
        r.register(PluginInfo("dummy", "yanling.tests.test_plugin", "DummyPlugin"))
        mgr = PluginManager(r, bus)

        await mgr.load_all()
        dummy = mgr.get("dummy")
        await bus.publish(Event("plugin.dummy.test", {"key": "val"}))

        await mgr.unload_all()
        assert len(mgr.list_loaded()) == 0
