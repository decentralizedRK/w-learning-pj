import requests
from loguru import logger

from config.settings import settings

MAX_MESSAGE_LEN = 4096


def send_telegram(message: str) -> bool:
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id

    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for attempt in range(2):
        try:
            resp = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": message[:MAX_MESSAGE_LEN],
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                logger.debug("Telegram message sent")
                return True
            logger.warning(f"Telegram HTTP {resp.status_code}: {resp.text[:200]}")
        except requests.RequestException as e:
            logger.warning(f"Telegram attempt {attempt + 1} failed: {e}")

    return False
