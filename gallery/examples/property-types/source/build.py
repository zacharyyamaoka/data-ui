"""Writes projects.json for the property-types case: Notion's "Projects" template (the four rows of Zach's 90.webp:
names, owners, status, priority, completion) plus six made-up projects, so every property type has cells to draw.
Made-up data, public-safe. Run: python3 source/build.py (from this folder)."""

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parents[1]
P = "../robotparts-actuators/photos/"
rows = [
    # name, status, owner, priority, completion, budget, due, tags, rating, shipped, url, email, phone, files, duration s, depends
    ("New Database View Types", "In Progress", "Ava Nguyen", "High", 0.25, 12000, "2026-11-14", ["views", "tables"], 4, False, "https://www.notion.so/templates/projects", "ava@example.com", "+1 604 555 0101", [P + "aifitlab-8541438771336.webp"], 5400, []),
    ("AI-Powered Search Overhaul", "In Progress", "Stephanie Lee", "Low", 0.40, 30500, "2026-12-01", ["search", "ai"], 3, False, "https://example.com/search", "stephanie@example.com", "+1 604 555 0102", [], 12600, ["p1"]),
    ("Mobile App Offline Mode Redesign", "Planning", "Florence Rossi", "Medium", 0.0, 8000, "2027-01-20", ["mobile"], 2, False, "https://example.com/offline", "florence@example.com", "+44 20 7946 0103", ["specs/offline-mode.pdf"], 1800, []),
    ("AI Meeting Notes Feature Expansion", "In Progress", "Katsu Hamaoka", "High", 0.20, 15250, "2026-11-30", ["ai", "notes"], 5, False, "https://example.com/notes", "katsu@example.com", "+81 3 5555 0104", [], 7200, ["p2", "p1"]),
    ("Billing Page Refresh", "Done", "Ava Nguyen", "Medium", 1.0, 4200, "2026-10-02", ["web"], 4, True, "https://example.com/billing", "ava@example.com", "+1 604 555 0101", [P + "aifitlab-8542347853960.webp"], 3600, []),
    ("Onboarding Checklist", "Not started", "Marcus Bell", "Low", 0.0, 2500, "2027-02-10", ["growth"], 1, False, "https://example.com/onboarding", "marcus@example.com", "+1 416 555 0106", [], 900, []),
    ("Data Export API", "In Progress", "Stephanie Lee", "High", 0.65, 22000, "2026-11-05", ["api", "tables"], 5, False, "https://example.com/export", "stephanie@example.com", "+1 604 555 0102", [], 16200, ["p1"]),
    ("Accessibility Audit", "Done", "Florence Rossi", "High", 1.0, 6000, "2026-09-18", ["a11y", "web"], 5, True, "https://example.com/a11y", "florence@example.com", "+44 20 7946 0103", ["reports/a11y-audit.pdf"], 10800, []),
    ("Team Calendar Sync", "Planning", "Marcus Bell", "Medium", 0.10, 9800, "2027-01-05", ["calendar"], 3, False, "https://example.com/calendar", "marcus@example.com", "+1 416 555 0106", [], 4500, ["p7"]),
    ("Dark Mode Polish", "In Progress", "Katsu Hamaoka", "Low", 0.80, 3100, "2026-10-30", ["web", "design"], 4, False, "https://example.com/dark", "katsu@example.com", "+81 3 5555 0104", [], 2700, []),
]
out = []
for i, (name, status, owner, prio, comp, budget, due, tags, rating, shipped, url, email, phone, files, dur, deps) in enumerate(rows, 1):
    out.append({
        "id": f"p{i}", "number": i, "name": name, "status": status, "owner": owner, "priority": prio, "completion": comp,
        "budget": budget, "spent": round(budget * comp, 2), "due": due, "edited": f"2026-10-{20 + (i % 6):02d}T{9 + i:02d}:15:00",
        "tags": tags, "rating": rating, "shipped": shipped, "url": url, "email": email, "phone": phone, "files": files,
        "effort": dur, "depends_on": deps,
    })
doc = {
    "id": "property-types", "title": "Projects", "titleProperty": "name",
    "properties": {
        "number": {"type": "number"}, "name": {"type": "text", "width": 270}, "status": {"type": "text", "width": 150},
        "owner": {"type": "text", "width": 170}, "priority": {"type": "text", "width": 110}, "completion": {"type": "number", "width": 170},
        "budget": {"type": "number", "width": 120}, "spent": {"type": "number", "width": 120, "derived": "budget × completion, by source/build.py"},
        "due": {"type": "date", "width": 130}, "edited": {"type": "date", "width": 130}, "tags": {"type": "list", "width": 170},
        "rating": {"type": "number", "width": 110}, "shipped": {"type": "boolean", "width": 90}, "url": {"type": "text", "width": 190},
        "email": {"type": "text", "width": 200}, "phone": {"type": "text", "width": 160}, "files": {"type": "list", "width": 150},
        "effort": {"type": "number", "width": 110}, "depends_on": {"type": "list", "width": 220, "relation": True},
    },
    "rows": out,
}
(HERE / "projects.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {len(out)} projects")
