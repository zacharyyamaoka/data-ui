"""Writes the P2 fixture's data files beside this script (tests/browser/p2_checks.py reads them for every oracle).
Stdlib only, deterministic.

    python3 tests/browser/fixtures/p2/make_fixture.py

PEP 0010 P2 (docs/peps/0010-robotics-playback.md §11): coverage. Every table is written the way a producer writes the
trajectory contract (gallery/robotics/CONTRACT.md §2): `{"schema": {"fields": […]}, "rows": […]}`, every column named in
its unit.

  runs137.json   137 runs of one synthetic tool path (family real), 24 samples each at 10 Hz (t = 0 … 2.3 s), in the
                 base frame, in mm, rounded to 0.001 mm. Each run is the same S-shaped sweep in x, offset in y and z by a
                 triangular draw (more runs near the middle, so the density has a peak to find) and jittered by ±3 mm per
                 sample. The coverage weight w is 1 on every row but each run's last (w = 0: a run's kept extreme, PEP 0010
                 §4.4), so value: time (Σ w ÷ hz) and value: count differ. Every 10th run starts exactly on a 25 mm cell
                 edge (x 50, y −25, z 125: the voxel edge rule), and run m/r007 has one missing z (null: never a 0).
  limits.json    two devices (A, B) over 10 s at 10 Hz, real and target, with limits as columns: lim_hi and lim_lo (a
                 device's own constant: A ±40, B ±60) and cap (time-varying: A 30 before t = 5 s and 45 from it, B 50 and
                 65): the rules and bands from a property (sim2real gap #6).
"""

from __future__ import annotations

import json
import math
import pathlib
import random

HERE = pathlib.Path(__file__).resolve().parent

POSE_FIELDS = [
    {"name": "t", "type": "number", "unit": "s"},
    {"name": "run", "type": "string"},
    {"name": "situation", "type": "string"},
    {"name": "source", "type": "string"},
    {"name": "body", "type": "string"},
    {"name": "frame", "type": "string"},
    {"name": "x_mm", "type": "number", "unit": "mm"},
    {"name": "y_mm", "type": "number", "unit": "mm"},
    {"name": "z_mm", "type": "number", "unit": "mm"},
    {"name": "w", "type": "number", "description": "1 on the 10 Hz grid, 0 on each run's last row (a kept extreme)"},
]
LIMIT_FIELDS = [
    {"name": "t", "type": "number", "unit": "s"},
    {"name": "device", "type": "string"},
    {"name": "situation", "type": "string"},
    {"name": "source", "type": "string"},
    {"name": "q_deg", "type": "number", "unit": "deg"},
    {"name": "lim_hi", "type": "number", "unit": "deg", "description": "the device's upper limit (a constant per device)"},
    {"name": "lim_lo", "type": "number", "unit": "deg", "description": "the device's lower limit (a constant per device)"},
    {"name": "cap", "type": "number", "unit": "deg", "description": "a limit that changes at t = 5 s"},
]


def write(path: pathlib.Path, title: str, fields: list[dict], rows: list[dict]) -> None:
    one = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
    head = {"title": title, "source": "synthetic, tests/browser/fixtures/p2/make_fixture.py", "schema": {"fields": fields}}
    # one row per line: a regenerated file diffs row by row
    path.write_text(one(head)[:-1] + ',"rows":[\n' + ",\n".join(one(r) for r in rows) + "\n]}\n", encoding="utf-8")


def runs137() -> list[dict]:
    rng = random.Random(137)
    rows = []
    n = 24
    for k in range(1, 138):
        run = f"m/r{k:03d}"
        dy = rng.triangular(-45.0, 45.0, 0.0)
        dz = rng.triangular(-30.0, 30.0, 0.0)
        for i in range(n):
            s = i / (n - 1)
            x = 20.0 + 260.0 * s + rng.uniform(-3.0, 3.0)
            y = 60.0 * math.sin(2 * math.pi * s) + dy + rng.uniform(-3.0, 3.0)
            z = 120.0 + 200.0 * s * (1 - s) + dz + rng.uniform(-3.0, 3.0)
            if k % 10 == 0 and i == 0:
                x, y, z = 50.0, -25.0, 125.0          # exactly on a 25 mm cell's edges
            row = {"t": round(i / 10, 1), "run": run, "situation": "real", "source": "real", "body": "tool0", "frame": "base",
                   "x_mm": round(x, 3), "y_mm": round(y, 3), "z_mm": round(z, 3), "w": 0 if i == n - 1 else 1}
            if k == 7 and i == 5:
                row["z_mm"] = None                    # missing: skipped, never binned as 0
            rows.append(row)
    return rows


def limits() -> list[dict]:
    rows = []
    for device, amp, lim, caps in (("A", 35.0, 40.0, (30.0, 45.0)), ("B", 55.0, 60.0, (50.0, 65.0))):
        for i in range(100):
            t = round(i / 10, 1)
            for situation, source, lag in (("real", "real", 0.0), ("target", "target", 0.15)):
                rows.append({"t": t, "device": device, "situation": situation, "source": source,
                             "q_deg": round(amp * math.sin(0.9 * (t - lag)), 4), "lim_hi": lim, "lim_lo": -lim,
                             "cap": caps[0] if t < 5.0 else caps[1]})
    return rows


def main() -> None:
    write(HERE / "runs137.json", "137 runs of one tool path (synthetic)", POSE_FIELDS, runs137())
    write(HERE / "limits.json", "Two devices with their limits as columns (synthetic)", LIMIT_FIELDS, limits())


if __name__ == "__main__":
    main()
