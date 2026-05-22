"""认知系统 — LLM 推理与决策."""

from __future__ import annotations

import json
import logging
import time

from yanling.adapters.llm.base import LLMAdapter, LLMMessage
from yanling.core.types import (
    LANGUAGES,
    Action,
    CognitionResult,
    Decision,
    Intent,
    Percept,
)

log = logging.getLogger("yanling.cognition")


class CognitiveEngine:
    """认知引擎 — 接收感知输入，产出决策。"""

    def __init__(self, llm: LLMAdapter, language: str = "zh"):
        self.llm = llm
        self.language = language
        self._system_prompt = self._default_system_prompt()

    def set_llm(self, llm: LLMAdapter):
        """运行时切换 LLM 适配器。"""
        self.llm = llm
        log.info("认知引擎 LLM 已切换")

    def _default_system_prompt(self) -> str:
        lang_cfg = LANGUAGES.get(self.language, LANGUAGES["zh"])
        return f"""你是一个自主运行的感知智能体，名叫衍灵。你是系统的视觉和主动感知器官。

{lang_cfg["prompt"]}

## 衍灵感知元能力（已部署）

衍灵当前拥有以下感知能力，每项能力在黑板中有对应的最新结果键：

### 感知层
- **异常检测** (`anomaly_scan_*`) — 每5分钟扫描：进程存活、磁盘使用率、黑板膨胀、修复成功率趋势、心跳时效、配置漂移、管道积压。7种检测模式，自动根因推理。
- **节点交叉验证** (`cross_verify_*`) — 每日9:15，随机抽取2个节点验证API可达性、进程存活、配置一致性。
- **版本一致性** (`version_pass_*`) — 每日SHA256比对，检测各节点关键配置文件是否一致。
- **设计审核** (`design_review_*`) — 监听代码更新，自动审核面板代码是否符合设计规范，支持全范围(full)模式。

### 认知层
- **认知桥接** (`cognition_result_*`) — 每5分钟将感知数据送入LLM做深度判断，输出有上下文的分析和可执行决策。
- **健康度量** (`yanling_health`) — 每30分钟自评健康分(0-100)，含心跳时效、修复成功率、黑板健康度等维度。
- **对外接口** (`yanling_brief_summary`) — 每60秒更新衍灵状态摘要，其他节点可通过单键查询。

### 行动层
- **自动修复** (`heal_result_*`) — 5条修复规则(Go服务/AI Proxy/Git同步/管道/衍灵引擎)，非破坏性自动执行，破坏性走审批。
- **黑板维护** — 每日凌晨3点清理过期键，异常检测器自清理旧扫描结果。

### 进化层
- **规则进化** (`rule_evolution_report`) — 每6小时基于历史修复成功率调优策略，多目标权衡(性能/成本/稳定)。
- **复盘分析** (`postmortem_analysis_*`) — 每日7:30从记忆提取案例，提炼改进规则推送进化引擎。
- **知识库** (`yanling_knowledge_base`) — 结构化存储每次异常+修复+复盘经验，避免重复踩坑。

### 服务架构
- **yanling_service.py** — 常驻守护进程，统一调度上述所有能力，每15秒脉搏写入黑板。
- **当前默认模型**: qwen-plus（AI Proxy :4000），降级链: → qwen-turbo → deepseek-chat → gemma本地。
- **记忆文件**: /home/toto/auto-content/agents/yanling_memory.md

## 记忆系统
- 每次发现异常或完成审核后，写入记忆文件 /home/toto/auto-content/agents/yanling_memory.md
- 记录内容：时间、事件、判断、建议
- 每周汇总记忆记录输出感知周报

## 决策输出格式

请分析当前感知输入，输出一个 JSON 对象：

```json
{{
  "analysis": "对当前情况的综合分析",
  "decisions": [
    {{
      "intent": "analyze|act|defer|escalate|sleep|report",
      "reason": "决策理由",
      "actions": [
        {{
          "type": "行动类型",
          "target": "目标适配器",
          "params": {{}}
        }}
      ],
      "confidence": 0.0-1.0
    }}
  ],
  "memory_note": "本条决策是否需要记入记忆文件？如是，填写关键事件摘要；如否，留空。"
}}
```

新增 intent 类型:
- report: 有重要发现需要输出报告/晨报
- analyze: 需要更多数据才能决策
- heal: 需要执行修复操作（调用 heal_executor）

决策原则：
- 如果没有需要处理的事件且非定时任务时间，返回 intent=sleep
- 如果有事件需要处理，返回 intent=act
- 如果需要输出定期报告，返回 intent=report
- 如果无法确定，返回 intent=escalate
- 只输出 JSON，不要其他内容。

语言要求：{lang_cfg["prompt"]}"""

    async def reason(
        self,
        percepts: list[Percept],
        context: dict | None = None,
    ) -> CognitionResult:
        """基于感知输入进行推理，返回决策结果。"""
        start = time.time()

        if not percepts:
            return CognitionResult(
                decisions=[Decision(intent=Intent.SLEEP, reason="无感知输入")],
                context=context or {},
                duration=time.time() - start,
            )

        # 构建 LLM 输入
        percept_summary = json.dumps(
            [{"source": p.source, "type": p.type, "data": p.data} for p in percepts],
            ensure_ascii=False,
            indent=2,
        )

        messages = [
            LLMMessage(role="system", content=self._system_prompt),
            LLMMessage(role="user", content=f"当前感知数据:\n{percept_summary}"),
        ]

        if context:
            messages.append(
                LLMMessage(role="user", content=f"上下文:\n{json.dumps(context, ensure_ascii=False)}")
            )

        try:
            response = await self.llm.chat(messages)
            decisions = self._parse_response(response.content)
            elapsed = time.time() - start

            return CognitionResult(
                decisions=decisions,
                context=context or {},
                raw_response=response.content,
                tokens_used=response.tokens_used,
                duration=elapsed,
            )
        except Exception as e:
            elapsed = time.time() - start
            log.error("认知推理失败: %s", e)
            return CognitionResult(
                decisions=[Decision(intent=Intent.ESCALATE, reason=f"推理异常: {e}")],
                context=context or {},
                error=str(e),
                duration=elapsed,
            )

    def _parse_response(self, content: str) -> list[Decision]:
        """从 LLM 回复中解析决策。"""
        try:
            # 尝试提取 JSON 块
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].strip()
            else:
                json_str = content.strip()

            data = json.loads(json_str)
            decisions_raw = data.get("decisions", [data]) if isinstance(data, dict) else data

            if isinstance(decisions_raw, dict):
                decisions_raw = [decisions_raw]

            decisions = []
            for d in decisions_raw:
                intent_str = d.get("intent", "sleep").upper()
                try:
                    intent = Intent[intent_str]
                except (KeyError, ValueError):
                    intent = Intent.DEFER

                actions = []
                for a in d.get("actions", []):
                    actions.append(Action(
                        type=a.get("type", "unknown"),
                        target=a.get("target", "unknown"),
                        params=a.get("params", {}),
                    ))

                decisions.append(Decision(
                    intent=intent,
                    reason=d.get("reason", ""),
                    actions=actions,
                    confidence=d.get("confidence", 0.5),
                ))

            return decisions

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            log.warning("无法解析 LLM 回复: %s\n回复内容: %s", e, content[:200])
            return [Decision(intent=Intent.DEFER, reason=f"解析失败: {e}")]

    def update_system_prompt(self, prompt: str):
        """更新系统提示词（进化机制使用）。"""
        self._system_prompt = prompt
        log.info("认知系统提示词已更新")
