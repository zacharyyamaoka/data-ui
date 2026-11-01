"""bench/publish.py keeps noisy runs out of the KPI series Vibe Tracks reads (its headline is the newest point,
whatever its trust): --move-noisy moves them to kpi_diagnostics.jsonl, atomically, and is idempotent; the
no_page_errors gate (no trust label) stays."""

import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bench_publish", ROOT / "bench" / "publish.py")
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)


def pt(kpi, value, trust=None):
    p = {"schema": "vt-kpi-point/1", "kpi": kpi, "t": "2026-10-27T00:00:00+00:00", "value": value, "labels": {}}
    if trust:
        p["labels"]["trust"] = trust
    return p


class MoveNoisy(unittest.TestCase):
    def test_moves_only_noisy_points_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d)
            pts = [pt("first_paint_ms", 127, "quiet"), pt("first_paint_ms", 2847, "noisy"), pt("no_page_errors", 0), pt("rail_ms", 5, "quiet")]
            (out / "kpi_series.jsonl").write_text("".join(json.dumps(p) + "\n" for p in pts))
            publish.move_noisy(out)
            kept = [json.loads(x) for x in (out / "kpi_series.jsonl").read_text().splitlines()]
            aside = [json.loads(x) for x in (out / "kpi_diagnostics.jsonl").read_text().splitlines()]
            self.assertEqual([p["value"] for p in kept], [127, 0, 5])
            self.assertEqual([p["value"] for p in aside], [2847])
            publish.move_noisy(out)
            self.assertEqual(len((out / "kpi_diagnostics.jsonl").read_text().splitlines()), 1)
            self.assertFalse((out / "kpi_series.jsonl.tmp").exists())

    def test_noisy_reads_the_trust_label(self):
        self.assertTrue(publish.noisy(pt("x", 1, "noisy")))
        self.assertFalse(publish.noisy(pt("x", 1, "quiet")))
        self.assertFalse(publish.noisy(pt("no_page_errors", 0)))


class MoveRun(unittest.TestCase):
    def test_moves_one_runs_points_to_history(self):
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d)
            a = pt("first_paint_ms", 128, "quiet"); a["source"] = {"run_ids": ["20261027-071035-robotparts-actuators"]}
            b = pt("first_paint_ms", 204, "quiet"); b["source"] = {"run_ids": ["20261027-115011-robotparts-actuators"]}
            g = pt("no_page_errors", 0); g["source"] = {"run_ids": ["20261027-115011-a", "20261027-115011-b"]}
            (out / "kpi_series.jsonl").write_text("".join(json.dumps(p) + "\n" for p in (a, b, g)))
            publish.move_run(out, "20261027-115011")
            kept = [json.loads(x)["value"] for x in (out / "kpi_series.jsonl").read_text().splitlines()]
            hist = [json.loads(x)["value"] for x in (out / "kpi_history.jsonl").read_text().splitlines()]
            self.assertEqual(kept, [128])
            self.assertEqual(hist, [204, 0])
            publish.move_run(out, "20261027-115011")
            self.assertEqual(len((out / "kpi_history.jsonl").read_text().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
