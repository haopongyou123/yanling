"""衍灵引擎主循环 — 感知→认知→行动→进化."""

from __future__ import annotations

import asyncio
import logging
import os
import time

from yanling.bus.bus import EventBus
from yanling.bus.event import TICK_END, TICK_START, Event
from yanling.bus.middleware import logging_middleware, timestamp_middleware
from yanling.core.clock import Clock
from yanling.core.config import Config
from yanling.core.node import NodeIdentity, NodeRole
from yanling.core.types import TickResult
from yanling.kernel.action import ActionSystem
from yanling.kernel.boundary import BoundaryControl
from yanling.kernel.cognition import CognitiveEngine
from yanling.kernel.evolution import EvolutionEngine
from yanling.kernel.lifecycle import Lifecycle, State
from yanling.kernel.memory import MemorySystem
from yanling.kernel.perception import PerceptionSystem, TimerAdapter
from yanling.kernel.stats import EngineStats, TickMetrics
from yanling.kernel.world_model import WorldModel, WorldModelAdapter
from yanling.plugin.manager import PluginManager
from yanling.plugin.registry import PluginRegistry

try:
    from yanling.adapters.registry.blackboard import BlackboardRegistry
except ImportError:
    BlackboardRegistry = None  # registry 模块可选

try:
    from yanling.adapters.content.monitor import ContentMonitor, ContentSummaryAdapter
    from yanling.adapters.content.feedback import FeedbackCollector
    from yanling.adapters.content.optimizer import ContentStrategyOptimizer
    from yanling.adapters.content.scraper import PlatformStatsScraper
    HAS_CONTENT_ADAPTERS = True
except ImportError:
    HAS_CONTENT_ADAPTERS = False
    ContentMonitor = None
    FeedbackCollector = None
    ContentStrategyOptimizer = None
    PlatformStatsScraper = None

log = logging.getLogger("yanling.engine")


class YanLingEngine:
    """衍灵引擎 — 四阶段主循环控制器。"""

    def __init__(
        self,
        config: Config | None = None,
        perception: PerceptionSystem | None = None,
        cognition: CognitiveEngine | None = None,
        action: ActionSystem | None = None,
        memory: MemorySystem | None = None,
        evolution: EvolutionEngine | None = None,
        boundary: BoundaryControl | None = None,
        clock: Clock | None = None,
        bus: EventBus | None = None,
        node: NodeIdentity | None = None,
        world_model: WorldModel | None = None,
    ):
        self.config = config or Config()
        self.perception = perception or PerceptionSystem()
        self.cognition = cognition
        self.action_sys = action or ActionSystem()
        self.memory = memory
        self.evolution = evolution
        self.boundary = boundary or BoundaryControl()
        self.clock = clock or Clock(interval=self.config.get("kernel", "tick_interval", default=30))
        self.bus = bus or EventBus()
        self.lifecycle = Lifecycle()
        self.stats = EngineStats()
        self.node = node or NodeIdentity.detect()

        # 世界模型 — 状态追踪 + 因果推理上下文
        self.world_model = world_model or WorldModel(window_size=200)
        world_adapter = WorldModelAdapter(self.world_model, check_interval=5)
        self.perception.register(world_adapter)

        # 内容管道适配器
        self._content_monitor: ContentMonitor | None = None
        self._content_feedback: FeedbackCollector | None = None
        self._content_optimizer: ContentStrategyOptimizer | None = None
        if HAS_CONTENT_ADAPTERS:
            self._init_content_adapters()

        # 插件系统
        plugin_config_path = self.config.get("plugins", "config_path", default="")
        self.plugin_registry = PluginRegistry(config_path=plugin_config_path)
        self.plugin_manager = PluginManager(self.plugin_registry, self.bus)
        self.plugin_manager.bind_kernel(self)

        self._tick_count = 0
        self._idle_ticks = 0
        self._max_idle = self.config.get("kernel", "max_idle_ticks", default=100)
        self._shutdown_event = asyncio.Event()
        self._loop_task: asyncio.Task | None = None

        # 分布式节点注册
        self._registry: BlackboardRegistry | None = None
        if BlackboardRegistry is not None and self.node.role != NodeRole.EMBEDDED:
            self._registry = BlackboardRegistry()
        self._heartbeat_interval = 10  # 每 10 tick 发送一次心跳

        # 设置总线中间件
        self.bus.use(timestamp_middleware)
        self.bus.use(logging_middleware(log))

        # 注册默认的定时器感知
        self.perception.register(TimerAdapter(interval=self.clock.interval))

    def _init_content_adapters(self):
        """初始化内容管道适配器。"""
        try:
            self._content_monitor = ContentMonitor()
            self.perception.register(self._content_monitor)
            # 内容主题汇总适配器（每 10 tick 产主题趋势）
            summary_adapter = ContentSummaryAdapter(
                self._content_monitor, interval_ticks=10
            )
            self.perception.register(summary_adapter)

            self._content_feedback = FeedbackCollector()
            self.perception.register(self._content_feedback)

            # 平台统计采集器（每 30 tick 拉取掘金等平台的阅读/点赞数据）
            self._content_scraper = PlatformStatsScraper(
                feedback=self._content_feedback,
                batch_size=5,
                scrape_interval_ticks=30,
            )
            self.perception.register(self._content_scraper)

            self._content_optimizer = ContentStrategyOptimizer(
                feedback_collector=self._content_feedback,
                evolution=self.evolution,
                cooldown_ticks=50,
            )
            log.info("内容管道适配器已加载 (含平台采集器)")
        except Exception as e:
            log.warning("内容适配器加载失败（跳过）: %s", e)

    def set_llm_model(self, model: str, base_url: str | None = None, api_key: str | None = None):
        """运行时切换 LLM 模型。"""
        from yanling.adapters.llm.deepseek import DeepSeekAdapter

        api_key = api_key or os.environ.get("AI_API_KEY", "1234")
        base_url = base_url or os.environ.get("YANLING_LLM_BASE_URL",
                                               "http://localhost:4000/v1/messages")

        # 关闭旧适配器连接
        if self.cognition and hasattr(self.cognition, "llm") and self.cognition.llm:
            try:
                import asyncio
                asyncio.ensure_future(self._close_adapter(self.cognition.llm))
            except Exception:
                pass

        adapter = DeepSeekAdapter(base_url=base_url, model=model, api_key=api_key)
        if self.cognition and hasattr(self.cognition, "set_llm"):
            self.cognition.set_llm(adapter)
        if self.evolution and hasattr(self.evolution, "set_llm"):
            self.evolution.set_llm(adapter)
        log.info("引擎 LLM 模型已切换: %s (%s)", model, base_url)

    async def _close_adapter(self, adapter):
        """安全关闭 LLM 适配器的 HTTP 连接。"""
        if adapter and hasattr(adapter, "close"):
            try:
                await adapter.close()
            except Exception:
                pass

    def reset_to_baseline(self) -> bool:
        """恢复为内置基线模型（TinyLlama / Ollama）。"""
        try:
            from yanling.core.baseline import create_baseline_adapter

            # 关闭旧适配器连接
            if self.cognition and hasattr(self.cognition, "llm") and self.cognition.llm:
                try:
                    import asyncio
                    asyncio.ensure_future(self._close_adapter(self.cognition.llm))
                except Exception:
                    pass

            adapter = create_baseline_adapter()
            if self.cognition and hasattr(self.cognition, "set_llm"):
                self.cognition.set_llm(adapter)
            if self.evolution and hasattr(self.evolution, "set_llm"):
                self.evolution.set_llm(adapter)
            log.info("引擎已恢复为内置基线模型: %s", adapter.model_name)
            return True
        except Exception as e:
            log.error("基线模型加载失败: %s", e)
            return False

    @property
    def using_baseline(self) -> bool:
        """是否正在使用内置基线模型。"""
        if not self.cognition or not self.cognition.llm:
            return False
        name = getattr(self.cognition.llm, "model_name", "")
        provider = getattr(self.cognition.llm, "provider", "")
        return "tinyllama" in name.lower() or "ollama" in provider.lower()

    async def start(self):
        """启动引擎。"""
        if not await self.lifecycle.transition(State.STARTING):
            raise RuntimeError(f"引擎无法启动，当前状态: {self.lifecycle.state.value}")

        # 输出配置警告
        for w in self.config.warnings:
            log.warning("配置: %s", w)

        # 初始化各子系统
        await self.perception.start_all()
        await self.action_sys.start_all()
        if self.memory:
            await self.memory.initialize()
        if self.evolution and self.memory:
            self.evolution.memory = self.memory

        # 加载插件
        await self.plugin_registry.load()
        if self.config.get("plugins", "auto_load", default=True):
            await self.plugin_manager.load_all(enabled_only=True)

        await self.lifecycle.transition(State.RUNNING)
        if self._registry:
            await self._registry.register(self.node)
        self._loop_task = asyncio.create_task(self._main_loop())
        log.info("衍灵引擎已启动 (间隔: %.1fs)", self.clock.interval)

    async def stop(self):
        """停止引擎。"""
        if not await self.lifecycle.transition(State.STOPPING):
            return

        self._shutdown_event.set()
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass

        if self._registry:
            await self._registry.deregister()
            await self._registry.close()
        await self.perception.stop_all()
        await self.action_sys.stop_all()
        await self.plugin_manager.unload_all()
        await self.lifecycle.transition(State.STOPPED)
        log.info("衍灵引擎已停止")

    async def _main_loop(self):
        """主循环：感知→认知→行动→进化。"""
        while not self._shutdown_event.is_set():
            try:
                self._tick_count += 1
                start_ts = time.time()

                # 1. 感知
                await self.bus.publish(Event(TICK_START, {"tick": self._tick_count}))

                percepts = await self.perception.collect()

                # 1b. 世界模型观察 — 记录状态、检测异常、更新关联
                self.world_model.observe(self._tick_count, percepts)

                # 空闲检测
                if not percepts:
                    self._idle_ticks += 1
                else:
                    self._idle_ticks = 0

                if self._idle_ticks >= self._max_idle:
                    log.info("空闲超过 %d 个 tick，进入休眠", self._max_idle)
                    await asyncio.sleep(self.clock.interval * 10)
                    continue

                # 2. 认知 — 融合世界模型上下文
                context = {}
                if self.memory:
                    context = await self.memory.recall_context()

                # 注入世界模型分析结果到认知上下文
                if self._tick_count % 5 == 0 and len(self.world_model._history) >= 5:
                    anomaly = self.world_model.detect_anomalies(
                        self._tick_count, percepts)
                    pred = self.world_model.predict_next(
                        self._tick_count, percepts)
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
                if self.cognition:
                    cognition_result = await self.cognition.reason(percepts, context)

                # 3. 行动
                action_results = []
                if cognition_result and cognition_result.decisions:
                    for decision in cognition_result.decisions:
                        for action in decision.actions:
                            # 边界检查
                            check = self.boundary.check(action)
                            if check.denied:
                                log.warning("行动被拦截 [%s]: %s", action.type, check.reason)
                                continue
                            result = await self.action_sys.execute(action)
                            action_results.append(result)

                # 4. 进化（轻量学习）
                if self.evolution and cognition_result:
                    tick_result = TickResult(
                        tick_id=self._tick_count,
                        perceptions=percepts,
                        cognition=cognition_result,
                        actions=action_results,
                    )
                    await self.evolution.learn(percepts, cognition_result, tick_result)

                    # 记录到记忆
                    if self.memory:
                        await self.memory.remember_tick(tick_result)

                # 4b. 内容策略优化（每 50 tick 生成提案）
                if self._content_optimizer and self._tick_count % 50 == 0:
                    try:
                        self._content_optimizer.sync(self.world_model, self._tick_count)
                    except Exception as e:
                        log.warning("内容优化同步异常: %s", e)

                elapsed = time.time() - start_ts

                # 记录指标
                success_count = sum(1 for r in action_results if r.success)
                total_actions = len(action_results)
                self.stats.record_tick(TickMetrics(
                    tick_id=self._tick_count,
                    percepts=len(percepts),
                    decisions=len(cognition_result.decisions) if cognition_result else 0,
                    actions=total_actions,
                    success_rate=success_count / total_actions if total_actions > 0 else 1.0,
                    latency=elapsed,
                    tokens=cognition_result.tokens_used if cognition_result else 0,
                    error=cognition_result.error if cognition_result else None,
                ))

                await self.bus.publish(Event(TICK_END, {
                    "tick": self._tick_count,
                    "percepts": len(percepts),
                    "actions": len(action_results),
                    "duration": round(elapsed, 3),
                }))

                # 节流
                await self.boundary.throttle()

                # 黑板心跳（每 N tick）
                if self._registry and self._tick_count % self._heartbeat_interval == 0:
                    await self._registry.heartbeat(tick=self._tick_count)

                await asyncio.sleep(self.clock.interval - elapsed)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("主循环异常: %s", e, exc_info=True)
                await asyncio.sleep(self.clock.interval)
