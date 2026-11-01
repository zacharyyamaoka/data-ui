"""Build facts.json: one published 2024 figure per Metro Vancouver solid-waste facility, to annotate on a map.

    python3 -I gallery/examples/map-annotations/source/build.py [RAW_DIR]

RAW_DIR (argument, else $RAW_DIR, else ./raw) holds:
    osm-flows/overpass.json                          ../../map-waste-flows/source/flows.overpassql: facility points
    mv-factsheet/solid-waste-system-fact-sheet.pdf   Metro Vancouver, 2024 Solid Waste System fact sheets
    cov-landfill-wayback/report.pdf                  City of Vancouver, 2024 Annual Report for the Vancouver Landfill
Each figure is checked against the text of its cited PDF page with `pdftotext` when the PDFs are present; `page` is
the PDF's page index (1-based), not a printed page number.
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
FACTSHEET = "https://metrovancouver.org/services/solid-waste/Documents/solid-waste-system-fact-sheet.pdf"
LANDFILL_REPORT = "https://vancouver.ca/files/cov/2024-annual-report-vancouver-landfill.pdf"
PDFS = {FACTSHEET: "mv-factsheet/solid-waste-system-fact-sheet.pdf", LANDFILL_REPORT: "cov-landfill-wayback/report.pdf"}

# id, facility, OSM element (None: found by tag), figure, unit, what, year, source, page, text on that page
FACTS = [
    ("landfill-disposed", "Vancouver Landfill", "relation/14118449", 733196, "t", "waste disposed in 2024 (municipal solid waste, bottom ash and demolition material)", 2024, LANDFILL_REPORT, 3, "In 2024, 733,196 tonnes of waste were disposed"),
    ("landfill-cap", "Vancouver Landfill", "relation/14118449", 750000, "t/yr", "most municipal solid waste the landfill is authorized to accept in a year", 2024, LANDFILL_REPORT, 3, "authorized to accept up to 750,000 tonnes of MSW for disposal each year"),
    ("vsts-transferred", "Vancouver South Transfer Station", "way/1207315845", 140013, "t", "waste transferred through the station to the Vancouver Landfill in 2024", 2024, LANDFILL_REPORT, 17, "140,013 tonnes were transferred through the VSTS"),
    ("wte-processed", "Metro Vancouver Waste-to-Energy Facility", None, 243169, "t", "garbage and residuals processed in 2024", 2024, FACTSHEET, 8, "Total Processed (2024): 243,169 tonnes"),
    ("wte-electricity", "Metro Vancouver Waste-to-Energy Facility", None, 180000, "MWh/yr", "electricity generated from the steam, approximately, per year", 2024, FACTSHEET, 8, "approximately 180,000 MWh / year"),
    ("united-boulevard-garbage", "United Boulevard Recycling and Waste Centre", "way/585031799", 263736, "t", "garbage received in 2024", 2024, FACTSHEET, 3, "Garbage 188,634 263,736"),
    ("north-surrey-garbage", "North Surrey Recycling and Waste Centre", "way/448908717", 235338, "t", "garbage received in 2024", 2024, FACTSHEET, 4, "Garbage 143,986 235,338"),
]


def verify(url: str, page: int, needle: str) -> None:
    pdf = RAW / PDFS[url]
    if not shutil.which("pdftotext") or not pdf.exists():
        print(f"  (not verified: no pdftotext or no {PDFS[url]})")
        return
    text = " ".join(subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), "-raw", str(pdf), "-"], capture_output=True, text=True, check=True).stdout.split())
    if needle not in text:
        raise SystemExit(f"{needle!r} is not on page {page} of {url}")


def main() -> None:
    answer = json.loads((RAW / "osm-flows" / "overpass.json").read_text())
    by_ref = {f"{e['type']}/{e['id']}": e for e in answer["elements"]}
    wte = sorted((e for e in answer["elements"] if e["tags"].get("plant:source") == "waste" or "waste-to-energy" in e["tags"].get("name", "").lower()),
                 key=lambda e: (e["type"] == "node", e["id"]))
    rows = []
    for fact_id, facility, ref, figure, unit, what, year, url, page, needle in FACTS:
        verify(url, page, needle)
        element = by_ref[ref] if ref else wte[0]
        p = element if element["type"] == "node" else element["center"]
        rows.append({"id": fact_id, "facility": facility, "location": [round(p["lat"], 5), round(p["lon"], 5)], "figure": figure, "unit": unit,
                     "what": what, "year": year, "source": url, "page": page, "osm_id": f"{element['type']}/{element['id']}"})
    doc = {
        "id": "metro-vancouver-facility-facts",
        "title": "Published 2024 figures for Metro Vancouver waste facilities",
        "titleProperty": "facility",
        "source": "Metro Vancouver 2024 Solid Waste System fact sheets; City of Vancouver 2024 Annual Report for the Vancouver Landfill; facility points © OpenStreetMap contributors, ODbL",
        "attribution": {"text": "© OpenStreetMap contributors", "url": "https://www.openstreetmap.org/copyright"},
        "properties": {
            "facility": {"type": "text", "label": "Facility"},
            "location": {"type": "list", "label": "Point (lat, lng)"},
            "figure": {"type": "number", "label": "Figure", "decimals": 0},
            "unit": {"type": "text", "label": "Unit"},
            "what": {"type": "text", "label": "What"},
            "year": {"type": "number", "label": "Year", "decimals": 0},
            "source": {"type": "text", "label": "Source"},
            "page": {"type": "number", "label": "PDF page", "decimals": 0},
            "osm_id": {"type": "text", "label": "OSM element"},
        },
        "rows": rows,
    }
    (HERE / "facts.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    print(f"facts.json: {len(rows)} rows, every figure found on its cited page" if shutil.which("pdftotext") else f"facts.json: {len(rows)} rows")


if __name__ == "__main__":
    main()
