"""Checkpoint 持久化测试。"""

import pytest

from yanling.adapters.storage.json_file import JsonFileStorage
from yanling.core.types import (
    ActionResult,
    CognitionResult,
    Decision,
    Intent,
    Percept,
    TickResult,
)
from yanling.kernel.memory import MemorySystem


@pytest.mark.asyncio
async def test_memory_checkpoint():
    """验证记忆系统定期 checkpoint 能正确保存长期记忆。"""
    import tempfile
    tmpdir = tempfile.mkdtemp()
    storage = JsonFileStorage(tmpdir)
    mem = MemorySystem(storage, {"checkpoint_interval": 2})
    await mem.initialize()

    # 产生 3 个 tick（包含失败，会触发长期记忆写入）
    for i in range(3):
        tick = TickResult(
            tick_id=i + 1,
            perceptions=[Percept(source="t", type="f", data={})],
            cognition=CognitionResult(decisions=[Decision(intent=Intent.SLEEP, reason="test")]),
            actions=[ActionResult(action_id=f"a{i}", success=(i != 1), error="fail" if i == 1 else None)],
        )
        await mem.remember_tick(tick)

    # checkpoint_interval=2，所以第 2 个 tick 之后触发了一次 checkpoint
    # 长期记忆应该保存了失败 tick
    assert len(mem.long_term._entries) >= 1

    # 清理
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
