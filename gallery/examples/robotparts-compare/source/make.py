"""Write compare.json and the photos of the robotparts-compare case from robotparts' own catalog.

    python3 gallery/examples/robotparts-compare/source/make.py      # ROBOTPARTS=~/robotparts by default

Six actuators of the one class people cross-shop (integrated, 6-10:1, 0.15-0.4 kg), each with a robotparts-hosted
photo: the four the compare view opens on, and two more to add. Values are the catalog's own (spec + unit + source
kind), read through robotparts' build helpers (build/site_pages.py: names, URLs, price from); each spec is converted
from its own unit, never by a fixed factor (gallery/tools/build_examples.py, UNIT_SCALE). The photos are robotparts'
own copies (dist/site/v2/files/<sha256>.webp), copied beside the case so nothing loads from another origin.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE.parent
ROBOTPARTS = pathlib.Path(os.environ.get("ROBOTPARTS", "~/robotparts"))
ORIGIN = "https://robotparts.dev"
IDS = ["aifitlab-8541438771336", "aifitlab-8542347853960", "aifitlab-8682672160904", "aifitlab-8649843966088",
       "aifitlab-8542620287112", "aifitlab-8682649092232"]

COLUMNS = [  # canonical key -> (property, column unit, label, better)
    ("peak_torque", "peak_torque", "N·m", "Peak torque", "higher"), ("rated_torque", "rated_torque", "N·m", "Rated torque", "higher"),
    ("max_output_speed", "max_speed", "rpm", "Max speed", "higher"), ("rated_speed", "rated_speed", "rpm", "Rated speed", "higher"),
    ("mass", "mass", "g", "Mass", "lower"), ("gear_ratio", "gear_ratio", ":1", "Gear ratio", None),
    ("nominal_voltage", "voltage", "V", "Voltage", None), ("backlash", "backlash", "arcmin", "Backlash", "lower"),
    ("outer_diameter", "od", "mm", "Outer diameter", "lower"), ("axial_length", "length", "mm", "Length", "lower"),
    ("rated_power", "rated_power", "W", "Rated power", "higher"),
]
UNIT_SCALE = {("kg", "g"): 1000.0, ("g", "g"): 1.0, ("N·m", "N·m"): 1.0, ("rpm", "rpm"): 1.0, (":1", ":1"): 1.0, ("", ":1"): 1.0,
              ("V", "V"): 1.0, ("mm", "mm"): 1.0, ("arcmin", "arcmin"): 1.0, ("W", "W"): 1.0}
BASIS = {"manufacturer": "datasheet", "distributor": "seller", "retailer": "seller", "aifitlab-text": "seller",
         "aifitlab-image-transcribed": "seller", "measured": "measured", "derived": "derived"}


def convert(spec: dict, unit: str):
    v = spec.get("value")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    scale = UNIT_SCALE.get((spec.get("unit") or "", unit))
    if scale is None:
        raise ValueError(f"no conversion from {spec.get('unit')!r} to {unit!r}")
    return round(v * scale, 6)


def main() -> None:
    sys.path.insert(0, str(ROBOTPARTS / "build"))
    import site_pages as sp  # noqa: E402  robotparts' catalog reader and helpers

    site = sp.Site(ROBOTPARTS / "dist" / "site", ROBOTPARTS / "schemas" / "registry.json")
    by_id = {r["id"]: r for r in site.catalog["parts"]}
    (CASE / "photos").mkdir(exist_ok=True)
    for old in (CASE / "photos").glob("*.webp"):
        old.unlink()
    rows = []
    for pid in IDS:
        rec = by_id[pid]
        photo = next(im["url"].rsplit("/", 1)[1] for im in rec["views"]["images"] if "/v2/files/" in im["url"])
        name = f"photos/{pid}.webp"  # relative to compare.json (docs/CONTRACT.md §1, amendment 2026-10-26)
        shutil.copyfile(ROBOTPARTS / "dist" / "site" / "v2" / "files" / photo, CASE / name)
        row = {"id": pid, "name": sp.name_of(rec), "brand": rec.get("brand"), "model": rec.get("model"), "photo": name,
               "url": ORIGIN + sp.canonical_url(rec), "level": rec["level"], "drivetrain": (rec.get("drivetrain") or {}).get("value"),
               "buses": rec.get("buses") or []}
        for key, prop, unit, _label, _better in COLUMNS:
            spec_key = rec["canonical"].get(key)
            s = rec["specs"].get(spec_key) if spec_key else None
            v = convert(s, unit) if s else None
            row[prop] = None if v is None else {"value": v, "basis": BASIS.get(s.get("source_kind"), "seller"),
                                                "source": sp.host_of(s.get("source_url")) or None, "note": s.get("note") or None}
        dens = rec["specs"].get("peak_nm_per_kg")
        row["torque_density"] = dens["value"] if dens and isinstance(dens.get("value"), (int, float)) else None
        row["price"] = sp.price_from(site, rec)
        row["sellers"] = len({li["seller"] for li in rec.get("listings") or []}) or None
        row["measured"] = len([m for m in rec.get("measured") or [] if not m.get("superseded")]) or None
        for check in ("cited", "cad", "sim"):
            row[check] = bool(rec["checks"].get(check))
        rows.append(row)
    props = {"name": {"type": "text", "label": "Part"}, "brand": {"type": "text", "label": "Brand"}, "model": {"type": "text", "label": "Model"},
             "photo": {"type": "text", "label": "Photo", "display": "image", "media": "image", "hidden": True},
             "url": {"type": "text", "label": "Page", "hidden": True},
             "level": {"type": "number", "label": "Level", "better": "higher", "note": "robotparts' level: listed, cited, CAD, sim, measured (0-5)"},
             "drivetrain": {"type": "text", "label": "Drivetrain", "display": "badge"}, "buses": {"type": "list", "label": "Bus"}}
    for _key, prop, unit, label, better in COLUMNS:
        props[prop] = {"type": "number", "label": label, "unitText": unit, **({"better": better} if better else {})}
    props["torque_density"] = {"type": "number", "label": "Peak torque / mass", "unitText": "N·m/kg", "better": "higher", "derived": "peak torque / mass, by robotparts"}
    props["price"] = {"type": "number", "label": "Price from", "unitText": "USD", "decimals": 0, "better": "lower", "note": "the lowest price of a listing selling the part alone"}
    props["sellers"] = {"type": "number", "label": "Sellers"}
    props["measured"] = {"type": "number", "label": "Measured records", "better": "higher"}
    for check, label in (("cited", "Datasheet cited"), ("cad", "CAD model"), ("sim", "Sim model")):
        props[check] = {"type": "boolean", "label": label}
    data = {"id": "robotparts-compare", "title": "Actuators side by side", "titleProperty": "name", "linkProperty": "url", "imageProperty": "photo",
            "source": f"robotparts dist/site/v2/catalog.json, release {site.catalog['release']}; photos from dist/site/v2/files/",
            "properties": props, "rows": rows}
    (CASE / "compare.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"compare.json: {len(rows)} rows; photos: {', '.join(r['photo'] for r in rows)}")


if __name__ == "__main__":
    main()
