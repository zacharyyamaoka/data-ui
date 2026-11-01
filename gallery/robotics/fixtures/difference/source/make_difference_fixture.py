#!/usr/bin/env python3
"""Rebuild the difference(a, b) fixture (gallery/robotics/CONTRACT.md §5) from nothing but this file:

    uv run --with numpy --with scipy python3 gallery/robotics/fixtures/difference/source/make_difference_fixture.py

Two trajectories of one run, a = situation "real" and b = situation "target", written as a producer writes the
contract's tables (poses.json, samples.json: {schema, rows}, the schema copied from ../../schemas/), and the rows
difference(a, b) must return (diff_poses.json, diff_samples.json). The expected rows are computed here with numpy
(linear interpolation, exact at b's own samples) and scipy's Rotation and Slerp (orientations, the short way; the angle
between two orientations; the canonical sign), from the files as written: the inputs are written first and read back,
so the expected rows come from exactly the numbers every reader of the files sees. tools/test_robotics_fixture.py
reproduces every row with an independent, stdlib-only difference(a, b).

The trajectories are synthetic on purpose: each case the spec names sits where it can be seen (README.md beside the
files lists them). Deterministic: a fixed seed, no clock, no machine-dependent value in the files."""

import json
import math
import pathlib
import platform

import numpy as np
import scipy
from scipy.spatial.transform import Rotation, Slerp

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent
SCHEMAS = OUT.parent.parent / "schemas"
SEED = 20261029
A, B = "real", "target"
RUN, RUN_A_ONLY = "fixture/r1", "fixture/r2"
POS = ("x_mm", "y_mm", "z_mm")
QUAT = ("quat_w", "quat_x", "quat_y", "quat_z")
REVOLUTE, PRISMATIC, DEVICE_A_ONLY = "J3 elbow", "Z lift", "J1 base"

rng = np.random.default_rng(SEED)


# --------------------------------------------------------------------------------------------- the trajectories
def b_times():
    """b: the target at 25 Hz from 0 to 1.6 s (41 samples)."""
    return [round(k / 25, 6) for k in range(41)]


def a_times(tb, start=-0.05, end=1.75):
    """a: the real run at a jittered 94.4 Hz, starting before b and ending after it, with three samples exactly on
    b's: its first, an interior one (0.4 s) and its last."""
    out, t = [], start
    while t <= end:
        out.append(round(t + rng.uniform(-0.0015, 0.0015), 6))
        t += 1 / 94.4
    for exact in (tb[0], tb[10], tb[-1]):
        k = min(range(len(out)), key=lambda i: abs(out[i] - exact))
        out[k] = exact
    out = sorted(set(out))
    assert all(x < y for x, y in zip(out, out[1:]))
    return out


def path_mm(t):
    """The target's tool path, mm."""
    w = 2 * math.pi * t / 1.6
    return (-600 + 150 * math.sin(w), -150 + 120 * math.sin(2 * w), 300 + 80 * math.cos(w))


def yaw_deg(t, stepped):
    """A steady turn with a wobble; `stepped` adds the 150° turn between b's samples 20 and 21 (0.80 → 0.84 s), where
    slerp and nlerp part by degrees, and which carries the yaw past 180°, so b's quaternions go to w < 0."""
    w = 2 * math.pi * t / 1.6
    return 120 * t / 1.6 + 40 * math.sin(w) + (150 if stepped else 0)


def rotation(t, stepped):
    w = 2 * math.pi * t / 1.6
    return Rotation.from_euler("ZYX", [yaw_deg(t, stepped), 20 * math.cos(w), 10], degrees=True)


def continuous(quats):
    """Quaternions written as a smooth track: each one's sign keeps the dot with the one before positive."""
    out = [np.asarray(quats[0], float)]
    for q in quats[1:]:
        q = np.asarray(q, float)
        out.append(-q if np.dot(out[-1], q) < 0 else q)
    return out


def wxyz(r):
    return r.as_quat(scalar_first=True)


# --------------------------------------------------------------------------------------------- the producer's rows
def poses_rows(tb, ta, ta2):
    rows = []
    # b, the target: tool0 and lever_tip in base. Its quaternions as a smooth track, but for one sample written with
    # the other sign (k = 30): the slerp from 29 to 30 and from 30 to 31 must take the short way
    qb = continuous([wxyz(rotation(t, k >= 21)) for k, t in enumerate(tb)])
    qb[30] = -qb[30]
    for k, t in enumerate(tb):
        x, y, z = path_mm(t)
        for body, dz in (("tool0", 0.0), ("lever_tip", -50.0)):
            rows.append({"t": t, "run": RUN, "situation": B, "source": "target", "body": body, "frame": "base",
                         "x_mm": round(x, 4), "y_mm": round(y, 4), "z_mm": round(z + dz, 4), **dict(zip(QUAT, (round(float(c), 9) for c in qb[k])))})
    # a, the real run: tracks b 30 ms late with a small wobble and noise; tool0 in base, lever_tip in belt (b writes it
    # in base: no rows), camera_link only in a (no rows)
    lag = 0.03
    qa = continuous([wxyz(rotation(t - lag, t - lag >= 0.84) * Rotation.from_rotvec([0.003 * math.sin(5 * t), 0, 0])) for t in ta])
    for i, t in enumerate(ta):
        x, y, z = path_mm(t - lag)
        x, y, z = x + 0.8 * math.sin(9 * t) + rng.normal(0, 0.2), y + 0.6 * math.cos(7 * t) + rng.normal(0, 0.2), z + rng.normal(0, 0.2)
        q = np.asarray(qa[i], float)
        if i % 7 == 3:
            q = -q  # a written with the other sign: the angle to b stays the small one (|⟨a, b⟩|)
        if i == 40:
            q = q * 1.000002  # not unit: every implementation normalizes before it measures
        quat = dict(zip(QUAT, (round(float(c), 9) for c in q)))
        for body, frame, dz in (("tool0", "base", 0.0), ("lever_tip", "belt", -50.0), ("camera_link", "base", 120.0)):
            rows.append({"t": t, "run": RUN, "situation": A, "source": "real", "body": body, "frame": frame,
                         "x_mm": round(x, 4), "y_mm": round(y, 4), "z_mm": round(z + dz, 4), **quat})
    # a run b never played: no rows
    for t in ta2:
        x, y, z = path_mm(t)
        rows.append({"t": t, "run": RUN_A_ONLY, "situation": A, "source": "real", "body": "tool0", "frame": "base",
                     "x_mm": round(x, 4), "y_mm": round(y, 4), "z_mm": round(z, 4), **dict(zip(QUAT, (round(float(c), 9) for c in wxyz(rotation(t, False)))))})
    return rows


SAMPLE_COLUMNS = ("q_deg", "qd_deg_s", "tau_nm", "q_mm", "qd_mm_s")


def joint(t):
    w = 2 * math.pi * t / 1.6
    return 30 * math.sin(w) + 10, 30 * (2 * math.pi / 1.6) * math.cos(w), 2.5 * math.sin(2 * math.pi * t / 0.8)


def lift(t):
    w = 2 * math.pi * t / 1.6
    return 100 + 50 * math.sin(w), 50 * (2 * math.pi / 1.6) * math.cos(w)


def sample(t, run, situation, source, device, **channels):
    row = {"t": t, "run": run, "situation": situation, "source": source, "device": device}
    row.update({c: channels.get(c) for c in SAMPLE_COLUMNS})
    return row


def samples_rows(tb, ta, ta2):
    rows = []
    for k, t in enumerate(tb):
        q, qd, tau = joint(t)
        # a null in b (k = 15): the error next to it is null, never a number made from 0
        rows.append(sample(t, RUN, B, "target", REVOLUTE, q_deg=round(q, 5), qd_deg_s=round(qd, 4), tau_nm=None if k == 15 else round(tau, 5)))
        p, pd = lift(t)
        rows.append(sample(t, RUN, B, "target", PRISMATIC, q_mm=round(p, 4), qd_mm_s=round(pd, 4)))
    lag = 0.02
    for i, t in enumerate(ta):
        q, qd, tau = joint(t - lag)
        rows.append(sample(t, RUN, A, "real", REVOLUTE, q_deg=round(q + 0.3 * math.sin(11 * t) + rng.normal(0, 0.05), 5),
                           qd_deg_s=None if i == 50 else round(qd + rng.normal(0, 0.5), 4), tau_nm=round(tau + rng.normal(0, 0.1), 5)))
        p, pd = lift(t - lag)
        rows.append(sample(t, RUN, A, "real", PRISMATIC, q_mm=round(p + rng.normal(0, 0.05), 4), qd_mm_s=round(pd + rng.normal(0, 0.5), 4)))
        rows.append(sample(t, RUN, A, "real", DEVICE_A_ONLY, q_deg=round(5 * math.sin(t), 5), qd_deg_s=round(5 * math.cos(t), 4), tau_nm=0.1))
    for t in ta2:
        q, qd, tau = joint(t)
        rows.append(sample(t, RUN_A_ONLY, A, "real", REVOLUTE, q_deg=round(q, 5), qd_deg_s=round(qd, 4), tau_nm=round(tau, 5)))
    return rows


# --------------------------------------------------------------------------------------------- the expected rows
def bracket(tb, t):
    """(i, f): t at b's sample i exactly (f None), or between i and i + 1 at fraction f; None outside b's span."""
    if t < tb[0] or t > tb[-1]:
        return None
    i = int(np.searchsorted(tb, t, side="right")) - 1
    if tb[i] == t:
        return i, None
    return i, (t - tb[i]) / (tb[i + 1] - tb[i])


def groups(rows, keys):
    out = {}
    for r in rows:
        out.setdefault(tuple(r[k] for k in keys), []).append(r)
    for g in out.values():
        ts = [r["t"] for r in g]
        assert all(x < y for x, y in zip(ts, ts[1:])), "b's times rise strictly within a key"
    return out


def expected_poses(rows):
    a = [r for r in rows if r["situation"] == A]
    b = groups([r for r in rows if r["situation"] == B], ("run", "body", "frame"))
    interp = {}
    for key, g in b.items():
        tb = np.array([r["t"] for r in g])
        pos = np.array([[r[c] for c in POS] for r in g])
        rot = Rotation.from_quat([[r[c] for c in QUAT] for r in g], scalar_first=True)
        interp[key] = (tb, pos, rot, Slerp(tb, rot))
    out = []
    for r in a:
        key = (r["run"], r["body"], r["frame"])
        if key not in interp:
            continue
        tb, pos, rot, slerp = interp[key]
        where = bracket(tb, r["t"])
        if where is None:
            continue
        i, f = where
        if f is None:
            ref, qref = pos[i], rot[i]
        else:
            ref, qref = pos[i] + f * (pos[i + 1] - pos[i]), slerp([r["t"]])[0]
        a_pos = np.array([r[c] for c in POS])
        a_rot = Rotation.from_quat([r[c] for c in QUAT], scalar_first=True)
        row = {"t": r["t"], "run": r["run"], "situation": r["situation"], "source": r["source"], "reference": B,
               "body": r["body"], "frame": r["frame"], **{c: r[c] for c in POS},
               **{f"ref_{c}": float(v) for c, v in zip(POS, ref)}, "err_mm": float(np.linalg.norm(ref - a_pos)),
               **{c: r[c] for c in QUAT},
               **{f"ref_{c}": float(v) for c, v in zip(QUAT, qref.as_quat(canonical=True, scalar_first=True))},
               "err_rot_mrad": float((a_rot.inv() * qref).magnitude() * 1000)}
        out.append(row)
    return out


def expected_samples(rows):
    a = [r for r in rows if r["situation"] == A]
    b = groups([r for r in rows if r["situation"] == B], ("run", "device"))
    out = []
    for r in a:
        g = b.get((r["run"], r["device"]))
        if not g:
            continue
        tb = np.array([x["t"] for x in g])
        where = bracket(tb, r["t"])
        if where is None:
            continue
        i, f = where

        def at(c):
            v0 = g[i][c]
            if f is None:
                return v0
            v1 = g[i + 1][c]
            return None if v0 is None or v1 is None else float(v0 + f * (v1 - v0))

        def minus(c):
            bv, av = at(c), r[c]
            return None if bv is None or av is None else float(bv - av)

        e_q_deg = minus("q_deg")
        out.append({"t": r["t"], "run": r["run"], "situation": r["situation"], "source": r["source"], "reference": B, "device": r["device"],
                    "e_q_mrad": None if e_q_deg is None else float(np.deg2rad(e_q_deg) * 1000), "e_q_mm": minus("q_mm"),
                    "e_qd_deg_s": minus("qd_deg_s"), "e_qd_mm_s": minus("qd_mm_s"), "e_tau_nm": minus("tau_nm")})
    return out


# --------------------------------------------------------------------------------------------- the files
def fields(table, rows):
    """The contract schema's fields for the columns these rows carry, in the schema's order."""
    contract = json.loads((SCHEMAS / f"{table}.schema.json").read_text(encoding="utf-8"))["schema"]["fields"]
    have = {k for r in rows for k in r}
    return [f for f in contract if f["name"] in have]


def write(name, table, rows):
    """{schema, rows}: data-ui's JSON form (CONTRACT §3), one row per line so a diff reads as rows."""
    head = json.dumps({"fields": fields(table, rows)}, ensure_ascii=False)
    body = ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in rows)
    (OUT / f"{name}.json").write_text(f'{{\n "schema": {head},\n "rows": [\n{body}\n ]\n}}\n', encoding="utf-8")


def read(name):
    return json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))["rows"]


def main():
    tb = b_times()
    ta, ta2 = a_times(tb), [round(k / 94.4, 6) for k in range(48)]
    write("poses", "poses", poses_rows(tb, ta, ta2))
    write("samples", "samples", samples_rows(tb, ta, ta2))
    # WHY read back: the expected rows come from the numbers as written, which is what every other reader sees
    poses, samples = read("poses"), read("samples")
    diff_poses, diff_samples = expected_poses(poses), expected_samples(samples)
    write("diff_poses", "diff_poses", diff_poses)
    write("diff_samples", "diff_samples", diff_samples)
    provenance = {
        "made_by": "source/make_difference_fixture.py",
        "command": "uv run --with numpy --with scipy python3 gallery/robotics/fixtures/difference/source/make_difference_fixture.py",
        "seed": SEED, "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
        "difference": {"a": A, "b": B, "poses": "per (run, body, frame)", "samples": "per (run, device)"},
        "rows": {"poses": len(poses), "samples": len(samples), "diff_poses": len(diff_poses), "diff_samples": len(diff_samples)},
    }
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(provenance["rows"]))


if __name__ == "__main__":
    main()
