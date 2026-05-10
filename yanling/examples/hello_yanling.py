"""衍灵内核最小可运行示例 — 感知→认知→行动→进化 完整闭环。"""

import asyncio
import os
import sys

# 确保能找到 yanling 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yanling.adapters.llm.deepseek import DeepSeekAdapter
from yanling.adapters.storage.json_file import JsonFileStorage
from yanling.core.config import Config
from yanling.core.logger import setup_logger
from yanling.kernel.action import Action, ActionAdapter, ActionResult, ActionSystem
from yanling.kernel.boundary import BoundaryControl, RateLimitRule, ScopeRule
from yanling.kernel.cognition import CognitiveEngine
from yanling.kernel.engine import YanLingEngine
from yanling.kernel.evolution import EvolutionEngine
from yanling.kernel.memory import MemorySystem
from yanling.kernel.perception import Percept, PerceptionAdapter, PerceptionSystem


class ConsoleActionAdapter(ActionAdapter):
    """控制台输出行动适配器（无需 LLM 即可验证的 demo 适配器）。"""

    @property
    def name(self) -> str:
        return "console"

    async def execute(self, action: Action) -> ActionResult:
        print(f"  [行动] {action.type}: {action.params.get('message', '')}")
        return ActionResult(action_id=action.id, success=True, output="ok")

    async def validate(self, action: Action) -> bool:
        return True


class DemoPerceptionAdapter(PerceptionAdapter):
    """模拟传感器 — 定时产生「系统健康检查」感知事件。"""

    def __init__(self, name: str = "demo"):
        self._name = name
        self._count = 0

    @property
    def name(self) -> str:
        return self._name

    async def poll(self) -> list[Percept]:
        self._count += 1
        # 前3次产生模拟感知，之后返回空（演示空闲检测）
        if self._count <= 3:
            return [
                Percept(
                    source="demo_sensor",
                    type="health_check",
                    data={"tick": self._count, "cpu": 45.2, "memory": 62.1},
                )
            ]
        return []


async def main():
    setup_logger(level="INFO")

    print("=" * 50)
    print("  衍灵内核 (YanLing Kernel) v0.1.0")
    print("  演示: 感知→认知→行动→进化 完整闭环")
    print("=" * 50)

    # 1. 配置
    config = Config()

    # 2. 适配器
    llm = DeepSeekAdapter(
        base_url=os.environ.get("ANTHROPIC_BASE_URL", "http://localhost:4000/v1/messages"),
        model=os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-flash"),
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
    )
    storage = JsonFileStorage(os.path.expanduser("~/.yanling/memory"))

    # 3. 子系统
    perception = PerceptionSystem()
    perception.register(DemoPerceptionAdapter())

    cognition = CognitiveEngine(llm)

    action_sys = ActionSystem()
    action_sys.register(ConsoleActionAdapter())

    memory = MemorySystem(storage)
    boundary = BoundaryControl(rules=[
        RateLimitRule(max_per_minute=30, max_per_hour=500),
        ScopeRule(allowed_types=["notify", "store", "analyze", "health_check"]),
    ])
    evolution = EvolutionEngine(memory, llm, cognition, deep_evolution_interval=10)

    # 4. 引擎
    engine = YanLingEngine(
        config=config,
        perception=perception,
        cognition=cognition,
        action=action_sys,
        memory=memory,
        evolution=evolution,
        boundary=boundary,
    )

    # 5. 启动
    try:
        await engine.start()
        print("\n  引擎运行中，将执行 3 次主循环后空闲...\n")

        # 运行一段时间后自动停止
        await asyncio.sleep(15)

    except KeyboardInterrupt:
        pass
    finally:
        await engine.stop()

    print("\n" + "=" * 50)
    print("  演示结束")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
