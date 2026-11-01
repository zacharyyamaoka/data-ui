#!/usr/bin/env python3
"""Copy the 256 px thumbnail of every object in objects.json from BAM's object library into thumbs/.
Usage: python3 build.py [library] [out_dir]

WHY objects.json is no longer rebuilt here (2026-10-27): this scenario first flattened the whole library (2,196
instances), whose tags name BAM's customers, and main carried it. objects.json is now the public sample (366 of the
2,196: open-licence scans and BAM's generated primitives), copied verbatim from the object-db-shelf gallery case
(lane/object-db-public 809e9b2); this script only fetches the pictures for those rows, so a rebuild cannot bring the
private rows back. tools/deny-scan.mjs --tree refuses the tree if it ever does.
"""
import json
import pathlib
import shutil
import sys

LIBRARY = pathlib.Path("~/bam-waste-objects")
OUT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    library = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else LIBRARY
    out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else OUT
    rows = json.loads((out / "objects.json").read_text())["rows"]
    (out / "thumbs").mkdir(parents=True, exist_ok=True)
    by_name = {p.name: p for p in (library / "objects").glob("*/*.webp")}
    copied = 0
    for row in rows:
        name = pathlib.PurePosixPath(row.get("thumbnail") or "").name
        if name and name in by_name:
            shutil.copyfile(by_name[name], out / "thumbs" / name)
            copied += 1
    print(f"{copied} of {len(rows)} thumbnails -> {out / 'thumbs'}")


if __name__ == "__main__":
    main()
