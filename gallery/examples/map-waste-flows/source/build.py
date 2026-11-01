"""Build flows.json: where Metro Vancouver's garbage went in 2024, facility to facility (synthetic split).

    python3 -I gallery/examples/map-waste-flows/source/build.py [RAW_DIR]

RAW_DIR (argument, else $RAW_DIR, else ./raw) holds:
    osm-flows/overpass.json                          flows.overpassql (beside this script): facility points, OSM
    mv-factsheet/solid-waste-system-fact-sheet.pdf   Metro Vancouver, 2024 Solid Waste System fact sheets
    cov-landfill-wayback/report.pdf                  City of Vancouver, 2024 Annual Report for the Vancouver Landfill
    mv-iswrmp/iswrmp-biennial-report-2024.pdf        Metro Vancouver, 2024 ISWRMP Biennial Report (DRAFT)
Every published figure below is checked against its PDF page with `pdftotext` when the PDFs are present.

Published: each Metro Vancouver station's 2024 garbage tonnes; the three destination totals of what those stations
sent on (Vancouver Landfill, Waste-to-Energy Facility, contingency landfills); VSTS -> Vancouver Landfill; bottom ash
WTE -> Vancouver Landfill. NOT published: how each station splits across the three destinations. Those rows are
invented: each station's tonnes are shared out in the proportions of the published destination totals (largest
remainder rounding, so every destination sums exactly to its published total), and say basis "synthetic".
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parents[1]
RAW = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("RAW_DIR", "raw"))
YEAR = 2024
FACTSHEET = "https://metrovancouver.org/services/solid-waste/Documents/solid-waste-system-fact-sheet.pdf"
LANDFILL_REPORT = "https://vancouver.ca/files/cov/2024-annual-report-vancouver-landfill.pdf"
BIENNIAL = "https://metrovancouver.org/services/solid-waste/Documents/iswrmp-biennial-report-2024.pdf"
PDFS = {FACTSHEET: "mv-factsheet/solid-waste-system-fact-sheet.pdf", LANDFILL_REPORT: "cov-landfill-wayback/report.pdf", BIENNIAL: "mv-iswrmp/iswrmp-biennial-report-2024.pdf"}

# facility key -> (name, OSM element). The OSM element supplies the point; names follow the operators' reports.
# "unmapped" / "none": no point, and the row says why.
NO_POINT = {
    "unmapped": "not mapped as a waste facility in OpenStreetMap (checked 2026-10-28)",
    "none": "Metro Vancouver does not name its three contingency landfills",
}
FACILITIES = {
    "united-boulevard": ("United Boulevard Recycling and Waste Centre", "way/585031799"),
    "north-surrey": ("North Surrey Recycling and Waste Centre", "way/448908717"),
    "central-surrey": ("Central Surrey Recycling and Waste Centre", "way/1418179695"),
    "langley": ("Langley Recycling and Waste Centre", "way/879884610"),
    "maple-ridge": ("Maple Ridge Recycling and Waste Centre", "unmapped"),
    "vsts": ("Vancouver South Transfer Station", "way/1207315845"),
    "landfill": ("Vancouver Landfill", "relation/14118449"),
    "wte": ("Metro Vancouver Waste-to-Energy Facility", "way/418204624"),
    "contingency": ("Contingency landfills (out of region, unnamed)", "none"),
}
# (station key, published garbage tonnes 2024, PDF page of the fact sheet). "withheld": the fact sheet's p. 2 station,
# whose name data-ui's public-data deny scan catches; it keeps its share of the split, but its rows are not written.
STATIONS = [("withheld", 123170, 2), ("united-boulevard", 263736, 3), ("north-surrey", 235338, 4), ("central-surrey", 10327, 5), ("langley", 7601, 6), ("maple-ridge", 9435, 7)]
# (destination key, published tonnes received from the Metro Vancouver stations in 2024, source, PDF page, text on that page)
DESTINATIONS = [
    ("landfill", 405722, LANDFILL_REPORT, 17, "405,722 tonnes were transferred"),
    ("wte", 84196, FACTSHEET, 8, "Transfer: 84,196 tonnes"),
    ("contingency", 151539, BIENNIAL, 12, "151,539"),
]
# Published facility-to-facility flows: (from, to, tonnes, material, source, page, text on that page)
PUBLISHED = [
    ("vsts", "landfill", 140013, "garbage", LANDFILL_REPORT, 17, "140,013 tonnes were transferred through the VSTS"),
    ("wte", "landfill", 39347, "bottom ash", LANDFILL_REPORT, 18, "receives bottom ash from the regional Waste-To-Energy Facility"),
]


def page_text(url: str, page: int) -> str | None:
    pdf = RAW / PDFS[url]
    if not shutil.which("pdftotext") or not pdf.exists():
        return None
    out = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), "-raw", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    return " ".join(out.split())


def verify(url: str, page: int, needle: str) -> None:
    text = page_text(url, page)
    if text is None:
        print(f"  (not verified: no pdftotext or no {PDFS[url]})")
    elif " ".join(needle.split()) not in text:
        raise SystemExit(f"{needle!r} is not on page {page} of {url}")


def points() -> dict[str, object]:
    answer = json.loads((RAW / "osm-flows" / "overpass.json").read_text())
    by_ref = {f"{e['type']}/{e['id']}": e for e in answer["elements"]}
    found = {}
    for key, (name, ref) in FACILITIES.items():
        if ref in NO_POINT:
            found[key] = {"value": None, "why": NO_POINT[ref]}
            continue
        element = by_ref[ref]
        p = element if element["type"] == "node" else element["center"]
        found[key] = [round(p["lat"], 5), round(p["lon"], 5)]
    return found


def split(total: int, weights: list[int]) -> list[int]:
    raw = [total * w / sum(weights) for w in weights]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True)[: total - sum(out)]:
        out[i] += 1
    return out


def main() -> None:
    for key, tonnes, page in STATIONS:
        verify(FACTSHEET, page, f"{tonnes:,}")
    for _, tonnes, url, page, needle in DESTINATIONS:
        verify(url, page, needle)
    for *_, url, page, needle in PUBLISHED:
        verify(url, page, needle)

    at = points()
    rows = []
    for origin, to, tonnes, material, url, page, _ in PUBLISHED:
        rows.append({"id": f"{origin}-to-{to}", "from": FACILITIES[origin][0], "to": FACILITIES[to][0], "origin": at[origin], "destination": at[to],
                     "tonnes": tonnes, "year": YEAR, "material": material, "basis": "published", "source": url, "page": page})
    station_tonnes = [t for _, t, _ in STATIONS]
    for dest, total, url, page, _ in DESTINATIONS:
        for (station, _, _), tonnes in zip(STATIONS, split(total, station_tonnes)):
            if station == "withheld":
                continue
            rows.append({"id": f"{station}-to-{dest}", "from": FACILITIES[station][0], "to": FACILITIES[dest][0], "origin": at[station], "destination": at[dest],
                         "tonnes": tonnes, "year": YEAR, "material": "garbage", "basis": "synthetic",
                         "note": f"invented split of the station's published {dict((s, t) for s, t, _ in STATIONS)[station]:,} t in the ratio of the published destination totals; the destination total ({total:,} t) is published"})
    rows.sort(key=lambda row: row["id"])
    doc = {
        "id": "metro-vancouver-garbage-flows",
        "title": "Metro Vancouver garbage flows between facilities, 2024 (synthetic split)",
        "titleProperty": "from",
        "source": "Metro Vancouver 2024 Solid Waste System fact sheets; City of Vancouver 2024 Annual Report for the Vancouver Landfill; Metro Vancouver 2024 ISWRMP Biennial Report (draft); facility points © OpenStreetMap contributors, ODbL",
        "attribution": {"text": "© OpenStreetMap contributors", "url": "https://www.openstreetmap.org/copyright"},
        "properties": {
            "from": {"type": "text", "label": "From"},
            "to": {"type": "text", "label": "To"},
            "origin": {"type": "list", "label": "Origin (lat, lng)"},
            "destination": {"type": "list", "label": "Destination (lat, lng)"},
            "tonnes": {"type": "number", "label": "Tonnes", "unitText": "t/yr", "decimals": 0},
            "year": {"type": "number", "label": "Year", "decimals": 0},
            "material": {"type": "text", "label": "Material"},
            "basis": {"type": "text", "label": "Basis"},
            "source": {"type": "text", "label": "Source"},
            "page": {"type": "number", "label": "PDF page", "decimals": 0},
            "note": {"type": "text", "label": "Note"},
        },
        "rows": rows,
    }
    (HERE / "flows.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    for key, (name, ref) in FACILITIES.items():
        print(f"  {name}: OSM {ref}")
    print(f"flows.json: {len(rows)} rows ({sum(r['basis'] == 'published' for r in rows)} published, {sum(r['basis'] == 'synthetic' for r in rows)} synthetic)")


if __name__ == "__main__":
    main()
