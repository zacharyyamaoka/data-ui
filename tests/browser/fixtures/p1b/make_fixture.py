"""Writes the P1b fixture's data files beside this script (tests/browser/p1b_checks.py reads them for every oracle).
Stdlib only, deterministic.

    python3 tests/browser/fixtures/p1b/make_fixture.py

PEP 0010 P1b (docs/CONTRACT.md §32): scene3d's stage and Layer 1 primitives, and trajectory3d. Every table is written
the way a producer writes the trajectory contract (gallery/robotics/CONTRACT.md §2): `{"schema": {"fields": […]},
"rows": […]}`, every column named in its unit.

  path.json         one synthetic tool path per situation, 564 samples at 100 Hz (t = 0 … 5.63 s), monotonic in x, so a
                    top view never draws it over itself (the decay check reads pixels along it). 564 samples at density
                    20 is the PEP's own example: stride ⌊564/20⌋ = 28, markers at 0, 28, … 560 plus the last: 22.
                    Situations real (family real), target (target), twin (sim) and replay (family "replay", which the
                    families map does not list: unclassified).
  two-frames.json   one body written in two frames (run r1 in base, run r2 in belt): the viewer names both, draws neither.
  arm/              a dashboard's worth of the contract on the UR5e: pid-tuning's robot.json (MuJoCo FK of the replayed
                    tape at 25 Hz, metres) written in millimetres. STAND-IN labels: pid-tuning's situations are all sim
                    controller rungs; here tuned plays "real", factory "twin" (sim), oracle "replay" (an unlisted family)
                    and target "target". Run arm/r2 is arm/r1 moved +40 mm in x and cut at 6.0 s, so a run switch moves every path and
                    changes the row count.
                    links.json is every other row (12.5 Hz); samples.json gives the device rail (J3 elbow in run r1 only, J4 wrist 1 in run r2 only; q_deg is
                    synthetic); diff_poses.json is difference(a, b) of each situation against target, computed by the
                    contract's stdlib reference implementation (tools/test_robotics_fixture.py).
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from test_robotics_fixture import difference  # noqa: E402  the contract's stdlib difference(a, b)

LINKS = ["base", "shoulder_link", "upper_arm_link", "forearm_link", "wrist_1_link", "wrist_2_link", "wrist_3_link"]
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
    {"name": "quat_w", "type": "number"},
    {"name": "quat_x", "type": "number"},
    {"name": "quat_y", "type": "number"},
    {"name": "quat_z", "type": "number"},
]


def write(path: pathlib.Path, title: str, fields: list[dict], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    one = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
    head = {"title": title, "source": "synthetic or derived, tests/browser/fixtures/p1b/make_fixture.py", "schema": {"fields": fields}}
    # one row per line: a diff of a regenerated file reads row by row
    path.write_text(one(head)[:-1] + ',"rows":[\n' + ",\n".join(one(r) for r in rows) + "\n]}\n", encoding="utf-8")


def qmul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw)


def r6(v):
    return round(v, 6)


# --------------------------------------------------------------------------------------------- path.json
PATH_N, PATH_HZ = 564, 100
PATH_SITUATIONS = [  # (situation, source, dy, dz)
    ("real", "real", 0.0, 0.0),
    ("target", "target", 8.0, 0.0),
    ("twin", "sim", -6.0, 4.0),
    ("replay", "replay", 0.0, 25.0),
]


def path_rows():
    rows = []
    for situation, source, dy, dz in PATH_SITUATIONS:
        for k in range(PATH_N):
            t = round(k / PATH_HZ, 4)
            theta = 0.35 * math.sin(0.9 * t)
            # the tool points down (180° about x), tilted θ about its own y: q = (0, cos θ/2, 0, sin θ/2)
            q = (0.0, math.cos(theta / 2), 0.0, math.sin(theta / 2))
            rows.append({"t": t, "run": "path/r1", "situation": situation, "source": source, "body": "tool0", "frame": "base",
                         "x_mm": round(-170 + 60 * t, 4), "y_mm": round(40 * math.sin(1.3 * t) + dy, 4), "z_mm": round(200 + 15 * t + dz, 4),
                         "quat_w": r6(q[0]), "quat_x": r6(q[1]), "quat_y": r6(q[2]), "quat_z": r6(q[3])})
    return rows


def two_frames_rows():
    rows = []
    for run, frame, dx in (("frames/r1", "base", 0.0), ("frames/r2", "belt", 300.0)):
        for k in range(201):
            t = round(k / 100, 4)
            rows.append({"t": t, "run": run, "situation": "real", "source": "real", "body": "tool0", "frame": frame,
                         "x_mm": round(dx + 50 * t, 4), "y_mm": round(30 * math.cos(2 * t), 4), "z_mm": 120.0,
                         "quat_w": 0.0, "quat_x": 1.0, "quat_y": 0.0, "quat_z": 0.0})
    return rows


# --------------------------------------------------------------------------------------------- arm/
ARM_MAP = {"target": ("target", "target"), "tuned": ("real", "real"), "factory": ("twin", "sim"), "oracle": ("replay", "replay")}
ARM_RUNS = [("arm/r1", 0.0, "J3 elbow", 7.88), ("arm/r2", 40.0, "J4 wrist 1", 6.0)]  # (run, x shift mm, device, last t)


def arm():
    doc = json.loads((ROOT / "gallery" / "examples" / "pid-tuning" / "robot.json").read_text(encoding="utf-8"))
    tool = doc["robot"]["tool"]
    site_q = tuple(tool["quat"])
    poses, links, samples = [], [], []
    for run, dx, device, last in ARM_RUNS:
        for r in doc["rows"]:
            if r["t"] > last + 1e-9:
                continue
            situation, source = ARM_MAP[r["situation"]]
            qw = qmul(tuple(r[f"wrist_3_link_q{c}"] for c in "wxyz"), site_q)
            n = math.sqrt(sum(c * c for c in qw))
            q = tuple(c / n for c in qw)
            poses.append({"t": r["t"], "run": run, "situation": situation, "source": source, "body": "tool0", "frame": "base",
                          "x_mm": round(r["px"] * 1000 + dx, 3), "y_mm": round(r["py"] * 1000, 3), "z_mm": round(r["pz"] * 1000, 3),
                          "quat_w": r6(q[0]), "quat_x": r6(q[1]), "quat_y": r6(q[2]), "quat_z": r6(q[3])})
            k = round(r["t"] / 0.04)
            # link poses at half the rate (12.5 Hz): the card slerps between rows, and the file stays under 1 MB
            if situation != "replay" and k % 2 == 0:
                row = {"t": r["t"], "run": run, "situation": situation, "source": source}
                for link in LINKS:
                    row[f"{link}_x"] = round(r[f"{link}_x"] * 1000 + dx, 3)
                    row[f"{link}_y"] = round(r[f"{link}_y"] * 1000, 3)
                    row[f"{link}_z"] = round(r[f"{link}_z"] * 1000, 3)
                    for c in "wxyz":
                        row[f"{link}_q{c}"] = r[f"{link}_q{c}"]
                links.append(row)
            if situation != "replay":
                base = 20 * math.sin(0.8 * r["t"] + (0.6 if device == "J4 wrist 1" else 0))
                off = {"real": 0.0, "twin": 0.9 * math.cos(1.7 * r["t"]), "target": -0.6}[situation]
                samples.append({"t": r["t"], "run": run, "situation": situation, "source": source, "device": device,
                                "q_deg": round(base + off + 0.002 * k, 4)})
    diffs = []
    for run, _dx, _device, _last in ARM_RUNS:
        b = [p for p in poses if p["run"] == run and p["situation"] == "target"]
        for a_name in ("real", "twin", "replay"):
            a = [p for p in poses if p["run"] == run and p["situation"] == a_name]
            for row in difference(a, b, "poses"):
                diffs.append({k: (round(v, 6) if isinstance(v, float) else v) for k, v in row.items()})
    link_fields = [{"name": "t", "type": "number", "unit": "s"}, {"name": "run", "type": "string"},
                   {"name": "situation", "type": "string"}, {"name": "source", "type": "string"}]
    for link in LINKS:
        link_fields += [{"name": f"{link}_{c}", "type": "number", "unit": "mm"} for c in "xyz"]
        link_fields += [{"name": f"{link}_q{c}", "type": "number"} for c in "wxyz"]
    diff_fields = POSE_FIELDS[:4] + [{"name": "reference", "type": "string"}] + POSE_FIELDS[4:] + [
        {"name": f"ref_{c}", "type": "number", "unit": "mm"} for c in ("x_mm", "y_mm", "z_mm")] + [
        {"name": "err_mm", "type": "number", "unit": "mm"}] + [
        {"name": f"ref_quat_{c}", "type": "number"} for c in "wxyz"] + [{"name": "err_rot_mrad", "type": "number", "unit": "mrad"}]
    runs = [{"run": run, "deployment": "UR5e cell (stand-in)", "started": f"2026-10-2{8 + i}T10:00:00-07:00", "duration_s": last,
             "kind": "coordinated", "devices": [device], "situations": ["target", "real", "twin", "replay"], "rate_hz": 25, "display_hz": 25}
            for i, (run, _dx, device, last) in enumerate(ARM_RUNS)]
    write(HERE / "arm" / "runs.json", "Runs (P1b arm fixture, stand-in)", [
        {"name": "run", "type": "string"}, {"name": "deployment", "type": "string"}, {"name": "started", "type": "datetime"},
        {"name": "duration_s", "type": "number", "unit": "s"}, {"name": "kind", "type": "string"}, {"name": "devices", "type": "array"},
        {"name": "situations", "type": "array"}, {"name": "rate_hz", "type": "number", "unit": "Hz"}, {"name": "display_hz", "type": "number", "unit": "Hz"}], runs)
    write(HERE / "arm" / "poses.json", "Tool poses (P1b arm fixture: pid-tuning's UR5e FK in mm, stand-in labels)", POSE_FIELDS, poses)
    write(HERE / "arm" / "links.json", "Link poses (P1b arm fixture: pid-tuning's UR5e FK in mm)", link_fields, links)
    write(HERE / "arm" / "samples.json", "Joint samples (P1b arm fixture: synthetic q_deg, the device rail)", [
        {"name": "t", "type": "number", "unit": "s"}, {"name": "run", "type": "string"}, {"name": "situation", "type": "string"},
        {"name": "source", "type": "string"}, {"name": "device", "type": "string"}, {"name": "q_deg", "type": "number", "unit": "deg"}], samples)
    write(HERE / "arm" / "diff_poses.json", "difference(a, target) per run (P1b arm fixture)", diff_fields, diffs)
    return len(poses), len(links), len(samples), len(diffs)


def main() -> None:
    write(HERE / "path.json", "Tool path (P1b fixture, synthetic: 564 samples at 100 Hz)", POSE_FIELDS, path_rows())
    write(HERE / "two-frames.json", "One body in two frames (P1b fixture, synthetic)", POSE_FIELDS, two_frames_rows())
    print("arm rows (poses, links, samples, diff):", arm())


if __name__ == "__main__":
    main()
