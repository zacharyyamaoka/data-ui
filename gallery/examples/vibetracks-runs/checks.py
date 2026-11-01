"""Browser checks for the Vibe Tracks run explorer dashboard (PEP 0004; cards PEP 0005). Oracles from the JSON files:
the ratio-of-sums cards and gauge, the runs-per-week lines, the bar list, a leader click narrowing them, and every chart
drawn inside its tile."""

import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from dashboard_helpers import D, card, counts, num, ready, rows  # noqa: E402

sys.path.insert(0, str(HERE.parent / "vibetracks-dashboard"))
from vt_measure import FITS, GAUGE, LINES, looks, sig3, weekly_oracle  # noqa: E402

RUNS = rows(HERE, "../vibetracks-dashboard/runs.json")
TRACKS = rows(HERE, "../vibetracks-dashboard/tracks.json")


def subtree(tid):
    out, todo = [], [tid]
    while todo:
        x = todo.pop()
        out.append(x)
        todo += [t["id"] for t in TRACKS if t["parent"] == x]
    return out


def run(ctx, path):
    page = ctx.page(path, width=1440, height=1000)
    ready(page)
    got = counts(page)
    leaders = sum(any(r["track"] in subtree(t["id"]) for r in RUNS) for t in TRACKS)
    ctx.check("run explorer: every panel over the 86 runs; the leaderboard lists the tracks whose tree has runs",
              got["every-run-over-time"] == len(RUNS) and got["the-runs"] == len(RUNS) and got["leaderboard"] == leaders and got["pass-rate-by-kind:cards"] == 4, got)
    tests = [r for r in RUNS if r["kind"] == "tests"]
    want = sum(r["passed"] for r in tests) / sum(r["checks"] for r in tests)
    shown = num(card(page, "pass-rate-by-kind", "tests").locator(".dv-kpi-num").inner_text())
    ctx.check(f"run explorer: the tests card is Σ passed / Σ checks over the test runs ({want:.4f}), not a mean of per-run rates",
              shown is not None and abs(shown - want) < 5e-4, {"shown": shown, "want": want, "mean of rates": sum(r["passed"] / r["checks"] for r in tests) / len(tests)})
    # ---- the gauge: Σ passed / Σ checks over every run, as a bar; runs per week as lines; the bar list of runs per track
    ratio = sum(r["passed"] for r in RUNS) / sum(r["checks"] for r in RUNS)
    g = page.evaluate(GAUGE, "checks-passing")
    ctx.check(f"run explorer gauge: the bar's fill is Σ passed / Σ checks over all {len(RUNS)} runs ({ratio:.4f}) within 1 %, written to 3 significant figures",
              g and not g.get("missing") and not g["arc"] and abs(g["frac"] - ratio) < 0.01 and g["value"] == sig3(ratio), {"got": g, "want": ratio})
    lw = page.evaluate(LINES, ["runs-per-week", "t", "kind"])
    got_w = {ln["series"]: dict(ln["points"]) for ln in (lw or {}).get("lines", [])}
    want_w = weekly_oracle(RUNS)
    ctx.check("run explorer runs per week: a line per kind (no bars), each point the oracle's ISO-week count, 0 in an empty week",
              lw and lw["rects"] == 0 and got_w == want_w, {"drawn": got_w, "want": want_w})
    per = {}
    for r in RUNS:
        per[r["track_title"]] = per.get(r["track_title"], 0) + 1
    desc = sorted(per.values(), reverse=True)
    bl = page.evaluate("""() => { const root = document.querySelector("#example .dd-panel[data-panel='check-runs-per-track'] .dv-barlist"); if (!root) return null;
      return { values: [...root.querySelectorAll('.dv-barlist-value')].map((e) => e.textContent.trim()), more: (root.querySelector('.dv-barlist-more') || {}).textContent }; }""")
    ctx.check(f"run explorer bar list: the top 6 tracks by number of check runs ({desc[:6]}), '+{len(desc) - 6} more'",
              bl and [int(v) for v in bl["values"]] == desc[:6] and (bl["more"] or "").strip() == f"+{len(desc) - 6} more", bl)
    over = {k: f for k in ("every-run-over-time", "runs-per-week") for f in [page.evaluate(FITS, k)] if not f or f["drawn"] > f["canvas"] + 1 or f["right"] > f["tile"] + 1}
    ctx.check("run explorer: each chart's drawing (its track legend included) fits its canvas, and the canvas its tile", not over, over)

    page.click(f"{D} [data-panel=leaderboard] tr.dv-row:has-text('Vibe Tracks')")
    page.wait_for_timeout(700)
    got = counts(page)
    vt = sum(r["track"] == "vibetracks" for r in RUNS)
    ctx.check("run explorer: clicking a leader narrows the chart, the cards and the runs to that track; the leaderboard keeps every leader",
              got["every-run-over-time"] == vt and got["the-runs"] == vt and got["leaderboard"] == leaders, got)
    vts = [r for r in RUNS if r["track"] == "vibetracks"]
    vr = sum(r["passed"] for r in vts) / sum(r["checks"] for r in vts)
    g = page.evaluate(GAUGE, "checks-passing")
    lw = page.evaluate(LINES, ["runs-per-week", "t", "kind"])
    got_w = {ln["series"]: dict(ln["points"]) for ln in (lw or {}).get("lines", [])}
    ctx.check(f"run explorer: the same click narrows the gauge to Vibe Tracks' Σ passed / Σ checks ({vr:.4f}) and the weekly lines to its runs",
              g and abs(g["frac"] - vr) < 0.01 and g["value"] == sig3(vr) and got_w == weekly_oracle(vts, RUNS), {"gauge": g, "lines": got_w})
    page.click(f"{D} .dd-chip")
    page.wait_for_timeout(500)
    page.check("data-facets[data-dataset=runs] input[data-p=kind][data-value=gates]")
    page.wait_for_timeout(700)
    got = counts(page)
    gates = {r["track"] for r in RUNS if r["kind"] == "gates"}
    # PEP 0004 §5.2: a link filters on its own column, so a parent with no gate runs of its own drops out
    lead = len(gates)
    ctx.check("run explorer rail: kind = gates narrows the runs, and the leaderboard to the tracks that ran gates (a link filters on its column, not up the tree)",
              got["the-runs"] == sum(r["kind"] == "gates" for r in RUNS) and got["leaderboard"] == lead, {"got": got, "leaders": lead})
    page.context.close()
    looks(ctx, path, ready, "vibetracks-runs")
