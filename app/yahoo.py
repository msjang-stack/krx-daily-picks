# app/yahoo.py
# 미국 시장(S&P500) 수집. 야후 파이낸스의 인증 불필요 엔드포인트만 사용합니다.
#
# 주의: 전 종목 배치 시세(v7/finance/quote)와 회사 개요(quoteSummary)는
# 최근 야후가 인증(crumb)을 요구하도록 막아 둘 다 401이 납니다. 그래서
# 배치 조회 대신 종목별 일별 시세(v8/finance/chart, 인증 불필요)의
# 마지막 행을 "당일 시세"로 쓰고, 회사 개요는 S&P500 목록에 이미 포함된
# GICS 업종 분류로 대신합니다.

import time
from datetime import datetime, timezone

import requests

from . import config

S = requests.Session()
S.headers.update(config.UA)

SP500_CSV = ("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
             "master/data/constituents.csv")

INDEX_SYMBOLS = [("^GSPC", "S&P500"), ("^IXIC", "나스닥종합"), ("^DJI", "다우존스")]


def _csv_row(line):
    """따옴표로 묶인 필드(예: "Saint Paul, Minnesota")를 살리는 최소 CSV 파서."""
    out, cur, q = [], "", False
    for ch in line:
        if ch == '"':
            q = not q
        elif ch == "," and not q:
            out.append(cur); cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def fetch_universe():
    """S&P500 구성종목. [{c,n,mkt,sector,sub,founded}, ...]"""
    r = S.get(SP500_CSV, timeout=20)
    r.raise_for_status()
    lines = [l for l in r.text.splitlines() if l.strip()]
    header = _csv_row(lines[0])
    idx = {name: i for i, name in enumerate(header)}
    out = []
    for line in lines[1:]:
        row = _csv_row(line)
        if len(row) <= max(idx.values()):
            continue
        out.append({
            "c": row[idx["Symbol"]].strip(),
            "n": row[idx["Security"]].strip(),
            "mkt": "US",
            "sector": row[idx.get("GICS Sector", -1)].strip() if "GICS Sector" in idx else "",
            "sub": row[idx.get("GICS Sub-Industry", -1)].strip() if "GICS Sub-Industry" in idx else "",
            "founded": row[idx.get("Founded", -1)].strip() if "Founded" in idx else "",
        })
    return out


def fetch_daily(symbol, days=None):
    """
    종목/지수 일별 시세. {d:[YYYYMMDD], c:[...], v:[...]} 또는 실패 시 None.
    range는 넉넉히 잡고 마지막 days개만 씁니다 (휴장일 등으로 부족해지지 않도록).
    """
    days = days or config.CHART_DAYS
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?range=6mo&interval=1d")
    try:
        r = S.get(url, timeout=15)
        if r.status_code != 200:
            return None
        result = r.json().get("chart", {}).get("result")
        if not result:
            return None
        res = result[0]
        ts = res.get("timestamp") or []
        q = res["indicators"]["quote"][0]
        closes, vols, dates = q.get("close") or [], q.get("volume") or [], []
        d, c, v = [], [], []
        for t, close, vol in zip(ts, closes, vols):
            if close is None:
                continue
            dt = datetime.fromtimestamp(t, tz=timezone.utc)
            d.append(dt.strftime("%Y%m%d"))
            c.append(round(close, 2))
            v.append(int(vol) if vol else 0)
        if len(c) < 2:
            return None
        return {"d": d[-days:], "c": c[-days:], "v": v[-days:]}
    except Exception:
        return None


def fetch_today_snapshot(universe, pace=0.15, progress_every=100):
    """
    전 종목의 '오늘' 시세를 일별 시세의 마지막 행에서 뽑아냅니다.
    배치 조회가 막혀 있어 종목마다 개별 호출하며, S&P500(500여개)이라 부담이 적습니다.
    반환: {code: {series, p, pct, val, vol}}  (series는 fetch_daily 결과, 차트에도 재사용)
    """
    out = {}
    fail = 0
    for i, s in enumerate(universe):
        series = fetch_daily(s["c"])
        if series and len(series["c"]) >= 2:
            p = series["c"][-1]
            prev = series["c"][-2]
            pct = (p / prev - 1) * 100 if prev else 0.0
            vol = series["v"][-1]
            out[s["c"]] = {
                "series": series, "p": p, "pct": round(pct, 2),
                "vol": vol, "val": round(p * vol, 2),
            }
        else:
            fail += 1
        if (i + 1) % progress_every == 0:
            print(f"  ... {i + 1}/{len(universe)} (실패 {fail})")
        time.sleep(pace)
    print(f"[미국 시세] {len(out)}/{len(universe)}종목 확보, 실패 {fail}")
    return out


def fetch_indices():
    """S&P500·나스닥·다우 지수의 일별 시세."""
    out = []
    for symbol, name in INDEX_SYMBOLS:
        series = fetch_daily(symbol, days=40)
        if not series or len(series["c"]) < 2:
            print(f"[미국 지수] {name} 실패")
            continue
        p, prev = series["c"][-1], series["c"][-2]
        pct = (p / prev - 1) * 100 if prev else 0.0
        out.append({
            "name": name, "val": p, "chg": round(p - prev, 2), "pct": round(pct, 2),
            "series": series["c"],
        })
    return out
