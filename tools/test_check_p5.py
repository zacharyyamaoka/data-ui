"""python3 -m unittest discover -s tools -p 'test_*.py'

PEP 0010 P5, the diagnostics and gates overlay: the Python proof's half (tests/unit/check-p5.test.mjs asks the Node
checker the same on the same files, tests/fixtures/p5/). The checker accepts every key P5 adds (docs/CONTRACT.md §35:
`display: status`, the tracker's `column`, `columns` and `order`, `limits` on a time series and a plot, a property
`kpi.target`, `trajectory3d.color` and `tolerance`, `voxels.better`, a record section's embedded `view`) and refuses,
at its line: a misspelt status display (did you mean), a limits side that is neither warn nor error or not a pair, a
`better` outside higher | lower, and a record section with neither properties nor a view. WHY no column checks here:
this proof reads no dataset but --data, so the columns each new key names are the Node checker's to name. Written red,
before the schema and the checker changed."""

import io
import pathlib
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

import check_views

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "p5"


def run(*args):
    out = io.StringIO()
    with redirect_stdout(out):
        check_views.main([str(a) for a in args])
    text = out.getvalue()
    counts = re.search(r"(\d+) errors, (\d+) warnings", text)
    return int(counts.group(1)), int(counts.group(2)), text


class CheckP5(unittest.TestCase):
    def setUp(self):
        self.dirs = []

    def tearDown(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)

    def variant(self, old, new):
        """A copy of the fixture folder with one line of gates.base swapped; its path and the line holding `new`."""
        target = pathlib.Path(tempfile.mkdtemp(prefix="dui-p5-"))
        self.dirs.append(target)
        shutil.copytree(FIX, target, dirs_exist_ok=True)
        path = target / "gates.base"
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(old), 1, f"'{old}' is in the fixture exactly once")
        text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
        line = next(i for i, l in enumerate(text.split("\n"), 1) if new in l)
        return path, line

    def error_at(self, text, line, pattern):
        return any(f":{line}: error:" in l and re.search(pattern, l) for l in text.splitlines())

    def test_every_key(self):
        errors, warnings, text = run(FIX / "gates.base")
        self.assertEqual((errors, warnings), (0, 0), text)

    def test_status_misspelt(self):
        path, line = self.variant("display: { verdict: status }", "display: { verdict: statuss }")
        errors, _, text = run(path)
        self.assertTrue(self.error_at(text, line, r"did you mean 'status'"), text)

    def test_limits_side(self):
        path, line = self.variant("limits: { warn: [warn_lo, warn_hi]", "limits: { warning: [warn_lo, warn_hi]")
        errors, _, text = run(path)
        self.assertTrue(self.error_at(text, line, r"warning"), text)

    def test_limits_pair(self):
        path, line = self.variant("limits: { error: [error_lo, error_hi] }", "limits: { error: [error_hi] }")
        errors, _, text = run(path)
        self.assertTrue(self.error_at(text, line, r"."), text)

    def test_better(self):
        path, line = self.variant("scale: verdict, better: higher", "scale: verdict, better: up")
        errors, _, text = run(path)
        self.assertTrue(self.error_at(text, line, r"higher|lower"), text)

    def test_section_needs_something(self):
        path, line = self.variant("- { name: Verdict, properties: [verdict, value, warn_hi, error_hi, message] }", "- { name: Verdict }")
        errors, _, text = run(path)
        self.assertTrue(self.error_at(text, line, r"."), text)


if __name__ == "__main__":
    unittest.main()
