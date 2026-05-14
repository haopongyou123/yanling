"""通信行动适配器 — 衍灵自主发送mailbox + 写入黑板 + 查询知识库"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.request

from yanling.core.types import Action, ActionResult
from yanling.kernel.action import ActionAdapter

log = logging.getLogger("yanling.comm_action")

DENGTA_HOST = "10.147.19.81"
DENGTA_PORT = 4321
MAILBOX_URL = f"http://{DENGTA_HOST}:{DENGTA_PORT}/api/mailbox"
BLACKBOARD_URL = f"http://{DENGTA_HOST}:{DENGTA_PORT}/api/blackboard"
KB_URL = "http://127.0.0.1:8766"

# ─── 消息签名（可选，无密钥时不阻塞）────────────────────────
_SIGNER = None
try:
    sys.path.insert(0, "/home/toto/auto-content")
    from signer import MessageSigner
    _key_path = os.path.expanduser("~/.config/yuanding/id_ed25519")
    if os.path.exists(_key_path):
        _SIGNER = MessageSigner("yanling", key_path=_key_path)
        log.info("[签名] 衍灵消息签名已启用 (fingerprint: %s)", _SIGNER.fingerprint)
except Exception:
    log.info("[签名] 衍灵消息签名未配置（降级为明文通信）")


def _sign_payload(payload: dict) -> dict:
    """如果签名器可用，添加签名。"""
    if _SIGNER:
        try:
            signed = _SIGNER.sign_mailbox(
                to=payload.get("to", ""),
                subject=payload.get("subject", ""),
                body=payload.get("body", ""),
                from_node=payload.get("from", "yanling"),
            )
            # 合并签名到原始 payload
            payload["signature"] = signed["signature"]
            payload["signer"] = signed["signer"]
            payload["key_fingerprint"] = signed["key_fingerprint"]
            payload["timestamp"] = signed["timestamp"]
        except Exception as e:
            log.warning("[签名] 签名失败（继续明文）: %s", e)
    return payload


class MailboxSender(ActionAdapter):
    """向中央 mailbox 发送消息给其他节点。"""

    def __init__(self):
        self._sent_count = 0

    @property
    def name(self) -> str:
        return "mailbox_sender"

    def capabilities(self) -> list[str]:
        return ["mailbox", "communicate"]

    async def execute(self, action: Action) -> ActionResult:
        to_node = action.params.get("to", "")
        subject = action.params.get("subject", "")
        body = action.params.get("body", "")
        if not to_node or not subject:
            return ActionResult(action_id=action.id, success=False, output="to和subject必填")

        payload = {
            "from": "yanling", "to": to_node,
            "subject": subject[:120], "body": str(body)[:500],
        }
        payload = _sign_payload(payload)
        msg = json.dumps(payload).encode()
        try:
            req = urllib.request.Request(MAILBOX_URL, data=msg,
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=5)
            self._sent_count += 1
            log.info("[mailbox] → %s: %s (signed: %s)", to_node, subject[:40],
                     "yes" if payload.get("signature") else "no")
            return ActionResult(action_id=action.id, success=True,
                                output={"to": to_node, "subject": subject[:40]})
        except Exception as e:
            log.warning("[mailbox] 发送失败 → %s: %s", to_node, e)
            return ActionResult(action_id=action.id, success=False, output=str(e))

    async def validate(self, action: Action) -> bool:
        return bool(action.params.get("to")) and bool(action.params.get("subject"))


class BlackboardWriter(ActionAdapter):
    """写入中央黑板。"""

    def __init__(self):
        self._write_count = 0

    @property
    def name(self) -> str:
        return "blackboard_writer"

    def capabilities(self) -> list[str]:
        return ["blackboard", "share"]

    async def execute(self, action: Action) -> ActionResult:
        key = action.params.get("key", "")
        value = action.params.get("value", "")
        if not key:
            return ActionResult(action_id=action.id, success=False, output="key必填")

        payload = {"key": key[:100], "value": str(value)[:500]}
        payload = _sign_payload(payload)
        body = json.dumps(payload).encode()
        try:
            req = urllib.request.Request(BLACKBOARD_URL, data=body,
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=5)
            self._write_count += 1
            return ActionResult(action_id=action.id, success=True, output={"key": key[:40]})
        except Exception as e:
            return ActionResult(action_id=action.id, success=False, output=str(e))

    async def validate(self, action: Action) -> bool:
        return bool(action.params.get("key"))


class KnowledgeBaseQuery(ActionAdapter):
    """查询本地知识库服务器。"""

    def __init__(self):
        self._query_count = 0

    @property
    def name(self) -> str:
        return "kb_query"

    def capabilities(self) -> list[str]:
        return ["knowledge", "search"]

    async def execute(self, action: Action) -> ActionResult:
        query = action.params.get("query", "")
        mode = action.params.get("mode", "search")

        try:
            if mode == "search":
                url = f"{KB_URL}/search?q={urllib.request.quote(query[:100])}"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                self._query_count += 1
                return ActionResult(action_id=action.id, success=True, output=data)
            elif mode == "get":
                tag = action.params.get("tag", "")
                url = f"{KB_URL}/tag/{urllib.request.quote(tag[:50])}"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                return ActionResult(action_id=action.id, success=True, output=data)
            else:
                return ActionResult(action_id=action.id, success=False, output=f"未知模式: {mode}")
        except Exception as e:
            return ActionResult(action_id=action.id, success=False, output=str(e))

    async def validate(self, action: Action) -> bool:
        return bool(action.params.get("query"))
