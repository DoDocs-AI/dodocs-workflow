"""DoDocs Support Bot — Gateway entry point.

Starts Telegram poller, Slack webhook server, and message processor.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from telegram_poller import TelegramPoller
from slack_receiver import SlackReceiver
from processor import Processor
from dispatcher import Dispatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("gateway")


async def main() -> None:
    logger.info("DoDocs Support Bot Gateway starting...")

    # Initialize components
    dispatcher = Dispatcher()
    await dispatcher.start()

    processor = Processor(dispatcher)

    poll_interval = int(os.environ.get("POLL_INTERVAL", "30"))

    # Telegram poller (required)
    telegram = None
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        telegram = TelegramPoller(
            on_message=processor.enqueue,
            poll_interval=poll_interval,
        )
        logger.info("Telegram poller configured (interval=%ds)", poll_interval)
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram disabled")

    # Slack receiver (optional)
    slack = SlackReceiver(on_message=processor.enqueue)

    # Start all components
    tasks: list[asyncio.Task] = []

    tasks.append(asyncio.create_task(processor.start(), name="processor"))

    if telegram:
        tasks.append(asyncio.create_task(telegram.start(), name="telegram"))

    if os.environ.get("SLACK_BOT_TOKEN"):
        tasks.append(asyncio.create_task(slack.start(), name="slack"))

    logger.info("Gateway running. Components: %s", ", ".join(t.get_name() for t in tasks))

    # Graceful shutdown
    stop_event = asyncio.Event()

    def handle_signal() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    await stop_event.wait()

    # Cleanup
    logger.info("Shutting down...")
    await processor.stop()
    if telegram:
        await telegram.stop()
    await slack.stop()
    await dispatcher.stop()

    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info("Gateway stopped.")


if __name__ == "__main__":
    asyncio.run(main())
