"""Write headline.json: kpis.json's rungs with the factory and oracle numbers beside each, for the dashboard's tiles.

    python3 -I gallery/examples/pid-tuning/source/build_headline.py

Input (read-only): kpis.json beside this folder (written by build_replay.py). A KPI tile's delta is against a property
of the same row (`compare.against`), and kpis.json has one row per rung, so this copies the factory's and the oracle's
cells onto every row. Nothing is recomputed: every cell is kpis.json's own, with its `source` saying which row it came
from. Sim, like kpis.json (basis derived, note sim).
"""

from __future__ import annotations

import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "tools"))  # parents[3] is gallery/
from public_paths import public  # noqa: E402  (judge r2 #6: no absolute home path in what the site publishes)
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parents[1]
KEYS = ("stop_p90", "tracking_rms")
BESIDE = ("factory", "oracle")


def main() -> None:
    kpis = json.loads((HERE / "kpis.json").read_text(encoding="utf-8"))
    by = {r["situation"]: r for r in kpis["rows"]}

    def copied(rung: str, key: str) -> dict:
        cell = dict(by[rung][key])
        cell["source"] = f"kpis.json rows[situation={rung}].{key}, as written ({cell.get('source', '')})"
        return cell

    rows = []
    for r in sorted(kpis["rows"], key=lambda r: r["order"]):
        row = {"id": r["id"], "situation": r["situation"], "title": r["title"], "order": r["order"]}
        for key in KEYS:
            row[key] = copied(r["situation"], key)
            for other in BESIDE:
                row[f"{other}_{key}"] = copied(other, key)
        rows.append(row)

    props = {
        "situation": kpis["properties"]["situation"],
        "title": kpis["properties"]["title"],
        "order": kpis["properties"]["order"],
    }
    for key in KEYS:
        props[key] = dict(kpis["properties"][key])
        for other in BESIDE:
            props[f"{other}_{key}"] = {"type": "number", "unit": "mrad",
                                       "note": f"The {other} rung's {props[key]['note'][0].lower()}{props[key]['note'][1:]} Copied from kpis.json's {other} row onto every row, so a tile can compare against it."}
    out = {
        "id": "pid-tuning-ur5e-headline",
        "title": "UR5e · each rung's worst-joint scores beside the factory's and the oracle's (sim)",
        "titleProperty": "title",
        "source": f"kpis.json (this case; {kpis['source']}), copied by source/build_headline.py: no number recomputed.",
        "properties": props,
        "rows": rows,
    }
    path = HERE / "headline.json"
    path.write_text(json.dumps(public(out), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{path.name}: {len(rows)} rows, {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
