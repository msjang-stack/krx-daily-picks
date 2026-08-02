# app/news.py
# 뉴스 수집. 네이버 검색 API를 우선 쓰고, 실패하면 구글 뉴스 RSS로 넘어갑니다.
# 검색이 느슨해 무관한 기사가 섞이므로 종목명이 실제로 들어간 기사만 남깁니다.

import html
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

from . import config

KST = timezone(timedelta(hours=9))
TAG_RE = re.compile(r"<[^>]+>")
S = requests.Session()
S.headers.update(config.UA)


def _clean(t):
    return html.unescape(TAG_RE.sub("", t or "")).strip()


def _ago(dt):
    if not dt:
        return ""
    delta = datetime.now(KST) - dt.astimezone(KST)
    h = delta.total_seconds() / 3600
    if h < 1:
        return f"{max(1, int(delta.total_seconds() // 60))}분 전"
    if h < 24:
        return f"{int(h)}시간 전"
    return f"{int(h // 24)}일 전"


def _relevant(name, title, desc):
    """종목명이 제목이나 본문에 실제로 들어간 기사만 통과."""
    blob = f"{title} {desc}"
    if name in blob:
        return True
    # '삼성전자' → '삼성' 처럼 앞부분만 나오는 경우도 허용 (4자 이상일 때)
    return len(name) >= 4 and name[:3] in blob and any(
        k in blob for k in ("주가", "증권", "코스피", "코스닥", "실적", "공시", "상장")
    )


# ---------------- 네이버 검색 API ----------------

def _naver(query, want, days):
    if not (config.NAVER_CLIENT_ID and config.NAVER_CLIENT_SECRET):
        return None
    r = S.get(
        "https://openapi.naver.com/v1/search/news.json",
        params={"query": query, "display": 30, "sort": "date"},
        headers={"X-Naver-Client-Id": config.NAVER_CLIENT_ID,
                 "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET},
        timeout=15,
    )
    if r.status_code != 200:
        print(f"[뉴스] 네이버 API HTTP {r.status_code}: {r.text[:120]}")
        return None
    cutoff = datetime.now(KST) - timedelta(days=days)
    out = []
    for it in r.json().get("items", []):
        title, desc = _clean(it.get("title")), _clean(it.get("description"))
        if not _relevant(query, title, desc):
            continue
        try:
            pub = datetime.strptime(it.get("pubDate", ""), "%a, %d %b %Y %H:%M:%S %z")
        except ValueError:
            pub = None
        if pub and pub < cutoff:
            continue
        link = it.get("originallink") or it.get("link") or ""
        out.append({"t": title, "url": link,
                    "s": urllib.parse.urlparse(link).netloc.replace("www.", ""),
                    "w": _ago(pub)})
        if len(out) >= want:
            break
    return out


# ---------------- 구글 뉴스 RSS (예비) ----------------

def _google(query, want, days):
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    r = S.get(url, timeout=20)
    if r.status_code != 200:
        return []
    cutoff = datetime.now(KST) - timedelta(days=days)
    out = []
    for it in ET.fromstring(r.content).findall(".//item"):
        title = _clean(it.findtext("title"))
        # 구글은 제목 끝에 ' - 언론사'를 붙입니다.
        src_el = it.find("source")
        src = src_el.text if src_el is not None else ""
        if src and title.endswith(" - " + src):
            title = title[: -(len(src) + 3)]
        if not _relevant(query, title, ""):
            continue
        try:
            pub = datetime.strptime(it.findtext("pubDate"), "%a, %d %b %Y %H:%M:%S %Z")
            pub = pub.replace(tzinfo=timezone.utc)
        except Exception:
            pub = None
        if pub and pub < cutoff:
            continue
        out.append({"t": title, "url": it.findtext("link") or "",
                    "s": src or "구글뉴스", "w": _ago(pub)})
        if len(out) >= want:
            break
    return out


def fetch_for(name, want=3, days=3):
    """한 종목의 최근 뉴스."""
    try:
        got = _naver(name, want, days)
        if got:
            return got
    except Exception as e:
        print(f"[뉴스] {name} 네이버 실패: {type(e).__name__}: {e}")
    try:
        return _google(name, want, days)
    except Exception as e:
        print(f"[뉴스] {name} 구글 실패: {type(e).__name__}: {e}")
        return []


def fetch_market(want=5, days=1):
    """시장 전체 주요 뉴스."""
    items, seen = [], set()
    for q in ("코스피", "코스닥", "증시"):
        try:
            got = _naver(q, want, days) or _google(q, want, days)
        except Exception:
            got = []
        for a in got:
            key = a["t"][:24]
            if key in seen:
                continue
            seen.add(key)
            a = dict(a, tag=q)
            items.append(a)
        time.sleep(0.2)
        if len(items) >= want:
            break
    return items[:want]
