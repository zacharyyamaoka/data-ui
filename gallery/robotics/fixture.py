"""The difference(a, b) fixture (CONTRACT.md §5), read the one way every consumer reads it. Stdlib only.

A trajectory library's own test (traj_compare today; lk_msgs or RobotDx when the types move, PEP 0010 Q7) proves its
difference(a, b) against it:

    import sys
    sys.path.insert(0, "<data-ui checkout>/gallery/robotics")
    import fixture
    assert fixture.check_difference(poses=difference, samples=difference) == []

A gallery case's checks.py reads the expected rows to measure what its view drew (PEP 0010 P1d: every arrow from a(t)
to b(t) within 1e-6 mm): fixture.rows("diff_poses"). data-ui's own proof is tools/test_robotics_fixture.py: an
independent difference(a, b) reproduces every row, and nine wrong ones fail.

The fixture: fixtures/difference/poses.json and samples.json hold two trajectories of one run, a = situation "real"
and b = situation "target", as a producer writes them; diff_poses.json and diff_samples.json hold the rows
difference(a, b) returns (computed with numpy and scipy by fixtures/difference/source/make_difference_fixture.py). """

import json
import math
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "difference"
A, B = "real", "target"
# WHY these: implementations differ in rounding order (p0 + f·(p1 − p0) against (1 − f)·p0 + f·p1, slerp by sine
# weights or by rotation vectors) by ~1e-13 in a column's unit; 2·acos(|⟨a, b⟩|) loses half its digits near 0
# (~4e-5 mrad), so err_rot_mrad gets 1e-4 mrad. Anything a reader could see is far above both.
DEFAULT_TOLERANCE = 1e-9
TOLERANCE = {"err_rot_mrad": 1e-4}


def tolerance(column: str) -> float:
    return TOLERANCE.get(column, DEFAULT_TOLERANCE)


def rows(name: str) -> list[dict]:
    """The rows of fixtures/difference/<name>.json (poses, samples, diff_poses, diff_samples), as written."""
    doc = json.loads((FIXTURE / f"{name}.json").read_text(encoding="utf-8"))
    return doc["rows"] if isinstance(doc, dict) else doc


def trajectories(table: str) -> tuple[list[dict], list[dict]]:
    """(a, b) of a table ('poses' or 'samples'): the rows of situation A and of situation B, each in file order."""
    every = rows(table)
    return [r for r in every if r.get("situation") == A], [r for r in every if r.get("situation") == B]


def _number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def compare(got, expected, *, limit: int = 20) -> list[str]:
    """What differs between a difference(a, b)'s rows and the expected ones; [] when they conform. Row for row, in
    order; each expected column: text equal, a number within tolerance(column), null as null (absent counts as null).
    Columns the expected rows do not have are a library's own (e_<channel> for another channel) and are not judged."""
    got = list(got or [])
    problems = []
    if len(got) != len(expected):
        problems.append(f"{len(got)} rows, expected {len(expected)} (one per sample of a inside b's span, in a's order)")
    for i, (g, e) in enumerate(zip(got, expected)):
        g = g if isinstance(g, dict) else {}
        for key, want in e.items():
            have = g.get(key)
            if want is None:
                ok = have is None
            elif _number(want):
                ok = _number(have) and math.isfinite(have) and abs(have - want) <= tolerance(key)
            else:
                ok = have == want
            if not ok:
                where = e.get("body") or e.get("device")
                problems.append(f"row {i} (t={e.get('t')}, {where}): {key} = {have!r}, expected {want!r}")
                if len(problems) >= limit:
                    return problems + ["…"]
    return problems


def check_difference(poses=None, samples=None) -> list[str]:
    """Run a difference(a, b) on the fixture's trajectories and compare its rows with the expected ones: [] when it
    conforms. `poses` and `samples` are functions (a_rows, b_rows) -> rows, for that table; give one or both."""
    if poses is None and samples is None:
        raise ValueError("give poses=, samples= or both: a difference(a, b) for that table")
    problems = []
    for table, fn in (("poses", poses), ("samples", samples)):
        if fn is None:
            continue
        a, b = trajectories(table)
        problems += [f"{table}: {p}" for p in compare(fn(a, b), rows(f"diff_{table}"))]
    return problems


if __name__ == "__main__":
    for name in ("poses", "samples", "diff_poses", "diff_samples"):
        print(f"{name}: {len(rows(name))} rows")
