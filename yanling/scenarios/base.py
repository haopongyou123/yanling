"""场景基类 — 快速配置和启动衍灵引擎的辅助工具."""

from __future__ import annotations

import asyncio
import logging

from yanling.adapters.llm.base import LLMAdapter
from yanling.adapters.llm.deepseek import DeepSeekAdapter
from yanling.adapters.llm.fallback import FallbackAdapter
from yanling.adapters.llm.omix import OmixAdapter
from yanling.adapters.storage.json_file import JsonFileStorage
from yanling.core.config import Config
from yanling.core.logger import setup_logger
from yanling.kernel.engine import YanLingEngine

log = logging.getLogger("yanling.scenario")


class Scenario:
    """场景基类 — 封装发动机器人的模板方法。"""

    def __init__(self, name: str, config: Config | None = None):
        self.name = name
        self.config = config or Config()
        self.engine: YanLingEngine | None = None

    def setup_logging(self, level: str = "INFO", log_file: str | None = None):
        setup_logger(f"yanling.{self.name}", level=level, log_file=log_file)

    def create_llm(self) -> LLMAdapter:
        """创建 LLM 适配器（含自动降级）。"""
        cfg = self.config
        primary = DeepSeekAdapter(
            base_url=cfg.get("llm", "base_url", default="http://localhost:4000/v1/messages"),
            model=cfg.get("llm", "model", default="deepseek-v4-flash"),
            api_key=cfg.get("llm", "api_key", default=""),
        )

        if cfg.get("llm", "fallback", default=True):
            fallback_order = cfg.get("llm", "fallback_order", default=["deepseek", "openrouter", "omix"])
            providers = [primary]
            if "omix" in fallback_order or "omix_local" in fallback_order:
                providers.append(OmixAdapter())
            return FallbackAdapter(providers) if len(providers) > 1 else primary

        return primary

    def create_storage(self) -> JsonFileStorage:
        path = self.config.get("memory", "storage_path",
                                default=str(__import__("pathlib").Path.home() / ".yanling" / "memory"))
        return JsonFileStorage(path)

    async def run(self, duration: float = 30.0) -> YanLingEngine:
        """启动并运行场景。"""
        log.info("场景 [%s] 启动 (运行 %.1fs)", self.name, duration)
        engine = self.build_engine()
        self.engine = engine
        await engine.start()
        await asyncio.sleep(duration)
        await engine.stop()
        log.info("场景 [%s] 结束", self.name)
        return engine

    def build_engine(self) -> YanLingEngine:
        """子类覆盖此方法构建自定义引擎。"""
        raise NotImplementedError
