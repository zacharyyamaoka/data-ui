"""Writes the P0 fixture's data files (runs.json, servo.json, camera.json) beside this script. Stdlib only, deterministic.

    python3 tests/browser/fixtures/p0/make_fixture.py

Modelled on the sim2real dashboards that found the gaps (docs/peps/0010-robotics-playback.md §11 P0; the backlog
reports/backlog-sim2real-gaps-2026-10-28.md):
  - the run spans are the rack's (sim2real dashboards/rack/samples_servo.json, measured 2026-10-28): CAN 14's staircase
    s03 runs 0 → 35.993 s (the "36 s clock"), CAN 11's held-out run s09 0 → 4.518 s (the "4.5 s run"), and CAN 12, 13
    and 1's held-out runs 4.0169, 3.5186 and 3.5326 s;
  - the devices are the suite's arm joints and its two cameras (dashboards/suite/2-type-catalog.base: a servo rail
    defaulting to "J3 elbow" and a camera rail defaulting to "Scene camera", both facets over `device`).
The samples are 10 Hz with the run's own last instant appended, two situations (real, twin) per instant, so every
run's min..max t is exactly its span above. The values are synthetic; the checks read these files for every oracle.
"""

from __future__ import annotations

import json
import math
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

# (run, run set, device, last t in s): the spans copied from the rack, the devices from the suite
RUNS = [
    ("CAN 14 · s03 · 10-23", "staircase", "J3 elbow", 35.993),
    ("CAN 11 · s09 · 10-25", "held-out", "J3 elbow", 4.518),
    ("CAN 12 · s09 · 10-25", "held-out", "J4 wrist 1", 4.0169),
    ("CAN 13 · s09 · 10-25", "held-out", "J2 shoulder lift", 3.5186),
    ("CAN 1 · s01 · 10-24", "held-out", "J1 shoulder pan", 3.5326),
]
STEP = 0.1  # s: 10 Hz


def instants(last: float) -> list[float]:
    """0, 0.1, 0.2 … up to the run's last instant, which is always the final sample."""
    out = [round(k * STEP, 4) for k in range(int(last / STEP) + 1)]
    if out[-1] < last:
        out.append(last)
    return out


def write(name: str, title: str, properties: dict, rows: list[dict]) -> None:
    head = {"id": f"p0-{name}", "title": title, "source": "synthetic, tests/browser/fixtures/p0/make_fixture.py",
            "properties": properties}
    one = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
    # one row per line: small, and a diff of a regenerated file reads row by row
    text = one(head)[:-1] + ',"rows":[\n' + ",\n".join(one(r) for r in rows) + "\n]}\n"
    (HERE / f"{name}.json").write_text(text, encoding="utf-8")


def main() -> None:
    runs = [{"id": run, "run": run, "run_set": run_set, "device": device, "duration_s": last}
            for run, run_set, device, last in RUNS]
    write("runs", "Runs (P0 fixture)", {
        "run": {"type": "text"}, "run_set": {"type": "text"}, "device": {"type": "text"},
        "duration_s": {"type": "number", "unit": "s"},
    }, runs)

    servo = []
    for k, (run, run_set, device, last) in enumerate(RUNS):
        for t in instants(last):
            real = round(20 * math.sin(0.7 * t + k) + 3 * k, 4)
            for situation, q in (("real", real), ("twin", round(real + 0.4 * math.cos(1.3 * t), 4))):
                servo.append({"t": t, "run": run, "run_set": run_set, "device": device, "situation": situation, "q_deg": q})
    write("servo", "Servo samples (P0 fixture)", {
        "t": {"type": "number", "unit": "s"}, "run": {"type": "text"}, "run_set": {"type": "text"},
        "device": {"type": "text"}, "situation": {"type": "text"}, "q_deg": {"type": "number", "unit": "°"},
    }, servo)

    camera = []
    for run, run_set, _device, last in RUNS:
        cams = ["Scene camera"] + (["Wrist camera"] if run_set == "held-out" else [])
        for cam in cams:
            for j in range(5):
                camera.append({"t": round(last * j / 4, 4), "run": run, "run_set": run_set, "device": cam,
                               "frame_dt_ms": round(33.3 + (j % 3) * 0.4 + (1.1 if cam == "Wrist camera" else 0), 2)})
    write("camera", "Camera frames (P0 fixture)", {
        "t": {"type": "number", "unit": "s"}, "run": {"type": "text"}, "run_set": {"type": "text"},
        "device": {"type": "text"}, "frame_dt_ms": {"type": "number", "unit": "ms"},
    }, camera)


if __name__ == "__main__":
    main()
