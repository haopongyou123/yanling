"""飞书通知适配器 — 发送消息到飞书群机器人."""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger("yanling.notify.feishu")


class FeishuNotifier:
    """飞书机器人通知。"""

    def __init__(self, webhook_url: str = "", timeout: float = 10.0):
        self._webhook_url = webhook_url or self._detect_webhook()
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    def _detect_webhook(self) -> str:
        import os
        return os.environ.get("FEISHU_WEBHOOK", "")

    async def send_text(self, text: str) -> bool:
        """发送纯文本消息。"""
        payload = {"msg_type": "text", "content": {"text": text}}
        return await self._post(payload)

    async def send_card(self, title: str, content: str, color: str = "blue") -> bool:
        """发送卡片消息。"""
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title[:128]},
                    "template": color,
                },
                "elements": [{"tag": "markdown", "content": content[:2000]}],
            },
        }
        return await self._post(payload)

    async def send_evolution_report(self, report: dict) -> bool:
        """发送进化报告。"""
        title = f"🧬 进化报告 tick #{report.get('total_ticks', '?')}"
        trend = report.get("performance", {}).get("trend", "unknown")
        patterns = report.get("top_patterns", [])
        adjustments = report.get("adjustments_made", 0)

        content = f"趋势: {trend}\n"
        content += f"调整次数: {adjustments}\n"
        if patterns:
            content += "\n高频模式:\n"
            for p in patterns[:5]:
                content += f"- {p['pattern']}: {p['count']}次\n"

        return await self.send_card(title, content)

    async def _post(self, payload: dict) -> bool:
        if not self._webhook_url:
            log.warning("飞书 webhook 未配置，跳过通知")
            return False
        try:
            resp = await self._client.post(self._webhook_url, json=payload)
            resp.raise_for_status()
            return True
        except Exception as e:
            log.error("飞书通知失败: %s", e)
            return False
