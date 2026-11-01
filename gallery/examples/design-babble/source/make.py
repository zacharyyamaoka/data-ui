"""Write this case's rows from robotparts' two design babbles and copy their stills, made small (read-only source).

    python3 gallery/examples/design-babble/source/make.py

Reads design/babble-2026-10-22/ and design/babble-2026-10-22b/ in robotparts (ROBOTPARTS to override): each
round's gallery-spec.json (the variants, their per-requirement scores and the weights) and three stills per variant
from its shots/ folder: the landing and the part page at 1280 px, and the phone at 375 px. Each still is re-encoded
as WebP (desktop 960 px wide, phone 375 px, quality 70) and written to stills/ as
b<round>-<variant>-<shot>.webp. The score is the babble's own weighted total out of 100:
sum(score x weight) / 5, which gives round 2's Views + Offers its published 92.0.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil

from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE.parent
ROBOTPARTS = pathlib.Path(os.environ.get("ROBOTPARTS", "~/robotparts"))
ROUNDS = [("babble-2026-10-22", 1, "five design languages"), ("babble-2026-10-22b", 2, "five catalog designs")]
STILLS = CASE / "stills"
SHOTS = [("landing-1280.png", "Landing", 960), ("hero-1280.png", "Part page", 960), ("phone-375.png", "Phone", 375)]


def main() -> None:
    shutil.rmtree(STILLS, ignore_errors=True)
    STILLS.mkdir()
    rows = []
    total = 0
    for folder, n, theme in ROUNDS:
        spec = json.loads((ROBOTPARTS / "design" / folder / "gallery-spec.json").read_text(encoding="utf-8"))
        weights = {r["id"]: r["weight"] for r in spec["requirements"]}
        for v in spec["variants"]:
            m = re.search(r"design/[^/]+/([^/]+)/index\.html", v["preview"])
            variant_dir = ROBOTPARTS / "design" / folder / m.group(1)
            score = round(sum(s["score"] * weights[k] for k, s in v["scores"].items()) / 5, 1)
            for i, (shot, label, width) in enumerate(SHOTS):
                src = variant_dir / "shots" / shot
                if not src.exists():
                    continue
                name = f"b{n}-{v['id']}-{shot.split('-')[0]}.webp"
                with Image.open(src) as im:
                    im = im.convert("RGB")
                    if im.width > width:
                        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
                    im.save(STILLS / name, "WEBP", quality=70, method=6)
                total += (STILLS / name).stat().st_size
                rows.append({
                    "id": name.removesuffix(".webp"),
                    "variant": f"R{n} {v['id']} · {v['name']}",
                    "name": v["name"],
                    "round": f"Round {n} · {theme}",
                    "shot": label,
                    "order": i,
                    "score": score,
                    "default": v["id"] == spec["defaultId"],
                    "thesis": v["thesis"],
                    "best_when": v.get("bestWhen"),
                    "loses_when": v.get("losesWhen"),
                    "still": {"value": f"stills/{name}", "source": f"robotparts design/{folder}/{m.group(1)}/shots/{shot}", "asOf": "2026-10-22"},
                })
    data = {
        "id": "design-babble",
        "title": "robotparts design babble",
        "titleProperty": "variant",
        "imageProperty": "still",
        "properties": {
            "variant": {"type": "text", "label": "Variant"},
            "name": {"type": "text", "label": "Name"},
            "round": {"type": "text", "label": "Round", "facet": True},
            "shot": {"type": "text", "label": "Still", "facet": True},
            "order": {"type": "number", "label": "Still order", "hidden": True},
            "score": {"type": "number", "label": "Score", "unitText": "/ 100", "derived": "the babble's weighted total, sum(score x weight) / 5"},
            "default": {"type": "boolean", "label": "Default pick"},
            "thesis": {"type": "text", "label": "Thesis"},
            "best_when": {"type": "text", "label": "Best when"},
            "loses_when": {"type": "text", "label": "Loses when"},
            "still": {"type": "text", "label": "Still", "media": "image"},
        },
        "rows": rows,
    }
    (CASE / "babble.json").write_text(json.dumps(data, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"babble.json: {len(rows)} stills of {len({r['variant'] for r in rows})} variants, {total:,} bytes")


if __name__ == "__main__":
    main()
