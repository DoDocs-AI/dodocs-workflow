"""Normalized message dataclass for cross-platform message handling."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Platform(Enum):
    TELEGRAM = "telegram"
    SLACK = "slack"


@dataclass
class Message:
    """Platform-agnostic message representation."""

    platform: Platform
    # Unique message ID on the platform
    message_id: str
    # Chat/channel ID where the message was sent
    chat_id: str
    # Display name of the chat/channel
    chat_name: str
    # Sender info
    sender_username: str
    sender_display_name: str
    sender_id: str
    # Message content
    text: str
    # Timestamp (unix)
    timestamp: float = field(default_factory=time.time)
    # Threading
    thread_id: Optional[str] = None
    # Whether the message is a DM
    is_dm: bool = False
    # Raw platform-specific payload
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "platform": self.platform.value,
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "chat_name": self.chat_name,
            "sender_username": self.sender_username,
            "sender_display_name": self.sender_display_name,
            "sender_id": self.sender_id,
            "text": self.text,
            "timestamp": self.timestamp,
            "thread_id": self.thread_id,
            "is_dm": self.is_dm,
        }

    @staticmethod
    def from_telegram_update(update: dict) -> Optional[Message]:
        """Parse a Telegram update into a Message."""
        msg = update.get("message")
        if not msg or not msg.get("text"):
            return None

        sender = msg.get("from", {})
        chat = msg.get("chat", {})
        is_dm = chat.get("type") == "private"

        return Message(
            platform=Platform.TELEGRAM,
            message_id=str(msg["message_id"]),
            chat_id=str(chat["id"]),
            chat_name=chat.get("title", chat.get("first_name", "DM")),
            sender_username=sender.get("username", ""),
            sender_display_name=f"{sender.get('first_name', '')} {sender.get('last_name', '')}".strip(),
            sender_id=str(sender.get("id", "")),
            text=msg["text"],
            timestamp=msg.get("date", time.time()),
            is_dm=is_dm,
            raw=update,
        )

    @staticmethod
    def from_slack_event(event: dict) -> Optional[Message]:
        """Parse a Slack event into a Message."""
        if event.get("type") != "message" or event.get("subtype"):
            return None

        text = event.get("text", "")
        if not text:
            return None

        return Message(
            platform=Platform.SLACK,
            message_id=event.get("ts", ""),
            chat_id=event.get("channel", ""),
            chat_name=event.get("channel", ""),
            sender_username=event.get("user", ""),
            sender_display_name=event.get("user", ""),
            sender_id=event.get("user", ""),
            text=text,
            timestamp=float(event.get("ts", time.time())),
            thread_id=event.get("thread_ts"),
            is_dm=event.get("channel_type") == "im",
            raw=event,
        )
