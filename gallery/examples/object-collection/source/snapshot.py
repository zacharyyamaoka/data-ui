"""Write this case's data: the public-safe sample of BAM's object library (ObjectDB) for the grouped gallery.

    python3 gallery/examples/object-collection/source/snapshot.py

WHY a sample, not the library (2026-10-27): data-ui.dev is public, and the library's rows carry customer tags, customer
mixes and supplier research. This case holds only the 366 objects of the public sample that lane/object-db-public
(809e9b2, gallery/examples/object-db-shelf) vetted: 150 Google Scanned Objects (CC BY 4.0), 30 EGAD shapes
(BSD-3-Clause) and 186 of BAM's generated primitives. Their ids are `public_ids.txt` beside this file. The rebuild
fails closed: an id outside that list, a source outside SOURCES, or a missing id stops it, so a rebuild can never
widen the sample.

Input (read-only): OBJECTS (default ~/.cache/object-database/site/data/objects.json), ObjectDB site's exported
rows, joined by id for generic columns only: name, family, type_name, grade, size_class, bbox_volume_ml, mass_g (its
value), source, geometry and geometry_class. Nothing else is read: no tags, streams, mixes, customers, labellers,
licences, notes or page URLs. No thumbnails: the grouped gallery draws a monogram where a picture would be.

One derived column, `area`, exists only to show a second heading level where the data has one: "Medical" or "Food" for
a plastic, glass or paper object of that grade, null everywhere else (McMaster's "Fastening & Joining > Fasteners"
beside "Pipe, Tubing, Hose & Fittings" with no second layer). `labels` name a family, shape and source in words.

Rows are written families-by-size first (the biggest material first), so a level with no direction (the material
grouping) draws its biggest section first, as a catalogue does.
"""

from __future__ import annotations

import collections
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parents[1]
SOURCE = pathlib.Path(os.environ.get("OBJECTS", "~/.cache/object-database/site/data/objects.json"))
PUBLIC_IDS = pathlib.Path(__file__).resolve().parent / "public_ids.txt"

# WHY an allow-list of sources too: the id list is the gate, this is the second lock (open licences and BAM's own shapes)
SOURCES = {"google-scanned-objects": "Google Scanned Objects", "egad": "EGAD", "synthetic": "Generated (synthetic)",
           "generated": "Generated"}
KEEP = ["id", "name", "family", "type_name", "grade", "size_class", "bbox_volume_ml", "mass_g", "source", "geometry", "geometry_class"]
AREA_FAMILIES = {"plastic", "glass", "paper"}
AREA = {"medical": "Medical", "food": "Food"}
FAMILY_LABELS = {"plastic": "Plastics", "textile": "Textiles", "paper": "Paper", "composite": "Composites", "other": "Other",
                 "metal": "Metals", "glass": "Glass", "electronic": "Electronics", "ceramic": "Ceramics", "organic": "Organics",
                 "rubber": "Rubber", "wood": "Wood"}
SHAPE_LABELS = {"long": "Long", "irregular": "Irregular", "flat": "Flat", "cubic": "Cubic"}


def main() -> None:
    public = [line.strip() for line in PUBLIC_IDS.read_text(encoding="utf-8").splitlines() if line.strip()]
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in src["rows"]}
    missing = [object_id for object_id in public if object_id not in by_id]
    if missing:
        sys.exit(f"snapshot: {len(missing)} public ids are not in {SOURCE} (first: {missing[0]}); nothing written")
    rows = []
    for object_id in public:
        r = by_id[object_id]
        if r.get("source") not in SOURCES:
            sys.exit(f"snapshot: {object_id} has source {r.get('source')!r}, not an open-licence or generated one; nothing written")
        row = {k: r.get(k) for k in KEEP}
        mass = r.get("mass_g")
        row["mass_g"] = mass.get("value") if isinstance(mass, dict) else mass
        row["area"] = AREA.get(r.get("grade")) if r.get("family") in AREA_FAMILIES else None
        rows.append(row)
    size = collections.Counter(r["family"] for r in rows)
    rows.sort(key=lambda r: (-size[r["family"]], r["family"] or "", r["type_name"] or "", r["name"] or "", r["id"]))
    props = src["properties"]
    out = {
        "id": "object-collection",
        "title": "BAM object library (public sample)",
        "titleProperty": "name",
        "source": f"ObjectDB's public sample (lane/object-db-public 809e9b2: open-licence scans and BAM's generated primitives; {len(rows)} rows, {len(KEEP) + 1} columns)",
        "properties": {
            "id": {"type": "text", "hidden": True},
            "name": {"type": "text"},
            "family": {"type": "text", "labels": FAMILY_LABELS},
            "area": {"type": "text", "derived": "Medical / Food for a plastic, glass or paper object of that grade; else none"},
            "type_name": {"type": "text"},
            "grade": {"type": "text"},
            "size_class": {"type": "text"},
            "bbox_volume_ml": {**props["bbox_volume_ml"]},
            "mass_g": {**props["mass_g"]},
            "source": {"type": "text", "labels": SOURCES},
            "geometry": {"type": "text"},
            "geometry_class": {"type": "text", "labels": SHAPE_LABELS},
        },
        "rows": rows,
    }
    path = HERE / "objects.json"
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{path.relative_to(HERE.parents[2])}: {len(rows)} rows, {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
