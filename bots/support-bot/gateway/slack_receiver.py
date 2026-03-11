"""Slack Events API webhook receiver."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Callable, Awaitable

from aiohttp import web

from message import Message

logger = logging.getLogger("slack_receiver")


class SlackReceiver:
    def __init__(
        self,
        on_message: Callable[[Message], Awaitable[None]],
        port: int = 8888,
    ):
        self.signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
        self.bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
        self.on_message = on_message
        self.port = port
        self._bot_user_id: str | None = None
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._seen_events: set[str] = set()

    def _verify_signature(self, body: bytes, timestamp: str, signature: str) -> bool:
        if not self.signing_secret:
            return True  # Skip verification if no secret configured
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return False
        sig_basestring = f"v0:{timestamp}:{body.decode()}"
        computed = "v0=" + hmac.new(
            self.signing_secret.encode(), sig_basestring.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed, signature)

    async def _handle_event(self, request: web.Request) -> web.Response:
        body = await request.read()
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "0")
        signature = request.headers.get("X-Slack-Signature", "")

        if not self._verify_signature(body, timestamp, signature):
            return web.Response(status=401, text="Invalid signature")

        payload = json.loads(body)

        # URL verification challenge
        if payload.get("type") == "url_verification":
            return web.json_response({"challenge": payload["challenge"]})

        # Event callback
        if payload.get("type") == "event_callback":
            event = payload.get("event", {})
            event_id = payload.get("event_id", "")

            # Deduplicate
            if event_id in self._seen_events:
                return web.Response(status=200, text="ok")
            self._seen_events.add(event_id)
            # Keep set bounded
            if len(self._seen_events) > 10000:
                self._seen_events = set(list(self._seen_events)[-5000:])

            # Ignore bot's own messages
            if event.get("bot_id") or event.get("user") == self._bot_user_id:
                return web.Response(status=200, text="ok")

            # Handle message and app_mention events
            if event.get("type") in ("message", "app_mention"):
                msg = Message.from_slack_event(event)
                if msg:
                    logger.info("Slack message from %s: %s", msg.sender_username, msg.text[:80])
                    await self.on_message(msg)

        return web.Response(status=200, text="ok")

    async def start(self) -> None:
        if not self.bot_token:
            logger.warning("SLACK_BOT_TOKEN not set — Slack receiver disabled")
            return

        self._app = web.Application()
        self._app.router.add_post("/slack/events", self._handle_event)
        self._app.router.add_get("/health", self._health)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        logger.info("Slack webhook server listening on port %d", self.port)

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "dodocs-support-bot"})

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
