"""Writes the data files of RobotDx's second round of asks (tests/browser/dx_asks_2_checks.py; RobotDx PEP 0001 §18.4).

    python3 tests/browser/fixtures/dx_asks_2/make_fixture.py

Synthetic and deterministic (closed-form curves, no clock, no random numbers), said so in each file's `source`. Times
are Unix seconds from T0, as RobotDx's host sends them, so the clock reads as a wall clock.
  - measures.json: the live append dataset's schema (no rows: the checks push them, stream `check`), RobotDx's
    `measures` (PEP 0001 §18.1) with the limits as four columns and `reading` a TYPED number column whose cells are
    `{value, unit}` (ask 4). readings.json: the rows the checks push, and the same rows as a file (the plain twin).
      board_temp  40 ± 3, warn_hi 60 until T0 + 20 s and 65 from then (a limit that changes), error_hi 70, no lower side
      supply_v    24 ± 0.6, warn 22..26 and error 20..28 (both sides)
  - components.json (a file) and nodes.json (a live keyed backlog): one tree, rack > plate1 > stations A and B, plate2 >
    station C; in the checks station C moves under plate1 at T0 + 25 s (a new version of its node). gates.json: the
    live keyed gate rows' schema (the checks push their versions). Ranks are RobotDx's (pass 0, warn 1, fail 4).
  - checks.json and parts.json: the peek's rows (ask 3). `stock` has every section's fields and three parts; `plain` has
    a level and a message only, and a note with a reason it is empty; `evidence` has a level and two parts.
"""

import json
import math
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = "synthetic: tests/browser/fixtures/dx_asks_2/make_fixture.py (illustrative numbers)"
T0 = 1792631000.0
RANKS = {"0": "pass", "1": "warn", "4": "fail"}


def write(name, doc):
    (HERE / name).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------------------- asks 1 and 4: the readings
LIMIT_PROPS = {
    "warn_lo": {"type": "number", "label": "Warn below"}, "warn_hi": {"type": "number", "label": "Warn above"},
    "error_lo": {"type": "number", "label": "Error below"}, "error_hi": {"type": "number", "label": "Error above"},
}
MEASURE_PROPS = {
    "t": {"type": "number", "unit": "s", "label": "Received", "display": "clock"},
    "check": {"type": "text", "label": "Check"},
    "value": {"type": "number", "label": "Value"},
    # WHY typed: ask 4, a typed number column must keep a cell's unit (RobotDx typed it as nothing to keep it)
    "reading": {"type": "number", "label": "Reading"},
    **LIMIT_PROPS,
}
write("measures.json", {"id": "measures", "title": "Diagnostic readings", "titleProperty": "check", "source": SOURCE,
                        "properties": MEASURE_PROPS, "rows": []})
write("latest.json", {"id": "latest", "title": "Newest reading per check", "titleProperty": "check", "source": SOURCE,
                      "properties": MEASURE_PROPS, "rows": []})

readings = []
for k in range(81):
    t = T0 + k * 0.5
    v = round(40 + 3 * math.sin(k / 5), 4)
    readings.append({"id": f"board_temp-{k:03d}", "t": t, "check": "board_temp", "value": v, "reading": {"value": v, "unit": "°C"},
                     "warn_lo": None, "warn_hi": 60 if k < 40 else 65, "error_lo": None, "error_hi": 70})
    w = round(24 + 0.6 * math.sin(k / 7), 4)
    readings.append({"id": f"supply_v-{k:03d}", "t": t, "check": "supply_v", "value": w, "reading": {"value": w, "unit": "V"},
                     "warn_lo": 22, "warn_hi": 26, "error_lo": 20, "error_hi": 28})
write("readings.json", {"id": "readings", "title": "Diagnostic readings (a file)", "titleProperty": "check", "source": SOURCE,
                        "properties": MEASURE_PROPS, "rows": readings})

# ---------------------------------------------------------------------------------------- ask 2: the roll-up's trees
TREE = [("rack", "Rack", None), ("plate1", "Plate 1", "rack"), ("plate2", "Plate 2", "rack"),
        ("stationA", "Station A", "plate1"), ("stationB", "Station B", "plate1"), ("stationC", "Station C", "plate2")]
WORST = {"type": "number", "label": "Worst gate", "labels": RANKS}
write("components.json", {"id": "components", "title": "Components (a file)", "titleProperty": "label", "source": SOURCE,
                          "properties": {"id": {"type": "text"}, "label": {"type": "text", "label": "Component"},
                                         "parent": {"type": "text", "label": "Parent"}, "worst": WORST},
                          "rows": [{"id": i, "label": label, "parent": parent} for i, label, parent in TREE]})
write("nodes.json", {"id": "nodes", "title": "Components (live)", "titleProperty": "label", "source": SOURCE,
                     "properties": {"id": {"type": "text"}, "t": {"type": "number", "unit": "s"}, "label": {"type": "text", "label": "Component"},
                                    "parent": {"type": "text", "label": "Parent"}, "worst": WORST},
                     "rows": [{"id": i, "t": T0, "label": label, "parent": parent} for i, label, parent in TREE]})
write("gates.json", {"id": "gates", "title": "Gates", "titleProperty": "gate", "source": SOURCE,
                     "properties": {"id": {"type": "text"}, "t": {"type": "number", "unit": "s"}, "device": {"type": "text", "label": "Device"},
                                    "gate": {"type": "text", "label": "Gate"}, "rank": {"type": "number", "label": "Rank", "labels": RANKS}},
                     "rows": []})

# ---------------------------------------------------------------------------------------- ask 3: the peek's rows
CHECK_PROPS = {
    "id": {"type": "text"}, "t": {"type": "number", "unit": "s"}, "name": {"type": "text", "label": "Check"},
    "level": {"type": "text", "label": "Level"}, "message": {"type": "text", "label": "Message"},
    "metric": {"type": "text", "label": "Metric"}, "value": {"type": "number", "label": "Value"}, "unit": {"type": "text", "label": "Unit"},
    "t0": {"type": "number", "label": "From"}, "t1": {"type": "number", "label": "To"}, "run": {"type": "text", "label": "Run"},
    "diagnostic": {"type": "text", "label": "Diagnostic"}, "hint": {"type": "text", "label": "View"}, "role": {"type": "text", "label": "Role"},
    "note": {"type": "text", "label": "Note"},
}
EMPTY = {k: None for k in ("metric", "value", "unit", "t0", "t1", "run", "diagnostic", "hint", "role", "note")}
write("checks.json", {"id": "checks", "title": "Checks", "titleProperty": "name", "source": SOURCE, "properties": CHECK_PROPS, "rows": [
    {"id": "stock", "t": T0 + 1, "name": "Board temperature", "level": "warn", "message": "above its warn limit", "metric": "board_temp",
     "value": 61.2, "unit": "Cel", "t0": T0 - 10, "t1": T0, "run": "r1", "diagnostic": "driver.board_temp", "hint": "threshold_band",
     "role": "health", "note": "reviewed"},
    {"id": "plain", "t": T0 + 1, "name": "Heartbeat", "level": "ok", "message": "alive", **EMPTY,
     "note": {"value": None, "why": "not measured on this host"}},
    {"id": "evidence", "t": T0 + 1, "name": "Stop error", "level": "ok", "message": "within tolerance", **EMPTY},
]})
write("parts.json", {"id": "parts", "title": "Parts", "titleProperty": "check", "source": SOURCE,
                     "properties": {"id": {"type": "text"}, "t": {"type": "number", "unit": "s"}, "check": {"type": "text", "label": "Check"},
                                    "x": {"type": "number", "label": "x"}, "y": {"type": "number", "label": "y"}},
                     "rows": [{"id": f"stock#{i}", "t": T0 + 1, "check": "stock", "x": i, "y": round(58 + i * 1.6, 2)} for i in range(3)]
                     + [{"id": f"evidence#{i}", "t": T0 + 1, "check": "evidence", "x": i, "y": round(0.2 + i * 0.1, 2)} for i in range(2)]})
