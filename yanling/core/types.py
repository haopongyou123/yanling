"""衍灵核心类型定义."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

# ─── 多语言支持 ───────────────────────────────────────────

LANGUAGES = {
    "zh": {
        "name": "中文",
        "prompt": "请使用中文输出所有分析和报告。",
    },
    "en": {
        "name": "English",
        "prompt": "Please output all analysis and reports in English.",
    },
    "ar": {
        "name": "العربية",
        "prompt": "يرجى إخراج جميع التحليلات والتقارير باللغة العربية.",
    },
    "ja": {
        "name": "日本語",
        "prompt": "すべての分析とレポートを日本語で出力してください。",
    },
    "ko": {
        "name": "한국어",
        "prompt": "모든 분석 및 보고서를 한국어로 출력하세요.",
    },
    "es": {
        "name": "Español",
        "prompt": "Por favor, emite todos los análisis e informes en español.",
    },
}

DEFAULT_LANGUAGE = "zh"


# ─── 感知层类型 ───────────────────────────────────────────

@dataclass
class Percept:
    """感知数据单元。任何外部输入都被封装为此类型。"""
    source: str                     # 来源标识 (如 "timer", "sensor.temp", "email")
    type: str                       # 事件类型 (如 "tick", "alert", "message")
    data: dict = field(default_factory=dict)  # 原始数据
    timestamp: float = 0.0          # 时间戳，0 表示自动填充
    confidence: float = 1.0         # 置信度 [0, 1]

    def __post_init__(self):
        if not self.timestamp:
            import time
            self.timestamp = time.time()


# ─── 认知层类型 ───────────────────────────────────────────

class Intent(Enum):
    """决策意图分类。"""
    ANALYZE = auto()     # 分析
    ACT = auto()         # 执行行动
    DEFER = auto()       # 推迟
    ESCALATE = auto()    # 上报
    SLEEP = auto()       # 休眠等待


@dataclass
class Decision:
    """认知系统产出的决策。"""
    intent: Intent
    reason: str                    # 决策理由
    actions: list[Action] = field(default_factory=list)
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)


# ─── 行动层类型 ───────────────────────────────────────────

@dataclass
class Action:
    """行动指令。"""
    type: str            # 行动类型 (如 "notify", "store", "analyze", "publish")
    target: str          # 目标适配器名称
    params: dict         # 执行参数
    priority: int = 0    # 优先级 (越大越高)
    timeout: float = 30.0
    id: str = ""


@dataclass
class ActionResult:
    """行动执行结果。"""
    action_id: str
    success: bool
    type: str = ""  # 行动类型 (如 notify/store/analyze/publish)
    output: Any = None
    error: str | None = None
    duration: float = 0.0
    metadata: dict = field(default_factory=dict)


# ─── 认知结果 ─────────────────────────────────────────────

@dataclass
class CognitionResult:
    """认知系统的完整输出。"""
    decisions: list[Decision]
    context: dict = field(default_factory=dict)       # 推理上下文
    raw_response: str = ""                             # LLM 原始回复
    tokens_used: int = 0
    duration: float = 0.0
    error: str | None = None


# ─── Tick 结果 ────────────────────────────────────────────

@dataclass
class TickResult:
    """一次完整主循环的输出。"""
    tick_id: int
    perceptions: list[Percept]
    cognition: CognitionResult
    actions: list[ActionResult]
    evolution_note: str = ""
    duration: float = 0.0
    error: str | None = None


# ─── 进化层类型 ───────────────────────────────────────────

@dataclass
class EvolutionStep:
    """单次进化步骤记录。"""
    tick_id: int
    observation: str                 # 观察到的现象
    adjustment: str                  # 调整内容
    reason: str                      # 调整理由
    success: bool = True
    metrics: dict = field(default_factory=dict)


@dataclass
class EvolutionReport:
    """深度进化报告。"""
    timestamp: float
    patterns_found: list[str]
    adjustments: list[EvolutionStep]
    performance_delta: dict = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)


# ─── 边界层类型 ───────────────────────────────────────────

@dataclass
class BoundCheckResult:
    """边界检查结果。"""
    denied: bool
    reason: str = ""
    rule_name: str = ""
