"""python3 -m unittest discover -s tools -p 'test_*.py'

PEP 0010 P1a: the difference(a, b) fixture (gallery/robotics/fixtures/difference/), read the way every consumer reads it,
through gallery/robotics/fixture.py: a trajectory library's own tests call fixture.check_difference(...) with its
difference(a, b); a gallery case's checks read fixture.rows('diff_poses') to measure what its view drew.

The fixture's expected rows were computed with numpy and scipy's Rotation/Slerp (its source/ script). This test is the
second oracle: an independent, stdlib-only difference(a, b) written from the spec (gallery/robotics/CONTRACT.md) must
reproduce every row, and each plausible wrong implementation (nlerp, no short way, extrapolating past b, ignoring the
frame, null read as 0, acos without |…|, a − b, degrees, a non-canonical sign) must fail it: a fixture no mistake can
fail measures nothing. Written red, before the fixture and its reader existed."""

import bisect
import math
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gallery" / "robotics"))

RUN, RUN_A_ONLY = "fixture/r1", "fixture/r2"
BODY, BODY_FRAMES_DIFFER, BODY_A_ONLY = "tool0", "lever_tip", "camera_link"
REVOLUTE, PRISMATIC, DEVICE_A_ONLY = "J3 elbow", "Z lift", "J1 base"
POS = ("x_mm", "y_mm", "z_mm")
QUAT = ("quat_w", "quat_x", "quat_y", "quat_z")


# --------------------------------------------------------------------------------------------- quaternions, by hand
def normalize(q):
    n = math.sqrt(sum(c * c for c in q))
    return tuple(c / n for c in q)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw)


def canonical(q):
    """w ≥ 0; when w is 0, the first non-zero of x, y, z positive (scipy's as_quat(canonical=True))."""
    for c in q:
        if c != 0:
            return q if c > 0 else tuple(-x for x in q)
    return q


def slerp(q0, q1, f, *, short_way=True, nlerp=False):
    q0, q1 = normalize(q0), normalize(q1)
    d = dot(q0, q1)
    if short_way and d < 0:
        q1, d = tuple(-c for c in q1), -d
    if nlerp:
        return normalize(tuple(a + f * (b - a) for a, b in zip(q0, q1)))
    theta = math.acos(max(-1.0, min(1.0, d)))
    if abs(math.sin(theta)) < 1e-12:
        return normalize(tuple(a + f * (b - a) for a, b in zip(q0, q1)))
    w0, w1 = math.sin((1 - f) * theta) / math.sin(theta), math.sin(f * theta) / math.sin(theta)
    return normalize(tuple(w0 * a + w1 * b for a, b in zip(q0, q1)))


def angle(qa, qb, *, acos_angle=False):
    """The rotation from a to b, in rad: 2·atan2(|v|, |w|) of conj(a)·b (well conditioned near 0)."""
    qa, qb = normalize(qa), normalize(qb)
    if acos_angle:  # the mutant: no |…|, so q and -q are two orientations
        return 2 * math.acos(max(-1.0, min(1.0, dot(qa, qb))))
    w, x, y, z = mul((qa[0], -qa[1], -qa[2], -qa[3]), qb)
    return 2 * math.atan2(math.sqrt(x * x + y * y + z * z), abs(w))


# --------------------------------------------------------------------------------------------- difference(a, b)
def difference(a, b, table, *, nlerp=False, short_way=True, extrapolate=False, match_frame=True, null_as_zero=False,
               acos_angle=False, sign=1, degrees=False, canonical_sign=True):
    """The spec, written out (gallery/robotics/CONTRACT.md, difference(a, b)); the keyword flags are the mutants."""
    keys = ("run", "body", "frame") if table == "poses" else ("run", "device")
    if not match_frame:
        keys = ("run", "body")
    groups = {}
    for r in b:
        groups.setdefault(tuple(r[k] for k in keys), []).append(r)
    out = []
    for r in a:
        bs = groups.get(tuple(r[k] for k in keys))
        if not bs:
            continue
        ts = [x["t"] for x in bs]
        t = r["t"]
        if t < ts[0] or t > ts[-1]:
            if not extrapolate:
                continue
            i, f = (0, None) if t < ts[0] else (len(ts) - 1, None)
        else:
            i = bisect.bisect_right(ts, t) - 1
            f = None if ts[i] == t else (t - ts[i]) / (ts[i + 1] - ts[i])

        def at(c):
            v0 = bs[i].get(c)
            if f is None:
                return 0.0 if v0 is None and null_as_zero else v0
            v1 = bs[i + 1].get(c)
            if v0 is None or v1 is None:
                if not null_as_zero:
                    return None
                v0, v1 = v0 or 0.0, v1 or 0.0
            return v0 + f * (v1 - v0)

        def minus(bv, av):
            if bv is None or av is None:
                if not null_as_zero:
                    return None
                bv, av = bv or 0.0, av or 0.0
            return sign * (bv - av)

        row = {"t": t, "run": r["run"], "situation": r["situation"], "source": r["source"], "reference": bs[0]["situation"]}
        if table == "poses":
            ref = [at(c) for c in POS]
            row.update({"body": r["body"], "frame": r["frame"], **{c: r[c] for c in POS}, **{f"ref_{c}": v for c, v in zip(POS, ref)}})
            row["err_mm"] = math.sqrt(sum((v - r[c]) ** 2 for c, v in zip(POS, ref)))
            qb = tuple(bs[i][c] for c in QUAT) if f is None else slerp(tuple(bs[i][c] for c in QUAT), tuple(bs[i + 1][c] for c in QUAT), f, short_way=short_way, nlerp=nlerp)
            qb = normalize(qb)
            if canonical_sign:
                qb = canonical(qb)
            qa = tuple(r[c] for c in QUAT)
            row.update({c: r[c] for c in QUAT})
            row.update({f"ref_{c}": v for c, v in zip(QUAT, qb)})
            row["err_rot_mrad"] = angle(qa, qb, acos_angle=acos_angle) * 1000
        else:
            row["device"] = r["device"]
            e_q = minus(at("q_deg"), r.get("q_deg"))
            row["e_q_mrad"] = None if e_q is None else (e_q if degrees else e_q * math.pi / 180 * 1000)
            row["e_qd_deg_s"] = minus(at("qd_deg_s"), r.get("qd_deg_s"))
            row["e_tau_nm"] = minus(at("tau_nm"), r.get("tau_nm"))
            row["e_q_mm"] = minus(at("q_mm"), r.get("q_mm"))
            row["e_qd_mm_s"] = minus(at("qd_mm_s"), r.get("qd_mm_s"))
        out.append(row)
    return out


def poses(**flags):
    return lambda a, b: difference(a, b, "poses", **flags)


def samples(**flags):
    return lambda a, b: difference(a, b, "samples", **flags)


class DifferenceFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import fixture  # gallery/robotics/fixture.py: the one reader
        cls.fx = fixture

    def test_the_reader_names_the_two_trajectories(self):
        self.assertEqual((self.fx.A, self.fx.B), ("real", "target"))
        for table in ("poses", "samples"):
            a, b = self.fx.trajectories(table)
            self.assertTrue(a and b, table)
            self.assertEqual({r["situation"] for r in a}, {"real"})
            self.assertEqual({r["situation"] for r in b}, {"target"})
        self.assertGreater(len(self.fx.rows("diff_poses")), 50)
        self.assertGreater(len(self.fx.rows("diff_samples")), 50)

    def test_an_independent_difference_reproduces_every_expected_row(self):
        self.assertEqual(self.fx.check_difference(poses=poses(), samples=samples()), [])

    def test_the_fixture_holds_every_case_the_spec_names(self):
        a, b = self.fx.trajectories("poses")
        ta = [r["t"] for r in a if r["run"] == RUN and r["body"] == BODY]
        bt = [r for r in b if r["run"] == RUN and r["body"] == BODY]
        tb = [r["t"] for r in bt]
        self.assertTrue(min(ta) < tb[0] and max(ta) > tb[-1], "a starts before b and ends after it: no rows there")
        self.assertIn(tb[0], ta, "an a sample at b's first t")
        self.assertIn(tb[-1], ta, "an a sample at b's last t")
        self.assertTrue(set(ta) & set(tb[1:-1]), "an a sample exactly on an interior b sample")
        qs = [tuple(r[c] for c in QUAT) for r in bt]
        self.assertTrue(any(dot(p, q) < 0 for p, q in zip(qs, qs[1:])), "b flips a quaternion's sign: slerp must take the short way")
        self.assertTrue(any(angle(p, q) > math.radians(90) for p, q in zip(qs, qs[1:])), "b turns > 90° between two samples: slerp and nlerp part")
        self.assertTrue(any(abs(math.sqrt(dot(q, q)) - 1) > 1e-7 for q in (tuple(r[c] for c in QUAT) for r in a)), "an a quaternion that is not unit")
        frames = lambda rows: {r["frame"] for r in rows if r["body"] == BODY_FRAMES_DIFFER}
        self.assertTrue(frames(a) and frames(b) and not frames(a) & frames(b), "a body a and b write in different frames")
        self.assertTrue(any(r["body"] == BODY_A_ONLY for r in a) and not any(r["body"] == BODY_A_ONLY for r in b))
        self.assertTrue(any(r["run"] == RUN_A_ONLY for r in a) and not any(r["run"] == RUN_A_ONLY for r in b))
        sa, sb = self.fx.trajectories("samples")
        self.assertTrue(any(r["device"] == REVOLUTE and r["tau_nm"] is None for r in sb), "a null in b")
        self.assertTrue(any(r["device"] == REVOLUTE and r["qd_deg_s"] is None for r in sa), "a null in a")
        self.assertTrue(any(r["device"] == PRISMATIC and r["q_mm"] is not None for r in sa), "a prismatic axis")
        self.assertTrue(any(r["device"] == DEVICE_A_ONLY for r in sa) and not any(r["device"] == DEVICE_A_ONLY for r in sb))
        diff = self.fx.rows("diff_poses")
        self.assertTrue(any(dot(normalize(tuple(r[c] for c in QUAT)), tuple(r[f"ref_{c}"] for c in QUAT)) < 0 for r in diff),
                        "an a quaternion written with the other sign than b's: err_rot_mrad stays the small angle")
        self.assertTrue(any(slerp(*(tuple(x[c] for c in QUAT) for x in pair), 0.5)[0] < 0 for pair in zip(bt, bt[1:])),
                        "b's slerp passes w < 0: the canonical sign is tested")

    def test_the_expected_rows_obey_the_spec(self):
        a, b = self.fx.trajectories("poses")
        diff = self.fx.rows("diff_poses")
        spans = {}
        for r in b:
            spans.setdefault((r["run"], r["body"], r["frame"]), []).append(r["t"])
        order = [(r["run"], r["body"], r["frame"], r["t"]) for r in a]
        got = [(r["run"], r["body"], r["frame"], r["t"]) for r in diff]
        self.assertEqual(got, [k for k in order if k[:3] in spans and spans[k[:3]][0] <= k[3] <= spans[k[:3]][-1]], "one row per a sample inside b's span, in a's order")
        for r in diff:
            self.assertAlmostEqual(r["err_mm"], math.dist([r[c] for c in POS], [r[f"ref_{c}"] for c in POS]), delta=1e-9)
            ref = tuple(r[f"ref_{c}"] for c in QUAT)
            self.assertEqual(ref, canonical(ref))
            self.assertAlmostEqual(r["err_rot_mrad"], angle(tuple(r[c] for c in QUAT), ref) * 1000, delta=1e-4)

    def test_every_wrong_implementation_fails_the_fixture(self):
        mutants = {
            "nlerp instead of slerp": dict(poses=poses(nlerp=True)),
            "slerp the long way after a sign flip": dict(poses=poses(short_way=False)),
            "extrapolating past b's span": dict(poses=poses(extrapolate=True)),
            "pairing a body across two frames": dict(poses=poses(match_frame=False)),
            "2·acos(⟨a, b⟩) without |…|": dict(poses=poses(acos_angle=True)),
            "the sign of b's slerp kept (not canonical)": dict(poses=poses(canonical_sign=False)),
            "a null read as 0": dict(samples=samples(null_as_zero=True)),
            "a − b instead of b − a": dict(samples=samples(sign=-1)),
            "e_q in degrees, not mrad": dict(samples=samples(degrees=True)),
        }
        for name, impl in mutants.items():
            with self.subTest(name):
                self.assertNotEqual(self.fx.check_difference(**impl), [], f"{name} passed the fixture")


if __name__ == "__main__":
    unittest.main()
