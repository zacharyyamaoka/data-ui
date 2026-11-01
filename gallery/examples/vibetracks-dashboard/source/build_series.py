"""Vibe Tracks' longer KPI histories and a per-day run roll-up, for the dashboard-cards time-series, tracker and bar-list cards.

Reads (read-only) the same owner bundle and producer folders as build.py:
  ~/.vibetracks/bundle/state.json, ~/.vibetracks/bundle/tracks/<id>.json   (which producer folders each track reads, and
                                                                          its KPI catalog: title, unit, direction)
  ~/vt/{zach,bam}/producers/<name>/{kpi_series.jsonl,runs_table.jsonl}
Writes, beside this folder: series.json and runs_daily.json (data-ui's runtime dataset shape, CONTRACT §3).

Run: python3 -I gallery/examples/vibetracks-dashboard/source/build_series.py

Public-safe rule (docs/SPEC.md §13): grasping's figures never enter the gallery: no series and no runs of it.
Every value is the producer's own point, never recomputed; runs_daily only counts runs and the producer's verdicts.
"""

import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "tools"))  # parents[3] is gallery/
from public_paths import public  # noqa: E402  (judge r2 #6: no absolute home path in what the site publishes)
import datetime
import json
import os
import pathlib
import zoneinfo

HERE = pathlib.Path(__file__).resolve().parents[1]
BUNDLE = pathlib.Path.home() / ".vibetracks" / "bundle"
ROOTS = [pathlib.Path("~/vt/zach"), pathlib.Path("~/vt/bam")]
PRIVATE = {"grasping"}
READ_ON = "2026-10-26"
END = datetime.date.fromisoformat(os.environ.get("END", READ_ON))  # the last day of the 30-day window
DAYS = 30
LOCAL = zoneinfo.ZoneInfo("America/Vancouver")  # WHY: a run at 20:00 Zach's time is that day's run, not tomorrow's UTC
MIN_POINTS = 20
# The series: (track, kpi). Whole-bench points only (no slice); each must have >= MIN_POINTS or the build stops.
SERIES = (
    ("ruckig", "wp_duration_ratio_geomean"),
    ("ruckig", "p2p_calc_time_ratio"),
    ("ruckig", "wp_calc_time_ratio"),
    ("ruckig", "wp_common_calc_time_ratio"),
    ("ruckig", "p2p_py_calc_time_ratio"),
    ("ruckig", "wp_py_calc_time_ratio"),
    ("vibetracks", "checks_passing"),
    ("vibetracks", "checks_with_purpose"),
)
BASIS = {"measured": "measured", "sealed": "measured", "estimate": "estimate", "stand-in": "stand-in", "claimed": "claimed"}


def jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def producer_dir(folder):
    for root in ROOTS:
        p = root / folder
        if p.is_dir():
            return p
    return None


def utc(text):
    """ISO 8601 text with any offset (or none: read as UTC) -> the same instant as ...Z, so the rows sort as text."""

    moment = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment.astimezone(datetime.timezone.utc)


def verdict(run):
    """The producer's own pass/fail for one run, or None when its runs carry none (timing and coverage benches)."""

    m, labels = run.get("metrics") or {}, run.get("labels") or {}
    if isinstance(labels.get("ok"), bool):                   # ruckig: labels.ok, its gate verdict
        return labels["ok"]
    if "checks" in m and "passed" in m and m.get("failed") is not None:   # vt spec runs (PEP 0012)
        return m["failed"] == 0
    if "checks_total" in m:                                   # fivebar's ladder
        return (m.get("checks_fail") or 0) + (m.get("checks_error") or 0) == 0
    if "runnable_goldens" in m and m.get("runnable_red") is not None:      # pyblocks' goldens
        return m["runnable_red"] == 0
    if "gates_pass" in m and m.get("gates_fail") is not None:              # tycoon-crm's parity gates
        return m["gates_fail"] == 0
    return None


def main():
    state = json.loads((BUNDLE / "state.json").read_text(encoding="utf-8"))
    generated = json.loads((BUNDLE / "bundle.json").read_text(encoding="utf-8"))["generated_at"]
    tracks = {t["id"]: t for t in state["tracks"]}
    details = {tid: json.loads((BUNDLE / "tracks" / f"{tid}.json").read_text(encoding="utf-8")) for tid in tracks}
    folders = {tid: [ref["folder"] for ref in (d.get("refs") or {}).get("kpi") or []] for tid, d in details.items()}

    # ---- series.json: whole-bench KPI points, every one the producer wrote
    series_rows = []
    for tid, kid in SERIES:
        assert tid not in PRIVATE, tid
        entry = next(k for k in details[tid].get("kpis") or [] if k["id"] == kid)
        pdir = producer_dir(entry["folder"])
        points = [p for p in jsonl(pdir / "kpi_series.jsonl")
                  if p.get("kpi") == kid and not p.get("slice") and isinstance(p.get("value"), (int, float)) and not isinstance(p.get("value"), bool)]
        assert len(points) >= MIN_POINTS, f"{tid}:{kid} has {len(points)} whole-bench points"
        points.sort(key=lambda p: utc(p["t"]))
        for i, p in enumerate(points):
            series_rows.append({
                "id": f"{tid}:{kid}:{i:03d}", "track": tid, "track_title": tracks[tid]["title"], "kpi": kid,
                "label": entry.get("title") or kid, "t": utc(p["t"]).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "value": p["value"] if isinstance(p["value"], int) else float(f"{p['value']:.5g}"),
                "unit": entry.get("unit") or None, "better": entry.get("direction"), "basis": BASIS.get(p.get("status")),
                "level": entry.get("level"), "n": p.get("n"), "sha": ((p.get("source") or {}).get("code_sha") or "")[:8] or None,
            })

    # ---- runs_daily.json: every run of every public track's producers, per local day, the last DAYS days
    days = [END - datetime.timedelta(days=k) for k in range(DAYS - 1, -1, -1)]
    daily_rows = []
    for tid in sorted(tracks, key=lambda x: (tracks[x].get("priority") or 99, x)):
        if tid in PRIVATE:
            continue
        counts = {day: [0, 0, 0] for day in days}  # runs, judged, passed
        producers = []
        for folder in folders[tid]:
            pdir = producer_dir(folder)
            if not pdir or not (pdir / "runs_table.jsonl").exists():
                continue
            producers.append(folder.split("/")[-1])
            for run in jsonl(pdir / "runs_table.jsonl"):
                if not run.get("t"):
                    continue
                day = utc(run["t"]).astimezone(LOCAL).date()
                if day not in counts:
                    continue
                ok = verdict(run)
                counts[day][0] += 1
                if ok is not None:
                    counts[day][1] += 1
                    counts[day][2] += bool(ok)
        if not any(c[0] for c in counts.values()):
            continue
        for day in days:
            runs, judged, passed = counts[day]
            if judged:
                rate = {"value": round(passed / judged, 4), "unit": "share", "basis": "derived", "n": judged,
                        "source": f"runs_table.jsonl of {', '.join(producers)} · passed runs / runs with a verdict"}
            else:
                rate = {"value": None, "why": "no runs that day" if not runs else "no pass/fail verdict in that day's runs"}
            daily_rows.append({"id": f"{tid}:{day.isoformat()}", "track": tid, "track_title": tracks[tid]["title"], "day": day.isoformat(),
                               "runs": runs, "judged_runs": judged, "passed_runs": passed, "pass_rate": rate, "producers": ", ".join(producers)})

    source = (f"Zach's Vibe Tracks owner bundle (~/.vibetracks/bundle, vt-state/1, generated {generated}) and its producer folders under "
              f"~/vt/{{zach,bam}}/producers, read {READ_ON}; grasping's figures left out (SPEC §13)")
    out = {
        "series.json": {
            "id": "vibetracks-series", "title": "Vibe Tracks KPI histories (real, every whole-bench point)", "titleProperty": "label", "source": source,
            "properties": {
                "track": {"type": "text", "hidden": True, "note": "Track id."},
                "track_title": {"type": "text", "display": "badge", "note": "The track, as vt state titles it."},
                "kpi": {"type": "text", "note": "KPI id in the producer's kpi_series.jsonl."},
                "label": {"type": "text", "note": "The catalog's title (the id when the catalog has none)."},
                "t": {"type": "date", "note": "When the producer wrote the point, as UTC (…Z): the producers mix offsets (Z, -07:00), so each is converted to the same instant in UTC."},
                "value": {"type": "number", "note": f"The producer's value, never recomputed; rounded to 5 significant digits for display. Whole-bench points only (no slice); every point of each series, {MIN_POINTS} or more each."},
                "unit": {"type": "text", "note": "The catalog's unit (× = a ratio against the reference implementation); null when the catalog gives none."},
                "better": {"type": "text", "note": "higher | lower: the catalog's direction."},
                "basis": {"type": "text", "display": "badge", "note": "The point's status in data-ui's words (measured, estimate, stand-in, claimed)."},
                "level": {"type": "number", "note": "Catalog level: 0 headline, 1 driver, 2 detail."},
                "n": {"type": "number", "note": "How many cases the producer's value is over (its own n)."},
                "sha": {"type": "text", "note": "Code commit the producer measured, first 8."},
            },
            "rows": series_rows,
        },
        "runs_daily.json": {
            "id": "vibetracks-runs-daily", "title": f"Vibe Tracks runs per track per day (real, {days[0]} to {days[-1]})", "titleProperty": "track_title", "source": source,
            "properties": {
                "track": {"type": "text", "hidden": True, "note": "Track id."},
                "track_title": {"type": "text", "display": "badge", "note": "The track, as vt state titles it."},
                "day": {"type": "date", "note": "The run's local date in Vancouver (America/Vancouver). Every day of the window is present, empty days with 0 runs."},
                "runs": {"type": "number", "note": "Runs in the track's producers' runs_table.jsonl that day: every run, benches included."},
                "judged_runs": {"type": "number", "note": "Of those, runs that carry a pass/fail verdict: ruckig labels.ok; spec runs failed == 0; fivebar checks_fail + checks_error == 0; pyblocks runnable_red == 0; tycoon-crm gates_fail == 0. Timing and coverage benches carry none."},
                "passed_runs": {"type": "number", "note": "Judged runs whose verdict is pass."},
                "pass_rate": {"type": "number", "display": "bar", "note": "passed_runs / judged_runs (derived, n = judged runs); null with the reason on a day with no verdict."},
                "producers": {"type": "text", "note": "The producer folders counted for the track."},
            },
            "rows": daily_rows,
        },
    }
    for name, doc in out.items():
        text = json.dumps(public(doc), ensure_ascii=False, separators=(",", ":"))
        (HERE / name).write_text(text + "\n", encoding="utf-8")
        ids = [r["id"] for r in doc["rows"]]
        assert len(set(ids)) == len(ids), name
        assert not any(r["track"] in PRIVATE for r in doc["rows"]), name
        print(f"{name}: {len(doc['rows'])} rows, {len(text) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
