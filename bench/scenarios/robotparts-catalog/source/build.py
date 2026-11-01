#!/usr/bin/env python3
"""Flatten robotparts' v2 catalog (dist/site/v2/catalog.json, 2,068 parts) into the one-row-per-part table this
scenario reads. Stdlib only. Usage: python3 build.py [catalog.json] [out.json]

WHY slim: the full catalog is 23 MB of listings, ports, views and citations; the bench measures the table, so the
row carries the columns a catalog table draws, with peak torque, mass and rated power as rich cells.
"""
import json
import pathlib
import sys

CATALOG = "~/robotparts/dist/site/v2/catalog.json"
OUT = pathlib.Path(__file__).resolve().parent.parent / "catalog.json"
BASIS = {"manufacturer": "datasheet", "distributor": "seller", "retailer": "seller", "aifitlab-text": "seller",
         "aifitlab-image-transcribed": "seller", "measured": "measured", "derived": "derived"}


def spec_cell(part: dict, key: str, scale: float = 1.0, unit: str = ""):
    s = (part.get("specs") or {}).get(key)
    if not s or not isinstance(s.get("value"), (int, float)):
        return None
    return {"value": round(s["value"] * scale, 4), "unit": unit or s.get("unit") or None,
            "basis": BASIS.get(s.get("source_kind"), "seller")}


def plain(part: dict, key: str):
    s = (part.get("specs") or {}).get(key)
    return s["value"] if s and isinstance(s.get("value"), (int, float)) else None


def row(part: dict) -> dict:
    prices = [o["price_usd"] for o in part.get("offers") or [] if isinstance(o.get("price_usd"), (int, float))]
    drive = part.get("drivetrain")
    return {
        "id": part["id"],
        "name": f"{part['brand']} {part['model']}",
        "category": part["category"],
        "brand": part["brand"],
        "model": part["model"],
        "level": part.get("level"),
        "drivetrain": drive.get("value") if isinstance(drive, dict) else drive,
        "buses": part.get("buses") or [],
        "peak_torque": spec_cell(part, "peak_torque_nm"),
        "mass": spec_cell(part, "mass_kg"),
        "rated_power": spec_cell(part, "rated_power_w"),
        "voltage": plain(part, "voltage_v"),
        "price": min(prices) if prices else None,
        "offers": len(part.get("offers") or []),
        "sellers": len({o["seller"] for o in part.get("offers") or []}) or None,
        "datasheet": bool(part.get("datasheet_url")),
        "url": part.get("url"),
        "image_url": part.get("image_url"),
    }


def main() -> None:
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else CATALOG)
    out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else OUT
    cat = json.loads(src.read_text())
    props = {
        "name": {"type": "text", "hidden": True},
        "category": {"type": "text", "width": 100, "display": "badge"},
        "brand": {"type": "text", "width": 130},
        "model": {"type": "text", "width": 190},
        "level": {"type": "number", "width": 58},
        "drivetrain": {"type": "text", "width": 104},
        "buses": {"type": "list", "width": 120},
        "peak_torque": {"type": "number", "unitText": "N·m", "width": 126},
        "mass": {"type": "number", "unitText": "kg", "width": 100},
        "rated_power": {"type": "number", "unitText": "W", "width": 110},
        "voltage": {"type": "number", "unitText": "V", "width": 90},
        "price": {"type": "number", "unitText": "USD", "decimals": 0, "width": 100},
        "offers": {"type": "number", "width": 70},
        "sellers": {"type": "number", "width": 70},
        "datasheet": {"type": "boolean", "width": 90},
        "url": {"type": "text", "hidden": True},
        "image_url": {"type": "text", "hidden": True},
    }
    data = {"id": "catalog", "title": "Parts", "titleProperty": "name", "linkProperty": "url",
            "source": f"robotparts {src.name} release {cat['release']} ({cat['format']})",
            "properties": props, "rows": [row(p) for p in cat["parts"]]}
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{len(data['rows'])} rows -> {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
