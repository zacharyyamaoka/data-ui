"""Print PyYAML's reading of each .base file as JSON lines: {"file", "doc"} or {"file", "error"}.

    python3 tools/yaml_oracle.py FILE.base [...]

The oracle for packages/core/src/base.js and packages/core/python/data_ui_base.py (tests/unit/base.test.mjs).
Dates PyYAML would make objects of are printed as their ISO text, the way the subset parsers keep them."""

import datetime
import json
import sys

import yaml


def plain(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k) if not isinstance(k, bool) and k is not None else json.dumps(k): plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


for path in sys.argv[1:]:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh.read())
        print(json.dumps({"file": path, "doc": plain(doc)}, ensure_ascii=False))
    except yaml.YAMLError as error:
        print(json.dumps({"file": path, "error": str(error).splitlines()[0]}))
