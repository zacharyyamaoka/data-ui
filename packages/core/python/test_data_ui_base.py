"""python3 -m unittest discover -s packages/core/python

The stdlib .base reader reads every gallery and example file the way PyYAML does (when PyYAML is present), writes
text it reads back unchanged, and refuses what the subset does not cover. tests/unit/base.test.mjs also checks
that it writes exactly what the JS writer writes, over the vault."""

import pathlib
import unittest

import data_ui_base as B

ROOT = pathlib.Path(__file__).resolve().parents[3]
FILES = sorted([*ROOT.glob("examples/*.base"), *ROOT.glob("gallery/examples/*/views.base")])

try:
    import yaml
except ImportError:  # the oracle is optional; the round trip is not
    yaml = None


class DataUiBase(unittest.TestCase):
    def test_reads_like_pyyaml(self):
        if yaml is None:
            self.skipTest("PyYAML is not installed")
        self.assertGreaterEqual(len(FILES), 6)
        for path in FILES:
            text = path.read_text(encoding="utf-8")
            self.assertEqual(B.loads(text), yaml.safe_load(text), path)

    def test_round_trip(self):
        for path in FILES:
            doc = B.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(B.loads(B.dumps(doc)), doc, path)

    def test_refuses_with_a_line(self):
        for text, part in [("a: &x 1", "anchors"), ("a: !x.isEmpty()", "quote it"), ("a: 1\na: 2", "twice"), ("a: [1, 2", "expected")]:
            with self.assertRaises(B.BaseSyntaxError) as caught:
                B.loads(text)
            self.assertIn(part, str(caught.exception))
            self.assertGreaterEqual(caught.exception.line, 1)

    def test_lines(self):
        _, lines = B.loads_with_lines("views:\n  - type: table\n    name: A\n")
        self.assertEqual(lines[("views", 0, "name")], 3)


if __name__ == "__main__":
    unittest.main()
