"""Writes the RobotDx asks fixture's data files (tests/browser/dx_asks_checks.py).

    python3 tests/browser/fixtures/dx_asks/make_fixture.py

Synthetic and deterministic (closed-form curves, no clock, no random numbers), said so in each file's `source`:
  - recorded.json: 10 s of four joints at 20 Hz for the plot card over a recording. `base` swings 100 times wider than
    the others, so hiding it must rescale y (CONTRACT §31: a hidden outlier must not flatten the rest), and the three
    small ones sit apart on y, so no line covers another. The joint names were picked so each takes its own palette
    slot (format.js hueOf: shoulder 1, base 2, elbow 4, wrist 8), and a series is measured by its own colour on the
    canvas. The checks push the live rows with the same curves (dx_asks_checks.py FEEDER).
  - config.json: the settings of two entities, path a and path b, for the boards that share one dataset (a host hands
    every board the same object, as RobotDx's /dx/ does) while each declares its own file.
samples.json (the live dataset's schema, no rows) is written by hand: its rows are pushed by the checks on the wall clock.
"""

import json
import math
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = "synthetic: tests/browser/fixtures/dx_asks/make_fixture.py (illustrative numbers)"
# joint: (swing, phase, offset): the three small joints sit apart on y so no line covers another; base swings 100 times wider
JOINTS = {"shoulder": (1.0, 0.0, 8.0), "elbow": (0.8, 1.1, 0.0), "wrist": (0.6, 2.3, -8.0), "base": (100.0, 0.5, 0.0)}


def write(name, doc):
    (HERE / name).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


rows = []
for k in range(201):
    t = round(k * 0.05, 2)
    for joint, (amp, phase, offset) in JOINTS.items():
        rows.append({"id": f"{joint}-{k:03d}", "t": t, "joint": joint, "position": round(offset + amp * math.sin(t * 1.3 + phase), 4)})
write("recorded.json", {
    "id": "dx-recorded", "title": "Recorded joints", "titleProperty": "id", "source": SOURCE,
    "properties": {"t": {"type": "number", "unit": "s", "label": "Time"}, "joint": {"type": "text", "label": "Joint"},
                   "position": {"type": "number", "unit": "rad", "label": "Position"}},
    "rows": rows,
})

config = []
for path, gain in (("a", 1.5), ("b", 2.5)):
    for key, value in (("kp", gain), ("ki", gain / 10), ("limit", gain * 4)):
        config.append({"id": f"{path}.{key}", "path": path, "key": key, "value": value})
write("config.json", {
    "id": "dx-config", "title": "Configuration", "titleProperty": "key", "source": SOURCE,
    "properties": {"path": {"type": "text", "label": "Entity"}, "key": {"type": "text", "label": "Setting"},
                   "value": {"type": "number", "label": "Value"}},
    "rows": config,
})
