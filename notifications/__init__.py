from loguru import logger

from notifications.telegram import send_telegram


def notify(message: str) -> None:
    """Send notification via Telegram (if configured) and log it."""
    logger.info(f"Notification: {message[:100]}...")
    send_telegram(message)
