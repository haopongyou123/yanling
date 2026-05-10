"""真实系统监控传感器 — 使用 psutil 采集本机指标."""
from __future__ import annotations

import logging
import time

import psutil

from yanling.core.types import Percept
from yanling.kernel.perception import PerceptionAdapter

log = logging.getLogger("yanling.scenario.embedded.real_sensor")


class SystemMonitorSensor(PerceptionAdapter):
    """系统监控传感器 — 采集 CPU/内存/磁盘/网络/进程数据。"""

    def __init__(self, disk_paths: list[str] | None = None):
        self._count = 0
        self._disk_paths = disk_paths or ["/", "/home"]
        self._prev_net = psutil.net_io_counters()
        self._prev_time = time.time()

    @property
    def name(self) -> str:
        return "system_monitor"

    async def poll(self) -> list[Percept]:
        self._count += 1
        percepts: list[Percept] = []
        now = time.time()

        # ─── CPU ───
        cpu_percent = psutil.cpu_percent(interval=0)
        cpu_per_core = psutil.cpu_percent(interval=0, percpu=True)
        load_1, load_5, load_15 = psutil.getloadavg()
        cpu_count = psutil.cpu_count()
        cpu_status = "normal"
        if cpu_percent > 90:
            cpu_status = "critical"
        elif cpu_percent > 75:
            cpu_status = "warning"

        percepts.append(Percept(
            source="system.cpu",
            type=f"cpu.{cpu_status}",
            data={
                "percent": cpu_percent,
                "per_core": cpu_per_core,
                "load_1m": round(load_1, 2),
                "load_5m": round(load_5, 2),
                "load_15m": round(load_15, 2),
                "core_count": cpu_count,
                "alert": cpu_status,
                "timestamp": now,
            },
        ))

        # ─── 内存 ───
        mem = psutil.virtual_memory()
        mem_status = "normal"
        if mem.percent > 90:
            mem_status = "critical"
        elif mem.percent > 80:
            mem_status = "warning"

        percepts.append(Percept(
            source="system.memory",
            type=f"memory.{mem_status}",
            data={
                "total_gb": round(mem.total / 1024**3, 1),
                "available_gb": round(mem.available / 1024**3, 1),
                "percent": mem.percent,
                "used_gb": round(mem.used / 1024**3, 1),
                "alert": mem_status,
                "timestamp": now,
            },
        ))

        # ─── 交换 ───
        swap = psutil.swap_memory()
        if swap.total > 0:
            swap_status = "normal"
            if swap.percent > 50:
                swap_status = "warning"
            percepts.append(Percept(
                source="system.swap",
                type=f"swap.{swap_status}",
                data={
                    "total_gb": round(swap.total / 1024**3, 1),
                    "percent": swap.percent,
                    "alert": swap_status,
                    "timestamp": now,
                },
            ))

        # ─── 磁盘 ───
        for path in self._disk_paths:
            try:
                disk = psutil.disk_usage(path)
                disk_status = "normal"
                if disk.percent > 92:
                    disk_status = "critical"
                elif disk.percent > 80:
                    disk_status = "warning"

                percepts.append(Percept(
                    source=f"system.disk.{path}",
                    type=f"disk.{disk_status}",
                    data={
                        "mount": path,
                        "total_gb": round(disk.total / 1024**3, 1),
                        "used_gb": round(disk.used / 1024**3, 1),
                        "free_gb": round(disk.free / 1024**3, 1),
                        "percent": disk.percent,
                        "alert": disk_status,
                        "timestamp": now,
                    },
                ))
            except PermissionError:
                pass

        # ─── 进程 ───
        try:
            proc_count = len(psutil.pids())
            zombie_count = 0
            for proc in psutil.process_iter(['status']):
                try:
                    if proc.info['status'] == psutil.STATUS_ZOMBIE:
                        zombie_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            proc_status = "normal"
            if zombie_count > 5:
                proc_status = "critical"
            elif zombie_count > 2:
                proc_status = "warning"

            percepts.append(Percept(
                source="system.process",
                type=f"process.{proc_status}",
                data={
                    "total": proc_count,
                    "zombie": zombie_count,
                    "alert": proc_status,
                    "timestamp": now,
                },
            ))
        except Exception as e:
            log.warning("进程扫描失败: %s", e)

        # ─── 网络 I/O 速率 ───
        try:
            net = psutil.net_io_counters()
            dt = now - self._prev_time
            if dt > 0:
                rx_mbps = (net.bytes_recv - self._prev_net.bytes_recv) / dt / 1024 / 1024
                tx_mbps = (net.bytes_sent - self._prev_net.bytes_sent) / dt / 1024 / 1024
                percepts.append(Percept(
                    source="system.network",
                    type="network.normal",
                    data={
                        "rx_mbps": round(rx_mbps, 3),
                        "tx_mbps": round(tx_mbps, 3),
                        "timestamp": now,
                    },
                ))
                self._prev_net = net
                self._prev_time = now
        except Exception as e:
            log.warning("网络统计失败: %s", e)

        return percepts
