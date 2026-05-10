#!/usr/bin/env python3
"""
衍灵产品介绍视频 v2.0 — 科技未来风
6场景 · 粒子特效 · 发光文字 · AI语音

用法:
  source /tmp/yanling_venv/bin/activate
  python3 gen_scene.py

依赖: Pillow, edge-tts, numpy, ffmpeg
"""

import json, math, os, shutil, struct, subprocess, sys, tempfile, textwrap, time
import random as _random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── 配置 ──

W, H = 1920, 1080
FPS = 30
BG = (10, 14, 23)       # #0a0e17 深空
CYAN = (34, 211, 238)   # #22d3ee
GREEN = (16, 185, 129)  # #10b981
PURPLE = (168, 85, 247)  # #a855f7
WHITE = (226, 232, 240) # #e2e8f0
DIM = (100, 116, 139)   # #64748b

OUT_DIR = Path("/tmp/yanling_video")
OUT_DIR.mkdir(parents=True, exist_ok=True)
FRAME_DIR = OUT_DIR / "frames"
FRAME_DIR.mkdir(exist_ok=True)

# ── 字体 ──

def find_font(size=36):
    """找合适的字体"""
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

# ── 粒子系统 ──

@dataclass
class Particle:
    x: float; y: float
    vx: float; vy: float
    life: float; max_life: float
    size: float; color: Tuple[int,int,int]
    alpha: float = 1.0

class ParticleSystem:
    def __init__(self, count=200):
        self.particles = []
        self.count = count

    def emit(self, cx, cy, spread=100, color=CYAN):
        for _ in range(self.count):
            angle = _random.random() * 2 * math.pi
            speed = _random.random() * 2 + 0.5
            self.particles.append(Particle(
                x=cx + (_random.random()-0.5)*spread,
                y=cy + (_random.random()-0.5)*spread,
                vx=math.cos(angle)*speed,
                vy=math.sin(angle)*speed,
                life=_random.random()*60+30,
                max_life=90,
                size=_random.random()*3+1,
                color=color,
            ))

    def update(self):
        dead = []
        for p in self.particles:
            p.x += p.vx; p.y += p.vy
            p.vx *= 0.98; p.vy *= 0.98
            p.life -= 1
            p.alpha = max(0, p.life / p.max_life)
            if p.life <= 0:
                dead.append(p)
        for p in dead:
            self.particles.remove(p)

    def draw(self, draw: ImageDraw):
        for p in self.particles:
            alpha = int(p.alpha * 255 * 0.6)
            if alpha <= 0: continue
            r, g, b = p.color
            draw.ellipse(
                [p.x-p.size, p.y-p.size, p.x+p.size, p.y+p.size],
                fill=(r, g, b, alpha)
            )

# ── 绘制工具 ──

def glow(draw, xy, text, font, color=CYAN, radius=6):
    """发光文字"""
    x, y = xy
    # 外发光层
    for dx, dy in [(r, r) for r in range(-radius, radius+1, 2)]:
        for dr in range(3):
            factor = 1 - abs(dx)//radius
            if factor <= 0: continue
            glow_color = tuple(
                min(255, c + 60) for c in color
            )
            draw.text((x+dx+dr, y+dy), text, font=font,
                      fill=(*glow_color, 40*factor))
    # 主体
    draw.text((x, y), text, font=font, fill=(*color, 255))

def draw_tech_grid(draw, t, color=CYAN):
    """绘制科技感网格"""
    grid_size = 60
    alpha = 30
    for x in range(0, W, grid_size):
        draw.line([(x, 0), (x, H)], fill=(*color, alpha), width=1)
    for y in range(0, H, grid_size):
        draw.line([(0, y), (W, y)], fill=(*color, alpha), width=1)

def draw_particle_flow(draw, t, color=CYAN):
    """动态粒子流线"""
    np.random.seed(int(t * 100) % 10000)
    for i in range(30):
        x = (t * 30 + i * 64) % W
        y = (t * 20 + i * 37 + 200 * math.sin(t * 0.5 + i * 0.1)) % H
        size = 2 + math.sin(t + i) * 1.5
        alpha = int(abs(math.sin(t * 0.3 + i * 0.2)) * 120 + 40)
        draw.ellipse([x-size, y-size, x+size, y+size],
                     fill=(*color, alpha))

def draw_node_network(draw, t, nodes=8):
    """节点网络连接图"""
    np.random.seed(42)
    positions = []
    for i in range(nodes):
        angle = 2 * math.pi * i / nodes + t * 0.1
        r = 250 + 50 * math.sin(t * 0.3 + i)
        cx, cy = W//2, H//2
        positions.append((
            cx + r * math.cos(angle),
            cy + r * math.sin(angle)
        ))
    # 连接线
    for i, (x1, y1) in enumerate(positions):
        for j, (x2, y2) in enumerate(positions):
            if j <= i: continue
            dist = math.sqrt((x2-x1)**2 + (y2-y1)**2)
            alpha = max(0, min(255, int(80 - dist/10)))
            if alpha > 10:
                draw.line([(x1, y1), (x2, y2)],
                         fill=(*CYAN, alpha), width=1)
    # 节点
    for x, y in positions:
        pulse = 3 + 2 * math.sin(t * 2 + x * 0.01)
        draw.ellipse([x-pulse, y-pulse, x+pulse, y+pulse],
                     fill=(*CYAN, 200))

# ── 场景定义 ──

@dataclass
class Scene:
    name: str
    duration: float  # 秒
    voice_text: str
    render_fn: callable  # (draw, t)  t: 0~1

    @property
    def frames(self): return int(self.duration * FPS)

def render_scene_1_intro(t):
    """开场：粒子汇聚→衍灵Logo"""
    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)
    font_lg = find_font(72)
    font_sm = find_font(28)

    draw_tech_grid(draw, t)

    # 粒子汇聚效果
    progress = min(1, t * 2)  # 前半段汇聚
    spread = 800 * (1 - progress) + 10
    np.random.seed(42)
    for i in range(150):
        angle = _random.random() * 2 * math.pi
        r = spread * _random.random()
        x = W//2 + r * math.cos(angle + t * 2)
        y = H//2 + r * math.sin(angle + t * 2)
        size = 2 + progress * 2
        alpha = int(progress * 200 + 55)
        draw.ellipse([x-size, y-size, x+size, y+size],
                     fill=(*CYAN, alpha))

    draw_particle_flow(draw, t)

    # 标题（后半段渐入）
    if t > 0.3:
        alpha_t = min(1, (t - 0.3) / 0.4)
        title = "衍灵"
        sub = "YANLING · AI 智能体引擎"
        glow(draw, (W//2 - 120, H//2 - 120), title, font_lg, CYAN)
        alpha = int(alpha_t * 255)
        draw.text((W//2 - 200, H//2), sub, font=font_sm,
                  fill=(*DIM, alpha))

    return img

def render_scene_2_iot(t):
    """IoT 运维监控"""
    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)
    font_md = find_font(40)
    font_sm = find_font(24)

    draw_tech_grid(draw, t)
    draw_node_network(draw, t)

    # 数据流
    for i in range(20):
        x = (t * 200 + i * 96) % W
        y = H//2 + 100 * math.sin(t * 1.5 + i * 0.3)
        draw.ellipse([x-3, y-3, x+3, y+3], fill=(*GREEN, 180))

    # 文字
    lines = [
        "分布式节点 · 实时监控",
        "多节点数据采集与智能分析",
        "异常检测 · 自动告警 · 自愈闭环",
    ]
    for i, line in enumerate(lines):
        alpha_t = max(0, min(1, (t - 0.1*i - 0.1) / 0.3))
        if alpha_t > 0:
            alpha = int(alpha_t * 255)
            draw.text((150, 200 + i*70), line, font=font_sm,
                      fill=(*WHITE, alpha))

    # 标题
    sub = "IoT · 企业级运维"
    pulse = 30 * math.sin(t * 3)
    glow(draw, (150, 100), sub, font_md, CYAN)

    return img

def render_scene_3_enterprise(t):
    """企业管理"""
    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)
    font_md = find_font(40)
    font_sm = find_font(24)

    # 科技网格
    draw_tech_grid(draw, t * 0.5, GREEN)

    # 仪表盘元素
    cx, cy = W//2, H//2 - 50
    metrics = [
        ("系统健康度", "98.5%", CYAN),
        ("活跃节点", "1,247", GREEN),
        ("告警响应", "1.2s", PURPLE),
    ]
    for i, (label, val, color) in enumerate(metrics):
        x_offset = (i - 1) * 300
        # 圆角背景
        draw.rounded_rectangle(
            [cx+x_offset-120, cy-60, cx+x_offset+120, cy+60],
            radius=12, fill=(*BG, 180),
            outline=(*color, 100), width=1
        )
        val_font = find_font(48)
        label_font = find_font(20)
        draw.text((cx+x_offset-60, cy-45), val, font=val_font,
                  fill=(*color, 200))
        draw.text((cx+x_offset-80, cy+10), label, font=label_font,
                  fill=(*DIM, 200))

    # 趋势图 (sparkline)
    np.random.seed(0)
    points = []
    spark_x, spark_y = 200, 700
    for i in range(40):
        x = spark_x + i * 25
        y = spark_y - 100 - 50 * math.sin(i * 0.3 + t * 2) - _random.random() * 20
        points.append((x, y))
    for i in range(len(points)-1):
        draw.line([points[i], points[i+1]], fill=(*CYAN, 150), width=3)

    # 文字
    title = "智能企业管理"
    glow(draw, (150, 100), title, font_md, GREEN)

    lines = [
        "AI 驱动决策 · 全链路可视化",
        "自动报表 · 智能预警 · 成本优化",
    ]
    for i, line in enumerate(lines):
        draw.text((150, 250 + i*60), line, font=font_sm,
                  fill=(*WHITE, 180))

    return img

def render_scene_4_smart_home(t):
    """智能家居"""
    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)
    font_md = find_font(40)
    font_sm = find_font(24)

    draw_tech_grid(draw, t * 0.3, PURPLE)

    # 家居节点
    rooms = [
        (W//2, 200, "客厅"), (W//2-250, 450, "卧室"),
        (W//2+250, 450, "厨房"), (W//2, 700, "阳台"),
    ]
    for x, y, name in rooms:
        pulse = 8 + 4 * math.sin(t * 2 + x * 0.01)
        draw.ellipse([x-pulse, y-pulse, x+pulse, y+pulse],
                     fill=(*PURPLE, 200))
        draw.text((x-40, y+20), name, font=font_sm,
                  fill=(*WHITE, 180))
        # 连接到中心
        draw.line([(W//2, H//2), (x, y)],
                  fill=(*PURPLE, 60), width=1)

    # 中心节点
    pulse = 15 + 5 * math.sin(t * 3)
    draw.ellipse([W//2-pulse, H//2-pulse,
                  W//2+pulse, H//2+pulse],
                 fill=(*PURPLE, 180))

    draw_particle_flow(draw, t * 0.7, PURPLE)

    title = "全屋智能中枢"
    glow(draw, (150, 100), title, font_md, PURPLE)

    lines = [
        "跨设备联动 · 场景自动化",
        "语音控制 · 能源优化 · 安防监控",
    ]
    for i, line in enumerate(lines):
        draw.text((150, 250 + i*60), line, font=font_sm,
                  fill=(*WHITE, 180))

    return img

def render_scene_5_agriculture(t):
    """农业养殖"""
    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)
    font_md = find_font(40)
    font_sm = find_font(24)

    draw_tech_grid(draw, t * 0.4, GREEN)

    # 环境数据
    sensors = [
        ("温度", "26.3°C", 300, 350),
        ("湿度", "72%", 800, 350),
        ("CO₂", "412ppm", 500, 550),
        ("光照", "38500lux", 650, 450),
    ]
    for name, val, x, y in sensors:
        pulse = 10 + 5 * _random.random()
        draw.ellipse([x-pulse, y-pulse, x+pulse, y+pulse],
                     fill=(*GREEN, 150))
        draw.text((x-30, y+20), name, font=find_font(18),
                  fill=(*DIM, 200))
        draw.text((x-35, y-40), val, font=find_font(20),
                  fill=(*GREEN, 200))

    # 波形图
    for i in range(5):
        prev = None
        for j in range(W//20):
            x = j * 20
            y = 750 + 60 * math.sin(j * 0.1 + t * 3 + i * 1.2)
            if prev:
                draw.line([prev, (x, y)],
                         fill=(*GREEN, 30+i*10), width=2)
            prev = (x, y)

    title = "智慧农业 · 精准养殖"
    glow(draw, (150, 100), title, font_md, GREEN)

    lines = [
        "环境感知 · 自动调控 · 远程管理",
        "数据驱动养殖 · 降本增效",
    ]
    for i, line in enumerate(lines):
        draw.text((150, 250 + i*60), line, font=font_sm,
                  fill=(*WHITE, 180))

    return img

def render_scene_6_outro(t):
    """结尾：愿景"""
    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)
    font_xl = find_font(64)
    font_md = find_font(36)
    font_sm = find_font(24)

    draw_tech_grid(draw, t)

    # 粒子扩散
    center_x, center_y = W//2, H//2 - 50
    for i in range(200):
        angle = _random.random() * 2 * math.pi
        r = t * 600 + _random.random() * 200
        x = center_x + r * math.cos(angle)
        y = center_y + r * math.sin(angle)
        if 0 < x < W and 0 < y < H:
            alpha = int(max(0, 200 - r * 0.3))
            size = 3 * (1 - r/800)
            if size > 0 and alpha > 0:
                draw.ellipse([x-size, y-size, x+size, y+size],
                             fill=(*CYAN, alpha))

    draw_particle_flow(draw, t)

    # 文字
    if t > 0.1:
        alpha_t = min(1, (t - 0.1) / 0.4)
        title = "衍灵 · 连接智能"
        glow(draw, (W//2 - 250, H//2 - 120), title, font_xl, CYAN,
             radius=8)
        if t > 0.4:
            alpha_t2 = min(1, (t - 0.4) / 0.3)
            sub = "让每一个设备都拥有 AI 大脑"
            draw.text((W//2 - 250, H//2), sub, font=font_md,
                      fill=(*WHITE, int(alpha_t2 * 200)))
        if t > 0.6:
            alpha_t3 = min(1, (t - 0.6) / 0.3)
            footer = "yanling.ai  |  开放 · 智能 · 进化"
            draw.text((W//2 - 220, H//2 + 80), footer, font=font_sm,
                      fill=(*DIM, int(alpha_t3 * 200)))

    return img

# ── 场景列表 ──

SCENES: List[Scene] = [
    Scene("开场·衍灵", 8, "衍灵——AI智能体引擎。让万物互联，让智能无处不在。", render_scene_1_intro),
    Scene("IoT运维", 7, "分布式节点实时监控。多源数据采集、智能分析与自动告警，运维从未如此高效。", render_scene_2_iot),
    Scene("企业管理", 7, "AI驱动企业智能管理。全链路可视化运营，数据驱动决策。", render_scene_3_enterprise),
    Scene("智能家居", 7, "全屋智能中枢。跨设备联动、场景自动化，打造智慧生活新体验。", render_scene_4_smart_home),
    Scene("智慧农业", 7, "精准农业与智慧养殖。环境感知、自动调控，数据驱动降本增效。", render_scene_5_agriculture),
    Scene("愿景", 8, "衍灵——连接智能。让每一个设备都拥有AI大脑，让世界更智能。", render_scene_6_outro),
]

# ── 语音生成 ──

async def generate_audio():
    """生成所有场景的语音"""
    import edge_tts
    print("生成语音...")
    voices = []
    for i, scene in enumerate(SCENES):
        out_path = OUT_DIR / f"voice_{i:02d}.mp3"
        if out_path.exists():
            print(f"  [{i}] 已有语音，跳过")
        else:
            communicate = edge_tts.Communicate(
                scene.voice_text,
                "zh-CN-XiaoxiaoNeural",
                rate="-5%",
                pitch="+3Hz",
            )
            await communicate.save(str(out_path))
            print(f"  [{i}] 语音已生成: {scene.name}")
        voices.append(out_path)
    return voices

# ── 帧渲染 ──

def render_frames():
    """渲染所有帧"""
    total_frames = sum(s.frames for s in SCENES)
    print(f"渲染 {total_frames} 帧 ({sum(s.duration for s in SCENES)}s @ {FPS}fps)...")

    frame_idx = 0
    for si, scene in enumerate(SCENES):
        print(f"\n场景 {si+1}/{len(SCENES)}: {scene.name} ({scene.frames}帧)")
        for fi in range(scene.frames):
            t = fi / scene.frames  # 0~1
            img = scene.render_fn(t)
            # 合成到背景
            bg = Image.new("RGB", (W, H), BG)
            if img.mode == "RGBA":
                bg.paste(img, (0, 0), img)
            else:
                bg.paste(img, (0, 0))
            out_path = FRAME_DIR / f"frame_{frame_idx:06d}.png"
            bg.save(out_path, "PNG")
            frame_idx += 1

            if fi % 30 == 0:
                print(f"  {fi}/{scene.frames} frames", end="\r")

    print(f"\n完成: {frame_idx} 帧 → {FRAME_DIR}/")

# ── 视频合成 ──

def assemble_video(audio_files, output="yanling_v2.mp4"):
    """ffmpeg 合成最终视频"""
    print("\n合成视频...")

    # 生成 concat 文件列表
    list_path = OUT_DIR / "frames.txt"
    with open(list_path, "w") as f:
        for i in range(sum(s.frames for s in SCENES)):
            f.write(f"file 'frames/frame_{i:06d}.png'\n")
            f.write(f"duration {1/FPS:.6f}\n")

    # 先合并无音频视频
    video_no_audio = OUT_DIR / "temp_no_audio.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        str(video_no_audio),
    ]
    subprocess.run(cmd, capture_output=True)

    # 混合音频
    if audio_files:
        # 生成音频 concat
        audio_list = OUT_DIR / "audio_list.txt"
        with open(audio_list, "w") as f:
            for af in audio_files:
                f.write(f"file '{af}'\n")

        mixed_audio = OUT_DIR / "mixed_audio.mp3"
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(audio_list),
            "-c", "copy",
            str(mixed_audio),
        ], capture_output=True)

        output_path = OUT_DIR / output
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_no_audio),
            "-i", str(mixed_audio),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-shortest",
            str(output_path),
        ], capture_output=True)
    else:
        shutil.copy(video_no_audio, OUT_DIR / output)
        output_path = OUT_DIR / output

    print(f"\n✅ 视频已生成: {output_path}")
    size_mb = os.path.getsize(output_path) / (1024*1024)
    print(f"   大小: {size_mb:.1f} MB")
    return output_path

# ── 主流程 ──

async def main():
    print("╔══════════════════════════════════╗")
    print("║  衍灵产品介绍视频 v2.0 生成器    ║")
    print("╚══════════════════════════════════╝")
    print()

    # Step 1: 语音
    voices = await generate_audio()

    # Step 2: 渲染帧
    render_frames()

    # Step 3: 合成
    output = assemble_video(voices, "yanling_v2.mp4")

    print(f"\n输出: {output}")

if __name__ == "__main__":
    import asyncio, random
    asyncio.run(main())
