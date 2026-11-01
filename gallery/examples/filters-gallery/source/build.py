"""Write the Filters case's data: the robotparts-actuators case's 1,149 rows plus the three columns its rail needs.

    python3 gallery/examples/filters-gallery/source/build.py      # rewrites ../actuators.json and ../logos/

The rows are ../../robotparts-actuators/actuators.json (written by gallery/tools/build_examples.py), unchanged except:
- `photo` points at that case's photos (../robotparts-actuators/photos/…), so the 150 photos are not copied twice;
- `in_stock` (yes / no / unknown), from robotparts' live actuator rows (ROBOTPARTS_ROWS, robotparts.dev's
  /search/views/actuator.json as built on disk), the field its own rail filters on;
- `checks` (listed, cited, cad, sim, measured), the same file's list of the checks a part has passed;
- `listed` (an ISO date), the day robotparts first saw the part listed for sale: the earliest `observed_at` of its
  listings in robotparts' catalog (ROBOTPARTS_CATALOG). Most parts were seen on 2026-10-22, a handful on 2026-10-08,
  so "Last 7 days" and "Older than 14 days" split the catalog the way a staleness check would.
And `logos/`: the three actuator brands robotparts has a logo for (JMC, Damiao, Steadywin), from its media index
(ROBOTPARTS_MEDIA, brands.jsonl), resized to 120 px high. Hosted on robotparts.dev on the owner's basis (brands.jsonl
`owner_note`). WHY a sibling file and not new columns in robotparts-actuators: that case is the orchestrator's, and
these columns exist for this case's rail; build_examples.py can take them over if the other cases want them.
"""

from __future__ import annotations

import io
import json
import os
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE.parent
SOURCE = CASE.parent / "robotparts-actuators" / "actuators.json"
RP = pathlib.Path(os.environ.get("ROBOTPARTS", "~/robotparts"))
ROWS = pathlib.Path(os.environ.get("ROBOTPARTS_ROWS", RP / "dist/site/search/views/actuator.json"))
CATALOG = pathlib.Path(os.environ.get("ROBOTPARTS_CATALOG", RP / "dist/site/v2/catalog.json"))
MEDIA = pathlib.Path(os.environ.get("ROBOTPARTS_MEDIA", RP / "media"))
LOGO_HEIGHT = 120


def main() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    live = {r["id"]: r for r in json.loads(ROWS.read_text(encoding="utf-8"))["rows"]}
    listed = {}
    for part in json.loads(CATALOG.read_text(encoding="utf-8"))["parts"]:
        seen = sorted(l["observed_at"][:10] for l in part.get("listings") or [] if l.get("observed_at"))
        if seen:
            listed[part["id"]] = seen[0]
    for row in data["rows"]:
        if row.get("photo"):
            row["photo"] = "../robotparts-actuators/" + row["photo"]
        other = live.get(row["id"], {})
        row["in_stock"] = other.get("in_stock")
        row["checks"] = other.get("checks") or []
        row["listed"] = listed.get(row["id"])
    props = data["properties"]
    props["in_stock"] = {"type": "text", "width": 90, "note": "robotparts' own reading of its sellers' stock (yes, no, unknown)"}
    props["checks"] = {"type": "list", "width": 160, "note": "the checks a part has passed on robotparts: listed, cited, CAD, sim, measured"}
    props["listed"] = {"type": "date", "width": 100, "note": "the day robotparts first saw the part listed for sale (its earliest listing)"}
    data["id"] = "actuators-filters"
    data["source"] = data["source"] + "; in_stock and checks: robotparts /search/views/actuator.json; listed: catalog listings[].observed_at"
    out = CASE / "actuators.json"
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{out.relative_to(CASE.parent.parent.parent)}: {len(data['rows'])} rows, {out.stat().st_size:,} bytes")
    logos()


def logos() -> None:
    from PIL import Image  # only to resize the three logos; the rows need nothing beyond the stdlib

    brands = {r["brand"]: r for r in map(json.loads, (MEDIA / "brands.jsonl").read_text(encoding="utf-8").splitlines()) if r.get("file")}
    data = json.loads((CASE / "actuators.json").read_text(encoding="utf-8"))
    have = sorted({r["brand"] for r in data["rows"]} & set(brands))
    (CASE / "logos").mkdir(exist_ok=True)
    for brand in have:
        image = Image.open(RP / brands[brand]["file"])
        if image.height > LOGO_HEIGHT:
            image = image.resize((round(image.width * LOGO_HEIGHT / image.height), LOGO_HEIGHT), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, "WEBP", quality=88)
        path = CASE / "logos" / f"{brand.lower().replace(' ', '-')}.webp"
        path.write_bytes(buffer.getvalue())
        print(f"logos/{path.name}: {image.width}x{image.height}, {path.stat().st_size:,} bytes ({brands[brand]['page_url']})")


if __name__ == "__main__":
    main()
