"""内置基线模型 — 衍灵的保底模型，不可变、始终可用。

基线模型特性：
- 固定为 TinyLlama (Apache 2.0, 1.1B, 637MB)
- 不可切换、不可删除
- 作为 LLM 不可用时的降级目标
- 后续可替换为自蒸馏模型（保持接口不变）
"""
from __future__ import annotations

import logging

log = logging.getLogger("yanling.baseline")

# 内置基线模型定义（不可变）
BASELINE_MODEL = {
    "id": "yanling-baseline",
    "name": "衍灵基线 (TinyLlama)",
    "model": "tinyllama:latest",
    "provider": "ollama",
    "base_url": "http://localhost:11434",
    "license": "Apache 2.0",
    "description": "内置保底模型，始终可用",
    # 后续替换为自蒸馏模型时只需改这里：
    # "model": "yanling-distilled-v1",
    # "provider": "ollama",
}


def create_baseline_adapter():
    """创建基线模型适配器实例。"""
    from yanling.adapters.llm.ollama import OllamaAdapter
    return OllamaAdapter(
        model=BASELINE_MODEL["model"],
        base_url=BASELINE_MODEL["base_url"],
        timeout=60.0,
    )


async def is_baseline_available() -> bool:
    """检查基线模型是否可用（Ollama 已加载）。"""
    adapter = create_baseline_adapter()
    try:
        return await adapter.is_available()
    except Exception:
        return False
    finally:
        await adapter._client.aclose()
