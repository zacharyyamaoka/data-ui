# /// script
# requires-python = ">=3.11"
# dependencies = ["rerun-sdk==0.40.0", "numpy"]
# ///
"""python3 -m unittest discover -s tools -p 'test_rerun_export.py'

The Open in Rerun export (docs/RERUN.md) on the dashboard-cards case, read back with the SDK: every time series
card's series is an entity with exactly the case JSON's samples after the card's filters (same t, same values), the
videos are there with one frame reference per frame, and the blueprint is inside the file. A copy of the case with one
sample changed must fail that same comparison, so the check can go red.

rerun-sdk is a build-time extra, never a dependency of data-ui: the export and the read-back run through
`uv run --script` (this file carries its own PEP 723 header for that). Skipped, with the reason, when neither the
plain python3 can import rerun nor uv is on PATH."""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CASE = ROOT / "gallery" / "examples" / "dashboard-cards"
EXPORTER = ROOT / "tools" / "rerun_export.py"
sys.path.insert(0, str(ROOT / "packages" / "core" / "python"))
from data_ui_base import loads  # noqa: E402

# The oracle's filters, written out by hand for the strings this case uses, so the test never shares the exporter's
# evaluator. A new filter string in the case fails the test until it is added here.
FILTERS = {
    None: lambda r: True,
    'joint == "elbow_joint"': lambda r: r["joint"] == "elbow_joint",
    'joint == "elbow_joint" && situation != "target"': lambda r: r["joint"] == "elbow_joint" and r["situation"] != "target",
    'kpi == "p2p_calc_time_ratio" || kpi == "wp_calc_time_ratio"': lambda r: r["kpi"] in ("p2p_calc_time_ratio", "wp_calc_time_ratio"),
}


def slug(text) -> str:
    import re
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", str(text).lower()))


def summarize(rrd: str) -> dict:
    """The .rrd as plain data: recordings, blueprint views, and every temporal entity's rows (run inside uv)."""
    import numpy as np
    from rerun.chunk import RrdReader

    reader = RrdReader(rrd)
    out = {"recordings": [s.application_id for s in reader.recordings()], "entities": {}, "static": {}}
    out["blueprints"] = [s.application_id for s in reader.blueprints()]
    out["blueprint_views"] = sorted({c.entity_path for b in reader.blueprints() for c in reader.stream(store=b).to_chunks()
                                     if c.entity_path.startswith("/view/") and c.entity_path.count("/") == 2})
    for chunk in reader.stream().to_chunks():
        batch = chunk.to_record_batch()
        names = [f.name for f in batch.schema]
        if chunk.is_static:
            out["static"].setdefault(chunk.entity_path, []).extend(n for n in names if n != "rerun.controls.RowId")
            continue
        entity = out["entities"].setdefault(chunk.entity_path, {"rows": 0, "t": [], "scalars": [], "timelines": []})
        entity["rows"] += chunk.num_rows
        # every timeline the entity is on, as [name, "duration" | "timestamp"]: a time series must be on exactly one
        for time_name in (n for n in chunk.timeline_names if n in names):
            column = batch.column(time_name)
            kind = "duration" if str(column.type).startswith("duration") else "timestamp" if str(column.type).startswith("timestamp") else str(column.type)
            if [time_name, kind] not in entity["timelines"]:
                entity["timelines"].append([time_name, kind])
            if [time_name, kind] == entity["timelines"][0]:
                # durations in seconds, timestamps in integer nanoseconds since the epoch (UTC)
                raw = column.cast("int64").to_numpy(zero_copy_only=False)
                entity["t"].extend((raw / 1e9).tolist() if kind == "duration" else raw.tolist())
        if "Scalars:scalars" in names:
            entity["scalars"].extend(np.concatenate(batch.column("Scalars:scalars").to_numpy(zero_copy_only=False)).tolist())
    return out


def can_run() -> str | None:
    try:
        import rerun  # noqa: F401
        return None
    except ImportError:
        pass
    return None if shutil.which("uv") else "rerun-sdk is not importable here and uv is not on PATH (it runs the build-time extra)"


def export(base: pathlib.Path, out: pathlib.Path) -> str:
    done = subprocess.run(["uv", "run", "--script", str(EXPORTER), str(base), "--out", str(out)], capture_output=True, text=True, timeout=600)
    if done.returncode:
        raise AssertionError(f"export failed ({done.returncode}):\n{done.stdout}\n{done.stderr}")
    return done.stdout


def read_back(rrd: pathlib.Path) -> dict:
    try:
        import rerun  # noqa: F401
        return summarize(str(rrd))
    except ImportError:
        done = subprocess.run(["uv", "run", "--script", __file__, "--summarize", str(rrd)], capture_output=True, text=True, timeout=600)
        if done.returncode:
            raise AssertionError(f"read-back failed:\n{done.stderr}")
        return json.loads(done.stdout)


def instant_ns(text: str) -> int:
    """An ISO date cell as integer nanoseconds since the epoch, UTC (a naive one is read as UTC)."""
    when = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    when = when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)
    delta = when - dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


def oracle(case_dir: pathlib.Path) -> dict:
    """{entity path: (timeline, kind, t list, value list)} for every timeseries card, straight from the case's JSON.

    The timeline is the clock's time column ("t"), a duration in seconds, when the card's x is seconds; it is "date", a
    timestamp in nanoseconds, when x is ISO dates (docs/RERUN.md, What is in the file)."""
    base = loads((case_dir / "views.base").read_text(encoding="utf-8"))
    clock_time = (base.get("clock") or {}).get("time") or "t"
    datasets = {name: (e if isinstance(e, str) else e["data"]) for name, e in base["datasets"].items()}
    default = next(name for name, file in datasets.items() if file == base["data"])
    expected = {}
    for view in base["views"]:
        if view.get("type") != "timeseries":
            continue
        spec = view["timeseries"]
        if view.get("filters") not in FILTERS:
            raise AssertionError(f"the oracle does not know the filter {view.get('filters')!r}: add it to FILTERS")
        rows = json.loads((case_dir / datasets[view.get("from") or default]).read_text(encoding="utf-8"))["rows"]
        rows = [r for r in rows if FILTERS[view.get("filters")](r)]
        on_dates = all(isinstance(r[spec["x"]], str) for r in rows)
        if not on_dates and spec["x"] != clock_time:
            raise AssertionError(f"{view['name']}: x {spec['x']!r} is not the clock's time {clock_time!r}; the oracle knows only those two timelines")
        timeline, kind = ("date", "timestamp") if on_dates else (clock_time, "duration")
        for r in rows:
            value = r[spec["y"]]
            value = value["value"] if isinstance(value, dict) else value
            if value is None:
                continue
            path = f"/timeseries/{slug(view['name'])}/{slug(r[spec['series']])}"
            _, _, ts, vs = expected.setdefault(path, (timeline, kind, [], []))
            ts.append(instant_ns(r[spec["x"]]) if on_dates else r[spec["x"]])
            vs.append(value)
    return expected


def mismatches(summary: dict, expected: dict) -> list[str]:
    """What the read-back gets wrong against the oracle: the entity, its one timeline (name and kind), as many times as
    values as the case has samples, and each (time, value) pair in time order."""
    problems = []
    for path, (timeline, kind, ts, vs) in expected.items():
        got = summary["entities"].get(path)
        if not got:
            problems.append(f"{path}: missing")
            continue
        if got.get("timelines") != [[timeline, kind]]:
            problems.append(f"{path}: on timelines {got.get('timelines')}, the case's x is the {kind} timeline {timeline!r}")
        if not got["rows"] == len(got["t"]) == len(got["scalars"]) == len(vs):
            problems.append(f"{path}: {got['rows']} samples with {len(got['t'])} times and {len(got['scalars'])} values, the case has {len(vs)} samples")
            continue
        # Rerun keeps durations as integer nanoseconds and may truncate 7.93 s to 7.929999999 s: 1 µs is far finer
        # than any sample period, and far coarser than that rounding; a timestamp is integer nanoseconds both sides
        tolerance = 1e-6 if kind == "duration" else 0
        want = sorted(zip(ts, vs, strict=True), key=lambda pair: pair[0])
        for i, ((want_t, want_v), (got_t, got_v)) in enumerate(zip(want, zip(got["t"], got["scalars"], strict=True), strict=True)):
            if got_v != want_v:
                problems.append(f"{path}: sample {i} is {got_v}, the case has {want_v}")
                break
            if abs(got_t - want_t) > tolerance:
                problems.append(f"{path}: sample {i} is at {got_t}, the case has it at {want_t}")
                break
    return problems


@unittest.skipIf(can_run(), can_run() or "")
class RerunExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="rerun-export-"))
        cls.rrd = cls.tmp / "dashboard-cards.rrd"
        cls.stdout = export(CASE / "views.base", cls.rrd)
        cls.summary = read_back(cls.rrd)
        cls.expected = oracle(CASE)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_one_recording_with_its_blueprint(self):
        self.assertEqual(self.summary["recordings"], ["data-ui-dashboard-cards"])
        self.assertEqual(self.summary["blueprints"], ["data-ui-dashboard-cards"])
        base = loads((CASE / "views.base").read_text(encoding="utf-8"))
        views = {v["name"]: v for v in base["views"]}
        kinds = [views[p["view"]]["type"] for p in base["layout"]["panels"] if p.get("view")]
        # one Rerun view per time series / 3D card, one per clip (a compare card shows two), and the notes
        want = sum(1 for k in kinds if k in ("timeseries", "trajectory", "scene3d", "video")) + 2 * kinds.count("video-compare") + 1
        self.assertEqual(len(self.summary["blueprint_views"]), want, self.summary["blueprint_views"])

    def test_every_series_round_trips(self):
        self.assertGreaterEqual(len(self.expected), 7)
        self.assertEqual(mismatches(self.summary, self.expected), [])

    def test_videos_have_a_frame_reference_per_frame(self):
        media = json.loads((CASE / "media.json").read_text(encoding="utf-8"))["rows"]
        for situation in ("tuned", "factory"):
            row = next(r for r in media if r["situation"] == situation)
            entity = self.summary["entities"].get(f"/video/{situation}")
            self.assertIsNotNone(entity, situation)
            self.assertIn("AssetVideo:blob", self.summary["static"][f"/video/{situation}"])
            # frames = duration x fps, the media row's own numbers
            self.assertEqual(entity["rows"], round(row["duration"] * row["fps"]))
            self.assertAlmostEqual(entity["t"][0], row["t0"])

    def test_paths_markers_and_notes(self):
        tool = json.loads((CASE / "tool.json").read_text(encoding="utf-8"))["rows"]
        for situation in ("target", "factory", "tuned"):
            n = sum(1 for r in tool if r["situation"] == situation)
            self.assertEqual(self.summary["entities"][f"/world/tool-path-3d/{situation}/marker"]["rows"], n)
            self.assertEqual(self.summary["entities"][f"/world/tool-path-3d/{situation}/skeleton"]["rows"], n)
            self.assertIn("LineStrips3D:strips", self.summary["static"][f"/world/tool-path-3d/{situation}/path"])
        self.assertIn("TextDocument:text", self.summary["static"]["/notes"])

    def test_a_changed_sample_fails_the_round_trip(self):
        mutant = self.tmp / "mutant"
        shutil.copytree(CASE, mutant / "dashboard-cards", ignore=shutil.ignore_patterns("rerun"))
        samples_path = mutant / "dashboard-cards" / "samples.json"
        doc = json.loads(samples_path.read_text(encoding="utf-8"))
        row = next(r for r in doc["rows"] if r["joint"] == "elbow_joint" and r["situation"] == "tuned" and r["t"] > 1)
        row["q_deg"] += 0.001
        samples_path.write_text(json.dumps(doc), encoding="utf-8")
        rrd = mutant / "mutant.rrd"
        export(mutant / "dashboard-cards" / "views.base", rrd)
        problems = mismatches(read_back(rrd), self.expected)
        # WHY every series that draws the row, not exactly one: the catalog draws the elbow's step response twice (the
        # simple card and the interactive one), so one changed sample is rightly caught in both; nothing else may move
        drawn_by = sorted(p.split(":")[0] for p in problems)
        self.assertEqual(drawn_by, ["/timeseries/step-response-interactive/tuned", "/timeseries/step-response/tuned"], problems)
        self.assertTrue(all("65.241" in p or str(round(row["q_deg"], 3)) in p for p in problems), problems)

    # ---- the oracle itself, mutation-tested: each wrong read-back below must be named by mismatches()
    def mutated(self, path: str, change) -> list[str]:
        """mismatches() on a copy of the read-back whose entity `path` was changed by change(entity)."""
        copy = json.loads(json.dumps(self.summary))
        change(copy["entities"][path])
        return mismatches(copy, self.expected)

    def paths(self) -> tuple[str, str]:
        """(a series on the clock's t, a series on dates), both from the oracle."""
        on_t = "/timeseries/step-response/tuned"
        on_date = next(p for p in self.expected if p.startswith("/timeseries/kpi-history/"))
        return on_t, on_date

    def assert_caught(self, path: str, change, why: str):
        problems = self.mutated(path, change)
        self.assertTrue(any(p.startswith(path + ":") and why in p for p in problems), f"{why!r} not caught for {path}: {problems}")

    def test_the_oracle_catches_empty_timestamps(self):
        for path in self.paths():
            self.assert_caught(path, lambda e: e["t"].clear(), "times")

    def test_the_oracle_catches_a_renamed_timeline(self):
        on_t, on_date = self.paths()
        self.assert_caught(on_t, lambda e: e.update(timelines=[["time", "duration"]]), "timeline")
        self.assert_caught(on_date, lambda e: e.update(timelines=[["day", "timestamp"]]), "timeline")
        # the right name with the wrong kind is wrong too
        self.assert_caught(on_t, lambda e: e.update(timelines=[["t", "timestamp"]]), "timeline")

    def test_the_oracle_catches_a_dropped_sample(self):
        def drop(e):
            del e["t"][5], e["scalars"][5]
            e["rows"] -= 1
        for path in self.paths():
            self.assert_caught(path, drop, "samples")

    def test_the_oracle_catches_a_shifted_or_swapped_timestamp(self):
        on_t, on_date = self.paths()
        def shift(by):
            return lambda e: e["t"].__setitem__(5, e["t"][5] + by)
        self.assert_caught(on_t, shift(0.001), "is at")
        self.assert_caught(on_date, shift(1_000_000_000), "is at")
        # two samples trading times: every time and every value still present, the pairs wrong
        i = next(i for i in range(len(self.summary["entities"][on_t]["t"]) - 1) if self.summary["entities"][on_t]["scalars"][i] != self.summary["entities"][on_t]["scalars"][i + 1])
        self.assert_caught(on_t, lambda e: e["t"].__setitem__(slice(i, i + 2), e["t"][i:i + 2][::-1]), "is at")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--summarize"]:
        print(json.dumps(summarize(sys.argv[2])))
    else:
        unittest.main()
