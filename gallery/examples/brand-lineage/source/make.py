"""Rebuild proposals.json and thumbs/ from Brandbook's brands.json (read-only; another session owns it).

    python3 -I gallery/examples/brand-lineage/source/make.py ~/brandbook/src/data/brands.json

One row per proposal of every brand. `parents` follows Brandbook's own rule (src/lib/lineage.ts parentsOf): a
variant's own `parents` when it has them (a splice or a named source), else its round's `parents`, keeping only ids
that name a proposal of the same brand. Every parent claim's evidence is in brandbook/tools/lineage-notes.md; nothing
here adds or guesses an edge. Thumbnails are the 96 x 96 PNG marks brands.json carries as data: URIs, written out as
files so the page loads them like any photo."""

import base64
import shutil
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent


def main(src: str) -> None:
    data = json.loads(pathlib.Path(src).read_text(encoding="utf-8"))
    thumbs = HERE / "thumbs"
    shutil.rmtree(thumbs, ignore_errors=True)  # WHY: a proposal dropped upstream must not leave its picture behind
    rows = []
    for brand in data["brands"]:
        known = {v["id"] for v in brand["variants"]}
        rounds = {r["id"]: r for r in brand["rounds"]}
        order = {r["id"]: i + 1 for i, r in enumerate(brand["rounds"])}
        pick = (brand["language"].get("pick") or {}).get("variantId")
        (thumbs / brand["id"]).mkdir(parents=True, exist_ok=True)
        for v in brand["variants"]:
            rnd = rounds[v["round"]]
            own = v["parents"] if v["parents"] is not None else rnd["parents"]
            parents = [f"{brand['id']}/{p}" for p in own if p in known]
            head, _, b64 = v["thumb"].partition(",")
            assert head == "data:image/png;base64", head
            (thumbs / brand["id"] / f"{v['id']}.png").write_bytes(base64.b64decode(b64))
            score = v["score"]
            rows.append({
                "id": f"{brand['id']}/{v['id']}",
                "name": v["name"],
                "brand": brand["name"],
                "round": "Final" if rnd["kind"] == "final" else f"R{rnd['n']}",
                "round_n": order[v["round"]],
                "round_title": rnd["label"],
                "round_kind": rnd["kind"],
                "proposal": v["localId"],
                "status": v["status"],
                "score": score if score is not None else {"value": None, "why": "this round was not scored"},
                "score_max": v["scoreMax"],
                "parents": parents,
                "splice": len(parents) > 1,
                "thumb": f"thumbs/{brand['id']}/{v['id']}.png",
                "note": v["note"],
                "reply": rnd["reply"],
                # WHY plain text, not a link: the path is on Zach's machine; the published case never links a file path.
                # WHY "~/": a home path must not ship (tests/unit/no-home-paths.test.mjs)
                "report_path": re.sub(r"^/home/[^/]+/", "~/", rnd["report"]) if rnd["report"] else {"value": None, "why": "this round has no HTML report"},
                "date": rnd["date"],
                "final_pick": v["id"] == pick,
            })
    props = {
        "name": {"type": "text", "width": 220},
        "brand": {"type": "text", "width": 100},
        "round": {"type": "text", "width": 70, "note": "R<n> in the brand's own round order; Final = the shipped files"},
        "round_n": {"type": "number", "width": 70, "note": "the round's position in its brand, 1 = the first"},
        "round_title": {"type": "text", "width": 220},
        "round_kind": {"type": "text", "width": 80, "display": "badge", "note": "explore = fresh directions; vary = variants of one parent; splice = parts of two or more; polish = steps on the pick; final = the shipped files"},
        "proposal": {"type": "text", "width": 70, "note": "the id Zach used in that round's report"},
        "status": {"type": "text", "width": 80, "display": "badge", "colors": {"picked": 1, "liked": 2, "rejected": 0, "neutral": 0}, "note": "from Zach's replies; rejected only when he said so"},
        "score": {"type": "number", "width": 70},
        "score_max": {"type": "number", "width": 70},
        "parents": {"type": "list", "width": 220, "relation": True, "note": "the proposals this one was derived from (Brandbook's lineage rule); two or more = a splice"},
        "splice": {"type": "boolean", "width": 60},
        "thumb": {"type": "text", "width": 80, "display": "image", "media": True},
        "note": {"type": "text", "width": 320},
        "reply": {"type": "text", "width": 320, "note": "Zach's reply to the round, verbatim"},
        "report_path": {"type": "text", "width": 260, "note": "where the round's HTML report lives on Zach's machine (plain text: a file path is not a link on the published site)"},
        "date": {"type": "date", "width": 100},
        "final_pick": {"type": "boolean", "width": 60},
    }
    out = {
        "id": "brand-lineage",
        "title": "Brand proposals and where each came from",
        "titleProperty": "name",
        "imageProperty": "thumb",
        "source": f"brandbook src/data/brands.json, generated {data['generated']} (tools/extract_lineage.py; evidence in tools/lineage-notes.md)",
        "properties": props,
        "rows": rows,
    }
    (HERE / "proposals.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(rows)} proposals, {sum(1 for r in rows if r['parents'])} with parents, {sum(1 for r in rows if r['splice'])} splices")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "~/brandbook/src/data/brands.json")
