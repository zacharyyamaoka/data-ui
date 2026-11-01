"""python3 -m unittest discover -s tools -p 'test_*.py'

Add to dashboard (docs/CONTRACT.md §34): the Python proof's half (tests/unit/add-to-dashboard.test.mjs asks the Node
checker the same on the same files, tests/browser/fixtures/add_to_dashboard/). A panel a reader adds may carry two keys
the feature adds: `hiddenSeries` on its view (the series its legend hides when it opens: a list of names) and `t` on its
layout panel (the instant it stands at, in seconds: a number). The checker reads both from schemas/view.schema.json,
accepts them, and refuses the wrong shape at its line. Written red, before the schema changed."""

import io
import pathlib
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

import check_views

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "browser" / "fixtures" / "add_to_dashboard"
VIEW = "    timeseries: { x: t, y: err_mm, series: joint }"
PANEL = "    - { view: Tool paths, w: 6, h: 3 }"


def run(*args):
    out = io.StringIO()
    with redirect_stdout(out):
        check_views.main([str(a) for a in args])
    text = out.getvalue()
    counts = re.search(r"(\d+) errors, (\d+) warnings", text)
    return int(counts.group(1)), int(counts.group(2)), text


class CheckAddToDashboard(unittest.TestCase):
    def setUp(self):
        self.dirs = []

    def tearDown(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)

    def variant(self, *swaps):
        """A copy of the fixture folder whose source.base has each (old, new) swapped; its path and text."""
        target = pathlib.Path(tempfile.mkdtemp(prefix="dui-a2d-"))
        self.dirs.append(target)
        shutil.copytree(FIX, target, dirs_exist_ok=True)
        path = target / "source.base"
        text = path.read_text(encoding="utf-8")
        for old, new in swaps:
            self.assertEqual(text.count(old), 1, f"'{old}' is in the fixture exactly once")
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
        return path, text

    @staticmethod
    def line_of(text, needle):
        return next(i for i, line in enumerate(text.split("\n"), 1) if needle in line)

    def test_the_fixture_is_clean(self):
        errors, warnings, out = run(FIX / "source.base")
        self.assertEqual((errors, warnings), (0, 0), out)

    def test_hidden_series_and_a_panels_t_are_known(self):
        path, _ = self.variant((VIEW, VIEW + "\n    hiddenSeries: [J1, J3]"), (PANEL, "    - { view: Tool paths, w: 6, h: 3, t: 1.5 }"))
        errors, warnings, out = run(path)
        self.assertEqual((errors, warnings), (0, 0), out)

    def test_hidden_series_is_a_list(self):
        path, text = self.variant((VIEW, VIEW + "\n    hiddenSeries: J3"))
        errors, _, out = run(path)
        self.assertGreaterEqual(errors, 1, out)
        self.assertRegex(out, rf"source\.base:{self.line_of(text, 'hiddenSeries: J3')}: error", out)

    def test_a_panels_t_is_a_number(self):
        path, text = self.variant((PANEL, "    - { view: Tool paths, w: 6, h: 3, t: soon }"))
        errors, _, out = run(path)
        self.assertGreaterEqual(errors, 1, out)
        self.assertRegex(out, rf"source\.base:{self.line_of(text, 't: soon')}: error", out)


if __name__ == "__main__":
    unittest.main()
