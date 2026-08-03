# app/picks.py
# 지표를 바탕으로 '내일 주목할 종목'을 고르고, 왜 골랐는지 근거를 문장으로 만듭니다.
# 예측이 아니라 오늘 나타난 사실을 정리해 보여주는 것이 목적입니다.

from . import config


def _won(v):
    return f"{round(v):,}"


def _eok(v):
    """원 단위 → 억/조 표기."""
    if v is None:
        return ""
    eok = v / 1e8
    if eok >= 10000:
        return f"{eok / 10000:.1f}조원"
    return f"{eok:,.0f}억원"


def _usd(v):
    if v is None:
        return ""
    if v >= 1e9:
        return f"${v / 1e9:,.1f}B"
    return f"${v / 1e6:,.0f}M"


def score(m, snap, currency="KRW"):
    """조건 충족 항목과 점수를 함께 돌려줍니다."""
    checks, pts = [], 0.0
    fmt_val = _usd if currency == "USD" else _eok
    fmt_px = (lambda v: f"${v:,.2f}") if currency == "USD" else (lambda v: f"{_won(v)}원")

    r = m.get("val_ratio")
    if r and r >= 2:
        pts += min(30, 10 * r ** 0.5)
        checks.append([
            f"거래대금이 20일 평균의 {r:.1f}배",
            f"오늘 {fmt_val(m['close'] * (snap.get('vol') or 0))} · 평소 {fmt_val(m['avg_val20'])}",
        ])

    if m["ma20"] and m["ma5"] and m["ma60"]:
        if m["close"] > m["ma5"] > m["ma20"] > m["ma60"]:
            pts += 20
            checks.append(["5·20·60일 이동평균선 정배열", "단기선이 장기선 위에 순서대로 정렬"])
        elif m["ma20_prev5"] and m["close"] > m["ma20"] >= m["ma20_prev5"]:
            pts += 12
            checks.append([
                "20일 이동평균선 위에서 상승 전환",
                f"20일선 {fmt_px(m['ma20'])} · 종가 {fmt_px(m['close'])}",
            ])

    if m.get("new_high"):
        pts += 18
        checks.append([
            "60일 최고가 경신",
            f"이전 최고 {fmt_px(m['prev_high60'])}",
        ])
    elif m.get("near_high") and m["near_high"] >= 0.97:
        pts += 10
        gap = (1 - m["near_high"]) * 100
        checks.append([
            f"60일 최고가에 {gap:.1f}% 근접",
            f"최고 {fmt_px(m['high60'])} · 종가 {fmt_px(m['close'])}",
        ])

    if m.get("up_streak", 0) >= 3:
        pts += 8
        checks.append([f"{m['up_streak']}거래일 연속 상승", ""])

    ret20 = m.get("ret20")
    if ret20 and ret20 > 0:
        pts += min(12, ret20 * 0.4)

    # 과열 감점 — 근거 목록에도 주의 항목으로 남깁니다.
    rsi = m.get("rsi")
    if rsi and rsi >= 75:
        pts -= (rsi - 75) * 1.2
        checks.append([f"RSI {rsi:.0f} — 과열 구간", "70을 넘으면 단기 과열 신호로 봅니다"])
    # 상하한가가 있는 한국 시장에서만 유효한 과열 신호입니다. 미국은 가격제한폭이 없습니다.
    if currency == "KRW":
        pct = snap.get("pct") or 0
        if pct >= 25:
            pts -= 12

    return pts, checks


def pick(rows, metrics, limit=None, currency="KRW"):
    """
    rows: 유니버스 스냅샷 [{c,n,mkt,p,pct,vol,val,cap}]
    metrics: {코드: indicators.compute 결과}
    """
    limit = limit or config.WATCH_N
    scored = []
    for s in rows:
        m = metrics.get(s["c"])
        if not m or m["days"] < 40:
            continue
        pts, checks = score(m, s, currency=currency)
        # 근거가 2개 미만이면 '주목할 이유'라 부르기 어렵습니다.
        if len(checks) < 2 or pts <= 20:
            continue
        scored.append({
            "n": s["n"], "c": s["c"], "mkt": s["mkt"],
            "p": s["p"], "pct": s["pct"], "val": s["val"],
            "score": round(pts, 1),
            "checks": checks,
            "chips": [c[0] for c in checks][:3],
            "hot": 0,
            "why": _summary(checks),
        })
    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


def _summary(checks):
    heads = [c[0] for c in checks]
    if not heads:
        return ""
    if len(heads) == 1:
        return heads[0] + " 상태입니다."
    return ", ".join(heads[:-1]) + f", {heads[-1]} 상태입니다."
