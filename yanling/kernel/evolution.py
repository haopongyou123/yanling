"""进化循环 — 模式提取 → 策略调整 → 回滚 完整的自我改进引擎.

增强：自助化进化 — 不依赖 LLM 也能做规则驱动的自我改进。
- 规则驱动自助提案（无需 LLM）
- 影响分析（调整前预估影响范围）
- 安全回滚评估（回滚后判断是否改善）
- 模式驱动自动调参
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
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
    impact_assessment: str = ""       # 调整前预估影响


@dataclass
class ImprovementProposal:
    """自助改进提案（无需 LLM 可生成）。"""
    area: str
    title: str
    description: str
    trigger: str                       # 触发条件描述
    confidence: float                  # 置信度 [0,1]
    estimated_impact: str              # high | medium | low
    related_patterns: list[str] = field(default_factory=list)


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
        half = len(values) // 2
        if half == 0:
            return 0.0
        first_half = sum(values[:half]) / half
        second_half = sum(values[half:]) / (len(values) - half)
        return second_half - first_half

    def volatility(self, metric: str = "latency") -> float:
        """返回指标波动率（标准差/均值），越大越不稳定。"""
        if len(self._ticks) < 3:
            return 0.0
        recent = self._ticks[-min(20, len(self._ticks)):]
        values = [t[metric] for t in recent]
        if not values:
            return 0.0
        avg = sum(values) / len(values)
        if avg == 0:
            return 0.0
        variance = sum((v - avg) ** 2 for v in values) / len(values)
        return (variance ** 0.5) / avg

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
            "volatility": round(self.volatility(), 3),
        }


class EvolutionEngine:
    """进化引擎 — 每次 tick 后轻量学习 + 自助提案 + 定期深度进化。"""

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
        self._pattern_db: dict[str, int] = defaultdict(int)
        self._reports: list[dict] = []
        # 自助提案跟踪
        self._proposals: list[ImprovementProposal] = []
        self._consecutive_failures = 0
        self._last_adjustment_tick = 0
        self._adjustment_cooldown = 20  # 调整冷却 tick 数

    def set_llm(self, llm):
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

        # 连续失败计数
        if total > 0 and success_rate < 0.5:
            self._consecutive_failures += 1
        else:
            self._consecutive_failures = 0

        # 失败分析
        failed_actions = [a for a in tick_result.actions if not a.success]
        if failed_actions or cognition_result.error:
            observation = self._analyze_failure(tick_result, failed_actions, cognition_result)
            self._record_step(tick_result, observation)
            self._extract_patterns(tick_result, observation)
        else:
            observation = "ok"

        # 自助提案（无需 LLM）
        proposals = self._generate_proposals()
        if proposals:
            self._proposals.extend(proposals)

        # 自助调参（高频失败模式触发）
        if self._consecutive_failures >= 5:
            self._auto_tune_on_failure(tick_result)

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
            # 按类型归类失败
            type_fails = defaultdict(int)
            for a in failed_actions:
                type_fails[a.type] += 1
            if type_fails:
                top_type = max(type_fails, key=type_fails.get)
                parts.append(f"高频失败类型: {top_type}({type_fails[top_type]}次)")
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
        for action_result in tick_result.actions:
            if not action_result.success:
                pattern_key = f"fail:{action_result.action_id}"
                self._pattern_db[pattern_key] += 1
                # 细化模式：按类型
                type_key = f"fail_type:{action_result.type}"
                self._pattern_db[type_key] += 1

        if cognition_result := tick_result.cognition:
            for d in cognition_result.decisions:
                if d.intent.name == "ESCALATE":
                    self._pattern_db["intent:escalate"] += 1

    # ─── 自助提案 ──────────────────────────────────────────────

    def _generate_proposals(self) -> list[ImprovementProposal]:
        """基于规则自助生成改进提案（无需 LLM）。"""
        proposals: list[ImprovementProposal] = []
        perf = self._performance.summary()

        # 1. 成功率过低 → 建议降级策略
        if perf["avg_success_rate"] < 0.6 and perf["samples"] >= 5:
            proposals.append(ImprovementProposal(
                area="parameter",
                title="成功率过低，建议降级操作策略",
                description=f"平均成功率 {perf['avg_success_rate']:.0%}，"
                           f"建议减少高风险操作比例",
                trigger=f"success_rate={perf['avg_success_rate']:.3f}",
                confidence=0.7,
                estimated_impact="high",
                related_patterns=[
                    p for p, c in self._pattern_db.items()
                    if c >= 3 and p.startswith("fail_type:")
                ],
            ))

        # 2. 延迟波动过大 → 建议节流
        if perf.get("volatility", 0) > 0.5 and perf["samples"] >= 5:
            proposals.append(ImprovementProposal(
                area="parameter",
                title="延迟波动过高，建议增加节流",
                description=f"延迟波动率 {perf['volatility']:.2f}，操作负载不均",
                trigger=f"volatility={perf['volatility']:.3f}",
                confidence=0.6,
                estimated_impact="medium",
            ))

        # 3. 连续失败 → 建议暂停高风险操作
        if self._consecutive_failures >= 3:
            proposals.append(ImprovementProposal(
                area="boundary",
                title="连续失败，建议暂停高频失败操作",
                description=f"连续 {self._consecutive_failures} tick 成功率 < 50%",
                trigger=f"consecutive_failures={self._consecutive_failures}",
                confidence=0.8,
                estimated_impact="high",
            ))

        # 4. 模式积累过多 → 建议清理或总结
        if len(self._pattern_db) > 20:
            proposals.append(ImprovementProposal(
                area="system_prompt",
                title="失败模式过多，建议优化策略",
                description=f"{len(self._pattern_db)} 种失败模式积累，需要策略级优化",
                trigger=f"pattern_count={len(self._pattern_db)}",
                confidence=0.5,
                estimated_impact="medium",
            ))

        return proposals

    def _auto_tune_on_failure(self, tick_result: TickResult):
        """连续失败时自助调参。"""
        if self._tick_count - self._last_adjustment_tick < self._adjustment_cooldown:
            return  # 冷却中

        # 分析哪个类型失败最多
        type_fails = defaultdict(int)
        all_actions = defaultdict(int)
        for a in tick_result.actions:
            all_actions[a.type] += 1
            if not a.success:
                type_fails[a.type] += 1

        if not type_fails:
            return

        worst_type = max(type_fails, key=type_fails.get)
        worst_count = type_fails[worst_type]
        total_count = all_actions.get(worst_type, 1)
        fail_ratio = worst_count / total_count

        if fail_ratio > 0.5 and self.cognition:
            prompt_adj = (
                f"操作类型 '{worst_type}' 失败率 {fail_ratio:.0%} "
                f"(连续 {self._consecutive_failures} tick)，"
                f"建议降低 '{worst_type}' 操作频率或增加前置条件检查。"
            )
            self._apply_simple_adjustment(
                area="system_prompt",
                new_value=prompt_adj,
                reason=f"自助调参: {worst_type} 失败率 {fail_ratio:.0%}",
            )
            self._last_adjustment_tick = self._tick_count
            log.info("自助调参: %s", prompt_adj)

    # ─── 影响分析 ──────────────────────────────────────────────

    def _estimate_impact(self, area: str, new_value: str) -> str:
        """预估调整的影响范围。"""
        if area == "system_prompt":
            return "影响所有决策的推理过程，覆盖面广但可回滚"
        elif area == "boundary":
            return "影响操作权限边界，需要谨慎评估"
        elif area == "parameter":
            return "影响特定参数，范围有限"
        return "影响范围未知"

    # ─── 深度进化 ──────────────────────────────────────────────

    async def evolve(self) -> EvolutionReport:
        """深度进化 — LLM 分析 + 自助提案融合。

        如果 LLM 不可用，使用规则生成的提案作为替代。
        """
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
            "pending_proposals": [
                {"title": p.title, "area": p.area, "confidence": p.confidence}
                for p in self._proposals[-5:]
            ],
        }

        # 尝试 LLM 深度进化
        if self.llm:
            try:
                return await self._llm_evolve(context, perf_summary)
            except Exception as e:
                log.warning("LLM 进化失败，降级到规则进化: %s", e)

        # 降级：规则驱动的自助进化
        return self._rule_evolve(context, perf_summary, top_patterns)

    async def _llm_evolve(self, context: dict, perf_summary: dict) -> EvolutionReport:
        """LLM 驱动的深度进化。"""
        messages = [
            LLMMessage(role="system", content=self._evolution_prompt()),
            LLMMessage(role="user", content=json.dumps(context, ensure_ascii=False, indent=2)),
        ]

        response = await self.llm.chat(messages, temperature=0.4)
        report = self._parse_evolution_response(response.content)

        for adj in report.adjustments:
            self._apply_adjustment(adj)

        log.info(
            "深度进化完成: %d 个调整, 趋势=%s",
            len(report.adjustments), perf_summary["trend"]
        )
        self._save_report(report)
        return report

    def _rule_evolve(
        self,
        context: dict,
        perf_summary: dict,
        top_patterns: list[tuple[str, int]],
    ) -> EvolutionReport:
        """无 LLM 时的规则驱动进化。"""
        adjustments: list[EvolutionStep] = []
        recommendations: list[str] = []

        perf = context["performance"]

        # 规则 1: 成功率下降 → 建议策略调整
        if perf.get("trend") == "declining":
            recommendations.append("成功率呈下降趋势，建议检查近期变更或降低操作复杂度")
            if top_patterns:
                worst = top_patterns[0]
                adjustments.append(EvolutionStep(
                    tick_id=self._tick_count,
                    observation=f"成功率下降，主要模式: {worst[0]}({worst[1]}次)",
                    adjustment=f"减少 {worst[0]} 相关操作频率",
                    reason=f"规则进化: 模式 {worst[0]} 累计 {worst[1]} 次",
                ))

        # 规则 2: 高频失败模式 → 针对性调整
        for pattern, count in top_patterns:
            if count >= 5:
                recommendations.append(f"模式 '{pattern}' 出现 {count} 次，建议关注")
                if pattern.startswith("fail_type:"):
                    adj_type = pattern.split(":", 1)[1]
                    adjustments.append(EvolutionStep(
                        tick_id=self._tick_count,
                        observation=f"{adj_type} 操作失败 {count} 次",
                        adjustment=f"对 {adj_type} 操作增加前置验证",
                        reason=f"规则进化: {adj_type} 高频失败 ({count})",
                    ))
                break  # 每次只处理一个模式的调整

        # 规则 3: 提案优先级排序
        if self._proposals:
            high_confidence = [p for p in self._proposals if p.confidence >= 0.7]
            for p in high_confidence[:2]:
                recommendations.append(f"[提案] {p.title} — {p.description[:60]}")

        report = EvolutionReport(
            timestamp=time.time(),
            patterns_found=[str(p) for p, _ in top_patterns],
            adjustments=adjustments,
            recommendations=recommendations or ["规则进化: 性能稳定，无需调整"],
            performance_delta=perf_summary,
        )

        for adj in adjustments:
            self._apply_adjustment(adj)

        log.info(
            "规则进化完成: %d 个调整, %d 条建议",
            len(adjustments), len(recommendations)
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

        data = None
        start = content.find("{")
        idx = content.rfind("}")
        while start >= 0 and idx >= 0 and start < idx and data is None:
            candidate = content[start:idx+1]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    key_map = {"analysi": "analysis", "analyis": "analysis",
                               "performace": "performance", "total_tick": "total_ticks"}
                    for old_k, new_k in key_map.items():
                        if old_k in parsed:
                            parsed[new_k] = parsed.pop(old_k)
                    if "analysis" in parsed or "patterns" in parsed:
                        data = parsed
            except json.JSONDecodeError:
                pass
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

        lines = [l.strip() for l in content.strip().split("\n") if len(l.strip()) > 10]
        log.info("进化 LLM 分析: %s", lines[0] if lines else content[:80])
        return EvolutionReport(
            timestamp=time.time(), patterns_found=[], adjustments=[],
            recommendations=lines[:3] or [content[:200]],
            performance_delta=self._performance.summary(),
        )

    # ─── 策略调整与回滚 ────────────────────────────────────────

    def _apply_simple_adjustment(self, area: str, new_value: str, reason: str):
        """自助调参 — 不经过 LLM 的快速调整。"""
        if area == "system_prompt" and self.cognition:
            self._snapshots.append(StrategySnapshot(
                system_prompt=self.cognition._system_prompt,
            ))
            self.cognition.update_system_prompt(new_value)

        impact = self._estimate_impact(area, new_value)
        record = AdjustmentRecord(
            id=f"auto_{self._tick_count}_{len(self._adjustments)}",
            timestamp=time.time(),
            area=area,
            old_value=self._snapshots[-1].system_prompt if self._snapshots else "",
            new_value=new_value,
            reason=reason,
            impact_assessment=impact,
        )
        self._adjustments.append(record)
        log.info("自助调参 [%s]: %s — %s", area, reason[:80], impact)

    def _apply_adjustment(self, step: EvolutionStep):
        """执行一次策略调整并记录快照。"""
        area = step.adjustment.split(":")[0] if ":" in step.adjustment else "system_prompt"

        if area == "system_prompt" and self.cognition:
            self._snapshots.append(StrategySnapshot(
                system_prompt=self.cognition._system_prompt,
            ))
            self.cognition.update_system_prompt(step.adjustment)

        impact = self._estimate_impact(area, step.adjustment)
        record = AdjustmentRecord(
            id=f"adj_{self._tick_count}_{len(self._adjustments)}",
            timestamp=time.time(),
            area=area,
            old_value=self._snapshots[-1].system_prompt if self._snapshots else "",
            new_value=step.adjustment,
            reason=step.reason,
            impact_assessment=impact,
        )
        self._adjustments.append(record)
        log.info("策略调整 [%s]: %s — %s", area, step.reason[:80], impact)

    def rollback(self, steps: int = 1) -> bool:
        """回滚最近的 N 次调整。"""
        if not self._snapshots:
            log.warning("无快照可回滚")
            return False
        if not self.cognition:
            return False

        last_snapshot: StrategySnapshot | None = None
        for _ in range(min(steps, len(self._snapshots))):
            last_snapshot = self._snapshots.pop()
        target = self._snapshots[-1] if self._snapshots else last_snapshot
        if target is None:
            return False
        self.cognition.update_system_prompt(target.system_prompt)
        for record in self._adjustments[-steps:]:
            record.outcome = "rolled_back"
        log.info("回滚了 %d 步调整", steps)
        return True

    def rollback_with_assessment(self, steps: int = 1) -> dict:
        """回滚并评估效果。"""
        before = self._performance.summary()
        success = self.rollback(steps)
        after = self._performance.summary()

        return {
            "success": success,
            "steps_rolled_back": steps,
            "performance_before": before,
            "performance_after": after,
            "assessment": "回滚完成" if success else "回滚失败（无快照）",
        }

    # ─── 属性暴露 ──────────────────────────────────────────────

    @property
    def adjustment_history(self) -> list[AdjustmentRecord]:
        return list(self._adjustments)

    @property
    def performance_summary(self) -> dict:
        return self._performance.summary()

    @property
    def reports(self) -> list[dict]:
        return list(self._reports)

    @property
    def proposals(self) -> list[ImprovementProposal]:
        return list(self._proposals)

    def add_proposal(self, proposal: ImprovementProposal):
        """注入一个外部提案到进化引擎。"""
        self._proposals.append(proposal)

    def add_proposals(self, proposals: list[ImprovementProposal]):
        """批量注入外部提案。"""
        self._proposals.extend(proposals)

    @property
    def pattern_db(self) -> dict[str, int]:
        return dict(self._pattern_db)

    @property
    def steps(self) -> list[EvolutionStep]:
        return list(self._steps)

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

    def clear_proposals(self):
        """清理已处理的提案。"""
        self._proposals.clear()
