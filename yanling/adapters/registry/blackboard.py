"""黑板注册适配器 — 节点注册/心跳/发现.

利用现有的黑板协议 (http://10.147.19.81:4321/api/blackboard) 做分布式节点管理。
"""
from __future__ import annotations

import json
import logging
import os
import time

import httpx

from yanling.core.node import NodeIdentity

log = logging.getLogger("yanling.registry.blackboard")

DEFAULT_BLACKBOARD_URL = "http://10.147.19.81:4321/api/blackboard"


class BlackboardRegistry:
    """衍灵节点黑板注册器。"""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.environ.get(
            "YANLING_BLACKBOARD_URL", DEFAULT_BLACKBOARD_URL,
        )
        self._client = httpx.AsyncClient(timeout=5.0)
        self._identity: NodeIdentity | None = None
        self._registered = False

    @property
    def _key(self) -> str:
        if not self._identity:
            return ""
        return f"yanling_{self._identity.role.value}"

    @property
    def _heartbeat_key(self) -> str:
        if not self._identity:
            return ""
        return f"{self._key}_heartbeat"

    async def register(self, identity: NodeIdentity) -> bool:
        """注册节点到黑板。"""
        self._identity = identity
        payload = identity.to_dict()
        payload["started_at"] = time.time()
        payload["status"] = "online"

        try:
            r = await self._client.post(self.base_url, json={
                "key": self._key,
                "value": json.dumps(payload, ensure_ascii=False),
            })
            self._registered = r.is_success
            if self._registered:
                log.info("已注册到黑板: %s (%s)", identity.role.display_name, self.base_url)
            else:
                log.warning("黑板注册失败: HTTP %d", r.status_code)
            return self._registered
        except httpx.RequestError as e:
            log.warning("黑板不可达: %s", e)
            return False

    async def heartbeat(self, tick: int = 0, status: str = "ok") -> bool:
        """发送心跳。"""
        if not self._registered or not self._identity:
            return False

        payload = {
            "status": status,
            "ts": time.time(),
            "tick": tick,
            "node_id": self._identity.node_id,
        }
        try:
            r = await self._client.post(self.base_url, json={
                "key": self._heartbeat_key,
                "value": json.dumps(payload),
            })
            return r.is_success
        except httpx.RequestError:
            return False

    async def deregister(self) -> bool:
        """下线标记。"""
        if not self._registered or not self._identity:
            return False
        try:
            await self._client.post(self.base_url, json={
                "key": self._key,
                "value": json.dumps({"status": "offline"}, ensure_ascii=False),
            })
            self._registered = False
            log.info("已从黑板注销")
            return True
        except httpx.RequestError:
            return False

    async def discover(self) -> list[dict]:
        """发现所有注册的衍灵节点。"""
        try:
            r = await self._client.get(self.base_url)
            data = r.json()
            nodes = []
            for k, v in data.items():
                if k.startswith("yanling_") and not k.endswith("_heartbeat"):
                    try:
                        nodes.append(json.loads(v))
                    except (json.JSONDecodeError, TypeError):
                        pass
            return nodes
        except (httpx.RequestError, json.JSONDecodeError) as e:
            log.warning("节点发现失败: %s", e)
            return []

    async def close(self):
        await self._client.aclose()
