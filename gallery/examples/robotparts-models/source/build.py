"""Write models.json: every actuator model the rack has scored, one file for three gallery cases.

    python3 gallery/examples/robotparts-models/source/build.py

The models case (robotparts-models: pivot, leaderboard and parameters as tabs of one .base) and the model page
case (robotparts-model) read this one file. Each `.base` view filters to
the record kind it needs, the way a Notion linked view filters one database:

- kind "model": one row per (actuator, model): its headline twin error, its rank on that actuator, and the fitted
  terms it runs (rich cells: value, unit, basis, 95 % CI);
- kind "run":   one row per (actuator, model, held-out run): the twin's joint-angle error q RMS on that run;
- kind "term":  one row per (actuator, term) of the full twin's ablation: what the error does when that term is
  switched off, i.e. what the term adds.

Every number is read from BAM's rack analysis under /archive/datasets/bam_rig (nothing illustrative):

- rack_2026-10-23/analysis/budget_can<N>.json: the Oct 23 held-out tapes (staircase, sine, tapes at three speeds),
  scored for the identified reference twin and the full twin, with each term's per-run ablation delta;
- rack_2026-10-24/analysis/dataset_twin_can<N>.json + plans/dataset/index.json: the Oct 24 dataset (four motion
  classes), the full twin with drive limits;
- rack_2026-10-25/analysis/twin_torque.json: the full twin replaying the 5 floor repeats; for CAN 11/12/13 the
  newer capture twin as well (its `previous` is the full twin);
- rack_2026-10-25/analysis/dataset_twin_can<N>.json: the Oct 25 held-out dataset seeds, where CAN 11/12/13's capture
  twin and the full twin ran side by side;
- rack_2026-10-24/analysis/floors.json: each actuator's floor (5 identical repeats of one tape), so errors compare
  across actuators as "x floor";
- rack_2026-10-23/analysis/model_cards/can<N>.json: the fitted terms, their 95 % CI and status.

Naming follows robotparts' models proposal round 2 (lane/datasheet @ ec9a13c, docs/proposals/models-2026-10-25.md):
M<rung>.<model>[.<variant>]. Mapping, as round 2 did for CAN 14 and generalised here:

- the budget's "identified" reference twin       -> M2.coulomb_viscous (MuJoCo native, soft friction, no driver);
- the budget's full twin                          -> M<k>.<model>.<driver>, named by the highest term it carries:
  a nonzero torque-ripple ablation -> M4.ripple, else a nonzero friction-weakening one -> M3.stribeck, else
  M2.coulomb_viscous; <driver> is the board's driver twin (c1 = moteus-c1, r4 = moteus-r4.11);
- full + the current-loop delta                   -> <full>.ideal (the driver's current loop off: an ideal driver);
- full + the friction-stiffness delta             -> <full>.soft (MuJoCo's default soft friction);
- CAN 11/12/13's round-7 "friction at capture" twin -> M3.capture.r4.
Left out, and why: the budget's "identified+" twin (its definition is not in the analysis files), CAN 11's
"current best" Oct 25 twin (it carries a refitted armature, so it is not the full twin), CAN 21's round-9 PLL twin (its
lineage, a current-mode twin, maps onto no single rung). M0.ideal, M1.datasheet, M3.lugre and M5.dcmotor ran nothing
yet: each keeps one model row with no error, which every view draws as "—", never 0.
"""

from __future__ import annotations

import json
import pathlib
import statistics
import subprocess
import urllib.parse
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "tools"))  # parents[3] is gallery/
from public_paths import public  # noqa: E402  (judge r2 #6: no absolute home path in what the site publishes)

HERE = pathlib.Path(__file__).resolve().parents[1]
RACK = pathlib.Path("/archive/datasets/bam_rig")
A23, A24, A25 = (RACK / f"rack_2026-10-{d}" / "analysis" for d in (23, 24, 25))
CANS = [14, 1, 15, 4, 21, 11, 12, 13]  # data order = the default group order: the GIM4305s first, as round 2 led with CAN 14
TWIN_GRADE = 1.5  # held-out error at most 1.5 x the floor (round 2, §6)
CLASS_LIMIT = 2.0  # and at most 2 x in every motion class

PART = {
    "steadywin-gim4305-10": "GIM4305-10",
    "jmc-60asm400": "JMC 60ASM400 direct",
    "jmc-60asm200": "JMC 60ASM200 + 10:1",
    "unidentified-small-arm": "small arm, 28-pole + 10:1",
}
DRIVER = {"moteus-c1": "c1", "moteus-r4.11": "r4"}
FAMILY = {
    "M0": "M0 · ideal", "M1": "M1 · datasheet", "M2": "M2 · fitted constant friction",
    "M3s": "M3 · static friction", "M3d": "M3 · dynamic friction", "M4": "M4 · grey-box drivetrain",
    "M5": "M5 · motor R, L and heat",
}
SUITES = [  # bench -> its tests, in column order
    ("Held-out tapes · Oct 23", ["staircase", "sine", "tape slow", "tape medium", "tape fast"]),
    ("Dataset · Oct 24", ["pickplace", "cycle", "jog", "sweep"]),
    ("Floor repeats · Oct 24", ["floor tape"]),
    ("Dataset seeds · Oct 25", ["pickplace", "cycle", "jog", "sweep"]),
]
SUITE_ORDER = {s: i for i, (s, _) in enumerate(SUITES)}
TEST_ORDER = {t: i for i, t in enumerate(["staircase", "sine", "tape slow", "tape medium", "tape fast", "pickplace", "cycle", "jog", "sweep", "floor tape"])}
HEADLINE = SUITES[0][0]
BAM_WS = pathlib.Path("~/bam_ws")  # the git repo the twin code lives in (read only)
TWIN_PKG = "src/dev/bam_rack_twin"
TWIN_WORKTREE = pathlib.Path("~/vt-lanes/rig-bam_ws") / TWIN_PKG  # a checkout of bam_ws holding the package
CONTRACT_REGISTRY = ("~/robotparts", "contract/v2.3", "schemas/registry.json")  # robotparts' model kinds (not merged)
KIND_OF = {"M1.datasheet": "datasheet", "M2.coulomb_viscous": "coulomb_viscous", "M3.stribeck": "stribeck", "M3.load": "load_dependent",
           "M3.lugre": "lugre", "M4.ripple": "ripple_map", "M5.dcmotor": "mujoco_dcmotor"}


def git_show(repo, rev, path):
    """A file as it was at a commit (read only); None when the commit or the file is not there."""
    out = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{path}"], capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def on_remote(repo, rev):
    """Whether a commit is on any remote-tracking branch (only then may a page link to a hosted copy)."""
    out = subprocess.run(["git", "-C", str(repo), "branch", "-r", "--contains", rev], capture_output=True, text=True)
    return out.returncode == 0 and bool(out.stdout.strip())


_kinds_text = subprocess.run(["git", "-C", CONTRACT_REGISTRY[0], "show", f"{CONTRACT_REGISTRY[1]}:{CONTRACT_REGISTRY[2]}"], capture_output=True, text=True).stdout
KINDS = json.loads(_kinds_text)["actuator_model_kinds"] if _kinds_text else {}
_readmes = {}


def readme_at(rev):
    if rev not in _readmes:
        _readmes[rev] = git_show(BAM_WS, rev, f"{TWIN_PKG}/README.md")
    return _readmes[rev]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


floors = load(A24 / "floors.json")
torque = load(A25 / "twin_torque.json")
index = load(RACK / "rack_2026-10-24" / "plans" / "dataset" / "index.json")
STEP_CLASS = {(r["can_id"], f"s{r['step']:02d}"): r["class"] for r in index["runs"]}


def r(x, d=6):
    return None if x is None else round(x, d)


def tape_test(run, kind):
    return f"tape {run.rsplit('_', 1)[1]}" if kind == "tape" else kind


# ----------------------------------------------------------------- fitted terms (the model card), as rich cells
# column -> (model-card term, unit text, decimals, how to read the card value)
TERM_COLUMNS = {
    "coulomb": ("coulomb", "N·m", 3), "viscous": ("viscous", "N·m·s/rad", 4),
    "breakaway": (None, "N·m", 3), "stribeck_velocity": (None, "rad/s", 3),
    "weakening": ("stribeck", "N·m·s/rad", 4),
    "capture_fraction": (None, "", 2), "capture_speed": (None, "rad/s", 3), "capture_dwell": (None, "s", 3),
    "ripple": ("ripple", "N·m", 4), "backlash": ("backlash", "arcmin", 1), "gear_stiffness": ("gear_compliance", "N·m/rad", 0),
    "inertia": ("axis_inertia", "kg·m²", 6), "torque_scale": (None, "", 2),
    "kt": ("kt", "N·m/A", 3), "current_loop": (None, "Hz", 0), "latency": ("latency", "ms", 1),
    "resistance": ("phase_resistance", "Ω", 3), "inductance": ("inductance_q", "mH", 3), "kv": ("kv", "rpm/V", 1),
    "winding_rth": ("thermal", "K/W", 2),
}
# which columns each model kind runs (the rest are "not in this model")
FRICTION = ["coulomb", "viscous", "inertia"]
RUNS = {
    "M0.ideal": [],
    "M1.datasheet": ["backlash", "resistance", "kv"],
    "M2.coulomb_viscous": FRICTION,
    "M3.stribeck": FRICTION + ["weakening", "breakaway", "stribeck_velocity"],
    "M3.capture": FRICTION + ["weakening", "capture_fraction", "capture_speed", "capture_dwell"],
    "M3.lugre": FRICTION + ["breakaway", "stribeck_velocity"],
    "M4.ripple": FRICTION + ["weakening", "ripple", "backlash", "gear_stiffness"],
    "M5.dcmotor": ["kt", "resistance", "inductance", "kv", "winding_rth"],
}
DRIVER_TERMS = ["kt", "current_loop", "latency", "torque_scale"]  # what a driver twin (.c1 / .r4) adds


def card_cell(term, unit, card_term):
    """A model-card term as a rich cell: the value in the column's unit, its basis, its 95 % CI as low/high."""
    t = card_term
    if t is None:
        return None
    status, value, ci = t["status"], t["value"], t["ci95"]
    if term == "kt":  # [rotor, output]: the output side
        value = value[1] if isinstance(value, list) else value
    if term == "winding_rth":
        value = value.get("winding_k_per_w", [None])[0] if isinstance(value, dict) else None
        ci = None
    if term == "backlash" and value is not None:
        pass  # the card's unit is arcmin already
    if value is None or isinstance(value, (dict, list)):
        return {"value": None, "why": "not measured yet" if status == "pending" else "not identified"}
    cell = {"value": round(value, 8), "unit": unit, "source": f"model card: {t['label']} ({t['method'] if t.get('method') else status})"}
    if status == "measured":
        cell["basis"] = "measured"
    elif status == "board":
        cell["basis"] = "chosen" if term == "current_loop" else "measured"
        cell["source"] = f"model card: {t['label']}, the board's calibration ({t.get('method') or 'board'})"
    elif status == "datasheet":
        cell["basis"] = "datasheet"
    elif status == "refused":
        # WHY estimate, not dropped: the fit exists but its CI failed the card's test; the reader sees the value and why
        cell["basis"] = "estimate"
        cell["note"] = "fit refused by the model card (its 95 % CI fails the card's test)"
    if ci and all(isinstance(x, (int, float)) for x in ci):
        cell["low"], cell["high"] = round(ci[0], 8), round(ci[1], 8)
    return cell


def datasheet_cell(term, ds):
    """M1.datasheet: the stated value (a band as low/high), basis datasheet."""
    key = {"backlash": "backlash_arcmin", "resistance": "phase_phase_ohm", "kv": "kv_rotor_rpm_v"}[term]
    v = ds.get(key)
    if v is None:
        return {"value": None, "why": "not published"}
    src = f"datasheet: {ds.get('title')}"
    if isinstance(v, list):
        lo, hi = v
        if term == "resistance":  # phase-phase on the sheet, phase-neutral on the card: halve it so the columns compare
            lo, hi = lo / 2, hi / 2
            src += " (phase-phase / 2)"
        return {"value": round((lo + hi) / 2, 6), "low": lo, "high": hi, "basis": "datasheet", "unit": TERM_COLUMNS[term][1], "source": src}
    return {"value": v, "basis": "datasheet", "unit": TERM_COLUMNS[term][1], "source": src}


# ----------------------------------------------------------------- build
rows, models, terms_out = [], [], []
summary = {}


def model_row(can, part, card, budget, name, variant, rung, family, about, backend, ladder, ladder_step):
    row = {
        "kind": "model", "actuator": f"CAN {can} · {PART[part]}", "can": can, "part": PART[part], "board": card["board"]["model"],
        "rung": rung, "family": FAMILY[family], "model": name, "variant": variant, "about": about, "backend": backend,
        "ladder": ladder, "ladder_step": ladder_step,
    }
    return row


blocks = []
for can in CANS:
    rows_before, terms_before = len(rows), len(terms_out)
    budget = load(A23 / f"budget_can{can}.json")
    card = load(A23 / "model_cards" / f"can{can}.json")
    dataset = load(A24 / f"dataset_twin_can{can}.json")
    part = card["motor"]["part"]
    driver = DRIVER[card["board"]["model"]]
    floor = floors[str(can)]["floor_mrad"]
    card_terms = {t["term"]: t for t in card["terms"]}
    deltas = {t["term"]: t for t in budget["terms"]}
    nonzero = lambda term: term in deltas and abs(deltas[term]["delta_rms_mrad"]) > 0  # noqa: E731
    if nonzero("torque ripple"):
        full_name, full_rung, full_family = "M4.ripple", "M4", "M4"
    elif nonzero("friction weakening"):
        full_name, full_rung, full_family = "M3.stribeck", "M3", "M3s"
    else:
        full_name, full_rung, full_family = "M2.coulomb_viscous", "M2", "M2"
    full_terms = [t for t in deltas if nonzero(t)]
    held = {h["run"]: tape_test(h["run"], h["kind"]) for h in budget["held_out_runs"]}
    full = budget["full_rms_per_run_mrad"]
    ref = budget["reference_twins_rms_mrad"]["identified"]["per_run"]
    per_term = {t: deltas[t]["per_run"] for t in deltas}

    # the models of this actuator: (name, variant, rung, family, about, backend, {suite: [(test, run, q)]})
    scored = []
    scored.append(("M2.coulomb_viscous", "M2.coulomb_viscous", "M2", "M2", "Coulomb + viscous, as identified",
                   "MuJoCo native, soft friction, no driver twin",
                   {HEADLINE: [(held[k], k, v) for k, v in ref.items()]}, "1 · M2 identified"))
    oct24 = [(STEP_CLASS[(can, row_["run"].rsplit("/", 1)[1].split("_")[0])], row_["run"].rsplit("/", 1)[1].removesuffix(".npz"),
              row_["twin_q_rms_mrad"]["full + drive limits"]) for row_ in dataset["rows"]]
    # floor repeats: the full twin's replay (twin_torque, or its `previous` / `round4` where a newer twin replaced it)
    tt = torque[str(can)]
    version = budget["full_twin"]["version"]
    floor_full, floor_capture = None, None
    for cand in (tt, tt.get("previous") or {}, (tt.get("previous") or {}).get("round4") or {}):
        if str(cand.get("twin", "")).startswith(version) and cand.get("runs"):
            floor_full = [("floor tape", x["run"].rsplit("/", 1)[1].removesuffix(".npz"), x["q_rms_mrad"]) for x in cand["runs"]]
            break
    if str(tt.get("twin", "")).startswith("capture-"):
        floor_capture = [("floor tape", x["run"].rsplit("/", 1)[1].removesuffix(".npz"), x["q_rms_mrad"]) for x in tt["runs"]]
    oct25_full, oct25_capture = None, None
    p25 = A25 / f"dataset_twin_can{can}.json"
    if p25.exists() and can in (11, 12, 13):
        d25 = load(p25)
        oct25_capture = [(x["class"], x["run"].rsplit("/", 1)[1].removesuffix(".npz"), x["twin_q_rms_mrad"]["full + drive limits"]) for x in d25["rows"]]
        if d25["twins"]["current best (10-24 twin)"] == version + "+limits":
            oct25_full = [(x["class"], x["run"].rsplit("/", 1)[1].removesuffix(".npz"), x["twin_q_rms_mrad"]["current best (10-24 twin)"]) for x in d25["rows"]]

    full_suites = {HEADLINE: [(held[k], k, v) for k, v in full.items()], "Dataset · Oct 24": oct24}
    if floor_full:
        full_suites["Floor repeats · Oct 24"] = floor_full
    if oct25_full:
        full_suites["Dataset seeds · Oct 25"] = oct25_full
    about_full = {"M4.ripple": "Coulomb + weakening + cogging map + backlash", "M3.stribeck": "Coulomb + velocity weakening",
                  "M2.coulomb_viscous": "Coulomb, sticking friction, tuned inertia"}[full_name]
    board_name = card["board"]["model"]
    scored.append((full_name, f"{full_name}.{driver}", full_rung, full_family, f"{about_full}, with the {board_name} driver twin",
                   f"MuJoCo + plugin + {board_name} driver twin", full_suites, "4 · full + driver twin"))
    if "current loop" in per_term:
        scored.append((full_name, f"{full_name}.ideal", full_rung, full_family, f"{about_full}, ideal driver (current loop off)",
                       "MuJoCo + plugin, ideal driver", {HEADLINE: [(held[k], k, full[k] + per_term["current loop"][k]) for k in full]}, "3 · full, ideal driver"))
    if "friction stiffness" in per_term:
        scored.append((full_name, f"{full_name}.soft", full_rung, full_family, f"{about_full}, MuJoCo's soft friction",
                       f"MuJoCo + plugin + {driver}, soft friction", {HEADLINE: [(held[k], k, full[k] + per_term["friction stiffness"][k]) for k in full]}, "2 · full, soft friction"))
    if floor_capture or oct25_capture:
        cap_suites = {}
        if floor_capture:
            cap_suites["Floor repeats · Oct 24"] = floor_capture
        if oct25_capture:
            cap_suites["Dataset seeds · Oct 25"] = oct25_capture
        scored.append(("M3.capture", f"M3.capture.{driver}", "M3", "M3s", "the full twin + friction that captures below a speed",
                       f"MuJoCo + plugin + {board_name} driver twin", cap_suites, "5 · M3.capture"))
    not_run = [
        ("M0.ideal", "M0.ideal", "M0", "M0", "no friction, datasheet inertia", "MuJoCo native", "0 · M0"),
        ("M1.datasheet", "M1.datasheet", "M1", "M1", "the stated values, nothing fitted", "MuJoCo native", "0 · M1"),
        ("M3.lugre", "M3.lugre", "M3", "M3d", "LuGre: a bristle state", "MuJoCo native (dcmotor)", "0 · M3.lugre"),
        ("M5.dcmotor", "M5.dcmotor", "M5", "M5", "R, L, motor constant, winding heat", "MuJoCo native (dcmotor)", "0 · M5"),
    ]

    actuator_models = []
    for name, variant, rung, family, about, backend, suites, step in scored:
        m = model_row(can, part, card, budget, name, variant, rung, family, about, backend, None, step)
        head = [q for _, _, q in suites.get(HEADLINE, [])]
        classes = {}
        for test, _, q in suites.get("Dataset · Oct 24", []):
            classes.setdefault(test, []).append(q)
        m.update({
            "_suites": suites, "_head": head,
            "headline_mrad": {"value": r(statistics.median(head)), "unit": "mrad", "n": len(head), "basis": "measured",
                              "source": f"median q RMS over the {len(head)} Oct 23 held-out runs (budget_can{can}.json)"} if head else {"value": None, "why": "not run on the Oct 23 held-out tapes"},
            "headline_runs": [r(q) for q in head],
            "headline_x": {"value": r(statistics.median(head) / floor, 6), "n": len(head), "basis": "derived",
                           "source": f"headline / this actuator's floor, {floor:.3f} mrad (floors.json, 5 repeats)"} if head else {"value": None, "why": "not run on the Oct 23 held-out tapes"},
            "headline_x_runs": [r(q / floor, 6) for q in head],
            "dataset_x": r(statistics.median([q for _, _, q in suites["Dataset · Oct 24"]]) / floor, 6) if "Dataset · Oct 24" in suites else None,
            "worst_class_x": r(max(statistics.median(v) for v in classes.values()) / floor, 6) if classes else None,
            "worst_class": max(classes, key=lambda c: statistics.median(classes[c])) if classes else None,
            "floor_tape_x": r(statistics.median([q for _, _, q in suites["Floor repeats · Oct 24"]]) / floor, 6) if "Floor repeats · Oct 24" in suites else None,
            "oct25_x": r(statistics.median([q for _, _, q in suites["Dataset seeds · Oct 25"]]) / floor, 6) if "Dataset seeds · Oct 25" in suites else None,
            "floor_mrad": r(floor),
            "n_runs": sum(len(v) for v in suites.values()),
            "benches": [s for s, _ in SUITES if s in suites],
        })
        actuator_models.append(m)
    for name, variant, rung, family, about, backend, step in not_run:
        m = model_row(can, part, card, budget, name, variant, rung, family, about, backend, None, step)
        m.update({"_suites": {}, "_head": [], "headline_mrad": {"value": None, "why": "not run yet"}, "headline_runs": [],
                  "headline_x": {"value": None, "why": "not run yet"}, "headline_x_runs": [], "dataset_x": None, "worst_class_x": None,
                  "worst_class": None, "floor_tape_x": None, "oct25_x": None, "floor_mrad": r(floor), "n_runs": 0, "benches": []})
        actuator_models.append(m)

    # rank on the headline bench, the best model, the runner-up (what the KPI card compares against)
    # WHY the exact median, not the printed one: two ablations can agree to 3 decimals (CAN 13's current loop changes
    # the median by 2e-5 mrad) and the rank must still follow what was measured
    ranked = sorted([m for m in actuator_models if m["_head"]], key=lambda m: statistics.median(m["_head"]))
    for i, m in enumerate(ranked):
        m["rank"] = i + 1
        m["rank_desc"] = len(ranked) - i  # worst first: a KPI card's spark reads worst -> best, the best is its last point
    best = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else None
    for m in actuator_models:
        m.setdefault("rank", None)
        m.setdefault("rank_desc", None)
        m["best"] = m is best
        m["best_model"] = best["variant"]
        m["leader"] = f"CAN {can} · {best['variant']}"  # WHY short: a KPI card's title is one line, ~26 characters
        m["runner_up_x"] = runner["headline_x"]["value"] if runner else None
        # WHY three states: twin-grade needs BOTH the held-out tapes (<= 1.5 x floor) and every motion class (<= 2 x);
        # a model that failed either is "no", one that passed the tapes but never ran the classes is unknown, not "yes"
        head_x, class_x = m["headline_x"]["value"], m["worst_class_x"]
        if (head_x is not None and head_x > TWIN_GRADE) or (class_x is not None and class_x > CLASS_LIMIT):
            m["twin_grade"] = "no"
        elif head_x is not None and class_x is not None:
            m["twin_grade"] = "yes"
        else:
            m["twin_grade"] = {"value": None, "why": "not run on " + ("the Oct 23 tapes" if head_x is None else "the motion classes (Oct 24)")}

    # fitted terms per model
    for m in actuator_models:
        base = m["model"]
        cols = list(RUNS[base])
        if m["variant"].endswith((".c1", ".r4")) or m["model"] == "M3.capture":
            cols += DRIVER_TERMS
        if m["variant"].endswith(".ideal"):
            cols += ["kt", "torque_scale"]
        for col, (term, unit, _dec) in TERM_COLUMNS.items():
            if col not in cols:
                m[col] = {"value": None, "why": f"not in {m['variant']}"}
                continue
            if base == "M1.datasheet":
                m[col] = datasheet_cell(col, card["datasheet"])
            elif col == "current_loop":
                hz = budget["full_twin"].get("current_loop_hz")
                m[col] = {"value": hz, "unit": "Hz", "basis": "chosen", "source": "the full twin's current loop: the board's servo.pid_dq_hz (budget)"} if hz else {"value": None, "why": "not set"}
            elif col == "torque_scale":
                ts = budget["full_twin"].get("torque_scale")
                m[col] = {"value": ts, "basis": "measured" if ts and ts != 1.0 else "chosen", "source": "budget: full_twin.torque_scale (independent Kt check)" if ts and ts != 1.0 else "budget: no scale (1.0)"} if ts else {"value": None, "why": "not set"}
            elif col.startswith("capture_"):
                fit = load(A25 / f"dataset_twin_can{can}.json").get("fit") if (A25 / f"dataset_twin_can{can}.json").exists() else None
                key = {"capture_fraction": "capture_fraction", "capture_speed": "capture_speed_rad_s", "capture_dwell": "capture_dwell_s"}[col]
                m[col] = {"value": fit[key], "unit": unit, "basis": "measured", "source": "round 7 capture fit on the training runs (dataset_twin, Oct 25)"} if fit else {"value": None, "why": "not fitted"}
            elif col in ("breakaway", "stribeck_velocity"):
                m[col] = {"value": None, "why": "not fitted: the rack fits a weakening slope, not breakaway and Stribeck velocity"}
            elif col == "weakening" and not nonzero("friction weakening") and base != "M3.stribeck":
                m[col] = {"value": None, "why": "not in this twin (the weakening ablation changes nothing)"}
            elif col in ("ripple", "backlash") and base == "M4.ripple" and not nonzero({"ripple": "torque ripple", "backlash": "backlash"}[col]):
                m[col] = {"value": None, "why": "not in this twin (its ablation changes nothing)"}
            else:
                m[col] = card_cell(col, unit, card_terms.get(term)) or {"value": None, "why": "not on the model card"}

    # each model's own page: what it is (contract 2.3's kind, its equation), what this twin runs, the code it was fitted
    # with (the README at that commit), read only from bam_ws; a hosted link only if the commit is on GitHub's origin
    round7 = load(A25 / "twin_round7.json")["code"]
    sources = budget["full_twin"].get("sources", {})
    variant_note = {".ideal": "The same twin with the driver's current loop switched off (an ideal driver): the budget's `current loop` ablation, run by run.",
                    ".soft": "The same twin on MuJoCo's default soft friction (it creeps instead of sticking): the budget's `friction stiffness` ablation, run by run.",
                    f".{driver}": f"The full twin with the {card['board']['model']} driver twin (its current loop), as the budget ran it."}
    for m in actuator_models:
        ran = m["n_runs"] > 0
        kind = KIND_OF.get(m["model"])
        k = KINDS.get(kind) if kind else None
        lines = [f"**{m['variant']}** on {m['actuator']}: {m['about']}.", ""]
        if k:
            lines += [f"Contract kind `{kind}` (robotparts contract 2.3, not merged): {k['definition']}", "", "```", k["equation"], "```", ""]
        elif m["model"] == "M3.capture":
            lines += ["Not a robotparts 2.3 model kind yet: the rack's round-7 study adds friction that **captures** (sticks) below a capture speed after a dwell, on top of the deployed twin. Its fitted levels are the Capture columns.", ""]
        elif m["model"] == "M0.ideal":
            lines += ["No friction and the datasheet's inertia: the ablation baseline. Not a contract kind.", ""]
        tail = "." + m["variant"].rsplit(".", 1)[1] if m["variant"].count(".") >= 2 else None
        if tail in variant_note:
            lines += [variant_note[tail], "", f"What this twin runs (`budget_can{can}.json`, full_twin.sources):", ""]
            lines += [f"- **{key}**: {str(val).replace(chr(10), ' ')}" for key, val in sources.items()]
        if m["variant"] == "M2.coulomb_viscous":
            lines += ["The budget's *identified* reference twin: the identified Coulomb friction and inertia on MuJoCo's native joint friction, no driver twin."]
        if not ran:
            lines += ["**Not run on the rack yet**: no twin code has scored it, so it has no error, commit or README of its own."]
        m["description"] = "\n".join(lines).strip()
        code = round7 if m["model"] == "M3.capture" else budget["code"]
        if ran:
            rev = code["git_head"]
            text = readme_at(rev)
            m["readme"] = text if text else {"value": None, "why": f"README.md not found at {rev[:10]}"}
            m["code_commit"] = rev[:10] + (f" + uncommitted changes (source sha256 {code['source_sha256']})" if code.get("dirty") else "")
            m["code_path"] = str(TWIN_WORKTREE)
            hosted = on_remote(BAM_WS, rev)
            m["code_hosted"] = "on GitHub (origin)" if hosted else "local only: the commit is not on GitHub's origin"
            m["code_url"] = f"https://github.com/zacharyyamaoka/bam_ws/tree/{rev}/{TWIN_PKG}" if hosted else None
        else:
            why = "not run: no twin code has scored this model"
            m["readme"] = {"value": None, "why": why}
            m["code_commit"] = {"value": None, "why": why}
            m["code_path"] = {"value": None, "why": why}
            m["code_hosted"] = None
            m["code_url"] = None
        m["page"] = "../robotparts-model/index.html?variant=" + urllib.parse.quote(m["variant"], safe="")
    page_of = {m["variant"]: m["page"] for m in actuator_models}

    # the runs (a model that ran nothing keeps one record with no bench, so a pivot still draws its row as "—")
    for m in actuator_models:
        if not m["_suites"]:
            rows.append({"kind": "run", "actuator": m["actuator"], "can": can, "part": m["part"], "board": m["board"],
                         "rung": m["rung"], "family": m["family"], "model": m["model"], "variant": m["variant"], "about": m["about"],
                         "backend": m["backend"], "bench": None, "benches": [], "bench_order": None, "test": None, "test_order": None,
                         "run": None, "q_rms_mrad": {"value": None, "why": "not run yet"}, "x_floor": {"value": None, "why": "not run yet"}, "floor_mrad": r(floor), "page": page_of[m["variant"]]})
        for suite, triples in m["_suites"].items():
            for test, run, q in triples:
                rows.append({"kind": "run", "actuator": m["actuator"], "can": can, "part": m["part"], "board": m["board"],
                             "rung": m["rung"], "family": m["family"], "model": m["model"], "variant": m["variant"], "about": m["about"],
                             "backend": m["backend"], "bench": suite, "benches": [suite], "bench_order": SUITE_ORDER[suite], "test": test, "test_order": TEST_ORDER[test],
                             "run": run, "q_rms_mrad": r(q), "x_floor": r(q / floor, 6), "floor_mrad": r(floor), "page": page_of[m["variant"]]})

    # what each term adds: the full twin's ablation (switch the term off; the error change on each held-out run)
    rung_of = {"friction stiffness": ("M2", "M2"), "inertia": ("M2", "M2"), "friction weakening": ("M3", "M3s"),
               "torque ripple": ("M4", "M4"), "backlash": ("M4", "M4"), "gravity": ("M2", "M2"),
               "current loop": ("driver", None), "command delay": ("driver", None), "torque scale": ("driver", None)}
    for t in budget["terms"]:
        runs_delta = [r(v) for v in t["per_run"].values()]
        rung, fam = rung_of.get(t["term"], ("other", None))
        terms_out.append({"kind": "term", "actuator": f"CAN {can} · {PART[part]}", "can": can, "part": PART[part], "board": card["board"]["model"],
                          "rung": rung, "family": FAMILY[fam] if fam else "driver twin (not a rung)", "variant": f"{full_name}.{driver}", "model": full_name,
                          "term": t["term"], "term_note": t.get("note", ""), "benches": [HEADLINE], "page": page_of[f"{full_name}.{driver}"],
                          "delta_mrad": {"value": r(t["delta_rms_mrad"]), "unit": "mrad", "n": len(runs_delta), "basis": "measured",
                                         "source": f"budget_can{can}.json: the error with '{t['term']}' off minus the full twin's, over {len(runs_delta)} held-out runs"},
                          "delta_runs": runs_delta,
                          "delta_x": r(t["delta_rms_mrad"] / floor, 6), "floor_mrad": r(floor)})
    for m in actuator_models:
        for k in ("_suites", "_head"):
            m.pop(k)
    blocks.append((best["headline_x"]["value"], actuator_models, rows_before, len(rows), terms_before, len(terms_out)))
    summary[can] = (best["variant"], best["headline_x"]["value"], len(actuator_models))

# WHY ranked: the data's order is every view's default group order, and a leaderboard reads best actuator first
blocks.sort(key=lambda b: b[0])
for _, ms, *_ in blocks:
    models.extend(ms)
runs_ranked = [x for _, _, a, b, _, _ in blocks for x in rows[a:b]]
terms_ranked = [x for _, _, _, _, a, b in blocks for x in terms_out[a:b]]
rows, terms_out = runs_ranked, terms_ranked
all_rows = models + rows + terms_out
for i, row in enumerate(all_rows):
    row["id"] = f"{row['kind'][0]}{i:04d}"

N = lambda unit, dec, **kw: {"type": "number", "unitText": unit, "decimals": dec, **kw}  # noqa: E731
props = {
    "kind": {"type": "text", "width": 70}, "actuator": {"type": "text", "width": 220}, "can": {"type": "number", "hidden": True},
    "part": {"type": "text", "width": 170}, "board": {"type": "text", "width": 110},
    "rung": {"type": "text", "width": 70}, "family": {"type": "text", "width": 210}, "model": {"type": "text", "width": 160},
    "variant": {"type": "text", "width": 190}, "about": {"type": "text", "width": 300}, "backend": {"type": "text", "width": 260},
    "ladder_step": {"type": "text", "width": 170}, "ladder": {"type": "text", "hidden": True},
    "headline_mrad": N("mrad", 2, width=130, values="headline_runs", better="lower"),
    "headline_runs": {"type": "list", "hidden": True},
    "headline_x": N("× floor", 2, width=130, values="headline_x_runs", better="lower"),
    "headline_x_runs": {"type": "list", "hidden": True},
    "dataset_x": N("× floor", 2, width=120, better="lower", derived="median over the Oct 24 dataset / floor"),
    "worst_class_x": N("× floor", 2, width=120, better="lower", derived="the worst motion class's median / floor"),
    "worst_class": {"type": "text", "width": 100},
    "floor_tape_x": N("× floor", 2, width=120, better="lower", derived="median over the 5 floor repeats / floor"),
    "oct25_x": N("× floor", 2, width=120, better="lower", derived="median over the Oct 25 held-out seeds / floor"),
    "floor_mrad": N("mrad", 3, width=100), "n_runs": N("", 0, width=70), "benches": {"type": "list", "width": 260},
    "rank": N("", 0, width=60), "rank_desc": {"type": "number", "hidden": True, "derived": "models ranked on this actuator, worst first"}, "best": {"type": "boolean", "width": 60},
    "best_model": {"type": "text", "width": 170}, "leader": {"type": "text", "width": 300},
    "runner_up_x": N("× floor", 2, width=110, derived="the second-best model's headline on this actuator"),
    "twin_grade": {"type": "text", "width": 100, "display": "badge", "colors": {"yes": 3, "no": 8}},
    "bench": {"type": "text", "width": 190}, "bench_order": {"type": "number", "hidden": True},
    "test": {"type": "text", "width": 110}, "test_order": {"type": "number", "hidden": True}, "run": {"type": "text", "width": 300},
    "q_rms_mrad": N("mrad", 2, width=110, better="lower"), "x_floor": N("× floor", 2, width=100, better="lower", derived="q RMS / this actuator's floor"),
    "term": {"type": "text", "width": 150}, "term_note": {"type": "text", "width": 360},
    "delta_mrad": N("mrad", 3, width=130, values="delta_runs"), "delta_runs": {"type": "list", "hidden": True},
    "delta_x": N("× floor", 2, width=110, derived="delta / this actuator's floor"),
    "description": {"type": "text", "display": "markdown", "width": 320}, "readme": {"type": "text", "display": "markdown", "width": 320},
    "code_commit": {"type": "text", "width": 260}, "code_path": {"type": "text", "width": 320}, "code_hosted": {"type": "text", "width": 220},
    "code_url": {"type": "text", "display": "link", "width": 220}, "page": {"type": "text", "hidden": True},
}
for col, (_t, unit, dec) in TERM_COLUMNS.items():
    props[col] = N(unit, dec, width=185)  # WHY wide: a cell carries value, 95 % CI and basis mark
data = {
    "id": "robotparts-models", "title": "Actuator models × benches (BAM rack)", "titleProperty": "variant",
    "source": "BAM rack analysis, /archive/datasets/bam_rig (budget Oct 23, dataset Oct 24/25, floors, model cards); naming: robotparts lane/datasheet @ ec9a13c",
    "properties": props,
    # WHY no actuator or model here: the peek's title already names them, and a narrow peek must fit the run's numbers
    "records": {"columns": [{"id": "bench", "label": "Bench"}, {"id": "test", "label": "Test"}, {"id": "run", "label": "Run"},
                            {"id": "q_rms_mrad", "label": "q RMS (mrad)"}, {"id": "x_floor", "label": "× floor"}]},
    "rows": all_rows,
}
out = HERE / "models.json"
out.write_text(json.dumps(public(data), ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
print(f"{out.name}: {len(models)} model rows, {len(rows)} run rows, {len(terms_out)} term rows, {out.stat().st_size:,} bytes")
for can, (v, x, n) in summary.items():
    print(f"  CAN {can}: {n} models, best {v} at {x} x floor")
