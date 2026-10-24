"""투자자별 순매수 JSON을 한 장짜리 HTML 페이지로 렌더링한다.

사용법: python render_html.py data.json out.html

JSON 형식 (fetch_naver.py가 만든다):
{
  "date": "2026-10-23", "note": "장 마감 기준",
  "tables": [
    {"market": "코스피", "investor": "외국인",
     "columns": ["종목명", "업종", "순매수 금액(억원)", "종가(원)", "등락률", "거래대금(억원)"],
     "rows": [[...], ...],
     "sectors": [...], "amounts": [...],   # rows와 같은 순서 (섹터 통계·막대용)
     "source": "네이버 증권",
     "missing": "rows가 비었을 때 보여줄 사유"}
  ]
}

화면 구성 (읽기 쉽게 한 번에 하나씩):
  [코스피 | 코스닥] 시장 탭
    요약 카드: 투자자별 1위 종목, 돈이 가장 많이 몰린 업종, 쌍끌이 수
    섹터 통계: 투자자별 업종 순매수 막대 (ETF는 막대에서 빼고 따로 합계)
    쌍끌이 종목: 외국인·기관이 모두 순매수한 종목 칩
    [외국인 | 기관 | 개인] 투자자 탭 → 표 하나를 넓게, 처음 30개 + '100위까지 보기'
"""
import html
import json
import sys
from collections import defaultdict

MARKETS = [("코스피", "kospi"), ("코스닥", "kosdaq")]
INVESTORS = [("외국인", "f"), ("기관", "o"), ("개인", "i")]
SECTOR_TOP = 10
FIRST_ROWS = 30

CSS = """
:root{--bg:#f7f7f5;--fg:#191917;--muted:#6b6b66;--line:#e6e5e0;--card:#fff;--soft:#f1f0ec;
--up:#d1242f;--down:#1f5fd1;--star:#b7791f;--f:#2f6bdb;--o:#d4831a;--i:#2f9a66;--sel:#191917;--sel-fg:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#121211;--fg:#ecebe6;--muted:#9a9993;--line:#2b2b29;--card:#1b1b19;--soft:#232321;
--up:#ff6b6b;--down:#6aa1ff;--star:#f0b847;--f:#6f9bf0;--o:#f0b05a;--i:#6cc79a;--sel:#ecebe6;--sel-fg:#121211}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:1080px;margin:0 auto;padding:28px 16px 56px}
h1{font-size:24px;margin:0}
.sub{color:var(--muted);font-size:14px;margin-top:2px}
.mtabs{display:flex;gap:8px;position:sticky;top:0;z-index:5;background:var(--bg);padding:14px 0 12px;margin-top:8px}
.mtabs button,.itabs button{font:inherit;cursor:pointer;color:var(--fg);background:var(--card);border:1px solid var(--line)}
.mtabs button{font-size:17px;font-weight:700;padding:9px 22px;border-radius:999px}
.mtabs button[aria-selected=true]{background:var(--sel);color:var(--sel-fg);border-color:var(--sel)}
.mtabs .ix{font-size:14px;font-weight:600;margin-left:10px;font-variant-numeric:tabular-nums}
.mtabs button[aria-selected=true] .ix.up{color:#ff8a8a}.mtabs button[aria-selected=true] .ix.down{color:#8ab4ff}
@media (prefers-color-scheme:dark){.mtabs button[aria-selected=true] .ix.up{color:var(--up)}.mtabs button[aria-selected=true] .ix.down{color:var(--down)}}
@media (max-width:480px){.mtabs button{padding:8px 14px;font-size:15px}.mtabs .ix{display:block;margin:0;font-size:12.5px}}
section[hidden],.panel[hidden]{display:none}
h2{font-size:17px;margin:28px 0 10px}
h2 small{font-size:13px;font-weight:400;color:var(--muted);margin-left:6px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(220px,44%),1fr));gap:12px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi .k{font-size:13px;color:var(--muted)}
.kpi .v{font-size:19px;font-weight:700;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kpi .d{font-size:13px;color:var(--muted)}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:1px}
.dot.f{background:var(--f)}.dot.o{background:var(--o)}.dot.i{background:var(--i)}
.sgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.box h3{font-size:15px;margin:0 0 10px}
.srow{display:grid;grid-template-columns:8.5em 1fr auto;align-items:center;gap:10px;padding:4px 0;font-size:14px}
.srow .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.srow .track{height:10px;background:var(--soft);border-radius:5px;overflow:hidden}
.srow .fill{height:100%;border-radius:5px}
.fill.f{background:var(--f)}.fill.o{background:var(--o)}.fill.i{background:var(--i)}
.srow .val{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
.srow .val small{color:var(--muted);margin-left:4px}
.etf{font-size:13px;color:var(--muted);margin-top:8px;padding-top:8px;border-top:1px solid var(--line)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-size:14px}
.chip b{color:var(--star);margin-right:4px}
.itabs{display:flex;gap:0;margin:28px 0 0;border-bottom:2px solid var(--line)}
.itabs button{border:0;background:none;font-size:16px;font-weight:600;color:var(--muted);padding:10px 18px;margin-bottom:-2px;border-bottom:3px solid transparent}
.itabs button[aria-selected=true]{color:var(--fg)}
.itabs button[data-c=f][aria-selected=true]{border-bottom-color:var(--f)}
.itabs button[data-c=o][aria-selected=true]{border-bottom-color:var(--o)}
.itabs button[data-c=i][aria-selected=true]{border-bottom-color:var(--i)}
.panel{background:var(--card);border:1px solid var(--line);border-top:0;border-radius:0 0 12px 12px;padding:6px 0 10px}
.meta{font-size:13px;color:var(--muted);padding:6px 16px 4px}
.tw{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14.5px}
th{font-size:13px;color:var(--muted);font-weight:600;text-align:right;padding:8px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
th.l,td.l{text-align:left}
td.rk{color:var(--muted);width:3em}
td.nm{font-weight:600}
td.sc{color:var(--muted);font-size:13.5px;max-width:12em;overflow:hidden;text-overflow:ellipsis}
td.amt{font-weight:700;min-width:10em}
td.amt .b{display:inline-block;height:6px;border-radius:3px;margin-right:8px;vertical-align:middle;opacity:.85}
.b.f{background:var(--f)}.b.o{background:var(--o)}.b.i{background:var(--i)}
.star{color:var(--star);margin-left:4px}
.up{color:var(--up)}.down{color:var(--down)}
tr.more{display:none}
.panel.open tr.more{display:table-row}
.morebtn{display:block;margin:12px auto 4px;font:inherit;font-size:14px;cursor:pointer;color:var(--fg);background:var(--soft);border:0;border-radius:999px;padding:8px 20px}
.panel.open .morebtn{display:none}
.missing{padding:28px 16px;color:var(--muted)}
.fgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}
.frow{display:grid;grid-template-columns:minmax(6em,10em) 1fr 14em;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--line)}
.frow:last-child{border-bottom:0}
.frow .nm{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.frow .nm small{display:block;font-weight:400;font-size:12.5px;color:var(--muted);overflow:hidden;text-overflow:ellipsis}
.frow .track{height:12px;background:var(--soft);border-radius:6px;overflow:hidden}
.frow .fill{display:block;height:100%;border-radius:6px}
.fill.in{background:var(--up)}.fill.out{background:var(--down)}
.frow .val{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:700}
.frow .val small{display:block;font-weight:400;font-size:12px;color:var(--muted)}
.frow .val .in{color:var(--up)}.frow .val .out{color:var(--down)}
.kpi .v.in{color:var(--up)}.kpi .v.out{color:var(--down)}
.kpi .d b{font-weight:600}
.note{font-size:13px;color:var(--muted);margin-top:8px}
details.detail{margin-top:32px}
.vtabs{display:inline-flex;background:var(--soft);border-radius:999px;padding:3px;margin:2px 0 6px;flex-wrap:wrap}
.vtabs button{font:inherit;font-size:14px;cursor:pointer;border:0;background:none;color:var(--muted);padding:6px 14px;border-radius:999px}
.vtabs button[aria-selected=true]{background:var(--card);color:var(--fg);font-weight:700;box-shadow:0 1px 2px rgba(0,0,0,.12)}
h3.sh{font-size:14px;color:var(--muted);margin:14px 0 8px;font-weight:600}
.fgrid.one{grid-template-columns:1fr}
.spark .axis{stroke:var(--line);stroke-width:1}.spark .sin{fill:var(--up)}.spark .sout{fill:var(--down)}
table.trend td{padding:7px 10px}table.trend td.st{font-size:13px;min-width:7em}
.dot.i{background:var(--i)}
details.detail>summary{cursor:pointer;font-size:17px;font-weight:700;list-style:none;padding:12px 16px;background:var(--card);border:1px solid var(--line);border-radius:12px}
details.detail>summary::after{content:" ▾";color:var(--muted)}
details.detail[open]>summary::after{content:" ▴"}
@media (max-width:600px){td.sc,th.sc{display:none}.srow{grid-template-columns:6.5em 1fr auto}.frow{grid-template-columns:1fr auto;grid-template-areas:"nm val" "tr tr";row-gap:6px}.frow .nm{grid-area:nm}.frow .val{grid-area:val}.frow .track{grid-area:tr}}
"""

JS = """
(function(){
  function tabs(sel,onShow){
    var groups={};
    [].slice.call(document.querySelectorAll(sel)).forEach(function(b){
      (groups[b.dataset.group]=groups[b.dataset.group]||[]).push(b);});
    Object.keys(groups).forEach(function(g){
      var bs=groups[g];
      function show(id){bs.forEach(function(b){var on=b.dataset.target===id;
        b.setAttribute('aria-selected',on);document.getElementById(b.dataset.target).hidden=!on;});
        if(onShow)onShow(id);}
      bs.forEach(function(b){b.addEventListener('click',function(){show(b.dataset.target);});});
      var h=(location.hash||'').slice(1);
      show(bs.some(function(b){return b.dataset.target===h;})?h:bs[0].dataset.target);
    });
  }
  tabs('.mtabs button',function(id){try{history.replaceState(null,'','#'+id);}catch(e){}});
  tabs('.itabs button');
  tabs('.vtabs button');
  [].slice.call(document.querySelectorAll('.morebtn')).forEach(function(b){
    b.addEventListener('click',function(){b.closest('.panel').classList.add('open');});});
})();
"""


def esc(v) -> str:
    return html.escape(str(v))


def inv_key(name: str) -> str:
    return "기관" if name.startswith("기관") else name


def num(s) -> float:
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return 0.0


def stock_table(t: dict, c: str, both: set) -> str:
    rows = t.get("rows") or []
    if not rows:
        return f'<div class="missing">{esc(t.get("missing", "데이터 없음"))}</div>'
    cols = t["columns"]
    ix = {name: i for i, name in enumerate(cols)}
    i_nm, i_sc = 0, ix.get("업종")
    i_amt = next(i for i, n in enumerate(cols) if n.startswith("순매수 금액"))
    i_rt = next((i for i, n in enumerate(cols) if "등락" in n), None)
    rest = [i for i in range(len(cols)) if i not in (i_nm, i_sc, i_amt)]
    peak = max(num(r[i_amt]) for r in rows) or 1

    head = ('<tr><th class="l">#</th><th class="l">종목명</th>'
            + (f'<th class="l sc">업종</th>' if i_sc is not None else "")
            + f'<th>{esc(cols[i_amt])}</th>'
            + "".join(f"<th>{esc(cols[i])}</th>" for i in rest) + "</tr>")
    body = []
    for k, r in enumerate(rows, 1):
        star = '<span class="star" title="외국인·기관 동반 순매수">★</span>' if str(r[i_nm]) in both else ""
        w = max(3, round(num(r[i_amt]) / peak * 60))
        tds = [f'<td class="l rk">{k}</td>', f'<td class="l nm">{esc(r[i_nm])}{star}</td>']
        if i_sc is not None:
            tds.append(f'<td class="l sc" title="{esc(r[i_sc])}">{esc(r[i_sc])}</td>')
        tds.append(f'<td class="amt"><span class="b {c}" style="width:{w}px"></span>{round(num(r[i_amt])):,}</td>')
        for i in rest:
            v = str(r[i])
            if "억원" in cols[i] and v:
                v = f"{round(num(v)):,}"
            cls = (' class="up"' if v.startswith("+") else ' class="down"' if v.startswith("-") else "") if i == i_rt else ""
            tds.append(f"<td{cls}>{esc(v)}</td>")
        body.append(f'<tr{" class=\"more\"" if k > FIRST_ROWS else ""}>' + "".join(tds) + "</tr>")
    more = (f'<button type="button" class="morebtn">{len(rows)}위까지 모두 보기</button>'
            if len(rows) > FIRST_ROWS else "")
    meta = f'{len(rows)}종목 · 순매수 금액 순 · 출처: {esc(t.get("source", ""))}'
    return (f'<div class="meta">{meta}</div><div class="tw"><table><thead>{head}</thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>{more}')


def sector_box(t: dict, label: str, c: str) -> str:
    agg = defaultdict(lambda: [0.0, 0])
    for s, a in zip(t.get("sectors", []), t.get("amounts", [])):
        agg[s][0] += a
        agg[s][1] += 1
    etf = agg.pop("ETF", None)
    ranked = sorted(agg.items(), key=lambda kv: -kv[1][0])[:SECTOR_TOP]
    peak = ranked[0][1][0] if ranked else 1
    rows = "".join(
        f'<div class="srow"><span class="nm" title="{esc(n)}">{esc(n)}</span>'
        f'<span class="track"><span class="fill {c}" style="width:{max(2, a / peak * 100):.0f}%;display:block"></span></span>'
        f'<span class="val">{a:,.0f}억<small>{k}종목</small></span></div>'
        for n, (a, k) in ranked)
    etf_line = (f'<div class="etf">ETF {etf[1]}종목 합계 {etf[0]:,.0f}억 (막대에서 제외)</div>' if etf else "")
    return f'<div class="box"><h3><span class="dot {c}"></span>{esc(label)}</h3>{rows}{etf_line}</div>'


def top_sector(ts: list):
    agg = defaultdict(float)
    for t in ts:
        for s, a in zip(t.get("sectors", []), t.get("amounts", [])):
            if s != "ETF":
                agg[s] += a
    return max(agg.items(), key=lambda kv: kv[1]) if agg else None


VIEWS = [("fo", "외국인+기관", ("f", "o")), ("f", "외국인", ("f",)), ("o", "기관", ("o",)), ("i", "개인", ("i",))]


def signed(v: float) -> str:
    return f"{v:+,.0f}"


def split_line(r) -> str:
    parts = [("f", "외"), ("o", "기"), ("i", "개")]
    return " · ".join(f'<span class="dot {k}"></span>{lab} {signed(r.get(k, 0))}' for k, lab in parts if k in r)


def amt(r, keys) -> float:
    return sum(r.get(k, 0.0) for k in keys)


def flow_rows(items, keys, peak, sub) -> str:
    out = []
    for r in items:
        tot = amt(r, keys)
        cls = "in" if tot >= 0 else "out"
        w = max(2, abs(tot) / peak * 100) if peak else 2
        out.append(
            f'<div class="frow"><span class="nm" title="{esc(r["name"])}">{esc(r["name"])}<small>{sub(r)}</small></span>'
            f'<span class="track"><span class="fill {cls}" style="width:{w:.0f}%"></span></span>'
            f'<span class="val"><span class="{cls}">{signed(tot)}억</span><small>{split_line(r)}</small></span></div>')
    return "".join(out)


def sector_agg(fl):
    agg = {}
    for r in fl:
        if r["sector"] == "ETF":
            continue
        a = agg.setdefault(r["sector"], {"name": r["sector"], "f": 0.0, "o": 0.0, "i": 0.0, "n": 0})
        for k in ("f", "o", "i"):
            a[k] += r.get(k, 0.0)
        a["n"] += 1
    return list(agg.values())


def view_panel(fl, keys) -> str:
    stocks = [r for r in fl if r["sector"] != "ETF"]
    secs = sector_agg(fl)
    sin = sorted([x for x in secs if amt(x, keys) > 0], key=lambda x: -amt(x, keys))[:10]
    sout = sorted([x for x in secs if amt(x, keys) < 0], key=lambda x: amt(x, keys))[:8]
    tin = sorted([r for r in stocks if amt(r, keys) > 0], key=lambda r: -amt(r, keys))[:15]
    tout = sorted([r for r in stocks if amt(r, keys) < 0], key=lambda r: amt(r, keys))[:15]
    sp = max([abs(amt(x, keys)) for x in sin + sout] or [1])
    tp = max([abs(amt(r, keys)) for r in tin + tout] or [1])
    ssub = lambda x: f'{x["n"]}종목'
    tsub = lambda r: f'{esc(r["sector"])} · <span class="{"up" if r["rate"] >= 0 else "down"}">{r["rate"]:+.2f}%</span>'
    etf = sum(amt(r, keys) for r in fl if r["sector"] == "ETF")
    return (
        '<h3 class="sh">섹터별</h3><div class="fgrid">'
        f'<div class="box"><h3>돈이 들어온 섹터</h3>{flow_rows(sin, keys, sp, ssub)}</div>'
        f'<div class="box"><h3>돈이 빠진 섹터</h3>{flow_rows(sout, keys, sp, ssub)}</div></div>'
        '<h3 class="sh">종목별</h3><div class="fgrid">'
        f'<div class="box"><h3>돈이 들어온 종목 TOP {len(tin)}</h3>{flow_rows(tin, keys, tp, tsub)}</div>'
        f'<div class="box"><h3>돈이 빠진 종목 TOP {len(tout)}</h3>{flow_rows(tout, keys, tp, tsub)}</div></div>'
        f'<div class="note">ETF는 따로 합계 {signed(etf)}억.</div>')


def vtabs(group: str, panels: dict, default_note: str = "") -> str:
    btns = "".join(f'<button type="button" data-group="{group}" data-target="{group}-{k}" data-c="{k}">{lab}</button>'
                   for k, lab, _ in VIEWS if k in panels)
    body = "".join(f'<div id="{group}-{k}" hidden>{panels[k]}</div>' for k, _, _ in VIEWS if k in panels)
    return f'<div class="vtabs">{btns}</div>{body}'


def spark(vals) -> str:
    if not vals:
        return ""
    peak = max(abs(v) for v in vals) or 1
    w, h, bw = 120, 28, 120 / len(vals)
    bars = []
    for i, v in enumerate(vals):
        bh = max(1, abs(v) / peak * (h / 2 - 1))
        y = h / 2 - bh if v >= 0 else h / 2
        bars.append(f'<rect x="{i * bw + 0.5:.1f}" y="{y:.1f}" width="{max(1, bw - 1.5):.1f}" height="{bh:.1f}" '
                    f'class="{"sin" if v >= 0 else "sout"}"/>')
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true">'
            f'<line x1="0" x2="{w}" y1="{h/2}" y2="{h/2}" class="axis"/>{"".join(bars)}</svg>')


def streak(vals) -> int:
    if not vals:
        return 0
    sign = vals[-1] > 0
    k = 0
    for v in reversed(vals):
        if (v > 0) == sign and v != 0:
            k += 1
        else:
            break
    return k if sign else -k


def trend_panel(hist, keys) -> str:
    dates = hist["dates"]
    rows = []
    for name, d in hist["sectors"].items():
        daily = [sum(d[k][i] for k in keys) for i in range(len(dates))]
        rows.append((name, daily, sum(daily[-5:]), sum(daily)))
    def table(items, title):
        trs = []
        for name, daily, s5, s20 in items:
            st = streak(daily)
            st_txt = ('<span class="up">오늘 유입</span>' if st == 1 else
                      '<span class="down">오늘 유출</span>' if st == -1 else
                      f'<span class="up">{st}일 연속 유입</span>' if st > 1 else
                      f'<span class="down">{-st}일 연속 유출</span>' if st < -1 else "")
            c5, c20 = ("up" if s5 >= 0 else "down"), ("up" if s20 >= 0 else "down")
            trs.append(f'<tr><td class="l nm">{esc(name)}</td><td class="l">{spark(daily)}</td>'
                       f'<td class="{c5}">{signed(s5)}</td><td class="{c20}"><b>{signed(s20)}</b></td>'
                       f'<td class="st">{st_txt}</td></tr>')
        return (f'<div class="box"><h3>{title}</h3><div class="tw"><table class="trend"><thead><tr>'
                f'<th class="l">업종</th><th class="l">일별 흐름 ({esc(dates[0])}~{esc(dates[-1])})</th>'
                f'<th>5일</th><th>{len(dates)}일 누적</th><th>연속</th></tr></thead><tbody>{"".join(trs)}</tbody></table></div></div>')
    tin = sorted([r for r in rows if r[3] > 0], key=lambda r: -r[3])[:8]
    tout = sorted([r for r in rows if r[3] < 0], key=lambda r: r[3])[:8]
    return (f'<div class="fgrid one">{table(tin, f"{len(dates)}거래일 누적 돈이 들어온 섹터")}'
            f'{table(tout, f"{len(dates)}거래일 누적 돈이 빠진 섹터")}</div>')


def market_section(m: str, anchor: str, ts: list, fl, hist) -> str:
    by = {inv_key(t["investor"]): t for t in ts}
    names = lambda k: [str(r[0]) for r in (by.get(k, {}).get("rows") or [])]
    both = set(names("외국인")) & set(names("기관"))

    cards, flow_html, trend_html = "", "", ""
    if fl:
        has_i = any(r.get("i") for r in fl)
        views = [v for v in VIEWS if v[0] != "i" or has_i]
        keys0 = views[0][2]
        stocks = [r for r in fl if r["sector"] != "ETF"]
        secs = sector_agg(fl)
        def kpi(label, r, keys):
            v = amt(r, keys); cls = "in" if v >= 0 else "out"
            return (f'<div class="kpi"><div class="k">{label}</div><div class="v {cls}">{esc(r["name"])}</div>'
                    f'<div class="d"><b>{signed(v)}억</b> · {split_line(r)}</div></div>')
        pick = lambda xs, rev: sorted(xs, key=lambda x: amt(x, keys0), reverse=rev)[0] if xs else None
        for label, r in (("돈이 가장 많이 들어온 섹터", pick(secs, True)), ("돈이 가장 많이 들어온 종목", pick(stocks, True)),
                         ("돈이 가장 많이 빠진 섹터", pick(secs, False)), ("돈이 가장 많이 빠진 종목", pick(stocks, False))):
            if r:
                cards += kpi(label, r, keys0)
        flow_html = ('<h2>오늘 자금 흐름<small>누구 돈 기준으로 볼지 고르세요 · ETF 제외 · 단위 억원</small></h2>'
                     + vtabs(f"{anchor}-flow", {k: view_panel(fl, keys) for k, _, keys in views}))
        if hist and hist.get("sectors"):
            trend_html = ('<h2>섹터 추세<small>최근 20거래일 업종별 순매수 · 미니차트 막대 하나가 하루 · 연속 = 최근 며칠째 같은 방향인지</small></h2>'
                          + vtabs(f"{anchor}-trend", {k: trend_panel(hist, keys) for k, _, keys in views}))

    itabs, panels = [], []
    for lab, c in INVESTORS:
        if lab not in by:
            continue
        pid = f"{anchor}-{c}"
        itabs.append(f'<button type="button" data-group="{anchor}" data-target="{pid}" data-c="{c}">{lab}</button>')
        panels.append(f'<div class="panel" id="{pid}" hidden>{stock_table(by[lab], c, both)}</div>')

    return (f'<section id="{anchor}" hidden>'
            f'<div class="cards">{cards}</div>{flow_html}{trend_html}'
            f'<details class="detail"><summary>투자자별 순매수 상위 100 전체 보기</summary>'
            f'<div class="itabs">{"".join(itabs)}</div>{"".join(panels)}</details>'
            f'<div class="note">외국인·기관의 오늘 금액은 네이버 순위의 정확한 값(순위 밖 종목은 수량×종가 추정), '
            f'개인과 섹터 추세는 종목별 순매수 수량 × 종가로 계산한 추정치예요. '
            f'모든 투자자를 더하면 0에 가까우므로(누가 사면 누가 판다) 기본 보기는 외국인+기관이에요.</div></section>')


def main(src: str, dst: str) -> None:
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    tables = data.get("tables", [])
    date, note = esc(data.get("date", "")), esc(data.get("note", ""))

    mtabs, sections = [], []
    for m, anchor in MARKETS:
        ts = [t for t in tables if t.get("market") == m]
        if not ts:
            continue
        sec = market_section(m, anchor, ts, data.get("flows", {}).get(m), data.get("history", {}).get(m))
        ix = data.get("indices", {}).get(m)
        ix_html = ""
        if ix and ix.get("close"):
            up = ix["rate"] >= 0
            ix_html = (f'<span class="ix {"up" if up else "down"}">{esc(ix["close"])} '
                       f'{"▲" if up else "▼"}{abs(ix["diff"]):,.2f} ({ix["rate"]:+.2f}%)</span>')
        mtabs.append(f'<button type="button" data-group="market" data-target="{anchor}">{m}{ix_html}</button>')
        sections.append(sec)

    footer = esc(data.get("footer", ""))
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>오늘 순매수 {date}</title><style>{CSS}</style></head><body><main>
<h1>오늘 순매수</h1>
<div class="sub">{date}{' · ' + note if note else ''} · 투자자별 자금 흐름 · 단위 억원 · <span class="up">빨강 유입</span> / <span class="down">파랑 유출</span></div>
<div class="mtabs">{''.join(mtabs)}</div>
{''.join(sections)}
{f'<div class="sub" style="margin-top:28px">{footer}</div>' if footer else ''}
</main><script>{JS}</script></body></html>"""
    with open(dst, "w", encoding="utf-8") as f:
        f.write(page)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
