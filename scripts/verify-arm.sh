#!/usr/bin/env bash
# ARM64 交叉编译验证脚本
# 在 Mac（灯塔）上运行，验证衍灵 ARM64 Docker 映像
set -euo pipefail

echo "=== 衍灵 ARM64 验证清单 ==="
echo ""

PASS=0
FAIL=0

check() {
    local desc="$1"
    shift
    if "$@" &>/dev/null; then
        echo "  ✅ $desc"
        PASS=$((PASS + 1))
    else
        echo "  ❌ $desc"
        FAIL=$((FAIL + 1))
    fi
}

# 1. 基础设施
echo "【基础设施】"
check "Docker 已安装" docker --version
check "buildx 可用" docker buildx version
check "QEMU 模拟器可用" docker run --rm --privileged multiarch/qemu-user-static --reset -p yes 2>/dev/null || docker run --rm --platform linux/arm64 alpine uname -m &>/dev/null

# 2. 构建验证（仅 ARM64 架构，快速验证构建通过）
echo ""
echo "【构建验证】"
check "ARM64 映像可构建" docker buildx build --platform linux/arm64 -t yanling:arm64-test --load .

# 3. 运行时验证
echo ""
echo "【运行时验证】"
# 启动容器
cleanup() { docker rm -f yanling-test 2>/dev/null || true; }
trap cleanup EXIT

docker run -d --name yanling-test -p 8764:8764 yanling:arm64-test

check "容器启动成功" docker ps -q -f name=yanling-test
sleep 3
check "API /api/ping 响应" curl -sf http://localhost:8764/api/ping
check "API /api/status 返回 running" curl -sf http://localhost:8764/api/status | grep -q '"running":true'
check "Web 页面可访问" curl -sf http://localhost:8764/ | grep -q "衍灵引擎"

# 4. 查看运行时信息
echo ""
echo "【运行时信息】"
docker exec yanling-test python3 --version 2>/dev/null || echo "  ⚠ python3 版本获取失败"
docker exec yanling-test uname -m 2>/dev/null || echo "  ⚠ 架构获取失败"
docker exec yanling-test ffmpeg -version 2>/dev/null | head -1 || echo "  ⚠ ffmpeg 版本获取失败"

# 5. 清理
cleanup

echo ""
echo "==========================="
echo "结果: ✅ $PASS 通过, ❌ $FAIL 失败"
if [ "$FAIL" -eq 0 ]; then
    echo "🎉 ARM64 验证全部通过!"
else
    echo "⚠  有 $FAIL 项未通过，请检查"
fi
