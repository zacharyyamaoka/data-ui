"""python3 -m unittest discover -s tools -p 'test_*.py'

The checker's contract (docs/SPEC.md §5.7): every Bases file Zach already has passes; data-ui's examples pass
against their datasets; each mistake in examples/broken.base is named on its own line with its line number and a
suggestion. The vault and table-lane cases are skipped, never faked, when those trees are not on disk."""

import io
import pathlib
import unittest
from contextlib import redirect_stdout

import check_views

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("~/zach_brain")
LANE = pathlib.Path("~/robotparts/.claude/worktrees/lane-tables/design/tables-2026-10-25")


def run(*args):
    out = io.StringIO()
    with redirect_stdout(out):
        status = check_views.main([str(a) for a in args])
    return status, out.getvalue()


class CheckViews(unittest.TestCase):
    def test_examples_pass_against_their_datasets(self):
        for base, data in [("actuators.base", "actuators.schema.json"), ("runs.base", "runs.schema.json")]:
            status, out = run(ROOT / "examples" / base, "--data", ROOT / "examples" / data)
            self.assertEqual(status, 0, out)
            self.assertIn("0 errors, 0 warnings", out)

    def test_broken_example_names_every_mistake(self):
        status, out = run(ROOT / "examples" / "broken.base", "--data", ROOT / "examples" / "actuators.schema.json")
        self.assertEqual(status, 1)
        expected = [
            "broken.base:3: error: filters: unknown key 'AND' (did you mean 'and'?)",
            "broken.base:11: error: views[0].chart.encoding: unknown key 'colour' (did you mean 'color'?)",
            "views[0].chart.encoding.x.scale.type: \"logarithmic\" is not one of",
            "(did you mean 'log'?)",
            "broken.base:10: error: views[0].chart.mark: \"dots\" is not one of",
            "broken.base:19: error: views[1].sort[0].direction: \"desc\" is not one of ASC, DESC (did you mean 'DESC'?)",
            "broken.base:21: error: views[2]: needs 'chart'",
            "warning: views[0].type: data-ui cannot draw type 'chrat' (did you mean 'chart'?)",
            "warning: views[1].groupby: unknown view key 'groupby' (did you mean 'groupBy'?)",
            "views[0].chart.encoding.x.field: 'mas' is not a property of actuators.schema.json (did you mean 'mass'?)",
            "views[1].order[1]: 'peak_torq' is not a property of actuators.schema.json (did you mean 'peak_torque'?)",
            "8 errors, 2 warnings",
        ]
        for line in expected:
            self.assertIn(line, out)

    @unittest.skipUnless(VAULT.exists(), "the vault is not on this machine")
    def test_every_base_file_in_the_vault_passes(self):
        files = [p for p in VAULT.rglob("*.base") if ".claude" not in p.parts and ".trash" not in p.parts]
        self.assertGreater(len(files), 50)
        status, out = run(*files, "--quiet")
        self.assertEqual(status, 0, out)
        self.assertIn("0 errors, 0 warnings", out)

    @unittest.skipUnless((LANE / "site" / "data").exists(), "the table lane's built data is not on disk")
    def test_the_table_lanes_presets_pass_against_their_rows(self):
        for name in ["actuators", "datasheet", "models", "sources"]:
            status, out = run(LANE / "presets" / f"{name}.base", "--data", LANE / "site" / "data" / f"{name}.json")
            self.assertEqual(status, 0, out)

    @unittest.skipUnless((LANE / "site" / "data").exists(), "the table lane's built data is not on disk")
    def test_the_lanes_rows_lack_a_photo_column_yet(self):
        # A real finding, kept as a test so it flips when robotparts adds photos to the dataset (SPEC §11, step 3).
        status, out = run(ROOT / "examples" / "actuators.base", "--data", LANE / "site" / "data" / "actuators.json")
        self.assertEqual(status, 1)
        self.assertIn("'photo' is not a property of actuators.json", out)

    def test_source_view(self):
        """`type: source` and its `rows: all | filtered` (amendment 2026-10-26 (raw source view), CONTRACT §24)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "v.base"
            path.write_text("views:\n  - type: source\n    name: Raw\n  - type: source\n    name: Shown\n    rows: filtered\n", encoding="utf-8")
            self.assertEqual(list(check_views.check_file(path, {"a"}, "d", None)), [])
            path.write_text("views:\n  - type: source\n    name: Raw\n    rows: some\n", encoding="utf-8")
            bad = [(level, check_views.show(where)) for level, _, where, _ in check_views.check_file(path, {"a"}, "d", None)]
            self.assertEqual(bad, [("error", "views[0].rows")], bad)

    def test_open_modes(self):
        """`open:` (amendment 2026-10-26 (open modes)): top level and per view, short or long form; an unknown mode is
        an error; link with no URL anywhere warns that it falls back to side."""
        import tempfile
        props = {"name", "url", "page"}
        with tempfile.TemporaryDirectory() as tmp:
            def problems(text, **kw):
                path = pathlib.Path(tmp) / "v.base"
                path.write_text(text, encoding="utf-8")
                return list(check_views.check_file(path, props, "d", None, **kw))
            good = "open: { mode: side, splitAt: 1100 }\nviews:\n  - type: table\n    name: A\n    open: expand\n  - type: table\n    name: B\n    open: { mode: link, url: url }\n"
            self.assertEqual(problems(good, link="url"), [])
            bad = [f"{line} {check_views.show(where)} {message}" for level, line, where, message in problems("open: sideways\nviews:\n  - type: table\n    name: A\n    open: { mode: peek }\n") if level == "error"]
            self.assertTrue(any(e.startswith('1 open "sideways" is not one of expand, side, link') and "did you mean 'side'" in e for e in bad), bad)
            self.assertTrue(any(e.startswith('5 views[0].open.mode "peek" is not one of expand, side, link') for e in bad), bad)
            typo = problems("views:\n  - type: table\n    name: A\n    open: { mode: link, url: pag }\n", link="url")
            self.assertTrue(any(level == "error" and "'pag' is not a property of d (did you mean 'page'?)" in m for level, _, _, m in typo), typo)
            nolink = problems("open: link\nviews:\n  - type: table\n    name: A\n  - type: table\n    name: B\n    open: { mode: link }\n", link=None)
            self.assertEqual([(level, check_views.show(where)) for level, _, where, _ in nolink], [("warning", "open"), ("warning", "views[1].open")], nolink)
            self.assertTrue(all("falls back to side" in m for _, _, _, m in nolink), nolink)

    def test_graph_layout_engine(self):
        """`layout.engine` on a graph (amendment 2026-10-27, graph layout engines): flow or mermaid; any other engine is
        an error that names both."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            def problems(engine):
                path = pathlib.Path(tmp) / "v.base"
                path.write_text(f"views:\n  - type: graph\n    name: A\n    edges: {{ property: depends_on }}\n    layout: {{ engine: {engine}, direction: BT }}\n", encoding="utf-8")
                return list(check_views.check_file(path, {"title", "depends_on"}, "d", None))
            self.assertEqual(problems("flow"), [])
            self.assertEqual(problems("mermaid"), [])
            bad = [f"{line} {check_views.show(where)} {message}" for level, line, where, message in problems("mermiad") if level == "error"]
            self.assertEqual(bad, ["5 views[0].layout.engine \"mermiad\" is not one of flow, mermaid (did you mean 'mermaid'?)"], bad)

    def test_time_groups(self):
        """groupBy / subGroupBy `by:` (amendment 2026-10-26 (time groups and peek trail)): one of day, week, month,
        quarter, year; `gaps` a yes/no; a grain on a property the data does not type as a date warns."""
        import tempfile
        props = {"started", "model", "env"}
        types = {"started": "date", "model": "text", "env": "text"}
        with tempfile.TemporaryDirectory() as tmp:
            def problems(text):
                path = pathlib.Path(tmp) / "v.base"
                path.write_text(text, encoding="utf-8")
                return [(level, line, check_views.show(where), message) for level, line, where, message in check_views.check_file(path, props, "runs.json", types)]
            good = "views:\n  - type: table\n    name: A\n    groupBy: { property: started, by: week, gaps: true }\n  - type: pivot\n    name: B\n    splitBy: [env]\n    groupBy: { property: started, by: quarter, direction: DESC }\n    subGroupBy: { property: started, by: month }\n"
            self.assertEqual(problems(good), [])
            bad = problems("views:\n  - type: table\n    name: A\n    groupBy: { property: started, by: weekly }\n  - type: table\n    name: B\n    subGroupBy: { property: started, by: month, gaps: often }\n")
            self.assertIn(("error", 4, "views[0].groupBy.by", "\"weekly\" is not one of day, week, month, quarter, year (did you mean 'week'?)"), bad)
            self.assertTrue(any(level == "error" and line == 7 and where == "views[1].subGroupBy.gaps" and message.startswith("must be boolean") for level, line, where, message in bad), bad)
            text = problems("views:\n  - type: table\n    name: A\n    groupBy: { property: model, by: month }\n")
            self.assertEqual(text, [("warning", 4, "views[0].groupBy.by", "'by: month' groups dates, and 'model' is text: a value that is not an ISO date falls in \"No model\"")])


if __name__ == "__main__":
    unittest.main()
