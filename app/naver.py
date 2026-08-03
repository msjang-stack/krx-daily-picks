# app/naver.py
# 네이버 금융에서 시세를 수집합니다.
# 공식 API가 아니므로 엔드포인트가 바뀔 수 있어, 주 경로가 실패하면 예비 경로로 넘어갑니다.

import json
import re
import time

import requests

from . import config

S = requests.Session()
S.headers.update(config.UA)

MARKETS = ("KOSPI", "KOSDAQ")


def _num(v):
    """'1,234' 또는 1234 → 1234. 실패하면 None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    t = str(v).replace(",", "").replace("%", "").replace("+", "").strip()
    if not t or t in ("-", "N/A"):
        return None
    try:
        return float(t) if "." in t else int(t)
    except ValueError:
        return None


def _get(url, **kw):
    r = S.get(url, timeout=kw.pop("timeout", 20), **kw)
    r.raise_for_status()
    return r


# ---------------- 전 종목 스냅샷 ----------------

def _snapshot_json(market):
    """모바일 JSON API. 거래대금까지 한 번에 주는 주 경로."""
    out, page = [], 1
    while page <= 60:
        url = (f"https://m.stock.naver.com/api/stocks/marketValue/{market}"
               f"?page={page}&pageSize=100")
        d = _get(url).json()
        rows = d.get("stocks") or d.get("datas") or []
        if not rows:
            break
        if page == 1:
            # 필드 이름과 단위는 예고 없이 바뀔 수 있어 첫 행을 남겨둡니다.
            print(f"[스냅샷] {market} 응답 예시: "
                  + json.dumps({k: v for k, v in list(rows[0].items())[:14]},
                               ensure_ascii=False)[:400])
        for r in rows:
            code = r.get("itemCode") or r.get("reutersCode")
            if not code or not re.fullmatch(r"\d{6}", str(code)):
                continue
            # 네이버는 단위가 항목마다 다릅니다. 시가총액은 억원, 거래대금은 백만원.
            # (예: 삼성전자 marketValue 15,346,481억원 = 1,534조 /
            #      accumulatedTradingValue 14,769,098백만원 = 14.8조)
            cap = _num(r.get("marketValue"))
            val = _num(r.get("accumulatedTradingValue"))
            out.append({
                "c": str(code),
                "n": r.get("stockName") or r.get("itemName") or "",
                "mkt": market,
                # 'stock' 외에 etf/etn 등이 섞여 옵니다. 종목만 남기는 데 씁니다.
                "kind": (r.get("stockEndType") or "").lower(),
                "p": _num(r.get("closePrice")),
                "pct": _num(r.get("fluctuationsRatio")),
                "vol": _num(r.get("accumulatedTradingVolume")),
                "val": val * 1e6 if val else None,
                "cap": cap * 1e8 if cap else None,
            })
        total = _num(d.get("totalCount")) or 0
        if len(out) >= total or len(rows) < 100:
            break
        page += 1
        time.sleep(0.12)
    return out


_ROW_RE = re.compile(
    r'/item/main\.naver\?code=(\d{6})">([^<]+)</a>.*?'
    r'<td class="number">([\d,]+)</td>.*?'
    r'<td class="number">([-\d,]+)</td>.*?'
    r'([-+]?\d+\.\d+)%',
    re.S,
)


def _snapshot_html(market):
    """예비 경로: 시가총액 페이지 HTML. 거래대금은 종가×거래량으로 추정합니다."""
    sosok = 0 if market == "KOSPI" else 1
    out, page = [], 1
    while page <= 60:
        url = (f"https://finance.naver.com/sise/sise_market_sum.naver"
               f"?sosok={sosok}&page={page}")
        r = _get(url)
        r.encoding = "euc-kr"
        found = 0
        for m in _ROW_RE.finditer(r.text):
            code, name, price, _diff, pct = m.groups()
            p = _num(price)
            out.append({"c": code, "n": name.strip(), "mkt": market,
                        "p": p, "pct": _num(pct), "vol": None,
                        "val": None, "cap": None})
            found += 1
        if not found:
            break
        page += 1
        time.sleep(0.12)
    return out


def fetch_snapshot():
    """전 종목 당일 시세. [{c,n,mkt,p,pct,vol,val,cap}, ...]"""
    rows = []
    for market in MARKETS:
        got = []
        try:
            got = _snapshot_json(market)
            print(f"[스냅샷] {market}: JSON API {len(got)}종목")
        except Exception as e:
            print(f"[스냅샷] {market}: JSON API 실패 ({type(e).__name__}: {e})")
        if not got:
            try:
                got = _snapshot_html(market)
                print(f"[스냅샷] {market}: HTML 예비경로 {len(got)}종목 (거래대금 추정)")
            except Exception as e:
                print(f"[스냅샷] {market}: HTML도 실패 ({type(e).__name__}: {e})")
        rows.extend(got)

    # 거래대금이 비면 종가×거래량으로 채웁니다 (추정치).
    for r in rows:
        if not r.get("val") and r.get("p") and r.get("vol"):
            r["val"] = r["p"] * r["vol"]
            r["val_est"] = True
    return rows


# ---------------- 종목 일별 시세 ----------------

def fetch_daily(code, days=None):
    """최근 거래일 시세. {d:[YYYYMMDD], o,h,l,c,v:[...]} 형태."""
    days = days or config.CHART_DAYS
    url = ("https://api.finance.naver.com/siseJson.naver"
           f"?symbol={code}&requestType=1&startTime=20000101&endTime=99991231"
           f"&timeframe=day&count={days + 10}")
    txt = _get(url).text.strip()
    rows = json.loads(txt.replace("'", '"'))
    if len(rows) < 2:
        return None
    body = rows[1:][-days:]
    out = {"d": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    for row in body:
        if len(row) < 6:
            continue
        out["d"].append(str(row[0]))
        out["o"].append(_num(row[1]))
        out["h"].append(_num(row[2]))
        out["l"].append(_num(row[3]))
        out["c"].append(_num(row[4]))
        out["v"].append(_num(row[5]))
    return out if len(out["c"]) >= 2 else None


# ---------------- 지수 ----------------

def fetch_index(name):
    url = f"https://polling.finance.naver.com/api/realtime/domestic/index/{name}"
    d = _get(url).json()
    rows = d.get("datas") or []
    if not rows:
        return None
    x = rows[0]
    return {
        "name": "코스피" if name == "KOSPI" else "코스닥",
        "val": _num(x.get("closePrice")),
        "chg": _num(x.get("compareToPreviousClosePrice")),
        "pct": _num(x.get("fluctuationsRatio")),
        "value": _num(x.get("accumulatedTradingValue")),
        "volume": _num(x.get("accumulatedTradingVolume")),
    }


def fetch_index_series(name, days=None):
    """지수 일별 시세 (지수 카드의 추이선용)."""
    days = days or 40
    code = "KOSPI" if name == "KOSPI" else "KOSDAQ"
    url = (f"https://api.finance.naver.com/siseJson.naver?symbol={code}"
           f"&requestType=1&startTime=20000101&endTime=99991231"
           f"&timeframe=day&count={days}")
    try:
        rows = json.loads(_get(url).text.strip().replace("'", '"'))
        return [_num(r[4]) for r in rows[1:] if len(r) > 4 and _num(r[4])]
    except Exception as e:
        print(f"[지수추이] {name} 실패: {type(e).__name__}: {e}")
        return []


# ---------------- 투자자 수급 ----------------

def fetch_index_investors():
    """
    시장별 개인·외국인·기관 순매수(억원). {"KOSPI": {...}, "KOSDAQ": {...}}
    시장 하나가 실패해도 나머지는 살리고, 전부 실패하면 빈 dict를 돌려
    화면에서 수급 칸을 자동으로 감춥니다.
    """
    out = {}
    for name in MARKETS:
        try:
            r = _get(f"https://m.stock.naver.com/api/index/{name}/integration")
            d = (r.json() or {}).get("dealTrendInfo") or {}
            personal = _num(d.get("personalValue"))
            foreign = _num(d.get("foreignValue"))
            institutional = _num(d.get("institutionalValue"))
            if personal is None or foreign is None or institutional is None:
                print(f"[수급] {name} 응답에 필요한 값이 없음: {d}")
                continue
            out[name] = {"개인": personal, "외국인": foreign, "기관": institutional}
        except Exception as e:
            print(f"[수급] {name} 실패: {type(e).__name__}: {e}")
    return out
