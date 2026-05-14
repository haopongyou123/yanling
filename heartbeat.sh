#!/usr/bin/env bash
# 衍灵引擎心跳 — 向所有黑板写入

TS=$(date +%s)
payload_enc="{\"key\":\"heartbeat_yanling_ts\",\"value\":\"{\\\"from\\\":\\\"yanling\\\",\\\"ts\\\":${TS},\\\"status\\\":\\\"ok\\\"}\"}"

# 向衍灵本地黑板写入
curl -s -X POST http://localhost:8767/api/blackboard \
  -H "Content-Type: application/json" -d "$payload_enc" >/dev/null 2>&1

# 向灯塔黑板写入
curl -s -X POST http://10.147.19.81:4321/api/blackboard \
  -H "Content-Type: application/json" -d "$payload_enc" >/dev/null 2>&1

# 向园丁黑板写入
curl -s -X POST http://10.147.49.29:8765/api/blackboard \
  -H "Content-Type: application/json" -d "$payload_enc" >/dev/null 2>&1
