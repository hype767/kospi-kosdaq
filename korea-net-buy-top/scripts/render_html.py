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
.itabs button[data-c=fo][aria-selected=true],.itabs button[data-c=foi][aria-selected=true]{border-bottom-color:var(--fg)}
.b.fo,.b.foi{background:var(--fg)}
.itabs{overflow-x:auto;white-space:nowrap}
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
.in{color:var(--up)}.out{color:var(--down)}.muted{color:var(--muted)}
.ctx h3 small{font-weight:400;color:var(--muted);font-size:12px}
.cxrow{display:grid;grid-template-columns:repeat(3,minmax(0,1fr)) minmax(0,2fr);gap:10px}
.cx{display:flex;flex-direction:column;gap:1px;font-variant-numeric:tabular-nums}
.cx .k{font-size:12.5px;color:var(--muted)}.cx b{font-size:17px}.cx small{font-size:12px;color:var(--muted)}
.cx small.inst{font-size:13px;color:var(--fg);line-height:1.6}
.cxline{font-size:13.5px;margin-top:10px;font-variant-numeric:tabular-nums}
.warn{margin-top:10px;font-size:13px;background:color-mix(in srgb,var(--star) 14%,transparent);border-radius:8px;padding:7px 10px}
.sgrid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.cards{margin-top:16px}
@media (max-width:820px){.sgrid2{grid-template-columns:1fr}}
.box.sig h3{margin-bottom:2px}.sd{font-size:12.5px;color:var(--muted);margin-bottom:6px}
.srow2,.wrow{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(8em,auto);align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--line)}
.srow2:last-child,.wrow:last-child{border-bottom:0}
.sn{min-width:0}.sn b{display:block;font-size:14.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sn small{display:block;font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sv,.wv{text-align:right;font-variant-numeric:tabular-nums;font-weight:700;font-size:14px;white-space:nowrap}
.sv small,.wv small{display:block;font-weight:400;font-size:12px;color:var(--muted)}
.wv b{font-size:15px}
.wrow .badge{display:inline-block;margin-top:3px}
.mspark .axis{stroke:var(--muted);stroke-width:1;opacity:.4}.mspark .sin{fill:var(--up)}.mspark .sout{fill:var(--down)}.mspark .recent{fill:var(--soft)}
.empty{font-size:13px;color:var(--muted);padding:10px 0}
.btsum{font-size:14.5px;line-height:1.6}
.btchart{display:flex;align-items:stretch;gap:3px;height:90px;margin:12px 0 24px;border-bottom:0}
.btb{flex:1;position:relative;background:linear-gradient(var(--line),var(--line)) center/100% 1px no-repeat}
.btb span{position:absolute;left:15%;width:70%;border-radius:2px;max-height:50%}
.btb span.in{background:var(--up)}.btb span.out{background:var(--down)}
.btb i{position:absolute;bottom:-16px;left:50%;transform:translateX(-50%);font-size:9.5px;font-style:normal;color:var(--muted);white-space:nowrap}
.fxline{font-size:13px;color:var(--muted);margin-top:2px}
.frow .lead{grid-column:1/-1;font-size:12.5px;color:var(--muted);background:var(--soft);border-radius:6px;padding:3px 8px;margin-top:-2px}
.frow .lead b{color:var(--fg);font-weight:600}
.frow .lead .heavy{color:var(--star);font-weight:700;margin-right:6px}
.vtabs{display:inline-flex;background:var(--soft);border-radius:999px;padding:3px;margin:2px 0 6px;flex-wrap:wrap}
.vtabs button{font:inherit;font-size:14px;cursor:pointer;border:0;background:none;color:var(--muted);padding:6px 14px;border-radius:999px}
.vtabs button[aria-selected=true]{background:var(--card);color:var(--fg);font-weight:700;box-shadow:0 1px 2px rgba(0,0,0,.12)}
h3.sh{font-size:14px;color:var(--muted);margin:14px 0 8px;font-weight:600}
.fgrid.one{grid-template-columns:1fr}
.tcard{padding:12px 0;border-bottom:1px solid var(--line)}
.tcard:last-child{border-bottom:0}
.th{display:flex;align-items:baseline;gap:8px;margin-bottom:6px}
.tn{font-weight:700;font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tv{margin-left:auto;font-weight:800;font-size:16px;font-variant-numeric:tabular-nums;white-space:nowrap}
.tv.in{color:var(--up)}.tv.out{color:var(--down)}
.badge{font-size:11.5px;font-weight:600;border-radius:999px;padding:1px 8px;white-space:nowrap}
.badge.in{color:var(--up);background:color-mix(in srgb,var(--up) 12%,transparent)}
.badge.out{color:var(--down);background:color-mix(in srgb,var(--down) 12%,transparent)}
.spark{display:block;width:100%;height:52px}
.spark .axis{stroke:var(--muted);stroke-width:1;opacity:.5;vector-effect:non-scaling-stroke}
.spark .sin{fill:var(--up)}.spark .sout{fill:var(--down)}
.spark .recent{fill:var(--soft)}
.sx{display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted);margin-top:2px;font-variant-numeric:tabular-nums}
.tf{font-size:13px;color:var(--muted);margin-top:6px}
.tf b{font-weight:700;font-variant-numeric:tabular-nums}
.tlegend{font-size:12.5px;color:var(--muted);margin:2px 0 10px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.tlegend .sw{display:inline-block;width:10px;height:10px;border-radius:2px}
.tlegend .sw.sin{background:var(--up)}.tlegend .sw.sout{background:var(--down)}.tlegend .sw.recent{background:var(--soft);border:1px solid var(--line)}
table.trend td{padding:7px 10px}table.trend td.st{font-size:13px;min-width:7em}
.dot.i{background:var(--i)}
details.detail>summary{cursor:pointer;font-size:17px;font-weight:700;list-style:none;padding:12px 16px;background:var(--card);border:1px solid var(--line);border-radius:12px}
details.detail>summary::after{content:" ▾";color:var(--muted)}
details.detail[open]>summary::after{content:" ▴"}
@media (max-width:600px){.cxrow{grid-template-columns:repeat(3,1fr)}.cx.wide{grid-column:1/-1}.srow2{grid-template-columns:minmax(0,1fr) auto}.wrow{grid-template-columns:1fr;gap:4px}.wv{text-align:left}.wrow .badge{display:inline-block;margin-top:3px}.srow2 .mspark,.wrow .mspark{display:none}.btb i{display:none}td.sc,th.sc{display:none}.srow{grid-template-columns:6.5em 1fr auto}.frow{grid-template-columns:1fr auto;grid-template-areas:"nm val" "tr tr" "ld ld";row-gap:6px}.frow .lead{grid-area:ld}.frow .nm{grid-area:nm}.frow .val{grid-area:val}.frow .track{grid-area:tr}}
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
            f'<span class="val"><span class="{cls}">{signed(tot)}억</span><small>{split_line(r)}</small></span>'
            + (f'<span class="lead">{lead_line(r, keys)}</span>' if r.get("members") and lead_line(r, keys) else "")
            + '</div>')
    return "".join(out)


def sector_agg(fl):
    agg = {}
    for r in fl:
        if r["sector"] == "ETF" or "ETN" in r["name"]:
            continue
        a = agg.setdefault(r["sector"], {"name": r["sector"], "f": 0.0, "o": 0.0, "i": 0.0, "n": 0, "members": []})
        for k in ("f", "o", "i"):
            a[k] += r.get(k, 0.0)
        a["n"] += 1
        a["members"].append(r)
    return list(agg.values())


def lead_line(sec, keys) -> str:
    """섹터의 주도 종목: 섹터 합계와 같은 방향으로 가장 크게 움직인 종목과 그 비중."""
    tot = amt(sec, keys)
    members = sec.get("members") or []
    if not members or not tot:
        return ""
    lead = max(members, key=lambda r: amt(r, keys)) if tot > 0 else min(members, key=lambda r: amt(r, keys))
    la = amt(lead, keys)
    if la * tot <= 0:
        return ""
    share = la / tot * 100
    share_txt = "섹터 합계 이상" if share >= 100 else f"섹터의 {share:.0f}%"
    tag = '<b class="heavy">한 종목 쏠림</b>' if share >= 70 else ""
    return f'{tag}주도 종목 <b>{esc(lead["name"])}</b> {signed(la)}억 · {share_txt}'


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


def spark(vals, dates) -> str:
    """일별 순매수 막대 차트 (폭은 카드에 맞춰 늘어남). 최근 5일은 배경 음영, 막대마다 날짜·금액 툴팁."""
    if not vals:
        return ""
    n = len(vals)
    peak = max(abs(v) for v in vals) or 1
    W, H, mid = 400, 52, 26
    bw = W / n
    parts = [f'<rect x="{(n - 5) * bw:.1f}" y="0" width="{5 * bw:.1f}" height="{H}" class="recent"/>' if n >= 5 else "",
             f'<line x1="0" x2="{W}" y1="{mid}" y2="{mid}" class="axis"/>']
    for i, v in enumerate(vals):
        bh = max(1.5, abs(v) / peak * (mid - 3))
        y = mid - bh if v >= 0 else mid
        parts.append(f'<rect x="{i * bw + bw * 0.25:.1f}" y="{y:.1f}" width="{bw * 0.5:.1f}" height="{bh:.1f}" rx="1.5" '
                     f'class="{"sin" if v >= 0 else "sout"}"><title>{esc(dates[i])}  {signed(v)}억</title></rect>')
    mid_i = n // 2
    labels = (f'<div class="sx"><span>{esc(dates[0])}</span><span>{esc(dates[mid_i])}</span>'
              f'<span class="r">최근 5일 ▸ {esc(dates[-1])}</span></div>')
    return (f'<svg class="spark" viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" '
            f'aria-label="일별 순매수 흐름">{"".join(parts)}</svg>{labels}')


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

    def card(name, daily, s5, s20):
        st = streak(daily)
        badge = ('<span class="badge in">오늘 유입</span>' if st == 1 else
                 '<span class="badge out">오늘 유출</span>' if st == -1 else
                 f'<span class="badge in">{st}일 연속 유입</span>' if st > 1 else
                 f'<span class="badge out">{-st}일 연속 유출</span>' if st < -1 else "")
        c20 = "in" if s20 >= 0 else "out"
        c5 = "up" if s5 >= 0 else "down"
        c1 = "up" if daily[-1] >= 0 else "down"
        return (f'<div class="tcard"><div class="th"><span class="tn">{esc(name)}</span>{badge}'
                f'<span class="tv {c20}">{signed(s20)}억</span></div>'
                f'{spark(daily, dates)}'
                f'<div class="tf">최근 5일 <b class="{c5}">{signed(s5)}억</b> · 오늘 <b class="{c1}">{signed(daily[-1])}억</b></div></div>')

    tin = sorted([r for r in rows if r[3] > 0], key=lambda r: -r[3])[:8]
    tout = sorted([r for r in rows if r[3] < 0], key=lambda r: r[3])[:8]
    n = len(dates)
    legend = ('<div class="tlegend"><span class="sw sin"></span>유입한 날 <span class="sw sout"></span>유출한 날 '
              '<span class="sw recent"></span>최근 5일 · 막대 높이는 업종마다 따로 맞춤 · PC에서 막대에 마우스를 올리면 날짜·금액</div>')
    return (legend + '<div class="fgrid">'
            f'<div class="box"><h3>{n}거래일 누적 돈이 들어온 섹터</h3>{"".join(card(*r) for r in tin)}</div>'
            f'<div class="box"><h3>{n}거래일 누적 돈이 빠진 섹터</h3>{"".join(card(*r) for r in tout)}</div></div>')


# ───────────────────────── 신호 (외국인+기관 기준) ─────────────────────────
MIN_MCAP = 500      # 억원: 이보다 작은 종목은 신호에서 뺀다 (작은 금액으로 강도가 튀는 것 방지)
MIN_AMT = 3         # 억원: 이보다 작은 순매수는 신호로 보지 않는다
MIN_VALUE = 10      # 억원: 그날 거래대금이 이보다 작으면 신호에서 뺀다 (거래가 거의 없는 종목의 '연속' 착시 방지)


def fo_series(r):
    h = r.get("h")
    return [a + b for a, b in zip(h["f"], h["o"])] if h else []


def ret_pct(h, a, b):
    try:
        return (h["c"][b] / h["c"][a] - 1) * 100
    except (TypeError, ZeroDivisionError, IndexError):
        return 0.0


def bp(x, mcap):
    """시가총액 대비 비율(%)."""
    return x / mcap * 100 if mcap else 0.0


def signal_universe(fl):
    return [r for r in fl if r.get("h") and r["sector"] != "ETF" and "ETN" not in r["name"]
            and "스팩" not in r["name"] and r.get("mcap", 0) >= MIN_MCAP and r.get("value", 0) >= MIN_VALUE]


def compute_signals(fl):
    U = signal_universe(fl)
    sig = {}
    # 1) 수급 강도: 오늘 외+기 순매수 / 시가총액
    st = [r for r in U if r["f"] + r["o"] >= MIN_AMT]
    sig["strength"] = sorted(st, key=lambda r: -bp(r["f"] + r["o"], r["mcap"]))[:12]
    # 2) 수급 전환: 앞 15일 누적 유출 → 최근 5일 누적 유입, 오늘도 유입
    tr = []
    for r in U:
        s_ = fo_series(r)
        if len(s_) < 10:
            continue
        prior, last5 = sum(s_[:-5]), sum(s_[-5:])
        if prior < 0 and last5 >= MIN_AMT and s_[-1] > 0:
            tr.append((r, prior, last5))
    sig["turn"] = [x for x in sorted(tr, key=lambda x: -bp(x[2], x[0]["mcap"]))[:10]]
    # 3) 연속 순매수: 오늘까지 며칠째 외+기 순매수
    sk = []
    for r in U:
        s_ = fo_series(r)
        k = 0
        for v in reversed(s_):
            if v > 0:
                k += 1
            else:
                break
        if k >= 5 and sum(s_[-k:]) >= MIN_AMT:
            sk.append((r, k, sum(s_[-k:])))
    sig["streak"] = sorted(sk, key=lambda x: (-x[1], -bp(x[2], x[0]["mcap"])))[:10]
    # 4) 신규 쌍끌이: 오늘 외국인·기관 동반 순매수, 어제는 아님
    nb = []
    for r in U:
        h = r["h"]
        if len(h["f"]) < 2:
            continue
        today = r["f"] > 0 and r["o"] > 0
        yday = h["f"][-2] > 0 and h["o"][-2] > 0
        if today and not yday and r["f"] + r["o"] >= MIN_AMT:
            nb.append(r)
    sig["newboth"] = sorted(nb, key=lambda r: -bp(r["f"] + r["o"], r["mcap"]))[:10]
    # 5) 주가-수급 괴리 (20일)
    acc, dis = [], []
    for r in U:
        s_ = fo_series(r)
        if len(s_) < 10:
            continue
        cum, ret = sum(s_), ret_pct(r["h"], 0, -1)
        if cum >= MIN_AMT * 3 and ret <= -3:
            acc.append((r, cum, ret))
        if cum <= -MIN_AMT * 3 and ret >= 5:
            dis.append((r, cum, ret))
    sig["acc"] = sorted(acc, key=lambda x: -bp(x[1], x[0]["mcap"]))[:8]
    sig["dis"] = sorted(dis, key=lambda x: bp(x[1], x[0]["mcap"]))[:8]
    return sig


def backtest(fl, days, top=20, fwd=5):
    """지난 20일 동안 매일 '수급 강도 상위 20종목'을 골랐다면 fwd일 뒤 시장(신호 대상 전체) 평균보다 나았나."""
    U = signal_universe(fl)
    n = len(days)
    rows = []
    for d in range(0, n - fwd):
        cand, allret = [], []
        for r in U:
            c = r["h"]["c"]
            if not c[d] or not c[d + fwd]:
                continue
            fr = (c[d + fwd] / c[d] - 1) * 100
            allret.append(fr)
            fo = r["h"]["f"][d] + r["h"]["o"][d]
            if fo >= MIN_AMT:
                mc = r["mcap"] * c[d] / c[-1] if c[-1] else r["mcap"]
                cand.append((fo / mc if mc else 0, fr))
        if len(cand) < top or not allret:
            continue
        pick = sorted(cand, key=lambda x: -x[0])[:top]
        avg = sum(x[1] for x in pick) / top
        mkt = sum(allret) / len(allret)
        rows.append({"day": days[d], "pick": avg, "mkt": mkt, "ex": avg - mkt})
    if not rows:
        return None
    return {"rows": rows, "avg_ex": sum(r["ex"] for r in rows) / len(rows),
            "wins": sum(1 for r in rows if r["ex"] > 0), "n": len(rows), "top": top, "fwd": fwd}


def mini_spark(vals, w=84, h=22) -> str:
    if not vals:
        return ""
    peak = max(abs(v) for v in vals) or 1
    n, mid = len(vals), h / 2
    bw = w / n
    bars = []
    for i, v in enumerate(vals):
        bh = max(1, abs(v) / peak * (mid - 1))
        y = mid - bh if v >= 0 else mid
        bars.append(f'<rect x="{i * bw + bw * .2:.1f}" y="{y:.1f}" width="{bw * .6:.1f}" height="{bh:.1f}" '
                    f'class="{"sin" if v >= 0 else "sout"}"/>')
    return (f'<svg class="mspark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true">'
            f'<rect x="{(n - 5) * bw:.1f}" y="0" width="{5 * bw:.1f}" height="{h}" class="recent"/>'
            f'<line x1="0" x2="{w}" y1="{mid}" y2="{mid}" class="axis"/>{"".join(bars)}</svg>')


def sig_row(r, main, sub) -> str:
    rate_cls = "up" if r["rate"] >= 0 else "down"
    return (f'<div class="srow2"><div class="sn"><b>{esc(r["name"])}</b>'
            f'<small>{esc(r["sector"])} · <span class="{rate_cls}">{r["rate"]:+.2f}%</span></small></div>'
            f'{mini_spark(fo_series(r))}<div class="sv">{main}<small>{sub}</small></div></div>')


def sig_box(title, desc, rows_html) -> str:
    body = rows_html or '<div class="empty">오늘은 해당 종목이 없어요</div>'
    return f'<div class="box sig"><h3>{title}</h3><div class="sd">{desc}</div>{body}</div>'


def signals_html(fl) -> str:
    sig = compute_signals(fl)
    pct = lambda x: f"{x:.2f}%"
    strength = "".join(sig_row(r, f'<span class="in">{signed(r["f"] + r["o"])}억</span>',
                               f'시총의 {pct(bp(r["f"] + r["o"], r["mcap"]))} · 거래대금의 '
                               f'{(r["f"] + r["o"]) / r["value"] * 100 if r.get("value") else 0:.0f}%')
                       for r in sig["strength"])
    turn = "".join(sig_row(r, f'<span class="in">5일 {signed(l5)}억</span>', f'앞 15일 {signed(pr)}억')
                   for r, pr, l5 in sig["turn"])
    streak_ = "".join(sig_row(r, f'<span class="in">{k}일 연속</span>', f'누적 {signed(c)}억 · 시총의 {pct(bp(c, r["mcap"]))}')
                      for r, k, c in sig["streak"])
    newb = "".join(sig_row(r, f'<span class="in">{signed(r["f"] + r["o"])}억</span>',
                           f'외 {signed(r["f"])} · 기 {signed(r["o"])}') for r in sig["newboth"])
    acc = "".join(sig_row(r, f'<span class="in">20일 {signed(c)}억</span>', f'20일 주가 <span class="down">{ret:+.1f}%</span>')
                  for r, c, ret in sig["acc"])
    dis = "".join(sig_row(r, f'<span class="out">20일 {signed(c)}억</span>', f'20일 주가 <span class="up">{ret:+.1f}%</span>')
                  for r, c, ret in sig["dis"])
    return (
        '<h2>오늘 눈여겨볼 변화<small>외국인+기관 기준 · 시총 500억·거래대금 10억 이상 · ETF·ETN 제외 · 미니차트 = 20일 외+기 순매수</small></h2>'
        '<div class="sgrid2">'
        + sig_box("수급 전환", "앞 15일은 빠지다가 최근 5일 들어오기 시작한 종목", turn)
        + sig_box("연속 순매수", "외+기가 오늘까지 5일 이상 연속으로 산 종목", streak_)
        + sig_box("신규 쌍끌이", "오늘 외국인·기관이 같이 샀고, 어제는 아니었던 종목", newb)
        + sig_box("수급 강도 TOP", "덩치 대비 많이 산 종목 (순매수 ÷ 시가총액)", strength)
        + '</div><h2>주가와 수급이 엇갈린 종목<small>20일 기준 · 같은 방향이 아니라 눈여겨볼 만한 곳</small></h2><div class="sgrid2">'
        + sig_box("주가는 빠졌는데 외+기는 산 종목", "20일 주가 −3% 이하 · 외+기 누적 순매수", acc)
        + sig_box("주가는 올랐는데 외+기는 판 종목", "20일 주가 +5% 이상 · 외+기 누적 순매도", dis)
        + '</div>')


def backtest_html(fl, hist) -> str:
    if not hist or not hist.get("dates"):
        return ""
    bt = backtest(fl, hist["dates"])
    if not bt:
        return ""
    peak = max(abs(r["ex"]) for r in bt["rows"]) or 1
    bars = "".join(
        f'<div class="btb" title="{esc(r["day"])}: 상위 {r["pick"]:+.2f}% / 시장 {r["mkt"]:+.2f}%">'
        f'<span class="{"in" if r["ex"] >= 0 else "out"}" style="height:{max(2, abs(r["ex"]) / peak * 100):.0f}%;'
        f'{"bottom:50%" if r["ex"] >= 0 else "top:50%"}"></span><i>{esc(r["day"])}</i></div>'
        for r in bt["rows"])
    cls = "in" if bt["avg_ex"] >= 0 else "out"
    return (f'<h2>신호 점검<small>이 페이지의 신호가 최근에 맞았는지 · 참고용</small></h2><div class="box bt">'
            f'<div class="btsum">지난 {bt["n"]}거래일 동안 매일 <b>수급 강도 상위 {bt["top"]}종목</b>을 골랐다면, '
            f'{bt["fwd"]}거래일 뒤 수익률이 시장 평균보다 평균 <b class="{cls}">{bt["avg_ex"]:+.2f}%p</b> '
            f'({bt["n"]}일 중 {bt["wins"]}일 앞섬)</div>'
            f'<div class="btchart">{bars}</div>'
            '<div class="note">막대 = 그날 고른 종목의 5일 뒤 수익률 − 시장 평균 (빨강 앞섬 / 파랑 뒤짐). '
            '표본이 작고(20일) 거래비용을 빼지 않았으며, 과거 결과가 앞으로를 보장하지 않아요. '
            '기록이 쌓이면 더 긴 기간으로 점검할 수 있어요.</div></div>')


def watch_html(fl, watch) -> str:
    if not watch:
        return ""
    by = {r["code"]: r for r in fl}
    by_name = {r["name"]: r for r in fl}
    rows = []
    for w in watch:
        r = by.get(w) or by_name.get(w)
        if not r:
            continue
        s_ = fo_series(r)
        k = 0
        for v in reversed(s_):
            if (v > 0) == (s_[-1] > 0) and v != 0:
                k += 1
            else:
                break
        streak_txt = (f'<span class="badge in">{k}일 연속 유입</span>' if s_ and s_[-1] > 0 and k > 1 else
                      f'<span class="badge out">{k}일 연속 유출</span>' if s_ and s_[-1] < 0 and k > 1 else "")
        r20 = ret_pct(r["h"], 0, -1) if r.get("h") else 0
        rows.append(
            f'<div class="wrow"><div class="sn"><b>{esc(r["name"])}</b><small>{esc(r["sector"])} · 종가 {r["price"]:,} '
            f'<span class="{"up" if r["rate"] >= 0 else "down"}">{r["rate"]:+.2f}%</span></small>{streak_txt}</div>'
            f'{mini_spark(s_, 120, 26)}'
            f'<div class="wv"><b class="{"in" if r["f"] + r["o"] >= 0 else "out"}">외+기 {signed(r["f"] + r["o"])}억</b>'
            f'<small>{split_line(r)}</small>'
            f'<small>5일 {signed(sum(s_[-5:]))}억 · 20일 {signed(sum(s_))}억 · 20일 주가 {r20:+.1f}%</small></div></div>')
    if not rows:
        return ""
    return f'<h2>내 관심 종목</h2><div class="box">{"".join(rows)}</div>'


def context_html(m, ctx, hist) -> str:
    """시장 맥락: 투자자별 시장 전체 순매수(정확), 기관 세부, 외국인 선물, 이벤트일."""
    days = (ctx or {}).get("markets", {}).get(m) or []
    parts = []
    if days:
        t = days[-1]
        last5 = days[-5:]
        def cell(lab, k, c):
            v, v5 = t[k], sum(d[k] for d in last5)
            return (f'<div class="cx"><span class="k"><span class="dot {c}"></span>{lab}</span>'
                    f'<b class="{"in" if v >= 0 else "out"}">{signed(v)}억</b><small>5일 {signed(v5)}억</small></div>')
        inst = t.get("inst", {})
        o_pos = t["o"]
        fin = inst.get("금융투자", 0)
        warn = ""
        if o_pos > 0 and fin > 0 and fin / o_pos >= .5:
            warn = (f'<div class="warn">기관 순매수의 {fin / o_pos * 100:.0f}%가 금융투자예요. '
                    'ETF 설정·차익거래 같은 기계적 매매일 수 있어 기관 수급을 조금 할인해서 보세요.</div>')
        inst_txt = " · ".join(f'{k} {signed(v)}' for k, v in sorted(inst.items(), key=lambda kv: -abs(kv[1]))[:4])
        parts.append(f'<div class="cxrow">{cell("외국인", "f", "f")}{cell("기관", "o", "o")}{cell("개인", "i", "i")}'
                     f'<div class="cx wide"><span class="k">기관 세부 (억원)</span><small class="inst">{inst_txt}</small></div></div>{warn}')
    fut = (ctx or {}).get("futures") or []
    if m == "코스피" and fut:
        t, f5 = fut[-1]["f"], sum(d["f"] for d in fut[-5:])
        parts.append(f'<div class="cxline">외국인 <b>코스피200 선물</b> 오늘 <b class="{"in" if t >= 0 else "out"}">{t:+,}계약</b>'
                     f' · 5일 {f5:+,}계약 <span class="muted">(현물 방향을 미리 보여주는 경우가 많아요)</span></div>')
    ev = (hist or {}).get("events") or {}
    if ev:
        dd = (hist or {}).get("days") or []
        today = dd[-1] if dd else ""
        recent = " · ".join(f'{d[4:6]}/{d[6:]} {nm}' for d, nm in sorted(ev.items()))
        if today in ev:
            parts.append(f'<div class="warn">오늘은 <b>{esc(ev[today])}</b>이에요. 이런 날은 수급이 기계적으로 크게 움직여 평소보다 해석에 주의가 필요해요.</div>')
        parts.append(f'<div class="cxline muted">최근 20일 이벤트: {esc(recent)}</div>')
    if not parts:
        return ""
    return f'<div class="box ctx"><h3>시장 전체 수급 <small>정확값</small></h3>{"".join(parts)}</div>'


def market_section(m: str, anchor: str, ts: list, fl, hist, ctx=None, watch=None) -> str:
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
            trend_html = ('<h2>섹터 추세<small>최근 20거래일 업종별 순매수 · 막대 하나가 하루</small></h2>'
                          + vtabs(f"{anchor}-trend", {k: trend_panel(hist, keys) for k, _, keys in views}))

    # 상위 100 탭: 외국인 | 기관 | 외국인+기관 | 개인 | 외국인+기관+개인
    def combo_table(keys, source):
        if not fl:
            return None
        cols = (by.get("외국인") or by.get("기관") or {}).get("columns") or \
            ["종목명", "업종", "순매수 금액(억원)", "종가(원)", "등락률", "거래대금(억원)"]
        top = sorted((r for r in fl if amt(r, keys) > 0), key=lambda r: -amt(r, keys))[:100]
        rows = [[r["name"], r["sector"], f"{amt(r, keys):,.0f}", f'{r["price"]:,}', f'{r["rate"]:+.2f}%',
                 f'{r.get("value", 0):,.0f}'] for r in top]
        return {"columns": cols, "rows": rows, "source": source}

    tabs100 = [
        ("외국인", "f", by.get("외국인")),
        ("기관", "o", by.get("기관")),
        ("외국인+기관", "fo", combo_table(("f", "o"), "외국인+기관 합산 (정확값 + 순위 밖 종목은 추정)")),
        ("개인", "i", by.get("개인")),
        ("외국인+기관+개인", "foi", combo_table(("f", "o", "i"),
            "세 투자자 합산 (추정) · 세 투자자를 더하면 남는 건 기타법인 등의 반대편 매매라 금액이 작아요")),
    ]
    itabs, panels = [], []
    for lab, c, t in tabs100:
        if not t or not t.get("rows"):
            continue
        pid = f"{anchor}-{c}"
        itabs.append(f'<button type="button" data-group="{anchor}" data-target="{pid}" data-c="{c}">{lab}</button>')
        panels.append(f'<div class="panel" id="{pid}" hidden>{stock_table(t, c, both)}</div>')

    return (f'<section id="{anchor}" hidden>'
            + context_html(m, ctx, hist) + watch_html(fl or [], watch)
            + f'<div class="cards">{cards}</div>'
            + (signals_html(fl) if fl else "")
            + f'{flow_html}{trend_html}'
            + backtest_html(fl or [], hist)
            + f'<details class="detail"><summary>투자자별 순매수 상위 100 전체 보기</summary>'
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
        sec = market_section(m, anchor, ts, data.get("flows", {}).get(m), data.get("history", {}).get(m),
                             data.get("context"), data.get("watch"))
        ix = data.get("indices", {}).get(m)
        ix_html = ""
        if ix and ix.get("close"):
            up = ix["rate"] >= 0
            ix_html = (f'<span class="ix {"up" if up else "down"}">{esc(ix["close"])} '
                       f'{"▲" if up else "▼"}{abs(ix["diff"]):,.2f} ({ix["rate"]:+.2f}%)</span>')
        mtabs.append(f'<button type="button" data-group="market" data-target="{anchor}">{m}{ix_html}</button>')
        sections.append(sec)

    fx = (data.get("context") or {}).get("fx")
    fx_html = ""
    if fx and fx.get("close"):
        cls = "up" if fx["diff"] > 0 else "down" if fx["diff"] < 0 else ""
        fx_html = (f'<div class="fxline">원·달러 환율 <b>{esc(fx["close"])}원</b> '
                   f'<span class="{cls}">{fx["diff"]:+.2f} ({fx["rate"]:+.2f}%)</span> · {esc(fx.get("at", ""))} 고시 '
                   '· 환율이 오르면(원화 약세) 외국인 매도 압력이 커지는 경향이 있어요</div>')
    footer = esc(data.get("footer", ""))
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>오늘 순매수 {date}</title><style>{CSS}</style></head><body><main>
<h1>오늘 순매수</h1>
<div class="sub">{date}{' · ' + note if note else ''} · 투자자별 자금 흐름 · 단위 억원 · <span class="up">빨강 유입</span> / <span class="down">파랑 유출</span></div>
{fx_html}<div class="mtabs">{''.join(mtabs)}</div>
{''.join(sections)}
{f'<div class="sub" style="margin-top:28px">{footer}</div>' if footer else ''}
</main><script>{JS}</script></body></html>"""
    with open(dst, "w", encoding="utf-8") as f:
        f.write(page)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
