# 임시 진단 스크립트: app/yahoo.py의 실제 함수들을 실 네트워크로 검증합니다.
# 확인 후 삭제합니다.
import sys
sys.path.insert(0, ".")

from app import yahoo


def main():
    print("=== fetch_universe ===")
    universe = yahoo.fetch_universe()
    print(f"종목 수: {len(universe)}")
    print("샘플:", universe[0], universe[1])
    assert len(universe) > 400, "S&P500 종목 수가 너무 적음"

    print("\n=== fetch_daily (AAPL) ===")
    series = yahoo.fetch_daily("AAPL")
    print("일수:", len(series["c"]) if series else None)
    print("마지막 5일:", list(zip(series["d"][-5:], series["c"][-5:], series["v"][-5:])) if series else None)
    assert series and len(series["c"]) >= 2

    print("\n=== fetch_indices ===")
    idx = yahoo.fetch_indices()
    for i in idx:
        print(i["name"], i["val"], i["chg"], i["pct"], "series_len=", len(i["series"]))
    assert len(idx) == 3

    print("\n=== fetch_today_snapshot (첫 15종목만 샘플) ===")
    sample_universe = universe[:15]
    snap = yahoo.fetch_today_snapshot(sample_universe, pace=0.1, progress_every=5)
    for code, v in list(snap.items())[:5]:
        print(code, v["p"], v["pct"], v["vol"], v["val"])
    assert len(snap) >= 10, "샘플 종목 시세 확보 실패율이 너무 높음"

    print("\n모든 진단 통과")


if __name__ == "__main__":
    main()
