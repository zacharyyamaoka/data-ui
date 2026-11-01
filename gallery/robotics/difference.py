"""difference(a, b), the one comparison of the trajectory contract (CONTRACT.md §5), as one shared implementation:
the robotics templates' producers call it (gallery/examples/robotics-*/source/build_diff.py), and so can a trajectory
library until the types have their home (PEP 0010 §13 Q7). Standard library only, so it runs in any producer's venv.

    import sys; sys.path.insert(0, "<data-ui checkout>/gallery/robotics")
    from difference import difference
    rows = difference(a_rows, b_rows)     # a's and b's rows of one table (poses or samples), each one situation

It reproduces the fixture (fixtures/difference/, computed with numpy and scipy): tools/test_robotics_difference.py
asserts fixture.check_difference(poses=difference, samples=difference) == []. The rules, from the contract:

- **Pairing.** b's rows are paired with a's by (run, body, frame) for poses and (run, device) for samples (the table is
  told apart by its columns); an a row whose key b lacks gives no row, so a body b writes in another frame gives none.
  Within a key, b's t rises strictly.
- **Times.** One row per sample of a whose t lies in b's span for that key, both ends included; never extrapolated;
  on a's own times, in a's order.
- **b at t.** At one of b's own times, b's values exactly. Between b's samples i and i + 1 at f = (t − tᵢ)/(tᵢ₊₁ − tᵢ):
  numbers vᵢ + f·(vᵢ₊₁ − vᵢ); orientations by slerp of the normalised quaternions, the short way (qᵢ₊₁ negated when
  ⟨qᵢ, qᵢ₊₁⟩ < 0). A null on either side is null at t, never a number made from 0.
- **diff_poses rows.** a's columns as written, `reference` = b's situation, `ref_<column>` = b at t, `err_mm` = |b − a|,
  `ref_quat_*` in the canonical sign (w ≥ 0; at w = 0 the first non-zero of x, y, z positive), and
  `err_rot_mrad` = 1000 · 2 · atan2(‖v‖, |w|) of (w, v) = conj(â) ⊗ b̂ (null when either has no quaternion).
- **diff_samples rows.** t, run, situation, source, reference, device, and b − a at t of each channel the rows carry:
  e_q_mrad (q_deg, in mrad), e_q_mm, e_qd_deg_s, e_qd_mm_s, e_tau_nm; null when either side is null.
"""

from __future__ import annotations

import bisect
import math

POS = ("x_mm", "y_mm", "z_mm")
QUAT = ("quat_w", "quat_x", "quat_y", "quat_z")
# samples: b − a of each channel, named e_<channel> in its unit; q_deg is written in mrad (CONTRACT.md §5)
CHANNELS = (("q_deg", "e_q_mrad", math.pi / 180 * 1000), ("q_mm", "e_q_mm", None), ("qd_deg_s", "e_qd_deg_s", None),
            ("qd_mm_s", "e_qd_mm_s", None), ("tau_nm", "e_tau_nm", None))


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def _norm(q):
    if q is None or any(c is None for c in q):
        return None
    n = math.sqrt(sum(c * c for c in q))
    return tuple(c / n for c in q) if n > 0 else None


def _mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw)


def _slerp(q0, q1, f):
    """Spherical interpolation of two unit quaternions, the short way; at an angle too small to divide by, the
    normalised lerp it tends to."""
    d = sum(x * y for x, y in zip(q0, q1))
    if d < 0:
        q1, d = tuple(-c for c in q1), -d
    theta = math.acos(min(1.0, d))
    if math.sin(theta) < 1e-12:
        return _norm(tuple(a + f * (b - a) for a, b in zip(q0, q1)))
    w0, w1 = math.sin((1 - f) * theta) / math.sin(theta), math.sin(f * theta) / math.sin(theta)
    return _norm(tuple(w0 * a + w1 * b for a, b in zip(q0, q1)))


def _canonical(q):
    """w ≥ 0; when w is 0, the first non-zero of x, y, z positive (scipy's as_quat(canonical=True))."""
    for c in q:
        if c != 0:
            return q if c > 0 else tuple(-x for x in q)
    return q


def _angle_mrad(qa, qb):
    """The rotation from a to b, mrad: 2·atan2(‖v‖, |w|) of conj(a)·b, well conditioned near 0."""
    w, x, y, z = _mul((qa[0], -qa[1], -qa[2], -qa[3]), qb)
    return 1000 * 2 * math.atan2(math.sqrt(x * x + y * y + z * z), abs(w))


def _quat(row, cols=QUAT):
    q = tuple(_num(row.get(c)) for c in cols)
    return None if any(c is None for c in q) else q


def difference(a, b):
    """The difference trajectory of a against b (rows of one table, one situation each): a list of rows, in a's order."""
    a, b = list(a), list(b)
    if not a or not b:
        return []
    poses = all(k in a[0] for k in ("body", "frame", *POS))
    keys = ("run", "body", "frame") if poses else ("run", "device")
    groups = {}
    for r in b:
        groups.setdefault(tuple(r.get(k) for k in keys), []).append(r)
    times = {}
    for key, g in groups.items():
        ts = [r["t"] for r in g]
        if any(x >= y for x, y in zip(ts, ts[1:])):
            raise ValueError(f"b's t must rise strictly within {dict(zip(keys, key))}")
        times[key] = ts
    reference = b[0].get("situation")
    has_quat = poses and any(c in r for r in (*a, *b) for c in QUAT)
    channels = [c for c in CHANNELS if any(c[0] in r for r in (*a, *b))] if not poses else []
    out = []
    for r in a:
        key = tuple(r.get(k) for k in keys)
        g = groups.get(key)
        t = _num(r.get("t"))
        if not g or t is None:
            continue
        ts = times[key]
        if t < ts[0] or t > ts[-1]:
            continue
        i = bisect.bisect_right(ts, t) - 1
        f = None if ts[i] == t else (t - ts[i]) / (ts[i + 1] - ts[i])

        def at(col):
            v0 = _num(g[i].get(col))
            if f is None:
                return v0
            v1 = _num(g[i + 1].get(col))
            return None if v0 is None or v1 is None else v0 + f * (v1 - v0)

        row = {"t": r["t"], "run": r.get("run"), "situation": r.get("situation"), "source": r.get("source"), "reference": reference}
        if poses:
            ref = [at(c) for c in POS]
            mine = [_num(r.get(c)) for c in POS]
            row.update({"body": r.get("body"), "frame": r.get("frame"), **{c: r.get(c) for c in POS},
                        **{f"ref_{c}": v for c, v in zip(POS, ref)}})
            row["err_mm"] = None if None in ref or None in mine else math.sqrt(sum((x - y) ** 2 for x, y in zip(ref, mine)))
            if has_quat:
                q0 = _norm(_quat(g[i]))
                qb = q0 if f is None or q0 is None else (None if _norm(_quat(g[i + 1])) is None else _slerp(q0, _norm(_quat(g[i + 1])), f))
                qb = None if qb is None else _canonical(_norm(qb))
                qa = _norm(_quat(r))
                row.update({c: r.get(c) for c in QUAT})
                row.update({f"ref_{c}": (None if qb is None else v) for c, v in zip(QUAT, qb or (None,) * 4)})
                row["err_rot_mrad"] = None if qa is None or qb is None else _angle_mrad(qa, qb)
        else:
            row["device"] = r.get("device")
            for col, name, scale in channels:
                bv, av = at(col), _num(r.get(col))
                d = None if bv is None or av is None else bv - av
                row[name] = None if d is None else (d * scale if scale else d)
        out.append(row)
    return out
