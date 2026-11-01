"""python3 -m unittest discover -s tools -p 'test_*.py'

Source columns (docs/CONTRACT.md §36, docs/peps/0021-source-columns.md), the Python checker's half of tests/unit/source-columns.test.mjs:
a list of sources unfolds to columns a .base may name, a value with several sources is a formula with no text, and the checker says
what a formula data-ui does not run will do. FROZEN: written before the code, red first."""

import io
import pathlib
import re
import tempfile
import unittest
from contextlib import redirect_stdout

import check_views

ROOT = pathlib.Path(__file__).resolve().parent.parent
PART = ROOT / "tests" / "browser" / "fixtures" / "source-precedence" / "part.json"


def run(text, data=PART):
    with tempfile.TemporaryDirectory() as folder:
        file = pathlib.Path(folder) / "views.base"
        file.write_text(text, encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            check_views.main([str(file), *(["--data", str(data)] if data else [])])
    said = out.getvalue()
    counts = re.search(r"(\d+) errors?, (\d+) warnings?", said)
    return int(counts.group(1)), int(counts.group(2)), said


def view(order, extra=""):
    return f"views:\n  - type: table\n    name: V\n    order: {order}\n{extra}"


class SourceColumns(unittest.TestCase):
    def test_a_list_of_sources_unfolds_to_columns_a_file_may_name(self):
        props = check_views.dataset_properties(PART)
        for name in ("nominal@bench", "nominal@chat", "nominal@source", "nominal@*"):
            self.assertIn(name, props)
        errors, _, said = run(view("[field, nominal, nominal@bench, nominal@source, nominal@*]"))
        self.assertEqual(errors, 0, said)

    def test_a_source_the_data_does_not_have_is_named(self):
        errors, _, said = run(view("[field, nominal@nope]"))
        self.assertEqual(errors, 1, said)
        self.assertIn("nominal@nope", said)

    def test_formula_is_bases_name_for_a_value_with_several_sources(self):
        errors, _, said = run(view("[field, formula.nominal]"))
        self.assertEqual(errors, 0, said)
        errors, _, said = run(view("[field, formula.nope]"))
        self.assertEqual(errors, 1, said)

    def test_a_view_says_no_to_the_source_column(self):
        errors, warnings, said = run(view("[field, nominal]", "    sourceColumn: false\n"))
        self.assertEqual((errors, warnings), (0, 0), said)

    def test_a_formula_data_ui_does_not_run_is_said_at_its_line(self):
        errors, warnings, said = run(f"formulas:\n  n: 'price * 2'\n{view('[field]')}")
        self.assertEqual(errors, 0, said)
        self.assertEqual(warnings, 1, said)
        self.assertIn("Obsidian", said)
        for spelling in ("[a, b].filter(!value.isEmpty())[0]", '[a, note["b c"]].filter(value.isType("boolean") || !value.isEmpty())[0]'):
            errors, warnings, said = run(f"formulas:\n  n: '{spelling}'\n{view('[field]')}")
            self.assertEqual((errors, warnings), (0, 0), said)

    def test_a_file_with_no_data_is_obsidians_own(self):
        # WHY (found by tools/test_check_views.py, which holds every .base in the vault to 0 warnings): any formula is right there
        errors, warnings, said = run(f"formulas:\n  n: 'price * 2'\n{view('[field]')}", data=None)
        self.assertEqual((errors, warnings), (0, 0), said)

    def test_a_headline_kpi_stays_the_producers(self):
        text = "formulas:\n  n: '[a, b].filter(!value.isEmpty())[0]'\nviews:\n  - type: kpi\n    name: K\n    kpi:\n      value: { property: formula.n }\n"
        errors, _, said = run(text, data=None)
        self.assertEqual(errors, 1, said)
        self.assertIn("producer", said)


if __name__ == "__main__":
    unittest.main()
