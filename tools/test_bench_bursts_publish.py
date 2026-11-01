"""Judge round 2, finding 4, the publisher's half: bench/publish.py computes the interaction KPIs from the samples
itself, so an interaction the runner judged unclean (it overlapped a burst on the assigned CPUs) must be left out of
interaction_ms, model_ms, render_ms and rail_ms (whole bench and per kind), while dom_added still counts every one."""

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
runner = load("bench_runner_bursts_publish_test", ROOT / "bench" / "runner.py")
publish = load("bench_publish_bursts_publish_test", ROOT / "bench" / "publish.py")


def timeline(seconds=20.0, burst=(10.0, 11.0), period=0.2):
    snaps, busy, total = [], 0.0, 0.0
    for i in range(round(seconds / period) + 1):
        t = round(i * period, 3)
        snaps.append({"t": 100.0 + t, "cpu": {c: (round(busy if c in ASSIGNED else 0), round(total)) for c in range(24)}, "own": 0})
        hot = burst[0] <= t + period / 2 < burst[1]
        busy += 100 * period * (1.0 if hot else 0.0)
        total += 100 * period
    return snaps


def sample(fup, t0):
    return {"first_useful_paint": fup, "tti": fup, "tbt": 0.0, "fcp": fup, "heap_mb": 12.0, "bytes_gzip": 150 * 1024, "chain": {},
            "view": "table", "status": "", "errors": [], "files": [], "t0": t0, "t1": t0 + 0.5}


class UncleanInteractionsAreLeftOut(unittest.TestCase):
    def setUp(self):
        t = {"id": HEAD, "target": HEAD, "title": "actuators", "app": "robotparts", "rows": 1149, "synthetic": False}
        cold = [sample(100, 100.0 + 3 * i) for i in range(5)]
        warm = [sample(50, 100.6 + 3 * i) for i in range(5)]
        # five sorts at 2, 5, 8, 10.5 and 14 s: the one at 10.5 s overlaps the burst and is slow because of it
        at = [2.0, 5.0, 8.0, 10.5, 14.0]
        inter = [{"kind": "sort", "ms": 900.0 if a == 10.5 else 40.0, "model_ms": 300.0 if a == 10.5 else 5.0, "render_ms": 400.0 if a == 10.5 else 10.0,
                  "rail_ms": 200.0 if a == 10.5 else 2.0, "dom_added": 300, "longtask_ms": 0.0, "how": "header click", "run": i,
                  "t0": 100.0 + a, "t1": 100.0 + a + 0.05} for i, a in enumerate(at)]
        cpus = {"assigned": ASSIGNED, "smt_siblings": SIBLINGS, "browser": ["4-11"]}
        s = runner.aggregate(t, cold, warm, inter, [], [], 50.0, 50.0, 50.0, 0.0, 0.0, 5, cpus=cpus, timeline=timeline())
        s.update(renderer={"kind": "none", "string": None, "args": [], "webgl": False}, verdict="ok", failed_because=[])
        self.s = s
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            res = {"schema": "data-ui-bench/1", "started": "2026-10-27T10:00:00+00:00", "finished": "2026-10-27T10:05:00+00:00", "label": "",
                   "code": {"sha": "abc12345", "dirty": False, "branch": "main"}, "runs": 5, "host": {"hostname": "test-host"}, "scenarios": [s], "verdict": "ok"}
            (d / "results.json").write_text(json.dumps(res))
            with mock.patch.object(sys, "argv", ["publish.py", str(d / "results.json"), "--to", str(d / "out")]), contextlib.redirect_stdout(io.StringIO()):
                publish.main()
            self.series = [json.loads(x) for x in (d / "out" / "kpi_series.jsonl").read_text().splitlines()]

    def point(self, kpi, slice_=None):
        return next((p for p in self.series if p["kpi"] == kpi and p.get("slice") == slice_), None)

    def test_the_runner_flagged_the_slow_one(self):
        self.assertEqual([x["clean"] for x in self.s["samples"]["interactions"]], [True, True, True, False, True])
        self.assertTrue(self.s["trust"]["timing"]["interactions"]["valid"])

    def test_the_whole_bench_interaction_kpis_leave_it_out(self):
        for kpi, want in (("interaction_ms", 40.0), ("model_ms", 5.0), ("render_ms", 10.0), ("rail_ms", 2.0)):
            p = self.point(kpi)
            self.assertEqual((p["value"], p["n"]), (want, 4), kpi)

    def test_the_per_kind_slices_leave_it_out(self):
        self.assertEqual(self.point("interaction_ms", {"kind": "sort"})["value"], 40.0)
        self.assertEqual(self.point("interaction_ms", {"scenario": HEAD, "kind": "sort"})["value"], 40.0)

    def test_dom_added_counts_every_interaction(self):
        self.assertEqual(self.point("dom_added")["n"], 5)


if __name__ == "__main__":
    unittest.main()
