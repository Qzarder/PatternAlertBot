import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
    binance_secret: str = os.getenv("BINANCE_SECRET", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    min_volume_usd: float = float(os.getenv("MIN_VOLUME_USD", "20000000"))
    timeframes: list[str] = field(default_factory=lambda: os.getenv("TIMEFRAMES", "1d,12h,4h,1h").split(","))
    check_interval_sec: int = int(os.getenv("CHECK_INTERVAL_SEC", "60"))

    def validate(self) -> list[str]:
        errors = []
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN не задан в .env")
        if not self.telegram_chat_id:
            errors.append("TELEGRAM_CHAT_ID не задан в .env")
        return errors
