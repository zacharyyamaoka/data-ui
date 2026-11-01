"""Judge round 2, finding 3 (2026-10-27): a timing regression must never vanish while every gate is green.

When bench/publish.py keeps a scenario's timings out of the KPI series (the machine was noisy), the series still has
to say so for the current build: the `timing_valid` gate fails, carrying the code_sha and the reason. Vibe Tracks'
headline skips null points, so without it the previous build's fast number stays the last word unflagged.

And stability under interference is conservative: interference can LOWER a CV (an additive offset raises the mean),
so a low CV on a noisy machine never certifies the app stable; it is pending.

The pipeline is the real one: bench/runner.py's aggregate() (Playwright stubbed), then bench/publish.py's main().
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
ASSIGNED = list(range(4, 12))
SIBLINGS = list(range(16, 24))
SHA = "abc12345"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_runner():
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        pw, api = types.ModuleType("playwright"), types.ModuleType("playwright.sync_api")
        api.sync_playwright = None
        pw.sync_api = api
        sys.modules["playwright"], sys.modules["playwright.sync_api"] = pw, api
    return load("bench_runner_timing_valid_test", ROOT / "bench" / "runner.py")


runner = load_runner()
publish = load("bench_publish_timing_valid_test", ROOT / "bench" / "publish.py")
trust = load("bench_trust_timing_valid_test", ROOT / "bench" / "trust.py")


def window(busy):
    """trust.pressure() over one second in which CPU c was busy for busy[c] of the time."""
    a = {"t": 100.0, "cpu": {c: (5000, 40000) for c in range(24)}, "own": 7000}
    b = {"t": 101.0, "cpu": {c: (5000 + round(100 * busy.get(c, 0.0)), 40100) for c in range(24)}, "own": 7000}
    return trust.pressure(a, b, ASSIGNED, SIBLINGS)


QUIET = window({})
SATURATED = window({c: 1.0 for c in ASSIGNED})


def sample(fup, kb=150.0, heap=12.0):
    return {"fcp": fup * 0.8, "lcp": fup, "first_render": fup * 0.9, "first_useful_paint": fup, "tti": fup * 1.2, "tbt": 0.0,
            "model_ms": 5.0, "render_ms": 10.0, "rail_ms": 3.0, "heap_mb": heap, "bytes_transfer": kb * 3 * 1024,
            "bytes_raw": kb * 3 * 1024, "bytes_gzip": kb * 1024, "mark_data": fup * 0.5, "mark_start": fup * 0.6,
            "dom_nodes": 9000, "longtask_ms": 0.0, "chain": {"core_js_end": 10.0}, "view": "table", "status": "1,149 rows",
            "errors": [], "health": {"ok": True, "why": []}, "files": []}


def scenario(cold_fup, calib=(50.0, 50.0), best=50.0, pressure=None, verdict="ok"):
    t = {"id": HEAD, "target": HEAD, "title": "actuators", "app": "robotparts", "rows": 1149, "synthetic": False}
    cold = [sample(v) for v in cold_fup]
    warm = [sample(v / 2) for v in cold_fup]
    inter = [{"kind": "sort", "ms": 40.0 + i, "model_ms": 5.0, "render_ms": 10.0, "rail_ms": 2.0, "dom_added": 300,
              "longtask_ms": 0.0, "how": "header click", "run": 0} for i in range(4)]
    cpus = {"assigned": ASSIGNED, "smt_siblings": SIBLINGS, "browser": ["4-11"]}
    s = runner.aggregate(t, cold, warm, inter, [], [], calib[0], calib[1], best, 0.0, 0.0, len(cold), pressure=pressure, cpus=cpus)
    s.update(renderer={"kind": "none", "string": None, "args": [], "webgl": False}, verdict=verdict,
             failed_because=["page error: boom"] if verdict == "FAILED" else [])
    return s


def publish_run(scenarios, *extra):
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        res = {"schema": "data-ui-bench/1", "started": "2026-10-27T10:00:00+00:00", "finished": "2026-10-27T10:05:00+00:00",
               "label": "", "code": {"sha": SHA, "dirty": False, "branch": "main"}, "runs": 5,
               "host": {"hostname": "test-host"}, "scenarios": scenarios, "verdict": "ok"}
        (d / "results.json").write_text(json.dumps(res))
        out = d / "producer"
        with mock.patch.object(sys, "argv", ["publish.py", str(d / "results.json"), "--to", str(out), *extra]), \
                contextlib.redirect_stdout(io.StringIO()):
            publish.main()
        read = lambda f: [json.loads(x) for x in (out / f).read_text().splitlines()] if (out / f).exists() else []
        return read("kpi_series.jsonl"), read("kpi_diagnostics.jsonl")


def whole(points, kpi):
    return next((p for p in points if p["kpi"] == kpi and not p.get("slice")), None)


def per_scenario(points, kpi):
    return next((p for p in points if p["kpi"] == kpi and p.get("slice") == {"scenario": HEAD}), None)


class InterferenceOnlyAfterTheMeasurement(unittest.TestCase):
    """The judge's repro: five genuine 1,000 ms paints, quiet calibration, interference seen only after."""

    def setUp(self):
        self.series, self.diag = publish_run([scenario([1000] * 5, pressure={"before": QUIET, "during": QUIET, "after": SATURATED})])

    def test_the_series_says_the_current_builds_timing_is_unresolved(self):
        g = whole(self.series, "timing_valid")
        self.assertIsNotNone(g, "a timing_valid gate evaluation must be in kpi_series.jsonl")
        self.assertIs(g["pass"], False)
        self.assertEqual(g["labels"]["code_sha"], SHA)
        self.assertEqual(g["source"]["code_sha"], SHA)
        self.assertIn(HEAD, g["labels"]["suppressed"])
        per = per_scenario(self.series, "timing_valid")
        self.assertIs(per["pass"], False)
        self.assertIn("after", per["labels"]["why"])

    def test_not_every_gate_is_green_at_this_instant(self):
        gates = [p for p in self.series if "pass" in p]
        self.assertTrue(any(p["pass"] is False for p in gates), [(p["kpi"], p["pass"]) for p in gates])

    def test_the_suppressed_timing_is_kept_in_the_diagnostics(self):
        self.assertEqual(whole(self.diag, "first_paint_ms")["value"], 1000)


class QuietMachine(unittest.TestCase):
    def test_timing_valid_passes(self):
        series, diag = publish_run([scenario([100] * 5, pressure={"before": QUIET, "during": QUIET, "after": QUIET})])
        self.assertIs(whole(series, "timing_valid")["pass"], True)
        self.assertIs(per_scenario(series, "timing_valid")["pass"], True)
        self.assertEqual(whole(series, "first_paint_ms")["value"], 100)
        self.assertEqual(diag, [])


class SlowCalibration(unittest.TestCase):
    def test_timing_valid_fails_and_names_the_calibration(self):
        series, _ = publish_run([scenario([100] * 5, calib=(100.0, 100.0), best=50.0)])
        self.assertIs(whole(series, "timing_valid")["pass"], False)
        self.assertIn("calibration", per_scenario(series, "timing_valid")["labels"]["why"])
        self.assertIsNotNone(whole(series, "load_kb"), "bytes are published whatever the machine")

    def test_include_noisy_publishes_the_timings_and_still_fails_the_gate(self):
        # WHY still failing: the number is in the series, hollow, but it was measured under interference
        series, _ = publish_run([scenario([100] * 5, calib=(100.0, 100.0), best=50.0)], "--include-noisy")
        self.assertEqual(whole(series, "first_paint_ms")["labels"]["trust"], "noisy")
        self.assertIs(whole(series, "timing_valid")["pass"], False)


class FailedScenario(unittest.TestCase):
    def test_timing_validity_is_not_judged(self):
        series, _ = publish_run([scenario([100] * 5, verdict="FAILED")])
        self.assertIsNone(per_scenario(series, "timing_valid")["pass"])
        self.assertIs(whole(series, "no_page_errors")["pass"], False)


class ResultsFromBeforeTheSplit(unittest.TestCase):
    def test_a_legacy_noisy_scenario_fails_timing_valid(self):
        s = scenario([100] * 5)
        s.pop("stability", None)
        s["trust"] = {"verdict": "noisy", "why": ["calibration 120 ms is 1.59x this host's best 75 ms"], "calibration_ms": [120.0, 90.0],
                      "best_calibration_ms": 75.0, "loadavg": [30.0, 30.0], "cpus": 24, "pinned_cpus": 8}
        series, _ = publish_run([s])
        self.assertIs(whole(series, "timing_valid")["pass"], False)


class StabilityUnderInterference(unittest.TestCase):
    """[100, 100, 100, 100, 1000] has a CV of 1.437; add 1,000 ms to each (an additive interference) and it is 0.314."""

    OFFSET = [1100, 1100, 1100, 1100, 2000]

    def test_the_offset_lowers_the_cv_below_the_bound(self):
        self.assertLess(trust.cv(self.OFFSET), trust.UNSTABLE_CV)

    def test_a_low_cv_on_a_noisy_machine_is_pending_never_stable(self):
        st = trust.stability(self.OFFSET, "noisy")
        self.assertEqual(st["verdict"], "pending")
        self.assertIsNone(trust.stability_pass(st))

    def test_the_gate_is_pending_through_the_pipeline(self):
        series, _ = publish_run([scenario(self.OFFSET, calib=(100.0, 100.0), best=50.0)])
        self.assertIsNone(per_scenario(series, "stable_samples")["pass"])
        self.assertIsNone(whole(series, "stable_samples")["pass"])

    def test_a_quiet_machine_still_judges_it(self):
        self.assertEqual(trust.stability(self.OFFSET, "quiet")["verdict"], "stable")


class Catalog(unittest.TestCase):
    def test_the_timing_valid_gate_is_declared(self):
        catalog = json.loads((ROOT / "bench" / "kpi_catalog.json").read_text())
        ids = [g["id"] for g in catalog["gates"]]
        self.assertIn("timing_valid", ids)
        g = catalog["gates"][ids.index("timing_valid")]
        self.assertEqual(g["bound"], {"op": "==", "value": 0})
        self.assertNotIn(g["applies_to"], {k["id"] for k in catalog["kpis"]})
        # WHY after the others: Vibe Tracks' next leg is the first failing gate in catalog order; a page that throws
        # outranks a re-measure
        self.assertLess(ids.index("no_page_errors"), ids.index("timing_valid"))


if __name__ == "__main__":
    unittest.main()
