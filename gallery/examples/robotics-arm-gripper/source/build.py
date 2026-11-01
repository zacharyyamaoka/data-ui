"""The Arm + gripper template's data (PEP 0010 P4, docs/peps/0010-robotics-playback.md §6, the arm-gripper.png mock) on
STAND-INS, labelled so in every table and on the page: no real arm run and no gripper log exist (2026-10-29).

    python3 -B -I gallery/examples/robotics-arm-gripper/source/build.py        (numpy only)

The ARM is sim2real's stand-in (~/sim2real/dashboards/source/arm_suite_sim.json, read-only): a MuJoCo UR5e with a tool on
pidtuna.com's 7.9 s "coordinated" tape, run as the twin (family sim) and as a SYNTHETIC "real" plant (the same model with
four declared perturbations; never measured); the target is the tape's tool point. Its 100 Hz rows are picked at 25 Hz.
poses.json holds the tool point (body tcp, frame base) in millimetres for target, real and twin.

The GRIPPER is ILLUSTRATIVE, made here from a stated rule on that same run, so its events sit where the arm's path says a
pick and a place happen:
  - contact: the target tool's lowest point in [1.0, 2.0] s (the tape's first dip, the pick);
  - grasp: CLOSE_S later, when the fingers have closed on a 38 mm object and the commanded force is on;
  - release: the target tool's lowest point in [4.5, 5.5] s (the second dip, the place); the fingers reopen over OPEN_S.
  target = the command (width 85 → 38 → 85 mm, force 0 → 20 → 0 N); twin = a first-order lag (30 ms) on a rigid object;
  real = a 40 ms lag, 0.8 mm of object compliance, 1.5 N of force ripple at 6 rad/s and seeded noise (σ 0.05 mm, 0.15 N).
  coverage_samples.json: GRASPS illustrative grasps (seed SEED): width at grasp ~ N(38, 4) mm, force at grasp ~ N(20, 1.5) N,
  one row each (w = 1), so the coverage histogram has a shape to show. None of it is measured.
Writes runs.json, poses.json, samples.json (the gripper's width_mm, force_n, grip), events.json (contact, grasp, release),
devices.json and coverage_samples.json beside this folder.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import pathlib
import sys
from zoneinfo import ZoneInfo

import numpy as np

CASE = pathlib.Path(__file__).resolve().parents[1]
SUITE = pathlib.Path(os.environ.get("ARM_SUITE_SIM", str(pathlib.Path.home() / "sim2real" / "dashboards" / "source" / "arm_suite_sim.json")))
LOCAL = ZoneInfo("America/Vancouver")
RUN = "ur5e-suite/coordinated"
DEPLOYMENT = "UR5e cell (stand-in)"
STRIDE = 4                      # 100 Hz -> 25 Hz (the arm template's rate)
SITUATIONS = (("target", "target", None), ("real", "real", "real_a"), ("twin", "sim", "twin"))
OPEN_MM, OBJECT_MM, FORCE_N = 85.0, 38.0, 20.0
CLOSE_S, OPEN_S = 0.30, 0.40
SEED, GRASPS = 7, 300
STAND_IN = "stand-in: the arm is sim2real's MuJoCo UR5e (synthetic real, never measured); the gripper is illustrative, made by source/build.py"


def r(v, digits):
    v = float(v)
    return round(v, digits) if math.isfinite(v) else None


def lag(t, cmd, tau):
    """A first-order lag of `cmd` sampled at `t` (exact discretisation per step)."""
    out = np.empty_like(cmd)
    out[0] = cmd[0]
    for i in range(1, t.size):
        a = math.exp(-(t[i] - t[i - 1]) / tau)
        out[i] = a * out[i - 1] + (1 - a) * cmd[i]
    return out


def gripper(t, contact, grasp, release, rng):
    """{situation: (width_mm, force_n, grip)} on the times `t`."""
    width_cmd = np.where(t < contact, OPEN_MM, np.where(t < grasp, OPEN_MM - (t - contact) / (grasp - contact) * (OPEN_MM - OBJECT_MM),
                         np.where(t < release, OBJECT_MM, np.minimum(OPEN_MM, OBJECT_MM + (t - release) / OPEN_S * (OPEN_MM - OBJECT_MM)))))
    force_cmd = np.where((t >= grasp) & (t < release), FORCE_N, 0.0)
    grip = np.where(t < contact, "open", np.where(t < grasp, "closing", np.where(t < release, "holding", "open")))
    twin_w = np.maximum(lag(t, width_cmd, 0.030), np.where((t >= grasp) & (t < release), OBJECT_MM, -np.inf))
    twin_f = lag(t, force_cmd, 0.030)
    hold = (t >= grasp) & (t < release)
    real_w = np.maximum(lag(t, width_cmd, 0.040), np.where(hold, OBJECT_MM + 0.8, -np.inf)) + rng.normal(0, 0.05, t.size)
    real_f = lag(t, force_cmd, 0.040) + np.where(hold, 2.0 + 1.5 * np.sin(6 * t), 0.0) + np.where(hold, rng.normal(0, 0.15, t.size), 0.0)
    return {"target": (width_cmd, force_cmd, grip), "real": (real_w, real_f, grip), "twin": (twin_w, twin_f, grip)}


def write(path: pathlib.Path, title: str, source: str, fields: list[dict], rows: list[dict]) -> None:
    one = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"), allow_nan=False)  # noqa: E731
    head = one({"title": title, "source": source, "schema": {"fields": fields}})
    path.write_text(head[:-1] + ',"rows":[\n' + ",\n".join(one(x) for x in rows) + "\n]}\n", encoding="utf-8")


def main() -> int:
    doc = json.loads(SUITE.read_text(encoding="utf-8"))
    rows = {k: doc["runs"][k] for k in ("twin", "real_a")}
    n = len(rows["twin"])
    picks = sorted(set(range(0, n, STRIDE)) | {n - 1})
    t_all = np.array([row["t"] for row in rows["twin"]])
    z_target = np.array([row["tool_target"][2] for row in rows["twin"]]) * 1000
    pick = lambda lo, hi: float(t_all[(t_all >= lo) & (t_all <= hi)][np.argmin(z_target[(t_all >= lo) & (t_all <= hi)])])  # noqa: E731
    contact = round(pick(1.0, 2.0), 4)
    grasp = round(contact + CLOSE_S, 4)
    release = round(pick(4.5, 5.5), 4)
    t = np.round(t_all[picks], 4)
    rng = np.random.default_rng(SEED)
    grip = gripper(t, contact, grasp, release, rng)
    src = ("~/sim2real/dashboards/source/arm_suite_sim.json (the stand-in arm, read-only) and this case's illustrative gripper; "
           "written by gallery/examples/robotics-arm-gripper/source/build.py")
    poses, samples = [], []
    for situation, source, key in SITUATIONS:
        for k in picks:
            row = rows["twin" if key is None else key][k]
            p = row["tool_target"] if key is None else row["tool"]
            poses.append({"t": round(row["t"], 4), "run": RUN, "situation": situation, "source": source, "body": "tcp", "frame": "base",
                          "x_mm": r(p[0] * 1000, 4), "y_mm": r(p[1] * 1000, 4), "z_mm": r(p[2] * 1000, 4)})
        w, f, g = grip[situation]
        for i, tk in enumerate(t):
            samples.append({"t": float(tk), "run": RUN, "situation": situation, "source": source, "device": "gripper",
                            "width_mm": r(w[i], 3), "force_n": r(f[i], 3), "grip": str(g[i])})
    events = [{"t": contact, "run": RUN, "device": "gripper", "kind": "contact", "label": "contact"},
              {"t": grasp, "run": RUN, "device": "gripper", "kind": "grasp", "label": "grasp"},
              {"t": release, "run": RUN, "device": "gripper", "kind": "release", "label": "release"}]
    rng2 = np.random.default_rng(SEED + 1)
    widths = np.clip(rng2.normal(OBJECT_MM, 4.0, GRASPS), 26.0, 52.0)
    forces = np.clip(rng2.normal(FORCE_N, 1.5, GRASPS), 14.0, 26.0)
    coverage = [{"t": grasp, "run": f"illustrative/grasp-{i + 1:03d}", "situation": "real", "source": "real", "device": "gripper",
                 "width_mm": r(widths[i], 3), "force_n": r(forces[i], 3), "w": 1} for i in range(GRASPS)]
    started = datetime.datetime.fromisoformat(doc["generated_at"].replace("Z", "+00:00")).astimezone(LOCAL)
    runs = [{"run": RUN, "deployment": DEPLOYMENT, "started": started.isoformat(timespec="seconds"), "when": started.strftime("%b %d %H:%M"),
             "duration_s": float(t[-1]), "kind": "coordinated tape, pick and place", "devices": ["tcp", "gripper"], "situations": [s for s, _, _ in SITUATIONS],
             "rate_hz": 100.0, "display_hz": 25.0, "label": "coordinated · UR5e stand-in + illustrative gripper", "basis": "stand-in", "note": STAND_IN}]
    devices = [{"device": "tcp", "type": "eef", "label": "Tool (EEF) · stand-in UR5e", "parent": "arm", "order": 1},
               {"device": "gripper", "type": "gripper", "label": "Gripper · illustrative (none logged yet)", "parent": "tcp", "order": 2}]
    write(CASE / "runs.json", "Runs: one stand-in run (UR5e simulation + an illustrative gripper)", src, [
        {"name": "run", "type": "string", "title": "Run"}, {"name": "deployment", "type": "string", "title": "Deployment"},
        {"name": "started", "type": "datetime", "title": "Started at", "description": "when sim2real generated the stand-in"},
        {"name": "when", "type": "string", "title": "Started"}, {"name": "duration_s", "type": "number", "unit": "s", "title": "Duration"},
        {"name": "kind", "type": "string", "title": "Kind"}, {"name": "devices", "type": "array", "title": "Devices"},
        {"name": "situations", "type": "array", "title": "Situations"}, {"name": "rate_hz", "type": "number", "unit": "Hz", "title": "Simulated at"},
        {"name": "display_hz", "type": "number", "unit": "Hz", "title": "Shown at"}, {"name": "label", "type": "string", "title": "Label"},
        {"name": "basis", "type": "string", "title": "Basis"}, {"name": "note", "type": "string", "title": "Note"},
    ], runs)
    write(CASE / "poses.json", "Poses: the stand-in arm's tool point (target, synthetic real, twin), mm in the base frame", src, [
        {"name": "t", "type": "number", "unit": "s"}, {"name": "run", "type": "string", "title": "Run"},
        {"name": "situation", "type": "string", "title": "Situation"}, {"name": "source", "type": "string", "title": "Family"},
        {"name": "body", "type": "string"}, {"name": "frame", "type": "string"},
        {"name": "x_mm", "type": "number", "unit": "mm", "title": "x"}, {"name": "y_mm", "type": "number", "unit": "mm", "title": "y"},
        {"name": "z_mm", "type": "number", "unit": "mm", "title": "EEF z", "description": "the tool point's height in the base frame (stand-in)"},
    ], poses)
    write(CASE / "samples.json", "Samples: the illustrative gripper (target, synthetic real, twin)", src, [
        {"name": "t", "type": "number", "unit": "s"}, {"name": "run", "type": "string", "title": "Run"},
        {"name": "situation", "type": "string", "title": "Situation"}, {"name": "source", "type": "string", "title": "Family"},
        {"name": "device", "type": "string", "title": "Device"},
        {"name": "width_mm", "type": "number", "unit": "mm", "title": "Gripper width", "description": "finger opening: ILLUSTRATIVE (no gripper logged yet)"},
        {"name": "force_n", "type": "number", "unit": "N", "title": "Grip force", "description": "ILLUSTRATIVE"},
        {"name": "grip", "type": "string", "title": "Grip", "description": "open, closing or holding"},
    ], samples)
    write(CASE / "events.json", "Events: the illustrative gripper's contact, grasp and release", src, [
        {"name": "t", "type": "number", "unit": "s", "description": "contact and release at the stand-in target path's two low points; grasp 0.3 s after contact"},
        {"name": "run", "type": "string", "title": "Run"}, {"name": "device", "type": "string"},
        {"name": "kind", "type": "string", "title": "Event"}, {"name": "label", "type": "string"},
    ], events)
    write(CASE / "devices.json", "Devices: the stand-in tool and the illustrative gripper", src, [
        {"name": "device", "type": "string"}, {"name": "type", "type": "string"}, {"name": "label", "type": "string"},
        {"name": "parent", "type": "string"}, {"name": "order", "type": "integer"},
    ], devices)
    write(CASE / "coverage_samples.json", f"Coverage: {GRASPS} ILLUSTRATIVE grasps (width and force at grasp), seed {SEED}", src, [
        {"name": "t", "type": "number", "unit": "s"}, {"name": "run", "type": "string", "title": "Grasp", "description": "an illustrative grasp, not a run"},
        {"name": "situation", "type": "string"}, {"name": "source", "type": "string", "title": "Family"}, {"name": "device", "type": "string"},
        {"name": "width_mm", "type": "number", "unit": "mm", "title": "Width at grasp", "description": "ILLUSTRATIVE: N(38, 4) mm, clipped to 26-52"},
        {"name": "force_n", "type": "number", "unit": "N", "title": "Force at grasp", "description": "ILLUSTRATIVE: N(20, 1.5) N, clipped to 14-26"},
        {"name": "w", "type": "integer", "title": "Weight"},
    ], coverage)
    sizes = {p.name: p.stat().st_size for p in sorted(CASE.iterdir()) if p.is_file() and p.suffix == ".json"}
    print(json.dumps({"events": events, "poses": len(poses), "samples": len(samples), "coverage": len(coverage), "bytes": sizes}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
