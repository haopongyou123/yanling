"""节点身份与角色定义 — 衍灵分布式部署的基础。"""
from __future__ import annotations

import enum
import logging
import os
import socket
from dataclasses import dataclass, field

log = logging.getLogger("yanling.node")


class NodeRole(enum.Enum):
    """衍灵节点角色枚举。"""
    LIGHTHOUSE = "lighthouse"
    BUTLER = "butler"
    ACCOUNTANT = "accountant"
    EMBEDDED = "embedded"  # 默认单机模式，不注册黑板

    @classmethod
    def detect(cls) -> NodeRole:
        """从 YANLING_NODE_ROLE 环境变量检测角色，默认 embedded。"""
        raw = os.environ.get("YANLING_NODE_ROLE", "").strip().lower()
        for role in cls:
            if role.value == raw:
                return role
        return cls.EMBEDDED

    @property
    def display_name(self) -> str:
        return {
            "lighthouse": "衍灵·灯塔 — 中央调度",
            "butler": "衍灵·管家 — 本地运维",
            "accountant": "衍灵·掌簿 — 凭证保险柜",
            "embedded": "衍灵·单机模式",
        }[self.value]

    @property
    def profile_filename(self) -> str | None:
        """对应的边界策略文件名，embedded 模式无策略文件。"""
        if self.value == "embedded":
            return None
        return f"{self.value}.yaml"


@dataclass
class NodeIdentity:
    """衍灵节点身份。"""
    node_id: str = field(default_factory=lambda: socket.gethostname())
    role: NodeRole = field(default_factory=NodeRole.detect)
    capabilities: set[str] = field(default_factory=set)

    def __post_init__(self):
        if not self.capabilities:
            self.capabilities = _default_capabilities(self.role)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "role": self.role.value,
            "display_name": self.role.display_name,
            "capabilities": sorted(self.capabilities),
        }

    @classmethod
    def detect(cls) -> NodeIdentity:
        """自动检测节点身份。"""
        return cls()


def _default_capabilities(role: NodeRole) -> set[str]:
    """每个角色的默认能力集。"""
    caps = {
        NodeRole.LIGHTHOUSE: {
            "perception.system", "perception.blackboard",
            "cognition.llm",
            "action.alert", "action.log", "action.adjust", "action.notify",
            "evolution.deep",
        },
        NodeRole.BUTLER: {
            "perception.system",
            "action.alert", "action.log", "action.adjust",
        },
        NodeRole.ACCOUNTANT: {
            "action.log",
        },
        NodeRole.EMBEDDED: {
            "perception.system",
            "action.alert", "action.log", "action.adjust",
        },
    }
    return caps.get(role, set())
