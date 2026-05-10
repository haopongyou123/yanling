"""生成衍灵场景驱动版配图 — matplotlib."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

OUT = Path("/home/toto/yanling/docs/assets")
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Noto Sans SC", "WenQuanYi Micro Hei", "DejaVu Sans"],
    "font.size": 20,
    "figure.facecolor": "#1a1a2e",
    "axes.facecolor": "#1a1a2e",
    "text.color": "#e0e0e0",
    "axes.edgecolor": "#334",
    "axes.labelcolor": "#e0e0e0",
    "xtick.color": "#889",
    "ytick.color": "#889",
})


# ─── 1. 痛点：被动 vs 主动 ───────────────────────────────

def draw_pain():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(19.2, 10.8))
    fig.subplots_adjust(wspace=0.3)

    # 左侧：传统被动系统
    ax1.set_xlim(0, 10)
    ax1.set_ylim(0, 10)
    ax1.set_aspect("equal")
    ax1.axis("off")
    ax1.set_title("传统系统：等人来管", fontsize=32, fontweight="bold", color="#f04747", pad=20)

    boxes = [
        (1, 7, "服务器\n告警", "#5a3e3e"),
        (1, 4, "审批流\n人工", "#5a3e3e"),
        (4, 7, "设备\n巡检", "#5a3e3e"),
        (4, 4, "库存\n盘点", "#5a3e3e"),
    ]
    for x, y, label, color in boxes:
        rect = mpatches.FancyBboxPatch((x, y), 4, 2.2, boxstyle="round,pad=0.1",
                                        facecolor=color, edgecolor="#f04747", linewidth=2)
        ax1.add_patch(rect)
        ax1.text(x+2, y+1.1, label, ha="center", va="center", fontsize=18, color="#ccc")

    # 人在中间
    ax1.text(5, 1.5, "·运维人员·", ha="center", fontsize=22, color="#f0c040")
    # 箭头
    ax1.annotate("", xy=(5, 2.5), xytext=(5, 3.8),
                 arrowprops=dict(arrowstyle="->", color="#f04747", lw=3))
    ax1.text(5, 3.0, "被动响应", ha="center", fontsize=14, color="#f04747")

    # 右侧：衍灵主动
    ax2.set_xlim(0, 10)
    ax2.set_ylim(0, 10)
    ax2.set_aspect("equal")
    ax2.axis("off")
    ax2.set_title("衍灵：自动感知·决策·进化", fontsize=32, fontweight="bold", color="#47b8f0", pad=20)

    items = [
        (1, 7, "感知", "#1a4a6e"),
        (1, 4, "决策", "#1a6e4a"),
        (4, 7, "行动", "#6e4a1a"),
        (4, 4, "进化", "#4a1a6e"),
    ]
    for x, y, label, color in items:
        rect = mpatches.FancyBboxPatch((x, y), 4, 2.2, boxstyle="round,pad=0.1",
                                        facecolor=color, edgecolor="#47b8f0", linewidth=2)
        ax2.add_patch(rect)
        ax2.text(x+2, y+1.1, label, ha="center", va="center", fontsize=20, color="#fff", fontweight="bold")

    # 循环箭头
    for (x1, y1), (x2, y2) in [((5, 6.8), (5, 5.8)), ((5, 4.2), (5, 3.2))]:
        ax2.annotate("", xy=(x2, y2), xytext=(x1, y1),
                     arrowprops=dict(arrowstyle="->", color="#47b8f0", lw=2))

    ax2.text(5, 1.5, "7×24 自主运行", ha="center", fontsize=22, color="#4ae04a")

    fig.savefig(OUT / "scene_pain.png", dpi=100)
    plt.close(fig)
    print("  ✓ scene_pain.png")


# ─── 2. IoT 边缘设备运维 ───────────────────────────────

def draw_iot():
    fig, ax = plt.subplots(figsize=(19.2, 10.8))
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 10)
    ax.axis("off")

    # 标题
    ax.text(10, 9.2, "IoT 边缘设备自主运维", fontsize=36, fontweight="bold",
            ha="center", color="#ffa94d")

    # 边缘设备集群
    devices = [
        (1, 5, "生产线\n传感器", "#2a4a6e"),
        (1, 2, "远程机房\n服务器", "#2a4a6e"),
        (4, 5, "环境\n监测器", "#2a4a6e"),
        (4, 2, "能源\n计量表", "#2a4a6e"),
        (7, 5, "城市\n摄像头", "#2a4a6e"),
        (7, 2, "交通\n传感器", "#2a4a6e"),
    ]
    for x, y, label, color in devices:
        rect = mpatches.FancyBboxPatch((x, y), 2.5, 2, boxstyle="round,pad=0.1",
                                        facecolor=color, edgecolor="#5a8ac0", linewidth=2)
        ax.add_patch(rect)
        ax.text(x+1.25, y+1, label, ha="center", va="center", fontsize=13, color="#ddd")

    # 中部：衍灵引擎
    eng = mpatches.FancyBboxPatch((10.5, 3.5), 4, 3, boxstyle="round,pad=0.2",
                                   facecolor="#1a3a5e", edgecolor="#ffa94d", linewidth=3)
    ax.add_patch(eng)
    ax.text(12.5, 5.5, "衍灵引擎", ha="center", fontsize=28, fontweight="bold", color="#ffa94d")
    ax.text(12.5, 4.3, "感知 → 认知 → 行动 → 进化", ha="center", fontsize=14, color="#aaa")

    # 箭头从设备到引擎
    for x, y, _, _ in devices:
        ax.annotate("", xy=(10.5, y+1), xytext=(x+2.5, y+1),
                     arrowprops=dict(arrowstyle="->", color="#5a8ac0", lw=1.5))

    # 右侧：自动操作
    ops = [
        (16, 6, "自动\n诊断", "#3a5e1a"),
        (16, 3.5, "自动\n清理", "#3a5e1a"),
        (16, 1, "自动\n切换", "#3a5e1a"),
    ]
    for x, y, label, color in ops:
        rect = mpatches.FancyBboxPatch((x, y), 2.5, 2, boxstyle="round,pad=0.1",
                                        facecolor=color, edgecolor="#6aaa3a", linewidth=2)
        ax.add_patch(rect)
        ax.text(x+1.25, y+1, label, ha="center", va="center", fontsize=16, color="#fff", fontweight="bold")

    # 箭头从引擎到操作
    for x, y, _, _ in ops:
        ax.annotate("", xy=(x, y+1), xytext=(14.5, y+1),
                     arrowprops=dict(arrowstyle="->", color="#6aaa3a", lw=1.5))

    fig.savefig(OUT / "scene_iot.png", dpi=100)
    plt.close(fig)
    print("  ✓ scene_iot.png")


# ─── 3. 企业管理自动化 ───────────────────────────────

def draw_enterprise():
    fig, ax = plt.subplots(figsize=(19.2, 10.8))
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(10, 9.2, "企业管理流程自动化", fontsize=36, fontweight="bold",
            ha="center", color="#4ae0c0")

    # 四个管理模块（上方）
    modules = [
        (0.5, 6, "采购审批", "#2a5e5e"),
        (5, 6, "工单分派", "#2a5e5e"),
        (9.5, 6, "库存预警", "#2a5e5e"),
        (14, 6, "合规检查", "#2a5e5e"),
    ]
    for x, y, label, color in modules:
        rect = mpatches.FancyBboxPatch((x, y), 4, 2.5, boxstyle="round,pad=0.1",
                                        facecolor=color, edgecolor="#4ae0c0", linewidth=2)
        ax.add_patch(rect)
        ax.text(x+2, y+1.25, label, ha="center", va="center", fontsize=20, color="#fff", fontweight="bold")

    # 衍灵决策引擎（中央）
    eng = mpatches.FancyBboxPatch((5.5, 2), 9, 2.5, boxstyle="round,pad=0.15",
                                   facecolor="#1a3a3a", edgecolor="#4ae0c0", linewidth=3)
    ax.add_patch(eng)
    ax.text(10, 3.75, "衍灵决策引擎", ha="center", fontsize=26, fontweight="bold", color="#4ae0c0")
    ax.text(10, 2.6, "7×24 自动处理常规决策 · 异常升级人工", ha="center", fontsize=14, color="#aaa")

    # 箭头：模块 → 引擎
    for x, y, _, _ in modules:
        ax.annotate("", xy=(x+2, y), xytext=(x+2, 4.5),
                     arrowprops=dict(arrowstyle="->", color="#4ae0c0", lw=1.5))

    # 底部：人工兜底
    rect = mpatches.FancyBboxPatch((6.5, 0.3), 7, 1.2, boxstyle="round,pad=0.1",
                                    facecolor="#5e3a2a", edgecolor="#f0c040", linewidth=2)
    ax.add_patch(rect)
    ax.text(10, 0.9, "·异常升级· → 人工处理（边界控制保障）", ha="center", fontsize=16, color="#f0c040")

    ax.annotate("", xy=(10, 2), xytext=(10, 1.5),
                 arrowprops=dict(arrowstyle="->", color="#f0c040", lw=2))

    fig.savefig(OUT / "scene_enterprise.png", dpi=100)
    plt.close(fig)
    print("  ✓ scene_enterprise.png")


# ─── 4. 智能家居 ───────────────────────────────

def draw_smarthome():
    fig, ax = plt.subplots(figsize=(19.2, 10.8))
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(10, 9.2, "智能家居自适应编排", fontsize=36, fontweight="bold",
            ha="center", color="#f0a0ff")

    # 家居场景
    rooms = [
        (0.5, 5, "·客厅·\n灯光·温度·音乐", "#4a2a5e"),
        (7, 5, "·卧室·\n窗帘·安防", "#4a2a5e"),
        (13.5, 5, "·入口·\n门锁·摄像头", "#4a2a5e"),
        (7, 1.5, "·厨房·\n烟感·燃气", "#4a2a5e"),
    ]
    for x, y, label, color in rooms:
        rect = mpatches.FancyBboxPatch((x, y), 5, 3, boxstyle="round,pad=0.1",
                                        facecolor=color, edgecolor="#d080f0", linewidth=2)
        ax.add_patch(rect)
        ax.text(x+2.5, y+1.5, label, ha="center", va="center", fontsize=18, color="#eee")

    # 中央衍灵
    eng = mpatches.FancyBboxPatch((6.5, 0.2), 7, 0.8, boxstyle="round,pad=0.05",
                                   facecolor="#2a1a3a", edgecolor="#f0a0ff", linewidth=2)
    ax.add_patch(eng)
    ax.text(10, 0.6, "衍灵：学习你的习惯 · 持续进化", ha="center", fontsize=16, color="#f0a0ff")

    fig.savefig(OUT / "scene_smarthome.png", dpi=100)
    plt.close(fig)
    print("  ✓ scene_smarthome.png")


# ─── 5. 农业养殖 ───────────────────────────────

def draw_agriculture():
    fig, ax = plt.subplots(figsize=(19.2, 10.8))
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(10, 9.2, "农业养殖环境智能调控", fontsize=36, fontweight="bold",
            ha="center", color="#6ae06a")

    # 四个监测场景
    scenes = [
        (0.5, 5, "·温室·\n温湿度控制", "#1a5e1a"),
        (5.5, 5, "·养殖场·\n气体浓度监测", "#1a5e1a"),
        (10.5, 5, "·鱼塘·\n溶氧量监测", "#1a5e1a"),
        (15.5, 5, "·农田·\n土壤湿度", "#1a5e1a"),
    ]
    for x, y, label, color in scenes:
        rect = mpatches.FancyBboxPatch((x, y), 3.5, 3, boxstyle="round,pad=0.1",
                                        facecolor=color, edgecolor="#6ae06a", linewidth=2)
        ax.add_patch(rect)
        ax.text(x+1.75, y+1.5, label, ha="center", va="center", fontsize=16, color="#ddd")

    # 衍灵边缘决策
    eng = mpatches.FancyBboxPatch((4, 1), 12, 2.5, boxstyle="round,pad=0.15",
                                   facecolor="#1a3a1a", edgecolor="#6ae06a", linewidth=3)
    ax.add_patch(eng)
    ax.text(10, 2.8, "衍灵边缘决策引擎", ha="center", fontsize=26, fontweight="bold", color="#6ae06a")
    ax.text(10, 1.6, "实时采集 → 边缘推理 → 自动调控（断网也可自主运行）", ha="center", fontsize=15, color="#aaa")

    fig.savefig(OUT / "scene_agriculture.png", dpi=100)
    plt.close(fig)
    print("  ✓ scene_agriculture.png")


# ─── 6. 四阶段循环 ───────────────────────────────

def draw_cycle():
    fig, ax = plt.subplots(figsize=(19.2, 10.8))
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(10, 9.2, "衍灵四阶段循环", fontsize=36, fontweight="bold",
            ha="center", color="#80d0ff")

    # 四个阶段 (顺时针)
    stages = [
        (1, 3, "感知\nPerception", "#1a4a6e",
         "传感器 · API · 定时器\n消息队列 · 文件变化"),
        (11, 3, "认知\nCognition", "#4a1a6e",
         "LLM 推理 / 规则匹配\n上下文融合 · 决策规划"),
        (11, 6.5, "行动\nAction", "#6e4a1a",
         "API 调用 · 设备控制\n通知 · 数据写入"),
        (1, 6.5, "进化\nEvolution", "#1a6e4a",
         "轻量学习 · 模式提取\n深度进化 · 策略调整"),
    ]
    for x, y, title, color, desc in stages:
        rect = mpatches.FancyBboxPatch((x, y), 8, 2.5, boxstyle="round,pad=0.1",
                                        facecolor=color, edgecolor="#80d0ff", linewidth=2)
        ax.add_patch(rect)
        ax.text(x+4, y+1.8, title, ha="center", va="center", fontsize=22, color="#fff", fontweight="bold")
        ax.text(x+4, y+0.7, desc, ha="center", va="center", fontsize=13, color="#bbd")

    # 循环箭头
    for start, end, label in [
        ((9, 4.25), (11, 4.25), ""),
        ((15, 5.9), (15, 6.5), ""),
        ((9, 7.75), (7, 7.75), ""),
        ((5, 5.9), (5, 5.5), ""),
    ]:
        ax.annotate("", xy=end, xytext=start,
                     arrowprops=dict(arrowstyle="->", color="#80d0ff", lw=3))

    # 双模式标签
    ax.text(10, 0.5, "LLM 驱动模式 · 规则驱动模式 · 可嵌入任何系统",
            ha="center", fontsize=16, color="#889")

    fig.savefig(OUT / "scene_cycle.png", dpi=100)
    plt.close(fig)
    print("  ✓ scene_cycle.png")


# ─── 7. 技术架构 ───────────────────────────────

def draw_architecture():
    fig, ax = plt.subplots(figsize=(19.2, 10.8))
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(10, 9.3, "可嵌入 · 可扩展 · 安全可控", fontsize=30, fontweight="bold",
            ha="center", color="#f0c040")

    # 三层
    layers = [
        (1, 7, "你的应用系统", "#3a5e8a", 18, 2.5,
         "Web 应用 · 工业控制 · 移动端 · 边缘设备"),
        (1, 3.5, "衍灵内核", "#1a3a5e", 18, 3,
         "感知 → 认知 → 行动 → 进化\n记忆系统 · 边界控制 · 事件总线"),
        (1, 0.3, "基础设施", "#2a4a3a", 18, 2,
         "本地服务器 · 边缘网关 · 云端"),
    ]
    for x, y, title, color, w, h, desc in layers:
        rect = mpatches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.15",
                                        facecolor=color, edgecolor="#f0c040", linewidth=2)
        ax.add_patch(rect)
        ax.text(x+w/2, y+h-0.8, title, ha="center", va="center", fontsize=22, color="#fff", fontweight="bold")
        ax.text(x+w/2, y+h/2-0.3, desc, ha="center", va="center", fontsize=13, color="#bbb")

    # 嵌入方式
    ax.annotate("", xy=(11, 7), xytext=(11, 6),
                 arrowprops=dict(arrowstyle="<->", color="#f0c040", lw=2))
    ax.text(14, 6.5, "作为 Python 库 import 或\n独立进程通过 API 通信",
            fontsize=14, color="#aaa", va="center")

    fig.savefig(OUT / "scene_architecture.png", dpi=100)
    plt.close(fig)
    print("  ✓ scene_architecture.png")


if __name__ == "__main__":
    print("生成场景配图...")
    draw_pain()
    draw_iot()
    draw_enterprise()
    draw_smarthome()
    draw_agriculture()
    draw_cycle()
    draw_architecture()
    print(f"\n全部配图已保存到 {OUT}/")
