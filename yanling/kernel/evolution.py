"""进化循环 — 模式提取 → 策略调整 → 回滚 完整的自我改进引擎."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from yanling.adapters.llm.base import LLMAdapter, LLMMessage
from yanling.core.types import (
    LANGUAGES,
    CognitionResult,
    EvolutionReport,
    EvolutionStep,
    Percept,
    TickResult,
)
from yanling.kernel.cognition import CognitiveEngine
from yanling.kernel.memory import MemorySystem

log = logging.getLogger("yanling.evolution")


@dataclass
class AdjustmentRecord:
    """一次策略调整的记录，支持回滚。"""
    id: str
    timestamp: float
    area: str                         # system_prompt | boundary | parameter
    old_value: Any
    new_value: Any
    reason: str
    outcome: str = "pending"          # pending | success | failure | rolled_back
    tokens_used: int = 0


class StrategySnapshot:
    """认知策略快照，用于回滚。"""

    def __init__(self, system_prompt: str, extra: dict | None = None):
        self.system_prompt = system_prompt
        self.extra = extra or {}
        self.timestamp = time.time()


class PerformanceTracker:
    """性能追踪 — 记录指标随时间的变化。"""

    def __init__(self, window: int = 50):
        self.window = window
        self._ticks: list[dict] = []

    def record(self, tick_id: int, success_rate: float, latency: float, tokens: int):
        self._ticks.append({
            "tick": tick_id,
            "success_rate": success_rate,
            "latency": latency,
            "tokens": tokens,
            "timestamp": time.time(),
        })
        if len(self._ticks) > self.window:
            self._ticks.pop(0)

    def trend(self, metric: str = "success_rate") -> float:
        """返回指标的趋势斜率（正 = 改善，负 = 恶化）。"""
        if len(self._ticks) < 3:
            return 0.0
        recent = self._ticks[-min(10, len(self._ticks)):]
        values = [t[metric] for t in recent]
        if len(values) < 2:
            return 0.0
        # 简单线性近似：比较前半和后半均值
        half = len(values) // 2
        if half == 0:
            return 0.0
        first_half = sum(values[:half]) / half
        second_half = sum(values[half:]) / (len(values) - half)
        return second_half - first_half

    def summary(self) -> dict:
        if not self._ticks:
            return {"avg_success_rate": 0, "avg_latency": 0, "trend": "stable"}
        recent = self._ticks[-min(10, len(self._ticks)):]
        avg_success = sum(t["success_rate"] for t in recent) / len(recent)
        avg_latency = sum(t["latency"] for t in recent) / len(recent)
        trend_val = self.trend("success_rate")
        if trend_val > 0.05:
            trend = "improving"
        elif trend_val < -0.05:
            trend = "declining"
        else:
            trend = "stable"
        return {
            "avg_success_rate": round(avg_success, 3),
            "avg_latency": round(avg_latency, 3),
            "trend": trend,
            "samples": len(recent),
        }


class EvolutionEngine:
    """进化引擎 — 每次 tick 后轻量学习 + 定期深度进化。"""

    def __init__(
        self,
        memory: MemorySystem,
        llm: LLMAdapter | None = None,
        cognition: CognitiveEngine | None = None,
        deep_evolution_interval: int = 100,
        language: str = "zh",
    ):
        self.memory = memory
        self.llm = llm
        self.cognition = cognition
        self.deep_evolution_interval = deep_evolution_interval
        self.language = language
        self._tick_count = 0
        self._steps: list[EvolutionStep] = []
        self._adjustments: list[AdjustmentRecord] = []
        self._snapshots: list[StrategySnapshot] = []
        self._performance = PerformanceTracker(window=100)
        self._pattern_db: dict[str, int] = defaultdict(int)  # 模式 → 出现次数
        self._reports: list[dict] = []  # 进化报告历史

    def set_llm(self, llm):
        """运行时切换 LLM 适配器。"""
        self.llm = llm
        log.info("进化引擎 LLM 已切换")

    # ─── 每次 tick 后的轻量学习 ────────────────────────────────

    async def learn(
        self,
        percepts: list[Percept],
        cognition_result: CognitionResult,
        tick_result: TickResult,
    ) -> str:
        self._tick_count += 1

        # 性能追踪
        success_count = sum(1 for a in tick_result.actions if a.success)
        total = len(tick_result.actions)
        success_rate = success_count / total if total > 0 else 1.0
        self._performance.record(
            tick_id=tick_result.tick_id,
            success_rate=success_rate,
            latency=tick_result.duration,
            tokens=cognition_result.tokens_used,
        )

        # 失败分析
        failed_actions = [a for a in tick_result.actions if not a.success]
        if failed_actions or cognition_result.error:
            observation = self._analyze_failure(tick_result, failed_actions, cognition_result)
            self._record_step(tick_result, observation)
            self._extract_patterns(tick_result, observation)
        else:
            observation = "ok"

        # 趋势恶化时自动触发深度进化
        trend = self._performance.trend("success_rate")
        if trend < -0.1 and self._tick_count > 10:
            log.info("性能趋势恶化 (%.3f)，触发深度进化", trend)
            await self.evolve()

        # 定期深度进化
        if self._tick_count % self.deep_evolution_interval == 0:
            await self.evolve()

        return observation

    def _analyze_failure(
        self,
        tick_result: TickResult,
        failed_actions: list,
        cognition_result: CognitionResult,
    ) -> str:
        parts = [f"tick {tick_result.tick_id}"]
        if failed_actions:
            errors = [a.error or a.action_id for a in failed_actions]
            parts.append(f"行动失败: {errors[:3]}")
        if cognition_result.error:
            parts.append(f"认知错误: {cognition_result.error[:100]}")
        return ", ".join(parts)

    def _record_step(self, tick_result: TickResult, observation: str):
        self._steps.append(EvolutionStep(
            tick_id=tick_result.tick_id,
            observation=observation,
            adjustment="",
            reason="自动记录",
            success=False,
            metrics={"actions": len(tick_result.actions)},
        ))
        log.info("进化: %s", observation)

    def _extract_patterns(self, tick_result: TickResult, observation: str):
        """从失败中提取可复用的模式。"""
        for action_result in tick_result.actions:
            if not action_result.success:
                pattern_key = f"fail:{action_result.action_id}"
                self._pattern_db[pattern_key] += 1

        if cognition_result := tick_result.cognition:
            for d in cognition_result.decisions:
                if d.intent.name == "ESCALATE":
                    self._pattern_db["intent:escalate"] += 1

    # ─── 深度进化 ──────────────────────────────────────────────

    async def evolve(self) -> EvolutionReport:
        """深度进化 — LLM 分析模式 → 调整策略 → 记录快照。"""
        log.info("开始深度进化 (tick #%d)", self._tick_count)

        perf_summary = self._performance.summary()
        recent_steps = self._steps[-30:] if len(self._steps) > 30 else self._steps
        top_patterns = sorted(self._pattern_db.items(), key=lambda x: -x[1])[:10]

        context = {
            "total_ticks": self._tick_count,
            "performance": perf_summary,
            "recent_failures": len([s for s in recent_steps if not s.success]),
            "top_patterns": [{"pattern": p, "count": c} for p, c in top_patterns],
            "adjustments_made": len(self._adjustments),
        }

        if not self.llm:
            log.info("无 LLM 可用，跳过深度进化 (模式追踪继续)")
            return EvolutionReport(
                timestamp=time.time(),
                patterns_found=[str(p) for p, _ in top_patterns],
                adjustments=[],
                recommendations=["无 LLM，跳过深度进化"],
                performance_delta=perf_summary,
            )

        try:
            messages = [
                LLMMessage(role="system", content=self._evolution_prompt()),
                LLMMessage(role="user", content=json.dumps(context, ensure_ascii=False, indent=2)),
            ]

            response = await self.llm.chat(messages, temperature=0.4)
            report = self._parse_evolution_response(response.content)

            # 执行策略调整
            for adj in report.adjustments:
                self._apply_adjustment(adj)

            log.info(
                "深度进化完成: %d 个调整, 趋势=%s",
                len(report.adjustments), perf_summary["trend"]
            )
            self._save_report(report)
            return report

        except Exception as e:
            log.error("深度进化失败: %s", e)
            report = EvolutionReport(
                timestamp=time.time(),
                patterns_found=[str(p) for p, _ in top_patterns],
                adjustments=[],
                recommendations=[f"进化异常: {e}"],
                performance_delta={"trend": perf_summary["trend"]},
            )
            self._save_report(report)
            return report

    def _evolution_prompt(self) -> str:
        lang_cfg = LANGUAGES.get(self.language, LANGUAGES["zh"])
        return f"""You are an evolution engine for an autonomous AI kernel. Analyze performance patterns and suggest strategy adjustments.

{lang_cfg["prompt"]}

Output a JSON object with the following structure:
{{
  "analysis": "Summary of current performance trends and key issues",
  "patterns": ["pattern_1", "pattern_2"],
  "adjustments": [
    {{
      "change": "system_prompt: <new prompt instruction>",
      "reason": "why this change is needed"
    }}
  ],
  "recommendations": ["recommendation_1", "recommendation_2"]
}}

Rules:
- Only suggest adjustments if there is a clear degrading trend
- Adjustments can target: system_prompt, boundary, parameter
- Keep recommendations actionable and specific
- If performance is stable or improving, set adjustments to empty

语言要求: {lang_cfg["prompt"]}"""

    def _parse_evolution_response(self, content: str) -> EvolutionReport:
        if not content or not content.strip():
            log.warning("进化响应为空")
            return EvolutionReport(
                timestamp=time.time(), patterns_found=[], adjustments=[],
                recommendations=["LLM 返回空响应"],
                performance_delta=self._performance.summary(),
            )

        # 尝试从响应中提取 JSON
        data = None
        start = content.find("{")
        idx = content.rfind("}")
        while start >= 0 and idx >= 0 and start < idx and data is None:
            candidate = content[start:idx+1]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    # 修正常见拼写
                    key_map = {"analysi": "analysis", "analyis": "analysis",
                               "performace": "performance", "total_tick": "total_ticks"}
                    for old_k, new_k in key_map.items():
                        if old_k in parsed:
                            parsed[new_k] = parsed.pop(old_k)
                    if "analysis" in parsed or "patterns" in parsed:
                        data = parsed
            except json.JSONDecodeError:
                pass
            # 尝试更小的 JSON 块
            idx = content.rfind("}", 0, idx)
            if idx <= start:
                start = content.find("{", start + 1)
                idx = content.rfind("}")

        if data:
            try:
                adjustments = []
                for a in data.get("adjustments", []):
                    adjustments.append(EvolutionStep(
                        tick_id=self._tick_count,
                        observation=a.get("change", "") if isinstance(a, dict) else "",
                        adjustment=a.get("change", "") if isinstance(a, dict) else "",
                        reason=a.get("reason", "") if isinstance(a, dict) else "",
                    ))
                return EvolutionReport(
                    timestamp=time.time(),
                    patterns_found=data.get("patterns", []),
                    adjustments=adjustments,
                    recommendations=data.get("recommendations", []),
                    performance_delta=self._performance.summary(),
                )
            except (KeyError, IndexError, AttributeError) as e:
                log.warning("进化响应字段提取失败: %s", e)

        # Fallback: 将 LLM 原始响应作为推荐信息
        lines = [l.strip() for l in content.strip().split("\n") if len(l.strip()) > 10]
        log.info("进化 LLM 分析: %s", lines[0] if lines else content[:80])
        return EvolutionReport(
            timestamp=time.time(), patterns_found=[], adjustments=[],
            recommendations=lines[:3] or [content[:200]],
            performance_delta=self._performance.summary(),
        )

    # ─── 策略调整与回滚 ────────────────────────────────────────

    def _apply_adjustment(self, step: EvolutionStep):
        """执行一次策略调整并记录快照。"""
        area = step.adjustment.split(":")[0] if ":" in step.adjustment else "system_prompt"

        if area == "system_prompt" and self.cognition:
            self._snapshots.append(StrategySnapshot(
                system_prompt=self.cognition._system_prompt,
            ))
            self.cognition.update_system_prompt(step.adjustment)

        record = AdjustmentRecord(
            id=f"adj_{self._tick_count}_{len(self._adjustments)}",
            timestamp=time.time(),
            area=area,
            old_value=self._snapshots[-1].system_prompt if self._snapshots else "",
            new_value=step.adjustment,
            reason=step.reason,
        )
        self._adjustments.append(record)
        log.info("策略调整 [%s]: %s", area, step.reason[:80])

    def rollback(self, steps: int = 1) -> bool:
        """回滚最近的 N 次调整。"""
        if not self._snapshots:
            log.warning("无快照可回滚")
            return False
        if not self.cognition:
            return False

        for _ in range(min(steps, len(self._snapshots))):
            snapshot = self._snapshots.pop()
        last = self._snapshots[-1] if self._snapshots else snapshot
        self.cognition.update_system_prompt(last.system_prompt)
        for record in self._adjustments[-steps:]:
            record.outcome = "rolled_back"
        log.info("回滚了 %d 步调整", steps)
        return True

    @property
    def adjustment_history(self) -> list[AdjustmentRecord]:
        return list(self._adjustments)

    @property
    def performance_summary(self) -> dict:
        return self._performance.summary()

    @property
    def reports(self) -> list[dict]:
        return list(self._reports)

    def _save_report(self, report: EvolutionReport):
        self._reports.append({
            "tick": self._tick_count,
            "time": __import__("time").strftime("%H:%M:%S"),
            "analysis": report.recommendations[0] if report.recommendations else "",
            "patterns": report.patterns_found[:5],
            "recommendations": report.recommendations[:5],
            "adjustments_count": len(report.adjustments),
        })
        if len(self._reports) > 50:
            self._reports.pop(0)

    @property
    def pattern_db(self) -> dict[str, int]:
        return dict(self._pattern_db)

    @property
    def steps(self) -> list[EvolutionStep]:
        return list(self._steps)
