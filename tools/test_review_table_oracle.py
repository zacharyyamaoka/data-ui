"""docs/review_table_oracle.py's compare(): it fails every undeclared change (judge r5 #2's five injected regressions,
r6 #4's and r7 #2's) and passes the changes lane/types declares. Pure data, no browser: a snapshot is what SNAPSHOT
returns, its `stops` the visit's measured bands and drawn rows' boxes; a view's types are the input's (types_from)."""

import copy
import importlib.util
import math
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("review", ROOT / "docs" / "review_table_oracle.py")
review = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(review)

# the input: the case's .base (and data file) say price is a USD currency without decimals and form a select; model and
# mass stay untyped (judge r7 #2: what is typed is read from here, never from the after build's own metadata)
BASE = {
    "properties": {"price": {"displayName": "Price", "type": "currency", "currency": "USD", "decimals": 0}, "form": {"type": "select", "options": {"servo": "blue", "hub": "green"}}},
    "views": [{"type": "table", "name": "T", "order": ["model", "mass", "price", "form"]}],
}
TYPES = review.types_from(BASE, "T", {})


def compare(before, after, types=TYPES):
    return review.compare(before, after, types)


def stop(top, band, rows):
    """A stop as SNAPSHOT measures it: the scroll offset, the band [top, foot] a reader sees rows in, each drawn row as
    [index, top, bottom] on screen; the virtualizer planned what was drawn."""
    return {"top": top, "band": list(band), "rows": [list(r) for r in rows], "planned": [r[0] for r in rows]}


BEFORE = {
    "heads": {"model": {"label": "Model", "unit": ""}, "mass": {"label": "Mass", "unit": "kg"}, "price": {"label": "Price", "unit": ""}, "form": {"label": "Form", "unit": ""}},
    "groupHeads": [],
    "modelIds": ["a", "b"],
    "leafOrder": ["model", "mass", "price", "form"],
    # every row of the view in drawn order (group rows included)
    "flatIds": ["group:brand:Acme", "a", "b"],
    # one stop: the box's client area runs from 0 to 400 under a 30 px header; the three 30 px rows end at 120, the
    # view's last row (a short table: the band's foot stays blank below it)
    "stops": [stop(0, [30, 400], [(0, 30, 60), (1, 60, 90), (2, 90, 120)])],
    "rows": [
        {"kind": "group", "id": "group:brand:Acme", "index": 0, "label": "Acme", "cells": {}, "values": {}},
        {"kind": "row", "id": "a", "index": 1, "cells": {"model": "A1", "mass": "1.5", "price": "70", "form": "servo"}, "values": {"model": "A1", "mass": 1.5, "price": 70, "form": "servo"}},
        {"kind": "row", "id": "b", "index": 2, "cells": {"model": "B2", "mass": "2", "price": "1,250", "form": "hub"}, "values": {"model": "B2", "mass": 2, "price": 1250, "form": "hub"}},
    ],
}


def lane_after():
    """The declared drawing: price typed as USD currency (no decimals), form a select (a pill per value), the unit as a
    '(kg)' caption."""
    a = copy.deepcopy(BEFORE)
    a["heads"]["mass"]["unit"] = "(kg)"
    a["rows"][1]["cells"]["price"] = "$70"
    a["rows"][2]["cells"]["price"] = "$1,250"
    a["rows"][1]["marks"] = {"form": ["pill:servo"]}
    a["rows"][2]["marks"] = {"form": ["pill:hub"]}
    return a


def visit(n, head=30, foot=400, row=30, overscan=2):
    """A build's visit of a view of n rows as SNAPSHOT makes and measures it: the box's client area from 0 to `foot`,
    its sticky header `head` px tall, rows `row` px each at their places, a virtualizer drawing the rows in the band and
    `overscan` more each side; down 0.8 of the band a step until the first CAP rows are drawn, then the last screen."""
    band = [head, foot]
    seen = foot - head
    end = max(0, n * row - seen)  # the largest scroll offset

    def at(top):
        first = max(0, math.floor(top / row) - overscan)
        last = min(n - 1, math.ceil((top + seen) / row) - 1 + overscan)
        return stop(top, band, [(i, head - top + i * row, head - top + (i + 1) * row) for i in range(first, last + 1)])

    stops, top = [at(0)], 0
    while stops[-1]["rows"][-1][0] < min(n, review.CAP) - 1 and top < end:
        top = min(end, top + math.floor(0.8 * seen))
        stops.append(at(top))
    if top < end:
        stops.append(at(end))
    return stops


def view(n, **geometry):
    """A plain view of n rows (model, mass), as a build snapshots it: the visit's stops, and every sample row it drew."""
    stops = visit(n, **geometry)
    drawn = {r[0] for s in stops for r in s["rows"]}
    return {
        "heads": {"model": {"label": "Model", "unit": ""}, "mass": {"label": "Mass", "unit": ""}},
        "groupHeads": [], "modelIds": [f"r{i}" for i in range(n)], "leafOrder": ["model", "mass"], "flatIds": [f"r{i}" for i in range(n)],
        "stops": stops,
        "rows": [{"kind": "row", "id": f"r{i}", "index": i, "cells": {"model": f"M{i}", "mass": str(i)}, "values": {"model": f"M{i}", "mass": i}} for i in review.sample(n) if i in drawn],
    }


def says(problems, *words):
    """True when some problem says every one of `words` (the reason a mutation fails, not just that something did)."""
    return any(all(w in p for w in words) for p in problems)


class Compare(unittest.TestCase):
    def test_declared_changes_pass(self):
        self.assertEqual(compare(BEFORE, lane_after()), [])

    def test_a_removed_row_fails(self):
        a = lane_after()
        a["modelIds"] = ["a"]
        del a["rows"][2]
        self.assertTrue(compare(BEFORE, a))

    def test_a_removed_untyped_column_fails(self):
        a = lane_after()
        del a["heads"]["model"]
        for r in a["rows"]:
            r["cells"].pop("model", None)
        self.assertTrue(compare(BEFORE, a))

    def test_a_blanked_typed_value_fails(self):
        a = lane_after()
        a["rows"][1]["cells"]["price"] = ""
        self.assertTrue(compare(BEFORE, a))

    def test_a_changed_unit_fails(self):
        a = lane_after()
        a["heads"]["mass"]["unit"] = "(USD)"
        self.assertTrue(compare(BEFORE, a))

    def test_a_replaced_group_label_fails(self):
        a = lane_after()
        a["rows"][0]["label"] = "Other"
        a["rows"][0]["id"] = "group:brand:Other"
        self.assertTrue(compare(BEFORE, a))

    def test_an_untyped_cell_change_fails(self):
        a = lane_after()
        a["rows"][1]["cells"]["model"] = "A1 (edited)"
        self.assertTrue(compare(BEFORE, a))

    def test_rows_reordered_fail(self):
        a = lane_after()
        a["modelIds"] = ["b", "a"]
        self.assertTrue(compare(BEFORE, a))

    def test_a_typed_value_formatted_wrongly_fails(self):
        a = lane_after()
        a["rows"][2]["cells"]["price"] = "$1,250.00"
        self.assertTrue(compare(BEFORE, a))


class R6Mutations(unittest.TestCase):
    """Judge r6 #4: regressions the r5 review still approved — each must now be a problem."""

    def test_dropping_the_last_drawn_row_fails(self):
        a = lane_after()
        del a["rows"][-1]
        self.assertTrue(compare(BEFORE, a))

    def test_a_duplicated_drawn_row_fails(self):
        a = lane_after()
        a["rows"].append(copy.deepcopy(a["rows"][-1]))
        self.assertTrue(compare(BEFORE, a))

    def test_a_replaced_merged_heading_fails(self):
        b = copy.deepcopy(BEFORE)
        b["groupHeads"] = ["Identity", "Physical"]
        a = lane_after()
        a["groupHeads"] = ["Identity", "Other"]
        self.assertTrue(compare(b, a))

    def test_a_dropped_merged_heading_fails(self):
        b = copy.deepcopy(BEFORE)
        b["groupHeads"] = ["Identity", "Physical"]
        a = lane_after()
        a["groupHeads"] = ["Identity"]
        self.assertTrue(compare(b, a))

    def test_a_unit_moved_onto_its_merged_heading_passes(self):
        b = copy.deepcopy(BEFORE)
        b["heads"]["coulomb:median"] = {"label": "median", "unit": "N·m"}
        b["leafOrder"] = b["leafOrder"] + ["coulomb:median"]
        b["groupHeads"] = ["Coulomb"]
        a = lane_after()
        a["heads"]["coulomb:median"] = {"label": "median", "unit": ""}
        a["leafOrder"] = a["leafOrder"] + ["coulomb:median"]
        a["groupHeads"] = ["Coulomb (N·m)"]
        self.assertEqual(compare(b, a), [])

    def test_reordered_leaf_columns_fail(self):
        a = lane_after()
        a["leafOrder"] = ["mass", "model", "price", "form"]
        a["heads"] = {k: a["heads"][k] for k in a["leafOrder"]}
        self.assertTrue(compare(BEFORE, a))

    def test_fewer_rows_drawn_because_fewer_fit_passes(self):
        # judge r7: proved by measured geometry, not by a smaller plan. A header 30 px taller leaves a band 30 px
        # shorter; the after build draws one row fewer at the top, and those rows still cover its band to the foot
        b, a = view(8, head=30, foot=150, overscan=0), view(8, head=60, foot=150, overscan=0)
        self.assertLess(len(a["stops"][0]["rows"]), len(b["stops"][0]["rows"]))
        self.assertEqual(a["stops"][0]["rows"][-1][2], a["stops"][0]["band"][1])
        self.assertEqual(compare(b, a, {}), [])

    def test_a_row_drawn_at_another_rows_index_fails(self):
        a = lane_after()
        a["rows"][2]["index"] = 1
        self.assertTrue(compare(BEFORE, a))

    def test_a_row_missing_from_the_view_fails(self):
        a = lane_after()
        a["flatIds"] = ["group:brand:Acme", "a"]
        a["stops"] = [stop(0, [30, 400], [(0, 30, 60), (1, 60, 90)])]
        del a["rows"][-1]
        self.assertTrue(compare(BEFORE, a))

    def test_a_rolled_up_typed_cell_reads_its_count(self):
        b, a = copy.deepcopy(BEFORE), lane_after()
        for snap in (b, a):
            snap["rows"][1]["values"]["form"] = {"value": None, "rolled": 2, "why": "2 forms"}
            snap["rows"][1]["cells"]["form"] = "2 values"
            snap["rows"][1].get("marks", {}).pop("form", None)  # a rolled-up cell is its count, no pill
        self.assertEqual(compare(b, a), [])
        a["rows"][1]["cells"]["form"] = "—"
        self.assertTrue(compare(b, a))

    def test_currency_reverted_to_its_old_text_fails(self):
        a = lane_after()
        a["rows"][1]["cells"]["price"] = "70"
        a["rows"][2]["cells"]["price"] = "1,250"
        self.assertTrue(compare(BEFORE, a))


class R7Mutations(unittest.TestCase):
    """Judge r7 #2: regressions the r6 review still approved, because each build's drawn rows were held only to its own
    virtualizer's plan, only the rows both builds drew were read, and a type was whatever the after build's own
    metadata said. Each must be a problem."""

    def test_dropping_the_final_drawn_row_and_its_planned_index_fails(self):
        # the view's rows (model and flat ids) unchanged: only the drawing lost its last row, its plan, and its reading
        a = lane_after()
        a["stops"][-1]["rows"].pop()
        a["stops"][-1]["planned"].pop()
        del a["rows"][-1]
        problems = compare(BEFORE, a)
        self.assertTrue(says(problems, "after at scroll 0", "the band's foot is blank from 90", "row 2 of 3 is not drawn"), problems)
        self.assertTrue(says(problems, "after:", "sample rows never drawn", "[2]"), problems)

    def test_drawing_no_rows_and_planning_none_fails(self):
        a = lane_after()
        for s in a["stops"]:
            s["rows"], s["planned"] = [], []
        a["rows"] = []
        problems = compare(BEFORE, a)
        self.assertTrue(says(problems, "after at scroll 0", "no row drawn, the view has 3"), problems)
        self.assertTrue(says(problems, "after: 3 of the review's 3 sample rows never drawn"), problems)

    def test_a_corrupted_cell_in_a_row_only_the_after_build_drew_fails(self):
        # the before build drew a shorter window (rows 0-1, its band ending at 90); the after build drew row 2 as well,
        # with a wrong cell. Both builds must draw the same sample, so the before build's gap is a problem of its own
        b = copy.deepcopy(BEFORE)
        b["stops"] = [stop(0, [30, 90], [(0, 30, 60), (1, 60, 90)])]
        del b["rows"][-1]
        a = lane_after()
        a["rows"][2]["cells"]["model"] = "B2 (corrupted)"
        problems = compare(b, a)
        self.assertTrue(says(problems, "before: 1 of the review's 3 sample rows never drawn", "[2]"), problems)
        # and once both builds draw it, the corrupted cell is read and fails on its own
        self.assertTrue(says(compare(BEFORE, a), "row 'b': model 'B2' -> 'B2 (corrupted)'"))

    def test_currency_without_its_kind_metadata_drawn_as_before_fails(self):
        # the input .base types price as a currency; the after build's own metadata dropped that and drew the old text.
        # The type comes from the input, so the after build's metadata cannot switch the check off
        a = lane_after()
        a["columns"] = {"price": {"type": "number"}}
        a["rows"][1]["cells"]["price"] = "70"
        a["rows"][2]["cells"]["price"] = "1,250"
        types = review.types_from({"properties": {"price": {"type": "currency", "currency": "USD", "decimals": 0}, "form": {"type": "select"}}}, "T", {})
        problems = review.compare(BEFORE, a, types)
        self.assertTrue(says(problems, "price (currency) '70' -> '70', expected '$70'"), problems)


class Drawing(unittest.TestCase):
    """Each build's drawing is measured at every stop (judge r7 #2): rows consecutive, abutting, covering the band."""

    def test_a_long_view_visited_past_its_first_window_passes(self):
        b, a = view(review.CAP + 50), view(review.CAP + 50, head=60)
        self.assertGreater(len(b["stops"]), 2)
        self.assertEqual(compare(b, a, {}), [])

    def test_the_review_samples_the_first_rows_and_the_last(self):
        self.assertEqual(review.sample(5), [0, 1, 2, 3, 4])
        n = review.CAP + 50
        self.assertEqual(review.sample(n), list(range(review.CAP)) + list(range(n - review.TAIL, n)))

    def test_a_build_that_stops_at_its_first_window_fails(self):
        n = review.CAP + 50
        b, a = view(n), view(n)
        a["stops"] = a["stops"][:1]
        first = {r[0] for r in a["stops"][0]["rows"]}
        a["rows"] = [r for r in a["rows"] if r["index"] in first]
        self.assertTrue(says(compare(b, a, {}), "after:", "sample rows never drawn and read"))

    def test_a_corrupted_cell_past_the_first_window_fails(self):
        n = review.CAP + 50
        for i in (200, n - 1):  # a row first drawn mid-visit, and the view's last (the last screen)
            b, a = view(n), view(n)
            next(r for r in a["rows"] if r["index"] == i)["cells"]["model"] = "corrupted"
            self.assertTrue(says(compare(b, a, {}), f"row 'r{i}': model 'M{i}' -> 'corrupted'"), i)

    def test_a_row_read_outside_the_sample_fails(self):
        n = review.CAP + 50
        b, a = view(n), view(n)
        a["rows"].append({"kind": "row", "id": f"r{review.CAP + 5}", "index": review.CAP + 5, "cells": {"model": "x", "mass": "x"}, "values": {}})
        self.assertTrue(says(compare(b, a, {}), f"row {review.CAP + 5} read outside the review's sample"))

    def test_a_row_read_but_drawn_at_no_stop_fails(self):
        b, a = view(8, foot=150), view(8, foot=150)
        for s in a["stops"]:
            s["rows"] = [r for r in s["rows"] if r[0] != 7]
            s["planned"] = [i for i in s["planned"] if i != 7]
        self.assertTrue(says(compare(b, a, {}), "row 7 read but drawn at no stop"))

    def test_fewer_rows_than_fit_fails(self):
        # the taller header again, but the top stop drew one row fewer than its band holds: its foot is blank
        b, a = view(8, head=30, foot=150, overscan=0), view(8, head=60, foot=150, overscan=0)
        a["stops"][0]["rows"].pop()
        a["stops"][0]["planned"].pop()
        self.assertTrue(says(compare(b, a, {}), "after at scroll 0", "the band's foot is blank from 120 to 150"))

    def test_the_band_top_left_blank_fails(self):
        b, a = view(8, foot=150), view(8, foot=150)
        s = a["stops"][1]
        s["rows"] = [r for r in s["rows"] if r[2] > s["band"][0] + 31]
        s["planned"] = [r[0] for r in s["rows"]]
        self.assertTrue(says(compare(b, a, {}), f"after at scroll {s['top']}", "the band's top is blank"))

    def test_a_gap_between_drawn_rows_fails(self):
        b, a = view(8, foot=150), view(8, foot=150)
        for r in a["stops"][0]["rows"][2:]:
            r[1] += 10
            r[2] += 10
        self.assertTrue(says(compare(b, a, {}), "after at scroll 0", "+10.0 px between rows 1 and 2"))

    def test_a_row_missing_between_drawn_rows_fails(self):
        b, a = view(8, foot=150), view(8, foot=150)
        del a["stops"][0]["rows"][2]
        a["stops"][0]["planned"] = [r[0] for r in a["stops"][0]["rows"]]
        self.assertTrue(says(compare(b, a, {}), "after at scroll 0", "rows [2] missing between drawn rows"))

    def test_a_row_drawn_twice_at_a_stop_fails(self):
        b, a = view(8, foot=150), view(8, foot=150)
        a["stops"][0]["rows"].append(list(a["stops"][0]["rows"][-1]))
        self.assertTrue(says(compare(b, a, {}), "after at scroll 0", "drawn twice"))

    def test_drawing_other_rows_than_planned_fails(self):
        # the plan is an extra consistency check only: it never proves the drawing complete
        b, a = view(8, foot=150), view(8, foot=150)
        a["stops"][0]["planned"].append(99)
        self.assertTrue(says(compare(b, a, {}), "after at scroll 0", "virtualizer planned"))

    def test_a_view_with_no_columns_in_either_build_has_no_band_to_cover(self):
        # a dashboard view reading `from:` another dataset draws no columns in the oracle's page, in both builds: its
        # rows have no cells, so no height. Nothing to cover a band with; the sample must still be drawn and read
        def bare(n=40):
            s = view(n, foot=150)
            s["heads"], s["leafOrder"] = {}, []
            for st in s["stops"]:
                st["rows"] = [[r[0], 60, 60] for r in st["rows"]]
            for r in s["rows"]:
                r["cells"], r["values"] = {}, {}
            return s
        self.assertEqual(compare(bare(), bare(), {}), [])
        a = bare()
        a["rows"] = a["rows"][:5]
        self.assertTrue(says(compare(bare(), a, {}), "after:", "sample rows never drawn and read"))

    def test_losing_every_column_fails(self):
        a = lane_after()
        a["heads"], a["leafOrder"] = {}, []
        for st in a["stops"]:
            st["rows"] = [[r[0], 30, 30] for r in st["rows"]]
        for r in a["rows"]:
            r["cells"] = {}
        problems = compare(BEFORE, a)
        self.assertTrue(says(problems, "column model is missing"), problems)

    def test_a_visit_with_no_stop_fails(self):
        a = lane_after()
        a["stops"] = []
        self.assertTrue(says(compare(BEFORE, a), "after: the visit measured no stop"))


class InputTypes(unittest.TestCase):
    """What is typed, and how, comes from the input (judge r7 #2): the .base's properties over its data file's."""

    def test_a_select_the_base_types_drawn_as_plain_text_fails(self):
        # the text of a pill and of plain text is the same; the drawing is not
        a = lane_after()
        a["rows"][1]["marks"] = {}
        self.assertTrue(says(compare(BEFORE, a), "row 'a': form (select) drawn as [] where its type draws ['pill:servo']"))

    def test_an_untyped_cell_drawn_another_way_fails(self):
        # the same text, drawn as a pill where the before build drew plain text: the input leaves model untyped
        a = lane_after()
        a["rows"][1]["marks"]["model"] = ["pill:A1"]
        self.assertTrue(says(compare(BEFORE, a), "row 'a': model drawn as [] -> ['pill:A1']"))

    def test_a_column_typed_only_by_the_after_builds_metadata_stays_untyped(self):
        # the after build calling mass a currency does not make "$2" right: the input leaves mass untyped
        a = lane_after()
        a["columns"] = {"mass": {"type": "number", "kind": "currency", "currency": "USD", "decimals": 0}}
        a["rows"][2]["cells"]["mass"] = "$2"
        self.assertTrue(says(compare(BEFORE, a), "row 'b': mass '2' -> '$2'"))

    def test_a_bar_the_base_asks_for_must_be_drawn(self):
        types = review.types_from({"properties": {**BASE["properties"], "mass": {"type": "number", "showAs": "bar"}}}, "T", {})
        a = lane_after()
        for r in a["rows"][1:]:
            r["marks"]["mass"] = ["bar"]
        self.assertEqual(compare(BEFORE, a, types), [])
        del a["rows"][2]["marks"]["mass"]
        self.assertTrue(says(compare(BEFORE, a, types), "row 'b': mass (number) drawn as [] where its type draws ['bar']"))

    def test_a_views_own_display_draws_the_column_its_way(self):
        # `display: {price: bar}` in the view: the view's bar replaces the type's drawing, its text is still the type's
        base = {**BASE, "views": [{"name": "T", "display": {"price": "bar"}}]}
        self.assertEqual(review.types_from(base, "T", {})["price"]["viewDisplay"], "bar")
        self.assertIsNone(review.drawing(review.types_from(base, "T", {})["price"], 70))
        self.assertEqual(compare(BEFORE, lane_after(), review.types_from(base, "T", {})), [])

    def test_the_data_files_options_under_the_bases(self):
        # robotparts-models: capture_fraction is a percent in the .base, its two decimals are the data file's
        types = review.types_from({"properties": {"share": {"type": "percent", "showAs": "bar"}}}, "T", {"share": {"type": "number", "decimals": 2, "kind": "text"}})
        self.assertEqual(types["share"]["kind"], "percent")  # a data file's kind never types a column
        self.assertEqual(review.expect(types["share"], 0.45), "45.00%")
        self.assertEqual(review.drawing(types["share"], 0.45), ["bar"])

    def test_note_keys_and_untyped_entries(self):
        types = review.types_from({"properties": {"note.form": {"type": "select"}, "model": {"displayName": "Model"}, "x": "y"}}, "T", {})
        self.assertEqual(sorted(types), ["form"])

    def test_a_status_rating_and_checkbox_draw_their_own(self):
        self.assertEqual(review.drawing({"kind": "status"}, "yes"), ["status:yes"])
        self.assertEqual(review.drawing({"kind": "rating", "max": 5}, 2.5), ["img:3 of 5"])
        self.assertEqual(review.drawing({"kind": "checkbox"}, True), ["img:Yes"])
        self.assertEqual(review.drawing({"kind": "multi_select"}, ["can", "ttl"]), ["pill:can", "pill:ttl"])
        self.assertEqual(review.drawing({"kind": "select"}, None), [])

    def test_input_types_reads_the_lanes_actuators_base(self):
        types = review.input_types(ROOT / "gallery" / "examples" / "robotparts-actuators", "Geared CAN under $150")
        self.assertEqual({k: types["price"][k] for k in ("kind", "currency", "decimals", "unitText")}, {"kind": "currency", "currency": "USD", "decimals": 0, "unitText": "USD"})
        self.assertEqual(types["price"]["viewDisplay"], "bar")
        self.assertEqual((types["form"]["kind"], types["level"]["kind"], types["level"]["max"]), ("select", "rating", 5))
        self.assertNotIn("model", types)


class GroupSummaries(unittest.TestCase):
    """A group row's summary of a typed column is written in the column's type (min 140 -> min $140): declared, but
    only with exactly the formatter's text for the same number; anything else fails."""

    CURRENCY = review.types_from({"properties": {"price": {"type": "currency", "currency": "USD", "decimals": 0}}}, "T", {})

    def snap(self, text):
        s = copy.deepcopy(BEFORE)
        s["heads"] = {"model": s["heads"]["model"], "price": s["heads"]["price"]}
        s["leafOrder"] = ["model", "price"]
        # one folded group: the view's only row
        s["flatIds"] = ["group:brand:Acme"]
        s["stops"] = [stop(0, [30, 400], [(0, 30, 60)])]
        s["rows"] = [{"kind": "group", "id": "group:brand:Acme", "index": 0, "label": "Acme", "cells": {"#0": "Acme 2", "#1": text}, "values": {}}]
        s["modelIds"] = ["a"]
        return s

    def test_a_typed_summary_in_its_type_passes(self):
        self.assertEqual(review.compare(self.snap("min 140"), self.snap("min $140"), self.CURRENCY), [])
        self.assertEqual(review.compare(self.snap("med 1,250"), self.snap("median $1,250"), self.CURRENCY), [])

    def test_a_typed_summary_with_another_number_fails(self):
        self.assertTrue(review.compare(self.snap("min 140"), self.snap("min $141"), self.CURRENCY))

    def test_a_typed_summary_left_in_the_old_text_fails(self):
        self.assertTrue(review.compare(self.snap("min 140"), self.snap("min 140"), self.CURRENCY))

    def test_an_untyped_summary_reformatted_fails(self):
        self.assertTrue(review.compare(self.snap("min 140"), self.snap("min $140"), {}))


if __name__ == "__main__":
    unittest.main()
