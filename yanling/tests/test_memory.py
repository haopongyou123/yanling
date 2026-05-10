"""记忆系统测试。"""

from yanling.kernel.memory import MemoryEntry, ShortTermMemory, WorkingMemory


class TestWorkingMemory:
    def test_set_and_get(self):
        wm = WorkingMemory(capacity=3)
        wm.set("a", 1)
        assert wm.get("a") == 1

    def test_capacity_eviction(self):
        wm = WorkingMemory(capacity=2)
        wm.set("a", 1)
        wm.set("b", 2)
        wm.set("c", 3)
        assert wm.get("a") is None
        assert wm.get("c") == 3


class TestShortTermMemory:
    def test_add_and_recent(self):
        stm = ShortTermMemory(capacity=10, ttl=3600)
        stm.add(MemoryEntry(key="k1", content="v1", type="test"))
        stm.add(MemoryEntry(key="k2", content="v2", type="test"))
        assert len(stm.recent(2)) == 2
        assert len(stm.recent(1)) == 1

    def test_query_by_type(self):
        stm = ShortTermMemory()
        stm.add(MemoryEntry(key="k1", content="v1", type="alpha"))
        stm.add(MemoryEntry(key="k2", content="v2", type="beta"))
        assert len(stm.query(type="alpha")) == 1
        assert len(stm.query(type="gamma")) == 0
