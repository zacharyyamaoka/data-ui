"""Judge round 2, finding 4 (2026-10-27): a brief burst of interference must not hide in a scenario-long average.

One second of full foreign saturation in a 20 s scenario averages to 5 %, so the whole-scenario "during" window read
quiet while the burst could own a paint or interaction p95. The fix: a sampler reads /proc/stat (and the bench's own
process tree) every 200 ms through the scenario, and each measured sample (a cold load, a warm load, an interaction,
a scroll) is judged by the windows that overlap its own time. Samples that overlapped interference are dropped from
the timing KPIs; a timing set with too few clean samples left is suppressed (and timing_valid fails). Interference
seen only before or after the samples no longer condemns them.

Pure functions on synthetic /proc timelines (bench/trust.py), then runner.aggregate() and publish.main().
"""

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEAD = "robotparts-actuators"
ASSIGNED = list(range(4, 12))
SIBLINGS = list(range(16, 24))
PERIOD = 0.2


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
    return load("bench_runner_bursts_test", ROOT / "bench" / "runner.py")


trust = load("bench_trust_bursts_test", ROOT / "bench" / "trust.py")
runner = load_runner()
publish = load("bench_publish_bursts_test", ROOT / "bench" / "publish.py")


def timeline(seconds=20.0, bursts=(), cpus=ASSIGNED, own=0.0, base=0.0, hz=100):
    """Snapshots every PERIOD s from t=0: each CPU busy `base` of the time, the CPUs in `cpus` fully busy inside any
    (start, end) of `bursts`; the bench's own tree busy for `own` CPUs throughout (and that much more busy time on the
    assigned CPUs, spread evenly, since the bench runs there)."""
    snaps, busy, total, mine = [], {c: 0.0 for c in range(24)}, {c: 0.0 for c in range(24)}, 0.0
    steps = round(seconds / PERIOD)
    for i in range(steps + 1):
        t = round(i * PERIOD, 3)
        snaps.append({"t": 100.0 + t, "cpu": {c: (round(busy[c]), round(total[c])) for c in range(24)}, "own": round(mine)})
        mid = t + PERIOD / 2
        hot = any(a <= mid < b for a, b in bursts)
        for c in range(24):
            share = 1.0 if hot and c in cpus else base
            if c in ASSIGNED:
                share = min(1.0, share + own / len(ASSIGNED))
            busy[c] += hz * PERIOD * share
            total[c] += hz * PERIOD
        mine += hz * PERIOD * own
    return snaps


def intervals(n, length, start=0.0):
    return [(100.0 + start + i * length, 100.0 + start + (i + 1) * length) for i in range(n)]


class TheAverageHidesABurst(unittest.TestCase):
    def test_one_second_in_twenty_averages_to_five_percent(self):
        tl = timeline(bursts=[(10.0, 11.0)])
        w = trust.pressure(tl[0], tl[-1], ASSIGNED, SIBLINGS)
        self.assertAlmostEqual(w["foreign_share"], 0.05, places=2)
        self.assertEqual(trust.machine(50.0, 50.0, 50.0, {"during": w})["verdict"], "quiet", "the blind spot this finding is about")


class JudgeEachSampleByItsOwnWindows(unittest.TestCase):
    def test_the_samples_that_overlap_the_burst_are_flagged(self):
        got = trust.judge_intervals(timeline(bursts=[(10.0, 11.0)]), intervals(40, 0.5), ASSIGNED, SIBLINGS)
        flagged = [i for i, j in enumerate(got) if not j["clean"]]
        self.assertEqual(flagged, [20, 21], "the two half-second samples inside 10-11 s, and only they")
        self.assertEqual(got[20]["foreign_share"], 1.0)
        self.assertIn("assigned", got[20]["why"])
        self.assertTrue(all(j["clean"] for k, j in enumerate(got) if k not in (20, 21)))

    def test_a_quiet_timeline_flags_nothing(self):
        got = trust.judge_intervals(timeline(base=0.1), intervals(40, 0.5), ASSIGNED, SIBLINGS)
        self.assertTrue(all(j["clean"] for j in got))
        self.assertLess(max(j["foreign_share"] for j in got), 0.15)

    def test_the_benchs_own_work_is_not_interference(self):
        got = trust.judge_intervals(timeline(own=2.0), intervals(40, 0.5), ASSIGNED, SIBLINGS)
        self.assertTrue(all(j["clean"] for j in got), max(j["foreign_share"] for j in got))

    def test_a_burst_on_the_smt_siblings_is_flagged(self):
        got = trust.judge_intervals(timeline(bursts=[(4.0, 5.0)], cpus=SIBLINGS), intervals(40, 0.5), ASSIGNED, SIBLINGS)
        self.assertEqual([i for i, j in enumerate(got) if not j["clean"]], [8, 9])
        self.assertIn("sibling", got[8]["why"])

    def test_a_short_interaction_inside_one_window(self):
        tl = timeline(bursts=[(10.0, 10.2)])
        hit, miss = trust.judge_intervals(tl, [(110.05, 110.09), (110.25, 110.29)], ASSIGNED, SIBLINGS)
        self.assertFalse(hit["clean"])
        self.assertTrue(miss["clean"])

    def test_a_sample_no_window_covers_is_not_vouched_for(self):
        (j,) = trust.judge_intervals(timeline(seconds=2.0), [(150.0, 150.5)], ASSIGNED, SIBLINGS)
        self.assertFalse(j["clean"])
        self.assertEqual(j["windows"], 0)


class EnoughCleanSamples(unittest.TestCase):
    def test_at_least_half_and_at_least_two(self):
        cases = {(7, 7): True, (4, 7): True, (3, 7): False, (2, 3): True, (1, 3): False, (2, 2): True, (1, 2): False, (1, 1): True, (0, 1): False}
        for (clean, n), want in cases.items():
            self.assertIs(trust.enough(clean, n), want, (clean, n))


def sample(fup, t0, t1, kb=150.0):
    return {"fcp": fup * 0.8, "lcp": fup, "first_render": fup * 0.9, "first_useful_paint": fup, "tti": fup * 1.2, "tbt": 0.0,
            "model_ms": 5.0, "render_ms": 10.0, "rail_ms": 3.0, "heap_mb": 12.0, "bytes_transfer": kb * 3 * 1024,
            "bytes_raw": kb * 3 * 1024, "bytes_gzip": kb * 1024, "mark_data": fup * 0.5, "mark_start": fup * 0.6,
            "dom_nodes": 9000, "longtask_ms": 0.0, "chain": {"core_js_end": 10.0}, "view": "table", "status": "1,149 rows",
            "errors": [], "health": {"ok": True, "why": []}, "files": [], "t0": t0, "t1": t1}


def scenario(cold_fup, tl, cold_at=None, inter_at=None, calib=(50.0, 50.0), pressure=None):
    """The headline scenario, each sample at its own time (seconds from the timeline's start)."""
    t = {"id": HEAD, "target": HEAD, "title": "actuators", "app": "robotparts", "rows": 1149, "synthetic": False}
    cold_at = cold_at or [(1.0 + 3 * i, 1.5 + 3 * i) for i in range(len(cold_fup))]
    cold = [sample(v, 100.0 + a, 100.0 + b) for v, (a, b) in zip(cold_fup, cold_at)]
    warm = [sample(v / 2, 100.0 + a + 0.6, 100.0 + b + 0.6) for v, (a, b) in zip(cold_fup, cold_at)]
    inter_at = inter_at or [(1.9 + 3 * i, 1.95 + 3 * i) for i in range(len(cold_fup))]
    inter = [{"kind": "sort", "ms": 40.0, "model_ms": 5.0, "render_ms": 10.0, "rail_ms": 2.0, "dom_added": 300, "longtask_ms": 0.0,
              "how": "header click", "run": i, "t0": 100.0 + a, "t1": 100.0 + b} for i, (a, b) in enumerate(inter_at)]
    cpus = {"assigned": ASSIGNED, "smt_siblings": SIBLINGS, "browser": ["4-11"]}
    s = runner.aggregate(t, cold, warm, inter, [], [], calib[0], calib[1], 50.0, 0.0, 0.0, len(cold),
                         pressure=pressure, cpus=cpus, timeline=tl)
    s.update(renderer={"kind": "none", "string": None, "args": [], "webgl": False}, verdict="ok", failed_because=[])
    return s


def publish_run(scenarios):
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        res = {"schema": "data-ui-bench/1", "started": "2026-10-27T10:00:00+00:00", "finished": "2026-10-27T10:05:00+00:00",
               "label": "", "code": {"sha": "abc12345", "dirty": False, "branch": "main"}, "runs": 5,
               "host": {"hostname": "test-host"}, "scenarios": scenarios, "verdict": "ok"}
        (d / "results.json").write_text(json.dumps(res))
        out = d / "producer"
        with mock.patch.object(sys, "argv", ["publish.py", str(d / "results.json"), "--to", str(out)]), contextlib.redirect_stdout(io.StringIO()):
            publish.main()
        read = lambda f: [json.loads(x) for x in (out / f).read_text().splitlines()] if (out / f).exists() else []
        return read("kpi_series.jsonl"), read("kpi_diagnostics.jsonl")


def whole(points, kpi):
    return next((p for p in points if p["kpi"] == kpi and not p.get("slice")), None)


def per_scenario(points, kpi):
    return next((p for p in points if p["kpi"] == kpi and p.get("slice") == {"scenario": HEAD}), None)


class TheRunnerDropsTheSamplesTheBurstTouched(unittest.TestCase):
    def setUp(self):
        # five cold loads at 1, 4, 7, 10 and 13 s; the one at 10 s runs inside the burst and is slow because of it
        self.s = scenario([100, 100, 100, 900, 100], timeline(bursts=[(10.0, 11.0)]))

    def test_the_overlapping_load_is_flagged_and_left_out(self):
        cold = self.s["samples"]["cold"]
        self.assertEqual([x["clean"] for x in cold], [True, True, True, False, True])
        self.assertEqual(cold[3]["pressure"]["foreign_share"], 1.0)
        self.assertEqual(self.s["load"]["cold"]["first_useful_paint"]["p95"], 100)
        self.assertEqual({k: self.s["trust"]["timing"]["cold"][k] for k in ("n", "clean", "valid")}, {"n": 5, "clean": 4, "valid": True})

    def test_bytes_still_count_every_load(self):
        self.assertEqual(self.s["load"]["cold"]["bytes_gzip"]["n"], 5)

    def test_the_timeline_is_recorded(self):
        tl = self.s["trust"]["timeline"]
        self.assertEqual(len(tl), 100)
        self.assertEqual(len(tl[0]), 4)
        self.assertEqual(max(w[2] for w in tl), 1.0)

    def test_it_publishes_the_clean_p95_and_says_one_was_dropped(self):
        series, diag = publish_run([self.s])
        self.assertEqual(whole(series, "first_paint_ms")["value"], 100)
        g = per_scenario(series, "timing_valid")
        self.assertIs(g["pass"], True)
        self.assertIn("cold 1 of 5", g["labels"]["dropped"])
        self.assertEqual([p for p in diag if p["kpi"] == "first_paint_ms"], [])


class InterferenceOnlyAfterTheSamples(unittest.TestCase):
    def test_it_no_longer_condemns_them(self):
        # the judge's finding-3 repro at its root: five genuine 1,000 ms paints, clean windows, a saturated after-window
        busy = trust.pressure(*timeline(seconds=1.0, bursts=[(0.0, 1.0)])[::5], ASSIGNED, SIBLINGS)
        s = scenario([1000] * 5, timeline(), pressure={"before": None, "during": None, "after": busy})
        self.assertEqual(s["trust"]["verdict"], "quiet", s["trust"]["why"])
        series, _ = publish_run([s])
        self.assertEqual(whole(series, "first_paint_ms")["value"], 1000)
        self.assertIs(whole(series, "timing_valid")["pass"], True)


class OneSetSuppressedTheOthersNot(unittest.TestCase):
    def setUp(self):
        # the interactions all fall inside a long burst (12-14.5 s); the cold loads, at 1-13.5 s, mostly do not
        inter_at = [(12.0 + 0.5 * i, 12.05 + 0.5 * i) for i in range(5)]
        self.s = scenario([100] * 5, timeline(bursts=[(12.0, 14.5)]), inter_at=inter_at)
        self.series, self.diag = publish_run([self.s])

    def test_the_interactions_are_suppressed(self):
        self.assertFalse(self.s["trust"]["timing"]["interactions"]["valid"])
        self.assertTrue(self.s["trust"]["timing"]["cold"]["valid"])
        self.assertIsNone(whole(self.series, "interaction_ms"))
        self.assertIsNotNone(whole(self.diag, "interaction_ms"))

    def test_the_paints_are_published(self):
        self.assertEqual(whole(self.series, "first_paint_ms")["value"], 100)

    def test_timing_valid_fails_and_names_the_interactions(self):
        g = per_scenario(self.series, "timing_valid")
        self.assertIs(g["pass"], False)
        self.assertIn("interactions", g["labels"]["why"])
        self.assertNotIn("cold", g["labels"]["suppressed"])


class TooFewCleanColdLoads(unittest.TestCase):
    def test_the_paints_are_suppressed_and_stability_pending(self):
        s = scenario([100] * 5, timeline(bursts=[(0.0, 9.0)]))
        self.assertFalse(s["trust"]["timing"]["cold"]["valid"])
        self.assertEqual(s["stability"]["verdict"], "pending")
        series, diag = publish_run([s])
        self.assertIsNone(whole(series, "first_paint_ms"))
        self.assertIsNone(per_scenario(series, "stable_samples")["pass"])
        self.assertIs(whole(series, "timing_valid")["pass"], False)


class CalibrationStillJudgesTheWholeScenario(unittest.TestCase):
    def test_a_slow_calibration_suppresses_every_set(self):
        s = scenario([100] * 5, timeline(), calib=(100.0, 100.0))
        self.assertTrue(all(not v["valid"] for v in s["trust"]["timing"].values()))


@unittest.skipUnless(os.path.exists("/proc/stat") and hasattr(os, "sched_getaffinity"), "Linux /proc only")
class TheSamplerOnThisMachine(unittest.TestCase):
    def test_it_records_time_aligned_snapshots_and_the_own_tree(self):
        cpus = sorted(os.sched_getaffinity(0))
        sampler = trust.Sampler(cpus, [], period=0.05)
        sampler.start()
        end = time.monotonic() + 0.4
        x = 0
        while time.monotonic() < end:
            x += 1
        snaps = sampler.stop()
        self.assertGreaterEqual(len(snaps), 4)
        self.assertEqual([s["t"] for s in snaps], sorted(s["t"] for s in snaps))
        self.assertTrue(set(cpus) <= set(snaps[0]["cpu"]))
        self.assertGreater(snaps[-1]["own"], snaps[0]["own"], "the busy loop above is the bench's own work")
        self.assertFalse(sampler.alive())


class Consistency(unittest.TestCase):
    def test_every_cpu_sensitive_kpi_has_a_timing_set(self):
        catalog = json.loads((ROOT / "bench" / "kpi_catalog.json").read_text())
        self.assertEqual({k["id"] for k in catalog["kpis"] if k["cpu_sensitive"]}, set(trust.TIMING_SETS))


if __name__ == "__main__":
    unittest.main()
