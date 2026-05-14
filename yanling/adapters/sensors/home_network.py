"""家用网络设备感知适配器。

扫描本地网络，发现并监控智能家居设备状态：
开关、插座、监控、影音设备、洗衣机、水阀、报警器、饮水机等。

设计：
- 启动时秒级完成：仅读 ARP 缓存发现设备
- 后台缓慢完成：逐步探测端口、识别类型
- 每个 tick 只做快速在线检查
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import subprocess
import time
from typing import Any

from yanling.core.types import Percept
from yanling.kernel.perception import PerceptionAdapter

log = logging.getLogger("yanling.sensor.home_network")


def _get_local_subnet() -> str:
    """自动探测本地子网。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ".".join(ip.split(".")[:3]) + ".0/24"
    except Exception:
        return "192.168.0.0/24"


async def _arp_scan() -> list[dict[str, str]]:
    """读取 ARP 缓存，发现局域网活跃设备（秒级完成）。"""
    found: list[dict[str, str]] = []
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "neigh", "show",
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        for line in stdout.decode().strip().split("\n"):
            line = line.strip()
            if not line or "INCOMPLETE" in line or "FAILED" in line:
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            ip = parts[0].strip()
            if ip.startswith("169.254") or ip.startswith("10."):
                continue  # 跳过 link-local 和 ZeroTier
            mac = ""
            state = parts[-1]
            for i, p in enumerate(parts):
                if p == "lladdr" and i + 1 < len(parts):
                    mac = parts[i + 1]
                    break
            if state in ("REACHABLE", "STALE", "DELAY", "PROBE", "PERMANENT"):
                found.append({"ip": ip, "mac": mac, "state": state})
    except Exception as e:
        log.warning("ARP 扫描失败: %s", e)
    return found


async def _fast_ping(host: str) -> bool:
    """单次快速 ping（0.5s 超时）。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", "1", "-n", host,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return await proc.wait() == 0
    except Exception:
        return False


async def _probe_device(host: str) -> list[int]:
    """探测设备开放端口（超时短，顺序探测）。"""
    open_ports = []
    for port in (80, 443, 22, 4321, 8765, 554, 8080, 8090, 1900, 1883, 8883):
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=0.5)
            open_ports.append(port)
            writer.close()
            await writer.wait_closed()
        except Exception:
            continue
    return open_ports


def _oui_vendor(mac: str) -> str:
    """通过 MAC OUI 识别常见厂商。"""
    if not mac or len(mac) < 8:
        return ""
    oui_map = {
        "60:01:94": "Sonoff",   "a4:c1:38": "Sonoff",
        "10:d5:6b": "Tuya",     "48:e1:e9": "Tuya",
        "d0:52:a8": "Tuya",     "00:1e:06": "Tuya",
        "54:2b:8d": "Tuya",     "68:57:2d": "Tuya",
        "50:c7:bf": "TP-Link",  "14:cf:92": "TP-Link",
        "d4:6e:0e": "TP-Link",  "bc:1c:81": "TP-Link",  # Archer series
        "48:22:54": "Xiaomi",   "f4:cf:a2": "Xiaomi",
        "9c:f4:8e": "Xiaomi",   "ac:bc:32": "Huawei",
        "b0:4e:26": "Huawei",   "38:f9:d3": "Huawei",
        "58:8a:5a": "Huawei",   "00:05:cd": "Hikvision",
        "b0:6c:bf": "Hikvision","1c:4a:aa": "Hikvision",
        "e0:98:61": "Hikvision","60:a3:e3": "Asus",
        "20:6b:e7": "Samsung",  "9c:47:82": "Raspberry Pi",
        "b8:27:eb": "Raspberry","dc:a6:32": "Raspberry",
        "ec:fa:bc": "Espressif","24:0a:c4": "Espressif",
        "80:2a:a8": "Xiaomi",   "f0:fe:6b": "Xiaomi",
        "00:2c:c8": "Apple",    "16:11:91": "Apple",
    }
    prefix = mac.upper()[:8]
    if prefix in oui_map:
        return oui_map[prefix]
    for key, val in oui_map.items():
        if key.upper().startswith(prefix[:5]):
            return val
    return ""


def _device_type(open_ports: list[int], vendor: str) -> str:
    """根据开放端口和厂商判断设备类型。"""
    port_set = set(open_ports)
    if 554 in port_set:
        return "摄像头"
    if 8090 in port_set or 1900 in port_set:
        return "影音设备"
    if vendor in ("Sonoff", "Espressif"):
        return "智能设备"
    if vendor == "Apple":
        return "Apple 设备"
    if vendor == "TP-Link" and 80 in port_set and 443 not in port_set:
        return "路由器/AP"
    if 4321 in port_set or 8765 in port_set:
        return "服务器"
    if 80 in port_set or 8080 in port_set:
        return "网页设备"
    return "通用设备"


# ── 主传感器 ─────────────────────────────────────

class HomeNetworkSensor(PerceptionAdapter):
    """家用网络设备感知传感器。"""

    def __init__(self, subnets: list[str] | None = None):
        env_subnets = os.environ.get("HOME_SUBNETS", "")
        if subnets:
            self._subnets = list(subnets)
        elif env_subnets:
            self._subnets = [s.strip() for s in env_subnets.split(",") if s.strip()]
        else:
            local = os.environ.get("HOME_SUBNET") or _get_local_subnet()
            self._subnets = [local]
            # 默认补充常见 IoT 子网
            iot = "192.168.1.0/24"
            if iot not in self._subnets:
                self._subnets.append(iot)
        self._device_states: dict[str, dict] = {}

        # 扫描完成标记
        self._initial_scan_done = False
        self._probe_done = set()     # 已探测端口的主机

    @property
    def name(self) -> str:
        return "home_network"

    async def start(self):
        """启动时快速扫描（ARP 缓存 + ping，秒级完成）。"""
        log.info("家用网络感知启动: 子网=%s", ", ".join(self._subnets))
        try:
            await self._discover()
        except Exception as e:
            log.warning("初始扫描出错: %s", e)

    async def stop(self):
        log.info("家用网络感知已停止")

    async def poll(self) -> list[Percept]:
        """每次 tick 采集设备状态。"""
        percepts: list[Percept] = []

        # 首次扫描只做 ARP + ping（快），后续探测端口（慢）
        if not self._initial_scan_done:
            self._initial_scan_done = True

        # 对所有已发现的设备做快速在线检查（每次 tick）
        changed = []
        for name, state in list(self._device_states.items()):
            host = state.get("host", "")
            if not host:
                continue
            old = state.get("online", False)
            now = await _fast_ping(host)
            state["online"] = now
            if now != old:
                state["changed_at"] = time.time()
                changed.append((name, old, now))

        # 后台探测端口（每次 tick 探测一个设备，避免卡住）
        unprobed = [n for n in self._device_states
                    if n not in self._probe_done]
        if unprobed:
            name = unprobed[0]
            state = self._device_states[name]
            host = state.get("host", "")
            if host:
                ports = await _probe_device(host)
                state["open_ports"] = ports
                state["type"] = _device_type(ports, state.get("vendor", ""))
                state["name"] = self._make_label(state)
                self._probe_done.add(name)
                log.info("设备端口探测: %s (%s) → %s", name, host, ports)

        # 生成状态变化 percept
        for name, old, now in changed:
            state = self._device_states[name]
            percepts.append(Percept(
                source="home_network",
                type="device.status_changed",
                data={
                    "device": state.get("label", name),
                    "host": state.get("host"),
                    "type": state.get("type", "unknown"),
                    "vendor": state.get("vendor", ""),
                    "online": now,
                    "previous": old,
                },
                confidence=0.9,
            ))
            log.info("设备变化: %s %s→%s", name,
                     "🟢" if now else "🔴", "在线" if now else "离线")

        # 定期（每 5 秒）输出一次设备快照
        if self._device_states:
            online = sum(1 for s in self._device_states.values() if s.get("online"))
            done = len(self._probe_done)
            total = len(self._device_states)
            # 只在新发现设备或状态变化时输出
            if percepts or not hasattr(self, "_last_count"):
                self._last_count = total
                percepts.append(Percept(
                    source="home_network",
                    type="network.snapshot",
                    data={
                        "total_devices": total,
                        "online": online,
                        "offline": total - online,
                        "probed": done,
                        "subnets": self._subnets,
                        "devices": {
                            name: {
                                "label": st.get("label", name),
                                "host": st["host"],
                                "type": st.get("type", "unknown"),
                                "vendor": st.get("vendor", ""),
                                "online": st.get("online", False),
                                "ports": st.get("open_ports", []),
                            }
                            for name, st in self._device_states.items()
                        },
                    },
                    confidence=0.8,
                ))

        return percepts

    async def _discover(self):
        """网络发现：ARP + ping 确认（多子网）。"""
        existing_hosts = lambda: {d["host"] for d in self._device_states.values()}

        for idx, subnet in enumerate(self._subnets):
            base = subnet.rsplit(".", 1)[0]

            # 首个子网：ARP 缓存快速发现
            if idx == 0:
                arp = await _arp_scan()
                log.info("ARP 发现 %d 台设备（子网 %s）", len(arp), subnet)
                for dev in arp:
                    if dev["ip"] not in existing_hosts():
                        await self._add_device(dev["ip"], dev["mac"])

            # 全子网 ping 扫描
            targets = [f"{base}.{i}" for i in range(1, 255)
                       if f"{base}.{i}" not in existing_hosts()]

            if not targets:
                continue

            results = await asyncio.gather(*[_fast_ping(h) for h in targets],
                                           return_exceptions=True)
            new_count = 0
            for host, ok in zip(targets, results):
                if ok is True and host not in existing_hosts():
                    await self._add_device(host, "")
                    new_count += 1
            log.info("子网 %s ping 扫描: +%d 台新设备", subnet, new_count)

        # 去重、重命名
        for name, state in self._device_states.items():
            state["label"] = self._make_label(state)

        log.info("初始发现完成: %d 设备在线",
                 sum(1 for s in self._device_states.values() if s.get("online")))

    async def _add_device(self, host: str, mac: str):
        """添加设备并做初步识别。"""
        vendor = _oui_vendor(mac)
        online = await _fast_ping(host)
        name = f"{host}"
        self._device_states[name] = {
            "host": host,
            "mac": mac,
            "vendor": vendor,
            "online": online,
            "type": "通用设备",
            "open_ports": [],
            "last_seen": time.time(),
        }

    def _make_label(self, state: dict) -> str:
        """生成可读的设备名称。"""
        parts = []
        if state.get("type") and state["type"] != "通用设备":
            parts.append(state["type"])
        if state.get("vendor"):
            parts.append(state["vendor"])
        host = state.get("host", "")
        mac = state.get("mac", "")
        if mac:
            parts.append(mac[-8:])
        else:
            parts.append(host)
        return " ".join(parts) if parts else host

    def get_device_states(self) -> dict:
        """获取当前设备状态（供 Web 面板使用）。"""
        return dict(self._device_states)
