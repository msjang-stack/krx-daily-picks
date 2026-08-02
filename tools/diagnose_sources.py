# tools/diagnose_sources.py
# API 키 없이 쓸 수 있는 데이터 소스들이 GitHub Actions에서 실제로 동작하는지 확인하는 임시 진단.
# 확인 대상: 시세(네이버 금융), 지수, 투자자 수급, 뉴스(구글 뉴스 RSS / 언론사 RSS)

import json
import re
import traceback
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
        print("  ❌ 예외:", type(e).__name__, e)
        traceback.print_exc(limit=2)


# ---------- 1. 구글 뉴스 RSS (키 불필요) ----------
def google_news():
    url = ("https://news.google.com/rss/search"
           "?q=%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90&hl=ko&gl=KR&ceid=KR:ko")
    r = requests.get(url, headers=UA, timeout=20)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    items = ET.fromstring(r.content).findall(".//item")
    if not items:
        return False, "기사 0건"
    for it in items[:3]:
        src = it.find("source")
        print("     -", it.findtext("title"))
        print("       언론사:", src.text if src is not None else "?",
              "| 발행:", it.findtext("pubDate"))
        print("       링크:", (it.findtext("link") or "")[:90])
    return True, f"기사 {len(items)}건, 제목·링크·발행일·언론사 모두 존재"


# ---------- 2. 네이버 금융 일별 시세 (차트용) ----------
def naver_chart():
    url = ("https://api.finance.naver.com/siseJson.naver?symbol=005930"
           "&requestType=1&startTime=20260501&endTime=20260731&timeframe=day")
    r = requests.get(url, headers=UA, timeout=20)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    txt = r.text.strip()
    rows = json.loads(txt.replace("'", '"'))
    if len(rows) < 2:
        return False, "데이터 없음"
    print("     헤더:", rows[0])
    print("     최근:", rows[-1])
    return True, f"{len(rows)-1}거래일 (날짜/시가/고가/저가/종가/거래량/외국인소진율)"


# ---------- 3. 네이버 금융 전 종목 시세 (스냅샷) ----------
def naver_market_sum():
    out = {}
    for sosok, market in ((0, "KOSPI"), (1, "KOSDAQ")):
        url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page=1"
        r = requests.get(url, headers=UA, timeout=20)
        if r.status_code != 200:
            return False, f"{market} HTTP {r.status_code}"
        r.encoding = "euc-kr"
        codes = set(re.findall(r'/item/main\.naver\?code=(\d{6})', r.text))
        pages = re.findall(r'page=(\d+)', r.text)
        last = max((int(p) for p in pages), default=1)
        out[market] = (len(codes), last)
        print(f"     {market}: 1페이지 {len(codes)}종목, 마지막 페이지 {last}")
    if not all(v[0] > 0 for v in out.values()):
        return False, "종목 추출 실패"
    total_pages = sum(v[1] for v in out.values())
    return True, f"전 종목 수집에 약 {total_pages}회 요청 필요"


# ---------- 4. 지수 시세 ----------
def naver_index():
    ok = []
    for idx in ("KOSPI", "KOSDAQ"):
        url = f"https://polling.finance.naver.com/api/realtime/domestic/index/{idx}"
        r = requests.get(url, headers=UA, timeout=20)
        if r.status_code != 200:
            print(f"     {idx}: HTTP {r.status_code}")
            continue
        d = r.json()
        s = json.dumps(d, ensure_ascii=False)
        print(f"     {idx}: {s[:220]}")
        ok.append(idx)
    return (len(ok) == 2), f"{', '.join(ok) or '없음'} 조회됨"


# ---------- 5. 투자자별 매매동향 (개인/외국인/기관) ----------
def naver_investor():
    url = "https://finance.naver.com/item/frgn.naver?code=005930"
    r = requests.get(url, headers=UA, timeout=20)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    r.encoding = "euc-kr"
    has_table = "기관" in r.text and "외국인" in r.text
    nums = len(re.findall(r'<td class="tc?">', r.text))
    print("     '기관'·'외국인' 문자열 존재:", has_table)
    return has_table, f"종목별 투자자 매매동향 페이지 파싱 가능 (셀 {nums}개)"


# ---------- 6. 언론사 RSS (뉴스 대안) ----------
def press_rss():
    feeds = {
        "한국경제 증권": "https://www.hankyung.com/feed/finance",
        "매일경제 증권": "https://www.mk.co.kr/rss/50200011/",
        "연합뉴스 경제": "https://www.yna.co.kr/rss/economy.xml",
    }
    good = []
    for name, url in feeds.items():
        try:
            r = requests.get(url, headers=UA, timeout=20)
            n = len(ET.fromstring(r.content).findall(".//item")) if r.status_code == 200 else 0
            print(f"     {name}: HTTP {r.status_code}, 기사 {n}건")
            if n:
                good.append(name)
        except Exception as e:
            print(f"     {name}: 실패 {type(e).__name__}")
    return bool(good), f"사용 가능: {', '.join(good) or '없음'}"


# ---------- 7. pykrx 네이버 백엔드 (참고) ----------
def pykrx_naver():
    from pykrx import stock
    df = stock.get_market_ohlcv_by_date("20260601", "20260731", "005930")
    if df is None or df.empty:
        return False, "빈 결과"
    print("     최근 2행:\n", df.tail(2))
    return True, f"{len(df)}거래일"


check("1. 구글 뉴스 RSS (뉴스, 키 불필요)", google_news)
check("2. 네이버 금융 일별시세 (차트)", naver_chart)
check("3. 네이버 금융 전종목 스냅샷", naver_market_sum)
check("4. 코스피·코스닥 지수", naver_index)
check("5. 투자자별 매매동향", naver_investor)
check("6. 언론사 RSS (뉴스 대안)", press_rss)
check("7. pykrx 네이버 백엔드", pykrx_naver)

print("=" * 70)
print("요약")
for k, v in results.items():
    print(("  ✅ " if v else "  ❌ ") + k)
