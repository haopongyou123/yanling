"""衍灵产品介绍动画 — 场景驱动版."""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from animation import SlideDeck, TitleScene, ImageScene, NoImageScene

ASSETS = "/home/toto/yanling/docs/assets"

def audio(path: str) -> str:
    return f"{ASSETS}/{path}"

# 语音时间映射 — 与幻灯片时长对齐 (秒 → 文件路径)
AUDIO_MAP: dict[float, str | None] = {
    0:   audio("narration_opening.mp3"),
    10:  audio("narration_pain.mp3"),
    26:  audio("narration_iot.mp3"),
    53:  audio("narration_enterprise.mp3"),
    77:  audio("narration_smarthome.mp3"),
    97:  audio("narration_agriculture.mp3"),
    114: audio("narration_howitworks.mp3"),
    136: audio("narration_architecture.mp3"),
    156: audio("narration_roadmap.mp3"),
    171: audio("narration_closing.mp3"),
}

AUDIO_MAP_FINAL: dict[float, str] = {k: v for k, v in AUDIO_MAP.items() if v}


def build_deck() -> SlideDeck:
    deck = SlideDeck()

    # 1. 封面 (10s)
    deck.add(TitleScene("衍灵", "通用 AI 自我进化系统内核", 10.0))

    # 2. 痛点：传统系统的局限 (16s)
    deck.add(ImageScene(f"{ASSETS}/scene_pain.png",
                        "痛点：被动系统的困境",
                        "传统系统等人来管 → 衍灵主动感知·决策·进化",
                        16.0, zoom_start=1.0, zoom_end=1.05))

    # 3. 场景A：IoT 边缘运维 (27s)
    deck.add(ImageScene(f"{ASSETS}/scene_iot.png",
                        "场景一：IoT 边缘设备自主运维",
                        "生产线 · 远程机房 · 城市物联网终端",
                        27.0, zoom_start=1.0, zoom_end=1.04))

    # 4. 场景B：企业管理自动化 (24s)
    deck.add(ImageScene(f"{ASSETS}/scene_enterprise.png",
                        "场景二：企业管理流程自动化",
                        "采购审批 · 工单分派 · 库存预警 · 合规检查",
                        24.0, zoom_start=1.0, zoom_end=1.04))

    # 5. 场景C：智能家居编排 (20s)
    deck.add(ImageScene(f"{ASSETS}/scene_smarthome.png",
                        "场景三：智能家居自适应编排",
                        "到家自动调光调温 · 持续学习你的习惯",
                        20.0, zoom_start=1.0, zoom_end=1.04))

    # 6. 场景D：农业养殖调控 (17s)
    deck.add(ImageScene(f"{ASSETS}/scene_agriculture.png",
                        "场景四：农业养殖环境智能调控",
                        "温室 · 养殖场 · 鱼塘 · 农田 — 边缘侧实时决策",
                        17.0, zoom_start=1.0, zoom_end=1.04))

    # 7. 四阶段循环：如何工作 (22s)
    deck.add(ImageScene(f"{ASSETS}/scene_cycle.png",
                        "如何工作：四阶段循环",
                        "感知 → 认知 → 行动 → 进化",
                        22.0, zoom_start=1.0, zoom_end=1.03))

    # 8. 技术架构：可嵌入设计 (20s)
    deck.add(ImageScene(f"{ASSETS}/scene_architecture.png",
                        "技术架构：可嵌入·可扩展",
                        "作为库 import · 或独立进程运行",
                        20.0, zoom_start=1.0, zoom_end=1.03))

    # 9. 路线图 (15s)
    deck.add(ImageScene(f"{ASSETS}/roadmap.png",
                        "路线图",
                        "v0.1 开源 → 插件生态 → 企业版 → 多节点集群",
                        15.0, zoom_start=1.0, zoom_end=1.05))

    # 10. 结尾 (14s)
    deck.add(TitleScene("衍灵", "让系统拥有生命", 14.0))

    return deck


def main():
    print("=== 衍灵产品介绍动画 (场景驱动版) ===")
    deck = build_deck()

    video_raw = "/tmp/yanling_video_raw.mp4"
    print("\n开始渲染动画...")
    deck.render(video_raw)

    print("\n混入语音解说...")
    output = deck.add_audio(video_raw, AUDIO_MAP_FINAL)

    mb = os.path.getsize(output) / 1024 / 1024
    import subprocess, json
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", output],
        capture_output=True, text=True)
    total = json.loads(dur.stdout)["format"]["duration"]

    print(f"\n  ✓ {output}")
    print(f"    时长: {float(total):.0f}s")
    print(f"    大小: {mb:.1f}MB")
    os.unlink(video_raw)


if __name__ == "__main__":
    import subprocess
    main()
