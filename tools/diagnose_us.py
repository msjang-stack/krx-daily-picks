# tools/diagnose_us.py
# 미국 시장 확장에 필요한 데이터 소스가 실제로 동작하는지 확인하는 임시 진단.
# 확인 대상: S&P500 구성종목 목록, 배치 시세, 일별 OHLCV, 회사 개요, 영문 뉴스

import xml.etree.ElementTree as ET

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"}

results = {}


def check(name, fn):
    print("=" * 70)
    print("[테스트]", name)
    try:
        ok, detail = fn()
        results[name] = ok
        print(("  ✅ 성공: " if ok else "  ❌ 실패: ") + detail)
    except Exception as e:
        results[name] = False
        print(f"  ❌ 예외: {type(e).__name__}: {e}")


# ---------- 1. S&P500 구성종목 목록 ----------
def sp500_list():
    url = ("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
           "master/data/constituents.csv")
    r = requests.get(url, headers=UA, timeout=20)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    lines = [l for l in r.text.splitlines() if l.strip()]
    print("     헤더:", lines[0])
    print("     예시 3개:", lines[1:4])
    return len(lines) > 400, f"{len(lines) - 1}개 종목"


# ---------- 2. 배치 시세 (Yahoo quote) ----------
def yahoo_quote_batch():
    syms = "AAPL,MSFT,NVDA,TSLA,AMZN"
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}"
    r = requests.get(url, headers=UA, timeout=20)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    d = r.json()
    rows = d.get("quoteResponse", {}).get("result", [])
    for x in rows[:3]:
        print(f"     {x.get('symbol')}: 가격={x.get('regularMarketPrice')} "
              f"등락률={x.get('regularMarketChangePercent')} "
              f"거래량={x.get('regularMarketVolume')} 시총={x.get('marketCap')}")
    return len(rows) == 5, f"{len(rows)}/5건 응답"


# ---------- 3. 일별 OHLCV (Yahoo chart) ----------
def yahoo_chart():
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
           "?range=3mo&interval=1d")
    r = requests.get(url, headers=UA, timeout=20)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    d = r.json()
    result = d.get("chart", {}).get("result")
    if not result:
        return False, f"결과 없음: {d.get('chart', {}).get('error')}"
    q = result[0]["indicators"]["quote"][0]
    closes = [c for c in q["close"] if c is not None]
    print(f"     종가 {len(closes)}개, 최근: {closes[-3:]}")
    return len(closes) > 40, f"{len(closes)}거래일"


# ---------- 4. 회사 개요 (Yahoo quoteSummary) ----------
def yahoo_profile():
    url = ("https://query1.finance.yahoo.com/v10/finance/quoteSummary/AAPL"
           "?modules=assetProfile")
    r = requests.get(url, headers=UA, timeout=20)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    d = r.json()
    result = d.get("quoteSummary", {}).get("result")
    if not result:
        return False, f"결과 없음: {d.get('quoteSummary', {}).get('error')}"
    profile = result[0].get("assetProfile", {})
    summary = (profile.get("longBusinessSummary") or "")[:120]
    print(f"     업종: {profile.get('industry')} / {profile.get('sector')}")
    print(f"     설명: {summary}...")
    return bool(summary), "assetProfile 확보"


# ---------- 5. 영문 뉴스 (구글 뉴스 RSS) ----------
def google_news_en():
    url = "https://news.google.com/rss/search?q=Apple+stock&hl=en-US&gl=US&ceid=US:en"
    r = requests.get(url, headers=UA, timeout=20)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    items = ET.fromstring(r.content).findall(".//item")
    for it in items[:3]:
        print(f"     - {it.findtext('title')}")
    return len(items) > 0, f"기사 {len(items)}건"


check("1. S&P500 구성종목 목록 (GitHub CSV)", sp500_list)
check("2. Yahoo Finance 배치 시세", yahoo_quote_batch)
check("3. Yahoo Finance 일별 OHLCV", yahoo_chart)
check("4. Yahoo Finance 회사 개요", yahoo_profile)
check("5. 구글 뉴스 RSS (영문)", google_news_en)

print("=" * 70)
print("요약")
for k, v in results.items():
    print(("  ✅ " if v else "  ❌ ") + k)
