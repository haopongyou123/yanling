"""衍灵动画视频引擎 — 纯 Python + Pillow + ffmpeg."""
from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from PIL import Image, ImageDraw, ImageFont
import numpy as np

ASSETS = "/home/toto/yanling/docs/assets"
OUT = "/home/toto/yanling/docs/衍灵产品介绍_动画版.mp4"
FONT = "/home/toto/.fonts/NotoSansSC-Regular.otf"
FPS = 30
W, H = 1920, 1080

# ─── 缓动函数 ────────────────────────────────────────────────

def ease_in_out(t: float) -> float:
    return t * t * (3 - 2 * t)

def ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3

def ease_in(t: float) -> float:
    return t ** 3

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def clamp(v: float, lo: float = 0, hi: float = 1) -> float:
    return max(lo, min(hi, v))


# ─── 字体工具 ────────────────────────────────────────────────

@dataclass
class FontCache:
    _fonts: dict = field(default_factory=dict)

    def get(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self._fonts:
            self._fonts[size] = ImageFont.truetype(FONT, size)
        return self._fonts[size]

FONTS = FontCache()


def text_size(draw: ImageDraw, text: str, size: int) -> tuple[int, int]:
    """获取文本渲染尺寸。"""
    bbox = draw.textbbox((0, 0), text, font=FONTS.get(size))
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


# ─── 基础场景类 ──────────────────────────────────────────────

class Scene:
    """一页动画场景。

    duration: 总时长(秒)
    start_time: 在视频中的起始时间(由 SlideDeck 设置)
    """
    duration: float
    start_time: float = 0

    def __init__(self, duration: float):
        self.duration = duration

    @property
    def end_time(self) -> float:
        return self.start_time + self.duration

    def render(self, img: Image.Image, t: float):
        """渲染当前帧。t 在 [0, 1] 范围内，表示本场景的进度。"""
        raise NotImplementedError


# ─── 具体场景 ────────────────────────────────────────────────

class TitleScene(Scene):
    """开场/结束标题页：文字动画 + 渐变背景。"""
    def __init__(self, title: str, subtitle: str, duration: float,
                 bg_color: tuple = (10, 10, 26)):
        super().__init__(duration)
        self.title = title
        self.subtitle = subtitle
        self.bg = bg_color

    def _draw_bg(self, img: Image.Image, t: float):
        """带微弱径向渐变的背景。"""
        draw = ImageDraw.Draw(img)
        # 纯色背景
        draw.rectangle([0, 0, W, H], fill=self.bg)
        # 微弱的装饰光晕
        cx, cy = W // 2, H // 2
        for r in range(300, 0, -2):
            alpha = int(max(0, 1 - r / 300) * 8 * t)
            if alpha > 0:
                draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                             fill=(74, 144, 217, alpha))

    def render(self, img: Image.Image, t: float):
        draw = ImageDraw.Draw(img)
        self._draw_bg(img, t)

        # 标题渐入 + 轻微上移
        title_t = ease_out(clamp((t - 0.1) / 0.5))
        title_y = lerp(H // 2 + 20, H // 2 - 40, title_t)
        title_alpha = int(title_t * 255)
        tw, th = text_size(draw, self.title, 72)
        tx = (W - tw) // 2
        # 阴影
        draw.text((tx + 2, title_y + 2), self.title, font=FONTS.get(72),
                  fill=(0, 0, 0, title_alpha // 2))
        draw.text((tx, title_y), self.title, font=FONTS.get(72),
                  fill=(255, 255, 255, title_alpha))

        # 副标题延迟出现
        sub_t = ease_out(clamp((t - 0.3) / 0.4))
        sub_y = lerp(H // 2 + 40, H // 2 + 20, sub_t)
        sub_alpha = int(sub_t * 180)
        sw, sh = text_size(draw, self.subtitle, 28)
        draw.text(((W - sw) // 2, sub_y), self.subtitle, font=FONTS.get(28),
                  fill=(136, 136, 204, sub_alpha))

        # 底部装饰线
        line_t = ease_out(clamp((t - 0.2) / 0.6))
        line_w = int(lerp(0, 100, line_t))
        if line_w > 0:
            draw.rectangle([(W - line_w) // 2, H // 2 + 5,
                           (W + line_w) // 2, H // 2 + 7],
                          fill=(74, 144, 217, int(100 * line_t)))


class ImageScene(Scene):
    """图片展示页：Ken Burns 慢推 + 底部文字条。"""
    def __init__(self, img_path: str, title: str, subtitle: str, duration: float,
                 zoom_start: float = 1.0, zoom_end: float = 1.08):
        super().__init__(duration)
        self.original = Image.open(img_path).convert("RGBA")
        self.title = title
        self.subtitle = subtitle
        self.zs = zoom_start
        self.ze = zoom_end

    def render(self, img: Image.Image, t: float):
        draw = ImageDraw.Draw(img)

        # Ken Burns 缓推
        zoom = lerp(self.zs, self.ze, ease_in_out(t))
        iw, ih = self.original.size
        # 裁剪原图到 16:9
        target_ratio = W / H
        src_ratio = iw / ih
        if src_ratio > target_ratio:
            new_w = int(ih * target_ratio)
            new_h = ih
            ox = (iw - new_w) // 2
            oy = 0
        else:
            new_w = iw
            new_h = int(iw / target_ratio)
            ox = 0
            oy = (ih - new_h) // 2
        cropped = self.original.crop((ox, oy, ox + new_w, oy + new_h))
        resized = cropped.resize((int(W * zoom), int(H * zoom)), Image.LANCZOS)
        # 居中裁剪到 WxH
        cx = (resized.width - W) // 2
        cy = (resized.height - H) // 2
        img.paste(resized.crop((cx, cy, cx + W, cy + H)), (0, 0))

        # 底部半透明黑条
        bar_t = ease_out(clamp((t - 0.15) / 0.3))
        bar_h = 90
        bar_alpha = int(180 * bar_t)
        draw.rectangle([0, H - bar_h, W, H],
                       fill=(0, 0, 0, bar_alpha))

        # 标题文字底部左对齐
        title_alpha = int(255 * bar_t)
        draw.text((40, H - 65), self.title, font=FONTS.get(32),
                  fill=(255, 255, 255, title_alpha))
        draw.text((40, H - 35), self.subtitle, font=FONTS.get(18),
                  fill=(170, 170, 204, title_alpha))


class NoImageScene(Scene):
    """无图片页（纯文字内容）：背景色 + 标题 + 要点。"""
    def __init__(self, title: str, bullets: list[str], duration: float):
        super().__init__(duration)
        self.title = title
        self.bullets = bullets

    def render(self, img: Image.Image, t: float):
        draw = ImageDraw.Draw(img)
        # 深色渐变背景
        for y in range(H):
            p = y / H
            r = int(lerp(15, 10, p))
            g = int(lerp(15, 10, p))
            b = int(lerp(26, 18, p))
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        # 标题
        title_t = ease_out(clamp((t - 0.05) / 0.3))
        tw, th = text_size(draw, self.title, 48)
        tx = (W - tw) // 2
        ty = 120
        draw.text((tx, int(lerp(ty + 20, ty, title_t))), self.title,
                  font=FONTS.get(48), fill=(255, 255, 255, int(255 * title_t)))

        # 装饰线下
        line_t = ease_out(clamp((t - 0.15) / 0.3))
        lw = int(lerp(0, 80, line_t))
        draw.rectangle([(W - lw) // 2, ty + 55, (W + lw) // 2, ty + 58],
                       fill=(74, 144, 217, int(150 * line_t)))

        # 要点逐条出现
        for i, bullet in enumerate(self.bullets):
            bt = clamp((t - 0.25 - i * 0.12) / 0.3)
            b_alpha = int(255 * ease_out(bt))
            bx, by = 300, 240 + i * 55
            # 圆点
            if bt > 0:
                draw.ellipse([bx - 15, by - 4, bx - 5, by + 6],
                             fill=(80, 200, 120, b_alpha))
            draw.text((bx + 10, by - 8), bullet, font=FONTS.get(24),
                      fill=(220, 220, 240, b_alpha))


# ─── 幻灯片组装 ──────────────────────────────────────────────

class SlideDeck:
    """一组场景 + 场景间淡入淡出 + ffmpeg 编码。"""
    def __init__(self):
        self.scenes: list[Scene] = []
        self._frame_buf: list[bytes] = []
        self._current_scene: int = -1

    def add(self, scene: Scene):
        self.scenes.append(scene)

    def _assign_times(self):
        t = 0
        for s in self.scenes:
            s.start_time = t
            t += s.duration
        return t

    def _render_frame(self, global_t: float) -> Image.Image:
        """渲染指定全局时间点的帧。"""
        img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        # 查找当前场景
        scene: Scene | None = None
        for s in self.scenes:
            if s.start_time <= global_t < s.end_time:
                scene = s
                break
        if scene is None:
            return img

        local_t = (global_t - scene.start_time) / scene.duration
        scene.render(img, local_t)

        # 场景间简单交叉淡化
        fade_dur = 0.3  # 300ms 过渡
        for s in self.scenes:
            if s is scene:
                continue
            # 从前一个场景淡入
            prev_end = s.end_time
            if 0 < prev_end - global_t <= fade_dur:
                alpha = int(255 * (prev_end - global_t) / fade_dur)
                overlay = Image.new("RGBA", (W, H), (0, 0, 0, alpha))
                img = Image.alpha_composite(img, overlay)

        return img

    def render(self, output_path: str):
        total_dur = self._assign_times()
        total_frames = int(total_dur * FPS) + 1
        print(f"总时长: {total_dur:.1f}s, 总帧数: {total_frames}")

        # 管道写入 ffmpeg
        cmd = [
            "ffmpeg", "-y",
            "-f", "image2pipe", "-vcodec", "png",
            "-r", str(FPS), "-i", "-",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

        batch_size = 30
        batch_frames = []

        for fi in range(total_frames):
            gt = fi / FPS
            frame = self._render_frame(gt)
            buf = frame.tobytes()
            batch_frames.append((frame.width, frame.height, buf))

            if len(batch_frames) >= batch_size or fi == total_frames - 1:
                for w, h, buf_data in batch_frames:
                    pil_img = Image.frombytes("RGBA", (w, h), buf_data)
                    pil_img.save(proc.stdin, "PNG")
                batch_frames.clear()

            if fi % 30 == 0:
                progress = int((fi / total_frames) * 100)
                print(f"\r  渲染中... {progress}%", end="", flush=True)

        print(f"\r  渲染完成! 100%")
        proc.stdin.close()
        proc.wait()

    def add_audio(self, video_path: str, audio_map: dict[float, str]) -> str:
        """混入语音。audio_map: {start_time: audio_file_path}"""
        out_path = video_path.replace(".mp4", "_with_audio.mp4")

        # 将所有音频合并为一个文件
        audio_parts = []
        for start, afile in sorted(audio_map.items()):
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "json", afile],
                capture_output=True, text=True)
            data = json.loads(result.stdout)
            dur = float(data["format"]["duration"])
            audio_parts.append((start, dur, afile))

        # 用 amix 合并多轨音频
        filter_parts = []
        inputs = ["ffmpeg", "-y", "-i", video_path]
        for i, (st, dur, af) in enumerate(audio_parts):
            inputs += ["-i", af]
            delay_ms = int(st * 1000)
            filter_parts.append(
                f"[{i+1}:a]adelay={delay_ms}|{delay_ms},apad[a{i}]"
            )
        audio_inputs = "".join(f"[a{i}]" for i in range(len(audio_parts)))
        filter_parts.append(f"{audio_inputs}amix=inputs={len(audio_parts)}:duration=first[aout]")

        filter_str = ";".join(filter_parts)
        inputs += [
            "-filter_complex", filter_str,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            out_path,
        ]
        subprocess.run(inputs, check=True, capture_output=True)
        return out_path
