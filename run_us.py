# run_us.py — 미국 빌드만 실행합니다. 국내는 전혀 몰라도 됩니다.
#   python run_us.py   →   cache/us_latest/ 생성 (dist/로 합치려면 assemble.py 실행)
import sys
import traceback

from app import us_build

if __name__ == "__main__":
    try:
        us_build.run()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
