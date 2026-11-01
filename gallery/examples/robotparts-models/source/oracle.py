"""The independent oracle for the three model cases' browser checks: the numbers the pages must show, recomputed from
the rack's own analysis files (/archive/datasets/bam_rig), never from models.json or from build.py's code. WHY a
second path: a check that compares the page with the file the page reads only proves the view copied it; this proves
the file and the page both say what the rack measured. When the archive is not on this machine, `available()` is
False and the checks fall back to models.json's run records (said so in the check's name), never faked.
"""

from __future__ import annotations

import json
import pathlib
import statistics

RACK = pathlib.Path("/archive/datasets/bam_rig")
CANS = (1, 4, 11, 12, 13, 14, 15, 21)


def available() -> bool:
    return (RACK / "rack_2026-10-24" / "analysis" / "floors.json").exists()


def _load(*parts):
    return json.loads(RACK.joinpath(*parts).read_text(encoding="utf-8"))


def floor(can: int) -> float:
    return _load("rack_2026-10-24", "analysis", "floors.json")[str(can)]["floor_mrad"]


def headline_runs(can: int) -> dict[str, dict[str, float]]:
    """Each headline configuration's per-run q RMS (mrad) on the Oct 23 held-out tapes, keyed by what it is, not by
    the case's model names: identified, full, full without the current loop, full with soft friction."""
    b = _load("rack_2026-10-23", "analysis", f"budget_can{can}.json")
    full = b["full_rms_per_run_mrad"]
    delta = {t["term"]: t["per_run"] for t in b["terms"]}
    out = {"identified": b["reference_twins_rms_mrad"]["identified"]["per_run"], "full": dict(full)}
    if "current loop" in delta:
        out["no current loop"] = {k: full[k] + delta["current loop"][k] for k in full}
    if "friction stiffness" in delta:
        out["soft friction"] = {k: full[k] + delta["friction stiffness"][k] for k in full}
    return out


def best(can: int) -> tuple[str, float, float | None]:
    """(configuration, its median / floor, the runner-up's median / floor) on the held-out tapes."""
    f = floor(can)
    scored = sorted((statistics.median(v.values()) / f, k) for k, v in headline_runs(can).items())
    return scored[0][1], scored[0][0], scored[1][0] if len(scored) > 1 else None


def staircase_runs(can: int, config: str = "full") -> list[float]:
    """The full twin's q RMS / floor on the Oct 23 held-out staircase runs."""
    b = _load("rack_2026-10-23", "analysis", f"budget_can{can}.json")
    kinds = {h["run"]: h["kind"] for h in b["held_out_runs"]}
    f = floor(can)
    return sorted(v / f for k, v in headline_runs(can)[config].items() if kinds[k] == "staircase")


def card_term(can: int, term: str) -> dict:
    card = _load("rack_2026-10-23", "analysis", "model_cards", f"can{can}.json")
    return next(t for t in card["terms"] if t["term"] == term)


def ablation_delta(can: int, term: str) -> float:
    b = _load("rack_2026-10-23", "analysis", f"budget_can{can}.json")
    return next(t["delta_rms_mrad"] for t in b["terms"] if t["term"] == term)


def pivot_cells(rows: list[dict], value: str = "x_floor") -> dict[tuple, float]:
    """From models.json's run records: the median of `value` per (variant, actuator, bench, test), as a pivot's cell."""
    cells: dict[tuple, list[float]] = {}
    for r in rows:
        v = r.get(value)
        v = v.get("value") if isinstance(v, dict) else v
        if r.get("kind") == "run" and v is not None:
            cells.setdefault((r["variant"], r["actuator"], r["bench"], r["test"]), []).append(v)
    return {k: statistics.median(v) for k, v in cells.items()}


def rolled_identified(test: str) -> tuple[float, int]:
    """The identified reference twin (M2.coulomb_viscous) rolled up across all 8 actuators on one Oct 23 held-out
    test: the median of every run's q RMS / its actuator's floor, and how many runs, straight from the budget files."""
    xs = []
    for can in CANS:
        b = _load("rack_2026-10-23", "analysis", f"budget_can{can}.json")
        kinds = {h["run"]: (f"tape {h['run'].rsplit('_', 1)[1]}" if h["kind"] == "tape" else h["kind"]) for h in b["held_out_runs"]}
        f = floor(can)
        xs += [q / f for run, q in b["reference_twins_rms_mrad"]["identified"]["per_run"].items() if kinds[run] == test]
    return statistics.median(xs), len(xs)


def identified_per_actuator_max() -> float:
    """The largest of the 8 actuators' identified-twin held-out medians (× floor): a roll-up with agg max."""
    return max(statistics.median(headline_runs(can)["identified"].values()) / floor(can) for can in CANS)


def readme_line(can: int) -> tuple[str, str]:
    """(fit commit, the README's first sentence at that commit), read with git from bam_ws, never from models.json."""
    import subprocess
    rev = _load("rack_2026-10-23", "analysis", f"budget_can{can}.json")["code"]["git_head"]
    text = subprocess.run(["git", "-C", "~/bam_ws", "show", f"{rev}:src/dev/bam_rack_twin/README.md"], capture_output=True, text=True).stdout
    para = text.split("\n\n")[1] if "\n\n" in text else text
    return rev, " ".join(para.split())[:80]
