"""Build blocks.json (rows + edges) from one SystemSketch board: communication-projection-prototype. Read-only.

    python3 gallery/examples/systemsketch-blocks/source/build.py

A block is a row (its title, block type, input and output ports); a SystemSketch connection is an edge, named by the
output port it leaves from. Each row's `sends_to` lists the blocks its connections go to and `via` (a list in the same
order) names the port, so two blocks joined by three connections keep three edges. Value blocks (a constant feeding
a port) have no title on the board; they take their output port's name, marked "(value)".
"""

from __future__ import annotations

import json
import pathlib

BOARD = pathlib.Path("~/systemsketch/sketches/review/communication-projection-prototype.systemsketch")
OUT = pathlib.Path(__file__).resolve().parents[1] / "blocks.json"


def main() -> None:
    records = json.loads(BOARD.read_text())["records"]
    blocks = [r for r in records if r.get("typeName") == "shape" and r.get("type") == "block"]
    rows, by_shape = [], {}
    for b in blocks:
        p = b["props"]
        inputs, outputs = p.get("inputs") or [], p.get("outputs") or []
        is_value = p.get("view") == "value"
        title = p.get("title") or (f"{outputs[0]['name']} (value)" if outputs else b["id"])
        row = {
            "id": b["id"].removeprefix("shape:"), "block": title, "kind": "value" if is_value else (p.get("blockType") or "component"),
            "inputs": [f"{x['name']}: {x['type']}" for x in inputs], "outputs": [f"{x['name']}: {x['type']}" for x in outputs],
            "n_in": len(inputs), "n_out": len(outputs), "definition": p.get("definitionKey"),
            "sends_to": [], "via": [],
        }
        rows.append(row)
        by_shape[b["id"]] = (row, {x["id"]: x["name"] for x in outputs})
    # a connection shape has two bindings: its start (an output port) and its end (an input port)
    ends: dict[str, dict] = {}
    for r in records:
        if r.get("typeName") == "binding" and r.get("type") == "connection":
            ends.setdefault(r["fromId"], {})[r["props"]["terminal"]] = (r["toId"], r["props"]["portId"])
    for edge, e in sorted(ends.items()):
        (src, port), (dst, _in) = e["start"], e["end"]
        row, names = by_shape[src]
        row["sends_to"].append(by_shape[dst][0]["id"])
        row["via"].append(names.get(port, port))
    out = {
        "id": "systemsketch-blocks", "title": "SystemSketch blocks", "titleProperty": "block",
        "source": f"systemsketch {BOARD.relative_to('~/systemsketch')} (Block-Ports-Edges)",
        "properties": {
            "block": {"type": "text", "label": "Block", "width": 200},
            "kind": {"type": "text", "label": "Block type", "display": "badge"},
            "inputs": {"type": "list", "label": "Inputs"},
            "outputs": {"type": "list", "label": "Outputs"},
            "n_in": {"type": "number", "label": "In ports"},
            "n_out": {"type": "number", "label": "Out ports"},
            "definition": {"type": "text", "label": "Definition"},
            "sends_to": {"type": "list", "label": "Sends to", "readOnly": True},
            "via": {"type": "list", "label": "Via port", "readOnly": True},
        },
        "rows": rows,
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(rows)} blocks, {sum(len(r['sends_to']) for r in rows)} connections")


if __name__ == "__main__":
    main()
