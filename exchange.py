import ccxt
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from config import Config

logger = logging.getLogger(__name__)

TIMEFRAME_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}


class BinanceFutures:
    def __init__(self, config: Config):
        self.config = config
        self.exchange = ccxt.binanceusdm({
            "apiKey": config.binance_api_key,
            "secret": config.binance_secret,
            "enableRateLimit": True,
            "timeout": 30000,
            "options": {"defaultType": "future"},
        })

    def _sync_fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100):
        return self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> list:
        return await asyncio.wait_for(
            asyncio.to_thread(self._sync_fetch_ohlcv, symbol, timeframe, limit), timeout=20
        )

    async def fetch_and_validate(self, symbol: str, tf: str, limit: int = 100) -> list:
        raw = await self.fetch_ohlcv(symbol, tf, limit=limit)

        if raw is None:
            logger.warning(f"[{symbol} {tf}] fetch_ohlcv returned None")
            return []

        tf_ms = TIMEFRAME_MS.get(tf, 0)
        if tf_ms == 0 or len(raw) < 2:
            return raw

        gaps = []
        for i in range(1, len(raw)):
            expected = raw[i - 1][0] + tf_ms
            if raw[i][0] != expected:
                gaps.append((raw[i - 1][0], raw[i][0], raw[i][0] - expected))

        if gaps:
            logger.warning(f"[{symbol} {tf}] {len(gaps)} gap(s) in candle history, skipping")
            return []

    async def fetch_tickers(self) -> dict:
        return await asyncio.wait_for(
            asyncio.to_thread(self._sync_fetch_tickers), timeout=45
        )

    def _sync_fetch_tickers(self):
        return self.exchange.fetch_tickers()

    async def get_liquid_pairs(self, min_volume_usd: float) -> list[str]:
        tickers = await self.fetch_tickers()
        now = datetime.now(timezone.utc)
        liquid = []
        total_usdt = 0

        day_fraction = max((now.hour + now.minute / 60 + now.second / 3600) / 24, 0.01)
        early_day = day_fraction < 0.25

        for symbol, ticker in tickers.items():
            if not symbol.endswith("USDT"):
                continue
            total_usdt += 1

            quote_volume = ticker.get("quoteVolume")
            if quote_volume is None:
                continue

            projected = quote_volume / day_fraction

            if projected >= min_volume_usd:
                liquid.append(symbol)
                continue

            if early_day:
                prev_day_volume = await self._get_prev_day_volume(symbol)
                if prev_day_volume and prev_day_volume >= min_volume_usd:
                    liquid.append(symbol)

        logger.info(f"Ticker returned {total_usdt} USDT pairs, {len(liquid)} passed volume filter "
                    f"(day_fraction={day_fraction:.2f})")
        return liquid

    async def _get_prev_day_volume(self, symbol: str) -> Optional[float]:
        try:
            candles = await self.fetch_ohlcv(symbol, "1d", limit=2)
            if len(candles) >= 2:
                return candles[-2][5]
        except Exception:
            pass
        return None

    async def close(self):
        await asyncio.to_thread(self.exchange.close)
