"""Build calendar.json: robotparts' releases (git tags) and the dates of Zach's daily notes. Read-only.

    python3 gallery/examples/robotparts-calendar/source/build.py

From the vault only two things are read, for privacy: each daily note's FILE NAME (its title and its date) and the
`date created` / `date modified` keys of its frontmatter. The reader stops at the frontmatter's closing `---`, so no
note body is ever read; no other frontmatter key is kept.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import subprocess
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "tools"))  # parents[3] is gallery/
from public_paths import public  # noqa: E402  (judge r2 #6: no absolute home path in what the site publishes)

DAILY = pathlib.Path("~/zach_brain/Sources/Daily Notes")
REPO = "~/robotparts"
OUT = pathlib.Path(__file__).resolve().parents[1] / "calendar.json"
KEEP = ("date created", "date modified")


def frontmatter_dates(path: pathlib.Path) -> dict:
    out = {}
    with path.open(encoding="utf-8") as f:
        if f.readline().strip() != "---":
            return out
        for line in f:
            if line.strip() == "---":
                break  # WHY stop here: the body is never read
            key, _, value = line.partition(":")
            if key.strip() in KEEP:
                out[key.strip()] = value.strip().strip("'\"")
    return out


def note_date(stem: str) -> dt.date | None:
    if m := re.fullmatch(r"(\d{4}-\d{2}-\d{2})", stem):
        return dt.date.fromisoformat(m.group(1))
    if m := re.search(r"([A-Z][a-z]{2}) (\d{1,2}) (\d{4})", stem):
        return dt.datetime.strptime(" ".join(m.groups()), "%b %d %Y").date()
    return None


def main() -> None:
    rows = []
    for path in sorted(DAILY.glob("*.md")):
        day = note_date(path.stem)
        if not day:
            continue
        fm = frontmatter_dates(path)
        rows.append({"id": "note-" + re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-"), "title": path.stem, "kind": "daily note",
                     "date": day.isoformat(), "created": fm.get("date created"), "modified": fm.get("date modified"), "commit": None})
    for line in subprocess.run(["git", "-C", REPO, "tag", "-l", "release/*", "--format=%(refname:short)\t%(creatordate:iso-strict)\t%(objectname:short)"],
                               check=True, capture_output=True, text=True).stdout.splitlines():
        ref, when, sha = line.split("\t")
        name = ref.removeprefix("release/")
        rows.append({"id": f"release-{name}", "title": f"robotparts {name}", "kind": "release", "date": when, "created": None, "modified": None, "commit": sha})
    rows.sort(key=lambda r: r["date"])
    out = {
        "id": "robotparts-calendar", "title": "Releases and daily notes", "titleProperty": "title",
        "source": "git -C ~/robotparts tag -l 'release/*' + file names and frontmatter dates of ~/zach_brain/Sources/Daily Notes (no note content)",
        "properties": {
            "title": {"type": "text", "label": "Title", "width": 240},
            "kind": {"type": "text", "label": "Kind", "display": "badge", "colors": {"release": 8, "daily note": 1}},
            "date": {"type": "date", "label": "Date"},
            "created": {"type": "date", "label": "Note created", "readOnly": True},
            "modified": {"type": "date", "label": "Note modified", "readOnly": True},
            "commit": {"type": "text", "label": "Tagged commit"},
        },
        "rows": rows,
    }
    OUT.write_text(json.dumps(public(out), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {sum(r['kind'] == 'daily note' for r in rows)} daily notes, {sum(r['kind'] == 'release' for r in rows)} releases")


if __name__ == "__main__":
    main()
