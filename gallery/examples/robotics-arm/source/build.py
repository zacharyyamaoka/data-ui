"""The Robot arm template's data (PEP 0010 P1c, docs/peps/0010-robotics-playback.md §6) on a STAND-IN: no real arm run
exists, so the UR5e here is simulation, labelled so in every table and on the page. Two runs of pidtuna.com's
"coordinated" tape (7.9 s, six joints), written as the trajectory contract's tables (gallery/robotics/CONTRACT.md):
runs.json, poses.json, samples.json, links.json and devices.json beside this folder.

    MUJOCO_GL=egl ~/pidtuna/.venv/bin/python -B -I gallery/examples/robotics-arm/source/build.py

  ur5e-suite/coordinated    sim2real's arm_suite_sim (~/sim2real/dashboards/source/arm_suite_sim.json, read-only): a
                            MuJoCo UR5e with a tool, run as the twin (family sim) and as a SYNTHETIC "real" plant, the
                            same model with four declared perturbations (payload, elbow friction, a wrist-1 encoder
                            offset, a camera shift), twice for its run-to-run floor ("real" and "real B", family real:
                            a stand-in, never measured); the target is the tape. Its 100 Hz rows picked at 25 Hz.
  ur5e-pidtuna/coordinated  pid-tuning's robot.json and samples.json (gallery/examples/pid-tuning, this repo): pidtuna's
                            MuJoCo replay of the tape under three tuning rungs (factory, tuned, oracle: family sim) and
                            the target, at robot.json's 25 Hz (samples.json's 50 Hz picked at 25 Hz).

What is computed here (the producer's job; data-ui computes none of it, CONTRACT §7): the tool's orientation, from the
wrist_3_link pose and the tool's fixed mounting (Menagerie's attachment_site, pos 0 0.1 0, quat −1 1 0 0: the same in
both sources) composed in quaternions; and, for the suite's target, which arm_suite_sim.json stores as joint angles and
a tool point only, the link poses by MuJoCo forward kinematics through arm_suite_sim.py's own kinematics() on its own
model (imported, read-only; the tool point it gives equals the file's tool_target, checked below). Every pose is
written in millimetres in the base frame; the links in the scene's unit (mm). Self-checks (refused if they fail): the
composed tool pose puts the tool point where each source wrote it, within 1e-6 mm.

Read-only: ~/sim2real/dashboards/source/arm_suite_sim.{json,py}, MuJoCo Menagerie's ur5e.xml (arm_suite_sim.py's
MENAGERIE), this repo's pid-tuning case; -B keeps Python's bytecode out of sim2real."""

from __future__ import annotations

import datetime
import json
import math
import os
import pathlib
import subprocess
import sys
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
os.environ.setdefault("MUJOCO_GL", "egl")

HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE.parent
REPO = CASE.parents[2]
SUITE_DIR = pathlib.Path(os.environ.get("ARM_SUITE_SIM", str(pathlib.Path.home() / "sim2real" / "dashboards" / "source")))
PIDTUNING = CASE.parent / "pid-tuning"
LOCAL = ZoneInfo("America/Vancouver")
DEPLOYMENT = "UR5e cell (stand-in)"
LINKS = ["base", "shoulder_link", "upper_arm_link", "forearm_link", "wrist_1_link", "wrist_2_link", "wrist_3_link"]
JOINTS = ["J1 shoulder pan", "J2 shoulder lift", "J3 elbow", "J4 wrist 1", "J5 wrist 2", "J6 wrist 3"]
PIDTUNA_JOINTS = ["shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint", "wrist_1_joint", "wrist_2_joint", "wrist_3_joint"]
SITE_POS = (0.0, 0.1, 0.0)            # the tool body on wrist_3_link (Menagerie attachment_site), metres
SITE_Q = (-math.sqrt(0.5), math.sqrt(0.5), 0.0, 0.0)   # its orientation, wxyz
TCP = (0.0, 0.0, 0.12)                # arm_suite_sim's tcp site in the tool body, metres
SUITE_STRIDE = 4                      # 100 Hz -> 25 Hz
# WHY links for two situations a run: a link row is 49 numbers, and the case stays a few MB; the mock draws the real and
# the twin robots (real B's is off), and the pidtuna run's tuned rung with the target as its ghost
ROBOTS = {"ur5e-suite/coordinated": {"real", "twin"}, "ur5e-pidtuna/coordinated": {"tuned", "target"}}
SUITE = {"run": "ur5e-suite/coordinated", "situations": [("target", "target", None), ("real", "real", "real_a"), ("real B", "real", "real_b"), ("twin", "sim", "twin")]}
PIDTUNA = {"run": "ur5e-pidtuna/coordinated", "situations": [("target", "target"), ("factory", "sim"), ("tuned", "sim"), ("oracle", "sim")]}


# --------------------------------------------------------------------------------------------- quaternions (wxyz)
def qmul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw)


def rotate(q, v):
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z)
    w, x, y, z = w / n, x / n, y / n, z / n
    p = qmul(qmul((w, x, y, z), (0.0, *v)), (w, -x, -y, -z))
    return p[1:]


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def r(v, digits):
    return None if v is None or not math.isfinite(v) else round(v, digits)


def tool_pose(w3_pos, w3_q, tip=(0.0, 0.0, 0.0)):
    """The tool's (or a point on it's) world position, metres, and its orientation (wxyz), from wrist_3_link's pose."""
    q = qmul(w3_q, SITE_Q)
    return add(w3_pos, rotate(w3_q, add(SITE_POS, rotate(SITE_Q, tip)))), q


def pose_row(t, run, situation, source, body, pos_m, q):
    return {"t": t, "run": run, "situation": situation, "source": source, "body": body, "frame": "base",
            "x_mm": r(pos_m[0] * 1000, 4), "y_mm": r(pos_m[1] * 1000, 4), "z_mm": r(pos_m[2] * 1000, 4),
            "quat_w": r(q[0], 7), "quat_x": r(q[1], 7), "quat_y": r(q[2], 7), "quat_z": r(q[3], 7)}


def link_row(t, run, situation, source, links):
    """links: {link: (x, y, z) metres, (w, x, y, z)}, written in the scene's unit (mm)."""
    row = {"t": t, "run": run, "situation": situation, "source": source}
    for name in LINKS:
        p, q = links[name]
        row.update({f"{name}_x": r(p[0] * 1000, 3), f"{name}_y": r(p[1] * 1000, 3), f"{name}_z": r(p[2] * 1000, 3),
                    f"{name}_qw": r(q[0], 6), f"{name}_qx": r(q[1], 6), f"{name}_qy": r(q[2], 6), f"{name}_qz": r(q[3], 6)})
    return row


# --------------------------------------------------------------------------------------------- run 1: arm_suite_sim
def suite():
    doc = json.loads((SUITE_DIR / "arm_suite_sim.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(SUITE_DIR))
    import arm_suite_sim as sim  # noqa: E402  its own model and kinematics, for the target's links
    import mujoco  # noqa: E402
    import numpy as np  # noqa: E402

    model = sim.build_model("twin")
    data = mujoco.MjData(model)
    run = SUITE["run"]
    poses, samples, links = [], [], []
    worst = 0.0
    for situation, source, key in SUITE["situations"]:
        rows = doc["runs"]["twin" if key is None else key]
        # every SUITE_STRIDE-th row, and the last: the display spans the run as simulated (0 to 7.9 s)
        for k in sorted(set(range(0, len(rows), SUITE_STRIDE)) | {len(rows) - 1}):
            row = rows[k]
            t = round(row["t"], 4)
            if key is None:
                fk = sim.kinematics(model, data, np.asarray(row["q_target"]))
                worst = max(worst, max(abs(a - b) for a, b in zip(fk["tool"], row["tool_target"])) * 1000)
                lk = {n: (fk["links"][n][:3], fk["links"][n][3:]) for n in LINKS}
                q = row["q_target"]
                tau = [None] * 6
                tip = tuple(row["tool_target"])
            else:
                lk = {n: (row["links"][n][:3], row["links"][n][3:]) for n in LINKS}
                q, tau, tip = row["q"], row["tau"], tuple(row["tool"])
            w3p, w3q = lk["wrist_3_link"]
            pos, quat = tool_pose(w3p, w3q, TCP)
            if key in (None, "twin"):  # noise-free situations: the composed pose must land on the file's tool point
                worst = max(worst, max(abs(a - b) for a, b in zip(pos, tip)) * 1000)
            # the stand-in's tool point carries its sensor noise (arm_suite_sim NOISE["tool"]): written as measured
            poses.append(pose_row(t, run, situation, source, "tcp", tip, quat))
            if situation in ROBOTS[run]:
                links.append(link_row(t, run, situation, source, lk))
            for j, name in enumerate(JOINTS):
                samples.append({"t": t, "run": run, "situation": situation, "source": source, "device": name,
                                "q_deg": r(math.degrees(q[j]), 5), "tau_nm": r(tau[j], 4)})
    assert worst <= 1e-6, f"the tool pose composed from wrist_3_link misses the file's tool point by {worst} mm"
    started = datetime.datetime.fromisoformat(doc["generated_at"].replace("Z", "+00:00")).astimezone(LOCAL)
    t_end = round(doc["runs"]["twin"][-1]["t"], 4)
    meta = {
        "run": run, "deployment": DEPLOYMENT, "started": started.isoformat(timespec="seconds"), "when": started.strftime("%b %d %H:%M"),
        "duration_s": t_end, "kind": "coordinated", "devices": JOINTS, "situations": [s for s, _, _ in SUITE["situations"]],
        "rate_hz": 100.0, "display_hz": 100.0 / SUITE_STRIDE, "label": "UR5e suite · coordinated tape · stand-in",
        "basis": "stand-in: sim2real's perturbed MuJoCo UR5e (no real arm run exists); real and real B are a synthetic plant, the twin the nominal model",
        "note": "; ".join(p["what"] for p in doc["perturbations"]), "source_file": "~/sim2real/dashboards/source/arm_suite_sim.json",
    }
    return meta, poses, samples, links, worst


# --------------------------------------------------------------------------------------------- run 2: pid-tuning
def pidtuna():
    robot = json.loads((PIDTUNING / "robot.json").read_text(encoding="utf-8"))
    tool = robot["robot"]["tool"]
    assert tool["link"] == "wrist_3_link" and tuple(tool["pos"]) == SITE_POS and max(abs(a - b) for a, b in zip(tool["quat"], SITE_Q)) < 1e-12, tool
    src = json.loads((PIDTUNING / "samples.json").read_text(encoding="utf-8"))["rows"]
    run = PIDTUNA["run"]
    keep = {s for s, _ in PIDTUNA["situations"]}
    fam = dict(PIDTUNA["situations"])
    poses, links = [], []
    worst = 0.0
    for row in robot["rows"]:
        if row["situation"] not in keep:
            continue
        lk = {n: ((row[f"{n}_x"], row[f"{n}_y"], row[f"{n}_z"]), (row[f"{n}_qw"], row[f"{n}_qx"], row[f"{n}_qy"], row[f"{n}_qz"])) for n in LINKS}
        pos, quat = tool_pose(*lk["wrist_3_link"])
        # robot.json rounds every metre to 1 µm, so the composed point and the stored one agree to that
        worst = max(worst, max(abs(a - b) for a, b in zip(pos, (row["px"], row["py"], row["pz"]))) * 1000)
        t = round(row["t"], 4)
        poses.append(pose_row(t, run, row["situation"], fam[row["situation"]], "tool0", (row["px"], row["py"], row["pz"]), quat))
        if row["situation"] in ROBOTS[run]:
            links.append(link_row(t, run, row["situation"], fam[row["situation"]], lk))
    assert worst <= 0.002, f"the tool pose composed from wrist_3_link misses robot.json's tool point by {worst} mm"
    pose_t = sorted({p["t"] for p in poses})
    at = set(pose_t)  # samples.json's 50 Hz picked at robot.json's 25 Hz rows
    samples = []
    for s in src:
        if s["situation"] not in keep or round(s["t"], 4) not in at:
            continue
        samples.append({"t": round(s["t"], 4), "run": run, "situation": s["situation"], "source": fam[s["situation"]],
                        "device": JOINTS[PIDTUNA_JOINTS.index(s["joint"])], "q_deg": r(s["q_deg"], 5), "tau_nm": None})
    commit = subprocess.run(["git", "-C", str(pathlib.Path.home() / "pidtuna-website"), "log", "-1", "--format=%cI", "c02e786"],
                            capture_output=True, text=True, check=False).stdout.strip()
    started = datetime.datetime.fromisoformat(commit or "2026-10-26T15:04:10-07:00").astimezone(LOCAL)
    meta = {
        "run": run, "deployment": DEPLOYMENT, "started": started.isoformat(timespec="seconds"), "when": started.strftime("%b %d %H:%M"),
        "duration_s": pose_t[-1], "kind": "coordinated", "devices": JOINTS, "situations": [s for s, _ in PIDTUNA["situations"]],
        "rate_hz": 100.0, "display_hz": 25.0, "label": "UR5e pidtuna · coordinated tape · sim ladder",
        "basis": "stand-in: pidtuna's MuJoCo replay of the tape under three tuning rungs (simulation, illustrative plant)",
        "note": "factory, tuned and oracle are controller rungs on one simulated plant; the export at pidtuna-website c02e786",
        "source_file": "gallery/examples/pid-tuning/robot.json, samples.json",
    }
    return meta, poses, samples, links, worst


# --------------------------------------------------------------------------------------------- the files
def write(path, title, source, fields, rows):
    one = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"), allow_nan=False)  # noqa: E731
    head = one({"title": title, "source": source, "schema": {"fields": fields}})
    path.write_text(head[:-1] + ',"rows":[\n' + ",\n".join(one(x) for x in rows) + "\n]}\n", encoding="utf-8")


def fields_of(table, extra=()):
    """The contract's sidecar fields for this table (gallery/robotics/schemas), in its order, then `extra`."""
    contract = json.loads((REPO / "gallery" / "robotics" / "schemas" / f"{table}.schema.json").read_text(encoding="utf-8"))["schema"]["fields"]
    return contract, list(extra)


def main() -> int:
    m1, p1, s1, l1, w1 = suite()
    m2, p2, s2, l2, w2 = pidtuna()
    runs = [m1, m2]
    labels = {m["run"]: m["label"] for m in runs}
    src = ("STAND-IN, simulation only: ~/sim2real/dashboards/source/arm_suite_sim.json (sim2real's perturbed MuJoCo UR5e) and "
           "gallery/examples/pid-tuning (pidtuna's MuJoCo replay); written by gallery/examples/robotics-arm/source/build.py")
    keep = lambda table, names, add=(): [f for f in fields_of(table)[0] if f["name"] in names] + list(add)  # noqa: E731
    run_field = {"name": "run", "type": "string", "title": "Run", "labels": labels}
    write(CASE / "runs.json", "Runs (stand-in): the UR5e's coordinated tape, two ways", src,
          [run_field if f["name"] == "run" else f for f in keep("runs", {"run", "deployment", "started", "duration_s", "kind", "devices", "situations", "rate_hz", "display_hz", "label", "basis", "note"})]
          + [{"name": "when", "type": "string", "title": "Started", "description": "started, as the table shows it"},
             {"name": "source_file", "type": "string", "title": "From"}], runs)
    poses = p1 + p2
    write(CASE / "poses.json", "Tool poses (stand-in): the tcp (suite) and tool0 (pidtuna) in the base frame, mm", src,
          [run_field if f["name"] == "run" else f for f in keep("poses", set(poses[0]))], poses)
    samples = s1 + s2
    write(CASE / "samples.json", "Joint samples (stand-in): q per joint, τ where the source has it", src,
          [run_field if f["name"] == "run" else f for f in keep("samples", {"t", "run", "situation", "source", "device", "q_deg", "tau_nm"})], samples)
    lfields = keep("links", {"t", "run", "situation", "source"}) + [
        {"name": f"{n}_{c}", "type": "number", **({"unit": "mm"} if c in "xyz" else {})} for n in LINKS for c in ("x", "y", "z", "qw", "qx", "qy", "qz")]
    write(CASE / "links.json", "Link poses (stand-in): each UR5e link's world pose, mm, for the meshed robot", src,
          [run_field if f["name"] == "run" else f for f in lfields], l1 + l2)
    devices = [{"device": name, "type": "servo", "label": f"{name} (UR5e joint)", "parent": "UR5e", "order": i + 1} for i, name in enumerate(JOINTS)]
    write(CASE / "devices.json", "Devices (stand-in): the UR5e's six joints", src,
          [{"name": "device", "type": "string"}, {"name": "type", "type": "string"}, {"name": "label", "type": "string"},
           {"name": "parent", "type": "string"}, {"name": "order", "type": "integer"}], devices)
    sizes = {n: (CASE / f"{n}.json").stat().st_size for n in ("runs", "poses", "samples", "links", "devices")}
    print(json.dumps({"poses": len(poses), "samples": len(samples), "links": len(l1 + l2), "tool point worst mm": [w1, w2], "bytes": sizes, "total": sum(sizes.values())}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
