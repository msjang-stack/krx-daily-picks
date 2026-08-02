# app/dart.py
# DART 전자공시에서 기업개황(업종·설립일·대표자)을 받아옵니다.
# 회사 정보는 거의 바뀌지 않으므로 캐시에 쌓아두고 새 종목만 조회합니다.

import io
import json
import os
import time
import zipfile
import xml.etree.ElementTree as ET

import requests

from . import config

# 한국표준산업분류 앞 3자리 → 사람이 읽는 업종명 (자주 나오는 것 위주)
KSIC = {
    "011": "농업", "032": "양식업", "051": "석탄 광업", "072": "금속 광업",
    "101": "육류 가공", "103": "과일·채소 가공", "104": "유지 제조", "105": "낙농품 제조",
    "106": "곡물 가공", "107": "기타 식품 제조", "108": "사료 제조", "111": "주류 제조",
    "112": "음료 제조", "131": "방적·가공", "134": "섬유제품 제조", "141": "봉제의복 제조",
    "151": "가죽·신발 제조", "161": "제재·목재 제조", "171": "펄프·종이 제조",
    "181": "인쇄업", "192": "석유정제품 제조", "201": "기초 화학물질 제조",
    "202": "합성고무·플라스틱 제조", "203": "비료·농약 제조", "204": "기타 화학제품 제조",
    "205": "화학섬유 제조", "211": "의약품 제조", "212": "의료용품 제조",
    "221": "고무제품 제조", "222": "플라스틱제품 제조", "231": "유리제품 제조",
    "232": "내화·요업 제조", "233": "시멘트·콘크리트 제조", "241": "1차 철강 제조",
    "242": "비철금속 제조", "243": "금속 주조", "251": "구조용 금속제품 제조",
    "259": "기타 금속가공품 제조", "261": "반도체 제조", "262": "전자부품 제조",
    "263": "컴퓨터·주변장치 제조", "264": "반도체·전자부품 제조",
    "265": "영상·음향기기 제조", "266": "마그네틱·광학 매체 제조",
    "271": "의료용 기기 제조", "272": "측정·제어장비 제조", "273": "광학기기 제조",
    "281": "전동기·발전기 제조", "282": "전지 제조", "283": "절연선·케이블 제조",
    "284": "전구·조명장치 제조", "285": "가정용 기기 제조", "289": "기타 전기장비 제조",
    "291": "일반 기계 제조", "292": "특수 기계 제조", "301": "자동차 제조",
    "303": "자동차 부품 제조", "311": "선박·보트 건조", "312": "철도장비 제조",
    "313": "항공기·우주선 제조", "319": "기타 운송장비 제조", "320": "가구 제조",
    "331": "귀금속·악기 제조", "334": "의료·정밀기기 제조", "339": "기타 제품 제조",
    "351": "발전·송전업", "352": "연료용 가스 공급업", "353": "냉난방 공급업",
    "360": "수도업", "411": "건물 건설업", "412": "토목 건설업", "421": "기반조성 공사업",
    "426": "전기·통신 공사업", "451": "자동차 판매업", "461": "상품 중개업",
    "464": "생활용품 도매업", "465": "기계·장비 도매업", "467": "건축자재 도매업",
    "471": "종합 소매업", "478": "무점포 소매업", "492": "육상 운송업",
    "501": "해상 운송업", "511": "항공 운송업", "521": "보관·창고업",
    "529": "운송 관련 서비스업", "551": "숙박업", "561": "음식점업",
    "581": "출판업", "582": "소프트웨어 개발·공급업", "591": "영화·방송 제작업",
    "601": "라디오·TV 방송업", "612": "유선·무선 통신업", "620": "컴퓨터 프로그래밍·시스템 통합",
    "631": "자료 처리·호스팅·포털", "641": "은행업", "649": "기타 금융업",
    "651": "보험업", "661": "금융 지원 서비스업", "681": "부동산 임대·공급업",
    "701": "연구개발업", "711": "법무·회계 서비스업", "713": "광고업",
    "714": "시장조사·경영컨설팅업", "721": "건축·엔지니어링 서비스업",
    "729": "기타 과학기술 서비스업", "731": "사업시설 관리업", "741": "사업 지원 서비스업",
    "851": "교육 서비스업", "861": "병원업", "901": "창작·예술 서비스업",
    "912": "스포츠 서비스업", "913": "오락 서비스업",
}


def _cache_path():
    return os.path.join(config.CACHE_DIR, "company_info.json")


def load_cache():
    p = _cache_path()
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[DART] 캐시 로드 실패: {e}")
    return {}


def save_cache(data):
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    with open(_cache_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0, sort_keys=True)


def fetch_corp_map():
    """종목코드 → DART 법인코드. 목록 파일이 3MB대라 캐시에 저장합니다."""
    p = os.path.join(config.CACHE_DIR, "corp_map.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                m = json.load(f)
            if len(m) > 1000:
                print(f"[DART] 법인코드 캐시 사용 ({len(m):,}개)")
                return m
        except Exception:
            pass
    if not config.DART_API_KEY:
        return {}
    r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                     params={"crtfc_key": config.DART_API_KEY}, timeout=120)
    if r.content[:2] != b"PK":
        print(f"[DART] 법인코드 내려받기 실패: {r.text[:150]}")
        return {}
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    root = ET.fromstring(zf.read(zf.namelist()[0]))
    m = {}
    for x in root.findall(".//list"):
        stock = (x.findtext("stock_code") or "").strip()
        if stock:
            m[stock] = x.findtext("corp_code")
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(m, f)
    print(f"[DART] 상장사 법인코드 {len(m):,}개 확보")
    return m


def _industry(code):
    c = (code or "").strip()
    return KSIC.get(c[:3]) or (f"업종코드 {c}" if c else "")


def enrich(codes):
    """필요한 종목의 기업개황을 캐시에 채우고 {코드: 설명항목} 반환."""
    cache = load_cache()
    todo = [c for c in codes if c not in cache]
    if todo and config.DART_API_KEY:
        cmap = fetch_corp_map()
        added = 0
        for code in todo:
            corp = cmap.get(code)
            if not corp:
                cache[code] = {}
                continue
            try:
                d = requests.get("https://opendart.fss.or.kr/api/company.json",
                                 params={"crtfc_key": config.DART_API_KEY,
                                         "corp_code": corp}, timeout=15).json()
                if d.get("status") == "000":
                    est = (d.get("est_dt") or "")[:4]
                    cache[code] = {
                        "industry": _industry(d.get("induty_code")),
                        "est": est,
                        "ceo": d.get("ceo_nm") or "",
                        "name": d.get("corp_name") or "",
                    }
                    added += 1
                else:
                    cache[code] = {}
            except Exception as e:
                print(f"[DART] {code} 실패: {type(e).__name__}")
                cache[code] = {}
            time.sleep(0.06)
        print(f"[DART] 기업개황 {added}건 신규 수집 (캐시 총 {len(cache)}건)")
        save_cache(cache)
    return {c: cache.get(c) or {} for c in codes}
