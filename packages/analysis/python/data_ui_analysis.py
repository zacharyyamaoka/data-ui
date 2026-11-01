"""Analyses, data-ui's third tier, for build scripts (docs/peps/0007-analyses.md, CONTRACT §19): the Python twin of
packages/analysis/src/format.js. Stdlib only, beside data_ui_base.py (it reads the frontmatter and every .base with
that module), so a static site's build can list analyses, read their frontmatter and find their embeds the way the
page does. tools/test_analysis_py.py runs both readers on the same files and requires the same answers.

    import data_ui_analysis as A
    front, body, body_line, problems = A.read_analysis(text)
    rows = [A.analysis_row(slug, front, url=f"/analysis/{slug}/") for slug, front in ...]
    A.build_index(folder)        # {"analyses": [{"src": "x.md", "row": {...}}]} for <data-analyses src="index.json">
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
# beside it in dist/python/; in the source tree data_ui_base.py is packages/core/python/
for _where in (HERE, HERE.parents[1] / "core" / "python"):
    if (_where / "data_ui_base.py").is_file() and str(_where) not in sys.path:
        sys.path.insert(0, str(_where))
import data_ui_base  # noqa: E402  the .base reader shipped beside this file

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
STATUSES = ("draft", "open", "decided", "superseded")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def _empty(value) -> bool:
    return value is None or value == "" or (isinstance(value, list) and not value)


def _list(value) -> list[str]:
    items = value if isinstance(value, list) else ([] if _empty(value) else [value])
    return [str(item).strip() for item in items if str(item).strip()]


def split_frontmatter(text: str):
    """(yaml or None, body, the body's first line)."""
    src = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    m = re.match(r"---[ \t]*\n((?:.*\n)*?)?---[ \t]*(?:\n|$)", src)
    if not m:
        return None, src, 1
    yaml = m.group(1) or ""
    lines = len(yaml.split("\n")) - 1 if yaml else 0
    return yaml, src[m.end():], lines + 3


def read_analysis(text: str):
    """(front, body, body_line, problems): the file read with data-ui's own reader, and what PEP 0002 §4 asks."""
    yaml, body, body_line = split_frontmatter(text)
    if yaml is None:
        return {}, body, body_line, [{"line": 1, "message": "no frontmatter: the file must start with --- and a title:"}]
    try:
        front = data_ui_base.loads(yaml) if yaml.strip() else {}
        if not isinstance(front, dict):
            raise data_ui_base.BaseSyntaxError("it is not a list of key: value lines")
    except (data_ui_base.BaseSyntaxError, ValueError) as error:
        return {}, body, body_line, [{"line": 2, "message": f"frontmatter does not parse: {error}"}]
    lines = yaml.split("\n")

    def at(key):
        for n, line in enumerate(lines):
            if re.match(rf"{key}\s*:", line):
                return n + 2
        return 1

    problems = []
    for key in ("title", "question"):
        if not (isinstance(front.get(key), str) and front[key].strip()):
            problems.append({"line": at(key), "message": f"{key}: is required"})
    status = front.get("status")
    if not _empty(status) and status not in STATUSES:
        problems.append({"line": at("status"), "message": f"status: must be one of {', '.join(STATUSES)} (it is {status})"})
    if not _empty(front.get("parts")) and not isinstance(front.get("parts"), list):
        problems.append({"line": at("parts"), "message": "parts: must be a list of part ids"})
    decision = front.get("decision")
    if not _empty(decision) and str(decision) not in _list(front.get("parts")):
        problems.append({"line": at("decision"), "message": f"decision: {decision} is not one of parts:"})
    date = front.get("date")
    if not _empty(date) and not DATE_RE.match(str(date)):
        problems.append({"line": at("date"), "message": f"date: must be YYYY-MM-DD (it is {date})"})
    return front, body, body_line, problems


def blocks_of(body: str, start: int = 1) -> list[dict]:
    """The body's blocks, as static/analysis.js blocksOf reads them."""
    lines = body.split("\n")
    out, prose, prose_line = [], [], 0

    def flush():
        nonlocal prose
        if any(line.strip() for line in prose):
            out.append({"kind": "markdown", "text": "\n".join(prose).strip("\n"), "line": prose_line})
        prose = []

    def add(line, n):
        nonlocal prose_line
        if not prose:
            prose_line = start + n
        prose.append(line)

    i = 0
    while i < len(lines):
        line = lines[i]
        fence = re.match(r"\s*(`{3,}|~{3,})\s*([\w-]*)\s*$", line)
        if fence:
            mark, lang = fence.groups()
            close = re.compile(rf"\s*{re.escape(mark[0])}{{{len(mark)},}}\s*$")
            j = i + 1
            while j < len(lines) and not close.match(lines[j]):
                j += 1
            if lang.lower() == "base":
                flush()
                out.append({"kind": "base", "text": "\n".join(lines[i + 1:j]), "line": start + i})
            else:
                for k in range(i, min(j, len(lines) - 1) + 1):
                    add(lines[k], k)
            i = j + 1
            continue
        embed = re.match(r"\s*!\[\[([^\]|#]+?\.base)(?:#([^\]|]+))?(?:\|[^\]]*)?\]\]\s*$", line)
        if embed:
            flush()
            out.append({"kind": "embed", "name": embed.group(1).strip(), "view": (embed.group(2) or "").strip() or None, "line": start + i})
            i += 1
            continue
        callout = re.match(r">\s*\[!([\w-]+)\]([+-]?)\s*(.*)$", line)
        if callout:
            flush()
            text, j = [], i + 1
            while j < len(lines) and lines[j].startswith(">"):
                text.append(re.sub(r"^>\s?", "", lines[j]))
                j += 1
            out.append({"kind": "callout", "type": callout.group(1).lower(), "fold": callout.group(2), "title": callout.group(3).strip(),
                        "text": "\n".join(text), "line": start + i})
            i = j
            continue
        add(line, i)
        i += 1
    flush()
    return out


def datasets_of(doc: dict) -> list[dict]:
    """A dashboard's datasets as data-ui names them (static/analysis.js datasetsOf)."""
    out = [{"name": name, "data": entry if isinstance(entry, str) else (entry or {}).get("data")}
           for name, entry in (doc.get("datasets") or {}).items()]
    data = doc.get("data")
    if isinstance(data, str) and not any(d["data"] == data for d in out):
        out.append({"name": re.sub(r"\.[^.]+$", "", data.rsplit("/", 1)[-1]), "data": data})
    return out


# --- the catalog the checker and the pages read (app data, from the built site) -----------------------------------


def analysis_row(slug: str, front: dict, lookup=lambda _id: None, url: str | None = None, path: str | None = None) -> dict:
    """format.js analysisRow: the list's row for one analysis."""
    ids = _list(front.get("parts"))
    decision = None if _empty(front.get("decision")) else str(front["decision"])
    chosen = lookup(decision) if decision else None
    text = lambda key: front[key] if isinstance(front.get(key), str) and front[key].strip() else None
    return {
        "id": slug, "title": text("title") or slug, "question": text("question"),
        "status": front.get("status") if front.get("status") in STATUSES else "draft",
        "parts": [((lookup(i) or {}).get("name")) or i for i in ids], "part_ids": ids, "parts_count": len(ids),
        "decision": ((chosen or {}).get("name") or decision) if decision else None, "decision_id": decision,
        "date": None if _empty(front.get("date")) else str(front["date"]), "author": text("author"),
        "tags": _list(front.get("tags")), "visibility": "public" if front.get("visibility") == "public" else "private",
        "url": url, "path": path,
    }


def build_index(folder, url=lambda slug: f"{slug}.html", lookup=lambda _id: None) -> dict:
    """<data-analyses src="index.json">'s file for every <slug>.md in `folder`: {"analyses": [{"src", "row"}]}."""
    out = []
    for path in sorted(pathlib.Path(folder).glob("*.md")):
        if not SLUG_RE.match(path.stem):
            continue
        front = read_analysis(path.read_text(encoding="utf-8"))[0]
        out.append({"src": path.name, "row": analysis_row(path.stem, front, lookup=lookup, url=url(path.stem), path=path.name)})
    return {"format": "data-ui-analyses/1", "analyses": out}


if __name__ == "__main__":
    print(json.dumps(build_index(sys.argv[1] if len(sys.argv) > 1 else "."), indent=1, ensure_ascii=False))
