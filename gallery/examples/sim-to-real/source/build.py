"""Write this case's data: the rack's eight motor twins against REAL hardware runs (Oct 23-25 2026).

    python3 -I gallery/examples/sim-to-real/source/build.py

Inputs (read-only), under RACK (default /archive/datasets/bam_rig):
  rack_2026-10-23/analysis/budget_can{1,4,11,12,13,14,15,21}.json   the error budget: real vs twin RMS per run (mrad)
  rack_2026-10-23/analysis/model_cards/can*.json                    the motor model cards (terms + datasheet)
  rack_2026-10-24/analysis/{acceptance,floors,friction_study}.json  gates, repeat floors, the M0-M3 friction ladder
  rack_2026-10-25/analysis/twin_round{4,5,6,7,9,10}.json            the twin rounds (round 8 is 1.4 MB and left out)
Code that defines them (read for meaning only): bam_ws worktree sim-to-real-motor-models-f1ee43, branch
claude/sim-to-real-motor-twins (00974f82), src/dev/bam_rack_twin/ (docs/friction_study.py, model_card.py).

Writes motors.json, models.json, terms.json, runs.json, rounds.json. Error cells are rich cells with basis
"measured": the RMS of (real run - twin replay) is a number computed from real hardware recordings. A floor that
is a stand-in (a sine cycle-to-cycle proxy because the station has no repeated identical tape) is drawn
"stand-in", never "measured". read_on 2026-10-26.
"""

from __future__ import annotations

import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "tools"))  # parents[3] is gallery/
from public_paths import public  # noqa: E402  (judge r2 #6: no absolute home path in what the site publishes)
import json
import os
import pathlib
import re
import statistics

HERE = pathlib.Path(__file__).resolve().parents[1]
RACK = pathlib.Path(os.environ.get("RACK", "/archive/datasets/bam_rig"))
CANS = (1, 4, 11, 12, 13, 14, 15, 21)
READ_ON = "2026-10-26"
D23, D24, D25 = RACK / "rack_2026-10-23/analysis", RACK / "rack_2026-10-24/analysis", RACK / "rack_2026-10-25/analysis"


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(name: str, data: dict) -> None:
    out = HERE / name
    out.write_text(json.dumps(public(data), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{out.relative_to(HERE.parents[2])}: {len(data['rows'])} rows, {out.stat().st_size:,} bytes")


def motor(can: int) -> str:
    return f"CAN {can}"


def mrad(value, source: str, basis: str = "measured", n: int | None = None, **extra) -> dict:
    cell = {"value": None if value is None else round(value, 4), "unit": "mrad", "basis": basis, "source": source}
    if n is not None:
        cell["n"] = n
    cell.update(extra)
    return cell


def ratio(value, source: str) -> dict:
    return {"value": None if value is None else round(value, 3), "unit": "×", "basis": "derived", "source": source}


def short(text, limit: int = 240) -> str:
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def sig(value) -> str:
    return f"{value:.4g}" if isinstance(value, (int, float)) else str(value)


SRC = f"{RACK}/rack_2026-10-23/analysis/budget_can*.json + model_cards/can*.json; rack_2026-10-24/analysis/{{acceptance,floors,friction_study}}.json; rack_2026-10-25/analysis/twin_round*.json"
SRC_TAIL = f" (bam_rack_twin 0.1.0, bam_ws sim-to-real-motor-models-f1ee43 @ 00974f82); read_on {READ_ON}. Real hardware recordings of the rack, Oct 23-25 2026."


def build_motors(budgets: dict, cards: dict, acceptance: dict, floors: dict) -> None:
    rows = []
    for can in CANS:
        b, card, floor = budgets[can], cards[can], floors[str(can)]
        gates = acceptance["stations"][str(can)]["gates"]
        count = lambda status: sum(1 for g in gates if g["status"] == status)  # noqa: E731
        terms = card["terms"]
        repeats = "repeat" in (b["floor"].get("method") or "") and b["floor"].get("status") == "ok"
        floor_cell = mrad(b["floor_rms_mrad"], f"budget_can{can}.json:floor_rms_mrad", "measured" if repeats else "stand-in",
                          n=len(b["floor"]["pairs"]) if repeats else None,
                          **({} if repeats else {"note": b.get("floor_kind", "proxy")}))
        peak = card["datasheet"].get("peak_torque_out_nm")
        rows.append({
            "id": f"can{can}", "motor": motor(can), "can": can, "part": card["motor"]["part"], "board": card["motor"]["board"],
            "floor": floor_cell, "floor_kind": "repeats: identical tape pairs" if repeats else "proxy: sine cycle-to-cycle (no repeated tape)",
            "repeat_floor": mrad(floor["floor_mrad"], f"floors.json:{can}.floor_mrad", n=floor["repeats"], note=f"median pairwise RMS of {floor['repeats']} identical floor-tape repeats ({floor['class']})"),
            "twin": mrad(b["full_rms_mrad"], f"budget_can{can}.json:full_rms_mrad", n=b["runs"]),
            "twin_over_floor": ratio(b["full_rms_mrad"] / b["floor_rms_mrad"], f"budget_can{can}.json: full_rms_mrad / floor_rms_mrad"),
            "gates_pass": count("pass"), "gates_fail": count("fail"), "gates_partial": count("partial"), "gates_not_run": count("not_run"),
            "terms_total": len(terms), "terms_measured": sum(1 for t in terms if t["status"] == "measured"),
            "datasheet_peak_torque_nm": ({"value": peak, "unit": "N·m", "basis": "datasheet", "source": f"model_cards/can{can}.json:datasheet.peak_torque_out_nm"}
                                         if peak is not None else {"value": None, "why": "the card's datasheet has no peak torque for this part"}),
            "ratio": {"value": card["datasheet"]["ratio"], "unit": ":1", "basis": "datasheet", "source": f"model_cards/can{can}.json:datasheet.ratio"},
        })
    write("motors.json", {
        "id": "sim-to-real-motors", "title": "Rack motor twins vs real hardware (8 motors)", "titleProperty": "motor",
        "source": f"{SRC}{SRC_TAIL}",
        "properties": {
            "motor": {"type": "text", "width": 80}, "can": {"type": "number", "width": 60, "note": "CAN id on the rack; joins every file here."},
            "part": {"type": "text", "display": "badge", "width": 190, "note": "Motor part from the model card (JMC parts are inferred from Kv/R, CAN 15 is unidentified)."},
            "board": {"type": "text", "width": 110, "note": "moteus board model."},
            "floor": {"type": "number", "width": 110, "note": "The measurement floor the budget compares the twin to: the RMS two identical runs disagree by. Measured for CAN 14 only; the other seven use a sine cycle-to-cycle proxy (drawn stand-in), because those stations have no repeated identical tape."},
            "floor_kind": {"type": "text", "width": 220, "note": "How `floor` was obtained (repeats or proxy)."},
            "repeat_floor": {"type": "number", "width": 120, "note": "Floor from 5 identical floor-tape repeats on the pick-and-place tape (rack_2026-10-24 floors.json), every motor: a different tape and day than `floor`, so not comparable to `twin`."},
            "twin": {"type": "number", "width": 110, "note": "Full twin: median over all real runs of the RMS of (real - twin) joint angle, from the 10-23 budget. All the budget's runs are listed as held out. n = runs."},
            "twin_over_floor": {"type": "number", "width": 120, "note": "twin / floor: 1× would be indistinguishable from the rack repeating itself; see floor_kind for how trustworthy the floor is."},
            "gates_pass": {"type": "number", "width": 80, "note": "Acceptance gates (T1-T11, rack_2026-10-24 acceptance.json) that passed."},
            "gates_fail": {"type": "number", "width": 80, "note": "Acceptance gates that failed."},
            "gates_partial": {"type": "number", "width": 80, "note": "Acceptance gates passed in part."},
            "gates_not_run": {"type": "number", "width": 80, "note": "Acceptance gates not run yet (pass + fail + partial + not run = 11)."},
            "terms_total": {"type": "number", "width": 80, "note": "Rows in the model card."},
            "terms_measured": {"type": "number", "width": 90, "note": "Card rows with status measured (the others are board settings, datasheet, refused or pending)."},
            "datasheet_peak_torque_nm": {"type": "number", "width": 130, "note": "Peak output torque from the vendor datasheet; the card has it for the GIM4305 only."},
            "ratio": {"type": "number", "width": 70, "note": "Gear ratio from the datasheet (1 = direct drive)."},
        },
        "rows": rows,
    })


# the ladder, simplest -> richest. rung is a global sort key across families (documented in the property note)
RUNG = {
    "naive torque scale": 0, "identified": 1, "identified+": 2, "inertia at the replay-error estimate": 3,
    "inertia at the prior's low end": 4, "inertia at the prior's high end": 5, "ripple k <= 32 only": 6, "full twin": 7,
    "current best": 10, "M0 Coulomb refit": 11, "M1 Coulomb + viscous": 12, "M2 Stribeck + viscous": 13, "M3 load + viscous": 14,
    "repeat floor": 20, "floor (sine-cycle proxy)": 20,
}


def build_models(budgets: dict, friction: dict) -> None:
    rows = []

    def add(can: int, model: str, family: str, error: dict, source_file: str, ruler: str, base_twin: str = "-") -> None:
        rows.append({"id": f"can{can}/{base_twin}/{model}", "motor": motor(can), "can": can, "model": model, "family": family, "rung": RUNG[model],
                     "error": error, "ruler": ruler, "base_twin": base_twin, "source_file": source_file})

    budget_ruler = "10-23 real runs (budget)"
    for can in CANS:
        b = budgets[can]
        f = f"budget_can{can}.json"
        n = b["runs"]
        for name, ref in b["reference_twins_rms_mrad"].items():
            add(can, name, "reference", mrad(ref["median"], f"{f}:reference_twins_rms_mrad.{name}.median", n=len(ref["per_run"])), f, budget_ruler)
        for name, diag in b["diagnostic_twins_rms_mrad"].items():
            add(can, name, "diagnostic", mrad(diag["median"], f"{f}:diagnostic_twins_rms_mrad.{name}.median", n=len(diag["per_run"])), f, budget_ruler)
        add(can, "full twin", "full", mrad(b["full_rms_mrad"], f"{f}:full_rms_mrad", n=n), f, budget_ruler)
        repeats = b["floor"].get("status") == "ok"
        add(can, "repeat floor" if repeats else "floor (sine-cycle proxy)", "floor",
            mrad(b["floor_rms_mrad"], f"{f}:floor_rms_mrad", "measured" if repeats else "stand-in", n=len(b["floor"]["pairs"]) if repeats else None), f, budget_ruler)
    study = "friction_study.json"
    for key in ("can11", "can12", "can13"):
        st = friction["stations"][key]
        can = int(key[3:])
        for base_twin, models in st["bases"].items():
            for model, entry in models.items():
                label = "current best" if model == "base" else model
                held = [entry["per_run_mrad"][r] for r in st["held_out"]]
                assert abs(statistics.median(held) - entry["held_out_median_mrad"]) < 1e-9
                add(can, label, "friction", mrad(entry["held_out_median_mrad"], f"{study}:stations.{key}.bases.{base_twin}.{model}.held_out_median_mrad", n=len(held)),
                    study, "10-24 dataset, held-out runs (friction study)", base_twin)
    rows.sort(key=lambda r: (r["can"], r["family"] == "friction", r["base_twin"], r["rung"], r["model"]))
    write("models.json", {
        "id": "sim-to-real-models", "title": "Model ladder vs error, per motor (real hardware runs)", "titleProperty": "model",
        "source": f"{SRC}{SRC_TAIL} Medians: reference, diagnostic and full twins are the median over the budget's per-run RMS; friction rows are the held-out median of the 12-run 10-24 dataset (8 held out, 4 trained on).",
        "properties": {
            "motor": {"type": "text", "width": 80}, "can": {"type": "number", "width": 60},
            "model": {"type": "text", "width": 240, "note": "The twin variant. reference = the earlier identified twins; diagnostic = the full twin with one term changed; full = the deployed twin; friction = the M0-M3 friction ladder; floor = how far two identical real runs disagree."},
            "family": {"type": "text", "display": "badge", "width": 100, "note": "reference | diagnostic | full | floor (10-23 budget ruler) or friction (10-24 dataset ruler: a different set of runs, do not plot on one axis with the others)."},
            "rung": {"type": "number", "width": 70, "note": "Sort key, simplest to richest. Budget family: 0 naive torque scale, 1 identified, 2 identified+, 3 inertia at the replay-error estimate, 4 inertia at the prior's low end, 5 inertia at the prior's high end, 6 ripple k <= 32 only, 7 full twin. Friction family (own ruler): 10 current best, 11 M0 Coulomb refit, 12 M1 Coulomb + viscous, 13 M2 Stribeck + viscous, 14 M3 load + viscous. Floor: 20."},
            "error": {"type": "number", "width": 130, "note": "RMS of (real - twin) joint angle, a median over runs (n). measured: computed from real hardware recordings. The floor of a station without repeated tapes is drawn stand-in."},
            "ruler": {"type": "text", "width": 230, "note": "Which runs the error is over. Budget rows: every 10-23 run of the station (all listed as held out). Friction rows: the 8 held-out runs of the 12-run 10-24 dataset (CAN 11, 12, 13 only)."},
            "base_twin": {"type": "text", "width": 120, "note": "Friction rows only: the twin the ladder starts from (`envelope inertia` = CAN 11 with its measured 10-24 armature 0.122 kg·m²). - for the rest."},
            "source_file": {"type": "text", "width": 180, "note": "File under rack_2026-10-23 / 10-24 analysis the number came from."},
        },
        "rows": rows,
    })


def build_terms(cards: dict) -> None:
    status_basis = {"measured": "measured", "board": "chosen", "datasheet": "datasheet", "refused": "estimate"}
    rows = []
    for can in CANS:
        card = cards[can]
        for t in card["terms"]:
            status, value, unit = t["status"], t["value"], t.get("unit") or ""
            source = f"model_cards/can{can}.json:terms.{t['term']}"
            ci = t.get("ci95")
            if isinstance(value, (int, float)) and not isinstance(value, bool) and status in status_basis:
                cell = {"value": float(f"{value:.6g}") if isinstance(value, float) else value, "basis": status_basis[status], "source": source}
                if unit:
                    cell["unit"] = unit
                if isinstance(ci, list) and len(ci) == 2:
                    cell["low"], cell["high"] = ci
                if status == "refused":
                    cell["note"] = "refused: the fit was rejected and the twin does not use this number"
            elif status == "pending":
                cell = {"value": None, "why": "pending: " + short(t.get("note") or t.get("method") or "not measured yet", 120)}
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                cell = {"value": value, "unit": unit, "basis": "estimate", "source": source}
            else:
                cell = {"value": None, "why": "not a single number" if value is not None else "no value in the card"}
            rows.append({
                "id": f"can{can}/{t['term']}", "motor": motor(can), "can": can, "term": t["term"], "label": t.get("label") or t["term"],
                "value": cell, "value_text": short(compact(value) if value is not None else "", 120), "unit": unit, "status": status,
                "method": short(t.get("method")), "ci95": "" if not ci else "[" + ", ".join(sig(x) for x in ci) + "]" if isinstance(ci, list) else str(ci),
                "datasheet": "" if t.get("datasheet") is None else short(compact(t["datasheet"]) if not isinstance(t["datasheet"], (int, float, str)) else sig(t["datasheet"]), 120),
                "agreement": short(t.get("agreement") or ""), "in_twin": bool(t.get("in_twin")), "note": short(t.get("note")),
            })
    write("terms.json", {
        "id": "sim-to-real-terms", "title": "Motor model-card terms (8 motors)", "titleProperty": "label",
        "source": f"{D23}/model_cards/can*.json{SRC_TAIL}",
        "properties": {
            "motor": {"type": "text", "width": 80}, "can": {"type": "number", "width": 60},
            "term": {"type": "text", "width": 140, "note": "Model-card key (the physical quantity)."}, "label": {"type": "text", "width": 180},
            "value": {"type": "number", "width": 130, "note": "The card's value. Drawn measured (fitted from real recordings), chosen (a board setting), datasheet, or estimate for a refused fit that the twin does not use. Not a single number or pending: shown as — with the reason; the raw value is in value_text."},
            "value_text": {"type": "text", "width": 220, "note": "The card's value as JSON text (composite values: lists, dicts, strings), cut at 120 characters."},
            "unit": {"type": "text", "width": 80, "note": "The card's unit text, unchanged."},
            "status": {"type": "text", "display": "badge", "width": 100, "note": "measured | board (read from the moteus config) | datasheet | refused (fit rejected as ill-posed) | pending (not measured yet)."},
            "method": {"type": "text", "width": 320, "note": "How the term was obtained, cut at 240 characters."},
            "ci95": {"type": "text", "width": 160, "note": "95% confidence interval as [low, high], 4 significant digits."},
            "datasheet": {"type": "text", "width": 140, "note": "The vendor datasheet's number or band for this term."},
            "agreement": {"type": "text", "width": 200, "note": "How the measured value compares with the datasheet or a second check."},
            "in_twin": {"type": "boolean", "width": 70, "note": "Whether the deployed twin uses this term."},
            "note": {"type": "text", "width": 320, "note": "The card's note, cut at 240 characters (…)."},
        },
        "rows": rows,
    })


def parse_run(run: str) -> tuple:
    session = re.match(r"session_(\d+)([a-z]*)/", run)
    speed = re.search(r"_(slow|medium|fast)$", run)
    kind = re.search(r"_can\d+_([a-z]+)", run)
    return int(session.group(1)), session.group(2), (speed.group(1) if speed else None), (kind.group(1) if kind else None)


def build_runs(budgets: dict) -> None:
    rows = []
    for can in CANS:
        b = budgets[can]
        held = {h["run"]: h for h in b["held_out_runs"]}
        ident = b["reference_twins_rms_mrad"]["identified"]["per_run"]
        ordered = sorted(b["full_rms_per_run_mrad"], key=lambda r: (parse_run(r)[0], parse_run(r)[1], r.split("/")[-1]))
        for order, run in enumerate(ordered, start=1):
            session, suffix, speed, _ = parse_run(run)
            f = f"budget_can{can}.json"
            rows.append({
                "id": f"can{can}/{run}", "motor": motor(can), "can": can, "run": run, "session": session, "session_label": f"{session:02d}{suffix}",
                "order": order, "kind": held[run]["kind"] if run in held else None, "speed": speed,
                "full_twin": mrad(b["full_rms_per_run_mrad"][run], f"{f}:full_rms_per_run_mrad.{run}"),
                "identified_twin": mrad(ident.get(run), f"{f}:reference_twins_rms_mrad.identified.per_run.{run}") if run in ident else {"value": None, "why": "not in the budget"},
                "rows": held[run]["rows"] if run in held else None, "held_out": run in held,
            })
    write("runs.json", {
        "id": "sim-to-real-runs", "title": "Twin error per real run (8 motors)", "titleProperty": "run",
        "source": f"{D23}/budget_can*.json (full_rms_per_run_mrad, reference_twins_rms_mrad.identified.per_run, held_out_runs){SRC_TAIL}",
        "properties": {
            "motor": {"type": "text", "width": 80}, "can": {"type": "number", "width": 60},
            "run": {"type": "text", "width": 300, "note": "Run key in the rack dataset: session_NN/runs/<run name>."},
            "session": {"type": "number", "width": 70, "note": "Session number parsed from the run key; 01a / 01c are sub-sessions of session 1 (see session_label)."},
            "session_label": {"type": "text", "width": 90, "note": "Session as written, with its sub-session letter."},
            "order": {"type": "number", "width": 70, "note": "Acquisition order within the motor: session number, then sub-session letter, then run name."},
            "kind": {"type": "text", "display": "badge", "width": 90, "note": "Run type from the budget's held_out_runs: staircase, sine or tape."},
            "speed": {"type": "text", "width": 80, "note": "slow | medium | fast, parsed from the run name; empty for staircases and sines."},
            "full_twin": {"type": "number", "width": 120, "note": "RMS of (real - full twin) joint angle for this run."},
            "identified_twin": {"type": "number", "width": 130, "note": "Same for the earlier `identified` twin."},
            "rows": {"type": "number", "width": 70, "note": "Samples in the run."},
            "held_out": {"type": "boolean", "width": 80, "note": "Listed in the budget's held_out_runs. Every run is, in all eight budgets."},
        },
        "rows": rows,
    })


def day(stamp: str) -> str:
    return stamp[:19].replace("T", " ") + " UTC" if stamp else ""


def class_text(ratios: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in ratios.items())


def build_rounds(floors: dict) -> None:
    r = {n: load(D25 / f"twin_round{n}.json") for n in (4, 5, 6, 7, 9, 10)}
    rows = []

    def add(rnd: int, can: int, metric: str, **cols) -> None:
        row = {"id": f"round{rnd}/can{can}", "round": rnd, "motor": motor(can), "can": can, "declared_at": r[rnd]["declared_at"], "metric": metric,
               "median": None, "baseline_median": None, "median_vs_baseline": None, "wrote": None, "twin": None,
               "deployed_worst_class": None, "candidate_worst_class": None, "deployed_class_ratio": None, "candidate_class_ratio": None, "source": ""}
        row.update(cols)
        if row["median"] and row["baseline_median"] and row["median"]["value"] is not None and row["baseline_median"]["value"]:
            row["median_vs_baseline"] = ratio(row["median"]["value"] / row["baseline_median"]["value"], f"round{rnd}: median / baseline_median")
        rows.append(row)

    f = lambda n: f"twin_round{n}.json"  # noqa: E731
    for can_key, d in r[4]["results"]["D"].items():  # round 4: full twin vs the real floor-tape repeats, all eight stations
        add(4, int(can_key), "full twin on the real floor-tape repeats", median=mrad(d["q_rms_mrad_median"], f"{f(4)}:results.D.{can_key}.q_rms_mrad_median", n=len(d["runs"])),
            twin=d["twin"], source=f"{f(4)}:results.D.{can_key}")
    e, h = r[5]["results"]["E"], r[5]["results"]["H"]  # round 5: live re-identification (CAN 12) and the new CAN 21 twin
    add(5, 12, "held-out median: live re-identification restored vs stale twin", median=mrad(e["held_out_medians_mrad"]["restored"], f"{f(5)}:results.E.held_out_medians_mrad.restored"),
        baseline_median=mrad(e["held_out_medians_mrad"]["stale"], f"{f(5)}:results.E.held_out_medians_mrad.stale"), twin="restored vs stale", source=f"{f(5)}:results.E")
    add(5, 21, "held-out median: new CAN 21 twin vs old", median=mrad(h["held_out_median_mrad"]["new"], f"{f(5)}:results.H.held_out_median_mrad.new"),
        baseline_median=mrad(h["held_out_median_mrad"]["old"], f"{f(5)}:results.H.held_out_median_mrad.old"), twin="new vs old", source=f"{f(5)}:results.H")
    for key in ("can11", "can12", "can13", "can21"):  # round 6: candidate I-a vs the deployed twin on the dataset family
        s = r[6]["results"]["I"]["stations"][key]
        fam = sorted(s["deployed"]["family_median_mrad"])[-1]
        add(6, int(key[3:]), f"held-out median, {fam}: candidate I-a vs deployed", median=mrad(s["candidates"]["I-a"]["family_median_mrad"][fam], f"{f(6)}:results.I.stations.{key}.candidates.I-a.family_median_mrad.{fam}"),
            baseline_median=mrad(s["deployed"]["family_median_mrad"][fam], f"{f(6)}:results.I.stations.{key}.deployed.family_median_mrad.{fam}"),
            wrote=r[6]["results"]["I"]["picks"][key]["overwrite"], twin="I-a vs " + s["deployed"]["twin"], source=f"{f(6)}:results.I.stations.{key}")
    for key, s in r[7]["results"]["K"]["stations"].items():  # round 7: candidate vs deployed
        fam = sorted(s["deployed"]["family_median_mrad"])[-1]
        add(7, int(key[3:]), f"held-out median, {fam}: candidate vs deployed", median=mrad(s["candidate"]["family_median_mrad"][fam], f"{f(7)}:results.K.stations.{key}.candidate.family_median_mrad.{fam}"),
            baseline_median=mrad(s["deployed"]["family_median_mrad"][fam], f"{f(7)}:results.K.stations.{key}.deployed.family_median_mrad.{fam}"),
            wrote=r[7]["results"]["K"]["picks"][key]["overwrite"], twin="round 7 candidate", source=f"{f(7)}:results.K.stations.{key}")
    for key, s in r[9]["results"]["split-ci"].items():  # round 9: the hold offset with its 95% interval
        lo, hi = s["median_ci95_mrad"]
        add(9, int(key[3:]), "median hold offset (twin - rack at holds), 95% CI", median=mrad(s["median_mrad"], f"{f(9)}:results.split-ci.{key}.median_mrad", n=s["holds"], low=round(lo, 4), high=round(hi, 4)),
            wrote=r[9]["results"]["n-write"]["stations"][key]["write"], twin=s["twin"], source=f"{f(9)}:results.split-ci.{key}")
    for key, s in r[10]["results"]["stations"].items():  # round 10: candidate vs deployed + T2 class ratios
        fam = sorted(s["family_median_mrad"])[-1]
        pick = r[10]["results"]["picks"][key]
        dep, cand = pick["t2_if_written"]["deployed"], pick["t2_if_written"]["candidate"]
        # family_median_mrad is [deployed, candidate]: relative_change vs_deployed in the same file is candidate / deployed - 1
        deployed_median, candidate_median = s["family_median_mrad"][fam]
        add(10, int(key[3:]), f"held-out median, {fam}: candidate {s['family']} vs deployed",
            median=mrad(candidate_median, f"{f(10)}:results.stations.{key}.family_median_mrad.{fam}[1]"),
            baseline_median=mrad(deployed_median, f"{f(10)}:results.stations.{key}.family_median_mrad.{fam}[0]"), wrote=pick["write"], twin=f"round 10 {s['family']}",
            deployed_worst_class=ratio(dep["worst_class"], f"{f(10)}:results.picks.{key}.t2_if_written.deployed.worst_class"), candidate_worst_class=ratio(cand["worst_class"], f"{f(10)}:results.picks.{key}.t2_if_written.candidate.worst_class"),
            deployed_class_ratio=class_text(dep["class_ratio"]), candidate_class_ratio=class_text(cand["class_ratio"]), source=f"{f(10)}:results.stations.{key} + picks.{key}")
    can21 = r[10]["results"]["R"]["can21"]
    dep21 = next(iter(can21["deployed"]["per_run"].values()))["all_mrad"]
    cand21 = next(iter(can21["candidate"]["per_run"].values()))["all_mrad"]
    add(10, 21, "T2 run (one pick-and-place run): candidate vs deployed", median=mrad(cand21, f"{f(10)}:results.R.can21.candidate.per_run", n=1), baseline_median=mrad(dep21, f"{f(10)}:results.R.can21.deployed.per_run", n=1),
        wrote=False, twin="round 10 candidate", deployed_worst_class=ratio(can21["deployed"]["over_floor"]["all"], f"{f(10)}:results.R.can21.deployed.over_floor.all"),
        candidate_worst_class=ratio(can21["candidate"]["over_floor"]["all"], f"{f(10)}:results.R.can21.candidate.over_floor.all"), source=f"{f(10)}:results.R.can21")
    for row in rows:
        row["declared_at"] = day(row["declared_at"])
    rows.sort(key=lambda x: (x["round"], x["can"]))
    write("rounds.json", {
        "id": "sim-to-real-rounds", "title": "Twin improvement rounds 4-10 per motor (real hardware runs)", "titleProperty": "metric",
        "source": f"{D25}/twin_round{{4,5,6,7,9,10}}.json (round 8, 1.4 MB, not read){SRC_TAIL} Rounds differ in structure; each row says in `metric` what its median is. Only the numbers each round shares are extracted.",
        "properties": {
            "round": {"type": "number", "width": 60, "note": "Twin round number. Round 8 is left out (a 1.4 MB file; the rounds' common numbers are in the others)."},
            "motor": {"type": "text", "width": 80}, "can": {"type": "number", "width": 60},
            "declared_at": {"type": "text", "width": 170, "note": "When the round declared its split and rule, before any fit (UTC)."},
            "metric": {"type": "text", "width": 360, "note": "What `median` is for this row. Rounds measure different things; compare rows only within one metric wording."},
            "median": {"type": "number", "width": 120, "note": "The round's headline median, mrad. Round 9: the median hold offset (twin - rack at holds, signed) with its 95% interval and n holds. Others: held-out median of RMS(real - twin) on the round's dataset family (the last family when a station has two)."},
            "baseline_median": {"type": "number", "width": 130, "note": "The same median for the twin it was compared against (deployed, stale or old). Empty where a round has no baseline."},
            "median_vs_baseline": {"type": "number", "width": 120, "note": "median / baseline_median: below 1× is better than the baseline."},
            "wrote": {"type": "boolean", "width": 70, "note": "Whether the round's rule wrote the candidate over the deployed twin (rounds 6, 7, 9, 10). Empty for rounds that have no write rule."},
            "twin": {"type": "text", "width": 220, "note": "Twin id or the comparison that was run."},
            "deployed_worst_class": {"type": "number", "width": 120, "note": "Round 10: the deployed twin's worst T2 class ratio over the floor (× floor); CAN 21: its all-rows ratio over the floor."},
            "candidate_worst_class": {"type": "number", "width": 120, "note": "Same for the candidate."},
            "deployed_class_ratio": {"type": "text", "width": 260, "note": "Round 10: the deployed twin's ratio over the floor per tape class (acceptance T2: 2.0 or less per class)."},
            "candidate_class_ratio": {"type": "text", "width": 260, "note": "Same for the candidate."},
            "source": {"type": "text", "width": 260, "note": "File:key path in the round's JSON."},
        },
        "rows": rows,
    })


def main() -> None:
    budgets = {c: load(D23 / f"budget_can{c}.json") for c in CANS}
    cards = {c: load(D23 / "model_cards" / f"can{c}.json") for c in CANS}
    acceptance, floors, friction = load(D24 / "acceptance.json"), load(D24 / "floors.json"), load(D24 / "friction_study.json")
    build_motors(budgets, cards, acceptance, floors)
    build_models(budgets, friction)
    build_terms(cards)
    build_runs(budgets)
    build_rounds(floors)


if __name__ == "__main__":
    main()
