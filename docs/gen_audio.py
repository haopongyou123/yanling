"""生成衍灵产品介绍语音 (edge-tts) — 场景驱动版."""
from __future__ import annotations

import asyncio
import edge_tts
from pathlib import Path

VOICE = "zh-CN-XiaoxiaoNeural"
OUT = "/home/toto/yanling/docs/assets"

NARRATIONS = [
    ("opening", "衍灵 — 通用 AI 自我进化系统内核。它不是另一个 AI 工具，而是一套让系统获得自主生命力的引擎。"),
    ("pain", "传统系统是被动的。你装一台服务器，需要人盯着告警你上一个 E R P，审批流程还是人工流转。衍灵改变这个范式让系统自主感知、自主决策、自主行动、自主进化。"),
    ("iot", "场景一：物联网边缘设备自主运维。生产线的传感器、远程机房的服务器、遍布城市的物联网终端衍灵作为嵌入式内核直接运行在边缘设备上。当 C P U 过载时自动诊断、当磁盘写满时自动清理、当网络中断时自动切换。当前已在园丁服务器上真实运行，五秒一个 tick 持续监控。"),
    ("enterprise", "场景二：企业管理流程自动化。采购审批、工单分派、库存预警、合规检查这些重复性决策占用了大量人力。衍灵嵌入到现有管理系统后，七乘二十四小时自动处理常规决策，仅异常情况升级到人工。内置边界控制确保每一步都在安全范围内。"),
    ("smarthome", "场景三：智能家居自适应编排。你回家，衍灵感知到你的出现自动调整灯光、温度、音乐场景。深夜检测到窗户未关，自动推送提醒。不是固定的 if else 规则，而是不断学习你的习惯、持续进化的智能管家。"),
    ("agriculture", "场景四：农业养殖环境智能调控。温室的温度湿度、养殖场的气体浓度、鱼塘的溶氧量衍灵连接各类传感器，在边缘侧实时决策通风、遮阳、投喂等动作，即使断网也能自主运行。"),
    ("howitworks", "如何工作？衍灵以固定 tick 运行感知、认知、行动、进化四阶段循环。感知层接入任意传感器和数据源认知层支持 L L M 驱动和规则驱动两种模式行动层输出到任意执行器进化层每次 tick 后轻量学习，定期深度自我改进。"),
    ("architecture", "衍灵的核心设计特点是可嵌入。作为 Python 库 import 到你的项目中，一行代码即可启动。也可独立进程运行，通过 A P I 与你的系统通信。边界控制确保安全，插件系统让你扩展，事件总线让你观察一切。"),
    ("roadmap", "路线图：本月发布 v 零点一开源版本，第三季度完善插件系统和规则自动生成，第四季度推出企业版，明年第一季度发布多节点集群和衍灵 Hub 云服务。"),
    ("closing", "衍灵 — 让系统拥有生命。无论是 I o T 设备、企业系统还是智能空间，衍灵都能赋予它们自主感知和进化的能力。加入我们，开启自主系统的新时代。"),
]

async def gen_one(slug: str, text: str):
    out = Path(OUT) / f"narration_{slug}.mp3"
    communicate = edge_tts.Communicate(text, VOICE, rate="+5%")
    await communicate.save(str(out))
    print(f"  ✓ {out.name}")

async def main():
    print("生成场景驱动版语音解说...")
    tasks = [gen_one(slug, text) for slug, text in NARRATIONS]
    await asyncio.gather(*tasks)
    print(f"\n全部语音已保存到 {OUT}/")

if __name__ == "__main__":
    asyncio.run(main())
