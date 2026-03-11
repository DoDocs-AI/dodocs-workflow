"""Telegram Bot API long-polling message fetcher."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Callable, Awaitable

import aiohttp

from message import Message

logger = logging.getLogger("telegram_poller")

STATE_FILE = Path("/app/state/telegram_state.json")


class TelegramPoller:
    def __init__(
        self,
        on_message: Callable[[Message], Awaitable[None]],
        poll_interval: int = 30,
    ):
        self.bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"
        self.on_message = on_message
        self.poll_interval = poll_interval
        self._last_update_id = self._load_state()
        self._running = False

    def _load_state(self) -> int:
        try:
            data = json.loads(STATE_FILE.read_text())
            return data.get("last_update_id", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            return 0

    def _save_state(self) -> None:
        STATE_FILE.write_text(json.dumps({"last_update_id": self._last_update_id}))

    async def start(self) -> None:
        self._running = True
        logger.info("Telegram poller started (interval=%ds)", self.poll_interval)
        async with aiohttp.ClientSession() as session:
            # On first start (no saved state), skip all old messages
            if self._last_update_id == 0:
                await self._skip_old_messages(session)
            while self._running:
                try:
                    await self._poll(session)
                except Exception:
                    logger.exception("Telegram poll error")
                await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        self._running = False

    async def _skip_old_messages(self, session: aiohttp.ClientSession) -> None:
        """On first start, mark all pending messages as read without processing them."""
        url = f"{self.api_base}/getUpdates"
        params = {"offset": 0, "timeout": 1, "allowed_updates": '["message"]'}
        try:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
            results = data.get("result", [])
            if results:
                max_id = max(u.get("update_id", 0) for u in results)
                self._last_update_id = max_id
                self._save_state()
                logger.info("Skipped %d old Telegram message(s) on first start", len(results))
            else:
                logger.info("No old Telegram messages to skip")
        except Exception:
            logger.exception("Failed to skip old messages")

    async def _poll(self, session: aiohttp.ClientSession) -> None:
        offset = self._last_update_id + 1 if self._last_update_id > 0 else 0
        url = f"{self.api_base}/getUpdates"
        params = {
            "offset": offset,
            "timeout": 5,
            "allowed_updates": '["message"]',
        }

        async with session.get(url, params=params) as resp:
            data = await resp.json()

        if not data.get("ok"):
            logger.error("Telegram API error: %s", data)
            return

        results = data.get("result", [])
        if not results:
            return

        logger.info("Received %d Telegram update(s)", len(results))

        for update in results:
            update_id = update.get("update_id", 0)
            if update_id > self._last_update_id:
                self._last_update_id = update_id

            msg = Message.from_telegram_update(update)
            if msg:
                await self.on_message(msg)

        self._save_state()
