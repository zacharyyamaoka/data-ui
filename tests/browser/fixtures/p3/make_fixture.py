"""Writes the P3 fixture's data files (runs.json, samples.json) beside this script. Stdlib only, deterministic.

    python3 tests/browser/fixtures/p3/make_fixture.py

What tests/browser/p3_checks.py measures on it (docs/peps/0010-robotics-playback.md §11 P3, sim2real gaps #7 and #8):
  - six runs on three stations (S1, S2, S3), two each, started ten minutes apart (r6 newest);
  - their samples: every run has `real` rows; r1-r4 also have `target` rows and r5, r6 do not. WHY: a pick of "target" on
    the samples' rail narrows the runs to r1-r4 through a two-way link (twoway.base: S3 leaves the Station counts) and
    leaves every run listed through a one-way link (oneway.base), so the one-way check can fail;
  - t in s from each run's start at 0.5 s steps, a run's length its own (r1 2.0 s … r6 4.5 s), q a ramp per run.
The values are synthetic; the checks read these files for every oracle.
"""

from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

# (run, station, kind, started, last t in s, has target rows)
RUNS = [
    ("r1", "S1", "sine", "2026-10-29T08:00:00-07:00", 2.0, True),
    ("r2", "S1", "waypoints", "2026-10-29T08:10:00-07:00", 2.5, True),
    ("r3", "S2", "sine", "2026-10-29T08:20:00-07:00", 3.0, True),
    ("r4", "S2", "waypoints", "2026-10-29T08:30:00-07:00", 3.5, True),
    ("r5", "S3", "sine", "2026-10-29T08:40:00-07:00", 4.0, False),
    ("r6", "S3", "chirp", "2026-10-29T08:50:00-07:00", 4.5, False),
]


def main() -> None:
    runs = {
        "id": "p3-runs", "title": "Runs",
        "properties": {"run": {"type": "text"}, "station": {"type": "text"}, "kind": {"type": "text"}, "started": {"type": "date"}},
        "rows": [{"id": run, "run": run, "station": station, "kind": kind, "started": started} for run, station, kind, started, _, _ in RUNS],
    }
    rows = []
    for k, (run, station, _, _, last, target) in enumerate(RUNS):
        steps = int(round(last / 0.5)) + 1
        for situation in ("real", "target") if target else ("real",):
            for i in range(steps):
                t = round(i * 0.5, 3)
                rows.append({"id": f"{run}-{situation}-{i}", "run": run, "station": station, "situation": situation, "t": t,
                             "q_deg": round(10 * (k + 1) + 2 * t + (0.25 if situation == "real" else 0), 3)})
    samples = {
        "id": "p3-samples", "title": "Samples",
        "properties": {"run": {"type": "text"}, "station": {"type": "text"}, "situation": {"type": "text"}, "t": {"type": "number", "unit": "s"},
                       "q_deg": {"type": "number", "unit": "deg"}},
        "rows": rows,
    }
    (HERE / "runs.json").write_text(json.dumps(runs, indent=1) + "\n", encoding="utf-8")
    (HERE / "samples.json").write_text(json.dumps(samples, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
