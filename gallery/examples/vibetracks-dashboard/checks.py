"""Browser checks for the Vibe Tracks track-overview dashboard (PEP 0004), written before the element existed.

Every expected number is computed here from the case's JSON files (the oracle), never read from the page's model:
the rail filters every panel, a click on a chart bar cross-filters the others (not itself), a roll-up equals the
independently computed sum, the URL round-trips the whole state, the drill-down peek opens at the right edge, the
rail drags and remembers its width, and at 390 px the grid is one column with no sideways scroll, light and dark.

Round 2 (the Klipfolio-style rebuild, PEP 0005 cards): the KPI tiles across the top show each track's newest headline
point to 3 significant figures with the ▲▼ delta the oracle says; the gauge is Σ passed / Σ judged runs; the last-30-days
tracker colours every day by its verdict (days.json); the bar list ranks producer runs; runs per week and the KPI
histories are lines whose points are the oracle's; a click narrows the tracker and the gauge too; and the runs dataset
re-fetches every 5 s, updating in place without losing the selection, the table's scroll or the rail."""

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from vt_measure import FITS, GAUGE, LINES, TRACKER, cell, probe, sig3, weekly_oracle, when  # noqa: E402
D = "#example"
TRACKS = json.loads((HERE / "tracks.json").read_text(encoding="utf-8"))["rows"]
KPIS = json.loads((HERE / "kpis.json").read_text(encoding="utf-8"))["rows"]
RUNS = json.loads((HERE / "runs.json").read_text(encoding="utf-8"))["rows"]
SERIES = json.loads((HERE / "series.json").read_text(encoding="utf-8"))["rows"]
DAYS = json.loads((HERE / "days.json").read_text(encoding="utf-8"))["rows"]
TITLE = {t["id"]: t["title"] for t in TRACKS}


def ready(page):
    page.wait_for_selector(f"{D} .dd-panel data-views .dv-status", timeout=20000)
    page.wait_for_function("""() => { const els = [...document.querySelectorAll('#example .dd-panel data-views')];
      return els.length >= 4 && els.every((e) => e.dataset.view && /of/.test(e.querySelector('.dv-status').textContent)); }""", timeout=20000)
    page.wait_for_selector(f"{D} [data-panel=headlines] data-kpi", timeout=20000)
    page.wait_for_selector(f"{D} [data-panel=runs-by-track] .dv-view-chart[data-drawn]", timeout=20000)
    page.wait_for_timeout(300)


def counts(page):
    """Each panel's 'N of M' as drawn, and the number of KPI cards."""
    return page.evaluate("""() => { const out = {};
      for (const sec of document.querySelectorAll('#example .dd-panel[data-panel]')) {
        const s = sec.querySelector('data-views .dv-status'); if (!s) continue;
        const m = /([\\d,]+) of ([\\d,]+)/.exec(s.textContent); out[sec.dataset.panel] = m ? Number(m[1].replace(/,/g, '')) : null; }
      out.cards = document.querySelectorAll('#example [data-panel=headlines] data-kpi').length; return out; }""")


def headline_tracks(track_ids):
    return len({k["track_title"] for k in KPIS if k["level"] == 0 and k["track"] in track_ids})


def descendants(tid):
    out, todo = [], [tid]
    while todo:
        x = todo.pop()
        out.append(x)
        todo += [t["id"] for t in TRACKS if t["parent"] == x]
    return out


def rollup(tid):
    """The oracle: the newest run per (track, suite) over the track and every descendant; Σ passed, Σ checks."""
    newest = {}
    for r in RUNS:
        k = (r["track"], r["suite"])
        if k not in newest or (r["t"] or "") > (newest[k]["t"] or ""):
            newest[k] = r
    rows = [r for (t, _), r in newest.items() if t in descendants(tid)]
    return sum(r["passed"] for r in rows), sum(r["checks"] for r in rows), len(rows)


def bar_center(page, panel, field, value):
    """The page coordinates of a Vega bar's centre, from the chart's own scenegraph (its bounds, plus each enclosing
    group's offset, plus the view's origin and the canvas' place on the page)."""
    return page.evaluate("""([panel, field, value]) => {
      const el = document.querySelector(`#example [data-panel="${panel}"] .dv-view-chart`); const view = el.vegaView;
      const canvas = el.querySelector('canvas').getBoundingClientRect(); const origin = view.origin();
      let hit = null;
      const walk = (node, ox, oy) => { if (!node || hit) return;
        for (const item of node.items || []) {
          if (item.datum && item.datum[field] === value && item.bounds && item.mark && item.mark.marktype === 'rect') { hit = { item, ox, oy }; return; }
          if (item.items) walk(item, ox + (item.x || 0), oy + (item.y || 0));
        } };
      walk(view.scenegraph().root, 0, 0);
      if (!hit) return null;
      const b = hit.item.bounds;
      return { x: canvas.left + origin[0] + hit.ox + (b.x1 + b.x2) / 2, y: canvas.top + origin[1] + hit.oy + (b.y1 + b.y2) / 2 };
    }""", [panel, field, value])


# ------------------------------------------------------------------ round 2: the cards (oracles from the JSON files)

def headline_oracle():
    """Per track title with a level-0 KPI: its newest point, the one before it, and which way is better."""
    out = {}
    for k in sorted((k for k in KPIS if k["level"] == 0), key=lambda k: when(k["t"])):
        out.setdefault(k["track_title"], []).append(k)
    return {title: (cell(ks[-1]["value"]), cell(ks[-2]["value"]) if len(ks) > 1 else None, ks[-1]["better"]) for title, ks in out.items()}


def delta_oracle(value, prev, better):
    """The KPI card's compare: {against: previous, neutral: 0.005}: the arrow from the sign, the tone by which way is better."""
    if not isinstance(value, (int, float)) or not isinstance(prev, (int, float)):
        return None, None
    d = value - prev
    rel = abs(d) / abs(prev) if prev else (0 if d == 0 else float("inf"))
    tone = "neutral" if rel <= 0.005 or d == 0 else "good" if (d > 0) == (better != "lower") else "bad"
    return ("up" if d > 0 else "down" if d < 0 else "flat"), tone


def cards(ctx, page):
    """The Klipfolio-style rows: KPI tiles on top, then the gauge and tracker, the bar list, the lines."""
    check = ctx.check

    # ---- layout: the KPI tiles are the top row; the gauge sits beside the tracker
    tops = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#example .dd-panel[data-panel]:not(.dd-panel-text)')].map((e) => {
      const r = e.getBoundingClientRect(); return [e.dataset.panel, { top: Math.round(r.top + scrollY), left: Math.round(r.left), w: Math.round(r.width), h: Math.round(r.height) }]; }))""")
    others = [v["top"] for k, v in tops.items() if k != "headlines"]
    g, st = tops.get("judged-runs-passing"), tops.get("last-30-days")
    check("layout: the KPI tiles are the dashboard's first row of cards; the pass-rate gauge sits beside the 30-day tracker, the same height",
          "headlines" in tops and all(tops["headlines"]["top"] < t for t in others) and g and st and g["top"] == st["top"] and g["left"] < st["left"] and abs(g["h"] - st["h"]) <= 1,
          {k: tops.get(k) for k in ("headlines", "judged-runs-passing", "last-30-days")})

    # ---- KPI tiles: the newest level-0 point per track, 3 significant figures, the delta the oracle computes
    want = headline_oracle()
    tiles = page.evaluate("""() => [...document.querySelectorAll('#example [data-panel=headlines] data-kpi')].map((k) => {
      const d = k.querySelector('.dv-kpi-delta'), n = k.querySelector('.dv-kpi-num');
      return { label: k.querySelector('.dv-kpi-label').textContent.trim(), num: n ? n.textContent : null, exact: n ? (n.dataset.exact || n.textContent) : null,
        dir: d ? d.dataset.dir : null, tone: k.dataset.tone || null, spark: !!k.querySelector('svg path, svg polyline') }; })""")
    bad = []
    for t in tiles:
        w = want.get(t["label"])
        if not w:
            bad.append((t["label"], "no oracle"))
            continue
        value, prev, better = w
        if t["num"] != sig3(value) or abs(float(t["exact"].replace(",", "")) - value) > 1e-9 * max(1, abs(value)):
            bad.append((t["label"], t["num"], t["exact"], sig3(value)))
        d, tone = delta_oracle(value, prev, better)
        if d and (t["dir"] != d or (t["tone"] or "neutral") != tone):
            bad.append((t["label"], "delta", t["dir"], t["tone"], d, tone))
    check(f"KPI tiles: one per track with a headline ({len(want)}), each the newest level-0 point to 3 significant figures (compact), the stored value on hover, ▲▼ and tone as the oracle's previous-point delta",
          len(tiles) == len(want) and not bad, {"bad": bad[:4], "tiles": len(tiles), "want": len(want)})
    check("KPI tiles: every tile with history draws a sparkline", all(t["spark"] for t in tiles if len([k for k in KPIS if k["level"] == 0 and k["track_title"] == t["label"]]) > 1),
          [t["label"] for t in tiles if not t["spark"]])

    # ---- gauge: Σ passed_runs / Σ judged_runs over the 30 days, as an arc
    ratio = sum(r["passed_runs"] for r in DAYS) / sum(r["judged_runs"] for r in DAYS)
    gm = page.evaluate(GAUGE, "judged-runs-passing")
    check(f"gauge: the arc's fill is Σ passed runs / Σ judged runs over days.json ({ratio:.4f}) within 1 %, written to 3 significant figures",
          gm and not gm.get("missing") and gm["arc"] and abs(gm["frac"] - ratio) < 0.01 and gm["value"] == sig3(ratio), {"got": gm, "want": ratio})

    # ---- tracker: one row per track, one block per day, coloured by the verdict's tone
    by = {}
    for r in sorted(DAYS, key=lambda r: r["day"]):
        by.setdefault(r["track_title"], []).append(r)
    rows_ = page.evaluate(TRACKER, "last-30-days")
    scope = f"{D} .dd-panel[data-panel='last-30-days'] .dv-view-tracker"
    tone_bg = {t: probe(page, t, scope) for t in ("good", "bad", "warn", "muted")}
    tone_of = {"pass": "good", "fail": "bad", "mixed": "warn", "none": "muted"}
    wrong = [(x["label"], r["day"], r["verdict"], b["bg"]) for x in rows_ for b, r in zip(x["blocks"], by.get(x["label"], []))
             if b["bg"] != tone_bg[tone_of[r["verdict"]]] or r["day"] not in b["title"]]
    check(f"tracker: one row per public track ({len(by)}), 30 blocks each in day order, every block its verdict's tone (pass good, mixed warn, fail bad, none muted); the four tones differ",
          len(rows_) == len(by) and all(len(x["blocks"]) == len(by.get(x["label"], [])) == 30 for x in rows_) and not wrong and len(set(tone_bg.values())) == 4,
          {"rows": len(rows_), "wrong": wrong[:3], "tones": tone_bg})
    fit = page.evaluate("""() => { const v = document.querySelector("#example .dd-panel[data-panel='last-30-days'] .dv-view"); const t = v && v.querySelector('.dv-tracker');
      return v && t && { view: [v.scrollHeight, v.clientHeight], tracker: Math.round(t.getBoundingClientRect().height) }; }""")
    check("tracker: all 13 rows fit the tile (no scroll inside it)", fit and fit["view"][0] <= fit["view"][1] + 1, fit)
    check("tracker: grasping (private) has no row", not any("Grasping" in x["label"] for x in rows_), [x["label"] for x in rows_])

    # ---- bar list: producer runs per track, top 8, '+N more'
    tot = {}
    for r in DAYS:
        tot[r["track_title"]] = tot.get(r["track_title"], 0) + r["runs"]
    desc = sorted(tot.items(), key=lambda kv: -kv[1])
    bl = page.evaluate("""() => { const root = document.querySelector("#example .dd-panel[data-panel='producer-runs-per-track'] .dv-barlist"); if (!root) return null;
      return { rows: [...root.querySelectorAll('.dv-barlist-row')].map((r) => { const t = r.querySelector('.dv-barlist-track').getBoundingClientRect(), b = r.querySelector('.dv-barlist-bar').getBoundingClientRect();
        return [r.querySelector('.dv-barlist-label').textContent, r.querySelector('.dv-barlist-value').textContent, b.width / t.width]; }),
        more: (root.querySelector('.dv-barlist-more') || {}).textContent }; }""")
    vals = [v for _, v in desc[:8]]
    check(f"bar list: the top 8 tracks by Σ producer runs over the 30 days (oracle {vals}), bar = value / max within 1 %, '+{len(desc) - 8} more'",
          bl and [int(x[1].replace(",", "")) for x in bl["rows"]] == vals and all(abs(x[2] - v / vals[0]) < 0.01 for x, v in zip(bl["rows"], vals))
          and (bl["more"] or "").strip() == f"+{len(desc) - 8} more", bl)

    # ---- runs per week: a line per kind (no bars), every week's count, 0 in an empty week
    want_w = weekly_oracle(RUNS)
    lw = page.evaluate(LINES, ["runs-per-week", "t", "kind"])
    got_w = {ln["series"]: dict(ln["points"]) for ln in (lw or {}).get("lines", [])}
    check("runs per week: one line per run kind and no bars; each line's points (read back through Vega's y scale) are the oracle's ISO-week counts, 0 in an empty week",
          lw and lw["rects"] == 0 and got_w == want_w, {"drawn": got_w, "want": want_w, "bars": lw and lw["rects"]})

    # ---- KPI history: date-x lines from series.json, the right series, every point
    for key, keep in (("trajectory-generation-vs-pro", lambda r: r["track"] == "ruckig" and r["level"] <= 1),
                      ("checks-passing", lambda r: r["kpi"] == "checks_passing"),
                      ("tests-with-a-purpose", lambda r: r["kpi"] == "checks_with_purpose")):
        want_s = {}
        for r in SERIES:
            if keep(r):
                want_s[r["label"]] = want_s.get(r["label"], 0) + 1
        ls = page.evaluate(LINES, [key, "t", "series"])
        got_s = {ln["series"]: ln["n"] for ln in (ls or {}).get("lines", []) if ln["series"] in want_s}
        ph = page.evaluate(f"[...document.querySelectorAll(\"#example .dd-panel[data-panel='{key}'] [data-playhead]\")].filter((e) => !e.hidden && e.getBoundingClientRect().width > 0).length")
        check(f"KPI history '{key}': a line per KPI with every point of series.json ({want_s}), on a date axis with no playhead (no clock)",
              got_s == want_s and not ph, {"drawn": got_s, "playheads": ph})


    # ---- every chart's drawing (axes, legend) stays inside its tile: nothing clipped at the right edge
    over = {k: f for k in ("runs-per-week", "runs-by-track", "trajectory-generation-vs-pro", "checks-passing", "tests-with-a-purpose")
            for f in [page.evaluate(FITS, k)] if not f or f["drawn"] > f["canvas"] + 1 or f["right"] > f["tile"] + 1}
    check("charts: each Vega drawing (axes and legend included) fits its canvas, and the canvas its tile", not over, over)


def refresh(ctx, path):
    """datasets.runs.refresh: 5s: the runs file changes under a live page; within ~8 s the runs panels show the new row,
    while the selection (a chip), the runs table's scroll, the rail and the page scroll stay as the reader left them."""
    check = ctx.check
    real = (HERE / "runs.json").read_text(encoding="utf-8")
    data = json.loads(real)
    newest = sorted((r for r in RUNS if r["track"] == "vibetracks"), key=lambda r: when(r["t"]))[-1]
    # WHY clearly synthetic: test-only, never written to disk; the id and suite say so
    extra = {**newest, "id": "synthetic-refresh-check", "run": "synthetic-refresh-check (test only)", "suite": "synthetic (test only)",
             "t": "2026-10-26T23:59:00+00:00", "sha": None, "branch": None}
    plus = json.dumps({**data, "rows": data["rows"] + [extra]})
    armed = {"on": False, "served": []}

    def serve(route):
        body = plus if armed["on"] else real
        armed["served"].append(len(data["rows"]) + (1 if armed["on"] else 0))
        route.fulfill(status=200, content_type="application/json", body=body)

    page = ctx.page(path, width=1440, height=1000)
    page.add_init_script("""window.__refreshes = []; document.addEventListener('data-dashboard-refresh', (e) => window.__refreshes.push({ ...e.detail, at: performance.now() }), true);""")
    page.route(re.compile(r".*/vibetracks-dashboard/runs\.json(\?.*)?$"), serve)
    page.reload()
    ready(page)
    page.evaluate("document.querySelector('#example [data-panel=runs-by-track]').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(300)
    at = bar_center(page, "runs-by-track", "track_title", "Vibe Tracks")
    page.mouse.click(at["x"], at["y"])
    page.wait_for_timeout(700)
    vt = sum(r["track"] == "vibetracks" for r in RUNS)
    STATE = """() => { const sec = document.querySelector('#example [data-panel=runs]');
      const sc = [...sec.querySelectorAll('*')].find((e) => e.scrollHeight > e.clientHeight + 40 && /(auto|scroll)/.test(getComputedStyle(e).overflowY));
      const rail = document.querySelector('#example .dd-rail').getBoundingClientRect();
      return { scroller: sc ? sc.className : null, scrollTop: sc ? Math.round(sc.scrollTop) : null, chip: document.querySelector('#example .dd-chips').innerText.trim(),
        rail: [Math.round(rail.left), Math.round(rail.width)], railTicks: document.querySelectorAll('#example .dd-rail input:checked').length,
        pageY: Math.round(scrollY), url: location.search + location.hash }; }"""
    page.evaluate("""() => { const sec = document.querySelector('#example [data-panel=runs]'); sec.scrollIntoView({block: 'start'});
      const sc = [...sec.querySelectorAll('*')].find((e) => e.scrollHeight > e.clientHeight + 40 && /(auto|scroll)/.test(getComputedStyle(e).overflowY)); if (sc) sc.scrollTop = 160; }""")
    page.wait_for_timeout(300)
    before = page.evaluate(STATE)
    rows_before = counts(page)["runs"]
    pre = page.evaluate("window.__refreshes.length")
    armed["on"] = True
    t0 = page.evaluate("performance.now()")
    shown = ctx.until(page, f"() => {{ const s = document.querySelector('#example [data-panel=runs] data-views .dv-status'); return s && /\\b{vt + 1} of/.test(s.textContent); }}", timeout=8500)
    took = (page.evaluate("performance.now()") - t0) / 1000
    page.wait_for_timeout(300)
    after = page.evaluate(STATE)
    got = counts(page)
    events = page.evaluate("(t0) => window.__refreshes.filter((e) => e.at >= t0)", t0)
    check(f"live data: with Vibe Tracks selected, the runs file gains one (synthetic, test-only) row and within 8 s the runs panels show it without a reload ({rows_before} -> {vt + 1}; the bar chart, which does not filter itself, {len(RUNS)} -> {len(RUNS) + 1})",
          shown and rows_before == vt and got["runs"] == vt + 1 and got["runs-by-track"] == len(RUNS) + 1, {"seconds": round(took, 2), "before": rows_before, "after": got})
    check("live data: the refresh keeps the selection chip, the runs table's scroll position, the rail and the page scroll exactly as they were",
          before["scroller"] and before["scrollTop"] > 0 and before == after and "Vibe Tracks" in after["chip"], {"before": before, "after": after})
    page.wait_for_timeout(5600)  # one more poll: the same text again must not re-render
    events = page.evaluate("(t0) => window.__refreshes.filter((e) => e.at >= t0)", t0)
    check("live data: data-dashboard-refresh fired once for the change (dataset runs, N+1 rows), and a poll returning the same file fires nothing",
          len(events) == 1 and events[0]["dataset"] == "runs" and events[0]["rows"] == len(RUNS) + 1,
          {"events after the change": events, "events before it (first poll)": pre, "served": armed["served"]})
    page.context.close()


def run(ctx, path):
    check = ctx.check
    page = ctx.page(path, width=1440, height=1000)
    ready(page)
    got = counts(page)
    all_ids = {t["id"] for t in TRACKS}
    want = {"headlines": None, "tracks": len(TRACKS), "runs-by-track": len(RUNS), "runs": len(RUNS), "cards": headline_tracks(all_ids)}
    check("dashboard: one .base file draws five panels over three linked datasets (18 tracks, 86 runs, a KPI card per track with a headline)",
          got["tracks"] == want["tracks"] and got["runs-by-track"] == want["runs-by-track"] and got["runs"] == want["runs"] and got["cards"] == want["cards"],
          {"got": got, "want": want})
    cards(ctx, page)

    # ---- numbers: the .base declares 3 significant figures (format: {digits: 3}); no card shows float noise such as
    # 0.9964028776978417, and the stored value is one hover away (Zach, 2026-10-26: "round the numbers")
    nums = page.evaluate("""() => [...document.querySelectorAll('#example [data-panel=headlines] .dv-kpi-num')].map((e) => [e.textContent, e.dataset.exact || null])""")
    sig = lambda t: len(re.sub(r"^0+", "", re.sub(r"[^0-9]", "", t.split("e")[0])).rstrip("0") or "0")
    noisy = [t for t, _ in nums if "." in t and sig(t) > 3 and not re.search(r"[KMB]$", t)]
    stored = [x for t, x in nums if x and x != t]
    check("numbers: every headline KPI is written to 3 significant figures, with the stored value on hover (no float noise)",
          nums and not noisy and stored and any(len(x) > 8 for x in stored), {"noisy": noisy[:4], "rounded (shown, stored)": [(t, x) for t, x in nums if x][:4]})

    # ---- the rail: one tick on the tracks dataset filters every panel, through the links
    page.check("data-facets[data-dataset=tracks] input[data-p=health][data-value=green]")
    page.wait_for_timeout(700)
    green = {t["id"] for t in TRACKS if t["health"] == "green"}
    got = counts(page)
    want = {"tracks": len(green), "runs": sum(r["track"] in green for r in RUNS), "runs-by-track": sum(r["track"] in green for r in RUNS), "cards": headline_tracks(green)}
    check("dashboard rail: health = green filters every panel (tracks directly; runs and KPI cards through their links)",
          all(got[k] == v for k, v in want.items()), {"got": got, "want": want})
    page.click("data-facets[data-dataset=tracks] [data-clear]")
    page.wait_for_timeout(500)

    # ---- the second rail: run kind lives on the runs dataset and narrows the tracks through the same link
    page.check("data-facets[data-dataset=runs] input[data-p=kind][data-value=tests]")
    page.wait_for_timeout(700)
    tested = {r["track"] for r in RUNS if r["kind"] == "tests"}
    got = counts(page)
    check("dashboard rail: kind = tests on the runs rail narrows the runs and, through the link, the tracks and KPI cards",
          got["runs"] == sum(r["kind"] == "tests" for r in RUNS) and got["tracks"] == len(tested) and got["cards"] == headline_tracks(tested),
          {"got": got, "tracks with tests": sorted(tested)})
    page.click("data-facets[data-dataset=runs] [data-clear]")
    page.wait_for_timeout(500)

    # ---- cross-filter: a real mouse click on the bar of Vibe Tracks in the chart
    page.evaluate("document.querySelector('#example [data-panel=runs-by-track]').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(400)
    at = bar_center(page, "runs-by-track", "track_title", "Vibe Tracks")
    check("dashboard cross-filter: the chart has a bar for Vibe Tracks (found in Vega's scenegraph)", at is not None, at)
    if at:
        page.mouse.click(at["x"], at["y"])
        page.wait_for_timeout(700)
        got = counts(page)
        vt = {"vibetracks"}
        want = {"runs-by-track": len(RUNS), "runs": sum(r["track"] == "vibetracks" for r in RUNS), "tracks": 1, "cards": headline_tracks(vt)}
        chip = page.inner_text(f"{D} .dd-chips")
        check("dashboard cross-filter: clicking the bar narrows every other panel to Vibe Tracks; the chart itself keeps all 86 runs (it does not filter itself)",
              all(got[k] == v for k, v in want.items()) and "Vibe Tracks" in chip, {"got": got, "want": want, "chip": chip})
        vt_days = [r for r in DAYS if r["track"] == "vibetracks"]
        vt_ratio = sum(r["passed_runs"] for r in vt_days) / sum(r["judged_runs"] for r in vt_days)
        trk, gm = page.evaluate(TRACKER, "last-30-days"), page.evaluate(GAUGE, "judged-runs-passing")
        check(f"dashboard cross-filter: the same click narrows the 30-day tracker to Vibe Tracks' row and the gauge to its judged runs ({vt_ratio:.4f}), through the days→tracks link",
              [x["label"] for x in trk] == ["Vibe Tracks"] and gm and abs(gm["frac"] - vt_ratio) < 0.01 and gm["value"] == sig3(vt_ratio), {"tracker": [x["label"] for x in trk], "gauge": gm})
        url = page.url
        # ---- the URL holds the whole state: a new page on the same URL draws the same counts
        page.check("data-facets[data-dataset=runs] input[data-p=kind][data-value=tests]")
        page.wait_for_timeout(700)
        before = counts(page)
        url = page.url
        p2 = ctx.page(url.replace(ctx.base + "/", ""), width=1440, height=1000)
        ready(p2)
        after = counts(p2)
        chip2 = p2.inner_text(f"{D} .dd-chips")
        check("dashboard URL: a reload of the link restores the rail tick and the chart selection (every panel's count the same)",
              before == after and "Vibe Tracks" in chip2 and "runs.kind=tests" in url and "s.runs-by-track=" in url, {"url": url.split("/")[-1], "before": before, "after": after})
        p2.context.close()
        page.click(f"{D} .dd-chip")
        page.wait_for_timeout(500)
        page.click("data-facets[data-dataset=runs] [data-clear]")
        page.wait_for_timeout(500)
        check("dashboard cross-filter: the chip clears the selection", counts(page)["runs"] == len(RUNS) and not page.inner_text(f"{D} .dd-chips").strip().startswith("Track"), counts(page))

    # ---- a roll-up equals the value computed here, and its cell says it is derived
    passed, total, n = rollup("bam-robotics")
    cell = page.evaluate("""() => { const sec = document.querySelector('#example [data-panel=tracks]');
      const row = [...sec.querySelectorAll('tr.dv-row')].find((tr) => tr.textContent.includes('BAM Robotics'));
      const td = (c) => row && row.querySelector(`td[data-col="${c}"]`);
      // the hover sits on the cell's .dv-value, or (models-views' aligned cells, CONTRACT §16) on the <td> itself
      const hover = (c) => { const v = td(c) && td(c).querySelector('.dv-value'); return v ? v.title : (td(c) ? td(c).title : ''); };
      return row && { passed: td('checks_passed').textContent, checks: td('checks_run').textContent, rate: td('pass_rate').textContent, title: hover('checks_passed') }; }""")
    num = lambda s: float(re.sub(r"[^\d.]", "", s or "") or "nan")
    check(f"dashboard roll-up: BAM Robotics' Passing = Σ passed of the newest run per suite of its child tracks ({passed} of {total}, {n} runs), computed independently",
          cell and num(cell["passed"]) == passed and num(cell["checks"]) == total and abs(num(cell["rate"]) - round(passed / total, 4)) < 1e-3, cell)
    check("dashboard roll-up: the cell is marked derived and says how it was made",
          cell and ("~" in cell["passed"] or "derived" in (cell["title"] or "").lower()) and "child" in (cell["title"] or ""), cell and cell["title"])

    # ---- drill: a click on a run opens the dashboard's one side peek at the right edge
    page.click(f"{D} [data-panel=runs] tr.dv-row >> nth=0")
    page.wait_for_selector(f"{D} .dd-drill .dv-peek:not([hidden])", timeout=8000)
    peek = page.evaluate("""() => { const p = document.querySelector('#example .dd-drill .dv-peek'); const r = p.getBoundingClientRect();
      return { right: Math.round(r.right), width: Math.round(r.width), top: Math.round(r.top), title: p.querySelector('h2').textContent, vw: innerWidth }; }""")
    newest = sorted(RUNS, key=lambda r: r["t"] or "", reverse=True)[0]
    check("dashboard drill: clicking the newest run opens one side peek, full height at the right edge, titled with that run",
          peek["right"] == peek["vw"] and peek["top"] == 0 and peek["width"] >= 320 and peek["title"] == newest["run"], peek)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # ---- the rail is a resizable side panel (measured), remembered after a reload
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(200)
    h = page.evaluate("() => { const r = document.querySelector('#example .dd-rail').getBoundingClientRect(); const s = [...document.querySelectorAll('#example .dv-splitter')].find((x) => !x.hidden && Math.abs(x.getBoundingClientRect().left + 4 - r.right) < 8); const b = s && s.getBoundingClientRect(); return { w: r.width, x: b && b.left + 4, y: b && b.top + b.height / 2 }; }")
    if h["x"]:
        page.mouse.move(h["x"], h["y"])
        page.mouse.down()
        page.mouse.move(h["x"] + 80, h["y"], steps=6)
        page.mouse.up()
        page.wait_for_timeout(300)
    w2 = page.evaluate("document.querySelector('#example .dd-rail').getBoundingClientRect().width")
    page.reload()
    ready(page)
    w3 = page.evaluate("document.querySelector('#example .dd-rail').getBoundingClientRect().width")
    check("dashboard rail: dragging its edge 80 px widens it by 80 px, and the width survives a reload",
          h["x"] is not None and abs(w2 - h["w"] - 80) <= 2 and abs(w3 - w2) <= 1, {"before": h["w"], "dragged": w2, "reloaded": w3})
    page.evaluate("localStorage.clear()")
    page.context.close()

    refresh(ctx, path)

    # ---- light and dark, desktop and phone
    for dark in (False, True):
        for width, mobile in ((1440, False), (390, True)):
            p = ctx.page(path, width=width, height=1000 if width > 400 else 844, dark=dark, mobile=mobile)
            ready(p)
            m = p.evaluate("""() => { const g = document.querySelector('#example .dd-grid').getBoundingClientRect();
              const ps = [...document.querySelectorAll('#example .dd-panel')].map((e) => e.getBoundingClientRect());
              const tile = document.querySelector('#example .dd-panel:not(.dd-panel-text)'), p = document.createElement('i');
              p.style.cssText = 'position:absolute;width:1px;height:1px;background:var(--dv-bg)'; tile.append(p); const token = getComputedStyle(p).backgroundColor; p.remove();
              return { scroll: document.scrollingElement.scrollWidth, grid: Math.round(g.width), widths: ps.map((r) => Math.round(r.width)),
                       tile: getComputedStyle(tile).backgroundColor, token }; }""")
            tag = f"{'dark' if dark else 'light'}, {width} px"
            if width == 390:
                check(f"dashboard {tag}: one column (every panel as wide as the grid) and no sideways page scroll",
                      m["scroll"] <= 390 and all(abs(w - m["grid"]) <= 1 for w in m["widths"]), m)
            else:
                check(f"dashboard {tag}: panels sit side by side (Tracks 7/12 beside Runs by track 5/12)",
                      len(set(m["widths"])) > 1 and m["scroll"] <= width, m["widths"])
            # WHY the tile, not <data-views>: inside a dashboard tile the view is transparent by design (PEP 0005 §5); the
            # tile is the surface. Light: the tile is the surface token itself; dark: the dashboard lifts it 5 % toward the ink.
            want_bg = "rgb(26, 26, 26)" if dark else "rgb(255, 255, 255)"
            ch = [float(x) for x in re.findall(r"[\d.]+", m["tile"].replace("srgb", ""))[:3]]
            lum = (sum(ch) / 3 if "color(" in m["tile"] else sum(ch) / (3 * 255)) if len(ch) == 3 else None
            check(f"dashboard {tag}: the tiles are made from Vibe Tracks' surface token ({want_bg}) and follow the theme",
                  m["token"] == want_bg and lum is not None and (lum < 0.3) == dark and (dark or m["tile"] == want_bg), {"tile": m["tile"], "token": m["token"]})
            p.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + window.scrollY - 70)")
            p.wait_for_timeout(200)
            ctx.shot(p, f"vibetracks-dashboard-{'dark' if dark else 'light'}-{width}")
            p.context.close()
