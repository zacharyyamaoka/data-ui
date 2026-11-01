"""python3 -m unittest discover -s tools -p 'test_*.py'

The Python checker knows `type: lineage` (docs/CONTRACT.md §21) exactly as the JS one does
(tests/unit/check-lineage.test.mjs), and the two gallery cases check clean against their data."""

import pathlib
import tempfile
import unittest

import check_views

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROPS = {"name", "parents", "round", "round_label", "thumb", "status"}


class CheckLineage(unittest.TestCase):
    def problems(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "v.base"
            path.write_text(text, encoding="utf-8")
            return list(check_views.check_file(path, PROPS, "d", None))

    def errors(self, text):
        return [f"{line} {check_views.show(where)} {message}" for level, line, where, message in self.problems(text) if level == "error"]

    def test_full_block_is_clean(self):
        good = ("views:\n  - type: lineage\n    name: Tree\n    lineage:\n      parents: parents\n      x: round\n      xLabel: round_label\n"
                "      image: thumb\n      label: name\n      focus: r16-02\n      kept: { status: [picked, liked] }\n      extinct: collapse\n      layout: radial\n")
        self.assertEqual(self.problems(good), [])

    def test_required(self):
        self.assertTrue(any("lineage" in e for e in self.errors("views:\n  - type: lineage\n    name: T\n")))
        self.assertTrue(any("parents" in e for e in self.errors("views:\n  - type: lineage\n    name: T\n    lineage: { x: round }\n")))

    def test_properties_checked(self):
        e = self.errors("views:\n  - type: lineage\n    name: T\n    lineage: { parents: parent, x: rund, kept: { stat: [a] } }\n")
        self.assertTrue(any("'parent' is not a property of d (did you mean 'parents'?)" in x for x in e), e)
        self.assertTrue(any("'rund' is not a property of d" in x for x in e), e)
        self.assertTrue(any("'stat' is not a property of d" in x for x in e), e)

    def test_enums(self):
        e = self.errors("views:\n  - type: lineage\n    name: T\n    lineage: { parents: parents, extinct: hide, layout: circle }\n")
        self.assertTrue(any('extinct "hide" is not one of show, collapse' in x for x in e), e)
        self.assertTrue(any('layout "circle" is not one of rectangular, radial' in x for x in e), e)

    def test_cases_check_clean(self):
        for case, data in (("brand-lineage", "proposals.json"), ("model-lineage", "ladder.json")):
            status = self._run(case, data)
            self.assertEqual(status, 0, case)

    def _run(self, case, data):
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            status = check_views.main([str(ROOT / "gallery" / "examples" / case / "views.base"), "--data", str(ROOT / "gallery" / "examples" / case / data)])
        if status:
            print(out.getvalue())
        return status


if __name__ == "__main__":
    unittest.main()
