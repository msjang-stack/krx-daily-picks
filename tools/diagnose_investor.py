# 임시 진단: 코스피/코스닥 투자자별 순매수(개인·외국인·기관) 원천을 찾습니다.
# 확인 후 삭제합니다.
import re
import sys

import requests

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
}
S = requests.Session()
S.headers.update(UA)


def dump_html_table():
    for code in ("KOSPI", "KOSDAQ"):
        url = f"https://finance.naver.com/sise/sise_index_investor.naver?code={code}"
        r = S.get(url, timeout=15)
        r.encoding = "euc-kr"
        print(f"\n=== {code} HTML status {r.status_code}, len={len(r.text)} ===")
        # type_2 테이블 부분만 잘라서 봅니다.
        m = re.search(r'<table[^>]*class="type_2"[^>]*>.*?</table>', r.text, re.S)
        if m:
            snippet = m.group(0)
            print(snippet[:3000])
        else:
            print("type_2 테이블을 못 찾음. 앞부분 원문:")
            print(r.text[:2000])


def try_mobile_api():
    # m.stock.naver.com 쪽에 지수용 투자자 동향 API가 있는지 확인
    candidates = [
        "https://m.stock.naver.com/api/index/KOSPI/investorTrend",
        "https://m.stock.naver.com/api/index/KOSPI/trend/investor",
        "https://m.stock.naver.com/api/stock/KOSPI/investors",
    ]
    for url in candidates:
        try:
            r = S.get(url, timeout=10)
            print(f"\n{url} -> {r.status_code}")
            print(r.text[:500])
        except Exception as e:
            print(f"\n{url} -> 실패 {type(e).__name__}: {e}")


if __name__ == "__main__":
    dump_html_table()
    try_mobile_api()
