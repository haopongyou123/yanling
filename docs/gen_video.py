"""生成衍灵产品介绍视频 — ffmpeg 合成图表+语音."""
from __future__ import annotations

import json
import os
import subprocess

ASSETS = "/home/toto/yanling/docs/assets"
OUT = "/home/toto/yanling/docs/衍灵产品介绍.mp4"
TMP = "/tmp/yanling_video"
os.makedirs(TMP, exist_ok=True)

FONT = "/home/toto/.fonts/NotoSansSC-Regular.otf"

SLIDES = [
    (None,       "narration_opening.mp3",    "衍灵",         "通用 AI 自我进化系统内核"),
    ("architecture.png", "narration_summary.mp3",  "执行摘要",     "7×24 感知→决策→行动→自我改进"),
    ("memory_arch.png",  "narration_product.mp3",  "核心能力矩阵", "感知·认知·记忆·进化·边界控制·可观测"),
    ("market.png",       "narration_market.mp3",   "目标市场",     "IoT边缘设备·企业管理·智能家居"),
    ("competitive.png",  "narration_competition.mp3", "竞争定位",  "嵌入式 AI 决策引擎"),
    ("evolution_flow.png", "narration_evolution.mp3", "进化引擎", "轻量学习 + 深度进化"),
    ("biz_model.png",    "narration_bizmodel.mp3", "商业模式",     "社区版·企业版·Hub云服务·定制"),
    ("revenue.png",      None,                     "收入预测",     "24个月增长路径"),
    ("roadmap.png",      "narration_roadmap.mp3",  "技术路线图",   "内核成熟→生态建设→商业化"),
    ("evolution_flow.png", "narration_risk.mp3",   "风险与对策",   "边界控制·本地推理·开源优先"),
    (None,               "narration_action.mp3",   "行动计划",     "打通园丁→场景模板→v0.1发布→首个客户"),
]


def get_duration(mp3: str) -> float:
    if not mp3 or not os.path.exists(mp3):
        return 4.0
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "json", mp3], capture_output=True, text=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def seg_image(idx: int, img: str, audio: str | None, title: str, subtitle: str) -> str:
    """图片页视频片段."""
    out = f"{TMP}/seg_{idx:02d}.ts"
    dur = get_duration(f"{ASSETS}/{audio}") if audio else 4.0
    img_path = f"{ASSETS}/{img}"
    audio_path = f"{ASSETS}/{audio}" if audio else None

    filter_str = (
        f"scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
        f"drawtext=text='{title}':fontcolor=white:fontsize=36"
        f":x=80:y=h-80:fontfile={FONT}:shadowcolor=black:shadowx=2:shadowy=2,"
        f"drawtext=text='{subtitle}':fontcolor=#aaaacc:fontsize=20"
        f":x=80:y=h-40:fontfile={FONT}:shadowcolor=black:shadowx=2:shadowy=2"
    )

    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", img_path]
    if audio_path:
        cmd += ["-i", audio_path]
    cmd += [
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
    ]
    if audio_path:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    else:
        cmd += ["-t", str(dur)]
    cmd += ["-f", "mpegts", out]

    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out


def seg_title(idx: int, audio: str, title: str, subtitle: str) -> str:
    """标题页视频片段."""
    out = f"{TMP}/seg_{idx:02d}.ts"
    dur = get_duration(f"{ASSETS}/{audio}")
    audio_path = f"{ASSETS}/{audio}"

    filter_str = (
        f"drawtext=text='{title}':fontcolor=white:fontsize=72"
        f":x=(w-text_w)/2:y=(h-text_h)/2-40"
        f":fontfile={FONT}:shadowcolor=black:shadowx=2:shadowy=2,"
        f"drawtext=text='{subtitle}':fontcolor=#8888cc:fontsize=28"
        f":x=(w-text_w)/2:y=(h+text_h)/2+20"
        f":fontfile={FONT}:shadowcolor=black:shadowx=2:shadowy=2"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=#0a0a1a:s=1920x1080:d={dur}:r=30",
        "-i", audio_path,
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-f", "mpegts", out,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out


def main():
    print("生成衍灵产品介绍视频...\n")
    segments = []

    for idx, (img, audio, title, subtitle) in enumerate(SLIDES):
        if img:
            seg = seg_image(idx, img, audio, title, subtitle)
        else:
            seg = seg_title(idx, audio, title, subtitle)
        segments.append(seg)
        print(f"  [{idx+1}/11] {title}")

    print("\n  拼接最终视频...")
    concat = f"{TMP}/concat.txt"
    with open(concat, "w") as f:
        for s in segments:
            if os.path.exists(s):
                f.write(f"file '{s}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat, "-c", "copy", "-movflags", "+faststart", OUT,
    ], check=True, capture_output=True, text=True)

    for s in segments:
        try: os.remove(s)
        except OSError: pass

    mb = os.path.getsize(OUT) / 1024 / 1024
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "json", OUT], capture_output=True, text=True)
    total = json.loads(r.stdout)["format"]["duration"]
    print(f"\n  ✓ {OUT}")
    print(f"    时长: {float(total):.0f}s")
    print(f"    大小: {mb:.1f}MB")


if __name__ == "__main__":
    main()
