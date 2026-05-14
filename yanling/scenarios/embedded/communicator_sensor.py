"""通信感知器 — 轮询 mailbox + 黑板，接收其他节点的消息。
   + 态势感知器 — 融合 L4/L5/告警/心跳，产出统一系统态势。"""

from __future__ import annotations

import copy
import json
import logging
import time
from collections import deque
from typing import Any

import urllib.request

from yanling.core.types import Percept
from yanling.kernel.perception import PerceptionAdapter

log = logging.getLogger("yanling.communicator")

# ── 中央 API 地址（灯塔 :4321） ──
DENGTA_HOST = "10.147.19.81"
DENGTA_PORT = 4321
MAILBOX_URL = f"http://{DENGTA_HOST}:{DENGTA_PORT}/api/mailbox"
BLACKBOARD_URL = f"http://{DENGTA_HOST}:{DENGTA_PORT}/api/blackboard"

NODE_NAME = "yanling"

# ── 态势常量 ──
SITUATION_WRITE_INTERVAL = 30
SITUATION_TREND_WINDOW = 6
SITUATION_KEY = "yanling_situational_latest"
SYSTEM_KEY_PREFIXES = [
    "zhangbu_l4_", "zhangbu_l5_", "alert_", "heartbeat_",
    "perception_", "watchdog_", "notice_", "recovered_",
]


class CommunicatorSensor(PerceptionAdapter):
    """感知适配器：轮询 mailbox 和黑板，将消息转为感知输入。

    衍灵通过此适配器接入三端通信回路：
    - mailbox: 接收定向消息（?from=yanling 过滤 to_node=yanling）
    - 黑板: 接收全局通知（notice_*、kb_* 等键）
    """

    def __init__(self):
        self._mailbox_since: float = 0.0
        self._bb_seen: set[str] = set()
        self._poll_count = 0

    @property
    def name(self) -> str:
        return "communicator"

    async def start(self):
        log.info("通信感知器启动 (mailbox:%s, blackboard:%s)", MAILBOX_URL, BLACKBOARD_URL)
        try:
            req = urllib.request.Request(BLACKBOARD_URL, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                bb = json.loads(resp.read())
            if isinstance(bb, dict):
                self._bb_seen.update(bb.keys())
            log.info("通信感知器已忽略 %d 个已存在的黑板键", len(self._bb_seen))
        except Exception as e:
            log.warning("通信感知器首次黑板轮询失败: %s", e)

    async def stop(self):
        log.info("通信感知器已停止")

    async def poll(self) -> list[Percept]:
        self._poll_count += 1
        percepts: list[Percept] = []

        # ── 轮询 mailbox ──
        try:
            url = f"{MAILBOX_URL}?from={NODE_NAME}&since={self._mailbox_since}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                msgs = json.loads(resp.read())
            if isinstance(msgs, list):
                for m in msgs:
                    percepts.append(Percept(
                        source="mailbox",
                        type="mail",
                        data={
                            "id": m.get("id", 0),
                            "from": m.get("from", "?"),
                            "to": m.get("to", ""),
                            "subject": m.get("subject", ""),
                            "body": m.get("body", ""),
                            "ts": m.get("ts", 0),
                        },
                    ))
                    ts = m.get("ts", 0)
                    if ts > self._mailbox_since:
                        self._mailbox_since = ts
        except Exception as e:
            log.warning("mailbox 轮询失败: %s", e)

        # ── 轮询黑板（仅新键） ──
        try:
            req = urllib.request.Request(BLACKBOARD_URL, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                bb = json.loads(resp.read())
            if isinstance(bb, dict):
                for k, v in bb.items():
                    if k in self._bb_seen:
                        continue
                    self._bb_seen.add(k)
                    if any(kw in k.lower() for kw in [
                        "notice_", "kb_", "yanling", "衍灵",
                        "yuanding_to_yanling", "dengta_to_yanling",
                        "heartbeat_", "watchdog_", "perception_",
                    ]):
                        percepts.append(Percept(
                            source="blackboard",
                            type="bb_update",
                            data={"key": k, "value": v[:500] if isinstance(v, str) else v},
                        ))
        except Exception as e:
            log.warning("黑板轮询失败: %s", e)

        if percepts:
            log.info("通信感知: %d 条新消息 (mailbox=%d, bb=%d)",
                     len(percepts),
                     sum(1 for p in percepts if p.source == "mailbox"),
                     sum(1 for p in percepts if p.source == "blackboard"))

        return percepts


class SituationalAwarenessSensor(PerceptionAdapter):
    """态势感知适配器：融合 L4/L5/告警/心跳/感知数据，产出统一系统态势。

    每 tick 轮询黑板全量，解析语义化的系统状态键，融合为结构化的
    态势报告，定期写回黑板 yanling_situational_latest（固定键覆盖）。

    趋势追踪：保留最近 N 个快照，判断告警增减、节点抖动等趋势。
    """

    def __init__(self):
        self._poll_count = 0
        self._last_write_ts: float = 0.0
        self._history: deque[dict] = deque(maxlen=SITUATION_TREND_WINDOW)
        self._prev_alerts: dict[str, float] = {}

    @property
    def name(self) -> str:
        return "situational_awareness"

    async def start(self):
        log.info("态势感知器启动 (黑板: %s, 写入键: %s)", BLACKBOARD_URL, SITUATION_KEY)
        try:
            req = urllib.request.Request(BLACKBOARD_URL, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                bb = json.loads(resp.read())
            if isinstance(bb, dict):
                known = {p: [k for k in bb if k.startswith(p)] for p in SYSTEM_KEY_PREFIXES}
                for prefix, keys in known.items():
                    if keys:
                        log.info("  发现 %s*: %d 个键 (如 %s)", prefix, len(keys), keys[-1])
                    else:
                        log.info("  未发现 %s* 键", prefix)
        except Exception as e:
            log.warning("态势感知器启动自检失败: %s", e)

    async def stop(self):
        log.info("态势感知器已停止")

    # ── 黑板 HTTP 工具 ──

    def _bb_get(self) -> dict | None:
        try:
            req = urllib.request.Request(BLACKBOARD_URL, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        except Exception as e:
            log.warning("态势: 黑板读取失败: %s", e)
            return None

    def _bb_post(self, key: str, value: dict) -> bool:
        try:
            body = json.dumps({"key": key, "value": json.dumps(value)}).encode()
            req = urllib.request.Request(BLACKBOARD_URL, data=body,
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception as e:
            log.warning("态势: 黑板写入 %s 失败: %s", key, e)
            return False

    # ── 解析器 ──

    def _parse_alerts(self, bb: dict) -> list[dict]:
        now = time.time()
        alerts = []
        for k, v in bb.items():
            if not k.startswith("alert_"):
                continue
            if v == "__deleted__":
                continue
            alert = {"key": k, "raw": str(v)[:300]}
            if isinstance(v, str):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, dict):
                        alert.update(parsed)
                except (json.JSONDecodeError, TypeError):
                    pass
            if k not in self._prev_alerts:
                self._prev_alerts[k] = now
            alert["first_seen_ago"] = round(now - self._prev_alerts[k], 1)
            alerts.append(alert)
        return alerts

    def _extract_ts(self, raw: Any) -> float | None:
        """从 heartbeat 键值中提取时间戳，兼容 JSON 对象和纯数字两种格式。"""
        if raw is None or raw == "__deleted__":
            return None
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str):
            # 先试纯数字
            try:
                return float(raw)
            except (ValueError, TypeError):
                pass
            # 再试 JSON 对象 {"ts": ..., ...}
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    ts = parsed.get("ts")
                    if ts is not None:
                        return float(ts)
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    def _parse_nodes(self, bb: dict) -> dict[str, dict]:
        now = time.time()
        # 节点 ID → 黑板 heartbeat 键名的映射
        node_map = {
            "dengta": "heartbeat_dengta_ts",
            "yuanding": "heartbeat_yuanding_ts",
            "guanjia": "heartbeat_windows_ts",
            "yanling": "heartbeat_yanling_ts",
            "zhangbu": "heartbeat_zhangbu_ts",
        }
        nodes: dict[str, dict] = {}
        for nid, hb_key in node_map.items():
            last_ts = self._extract_ts(bb.get(hb_key))
            online = last_ts is not None and (now - last_ts) < 180
            nodes[nid] = {
                "online": online,
                "last_heartbeat": last_ts,
                "seconds_ago": round(now - last_ts, 1) if last_ts else None,
            }
        return nodes

    def _parse_l4(self, bb: dict) -> list[str]:
        raw = bb.get("zhangbu_l4_alerts")
        if not raw or raw == "__deleted__":
            return []
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed.get("alerts", [])
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    def _parse_l5(self, bb: dict) -> dict | None:
        raw = bb.get("zhangbu_l5_meta")
        if not raw or raw == "__deleted__":
            return None
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    def _parse_perception(self, bb: dict) -> dict | None:
        raw = bb.get("perception_windows_status")
        if not raw or raw == "__deleted__":
            return None
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    def _compute_trend(self, snapshot: dict) -> dict:
        if not self._history:
            return {"alert_rate": 0, "nodes_flapping": [], "bb_growth": 0}

        prev = self._history[-1]
        trend: dict = {}

        curr_alert_count = len(snapshot.get("alerts", []))
        prev_alert_count = len(prev.get("alerts", []))
        trend["alert_rate"] = curr_alert_count - prev_alert_count

        curr_nodes = snapshot.get("nodes", {})
        prev_nodes = prev.get("nodes", {})
        flapping = []
        for nid in curr_nodes:
            curr_online = curr_nodes[nid].get("online", False)
            prev_online = prev_nodes.get(nid, {}).get("online", False)
            if curr_online != prev_online:
                flapping.append({"node": nid, "was_online": prev_online, "now_online": curr_online})
        trend["nodes_flapping"] = flapping

        curr_bb = snapshot.get("blackboard", {})
        prev_bb = prev.get("blackboard", {})
        trend["bb_growth"] = curr_bb.get("total_keys", 0) - prev_bb.get("total_keys", 0)

        return trend

    # ── 主轮询 ──

    async def poll(self) -> list[Percept]:
        self._poll_count += 1
        now = time.time()

        bb = self._bb_get()
        if not bb:
            return []

        percepts: list[Percept] = []

        # 1. 构建态势快照
        nodes = self._parse_nodes(bb)
        alerts = self._parse_alerts(bb)
        l4_alerts = self._parse_l4(bb)
        l5_meta = self._parse_l5(bb)
        perception = self._parse_perception(bb)

        total_keys = len(bb)
        ack_keys = sum(1 for k in bb if "ack" in k.lower())
        alert_keys = sum(1 for k in bb if k.startswith("alert_"))

        snapshot: dict[str, Any] = {
            "ts": now,
            "nodes": nodes,
            "alerts": {
                "active": alerts,
                "l4": l4_alerts,
                "total_active": len(alerts),
            },
            "queue": {
                "backlog": 0,
                "suspended": 0,
            },
            "blackboard": {
                "total_keys": total_keys,
                "ack_keys": ack_keys,
                "alert_keys": alert_keys,
                "ack_ratio": round(ack_keys / max(total_keys, 1), 3),
            },
            "l5_meta": l5_meta,
            "perception": perception,
        }

        for a in l4_alerts:
            if "队列积压" in a or "backlog" in a.lower():
                try:
                    parts = a.split("> ")
                    if len(parts) > 1:
                        snapshot["queue"]["backlog"] = int(parts[-1].split()[0])
                except (ValueError, IndexError):
                    pass
            if "挂起" in a:
                try:
                    parts = a.split("个")
                    if len(parts) > 0:
                        n = parts[0].split()[-1]
                        snapshot["queue"]["suspended"] = int(n)
                except (ValueError, IndexError):
                    pass

        # 2. 趋势
        snapshot["trend"] = self._compute_trend(snapshot)
        self._history.append(copy.deepcopy(snapshot))

        # 3. 产出态势 Percept
        percepts.append(Percept(
            source="situational_awareness",
            type="situation_report",
            data=snapshot,
        ))

        # 4. 定期写黑板（固定键覆盖，防膨胀）
        if now - self._last_write_ts >= SITUATION_WRITE_INTERVAL:
            write_data = {
                "ts": now,
                "nodes": {nid: {"online": info["online"]} for nid, info in nodes.items()},
                "alerts": {
                    "active_count": len(alerts),
                    "l4_count": len(l4_alerts),
                    "trend": snapshot["trend"].get("alert_rate", 0),
                },
                "queue": snapshot["queue"],
                "blackboard": snapshot["blackboard"],
                "trend": {
                    "alert_rate": snapshot["trend"].get("alert_rate", 0),
                    "nodes_flapping": snapshot["trend"].get("nodes_flapping", []),
                    "bb_growth": snapshot["trend"].get("bb_growth", 0),
                },
            }
            ok = self._bb_post(SITUATION_KEY, write_data)
            if ok:
                log.info("态势已写入黑板 %s (节点=%d, 告警=%d, L4=%d)",
                         SITUATION_KEY, sum(1 for n in nodes.values() if n["online"]),
                         len(alerts), len(l4_alerts))
            self._last_write_ts = now

        return percepts
