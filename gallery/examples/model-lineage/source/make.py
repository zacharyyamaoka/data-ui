"""Rebuild ladder.json: the GIM4305-10 actuator model ladder (M0 -> M5) as rows with authored parents.

    python3 -I gallery/examples/model-lineage/source/make.py

The models and their runs are the models-benches case's own rows (../../models-benches/models.json, robotparts
lane/datasheet @ ec9a13c), one row per model variant here, with its run count and median q RMS. `parents` is written
by hand in PARENTS below, each with the sentence that says so, from robotparts lane/datasheet
docs/proposals/models-2026-10-25.md ("Rung k adds a layer of physics", its actuator ladder table, and line 274's
terms for M4.ripple). A model whose base the proposal never names (M5.dcmotor) has no parent: no edge is guessed."""

import json
import pathlib
import statistics

HERE = pathlib.Path(__file__).resolve().parent.parent
SRC = HERE.parent / "models-benches" / "models.json"
DOC = "robotparts lane/datasheet docs/proposals/models-2026-10-25.md"

IDS = {
    "M0.ideal": "m0-ideal", "M1.datasheet": "m1-datasheet", "M2.coulomb_viscous": "m2-coulomb-viscous",
    "M3.stribeck": "m3-stribeck", "M3.load": "m3-load", "M3.capture": "m3-capture", "M3.lugre": "m3-lugre",
    "M4.ripple (ideal driver)": "m4-ripple", "M4.ripple (moteus-c1 driver twin)": "m4-ripple-c1",
    "M4.ripple (c1, soft friction)": "m4-ripple-c1-soft", "M5.dcmotor": "m5-dcmotor",
}
# id -> ([parents], why). The first parent is the tree parent; a second one is a splice.
PARENTS = {
    "m0-ideal": ([], "heads every ladder as the ablation baseline"),
    "m1-datasheet": (["m0-ideal"], "M1 adds the stated values (Kt, any stated friction and backlash) to M0's gear ratio and inertia"),
    "m2-coulomb-viscous": (["m1-datasheet"], "M2 adds fitted constant friction: Coulomb, viscous"),
    "m3-stribeck": (["m2-coulomb-viscous"], "stribeck: + breakaway, Stribeck speed (on M2's Coulomb + viscous)"),
    "m3-load": (["m2-coulomb-viscous"], "load: + load coefficient (Coulomb + viscous + load)"),
    "m3-capture": (["m2-coulomb-viscous"], "capture: + capture level, speed, dwell (Coulomb + viscous + capture)"),
    "m3-lugre": (["m2-coulomb-viscous"], "lugre: + bristle state σ0, σ1, σ2"),
    "m4-ripple": (["m3-stribeck"], "line 274: M4.ripple = Coulomb + Stribeck-like weakening + cogging map + backlash"),
    "m4-ripple-c1": (["m4-ripple"], "the same model, with the moteus-c1 driver's current loop as run"),
    "m4-ripple-c1-soft": (["m4-ripple-c1", "m2-coulomb-viscous"], "the c1 twin, on MuJoCo's default soft friction (M2's backend): a splice"),
    "m5-dcmotor": ([], "M5 adds the motor's R, L and heat; the proposal names no base model, so none is drawn"),
}


def main() -> None:
    src = json.loads(SRC.read_text(encoding="utf-8"))
    by = {}
    for r in src["rows"]:
        by.setdefault(r["variant"], []).append(r)
    rows = []
    for variant, runs in sorted(by.items(), key=lambda kv: kv[1][0]["model_order"]):
        first = runs[0]
        rid = IDS[variant]
        parents, why = PARENTS[rid]
        q = [r["q_rms_mrad"] for r in runs if r["q_rms_mrad"] is not None]
        rows.append({
            "id": rid,
            "variant": variant,
            "rung": int(first["rung"].lstrip("M")),
            "rung_name": first["rung"],
            "family": first["family"],
            "backend": first["backend"],
            "about": first["about"],
            "runs": len(q),
            "q_rms_median": round(statistics.median(q), 3) if q else {"value": None, "why": "no run on the bench yet"},
            "status": "measured" if q else "no runs",
            "parents": parents,
            "parents_why": why,
        })
    out = {
        "id": "model-lineage",
        "title": "GIM4305-10 actuator model ladder",
        "titleProperty": "variant",
        "source": f"models-benches/models.json (robotparts lane/datasheet @ ec9a13c); parents from {DOC}",
        "properties": {
            "variant": {"type": "text", "width": 240},
            "rung": {"type": "number", "width": 60, "note": "how much physics the model captures (M0-M5)"},
            "rung_name": {"type": "text", "width": 60},
            "family": {"type": "text", "width": 230},
            "backend": {"type": "text", "width": 250},
            "about": {"type": "text", "width": 260},
            "runs": {"type": "number", "width": 60},
            "q_rms_median": {"type": "number", "unitText": "mrad", "decimals": 2, "width": 110, "better": "lower"},
            "status": {"type": "text", "width": 90, "display": "badge", "colors": {"measured": 1, "no runs": 0}},
            "parents": {"type": "list", "width": 200, "relation": True, "note": "the model this one adds physics to; two = a splice"},
            "parents_why": {"type": "text", "width": 320, "note": f"the sentence in {DOC} that names the parent"},
        },
        "rows": rows,
    }
    (HERE / "ladder.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(rows)} models, {sum(r['status'] == 'measured' for r in rows)} measured")


if __name__ == "__main__":
    main()
