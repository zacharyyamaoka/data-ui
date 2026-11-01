"""The playback proposals' data: a small slice of the card catalog's real rows (../dashboard-cards, itself cut from
pid-tuning's UR5e replay, sim), so every proposal can be tried against videos and time series on one clock
(docs/peps/0005-dashboard-cards.md §4b). Nothing here is invented; each file's `source` says where its rows came from.
Run: python3 -I gallery/examples/playback-proposals/source/build.py"""

import json
import pathlib
import shutil

HERE = pathlib.Path(__file__).resolve().parents[1]
SRC = HERE.parent / "dashboard-cards"


def load(name):
    return json.loads((SRC / name).read_text(encoding="utf-8"))


def write(name, d, rows, source, keep=None):
    out = {k: v for k, v in d.items() if k != "rows"}
    if keep:
        out["properties"] = {k: v for k, v in out.get("properties", {}).items() if k in keep}
        out.pop("skeleton", None)
        rows = [{k: v for k, v in r.items() if k in keep or k == "id"} for r in rows]
    out["rows"] = rows
    out["source"] = source
    (HERE / name).write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"{name}: {len(rows)} rows")


s = load("samples.json")
write("samples.json", s, [r for r in s["rows"] if r["joint"] == "elbow_joint"],
      "dashboard-cards/samples.json (pid-tuning, UR5e, sim): the elbow joint only")
t = load("tool.json")
write("tool.json", t, t["rows"], "dashboard-cards/tool.json (pid-tuning, UR5e, sim): the tool path only, no stick robot",
      keep={"t", "situation", "px", "py", "pz", "err_mm"})
m = load("media.json")
(HERE / "media").mkdir(exist_ok=True)
for r in m["rows"]:
    for k in ("src", "poster"):
        shutil.copy(SRC / r[k], HERE / r[k])
write("media.json", m, m["rows"], "dashboard-cards/media.json (pid-tuning): MuJoCo renders of target, factory, tuned")
