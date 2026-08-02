# app/indicators.py
# 일별 시세에서 이동평균·RSI·거래대금 급증 등 판단 근거가 되는 값을 계산합니다.


def sma(vals, win, at=-1):
    """단순 이동평균. 데이터가 모자라면 None."""
    n = len(vals)
    i = n + at if at < 0 else at
    if i - win + 1 < 0:
        return None
    seg = [v for v in vals[i - win + 1: i + 1] if v is not None]
    return sum(seg) / len(seg) if len(seg) == win else None


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for a, b in zip(closes[-period - 1:-1], closes[-period:]):
        d = b - a
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains) / period
    al = sum(losses) / period
    if al == 0:
        return 100.0
    rs = ag / al
    return 100 - 100 / (1 + rs)


def compute(series):
    """
    series: {d,o,h,l,c,v}
    반환: 지표 묶음. 계산 불가한 항목은 None.
    """
    c = [x for x in series["c"] if x is not None]
    v = [x for x in series["v"] if x is not None]
    if len(c) < 25:
        return None

    close = c[-1]
    # 거래대금은 일별 API에 없어 종가×거래량으로 추정합니다.
    values = [ci * vi for ci, vi in zip(c, v)] if len(v) == len(c) else []

    ma5, ma20, ma60 = sma(c, 5), sma(c, 20), sma(c, 60)
    ma20_prev5 = sma(c, 20, at=len(c) - 6) if len(c) >= 26 else None

    avg_val20 = None
    val_ratio = None
    if len(values) >= 21:
        prev = values[-21:-1]
        avg_val20 = sum(prev) / len(prev)
        if avg_val20:
            val_ratio = values[-1] / avg_val20

    window = c[-60:] if len(c) >= 60 else c
    high = max(window)
    prev_high = max(window[:-1]) if len(window) > 1 else None

    return {
        "close": close,
        "ma5": ma5, "ma20": ma20, "ma60": ma60, "ma20_prev5": ma20_prev5,
        "rsi": rsi(c),
        "avg_val20": avg_val20,
        "val_ratio": val_ratio,
        "high60": high,
        "prev_high60": prev_high,
        "near_high": (close / high) if high else None,
        "new_high": bool(prev_high and close > prev_high),
        "ret5": (close / c[-6] - 1) * 100 if len(c) >= 6 else None,
        "ret20": (close / c[-21] - 1) * 100 if len(c) >= 21 else None,
        "up_streak": _streak(c),
        "days": len(c),
    }


def _streak(c):
    n = 0
    for i in range(len(c) - 1, 0, -1):
        if c[i] > c[i - 1]:
            n += 1
        else:
            break
    return n
