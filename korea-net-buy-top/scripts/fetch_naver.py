"""stock.naver.com에서 그날 외국인·기관·개인 순매수를 모아 render_html.py용 JSON을 만든다.

사용법: python fetch_naver.py out.json [--top 100] [--workers 16]
(전 종목 약 4,300개를 조회하므로 3~5분 걸린다.)

데이터 출처 (모두 로그인 불필요):
1) 외국인·기관 순매수/순매도 상위 (정확한 금액)
   https://stock.naver.com/api/domestic/market/trend/trendForeignOrg
     ?investorType=FOREIGNER|ORGANIZATION&marketType=KOSPI|KOSDAQ&tradeType=KRX&periodType=DAY&startIdx=0&pageSize=100
   -> sections.buyRankList / sellRankList, accTradeAmount(원), bizdateTo, estimated
2) 전 종목 목록·종가·등락률·거래대금(백만원, 정규장)
   https://m.stock.naver.com/api/stocks/marketValue/{KOSPI|KOSDAQ}?page=N&pageSize=100
3) 종목별 투자자 순매수 수량 (개인 포함), 최근 20거래일
   https://m.stock.naver.com/api/stock/{code}/trend?pageSize=20
   -> foreignerPureBuyQuant, organPureBuyQuant, individualPureBuyQuant, bizdate
5) 지수: https://m.stock.naver.com/api/index/{KOSPI|KOSDAQ}/basic -> closePrice, compareToPreviousClosePrice, fluctuationsRatio
6) 시장 전체 투자자 수급 (기관 세부 포함, 정확값, 최근 20일)
   https://stock.naver.com/api/domestic/market/trend/daily?marketType={KOSPI|KOSDAQ|FUT}&tradeType=KRX&startIdx=0&pageSize=20
   -> content[].netAmounts[].investorGubun / diffValue(원) / buyQuant / sellQuant
   투자자 코드: 9000 외국인, 9001 기타외국인, 8000 개인, 1000 금융투자, 2000 보험, 3000 투신, 3100 사모,
   4000 은행, 5000 기타금융, 6000 연기금, 7000 국가·지자체, 7100 기타법인. 기관계 = 1000~6000 합.
   FUT(코스피200 선물)은 diffValue가 0이라 buyQuant - sellQuant(계약 수)로 순매수를 본다.
7) 원·달러 환율: https://m.stock.naver.com/front-api/marketIndex/productDetail?category=exchange&reutersCode=FX_USDKRW
4) 업종: 코드 목록은 upjong/{1..399}/info 로 찾고, 업종별 종목은
   https://stock.naver.com/api/domestic/market/upjong/{code}/stocklist?sortType=marketCap&sortDirection=desc&size=100(&cursor=)

금액 규칙:
- 외국인·기관: 1)의 상위·하위 100 안에 있으면 그 정확한 금액, 아니면 3)의 수량 × 종가 추정.
- 개인: 항상 3)의 수량 × 종가 추정 (네이버에 개인 금액 순위가 없음).
- 추세(history): 최근 20거래일 섹터별·투자자별 일별 순매수. 날마다 같은 기준이 되도록
  세 투자자 모두 그날 수량 × 그날 종가 추정으로 계산한다. ETF는 제외.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

RANK_API = "https://stock.naver.com/api/domestic/market/trend/trendForeignOrg"
LIST_API = "https://m.stock.naver.com/api/stocks/marketValue/{}?page={}&pageSize=100"
TREND_API = "https://m.stock.naver.com/api/stock/{}/trend?pageSize={}"
HIST_DAYS = 20
UPJONG_INFO = "https://stock.naver.com/api/domestic/market/upjong/{}/info?marketType=ALL"
UPJONG_LIST = "https://stock.naver.com/api/domestic/market/upjong/{}/stocklist"
INDEX_API = "https://m.stock.naver.com/api/index/{}/basic"
MKT_TREND_API = "https://stock.naver.com/api/domestic/market/trend/daily?marketType={}&tradeType=KRX&startIdx=0&pageSize=20"
FX_API = "https://m.stock.naver.com/front-api/marketIndex/productDetail?category=exchange&reutersCode=FX_USDKRW"
INST_CODES = {"1000": "금융투자", "2000": "보험", "3000": "투신", "3100": "사모", "4000": "은행",
              "5000": "기타금융", "6000": "연기금"}
MARKETS = [("KOSPI", "코스피"), ("KOSDAQ", "코스닥")]
COLUMNS = ["종목명", "업종", "순매수 금액(억원)", "종가(원)", "등락률", "거래대금(억원)"]


def get_json(url, retries=2):
    for k in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception:
            if k == retries:
                raise


def n(s):
    try:
        return float(str(s).replace(",", "").replace("+", "").replace("%", ""))
    except (TypeError, ValueError):
        return 0.0


def fetch_rank(investor, market, top):
    q = urllib.parse.urlencode({"investorType": investor, "tradeType": "KRX", "marketType": market,
                                "startIdx": 0, "pageSize": top, "periodType": "DAY"})
    s = get_json(f"{RANK_API}?{q}")["sections"]
    return s["buyRankList"], s.get("sellRankList", [])


def fetch_universe(market):
    first = get_json(LIST_API.format(market, 1))
    pages = -(-int(first["totalCount"]) // 100)
    out = list(first["stocks"])
    for p in range(2, pages + 1):
        out += get_json(LIST_API.format(market, p))["stocks"]
    return out


def fetch_industries(workers):
    def info(c):
        try:
            return c, get_json(UPJONG_INFO.format(c), retries=0).get("name")
        except Exception:
            return c, None
    with ThreadPoolExecutor(workers) as ex:
        names = {c: nm for c, nm in ex.map(info, range(1, 400)) if nm}

    def members(c):
        codes, cursor = [], None
        while True:
            q = {"sortType": "marketCap", "sortDirection": "desc", "size": 100}
            if cursor:
                q["cursor"] = cursor
            d = get_json(UPJONG_LIST.format(c) + "?" + urllib.parse.urlencode(q))
            codes += [it["itemCode"] for it in d.get("items", [])]
            cursor = d.get("cursor")
            if not d.get("hasNext") or not cursor:
                return c, codes
    with ThreadPoolExecutor(workers) as ex:
        sector = {}
        for c, codes in ex.map(members, sorted(names)):
            for code in codes:
                # '기타'(25)보다 구체적인 업종이 있으면 그쪽을 쓴다
                if code not in sector or sector[code] == names.get(25):
                    sector[code] = names[c]
    return sector


def fetch_indices():
    """코스피·코스닥 지수 종가, 전일 대비, 등락률."""
    out = {}
    for mcode, mname in MARKETS:
        try:
            d = get_json(INDEX_API.format(mcode))
            out[mname] = {"close": d.get("closePrice"), "diff": n(d.get("compareToPreviousClosePrice")),
                          "rate": n(d.get("fluctuationsRatio")), "at": d.get("localTradedAt", "")[:10]}
        except Exception:
            pass
    return out


def fetch_context():
    """시장 맥락: 시장별 투자자 수급(기관 세부), 외국인 선물 계약, 환율. 실패한 항목은 빠진다."""
    ctx = {"markets": {}}
    for mcode, mname in MARKETS:
        try:
            days = []
            for row in get_json(MKT_TREND_API.format(mcode))["content"]:
                na = {a["investorGubun"]: int(a["diffValue"]) / 1e8 for a in row["netAmounts"]}
                inst = {nm: round(na.get(c, 0.0), 1) for c, nm in INST_CODES.items()}
                days.append({"date": row["bizdate"], "f": round(na.get("9000", 0.0) + na.get("9001", 0.0), 1),
                             "i": round(na.get("8000", 0.0), 1), "o": round(sum(inst.values()), 1),
                             "etc": round(na.get("7100", 0.0) + na.get("7000", 0.0), 1), "inst": inst})
            ctx["markets"][mname] = sorted(days, key=lambda d: d["date"])
        except Exception:
            pass
    try:
        fut = []
        for row in get_json(MKT_TREND_API.format("FUT"))["content"]:
            q = {a["investorGubun"]: int(n(a["buyQuant"]) - n(a["sellQuant"])) for a in row["netAmounts"]}
            fut.append({"date": row["bizdate"], "f": q.get("9000", 0) + q.get("9001", 0),
                        "i": q.get("8000", 0), "fi": q.get("1000", 0)})
        ctx["futures"] = sorted(fut, key=lambda d: d["date"])
    except Exception:
        pass
    try:
        r = get_json(FX_API)["result"]
        up = (r.get("fluctuationsType") or {}).get("name") == "RISING"
        down = (r.get("fluctuationsType") or {}).get("name") == "FALLING"
        diff = n(r.get("fluctuations"))
        ctx["fx"] = {"close": r.get("closePrice"), "diff": diff if up else -diff if down else 0.0,
                     "rate": n(r.get("fluctuationsRatio")) * (1 if up else -1 if down else 0),
                     "at": (r.get("localTradedAt") or "")[:16].replace("T", " ")}
    except Exception:
        pass
    return ctx


def event_days(days):
    """수급이 기계적으로 왜곡되기 쉬운 날: 옵션 만기(매월 둘째 목요일), 3·6·9·12월은 동시만기,
    MSCI 분기 리뷰 반영일(2·5·8·11월 마지막 거래일). 휴장으로 날짜가 밀리는 경우는 반영하지 않는다."""
    import datetime as dt
    ev = {}
    for d in days:
        t = dt.date(int(d[:4]), int(d[4:6]), int(d[6:]))
        if t.weekday() == 3 and 8 <= t.day <= 14:
            ev[d] = "동시만기" if t.month in (3, 6, 9, 12) else "옵션만기"
    by_month = {}
    for d in days:
        by_month.setdefault(d[:6], []).append(d)
    for ym, ds in by_month.items():
        last = max(ds)
        t = dt.date(int(last[:4]), int(last[4:6]), int(last[6:]))
        nxt = t + dt.timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += dt.timedelta(days=1)
        if t.month in (2, 5, 8, 11) and nxt.month != t.month:
            ev[last] = (ev.get(last, "") + " · " if last in ev else "") + "MSCI 리밸런싱"
    return ev


def fetch_trend(code):
    try:
        return code, get_json(TREND_API.format(code, HIST_DAYS)) or []
    except Exception:
        return code, None


def eok(v):
    return f"{round(v):,}"  # 억원, 소수점 반올림


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--watch", default="", help="관심 종목: 이름 또는 코드, 쉼표로 구분")
    a = ap.parse_args()
    log = lambda *x: print(*x, file=sys.stderr, flush=True)

    # 1) 외국인·기관 정확한 금액
    exact, rank_tables, dates, estimated = {}, {}, set(), False
    for mcode, _ in MARKETS:
        for icode, key in (("FOREIGNER", "f"), ("ORGANIZATION", "o")):
            buy, sell = fetch_rank(icode, mcode, a.top)
            rank_tables[(mcode, key)] = buy
            for it in buy + sell:
                exact[(it["itemcode"], key)] = int(it["accTradeAmount"]) / 1e8
                dates.add(it.get("bizdateTo", ""))
                estimated |= bool(it.get("estimated"))
    date = max(d for d in dates if d)
    log("기준일", date)

    # 2) 전 종목
    uni = {}
    for mcode, mname in MARKETS:
        for s in fetch_universe(mcode):
            uni[s["itemCode"]] = {
                "market": mname, "name": s["stockName"], "etf": s.get("stockEndType") in ("etf", "etn") or "ETN" in s["stockName"],
                "price": n(s.get("closePrice")), "rate": n(s.get("fluctuationsRatio")),
                "value": n(s.get("accumulatedTradingValue")) / 100,  # 백만원 -> 억원
                "mcap": n(s.get("marketValue")),  # 억원
            }
    log("종목 수", len(uni))

    # 3) 업종
    sector = fetch_industries(a.workers)
    log("업종 매핑", len(sector))

    # 4) 종목별 투자자 수량
    with ThreadPoolExecutor(a.workers) as ex:
        hist = dict(ex.map(fetch_trend, list(uni)))
    log("수량 조회 실패", sum(1 for v in hist.values() if v is None))
    trend = {c: (h[0] if h else None) for c, h in hist.items()}

    # 추세: 섹터별 일별 순매수 (억원, 추정)
    history = {}
    for _, mname in MARKETS:
        days = sorted({d["bizdate"] for c, h in hist.items() if h and uni[c]["market"] == mname
                       for d in h if d.get("bizdate")})[-HIST_DAYS:]
        idx = {d: i for i, d in enumerate(days)}
        secs = {}
        for c, h in hist.items():
            u = uni[c]
            if not h or u["market"] != mname or u["etf"]:
                continue
            sec = sector.get(c, "미분류")
            arr = secs.setdefault(sec, {k: [0.0] * len(days) for k in ("f", "o", "i")})
            for d in h:
                i = idx.get(d.get("bizdate"))
                if i is None:
                    continue
                px = n(d.get("closePrice")) / 1e8
                arr["f"][i] += n(d.get("foreignerPureBuyQuant")) * px
                arr["o"][i] += n(d.get("organPureBuyQuant")) * px
                arr["i"][i] += n(d.get("individualPureBuyQuant")) * px
        history[mname] = {"dates": [f"{d[4:6]}/{d[6:]}" for d in days], "days": days,
                          "events": event_days(days),
                          "sectors": {k: {kk: [round(x, 1) for x in vv] for kk, vv in v.items()}
                                      for k, v in secs.items()}}

    # 종목별 20일 이력 (억원 추정 + 종가). 신호 계산용.
    mdays = {m: [d for d in sorted({d["bizdate"] for c, h in hist.items() if h and uni[c]["market"] == m
                                     for d in h if d.get("bizdate")})[-HIST_DAYS:]] for _, m in MARKETS}

    def stock_hist(code, u):
        h = hist.get(code)
        if not h or u["etf"]:
            return None
        days = mdays[u["market"]]
        idx = {d: i for i, d in enumerate(days)}
        out = {k: [0.0] * len(days) for k in ("f", "o", "i")}
        out["c"] = [None] * len(days)
        for d in h:
            i = idx.get(d.get("bizdate"))
            if i is None:
                continue
            px = n(d.get("closePrice"))
            out["c"][i] = px
            for k, q in (("f", "foreignerPureBuyQuant"), ("o", "organPureBuyQuant"), ("i", "individualPureBuyQuant")):
                out[k][i] = round(n(d.get(q)) * px / 1e8, 2)
        # 빈 종가는 앞 값으로 채운다 (거래정지일 등)
        last = None
        for i, v in enumerate(out["c"]):
            if v is None:
                out["c"][i] = last
            else:
                last = v
        if out["c"][0] is None:
            return None
        return out

    stocks = []
    for code, u in uni.items():
        t = trend.get(code)
        if t and t.get("bizdate") != date:
            t = None  # 날짜가 다르면(거래정지 등) 쓰지 않는다
        price = n(t.get("closePrice")) if t else u["price"]
        est = lambda q: n(t.get(q)) * price / 1e8 if t else 0.0
        rec = {
            "code": code, "market": u["market"], "name": u["name"],
            "sector": "ETF" if u["etf"] else sector.get(code, "미분류"),
            "price": int(price), "rate": u["rate"], "value": round(u["value"], 1),
            "f": round(exact.get((code, "f"), est("foreignerPureBuyQuant")), 2),
            "o": round(exact.get((code, "o"), est("organPureBuyQuant")), 2),
            "i": round(est("individualPureBuyQuant"), 2),
            "mcap": round(u["mcap"]),
        }
        sh = stock_hist(code, u)
        if sh:
            # 마지막 날(오늘)은 정확값이 있으면 그것으로 맞춘다
            sh["f"][-1], sh["o"][-1], sh["i"][-1] = rec["f"], rec["o"], rec["i"]
            rec["h"] = sh
        if rec["f"] or rec["o"] or rec["i"]:
            stocks.append(rec)

    # 투자자별 상위 표: 외국인·기관은 순위 API 순서(정확), 개인은 추정 금액 순
    by_code = {s["code"]: s for s in stocks}

    def row(s, amt):
        return [s["name"], s["sector"], eok(amt), f"{s['price']:,}", f"{s['rate']:+.2f}%", eok(s["value"])]

    tables = []
    for mcode, mname in MARKETS:
        for key, iname in (("f", "외국인"), ("o", "기관")):
            rows, secs, amts = [], [], []
            for it in rank_tables[(mcode, key)]:
                s = by_code.get(it["itemcode"]) or {
                    "name": it["itemname"], "sector": "ETF" if it.get("type") == "EF" else "미분류",
                    "price": int(n(it["nowPrice"])), "rate": n(it["prevChangeRate"]), "value": 0.0}
                amt = int(it["accTradeAmount"]) / 1e8
                rows.append(row(s, amt)); secs.append(s["sector"]); amts.append(round(amt, 2))
            tables.append({"market": mname, "investor": iname, "columns": COLUMNS, "rows": rows,
                           "sectors": secs, "amounts": amts, "source": "네이버 증권 (정확한 금액)"})
        ind = sorted((s for s in stocks if s["market"] == mname and s["i"] > 0), key=lambda s: -s["i"])[:a.top]
        tables.append({"market": mname, "investor": "개인", "columns": COLUMNS,
                       "rows": [row(s, s["i"]) for s in ind],
                       "sectors": [s["sector"] for s in ind], "amounts": [s["i"] for s in ind],
                       "source": "네이버 종목별 순매수 수량 × 종가 (추정)"})

    flows = {mname: [s for s in stocks if s["market"] == mname] for _, mname in MARKETS}

    # 관심 종목: 이름(정확히 일치) 또는 코드
    watch = []
    for w in [x.strip() for x in a.watch.split(",") if x.strip()]:
        hit = [s["code"] for s in stocks if s["code"] == w or s["name"] == w]
        watch += hit if hit else [w]
    log("시장 맥락 수집")
    ctx = fetch_context()
    pretty = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    json.dump({"date": pretty, "note": "장중 잠정치" if estimated else "장 마감 기준",
               "indices": fetch_indices(), "context": ctx, "watch": watch,
               "flows": flows, "history": history, "tables": tables},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    log(f"완료 -> {a.out}")


if __name__ == "__main__":
    main()
