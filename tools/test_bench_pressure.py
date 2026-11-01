"""Codex's finding 7 (2026-10-27): the quiet-machine check must judge the CPUs the bench is pinned to, not the host.

bench/run.mjs pins the runner (and so its browser) to DATA_UI_BENCH_CPUS, default 4-11, but the check divided the host's
load average by its 24 CPUs, so eight saturated assigned CPUs passed as quiet, and work on other CPUs could count
against a run it never touched. The fix samples /proc/stat per CPU before, during and after each scenario, takes the
bench's own process tree out, and judges the assigned CPUs and their SMT siblings (the same physical cores).

Pure functions on synthetic /proc snapshots (bench/trust.py), then runner.aggregate() with them (Playwright stubbed).
"""

import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSIGNED = list(range(4, 12))
SIBLINGS = list(range(16, 24))
HEAD = "robotparts-actuators"


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
    return load("bench_runner_pressure_test", ROOT / "bench" / "runner.py")


trust = load("bench_trust_under_test", ROOT / "bench" / "trust.py")
runner = load_runner()


def snaps(busy, own=0.0, seconds=1.0, ncpu=24, hz=100):
    """Two snapshots `seconds` apart: CPU c busy for busy[c] of the time (0..1), the bench's own tree for `own` CPUs."""
    ticks = round(hz * seconds)
    a = {"t": 100.0, "cpu": {c: (5000, 40000) for c in range(ncpu)}, "own": 7000}
    b = {"t": 100.0 + seconds, "cpu": {c: (5000 + round(ticks * busy.get(c, 0.0)), 40000 + ticks) for c in range(ncpu)},
         "own": 7000 + round(ticks * own)}
    return a, b


def window(busy, own=0.0):
    a, b = snaps(busy, own)
    return trust.pressure(a, b, ASSIGNED, SIBLINGS)


class ProcParsing(unittest.TestCase):
    def test_per_cpu_busy_and_total_ticks(self):
        text = ("cpu  10 0 10 100 0 0 0 0 0 0\n"
                "cpu0 1 2 3 40 5 6 7 8 0 0\n"
                "cpu1 0 0 0 100 0 0 0 0 0 0\n"
                "intr 1 2 3\n")
        got = trust.parse_cpu_stat(text)
        self.assertEqual(set(got), {0, 1})
        self.assertEqual(got[0], (1 + 2 + 3 + 6 + 7 + 8, 1 + 2 + 3 + 40 + 5 + 6 + 7 + 8))  # busy leaves out idle and iowait
        self.assertEqual(got[1], (0, 100))

    def test_a_process_stat_line_with_spaces_and_parens_in_its_name(self):
        line = "4242 (Web Content (x)) S 4200 4242 4242 0 -1 4194304 1 0 0 0 30 12 5 3 20 0 1 0 1 1 1 1"
        self.assertEqual(trust.parse_pid_stat(line), (4242, 4200, 30 + 12 + 5 + 3))

    def test_the_tree_is_the_root_and_its_descendants_only(self):
        procs = [(1, 0, 999), (10, 1, 5), (20, 10, 7), (21, 20, 11), (30, 1, 1000)]
        self.assertEqual(trust.tree_ticks(procs, 10), 5 + 7 + 11)

    def test_cpu_lists(self):
        self.assertEqual(trust.parse_cpu_list("4-11"), ASSIGNED)
        self.assertEqual(trust.parse_cpu_list("0,4-5,16"), [0, 4, 5, 16])

    def test_smt_siblings_outside_the_set(self):
        siblings_of = {c: sorted({c, (c + 12) % 24}) for c in range(24)}
        self.assertEqual(trust.smt_siblings(ASSIGNED, siblings_of), SIBLINGS)
        self.assertEqual(trust.smt_siblings(list(range(24)), siblings_of), [])


class AssignedCpuPressure(unittest.TestCase):
    def test_a_saturated_assigned_set_on_an_idle_host_is_noisy(self):
        w = window({c: 1.0 for c in ASSIGNED})
        self.assertEqual(w["foreign_share"], 1.0)
        self.assertLess(w["host_busy_share"], 0.34, "8 of 24 CPUs: the old host-wide check read this as quiet")
        m = trust.machine(50.0, 50.0, 50.0, {"during": w})
        self.assertEqual(m["verdict"], "noisy")
        self.assertTrue(any("assigned" in x for x in m["why"]), m["why"])

    def test_an_idle_assigned_set_with_other_cpus_busy_is_quiet(self):
        others = {c: 1.0 for c in range(24) if c not in ASSIGNED and c not in SIBLINGS}
        w = window(others)
        self.assertEqual(w["foreign_share"], 0.0)
        self.assertEqual(w["siblings_busy_share"], 0.0)
        self.assertEqual(trust.machine(50.0, 50.0, 50.0, {"before": w, "during": w, "after": w})["verdict"], "quiet")

    def test_the_benchs_own_browser_on_the_assigned_cpus_is_not_interference(self):
        w = window({c: 0.25 for c in ASSIGNED}, own=2.0)
        self.assertEqual(w["own_cpus"], 2.0)
        self.assertEqual(w["foreign_cpus"], 0.0)
        self.assertEqual(trust.machine(50.0, 50.0, 50.0, {"during": w})["verdict"], "quiet")

    def test_busy_smt_siblings_share_the_assigned_cores_so_they_are_noisy(self):
        w = window({c: 1.0 for c in SIBLINGS})
        self.assertEqual(w["foreign_share"], 0.0)
        self.assertEqual(w["siblings_busy_share"], 1.0)
        m = trust.machine(50.0, 50.0, 50.0, {"during": w})
        self.assertEqual(m["verdict"], "noisy")
        self.assertTrue(any("sibling" in x for x in m["why"]), m["why"])

    def test_the_slow_calibration_rule_stays(self):
        self.assertEqual(trust.machine(100.0, 100.0, 50.0, {"during": window({})})["verdict"], "noisy")

    def test_a_browser_not_on_the_assigned_cpus_is_noisy(self):
        m = trust.machine(50.0, 50.0, 50.0, {"during": window({})}, unpinned=["0-23"])
        self.assertEqual(m["verdict"], "noisy")


class TheRunnerRecordsAndUsesIt(unittest.TestCase):
    def scenario(self, pressure, load=(0.0, 0.0), browser=("4-11",)):
        t = {"id": HEAD, "target": HEAD, "title": "actuators", "app": "robotparts", "rows": 1149, "synthetic": False}
        cold = [{"first_useful_paint": 100.0, "chain": {}, "view": "table", "status": ""} for _ in range(5)]
        cpus = {"assigned": ASSIGNED, "smt_siblings": SIBLINGS, "browser": list(browser)}
        return runner.aggregate(t, cold, cold, [], [], [], 50.0, 50.0, 50.0, load[0], load[1], 5, pressure=pressure, cpus=cpus)

    def test_the_windows_land_in_the_results(self):
        w = window({})
        s = self.scenario({"before": w, "during": w, "after": w})
        self.assertEqual(set(s["trust"]["pressure"]), {"before", "during", "after"})
        self.assertEqual(s["trust"]["assigned_cpus"], ASSIGNED)
        self.assertEqual(s["trust"]["smt_siblings"], SIBLINGS)
        self.assertEqual(s["trust"]["browser_cpus"], ["4-11"])
        self.assertEqual(s["trust"]["verdict"], "quiet")

    def test_a_saturated_assigned_set_makes_the_scenario_noisy(self):
        busy = window({c: 1.0 for c in ASSIGNED})
        self.assertEqual(self.scenario({"before": window({}), "during": busy, "after": window({})})["trust"]["verdict"], "noisy")

    def test_a_host_load_on_other_cpus_no_longer_makes_it_noisy(self):
        # WHY: load average 40 on 24 CPUs read as noisy under the old rule though the assigned set was idle
        others = window({c: 1.0 for c in range(24) if c not in ASSIGNED and c not in SIBLINGS})
        s = self.scenario({"before": others, "during": others, "after": others}, load=(40.0, 40.0))
        self.assertEqual(s["trust"]["verdict"], "quiet", s["trust"]["why"])
        self.assertEqual(s["trust"]["loadavg"], [40.0, 40.0], "the load average is still recorded, as context")


if __name__ == "__main__":
    unittest.main()
