"""python3 -m unittest discover -s tools -p 'test_*.py'

The grouped gallery's keys (docs/CONTRACT.md §20) in the Python checker: numeric `bins:` on a group level, `tiles:`,
`sections:`, `groupings:` with `grouping:`, `switcher:`, `keepFilter:` and the rail's `as: nav` facet. The Node checker
gives the same answers (tests/unit/collection.test.mjs runs the case's file through it)."""

import pathlib
import tempfile
import unittest

import check_views

ROOT = pathlib.Path(__file__).resolve().parent.parent
CASE = ROOT / "gallery" / "examples" / "object-collection"
PROPS = {"name", "family", "area", "type_name", "bbox_volume_ml", "streams", "source"}
TYPES = {"name": "text", "family": "text", "area": "text", "type_name": "text", "bbox_volume_ml": "number", "streams": "list", "source": "text"}

GOOD = """facets:
  - { as: nav, follow: groupBy, clear: true }
  - { property: family, as: nav, label: Choose a material }
views:
  - type: cards
    name: Home
    groupBy: { property: family }
    subGroupBy: { property: area }
    sections: true
    tiles: { property: type_name, all: true, limit: 12, size: 96 }
    grouping: size
    keepFilter: true
    switcher: segmented
    groupings:
      - { id: material, label: Material, groupBy: { property: family }, subGroupBy: { property: area }, tiles: { property: type_name } }
      - { id: size, label: Size, groupBy: { property: bbox_volume_ml, bins: [250, 1000, 5000, 50000], log: true, unit: mL } }
      - { id: auto, label: Size (auto), groupBy: { property: bbox_volume_ml, bins: auto, log: true } }
      - { id: named, label: Size (named), groupBy: { property: bbox_volume_ml, bins: [{ label: Small, max: 1000 }, { label: Large, min: 1000 }] } }
"""


class CheckCollection(unittest.TestCase):
    def problems(self, text, props=PROPS, types=TYPES):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "v.base"
            path.write_text(text, encoding="utf-8")
            return [(level, line, check_views.show(where), message) for level, line, where, message in check_views.check_file(path, props, "objects.json", types)]

    def test_the_case_passes_against_its_data(self):
        out = self.problems((CASE / "views.base").read_text(encoding="utf-8"), props=check_views.dataset_properties(CASE / "objects.json"),
                            types=check_views.dataset_types(CASE / "objects.json"))
        self.assertEqual(out, [])

    def test_every_key_is_known(self):
        self.assertEqual(self.problems(GOOD), [])

    def test_mistakes_are_named(self):
        bad = self.problems(GOOD.replace("switcher: segmented", "switcher: pills").replace("bins: auto", "bins: sometimes")
                            .replace("grouping: size", "grouping: sise").replace("tiles: { property: type_name, all", "tiles: { property: type_nam, all"))
        text = [f"{level} {where} {message}" for level, _, where, message in bad]
        self.assertTrue(any(t.startswith('error views[0].switcher "pills" is not one of tabs, segmented, dropdown, none') for t in text), text)
        self.assertTrue(any(t.startswith("error views[0].groupings[2].groupBy.bins") for t in text), text)
        self.assertTrue(any(t.startswith("warning views[0].grouping") and "did you mean 'size'" in t for t in text), text)
        self.assertTrue(any(t.startswith("error views[0].tiles.property 'type_nam' is not a property of objects.json (did you mean 'type_name'?)") for t in text), text)

    def test_bins_rules(self):
        both = self.problems("views:\n  - type: cards\n    name: A\n    groupBy: { property: bbox_volume_ml, bins: [1, 10], by: week }\n")
        self.assertTrue(any(level == "error" and where == "views[0].groupBy.bins" and "not both" in message for level, _, where, message in both), both)
        text = self.problems("views:\n  - type: cards\n    name: A\n    groupBy: { property: family, bins: [1, 10] }\n")
        self.assertEqual([(level, where) for level, _, where, _ in text], [("warning", "views[0].groupBy.bins")], text)
        typo = self.problems("views:\n  - type: cards\n    name: A\n    groupings:\n      - { id: a, groupBy: { property: famly } }\n")
        self.assertTrue(any(level == "error" and where == "views[0].groupings[0].groupBy.property" and "did you mean 'family'" in message for level, _, where, message in typo), typo)
        twice = self.problems("views:\n  - type: cards\n    name: A\n    groupings:\n      - { id: a, groupBy: { property: family } }\n      - { id: a, groupBy: { property: source } }\n")
        self.assertTrue(any(level == "error" and where == "views[0].groupings[1].id" for level, _, where, _ in twice), twice)


if __name__ == "__main__":
    unittest.main()
