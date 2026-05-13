"""嵌入式监控场景 — 主入口.

模拟现场设备传感器数据采集 → 自主决策 → 告警 → 自我进化 的完整闭环。

运行方式:
    PYTHONPATH=/home/toto/yanling .venv/bin/python -m yanling.scenarios.embedded.main

支持两种模式:
    - rule: 规则驱动 (无需 LLM，适合离线/本地)
    - llm:  LLM 驱动 (需 AI Proxy 或 API 密钥)
"""

from __future__ import annotations

import asyncio
import os

from yanling.adapters.storage.json_file import JsonFileStorage
from yanling.core.config import Config
from yanling.core.logger import setup_logger
from yanling.kernel.action import ActionSystem
from yanling.kernel.boundary import BoundaryControl, ScopeRule
from yanling.kernel.engine import YanLingEngine
from yanling.kernel.evolution import EvolutionEngine
from yanling.kernel.memory import MemorySystem
from yanling.kernel.perception import PerceptionSystem
from yanling.kernel.rule_cognition import RuleCognitiveEngine, make_alert_rules, make_heartbeat_rule
from yanling.scenarios.base import Scenario
from yanling.scenarios.embedded.actions import AlertLogger, DeviceControl, SystemLog
from yanling.scenarios.embedded.sensor import SimulatedSensorAdapter

log = setup_logger("yanling.scenario.embedded", level="INFO")


class EmbeddedMonitorMode:
    """运行模式选择。"""
    RULE = "rule"
    LLM = "llm"


class EmbeddedMonitorScenario(Scenario):
    """嵌入式监控场景。"""

    def __init__(self, mode: str = EmbeddedMonitorMode.RULE):
        super().__init__("embedded")
        self.mode = mode
        self.sensor = SimulatedSensorAdapter()
        self.alert_logger = AlertLogger()
        self.system_log = SystemLog()
        self.device_control = DeviceControl()

        # 自定义配置
        self.config._data["kernel"]["tick_interval"] = 2.0
        self.config._data["kernel"]["max_idle_ticks"] = 1000
        self.config._data["boundaries"]["allowed_action_types"] = ["alert", "log", "adjust"]

    def build_engine(self) -> YanLingEngine:
        perception = PerceptionSystem()
        perception.register(self.sensor)

        action_sys = ActionSystem()
        action_sys.register(self.alert_logger)
        action_sys.register(self.system_log)
        action_sys.register(self.device_control)

        storage = JsonFileStorage(os.path.expanduser("~/.yanling/memory/embedded"))
        memory = MemorySystem(storage)
        boundary = BoundaryControl(rules=[
            ScopeRule(allowed_types=["alert", "log", "adjust"]),
        ])

        if self.mode == EmbeddedMonitorMode.RULE:
            cognition = RuleCognitiveEngine()
            for rule in make_alert_rules():
                cognition.add_rule(rule)
            cognition.add_rule(make_heartbeat_rule(interval_ticks=3))

            engine = YanLingEngine(
                config=self.config,
                perception=perception,
                action=action_sys,
                memory=memory,
                boundary=boundary,
            )
            # 规则模式没有 LLM，所以直接设置 cognition
            engine.cognition_rule = cognition

            # 改造主循环 — 在引擎启动后替换 cognition
            return engine
        else:
            # LLM 模式
            llm = self.create_llm()
            from yanling.kernel.cognition import CognitiveEngine
            cognition = CognitiveEngine(llm)
            evolution = EvolutionEngine(memory, llm, cognition, deep_evolution_interval=20)

            return YanLingEngine(
                config=self.config,
                perception=perception,
                cognition=cognition,
                action=action_sys,
                memory=memory,
                evolution=evolution,
                boundary=boundary,
            )


class PatchedEngine(YanLingEngine):
    """支持 RuleCognitiveEngine 的引擎变体。"""

    def __init__(self, *args, **kwargs):
        self.cognition_rule = None
        super().__init__(*args, **kwargs)

    async def _main_loop(self):
        """覆写主循环，支持规则引擎 + 世界模型。"""
        tick_count = 0
        import time as t_mod

        from yanling.core.types import TickResult as TR

        while not self._shutdown_event.is_set():
            try:
                tick_count += 1
                start_ts = t_mod.time()

                await self.bus.publish(Event("tick.start", {"tick": tick_count}))
                percepts = await self.perception.collect()

                # 世界模型观察
                self.world_model.observe(tick_count, percepts)

                if not percepts:
                    self._idle_ticks += 1
                else:
                    self._idle_ticks = 0

                if self._idle_ticks >= self._max_idle:
                    log.info("空闲超过 %d 个 tick，进入休眠", self._max_idle)
                    await asyncio.sleep(self.clock.interval * 10)
                    continue

                # 认知 — 融合世界模型上下文
                context = {}
                if self.memory:
                    context = await self.memory.recall_context()

                # 注入世界模型分析
                if tick_count % 5 == 0 and len(self.world_model._history) >= 5:
                    anomaly = self.world_model.detect_anomalies(tick_count, percepts)
                    pred = self.world_model.predict_next(tick_count, percepts)
                    context["world_model"] = {
                        "anomalies": [
                            {k: v for k, v in a.items() if k != "baseline_mean"}
                            for a in anomaly.anomalies
                        ],
                        "predicted_events": pred.predicted_event_types,
                        "prediction_confidence": round(pred.probability, 2),
                        "correlations_active": len(self.world_model.get_correlations(min_count=3)),
                    }

                cognition_result = None
                if self.cognition_rule:
                    cognition_result = await self.cognition_rule.reason(percepts, context)
                elif self.cognition:
                    cognition_result = await self.cognition.reason(percepts, context)

                # 行动
                action_results = []
                if cognition_result and cognition_result.decisions:
                    for decision in cognition_result.decisions:
                        for action in decision.actions:
                            check = self.boundary.check(action)
                            if check.denied:
                                continue
                            result = await self.action_sys.execute(action)
                            action_results.append(result)

                # 进化
                if self.evolution and cognition_result:
                    tick_res = TR(
                        tick_id=tick_count, perceptions=percepts,
                        cognition=cognition_result, actions=action_results,
                    )
                    await self.evolution.learn(percepts, cognition_result, tick_res)
                    if self.memory:
                        await self.memory.remember_tick(tick_res)

                elapsed = t_mod.time() - start_ts
                await self.bus.publish(Event("tick.end", {
                    "tick": tick_count, "percepts": len(percepts),
                    "actions": len(action_results), "duration": round(elapsed, 3),
                }))

                await self.boundary.throttle()
                sleep = self.clock.interval - elapsed
                if sleep > 0:
                    await asyncio.sleep(sleep)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("主循环异常: %s", e, exc_info=True)
                await asyncio.sleep(self.clock.interval)


from yanling.bus.event import Event


async def main_rule():
    """规则模式运行入口。"""
    print("=" * 56)
    print("  衍灵内核 × 嵌入式监控场景 (规则模式)")
    print("  模拟: 温度/振动/压力传感器 → 自主决策 → 告警 → 进化")
    print("=" * 56)

    config = Config()
    config._data["kernel"]["tick_interval"] = 2.0

    perception = PerceptionSystem()
    sensor = SimulatedSensorAdapter()
    perception.register(sensor)

    action_sys = ActionSystem()
    alert_logger = AlertLogger()
    system_log = SystemLog()
    device_control = DeviceControl()
    action_sys.register(alert_logger)
    action_sys.register(system_log)
    action_sys.register(device_control)

    storage = JsonFileStorage(os.path.expanduser("~/.yanling/memory/embedded"))
    memory = MemorySystem(storage)
    boundary = BoundaryControl(rules=[
        ScopeRule(allowed_types=["alert", "log", "adjust"]),
    ])

    cognition = RuleCognitiveEngine()
    for rule in make_alert_rules():
        cognition.add_rule(rule)
    cognition.add_rule(make_heartbeat_rule(interval_ticks=3))

    engine = PatchedEngine(
        config=config, perception=perception, action=action_sys,
        memory=memory, boundary=boundary,
    )
    engine.cognition_rule = cognition

    print("\n  启动引擎，运行 20 秒...\n")
    await engine.start()

    for i in range(10):
        await asyncio.sleep(2)
        alerts = alert_logger.recent(5)
        if alerts:
            for a in alerts:
                print(f"  [{a['time_str']}] 告警 #{a['id']} [{a['params'].get('level','')}] {a['params'].get('message','')}")
        else:
            print(f"  [tick {i*2+2}s] 无告警，系统运行正常")

    await engine.stop()

    print("\n  运行统计:")
    print(f"    总告警数: {alert_logger.alert_count}")
    print(f"    日志条目: {system_log.summary()['total_entries']}")
    print(f"    传感器读数: {sensor.anomaly_count} 次异常检测")
    print("=" * 56)


async def main_llm():
    """LLM 模式运行入口。"""
    print("=" * 56)
    print("  衍灵内核 × 嵌入式监控场景 (LLM 模式)")
    print("  传感器 → LLM 决策 → 告警 → 自我进化")
    print("=" * 56)

    config = Config()
    config._data["kernel"]["tick_interval"] = 3.0
    config._data["boundaries"]["allowed_action_types"] = ["alert", "log", "adjust"]

    perception = PerceptionSystem()
    sensor = SimulatedSensorAdapter()
    perception.register(sensor)

    action_sys = ActionSystem()
    alert_logger = AlertLogger()
    action_sys.register(alert_logger)
    action_sys.register(SystemLog())
    action_sys.register(DeviceControl())

    storage = JsonFileStorage(os.path.expanduser("~/.yanling/memory/embedded"))
    memory = MemorySystem(storage)
    boundary = BoundaryControl(rules=[
        ScopeRule(allowed_types=["alert", "log", "adjust"]),
    ])

    from yanling.adapters.llm.deepseek import DeepSeekAdapter
    llm = DeepSeekAdapter()
    from yanling.kernel.cognition import CognitiveEngine
    cognition = CognitiveEngine(llm)
    evolution = EvolutionEngine(memory, llm, cognition, deep_evolution_interval=10)

    engine = YanLingEngine(
        config=config, perception=perception, cognition=cognition,
        action=action_sys, memory=memory, evolution=evolution,
        boundary=boundary,
    )

    print("\n  启动引擎，运行 30 秒...\n")
    await engine.run(30.0)

    print("\n  运行统计:")
    print(f"    总告警数: {alert_logger.alert_count}")
    print(f"    传感器异常检测: {sensor.anomaly_count} 次")
    print(f"    进化调整次数: {len(evolution._adjustments)}")
    print(f"    性能趋势: {evolution.performance_summary['trend']}")
    print("=" * 56)


if __name__ == "__main__":
    mode = os.environ.get("EMBEDDED_MODE", "rule")
    if mode == "llm":
        asyncio.run(main_llm())
    else:
        asyncio.run(main_rule())
