"""Codex's finding 6 (2026-10-27): a real slowdown must never be classified as noise and disappear from the KPIs.

Application instability (the spread of the app's own samples) is a result, published as measured beside a failing
`stable_samples` gate. Only machine interference, measured independently (the calibration loop, the load on the
assigned CPUs), routes a point away from kpi_series.jsonl, and only a timing: bytes, DOM counts and heap are the same
on a busy machine, so they are never routed away for noise.

Each case goes through the real pipeline: bench/runner.py's aggregate() on synthetic samples (Playwright stubbed, as
`python3 -m unittest` has none), then bench/publish.py's main() into a scratch producer folder.
"""

import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEAD = "robotparts-actuators"
TIMINGS = ("first_paint_ms", "first_paint_warm_ms", "interactive_ms", "blocking_ms", "interaction_ms", "model_ms", "render_ms", "rail_ms")
NOT_TIMINGS = ("load_kb", "heap_mb", "dom_added")
# not a bench timing and not a bench point at all: npm test measures the silhouette ratio (bench/KPIS.md)
CHECKED_NOT_RUN = ("mesh_first_frame_outline_pct",)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_runner():
    try:
        import playwright.sync_api  # noqa: F401  (the bench's own venv has it)
    except ImportError:
        pw, api = types.ModuleType("playwright"), types.ModuleType("playwright.sync_api")
        api.sync_playwright = None
        pw.sync_api = api
        sys.modules["playwright"], sys.modules["playwright.sync_api"] = pw, api
    return load("bench_runner_under_test", ROOT / "bench" / "runner.py")


runner = load_runner()
publish = load("bench_publish_under_test", ROOT / "bench" / "publish.py")


def sample(fup, kb=150.0, heap=12.0):
    """One load as bench/runner.py's load_once() returns it, every time scaled from its first useful paint."""
    return {"fcp": fup * 0.8, "lcp": fup, "first_render": fup * 0.9, "first_useful_paint": fup, "tti": fup * 1.2, "tbt": 0.0,
            "model_ms": 5.0, "render_ms": 10.0, "rail_ms": 3.0, "heap_mb": heap, "bytes_transfer": kb * 3 * 1024,
            "bytes_raw": kb * 3 * 1024, "bytes_gzip": kb * 1024, "mark_data": fup * 0.5, "mark_start": fup * 0.6,
            "dom_nodes": 9000, "longtask_ms": 0.0, "chain": {"core_js_end": 10.0}, "view": "table", "status": "1,149 rows",
            "errors": [], "health": {"ok": True, "why": []}, "files": []}


def scenario(cold_fup, calib=(50.0, 50.0), best=50.0, load=(0.0, 0.0)):
    """The headline scenario as the runner records it: aggregate() then the health verdict main() adds."""
    t = {"id": HEAD, "target": HEAD, "title": "actuators", "app": "robotparts", "rows": 1149, "synthetic": False}
    cold = [sample(v) for v in cold_fup]
    warm = [sample(v / 2) for v in cold_fup]
    inter = [{"kind": "sort", "ms": 40.0 + i, "model_ms": 5.0, "render_ms": 10.0, "rail_ms": 2.0, "dom_added": 300,
              "longtask_ms": 0.0, "how": "header click", "run": 0} for i in range(4)]
    s = runner.aggregate(t, cold, warm, inter, [], [], calib[0], calib[1], best, load[0], load[1], len(cold))
    s.update(renderer={"kind": "none", "string": None, "args": [], "webgl": False}, verdict="ok", failed_because=[])
    return s


def publish_run(scenarios, *extra):
    """Publish one results file into a scratch producer folder: (kpi_series lines, kpi_diagnostics lines)."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        res = {"schema": "data-ui-bench/1", "started": "2026-10-27T10:00:00+00:00", "finished": "2026-10-27T10:05:00+00:00",
               "label": "", "code": {"sha": "abc12345", "dirty": False, "branch": "main"}, "runs": 5,
               "host": {"hostname": "test-host"}, "scenarios": scenarios, "verdict": "ok"}
        (d / "results.json").write_text(json.dumps(res))
        out = d / "producer"
        with mock.patch.object(sys, "argv", ["publish.py", str(d / "results.json"), "--to", str(out), *extra]), \
                contextlib.redirect_stdout(io.StringIO()):
            publish.main()
        read = lambda f: [json.loads(x) for x in (out / f).read_text().splitlines()] if (out / f).exists() else []
        return read("kpi_series.jsonl"), read("kpi_diagnostics.jsonl")


def whole(points, kpi):
    """The whole-bench point of a KPI or gate (no slice), or None."""
    return next((p for p in points if p["kpi"] == kpi and not p.get("slice")), None)


def sliced(points, kpi, scenario_id=HEAD):
    return next((p for p in points if p["kpi"] == kpi and p.get("slice") == {"scenario": scenario_id, "rows": 1149}
                 or p["kpi"] == kpi and p.get("slice") == {"scenario": scenario_id}), None)


class UnstableAppOnAQuietMachine(unittest.TestCase):
    """The repro: quiet calibration, zero load, cold first paints of 100, 100, 100, 100 and 1,000 ms."""

    def setUp(self):
        self.series, self.diag = publish_run([scenario([100, 100, 100, 100, 1000])])

    def test_the_slow_p95_is_published_to_the_series(self):
        p = whole(self.series, "first_paint_ms")
        self.assertIsNotNone(p, "the headline first paint must be in kpi_series.jsonl, not routed away as noise")
        self.assertEqual(p["value"], 1000)
        self.assertEqual(p["status"], "measured")
        self.assertEqual(p["labels"]["trust"], "quiet")
        self.assertEqual([x for x in self.diag if x["kpi"] == "first_paint_ms"], [])

    def test_a_failing_stability_result_is_published_beside_it(self):
        g = whole(self.series, "stable_samples")
        self.assertIsNotNone(g, "a stable_samples gate evaluation must be published")
        self.assertIs(g["pass"], False)
        per = sliced(self.series, "stable_samples")
        self.assertIsNotNone(per)
        self.assertIs(per["pass"], False)
        self.assertGreater(per["value"], 0.5)

    def test_the_timing_points_say_the_samples_were_unstable(self):
        self.assertEqual(whole(self.series, "first_paint_ms")["labels"].get("stability"), "unstable")


class StableAppOnAQuietMachine(unittest.TestCase):
    def test_the_gate_passes(self):
        series, diag = publish_run([scenario([100, 102, 98, 101, 99])])
        self.assertIs(whole(series, "stable_samples")["pass"], True)
        self.assertIs(sliced(series, "stable_samples")["pass"], True)
        self.assertEqual(whole(series, "first_paint_ms")["value"], 102)
        self.assertEqual(diag, [])


class SlowCalibration(unittest.TestCase):
    """Machine interference (calibration 2x this host's best): timings go aside, bytes, nodes and heap stay."""

    def setUp(self):
        self.series, self.diag = publish_run([scenario([100] * 5, calib=(100.0, 100.0), best=50.0)])

    def test_timings_are_routed_to_diagnostics(self):
        for kpi in TIMINGS:
            self.assertIsNone(whole(self.series, kpi), f"{kpi} on a noisy machine must not be a KPI point")
            self.assertIsNotNone(whole(self.diag, kpi), f"{kpi} must be kept in kpi_diagnostics.jsonl")

    def test_bytes_dom_counts_and_heap_stay_in_the_series(self):
        expect = {"load_kb": 150.0, "heap_mb": 12.0, "dom_added": 300}
        for kpi in NOT_TIMINGS:
            p = whole(self.series, kpi)
            self.assertIsNotNone(p, f"{kpi} is not sensitive to CPU contention: it must stay in kpi_series.jsonl")
            self.assertEqual(p["value"], expect[kpi])
            self.assertEqual(p["labels"]["trust"], "quiet", f"{kpi}: a busy machine does not change it, so it draws filled")
            self.assertEqual(p["labels"]["machine"], "noisy")
            self.assertIsNone(whole(self.diag, kpi))

    def test_the_gates_stay_in_the_series(self):
        self.assertIsNotNone(whole(self.series, "no_page_errors"))
        self.assertIsNotNone(whole(self.series, "stable_samples"))

    def test_include_noisy_still_publishes_every_point(self):
        series, diag = publish_run([scenario([100] * 5, calib=(100.0, 100.0), best=50.0)], "--include-noisy")
        self.assertEqual(whole(series, "first_paint_ms")["labels"]["trust"], "noisy")
        self.assertEqual(diag, [])


class UnstableSamplesOnANoisyMachine(unittest.TestCase):
    def test_stability_is_pending_not_failed(self):
        # WHY pending: on a loaded machine the spread may be the machine's, so it is no result about the app
        series, diag = publish_run([scenario([100, 100, 100, 100, 1000], calib=(100.0, 100.0), best=50.0)])
        g = whole(series, "stable_samples")
        self.assertIsNotNone(g)
        self.assertIsNone(g["pass"])
        self.assertIn("noisy", sliced(series, "stable_samples")["labels"]["why"])
        self.assertIsNotNone(whole(diag, "first_paint_ms"))


class ResultsFromBeforeTheSplit(unittest.TestCase):
    """A results file the old runner wrote: trust.verdict 'noisy' only because of the cold first-paint spread."""

    def test_it_is_reclassified_from_what_it_recorded(self):
        s = scenario([100, 100, 100, 100, 1000])
        s.pop("stability", None)
        s["trust"] = {"verdict": "noisy", "why": ["cold first-paint spread cv 1.437"], "calibration_ms": [50.0, 50.0],
                      "best_calibration_ms": 50.0, "loadavg": [0.0, 0.0], "cpus": 24, "pinned_cpus": 8}
        series, diag = publish_run([s])
        self.assertEqual(whole(series, "first_paint_ms")["value"], 1000)
        self.assertIs(whole(series, "stable_samples")["pass"], False)
        self.assertEqual([x for x in diag if x["kpi"] == "first_paint_ms"], [])


class MoveNoisyIsPerMetric(unittest.TestCase):
    def test_only_timings_are_moved(self):
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d)
            pts = [{"schema": "vt-kpi-point/1", "kpi": k, "t": "2026-10-27T00:00:00+00:00", "value": v, "labels": {"trust": "noisy"}}
                   for k, v in (("first_paint_ms", 2847), ("load_kb", 149.0), ("heap_mb", 12.0), ("dom_added", 300))]
            (out / "kpi_series.jsonl").write_text("".join(json.dumps(p) + "\n" for p in pts))
            with contextlib.redirect_stdout(io.StringIO()):
                publish.move_noisy(out)
            kept = [json.loads(x)["kpi"] for x in (out / "kpi_series.jsonl").read_text().splitlines()]
            aside = [json.loads(x)["kpi"] for x in (out / "kpi_diagnostics.jsonl").read_text().splitlines()]
            self.assertEqual(kept, ["load_kb", "heap_mb", "dom_added"])
            self.assertEqual(aside, ["first_paint_ms"])


class Catalog(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / "bench" / "kpi_catalog.json").read_text())

    def test_every_kpi_says_whether_a_busy_cpu_moves_it(self):
        for k in self.catalog["kpis"]:
            self.assertIsInstance(k.get("cpu_sensitive"), bool, k["id"])
            self.assertEqual(k["cpu_sensitive"], k["id"] not in NOT_TIMINGS + CHECKED_NOT_RUN, k["id"])

    def test_the_stable_samples_gate_is_declared(self):
        g = next((g for g in self.catalog["gates"] if g["id"] == "stable_samples"), None)
        self.assertIsNotNone(g)
        self.assertEqual(g["bound"], {"op": "<=", "value": 0.5})
        self.assertNotIn(g["applies_to"], {k["id"] for k in self.catalog["kpis"]}, "a cv bound must not draw on a ms chart")


if __name__ == "__main__":
    unittest.main()
