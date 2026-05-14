# 衍灵 (YanLing) — 自主 AI 内核

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: Custom](https://img.shields.io/badge/License-Custom-blue)](LICENSE)
[![CI](https://github.com/haopongyou123/yanling/actions/workflows/ci.yml/badge.svg)](https://github.com/haopongyou123/yanling/actions/workflows/ci.yml)

**衍灵是一个通用 AI 自我进化系统内核。** 它以固定频率循环运行"感知→认知→行动→进化"四阶段流程，可嵌入到任何系统中，使其具备自主决策和自我优化的能力。

```
                 ┌─────────────────────────────────────┐
                 │         衍灵引擎 主循环               │
                 │                                     │
    ┌──────────┐ │  ┌──────────┐  ┌──────────┐  ┌────┐ │
    │ 感知      │──→│ 认知      │──→│ 行动      │──→│进化│ │
    │ Perception│ │  │ Cognition│  │ Action   │  │Evolution │
    └──────────┘ │  └──────────┘  └──────────┘  └────┘ │
         │       │       │              │               │
    ┌────┴───┐   │   ┌───┴────┐    ┌───┴────┐         │
    │传感器/  │   │   │LLM/规则│    │执行器/  │         │
    │适配器   │   │   │ 推理    │    │命令     │         │
    └────────┘   │  └────────┘    └────────┘         │
                 └─────────────────────────────────────┘
```

## 核心特性

- **主动式** — 7×24 自主运行，不依赖人工触发
- **双模式认知** — 规则驱动（离线/低延迟）或 LLM 驱动（复杂推理）
- **自我进化** — 持续分析性能模式，自动调整策略
- **轻量** — 仅依赖 `httpx`，核心引擎 < 200KB
- **可嵌入** — 作为 Python 库导入，或独立进程运行
- **事件总线** — 插件化架构，支持中间件链
- **边界控制** — 速率限制、作用域约束、时间窗口

## 快速开始

### 安装

```bash
pip install yanling

# 可选：Web 管理面板
pip install 'yanling[web]'
```

### 运行嵌入式监控示例

```bash
# 规则模式（无需 LLM，离线可用）
yanling run embedded

# LLM 模式（需配置 API 密钥）
EMBEDDED_MODE=llm yanling run embedded
```

### 启动 Web 面板

```bash
# 方式一：随引擎启动
yanling start --web

# 方式二：独立启动
yanling web --port 8764
```

### 作为库使用

```python
from yanling.kernel.engine import YanLingEngine
from yanling.kernel.perception import PerceptionSystem
from yanling.kernel.action import ActionSystem
from yanling.kernel.memory import MemorySystem
from yanling.adapters.storage.json_file import JsonFileStorage

engine = YanLingEngine(
    perception=PerceptionSystem(),
    action=ActionSystem(),
    memory=MemorySystem(JsonFileStorage("/tmp/yanling")),
)

await engine.start()
# 引擎自动循环运行...
await engine.stop()
```

## 架构

### 项目结构

```
yanling/
├── core/         类型系统、配置、时钟、日志、错误处理
├── kernel/       引擎主循环、感知/认知/行动/记忆/进化/边界/生命周期
├── bus/          事件总线 + 中间件
├── plugin/       插件系统（注册、加载、管理）
├── adapters/     接入适配器
│   ├── llm/      LLM 适配器（DeepSeek、oMLX、Ollama、自动降级）
│   ├── storage/  存储适配器（JSON 文件、可扩展）
│   ├── registry/ 节点注册发现（黑板协议）
│   └── notify/   通知适配器（飞书）
├── scenarios/    场景层（嵌入式监控、扩展点）
└── web/          Web 管理面板（FastAPI + Jinja2）
```

### 四阶段主循环

| 阶段 | 职责 | 扩展点 |
|------|------|--------|
| **感知 (Perception)** | 从传感器/适配器采集数据 | `SensorAdapter` 接口 |
| **认知 (Cognition)** | 规则匹配 or LLM 推理 | `RuleCognitiveEngine` / `CognitiveEngine` |
| **行动 (Action)** | 执行决策 | `ActionAdapter` 接口 |
| **进化 (Evolution)** | 分析性能 → 调整策略 | 轻量学习 + LLM 深度分析 |

### 两种认知模式

| 模式 | 适用场景 | 延迟 | 需要网络 |
|------|---------|------|---------|
| 规则驱动 | 边缘设备、本地运行 | 微秒级 | 否 |
| LLM 驱动 | 复杂推理、云端 | 秒级 | 是 |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ANTHROPIC_BASE_URL` | LLM API 端点（兼容格式） | `https://api.deepseek.com/anthropic` |
| `ANTHROPIC_MODEL` | 模型名 | — |
| `ANTHROPIC_API_KEY` | API 密钥 | — |
| `YANLING_TICK_INTERVAL` | 主循环间隔(秒) | `30` |
| `YANLING_STORAGE_PATH` | 记忆持久化路径 | `~/.yanling/memory` |

## 测试

```bash
pip install 'yanling[dev]'
pytest -v
```

## 路线图

- [ ] 分布式节点记忆共享
- [ ] 推送式感知（Webhook）
- [ ] 规则自动生成
- [ ] 多 Agent 协作推理
- [ ] 动态边界策略
- [ ] 插件市场

## 许可

[MIT](LICENSE)

## 贡献

欢迎 Issue 和 PR！请先阅读 [CONTRIBUTING.md]（可选）。
