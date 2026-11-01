"""python3 -m unittest discover -s tools -p 'test_*.py'

PEP 0010 P1d: the one shared difference(a, b) (gallery/robotics/difference.py, beside fixture.py) and the difference
tables the two robotics templates write with it (gallery/examples/robotics-servo, robotics-arm).

- difference.py reproduces the fixture: fixture.check_difference(poses=difference, samples=difference) == []. The
  fixture's expected rows were computed with numpy and scipy (its source/ script), an oracle outside this code;
  tools/test_robotics_fixture.py is the second, stdlib one.
- it imports nothing but the standard library, so a producer in any venv can call it.
- each template's diff_*.json is exactly difference()'s rows over the template's own poses.json / samples.json, every
  number rounded to 6 decimals (the display projection: 1e-6 of the column's unit), for every pair the contract names
  (gallery/robotics/CONTRACT.md §5: each situation against the target; each sim situation against each real one), in
  a's order; no other pair, nothing else.
- the difference tables are the contract's: every column a contract column with its type and unit, every row with the
  required ones.
Written red, before difference.py and the producers."""

import ast
import importlib
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HERE = ROOT / "gallery" / "robotics"
EX = ROOT / "gallery" / "examples"
sys.path.insert(0, str(HERE))
CASES = {"robotics-servo": [("samples", "diff_samples")], "robotics-arm": [("poses", "diff_poses"), ("samples", "diff_samples")]}
DIGITS = 6


def table(case, name):
    return json.loads((EX / case / f"{name}.json").read_text(encoding="utf-8"))


def rounded(row):
    return {k: (round(v, DIGITS) if isinstance(v, float) else v) for k, v in row.items()}


def pairs(rows):
    """The pairs the contract names, from the situations and their families in these rows: (a, b) for each situation a
    against each target b, and each sim situation a against each real b."""
    family = {}
    for r in rows:
        family.setdefault(r["situation"], r["source"])
    sits = sorted(family)
    out = [(a, b) for b in sits if family[b] == "target" for a in sits if a != b]
    out += [(a, b) for a in sits if family[a] == "sim" for b in sits if family[b] == "real"]
    return out


class Difference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = importlib.import_module("fixture")
        cls.lib = importlib.import_module("difference")  # gallery/robotics/difference.py

    def test_it_reproduces_the_fixture(self):
        self.assertEqual(self.fixture.check_difference(poses=self.lib.difference, samples=self.lib.difference), [])

    def test_it_is_stdlib_only(self):
        tree = ast.parse((HERE / "difference.py").read_text(encoding="utf-8"))
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and not n.level}
        self.assertTrue(names <= set(sys.stdlib_module_names) | {"__future__"}, sorted(names - set(sys.stdlib_module_names)))

    def test_each_template_writes_exactly_its_differences(self):
        for case, tables in CASES.items():
            for src, dst in tables:
                with self.subTest(case=case, table=dst):
                    rows = table(case, src)["rows"]
                    got = table(case, dst)["rows"]
                    want_pairs = pairs(rows)
                    seen = []
                    for a, b in want_pairs:
                        want = [rounded(r) for r in self.lib.difference([r for r in rows if r["situation"] == a], [r for r in rows if r["situation"] == b])]
                        have = [r for r in got if r["situation"] == a and r["reference"] == b]
                        self.assertEqual(len(have), len(want), f"{case}/{dst}: {a} against {b}")
                        for i, (h, w) in enumerate(zip(have, want)):
                            self.assertEqual(h, w, f"{case}/{dst}: {a} against {b}, row {i}")
                        if want:
                            seen.append((a, b))
                    others = sorted({(r["situation"], r["reference"]) for r in got} - set(want_pairs))
                    self.assertEqual(others, [], f"{case}/{dst}: pairs the contract does not name")
                    self.assertTrue(seen, f"{case}/{dst}: no pair at all")

    def test_the_difference_tables_are_the_contracts(self):
        for case, tables in CASES.items():
            for _, dst in tables:
                with self.subTest(case=case, table=dst):
                    doc = table(case, dst)
                    contract = json.loads((HERE / "schemas" / f"{dst}.schema.json").read_text(encoding="utf-8"))
                    want = {f["name"]: f for f in contract["schema"]["fields"]}
                    for f in doc["schema"]["fields"]:
                        self.assertIn(f["name"], want, f"{case}/{dst}.json: {f['name']} is a contract column")
                        self.assertEqual((f["type"], f.get("unit")), (want[f["name"]]["type"], want[f["name"]].get("unit")), f"{case}/{dst}.json: {f['name']}")
                    for req in contract["required"]:
                        self.assertTrue(all(req in r for r in doc["rows"]), f"{case}/{dst}.json: every row has {req}")
                    if dst == "diff_samples":
                        self.assertTrue(all("e_q_mrad" in r for r in doc["rows"]), f"{case}: e_q_mrad (a revolute axis)")


if __name__ == "__main__":
    unittest.main()
