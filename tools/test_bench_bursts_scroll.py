"""Judge round 2, finding 4, scroll: a scroll run lasts 2 s, ten 200 ms pressure windows, so judging it whole drops
the whole run whenever any of them was busy (on the shared box, every run: 5 of 5 in the first live check). Its
frames are its samples: frame k ends at the run's start plus the first k intervals, and each frame is judged by the
window over it; scroll_frame_ms is the p95 of the clean frames."""

import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSIGNED = list(range(4, 12))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


try:
    import playwright.sync_api  # noqa: F401
except ImportError:
    _pw, _api = types.ModuleType("playwright"), types.ModuleType("playwright.sync_api")
    _api.sync_playwright = None
    _pw.sync_api = _api
    sys.modules["playwright"], sys.modules["playwright.sync_api"] = _pw, _api
runner = load("bench_runner_bursts_scroll_test", ROOT / "bench" / "runner.py")


def timeline(seconds=20.0, burst=(10.0, 11.0), period=0.2):
    snaps, busy, total = [], 0.0, 0.0
    for i in range(round(seconds / period) + 1):
        t = round(i * period, 3)
        snaps.append({"t": 100.0 + t, "cpu": {c: (round(busy if c in ASSIGNED else 0), round(total)) for c in range(24)}, "own": 0})
        busy += 100 * period * (1.0 if burst[0] <= t + period / 2 < burst[1] else 0.0)
        total += 100 * period
    return snaps


class ScrollFramesAreJudgedOneByOne(unittest.TestCase):
    def setUp(self):
        # a run from 9.0 s: 60 frames of 16.7 ms (to 10.0 s), 20 of 50 ms inside the burst (to 11.0 s), 60 of 16.7 ms
        frames = [16.7] * 60 + [50.0] * 20 + [16.7] * 60
        scroll = {"frames": frames, "scrolled_px": 9000, "longtask_ms": 0.0, "dom_added": 40, "t0": 109.0, "t1": 109.0 + sum(frames) / 1000}
        t = {"id": "large-table", "target": "large-table@10000", "title": "large", "app": "synthetic", "rows": 10000, "synthetic": True}
        cold = [{"first_useful_paint": 100.0, "chain": {}, "view": "table", "status": "", "t0": 101.0 + i, "t1": 101.4 + i} for i in range(3)]
        cpus = {"assigned": ASSIGNED, "smt_siblings": [], "browser": ["4-11"]}
        self.s = runner.aggregate(t, cold, cold, [], [scroll], [], 50.0, 50.0, 50.0, 0.0, 0.0, 3, cpus=cpus, timeline=timeline())

    def test_only_the_frames_inside_the_burst_are_dropped(self):
        tm = self.s["trust"]["timing"]["scroll"]
        self.assertEqual(tm["n"], 140)
        self.assertGreaterEqual(tm["clean"], 115)
        self.assertLessEqual(tm["clean"], 120)
        self.assertTrue(tm["valid"])

    def test_the_scroll_kpi_is_the_clean_frames(self):
        self.assertEqual(self.s["scroll"]["p95"], 16.7)
        self.assertEqual(self.s["scroll"]["dropped_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
