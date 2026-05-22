#!/usr/bin/env bash
# 衍灵引擎心跳 — 向所有黑板写入

TS=$(date +%s)
payload_enc="{\"key\":\"heartbeat_yanling_ts\",\"value\":\"{\\\"from\\\":\\\"yanling\\\",\\\"ts\\\":${TS},\\\"status\\\":\\\"ok\\\"}\"}"

# 向本地黑板写入（园丁 :8767）
curl -s -X POST http://localhost:8767/api/blackboard \
  -H "Content-Type: application/json" -d "$payload_enc" >/dev/null 2>&1

# 向灯塔黑板写入（LAN 地址，ZT 在 WSL2 不可用）
curl -s -X POST http://192.168.0.113:4321/api/blackboard \
  -H "Content-Type: application/json" -d "$payload_enc" >/dev/null 2>&1
