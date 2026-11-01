"""Write this case's data: one row per training-bench run (model, params, metrics) from Vibe Tracks' committed
synthetic grasp bench.

    python3 gallery/examples/ml-experiments/source/build.py

Input (read-only): VIBETRACKS (default ~/vibetracks) tests/fixtures/kpi/synthetic/runs_table.jsonl (vt-run/1:
120 runs, 40 rounds x 3 environments) and models_catalog.json. ILLUSTRATIVE: the fixture's models are made up ("a
made-up grasp model") and its numbers are generated for Vibe Tracks' tests. No real run log with per-run metrics
is committed in Vibe Tracks or bam_ws (their tracked .jsonl / .csv files, searched 2026-10-26), so this case shows
the shape of experiment tracking, not results.

Columns: the run's facets as written (model, env, tier, lane, bench), its round (r01 -> 1, the step), its counts
(attempts, successes, compute_s), and three derived per-run metrics, each marked derived: success_rate =
successes / attempts, compute_mean_s = compute_s / attempts, sppm = 60 x success_rate / compute_mean_s.
"""

from __future__ import annotations

import json
import os
import pathlib

HERE = pathlib.Path(__file__).resolve().parents[1]
VT = pathlib.Path(os.environ.get("VIBETRACKS", "~/vibetracks"))
FIXTURE = VT / "tests" / "fixtures" / "kpi" / "synthetic"


def main() -> None:
    families = {e["id"]: e["family"] for e in json.loads((FIXTURE / "models_catalog.json").read_text(encoding="utf-8"))["entries"]}
    rows = []
    for line in (FIXTURE / "runs_table.jsonl").read_text(encoding="utf-8").splitlines():
        run = json.loads(line)
        f, m = run["facets"], run["metrics"]
        rate = m["successes"] / m["attempts"] if m["attempts"] else None
        mean = m["compute_s_sum"] / m["attempts"] if m["attempts"] else None
        rows.append({"id": run["run_id"], "run": run["run_id"], "round": int(run["run_id"][1:3]), "started": run["t"],
                     "model": f["model"], "family": families.get(f["model"], f["model"].split(".")[0]), "env": f["env"],
                     "tier": f["tier"], "lane": f["lane"], "bench": f["bench_version"],
                     "attempts": m["attempts"], "successes": m["successes"], "compute_s": round(m["compute_s_sum"], 3),
                     "success_rate": None if rate is None else round(rate, 4),
                     "compute_mean_s": None if mean is None else round(mean, 4),
                     "sppm": None if not rate or not mean else round(60 * rate / mean, 3)})
    data = {
        "id": "ml-experiments", "title": "Grasp model runs (synthetic, illustrative)", "titleProperty": "run",
        "source": f"vibetracks {FIXTURE.relative_to(VT)}/runs_table.jsonl (vt-run/1, synthetic: made-up models)",
        "properties": {
            "run": {"type": "text", "width": 190}, "round": {"type": "number", "width": 64, "note": "the run's round, r01 -> 1: the step"},
            "started": {"type": "date", "width": 190}, "model": {"type": "text", "width": 120, "display": "badge"},
            "family": {"type": "text", "width": 70}, "env": {"type": "text", "width": 160}, "tier": {"type": "text", "width": 60},
            "lane": {"type": "text", "width": 80}, "bench": {"type": "text", "width": 60},
            "attempts": {"type": "number", "width": 80}, "successes": {"type": "number", "width": 90},
            "compute_s": {"type": "number", "unitText": "s", "width": 100},
            "success_rate": {"type": "number", "decimals": 3, "width": 110, "derived": "successes / attempts"},
            "compute_mean_s": {"type": "number", "unitText": "s", "width": 120, "derived": "compute_s / attempts"},
            "sppm": {"type": "number", "unitText": "picks/min", "width": 120, "derived": "60 x success_rate / compute_mean_s"},
        },
        "rows": rows,
    }
    out = HERE / "runs.json"
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{out.relative_to(HERE.parents[2])}: {len(rows)} rows, {out.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
