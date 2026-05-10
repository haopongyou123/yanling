"""衍灵商业计划书图表生成."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
import numpy as np

# 注册本地下载的 Noto Sans SC 字体
_font_path = "/home/toto/.fonts/NotoSansSC-Regular.otf"
fm.fontManager.addfont(_font_path)
_font_prop = fm.FontProperties(fname=_font_path)
_font_name = _font_prop.get_name()

plt.rcParams["font.family"] = [_font_name, "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

OUT = "/home/toto/yanling/docs/assets"


def chart_architecture():
    """衍灵四阶段架构图"""
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4)
    ax.axis("off")

    stages = [
        (1, 1, "感知\nPerceive", "#4A90D9", "传感器/外部输入\n统一感知抽象"),
        (4, 1, "认知\nCognize", "#50C878", "规则匹配 / LLM 推理\n双模式决策引擎"),
        (7, 1, "行动\nAct", "#F5A623", "执行决策\n适配器调度"),
        (10, 1, "进化\nEvolve", "#E74C3C", "分析结果\n模式提取 + 策略调整"),
    ]
    for x, y, title, color, desc in stages:
        rect = mpatches.FancyBboxPatch((x, y), 2, 1.5, boxstyle="round,pad=0.1",
                                        facecolor=color, alpha=0.85, edgecolor="none")
        ax.add_patch(rect)
        ax.text(x + 1, y + 0.75, title, ha="center", va="center", fontsize=13,
                fontweight="bold", color="white")
        ax.text(x + 1, y - 0.3, desc, ha="center", va="top", fontsize=8, color="#666")

    # arrows
    for i in range(3):
        sx = stages[i][0] + 2
        ex = stages[i + 1][0]
        ax.annotate("", xy=(ex, 1.75), xytext=(sx, 1.75),
                    arrowprops=dict(arrowstyle="->", color="#333", lw=2))

    # bottom loop arrow
    ax.annotate("", xy=(3, 0.3), xytext=(10, 0.3),
                arrowprops=dict(arrowstyle="->", color="#999", lw=1, linestyle="dashed"))
    ax.text(6.5, 0.1, "循环迭代 (Tick)", ha="center", fontsize=9, color="#999")

    fig.savefig(f"{OUT}/architecture.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ architecture.png")


def chart_roadmap():
    """产品路线图"""
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 5)
    ax.axis("off")

    phases = [
        (0.5, 3.0, "内核成熟", "#4A90D9",
         "2026 Q2-Q3", ["四阶段循环", "双模式认知", "进化引擎", "Web 面板"]),
        (4.5, 3.0, "生态建设", "#50C878",
         "2026 Q3-Q4", ["适配器市场", "Docker 部署", "场景模板", "多节点同步"]),
        (8.5, 3.0, "商业化", "#F5A623",
         "2027", ["衍灵 Hub", "企业版", "经验市场", "移动端监控"]),
    ]
    for x, y, title, color, period, items in phases:
        rect = mpatches.FancyBboxPatch((x, y - 0.4), 3, 0.6, boxstyle="round,pad=0.05",
                                        facecolor=color, alpha=0.2, edgecolor=color, lw=2)
        ax.add_patch(rect)
        ax.text(x + 1.5, y - 0.1, f"{title} ({period})", ha="center", va="center",
                fontsize=11, fontweight="bold", color=color)
        for i, item in enumerate(items):
            ax.text(x + 0.2, y - 0.8 - i * 0.35, f"• {item}", fontsize=9, color="#444")

    # timeline
    ax.plot([0.5, 11.5], [2.3, 2.3], "k-", lw=2, color="#333")
    for x, label in [(0.5, "现在"), (4.5, "3个月"), (8.5, "6个月"), (11.5, "12个月")]:
        ax.plot([x, x], [2.1, 2.5], "k-", lw=1.5, color="#333")
        ax.text(x, 2.0, label, ha="center", fontsize=9, color="#666")

    fig.savefig(f"{OUT}/roadmap.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ roadmap.png")


def chart_competitive():
    """竞争定位图 - 气泡图"""
    fig, ax = plt.subplots(figsize=(10, 7))

    companies = {
        "衍灵":      (8, 9, 120, "#E74C3C", "嵌入式 AI 决策"),
        "LangChain":  (7, 5, 100, "#4A90D9", "LLM 框架"),
        "AutoGPT":   (6, 4, 80, "#50C878", "自主 Agent"),
        "Node-RED":  (3, 3, 70, "#F5A623", "可视化编排"),
        "Zabbix":    (2, 2, 60, "#9B59B6", "传统监控"),
        "Prometheus": (4, 2, 65, "#1ABC9C", "监控告警"),
    }

    for name, (x, y, s, color, cat) in companies.items():
        ax.scatter(x, y, s=s*15, c=color, alpha=0.6, edgecolors="white", linewidth=2)
        offset = 15 if name != "衍灵" else 20
        ax.annotate(name, (x, y), fontsize=11 if name == "衍灵" else 9,
                    fontweight="bold" if name == "衍灵" else "normal",
                    ha="center", va="center", color="white" if name == "衍灵" else "#333")

    ax.set_xlabel("产品成熟度 →", fontsize=11)
    ax.set_ylabel("AI 自主决策能力 →", fontsize=11)
    ax.set_title("竞争定位", fontsize=14, fontweight="bold", pad=15)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)

    fig.savefig(f"{OUT}/competitive.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ competitive.png")


def chart_revenue():
    """收入预测"""
    fig, ax = plt.subplots(figsize=(10, 5))

    months = np.arange(1, 25)
    # 假设: 社区免费 → 第6月起有企业版收入 → 第18月起SaaS
    community = np.zeros(24)
    enterprise = np.where(months >= 6, (months - 5) * 5000, 0)
    saas = np.where(months >= 18, (months - 17) * 8000, 0)
    custom = np.where(months >= 10, np.random.randint(30000, 80000, 24) * (months >= 10), 0)

    ax.stackplot(months, [community, enterprise, saas, custom],
                 labels=["社区版 (免费)", "企业版订阅", "SaaS 云服务", "定制项目"],
                 colors=["#ECF0F1", "#4A90D9", "#50C878", "#F5A623"], alpha=0.8)

    ax.set_xlabel("月份", fontsize=11)
    ax.set_ylabel("收入 (¥)", fontsize=11)
    ax.set_title("收入预测 (24个月)", fontsize=14, fontweight="bold")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_xlim(1, 24)
    ax.grid(True, alpha=0.3)

    # add total at month 24
    total = enterprise[-1] + saas[-1] + custom[-1]
    ax.annotate(f"第24月: ¥{total:,.0f}", xy=(24, total),
                fontsize=11, fontweight="bold", color="#333",
                ha="center", va="bottom")

    fig.savefig(f"{OUT}/revenue.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ revenue.png")


def chart_market():
    """市场规模"""
    fig, ax = plt.subplots(figsize=(8, 5))

    labels = ["IoT 设备管理", "AI 中台", "嵌入式 AI 决策"]
    values = [180, 200, 15]
    colors = ["#4A90D9", "#50C878", "#E74C3C"]

    bars = ax.barh(labels, values, color=colors, height=0.5, alpha=0.8)
    for bar, v in zip(bars, values):
        ax.text(bar.get_width() + 3, bar.get_y() + bar.get_height()/2,
                f"¥{v}亿", va="center", fontsize=11, fontweight="bold")

    ax.set_xlabel("市场规模 (亿元人民币)", fontsize=11)
    ax.set_title("目标市场规模", fontsize=14, fontweight="bold")
    ax.set_xlim(0, 260)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # annotation
    ax.annotate("衍灵切入点", xy=(15, 2), xytext=(80, 2.3),
                arrowprops=dict(arrowstyle="->", color="#E74C3C", lw=2),
                fontsize=10, color="#E74C3C", fontweight="bold")

    fig.savefig(f"{OUT}/market.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ market.png")


def chart_evolution():
    """进化引擎工作流"""
    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.5)
    ax.axis("off")

    boxes = [
        (0.3, 1.2, "每次 Tick\n轻量学习", "#4A90D9",
         "性能追踪 → 失败分析\n→ 模式提取 → 记忆写入"),
        (3.5, 1.2, "趋势恶化\n自动触发", "#F5A623",
         "成功率下降 >10%\n自动唤醒深度进化"),
        (6.7, 1.2, "深度进化\nLLM 分析", "#E74C3C",
         "分析模式 → 生成策略\n→ 应用调整 → 记录快照"),
    ]
    for x, y, title, color, desc in boxes:
        rect = mpatches.FancyBboxPatch((x, y), 2.5, 1.3, boxstyle="round,pad=0.1",
                                        facecolor=color, alpha=0.85, edgecolor="none")
        ax.add_patch(rect)
        ax.text(x + 1.25, y + 0.65, title, ha="center", va="center",
                fontsize=10, fontweight="bold", color="white")
        ax.text(x + 1.25, y - 0.15, desc, ha="center", va="top", fontsize=7.5, color="#666")

    for i in range(2):
        sx = boxes[i][0] + 2.5
        ex = boxes[i + 1][0]
        ax.annotate("", xy=(ex, 1.85), xytext=(sx, 1.85),
                    arrowprops=dict(arrowstyle="->", color="#333", lw=2))

    # rollback arrow
    ax.annotate("回滚", xy=(7, 0.3), xytext=(7, 0.9),
                arrowprops=dict(arrowstyle="->", color="#999", lw=1, linestyle="dashed"))
    ax.text(7.3, 0.6, "调整失败 → 自动回滚快照", fontsize=7.5, color="#999")

    fig.savefig(f"{OUT}/evolution_flow.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ evolution_flow.png")


def chart_biz_model():
    """商业模式对比"""
    fig, ax = plt.subplots(figsize=(8, 4.5))

    tiers = ["社区版\n(开源免费)", "企业版\n(订阅)", "Hub 云服务\n(SaaS)", "定制方案\n(项目)"]
    prices = [0, 10000, 12000, 100000]
    labels_full = [
        "核心功能开放\n社区支持",
        "私有化部署\nSLA 保障\n专属适配器",
        "多节点管理\n经验市场\n实时监控",
        "全定制开发\n专属进化策略\n驻场支持",
    ]
    colors = ["#ECF0F1", "#4A90D9", "#50C878", "#F5A623"]

    for i, (tier, price, desc, color) in enumerate(zip(tiers, prices, labels_full, colors)):
        ax.bar(i, price if price > 0 else 0.5, width=0.5, color=color, alpha=0.8, edgecolor="white")
        ax.text(i, price + 2000 if price > 0 else 5000, f"¥{price:,}/年" if price > 0 else "免费",
                ha="center", fontsize=10, fontweight="bold")
        ax.text(i, -8000, tier, ha="center", fontsize=9, fontweight="bold")
        ax.text(i, -15000, desc, ha="center", fontsize=7.5, color="#666")

    ax.set_ylim(-20000, 120000)
    ax.set_xticks([])
    ax.set_title("商业模式 — 四层定价体系", fontsize=13, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.set_yticks([])

    fig.savefig(f"{OUT}/biz_model.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ biz_model.png")


def chart_memory():
    """记忆系统架构"""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 4)
    ax.axis("off")

    layers = [
        (1, 2.5, "工作记忆\nWorking Memory", "#4A90D9", "当前 Tick 快照\n容量有限，随 Tick 滚动"),
        (1, 1.3, "短期记忆\nShort-Term", "#50C878", "最近 N 条记录\nTTL 过期淘汰"),
        (1, 0.1, "长期记忆\nLong-Term", "#F5A623", "重要经验/失败模式\nJSON/Supabase 持久化"),
    ]
    for x, y, title, color, desc in layers:
        rect = mpatches.FancyBboxPatch((x, y), 3, 0.9, boxstyle="round,pad=0.1",
                                        facecolor=color, alpha=0.2, edgecolor=color, lw=2)
        ax.add_patch(rect)
        ax.text(x + 0.2, y + 0.45, title, va="center", fontsize=10, fontweight="bold", color=color)
        ax.text(x + 3.3, y + 0.45, desc, va="center", fontsize=8, color="#666")

    # arrows between layers
    for y in [2.3, 1.1]:
        ax.annotate("", xy=(2.5, y), xytext=(2.5, y + 0.4),
                    arrowprops=dict(arrowstyle="->", color="#999", lw=1))

    # side note
    ax.text(5.5, 2.0, "进化记忆\n(策略变更历史)", fontsize=9,
            bbox=dict(boxstyle="round", facecolor="#E74C3C", alpha=0.1))

    fig.savefig(f"{OUT}/memory_arch.png", dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  ✓ memory_arch.png")


if __name__ == "__main__":
    print("生成衍灵商业计划书图表...")
    chart_architecture()
    chart_roadmap()
    chart_competitive()
    chart_revenue()
    chart_market()
    chart_evolution()
    chart_biz_model()
    chart_memory()
    print(f"\n全部图表已保存到 {OUT}/")
