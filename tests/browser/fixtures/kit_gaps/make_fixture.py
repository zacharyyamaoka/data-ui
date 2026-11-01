"""Writes this folder's small datasets for tests/browser/kit_gaps_checks.py (deterministic; stdlib only):

    python3 -B -I tests/browser/fixtures/kit_gaps/make_fixture.py

  marks_runs.json, marks_samples.json, marks_events.json   two 5 s runs; A carries the gripper's three events (contact
      1.61, grasp 1.91 s: 0.3 s apart; release 4.97 s), B a dense run of 12 limiter events 40 ms apart and one more; the
      samples carry an `event` column set on a few rows (annotations from the view's own rows)
  levels.json      a recording of two streams' levels over 0..120 s (ok, warn, error), irregular times
  colors.json      a state column whose schema colours ok / idle / hot / custom / zero, with null cells; a second column
                   with no colours and nulls
  media.json       one rgb clip row: the depth, band and pair views filter to none
  strip.json       one run's mode register, 0..4.5 s: a state strip whose end time a transform makes
"""

import json
import math
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def write(name, doc):
    (HERE / name).write_text(json.dumps(doc, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")


def marks():
    runs = [{"run": "A", "device": "gripper", "kind": "pick", "started": "2026-10-28T10:00:00"},
            {"run": "B", "device": "gripper", "kind": "limiters", "started": "2026-10-28T11:00:00"}]
    write("marks_runs.json", {"title": "kit gaps fixture: runs", "schema": {"fields": [
        {"name": "run", "type": "string"}, {"name": "device", "type": "string"}, {"name": "kind", "type": "string"}, {"name": "started", "type": "datetime"}]}, "rows": runs})
    rows = []
    own = {("A", 60): "slip", ("A", 61): "slip end", ("B", 30): "warm"}
    for run in ("A", "B"):
        for i in range(101):
            t = round(i * 0.05, 4)
            rows.append({"t": t, "run": run, "situation": "real", "source": "real",
                         "v": round(math.sin(t * (1.3 if run == "A" else 2.1)) * 10, 4), "event": own.get((run, i))})
    write("marks_samples.json", {"title": "kit gaps fixture: samples", "schema": {"fields": [
        {"name": "t", "type": "number", "unit": "s"}, {"name": "run", "type": "string"}, {"name": "situation", "type": "string"},
        {"name": "source", "type": "string"}, {"name": "v", "type": "number", "unit": "mm"}, {"name": "event", "type": "string", "title": "Event"}]}, "rows": rows})
    events = [{"t": 1.61, "run": "A", "kind": "contact", "label": "contact"}, {"t": 1.91, "run": "A", "kind": "grasp", "label": "grasp"},
              {"t": 4.97, "run": "A", "kind": "release", "label": "release"}]
    events += [{"t": round(2.0 + i * 0.04, 4), "run": "B", "kind": "fault", "label": f"limiter {98 + i % 5} · step {i}"} for i in range(12)]
    events += [{"t": 4.0, "run": "B", "kind": "fault", "label": "none"}]
    write("marks_events.json", {"title": "kit gaps fixture: events", "schema": {"fields": [
        {"name": "t", "type": "number", "unit": "s"}, {"name": "run", "type": "string"}, {"name": "kind", "type": "string"}, {"name": "label", "type": "string"}]}, "rows": events})


def levels():
    rows = []
    plan = {"pump": [(0.0, "ok"), (11.3, "warn"), (12.1, "ok"), (47.9, "error"), (48.2, "warn"), (63.0, "ok"), (99.7, "warn"), (120.0, "ok")],
            "fan": [(0.4, "ok"), (30.05, "warn"), (30.1, "error"), (31.0, "ok"), (88.8, "warn"), (119.5, "ok")]}
    for stream, changes in plan.items():
        for t, level in changes:
            rows.append({"t": t, "stream": stream, "level": level})
    rows.sort(key=lambda r: (r["t"], r["stream"]))
    write("levels.json", {"title": "kit gaps fixture: a recorded level history", "schema": {"fields": [
        {"name": "t", "type": "number", "unit": "s"}, {"name": "stream", "type": "string"}, {"name": "level", "type": "string"}]}, "rows": rows})


def colors():
    states = ["ok", "idle", "hot", "custom", "zero", None, "ok", "idle", None, "hot"]
    others = ["a", "b", None, "a", "c", None, "b", "a", "c", None]
    rows = [{"k": f"k{i % 3}", "v": i + 1, "state": s, "other": o} for i, (s, o) in enumerate(zip(states, others))]
    write("colors.json", {"title": "kit gaps fixture: colours", "schema": {"fields": [
        {"name": "k", "type": "string"}, {"name": "v", "type": "number"},
        {"name": "state", "type": "string", "title": "State", "colors": {"ok": 1, "idle": "muted", "hot": "var(--data-bad)", "custom": "#7a3db8", "zero": 0}},
        {"name": "other", "type": "string", "title": "Other"}]}, "rows": rows})


def media():
    write("media.json", {"title": "kit gaps fixture: media", "schema": {"fields": [
        {"name": "run", "type": "string"}, {"name": "kind", "type": "string"}, {"name": "src", "type": "string"}, {"name": "poster", "type": "string"}, {"name": "t0", "type": "number", "unit": "s"}]},
        "rows": [{"run": "A", "kind": "rgb", "src": "none.mp4", "poster": "none.png", "t0": 0}]})


def strip():
    changes = [(0.0, "stopped"), (0.011, "preparing"), (0.022, "position"), (2.5, "fault"), (2.75, "position")]
    rows = []
    for i in range(91):
        t = round(i * 0.05, 4)
        mode = [m for c, m in changes if c <= t][-1]
        rows.append({"t": t, "run": "A", "mode": mode})
    for c, m in changes:
        if not any(abs(r["t"] - c) < 1e-9 for r in rows):
            rows.append({"t": c, "run": "A", "mode": m})
    rows.sort(key=lambda r: r["t"])
    write("strip.json", {"title": "kit gaps fixture: a mode register", "schema": {"fields": [
        {"name": "t", "type": "number", "unit": "s"}, {"name": "run", "type": "string"}, {"name": "mode", "type": "string", "title": "Mode"}]}, "rows": rows})


if __name__ == "__main__":
    marks()
    levels()
    colors()
    media()
    strip()
