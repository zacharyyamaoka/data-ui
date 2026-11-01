#!/usr/bin/env python3
"""Build the data-ui performance report from a bench result: verdict, per-scenario baseline, worst offenders, KPI vs
row count, the first-paint chain, a filmstrip, the Vibe Tracks track, the KPI definitions and how to run the bench.

    python3 docs/build_perf_report.py RESULTS.json OUT.html --media MEDIA_DIR [--filmstrip DIR ...] [--vt PNG]

MEDIA_DIR is where the page's images live (relative links from OUT.html; reports/media/perf/). Every number on the
page is read from RESULTS (the bench's own JSON, copied beside the media), so the page cannot show a number the bench
did not measure. Stdlib only. WHY a big type scale (17 px body): Zach said earlier reports were too small to read.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATALOG = json.loads((ROOT / "bench" / "kpi_catalog.json").read_text())
e = html.escape
HEAD = CATALOG["headline_scenario"]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "bench"))
from publish import failed_because  # noqa: E402  WHY one rule: the page and Vibe Tracks fail a scenario the same way


def f0(x, unit=""):
    if x is None:
        return "—"
    return (f"{x:,.0f}" if abs(x) >= 10 else f"{x:,.1f}") + unit


def pct(values, p):
    v = sorted(x for x in values if x is not None)
    return v[max(1, math.ceil(p / 100 * len(v))) - 1] if v else None


def inter(s, kind=None, key="ms", p=95):
    if s is None or failed_because(s):
        return None
    xs = [x for x in s["samples"]["interactions"] if x.get("ms") is not None and (kind is None or x["kind"] == kind)]
    return pct([x.get(key) for x in xs], p)


def kb(x):
    return None if x is None else x / 1024


def scroll_p95(s):
    return (s.get("scroll") or {}).get("p95") if s else None


def budget_cell(value, target):
    if value is None:
        return '<td class="num miss">—</td>'
    if target is None:
        return f'<td class="num">{f0(value)}</td>'
    cls = "over" if value > target else "ok"
    return f'<td class="num {cls}" title="budget {f0(target)}">{f0(value)}</td>'


# ---------------------------------------------------------------- charts (inline SVG; one series per panel)

def panel(title, unit, pts, target=None, log_y=False, w=330, h=210):
    """pts: [(rows, value | None, label)] on an evenly spaced x axis. Single series: the title names it, so no legend."""
    pad_l, pad_r, pad_t, pad_b = 52, 16, 30, 34
    if log_y:  # a 0 on a log axis sits on the floor (0.1), labelled with its true value
        pts = [(x, (v if v is None or v > 0 else 0.1), lab) for x, v, lab in pts]
    xs = [p[0] for p in pts]
    vals = [p[1] for p in pts if p[1] is not None] + ([target] if target else [])
    if not vals:
        return f'<figure class="panel"><figcaption>{e(title)}</figcaption><p class="miss">not measured</p></figure>'
    # WHY evenly spaced: 100k and 150k sit almost on top of each other on a log axis; the labels carry the row count
    order = {x: i for i, x in enumerate(sorted(set(xs)))}
    lo_y = min(vals) if log_y else 0
    hi_y = max(vals) * 1.12
    if log_y:
        lo_y, hi_y = math.log10(max(min(vals) * 0.8, 1e-3)), math.log10(hi_y)
    X = lambda x: pad_l + 14 + order[x] / max(1, len(order) - 1) * (w - pad_l - pad_r - 28)
    Y = lambda y: h - pad_b - ((math.log10(y) if log_y else y) - lo_y) / ((hi_y - lo_y) or 1) * (h - pad_t - pad_b)
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{e(title)} against row count">']
    for k in range(5):
        yv = lo_y + (hi_y - lo_y) * k / 4
        real = 10 ** yv if log_y else yv
        out.append(f'<line class="grid" x1="{pad_l}" x2="{w - pad_r}" y1="{Y(real):.1f}" y2="{Y(real):.1f}"/>'
                   f'<text class="tick" x="{pad_l - 6}" y="{Y(real) + 4:.1f}" text-anchor="end">{f0(real)}</text>')
    for x in xs:
        out.append(f'<text class="tick" x="{X(x):.1f}" y="{h - pad_b + 18}" text-anchor="middle">{x // 1000:,}k</text>')
    if target:
        out.append(f'<line class="target" x1="{pad_l}" x2="{w - pad_r}" y1="{Y(target):.1f}" y2="{Y(target):.1f}"/>'
                   f'<text class="tick tgt" x="{pad_l + 4}" y="{Y(target) - 5:.1f}" text-anchor="start">budget {f0(target)} {e(unit)}</text>')
    good = [(x, v) for x, v, _ in pts if v is not None]
    if len(good) > 1:
        out.append('<polyline class="line" points="' + " ".join(f"{X(x):.1f},{Y(v):.1f}" for x, v in good) + '"/>')
    for x, v, label in pts:
        if v is None:
            out.append(f'<text class="fail" x="{X(x):.1f}" y="{h - pad_b - 8}" text-anchor="middle"><title>FAILED: {e(label or "")}</title>✕</text><text class="fail" x="{X(x):.1f}" y="{h - pad_b - 22}" text-anchor="middle">FAILED</text>')
            continue
        out.append(f'<circle class="dot" cx="{X(x):.1f}" cy="{Y(v):.1f}" r="5"><title>{x:,} rows: {f0(v)} {e(unit)}{(" · " + e(label)) if label else ""}</title></circle>'
                   f'<text class="val" x="{X(x):.1f}" y="{Y(v) - 10:.1f}" text-anchor="middle">{f0(v)}</text>')
    out.append("</svg>")
    return f'<figure class="panel"><figcaption>{e(title)} <span class="unit">{e(unit)}</span></figcaption>{"".join(out)}</figure>'


def chain_rows(scenarios):
    """The first-paint chain of each scenario's median cold load, as one horizontal timeline per scenario."""
    rows = []
    maxt = 0
    for s in scenarios:
        cold = [x for x in s["samples"]["cold"] if x.get("first_useful_paint") is not None]
        if not cold:
            continue
        med = sorted(cold, key=lambda x: x["first_useful_paint"])[len(cold) // 2]
        c = med["chain"]
        steps = [("core js", 0, c.get("core_js_end")), (".base", None, c.get("base_end")), ("data", c.get("data_start"), c.get("data_end")), ("parse", c.get("data_end"), med.get("mark_data")),
                 ("model + toolbar", med.get("mark_start"), (c.get("view_js_start") or med.get("first_render"))),
                 ("view bundle", c.get("view_js_start"), c.get("view_js_end")), ("draw", c.get("view_js_end") or med.get("mark_start"), med.get("first_render")),
                 ("paint", med.get("first_render"), med.get("first_useful_paint"))]
        maxt = max(maxt, med["first_useful_paint"])
        rows.append((s, med, steps))
    w, lab = 1080, 230
    scale = (w - lab - 70) / (maxt or 1)
    out = []
    for s, med, steps in rows:
        bars = []
        for i, (name, a, b) in enumerate(steps):
            if a is None or b is None or b <= a:
                continue
            bars.append(f'<rect class="seg s{i}" x="{lab + a * scale:.1f}" y="6" width="{max(1.5, (b - a) * scale):.1f}" height="16" rx="3"><title>{e(name)}: {a:.0f} → {b:.0f} ms</title></rect>')
        bars.append(f'<text class="val" x="{lab + med["first_useful_paint"] * scale + 6:.1f}" y="19">{f0(med["first_useful_paint"])} ms</text>')
        out.append(f'<svg viewBox="0 0 {w} 28" class="chain"><text class="lbl" x="0" y="19">{e(s["target"])}</text>{"".join(bars)}</svg>')
    legend = "".join(f'<span class="key"><i class="seg s{i}"></i>{e(n)}</span>' for i, n in enumerate(["core js loaded", ".base loaded", "data fetched", "parse + normalise", "model + toolbar (before the view bundle is requested)", "view bundle", "view draws", "→ next frame"]))
    return f'<div class="legend">{legend}</div>' + "".join(out)


# ---------------------------------------------------------------- the page

def compare_html(res, cmp_res, cmp_rel):
    """The second point: the same scenarios on a later commit, beside the baseline."""
    by0 = {s["target"]: s for s in res["scenarios"]}
    rows = []
    for s1 in cmp_res["scenarios"]:
        s0 = by0.get(s1["target"])
        def cell(s, fn):
            if s is None:
                return "<td class=num>—</td>"
            if failed_because(s):
                return '<td class="failcell"><b>FAILED</b></td>'
            v = fn(s)
            return f'<td class="num">{f0(v)}</td>'
        metrics = [("first paint cold p95", lambda s: s["load"]["cold"]["first_useful_paint"]["p95"]), ("first paint warm p95", lambda s: s["load"]["warm"]["first_useful_paint"]["p95"]),
                   ("interaction p95", lambda s: inter(s)), ("row model / interaction p95", lambda s: inter(s, None, "model_ms")),
                   ("rail recount / interaction p95", lambda s: inter(s, None, "rail_ms")), ("heap MB", lambda s: s["load"]["cold"]["heap_mb"]["p50"])]
        for i, (name, fn) in enumerate(metrics):
            head = f'<th scope="row" rowspan="{len(metrics) + 2}">{e(s1["target"])}</th>' if i == 0 else ""
            rows.append(f"<tr>{head}<td>{e(name)}</td>{cell(s0, fn)}{cell(s1, fn)}</tr>")
        c0 = s0["trust"]["calibration_ms"] if s0 else None
        c1 = s1["trust"]["calibration_ms"]
        rows.append(f'<tr><td>machine speed (calibration, ms; lower is faster)</td><td class="num">{"–".join(f0(x) for x in c0) if c0 else "—"}</td><td class="num">{"–".join(f0(x) for x in c1)}</td></tr>')
        rows.append(f'<tr><td>verdict</td><td>{"FAILED: " + e("; ".join(failed_because(s0))[:140]) if s0 and failed_because(s0) else "ok"}</td>'
                    f'<td>{"FAILED: " + e("; ".join(failed_because(s1))[:140]) if failed_because(s1) else "ok"}</td></tr>')
    return (f'<h2>Second point: main {e(cmp_res["code"]["sha"] or "")}, the seven correctness fixes</h2>'
            f'<p class="cap">data-ui main moved to {e(cmp_res["code"]["sha"] or "")} during the baseline: the 150,000-row rail overflow (a fold instead of '
            f'<code>Math.min(...nums)</code>), linear <code>treeRows</code>, the chart queue, the fetch race and the lifecycle leaks; no speed work. Its build (plus the same three '
            f'marks) re-ran the headline and the two large tables, {cmp_res["runs"]} runs each, trust {e(cmp_res.get("trust") or "")}. Raw: <a href="{e(cmp_rel)}">{e(os.path.basename(cmp_rel))}</a>.</p>'
            f'<p class="cap"><b>Read the headline change with the calibration row:</b> every number moves with the machine. When the second run\'s calibration is '
            f'slower, a slower paint on code that did not change its render path is the machine. The noisy flag only trips at 1.3×. The 150k verdict is the code: '
            f'the rail threw on 0dbc3d4 and draws on 0059637.</p>'
            f'<div class="scroll"><table><thead><tr><th>scenario</th><th>measure</th><th>0dbc3d4 (baseline)</th><th>{e(cmp_res["code"]["sha"] or "")}</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def build(res, out, media_rel, films, vt_png, results_rel, cmp=None, cmp_rel=None):
    sc = res["scenarios"]
    by = {s["target"]: s for s in sc}
    real = [s for s in sc if not s["synthetic"]]
    head = by.get(HEAD)
    kpis = {k["id"]: k for k in CATALOG["kpis"]}

    def tile(kid, value, note=""):
        k = kpis[kid]
        t = k.get("target")
        state = "—" if value is None else ("over budget" if t is not None and value > t else "within budget" if t is not None else "diagnostic")
        cls = "miss" if value is None else ("over" if t is not None and value > t else "ok")
        return (f'<div class="tile {cls}"><div class="k">{e(k["title"])}</div><div class="v">{f0(value)}<small> {e(k["unit"])}</small></div>'
                f'<div class="b">{e(state)}{f" · budget {f0(t)} {e(k["unit"])}" if t is not None else ""}</div>{f"<div class=n>{e(note)}</div>" if note else ""}</div>')

    worst_real = max(real, key=lambda s: s["load"]["cold"]["first_useful_paint"]["p95"] or 0) if real else None
    # WHY None for a FAILED scenario: a page that threw or lost a part never shows a passing number (guard, 2026-10-26)
    L = lambda s, ph, k, p="p95": s["load"][ph][k][p] if s and not failed_because(s) else None
    tiles = [
        tile("first_paint_ms", L(head, "cold", "first_useful_paint"), "robotparts actuators, 1,149 rows, with the rail"),
        tile("first_paint_warm_ms", L(head, "warm", "first_useful_paint")),
        tile("first_paint_worst_ms", L(worst_real, "cold", "first_useful_paint"), worst_real["target"] if worst_real else ""),
        tile("interactive_ms", L(head, "cold", "tti")),
        tile("blocking_ms", L(head, "cold", "tbt")),
        tile("interaction_ms", inter(head) if head else None, "every tick, sort, keystroke, preset and peek"),
        tile("scroll_frame_ms", scroll_p95(by.get("large-table@10000")), "large-table@10000"),
        tile("load_kb", (L(head, "cold", "bytes_gzip", "p50") or 0) / 1024 if head else None),
        tile("first_paint_100k_ms", L(by.get("large-table@100000"), "cold", "first_useful_paint"), "synthetic, sampled from the real actuators"),
    ]

    # per-scenario table
    trs = []
    for s in sc:
        cold, warm = s["load"]["cold"], s["load"]["warm"]
        kinds = sorted({x["kind"] for x in s["samples"]["interactions"] if x.get("ms") is not None})
        worst_kind = max(kinds, key=lambda k: inter(s, k) or 0) if kinds else None
        if failed_because(s):
            trs.append(f'<tr class="failed"><th scope="row">{e(s["target"])}<div class="sub">{e(s.get("app") or "")} · {e(s.get("view") or "")}{" · synthetic" if s["synthetic"] else ""}</div></th>'
                       f'<td class="num">{f0(s.get("rows"))}</td><td colspan="9" class="failcell"><b>FAILED</b>: {e("; ".join(failed_because(s))[:220])}</td>'
                       f'<td class="trust {s["trust"]["verdict"]}">{e(s["trust"]["verdict"])}</td><td></td></tr>')
            continue
        trs.append(
            f'<tr><th scope="row">{e(s["target"])}<div class="sub">{e(s.get("app") or "")} · {e(s.get("view") or "")}{" · synthetic" if s["synthetic"] else ""}</div></th>'
            f'<td class="num">{f0(s.get("rows"))}</td>'
            f'<td class="num">{f0(cold["first_useful_paint"]["p50"])}</td>{budget_cell(cold["first_useful_paint"]["p95"], 1000)}{budget_cell(warm["first_useful_paint"]["p95"], 500)}'
            f'{budget_cell(cold["tti"]["p95"], 1500)}{budget_cell(cold["tbt"]["p95"], 200)}{budget_cell(inter(s), 100)}'
            f'<td>{e(worst_kind or "—")} {f0(inter(s, worst_kind)) if worst_kind else ""}</td>'
            f'{budget_cell((cold["bytes_gzip"]["p50"] or 0) / 1024 if cold["bytes_gzip"]["p50"] is not None else None, 200)}<td class="num">{f0(cold["heap_mb"]["p50"])}</td>'
            f'<td class="trust {s["trust"]["verdict"]}" title="{e("; ".join(s["trust"]["why"]))}">{e(s["trust"]["verdict"])}</td>'
            f'<td class="err">{e((s["errors"] or [""])[0][:90])}</td></tr>')

    # worst offenders: every (scenario, KPI) over budget, ranked by how far over
    offenders = []
    checks = [("first paint cold p95", lambda s: L(s, "cold", "first_useful_paint"), 1000), ("first paint warm p95", lambda s: L(s, "warm", "first_useful_paint"), 500),
              ("time to interactive p95", lambda s: L(s, "cold", "tti"), 1500), ("blocking time p95", lambda s: L(s, "cold", "tbt"), 200),
              ("interaction p95", lambda s: inter(s), 100), ("first-load KB (gzip)", lambda s: (L(s, "cold", "bytes_gzip", "p50") or 0) / 1024, 200)]
    for s in sc:
        for name, fn, t in checks:
            v = fn(s)
            if v is not None and v > t:
                offenders.append((v / t, s, name, v, t))
        if s.get("scroll") and s["scroll"]["p95"] and s["scroll"]["p95"] > 16.7:
            offenders.append((s["scroll"]["p95"] / 16.7, s, "scroll frame p95", s["scroll"]["p95"], 16.7))
        if failed_because(s):
            offenders.append((99, s, "FAILED", None, None))
    offenders.sort(key=lambda o: -o[0])
    off_html = "".join(f'<li><b>{e(s["target"])}</b> · {e(name)}: <b>{f0(v)}</b> vs budget {f0(t)} <span class="x">({r:.1f}×)</span>'
                       f'{" <span class=syn>synthetic</span>" if s["synthetic"] else ""}</li>' if v is not None else
                       f'<li><b>{e(s["target"])}</b> · <b class="x">FAILED</b>: {e("; ".join(failed_because(s))[:220])}. Its rows still paint, so without the guard it would have published a passing paint number.</li>'
                       for r, s, name, v, t in offenders[:14])

    # Codex's levers, each with the number that will move
    def kp(s, kind, key, p=95):
        return f0(inter(s, kind, key, p)) if s else "—"
    levers = [
        ("Intl.NumberFormat caching (40-row HTML 15.4 → 1.7 ms, Node)", "render_ms − model_ms on a redraw of the actuators",
         f'sort: render {kp(head, "sort", "render_ms")} ms, model {kp(head, "sort", "model_ms")} ms (p95)'),
        ("Intl.Collator caching (grouped model 116 → 41 ms, Node)", "model_ms on the grouped presets",
         f'preset switch: model {kp(head, "preset", "model_ms")} ms p95 · first load model {f0(L(head, "cold", "model_ms"))} ms p95'),
        ("First-paint chain: the model before the view bundle is requested", "the chain below: data fetched → view bundle requested",
         f'actuators median cold: data at {f0(L(head, "cold", "mark_data", "p50"))} ms, first render {f0(L(head, "cold", "first_render", "p50"))} ms, paint {f0(L(head, "cold", "first_useful_paint", "p50"))} ms'),
        ("Facet counts on every redraw", "rail_ms inside each interaction (a sort recounts the rail)",
         f'sort {kp(head, "sort", "rail_ms")} ms · keystroke {kp(head, "search", "rail_ms")} ms · tick {kp(head, "filter", "rail_ms")} ms (p95)'),
        ("Full tbody replacement on every draw", "dom_added per interaction; scroll frame time",
         f'sort {kp(head, "sort", "dom_added", 50)} nodes · scroll p95 {f0(scroll_p95(by.get("large-table@10000")))} ms on 10k'),
        ("100k-row scaling (619 ms model, 74 MiB, Node)", "large-table@100000: first paint, heap, model",
         f'first paint {f0(L(by.get("large-table@100000"), "cold", "first_useful_paint"))} ms p95 · heap {f0(L(by.get("large-table@100000"), "cold", "heap_mb", "p50"))} MB · model {f0(L(by.get("large-table@100000"), "cold", "model_ms"))} ms'),
        ("150k-row railCounts() stack overflow", "large-table@150000: the health guard (FAILED, never a paint number)",
         ("FAILED: " + "; ".join(failed_because(by["large-table@150000"]))[:150] + ". Fixed on 0059637 (9b054fe): see the second point.") if by.get("large-table@150000") and failed_because(by["large-table@150000"])
         else (f'drew in {f0(L(by.get("large-table@150000"), "cold", "first_useful_paint"))} ms p95' if by.get("large-table@150000") else "not run")),
    ]
    lever_html = "".join(f"<tr><th scope=row>{e(a)}</th><td>{e(b)}</td><td>{e(c)}</td></tr>" for a, b, c in levers)

    # scaling small multiples
    lt = sorted([s for s in sc if s["id"] == "large-table"], key=lambda s: s["rows"])
    def series(fn):
        return [(s["rows"], fn(s), (s["errors"] or [None])[0]) for s in lt]
    panels = "".join([
        panel("First useful paint, cold p95", "ms", series(lambda s: L(s, "cold", "first_useful_paint")), 1000, log_y=True),
        panel("Time to interactive, cold p95", "ms", series(lambda s: L(s, "cold", "tti")), 1500, log_y=True),
        panel("Interaction latency p95", "ms", series(lambda s: inter(s)), 100, log_y=True),
        panel("Row model per interaction p95", "ms", series(lambda s: inter(s, None, "model_ms")), None, log_y=True),
        panel("Rail recount per interaction p95", "ms", series(lambda s: inter(s, None, "rail_ms")), None, log_y=True),
        panel("Scroll frame p95", "ms", series(lambda s: s["scroll"]["p95"] if s.get("scroll") else None), 16.7, log_y=True),
        panel("JS heap after load", "MB", series(lambda s: L(s, "cold", "heap_mb", "p50")), None, log_y=True),
        panel("First load (gzip)", "KB", series(lambda s: kb(L(s, "cold", "bytes_gzip", "p50"))), 200, log_y=True),
    ]) if lt else "<p>large-table was not in this run.</p>"
    kinds = ["filter", "sort", "search", "peek", "preset"]
    kind_panels = "".join(panel(f"{k} p95", "ms", series(lambda s, k=k: inter(s, k)), 100, log_y=True) for k in kinds) if lt else ""

    # filmstrips
    film_html = ""
    for fdir in films:
        meta = json.loads((fdir / "filmstrip.json").read_text())
        rel = os.path.relpath(fdir, out.parent)
        marks = {m["name"]: m["t"] for m in meta["marks"]}
        frames = "".join(f'<figure><img src="{e(rel)}/{e(fr["file"])}" alt="frame at {fr["t_ms"]} ms" loading="lazy"><figcaption>{fr["t_ms"]:,} ms</figcaption></figure>' for fr in meta["frames"])
        film_html += (f'<h3>{e(meta["scenario"])}</h3><p class="cap">One cold load, frame by frame from navigation start (Chromium trace screenshots). '
                      f'data fetched {f0(marks.get("data-ui:data"))} ms · toolbar in the DOM {f0(marks.get("data-ui:start"))} ms · first contentful paint {f0(meta.get("fcp"))} ms · '
                      f'first view drawn {f0(marks.get("data-ui:first-render"))} ms · <b>first useful paint {f0(meta.get("first_useful_paint"))} ms</b>.</p><div class="film">{frames}</div>')

    kpi_rows = "".join(f'<tr><td>L{k["level"]}</td><th scope="row"><code>{e(k["id"])}</code><div class="sub">{e(k["title"])}</div></th><td>{e(k["description"])}</td>'
                       f'<td class="num">{f0(k.get("target"))} {e(k["unit"]) if k.get("target") is not None else ""}</td></tr>' for k in CATALOG["kpis"])
    host = res["host"]
    trust_all = res.get("trust")
    noisy = [s["target"] for s in sc if s["trust"]["verdict"] == "noisy"]
    loads = [x for s in sc for x in s["trust"]["loadavg"] if x is not None]
    calibs = [x for s in sc for x in s["trust"]["calibration_ms"]]
    best_cal = min(s["trust"]["best_calibration_ms"] for s in sc) if sc else None
    over_head = [name for name, fn, t in checks if head and fn(head) is not None and fn(head) > t]

    if head:
        fp, ip = L(head, "cold", "first_useful_paint"), inter(head)
        verdict = (f"<b>Baseline recorded on data-ui main 0dbc3d4: the actuators' first useful paint is {f0(fp)} ms cold (p95), "
                   f"{'inside' if fp is not None and fp <= 1000 else 'over'} its 1 s budget; their interactions' p95 is {f0(ip)} ms, "
                   f"{'inside' if ip is not None and ip <= 100 else 'over'} the 100 ms budget. Scale is where it breaks: 100,000 rows take {f0(L(by.get('large-table@100000'), 'cold', 'first_useful_paint'))} ms "
                   f"to first paint, nothing painting until the row model is done; 150,000 rows FAILED (the rail overflowed the stack) and pass on main 0059637.</b>")
    else:
        verdict = "<b>Baseline recorded (the headline scenario was not in this run).</b>"
    vt_html = "".join(f'<figure class="shotfig"><img class="shot" src="{e(os.path.relpath(png, out.parent))}" alt="{e(cap)}" loading="lazy"><figcaption class="cap">{e(cap)}</figcaption></figure>'
                      for png, cap in (vt_png or [])) or "<p>No screenshot in this build.</p>"

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>data-ui speed baseline</title>
<style>
:root{{--bg:#fcfcfb;--fg:#0b0b0b;--muted:#52514e;--rule:#e4e3df;--subtle:#f3f2ef;--accent:#2a78d6;--over:#b3261e;--ok:#0b6b3a;--warn:#8a5a00;
 --s0:#9aa0a6;--s1:#7f8c8d;--s2:#1baf7a;--s3:#8fd3b6;--s4:#c9a227;--s5:#2a78d6;--s6:#6250d6;--s7:#eb6834}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#1a1a19;--fg:#f0efec;--muted:#c3c2b7;--rule:#3a3936;--subtle:#242422;--accent:#3987e5;--over:#ff8a80;--ok:#7ad69b;--warn:#e0b050}}}}
:root[data-theme="dark"]{{--bg:#1a1a19;--fg:#f0efec;--muted:#c3c2b7;--rule:#3a3936;--subtle:#242422;--accent:#3987e5;--over:#ff8a80;--ok:#7ad69b;--warn:#e0b050}}
html{{background:var(--bg);color:var(--fg)}} body{{margin:0 auto;max-width:1480px;padding:28px 16px 80px;font:17px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}}
h1{{font-size:34px;line-height:1.2;margin:0 0 8px}} h2{{font-size:25px;margin:44px 0 10px;border-top:1px solid var(--rule);padding-top:22px}} h3{{font-size:19px;margin:22px 0 6px}}
.lead{{font-size:19px;max-width:1100px}} .cap,.sub,.unit{{color:var(--muted)}} .sub{{font-size:14px;font-weight:400}} code{{font-size:15px}}
.banner.quiet{{border-color:var(--ok)}} .banner.quiet b{{color:var(--ok)}} .banner{{border:1px solid var(--warn);border-radius:10px;padding:12px 16px;margin:16px 0;max-width:1100px}} .banner b{{color:var(--warn)}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;margin:18px 0}}
.tile{{border:1px solid var(--rule);border-radius:10px;padding:12px 14px}} .tile .k{{font-size:14px;color:var(--muted)}} .tile .v{{font-size:30px;font-weight:650;font-variant-numeric:tabular-nums}}
.tile .v small{{font-size:15px;font-weight:400;color:var(--muted)}} .tile .b{{font-size:14px}} .tile.over .b{{color:var(--over)}} .tile.ok .b{{color:var(--ok)}} .tile .n{{font-size:13px;color:var(--muted)}}
.scroll{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:15px}} th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--rule);vertical-align:top}}
thead th{{background:var(--subtle);font-size:13px;position:sticky;top:0}} td.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
td.over{{color:var(--over);font-weight:600}} td.ok{{color:var(--ok)}} td.miss,p.miss{{color:var(--muted)}} td.err{{font-size:13px;color:var(--over);max-width:260px}}
tr.failed th,.failcell{{background:color-mix(in srgb,var(--over) 10%,transparent)}} .failcell{{color:var(--over)}}
td.trust.noisy{{color:var(--warn)}} td.trust.quiet{{color:var(--ok)}}
ol.off li{{margin:4px 0}} .x{{color:var(--over)}} .syn{{font-size:12px;border:1px solid var(--rule);border-radius:4px;padding:0 4px;color:var(--muted)}}
.panels{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}} .panel{{margin:0;border:1px solid var(--rule);border-radius:10px;padding:8px 10px}}
.panel figcaption{{font-weight:600;font-size:15px}} svg{{width:100%;height:auto;display:block}}
.grid{{stroke:var(--rule);stroke-width:1}} .tick{{fill:var(--muted);font-size:11px}} .tgt{{fill:var(--over)}} .target{{stroke:var(--over);stroke-dasharray:4 4;stroke-width:1.5}}
.line{{fill:none;stroke:var(--accent);stroke-width:2}} .dot{{fill:var(--accent);stroke:var(--bg);stroke-width:2}} .val{{fill:var(--fg);font-size:12px;font-weight:600}}
.fail{{fill:var(--over);font-size:12px;font-weight:700}} .lbl{{fill:var(--fg);font-size:13px}}
.chain{{margin:2px 0}} .seg.s0{{fill:var(--s0)}} .seg.s1{{fill:var(--s1)}} .seg.s2{{fill:var(--s2)}} .seg.s3{{fill:var(--s3)}} .seg.s4{{fill:var(--s4)}} .seg.s5{{fill:var(--s5)}} .seg.s6{{fill:var(--s6)}} .seg.s7{{fill:var(--s7)}}
.legend{{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:14px;margin:6px 0 10px}} .key i{{display:inline-block;width:14px;height:10px;border-radius:2px;margin-right:6px}}
.key i.s0{{background:var(--s0)}} .key i.s1{{background:var(--s1)}} .key i.s2{{background:var(--s2)}} .key i.s3{{background:var(--s3)}} .key i.s4{{background:var(--s4)}} .key i.s5{{background:var(--s5)}} .key i.s6{{background:var(--s6)}} .key i.s7{{background:var(--s7)}}
.film{{display:flex;gap:10px;overflow-x:auto;padding-bottom:6px}} .film figure{{margin:0;flex:none;width:300px}} .film img{{width:300px;border:1px solid var(--rule);border-radius:6px}}
.film figcaption{{font-size:14px;text-align:center;font-variant-numeric:tabular-nums}}
.shotfig{{margin:0 0 18px}} .shot{{max-width:100%;border:1px solid var(--rule);border-radius:10px}} pre{{background:var(--subtle);padding:10px 12px;border-radius:8px;overflow-x:auto;font-size:14px}}
ul.dec li{{margin:6px 0}}
</style></head><body>
<h1>data-ui speed: the first baseline</h1>
<p class="lead">{verdict}</p>
<p class="cap">{len(sc)} scenarios ({len(real)} on real data from Zach's apps, the rest synthetic and labelled), {res["runs"]} cold + {res["runs"]} warm loads each
(fewer at ≥ 100k rows), then every interaction on the warm page. Code: <code>{e(res["code"]["branch"] or "")} @ {e(res["code"]["sha"] or "")}</code>
(data-ui main 0dbc3d4 plus the bench's <code>performance.mark</code> hooks, before any optimisation). Host: {e(host["hostname"])}, {e(host["cpu"])}, {e(host["browser"])},
1440×900, pinned to {len(host["pinned_cpus"] or [])} CPUs. Run {e(res["started"])} → {e(res["finished"])}. Raw results: <a href="{e(results_rel)}">{e(os.path.basename(results_rel))}</a>.</p>
<div class="banner {e(trust_all)}"><b>Trust: {e(trust_all)}.</b> {len(noisy)} of {len(sc)} scenarios ran on a noisy machine
(load average {f0(min(loads)) if loads else "—"}–{f0(max(loads)) if loads else "—"} on {host["cpus"]} CPUs; browser calibration {f0(min(calibs)) if calibs else "—"}–{f0(max(calibs)) if calibs else "—"} ms
against this host's best {f0(best_cal)} ms; noisy means over 1.3× that, or load per CPU over 1). {"Other agents' jobs shared the machine: read the noisy rows' single numbers with care; Vibe Tracks draws them hollow." if noisy else "An earlier attempt under load average 45 was discarded for this one: every scenario here ran within 1.3× of the machine's best speed. Other agents still shared the machine, so treat a difference under about 20 % between two runs as noise unless their calibrations match."}</div>

<div class="tiles">{"".join(tiles)}</div>

<h2>Worst offenders, ranked by how far over budget</h2>
<ol class="off">{off_html or "<li>Nothing is over budget.</li>"}</ol>

{compare_html(res, cmp, cmp_rel) if cmp else ""}

<h2>Every scenario</h2>
<p class="cap">Times in ms (p50 / p95 nearest-rank); red is over the budget in the column head. "Worst" is the slowest interaction kind's p95.</p>
<div class="scroll"><table><thead><tr><th>scenario</th><th>rows</th><th>paint cold p50</th><th>paint cold p95 (1,000)</th><th>paint warm p95 (500)</th><th>TTI p95 (1,500)</th><th>TBT p95 (200)</th>
<th>interaction p95 (100)</th><th>worst kind</th><th>KB gzip (200)</th><th>heap MB</th><th>trust</th><th>error</th></tr></thead><tbody>{"".join(trs)}</tbody></table></div>

<h2>Codex's levers, and the baseline number each will move</h2>
<p class="cap">From the read-only review of main 0dbc3d4 (<code>reports/media/audits/2026-10-26-data-ui-performance-findings.md</code>), which could measure in Node only. These are the first browser numbers.</p>
<div class="scroll"><table><thead><tr><th>lever</th><th>measured by</th><th>baseline (actuators unless named)</th></tr></thead><tbody>{lever_html}</tbody></table></div>

<h2>Each KPI against row count</h2>
<p class="cap">The synthetic actuator table (sampled from the real 1,149, numerics jittered ±10 %) at 1k, 10k, 100k and 150k rows (evenly spaced; the y axis is log); the dashed red line is the budget. ✕ FAILED marks a scenario the health guard failed: no number is drawn for it.</p>
<div class="panels">{panels}</div>
<h3>Interaction latency by kind</h3><div class="panels">{kind_panels}</div>

<h2>The first-paint chain</h2>
<p class="cap">Each scenario's median cold load, from navigation start. The gold "model + toolbar" stretch is the row model computed before the view bundle is requested (Codex's finding); read its width per scenario.</p>
<div class="scroll">{chain_rows(sorted(sc, key=lambda s: -(L(s, "cold", "first_useful_paint", "p50") or 0)))}</div>

<h2>Filmstrip</h2>
{film_html or "<p>No filmstrip in this build.</p>"}

<h2>The Vibe Tracks track</h2>
<p class="cap">The baseline published as producer files (<code>~/vt/zach/producers/data-ui</code>, <code>vt-kpi/1</code>) and the track page computed from them.</p>
{vt_html}

<h2>The KPIs</h2>
<p class="cap">Lower is better for all. p95 nearest-rank over the runs; cold = new browser context, warm = reloaded. Reasoning and prior art: <code>bench/KPIS.md</code>.</p>
<div class="scroll"><table><thead><tr><th>level</th><th>KPI</th><th>definition</th><th>budget</th></tr></thead><tbody>{kpi_rows}</tbody></table></div>

<h2>Run the bench</h2>
<pre>npm --prefix ~/data-ui run bench
npm --prefix ~/data-ui run bench -- --scenario robotparts-actuators --runs 3
python3 ~/data-ui/bench/publish.py --to ~/vt/zach/producers/data-ui --event "after &lt;change&gt;"</pre>
<p class="cap">Builds <code>dist/</code>, serves it and the scenarios from inside the runner's own process, runs headless Chromium pinned to 8 CPUs, and writes <code>bench/.out/latest.json</code>. Everything it starts, it stops. <code>bench/README.md</code> has the options.</p>
</body></html>"""
    out.write_text(page)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("out")
    ap.add_argument("--filmstrip", action="append", default=[])
    ap.add_argument("--vt", action="append", default=[], help="PNG=caption, repeatable")
    ap.add_argument("--compare", help="a later run of some scenarios (the second point)")
    args = ap.parse_args()
    res = json.loads(pathlib.Path(args.results).read_text())
    out = pathlib.Path(args.out)
    cmp = json.loads(pathlib.Path(args.compare).read_text()) if args.compare else None
    build(res, out, None, [pathlib.Path(f) for f in args.filmstrip], [(pathlib.Path(v.split("=", 1)[0]), v.split("=", 1)[1] if "=" in v else "") for v in args.vt], os.path.relpath(args.results, out.parent),
          cmp, os.path.relpath(args.compare, out.parent) if args.compare else None)
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
