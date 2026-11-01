"""Write analyses.json, the list's rows, from this case's analyses (docs/peps/0007-analyses.md).

    python3 gallery/examples/analyses/source/build.py

data_ui_analysis.build_index reads each <slug>.md's frontmatter the way the page does; the rows link to the pages the
site writes beside them (<slug>.html). tools/test_analysis_py.py checks the file is current.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "packages" / "analysis" / "python"))
import data_ui_analysis  # noqa: E402

PROPERTIES = {"title": {"type": "text", "label": "Analysis"}, "question": {"type": "text", "label": "Question"},
              "status": {"type": "text", "label": "Status"}, "parts": {"type": "list", "label": "Parts considered"},
              "part_ids": {"type": "list", "hidden": True}, "parts_count": {"type": "number", "label": "Parts"},
              "decision": {"type": "text", "label": "Decision"}, "decision_id": {"type": "text", "hidden": True},
              "date": {"type": "date", "label": "Date"}, "author": {"type": "text", "label": "Author"},
              "tags": {"type": "list", "label": "Tags"}, "visibility": {"type": "text", "label": "Visibility"},
              "url": {"type": "text", "hidden": True}, "path": {"type": "text", "label": "File"}}


def names() -> dict:
    """id -> {name}: the actuators' names, so a row's parts and decision read as names (the element's lookup)."""
    data = json.loads((HERE.parent / "robotparts-actuators" / "actuators.json").read_text(encoding="utf-8"))
    rows = data["rows"] if isinstance(data, dict) else data
    return {row["id"]: {"name": row.get("name")} for row in rows}


def dataset() -> dict:
    known = names()
    index = data_ui_analysis.build_index(HERE, lookup=known.get)
    return {"id": "data-ui-analyses", "title": "Analyses", "titleProperty": "title", "linkProperty": "url",
            "properties": PROPERTIES, "rows": [a["row"] for a in index["analyses"]]}


if __name__ == "__main__":
    (HERE / "analyses.json").write_text(json.dumps(dataset(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {HERE / 'analyses.json'}")
