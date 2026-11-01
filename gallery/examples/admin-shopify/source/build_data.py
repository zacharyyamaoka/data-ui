"""Writes organizations.json and deals.json for the admin-shopify case: 14 invented organizations and 4 invented deals.

    python3 gallery/examples/admin-shopify/source/build_data.py

Every name, place, tag and note here is made up (data-ui.dev is public: invented or public data only, never CRM
data). The shape copies Tycoon S6's Organizations and Deals screens (Zach's screenshots, 2026-10-28): kind, stage,
tags, place, people, deals and last activity for an organization; organization, stage, facility, due date, next step
and value for a deal. Dates are fixed, so "Due this month" and "Next due" are computed against the reader's today.
"""

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parents[1]

# name, kind, stage, tags, place, people, deals, last activity
ORGS = [
    ("Alderbank Medical Waste", "Customer", "Contacted", ["medical-waste", "collector", "hauler", "hospital"], "Harbour City", 1, 1, "2026-04-10"),
    ("Birchway Sorting Co", "Prospect", "Contacted", ["hauler", "2023-discovery", "recycler"], "Harbour City", 3, None, "2023-07-25"),
    ("City of Larkspur", "Prospect", "Contacted", ["public", "municipal", "regulator", "collector"], "City of Larkspur", 3, None, "2023-08-11"),
    ("Coldstream Health Services", "Competitor", "Prospect", ["incumbent", "medical-waste"], None, None, None, None),
    ("Driftwood MedServ", "Prospect", "Contacted", ["medical-waste", "collector", "hauler"], "Harbour City", None, None, "2023-04-18"),
    ("Fernhill Environmental", "Competitor", "Prospect", ["incumbent", "hauler", "mrf", "collector"], None, None, None, None),
    ("Glasswing Plastics Supply", "Competitor", "Prospect", ["recycler", "optical-sorting", "plastics"], "Harbour City", None, None, None),
    ("Harbour City Regional District", "Prospect", "Contacted", ["public", "regulator", "municipal", "landfill"], "Harbour City", 3, 1, "2023-11-20"),
    ("Kestrel Health Care", "Prospect", "Contacted", ["hospital", "producer", "ppe"], "City of Larkspur", 1, None, "2024-02-06"),
    ("Loopline Recycling", "Customer", "Contacted", ["recycler", "collector", "mrf", "hauler", "commercial"], "City of Larkspur", 4, 1, "2026-06-30"),
    ("Northgate Biohazard", "Competitor", "Prospect", ["incumbent", "medical-waste"], None, None, None, None),
    ("Quarry Lane Recycling", "Competitor", "Lead", ["mrf", "recycler", "glass", "metals"], "Harbour City", None, None, None),
    ("Timberjack Reclaim", "Prospect", "Contacted", ["wood", "recycler", "construction"], "City of Larkspur", 3, None, "2024-04-19"),
    ("Veridian Glove Works", "Customer", "Contacted", ["ppe", "manufacturer", "nitrile", "medical", "plastics"], "Harbour City", 1, 1, "2024-06-11"),
]

# title, organization, stage, facility, due, next step, value (CAD, a guess)
DEALS = [
    ("Food-court tray sort: a sorting cell pilot", "Loopline Recycling", "Idea", "Loopline Recycling (commercial recycler)", "2026-11-05", "Send the follow-up note (sprint: Oct 14, not yet sent)", None),
    ("Glove-line offcuts: a demo, then a sorting pilot", "Veridian Glove Works", "Idea", "Veridian Glove Works (PPE manufacturer)", "2026-11-05", "Send the follow-up note (sprint: Oct 15, not yet sent)", None),
    ("Pilot V1: one arm over one bin of mixed clinic waste", "Alderbank Medical Waste", "Idea", "Alderbank Medical Waste (small medical-waste hauler)", "2026-11-13", "Send the owner the five sizing questions", 20),
    ("Transfer station: a sorting line by year end", "Harbour City Regional District", "Idea", "Harbour City Recycling and Waste Centre", "2026-12-31", None, None),
]

slug = lambda s: "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-").replace("--", "-")

orgs = {
    "id": "admin-organizations",
    "title": "Organizations",
    "titleProperty": "name",
    "source": "invented for the data-ui gallery (gallery/examples/admin-shopify/source/build_data.py)",
    "properties": {
        "name": {"type": "text", "label": "Organization"},
        "kind": {"type": "text", "label": "Kind", "display": "badge", "colors": {"Customer": 0, "Prospect": 0, "Competitor": 0}},
        "stage": {"type": "text", "label": "Stage", "display": "badge", "colors": {"Contacted": 1, "Prospect": 0, "Lead": 0}},
        "tags": {"type": "list", "label": "Tags", "display": "badge", "colors": {}},
        "place": {"type": "text", "label": "Place"},
        "people": {"type": "number", "label": "People", "note": "contacts recorded at this organization"},
        "deals": {"type": "number", "label": "Deals", "note": "deals with this organization"},
        "last_activity": {"type": "date", "label": "Last activity"},
    },
    "rows": [
        {"id": slug(n), "name": n, "kind": k, "stage": s, "tags": t, "place": pl, "people": pe, "deals": d, "last_activity": la}
        for n, k, s, t, pl, pe, d, la in ORGS
    ],
}
# every tag grey, as Polaris' default Badge: colour slot 0 for each value that occurs
orgs["properties"]["tags"]["colors"] = {t: 0 for row in ORGS for t in row[3]}

deals = {
    "id": "admin-deals",
    "title": "Deals",
    "titleProperty": "deal",
    "source": "invented for the data-ui gallery (gallery/examples/admin-shopify/source/build_data.py)",
    "properties": {
        "deal": {"type": "text", "label": "Deal"},
        "organization": {"type": "text", "label": "Organization"},
        "stage": {"type": "text", "label": "Stage", "display": "badge", "colors": {"Idea": 0, "Won": 6, "Lost": 8}},
        "facility": {"type": "text", "label": "Facility"},
        "due": {"type": "date", "label": "Due"},
        "next_step": {"type": "text", "label": "Next step"},
        "value": {"type": "number", "label": "Value", "unitText": "CAD"},
    },
    "rows": [
        {"id": slug(t), "deal": t, "organization": o, "stage": s, "facility": f, "due": du, "next_step": n,
         "value": None if v is None else {"value": v, "unit": "CAD", "basis": "estimate", "note": "a guess"}}
        for t, o, s, f, du, n, v in DEALS
    ],
}

for name, doc in (("organizations.json", orgs), ("deals.json", deals)):
    (HERE / name).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {name}: {len(doc['rows'])} rows")
