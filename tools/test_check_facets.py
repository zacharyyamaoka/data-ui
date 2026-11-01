"""python3 -m unittest discover -s tools -p 'test_*.py'

The Python checker learns the rail's kinds the way the Node one does (docs/CONTRACT.md §7, amendment 2026-10-26
(filters)): the schema names every kind and option with a "did you mean", and facet_problems checks that a facet
names what it filters and that its kind fits the property's type. Same file, same messages as
tests/unit/facets.test.mjs."""

import io
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout

import check_views

ROOT = pathlib.Path(__file__).resolve().parent.parent
CASE = ROOT / "gallery" / "examples" / "filters-gallery"
BROKEN = """data: actuators.json
facets:
  - { property: brand, as: slidr }
  - { property: price, as: buckets, bukets: [1, 10] }
  - { property: brand, as: slider }
  - { as: tree }
  - { property: in_stock, as: toggle, value: "yes" }
views:
  - type: table
    name: A
  - type: table
    name: B
    facets: [{ property: price, as: rating, styl: stars }, { property: brnd, as: values }]
"""


def run(*args):
    out = io.StringIO()
    with redirect_stdout(out):
        status = check_views.main([str(a) for a in args])
    return status, out.getvalue()


class CheckFacets(unittest.TestCase):
    def test_the_filters_case_checks_clean(self):
        status, out = run(CASE / "views.base", "--data", CASE / "actuators.json")
        self.assertEqual(status, 0, out)
        self.assertIn("0 errors, 0 warnings", out)

    def test_each_facet_mistake_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "broken.base"
            path.write_text(BROKEN, encoding="utf-8")
            status, out = run(path, "--data", CASE / "actuators.json")
        self.assertEqual(status, 1)
        for expected in [
            "broken.base:3: error: facets[0].as: \"slidr\" is not one of",
            "(did you mean 'slider'?)",
            "broken.base:4: error: facets[1]: unknown key 'bukets' (did you mean 'buckets'?)",
            "broken.base:5: error: facets[2].as: 'slider' needs a number property; 'brand' is text (did you mean 'values'?)",
            "broken.base:6: error: facets[3]: a tree facet needs 'property' or 'levels'",
            "views[1].facets[0]: unknown key 'styl' (did you mean 'style'?)",
            "views[1].facets[1].property: 'brnd' is not a property of actuators.json (did you mean 'brand'?)",
        ]:
            self.assertIn(expected, out)
        self.assertNotIn("facets[4]", out, "a toggle names its value with value:, never on: (YAML 1.1 reads on as true)")


if __name__ == "__main__":
    unittest.main()
