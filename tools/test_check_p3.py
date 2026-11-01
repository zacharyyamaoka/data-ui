"""python3 -m unittest discover -s tools -p 'test_*.py'

PEP 0010 P3, navigation: the Python proof's half (tests/unit/check-p3.test.mjs asks the Node checker the same on the same
files, tests/fixtures/p3/). The checker accepts every key P3 adds (a link's `direction`, a dataset whose data: names a
placeholder, a view's `selected:`) and refuses what an agent gets wrong, at its line: a misspelt direction; selected:
without select:; a placeholder no link reaches; a per-pick dataset on a timer; the file's own data: as a template; and it
warns on a link into a per-pick dataset written two-way. WHY no file checks here: this proof reads no dataset but --data,
so the per-pick dataset's columns and a literal selected: value are the Node checker's to name. Written red, before the
schema and the checker changed."""

import io
import pathlib
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

import check_views

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "p3"


def run(*args):
    out = io.StringIO()
    with redirect_stdout(out):
        check_views.main([str(a) for a in args])
    text = out.getvalue()
    counts = re.search(r"(\d+) errors, (\d+) warnings", text)
    return int(counts.group(1)), int(counts.group(2)), text


class CheckP3(unittest.TestCase):
    def setUp(self):
        self.dirs = []

    def tearDown(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)

    def variant(self, old, new):
        """A copy of the fixture folder with one line of nav.base swapped; its path and the (first) line holding `needle`."""
        target = pathlib.Path(tempfile.mkdtemp(prefix="dui-p3-"))
        self.dirs.append(target)
        shutil.copytree(FIX, target, dirs_exist_ok=True)
        path = target / "nav.base"
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(old), 1, f"'{old}' is in the fixture exactly once")
        path.write_text(text.replace(old, new), encoding="utf-8")
        return path

    def line(self, path, needle):
        return next(i for i, l in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if needle in l)

    def test_every_key_p3_adds_passes(self):
        errors, warnings, out = run(FIX / "nav.base")
        self.assertEqual((errors, warnings), (0, 0), out)

    def test_a_misspelt_direction(self):
        path = self.variant("{ from: runs.run, to: samples.run, direction: one-way }", "{ from: runs.run, to: samples.run, direction: oneway }")
        errors, _, out = run(path)
        self.assertGreaterEqual(errors, 1, out)
        self.assertIn(f"nav.base:{self.line(path, 'direction: oneway')}: error:", out)
        self.assertIn("did you mean 'one-way'", out)

    def test_selected_without_select(self):
        path = self.variant("    select: deployment\n    selected: first", "    selected: first")
        errors, _, out = run(path)
        self.assertIn(f"nav.base:{self.line(path, 'selected: first')}: error: views[0].selected:", out)
        self.assertIn("select:", out)

    def test_a_two_way_link_into_a_per_pick_dataset_warns(self):
        path = self.variant("{ from: runs.run, to: samples.run, direction: one-way }", "{ from: runs.run, to: samples.run }")
        errors, warnings, out = run(path)
        self.assertEqual(errors, 0, out)
        self.assertIn(f"nav.base:{self.line(path, '{ from: runs.run, to: samples.run }')}: warning: links[1]:", out)
        self.assertIn("one-way", out)

    def test_a_placeholder_no_link_reaches(self):
        path = self.variant("  - { from: runs.run, to: samples.run, direction: one-way }\n", "")
        errors, _, out = run(path)
        self.assertIn(f"nav.base:{self.line(path, chr(39) + 'runs/{run}.json' + chr(39))}: error: datasets.samples.data:", out)
        self.assertIn("link", out)

    def test_a_misnamed_placeholder(self):
        path = self.variant("data: 'runs/{run}.json'", "data: 'runs/{rnu}.json'")
        errors, _, out = run(path)
        self.assertGreaterEqual(errors, 1, out)
        self.assertIn("rnu", out)

    def test_the_files_own_data_as_a_template(self):
        path = self.variant("data: runs.json\nclock:", "data: 'runs/{run}.json'\nclock:")
        errors, _, out = run(path)
        self.assertIn(f"nav.base:{self.line(path, chr(39) + 'runs/{run}.json' + chr(39))}: error: data:", out)

    def test_a_per_pick_dataset_on_a_timer(self):
        path = self.variant("    data: 'runs/{run}.json'\n", "    data: 'runs/{run}.json'\n    refresh: 10s\n")
        errors, _, out = run(path)
        self.assertIn(f"nav.base:{self.line(path, 'refresh: 10s')}: error: datasets.samples.refresh:", out)


if __name__ == "__main__":
    unittest.main()
