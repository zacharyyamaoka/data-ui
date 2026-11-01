"""Write this case's data and copy the photos and logos it uses from robotparts (read-only).

    python3 gallery/examples/robotparts-photos/source/make.py

Reads robotparts' v2 catalog (dist/site/v2/catalog.json), its hosted media index (media/photos.jsonl,
media/brands.jsonl) and the files under media/files/. Picks a few hundred KB per brand, never the whole store: up to
~100 actuators and ~80 cameras (brands with a hosted logo first), one photo each, plus each brand's logo. Writes
photos.json beside this folder and copies each file into media/, as `p-<sha8>.webp` and `logo-<slug>.<ext>`.
WHY these photos may be copied: robotparts hosts them under Zach's 2026-10-25 decision (`hosting_basis: owner`,
"real photos for a personal catalog for friends, family and BAM; linked to the source; removed on request"), and
each caption names its source and the day it was fetched.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE.parent
ROBOTPARTS = pathlib.Path(os.environ.get("ROBOTPARTS", "~/robotparts"))
ACTUATOR_QUOTA = {"Steadywin": 30, "Damiao": 20}  # the two actuator brands with a hosted logo
ACTUATOR_OTHERS = ["CubeMars", "MyActuator", "RobStride", "Unitree", "Feetech", "KST", "LKMTech", "EYOU"]
ACTUATOR_EACH = 6
CAMERA_EACH = 8
CAMERA_NO_LOGO = {"Hikrobot": 4, "Teledyne FLIR": 4, "Arducam": 4}
BUDGET = 8 * 1024 * 1024
MEDIA = CASE / "media"


def jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def spec(part: dict, key: str):
    s = (part.get("specs") or {}).get(key)
    return s.get("value") if isinstance(s, dict) else s


def grams(part: dict):
    s = (part.get("specs") or {}).get("mass_kg")
    if not isinstance(s, dict) or s.get("value") is None:
        return spec(part, "mass_g")
    # WHY from the spec's own unit: robotparts' mass_kg carries its unit, and one record's is grams (the table lane's x1000 bug)
    scale = {"kg": 1000, "g": 1}.get(s.get("unit"), 1000)
    return round(s["value"] * scale, 1)


def main() -> None:
    catalog = json.loads((ROBOTPARTS / "dist/site/v2/catalog.json").read_text(encoding="utf-8"))
    photos = {}
    for p in jsonl(ROBOTPARTS / "media/photos.jsonl"):
        photos.setdefault(p["part"], p)
    logos = {}
    for b in jsonl(ROBOTPARTS / "media/brands.jsonl"):
        logos.setdefault(b["brand"].lower(), b)
    live = [p for p in catalog["parts"] if p["id"] in photos and not p.get("retired") and not p.get("same_as")]
    by_brand = defaultdict(list)
    for p in sorted(live, key=lambda x: (x["category"], x["brand"], x["model"] or "")):
        by_brand[(p["category"], p["brand"])].append(p)

    picked: list[dict] = []
    for brand, n in ACTUATOR_QUOTA.items():
        picked += by_brand[("actuator", brand)][:n]
    for brand in ACTUATOR_OTHERS:
        picked += by_brand[("actuator", brand)][:ACTUATOR_EACH]
    camera_brands = Counter(p["brand"] for p in live if p["category"] == "camera")
    for brand, _ in camera_brands.most_common():
        if brand.lower() in logos:
            picked += by_brand[("camera", brand)][:CAMERA_EACH]
    for brand, n in CAMERA_NO_LOGO.items():
        picked += by_brand[("camera", brand)][:n]

    shutil.rmtree(MEDIA, ignore_errors=True)
    MEDIA.mkdir()
    used = 0
    rows = []
    copied_logos: dict[str, str] = {}
    for p in picked:
        ph = photos[p["id"]]
        src = ROBOTPARTS / ph["file"]
        name = f"media/p-{ph['sha256'][:8]}.{src.suffix.lstrip('.')}"
        shutil.copyfile(src, CASE / name)
        used += src.stat().st_size
        logo = logos.get(p["brand"].lower())
        logo_name = None
        if logo:
            if p["brand"] not in copied_logos:
                lsrc = ROBOTPARTS / logo["file"]
                copied_logos[p["brand"]] = f"media/logo-{logo['slug']}{lsrc.suffix}"
                shutil.copyfile(lsrc, CASE / copied_logos[p["brand"]])
                used += lsrc.stat().st_size
            logo_name = copied_logos[p["brand"]]
        actuator = p["category"] == "actuator"
        rows.append({
            "id": p["id"],
            "model": p["model"] or p["title"],
            "brand": p["brand"],
            "logo": logo_name,
            "category": "Actuator" if actuator else "Camera",
            # a rich cell: the photo with where it came from and when (the lightbox caption's second line)
            "photo": {"value": name, "source": ph.get("page_url") or ph["image_url"], "asOf": ph["retrieved_on"][:10]},
            "level": p.get("level"),
            "peak_torque": spec(p, "peak_torque_nm") if actuator else None,
            "mass": grams(p),
            "resolution": round(spec(p, "resolution_mp"), 2) if not actuator and spec(p, "resolution_mp") else None,
            "fps": spec(p, "fps_max") if not actuator else None,
            "shutter": spec(p, "shutter") if not actuator else None,
            "sensor": spec(p, "sensor_model") if not actuator else None,
            "url": p.get("url"),
        })
    assert used <= BUDGET, f"{used:,} bytes of media is over the {BUDGET:,} budget"
    data = {
        "id": "robotparts-photos",
        "title": "robotparts photos",
        "titleProperty": "model",
        "linkProperty": "url",
        "imageProperty": "photo",
        "properties": {
            "model": {"type": "text", "label": "Model"},
            "brand": {"type": "text", "label": "Brand", "facet": True},
            "logo": {"type": "text", "label": "Logo", "display": "image"},
            "category": {"type": "text", "label": "Category", "facet": True},
            "photo": {"type": "text", "label": "Photo", "media": "image"},
            "level": {"type": "number", "label": "Level", "note": "robotparts' evidence level, 0-5", "derived": "robotparts' checks"},
            "peak_torque": {"type": "number", "label": "Peak torque", "unitText": "N·m"},
            "mass": {"type": "number", "label": "Mass", "unitText": "g"},
            "resolution": {"type": "number", "label": "Resolution", "unitText": "MP"},
            "fps": {"type": "number", "label": "Max fps", "unitText": "fps"},
            "shutter": {"type": "text", "label": "Shutter"},
            "sensor": {"type": "text", "label": "Sensor"},
            "url": {"type": "text", "label": "Page", "display": "link"},
        },
        "rows": rows,
    }
    (CASE / "photos.json").write_text(json.dumps(data, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    kinds = Counter(r["category"] for r in rows)
    print(f"photos.json: {len(rows)} rows ({dict(kinds)}), {len(rows)} photos + {len(copied_logos)} logos, {used:,} bytes, release {catalog['release']}")


if __name__ == "__main__":
    main()
