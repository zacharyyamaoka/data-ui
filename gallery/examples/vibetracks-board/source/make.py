"""Write this case's rows from Vibe Tracks' feature notes (read-only).

    python3 gallery/examples/vibetracks-board/source/make.py

Reads ~/vibetracks/features/VT-*.md (VIBETRACKS to override): each note's front matter (vibe-id,
vibe-status, vibe-priority, vibe-areas, vibe-description, vibe-depends-on, vibe-evidence, vibe-commits) and its title
from the file name. `proof` is derived here, the way Vibe Tracks derives state instead of letting anyone claim it:
"commits" when the note lists commits, "evidence" when it lists evidence only, else "none". Its property says
`derived`, so the board refuses to move a card between proof columns. Feature notes carry no KPI figures; nothing
private is copied.
"""

from __future__ import annotations

import json
import os
import pathlib
import re

import yaml

HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE.parent
VIBETRACKS = pathlib.Path(os.environ.get("VIBETRACKS", "~/vibetracks"))
# Vibe Tracks' own column order (vibetracks/descriptor.py DEFAULT_STATUSES); a status it does not list follows them
STATUSES = ["backlog", "ready", "running", "waiting", "review", "frontier", "done", "archived"]


def front(text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    return yaml.safe_load(m.group(1)) if m else {}


def listed(v) -> list:
    return [x for x in (v or []) if x] if isinstance(v, list) else ([v] if v else [])


def main() -> None:
    rows = []
    for note in sorted((VIBETRACKS / "features").glob("VT-*.md")):
        fm = front(note.read_text(encoding="utf-8"))
        title = note.stem.split(" - ", 1)[1] if " - " in note.stem else note.stem
        commits, evidence = listed(fm.get("vibe-commits")), listed(fm.get("vibe-evidence"))
        rows.append({
            "id": fm.get("vibe-id") or note.stem.split(" ")[0],
            "title": title,
            "status": fm.get("vibe-status"),
            "priority": fm.get("vibe-priority"),
            "areas": listed(fm.get("vibe-areas")),
            "description": fm.get("vibe-description"),
            "depends": len(listed(fm.get("vibe-depends-on"))),
            "evidence": len(evidence),
            "commits": len(commits),
            "proof": "commits" if commits else "evidence" if evidence else "none",
        })
    data = {
        "id": "vibetracks-features",
        "title": "Vibe Tracks features",
        "titleProperty": "title",
        "properties": {
            "id": {"type": "text", "label": "ID"},
            "title": {"type": "text", "label": "Feature"},
            "status": {"type": "text", "label": "Status", "facet": True},
            "priority": {"type": "text", "label": "Priority", "facet": True, "colors": {"high": 8, "medium": 4, "low": 0}},
            "areas": {"type": "list", "label": "Areas", "facet": True},
            "description": {"type": "text", "label": "Description"},
            "depends": {"type": "number", "label": "Depends on", "note": "notes this feature waits on"},
            "evidence": {"type": "number", "label": "Evidence", "note": "evidence links in the note"},
            "commits": {"type": "number", "label": "Commits"},
            "proof": {"type": "text", "label": "Proof", "facet": True, "derived": "from the note's vibe-commits and vibe-evidence",
                      "colors": {"commits": 3, "evidence": 1, "none": 0}},
        },
        "rows": rows,
    }
    (CASE / "features.json").write_text(json.dumps(data, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"features.json: {len(rows)} features; by status {counts}")


if __name__ == "__main__":
    main()
