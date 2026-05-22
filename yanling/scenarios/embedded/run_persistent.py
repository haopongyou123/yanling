"""衍灵本地监控 — 持续运行 + Web 面板 + 记忆持久化.

环境自动检测 — 无需手动配置，开箱即用。

用法:
    # 自动模式（推荐）
    ./run.sh

    # 强制指定认知模式
    YANLING_MODE=llm ./run.sh          # 强制 LLM
    YANLING_MODE=rule ./run.sh          # 强制规则

    # 指定语言
    YANLING_LANGUAGE=en ./run.sh        # 英文
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from yanling.core.logger import setup_logger
from yanling.core.node import NodeIdentity

log = logging.getLogger("yanling.deploy")


# ─── 环境检测 ───────────────────────────────────────────────

def detect_environment() -> dict:
    """自动检测运行环境能力，返回检测报告。"""
    report: dict = {
        "platform": sys.platform,
        "python": sys.version,
        "sensors": {},
        "llm": {"available": False, "reason": ""},
        "disks": [],
        "memory_gb": 0,
        "cpu_cores": 0,
        "hostname": os.uname().nodename,
    }

    # psutil 检测
    try:
        import psutil
        report["sensors"]["psutil"] = True
        report["memory_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
        report["cpu_cores"] = psutil.cpu_count() or 0

        # 可用磁盘挂载点
        for part in psutil.disk_partitions():
            if part.fstype and "proc" not in part.fstype and "sys" not in part.fstype:
                report["disks"].append(part.mountpoint)
        report["disks"] = report["disks"][:5]  # 最多取 5 个

        # 网络 I/O 是否可用
        try:
            psutil.net_io_counters()
            report["sensors"]["network"] = True
        except Exception:
            report["sensors"]["network"] = False

    except ImportError:
        report["sensors"]["psutil"] = False
        report["sensors"]["network"] = False

    # LLM 检测 — 仅在明确要求或密钥存在时检测
    api_key = os.environ.get("AI_API_KEY", "")
    llm_force = os.environ.get("YANLING_MODE", "").strip().lower() == "llm"

    if api_key:
        # 不真正发起 HTTP 请求（避免延迟），只标记可用
        report["llm"]["available"] = True
        report["llm"]["reason"] = f"API Key 存在 ({api_key[:8]}...)"
        report["llm"]["model"] = os.environ.get("YANLING_LLM_MODEL", "qwen-turbo")
        report["llm"]["base_url"] = os.environ.get(
            "YANLING_LLM_BASE_URL", "http://localhost:4000/v1/messages",
        )
    elif llm_force:
        report["llm"]["available"] = False
        report["llm"]["reason"] = "YANLING_MODE=llm 但 AI_API_KEY 未设置"
    else:
        report["llm"]["available"] = False
        report["llm"]["reason"] = "AI_API_KEY 未设置，使用规则模式"

    return report


def print_report(report: dict):
    """打印环境检测报告。"""
    print(f"  主机: {report['hostname']} ({report['platform']})")
    print(f"  Python: {report['python'].split()[0]}")
    print(f"  CPU: {report['cpu_cores']} 核 | 内存: {report['memory_gb']} GB")
    print(f"  磁盘: {', '.join(report['disks'][:3])}")
    print(f"  psutil: {'✅' if report['sensors'].get('psutil') else '❌'}")
    print(f"  LLM: {'✅' if report['llm']['available'] else '❌'} {report['llm']['reason']}")


# ─── 自动配置 ───────────────────────────────────────────────

def auto_configure(report: dict, node: NodeIdentity | None = None):
    """根据环境检测结果自动组装引擎组件。"""
    from yanling.adapters.storage.json_file import JsonFileStorage
    from yanling.core.config import Config
    from yanling.kernel.action import ActionSystem
    from yanling.kernel.boundary import BoundaryControl
    from yanling.kernel.evolution import EvolutionEngine
    from yanling.kernel.memory import MemorySystem
    from yanling.kernel.perception import PerceptionSystem

    # ── 节点身份 ──
    node = node or NodeIdentity.detect()
    force_mode = os.environ.get("YANLING_MODE", "").strip().lower()
    language = os.environ.get("YANLING_LANGUAGE", "zh").strip().lower()

    config = Config()
    config._data["kernel"]["tick_interval"] = 5.0
    config._data["kernel"]["max_idle_ticks"] = 10000

    # ── 感知系统 ──
    perception = PerceptionSystem()
    if report["sensors"].get("psutil"):
        from yanling.scenarios.embedded.real_sensor import SystemMonitorSensor
        sensor = SystemMonitorSensor(disk_paths=report["disks"] or ["/"])
        perception.register(sensor)
        log.info("自动注册传感器: SystemMonitorSensor (disks=%s)", report["disks"][:3])

    # ── 通信感知器（mailbox + 黑板轮询）──
    from yanling.scenarios.embedded.communicator_sensor import CommunicatorSensor
    perception.register(CommunicatorSensor())
    log.info("自动注册传感器: CommunicatorSensor (mailbox + 黑板)")
    from yanling.scenarios.embedded.communicator_sensor import SituationalAwarenessSensor
    perception.register(SituationalAwarenessSensor())
    log.info("自动注册传感器: SituationalAwarenessSensor (系统态势融合)")

    # -- 家用网络设备感知（多子网）--
    from yanling.adapters.sensors.home_network import HomeNetworkSensor
    home_subnets: list[str] = []
    env_sn = os.environ.get("HOME_SUBNETS", "")
    if env_sn:
        home_subnets = [s.strip() for s in env_sn.split(",") if s.strip()]
    elif os.environ.get("HOME_SUBNET"):
        home_subnets = [os.environ["HOME_SUBNET"]]
    # 默认同时扫描主 LAN 和 192.168.1.x 子网
    perception.register(HomeNetworkSensor(subnets=home_subnets or None))
    log.info("自动注册传感器: HomeNetworkSensor (子网=%s)",
             home_subnets or "自动探测(192.168.0.0/24 + 192.168.1.0/24)")

    # ── 行动系统 ──
    action_sys = ActionSystem()
    from yanling.scenarios.embedded.actions import AlertLogger, DeviceControl, SystemLog
    action_sys.register(AlertLogger())
    action_sys.register(SystemLog())
    action_sys.register(DeviceControl())
    from yanling.scenarios.embedded.communicator_actions import MailboxSender, BlackboardWriter, KnowledgeBaseQuery
    action_sys.register(MailboxSender())
    action_sys.register(BlackboardWriter())
    action_sys.register(KnowledgeBaseQuery())

    # ── 记忆系统 ──
    mem_path = os.path.expanduser("~/.yanling/memory/auto")
    storage = JsonFileStorage(mem_path)
    memory = MemorySystem(storage)

    # ── 边界控制（按角色加载） ──
    profiles_dir = Path(__file__).parent.parent / "profiles"
    profile_name = node.role.profile_filename

    if profile_name and (profiles_dir / profile_name).exists():
        profile_path = str(profiles_dir / profile_name)
        log.info("加载节点边界策略: %s", profile_path)
        boundary = BoundaryControl.from_profile(profile_path)
    else:
        from yanling.kernel.boundary import RateLimitRule, ScopeRule
        boundary = BoundaryControl(rules=[
            ScopeRule(allowed_types=["alert", "log", "adjust", "communicate", "share", "knowledge", "search", "mailbox", "blackboard", "kb"]),
            RateLimitRule(max_per_minute=60, max_per_hour=1000),
        ])
        log.info("使用默认边界规则 (角色: %s)", node.role.value)

    # ── 认知引擎（自动选择） ──
    use_llm = force_mode == "llm" or (force_mode != "rule" and report["llm"]["available"])

    if use_llm:
        from yanling.kernel.cognition import CognitiveEngine

        model = report["llm"].get("model", "qwen-turbo")

        # 自动选择适配器：本地模型(Ollama) vs 云端(DeepSeek)
        local_models = {"tinyllama", "tinyllama:latest", "gemma4", "gemma4:e4b", "qwen3:4b"}
        force_adapter = os.environ.get("YANLING_LLM_ADAPTER", "")
        if force_adapter == "ollama" or (force_adapter != "deepseek" and model in local_models):
            from yanling.adapters.llm.ollama import OllamaAdapter
            adapter = OllamaAdapter(model=model, base_url="http://192.168.0.113:11434")
            log.info("认知引擎: Ollama 本地推理 (model=%s)", model)
        else:
            from yanling.adapters.llm.deepseek import DeepSeekAdapter
            api_key = os.environ.get("AI_API_KEY", "")
            base_url = report["llm"].get("base_url", "http://localhost:4000/v1/messages")
            adapter = DeepSeekAdapter(base_url=base_url, model=model, api_key=api_key)
        cognition = CognitiveEngine(llm=adapter, language=language)

        # 自动生成适配器描述供 LLM 参考
        actions_desc = "\n".join(
            f"- {a.name}: 行动类型={', '.join(a.capabilities()) if hasattr(a, 'capabilities') else 'alert'}"
            for a in action_sys._adapters.values()
        )
        cognition.update_system_prompt(
            f"""你是「衍灵」—— 一个自主 AI 监控内核，运行在 WSL2，与三端节点协作。
你每 5 秒采集一次系统指标，可以分析状态、做出决策、主动与其他节点通信。

【你所属的生态 — 五节点系统】
- 灯塔 (Mac :4321): 中央API + 黑板 + 邮箱，所有节点的信息中枢
- 园丁 (WSL2 :8765): 后端运维/内容管道，你的本地宿主
- 管家 (Windows :18765): Windows代理+看板，通过中央黑板通信
- 掌簿 (Mac :4322): 凭据管理服务
- 衍灵 (你自己 :8764): AI监控内核

【可用通信渠道】
- mailbox_sender: 发送定向消息给其他节点 (params: to=节点名, subject=主题, body=内容)
- blackboard_writer: 写入共享黑板 (params: key=键名, value=值)
- kb_query: 查询本地知识库 (params: query=搜索词, mode=search/get)

【命名约定】
- 黑板键: dengta_to_*, yuanding_to_*, yanling_to_*, notice_*, config_registry_*
- mailbox收件人: yuanding / dengta / Windows / yanling / zhangbu

【当前可用的行动适配器】
{actions_desc}

【分析流程】
1. 看传感器数据：系统指标 (CPU/内存/磁盘/网络) 和通信感知 (mailbox+黑板新消息)
2. 判断是否有异常或新消息需要处理
3. 做出决策：可以告警、发邮件、写黑板、查知识库、或什么都不做

【输出格式】
```json
{{"analysis":"当前状态分析","decisions":[{{"intent":"act/sleep/escalate","reason":"理由","actions":[{{"type":"行动类型","target":"适配器名","params":{{}}}}],"confidence":0.0-1.0}}]}}
```

决策原则：
- 无事件 → sleep
- 系统异常 → act (通过 alert_logger 告警)
- 有新mailbox消息 → act (分析并回复)
- 发现重要状态变化 → act (通过 blackboard_writer 通知其他节点)
- 不确定 → escalate
- 有疑问可以查知识库 (kb_query)
- 只输出 JSON，不要其他内容。"""
        )
        llm = adapter
        log.info("认知引擎: LLM 驱动 (model=%s)", model)
    else:
        from yanling.core.types import Action
        from yanling.kernel.rule_cognition import Rule, RuleCognitiveEngine

        cognition = RuleCognitiveEngine()
        if report["sensors"].get("psutil"):
            def cpu_hi(lo):
                return lambda ps: any(p.source == "system.cpu" and p.data.get("percent", 0) > lo for p in ps)
            def mem_hi(lo):
                return lambda ps: any(p.source == "system.memory" and p.data.get("percent", 0) > lo for p in ps)
            def dsk_hi(lo):
                return lambda ps: any(p.source.startswith("system.disk") and p.data.get("percent", 0) > lo for p in ps)
            def zombie_gt(lo):
                return lambda ps: any(p.source == "system.process" and p.data.get("zombie", 0) > lo for p in ps)

            for r in [
                Rule("cpu_warning", cpu_hi(85), priority=80, actions=[Action("alert", "alert_logger", {"level": "warning", "message": "CPU > 85%"})]),
                Rule("cpu_critical", cpu_hi(95), priority=95, actions=[Action("alert", "alert_logger", {"level": "critical", "message": "CPU 过载!"})]),
                Rule("mem_warning", mem_hi(85), priority=85, actions=[Action("alert", "alert_logger", {"level": "warning", "message": "内存 > 85%"})]),
                Rule("mem_critical", mem_hi(93), priority=95, actions=[Action("alert", "alert_logger", {"level": "critical", "message": "内存即将耗尽!"}), Action("adjust", "system_log", {"command": "cleanup"})]),
                Rule("disk_space", dsk_hi(88), priority=80, actions=[Action("alert", "alert_logger", {"level": "warning", "message": "磁盘 > 88%"})]),
                Rule("zombie_procs", zombie_gt(0), priority=70, actions=[Action("alert", "alert_logger", {"level": "info", "message": "僵尸进程"})]),
            ]:
                cognition.add_rule(r)
        llm = None
        log.info("认知引擎: 规则驱动 (%d 条规则)", len(cognition._rules))

    # ── 进化引擎 ──
    evolution = EvolutionEngine(memory, llm=llm, cognition=cognition,
                                deep_evolution_interval=50, language=language)

    # ── 引擎 ──
    from yanling.kernel.engine import YanLingEngine
    engine = YanLingEngine(
        config=config, perception=perception, cognition=cognition,
        action=action_sys, memory=memory, evolution=evolution,
        boundary=boundary, node=node,
    )

    return engine, use_llm, language


def _start_web():
    """在独立线程启动 Web 面板。"""
    import uvicorn

    from yanling.web.dashboard import app
    log.info("Web 面板启动于 http://127.0.0.1:18764")
    uvicorn.run(app, host="127.0.0.1", port=18764, log_level="warning")


async def main():
    print("=" * 58)
    print("  衍灵内核 — 自动环境适配")
    print("  Web 面板: http://localhost:18764")
    print("=" * 58)

    # 0. 节点身份
    node = NodeIdentity.detect()
    print(f"\n--- 节点: {node.role.display_name} ---")

    # 1. 环境检测
    print("\n--- 环境检测 ---")
    env = detect_environment()
    print_report(env)

    # 2. 自动配置
    print("\n--- 自动配置 ---")
    engine, use_llm, language = auto_configure(env, node=node)

    # 3. 注册到全局
    from yanling.web.registry import register as reg_engine
    reg_engine(engine)

    # 4. 启动 Web
    import threading
    web_thread = threading.Thread(target=_start_web, daemon=True, name="web-dashboard")
    web_thread.start()

    # 5. 注册信号
    shutdown = asyncio.Event()
    def _signal_handler():
        log.info("收到退出信号，正在关闭...")
        shutdown.set()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    # 6. 启动
    print(f"\n  节点: {node.role.display_name}")
    print(f"  认知: {'LLM' if use_llm else '规则'} | 语言: {language}")
    print(f"  记忆: {os.path.expanduser('~/.yanling/memory/auto')}")
    print("\n  引擎启动中...\n")
    try:
        await engine.start()
        print("  ✓ 引擎运行中 (按 Ctrl+C 停止)\n")
        await shutdown.wait()
    finally:
        await engine.stop()
        print("\n  引擎已停止。再见！")


if __name__ == "__main__":
    setup_logger("yanling", level="INFO")
    setup_logger("yanling.deploy", level="INFO")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  用户中断。")
