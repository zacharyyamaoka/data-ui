"""Write the data files of the two robotparts gallery examples from robotparts' own data.

    python3 gallery/tools/build_examples.py            # rewrites gallery/examples/*/{actuators,datasheet}.json
                                                       # and robotparts-actuators/photos/

Moved from robotparts lane/tables @ ab5ba92 (design/tables-2026-10-25/build_prototypes.py), keeping its readers and
fixing two things it got wrong:
- actuator mass: the lane multiplied every mass by 1,000, assuming kilograms (its ACT_COLUMNS, line 127). One
  record's canonical mass is the spec `mass` in grams, so CubeMars AKE40-6 KV90 read 140,000 g. Each spec is now
  converted from its own unit (UNIT_SCALE), never by a fixed factor: AKE40-6 KV90 reads 140 g.
- CAN 14's torque values: the datasheet snapshot carries the values published on 2026-10-21, read while that
  board's Kv was a stale 199.78 (true 162.56), so torque read 1/1.229 of true. robotparts' correction record
  (parts/aifitlab-8541438771336/measured/2026-10-25-bam-kt-correction.json) supersedes them: coulomb friction
  0.0551 N·m (was 0.0448), torque ripple 25.8 / 12.3 / 11.1 mN·m at k14 / k28 / k24 (were 21 / 10 / 9).

Inputs (read-only): the datasheet snapshot in gallery/examples/gim4305-datasheet/source/ (committed), and for the
actuators robotparts' catalog and build helpers (ROBOTPARTS, default the lane/tables checkout) and its media index
(ROBOTPARTS_MEDIA, default ~/robotparts/media: photos.jsonl + files/<sha>.webp). The committed JSON is what
the gallery and its tests read, so the gallery builds without robotparts on disk.
The actuators' `photo` column (moved here from the actuator-charts case's own copy of these rows, 2026-10-26): at
most PHOTOS primary photos, each resized to WIDTH px, so the case stays small; a part without one has `photo: null`.
Photos are hosted on robotparts.dev on the owner's basis (photos.jsonl `owner_note`). WHY here and not a join in
the .base file: a column the data needs belongs in the data's producer; the chart case then reads these rows.
WHY committed data: a gallery case is a test fixture; its rows are public catalog data (no private track figures).
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
EXAMPLES = HERE.parent / "examples"
ROBOTPARTS = pathlib.Path(os.environ.get("ROBOTPARTS", "~/robotparts/.claude/worktrees/lane-tables"))
MEDIA = pathlib.Path(os.environ.get("ROBOTPARTS_MEDIA", "~/robotparts/media"))
ORIGIN = "https://robotparts.dev"
PHOTOS = 150
WIDTH = 240


def load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: pathlib.Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{path.relative_to(EXAMPLES.parent.parent)}: {len(data['rows'])} rows, {path.stat().st_size:,} bytes")


# ------------------------------------------------------------------------------------------------- the datasheet

RUNG = {"datasheet": "M1.datasheet", "coulomb_viscous": "M2.coulomb_viscous", "stribeck": "M3.stribeck",
        "load_dependent": "M3.load", "lugre": "M3.lugre", "ripple_map": "M4.ripple", "mujoco_dcmotor": "M5.dcmotor"}
COLUMN_KIND = {"ds": "datasheet", "board": "board", "meas": "measured", "der": "derived"}

# CAN 14's corrected torque values (robotparts 2026-10-25-bam-kt-correction.json), keyed by (field, published text)
KT = 199.78 / 162.56
CORRECTED = {
    ("coulomb_friction", "0.0448"): ("0.0551", 0.0551),
    ("torque_ripple", "k14: 21"): ("k14: 25.8", 25.8),
    ("torque_ripple", "k28: 10"): ("k28: 12.3", 12.3),
    ("torque_ripple", "k24: 9"): ("k24: 11.1", 11.1),
}
CORRECTION_NOTE = (f"Corrected 2026-10-25: same runs, torque x {KT:.3f}; the board's Kv was a stale 199.78 when they "
                   "were logged (recalibrated to 162.56 on 2026-10-23). Supersedes the {was} published on 2026-10-21.")
# lane hue index -> data-ui badge slot: 0 muted, 1-8 = --data-series-1..8 (blue orange aqua yellow magenta green violet red)
STATUS_HUE = {"measured": 6, "board": 1, "datasheet": 0, "derived": 7, "partial": 2, "pending": 4, "refused": 8, "missing": 0, "candidate": 3}


def strip_unit(text: str, unit: str) -> str:
    """'140.0 g' -> '140.0' when the field's unit is g: the unit lives in its own column (or is put back inline)."""
    if unit and text.endswith(unit):
        return text[: -len(unit)].rstrip()
    return text


def as_number(text: str):
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def correct(row: dict) -> dict:
    """Apply CAN 14's Kt correction to the snapshot's superseded entries, saying so on each."""
    fixed = 0
    for x in row["meas"]:
        hit = CORRECTED.get((row["key"], x["text"])) if str(x.get("can")) == "14" else None
        if hit:
            was = x["text"]
            x["text"], x["n"] = hit
            x["how"] = (x.get("how") or "") + (" " if x.get("how") else "") + CORRECTION_NOTE.format(was=f"{was} {row['unit']}")
            x["date"] = "2026-10-25"
            fixed += 1
    return {**row, "_fixed": fixed}


def datasheet() -> dict:
    snap = load(EXAMPLES / "gim4305-datasheet" / "source" / "gim4305-10-rows.json")
    rows = []
    fixed = 0
    for order, r in enumerate(snap["rows"]):
        r = correct(r)
        fixed += r["_fixed"]
        unit = r["unit"]
        ds = [strip_unit(x["text"], unit) for x in r["ds"]]
        nominal = None
        if ds:
            nominal = next((x["n"] for x in r["ds"] if x["n"] is not None and as_number(strip_unit(x["text"], unit)) is not None), None)
            nominal = nominal if nominal is not None and len(ds) == 1 else " · ".join(ds)
        stats = r["stats"]
        measured = stats["median"] if stats else (" · ".join(x["text"] for x in r["meas"]) or None)
        delta = None
        if isinstance(nominal, float) and stats and nominal:
            delta = 100.0 * (stats["median"] - nominal) / nominal
        entries = []
        for part in ("ds", "board", "meas", "der"):
            for x in r[part]:
                entries.append({"column": COLUMN_KIND[part], "status": x["status"], "value": x["text"],
                                "specimen": (f"CAN {x['can']} · {x['unit']}" if x.get("can") else ""), "date": x["date"],
                                "source": x["src"], "url": x["url"], "method": x["how"],
                                "ci95": f"[{x['ci'][0]:.4g}, {x['ci'][1]:.4g}]" if x.get("ci") else ""})
        m2 = "required" if "coulomb_viscous" in r["req"] else "optional" if "coulomb_viscous" in r["feeds"] else None
        rows.append({
            "id": r["key"], "field": r["label"], "section": r["sec"], "order": order,
            "nominal": nominal, "measured": measured, "measured_values": stats["values"] if stats else [],
            "board": " · ".join(strip_unit(x["text"], unit) for x in r["board"]) or None,
            "derived": " · ".join(strip_unit(x["text"], unit) for x in r["der"]) or None,
            "unit": unit or None, "delta": delta, "status": r["status"], "n": len(entries),
            "sources": r["sources"], "specimens": sorted({f"CAN {x['can']}" for p in ("board", "meas") for x in r[p] if x.get("can")}),
            "latest": max((x["date"] for x in entries if x["date"]), default=None),
            "m2": m2, "models": [RUNG[k] for k in r["feeds"] if k in RUNG], "bench": r["bench"], "_detail": entries,
        })
    assert fixed == len(CORRECTED), f"expected to correct {len(CORRECTED)} CAN 14 entries, corrected {fixed}"
    return {
        "id": "gim4305-10-datasheet", "title": "SteadyWin GIM4305-10 datasheet", "titleProperty": "field",
        "source": snap["from"] + "; CAN 14 torque corrected per robotparts 2026-10-25-bam-kt-correction.json",
        "properties": {
            "field": {"type": "text", "width": 230}, "section": {"type": "text", "width": 160},
            "nominal": {"type": "number", "unit": "unit", "align": "left", "width": 150},
            "measured": {"type": "number", "unit": "unit", "values": "measured_values", "align": "left", "width": 170},
            "board": {"type": "text", "unit": "unit", "width": 190}, "derived": {"type": "text", "unit": "unit", "width": 150},
            "unit": {"type": "text", "width": 84}, "delta": {"type": "number", "unitText": "%", "decimals": 1, "width": 110},
            "status": {"type": "text", "display": "badge", "colors": STATUS_HUE, "width": 96},
            "n": {"type": "number", "width": 52}, "sources": {"type": "list", "width": 210},
            "specimens": {"type": "list", "width": 120}, "latest": {"type": "text", "width": 100},
            "m2": {"type": "text", "display": "badge", "colors": {"required": 8, "optional": 0}, "width": 96},
            "models": {"type": "list", "width": 260}, "bench": {"type": "text", "width": 300},
            "order": {"type": "number", "hidden": True}, "measured_values": {"type": "list", "hidden": True},
        },
        "detail": {"property": "_detail", "kind": "column", "columnKinds": {"nominal": "datasheet", "measured": "measured", "board": "board", "derived": "derived"},
                   "columns": [{"id": "column", "label": "Column"}, {"id": "value", "label": "Value"}, {"id": "specimen", "label": "Unit"},
                               {"id": "date", "label": "Date"}, {"id": "ci95", "label": "95% CI"}, {"id": "status", "label": "Status"},
                               {"id": "source", "label": "Source", "link": "url", "block": True}, {"id": "method", "label": "Method", "block": True}]},
        "rows": rows,
    }


# ------------------------------------------------------------------------------------------------- actuators

ACT_COLUMNS = [  # canonical key -> (property, the unit the column is in)
    ("peak_torque", "peak_torque", "N·m"), ("rated_torque", "rated_torque", "N·m"), ("max_output_speed", "max_speed", "rpm"),
    ("mass", "mass", "g"), ("gear_ratio", "gear_ratio", ":1"), ("nominal_voltage", "voltage", "V"),
    ("outer_diameter", "od", "mm"), ("axial_length", "length", "mm"),
]
# WHY a table of units and not a factor: the catalog states each spec in its own unit (1,067 masses in kg, one in g)
UNIT_SCALE = {("kg", "g"): 1000.0, ("g", "g"): 1.0, ("N·m", "N·m"): 1.0, ("mN·m", "N·m"): 0.001, ("rpm", "rpm"): 1.0,
              (":1", ":1"): 1.0, ("", ":1"): 1.0, ("V", "V"): 1.0, ("mm", "mm"): 1.0, ("cm", "mm"): 10.0, ("m", "mm"): 1000.0}
RICH = {"peak_torque", "mass"}  # cells that carry their basis and source (SPEC §4.3), read by <data-value>
BASIS = {"manufacturer": "datasheet", "distributor": "seller", "retailer": "seller", "aifitlab-text": "seller",
         "aifitlab-image-transcribed": "seller", "measured": "measured", "derived": "derived"}
FORM = {"hobby_servo": "hobby servo", "integrated_actuator": "integrated actuator", "direct_drive": "direct drive",
        "bare_gearmotor": "bare gearmotor", "wheel_hub": "wheel hub"}


def convert(spec: dict, unit: str):
    v = spec.get("value")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    scale = UNIT_SCALE.get((spec.get("unit") or "", unit))
    if scale is None:
        raise ValueError(f"no conversion from {spec.get('unit')!r} to {unit!r}")
    return round(v * scale, 6)


def actuators() -> dict:
    sys.path.insert(0, str(ROBOTPARTS / "build"))
    import site_pages as sp  # noqa: E402  robotparts' own catalog reader and helpers (prices, names, URLs)

    site = sp.Site(ROBOTPARTS / "dist" / "site", ROBOTPARTS / "schemas" / "registry.json")
    rows = []
    for rec in site.catalog["parts"]:
        if rec["category"] != "actuator":
            continue
        row = {"id": rec["id"], "name": sp.name_of(rec), "brand": rec.get("brand") or None, "model": rec.get("model") or rec.get("title"),
               "form": FORM.get((rec.get("extras") or {}).get("category")), "drivetrain": (rec.get("drivetrain") or {}).get("value"),
               "buses": rec.get("buses") or [], "level": rec.get("level"), "url": ORIGIN + sp.canonical_url(rec)}
        for key, prop, unit in ACT_COLUMNS:
            spec_key = rec["canonical"].get(key)
            s = rec["specs"].get(spec_key) if spec_key else None
            v = convert(s, unit) if s else None
            if prop in RICH and v is not None:
                v = {"value": v, "basis": BASIS.get(s.get("source_kind"), "seller"), "source": sp.host_of(s.get("source_url")) or None}
            row[prop] = v
        dens = rec["specs"].get("peak_nm_per_kg")
        row["torque_density"] = dens["value"] if dens and isinstance(dens.get("value"), (int, float)) else None
        row["price"] = sp.price_from(site, rec)
        row["sellers"] = len({l["seller"] for l in rec.get("listings") or []}) or None
        rows.append(row)
    ake = next(r for r in rows if r["id"] == "cubemars-ake40-6-kv90")
    assert ake["mass"]["value"] == 140, f"AKE40-6 KV90 must weigh 140 g, reads {ake['mass']}"
    props = {"name": {"type": "text", "hidden": True}, "model": {"type": "text", "width": 190}, "brand": {"type": "text", "width": 120},
             "form": {"type": "text", "width": 140, "display": "badge"}, "drivetrain": {"type": "text", "width": 104},
             "buses": {"type": "list", "width": 120}, "level": {"type": "number", "width": 58}, "url": {"type": "text", "hidden": True},
             "torque_density": {"type": "number", "unitText": "N·m/kg", "width": 130, "derived": "peak torque / mass, by robotparts"},
             "price": {"type": "number", "unitText": "USD", "decimals": 0, "width": 120},
             "sellers": {"type": "number", "width": 70}}
    for _, prop, unit in ACT_COLUMNS:
        props[prop] = {"type": "number", "unitText": unit, "width": 126}
    return {"id": "actuators", "title": "Actuators", "titleProperty": "name", "linkProperty": "url",
            "source": f"robotparts dist/site/v2/catalog.json, release {site.catalog['release']} (lane/tables @ ab5ba92); mass from each spec's own unit",
            "properties": props, "rows": rows}


def with_photos(data: dict) -> dict:
    """Add the `photo` column and copy the photos it names into robotparts-actuators/photos/."""
    from PIL import Image  # only this step needs Pillow

    rows = data["rows"]
    photos: dict[str, dict] = {}
    for line in (MEDIA / "photos.jsonl").read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry.get("role") == "primary" and entry["part"] not in photos and (MEDIA / entry["file"].removeprefix("media/")).exists():
            photos[entry["part"]] = entry

    def num(cell):
        v = cell.get("value") if isinstance(cell, dict) else cell
        return v if isinstance(v, (int, float)) else None

    # the parts the charts draw (peak torque and mass both known), round-robin over brands so every brand's dots
    # have photos, best-documented first (level, then sellers)
    drawn = [r for r in rows if r["id"] in photos and num(r.get("peak_torque")) and num(r.get("mass"))]
    drawn.sort(key=lambda r: (-(r.get("level") or 0), -(r.get("sellers") or 0), r["id"]))
    by_brand: dict[str, list] = {}
    for r in drawn:
        by_brand.setdefault(r.get("brand") or "", []).append(r)
    chosen: list[str] = []
    while len(chosen) < PHOTOS and any(by_brand.values()):
        for brand in sorted(by_brand, key=lambda b: (-len(by_brand[b]), b)):
            if by_brand[brand] and len(chosen) < PHOTOS:
                chosen.append(by_brand[brand].pop(0)["id"])

    photos_dir = EXAMPLES / "robotparts-actuators" / "photos"
    photos_dir.mkdir(exist_ok=True)
    for old in photos_dir.glob("*.webp"):
        old.unlink()
    for part in chosen:
        image = Image.open(MEDIA / photos[part]["file"].removeprefix("media/")).convert("RGB")
        image.thumbnail((WIDTH, WIDTH))
        buffer = io.BytesIO()
        image.save(buffer, "WEBP", quality=72, method=6)
        (photos_dir / f"{part}.webp").write_bytes(buffer.getvalue())
    keep = set(chosen)
    for r in rows:
        r["photo"] = f"photos/{r['id']}.webp" if r["id"] in keep else None  # relative to actuators.json
    # step_up: a defined, derived edge for the graph view (never inferred by a view): among the photographed parts of
    # one brand, the next one up in peak torque (ties: the lighter first). The landing page's hero draws it.
    by_torque: dict[str, list] = {}
    for r in rows:
        if r["id"] in keep and num(r.get("peak_torque")):
            by_torque.setdefault(r.get("brand") or "", []).append(r)
    step_up: dict[str, str] = {}
    for brand_rows in by_torque.values():
        brand_rows.sort(key=lambda r: (num(r["peak_torque"]), num(r.get("mass")) or 0, r["id"]))
        for lower, upper in zip(brand_rows, brand_rows[1:]):
            step_up[lower["id"]] = upper["id"]
    for r in rows:
        r["step_up"] = step_up.get(r["id"])
    data["imageProperty"] = "photo"
    data["properties"]["photo"] = {"type": "text", "hidden": True, "display": "image",
                                   "note": "robotparts' primary photo, resized; only the parts this case copied have one"}
    data["properties"]["step_up"] = {"type": "text", "hidden": True, "derived": "the next photographed part of the same brand up in peak torque (build_examples.py)",
                                     "note": "an edge for the graph view: among the parts with a photo here, the brand's next one up in peak torque"}
    data["source"] += f"; photo: robotparts media/photos.jsonl, {len(chosen)} of {len(photos)} copied at {WIDTH} px"
    return data


def main() -> None:
    write(EXAMPLES / "gim4305-datasheet" / "datasheet.json", datasheet())
    if (ROBOTPARTS / "dist" / "site" / "v2" / "catalog.json").exists() and (MEDIA / "photos.jsonl").exists():
        write(EXAMPLES / "robotparts-actuators" / "actuators.json", with_photos(actuators()))
    else:
        print(f"skipped actuators: no robotparts catalog under {ROBOTPARTS} or media under {MEDIA} (set ROBOTPARTS, "
              "ROBOTPARTS_MEDIA); the committed file stays")


if __name__ == "__main__":
    main()
