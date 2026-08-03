# us_morning.py
# 미국 장 마감 직후(한국시간 아침) 실행: 국내 페이지는 어제(마지막 거래일) 것을
# 그대로 두고, 미국 데이터(dist/us.json, dist/us/charts)만 새로 만들어 배포합니다.
#
# 국내 빌드(build.py)가 오후 16:40에 다시 돌 때 국내·미국 데이터가 함께 정식으로
# 그날 아카이브에 반영됩니다. 이 스크립트는 그 사이 시간대(아침~오후)에 미국 탭이
# 전날 오후 데이터로 멈춰 있는 것을 줄이기 위한 것으로, 아카이브는 건드리지 않습니다.
#   python us_morning.py   →   dist/ 를 어제 사이트로 복원한 뒤 dist/us.json만 새로 만듦

import os
import shutil
import sys

from app import config, us_build


def restore_latest_site() -> bool:
    """cache/archive/의 가장 최근 날짜 사이트를 dist/로 복원합니다.
    (평소 build.py가 오늘자를 저장하는 바로 그 캐시를 그대로 읽습니다.)
    아직 한 번도 빌드된 적이 없으면(캐시 없음) 복원할 게 없어 False를 돌려줍니다.
    """
    archive_root = os.path.join(config.CACHE_DIR, "archive")
    if not os.path.isdir(archive_root):
        print("[아침 갱신] 캐시에 저장된 이전 사이트가 없어 건너뜁니다")
        return False
    dates = sorted(n for n in os.listdir(archive_root) if os.path.isdir(os.path.join(archive_root, n)))
    if not dates:
        print("[아침 갱신] 아카이브가 비어 있어 건너뜁니다")
        return False
    latest = dates[-1]
    print(f"[아침 갱신] {latest} 사이트를 기준으로 복원합니다")

    if os.path.exists(config.OUT_DIR):
        shutil.rmtree(config.OUT_DIR)
    shutil.copytree(os.path.join(archive_root, latest), config.OUT_DIR)

    # 날짜 선택 목록도 그대로 복원합니다 (사이트가 배포될 때 필요).
    dist_archive = os.path.join(config.OUT_DIR, "archive")
    if os.path.exists(dist_archive):
        shutil.rmtree(dist_archive)
    shutil.copytree(archive_root, dist_archive)
    return True


def save_pending_cache():
    """오후 국내 빌드(build.py)가 미국 데이터를 다시 받아오지 않고 재사용할 수 있도록,
    방금 만든 dist/us.json + dist/us/charts를 캐시에도 남겨 둡니다."""
    pending = os.path.join(config.CACHE_DIR, "us_pending")
    if os.path.exists(pending):
        shutil.rmtree(pending)
    os.makedirs(pending, exist_ok=True)
    shutil.copy2(os.path.join(config.OUT_DIR, "us.json"), os.path.join(pending, "us.json"))
    src_charts = os.path.join(config.OUT_DIR, "us", "charts")
    if os.path.isdir(src_charts):
        shutil.copytree(src_charts, os.path.join(pending, "us", "charts"))


def main():
    if not restore_latest_site():
        return 1
    us_build.run()
    save_pending_cache()
    print("[아침 갱신] 완료 — 국내 페이지는 어제 것 그대로, 미국 데이터만 새로 만들었습니다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
