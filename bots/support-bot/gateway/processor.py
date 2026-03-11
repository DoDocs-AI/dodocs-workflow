"""Dequeues messages and invokes Claude CLI for processing."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from message import Message, Platform
from dispatcher import Dispatcher

logger = logging.getLogger("processor")

PENDING_FILE = Path("/app/state/pending_conversations.json")
AUDIT_DIR = Path("/app/state/audit")


class Processor:
    def __init__(self, dispatcher: Dispatcher):
        self.dispatcher = dispatcher
        self._queue: asyncio.Queue[Message] = asyncio.Queue()
        self._running = False
        self._max_concurrent = int(os.environ.get("MAX_CLAUDE_CONCURRENT", "2"))
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        # Rate limiting: per-user, max 5 messages per 5 minutes
        self._user_timestamps: dict[str, list[float]] = defaultdict(list)

    async def enqueue(self, message: Message) -> None:
        """Add a message to the processing queue."""
        # In group chats, only respond when explicitly mentioned or a bug/problem is raised
        if not message.is_dm and not self._should_respond_in_group(message):
            logger.debug(
                "Skipping group message from %s in '%s' — not triggered",
                message.sender_username, message.chat_name,
            )
            return

        # Rate limit check
        user_key = f"{message.platform.value}:{message.sender_id}"
        now = time.time()
        timestamps = self._user_timestamps[user_key]
        # Remove entries older than 5 minutes
        timestamps[:] = [t for t in timestamps if now - t < 300]
        if len(timestamps) >= 5:
            logger.warning("Rate limited user %s (%s)", message.sender_username, user_key)
            return
        timestamps.append(now)

        self._audit_inbound(message)
        await self._queue.put(message)

    # Bot mention patterns and bug/problem keywords for group message filtering
    _BOT_MENTIONS = ("@dodocs_customer_support_bot", "/support", "/bot")
    _BUG_KEYWORDS = (
        "bug", "error", "problem", "issue", "broken", "crash", "fail",
        "not working", "doesn't work", "does not work", "баг", "ошибка",
        "не работает", "сломал", "проблема", "błąd", "nie działa",
    )

    def _should_respond_in_group(self, message: Message) -> bool:
        """Return True if the bot should respond to this group message.

        Triggers:
        1. Bot is explicitly mentioned (@dodocs_customer_support_bot, /support, /bot)
        2. Message contains bug/problem keywords (indicates an issue being reported)
        3. Message is a reply to a bot's own message (conversation continuity)
        """
        text_lower = message.text.lower()

        # Explicit mention
        for mention in self._BOT_MENTIONS:
            if mention in text_lower:
                return True

        # Bug/problem keywords
        for keyword in self._BUG_KEYWORDS:
            if keyword in text_lower:
                return True

        return False

    async def start(self) -> None:
        self._running = True
        logger.info("Processor started (max_concurrent=%d)", self._max_concurrent)
        while self._running:
            try:
                # Collect messages in a batch window (2 seconds)
                batch: list[Message] = []
                try:
                    msg = await asyncio.wait_for(self._queue.get(), timeout=5.0)
                    batch.append(msg)
                    # Drain any immediately available messages
                    while not self._queue.empty() and len(batch) < 10:
                        batch.append(self._queue.get_nowait())
                except asyncio.TimeoutError:
                    continue

                if batch:
                    await self._process_batch(batch)
            except Exception:
                logger.exception("Processor loop error")
                await asyncio.sleep(5)

    async def stop(self) -> None:
        self._running = False

    async def _process_batch(self, batch: list[Message]) -> None:
        """Process a batch of messages through Claude CLI."""
        async with self._semaphore:
            batch_data = {
                "messages": [m.to_dict() for m in batch],
                "timestamp": datetime.utcnow().isoformat(),
            }
            batch_file = Path("/app/state/current_batch.json")
            batch_file.write_text(json.dumps(batch_data, indent=2))

            logger.info(
                "Processing batch of %d message(s) from %s",
                len(batch),
                ", ".join(m.sender_username for m in batch),
            )

            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, self._invoke_claude, str(batch_file)
                )
                await self._handle_result(result, batch)
            except Exception:
                logger.exception("Claude invocation failed")

    def _invoke_claude(self, batch_file: str) -> Optional[dict]:
        """Run Claude CLI with the /support command."""
        try:
            proc = subprocess.run(
                [
                    "claude",
                    "--dangerously-skip-permissions",
                    "-p",
                    f'/support --batch-file "{batch_file}"',
                    "--output-format",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                cwd="/app",
            )

            if proc.returncode != 0:
                logger.error("Claude CLI exited with code %d: %s", proc.returncode, proc.stderr[:500])
                return None

            # Parse JSON output — Claude CLI wraps output in {"type":"result","result":"..."}
            try:
                output = json.loads(proc.stdout)
            except json.JSONDecodeError:
                return {"type": "text", "content": proc.stdout}

            # Extract the actual result text from Claude CLI envelope
            result_text = output.get("result", "")
            if not result_text:
                return {"type": "text", "content": proc.stdout}

            # Try to extract JSON actions block from the result text
            actions = self._extract_actions(result_text)
            if actions:
                return {"actions": actions}
            return {"type": "text", "content": result_text}

        except subprocess.TimeoutExpired:
            logger.error("Claude CLI timed out after 300s")
            return None
        except Exception:
            logger.exception("Failed to invoke Claude CLI")
            return None

    @staticmethod
    def _extract_actions(text: str) -> list[dict] | None:
        """Extract JSON actions from Claude's result text.

        Claude embeds actions as a ```json code block inside its response.
        """
        import re
        # Look for JSON code block containing "actions"
        pattern = r'```json\s*\n(\{[^`]*"actions"\s*:\s*\[.*?\].*?\})\s*\n```'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                return data.get("actions", [])
            except json.JSONDecodeError:
                pass

        # Fallback: look for raw JSON object with actions
        pattern2 = r'(\{[^{}]*"actions"\s*:\s*\[.*?\]\s*\})'
        match2 = re.search(pattern2, text, re.DOTALL)
        if match2:
            try:
                data = json.loads(match2.group(1))
                return data.get("actions", [])
            except json.JSONDecodeError:
                pass

        return None

    async def _handle_result(self, result: Optional[dict], batch: list[Message]) -> None:
        """Parse Claude's response and route actions."""
        if not result:
            # On failure, send a generic error to each sender
            for msg in batch:
                await self.dispatcher.send(
                    msg.platform,
                    msg.chat_id,
                    "Sorry, I encountered an error processing your message. A team member has been notified.",
                    reply_to=msg.message_id if msg.platform == Platform.TELEGRAM else None,
                    thread_id=msg.thread_id if msg.platform == Platform.SLACK else None,
                )
            return

        # Handle structured actions from Claude
        actions = result.get("actions", [])
        if actions:
            for action in actions:
                await self._execute_action(action)
        elif result.get("content"):
            # Plain text response — reply to the first message
            if batch:
                msg = batch[0]
                await self.dispatcher.send(
                    msg.platform,
                    msg.chat_id,
                    result["content"],
                    reply_to=msg.message_id if msg.platform == Platform.TELEGRAM else None,
                    thread_id=msg.thread_id if msg.platform == Platform.SLACK else None,
                )

    async def _execute_action(self, action: dict) -> None:
        """Execute a single action from Claude's response."""
        action_type = action.get("type")

        if action_type == "reply":
            platform = Platform(action["platform"])
            await self.dispatcher.send(
                platform,
                str(action["chat_id"]),
                action["text"],
                reply_to=str(action.get("reply_to", "")) or None,
                thread_id=action.get("thread_id"),
            )
        elif action_type == "escalate":
            # Forward to escalation channel
            escalation_chat = os.environ.get("ESCALATION_TELEGRAM_CHAT_ID")
            if escalation_chat:
                await self.dispatcher.send(
                    Platform.TELEGRAM,
                    escalation_chat,
                    action.get("text", "Escalation triggered"),
                )
            escalation_slack = os.environ.get("ESCALATION_SLACK_CHANNEL")
            if escalation_slack:
                await self.dispatcher.send(
                    Platform.SLACK,
                    escalation_slack,
                    action.get("text", "Escalation triggered"),
                )
        elif action_type == "save_pending":
            self._save_pending(action.get("data", {}))

    def _save_pending(self, data: dict) -> None:
        """Save a pending conversation to state."""
        try:
            existing = json.loads(PENDING_FILE.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            existing = {"conversations": []}

        if "conversations" not in existing:
            existing["conversations"] = []

        existing["conversations"].append(data)
        PENDING_FILE.write_text(json.dumps(existing, indent=2))

    def _audit_inbound(self, msg: Message) -> None:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        log_file = AUDIT_DIR / f"{datetime.utcnow():%Y-%m-%d}.jsonl"
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "direction": "inbound",
            "platform": msg.platform.value,
            "chat_id": msg.chat_id,
            "sender": msg.sender_username,
            "text": msg.text[:500],
        }
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
