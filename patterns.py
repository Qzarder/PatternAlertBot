from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import logging

logger = logging.getLogger("patterns")


class PatternType(Enum):
    MORNING_STAR = "morning_star"
    EVENING_STAR = "evening_star"


@dataclass
class PatternResult:
    pattern: PatternType
    symbol: str
    timeframe: str
    confidence: str
    description: str
    score: float
    c3_timestamp: int = 0


# ============================================================================
# Индикаторы
# ============================================================================

def _closes(candles: List[List]) -> List[float]:
    return [c[4] for c in candles]


def _atr(candles: List[List], period: int = 14) -> float:
    if len(candles) < period + 1:
        period = len(candles) - 1
    if period < 1:
        return 0.0
    trs = []
    for i in range(1, period + 1):
        c = candles[-i]
        p = candles[-(i + 1)]
        high, low, close = c[2], c[3], c[4]
        prev_close = p[4]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs) / len(trs)


def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        diff = closes[-i] - closes[-(i + 1)]
        if diff > 0:
            gains += diff
        else:
            losses += abs(diff)
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))


def _ema(closes: List[float], period: int = 20) -> float:
    if len(closes) < period:
        return sum(closes) / len(closes) if closes else 0.0
    k = 2.0 / (period + 1.0)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return ema


def _avg_volume(candles: List[List], period: int = 20) -> float:
    if len(candles) < 2:
        return 0.0
    samples = candles[-period:] if len(candles) >= period else candles
    return sum(c[5] for c in samples if len(c) > 5) / len(samples)


def _history_valid(candles: List[List], tf_ms: int) -> bool:
    if len(candles) < 2:
        return True
    gaps = 0
    for i in range(1, len(candles)):
        if candles[i][0] - candles[i - 1][0] != tf_ms:
            gaps += 1
    return gaps <= 3


# ============================================================================
# Тренд по 5 свечам контекста
# ============================================================================

def _is_uptrend(ctx: List[List]) -> bool:
    if len(ctx) < 5:
        return False
    closes = [c[4] for c in ctx]
    bullish = sum(1 for c in ctx if c[4] > c[1])
    return bullish >= 4 and closes[-1] > closes[0] * 1.005


def _is_downtrend(ctx: List[List]) -> bool:
    if len(ctx) < 5:
        return False
    closes = [c[4] for c in ctx]
    bearish = sum(1 for c in ctx if c[4] < c[1])
    return bearish >= 4 and closes[-1] < closes[0] * 0.995


# ============================================================================
# Основной детектор — только последняя свеча окна
# ============================================================================

def detect_patterns(
    candles: List[List],
    symbol: str,
    timeframe: str,
    tf_ms: int = 0,
    min_atr: float = 0.0,
) -> List[PatternResult]:
    if len(candles) < 25:
        return []

    cl = _closes(candles)
    atr_val = _atr(candles, 14)
    rsi_val = _rsi(cl, 14)
    ema_val = _ema(cl, 20)
    avg_vol = _avg_volume(candles, 20)

    if min_atr > 0 and atr_val < min_atr:
        return []

    if tf_ms > 0 and not _history_valid(candles, tf_ms):
        return []

    # Паттерн: candles[-3]=C1, candles[-2]=C2, candles[-1]=C3
    # Тренд: candles[-8:-3] = 5 свечей перед C1
    c1 = candles[-3]
    c2 = candles[-2]
    c3 = candles[-1]
    trend_ctx = candles[-8:-3] if len(candles) >= 8 else candles[:-3]

    if tf_ms > 0:
        if (c2[0] - c1[0] != tf_ms) or (c3[0] - c2[0] != tf_ms):
            return []

    price = c3[4]
    has_volume = len(c1) > 5 and all(len(c) > 5 for c in [c1, c2, c3])

    results = []
    ms = _check_morning_star(
        trend_ctx, c1, c2, c3,
        symbol, timeframe, atr_val, rsi_val, ema_val,
        avg_vol if has_volume else 0.0, has_volume, price
    )
    if ms:
        ms.c3_timestamp = c3[0]
        results.append(ms)

    es = _check_evening_star(
        trend_ctx, c1, c2, c3,
        symbol, timeframe, atr_val, rsi_val, ema_val,
        avg_vol if has_volume else 0.0, has_volume, price
    )
    if es:
        es.c3_timestamp = c3[0]
        results.append(es)

    return results


# ============================================================================
# Morning Star
# ============================================================================

def _check_morning_star(
    trend_ctx, c1, c2, c3,
    symbol: str, timeframe: str,
    atr: float, rsi: float, ema: float,
    avg_vol: float, has_volume: bool, price: float
) -> Optional[PatternResult]:
    o1, h1, l1, cl1 = c1[1], c1[2], c1[3], c1[4]
    o2, h2, l2, cl2 = c2[1], c2[2], c2[3], c2[4]
    o3, h3, l3, cl3 = c3[1], c3[2], c3[3], c3[4]

    body1 = abs(cl1 - o1)
    body2 = abs(cl2 - o2)
    body3 = abs(cl3 - o3)
    hl1 = h1 - l1

    if body1 == 0 or body3 == 0 or hl1 == 0:
        return None
    if cl1 >= o1:
        return None
    if cl3 <= o3:
        return None

    lower_wick2 = min(o2, cl2) - l2
    upper_wick2 = h2 - max(o2, cl2)

    if atr == 0:
        return None
    min_body = max(atr * 0.5, price * 0.001)
    if body1 < min_body or body3 < min_body:
        return None

    # C2: тело крошечное, строго
    if body2 > body1 * 0.15:
        return None
    if body2 > atr * 0.1:
        return None

    # C2 позиция: строго внизу C1
    if max(o2, cl2) > cl1:
        return None

    c1_mid = (h1 + l1) / 2
    if max(o2, cl2) > c1_mid:
        return None

    # C2: должна быть "звездой" — длинная нижняя тень (hammer)
    # верхняя тень для MS нежелательна — продавцы давят сверху
    is_star = lower_wick2 > body2 * 1.5
    if not is_star:
        return None

    # C3: подтверждение
    penetration = (cl3 - cl1) / body1
    if penetration < 0.6:
        return None
    if body3 < body1 * 0.5:
        return None

    # EMA: жёстко — цена должна быть ниже EMA20 (перепроданность)
    if cl1 >= ema:
        # DEBUG: logger.debug(f"[MS {symbol}] REJECT EMA: cl1={cl1:.4f} ema={ema:.4f}")
        return None

    # Тренд
    if not _is_downtrend(trend_ctx):
        # DEBUG: logger.debug(f"[MS {symbol}] REJECT trend: ctx_len={len(trend_ctx)}")
        return None

    # Локальный минимум
    recent_low = min(c[3] for c in trend_ctx[-5:]) if len(trend_ctx) >= 5 else l1
    at_low = cl1 <= recent_low * 1.02

    # Scoring
    score = 0.5
    reasons = []

    if penetration >= 0.8:
        score += 0.15
        reasons.append("strong_pen")
    elif penetration >= 0.6:
        score += 0.05

    if cl3 > o1:
        score += 0.1
        reasons.append("engulfing")

    if rsi < 35:
        score += 0.15
        reasons.append(f"RSI={rsi:.0f}<35")
    elif rsi < 45:
        score += 0.05

    if is_star:
        score += 0.1
        reasons.append("star_wick")

    if at_low:
        score += 0.1
        reasons.append("at_local_low")

    if has_volume:
        v1, v2, v3 = c1[5], c2[5], c3[5]
        if v3 > v2 * 1.5 and v1 > avg_vol:
            score += 0.15
            reasons.append("volume")
        elif v3 > v2:
            score += 0.05

    confidence = "high" if score >= 0.85 else ("medium" if score >= 0.65 else "low")

    description = _make_description(
        "\u2600\ufe0f \u0423\u0442\u0440\u0435\u043d\u043d\u044f\u044f \u0437\u0432\u0435\u0437\u0434\u0430",
        confidence, score, reasons,
        o1, cl1, o2, cl2, o3, cl3, atr, rsi
    )
    return PatternResult(
        pattern=PatternType.MORNING_STAR,
        symbol=symbol,
        timeframe=timeframe,
        confidence=confidence,
        description=description,
        score=round(score, 3),
    )


# ============================================================================
# Evening Star
# ============================================================================

def _check_evening_star(
    trend_ctx, c1, c2, c3,
    symbol: str, timeframe: str,
    atr: float, rsi: float, ema: float,
    avg_vol: float, has_volume: bool, price: float
) -> Optional[PatternResult]:
    o1, h1, l1, cl1 = c1[1], c1[2], c1[3], c1[4]
    o2, h2, l2, cl2 = c2[1], c2[2], c2[3], c2[4]
    o3, h3, l3, cl3 = c3[1], c3[2], c3[3], c3[4]

    body1 = abs(cl1 - o1)
    body2 = abs(cl2 - o2)
    body3 = abs(cl3 - o3)
    hl1 = h1 - l1

    if body1 == 0 or body3 == 0 or hl1 == 0:
        return None
    if cl1 <= o1:
        return None
    if cl3 >= o3:
        return None

    upper_wick2 = h2 - max(o2, cl2)
    lower_wick2 = min(o2, cl2) - l2

    if atr == 0:
        return None
    min_body = max(atr * 0.5, price * 0.001)
    if body1 < min_body or body3 < min_body:
        return None

    # C2: тело крошечное
    if body2 > body1 * 0.15:
        return None
    if body2 > atr * 0.1:
        return None

    # C2 позиция: строго наверху C1
    if max(o2, cl2) < cl1:
        return None

    c1_mid = (h1 + l1) / 2
    if min(o2, cl2) < c1_mid:
        return None

    # C2: shooting star или doji
    is_star = (upper_wick2 > body2 * 1.5) or (lower_wick2 > body2 * 1.5)
    if not is_star:
        return None

    # C3: подтверждение
    penetration = (cl1 - cl3) / body1
    if penetration < 0.6:
        return None
    if body3 < body1 * 0.5:
        return None

    # EMA: жёстко — цена должна быть выше EMA20 (перекупленность)
    if cl1 <= ema:
        # DEBUG: logger.debug(f"[ES {symbol}] REJECT EMA: cl1={cl1:.4f} ema={ema:.4f}")
        return None

    # Тренд
    if not _is_uptrend(trend_ctx):
        # DEBUG: logger.debug(f"[ES {symbol}] REJECT trend: ctx_len={len(trend_ctx)}")
        return None

    # Локальный максимум
    recent_high = max(c[2] for c in trend_ctx[-5:]) if len(trend_ctx) >= 5 else h1
    at_high = cl1 >= recent_high * 0.98

    # Scoring
    score = 0.5
    reasons = []

    if penetration >= 0.8:
        score += 0.15
        reasons.append("strong_pen")
    elif penetration >= 0.6:
        score += 0.05

    if cl3 < o1:
        score += 0.1
        reasons.append("engulfing")

    if rsi > 65:
        score += 0.15
        reasons.append(f"RSI={rsi:.0f}>65")
    elif rsi > 55:
        score += 0.05

    if is_star:
        score += 0.1
        reasons.append("star_wick")

    if at_high:
        score += 0.1
        reasons.append("at_local_high")

    if has_volume:
        v1, v2, v3 = c1[5], c2[5], c3[5]
        if v3 > v2 * 1.5 and v1 > avg_vol:
            score += 0.15
            reasons.append("volume")
        elif v3 > v2:
            score += 0.05

    confidence = "high" if score >= 0.85 else ("medium" if score >= 0.65 else "low")

    description = _make_description(
        "\U0001f319 \u0412\u0435\u0447\u0435\u0440\u043d\u044f\u044f \u0437\u0432\u0435\u0437\u0434\u0430",
        confidence, score, reasons,
        o1, cl1, o2, cl2, o3, cl3, atr, rsi
    )
    return PatternResult(
        pattern=PatternType.EVENING_STAR,
        symbol=symbol,
        timeframe=timeframe,
        confidence=confidence,
        description=description,
        score=round(score, 3),
    )


# ============================================================================
# Форматирование
# ============================================================================

def _make_description(
    name: str, confidence: str, score: float, reasons: List[str],
    o1: float, cl1: float, o2: float, cl2: float,
    o3: float, cl3: float, atr: float, rsi: float
) -> str:
    conf_emoji = "\U0001f7e2" if confidence == "high" else ("\U0001f7e1" if confidence == "medium" else "\U0001f534")
    body1 = abs(cl1 - o1)
    body2 = abs(cl2 - o2)
    body3 = abs(cl3 - o3)
    ratio = round(body3 / body1, 2) if body1 else 0
    reasons_str = ", ".join(reasons) if reasons else "base"

    return (
        f"{name} {conf_emoji} {confidence.upper()} (score:{score:.2f})\n"
        f"\u0424\u0430\u043a\u0442\u043e\u0440\u044b: {reasons_str}\n"
        f"C1: O={o1:.4f} C={cl1:.4f} body={body1:.4f}\n"
        f"C2: O={o2:.4f} C={cl2:.4f} body={body2:.4f}\n"
        f"C3: O={o3:.4f} C={cl3:.4f} body={body3:.4f}\n"
        f"Penetration: {ratio} | ATR:{atr:.4f} | RSI:{rsi:.1f}"
    )
