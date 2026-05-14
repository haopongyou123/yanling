"""图文 → 短视频转化流水线

从 auto-content JSON 读取内容，生成 TikTok/YouTube Shorts 格式短视频。
使用 edge-tts 生成语音 + FFmpeg 合成画面。

用法:
  # 从 auto-content 数据文件生成
  python pipeline_video.py --date 2026-05-13

  # 自定义内容
  python pipeline_video.py --title "标题" --text "正文内容"
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path

# ── 配置 ──────────────────────────────────────────

FONT = "/home/toto/.fonts/NotoSansSC-Regular.otf"
ASSETS = Path(__file__).parent / "assets"
DATA_DIR = Path(os.environ.get("HOME", "/home/toto")) / "auto-content" / "data"
OUTPUT_DIR = Path(__file__).parent / "output"

EDGE_TTS_VOICE = "zh-CN-XiaoxiaoNeural"
EDGE_TTS_RATE = "+5%"

OUTPUT_DIR.mkdir(exist_ok=True)

# ── TTS ───────────────────────────────────────────

async def gen_audio(text: str, out_path: str) -> None:
    """用 edge-tts 生成中文语音。"""
    import edge_tts
    tts = edge_tts.Communicate(text, EDGE_TTS_VOICE, rate=EDGE_TTS_RATE)
    await tts.save(out_path)


def get_duration(mp3: str) -> float:
    if not os.path.exists(mp3):
        return 3.0
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", mp3],
        capture_output=True, text=True, timeout=30)
    return float(json.loads(r.stdout)["format"]["duration"])


# ── 视频片段生成 ──────────────────────────────────

def escape_ff(text: str) -> str:
    """转义 FFmpeg drawtext 特殊字符。"""
    return (text
            .replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
            .replace("%", "\\%")
            .replace(")", "\\)")
            .replace("(", "\\("))


def make_segment(
    seg_id: int,
    title: str,
    body: str,
    audio_path: str | None,
    font_size: int = 48,
    sub_size: int = 28,
) -> str:
    """生成一个视频片段（深色背景 + 文字 + 语音）。"""
    out = f"/tmp/yanling_seg_{seg_id:03d}.ts"
    dur = get_duration(audio_path) if audio_path and os.path.exists(audio_path) else 4.0

    # 主体文字自动换行
    wrapped = textwrap.fill(body, width=18 if font_size > 36 else 30)
    lines = wrapped.split("\n")
    line_h = font_size + 8
    total_h = len(lines) * line_h
    y_start = max(540 - total_h // 2, 200)

    # 构建 drawtext 滤镜（输入已是 color 流，只需 drawtext）
    filters = []

    # 1) 标题（顶部）
    y_title = 240 if body else 540
    filters.append(
        f"drawtext=text='{escape_ff(title)}':fontcolor=white:fontsize={font_size}"
        f":x=(w-text_w)/2:y={y_title}"
        f":fontfile={FONT}:shadowcolor=black:shadowx=3:shadowy=3"
    )

    # 2) 主体文字（居中偏下）
    if body:
        for i, line in enumerate(lines):
            y_line = y_start + i * line_h
            filters.append(
                f"drawtext=text='{escape_ff(line)}':fontcolor=#ccccdd"
                f":fontsize={sub_size}:x=(w-text_w)/2:y={y_line}"
                f":fontfile={FONT}:shadowcolor=black:shadowx=2:shadowy=2"
            )

    # 3) 底部装饰线
    filters.append(
        f"drawtext=text='衍灵 · 智能内容'"
        f":fontcolor=#555577:fontsize=16"
        f":x=(w-text_w)/2:y=h-60"
        f":fontfile={FONT}"
    )

    filter_str = ",".join(filters)

    cmd = ["ffmpeg", "-y"]
    # Input: generated color stream
    cmd += ["-f", "lavfi", "-i", f"color=c=#0a0a1a:s=1080x1920:d={dur}:r=30"]
    # Input: audio (optional)
    if audio_path and os.path.exists(audio_path):
        cmd += ["-i", audio_path]
    cmd += [
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "fast", "-crf", "26",
        "-pix_fmt", "yuv420p",
    ]
    if audio_path and os.path.exists(audio_path):
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    else:
        cmd += ["-t", str(dur)]
    cmd += ["-f", "mpegts", out]

    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    return out


# ── 从 auto-content 生成 ──────────────────────────

def load_auto_content(date_str: str) -> dict | None:
    """加载指定日期的 auto-content 数据。"""
    path = DATA_DIR / f"{date_str}.json"
    if not path.exists():
        # 找最新
        files = sorted(DATA_DIR.glob("*.json"))
        if not files:
            return None
        path = files[-1]
    with open(path) as f:
        return json.load(f)


def build_news_segments(content: dict) -> list[dict]:
    """从 auto-content 构建短视频片段列表。"""
    c = content.get("content", content)
    titles = c.get("titles", [c.get("title", "科技日报")])
    opening = c.get("opening", "")
    items = c.get("items", c.get("articles", []))
    tags = c.get("tags", [])

    segs = []

    # 开场
    segs.append({
        "title": titles[0] if titles else "今日科技",
        "body": opening[:120] if opening else "",
        "audio_text": opening if opening else f"欢迎收看{ titles[0] if titles else '今日科技' }",
    })

    # 每条新闻
    for item in items[:5]:  # 最多 5 条
        title = item.get("title", "")
        summary = item.get("summary", item.get("content", ""))
        if not title:
            continue
        segs.append({
            "title": title[:50],
            "body": summary[:150] if summary else "",
            "audio_text": f"{title}。{summary[:200] if summary else ''}",
        })

    # 结尾
    if tags:
        tag_text = " ".join(tags[:5])
        segs.append({
            "title": "感谢收看",
            "body": tag_text,
            "audio_text": f"以上就是今日科技动态。{tag_text}。关注衍灵，获取每日智能资讯。",
        })
    else:
        segs.append({
            "title": "感谢收看",
            "body": "关注衍灵，获取每日智能资讯",
            "audio_text": "以上就是今日科技动态。关注衍灵，获取每日智能资讯。",
        })

    return segs


# ── 主流程 ─────────────────────────────────────────

async def run_pipeline(
    segments: list[dict],
    output_name: str = None,
) -> str:
    """执行完整视频生成管道。

    Args:
        segments: [{"title": ..., "body": ..., "audio_text": ...}]
        output_name: 输出文件名（不含路径）

    Returns:
        输出文件路径
    """
    print(f"📹 视频管道启动 — {len(segments)} 个片段\n")

    audio_dir = tempfile.mkdtemp(prefix="yanling_audio_")
    ts_files = []

    try:
        # Step 1: 生成所有语音
        print("🎤 生成语音...")
        audio_tasks = []
        for i, seg in enumerate(segments):
            audio_path = os.path.join(audio_dir, f"seg_{i:03d}.mp3")
            seg["_audio"] = audio_path
            audio_tasks.append(gen_audio(seg["audio_text"], audio_path))

        await asyncio.gather(*audio_tasks)
        for i, seg in enumerate(segments):
            dur = get_duration(seg["_audio"])
            print(f"  [{i+1}/{len(segments)}] {seg['title'][:30]:30s}  {dur:.1f}s")

        # Step 2: 生成视频片段
        print("\n🎬 合成视频片段...")
        for i, seg in enumerate(segments):
            title_fs = 40 if len(seg["title"]) > 20 else 48
            body_fs = 26 if seg.get("body") and len(seg["body"]) > 100 else 30
            ts = make_segment(
                i, seg["title"], seg.get("body", ""),
                seg["_audio"], font_size=title_fs, sub_size=body_fs,
            )
            ts_files.append(ts)
            print(f"  [{i+1}/{len(segments)}] ✓")

        # Step 3: 拼接最终视频
        print("\n🔗 拼接最终视频...")
        concat = os.path.join(audio_dir, "concat.txt")
        with open(concat, "w") as f:
            for ts in ts_files:
                if os.path.exists(ts):
                    f.write(f"file '{ts}'\n")

        if not output_name:
            from datetime import datetime
            output_name = f"衍灵短视频_{datetime.now():%m%d_%H%M}.mp4"

        output_path = str(OUTPUT_DIR / output_name)

        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat, "-c", "copy", "-movflags", "+faststart",
            output_path,
        ], check=True, capture_output=True, text=True, timeout=180)

        # 结果
        size_mb = os.path.getsize(output_path) / 1024 / 1024
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", output_path],
            capture_output=True, text=True, timeout=10)
        total_dur = float(json.loads(r.stdout)["format"]["duration"])

        print(f"\n✅ 完成！")
        print(f"   输出: {output_path}")
        print(f"   时长: {total_dur:.0f}s")
        print(f"   大小: {size_mb:.1f}MB")
        print(f"   片段: {len(segments)} 个")

        return output_path

    finally:
        # 清理临时文件
        for ts in ts_files:
            try:
                os.remove(ts)
            except OSError:
                pass
        try:
            import shutil
            shutil.rmtree(audio_dir, ignore_errors=True)
        except OSError:
            pass


# ── CLI ───────────────────────────────────────────

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="图文→短视频转化流水线")
    parser.add_argument("--date", help="auto-content 日期，如 2026-05-13")
    parser.add_argument("--title", help="自定义标题")
    parser.add_argument("--text", help="自定义正文")
    parser.add_argument("--output", help="输出文件名")
    args = parser.parse_args()

    if args.title and args.text:
        # 自定义模式
        segments = [{
            "title": args.title,
            "body": args.text[:200],
            "audio_text": f"{args.title}。{args.text[:300]}",
        }]
    elif args.date:
        content = load_auto_content(args.date)
        if not content:
            print(f"❌ 未找到 {args.date} 的数据")
            return
        segments = build_news_segments(content)
        print(f"📄 加载: {args.date} — {len(segments)} 个片段\n")
    else:
        # 默认：最新数据
        content = load_auto_content("")
        if not content:
            print("❌ 未找到 auto-content 数据")
            return
        segments = build_news_segments(content)
        date_str = content.get("date", "latest")
        print(f"📄 加载: {date_str} — {len(segments)} 个片段\n")

    await run_pipeline(segments, args.output)


if __name__ == "__main__":
    asyncio.run(main())
