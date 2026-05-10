#!/usr/bin/env bash
# ─── 衍灵本地监控 — 一键启动 ──────────────────────────────
set -e
cd "$(dirname "$0")"

MODE="${YANLING_MODE:-rule}"          # rule | llm
LANG="${YANLING_LANGUAGE:-zh}"        # zh | en | ar | ja | ko | es

echo "╔════════════════════════════════════════════════╗"
echo "║     衍灵内核 — 本机系统监控                    ║"
echo "║     Web 面板: http://localhost:8764            ║"
echo "║     模式: ${MODE} · 语言: ${LANG}               ║"
echo "║     按 Ctrl+C 停止                             ║"
echo "╚════════════════════════════════════════════════╝"
echo ""

# 激活虚拟环境
VENV=".venv"
if [ ! -d "$VENV" ]; then
    echo "创建虚拟环境..."
    python3 -m venv "$VENV"
fi
source "$VENV/bin/activate"

# 确保依赖
pip install -q psutil 2>/dev/null || true

# 启动
YANLING_MODE="${MODE}" YANLING_LANGUAGE="${LANG}" \
  PYTHONPATH="$PWD" exec "$VENV/bin/python" -m yanling.scenarios.embedded.run_persistent
