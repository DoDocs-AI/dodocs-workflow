"""Sends replies back to Telegram and Slack."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import aiohttp

from message import Platform

logger = logging.getLogger("dispatcher")

AUDIT_DIR = Path("/app/state/audit")


class Dispatcher:
    def __init__(self):
        self.telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()

    async def stop(self) -> None:
        if self._session:
            await self._session.close()

    async def send(
        self,
        platform: Platform,
        chat_id: str,
        text: str,
        reply_to: str | None = None,
        thread_id: str | None = None,
    ) -> bool:
        """Send a message to the specified platform."""
        success = False
        if platform == Platform.TELEGRAM:
            success = await self._send_telegram(chat_id, text, reply_to)
        elif platform == Platform.SLACK:
            success = await self._send_slack(chat_id, text, thread_id)

        self._audit_log(platform, chat_id, text, success)
        return success

    async def _send_telegram(
        self, chat_id: str, text: str, reply_to: str | None = None
    ) -> bool:
        if not self.telegram_token or not self._session:
            logger.error("Telegram not configured")
            return False

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload: dict = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if reply_to:
            payload["reply_to_message_id"] = reply_to

        for attempt in range(3):
            try:
                async with self._session.post(url, json=payload) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        return True
                    # Rate limited
                    if resp.status == 429:
                        retry_after = data.get("parameters", {}).get("retry_after", 5)
                        logger.warning("Telegram rate limited, waiting %ds", retry_after)
                        await _sleep(retry_after)
                        continue
                    logger.error("Telegram API error: %s", data)
                    return False
            except Exception:
                logger.exception("Telegram send error (attempt %d)", attempt + 1)
                await _sleep(2 ** attempt)

        return False

    async def _send_slack(
        self, channel: str, text: str, thread_ts: str | None = None
    ) -> bool:
        if not self.slack_token or not self._session:
            logger.error("Slack not configured")
            return False

        url = "https://slack.com/api/chat.postMessage"
        headers = {"Authorization": f"Bearer {self.slack_token}"}
        payload: dict = {
            "channel": channel,
            "text": text,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts

        for attempt in range(3):
            try:
                async with self._session.post(url, json=payload, headers=headers) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        return True
                    if data.get("error") == "ratelimited":
                        retry_after = int(resp.headers.get("Retry-After", "5"))
                        logger.warning("Slack rate limited, waiting %ds", retry_after)
                        await _sleep(retry_after)
                        continue
                    logger.error("Slack API error: %s", data)
                    return False
            except Exception:
                logger.exception("Slack send error (attempt %d)", attempt + 1)
                await _sleep(2 ** attempt)

        return False

    def _audit_log(
        self, platform: Platform, chat_id: str, text: str, success: bool
    ) -> None:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        log_file = AUDIT_DIR / f"{datetime.utcnow():%Y-%m-%d}.jsonl"
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "direction": "outbound",
            "platform": platform.value,
            "chat_id": chat_id,
            "text": text[:500],
            "success": success,
        }
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
