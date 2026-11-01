"""Interleaved A/B (and A/B/C...) runs of the scenario bench, to attribute a KPI drift to commits.

    python3 bench/ab.py run --arm 636a598=/abs/dist-636a598 --arm a1e3042=/abs/dist-a1e3042 --rounds 8 --out DIR
    python3 bench/ab.py summarize DIR [--pair 636a598:a1e3042 ...]

`run` calls the real bench (npm run bench -- --no-build --dist D --sha S, so bench/run.mjs pins it to the same CPUs,
DATA_UI_BENCH_CPUS, default 4-11) once per arm per round, writing each results JSON to DIR/<arm>/r<round>/. The arms'
order changes every round: rotated by the round, and reversed on odd rounds (two arms: A B | B A | A B | B A), so a
machine that gets busier or quieter during the campaign hits every arm alike. WHY interleave: the box is shared (load
12-60 on 24 cores), and one 5-load run per commit taken hours apart (the drift this was written for: 636a598 at
04:35Z vs a1e3042 at 07:10Z) cannot tell code from load. Each invocation also records the load average and how busy
the pinned CPUs were with other work in the second before it started (DIR/log.jsonl).

`summarize` reads every results JSON under DIR and prints, per arm, the median over rounds of each run's KPIs (the
published ones are a run's p95: warm first useful paint, interaction), and for each pair the per-round paired
difference B - A (median, min, max, how many rounds B was slower, an exact two-sided sign test), plus pooled-sample
medians (every load or interaction of every round) and where each interaction kind's time goes (model, the view's
update(), the rail, and the rest: style, layout and paint). It writes DIR/summary.json.
WHY the paired rounds are the verdict and the pooled bootstrap CI is not: the CI treats every sample as independent,
but the loads and interactions of one run share that run's machine state, so it is too narrow (measured 2026-10-27 on
robotparts-actuators: 636a598 and ec3e52e, which differ only by exports nothing calls, came out 1.6 ms apart in median
interaction over 8 rounds with a CI of -2.6..-0.7, while their paired rounds split 3/8, sign p 1.0). Put an A/A arm in a
campaign (one dist under two names, c109886=D and c109886@aa=D) to see the noise floor beside the effect.

Stdlib only; it measures, it never builds (build each commit's dist yourself, e.g. in a detached worktree) and it never
publishes. SIGTERM/SIGINT stop the bench it is running (its whole process group) before it exits.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import pathlib
import random
import signal
import statistics
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
CPUS = os.environ.get("DATA_UI_BENCH_CPUS", "4-11")
CHILD: subprocess.Popen | None = None


def cpu_list(spec: str) -> list[int]:
    if spec == "all":
        return list(range(os.cpu_count() or 1))
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def cpu_times(cpus: list[int]) -> dict[int, tuple[int, int]]:
    """(busy, total) jiffies per CPU from /proc/stat."""
    out = {}
    for line in open("/proc/stat"):
        if line.startswith("cpu") and line[3].isdigit():
            name, *vals = line.split()
            n = int(name[3:])
            if n in cpus:
                v = [int(x) for x in vals]
                idle = v[3] + v[4]
                out[n] = (sum(v) - idle, sum(v))
    return out


def busy_between(a, b) -> float | None:
    busy = sum(b[c][0] - a[c][0] for c in a if c in b)
    total = sum(b[c][1] - a[c][1] for c in a if c in b)
    return round(busy / total, 3) if total else None


def stop_child(*_):
    # WHY no CHILD.wait() here: the handler runs inside the main loop's own wait(), which holds Popen's wait lock
    if CHILD is not None:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(CHILD.pid, sig)
            except ProcessLookupError:
                break
            for _ in range(100):
                try:
                    if os.waitpid(CHILD.pid, os.WNOHANG)[0]:
                        break
                except ChildProcessError:
                    break
                time.sleep(0.1)
            else:
                continue
            break
    os._exit(130)


def order_for(arms: list[str], r: int) -> list[str]:
    """Round r's order: rotated by r (each arm takes each slot once per len(arms) rounds), reversed on every other
    cycle so who-runs-after-whom is balanced too. Two arms: A B | B A | B A | A B | A B | B A ..."""
    k = r % len(arms)
    rot = arms[k:] + arms[:k]
    return rot[::-1] if (r // len(arms)) % 2 else rot


def cmd_run(args):
    global CHILD
    arms = []
    for a in args.arm:
        name, _, dist = a.partition("=")
        sha = name.split("@")[0]
        if not (pathlib.Path(dist) / "data-ui.js").exists():
            sys.exit(f"{dist}/data-ui.js is missing")
        arms.append({"name": name, "sha": sha, "dist": str(pathlib.Path(dist).resolve())})
    out = pathlib.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    names = [a["name"] for a in arms]
    plan = {"started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "arms": arms, "rounds": args.rounds, "runs": args.runs,
            "scenario": args.scenario, "cpus": CPUS, "orders": [order_for(names, r) for r in range(args.start_round, args.start_round + args.rounds)],
            "runner_checkout": str(ROOT), "pid": os.getpid()}
    (out / f"plan-{plan['started'].replace(':', '')}.json").write_text(json.dumps(plan, indent=1))
    signal.signal(signal.SIGTERM, stop_child)
    signal.signal(signal.SIGINT, stop_child)
    pinned = cpu_list(CPUS)
    by_name = {a["name"]: a for a in arms}
    for r in range(args.start_round, args.start_round + args.rounds):
        for slot, name in enumerate(order_for(names, r)):
            a = by_name[name]
            dest = out / name / f"r{r}"
            dest.mkdir(parents=True, exist_ok=True)
            t_a = cpu_times(pinned)
            time.sleep(1.0)
            t_b = cpu_times(pinned)
            pre = {"loadavg": os.getloadavg(), "pinned_busy_others": busy_between(t_a, t_b)}
            cmd = ["npm", "--prefix", str(ROOT), "run", "bench", "--", "--scenario", args.scenario, "--runs", str(args.runs), "--no-build",
                   "--dist", a["dist"], "--sha", a["sha"], "--out", str(dest), "--label", f"ab {out.name} round {r} slot {slot} {name}"]
            t0 = time.time()
            with open(dest / "bench.log", "w") as log:
                CHILD = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env={**os.environ, "DATA_UI_BENCH_CPUS": CPUS})
                code = CHILD.wait()
            t_c = cpu_times(pinned)
            rec = {"round": r, "slot": slot, "arm": name, "sha": a["sha"], "start": dt.datetime.fromtimestamp(t0, dt.timezone.utc).isoformat(timespec="seconds"),
                   "seconds": round(time.time() - t0, 1), "exit": code, "pre": pre, "post_loadavg": os.getloadavg(),
                   "pinned_busy_during": busy_between(t_b, t_c), "results": sorted(str(p) for p in dest.glob("results-*.json"))}
            with open(out / "log.jsonl", "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"round {r} slot {slot} {name}: exit {code} in {rec['seconds']} s; load {pre['loadavg'][0]:.1f}, pinned CPUs busy before {pre['pinned_busy_others']}", flush=True)
    CHILD = None


# ------------------------------------------------------------------ summarize
SCEN = "robotparts-actuators"


def metrics(path: pathlib.Path, scenario: str) -> dict | None:
    d = json.loads(path.read_text())
    s = next((x for x in d["scenarios"] if x["id"] == scenario or x["target"] == scenario), None)
    if s is None:
        return None
    L, I = s["load"], s["interaction"]
    m = {
        "warm_fup_p95": L["warm"]["first_useful_paint"]["p95"], "warm_fup_p50": L["warm"]["first_useful_paint"]["p50"],
        "cold_fup_p95": L["cold"]["first_useful_paint"]["p95"], "cold_fup_p50": L["cold"]["first_useful_paint"]["p50"],
        "warm_render_p50": L["warm"]["render_ms"]["p50"], "warm_model_p50": L["warm"]["model_ms"]["p50"],
        "cold_render_p50": L["cold"]["render_ms"]["p50"], "cold_model_p50": L["cold"]["model_ms"]["p50"],
        "warm_mark_data_p50": L["warm"]["mark_data"]["p50"], "cold_mark_data_p50": L["cold"]["mark_data"]["p50"],
        "warm_longtask_runs": sum(1 for x in s["samples"]["warm"] if x.get("longtasks")),
        "int_p95": I["all"]["p95"], "int_p50": I["all"]["p50"],
        "bytes_gzip": L["cold"]["bytes_gzip"]["p50"], "dom_nodes": L["cold"]["dom_nodes"]["p50"],
        "calib_max": max(s["trust"]["calibration_ms"]), "trust": s["trust"]["verdict"], "verdict": s.get("verdict"),
        "failed_because": s.get("failed_because") or [],
    }
    for k in ("filter", "sort", "search", "peek", "preset"):
        if k in I:
            m[f"{k}_p95"], m[f"{k}_p50"] = I[k]["p95"], I[k]["p50"]
    samples = {"warm_fup": [x["first_useful_paint"] for x in s["samples"]["warm"]], "cold_fup": [x["first_useful_paint"] for x in s["samples"]["cold"]],
               "int": [x["ms"] for x in s["samples"]["interactions"] if x.get("ms") is not None]}
    for k in ("filter", "sort", "search", "peek", "preset"):
        samples[k] = [x["ms"] for x in s["samples"]["interactions"] if x["kind"] == k and x.get("ms") is not None]
    samples["ix"] = [x for x in s["samples"]["interactions"] if x.get("ms") is not None]
    return {"m": m, "samples": samples}


def sign_test(diffs: list[float]) -> float | None:
    """Exact two-sided sign test on non-zero paired differences."""
    nz = [d for d in diffs if d]
    n = len(nz)
    if not n:
        return None
    k = min(sum(1 for d in nz if d > 0), sum(1 for d in nz if d < 0))
    p = 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return round(min(1.0, p), 4)


def verdict(diffs: list[float], aa: list[float] | None, margin: float | None) -> dict:
    """What a paired comparison (B - A per round) supports, and no more (judge r2, 2026-10-27).

    - "regression": B slower beyond doubt: a same-campaign A/A control exists, B is slower in a sign test (p < 0.05)
      and the median difference exceeds every A/A difference (the A/A showed this procedure itself can give p = 0.04
      on identical builds, so a sign test alone is not enough)
    - "equivalent within ±M ms": a same-campaign A/A exists, a margin M was declared before the run, and every paired
      difference and every A/A difference lies inside it
    - "slower, unconfirmed": a consistent slowdown with no A/A control to measure it against
    - "not consistently reproduced": anything else; a jump that does not repeat is not shown to be noise
    """
    d = [x for x in diffs if x is not None]
    out = {"n": len(d), "median": round(statistics.median(d), 2) if d else None, "sign_p": sign_test(d) if d else None,
           "aa_max_abs": round(max(abs(x) for x in aa), 2) if aa else None, "margin": margin}
    if not d:
        return {**out, "verdict": "not consistently reproduced"}
    slower = out["median"] > 0 and out["sign_p"] is not None and out["sign_p"] < 0.05
    if slower and aa and out["median"] > out["aa_max_abs"]:
        return {**out, "verdict": "regression"}
    if aa and margin is not None and all(abs(x) <= margin for x in d) and all(abs(x) <= margin for x in aa):
        return {**out, "verdict": f"equivalent within ±{margin} ms"}
    if slower and not aa:
        return {**out, "verdict": "slower, unconfirmed"}
    return {**out, "verdict": "not consistently reproduced"}


def boot_median_diff(a: list[float], b: list[float], n: int = 2000, seed: int = 1) -> tuple[float, float] | None:
    if not a or not b:
        return None
    rnd = random.Random(seed)
    ds = sorted(statistics.median(rnd.choices(b, k=len(b))) - statistics.median(rnd.choices(a, k=len(a))) for _ in range(n))
    return round(ds[int(0.025 * n)], 1), round(ds[int(0.975 * n)], 1)


def cmd_summarize(args):
    out = pathlib.Path(args.dir).resolve()
    log = [json.loads(line) for line in (out / "log.jsonl").read_text().splitlines() if line.strip()]
    per = {}  # arm -> round -> {"m","samples","log"}
    for rec in log:
        # WHY opt-in: a FAILED run is excluded by default (bench/README: FAILED, never fast); --include-failed reads one
        # whose only failure is instrumentation it predates (a build before perf core 3 has no data-ui:rail measure)
        if not rec["results"] or (rec["exit"] != 0 and not args.include_failed):
            continue
        got = metrics(pathlib.Path(rec["results"][-1]), args.scenario)
        if got:
            got["log"] = rec
            per.setdefault(rec["arm"], {})[rec["round"]] = got
    arms = list(dict.fromkeys(rec["arm"] for rec in log))
    keys = ["warm_fup_p95", "warm_fup_p50", "cold_fup_p95", "cold_fup_p50", "int_p95", "int_p50", "filter_p95", "sort_p95", "search_p95", "peek_p95",
            "preset_p95", "filter_p50", "sort_p50", "search_p50", "peek_p50", "preset_p50", "warm_render_p50", "warm_model_p50", "cold_render_p50",
            "cold_model_p50", "warm_mark_data_p50", "warm_longtask_runs", "bytes_gzip", "dom_nodes", "calib_max"]
    summary = {"dir": str(out), "scenario": args.scenario, "arms": {}, "pairs": []}
    print(f"{out.name}: {len(log)} invocations, arms {', '.join(arms)}")
    print(f"\n{'metric':20}" + "".join(f"{a:>26}" for a in arms))
    for k in keys:
        row = f"{k:20}"
        for a in arms:
            vals = [r["m"].get(k) for r in per.get(a, {}).values() if r["m"].get(k) is not None]
            if vals:
                med = statistics.median(vals)
                summary["arms"].setdefault(a, {})[k] = {"median": med, "min": min(vals), "max": max(vals), "n": len(vals)}
                row += f"{med:>10.1f} [{min(vals):>6.1f}-{max(vals):>6.1f}]".rjust(26)
            else:
                row += f"{'-':>26}"
        print(row)
    print(f"\n{'pooled samples':20}" + "".join(f"{a:>26}" for a in arms))
    for k in ("warm_fup", "cold_fup", "int", "filter", "sort", "search", "peek", "preset"):
        row = f"{k + ' p50/p95':20}"
        for a in arms:
            xs = sorted(x for r in per.get(a, {}).values() for x in r["samples"][k])
            if xs:
                p95 = xs[max(1, math.ceil(0.95 * len(xs))) - 1]
                summary["arms"].setdefault(a, {})[f"pooled_{k}"] = {"p50": statistics.median(xs), "p95": p95, "n": len(xs)}
                row += f"{statistics.median(xs):>10.1f} / {p95:>6.1f} (n {len(xs)})".rjust(26)
            else:
                row += f"{'-':>26}"
        print(row)
    # where an interaction's time goes: data-ui's own measures (model, the view's update, the rail) and the rest, which
    # is input dispatch plus the browser's style, layout and paint of what update() wrote (the frame after it)
    print("\ninteraction breakdown, pooled medians in ms: total = model + render + rail + rest (rest: style/layout/paint)")
    for k in ("filter", "sort", "preset", "peek", "search"):
        for a in arms:
            xs = [x for r in per.get(a, {}).values() for x in r["samples"]["ix"] if x["kind"] == k]
            if not xs:
                continue
            med = lambda f: statistics.median(f(x) for x in xs)
            parts = {"total": med(lambda x: x["ms"]), "model": med(lambda x: x.get("model_ms") or 0), "render": med(lambda x: x.get("render_ms") or 0),
                     "rail": med(lambda x: x.get("rail_ms") or 0),
                     "rest": med(lambda x: x["ms"] - (x.get("model_ms") or 0) - (x.get("render_ms") or 0) - (x.get("rail_ms") or 0))}
            summary["arms"].setdefault(a, {})[f"breakdown_{k}"] = parts
            print(f"  {k:7} {a:16} " + "  ".join(f"{n} {v:5.1f}" for n, v in parts.items()))
    print("\nper round (load avg before, pinned CPUs busy with other work before, calibration max):")
    for a in arms:
        for rnd, r in sorted(per.get(a, {}).items()):
            lg = r["log"]
            print(f"  {a:16} r{rnd} slot {lg['slot']} {lg['start']}: load {lg['pre']['loadavg'][0]:5.1f} pinned-busy {lg['pre']['pinned_busy_others']}"
                  f" calib {r['m']['calib_max']:6.1f} trust {r['m']['trust']:5} | warm p95 {r['m']['warm_fup_p95']:6.1f} cold p95 {r['m']['cold_fup_p95']:6.1f}"
                  f" int p95 {r['m']['int_p95']:5.1f} warm-longtask-runs {r['m']['warm_longtask_runs']}"
                  + (f" | FAILED: {'; '.join(sorted({w.split(': ', 1)[-1] for w in r['m']['failed_because']}))}" if r["m"]["verdict"] == "FAILED" else ""))
    pairs = [tuple(p.split(":")) for p in (args.pair or [])] or list(zip(arms, arms[1:]))
    for A, B in pairs:
        common = sorted(set(per.get(A, {})) & set(per.get(B, {})))
        if not common:
            continue
        print(f"\npair {A} -> {B}: {len(common)} rounds (paired B - A within a round)")
        pr = {"a": A, "b": B, "rounds": common, "metrics": {}}
        for k in keys[:22]:
            d = [per[B][r]["m"][k] - per[A][r]["m"][k] for r in common if per[B][r]["m"].get(k) is not None and per[A][r]["m"].get(k) is not None]
            if not d:
                continue
            st = {"median": round(statistics.median(d), 2), "min": round(min(d), 2), "max": round(max(d), 2), "b_slower": sum(1 for x in d if x > 0), "n": len(d),
                  "sign_p": sign_test(d), "a_median": statistics.median(per[A][r]["m"][k] for r in common), "b_median": statistics.median(per[B][r]["m"][k] for r in common)}
            aa = None
            if getattr(args, "aa", None):
                x, y = args.aa.split(":")
                rr = sorted(set(per.get(x, {})) & set(per.get(y, {})))
                aa = [per[y][r]["m"][k] - per[x][r]["m"][k] for r in rr if per[y][r]["m"].get(k) is not None and per[x][r]["m"].get(k) is not None] or None
            st["verdict"] = verdict(d, aa, getattr(args, "margin", None))["verdict"]
            pr["metrics"][k] = st
            print(f"  {k:20} A {st['a_median']:7.1f}  B {st['b_median']:7.1f}  diff median {st['median']:+7.1f} [{st['min']:+7.1f} .. {st['max']:+7.1f}]"
                  f"  B slower {st['b_slower']}/{st['n']}  sign p {st['sign_p']}  -> {st['verdict']}")
        for k in ("warm_fup", "cold_fup", "int", "filter", "sort", "search", "peek", "preset"):
            a = [x for r in common for x in per[A][r]["samples"][k]]
            b = [x for r in common for x in per[B][r]["samples"][k]]
            if a and b:
                ci = boot_median_diff(a, b)
                pr["metrics"][f"pooled_{k}_median_diff"] = {"diff": round(statistics.median(b) - statistics.median(a), 2), "ci95": ci, "n": [len(a), len(b)]}
                print(f"  pooled {k:13} median A {statistics.median(a):7.1f}  B {statistics.median(b):7.1f}  diff {statistics.median(b) - statistics.median(a):+6.1f}  boot 95% CI {ci}")
        summary["pairs"].append(pr)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(f"\nwrote {out / 'summary.json'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--arm", action="append", required=True, help="NAME=DIST, NAME being the commit (sha, or sha@note)")
    r.add_argument("--rounds", type=int, default=4)
    r.add_argument("--start-round", type=int, default=0, help="continue a campaign: the first round's number")
    r.add_argument("--runs", type=int, default=5)
    r.add_argument("--scenario", default=SCEN)
    r.add_argument("--out", required=True)
    s = sub.add_parser("summarize")
    s.add_argument("dir")
    s.add_argument("--pair", action="append", help="A:B (default: each arm against the next)")
    s.add_argument("--scenario", default=SCEN)
    s.add_argument("--include-failed", action="store_true", help="also read runs the bench marked FAILED (their reasons are printed per round)")
    s.add_argument("--aa", help="A:A' arms of the same build, run in this campaign: the control the verdict is measured against")
    s.add_argument("--margin", type=float, help="the regression margin in ms, declared before the run: the only basis for 'equivalent'")
    args = ap.parse_args()
    (cmd_run if args.cmd == "run" else cmd_summarize)(args)


if __name__ == "__main__":
    main()
