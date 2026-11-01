#!/usr/bin/env python3
"""Build the perf-core round-2 report: verdict, per-item before/after (Node microbench and browser bench), every KPI per
scenario across the commits, a chart over commits, first-paint filmstrips before vs after, and the Vibe Tracks points.

    python3 docs/build_perf_r2_report.py MEDIA_DIR OUT.html --items ITEMS.json [--films NAME=DIR ...] [--vt PNG]

MEDIA_DIR (reports/media/perf-r2/) holds runs/NN-<name>.json (bench results, one per commit, in order),
micro/NN-<name>.json (bench/micro.mjs --json, same names) and the filmstrip frames. ITEMS.json lists the items:
[{"n", "title", "commit", "before": "<run name>", "after": "<run name>", "micro": [case ids], "verdict", "note"}].
Every number on the page is read from those files (the bench's own JSON), so the page cannot show a number nothing
measured. Stdlib only. WHY a big type scale (17 px body): Zach said earlier reports were too small to read.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
from publish import failed_because  # noqa: E402  WHY one rule: the page and Vibe Tracks fail a scenario the same way

e = html.escape

KPIS = [
    ("first_paint", "First useful paint, cold p95", "ms", lambda s: s["load"]["cold"]["first_useful_paint"]["p95"]),
    ("first_paint_warm", "First useful paint, warm p95", "ms", lambda s: s["load"]["warm"]["first_useful_paint"]["p95"]),
    ("tti", "Time to interactive, cold p95", "ms", lambda s: s["load"]["cold"]["tti"]["p95"]),
    ("tbt", "Total blocking time, cold p95", "ms", lambda s: s["load"]["cold"]["tbt"]["p95"]),
    ("model", "Row model at load, p50", "ms", lambda s: s["load"]["cold"]["model_ms"]["p50"]),
    ("rail_load", "Rail count + draw at load, p50", "ms", lambda s: s["load"]["cold"]["rail_ms"]["p50"]),
    ("interaction", "Interaction latency, p95", "ms", lambda s: s["interaction"]["all"]["p95"]),
    ("filter", "Rail tick (filter), p95", "ms", lambda s: (s["interaction"].get("filter") or {}).get("p95")),
    ("search", "Search keystroke, p95", "ms", lambda s: (s["interaction"].get("search") or {}).get("p95")),
    ("preset", "Preset switch, p95", "ms", lambda s: (s["interaction"].get("preset") or {}).get("p95")),
    ("sort", "Sort, p95", "ms", lambda s: (s["interaction"].get("sort") or {}).get("p95")),
    ("scroll", "Scroll frame, p95", "ms", lambda s: (s.get("scroll") or {}).get("p95")),
    ("bytes", "Bytes on first load (gzip)", "KB", lambda s: s["load"]["cold"]["bytes_gzip"]["p50"] / 1024 if s["load"]["cold"]["bytes_gzip"]["p50"] is not None else None),
]
CHART_KPIS = ["first_paint", "interaction", "model"]


def get(s, fn):
    if s is None or failed_because(s):
        return None
    try:
        return fn(s)
    except (KeyError, TypeError):
        return None


def f0(x, unit=""):
    if x is None:
        return "—"
    return (f"{x:,.0f}" if abs(x) >= 10 else f"{x:,.1f}") + unit


def sid(s):
    return s["target"] if s.get("target") else s["id"]


def load_runs(media):
    runs = []
    for p in sorted((media / "runs").glob("*.json")):
        r = json.loads(p.read_text())
        micro_p = media / "micro" / p.name
        runs.append({"name": p.stem, "res": r, "micro": json.loads(micro_p.read_text()) if micro_p.exists() else None,
                     "by": {sid(s): s for s in r["scenarios"]}})
    return runs


def change(a, b):
    if a is None or b is None or a == 0:
        return ""
    r = b / a
    cls = "good" if r < 0.9 else "bad" if r > 1.1 else "flat"
    return f'<span class="chg {cls}">{"×" + format(1 / r, ".1f") + " faster" if r < 0.9 else format(r, ".2f") + "×" if r > 1.1 else "≈"}</span>'


def chart(runs, scenarios, kpi, w=520, h=260):
    """One small-multiple: a KPI per scenario over the commits, log y (the scenarios span 100 ms to 5 s)."""
    label, unit, fn = next((k[1], k[2], k[3]) for k in KPIS if k[0] == kpi)
    xs = list(range(len(runs)))
    series = []
    for sc in scenarios:
        # WHY noisy runs left out of the lines: a run on a loaded machine reads as a regression that is not one; the
        # table below still lists it, labelled
        pts = [(i, get(r["by"].get(sc), fn)) for i, r in enumerate(runs) if ((r["by"].get(sc) or {}).get("trust") or {}).get("verdict") != "noisy"]
        pts = [(i, v) for i, v in pts if v is not None and v > 0]
        if pts:
            series.append((sc, pts))
    vals = [v for _, pts in series for _, v in pts]
    if not vals:
        return ""
    lo, hi = math.log10(max(1, min(vals)) / 1.3), math.log10(max(vals) * 1.3)
    L, R, T, B = 56, 150, 28, 46
    X = lambda i: L + (w - L - R) * (i / max(1, len(xs) - 1))  # noqa: E731
    Y = lambda v: T + (h - T - B) * (1 - (math.log10(v) - lo) / (hi - lo or 1))  # noqa: E731
    out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="{e(label)} over commits">',
           f'<text x="{L}" y="16" class="ct">{e(label)} ({unit}, log scale; quiet runs only)</text>']
    for d in range(int(math.floor(lo)), int(math.ceil(hi)) + 1):
        for m in (1, 2, 5):
            v = m * 10 ** d
            if lo <= math.log10(v) <= hi:
                out.append(f'<line x1="{L}" x2="{w - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/><text x="{L - 6}" y="{Y(v) + 4:.1f}" class="ax" text-anchor="end">{v:g}</text>')
    for i, r in enumerate(runs):
        out.append(f'<text x="{X(i):.1f}" y="{h - B + 16}" class="ax" text-anchor="middle">{e(r["name"].split("-")[0])}</text>')
    for k, (sc, pts) in enumerate(series):
        c = f"var(--s{k % 6 + 1})"
        d = " ".join(f"{'M' if j == 0 else 'L'}{X(i):.1f},{Y(v):.1f}" for j, (i, v) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="2.2"/>')
        for i, v in pts:
            out.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3.2" fill="{c}"><title>{e(sc)} · {e(runs[i]["name"])}: {f0(v)} {unit}</title></circle>')
        i, v = pts[-1]
        out.append(f'<text x="{X(i) + 8:.1f}" y="{Y(v) + 4:.1f}" class="lab" fill="{c}">{e(sc)} {f0(v)}</text>')
    out.append("</svg>")
    return "".join(out)


def film_html(media, out_dir, name, title):
    d = media / "films" / name
    meta = d / "filmstrip.json"
    if not meta.exists():
        return f"<p class='miss'>No filmstrip for {e(name)}.</p>"
    fm = json.loads(meta.read_text())
    frames = fm.get("frames") or []
    fup = fm.get("first_useful_paint")
    # every frame up to and including first useful paint, thinned to at most 8
    # WHY through the first frame at or after the paint: frames are only captured when something changes, so the
    # frame that shows the rows can land a few ms after first useful paint; stopping at the paint hid the rows
    after = next((f for f in frames if fup is not None and f["t_ms"] > fup + 1), None)
    upto = ([f for f in frames if fup is None or f["t_ms"] <= fup + 1] + ([after] if after else [])) or frames
    pick = upto if len(upto) <= 8 else [upto[round(i * (len(upto) - 1) / 7)] for i in range(8)]
    rel = os.path.relpath(d, out_dir)
    cells = "".join(f'<figure><img src="{e(rel)}/{e(f["file"])}" alt="{e(title)} at {f["t_ms"]:.0f} ms" loading="lazy"><figcaption>{f["t_ms"]:,.0f} ms</figcaption></figure>' for f in pick)
    return f'<div class="film"><h4>{e(title)} <span class="dim">first useful paint {f0(fup)} ms</span></h4><div class="frames">{cells}</div></div>'


VT_KPIS = [("first_paint_ms", "first paint (headline)"), ("first_paint_100k_ms", "first paint, 100k"), ("interaction_ms", "interaction"),
           ("model_ms", "row model"), ("rail_ms", "rail"), ("scroll_frame_ms", "scroll frame"), ("no_page_errors", "page errors (gate)")]


def producer_html(folder):
    """The whole-bench points the producer folder holds, per commit, as Vibe Tracks will read them (vt-kpi/1)."""
    path = pathlib.Path(folder).expanduser() / "kpi_series.jsonl"
    if not path.exists():
        return ""
    pts = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    whole = [p for p in pts if not p.get("slice")]
    order, by = [], {}
    for p in whole:
        sha = (p.get("source") or {}).get("code_sha")
        key = (sha, p["t"])
        if key not in by:
            by[key] = {}
            order.append(key)
        by[key][p["kpi"]] = p
    head = "".join(f'<th class="num">{e(lab)}</th>' for _, lab in VT_KPIS)
    rows = []
    for sha, t in order:
        cells = ""
        for k, _ in VT_KPIS:
            p = by[(sha, t)].get(k)
            if p is None:
                cells += '<td class="num miss">—</td>'
            elif k == "no_page_errors":
                cells += f'<td class="num">{"pass" if p.get("pass") else "FAIL"}</td>'
            else:
                trust = (p.get("labels") or {}).get("trust")
                cells += f'<td class="num{" dim" if trust == "noisy" else ""}">{f0(p.get("value"))}{" ○" if trust == "noisy" else ""}</td>'
        ev = next((p.get("event") or (p.get("labels") or {}).get("event") for p in by[(sha, t)].values() if p.get("event") or (p.get("labels") or {}).get("event")), "")
        rows.append(f"<tr><td><code>{e(sha or '')}</code></td><td class='dim'>{e(t[:16].replace('T', ' '))}</td>{cells}</tr>")
    return (f"<p>{len(pts):,} points in <code>{e(str(path))}</code>; the whole-bench points (headline scenario, plus the 100k paint), one row "
            f"per published run, ms. ○ = the bench marked the machine noisy (Vibe Tracks draws it hollow).</p>"
            f'<div class="scroll"><table><thead><tr><th>commit</th><th>published (UTC)</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def presentation_html(media):
    """bench/presentation.py's before/after JSON (presentation/<rows>-before|after.json): item 5's own measure."""
    d = media / "presentation"
    if not d.exists():
        return ""
    rows = []
    for rows_n in sorted({p.name.split("-")[0] for p in d.glob("*.json")}, key=int):
        b, a = d / f"{rows_n}-before.json", d / f"{rows_n}-after.json"
        if not (b.exists() and a.exists()):
            continue
        jb, ja = json.loads(b.read_text()), json.loads(a.read_text())
        for k, lab in (("units", "Units toggle"), ("theme", "Dark theme on <html>"), ("search", "Three search keys at once")):
            vb, va = jb[k + "_median_ms"], ja[k + "_median_ms"]
            rows.append(f"<tr><td>{int(rows_n):,}</td><td>{e(lab)}</td><td class='num'>{f0(vb)}</td><td class='num'><b>{f0(va)}</b></td><td>{change(vb, va)}</td>"
                        f"<td class='num'>{e(str(jb[k + '_builds']))} → {e(str(ja[k + '_builds']))}</td></tr>")
    return ("<h3>Item 5's own measure: renders that cannot change the rows</h3><p>bench/presentation.py on the bench's large-table pages, "
            "parent d24530a vs 5a7c0e5, median of 3, ms from the change to the view's data-views-render.</p>"
            "<div class='scroll'><table><thead><tr><th>rows</th><th>change</th><th class='num'>before</th><th class='num'>after</th><th></th>"
            f"<th class='num'>model builds per change</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>")


def build(media, out, items, vt_png, verdict, notes, producer=None, includes=()):
    runs = load_runs(media)
    names = {r["name"]: r for r in runs}
    out_dir = out.parent
    scenarios = []
    for r in runs:
        for k in r["by"]:
            if k not in scenarios:
                scenarios.append(k)

    # ---- per item
    item_rows = []
    for it in items:
        b, a = names.get(it["before"]), names.get(it["after"])
        micro = ""
        for case in it.get("micro", []):
            mb = (b or {}).get("micro") or {}
            ma = (a or {}).get("micro") or {}
            vb, va = (mb.get(case) or {}).get("median"), (ma.get(case) or {}).get("median")
            micro += f"<div><code>{e(case)}</code> {f0(vb)} → <b>{f0(va)}</b> ms {change(vb, va)}</div>"
        bench = ""
        for sc, kpi in it.get("bench", []):
            fn = next(k[3] for k in KPIS if k[0] == kpi)
            lab = next(k[1] for k in KPIS if k[0] == kpi)
            vb = get((b or {"by": {}})["by"].get(sc), fn)
            va = get((a or {"by": {}})["by"].get(sc), fn)
            bench += f"<div>{e(sc)} · {e(lab)}: {f0(vb)} → <b>{f0(va)}</b> ms {change(vb, va)}</div>"
        item_rows.append(f'<tr><td class="n">{it["n"]}</td><td><b>{e(it["title"])}</b><div class="dim"><code>{e(it.get("commit", ""))}</code> · {e(it.get("verdict", ""))}</div><div class="note">{it.get("note", "")}</div></td>'
                         f'<td>{micro or "—"}</td><td>{bench or "—"}</td></tr>')

    # ---- the big table: KPI x scenario x commit
    head = "".join(f'<th class="num">{e(r["name"])}<div class="dim">{e((r["res"].get("code") or {}).get("sha", "")[:7] if isinstance(r["res"].get("code"), dict) else "")} · {e(r["res"].get("trust", ""))}</div></th>' for r in runs)
    body = []
    for sc in scenarios:
        first = True
        rows_for = []
        for kid, lab, unit, fn in KPIS:
            vals = [get(r["by"].get(sc), fn) for r in runs]
            if all(v is None for v in vals):
                continue
            base = next((v for v in vals if v is not None), None)
            # WHY marked, not dropped: a scenario the bench judged noisy still ran; the reader sees it, hollow
            noisy_at = [((r["by"].get(sc) or {}).get("trust") or {}).get("verdict") == "noisy" for r in runs]
            cells = "".join(f'<td class="num{" dim" if noisy_at[i] and v is not None else ""}">{f0(v)}{" ○" if noisy_at[i] and v is not None else ""}</td>' for i, v in enumerate(vals))
            last = next((v for v in reversed(vals) if v is not None), None)
            rows_for.append((lab, unit, cells, change(base, last)))
        for lab, unit, cells, chg in rows_for:
            body.append(f'<tr>{f"<th rowspan={len(rows_for)} class=sc>{e(sc)}</th>" if first else ""}<td>{e(lab)} <span class="dim">{unit}</span></td>{cells}<td>{chg}</td></tr>')
            first = False

    charts = "".join(f"<figure class='cfig'>{chart(runs, scenarios, k)}</figure>" for k in CHART_KPIS)
    films = ""
    for pair_title, before, after in [("robotparts actuators (1,149 rows)", "actuators-before", "actuators-after"), ("synthetic table, 100,000 rows", "100k-before", "100k-after")]:
        films += f"<h3>{e(pair_title)}</h3>" + film_html(media, out_dir, before, "Before (main 7b9d09e)") + film_html(media, out_dir, after, "After (main a1e3042)")
    vt = ""
    if vt_png:
        vt = f'<figure><img class="shot" src="{e(os.path.relpath(vt_png, out_dir))}" alt="The data-ui track in Vibe Tracks"><figcaption>{e(notes.get("vt_caption", ""))}</figcaption></figure>'
    vt += notes.get("vt_html", "")
    if producer:
        vt += producer_html(producer)

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>data-ui perf round 2</title>
<style>
:root {{ --bg:#fff; --fg:#1d1d1f; --dim:#6e6e73; --line:#e3e3e8; --card:#f6f6f8; --good:#0a7d32; --bad:#b3261e;
  --over:#b3261e; --ok:#0a7d32; --rule:#e3e3e8; --s1:#2563eb; --s2:#d97706; --s3:#059669; --s4:#7c3aed; --s5:#db2777; --s6:#0891b2; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141416; --fg:#ececf0; --dim:#9a9aa3; --line:#2c2c31; --card:#1d1d21; --good:#4ade80; --bad:#f87171;
  --over:#f87171; --ok:#4ade80; --rule:#2c2c31; --s1:#60a5fa; --s2:#fbbf24; --s3:#34d399; --s4:#a78bfa; --s5:#f472b6; --s6:#22d3ee; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:17px/1.55 system-ui, -apple-system, Segoe UI, sans-serif; }}
main {{ max-width:1180px; margin:0 auto; padding:28px 16px 80px; }}
h1 {{ font-size:30px; margin:0 0 6px; }} h2 {{ font-size:23px; margin:44px 0 10px; border-top:1px solid var(--line); padding-top:22px; }}
h3 {{ font-size:19px; margin:26px 0 8px; }} h4 {{ margin:10px 0 6px; font-size:16px; }}
.verdict {{ font-size:20px; background:var(--card); border-left:4px solid var(--good); padding:14px 18px; border-radius:6px; }}
.dim {{ color:var(--dim); font-weight:normal; font-size:14px; }} .note {{ font-size:15px; margin-top:4px; }}
table {{ border-collapse:collapse; width:100%; font-size:15px; }} th, td {{ border-bottom:1px solid var(--line); padding:6px 8px; vertical-align:top; text-align:left; }}
td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }} th.sc {{ background:var(--card); }}
.scroll {{ overflow-x:auto; }} td.n {{ font-weight:700; font-size:20px; }}
.chg {{ font-size:13px; padding:1px 6px; border-radius:10px; white-space:nowrap; }} .chg.good {{ color:var(--good); }} .chg.bad {{ color:var(--bad); }} .chg.flat {{ color:var(--dim); }}
.charts {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(340px, 1fr)); gap:14px; }} .cfig {{ margin:0; background:var(--card); border-radius:8px; padding:6px; }}
svg.chart {{ width:100%; height:auto; }} .grid {{ stroke:var(--line); }} .ax {{ fill:var(--dim); font-size:11px; }} .ct {{ fill:var(--fg); font-size:13px; font-weight:600; }} .lab {{ font-size:11px; }}
.film .frames {{ display:flex; gap:6px; overflow-x:auto; }} .film figure {{ margin:0; flex:0 0 auto; }} .film img {{ width:150px; border:1px solid var(--line); border-radius:4px; display:block; }}
.film figcaption {{ font-size:12px; color:var(--dim); text-align:center; }} img.shot {{ max-width:100%; border:1px solid var(--line); border-radius:6px; }}
code {{ font-size:0.9em; }} pre {{ background:var(--card); padding:10px 12px; border-radius:6px; overflow-x:auto; font-size:14px; }}
ul li {{ margin:4px 0; }} .miss {{ color:var(--dim); }}
</style></head><body><main>
<h1>data-ui perf, round 2: the core</h1>
<p class="dim">perf review 2026-10-26 items 1–6 · bench on this machine (Chromium, pinned CPUs), Node microbench on the same data · {e(notes.get("where", ""))}</p>
<div class="verdict">{verdict}</div>
{notes.get("summary_html", "")}
<h2>Each item, before → after</h2>
<p>○ in the big table = the bench marked that scenario's machine noisy (kept, never charted). Micro: <code>node --expose-gc bench/micro.mjs CHECKOUT</code>, median of 15 (7 for 10k/100k). Bench: <code>npm run bench</code>, 5 cold and 5 warm loads per scenario, p95; each run's machine trust is in the column head.</p>
<div class="scroll"><table><thead><tr><th>#</th><th>Item</th><th>Microbench (Node)</th><th>Browser bench</th></tr></thead><tbody>{"".join(item_rows)}</tbody></table></div>
{presentation_html(media)}
<h2>Over the commits</h2>
<div class="charts">{charts}</div>
<h2>Every KPI, every scenario, every commit</h2>
<div class="scroll"><table><thead><tr><th>Scenario</th><th>KPI</th>{head}<th>first → last</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>
<h2>First paint, frame by frame</h2>
<p class="dim">One cold load each (bench/filmstrip.py, Chromium's own screenshot trace; time zero is navigation). A picture of the chain, not a measurement: the numbers above are the measurement.</p>
{films}
{"".join(pathlib.Path(f).read_text() for f in includes)}
<h2>Vibe Tracks</h2>
{vt}
{notes.get("tail_html", "")}
</main></body></html>"""
    out.write_text(page)
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("media")
    ap.add_argument("out")
    ap.add_argument("--items", required=True)
    ap.add_argument("--vt")
    ap.add_argument("--include", action="append", default=[], help="an HTML fragment to place before the Vibe Tracks section (repeatable)")
    ap.add_argument("--producer", help="the Vibe Tracks producer folder (~/vt/zach/producers/data-ui)")
    a = ap.parse_args()
    spec = json.loads(pathlib.Path(a.items).read_text())
    build(pathlib.Path(a.media).resolve(), pathlib.Path(a.out).resolve(), spec["items"], a.vt, spec["verdict"], spec.get("notes", {}), a.producer, a.include)


if __name__ == "__main__":
    main()
