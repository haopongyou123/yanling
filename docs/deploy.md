# 衍灵部署指南

## Docker 部署

```bash
# 构建映像
docker build -t yanling:latest .

# 启动
docker compose up -d

# 查看日志
docker logs -f yanling

# 访问
open http://localhost:8764
```

## ARM64 交叉编译（在 x86 上构建 ARM 映像）

```bash
# 安装 buildx（Docker Desktop 已内置）
docker buildx create --use --name arm-builder

# 构建并推送
docker buildx build \
  --platform linux/arm64,linux/amd64 \
  -t your-registry/yanling:latest \
  --push .

# 仅构建 ARM64 本地映像
docker buildx build \
  --platform linux/arm64 \
  -t yanling:arm64 \
  --load .
```

## ARM 盒子部署（Raspberry Pi / Orange Pi）

```bash
# 在 ARM 设备上
docker pull your-registry/yanling:arm64
docker run -d \
  --name yanling \
  --restart unless-stopped \
  -p 8764:8764 \
  -v yanling-data:/root/.yanling \
  -e DEEPSEEK_API_KEY=your_key \
  your-registry/yanling:arm64
```

## 三种部署形态

| 形态 | 硬件 | 模型 | 适用场景 |
|------|------|------|---------|
| ARM 盒子 | Orange Pi / RPi ¥150-200 | 本地 TinyLlama + 云端按需 | IoT 边缘设备、小型车间 |
| x86 工控机 | 标准 x86 主机 | 本地 Gemma4 + 云端按需 | 工厂线边、企业管理 |
| Docker 映像 | 现有服务器 | 全模型链 | 已有 IT 基础设施的客户 |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `YANLING_TICK_INTERVAL` | 主循环间隔（秒） | 5 |
| `YANLING_LANGUAGE` | 引擎语言 | zh |
| `YANLING_MODE` | 运行模式 | auto |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | — |
| `ANTHROPIC_BASE_URL` | LLM API 端点 | — |
| `ANTHROPIC_MODEL` | LLM 模型名 | — |
| `YANLING_NODE_ROLE` | 集群角色（可选） | — |

## 数据持久化

记忆和配置保存在 `/root/.yanling/`（Docker volume），包括：
- `memory/` — 分层记忆存储
- `config.json` — 运行时配置
- `engine.pid` — 进程 PID

## 健康检查

```bash
curl http://localhost:8764/api/ping
# {"ok": true, "node": "yanling", "version": "0.1.0"}

curl http://localhost:8764/api/status
# {"running": true, "state": "running", "tick": 1234, "uptime": 3600}
```
