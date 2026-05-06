import asyncio
import logging
import sys
from datetime import datetime, timezone

from config import Config
from exchange import BinanceFutures, TIMEFRAME_MS
from patterns import detect_patterns
from chart import generate_chart
from alerts import TelegramAlerter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("star_bot")

CHART_CONTEXT_CANDLES = 40
PATTERN_CHECK_LIMIT = 50


class StarBot:
    def __init__(self, config: Config):
        self.config = config
        self.exchange = BinanceFutures(config)
        self.alerter = TelegramAlerter(config)
        self.running = True
        self.liquid_pairs: list[str] = []
        self.last_liquid_refresh = 0.0
        self.last_check: dict[str, int] = {}
        self.alerted: set[tuple[str, str, int]] = set()

    async def start(self):
        logger.info("=== Star Bot starting ===")
        errors = self.config.validate()
        if errors:
            for e in errors:
                logger.error(e)
            logger.error("Fill in the .env file (see .env.example) and restart the bot")
            return

        await self._refresh_liquid_pairs()
        logger.info(f"Liquid pairs: {len(self.liquid_pairs)}")
        await self.alerter.send_startup(len(self.liquid_pairs))

        for tf in self.config.timeframes:
            asyncio.create_task(self._timeframe_worker(tf))

        while self.running:
            await asyncio.sleep(30)
            now = asyncio.get_event_loop().time()
            if now - self.last_liquid_refresh > 1800:
                await self._refresh_liquid_pairs()
                logger.info(f"Pair list refreshed: {len(self.liquid_pairs)} pairs")

    async def _refresh_liquid_pairs(self):
        try:
            self.liquid_pairs = await self.exchange.get_liquid_pairs(self.config.min_volume_usd)
            self.last_liquid_refresh = asyncio.get_event_loop().time()
        except Exception as e:
            logger.error(f"Error fetching pairs: {e}")

    async def _timeframe_worker(self, tf: str):
        tf_ms = TIMEFRAME_MS[tf]
        logger.info(f"Worker [{tf}] started")

        while self.running:
            try:
                now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                candle_ts = now_ms - (now_ms % tf_ms)

                if tf in self.last_check and self.last_check[tf] >= candle_ts:
                    await asyncio.sleep(self.config.check_interval_sec)
                    continue

                self.last_check[tf] = candle_ts
                logger.info(f"[{tf}] New candle closed ({datetime.fromtimestamp(candle_ts/1000, tz=timezone.utc)}), "
                            f"scanning {len(self.liquid_pairs)} pairs...")

                if len(self.liquid_pairs) == 0:
                    continue

                found = 0
                for i, symbol in enumerate(self.liquid_pairs):
                    if not self.running:
                        break
                    if i > 0 and i % 10 == 0:
                        await asyncio.sleep(0.5)

                    try:
                        results = await self._check_symbol(symbol, tf, candle_ts, tf_ms)
                        for r in results:
                            alert_key = (symbol, tf, candle_ts)
                            if alert_key in self.alerted:
                                continue
                            self.alerted.add(alert_key)
                            logger.info(f">>> PATTERN: {r.pattern.value} {symbol} {tf} "
                                        f"({r.confidence}, score={r.score:.2f})")

                            chart_candles = await self._fetch_chart_candles(symbol, tf)
                            img = None
                            if chart_candles:
                                img = await asyncio.to_thread(
                                    generate_chart, chart_candles, symbol, tf, r.pattern
                                )

                            if img:
                                await self.alerter.send_alert(r, img.getvalue())
                            found += 1
                            await asyncio.sleep(0.3)
                    except Exception as e:
                        logger.debug(f"Error checking {symbol} {tf}: {e}")
                        continue

                logger.info(f"[{tf}] Scan done, patterns found: {found}")

            except Exception as e:
                logger.error(f"[{tf}] Worker error: {e}")
                await asyncio.sleep(5)

    async def _check_symbol(self, symbol: str, tf: str, candle_ts: int, tf_ms: int) -> list:
        candles = await self.exchange.fetch_and_validate(symbol, tf, limit=PATTERN_CHECK_LIMIT)

        c3_idx = None
        for i in range(len(candles) - 1, -1, -1):
            if candles[i][0] == candle_ts:
                c3_idx = i
                break

        if c3_idx is None or c3_idx < 19:
            return []

        window = candles[:c3_idx + 1]
        price = candles[c3_idx][4] if c3_idx < len(candles) else 0
        min_atr = price * self.config.min_atr_multiplier
        return detect_patterns(
            candles=window,
            symbol=symbol,
            timeframe=tf,
            tf_ms=tf_ms,
            min_atr=min_atr,
        )

    async def _fetch_chart_candles(self, symbol: str, tf: str) -> list | None:
        try:
            return await self.exchange.fetch_ohlcv(symbol, tf, limit=3 + CHART_CONTEXT_CANDLES)
        except Exception as e:
            logger.warning(f"Failed to fetch chart candles for {symbol} {tf}: {e}")
            return None

    async def stop(self):
        self.running = False
        await self.alerter.close()
        logger.info("Bot stopped")


async def main():
    print(">>> Initializing config...", flush=True)
    config = Config()
    print(">>> Creating bot...", flush=True)
    bot = StarBot(config)
    print(">>> Bot created, starting...", flush=True)

    try:
        await bot.start()
    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
    finally:
        await bot.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted", flush=True)
