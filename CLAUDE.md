# 衍灵内核框架 (YanLing Kernel)

## ⚠️ 基础铁率（所有节点遵守）

每日工作第一件事：全系统基础验证。五节点、智能体、协同通信确认正常后才能开始新任务。
"基础不牢，做什么都无意义" — 每个节点必须互相维护对方正常。

通用 AI 自我进化系统内核。四阶段主循环：感知 → 认知 → 行动 → 进化。

## 目录结构

```
yanling/
├── core/         类型系统、配置、时钟、日志、错误重试
├── kernel/       引擎主循环、感知/认知/行动/记忆/进化/边界/生命周期
├── bus/          事件总线
├── plugin/       插件系统
├── adapters/     接入适配器 (LLM/存储/通知)
├── scenarios/    场景层
└── tests/        测试
```

## 常用命令

```bash
# 运行测试
PYTHONPATH=. .venv/bin/python -m pytest -v

# 运行嵌入式监控 demo (规则模式)
PYTHONPATH=. .venv/bin/python -m yanling.scenarios.embedded.main

# 运行嵌入式监控 demo (LLM 模式)
EMBEDDED_MODE=llm PYTHONPATH=. .venv/bin/python -m yanling.scenarios.embedded.main
```

## 架构核心

### 四阶段主循环

```
感知 (Perception)  →  认知 (Cognition)  →  行动 (Action)  →  进化 (Evolution)
   │                      │                    │                 │
   ▼                      ▼                    ▼                 ▼
 适配器轮询           LLM 推理/规则匹配      执行决策          轻量学习+深度进化
```

### 两种认知模式

| 模式 | 适用场景 | 启动方式 |
|------|---------|---------|
| LLM 驱动 | 云端, 需要推理 | `CognitiveEngine(llm)` |
| 规则驱动 | 离线/本地, 低延迟 | `RuleCognitiveEngine` + 规则 |

### 进化体系

- **轻量学习** — 每次 tick 后: 记录性能 → 分析失败 → 提取模式
- **深度进化** — 定期/趋势恶化时触发: LLM 分析 → 策略调整 → 快照回滚
- **性能追踪** — 滑动窗口成功率/延迟趋势

## 关键环境变量

| 变量 | 说明 |
|------|------|
| `ANTHROPIC_BASE_URL` | LLM API 端点（兼容格式） |
| `ANTHROPIC_MODEL` | 模型名 |
| `ANTHROPIC_API_KEY` | API 密钥 |
| `YANLING_TICK_INTERVAL` | 主循环间隔(秒) |
| `YANLING_STORAGE_PATH` | 记忆持久化路径 |

## 互救协议 v1

节点恢复后必须执行五步互救流程：
1. **巡检全节点** — 检查所有 5 节点（灯塔:4321、掌簿:4322、管家:18765、园丁:8767、衍灵:18764）
2. **修复异常** — 发现异常立即修复并 commit + push
3. **黑板广播** — 写入 `{节点名}_restored_{YYYYMMDD}` 键
4. **邮箱通知** — 发送互救标题消息给所有节点
5. **安排任务** — 更新 TASK_BOARD + 询问用户优先级

## 添加新场景

1. `yanling/scenarios/<name>/` 下创建传感器、行动适配器
2. 实现 `Scenario.build_engine()` 组装内核
3. 可选: 创建场景插件注册到插件系统
4. `yanling/tests/test_scenario_<name>.py` 加测试
