"""Deliberate interference, to validate the bench's trust verdict (bench/trust.py) on a real run. Stdlib only, Linux.

    python3 bench/inject_interference.py run --cpus 4-11 --seconds 1 --out INJ.json     # busy loops, one per CPU
    python3 bench/inject_interference.py check RESULTS.json INJ.json                     # what the bench caught

run forks one busy loop per CPU, each pinned to its CPU, for `--seconds`, and writes {"start", "end" (time.monotonic,
the clock the bench's samples carry), "cpus", "pids"}. The parent waits for its children and kills any that outstay
the deadline by two seconds, by PID. Start it while a bench runs on the same CPUs (DATA_UI_BENCH_CPUS, default 4-11).

check reads a results file and the injection record and prints, per timing set, the samples that overlapped the
injection and were caught (not clean), the ones that overlapped and were missed, and the ones that did not overlap
but were flagged anyway (other agents' work, or a false alarm); exit 1 when any overlapping sample was missed.
WHY (judge r2, finding 4): the thresholds were chosen, not measured; this is the measurement.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import signal
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import trust as trustlib  # noqa: E402


def run(cpus: list[int], seconds: float) -> dict:
    start = time.monotonic()
    end = start + seconds
    pids = []
    for cpu in cpus:
        pid = os.fork()
        if pid == 0:  # the child: pin, spin until the deadline, leave without running the parent's cleanup
            try:
                os.sched_setaffinity(0, {cpu})
                while time.monotonic() < end:
                    pass
            finally:
                os._exit(0)
        pids.append(pid)
    left = set(pids)
    while left and time.monotonic() < end + 2.0:
        for pid in list(left):
            done, _ = os.waitpid(pid, os.WNOHANG)
            if done:
                left.discard(pid)
        time.sleep(0.02)
    for pid in left:  # outstayed the deadline: stopped by its PID, then reaped
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
    return {"start": round(start, 4), "end": round(time.monotonic(), 4), "spin_until": round(end, 4), "cpus": cpus, "pids": pids,
            "killed": sorted(left)}


def check(results: dict, inj: dict) -> int:
    a, b = inj["start"], inj["spin_until"]
    missed_any = False
    for s in results["scenarios"]:
        rows = {"cold": s["samples"]["cold"], "warm": s["samples"]["warm"], "interactions": [x for x in s["samples"]["interactions"] if x.get("ms") is not None]}
        print(f"{s['target']}: injection {b - a:.2f} s on CPUs {inj['cpus'][0]}-{inj['cpus'][-1]}; timing {json.dumps({k: {x: v[x] for x in ('n', 'clean', 'valid')} for k, v in s['trust']['timing'].items()})}")
        for name, xs in rows.items():
            over = [x for x in xs if x.get("t0") is not None and x["t0"] < b and x["t1"] > a]
            caught = [x for x in over if x.get("clean") is False]
            missed = [x for x in over if x.get("clean") is not False]
            alarms = [x for x in xs if x not in over and x.get("clean") is False]
            missed_any |= bool(missed)
            print(f"  {name:12} {len(xs):3} samples; {len(over)} overlapped the injection: {len(caught)} caught, {len(missed)} missed; "
                  f"{len(alarms)} flagged outside it"
                  + (f" (foreign share {', '.join(str(x['pressure']['foreign_share']) for x in alarms[:6])})" if alarms else ""))
            for x in missed:
                print(f"      MISSED {x.get('kind', name)} {x['t0']:.3f}-{x['t1']:.3f} pressure {x.get('pressure')}")
        for sc in s["samples"].get("scroll") or []:
            if sc.get("t0") is not None and sc["t0"] < b and sc["t1"] > a:
                over_s = min(b, sc["t1"]) - max(a, sc["t0"])
                print(f"  scroll run {sc['t0']:.3f}-{sc['t1']:.3f}: overlapped the injection for {over_s:.2f} s; "
                      f"{sc['frames'] - (sc['frames_clean'] or 0)} of {sc['frames']} frames dropped")
    return 1 if missed_any else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--cpus", default=os.environ.get("DATA_UI_BENCH_CPUS", "4-11"))
    r.add_argument("--seconds", type=float, default=1.0)
    r.add_argument("--out", default=None)
    c = sub.add_parser("check")
    c.add_argument("results")
    c.add_argument("injection")
    args = ap.parse_args()
    if args.cmd == "run":
        rec = run(trustlib.parse_cpu_list(args.cpus), args.seconds)
        print(json.dumps(rec))
        if args.out:
            pathlib.Path(args.out).write_text(json.dumps(rec) + "\n")
        return 0
    return check(json.loads(pathlib.Path(args.results).read_text()), json.loads(pathlib.Path(args.injection).read_text()))


if __name__ == "__main__":
    sys.exit(main())
