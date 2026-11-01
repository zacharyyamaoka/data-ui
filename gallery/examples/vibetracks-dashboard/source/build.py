"""Vibe Tracks' real tracks, KPI points and check runs, copied small for the dashboard gallery cases.

Reads (read-only) Zach's owner bundle and the producer folders it points at:
  ~/.vibetracks/bundle/state.json, ~/.vibetracks/bundle/tracks/<id>.json   (vt state's output, vt-state/1)
  ~/vt/{zach,bam}/producers/<name>/{kpi_series.jsonl,runs_table.jsonl}   (vt-kpi/1 producers)
Writes, beside this folder: tracks.json, kpis.json, runs.json (data-ui's runtime dataset shape, CONTRACT §3).

Run: python3 -I gallery/examples/vibetracks-dashboard/source/build.py

Public-safe rule (docs/SPEC.md §13): grasping's figures never enter the gallery. The grasping track keeps its row and
title; its headline is null with the reason, and none of its KPI points or runs are copied.
"""

import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "tools"))  # parents[3] is gallery/
from public_paths import public  # noqa: E402  (judge r2 #6: no absolute home path in what the site publishes)
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parents[1]
BUNDLE = pathlib.Path.home() / ".vibetracks" / "bundle"
ROOTS = [pathlib.Path("~/vt/zach"), pathlib.Path("~/vt/bam")]
PRIVATE = {"grasping"}
WHY_PRIVATE = "private: grasping's figures stay out of the gallery (data-ui SPEC §13)"
READ_ON = "2026-10-26"
POINTS_PER_KPI = 30
BASIS = {"measured": "measured", "sealed": "measured", "estimate": "estimate", "stand-in": "stand-in", "claimed": "claimed"}


def jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def producer_dir(folder):
    for root in ROOTS:
        p = root / folder
        if p.is_dir():
            return p
    return None


def short_unit(u):
    return u if u else None


def main():
    state = json.loads((BUNDLE / "state.json").read_text(encoding="utf-8"))
    tracks = state["tracks"]
    by_id = {t["id"]: t for t in tracks}

    def root_of(t):
        seen = set()
        while t.get("parent") and t["parent"] in by_id and t["id"] not in seen:
            seen.add(t["id"])
            t = by_id[t["parent"]]
        return t

    track_rows, kpi_rows, run_rows = [], [], []
    for t in sorted(tracks, key=lambda x: (x.get("priority") or 99, x["id"])):
        detail = json.loads((BUNDLE / "tracks" / f"{t['id']}.json").read_text(encoding="utf-8"))
        private = t["id"] in PRIVATE
        h = t.get("headline") or {}
        if private:
            headline = {"value": None, "why": WHY_PRIVATE}
        elif h.get("kpi"):
            headline = {"value": h.get("value"), "unit": short_unit(h.get("unit")), "basis": BASIS.get(h.get("status")),
                        "asOf": h.get("t"), "source": f"vt state headline · {h.get('kpi')}"}
            if headline["value"] is None:
                headline = {"value": None, "why": "no reading yet"}
            headline = {k: v for k, v in headline.items() if v is not None or k == "value"}
        else:
            headline = {"value": None, "why": "no headline KPI"}
        root = root_of(t)
        track_rows.append({
            "id": t["id"], "title": t["title"], "parent": t.get("parent"),
            "parent_title": by_id[t["parent"]]["title"] if t.get("parent") in by_id else None,
            "area": root["title"], "children": len(t.get("children") or []),
            "health": t.get("health"), "state": (t.get("state") or {}).get("label"),
            "priority": t.get("priority"),
            "headline_kpi": None if private else h.get("title"), "headline": headline,
            "headline_better": None if private else h.get("direction"),
            "kpis": len(detail.get("kpis") or []),
        })
        if private:
            continue
        catalog = {k["id"]: k for k in detail.get("kpis") or []}
        for ref in (detail.get("refs") or {}).get("kpi") or []:
            folder = ref["folder"]
            pdir = producer_dir(folder)
            if not pdir:
                continue
            producer = folder.split("/")[-1]
            # ---- KPI points: whole-bench points (no slice) of the track's level-0 and level-1 KPIs, newest 30 each
            if (pdir / "kpi_series.jsonl").exists():
                keep = {k for k, c in catalog.items() if c.get("level") in (0, 1) and c.get("folder") == folder}
                series = {}
                for p in jsonl(pdir / "kpi_series.jsonl"):
                    if p.get("kpi") in keep and not p.get("slice") and p.get("value") is not None and isinstance(p.get("value"), (int, float)):
                        series.setdefault(p["kpi"], []).append(p)
                for kid, pts in series.items():
                    pts.sort(key=lambda p: p["t"])
                    c = catalog[kid]
                    for i, p in enumerate(pts[-POINTS_PER_KPI:]):
                        src = p.get("source") or {}
                        kpi_rows.append({
                            "id": f"{t['id']}:{kid}:{i:02d}", "track": t["id"], "track_title": t["title"],
                            "kpi": kid, "label": c.get("title") or kid, "level": c.get("level"),
                            "t": p["t"], "better": c.get("direction"),
                            "value": {k: v for k, v in {"value": p["value"], "unit": short_unit(c.get("unit")),
                                      "basis": BASIS.get(p.get("status")), "n": p.get("n"),
                                      "source": f"{folder}/kpi_series.jsonl · {src.get('code_sha') or ''}".strip(" ·"),
                                      "asOf": p["t"]}.items() if v is not None},
                            "role": (p.get("labels") or {}).get("role"), "sha": (src.get("code_sha") or "")[:8] or None,
                        })
            # ---- check runs: every producer whose runs count passes and fails, normalised to one shape
            if (pdir / "runs_table.jsonl").exists():
                for r in jsonl(pdir / "runs_table.jsonl"):
                    m, f = r.get("metrics") or {}, r.get("facets") or {}
                    if "checks" in m and "passed" in m:          # vt spec runs (PEP 0012)
                        kind, passed, failed, skipped, total = "tests", m["passed"], m.get("failed"), m.get("skipped"), m["checks"]
                        secs = m.get("duration_s")
                    elif "checks_total" in m:                     # fivebar's ladder
                        kind, passed, total = "checks", m["checks_pass"], m["checks_total"]
                        failed, skipped, secs = (m.get("checks_fail") or 0) + (m.get("checks_error") or 0), m.get("checks_skipped"), m.get("seconds")
                    elif "runnable_goldens" in m:                 # pyblocks' goldens
                        kind, passed, failed, skipped, total = "goldens", m["runnable_green"], m.get("runnable_red"), m.get("runnable_grey"), m["runnable_goldens"]
                        secs = None
                    elif "gates_pass" in m:                       # tycoon-crm's parity gates
                        kind, passed, failed = "gates", m["gates_pass"], m.get("gates_fail")
                        skipped = m.get("gates_unmeasured")
                        total = (passed or 0) + (failed or 0) + (skipped or 0)
                        secs = None
                    else:
                        continue
                    if not total:
                        continue
                    run_rows.append({
                        "id": f"{producer}:{r['run_id']}", "run": r["run_id"], "track": t["id"], "track_title": t["title"],
                        "producer": producer, "kind": kind, "t": r.get("t"),
                        "suite": f.get("suite") or producer, "channel": f.get("channel"),
                        "branch": f.get("branch"), "sha": (f.get("sha") or f.get("code_sha") or f.get("commit") or "")[:8] or None,
                        "passed": passed, "failed": failed, "skipped": skipped, "checks": total,
                        "pass_rate": {"value": round(passed / total, 4), "unit": "share", "basis": "derived", "n": total,
                                      "source": f"{folder}/runs_table.jsonl · passed / checks"},
                        "seconds": round(secs, 1) if isinstance(secs, (int, float)) else None,
                    })

    run_rows.sort(key=lambda r: (r["t"] or "", r["id"]))
    kpi_rows.sort(key=lambda r: (r["track"], r["kpi"], r["t"]))
    source = (f"Zach's Vibe Tracks owner bundle (~/.vibetracks/bundle, vt-state/1, generated {json.loads((BUNDLE / 'bundle.json').read_text())['generated_at']}) "
              f"and its producer folders under ~/vt/{{zach,bam}}/producers, read {READ_ON}; grasping's figures left out (SPEC §13)")
    tprops = {
        "title": {"type": "text", "width": 230}, "parent": {"type": "text", "hidden": True},
        "parent_title": {"type": "text", "width": 140}, "area": {"type": "text", "width": 130, "display": "badge"},
        "children": {"type": "number", "width": 70, "note": "child tracks"},
        "health": {"type": "text", "width": 80, "display": "badge", "colors": {"green": 0, "yellow": 4, "red": 2}},
        "state": {"type": "text", "width": 110}, "priority": {"type": "number", "width": 60},
        "headline_kpi": {"type": "text", "width": 220, "note": "the track's L0 KPI, as vt state names it"},
        "headline": {"type": "number", "width": 120, "note": "the producer's newest headline value, never recomputed"},
        "headline_better": {"type": "text", "hidden": True}, "kpis": {"type": "number", "width": 60, "note": "KPIs in the track's catalogs"},
    }
    kprops = {
        "track": {"type": "text", "hidden": True}, "track_title": {"type": "text", "width": 180, "display": "badge"},
        "kpi": {"type": "text", "hidden": True}, "label": {"type": "text", "width": 220}, "level": {"type": "number", "width": 50},
        "t": {"type": "date", "width": 190}, "better": {"type": "text", "width": 70}, "value": {"type": "number", "width": 130},
        "role": {"type": "text", "width": 70}, "sha": {"type": "text", "width": 80},
    }
    rprops = {
        "run": {"type": "text", "width": 260}, "track": {"type": "text", "hidden": True}, "track_title": {"type": "text", "width": 170, "display": "badge"},
        "producer": {"type": "text", "width": 140}, "kind": {"type": "text", "width": 70, "display": "badge"}, "t": {"type": "date", "width": 190},
        "suite": {"type": "text", "width": 110}, "channel": {"type": "text", "width": 80}, "branch": {"type": "text", "width": 200},
        "sha": {"type": "text", "width": 80}, "passed": {"type": "number", "width": 70}, "failed": {"type": "number", "width": 70},
        "skipped": {"type": "number", "width": 70}, "checks": {"type": "number", "width": 70},
        "pass_rate": {"type": "number", "width": 90, "display": "bar", "note": "passed / checks of this run"},
        "seconds": {"type": "number", "width": 80, "unit": "s"},
    }
    out = {
        "tracks.json": {"id": "vibetracks-tracks", "title": "Vibe Tracks tracks (real, Oct 26 2026)", "titleProperty": "title", "source": source, "properties": tprops, "rows": track_rows},
        "kpis.json": {"id": "vibetracks-kpi-points", "title": "Vibe Tracks KPI points (real, newest 30 per KPI)", "titleProperty": "label", "source": source, "properties": kprops, "rows": kpi_rows},
        "runs.json": {"id": "vibetracks-check-runs", "title": "Vibe Tracks check runs (real: tests, checks, goldens, gates)", "titleProperty": "run", "source": source, "properties": rprops, "rows": run_rows},
    }
    for name, doc in out.items():
        text = json.dumps(public(doc), ensure_ascii=False, separators=(",", ":"), sort_keys=False)
        (HERE / name).write_text(text + "\n", encoding="utf-8")
        ids = [r["id"] for r in doc["rows"]]
        assert len(set(ids)) == len(ids), name
        print(f"{name}: {len(doc['rows'])} rows, {len(text) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
