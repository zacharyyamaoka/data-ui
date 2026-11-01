"""Publish a bench result to a Vibe Tracks producer folder (vt-kpi/1, PEP 0005): runs in, KPIs out.

    python3 bench/publish.py [RESULTS.json] --to ~/vt/zach/producers/data-ui

RESULTS defaults to bench/.out/latest.json. It writes, in the producer folder (the only place it writes):
  kpi_catalog.json     bench/kpi_catalog.json, stamped generated_at (the KPI definitions; bench/KPIS.md says why)
  kpi_series.jsonl     appended: each KPI's whole-bench point (the headline scenario) and its slices (every scenario,
                       interaction kind, row count), labelled with the machine's trust (noisy points draw hollow), and
                       the three gates, no_page_errors, stable_samples and timing_valid
  runs_table.jsonl     appended: one vt-run/1 per scenario, additive metrics only (counts and sums)
  items/<run_id>.jsonl every load and interaction sample of that run
  kpi_diagnostics.jsonl appended: the timing points of a scenario whose machine was noisy (not read by Vibe Tracks)
A result already published (its run ids are in runs_table.jsonl) is skipped, so publishing twice changes nothing.

Two verdicts per scenario (bench/trust.py), and they are handled differently:
- machine noisy (the calibration was slow, or the CPUs loaded): its TIMING points are kept out of kpi_series.jsonl
  and written to kpi_diagnostics.jsonl; --include-noisy publishes them as KPI points (drawn hollow). Points a busy CPU
  cannot move (cpu_sensitive false in kpi_catalog.json: load_kb, heap_mb, dom_added) are published either way, labelled
  trust quiet and machine noisy. WHY: Vibe Tracks' headline is the newest point whatever its trust, so one run on a
  loaded machine (2,847 ms against quiet runs of 127-203 ms, 2026-10-27) became the track's headline.
- app unstable (its own cold first paints spread, cv over 0.5, on a quiet machine): a result, never noise. Its points
  are published as measured (labels.stability unstable), and the stable_samples gate fails for it. WHY: Codex's
  finding 6 (2026-10-27): cold samples of 100, 100, 100, 100 and 1,000 ms were filed as noise, so the real 1,000 ms p95
  went to the diagnostics and the old headline stayed. Under interference stability is pending (pass null), never
  stable: an additive slowdown lowers a CV.
- timings suppressed (either of the above routed a scenario's timing set away, or --include-noisy published it
  hollow): the timing_valid gate fails for that scenario and for the whole bench, with the code_sha and the reason.
  WHY (judge r2, finding 3): Vibe Tracks' headline skips null points, so a suppressed run left the previous build's
  fast number as the last word while every other gate passed; a failing gate is also the next leg in `vt brief`.
The gates are published either way: a page that throws is a fact on any machine. `--move-noisy` moves the noisy
timing points already in kpi_series.jsonl to kpi_diagnostics.jsonl (the producer's own files; Vibe Tracks is never
edited by hand):

    python3 bench/publish.py --to ~/vt/zach/producers/data-ui --move-noisy
Missing is null with a reason (a scenario that failed to draw), never 0. Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import sys

BENCH = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))
import trust as trustlib  # noqa: E402  (bench/trust.py: the machine and stability verdicts, shared with runner.py)

CATALOG = json.loads((BENCH / "kpi_catalog.json").read_text())
HEAD = CATALOG["headline_scenario"]
LANE = "chromium-desktop"


def pct(values, p):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    return v[max(1, math.ceil(p / 100 * len(v))) - 1]


def rnd(x, d=1):
    return None if x is None else round(x, d)


def failed_because(s):
    """Why a scenario's numbers must not be published as passing, or [] (bench/runner.py's health guard). Results made
    before the guard existed are judged by what they recorded: a page error or a load with no first paint."""
    why = list(s.get("failed_because") or [])
    if s.get("verdict") == "FAILED" and not why:
        why = ["marked FAILED by the runner"]
    if not why:
        why = [f"page error: {x[:160]}" for x in (s.get("errors") or [])[:2]]
        if s["load"]["cold"].get("failed"):
            why.append("a cold load drew nothing")
    return why


def classify(s):
    """(machine verdict, stability, {timing set: why it was suppressed}) of one scenario.

    The suppressed sets come from trust.timing (runner.py since judge r2); a result without it suppressed every set
    when its machine was noisy. Results written before the trust split (no "stability" key) carried the app's spread
    as one of trust.why's reasons, so their machine is re-judged from what they recorded. Stability is always
    re-judged from the samples under the current rule (bench/trust.py), never read from the record: a result written
    while the rule was wrong (a low CV on a noisy machine read stable) must not keep its old verdict."""
    trust = s["trust"]
    machine = trust["verdict"] if "stability" in s else trustlib.legacy_machine(trust)["verdict"]
    if isinstance(trust.get("timing"), dict):
        suppressed = {k: v.get("why") or "suppressed" for k, v in trust["timing"].items() if not v.get("valid")}
    else:
        present = [k for k, n in (("cold", s["samples"]["cold"]), ("warm", s["samples"]["warm"]),
                                  ("interactions", s["samples"]["interactions"]), ("scroll", s.get("scroll"))) if n]
        why = "; ".join(trust.get("why") or []) or "the machine was noisy"
        suppressed = {k: why for k in present} if machine == "noisy" else {}
    cold = [x.get("first_useful_paint") for x in s["samples"]["cold"] if x.get("clean", True) or "cold" in suppressed]
    st = trustlib.stability(cold, "noisy" if "cold" in suppressed else "quiet")
    return machine, st, suppressed


def trust_labels(kpi, s):
    """The labels that say how far a point can be trusted. trust is per point: noisy only when the timing set the KPI is
    computed from was suppressed (a KPI the catalog marks cpu_sensitive with no known set: when any set was), so a
    byte count from a loaded machine draws filled. machine is the scenario's own."""
    machine, st, suppressed = classify(s)
    sensitive = trustlib.cpu_sensitive(kpi, CATALOG)
    which = trustlib.TIMING_SETS.get(kpi)
    hit = (which in suppressed) if which else bool(suppressed)
    labels = {"trust": "noisy" if sensitive and hit else "quiet", "machine": machine}
    if sensitive:
        labels["stability"] = st["verdict"]
        if st["verdict"] == "unstable":
            labels["stability_why"] = st["why"][:200]
    return labels


def renderer_labels(s):
    """{renderer, renderer_string} for a scenario that draws with WebGL (the map), else {}. WHY: headless Chromium's
    default WebGL is SwiftShader, a CPU rasteriser; a map point must say which it was, so a software number is never
    read as a GPU one. Results from before the runner recorded it ran on the default browser, so they were software."""
    r = s.get("renderer")
    if r is None:
        if s.get("view") != "map":
            return {}
        return {"renderer": "software", "renderer_string": "not recorded (before 2026-10-26 the bench ran WebGL on SwiftShader)"}
    if not r.get("webgl"):
        return {}
    return {"renderer": r.get("kind") or "none", "renderer_string": (r.get("string") or "")[:160]}


def interactions(s):
    """(the interactions the timing KPIs are over, every measured interaction). The first are the clean ones
    (runner.py judged each against the pressure timeline) while the interaction set is valid; when it was suppressed,
    all of them, since its points go to the diagnostics, which should show what was measured. WHY (judge r2, finding
    4): an interaction that overlapped a burst on the assigned CPUs is the machine's number, not data-ui's."""
    every = [x for x in s["samples"]["interactions"] if x.get("ms") is not None]
    if "interactions" in classify(s)[2]:
        return every, every
    return [x for x in every if x.get("clean", True)], every


def scenario_points(s):
    """{kpi id: (value, n, extra labels)} for one scenario target: what each KPI means on that scenario alone."""
    cold, warm = s["load"]["cold"], s["load"]["warm"]
    inter, every = interactions(s)
    out = {
        "first_paint_ms": (cold["first_useful_paint"]["p95"], cold["first_useful_paint"]["n"]),
        "first_paint_warm_ms": (warm["first_useful_paint"]["p95"], warm["first_useful_paint"]["n"]),
        "interactive_ms": (cold["tti"]["p95"], cold["tti"]["n"]),
        "blocking_ms": (cold["tbt"]["p95"], cold["tbt"]["n"]),
        "load_kb": (rnd(cold["bytes_gzip"]["p50"] / 1024 if cold["bytes_gzip"]["p50"] is not None else None), cold["bytes_gzip"]["n"]),
        "heap_mb": (cold["heap_mb"]["p50"], cold["heap_mb"]["n"]),
        "interaction_ms": (rnd(pct([x["ms"] for x in inter], 95)), len(inter)),
        "model_ms": (rnd(pct([x.get("model_ms") for x in inter], 95)), len(inter)),
        "render_ms": (rnd(pct([x.get("render_ms") for x in inter], 95)), len(inter)),
        "rail_ms": (rnd(pct([x.get("rail_ms") for x in inter], 95)), len(inter)),
        "dom_added": (pct([x.get("dom_added") for x in every], 50), len(every)),
    }
    if s.get("scroll"):
        out["scroll_frame_ms"] = (s["scroll"]["p95"], s["scroll"]["n"])
    return out


def kind_points(s):
    inter, every = interactions(s)
    kinds = sorted({x["kind"] for x in every})
    for k in kinds:
        xs = [x for x in inter if x["kind"] == k]
        all_k = [x for x in every if x["kind"] == k]
        yield k, {"interaction_ms": (rnd(pct([x["ms"] for x in xs], 95)), len(xs)),
                  "model_ms": (rnd(pct([x.get("model_ms") for x in xs], 95)), len(xs)),
                  "render_ms": (rnd(pct([x.get("render_ms") for x in xs], 95)), len(xs)),
                  "rail_ms": (rnd(pct([x.get("rail_ms") for x in xs], 95)), len(xs)),
                  "dom_added": (pct([x.get("dom_added") for x in all_k], 50), len(all_k))}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="?", default=str(BENCH / ".out" / "latest.json"))
    ap.add_argument("--to", required=True, help="the producer folder, e.g. ~/vt/zach/producers/data-ui")
    ap.add_argument("--sha", default=None, help="the data-ui commit the run measured, when it differs from the results' (a lane commit carrying only the bench)")
    ap.add_argument("--include-noisy", action="store_true", help="publish a noisy run's points as KPI points too (default: kpi_diagnostics.jsonl)")
    ap.add_argument("--history", action="store_true", help="a re-measure of a past commit: its points go to kpi_history.jsonl, never the KPI series")
    ap.add_argument("--move-run", metavar="STAMP", help="move the points of an already published run (its stamp, e.g. 20261027-115011) to kpi_history.jsonl, then stop")
    ap.add_argument("--move-noisy", action="store_true", help="move the noisy points already in kpi_series.jsonl to kpi_diagnostics.jsonl, then stop")
    ap.add_argument("--event", default=None, help="a milestone label for the top row of the chart (e.g. 'baseline, main 0dbc3d4')")
    args = ap.parse_args()
    if args.move_run:
        return move_run(pathlib.Path(args.to).expanduser(), args.move_run)
    if args.move_noisy:
        return move_noisy(pathlib.Path(args.to).expanduser())
    res = json.loads(pathlib.Path(args.results).expanduser().read_text())
    out = pathlib.Path(args.to).expanduser()
    (out / "items").mkdir(parents=True, exist_ok=True)

    t = res["finished"]
    stamp = dt.datetime.fromisoformat(res["started"]).strftime("%Y%m%d-%H%M%S")
    sha = args.sha or (res["code"]["sha"] + ("+dirty" if res["code"].get("dirty") else ""))
    host = res["host"]["hostname"]
    runs_file = out / "runs_table.jsonl"
    seen = set()
    if runs_file.exists():
        for line in runs_file.read_text().splitlines():
            try:
                seen.add(json.loads(line)["run_id"])
            except (ValueError, KeyError):
                pass
    by = {s["target"]: s for s in res["scenarios"]}
    run_id = lambda s: f"{stamp}-{s['target'].replace('@', '-')}"
    if any(run_id(s) in seen for s in res["scenarios"]):
        print(f"already published: {stamp} ({args.results}); nothing written")
        return 0

    catalog = dict(CATALOG, generated_at=t)
    (out / "kpi_catalog.json").write_text(json.dumps(catalog, indent=1) + "\n")

    runs, points = [], []
    for s in res["scenarios"]:
        rid = run_id(s)
        samples = [{"phase": "cold", **x} for x in s["samples"]["cold"]] + [{"phase": "warm", **x} for x in s["samples"]["warm"]] + \
                  [{"phase": "interaction", **x} for x in s["samples"]["interactions"]]
        with (out / "items" / f"{rid}.jsonl").open("w") as f:
            for i, x in enumerate(samples):
                x = {k: v for k, v in x.items() if k != "files"}
                f.write(json.dumps({"item_id": f"{rid}-{i}", "compute_s": (x.get("first_useful_paint") or x.get("ms") or 0) / 1000 or None,
                                    "facets": {"phase": x["phase"], "kind": x.get("kind")}, **x}) + "\n")
        cold, warm = s["samples"]["cold"], s["samples"]["warm"]
        inter = [x for x in s["samples"]["interactions"] if x.get("ms") is not None]
        runs.append({"schema": "vt-run/1", "run_id": rid, "t": t,
                     "facets": {"scenario": s["target"], "app": s.get("app"), "rows": s.get("rows"), "synthetic": s["synthetic"], "view": s.get("view"),
                                "host": host, "lane": LANE, "trust": classify(s)[0], "stability": classify(s)[1]["verdict"],
                                "timing_valid": not classify(s)[2], "code_sha": sha, "counted": True,
                                **{k: v for k, v in renderer_labels(s).items() if k == "renderer"}},
                     "metrics": {"loads_cold": len(cold), "loads_warm": len(warm),
                                 "first_paint_cold_ms_sum": sum(x["first_useful_paint"] for x in cold if x.get("first_useful_paint") is not None),
                                 "first_paint_warm_ms_sum": sum(x["first_useful_paint"] for x in warm if x.get("first_useful_paint") is not None),
                                 "failed_loads": sum(1 for x in cold + warm if x.get("first_useful_paint") is None),
                                 "interactions": len(inter), "interaction_ms_sum": sum(x["ms"] for x in inter),
                                 "bytes_gzip_sum": sum(x.get("bytes_gzip") or 0 for x in cold), "errors": len(s.get("errors") or []),
                                 # the samples runner.py judged unclean against the pressure timeline (left out of the timing KPIs)
                                 "samples_dropped": sum(1 for x in cold + warm + s["samples"]["interactions"] if x.get("clean") is False)},
                     "items": {"path": f"items/{rid}.jsonl", "schema": "data-ui-bench-sample/1", "n": len(samples)}})

        base_labels = {"lane": LANE, "host": host, "scenario": s["target"], **renderer_labels(s)}
        bad = failed_because(s)
        if bad:
            base_labels.update(verdict="FAILED", why="FAILED: " + "; ".join(bad)[:280])
        src = {"code_sha": sha, "bench_version": CATALOG["producer"]["bench_version"], "run_ids": [rid]}
        for kpi, (value, n) in scenario_points(s).items():
            slice_ = {"scenario": s["target"]}
            if s.get("rows"):
                slice_["rows"] = s["rows"]
            points.append(point(kpi, t, value, n, slice_, base_labels, src, s))
        for kind, kp in kind_points(s):
            for kpi, (value, n) in kp.items():
                points.append(point(kpi, t, value, n, {"scenario": s["target"], "kind": kind}, base_labels, src, s))
                if s["target"] == HEAD:
                    points.append(point(kpi, t, value, n, {"kind": kind}, base_labels, src, s))

    # the whole-bench points: the headline scenario, and the three that name their own scenario
    def whole(kpi, target, value=None, n=None, extra=None):
        s = by.get(target)
        if s is None:
            # WHY skipped, not null: a run of a few scenarios (a re-check on a new commit) did not measure this
            # whole-bench KPI; a null would read as "broken", a value from other scenarios as a change
            return None
        if value is None and n is None:
            value, n = scenario_points(s).get(kpi, (None, 0))
        labels = {"lane": LANE, "host": host, "scenario": target, **renderer_labels(s), **(extra or {})}
        if args.event:
            labels["event"] = args.event
        return point(kpi, t, value, n, None, labels, {"code_sha": sha, "bench_version": CATALOG["producer"]["bench_version"], "run_ids": [run_id(s)]}, s)

    for kpi in ("first_paint_ms", "first_paint_warm_ms", "interactive_ms", "blocking_ms", "interaction_ms", "load_kb", "model_ms", "render_ms", "rail_ms", "heap_mb", "dom_added"):
        points.append(whole(kpi, HEAD))
    points.append(whole("scroll_frame_ms", "large-table@10000"))
    points.append(whole("first_paint_100k_ms", "large-table@100000", *(scenario_points(by["large-table@100000"])["first_paint_ms"] if "large-table@100000" in by else (None, 0))))
    real = [s for s in res["scenarios"] if not s["synthetic"] and s["load"]["cold"]["first_useful_paint"]["p95"] is not None]
    broken = [s for s in res["scenarios"] if not s["synthetic"] and failed_because(s)]
    every_real = {f.parent.name for f in (BENCH / "scenarios").glob("*/scenario.json") if not json.loads(f.read_text()).get("synthetic")}
    partial = not every_real <= {s["target"] for s in res["scenarios"]}
    if partial:
        pass  # the worst real scenario is defined over all of them; a partial run says nothing about it
    elif broken:
        # the worst real scenario is a failed one: its paint is not a number to rank
        points.append(whole("first_paint_worst_ms", broken[0]["target"], None, 0))
    elif real:
        worst = max(real, key=lambda s: s["load"]["cold"]["first_useful_paint"]["p95"])
        points.append(whole("first_paint_worst_ms", worst["target"], worst["load"]["cold"]["first_useful_paint"]["p95"], worst["load"]["cold"]["first_useful_paint"]["n"]))
    else:
        points.append(whole("first_paint_worst_ms", "(no real scenario)"))

    # the gate: no scenario threw (a gate evaluation is a line whose kpi is the gate id, with pass)
    failing = [s["target"] for s in res["scenarios"] if failed_because(s)]
    gsrc = {"code_sha": sha, "bench_version": CATALOG["producer"]["bench_version"], "run_ids": [run_id(s) for s in res["scenarios"]]}
    points.append({"schema": "vt-kpi-point/1", "kpi": "no_page_errors", "t": t, "value": len(failing), "n": len(res["scenarios"]), "status": "measured",
                   "pass": not failing, "labels": {"lane": LANE, "host": host, "failing": ", ".join(failing)[:300]}, "source": gsrc})
    for s in res["scenarios"]:
        bad = failed_because(s)
        points.append({"schema": "vt-kpi-point/1", "kpi": "no_page_errors", "t": t, "value": len(bad), "n": 1, "status": "measured",
                       "pass": not bad, "slice": {"scenario": s["target"]},
                       "labels": {"lane": LANE, "host": host, **({"why": "; ".join(bad)[:300]} if bad else {})}, "source": {**gsrc, "run_ids": [run_id(s)]}})
    points += stability_gate(res["scenarios"], t, host, gsrc, run_id)
    points += timing_gate(res["scenarios"], t, host, gsrc, run_id, sha)

    with runs_file.open("a") as f:
        for r in runs:
            f.write(json.dumps(r) + "\n")
    points = [p for p in points if p is not None]
    if args.history:
        # WHY: Vibe Tracks' headline is the newest point by time, so a re-measure of an old commit (a before/after
        # pair re-run hours later) published as a KPI point became the track's headline (203.7 ms from 7b9d09e on
        # 2026-10-27, while main measured 128 ms); history keeps it, the track never reads it
        with (out / "kpi_history.jsonl").open("a") as f:
            for p in points:
                f.write(json.dumps(p) + "\n")
        print(f"published {len(runs)} runs; {len(points)} points of a re-measured past commit ({sha}) to {out / 'kpi_history.jsonl'}")
        return 0
    kept = points if args.include_noisy else [p for p in points if not noisy(p)]
    aside = [] if args.include_noisy else [p for p in points if noisy(p)]
    with (out / "kpi_series.jsonl").open("a") as f:
        for p in kept:
            f.write(json.dumps(p) + "\n")
    if aside:
        with (out / "kpi_diagnostics.jsonl").open("a") as f:
            for p in aside:
                f.write(json.dumps(p) + "\n")
    print(f"published {len(runs)} runs and {len(kept)} KPI points ({stamp}, {sha}, trust {res.get('trust')}) to {out}"
          + (f"; {len(aside)} points of noisy scenarios to kpi_diagnostics.jsonl (--include-noisy publishes them)" if aside else ""))
    return 0


def stability_gate(scenarios, t, host, gsrc, run_id):
    """The stable_samples gate: per scenario the cold first paints' cv against the catalog's bound (pass, or null when
    the cv is over it on a noisy machine, the samples are too few or the scenario FAILED), and a whole-bench line: the worst judged cv,
    pass false when any scenario is unstable, null when any is pending, else true. Never routed away."""
    out, judged = [], []
    for s in scenarios:
        machine, st, _ = classify(s)
        bad = failed_because(s)
        ok = None if bad else trustlib.stability_pass(st)
        why = ("FAILED: " + "; ".join(bad))[:300] if bad else st["why"][:300]
        value = None if bad else st["cv"]
        judged.append((s["target"], ok, value))
        out.append({"schema": "vt-kpi-point/1", "kpi": "stable_samples", "t": t, "value": value, "n": st["n"],
                    "status": "measured" if value is not None else "not_measured", "pass": ok, "slice": {"scenario": s["target"]},
                    "labels": {"lane": LANE, "host": host, "machine": machine, "stability": st["verdict"], "metric": st["metric"],
                               **({"why": why} if why else {})},
                    "source": {**gsrc, "run_ids": [run_id(s)]}})
    unstable = [k for k, ok, _ in judged if ok is False]
    pending = [k for k, ok, _ in judged if ok is None]
    cvs = [v for _, ok, v in judged if ok is not None and v is not None]
    ok = False if unstable else None if pending or not judged else True
    out.append({"schema": "vt-kpi-point/1", "kpi": "stable_samples", "t": t, "value": max(cvs) if cvs else None, "n": len(cvs),
                "status": "measured" if cvs else "not_measured", "pass": ok,
                "labels": {"lane": LANE, "host": host, "unstable": ", ".join(unstable)[:300], "pending": ", ".join(pending)[:300]},
                "source": gsrc})
    return out


def timing_gate(scenarios, t, host, gsrc, run_id, sha):
    """The timing_valid gate: per scenario the number of its timing sets that were suppressed (pass when 0; null when the
    scenario FAILED, which no_page_errors already reports), and a whole-bench line, the sum, read as Vibe Tracks reads
    an instant (false if any scenario is false). Every line carries the code_sha and the reason, so the current
    build's timing reads as unresolved instead of the last published number standing as its result. Never routed
    away; --include-noisy publishes the timings, hollow, and this still fails: they were measured under interference."""
    out, verdicts, suppressed_in, total = [], [], [], 0
    for s in scenarios:
        machine, _st, suppressed = classify(s)
        bad = failed_because(s)
        timing = s["trust"].get("timing") or {}
        dropped = {k: f"{v.get('n', 0) - v.get('clean', 0)} of {v.get('n', 0)}" for k, v in timing.items() if v.get("n", 0) - v.get("clean", 0)}
        if bad:
            value, ok, why = None, None, ("FAILED: " + "; ".join(bad))[:300]
        else:
            value, ok = len(suppressed), not suppressed
            by_why = {}
            for k, v in suppressed.items():
                by_why.setdefault(v, []).append(k)
            why = " | ".join(f"{', '.join(ks)}: {w}" for w, ks in by_why.items())[:300]
            total += value
        if suppressed and not bad:
            suppressed_in.append(s["target"])
        verdicts.append(ok)
        out.append({"schema": "vt-kpi-point/1", "kpi": "timing_valid", "t": t, "value": value, "n": len(timing) or 1,
                    "status": "measured" if value is not None else "not_measured", "pass": ok, "slice": {"scenario": s["target"]},
                    "labels": {"lane": LANE, "host": host, "code_sha": sha, "machine": machine, "suppressed": ", ".join(suppressed),
                               **({"dropped": ", ".join(f"{k} {v}" for k, v in dropped.items())} if dropped else {}),
                               **({"why": why} if why else {})},
                    "source": {**gsrc, "run_ids": [run_id(s)]}})
    head = next((s for s in scenarios if s["target"] == HEAD), None)
    out.append({"schema": "vt-kpi-point/1", "kpi": "timing_valid", "t": t, "value": total, "n": len(scenarios), "status": "measured",
                "pass": trustlib.worst(verdicts), "labels": {"lane": LANE, "host": host, "code_sha": sha, "suppressed": ", ".join(suppressed_in)[:300],
                                                             **({"headline": "suppressed: the headline scenario's timings are not in the series"}
                                                                if head is not None and head["target"] in suppressed_in else {})},
                "source": gsrc})
    return out


def noisy(p):
    """A point to keep out of the KPI series: its machine was noisy and it is a KPI a busy CPU moves. WHY per metric:
    points published before 2026-10-27 were labelled with the scenario's trust whatever the KPI, so --move-noisy would
    otherwise move a byte count, which a loaded machine cannot change."""
    return (p.get("labels") or {}).get("trust") == "noisy" and trustlib.cpu_sensitive(p.get("kpi"), CATALOG)


def move_run(out, stamp):
    """Move the points of one published run (run ids starting with STAMP) from kpi_series.jsonl to kpi_history.jsonl,
    the series rewritten whole through a temp file, as move_noisy."""
    series = out / "kpi_series.jsonl"
    lines = series.read_text().splitlines()
    keep, moved = [], []
    for line in lines:
        try:
            ids = (json.loads(line).get("source") or {}).get("run_ids") or []
        except ValueError:
            ids = []
        (moved if any(str(i).startswith(stamp) for i in ids) else keep).append(line)
    if not moved:
        print(f"no points of run {stamp} in {series}")
        return 0
    with (out / "kpi_history.jsonl").open("a") as f:
        for line in moved:
            f.write(line + "\n")
    tmp = series.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(line + "\n" for line in keep))
    tmp.replace(series)
    print(f"moved {len(moved)} points of run {stamp} to {out / 'kpi_history.jsonl'}; {len(keep)} stay in {series}")
    return 0


def move_noisy(out):
    """Move the noisy points of kpi_series.jsonl to kpi_diagnostics.jsonl: the series is rewritten whole (a temp file
    renamed over it, so a reader never sees half a file), the moved lines appended to the diagnostics, unchanged."""
    series = out / "kpi_series.jsonl"
    lines = series.read_text().splitlines()
    keep, moved = [], []
    for line in lines:
        try:
            (moved if noisy(json.loads(line)) else keep).append(line)
        except ValueError:
            keep.append(line)
    if not moved:
        print(f"no noisy points in {series}")
        return 0
    with (out / "kpi_diagnostics.jsonl").open("a") as f:
        for line in moved:
            f.write(line + "\n")
    tmp = series.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(line + "\n" for line in keep))
    tmp.replace(series)
    print(f"moved {len(moved)} noisy points of {len(lines)} to {out / 'kpi_diagnostics.jsonl'}; {len(keep)} stay in {series}")
    return 0


def point(kpi, t, value, n, slice_, labels, source, s):
    # WHY: a FAILED scenario (it threw, or a part of the page is missing) never publishes a passing number
    if s is not None and failed_because(s):
        value = None
        labels = {**labels, "verdict": "FAILED", "why": "FAILED: " + "; ".join(failed_because(s))[:280]}
    status = "measured" if value is not None else "not_measured"
    if s is not None:
        labels = {**labels, **trust_labels(kpi, s)}
    p = {"schema": "vt-kpi-point/1", "kpi": kpi, "t": t, "value": value, "n": n or 0, "status": status, "labels": dict(labels), "source": source}
    if slice_:
        p["slice"] = slice_
    if value is None and s is not None and "why" not in p["labels"]:
        why = (s.get("errors") or ["no sample"])[0]
        p["labels"]["why"] = why[:300]
    return p


if __name__ == "__main__":
    sys.exit(main())
