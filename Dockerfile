# 衍灵引擎 — 多架构 Docker 映像
# 构建:  docker build -t yanling:latest .
# ARM64: docker buildx build --platform linux/arm64 -t yanling:arm64 .
# 运行:  docker run -d --name yanling -p 8764:8764 -v yanling-data:/root/.yanling yanling:latest

# ── 构建阶段 ──────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir build && \
    python -m build --wheel

# ── 运行阶段 ──────────────────────────────────
FROM python:3.11-slim

LABEL org.opencontainers.image.title="衍灵引擎"
LABEL org.opencontainers.image.description="通用 AI 自我进化系统内核"
LABEL org.opencontainers.image.version="0.1.0"

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 安装衍灵
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && \
    rm /tmp/*.whl

# Web 面板额外依赖（默认同进程模式需要 FastAPI + uvicorn）
RUN pip install --no-cache-dir "uvicorn[standard]>=0.34" jinja2 aiohttp httpx

# edge-tts（配音）
RUN pip install --no-cache-dir edge-tts

# 数据卷
VOLUME ["/root/.yanling"]

# 端口
EXPOSE 8764

# 环境变量
ENV YANLING_TICK_INTERVAL=5 \
    YANLING_LANGUAGE=zh \
    YANLING_MODE=auto

# 入口：运行嵌入式场景 + Web 面板
ENTRYPOINT ["python", "-m", "yanling.scenarios.embedded.run_persistent"]
CMD ["--web", "--host", "0.0.0.0", "--port", "8764"]
