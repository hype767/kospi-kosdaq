"""쌓아 둔 일별 데이터(fetch_naver.py 결과 JSON, .json 또는 .json.gz)로 신호를 긴 기간에 걸쳐 점검한다.

사용법: python archive_check.py 폴더 [--fwd 5] [--top 20]

각 날짜 파일에서 '수급 강도 상위 N종목'(외국인+기관 순매수 ÷ 시가총액, 시총 500억 이상, ETF 제외,
순매수 3억 이상)을 고르고, 다른 날짜 파일들에 들어 있는 종가 이력으로 fwd거래일 뒤 수익률을 구해
같은 날 신호 대상 전체 평균과 비교한다. 결과는 표준 출력으로 요약한다.
파일이 많을수록(몇 달치) 의미가 생긴다. 과거 결과가 앞으로를 보장하지 않는다.
"""
import argparse
import glob
import gzip
import json
import os
import statistics as st

MIN_MCAP, MIN_AMT, MIN_VALUE = 500, 3, 10


def load(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--fwd", type=int, default=5)
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.folder, "*.json")) + glob.glob(os.path.join(a.folder, "*.json.gz")))
    if not files:
        print("데이터 파일이 없어요.")
        return
    prices = {}     # (code, YYYYMMDD) -> 종가
    picks = []      # (YYYYMMDD, market, [codes], [universe codes])
    for p in files:
        d = load(p)
        for m, hist in d.get("history", {}).items():
            days = hist.get("days") or []
            fl = d.get("flows", {}).get(m, [])
            for r in fl:
                h = r.get("h")
                if h:
                    for day, c in zip(days, h["c"]):
                        if c:
                            prices[(r["code"], day)] = c
            if not days:
                continue
            today = days[-1]
            U = [r for r in fl if r.get("h") and r["sector"] != "ETF" and "ETN" not in r["name"] and "스팩" not in r["name"] and r.get("mcap", 0) >= MIN_MCAP and r.get("value", 0) >= MIN_VALUE]
            cand = [r for r in U if r["f"] + r["o"] >= MIN_AMT]
            top = sorted(cand, key=lambda r: -(r["f"] + r["o"]) / r["mcap"])[:a.top]
            picks.append((today, m, [r["code"] for r in top], [r["code"] for r in U]))

    all_days = sorted({day for (_, day) in prices})
    pos = {day: i for i, day in enumerate(all_days)}
    rows = []
    for day, m, top, uni in picks:
        i = pos.get(day)
        if i is None or i + a.fwd >= len(all_days):
            continue
        later = all_days[i + a.fwd]

        def fr(c):
            p0, p1 = prices.get((c, day)), prices.get((c, later))
            return (p1 / p0 - 1) * 100 if p0 and p1 else None
        t = [x for x in map(fr, top) if x is not None]
        u = [x for x in map(fr, uni) if x is not None]
        if len(t) >= a.top // 2 and u:
            rows.append((day, m, st.mean(t), st.mean(u)))
    if not rows:
        print(f"{a.fwd}거래일 뒤 가격이 있는 날짜가 아직 없어요. 기록이 더 쌓여야 해요.")
        return
    for m in sorted({r[1] for r in rows}):
        rs = [r for r in rows if r[1] == m]
        ex = [r[2] - r[3] for r in rs]
        print(f"[{m}] {len(rs)}일 · 상위 {a.top}종목 {a.fwd}일 뒤 평균 {st.mean(r[2] for r in rs):+.2f}% "
              f"/ 시장 {st.mean(r[3] for r in rs):+.2f}% / 초과 {st.mean(ex):+.2f}%p "
              f"(중앙값 {st.median(ex):+.2f}%p) · 앞선 날 {sum(1 for x in ex if x > 0)}/{len(ex)}")


if __name__ == "__main__":
    main()
