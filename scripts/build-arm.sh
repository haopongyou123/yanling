#!/usr/bin/env bash
# ARM64 Docker 构建脚本 — 在 Mac（灯塔）上运行
# 用法: ./scripts/build-arm.sh [--push]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(dirname "$HERE")"

cd "$PROJECT"

echo "=== 衍灵 ARM64 Docker 构建 ==="
echo ""

# 1. 检查 Docker
if ! command -v docker &>/dev/null; then
    echo "❌ 需要 Docker Desktop（含 buildx）"
    echo "   下载: https://www.docker.com/products/docker-desktop/"
    exit 1
fi

if ! docker buildx version &>/dev/null; then
    echo "❌ 需要 Docker BuildX"
    echo "   docker buildx install"
    exit 1
fi

# 2. 创建 buildx builder（如果不存在）
if ! docker buildx ls | grep -q arm-builder; then
    echo "→ 创建 ARM buildx builder..."
    docker buildx create --use --name arm-builder
fi
docker buildx use arm-builder

# 3. 构建 amd64 + arm64 多架构映像
echo ""
echo "→ 构建多架构映像..."

BUILD_OPTS=(
    --platform linux/amd64,linux/arm64
    -t yanling:latest
)

if [ "${1:-}" = "--push" ]; then
    # 推送到仓库
    REGISTRY="${REGISTRY:-docker.io/youruser}"
    BUILD_OPTS=(
        --platform linux/amd64,linux/arm64
        -t "$REGISTRY/yanling:latest"
        -t "$REGISTRY/yanling:$(date +%Y%m%d)"
        --push
    )
    echo "  推送目标: $REGISTRY/yanling:latest"
fi

docker buildx build "${BUILD_OPTS[@]}" .

echo ""
echo "=== 构建完成 ==="
echo ""
echo "本地验证:"
echo "  docker run --rm -p 8764:8764 yanling:latest"
echo ""
echo "ARM 设备部署:"
echo "  docker pull your-registry/yanling:latest"
echo "  docker run -d --name yanling --restart unless-stopped \\"
echo "    -p 8764:8764 \\"
echo "    -v yanling-data:/root/.yanling \\"
echo "    -e DEEPSEEK_API_KEY=your_key \\"
echo "    your-registry/yanling:latest"
