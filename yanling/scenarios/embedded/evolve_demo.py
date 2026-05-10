"""进化实战验证 — 长时间运行，观察进化引擎的真实表现。

模拟传感器持续产生异常，规则引擎决策，进化引擎追踪模式和性能趋势。
通过 Web 面板 (端口 8764) 实时观察。

用法:
    PYTHONPATH=/home/toto/yanling .venv/bin/python -m yanling.scenarios.embedded.evolve_demo

    # 带 Web 面板 (同进程)
    PYTHONPATH=/home/toto/yanling .venv/bin/python -m yanling.scenarios.embedded.evolve_demo --web

    # 控制异常频率 (默认 0.3 = 30% tick 产生异常)
    ANOMALY_RATE=0.5 PYTHONPATH=/home/toto/yanling .venv/bin/python -m yanling.scenarios.embedded.evolve_demo --web
"""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import time

from yanling.adapters.llm.ollama import OllamaAdapter
from yanling.adapters.storage.json_file import JsonFileStorage
from yanling.bus.event import Event
from yanling.core.config import Config
from yanling.core.logger import setup_logger
from yanling.core.types import Action
from yanling.core.types import ActionResult as AR
from yanling.core.types import TickResult as TR
from yanling.kernel.action import ActionAdapter


class FlakyAction(ActionAdapter):
    """抽风行动适配器 — 随机失败，模拟不稳定的执行环境。"""

    def __init__(self, fail_rate: float = 0.4):
        super().__init__()
        self.fail_rate = fail_rate
        self.fail_count = 0
        self.total_count = 0

    @property
    def name(self) -> str:
        return "flaky_adjust"

    async def execute(self, action: Action) -> AR:
        self.total_count += 1
        import random
        if random.random() < self.fail_rate:
            self.fail_count += 1
            return AR(action_id=action.id, success=False, error="抽风行动随机失败")
        return AR(action_id=action.id, success=True, output="抽风行动成功")

    async def validate(self, action: Action) -> bool:
        return True
from yanling.kernel.action import ActionSystem
from yanling.kernel.boundary import BoundaryControl, ScopeRule
from yanling.kernel.engine import YanLingEngine
from yanling.kernel.evolution import EvolutionEngine
from yanling.kernel.memory import MemorySystem
from yanling.kernel.perception import PerceptionSystem
from yanling.kernel.rule_cognition import RuleCognitiveEngine, make_alert_rules, make_heartbeat_rule
from yanling.scenarios.embedded.actions import AlertLogger, DeviceControl, SystemLog
from yanling.scenarios.embedded.sensor import SimulatedSensorAdapter

log = setup_logger("yanling.evolve_demo", level="INFO")
setup_logger("yanling.evolution", level="INFO")  # 确保进化引擎日志输出


class EvolveDemo:
    """进化验证器 — 长时间运行，观察进化系统的真实表现。"""

    def __init__(self, anomaly_rate: float = 0.3, web: bool = False, web_port: int = 8764, use_llm: bool = False):
        self.anomaly_rate = anomaly_rate
        self.web = web
        self.web_port = web_port
        self.use_llm = use_llm
        self.llm_model = "tinyllama:latest"
        self._engine: YanLingEngine | None = None
        self._stop_event = asyncio.Event()

    def build_engine(self) -> YanLingEngine:
        """构建引擎 — 规则模式 + 进化追踪。"""
        config = Config()
        config._data["kernel"]["tick_interval"] = 2.0
        config._data["kernel"]["max_idle_ticks"] = 10000
        config._data["boundaries"]["allowed_action_types"] = ["alert", "log", "adjust"]

        # 传感器 — 提高异常频率
        sensor = SimulatedSensorAdapter()

        perception = PerceptionSystem()
        perception.register(sensor)

        # 行动适配器
        action_sys = ActionSystem()
        alert_logger = AlertLogger()
        system_log = SystemLog()
        device_control = DeviceControl()
        flaky = FlakyAction(fail_rate=0.4)
        action_sys.register(alert_logger)
        action_sys.register(system_log)
        action_sys.register(device_control)
        action_sys.register(flaky)

        # 边界
        boundary = BoundaryControl(rules=[
            ScopeRule(allowed_types=["alert", "log", "adjust"]),
        ])

        # 记忆
        storage = JsonFileStorage(os.path.expanduser("~/.yanling/memory/evolve_demo"))
        memory = MemorySystem(storage)

        # 规则认知
        cognition = RuleCognitiveEngine()
        for rule in make_alert_rules():
            cognition.add_rule(rule)
        cognition.add_rule(make_heartbeat_rule(interval_ticks=3))

        # 添加抽风规则 — 异常时触发告警 + 尝试调整设备
        from yanling.kernel.rule_cognition import Rule
        cognition.add_rule(Rule(
            name="alert_and_adjust_on_anomaly",
            priority=75,
            match=lambda percepts: any(
                p.data.get("alert", "normal") != "normal" for p in percepts
            ),
            actions=[Action(type="alert", target="alert_logger",
                           params={"message": "异常检测", "level": "warning"},
                           id="anomaly_alert"),
                    Action(type="adjust", target="flaky_adjust", params={},
                           id="adjust_device")],
        ))

        # 进化引擎 + 可选 LLM 深度进化
        llm = OllamaAdapter(model=self.llm_model, timeout=30) if self.use_llm else None
        evolution = EvolutionEngine(memory, llm=llm, cognition=None, deep_evolution_interval=50)

        # 引擎
        engine = _PatchedEvolveEngine(
            config=config,
            perception=perception,
            action=action_sys,
            memory=memory,
            evolution=evolution,
            boundary=boundary,
        )
        engine._cognition_rule = cognition
        engine._anomaly_rate = self.anomaly_rate
        engine._alert_logger = alert_logger
        engine._system_log = system_log
        self._engine = engine
        return engine

    async def run(self):
        engine = self.build_engine()

        # 注册 Web 面板
        if self.web:
            from yanling.web.registry import register as reg_engine
            reg_engine(engine)
            log.info("Web 面板 http://0.0.0.0:%d", self.web_port)
            import uvicorn

            from yanling.web.dashboard import app as web_app
            web_cfg = uvicorn.Config(web_app, host="0.0.0.0", port=self.web_port, log_level="info")
            web_task = asyncio.create_task(uvicorn.Server(web_cfg).serve())
        else:
            web_task = None

        # 信号处理
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop_event.set)
            except NotImplementedError:
                pass

        await engine.start()

        # 状态报告循环
        report_interval = 30  # 每 30 秒报告一次
        last_report = time.time()

        print(f"\n{'='*56}")
        print("  进化实战验证")
        print(f"  异常频率: {self.anomaly_rate:.0%}")
        print(f"  LLM 深度进化: {'已开启 (Ollama ' + self.llm_model + ')' if self.use_llm else '未开启'}")
        print(f"  Web 面板: {'http://0.0.0.0:' + str(self.web_port) if self.web else '未启动'}")
        print("  Ctrl+C 停止")
        print(f"{'='*56}\n")

        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(1)

                # 定期报告
                now = time.time()
                if now - last_report >= report_interval:
                    self._print_status(engine)
                    last_report = now
        finally:
            print("\n正在停止...")
            if web_task:
                web_task.cancel()
            await engine.stop()

        # 最终报告
        print(f"\n{'='*56}")
        print("  进化验证完成")
        self._print_status(engine)
        print(f"{'='*56}")

    def _print_status(self, engine):
        """打印当前状态摘要。"""
        evo = engine.evolution
        perf = evo.performance_summary if evo else {}
        patterns = evo.pattern_db if evo else {}
        adjustments = evo.adjustment_history if evo else []

        trend_icon = {"improving": "📈", "declining": "📉", "stable": "→"}
        trend = perf.get("trend", "stable")

        print(f"\n  [{time.strftime('%H:%M:%S')}] Tick #{engine._tick_count}")
        print(f"    成功率: {perf.get('avg_success_rate', 0)*100:.1f}%  "
              f"延迟: {perf.get('avg_latency', 0)*1000:.0f}ms  "
              f"趋势: {trend_icon.get(trend, '')} {trend}")
        print(f"    模式库: {len(patterns)} 种  "
              f"策略调整: {len(adjustments)} 次  "
              f"记忆条目: {len(engine.memory.long_term._entries) if engine.memory else 0}")

        if patterns:
            top = sorted(patterns.items(), key=lambda x: -x[1])[:3]
            print(f"    热门模式: {', '.join(f'{p}({c})' for p, c in top)}")


class _PatchedEvolveEngine(YanLingEngine):
    """支持规则认知 + 进化追踪的引擎变体。"""

    def __init__(self, *args, **kwargs):
        self._cognition_rule = None
        self._anomaly_rate = 0.3
        self._alert_logger = None
        self._system_log = None
        super().__init__(*args, **kwargs)

    async def _main_loop(self):
        tick_count = 0
        while not self._shutdown_event.is_set():
            try:
                tick_count += 1
                self._tick_count = tick_count
                start_ts = time.time()

                await self.bus.publish(Event("tick.start", {"tick": tick_count}))
                percepts = await self.perception.collect()

                if not percepts:
                    self._idle_ticks += 1
                else:
                    self._idle_ticks = 0

                if self._idle_ticks >= self._max_idle:
                    await asyncio.sleep(self.clock.interval * 10)
                    continue

                # 认知
                context = {}
                if self.memory:
                    context = await self.memory.recall_context()

                cognition_result = None
                if self._cognition_rule:
                    cognition_result = await self._cognition_rule.reason(percepts, context)
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

                elapsed = time.time() - start_ts

                # 记录指标
                success_count = sum(1 for r in action_results if r.success)
                total_actions = len(action_results)
                from yanling.kernel.stats import TickMetrics
                self.stats.record_tick(TickMetrics(
                    tick_id=tick_count,
                    percepts=len(percepts),
                    decisions=len(cognition_result.decisions) if cognition_result else 0,
                    actions=total_actions,
                    success_rate=success_count / total_actions if total_actions > 0 else 1.0,
                    latency=elapsed,
                ))

                await self.bus.publish(Event("tick.end", {
                    "tick": tick_count, "percepts": len(percepts),
                    "actions": len(action_results), "duration": round(elapsed, 3),
                }))

                sleep = self.clock.interval - elapsed
                if sleep > 0:
                    await asyncio.sleep(sleep)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("主循环异常: %s", e, exc_info=True)
                await asyncio.sleep(self.clock.interval)


def main():
    parser = argparse.ArgumentParser(description="衍灵进化实战验证")
    parser.add_argument("--web", action="store_true", help="启动 Web 面板")
    parser.add_argument("--port", type=int, default=8764, help="Web 面板端口")
    parser.add_argument("--llm", action="store_true", help="启用 LLM 深度进化 (Ollama)")
    parser.add_argument("--anomaly-rate", type=float, default=0.3,
                        help="异常频率 (0-1), 默认 0.3")
    args = parser.parse_args()

    demo = EvolveDemo(
        anomaly_rate=args.anomaly_rate,
        web=args.web,
        web_port=args.port,
        use_llm=args.llm,
    )
    asyncio.run(demo.run())


if __name__ == "__main__":
    main()
