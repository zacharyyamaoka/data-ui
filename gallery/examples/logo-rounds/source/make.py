"""Write this case's rows from robotparts' logo rounds and copy every round's SVGs (read-only source).

    python3 gallery/examples/logo-rounds/source/make.py

Reads each design/logos-2026-10-25*/ folder of robotparts' logo lane (LOGOS, default its worktree): every .svg
becomes a row, joined to its round's logos.json by file name (a proposal's lockup, mark or header; a reference
carried from an earlier round). An SVG no entry names (an animation, a dark variant, the live logo) is still a row,
named from its file. Score is the round's own: the sum of seven 1-5 criteria, out of 35; round 1 was not scored, so
its score is {value: null, why}. Copies the SVGs into svg/ as r<NN>-<file>.svg.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil

HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE.parent
SVG = CASE / "svg"
LOGOS = pathlib.Path(os.environ.get("LOGOS", "~/robotparts/.claude/worktrees/lane-logos/design"))


def round_of(folder: pathlib.Path) -> int:
    suffix = folder.name.removeprefix("logos-2026-10-25")
    return 1 if not suffix else ord(suffix) - ord("a") + 1


def entries(meta) -> list[tuple[str, dict]]:
    if isinstance(meta, list):
        return [("proposal", e) for e in meta]
    return [("reference", e) for e in meta.get("references", [])] + [("proposal", e) for e in meta.get("proposals", [])]


def title_from(file: str) -> str:
    stem = re.sub(r"^\d+-", "", file.removesuffix(".svg"))
    return stem.replace("-", " ").capitalize()


def main() -> None:
    shutil.rmtree(SVG, ignore_errors=True)
    SVG.mkdir()
    rows = []
    rounds = sorted((d for d in LOGOS.glob("logos-2026-10-25*") if d.is_dir()), key=round_of)
    for folder in rounds:
        n = round_of(folder)
        meta = json.loads((folder / "logos.json").read_text(encoding="utf-8"))
        criteria = meta.get("criteria") if isinstance(meta, dict) else None
        by_file: dict[str, tuple[str, str, dict]] = {}
        for role, e in entries(meta):
            for key, kind in (("file", "lockup"), ("mark", "mark"), ("header", "header"), ("file_dark", "lockup, dark")):
                if e.get(key):
                    by_file.setdefault(pathlib.Path(e[key]).name, (role, kind, e))
        for svg in sorted(folder.glob("*.svg")):
            role, kind, e = by_file.get(svg.name, ("extra", "extra", {}))
            if role == "reference":
                kind = f"reference {kind}"
            scores = e.get("scores")
            name = f"r{n:02d}-{svg.name}"
            shutil.copyfile(svg, SVG / name)
            rows.append({
                "id": name.removesuffix(".svg"),
                "round": n,
                "proposal": str(e["id"]) if e.get("id") is not None else None,
                "name": e.get("name") or title_from(svg.name),
                "kind": kind,
                "score": sum(scores) if scores else {"value": None, "why": "round 1 was not scored" if n == 1 else "not scored in its round"},
                "rationale": e.get("rationale"),
                "file": f"svg/{name}",
                "source": f"{folder.name}/{svg.name}",
            })
        print(f"round {n:2d} ({folder.name}): {sum(1 for r in rows if r['round'] == n)} SVGs{'; criteria: ' + ', '.join(criteria) if criteria and n == 2 else ''}")
    data = {
        "id": "logo-rounds",
        "title": "robotparts logo rounds",
        "titleProperty": "name",
        "imageProperty": "file",
        "properties": {
            "name": {"type": "text", "label": "Name"},
            "round": {"type": "number", "label": "Round", "facet": True, "labels": {str(r): f"Round {r}" for r in range(1, 12)}},
            "proposal": {"type": "text", "label": "Proposal"},
            "kind": {"type": "text", "label": "Kind", "facet": True},
            "score": {"type": "number", "label": "Score", "unitText": "/ 35", "note": "the round's own: seven criteria, 1-5 each"},
            "rationale": {"type": "text", "label": "Rationale"},
            "file": {"type": "text", "label": "SVG", "media": "image"},
            "source": {"type": "text", "label": "Source file"},
        },
        "rows": rows,
    }
    (CASE / "logos.json").write_text(json.dumps(data, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    size = sum((CASE / r["file"]).stat().st_size for r in rows)
    print(f"logos.json: {len(rows)} rows over {len(rounds)} rounds, {size:,} bytes of SVG")


if __name__ == "__main__":
    main()
