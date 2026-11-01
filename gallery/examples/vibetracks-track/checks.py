"""Browser checks for the one-track dashboard (PEP 0004; cards PEP 0005): the rail's Track picker is the dashboard
variable, and the KPI tiles, the gauge, the 30-day tracker and the runs-per-week lines follow it (oracles from the JSON)."""

import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from dashboard_helpers import counts, ready, rows  # noqa: E402

sys.path.insert(0, str(HERE.parent / "vibetracks-dashboard"))
from vt_measure import FITS, GAUGE, LINES, TRACKER, looks, probe, sig3, weekly_oracle  # noqa: E402

RUNS = rows(HERE, "../vibetracks-dashboard/runs.json")
KPIS = rows(HERE, "../vibetracks-dashboard/kpis.json")
DAYS = rows(HERE, "../vibetracks-dashboard/days.json")
TONE = {"pass": "good", "fail": "bad", "mixed": "warn", "none": "muted"}


def follows(ctx, page, tid, name):
    """The stat cards and lines of one track, against the oracle: Σ passed / Σ checks of its runs, its 30 days' verdicts,
    its runs per ISO week."""
    runs = [r for r in RUNS if r["track"] == tid]
    ratio = sum(r["passed"] for r in runs) / sum(r["checks"] for r in runs)
    g = page.evaluate(GAUGE, "checks-passing")
    ctx.check(f"one track ({name}): the gauge is its runs' Σ passed / Σ checks ({ratio:.4f}) within 1 %, to 3 significant figures",
              g and not g.get("missing") and abs(g["frac"] - ratio) < 0.01 and g["value"] == sig3(ratio), {"got": g, "want": ratio})
    days = sorted((r for r in DAYS if r["track"] == tid), key=lambda r: r["day"])
    tr = page.evaluate(TRACKER, "last-30-days")
    tone_bg = {t: probe(page, t, "#example .dd-panel[data-panel='last-30-days'] .dv-view-tracker") for t in TONE.values()}
    wrong = [(r["day"], r["verdict"], b["bg"]) for x in tr for b, r in zip(x["blocks"], days) if b["bg"] != tone_bg[TONE[r["verdict"]]] or r["day"] not in b["title"]]
    ctx.check(f"one track ({name}): the 30-day tracker is its one row, 30 blocks in day order, each its verdict's tone",
              [x["label"] for x in tr] == [name] and len(tr[0]["blocks"]) == len(days) == 30 and not wrong, {"rows": [x["label"] for x in tr], "wrong": wrong[:3]})
    lw = page.evaluate(LINES, ["runs-per-week", "t", "kind"])
    got_w = {ln["series"]: dict(ln["points"]) for ln in (lw or {}).get("lines", [])}
    ctx.check(f"one track ({name}): runs per week is a line per kind (no bars), each point the oracle's ISO-week count",
              lw and lw["rects"] == 0 and got_w == weekly_oracle(runs, RUNS), {"drawn": got_w, "want": weekly_oracle(runs, RUNS)})


def run(ctx, path):
    page = ctx.page(path, width=1440, height=1000)
    ready(page)
    got = counts(page)
    labels = lambda tid: len({k["label"] for k in KPIS if k["track"] == tid})
    ctx.check("one track: opens on Vibe Tracks (the file's filters:): one track row, a card per KPI, its runs and points",
              got["the-track"] == 1 and got["kpis:cards"] == labels("vibetracks") and got["check-runs"] == sum(r["track"] == "vibetracks" for r in RUNS)
              and got["every-kpi-point"] == sum(k["track"] == "vibetracks" for k in KPIS), got)
    follows(ctx, page, "vibetracks", "Vibe Tracks")
    over = {k: f for k in ("kpi-history", "pass-rate-by-suite", "runs-per-week") for f in [page.evaluate(FITS, k)] if not f or f["drawn"] > f["canvas"] + 1 or f["right"] > f["tile"] + 1}
    ctx.check("one track: each chart's drawing fits its tile (KPI history's three columns of cells, each on its own y, included)", not over, over)
    page.select_option("data-facets[data-dataset=tracks] select", value="Five-Bar Arm Regression")
    page.wait_for_timeout(900)
    got = counts(page)
    ctx.check("one track: picking Five-Bar Arm Regression in the rail moves every panel to that track, and the URL says so",
              got["the-track"] == 1 and got["kpis:cards"] == labels("fivebar") and got["check-runs"] == sum(r["track"] == "fivebar" for r in RUNS)
              and "title=Five-Bar" in page.url, {"got": got, "url": page.url.split("/")[-1]})
    follows(ctx, page, "fivebar", "Five-Bar Arm Regression")
    page.context.close()
    looks(ctx, path, ready, "vibetracks-track")
