"""Build rack.json (rows + edges) from robotparts' Splice proof of the 1-DOF rack. Read-only on robotparts.

    python3 gallery/examples/rack-wiring/source/build.py

Nodes are the parts: Splice's seven nodes (rack.splice.json), the two motors the boards drive and the D405 camera
(rack-analysis.json `rack`). Edges are wires: each row's `feeds` lists the ids its wires go to, and `wire` (a list in
the same order) says what each wire carries. Splice's cables give power and CAN; a board -> motor edge is the board's
phase wires, from `rack.motors`. The D405 has no edge: no cable to it is recorded, and none is invented.
Voltages, currents and findings are Splice's own results (continuous scenario), copied, never recomputed.
"""

from __future__ import annotations

import json
import pathlib

RACK = pathlib.Path("~/robotparts/reports/media/rack")
CATALOG = pathlib.Path("~/robotparts/dist/site/v2/catalog.json")
OUT = pathlib.Path(__file__).resolve().parents[1] / "rack.json"

ROLE = {"psu": "Power", "clamp": "Power", "xt30_junction": "Power", "fdcanusb": "CAN", "ph3_junction": "CAN",
        "r4_11": "Boards", "c1": "Boards"}
WIRE = {"power": "power", "can": "CAN"}


def main() -> None:
    splice = json.loads((RACK / "rack.splice.json").read_text())
    analysis = json.loads((RACK / "rack-analysis.json").read_text())
    catalog = {p["id"]: p for p in json.loads(CATALOG.read_text())["parts"]}
    engine = f"Splice engine @ {analysis['splice']['commit'][:8]} (rack-analysis.json)"
    scenario = next(s for s in analysis["scenarios"] if s["scenario"] == "continuous")
    continuous, supplies = scenario["nodes"], scenario["psus"]
    custom = {p["id"]: p for p in splice["customParts"]}

    def part(pid):
        p = catalog.get(pid, {})
        return {"part": pid, "maker": p.get("brand"), "model": p.get("model"), "category": p.get("category"),
                "url": f"https://robotparts.dev/{p['category']}/{pid}/" if p.get("category") else None}

    rows = []
    for n in splice["nodes"]:
        cp = custom[n["part"]]
        res = continuous.get(n["id"], {})
        amps = res.get("loadA") or res.get("throughA") or supplies.get(n["id"], {}).get("currentA")
        findings = [f"{f['severity']}: {f['message']}" for f in analysis["findings"] if f.get("target") == f"node:{n['id']}"]
        rows.append({
            "id": n["id"], "name": n["label"], "role": ROLE[n["id"]], "kind": cp["kind"], **part(n["part"]),
            "ports": [f"{p['id']} ({p['kind']}, {p.get('connector') or 'no connector'})" for p in cp["ports"]],
            "v_load": {"value": round(res["vLoad"], 2), "basis": "derived", "source": engine, "note": "continuous scenario"} if res.get("vLoad") else {"value": None, "why": "not on the power path"},
            "current": {"value": round(amps, 2), "basis": "derived", "source": engine, "note": "continuous scenario: load, pass-through or supply current"} if amps else {"value": None, "why": "carries no supply current"},
            "findings": findings, "feeds": [], "wire": [], "cables": [],
        })
    by_id = {r["id"]: r for r in rows}
    for c in splice["cables"]:
        src = by_id[c["from"]["node"]]
        src["feeds"].append(c["to"]["node"])
        src["wire"].append(WIRE[c["kind"]])
        src["cables"].append(f"{c['id']}: {c['from']['port']} -> {c['to']['node']}.{c['to']['port']}, {c['awg']} AWG, {c['lengthM']} m{' twisted' if c.get('twisted') else ''} (assumed)")

    rack = analysis["rack"]
    for board, motor in rack["motors"].items():
        mid = f"motor_{board}"
        p = part(motor)
        rows.append({"id": mid, "name": f"{p['maker']} {p['model']}", "role": "Motors", "kind": "motor", **p, "ports": [],
                     "v_load": {"value": None, "why": "after the board"}, "current": {"value": None, "why": "not in Splice's model"},
                     "findings": [], "feeds": [], "wire": [], "cables": []})
        by_id[board]["feeds"].append(mid)
        by_id[board]["wire"].append("phases")
        by_id[board]["cables"].append(f"phases -> {mid} (rack-analysis.json rack.motors)")
    cam = part(rack["camera"])
    rows.append({"id": "d405", "name": f"{cam['maker']} {cam['model']}", "role": "Sensing", "kind": "camera", **cam, "ports": [],
                 "v_load": {"value": None, "why": "USB powered; no cable recorded"}, "current": {"value": None, "why": "not in Splice's model"},
                 "findings": [], "feeds": [], "wire": [], "cables": []})

    out = {
        "id": "rack-wiring", "title": "1-DOF rack wiring", "titleProperty": "name", "linkProperty": "url",
        "source": f"robotparts reports/media/rack/rack.splice.json + rack-analysis.json (release {analysis['robotparts']['release']}, {engine})",
        "properties": {
            "name": {"type": "text", "label": "Part", "width": 240},
            "role": {"type": "text", "label": "Role", "display": "badge", "colors": {"Power": 8, "CAN": 1, "Boards": 7, "Motors": 4, "Sensing": 3}},
            "kind": {"type": "text", "label": "Kind"},
            "maker": {"type": "text", "label": "Maker"},
            "model": {"type": "text", "label": "Model"},
            "category": {"type": "text", "label": "Category", "hidden": True},
            "part": {"type": "text", "label": "robotparts id", "hidden": True},
            "url": {"type": "text", "label": "robotparts.dev", "hidden": True},
            "ports": {"type": "list", "label": "Ports"},
            "v_load": {"type": "number", "label": "V at load", "unitText": "V", "decimals": 2},
            "current": {"type": "number", "label": "Current", "unitText": "A", "decimals": 2},
            "findings": {"type": "list", "label": "Splice findings"},
            "feeds": {"type": "list", "label": "Wires to", "readOnly": True},
            "wire": {"type": "list", "label": "Carries", "colors": {"power": 8, "CAN": 1, "phases": 4}, "readOnly": True},
            "cables": {"type": "list", "label": "Cables"},
        },
        "rows": rows,
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(rows)} parts, {sum(len(r['feeds']) for r in rows)} wires")


if __name__ == "__main__":
    main()
