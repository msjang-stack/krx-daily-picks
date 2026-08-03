# run_kr.py — 국내 빌드만 실행합니다. 미국은 전혀 몰라도 됩니다.
#   python run_kr.py   →   cache/kr_latest/ 생성 (dist/로 합치려면 assemble.py 실행)
import sys
import traceback

from app import kr_build

if __name__ == "__main__":
    try:
        sys.exit(kr_build.run())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
