"""python3 -m unittest discover -s tools -p 'test_*.py'

PEP 0010 P1a (docs/CONTRACT.md §32), the Python proof's half: the checker accepts every key the robotics amendment adds
and refuses the three typos the PEP names, `projection: diagonal`, `decay: -1` and `primitive: arow`, each once, at its
line, with "did you mean". The same fixtures as tests/unit/check-robotics.test.mjs (tests/fixtures/robotics/); each
refused variant is a copy of the folder with one line swapped. Written red, before the schema and the checker changed."""

import io
import pathlib
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

import check_views

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "robotics"
LINE = re.compile(r"^(?P<file>.+?):(?P<line>\d+): (?P<level>error|warning): (?P<path>\S+): (?P<message>.*)$")


def run(*args):
    out = io.StringIO()
    with redirect_stdout(out):
        status = check_views.main([str(a) for a in args])
    text = out.getvalue()
    problems = [m.groupdict() for m in map(LINE.match, text.splitlines()) if m]
    counts = re.search(r"(\d+) errors, (\d+) warnings", text)
    return status, int(counts.group(1)), int(counts.group(2)), problems, text


class Variants:
    """Copies of the fixture folder, each with one line swapped; removed when the test case ends."""

    def __init__(self):
        self.dirs = []

    def make(self, file, old, new):
        target = pathlib.Path(tempfile.mkdtemp(prefix="dui-robotics-"))
        self.dirs.append(target)
        shutil.copytree(FIX, target, dirs_exist_ok=True)
        path = target / file
        text = path.read_text(encoding="utf-8")
        assert text.count(old) == 1, f"'{old}' is in the fixture exactly once"
        path.write_text(text.replace(old, new), encoding="utf-8")
        line = next(i for i, l in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if new in l)
        return path, line

    def close(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)


REFUSED = [
    ("projection: diagonal", "projection: perspective", "projection: diagonal", "trajectory3d.projection", r"did you mean .*dir"),
    ("decay: -1", "decay: 0.5", "decay: -1", "trajectory3d.decay", r"did you mean inf\b"),
    ("primitive: arow", "primitive: arrows", "primitive: arow", "scene3d.layers[3].primitive", r"did you mean 'arrows'\?"),
]
MORE = [
    ("axes: off", "axes: none", "axes: off", r"did you mean 'none'"),
    ("decay: .inf", "decay: inf", "decay: .inf", r"did you mean inf\b"),
    ("a layer's data: naming no dataset", "data: diff, from:", "data: dif, from:", r"no dataset 'dif'"),
    ("projection.dir all zero", "projection: { dir: [-1, -1, -1], up: [0, 0, 1] }", "projection: { dir: [0, 0, 0] }", r"dir"),
    ("projection.up parallel to dir", "projection: { dir: [-1, -1, -1], up: [0, 0, 1] }", "projection: { dir: [0, 0, -1], up: [0, 0, 1] }", r"parallel"),
]


class CheckRobotics(unittest.TestCase):
    def setUp(self):
        self.variants = Variants()

    def tearDown(self):
        self.variants.close()

    def test_dashboard_with_every_new_key_passes(self):
        status, errors, warnings, _, text = run(FIX / "dashboard.base")
        self.assertEqual((status, errors, warnings), (0, 0, 0), text)

    def test_plain_base_passes_against_its_data(self):
        status, errors, warnings, _, text = run(FIX / "plain.base", "--data", FIX / "poses.json")
        self.assertEqual((status, errors, warnings), (0, 0, 0), text)

    def test_the_three_refusals_each_once_at_the_line_with_did_you_mean(self):
        for name, old, new, path, hint in REFUSED:
            with self.subTest(name):
                file, line = self.variants.make("dashboard.base", old, new)
                status, errors, warnings, problems, text = run(file)
                self.assertEqual((status, errors, warnings), (1, 1, 0), text)
                self.assertEqual(int(problems[0]["line"]), line, text)
                self.assertTrue(problems[0]["path"].endswith(path), text)
                self.assertRegex(problems[0]["message"], hint)

    def test_more_refusals_each_once_at_the_line(self):
        for name, old, new, hint in MORE:
            with self.subTest(name):
                file, line = self.variants.make("dashboard.base", old, new)
                status, errors, warnings, problems, text = run(file)
                self.assertEqual((errors, warnings), (1, 0), text)
                self.assertEqual(int(problems[0]["line"]), line, text)
                self.assertRegex(problems[0]["message"], hint)

    def test_plain_columns_are_checked_against_the_data(self):
        data = ("--data", FIX / "poses.json")
        file, line = self.variants.make("plain.base", "{ primitive: lines, x: x_mm,", "{ primitive: lines, x: x_m,")
        status, errors, warnings, problems, text = run(file, *data)
        self.assertEqual((errors, warnings), (1, 0), text)
        self.assertEqual(problems[0]["message"], "'x_m' is not a property of poses.json (did you mean 'x_mm'?)")
        self.assertEqual(int(problems[0]["line"]), line)
        file, _ = self.variants.make("plain.base", "value: count", "value: reach")
        status, errors, warnings, problems, text = run(file, *data)
        self.assertEqual((errors, warnings), (1, 0), text)
        self.assertTrue(problems[0]["message"].startswith("'reach' is not a property of poses.json"), text)
        file, _ = self.variants.make("plain.base", "{ primitive: frames, x:", "{ primitive: frames, data: diff, x:")
        status, errors, warnings, problems, text = run(file, *data)
        self.assertEqual((errors, warnings), (0, 1), text)
        self.assertIn("diff", problems[0]["message"])


if __name__ == "__main__":
    unittest.main()
