# 임시 진단: 코스피/코스닥 투자자별 순매수(개인·외국인·기관) 원천을 찾습니다.
# 확인 후 삭제합니다.
import re

import requests

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://m.stock.naver.com/",
}
S = requests.Session()
S.headers.update(UA)


def dump_mobile_page():
    for path in ("https://m.stock.naver.com/index/KOSPI",
                 "https://m.stock.naver.com/domestic/index/KOSPI/total"):
        r = S.get(path, timeout=15)
        print(f"\n=== GET {path} -> {r.status_code}, len={len(r.text)} ===")
        if r.status_code != 200:
            continue
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        if m:
            print("__NEXT_DATA__ 길이:", len(m.group(1)))
            print(m.group(1)[:4000])
        else:
            # API 호출 흔적(문자열 리터럴 경로)을 찾아봅니다.
            apis = sorted(set(re.findall(r'"(/api/[a-zA-Z0-9/_\-]+)"', r.text)))
            print("발견된 /api/ 경로:", apis[:40])


def try_more_apis():
    candidates = [
        "https://m.stock.naver.com/api/index/KOSPI/integration",
        "https://m.stock.naver.com/api/index/KOSPI/basic",
        "https://api.stock.naver.com/index/KOSPI/investor",
        "https://m.stock.naver.com/api/json/index/KOSPI/investorDeal",
    ]
    for url in candidates:
        try:
            r = S.get(url, timeout=10)
            print(f"\n{url} -> {r.status_code}")
            if r.status_code == 200:
                print(r.text[:1500])
        except Exception as e:
            print(f"\n{url} -> 실패 {type(e).__name__}: {e}")


if __name__ == "__main__":
    dump_mobile_page()
    try_more_apis()
