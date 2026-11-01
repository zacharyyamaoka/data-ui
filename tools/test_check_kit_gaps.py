"""python3 -m unittest discover -s tools -p 'test_*.py'

The kit gaps the PEP 0010 template lanes found, the Python proof's half (tests/unit/check-kit-gaps.test.mjs asks the
Node checker the same on the same files, tests/fixtures/kit_gaps/): the checker accepts every key the fixes add
(timeseries annotations from a dataset or the view's own rows, gap 2; a facet's `parent:`, gap 8; a view's `empty:`
text, gap 9) and knows the fields a chart's transforms create (gap 5), and refuses what an agent gets wrong, at its
line. WHY only the default dataset's columns: this proof has no dashboard model, so a view with `from:` and an
annotation with `data:` are the Node checker's to name. Written red, before the schema and the checker changed."""

import io
import pathlib
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

import check_views

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "kit_gaps"
SAMPLES = FIX / "samples.json"


def run(*args):
    out = io.StringIO()
    with redirect_stdout(out):
        check_views.main([str(a) for a in args])
    text = out.getvalue()
    counts = re.search(r"(\d+) errors, (\d+) warnings", text)
    return int(counts.group(1)), int(counts.group(2)), text


class Variants:
    """Copies of the fixture folder, each with one line swapped; removed when the test case ends."""

    def __init__(self):
        self.dirs = []

    def make(self, file, old, new):
        target = pathlib.Path(tempfile.mkdtemp(prefix="dui-kit-gaps-"))
        self.dirs.append(target)
        shutil.copytree(FIX, target, dirs_exist_ok=True)
        path = target / file
        text = path.read_text(encoding="utf-8")
        assert text.count(old) == 1, f"'{old}' is in the fixture exactly once"
        path.write_text(text.replace(old, new), encoding="utf-8")
        needle = new.splitlines()[-1].strip()
        line = next(i for i, l in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if needle in l)
        return path, line

    def close(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)


class KitGaps(unittest.TestCase):
    def setUp(self):
        self.v = Variants()

    def tearDown(self):
        self.v.close()

    def test_both_files_pass(self):
        errors, warnings, text = run(FIX / "plain.base", "--data", SAMPLES)
        self.assertEqual((errors, warnings), (0, 0), text)
        errors, warnings, text = run(FIX / "dashboard.base")
        self.assertEqual((errors, warnings), (0, 0), text)

    def test_gap5_a_field_nothing_makes_is_an_error(self):
        path, line = self.v.make("plain.base", "size: { field: q, type: quantitative }", "size: { field: qq, type: quantitative }")
        errors, _, text = run(path, "--data", SAMPLES)
        self.assertEqual(errors, 1, text)
        self.assertRegex(text, rf":{line}: error: .*'qq' is not a property of samples\.json")

    def test_gap5_created_fields_are_known_in_their_scope(self):
        # the pivot's columns (any value of mode) and every transform's own names: no error in the plain file
        errors, _, text = run(FIX / "plain.base", "--data", SAMPLES)
        self.assertEqual(errors, 0, text)

    def test_gap2_own_rows_annotation_columns(self):
        path, line = self.v.make("plain.base", "- { x: t, label: event }", "- { x: t, label: evnt }")
        errors, _, text = run(path, "--data", SAMPLES)
        self.assertEqual(errors, 1, text)
        self.assertRegex(text, rf":{line}: error: .*'evnt' is not a property of samples\.json \(did you mean 'event'\?\)")

    def test_gap2_dataset_annotation_in_a_plain_file_warns(self):
        path, line = self.v.make("plain.base", "- { x: 0.25, label: fixed }", "- { x: 0.25, label: fixed }\n        - { data: events, x: t, label: label }")
        errors, warnings, text = run(path, "--data", SAMPLES)
        self.assertEqual((errors, warnings), (0, 1), text)
        self.assertRegex(text, rf":{line}: warning: .*names a dashboard dataset")

    def test_gap8_parent_typo(self):
        path, line = self.v.make("dashboard.base", "parent: device }", "parent: devise }")
        errors, _, text = run(path)
        self.assertEqual(errors, 1, text)
        self.assertRegex(text, rf":{line}: error: .*did you mean 'device'\?")

    def test_gap8_own_parent(self):
        path, _ = self.v.make("dashboard.base", "parent: device }", "parent: run }")
        errors, _, text = run(path)
        self.assertEqual(errors, 1, text)
        self.assertIn("own parent", text)


if __name__ == "__main__":
    unittest.main()
