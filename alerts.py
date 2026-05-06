import aiohttp
import asyncio
import logging

from config import Config
from patterns import PatternResult

logger = logging.getLogger(__name__)

_FIRE_MAP = {
    "1h": "\U0001f525",
    "4h": "\U0001f525\U0001f525",
    "12h": "\U0001f525\U0001f525\U0001f525",
    "1d": "\U0001f525\U0001f525\U0001f525\U0001f525",
}


def _fire(tf: str) -> str:
    return _FIRE_MAP.get(tf, "\U0001f525")


def _tf_display(tf: str) -> str:
    mapping = {
        "1m": "1\u043c", "5m": "5\u043c", "15m": "15\u043c", "30m": "30\u043c",
        "1h": "1\u0447", "2h": "2\u0447", "4h": "4\u0447", "6h": "6\u0447",
        "12h": "12\u0447", "1d": "1\u0434", "1w": "1\u043d",
    }
    return mapping.get(tf, tf)


class TelegramAlerter:
    def __init__(self, config: Config):
        self.token = config.telegram_bot_token
        self.chat_id = config.telegram_chat_id
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def make_caption(self, pattern: PatternResult) -> str:
        fire = _fire(pattern.timeframe)
        tf_d = _tf_display(pattern.timeframe)
        score_tag = f" [score:{pattern.score:.2f}]" if hasattr(pattern, "score") else ""
        return f"{fire} #{pattern.symbol} {tf_d}{score_tag}\n{pattern.description}"

    async def send_alert(self, pattern: PatternResult, image_bytes: bytes) -> bool:
        caption = self.make_caption(pattern)
        return await self._send_photo(image_bytes, caption)

    async def send_startup(self, pairs_count: int) -> bool:
        tf_list = ["1d", "12h", "4h", "1h"]
        msg = (
            "\U0001f916 \u0411\u043e\u0442 \u0437\u0430\u043f\u0443\u0449\u0435\u043d\n"
            f"\u041c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433 {pairs_count} \u043b\u0438\u043a\u0432\u0438\u0434\u043d\u044b\u0445 \u043f\u0430\u0440\n"
            "\u041f\u0430\u0442\u0442\u0435\u0440\u043d\u044b: \u0423\u0442\u0440\u0435\u043d\u043d\u044f\u044f/\u0412\u0435\u0447\u0435\u0440\u043d\u044f\u044f \u0437\u0432\u0435\u0437\u0434\u0430\n"
            "\u0422\u0430\u0439\u043c\u0444\u0440\u0435\u0439\u043c\u044b: " + ", ".join(_tf_display(t) for t in tf_list)
        )
        return await self._send_message(msg)

    async def _send_photo(self, image_bytes: bytes, caption: str, retries: int = 3) -> bool:
        session = await self._get_session()
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"

        form = aiohttp.FormData()
        form.add_field("chat_id", self.chat_id)
        form.add_field("caption", caption)
        form.add_field("photo", image_bytes, filename="chart.png", content_type="image/png")

        for attempt in range(retries):
            try:
                async with session.post(url, data=form, timeout=30) as resp:
                    if resp.status == 200:
                        return True
                    body = await resp.text()
                    logger.warning(f"Telegram sendPhoto error {resp.status}: {body}")
            except Exception as e:
                logger.warning(f"Telegram sendPhoto attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return False

    async def _send_message(self, text: str, retries: int = 3) -> bool:
        session = await self._get_session()
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}

        for attempt in range(retries):
            try:
                async with session.post(url, json=payload, timeout=15) as resp:
                    if resp.status == 200:
                        return True
                    logger.warning(f"Telegram API error {resp.status}: {await resp.text()}")
            except Exception as e:
                logger.warning(f"Telegram send attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return False

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
