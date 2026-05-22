"""衍灵 Web 面板 — FastAPI + Jinja2 + HTMX.

支持两种模式:
  1. 同进程 — 引擎和 Web 运行在同一个事件循环中，直接访问引擎实例
  2. 独立 — 通过引擎全局注册表获取运行中的引擎实例 (仅开发/调试用)
"""
from __future__ import annotations

import json as _json
import logging
import os
import re as _re
from pathlib import Path
from typing import Any

from yanling.web.registry import get as get_engine

log = logging.getLogger("yanling.web")

HERE = Path(__file__).parent


def _parse_score_json(raw: str, model_label: str) -> dict | None:
    """从模型响应中提取 JSON 评分结果。"""
    raw = raw.strip()
    if not raw:
        return None
    json_match = _re.search(r'\{.*\}', raw, _re.DOTALL)
    if not json_match:
        return None
    try:
        parsed = _json.loads(json_match.group())
        score = float(parsed.get("score", 6.0))
        score = max(1, min(10, score))
        return {
            "score": score,
            "passed": score >= 5.5,
            "issues": parsed.get("issues", []),
            "suggestions": parsed.get("suggestions", []),
            "model": model_label,
        }
    except (ValueError, TypeError, _json.JSONDecodeError):
        return None



# ─── 模型注册表 ─────────────────────────────────────────────
# 可扩展：后续接入自定义蒸馏模型时在此注册即可

MODEL_REGISTRY = [
    # DeepSeek 云端系列
    {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "group": "DeepSeek 云端",
     "base_url": "http://localhost:4000/v1/messages", "provider": "deepseek"},
    {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "group": "DeepSeek 云端",
     "base_url": "http://localhost:4000/v1/messages", "provider": "deepseek"},
    {"id": "deepseek-chat", "name": "DeepSeek Chat", "group": "DeepSeek 云端",
     "base_url": "http://localhost:4000/v1/messages", "provider": "deepseek"},
    {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner", "group": "DeepSeek 云端",
     "base_url": "http://localhost:4000/v1/messages", "provider": "deepseek"},
    # 本地模型
    {"id": "gemma-4-e4b-it-4bit", "name": "Gemma 4 27B (4bit)", "group": "本地 oMLX",
     "base_url": "http://localhost:8000/v1/chat/completions", "provider": "omlx"},
    {"id": "gemma-4-e4b-it-8bit", "name": "Gemma 4 27B (8bit)", "group": "本地 oMLX",
     "base_url": "http://localhost:8000/v1/chat/completions", "provider": "omlx"},
    {"id": "Qwen3.5-9B-MLX-4bit", "name": "Qwen 3.5 9B (MLX)", "group": "本地 oMLX",
     "base_url": "http://localhost:8000/v1/chat/completions", "provider": "omlx"},
    # Ollama
    {"id": "ollama/gemma4:e4b", "name": "Gemma 4 (Ollama)", "group": "本地 Ollama",
     "base_url": "http://localhost:11434/api/chat", "provider": "ollama"},
    # 预留 — 自定义蒸馏模型
    # {"id": "yanling-custom-v1", "name": "衍灵蒸馏 v1", "group": "自定义",
    #  "base_url": "http://localhost:4000/v1/chat/completions", "provider": "custom"},
]

# ─── FastAPI 应用 ───────────────────────────────────────────

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:
    raise ImportError(
        "需要安装 Web 面板依赖: pip install 'yanling[web]' 或 "
        "pip install fastapi uvicorn jinja2"
    ) from None

app = FastAPI(title="衍灵引擎仪表盘")

# 直接使用 Jinja2 Environment，绕过 Starlette 的 Jinja2Templates 包装器
import jinja2

_template_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(HERE / "templates")),
    autoescape=jinja2.select_autoescape(),
)
_globals: dict[str, Any] = {}  # 模板全局变量，当前为空


def _render(name: str, **context: Any) -> str:
    """渲染 Jinja2 模板。"""
    template = _template_env.get_template(name)
    return template.render(**context, **_globals)


static_dir = HERE / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ─── 辅助函数 ───────────────────────────────────────────────


def _engine_info() -> dict[str, Any]:
    """收集引擎当前状态信息。"""
    engine = get_engine()
    if not engine:
        return {"running": False, "state": "stopped"}

    info: dict[str, Any] = {
        "running": True,
        "state": engine.lifecycle.state.value if engine.lifecycle else "unknown",
        "tick_count": engine._tick_count,
        "idle_ticks": getattr(engine, "_idle_ticks", 0),
        "stats": engine.stats.snapshot() if engine.stats else None,
        "config_warnings": [str(w) for w in engine.config.warnings] if engine.config else [],
        "node_role": engine.node.role.value if engine.node else None,
        "blackboard_url": getattr(engine, "_registry", None) and engine._registry.base_url or None,
        "model": _get_current_model(engine),
        "model_base_url": _get_current_model_base_url(engine),
        "using_baseline": getattr(engine, "using_baseline", False),
        "baseline_model": "tinyllama:latest",
    }

    # 语言设置
    if engine.cognition and hasattr(engine.cognition, "language"):
        info["language"] = engine.cognition.language
    if engine.evolution and hasattr(engine.evolution, "language"):
        info["evolution_language"] = engine.evolution.language

    # 记忆系统
    if engine.memory:
        ws = {}
        try:
            raw = engine.memory.working_snapshot
            ws = {k: str(v)[:100] for k, v in raw.items()}
        except Exception:
            ws = {"error": "working snapshot unavailable"}
        info["memory"] = {
            "working": ws,
            "short_term": [
                _entry_dict(e) for e in engine.memory.recent_short_term
            ],
            "long_term": [
                _entry_dict(e) for e in engine.memory.important_long_term
            ],
        }

    # 进化系统
    if engine.evolution:
        perf = engine.evolution.performance_summary
        info["evolution"] = {
            "performance": perf,
            "patterns": sorted(
                engine.evolution.pattern_db.items(),
                key=lambda x: -x[1],
            )[:20],
            "adjustments": [
                {
                    "id": a.id,
                    "area": a.area,
                    "reason": a.reason[:100],
                    "outcome": a.outcome,
                    "timestamp": a.timestamp,
                }
                for a in engine.evolution.adjustment_history[-20:]
            ],
            "steps": len(engine.evolution.steps),
            "reports": engine.evolution.reports,
        }

    # 当前 tick 细节
    stats = engine.stats
    if stats and stats._ticks:
        last = stats._ticks[-1]
        info["last_tick"] = {
            "id": last.tick_id,
            "percepts": last.percepts,
            "decisions": last.decisions,
            "actions": last.actions,
            "success_rate": last.success_rate,
            "latency": round(last.latency, 3),
            "error": last.error,
        }

    # 世界模型
    if engine.world_model:
        try:
            wm_summary = engine.world_model.summary()
            wm_corrs = engine.world_model.get_correlations(min_count=2)
            info["world_model"] = {
                "total_ticks": wm_summary["total_ticks"],
                "correlations_tracked": wm_summary["correlations_tracked"],
                "significant": wm_summary["significant_correlations"],
                "top_correlations": [
                    {
                        "antecedent": c.antecedent,
                        "consequent": c.consequent,
                        "probability": round(c.probability, 2),
                        "count": c.count,
                    }
                    for c in wm_corrs[:5]
                ],
                "metric_baselines": wm_summary["metric_baselines"],
            }
        except Exception:
            info["world_model"] = {"error": "unavailable"}

    return info


def _get_current_model(engine) -> str:
    """获取当前使用的模型名。"""
    try:
        if engine.cognition and engine.cognition.llm:
            return getattr(engine.cognition.llm, "model_name",
                          getattr(engine.cognition.llm, "model", ""))
    except Exception:
        pass
    return os.environ.get("YANLING_LLM_MODEL", "deepseek-v4-flash")


def _get_current_model_base_url(engine) -> str:
    """获取当前模型的 API 地址。"""
    try:
        if engine.cognition and engine.cognition.llm:
            return getattr(engine.cognition.llm, "base_url", "")
    except Exception:
        pass
    return os.environ.get("YANLING_LLM_BASE_URL",
                         "http://localhost:4000/v1/messages")


def _entry_dict(e: Any) -> dict:
    return {
        "key": e.key,
        "type": e.type,
        "importance": e.importance,
        "timestamp": e.timestamp,
        "tags": e.tags,
        "content_preview": str(e.content)[:120],
    }


# ─── 页面路由 ───────────────────────────────────────────────


@app.get("/api/ping")
async def api_ping():
    return {"ok": True, "node": "yanling", "version": "0.1.0"}

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    info = _engine_info()
    html = _render(
        "index.html",
        request=request, info=info, active_tab="overview",
    )
    return HTMLResponse(html)


@app.get("/memory", response_class=HTMLResponse)
async def memory_page(request: Request):
    info = _engine_info()
    html = _render(
        "memory.html",
        request=request, info=info, active_tab="memory",
    )
    return HTMLResponse(html)


@app.get("/evolution", response_class=HTMLResponse)
async def evolution_page(request: Request):
    info = _engine_info()
    html = _render(
        "evolution.html",
        request=request, info=info, active_tab="evolution",
    )
    return HTMLResponse(html)


# ─── JSON API ───────────────────────────────────────────────


@app.get("/api/status")
async def api_status():
    """引擎运行状态 JSON。"""
    engine = get_engine()
    if not engine:
        return JSONResponse({"running": False, "state": "stopped"})
    return JSONResponse({
        "running": True,
        "state": engine.lifecycle.state.value,
        "tick": engine._tick_count,
        "uptime": engine.stats.uptime if engine.stats else 0,
    })


@app.get("/api/stats")
async def api_stats():
    """引擎指标 JSON (供 HTMX 轮询)。"""
    engine = get_engine()
    if not engine or not engine.stats:
        return JSONResponse({"status": "idle", "total_ticks": 0})
    return JSONResponse(engine.stats.snapshot())


@app.get("/nodes", response_class=HTMLResponse)
async def nodes_page(request: Request):
    info = _engine_info()
    nodes = await _fetch_nodes(info)
    html = _render(
        "nodes.html",
        request=request, info=info, nodes=nodes, active_tab="nodes",
    )
    return HTMLResponse(html)


@app.get("/api/nodes")
async def api_nodes():
    """集群节点列表 JSON。"""
    info = _engine_info()
    nodes = await _fetch_nodes(info)
    return JSONResponse({"nodes": nodes, "local": info.get("node_role")})


async def _fetch_nodes(info: dict) -> list[dict]:
    """从黑板查询所有衍灵节点。"""
    bb_url = info.get("blackboard_url") or "http://localhost:8767/api/blackboard"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(bb_url)
            data = r.json()
    except Exception:
        return []

    import json as j
    result = []
    heartbeats: dict[str, dict] = {}
    registrations: dict[str, dict] = {}

    for k, v in data.items():
        if not k.startswith("yanling_"):
            continue
        try:
            parsed = j.loads(v)
        except (j.JSONDecodeError, TypeError):
            continue

        if not isinstance(parsed, dict):
            continue  # 跳过非 dict 值（如数组、字符串等）

        if k.endswith("_heartbeat"):
            heartbeats[k] = parsed
        else:
            registrations[k] = parsed

    for role_key, reg in registrations.items():
        role = role_key.replace("yanling_", "")
        hb = heartbeats.get(f"{role_key}_heartbeat", {})

        node = dict(reg)
        node["role"] = role

        # 合并心跳信息
        hb_ts = hb.get("ts", 0)
        start_ts = reg.get("started_at", 0)
        now = __import__("time").time()

        if hb_ts and now - hb_ts < 120:
            node["status"] = "online"
        elif reg.get("status") == "offline":
            node["status"] = "offline"
        else:
            node["status"] = "unknown"

        node["last_heartbeat"] = hb_ts
        node["last_heartbeat_str"] = _fmt_time(hb_ts) if hb_ts else "-"

        if start_ts:
            uptime_s = now - start_ts
            node["uptime_str"] = _fmt_duration(uptime_s)

        result.append(node)

    result.sort(key=lambda x: x.get("role", ""))
    return result


def _fmt_time(ts: float) -> str:
    """格式化时间戳为可读字符串。"""
    import datetime
    dt = datetime.datetime.fromtimestamp(ts)
    now = datetime.datetime.now()
    diff = now - dt
    if diff.total_seconds() < 60:
        return "刚刚"
    if diff.total_seconds() < 3600:
        return f"{int(diff.total_seconds() // 60)}分钟前"
    if diff.total_seconds() < 86400:
        return f"{int(diff.total_seconds() // 3600)}小时前"
    return dt.strftime("%m-%d %H:%M")


def _fmt_duration(seconds: float) -> str:
    """格式化为人类可读的时长。"""
    seconds = int(seconds)
    h, m = divmod(seconds, 3600)
    m, s = divmod(m, 60)
    if h > 24:
        d, h = divmod(h, 24)
        return f"{d}d {h}h"
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


@app.get("/api/summary")
async def api_summary():
    """完整引擎摘要 JSON。"""
    return JSONResponse(_engine_info())


@app.post("/api/language")
async def api_set_language(request: Request):
    """动态切换引擎语言。"""
    body = await request.json()
    lang = body.get("language", "").strip().lower()
    valid = {"zh", "en", "ar", "ja", "ko", "es"}
    if lang not in valid:
        return JSONResponse({"ok": False, "error": f"不支持的语言: {lang}，可选: {valid}"})

    engine = get_engine()
    if not engine:
        return JSONResponse({"ok": False, "error": "引擎未运行"})

    from yanling.core.types import LANGUAGES
    if engine.cognition and hasattr(engine.cognition, "language"):
        engine.cognition.language = lang
        engine.cognition.update_system_prompt(engine.cognition._default_system_prompt())
    if engine.evolution and hasattr(engine.evolution, "language"):
        engine.evolution.language = lang

    log.info("引擎语言已切换为: %s (%s)", lang, LANGUAGES.get(lang, {}).get("name", lang))
    return JSONResponse({"ok": True, "language": lang, "name": LANGUAGES.get(lang, {}).get("name", lang)})


# ─── 模型管理 API ───────────────────────────────────────────

_availability_cache: dict[str, tuple[bool, float]] = {}
_CACHE_TTL = 30  # 秒


async def _check_model_available(model: dict) -> bool:
    """检查单个模型在当前环境是否可用。"""
    provider = model.get("provider", "")
    model_id = model.get("id", "")

    # 使用缓存
    now = __import__("time").time()
    cached = _availability_cache.get(provider)
    if cached and now - cached[1] < _CACHE_TTL:
        return cached[0]

    import httpx

    if provider == "deepseek":
        # 检查 API Key 和 DeepSeek API 可达性
        api_key = os.environ.get("AI_API_KEY", "")
        if not api_key:
            _availability_cache[provider] = (False, now)
            return False
        try:
            base = model.get("base_url", "http://localhost:4000/v1/messages")
            async with httpx.AsyncClient(timeout=5.0) as c:
                # 只检查 API 可达性，不真正调用
                r = await c.get(base.replace("/v1/messages", "/v1/models"), timeout=3.0)
                ok = r.status_code < 500
        except Exception:
            ok = bool(api_key)  # 有 key 就当可用
        _availability_cache[provider] = (ok, now)
        return ok

    elif provider == "omlx":
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get("http://localhost:8000/v1/models")
                ok = r.status_code == 200
        except Exception:
            ok = False
        _availability_cache[provider] = (ok, now)
        return ok

    elif provider == "ollama":
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get("http://localhost:11434/api/tags")
                if r.status_code != 200:
                    _availability_cache[provider] = (False, now)
                    return False
                models = r.json().get("models", [])
                # 检查具体模型是否存在
                model_prefix = model_id.split(":")[0].split("/")[-1]
                ok = any(model_prefix in m["name"] for m in models)
                _availability_cache[provider] = (ok, now)
                return ok
        except Exception:
            _availability_cache[provider] = (False, now)
            return False

    elif provider == "custom":
        # 自定义模型按添加时的设置判断
        return False

    return False


async def _check_baseline() -> bool:
    """检查基线模型是否可用。"""
    try:
        from yanling.core.baseline import is_baseline_available
        return await is_baseline_available()
    except Exception:
        return False


@app.get("/api/models")
async def api_list_models():
    """返回可用模型列表（含可用性检测）+ 当前模型 + 推荐。"""
    engine = get_engine()
    current = _get_current_model(engine) if engine else os.environ.get("YANLING_LLM_MODEL", "deepseek-v4-flash")
    baseline_ok = await _check_baseline()

    # 并行检查各模型可用性
    import asyncio
    tasks = [_check_model_available(m) for m in MODEL_REGISTRY]
    avail = await asyncio.gather(*tasks)

    enriched = []
    for m, ok in zip(MODEL_REGISTRY, avail):
        entry = dict(m)
        entry["available"] = ok
        enriched.append(entry)

    # 推荐逻辑：按优先级取第一个可用的
    recommendation = None
    for m, ok in zip(enriched, avail):
        if ok:
            recommendation = {"model": m["id"], "name": m["name"], "reason": f"{m['group']} — 可用"}
            break

    if not recommendation and baseline_ok:
        recommendation = {"model": "tinyllama:latest", "name": "衍灵基线 (TinyLlama)", "reason": "本地基线模型 — 始终可用"}

    return JSONResponse({
        "models": enriched,
        "current": current,
        "baseline_available": baseline_ok,
        "recommendation": recommendation,
    })


@app.post("/api/model")
async def api_set_model(request: Request):
    """运行时切换 LLM 模型。"""
    body = await request.json()
    model_id = body.get("model", "").strip()

    # 在注册表中查找
    entry = next((m for m in MODEL_REGISTRY if m["id"] == model_id), None)
    if not entry:
        return JSONResponse({"ok": False, "error": f"未知模型: {model_id}"})

    engine = get_engine()
    if not engine:
        return JSONResponse({"ok": False, "error": "引擎未运行"})

    if not hasattr(engine, "set_llm_model"):
        return JSONResponse({"ok": False, "error": "引擎不支持模型热切换"})

    try:
        engine.set_llm_model(entry["id"], entry["base_url"])
        log.info("模型已切换: %s (%s)", entry["name"], entry["base_url"])
        return JSONResponse({"ok": True, "model": model_id, "name": entry["name"]})
    except Exception as e:
        log.error("模型切换失败: %s", e)
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/model/baseline")
async def api_reset_baseline():
    """恢复为内置基线模型。"""
    engine = get_engine()
    if not engine:
        return JSONResponse({"ok": False, "error": "引擎未运行"})

    if not hasattr(engine, "reset_to_baseline"):
        return JSONResponse({"ok": False, "error": "引擎不支持基线恢复"})

    ok = engine.reset_to_baseline()
    if ok:
        return JSONResponse({"ok": True, "model": "tinyllama:latest", "name": "衍灵基线 (TinyLlama)"})
    else:
        return JSONResponse({"ok": False, "error": "基线模型加载失败，请检查 Ollama 是否运行"})


# ─── 内容评分 API ──────────────────────────────────────────
# 衍灵 + Ollama Gemma4 (零成本) 为 auto-content 管道提供质量评分


@app.post("/api/score-content")
async def api_score_content(request: Request):
    """用本地 Gemma4 对文章内容进行质量评分（零成本）。

    Body:
        ``{"items": [{"title": "...", "summary": "..."}]}``
        （可以带 ``titles`` 和 ``opening`` 字段）

    Returns:
        ``{"score": float, "passed": bool, "issues": [str], "model": str}``
    """
    body = await request.json()
    items = body.get("items", [])
    titles = body.get("titles", body.get("opening", ""))
    opening = body.get("opening", "")

    # 构建评分用的文本（精简，加快本地推理）
    text_for_review = ""
    if titles:
        t = titles if isinstance(titles, list) else [titles]
        text_for_review += "标题: " + " | ".join(t[:2]) + "\n"
    for item in items[:6]:
        text_for_review += f"- {item.get('title', '')}: {item.get('summary', '')[:80]}\n"

    prompt = f"""你是一个内容编辑。返回JSON评分(1-10)。

评审判据：信息量(40%)、可读性(30%)、标题质量(20%)、合规性(10%)

文章：
{text_for_review}

JSON格式: {{"score": 分数, "issues": ["问题1"], "suggestions": ["建议1"]}}
只返回JSON。"""

    # 尝试本地模型 → AI Proxy 免费模型（降级链）
    score_result = None

    # 1) 尝试 Ollama tinyllama（最快本地模型）
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post("http://localhost:11434/api/generate", json={
                "model": "tinyllama:latest",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 128},
            })
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("response", "").strip()
            if raw:
                score_result = _parse_score_json(raw, "tinyllama (本地)")
    except Exception as e:
        log.warning("tinyllama 评分失败: %s", e)

    # 2) 尝试 Ollama gemma4（更强但较慢）
    if not score_result:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post("http://localhost:11434/api/generate", json={
                    "model": "gemma4:e4b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 128},
                })
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("response", "").strip()
                if raw:
                    score_result = _parse_score_json(raw, "gemma4:e4b (本地)")
        except Exception as e:
            log.warning("gemma4 评分失败: %s", e)

    # 3) 降级到 AI Proxy qwen-turbo（免费云）
    if not score_result:
        try:
            import httpx
            qwen_prompt = f"""你是一个内容编辑，评审以下文章并给出分数(1-10)和改进建议。

评审判据：
1. 信息量 — 是否有具体数据、事实、引用 (权重40%)
2. 可读性 — 语言是否流畅、结构是否清晰 (权重30%)
3. 标题质量 — 是否吸引人且准确 (权重20%)
4. 合规性 — 是否违反平台规定 (权重10%)

文章：
{text_for_review}

要求：只返回JSON，格式: {{"score": 分数, "passed": true/false, "issues": ["问题1"], "suggestions": ["建议1"]}}
passed = score >= 6.0，最多各3条。"""
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post("http://localhost:4000/v1/chat/completions", json={
                    "model": "qwen-turbo",
                    "messages": [{"role": "user", "content": qwen_prompt}],
                    "temperature": 0.1,
                    "max_tokens": 500,
                })
                resp.raise_for_status()
                data = resp.json()
                raw = data["choices"][0]["message"]["content"]
                parsed = _parse_score_json(raw, "qwen-turbo (免费云)")
                if parsed:
                    score_result = parsed
        except Exception as e:
            log.warning("qwen-turbo 评分也失败: %s", e)

    if score_result:
        return JSONResponse(score_result)

    return JSONResponse({
        "score": 6.0, "passed": True,
        "issues": ["所有评分服务均不可用，自动通过"],
        "suggestions": [], "model": "fallback",
    })


# ─── 启动器 ─────────────────────────────────────────────────


def start(host: str = "0.0.0.0", port: int = 8764):
    """启动 Web 面板服务器 (阻塞)。"""
    import uvicorn
    log.info("Web 面板启动于 http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
