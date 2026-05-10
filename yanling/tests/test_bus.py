"""事件总线测试。"""

import pytest

from yanling.bus.bus import EventBus
from yanling.bus.event import Event


class TestEventBus:
    @pytest.mark.asyncio
    async def test_publish_subscribe(self):
        bus = EventBus()
        received = []

        async def handler(e: Event):
            received.append(e)

        bus.subscribe("test.event", handler)
        await bus.publish(Event("test.event", {"key": "val"}))

        assert len(received) == 1
        assert received[0].type == "test.event"
        assert received[0].data["key"] == "val"

    @pytest.mark.asyncio
    async def test_wildcard_subscribe(self):
        bus = EventBus()
        received = []

        async def handler(e: Event):
            received.append(e)

        bus.subscribe("prefix.*", handler)
        await bus.publish(Event("prefix.abc"))
        await bus.publish(Event("other"))

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        bus = EventBus()
        received = []

        async def handler(e: Event):
            received.append(e)

        sub = bus.subscribe("test", handler)
        sub.unsubscribe()
        await bus.publish(Event("test"))

        assert len(received) == 0
