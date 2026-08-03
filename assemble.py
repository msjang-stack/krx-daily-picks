# assemble.py
# 국내(cache/kr_latest/)와 미국(cache/us_latest/)은 서로를 모르고 각자 자기
# 자리에만 결과물을 씁니다. 이 파일이 유일하게 둘을 알고, 최신 것들을 모아
# dist/로 합칩니다. 한쪽이 아직 없거나 실패했으면 있는 것만 나갑니다.
#
#   python assemble.py            → dist/ 로 합치기만 (미국 갱신 뒤: us-morning.yml)
#   python assemble.py --archive  → 합친 뒤 오늘자로 정식 보관까지 (국내 빌드 뒤: daily.yml)

import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

from app import config

KST = timezone(timedelta(hours=9))
WEEKDAY = config.WEEKDAY


def _copy_kr():
    src = config.KR_CACHE_DIR
    if not os.path.isdir(src):
        print("[조립] 국내 데이터 없음 (아직 안 만들어졌거나 실패) — 건너뜁니다")
        return
    for name in os.listdir(src):
        if name == "meta.json":
            continue
        s, d = os.path.join(src, name), os.path.join(config.OUT_DIR, name)
        if os.path.isdir(s):
            if os.path.exists(d):
                shutil.rmtree(d)
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    print("[조립] 국내 데이터 반영")


def _copy_us():
    src = config.US_CACHE_DIR
    if not os.path.isdir(src) or not os.path.exists(os.path.join(src, "us.json")):
        print("[조립] 미국 데이터 없음 (아직 안 만들어졌거나 실패) — 건너뜁니다")
        return
    shutil.copy2(os.path.join(src, "us.json"), os.path.join(config.OUT_DIR, "us.json"))
    dst_us_dir = os.path.join(config.OUT_DIR, "us")
    if os.path.exists(dst_us_dir):
        shutil.rmtree(dst_us_dir)
    shutil.copytree(os.path.join(src, "us"), dst_us_dir)
    print("[조립] 미국 데이터 반영")


def _archive():
    """오늘자 dist/ 전체(국내+미국)를 날짜별로 보관합니다. 국내 빌드가 남긴
    meta.json의 거래일을 기준으로 삼습니다 — '그날'의 정의는 국내 장 기준입니다."""
    meta_path = os.path.join(config.KR_CACHE_DIR, "meta.json")
    if not os.path.exists(meta_path):
        print("[아카이브] 국내 데이터가 없어 건너뜁니다")
        return
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    date_iso = meta["dateISO"]
    dt = datetime.fromisoformat(meta["dt"])

    now = datetime.now(KST)
    # 평일이라도 국내만 쉬면 dt가 today보다 과거로 남습니다. 그럴 때 이미 확정된
    # 과거 아카이브를 (그새 새로 갱신됐을 수 있는) 미국 데이터로 덮어쓰지 않도록 막습니다.
    fresh = dt.date() == now.date()
    if not fresh:
        print(f"[아카이브] 국내 장이 오늘({now:%Y-%m-%d}) 쉬어 마지막 거래일({date_iso}) 기준으로 판단합니다")

    archive_root = os.path.join(config.CACHE_DIR, "archive")
    os.makedirs(archive_root, exist_ok=True)

    today_dir = os.path.join(archive_root, date_iso)
    if fresh or not os.path.exists(today_dir):
        if os.path.exists(today_dir):
            shutil.rmtree(today_dir)
        shutil.copytree(config.OUT_DIR, today_dir, ignore=shutil.ignore_patterns("archive"))
    else:
        print(f"[아카이브] {date_iso}는 이미 확정된 기록이라 건드리지 않습니다")

    dt_naive = dt.replace(tzinfo=None) if dt.tzinfo else dt
    cutoff = dt_naive - timedelta(days=config.ARCHIVE_DAYS)
    for name in os.listdir(archive_root):
        path = os.path.join(archive_root, name)
        if not os.path.isdir(path):
            continue
        try:
            d = datetime.strptime(name, "%Y-%m-%d")
        except ValueError:
            continue
        if d < cutoff:
            shutil.rmtree(path)
            print(f"[아카이브] {name} 삭제 (보관기간 {config.ARCHIVE_DAYS}일 초과)")

    dates = sorted(
        (n for n in os.listdir(archive_root) if os.path.isdir(os.path.join(archive_root, n))),
        reverse=True,
    )
    manifest = []
    for d in dates:
        dt_d = datetime.strptime(d, "%Y-%m-%d")
        manifest.append({
            "iso": d,
            "label": f"{dt_d.month}월 {dt_d.day}일 ({WEEKDAY[dt_d.weekday()][0]})",
        })
    with open(os.path.join(archive_root, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)

    print(f"[아카이브] {date_iso} 저장 (보관 중 {len(dates)}일치)")


def _rebuild_dist_archive():
    """date-picker 목록(archive/)을 캐시 전체의 최신 상태로 맞춥니다.
    미국만 갱신한 조립(--archive 없이)에서도 날짜 목록은 그대로 보여야 합니다."""
    archive_root = os.path.join(config.CACHE_DIR, "archive")
    dist_archive = os.path.join(config.OUT_DIR, "archive")
    if os.path.exists(dist_archive):
        shutil.rmtree(dist_archive)
    if os.path.isdir(archive_root):
        shutil.copytree(archive_root, dist_archive)


def run(archive: bool):
    os.makedirs(config.OUT_DIR, exist_ok=True)
    _copy_kr()
    _copy_us()
    if archive:
        _archive()
    _rebuild_dist_archive()
    print(f"[조립] 완료 → {config.OUT_DIR}/")


if __name__ == "__main__":
    run(archive="--archive" in sys.argv)
