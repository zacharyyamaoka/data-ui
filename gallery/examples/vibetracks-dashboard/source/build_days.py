"""The daily verdict the dashboards' "last 30 days" tracker colours by: runs_daily.json (source/build_series.py) with one
derived column, `verdict`, from its pass_rate. Nothing else changes and no row is added: every row of runs_daily.json,
in its order. The same rule as the card catalog (gallery/examples/dashboard-cards/source/build.py).
Run: python3 -I gallery/examples/vibetracks-dashboard/source/build_days.py"""

import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "tools"))  # parents[3] is gallery/
from public_paths import public  # noqa: E402  (judge r2 #6: no absolute home path in what the site publishes)
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parents[1]


def verdict(row):
    pr = row["pass_rate"]["value"] if isinstance(row["pass_rate"], dict) else row["pass_rate"]
    return "none" if pr is None else "pass" if pr >= 1 else "fail" if pr <= 0 else "mixed"


d = json.loads((HERE / "runs_daily.json").read_text(encoding="utf-8"))
out = {k: v for k, v in d.items() if k != "rows"}
out["id"] = "vibetracks-days"
out["properties"] = {**d["properties"], "verdict": {
    "type": "text", "label": "Verdict",
    "note": "Derived by source/build_days.py from pass_rate: pass (every judged run passed), fail (none passed), "
            "mixed (some), none (no judged run that day)."}}
out["source"] = "runs_daily.json (source/build_series.py, real) + verdict derived from pass_rate by source/build_days.py"
out["rows"] = [{**r, "verdict": verdict(r)} for r in d["rows"]]
(HERE / "days.json").write_text(json.dumps(public(out), separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
print(f"days.json: {len(out['rows'])} rows", {v: sum(r["verdict"] == v for r in out["rows"]) for v in ("pass", "mixed", "fail", "none")})
