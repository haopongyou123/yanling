#!/usr/bin/env bash
# 衍灵引擎心跳 — 每60s写入中央黑板
ts=$(date +%s)
payload="{\"key\":\"heartbeat_yanling_ts\",\"value\":\"{\\\"from\\\":\\\"yanling\\\",\\\"ts\\\":$ts,\\\"status\\\":\\\"ok\\\"}\"}"
curl -s -X POST http://10.147.19.81:4321/api/blackboard \
  -H "Content-Type: application/json" \
  -d "$payload" >/dev/null 2>&1
