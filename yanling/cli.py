"""衍灵引擎命令行接口.

用法:
    yanling start                启动引擎
    yanling stop                 停止引擎
    yanling status               查看状态
    yanling run <scenario>       运行场景
    yanling list-scenarios       列出可用场景
    yanling config               查看当前配置
"""

from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing
import os
import signal
import sys
import time
from pathlib import Path

from yanling.core.config import Config
from yanling.core.logger import setup_logger

log = setup_logger("yanling.cli", level="INFO")

_WEB_HELP = "启动 Web 面板 (默认 http://0.0.0.0:8764)"

# PID 文件路径
PID_DIR = Path.home() / ".yanling"
PID_FILE = PID_DIR / "engine.pid"
STATUS_FILE = PID_DIR / "engine.status"


def _ensure_dir():
    PID_DIR.mkdir(parents=True, exist_ok=True)


def _write_pid(pid: int):
    _ensure_dir()
    PID_FILE.write_text(str(pid))


def _read_pid() -> int | None:
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except (ValueError, OSError):
            return None
    return None


def _write_status(status: dict):
    _ensure_dir()
    STATUS_FILE.write_text(
        json.dumps(status, ensure_ascii=False, indent=2, default=str),
    )


def _read_status() -> dict:
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def cmd_start(args: argparse.Namespace):
    """启动引擎守护进程。"""
    pid = _read_pid()
    if pid:
        try:
            os.kill(pid, 0)
            print(f"引擎已在运行 (PID {pid})")
            return
        except OSError:
            pass  # 进程已死，清理

    # 分离为守护进程
    proc = multiprocessing.Process(target=_run_engine, args=(args,), daemon=False)
    proc.start()
    print(f"引擎已启动 (PID {proc.pid})")
    _write_pid(proc.pid)


def _run_engine(args: argparse.Namespace):
    """在子进程中运行引擎。"""
    asyncio.run(_async_run_engine(args))


async def _async_run_engine(args: argparse.Namespace):
    config = Config()
    log.info("引擎守护进程启动 (PID %d)", os.getpid())

    from yanling.adapters.llm.deepseek import DeepSeekAdapter
    from yanling.adapters.llm.fallback import FallbackAdapter
    from yanling.adapters.llm.omix import OmixAdapter
    from yanling.adapters.storage.json_file import JsonFileStorage
    from yanling.kernel.action import ActionSystem
    from yanling.kernel.boundary import BoundaryControl
    from yanling.kernel.cognition import CognitiveEngine
    from yanling.kernel.engine import YanLingEngine
    from yanling.kernel.evolution import EvolutionEngine
    from yanling.kernel.memory import MemorySystem
    from yanling.kernel.perception import PerceptionSystem

    storage = JsonFileStorage(config.get("memory", "storage_path",
                                          default=str(Path.home() / ".yanling" / "memory")))
    memory = MemorySystem(storage, config.get("memory"))
    llm = FallbackAdapter([DeepSeekAdapter(), OmixAdapter()])
    cognition = CognitiveEngine(llm)
    evolution = EvolutionEngine(memory, llm, cognition)
    boundary = BoundaryControl()

    engine = YanLingEngine(
        config=config,
        perception=PerceptionSystem(),
        cognition=cognition,
        action=ActionSystem(),
        memory=memory,
        evolution=evolution,
        boundary=boundary,
    )

    # 信号处理
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    # 可选 Web 面板
    web_task = None
    if getattr(args, "web", False):
        try:
            from yanling.web.registry import register as reg_engine
            reg_engine(engine)
            import uvicorn

            from yanling.web.dashboard import app as web_app
            host = getattr(args, "web_host", "0.0.0.0")
            port = getattr(args, "web_port", 8764)
            web_cfg = uvicorn.Config(web_app, host=host, port=port, log_level="info")
            web_task = asyncio.create_task(uvicorn.Server(web_cfg).serve())
            log.info("Web 面板已启动: http://%s:%d", host, port)
        except ImportError as e:
            log.warning("Web 面板不可用: %s", e)

    try:
        await engine.start()
        await stop_event.wait()
    except Exception as e:
        log.error("引擎异常退出: %s", e)
    finally:
        status = {
            "pid": os.getpid(),
            "uptime": time.time(),
            "state": engine.lifecycle.state.value,
        }
        _write_status(status)
        if web_task:
            web_task.cancel()
        await engine.stop()


def cmd_stop(args: argparse.Namespace):
    """停止引擎。"""
    pid = _read_pid()
    if not pid:
        print("引擎未在运行")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(10):
            try:
                os.kill(pid, 0)
                time.sleep(0.5)
            except OSError:
                break
        else:
            os.kill(pid, signal.SIGKILL)
        print(f"引擎已停止 (PID {pid})")
    except OSError:
        print(f"引擎未在运行 (PID {pid} 不存在)")
    finally:
        PID_FILE.unlink(missing_ok=True)


def cmd_status(args: argparse.Namespace):
    """查看引擎状态。"""
    pid = _read_pid()
    status = _read_status()

    if pid:
        try:
            os.kill(pid, 0)
            print(f"状态: 运行中 (PID {pid})")
            if status:
                print(f"最近状态: {status.get('state', 'unknown')}")
            return
        except OSError:
            pass

    print("状态: 已停止")


def cmd_run(args: argparse.Namespace):
    """运行指定场景。"""
    scenario_name = args.scenario

    if scenario_name == "embedded":
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from yanling.scenarios.embedded.main import main_rule

        if args.web:
            asyncio.run(_run_embedded_with_web(main_rule(), args.web_host, args.web_port))
        else:
            asyncio.run(main_rule())
    else:
        print(f"未知场景: {scenario_name}")
        print("可用场景: embedded")
        sys.exit(1)


async def _run_embedded_with_web(scenario_coro, host: str, port: int):
    """运行场景 + Web 面板，自动注册引擎到面板。"""
    import uvicorn

    from yanling.kernel.engine import YanLingEngine
    from yanling.web.dashboard import app as web_app
    from yanling.web.registry import register as reg_engine

    # Hook engine construction so the web panel can reference it
    original_init = YanLingEngine.__init__
    def _patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        reg_engine(self)
    YanLingEngine.__init__ = _patched_init

    try:
        web_cfg = uvicorn.Config(web_app, host=host, port=port, log_level="info")
        _web_task = asyncio.create_task(uvicorn.Server(web_cfg).serve())
        log.info("Web 面板已在 http://%s:%d 启动", host, port)
        await scenario_coro
    finally:
        YanLingEngine.__init__ = original_init


def cmd_list_scenarios(args: argparse.Namespace):
    """列出可用场景。"""
    scenarios_dir = Path(__file__).parent / "scenarios"
    if not scenarios_dir.exists():
        print("无可用场景")
        return

    scenarios = [d.name for d in scenarios_dir.iterdir() if d.is_dir() and not d.name.startswith("_")]
    if not scenarios:
        print("无可用场景")
        return

    print("可用场景:")
    for s in sorted(scenarios):
        print(f"  - {s}")


def cmd_config(args: argparse.Namespace):
    """查看当前配置。"""
    config = Config()
    print(json.dumps(config.raw, ensure_ascii=False, indent=2))
    warns = config.warnings
    if warns:
        print("\n配置警告:")
        for w in warns:
            print(f"  {w}")


def cmd_web(args: argparse.Namespace):
    """启动独立 Web 面板。"""
    try:
        from yanling.web.dashboard import start
    except ImportError as e:
        print(f"错误: Web 面板依赖缺失 — {e}", file=sys.stderr)
        print("请安装: pip install 'yanling[web]' 或 pip install fastapi uvicorn jinja2", file=sys.stderr)
        sys.exit(1)
    start(host=args.host, port=args.port)


def main():
    parser = argparse.ArgumentParser(prog="yanling", description="衍灵引擎命令行")
    sub = parser.add_subparsers(dest="command", help="可用命令")

    start_parser = sub.add_parser("start", help="启动引擎守护进程")
    start_parser.add_argument("--web", action="store_true", help=_WEB_HELP)
    start_parser.add_argument("--web-host", default="0.0.0.0", help="Web 面板监听地址")
    start_parser.add_argument("--web-port", type=int, default=8764, help="Web 面板端口")
    sub.add_parser("stop", help="停止引擎")
    sub.add_parser("status", help="查看引擎状态")

    run_parser = sub.add_parser("run", help="运行场景")
    run_parser.add_argument("scenario", help="场景名 (如 embedded)")
    run_parser.add_argument("--web", action="store_true", help=_WEB_HELP)
    run_parser.add_argument("--web-host", default="0.0.0.0", help="Web 面板监听地址")
    run_parser.add_argument("--web-port", type=int, default=8764, help="Web 面板端口")

    sub.add_parser("list-scenarios", help="列出可用场景")
    sub.add_parser("config", help="查看当前配置")

    web_parser = sub.add_parser("web", help="启动 Web 面板 (独立模式)")
    web_parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    web_parser.add_argument("--port", type=int, default=8764, help="监听端口")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    dispatch = {
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "run": cmd_run,
        "list-scenarios": cmd_list_scenarios,
        "config": cmd_config,
        "web": cmd_web,
    }

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
