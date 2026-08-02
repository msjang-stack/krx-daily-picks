# tools/check_keys.py
# 등록된 Secrets가 실제로 동작하는지 확인하는 임시 스크립트.
# 키 값 자체는 절대 출력하지 않고, 존재 여부와 응답만 확인합니다.

import io
import os
import zipfile
import xml.etree.ElementTree as ET

import requests

UA = {"User-Agent": "Mozilla/5.0"}


def mask(v):
    """키 존재 여부만 알려주고 값은 감춥니다."""
    if not v:
        return "없음"
    return f"설정됨 (길이 {len(v)}자, 끝 2자리 ..{v[-2:]})"


print("=" * 68)
NID = os.environ.get("NAVER_CLIENT_ID", "")
NSEC = os.environ.get("NAVER_CLIENT_SECRET", "")
DART = os.environ.get("DART_API_KEY", "")
print("NAVER_CLIENT_ID    :", mask(NID))
print("NAVER_CLIENT_SECRET:", mask(NSEC))
print("DART_API_KEY       :", mask(DART))

# ---------- 1. 네이버 뉴스 검색 API ----------
print("=" * 68)
print("[1] 네이버 뉴스 검색 API")
if not (NID and NSEC):
    print("  ⏭  키가 없어 건너뜁니다.")
else:
    try:
        r = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            params={"query": "삼성전자", "display": 5, "sort": "date"},
            headers={"X-Naver-Client-Id": NID, "X-Naver-Client-Secret": NSEC},
            timeout=15,
        )
        print("  HTTP", r.status_code)
        if r.status_code == 200:
            items = r.json().get("items", [])
            print(f"  ✅ 검색 권한 있음 — 기사 {len(items)}건")
            for it in items[:3]:
                t = it.get("title", "").replace("<b>", "").replace("</b>", "")
                t = t.replace("&quot;", '"').replace("&amp;", "&")
                print("     -", t)
                print("       발행:", it.get("pubDate"))
                print("       원문:", (it.get("originallink") or "")[:80])
        else:
            print("  ❌ 응답:", r.text[:300])
            print("     → 검색 API 권한이 없는 키입니다. 구글 뉴스 RSS를 씁니다.")
    except Exception as e:
        print("  ❌ 예외:", type(e).__name__, e)

# ---------- 2. DART 기업개황 ----------
print("=" * 68)
print("[2] DART 전자공시 API")
if not DART:
    print("  ⏭  키가 없어 건너뜁니다.")
else:
    corp_code = None
    try:
        r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                         params={"crtfc_key": DART}, timeout=60)
        print("  corpCode.xml HTTP", r.status_code, f"({len(r.content):,} bytes)")
        if r.content[:2] == b"PK":
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            root = ET.fromstring(zf.read(zf.namelist()[0]))
            rows = root.findall(".//list")
            listed = [x for x in rows if (x.findtext("stock_code") or "").strip()]
            print(f"  ✅ 전체 {len(rows):,}개 법인 중 상장사 {len(listed):,}개")
            for x in listed:
                if (x.findtext("stock_code") or "").strip() == "005930":
                    corp_code = x.findtext("corp_code")
                    print("     삼성전자 corp_code:", corp_code)
                    break
        else:
            print("  ❌ ZIP이 아님:", r.text[:250])
    except Exception as e:
        print("  ❌ corpCode 예외:", type(e).__name__, e)

    if corp_code:
        try:
            r = requests.get("https://opendart.fss.or.kr/api/company.json",
                             params={"crtfc_key": DART, "corp_code": corp_code}, timeout=20)
            d = r.json()
            print("  company.json status:", d.get("status"), d.get("message"))
            if d.get("status") == "000":
                print("  ✅ 기업개황 조회 성공")
                for k in ("corp_name", "induty_code", "est_dt", "ceo_nm", "adres"):
                    print(f"     {k}: {d.get(k)}")
            else:
                print("  ❌ 실패")
        except Exception as e:
            print("  ❌ company 예외:", type(e).__name__, e)

print("=" * 68)
print("확인 종료")
