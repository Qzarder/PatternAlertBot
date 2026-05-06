from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


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


# ============================================================================
# Вспомогательные индикаторы
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


def _sequential_check(candles: List[List], tf_ms: int) -> bool:
    if len(candles) < 5:
        return False
    for i in range(1, 5):
        if candles[-i][0] - candles[-(i + 1)][0] != tf_ms:
            return False
    return True


# ============================================================================
# Основной детектор
# ============================================================================

def detect_patterns(
    candles: List[List],
    symbol: str,
    timeframe: str,
    tf_ms: int = 0,
    min_atr: float = 0.0,
) -> List[PatternResult]:
    if len(candles) < 20:
        return []

    cl = _closes(candles)
    atr_val = _atr(candles, 14)
    rsi_val = _rsi(cl, 14)
    ema_val = _ema(cl, 20)
    avg_vol = _avg_volume(candles, 20)

    if min_atr > 0 and atr_val < min_atr:
        return []

    if tf_ms > 0 and not _sequential_check(candles, tf_ms):
        return []

    ctx1 = candles[-5]
    ctx2 = candles[-4]
    c1 = candles[-3]
    c2 = candles[-2]
    c3 = candles[-1]

    price = c3[4]
    has_volume = len(c1) > 5 and all(len(c) > 5 for c in [c1, c2, c3])

    results = []
    ms = _check_morning_star(
        ctx1, ctx2, c1, c2, c3,
        symbol, timeframe, atr_val, rsi_val, ema_val,
        avg_vol if has_volume else 0.0, has_volume, price
    )
    if ms:
        results.append(ms)

    es = _check_evening_star(
        ctx1, ctx2, c1, c2, c3,
        symbol, timeframe, atr_val, rsi_val, ema_val,
        avg_vol if has_volume else 0.0, has_volume, price
    )
    if es:
        results.append(es)

    return results


# ============================================================================
# Morning Star — ПЕРЕРАБОТАНО зеркально Evening Star
# ============================================================================

def _check_morning_star(
    ctx1, ctx2, c1, c2, c3,
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
    hl3 = h3 - l3

    if body1 == 0 or body3 == 0 or hl1 == 0 or hl3 == 0:
        return None
    if cl1 >= o1:
        return None
    if cl3 <= o3:
        return None

    lower_wick2 = min(o2, cl2) - l2
    upper_wick2 = h2 - max(o2, cl2)
    lower_wick3 = min(o3, cl3) - l3
    upper_wick3 = h3 - max(o3, cl3)

    # --- минимальное тело относительно цены (защита от пылевых альтов) ---
    min_body_price = price * 0.002
    min_body1 = max(atr * 0.35, min_body_price)
    min_body3 = max(atr * 0.35, min_body_price)
    if atr == 0:
        return None
    if body1 < min_body1:
        return None
    if body3 < min_body3:
        return None

    # --- C2 (звезда): маленькое тело ИЛИ hammer (длинная нижняя тень) ---
    is_hammer = lower_wick2 > body2 * 1.5 and lower_wick2 > atr * 0.2
    if is_hammer:
        if body2 > atr * 0.4:
            return None
    else:
        if body2 > atr * 0.25:
            return None

    # --- C3: смягчаем требование к телу при длинной нижней тени ---
    strong_lower_wick3 = lower_wick3 > body3 * 1.2 and lower_wick3 > atr * 0.2
    if strong_lower_wick3:
        if body3 < hl3 * 0.25:
            return None
    else:
        if body3 < hl3 * 0.4:
            return None

    # --- позиционирование C2: звезда в нижней половине C1 ---
    if max(o2, cl2) > cl1 + atr * 0.15:
        return None

    c1_mid = l1 + hl1 * 0.5
    if max(o2, cl2) > c1_mid and not is_hammer:
        return None

    # --- C2 не должна открыться далеко над хаем C1 ---
    if o2 > h1 - atr * 0.1:
        return None

    # --- пенетрация C3 в тело C1 ---
    penetration = (cl3 - cl1) / body1
    if penetration < 0.45:
        return None

    # --- тело C3 пропорционально C1 ---
    if body3 < body1 * 0.35:
        return None

    # --- контекст тренда ---
    ctx1_close, ctx2_close = ctx1[4], ctx2[4]
    downtrend = (ctx1_close < ctx2_close < cl1) or (ctx2[4] < ctx2[1] and ctx1[4] < ctx1[1])
    if not downtrend:
        if cl1 < ema:
            return None

    # --- confidence scoring ---
    score = 0.5
    reasons = []

    if penetration >= 0.75:
        score += 0.15
        reasons.append("penetration>75%")
    elif penetration >= 0.6:
        score += 0.05

    if rsi < 30:
        score += 0.15
        reasons.append(f"RSI={rsi:.1f}<30")
    elif rsi < 40:
        score += 0.05

    if cl1 > ema:
        score += 0.1
        reasons.append("price>EMA20")

    if is_hammer:
        score += 0.15
        reasons.append("hammer_C2")

    if strong_lower_wick3:
        score += 0.1
        reasons.append("lower_wick_C3")

    if has_volume:
        v1, v2, v3 = c1[5], c2[5], c3[5]
        if v3 > v2 * 1.3 and v1 > avg_vol * 1.1:
            score += 0.15
            reasons.append("volume_confirm")
        elif v3 > v2:
            score += 0.05

    if score >= 0.85:
        confidence = "high"
    elif score >= 0.65:
        confidence = "medium"
    else:
        confidence = "low"

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
# Evening Star — версия с ATR, shooting star, scoring
# ============================================================================

def _check_evening_star(
    ctx1, ctx2, c1, c2, c3,
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
    hl3 = h3 - l3

    if body1 == 0 or body3 == 0 or hl1 == 0 or hl3 == 0:
        return None
    if cl1 <= o1:
        return None
    if cl3 >= o3:
        return None

    upper_wick2 = h2 - max(o2, cl2)
    lower_wick2 = min(o2, cl2) - l2
    upper_wick3 = h3 - max(o3, cl3)
    lower_wick3 = min(o3, cl3) - l3

    # --- минимальное тело относительно цены ---
    min_body_price = price * 0.002
    min_body1 = max(atr * 0.35, min_body_price)
    min_body3 = max(atr * 0.35, min_body_price)
    if atr == 0:
        return None
    if body1 < min_body1:
        return None
    if body3 < min_body3:
        return None

    # --- C2: звезда или shooting star ---
    is_shooting_star = upper_wick2 > body2 * 1.5 and upper_wick2 > atr * 0.2
    if is_shooting_star:
        if body2 > atr * 0.4:
            return None
    else:
        if body2 > atr * 0.25:
            return None

    # --- C3: смягчаем при длинной верхней тени ---
    strong_upper_wick3 = upper_wick3 > body3 * 1.2 and upper_wick3 > atr * 0.2
    if strong_upper_wick3:
        if body3 < hl3 * 0.25:
            return None
    else:
        if body3 < hl3 * 0.4:
            return None

    # --- позиционирование C2: звезда в верхней половине C1 ---
    if min(o2, cl2) < cl1 - atr * 0.15:
        return None

    c1_mid = l1 + hl1 * 0.5
    if min(o2, cl2) < c1_mid and not is_shooting_star:
        return None

    if o2 < l1 + atr * 0.1:
        return None

    # --- пенетрация C3 в тело C1 ---
    penetration = (cl1 - cl3) / body1
    if penetration < 0.45:
        return None

    if body3 < body1 * 0.35:
        return None

    # --- контекст тренда ---
    ctx1_close, ctx2_close = ctx1[4], ctx2[4]
    uptrend = (ctx1_close > ctx2_close > cl1) or (ctx2[4] > ctx2[1] and ctx1[4] > ctx1[1])
    if not uptrend:
        if cl1 < ema:
            return None

    # --- confidence scoring ---
    score = 0.5
    reasons = []

    if penetration >= 0.75:
        score += 0.15
        reasons.append("penetration>75%")
    elif penetration >= 0.6:
        score += 0.05

    if rsi > 70:
        score += 0.15
        reasons.append(f"RSI={rsi:.1f}>70")
    elif rsi > 60:
        score += 0.05

    if cl1 > ema:
        score += 0.1
        reasons.append("price>EMA20")

    if is_shooting_star:
        score += 0.15
        reasons.append("shooting_star_C2")

    if strong_upper_wick3:
        score += 0.1
        reasons.append("upper_wick_C3")

    if has_volume:
        v1, v2, v3 = c1[5], c2[5], c3[5]
        if v3 > v2 * 1.3 and v1 > avg_vol * 1.1:
            score += 0.15
            reasons.append("volume_confirm")
        elif v3 > v2:
            score += 0.05

    if score >= 0.85:
        confidence = "high"
    elif score >= 0.65:
        confidence = "medium"
    else:
        confidence = "low"

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
    reasons_str = ", ".join(reasons) if reasons else "base pattern"

    return (
        f"{name} {conf_emoji} {confidence.upper()} (score: {score:.2f})\n"
        f"\u0424\u0430\u043a\u0442\u043e\u0440\u044b: {reasons_str}\n"
        f"\u0421\u0432\u0435\u0447\u0430 1: O={o1:.4f} C={cl1:.4f} \u0442\u0435\u043b\u043e={body1:.4f}\n"
        f"\u0421\u0432\u0435\u0447\u0430 2: O={o2:.4f} C={cl2:.4f} \u0442\u0435\u043b\u043e={body2:.4f}\n"
        f"\u0421\u0432\u0435\u0447\u0430 3: O={o3:.4f} C={cl3:.4f} \u0442\u0435\u043b\u043e={body3:.4f}\n"
        f"\u0421\u043e\u043e\u0442\u043d\u043e\u0448\u0435\u043d\u0438\u0435 3/1: {ratio} | ATR: {atr:.4f} | RSI: {rsi:.1f}"
    )
