"""内容策略优化器 — 连接内容反馈 → 进化引擎提案.

从世界模型和反馈收集器中提取内容相关模式，
生成 ImprovementProposal 供进化引擎做策略调整。

闭环: 发布 → 反馈 → 模式分析 → 策略提案 → 下一代优化
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from yanling.adapters.content.feedback import FeedbackCollector
from yanling.kernel.evolution import ImprovementProposal, EvolutionEngine
from yanling.kernel.world_model import WorldModel

log = logging.getLogger("yanling.content.optimizer")

# 提案置信度阈值
CONFIDENCE_HIGH = 0.75
CONFIDENCE_MEDIUM = 0.55


class ContentStrategyOptimizer:
    """内容策略优化器 — 分析模式 → 生成进化提案。"""

    def __init__(
        self,
        feedback_collector: FeedbackCollector | None = None,
        evolution: EvolutionEngine | None = None,
        cooldown_ticks: int = 50,
    ):
        self._feedback = feedback_collector
        self._evolution = evolution
        self._cooldown = cooldown_ticks
        self._last_proposal_tick = 0

    @property
    def has_evolution(self) -> bool:
        return self._evolution is not None

    def bind_evolution(self, evolution: EvolutionEngine):
        """绑定进化引擎。"""
        self._evolution = evolution

    def bind_feedback(self, collector: FeedbackCollector):
        """绑定反馈收集器。"""
        self._feedback = collector

    # ─── 提案生成 ─────────────────────────────────────────

    def generate_proposals(
        self,
        world_model: WorldModel | None = None,
        current_tick: int = 0,
    ) -> list[ImprovementProposal]:
        """从世界模型 + 反馈数据生成内容策略提案。"""
        proposals: list[ImprovementProposal] = []

        # 冷却检查
        if current_tick and self._last_proposal_tick:
            if current_tick - self._last_proposal_tick < self._cooldown:
                return proposals

        if world_model is None and self._feedback is None:
            return proposals

        # 1. 世界模型关联分析
        if world_model:
            proposals.extend(self._analyze_world_correlations(world_model))

        # 2. 反馈数据分析
        if self._feedback:
            proposals.extend(self._analyze_feedback_trends())

        if proposals:
            self._last_proposal_tick = current_tick

        return proposals

    def feed_to_evolution(self, proposals: list[ImprovementProposal]):
        """将提案注入进化引擎。"""
        if not self._evolution or not proposals:
            return
        self._evolution.add_proposals(proposals)
        log.info("内容优化器注入 %d 个提案到进化引擎", len(proposals))

    def sync(self, world_model: WorldModel | None = None, current_tick: int = 0):
        """一站式: 生成提案 → 注入进化引擎。"""
        proposals = self.generate_proposals(world_model, current_tick)
        if proposals:
            self.feed_to_evolution(proposals)

    # ─── 分析引擎 ─────────────────────────────────────────

    def _analyze_world_correlations(
        self,
        model: WorldModel,
    ) -> list[ImprovementProposal]:
        """从世界模型的关联数据生成提案。"""
        proposals: list[ImprovementProposal] = []
        correlations = model.get_correlations(min_count=3)

        # 查找内容发布相关的事件关联
        content_corrs = [
            c for c in correlations
            if "content" in c.antecedent or "content" in c.consequent
        ]

        if content_corrs:
            best = content_corrs[0]
            proposals.append(ImprovementProposal(
                area="parameter",
                title="内容发布关联模式检测",
                description=(
                    f"内容类型 '{best.antecedent}' → '{best.consequent}' "
                    f"(概率 {best.probability:.0%}, {best.count} 次)"
                ),
                trigger=f"content_correlation:{best.antecedent}→{best.consequent}",
                confidence=CONFIDENCE_MEDIUM,
                estimated_impact="medium",
                related_patterns=[
                    f"{c.antecedent}→{c.consequent}"
                    for c in content_corrs[:3]
                ],
            ))

        # 检查主题多样性
        summary = model.summary()
        metric_baselines = summary.get("metric_baselines", {})
        topic_baselines = {
            k: v for k, v in metric_baselines.items()
            if "topic" in k or "content" in k
        }
        if len(topic_baselines) < 3:
            proposals.append(ImprovementProposal(
                area="system_prompt",
                title="内容主题多样性不足",
                description=(
                    f"检测到 {len(topic_baselines)} 个主题维度，"
                    f"建议扩展内容源范围覆盖更多主题"
                ),
                trigger=f"topic_diversity={len(topic_baselines)}",
                confidence=CONFIDENCE_MEDIUM,
                estimated_impact="medium",
            ))

        return proposals

    def _analyze_feedback_trends(self) -> list[ImprovementProposal]:
        """从反馈数据生成提案。"""
        proposals: list[ImprovementProposal] = []
        if not self._feedback:
            return proposals

        stats = self._feedback.topic_statistics()
        if not stats:
            return proposals

        topics = stats.get("topics", {})
        if len(topics) < 2:
            return proposals

        # 找最佳和最差主题
        sorted_topics = sorted(
            topics.items(),
            key=lambda x: x[1].get("avg", 0),
            reverse=True,
        )
        best = sorted_topics[0]
        worst = sorted_topics[-1]
        gap = best[1].get("avg", 0) - worst[1].get("avg", 0)

        # 如果主题间表现差异大 → 建议聚焦
        if gap > 1.0:
            proposals.append(ImprovementProposal(
                area="system_prompt",
                title="内容主题表现分化 — 建议聚焦优质主题",
                description=(
                    f"最佳主题 '{best[0]}' (均分 {best[1]['avg']}) "
                    f"vs 最差 '{worst[0]}' (均分 {worst[1]['avg']})，"
                    f"差距 {gap:.1f} 分"
                ),
                trigger=f"topic_gap={gap:.1f}",
                confidence=CONFIDENCE_HIGH,
                estimated_impact="high",
                related_patterns=[
                    f"{t}:{d['avg']}" for t, d in sorted_topics[:3]
                ],
            ))

        # 数据量过少 → 建议增加反馈源
        if stats["total_entries"] < 10:
            proposals.append(ImprovementProposal(
                area="parameter",
                title="反馈数据不足 — 建议接入更多反馈源",
                description=(
                    f"当前仅 {stats['total_entries']} 条反馈，"
                    f"建议接入平台 API (掘金/知乎) 自动采集"
                ),
                trigger=f"feedback_count={stats['total_entries']}",
                confidence=CONFIDENCE_MEDIUM,
                estimated_impact="low",
            ))

        return proposals
