#!/usr/bin/env python3
"""短视频发布工具 — 准备 + 上传 YouTube Shorts

用法:
  # 只准备（生成缩略图 + 元数据，不上传）
  python publish_shorts.py --video output/test_short.mp4 --title "今日科技" --desc "你的描述"

  # 从内容数据自动生成
  python publish_shorts.py --from-content 2026-05-13

  # 完整上传（需配置 YouTube API 凭据）
  python publish_shorts.py --upload output/衍灵短视频_0513_2300.mp4

  # 列出准备好的视频
  python publish_shorts.py --list
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
OUTPUT_DIR = HERE / "output"
DATA_DIR = Path(os.environ.get("HOME", "/home/toto")) / "auto-content" / "data"
READY_DIR = HERE / "upload-ready"

READY_DIR.mkdir(exist_ok=True)


# ── 工具函数 ──────────────────────────────────────

def generate_thumbnail(video_path: str, out_path: str, time_sec: float = 1.0) -> bool:
    """从视频中截取一帧作为缩略图。"""
    try:
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(time_sec),
            "-i", video_path, "-vframes", "1",
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            out_path,
        ], check=True, capture_output=True, text=True, timeout=30)
        return True
    except subprocess.CalledProcessError:
        return False


def get_video_duration(video_path: str) -> float:
    try:
        r = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", video_path,
        ], capture_output=True, text=True, timeout=10)
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def load_content(date_str: str) -> dict | None:
    """从 auto-content 加载数据。"""
    path = DATA_DIR / f"{date_str}.json"
    if not path.exists():
        files = sorted(DATA_DIR.glob("*.json"))
        if not files:
            return None
        path = files[-1]
    with open(path) as f:
        return json.load(f)


# ── 准备发布 ──────────────────────────────────────

def prepare_upload(
    video_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    category: str = "科技",
) -> dict:
    """准备上传文件夹：视频 + 缩略图 + 元数据。"""
    video = Path(video_path)
    if not video.exists():
        print(f"❌ 视频文件不存在: {video_path}")
        return {}

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = f"shorts_{ts}"
    dest_dir = READY_DIR / slug
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1. 复制视频
    dest_video = dest_dir / video.name
    import shutil
    shutil.copy2(video, dest_video)

    # 2. 生成缩略图
    thumb = dest_dir / "thumbnail.jpg"
    if generate_thumbnail(str(dest_video), str(thumb)):
        print(f"  ✓ 缩略图: {thumb.name}")
    else:
        print(f"  ⚠ 缩略图生成失败")

    # 3. 元数据
    duration = get_video_duration(str(dest_video))
    tags = tags or []
    meta = {
        "title": title,
        "description": description,
        "tags": tags,
        "category": category,
        "duration_sec": round(duration),
        "filename": video.name,
        "platforms": {
            "youtube": {
                "privacy_status": "public",  # public | unlisted | private
                "made_for_kids": False,
                "category_id": "28",  # 科技
            },
            "tiktok": {
                "note": "TikTok API 暂不支持自动上传，请手动发布",
            },
        },
        "prepared_at": datetime.now().isoformat(),
    }
    meta_path = dest_dir / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    size_mb = dest_video.stat().st_size / 1024 / 1024
    print(f"\n✅ 准备完成: {dest_dir}/")
    print(f"   视频: {video.name} ({size_mb:.1f}MB, {duration:.0f}s)")
    print(f"   标题: {title}")
    print(f"   标签: {' '.join(tags[:5])}")
    print(f"\n👉 上传方式:")
    print(f"   1. YouTube: 打开 https://studio.youtube.com 拖入视频")
    print(f"   2. TikTok:  打开 https://tiktok.com/upload 拖入视频")
    print(f"   3. 元数据文件: {meta_path}")

    return meta


def auto_prepare(date_str: str) -> dict | None:
    """从 auto-content 自动生成发布包。"""
    content = load_content(date_str)
    if not content:
        print("❌ 未找到内容数据")
        return None

    c = content.get("content", content)
    titles = c.get("titles", [])
    opening = c.get("opening", "")
    tags = c.get("tags", [])

    # 找最新视频
    videos = sorted(OUTPUT_DIR.glob("*.mp4"))
    if not videos:
        print("❌ 未找到已生成的视频，请先运行 pipeline_video.py")
        return None

    latest = videos[-1]
    title = titles[0] if titles else latest.stem
    desc = (opening[:200] if opening else title) + \
           "\n\n#衍灵AI #智能内容 #科技日报" + \
           "\n\n更多内容: https://github.com/haopongyou123/auto-content"

    return prepare_upload(
        video_path=str(latest),
        title=title[:100],
        description=desc,
        tags=tags[:8],
    )


# ── YouTube API 上传 ──────────────────────────────

def upload_youtube(video_path: str) -> bool:
    """通过 YouTube Data API v3 上传。

    需要先配置 OAuth 凭据：
      export YOUTUBE_CLIENT_SECRETS=/path/to/client_secret.json

    首次运行会自动打开浏览器进行 OAuth 授权。
    """
    client_secrets = os.environ.get("YOUTUBE_CLIENT_SECRETS", "")
    if not client_secrets or not Path(client_secrets).exists():
        print("❌ 未配置 YouTube API 凭据")
        print("   1. 访问 https://console.cloud.google.com/apis/credentials")
        print("   2. 创建 OAuth 2.0 客户端 ID（桌面应用）")
        print("   3. 下载 client_secret.json")
        print("   4. export YOUTUBE_CLIENT_SECRETS=/path/to/client_secret.json")
        print("   5. 重新运行 --upload")
        return False

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        print("❌ 需要安装 Google API 库:")
        print("   pip install google-auth-oauthlib google-api-python-client")
        return False

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    # 查找元数据
    video = Path(video_path)
    meta_paths = list(READY_DIR.rglob("metadata.json"))
    meta = None
    for mp in meta_paths:
        if video.name in mp.read_text():
            meta = json.loads(mp.read_text())
            break

    if not meta:
        print("⚠ 未找到对应元数据文件，使用默认值")
        meta = {
            "title": video.stem,
            "description": "",
            "tags": [],
            "platforms": {"youtube": {"privacy_status": "unlisted", "made_for_kids": False}},
        }

    # OAuth
    creds = None
    token_path = READY_DIR / ".youtube_token.json"
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    # 上传
    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"][:8],
            "categoryId": meta["platforms"]["youtube"].get("category_id", "28"),
        },
        "status": {
            "privacyStatus": meta["platforms"]["youtube"].get("privacy_status", "unlisted"),
            "madeForKids": meta["platforms"]["youtube"].get("made_for_kids", False),
        },
    }

    media = MediaFileUpload(str(video), chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    print(f"⏫ 上传中: {video.name}...")
    response = request.execute()
    video_id = response.get("id", "")
    print(f"\n✅ 上传成功!")
    print(f"   YouTube: https://youtu.be/{video_id}")
    print(f"   标题: {meta['title']}")
    return True


# ── 列表 ──────────────────────────────────────────

def list_ready():
    """列出所有准备好的上传包。"""
    dirs = sorted(READY_DIR.glob("shorts_*"))
    if not dirs:
        print("📭 没有准备好的视频")
        print(f"   先运行: python publish_shorts.py --from-content <日期>")
        return

    print(f"📦 已准备好的上传包 ({len(dirs)}):\n")
    for d in dirs:
        meta = d / "metadata.json"
        video = next(d.glob("*.mp4"), None)
        if meta.exists():
            m = json.loads(meta.read_text())
            print(f"  📁 {d.name}")
            print(f"     标题: {m['title'][:50]}")
            print(f"     时长: {m['duration_sec']}s")
            print(f"     标签: {' '.join(m['tags'][:3])}")
        if video:
            print(f"     视频: {video.name} ({video.stat().st_size/1e6:.0f}MB)")
        print()


# ── CLI ───────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="短视频发布工具")
    parser.add_argument("--video", help="视频文件路径")
    parser.add_argument("--title", help="视频标题（建议 ≤60 字符）")
    parser.add_argument("--desc", help="视频描述")
    parser.add_argument("--tags", nargs="*", default=[], help="标签列表")
    parser.add_argument("--category", default="科技", help="分类")
    parser.add_argument("--from-content", metavar="DATE", help="从 auto-content 数据自动准备")
    parser.add_argument("--upload", metavar="VIDEO", help="上传到 YouTube")
    parser.add_argument("--list", action="store_true", help="列出已准备的视频")
    parser.add_argument("--prepare-only", action="store_true", default=True, help="仅准备不上传")

    args = parser.parse_args()

    if args.list:
        list_ready()
        return

    if args.upload:
        target = args.upload
        # 检查是文件还是目录
        p = Path(target)
        if p.is_dir():
            videos = list(p.glob("*.mp4"))
            if not videos:
                print(f"❌ 目录 {target} 中没有视频")
                return
            target = str(videos[0])
        upload_youtube(target)
        return

    if args.from_content:
        auto_prepare(args.from_content)
        return

    if args.video:
        desc = args.desc or ""
        if not args.title:
            print("⚠ 未指定标题，从文件名推断")
        prepare_upload(
            video_path=args.video,
            title=args.title or Path(args.video).stem,
            description=desc,
            tags=args.tags,
            category=args.category,
        )
        return

    parser.print_help()


if __name__ == "__main__":
    main()
