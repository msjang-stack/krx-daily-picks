# app/us_build.py
# 미국 시장(S&P500) 페이지 데이터를 만듭니다. build.py가 국내 페이지를 다 만든 뒤 호출합니다.
#   결과는 국내 페이지와 별도로 dist/us.json + dist/us/charts/*.json 에 저장되어,
#   "미국 시장" 탭을 누를 때만 내려받습니다 (국내 탭만 볼 때 페이지가 무거워지지 않도록).
#
# 국내(app/naver.py) 흐름과 다른 점:
#   - 배치 시세가 막혀 있어 종목별 일별 시세 하나로 "오늘 시세"와 "차트"를 동시에 얻습니다.
#     그래서 거래대금 상위 몇 종목만 고르는 별도 단계가 없고, S&P500 전체가 곧 유니버스입니다.
#   - 회사 개요는 DART 대신 S&P500 목록에 이미 있는 GICS 업종 분류를 씁니다.
#   - 가격제한폭이 없어 picks.py의 상한가 과열 감점을 켜지 않습니다 (currency="USD").

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

from . import config, gics, indicators, news, picks, yahoo

KST = timezone(timedelta(hours=9))


def _core_name(name):
    """검색어·기사 매칭용으로 회사명에서 부가 표기를 뗍니다. 'Alphabet Inc. (Class A)' → 'Alphabet'."""
    n = re.sub(r"\s*\(.*?\)\s*$", "", name)
    n = re.sub(r",?\s+(Inc|Corp|Corporation|Co|Company|plc|Ltd|Group|Holdings)\.?$", "", n)
    return n.strip() or name


def _founded_year(v):
    m = re.match(r"\d{4}", v or "")
    return m.group(0) if m else None


def usd_big(v):
    if not v:
        return "-"
    a = abs(v)
    if a >= 1e9:
        return f"${v / 1e9:,.1f}B"
    if a >= 1e6:
        return f"${v / 1e6:,.1f}M"
    return f"${v:,.0f}"


def run():
    started = time.time()
    print("[미국 시장] 시작")

    universe = yahoo.fetch_universe()
    print(f"[미국 시장] S&P500 {len(universe):,}종목")

    snap = yahoo.fetch_today_snapshot(universe[: config.US_CHART_LIMIT])

    charts, metrics, rows = {}, {}, []
    for s in universe:
        v = snap.get(s["c"])
        if not v:
            continue
        series = v["series"]
        charts[s["c"]] = {"d": series["d"], "c": series["c"], "v": series["v"]}
        m = indicators.compute(series)
        if m:
            metrics[s["c"]] = m
        rows.append({
            "n": s["n"], "c": s["c"], "mkt": "US",
            "p": v["p"], "pct": v["pct"], "vol": v["vol"], "val": v["val"],
        })
    print(f"[미국 시장] 시세 확보 {len(rows):,}종목, 지표 {len(metrics):,}개")

    by_value = sorted(rows, key=lambda x: -(x.get("val") or 0))
    by_gain = sorted(rows, key=lambda x: -(x.get("pct") or -999))

    # ---------- 지수 ----------
    indices = yahoo.fetch_indices()
    market_value = sum(r.get("val") or 0 for r in rows)
    for ix in indices:
        ix["value"] = usd_big(market_value)
        ix["flow"] = None
    print(f"[미국 시장] 지수 {len(indices)}개")

    # ---------- 등락 종목 수 ----------
    up = sum(1 for r in rows if (r.get("pct") or 0) > 0)
    down = sum(1 for r in rows if (r.get("pct") or 0) < 0)
    flat = len(rows) - up - down

    lines = []
    for ix in indices:
        verb = "올라" if (ix["pct"] or 0) > 0 else ("내려" if (ix["pct"] or 0) < 0 else "보합으로")
        lines.append(
            f"{ix['name']}는 {abs(ix['pct'] or 0):.2f}% {verb} "
            f"{ix['val']:,.2f}로 마감했습니다."
        )
    if lines:
        lines.append(f"S&P500 {len(rows):,}종목 중 {up:,}종목이 오르고 {down:,}종목이 내렸습니다.")

    # ---------- 목록 ----------
    def row_note(s):
        m = metrics.get(s["c"]) or {}
        if m.get("val_ratio") and m["val_ratio"] >= 2:
            return f"거래대금 평소의 {m['val_ratio']:.1f}배"
        if m.get("new_high"):
            return "60일 최고가 경신"
        if m.get("ret20") is not None:
            return f"20일 수익률 {m['ret20']:+.1f}%"
        return ""

    stocks = [dict(r, note=row_note(r)) for r in rows]

    watch_pool = [r for r in by_value if (r.get("val") or 0) >= config.US_WATCH_VALUE]
    print(f"[미국 시장 주목] 후보 {len(watch_pool):,}종목")
    watch = picks.pick(watch_pool, metrics, currency="USD")
    print(f"[미국 시장 주목] {len(watch)}종목 선정: " + ", ".join(w["n"] for w in watch))

    # ---------- 뉴스 ----------
    name_by_code = {s["c"]: s["n"] for s in universe}
    news_targets, seen = [], set()
    for s in [dict(w) for w in watch] + by_value[: config.TOP_N] + by_gain[: config.TOP_N]:
        if s["c"] not in seen and len(news_targets) < config.NEWS_STOCKS:
            seen.add(s["c"]); news_targets.append(s)

    stock_news = {}
    for s in news_targets:
        query = _core_name(name_by_code.get(s["c"], s["n"]))
        try:
            arts = news.fetch_for(query, locale="en")
        except Exception as e:
            print(f"[미국 뉴스] {s['c']} 실패: {type(e).__name__}: {e}")
            arts = []
        if arts:
            stock_news[s["c"]] = arts
        time.sleep(0.15)
    print(f"[미국 뉴스] 종목 뉴스 {len(stock_news)}건 / 조회 {len(news_targets)}종목")

    try:
        market_news = news.fetch_market(locale="en")
    except Exception as e:
        print(f"[미국 뉴스] 시장 뉴스 실패: {type(e).__name__}: {e}")
        market_news = []
    print(f"[미국 뉴스] 시장 뉴스 {len(market_news)}건")

    # ---------- 회사 개요 (GICS 업종, DART 대신) ----------
    sector_by_code = {s["c"]: s for s in universe}
    info = {}
    for code in {s["c"] for s in news_targets}:
        s = sector_by_code.get(code)
        if not s:
            continue
        parts = [gics.translate(p) for p in (s.get("sector"), s.get("sub")) if p]
        yr = _founded_year(s.get("founded"))
        if yr:
            parts.append(f"{yr}년 설립")
        if parts:
            info[code] = " · ".join(parts)
    print(f"[미국 기업정보] {len(info)}건")

    # ---------- 출력 ----------
    trade_day = None
    for c in charts.values():
        if c["d"]:
            trade_day = max(trade_day or "", c["d"][-1])
    dt = datetime.strptime(trade_day, "%Y%m%d") if trade_day else datetime.now(KST).replace(tzinfo=None)
    date_iso = dt.strftime("%Y-%m-%d")

    visible = set()
    for s in watch:
        visible.add(s["c"])
    for group in (by_value, by_gain):
        for s in group[: config.TOP_N * 2]:
            visible.add(s["c"])

    us_dir = os.path.join(config.OUT_DIR, "us")
    chart_dir = os.path.join(us_dir, "charts")
    os.makedirs(chart_dir, exist_ok=True)
    for code, c in charts.items():
        with open(os.path.join(chart_dir, f"{code}.json"), "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, separators=(",", ":"))
    inline = {c: v for c, v in charts.items() if c in visible}
    print(f"[미국 차트] 개별 파일 {len(charts):,}개 저장, 페이지 내장 {len(inline)}개")

    data = {
        "currency": "USD",
        "chartDir": "us/charts/",
        "dateISO": date_iso,
        "dateLabel": f"{dt.year}년 {dt.month}월 {dt.day}일",
        "weekday": config.WEEKDAY[dt.weekday()],
        "closeNote": "뉴욕증권거래소 종가 기준",
        "indices": indices,
        "briefing": {"lines": lines, "breadth": {"up": up, "flat": flat, "down": down}},
        "news": market_news,
        "stocks": stocks,
        "watch": watch,
        "info": info,
        "stockNews": stock_news,
        "charts": inline,
        "builtAt": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
    }

    with open(os.path.join(config.OUT_DIR, "us.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    kb = os.path.getsize(os.path.join(config.OUT_DIR, "us.json")) / 1024
    print(f"[미국 시장] 완료: us.json ({kb:,.0f} KB) · {time.time() - started:.0f}초 소요")
