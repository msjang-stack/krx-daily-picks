# build.py
# 로컬에서 국내+미국을 한 번에 만들어보고 싶을 때 씁니다. 실제 배포는 이 파일을
# 쓰지 않습니다 — 국내는 daily.yml(run_kr.py), 미국은 us-morning.yml(run_us.py)이
# 각자 독립적으로 돌리고, assemble.py가 둘의 결과물만 모아 dist/로 합칩니다.
#   python build.py   →   dist/ 에 국내+미국 전부 생성

import sys
import traceback

from app import kr_build, us_build

import assemble


def main():
    rc = kr_build.run()
    try:
        us_build.run()
    except Exception:
        print("[미국 시장] 실패, 국내 페이지만 나갑니다")
        traceback.print_exc()
    assemble.run(archive=True)
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
