"""How far the 3D card's robot is from true forward kinematics BETWEEN robot.json's 25 Hz rows (judge round 1, item 9).

    ~/pidtuna/.venv/bin/python gallery/examples/pid-tuning/source/measure_robot_interp.py

The card lerps link positions and slerps link orientations between rows (packages/views/scene3d/src/math.js). The truth
between rows is MuJoCo's forward kinematics of the replay's joint angles at t, linearly interpolated between the
replay's own 100 Hz samples (`joint_at` below; build_replay.py `at` answers only ON a sample, so it cannot be used
between them). This walks EVERY point of the advertised grid (19 points inside each 25 Hz interval, every situation,
every link), asserts that none was skipped, and prints the worst position error (m), rotation error (rad), the 95th
percentile and the number of points evaluated. At the rows themselves
the card is exact (checks_robot.py, within 1e-6); this is the error in between."""

import importlib.util
import json
import math
import pathlib

import numpy as np

HERE = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_robot", pathlib.Path(__file__).with_name("build_robot.py"))
robot_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(robot_mod)
replay = robot_mod.replay


def slerp(qa, qb, f):
    qa, qb = np.array(qa), np.array(qb)
    d = float(np.dot(qa, qb))
    if d < 0:
        qb, d = -qb, -d
    if d > 0.9995:
        q = qa + f * (qb - qa)
        return q / np.linalg.norm(q)
    th = math.acos(d)
    return (math.sin((1 - f) * th) * qa + math.sin(f * th) * qb) / math.sin(th)


def joint_at(series, dt, t):
    """A joint angle at any t inside its series: linear between the replay's own samples (its t0 and dt); None outside."""
    x = (t - series["t0"]) / dt
    if x < -1e-9 or x > len(series["q"]) - 1 + 1e-9:
        return None
    i = min(int(math.floor(x + 1e-9)), len(series["q"]) - 2)
    f = min(1.0, max(0.0, x - i))
    return series["q"][i] + (series["q"][i + 1] - series["q"][i]) * f


def main():
    import mujoco
    data_json = json.loads((HERE / "robot.json").read_text())
    rows = data_json["rows"]
    robot = json.loads((replay.DATA / "ur5e.json").read_text(encoding="utf-8"))
    tape = replay.tape_of(robot, "coordinated")
    dt = tape["dt"]
    model, data = replay.load_model(mujoco, for_render=False)
    bodies = replay.chain(model)
    links = [model.body(b).name for b in bodies]
    worst = {l: [0.0, 0.0, None] for l in links}
    errs = []
    expected = 0
    for situation in robot_mod.SITUATIONS:
        rs = sorted((r for r in rows if r["situation"] == situation), key=lambda r: r["t"])
        for a, b in zip(rs, rs[1:]):
            expected += 19 * len(links)
            for k in range(1, 20):
                f = k / 20
                t = a["t"] + (b["t"] - a["t"]) * f
                angles = {}
                for joint in robot["joints"]:
                    series = tape["target"][joint["name"]] if situation == "target" else tape["rungs"][situation][joint["name"]]
                    angles[joint["name"]] = joint_at(series, dt, t)
                # every point lies between two rows the producer wrote, so every joint has a value there; none is skipped
                assert all(v is not None for v in angles.values()), (situation, t)
                replay.pose(model, data, mujoco, robot, angles)
                for bi, name in zip(bodies, links):
                    lerp = np.array([a[f"{name}_{c}"] + (b[f"{name}_{c}"] - a[f"{name}_{c}"]) * f for c in "xyz"])
                    dp = float(np.linalg.norm(lerp - data.xpos[bi]))
                    q = slerp([a[f"{name}_q{c}"] for c in "wxyz"], [b[f"{name}_q{c}"] for c in "wxyz"], f)
                    dq = 2 * math.acos(min(1.0, abs(float(np.dot(q, data.xquat[bi])))))
                    errs.append(dp)
                    if dp > worst[name][0]:
                        worst[name][0], worst[name][2] = dp, (situation, round(t, 4))
                    worst[name][1] = max(worst[name][1], dq)
    assert len(errs) == expected, f"evaluated {len(errs)} link samples, the grid has {expected}"
    errs.sort()
    out = {"grid": "19 points inside every 25 Hz interval (2 ms apart), every situation and link", "samples": len(errs), "expected": expected,
           "p95_m": errs[int(0.95 * len(errs))], "max_m": errs[-1],
           "per_link": {l: {"max_m": round(v[0], 7), "max_rad": round(v[1], 7), "at": v[2]} for l, v in worst.items()}}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
