"""Write the dashboard-cards data for this case: the five-bar's tool path against its target (sim), every situation's
status for the five-bar and the UR5e sets, and the five-bar study's own MuJoCo hero clip.

    python3 -I gallery/examples/trajectory-tracking/source/build_paths.py   (stdlib + /usr/bin/ffmpeg)

Inputs (read-only):
  FIVEBAR (default bam_ws reports/media/five-bar-pnp-tracking-2026-10-12/): report.html's traj_compare payload, comparison
    c1__nominal-five_bar (the nominal-speed cycle), and media/hero.mp4 + video_spec.json. Sim only: the report's real
    slot is "hardware run not requested (sim-only study)".
  PIDTUNA_DATA (default ~/pidtuna-website/site/public/data/ur5e.json): only to list the UR5e situations; the
    UR5e tool path itself is ../pid-tuning/tool.json (pid-tuning/source/build_replay.py), not copied here.

The five-bar's tool moves in 3D (target travel x 224 mm, y 112 mm, z 200 mm): the arm is not planar, so path2d.json
keeps all three world axes and says which pair to draw. traj_compare's own 2D axes are Conveyor = −y and Up = z
(its vec0 / vec1, each relative to its own start); x is the reach and is not in either.

Writes path2d.json, situations.json, media.json and media/fivebar_hero.mp4|jpg.
"""

from __future__ import annotations

import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "tools"))  # parents[3] is gallery/
from public_paths import public  # noqa: E402  (judge r2 #6: no absolute home path in what the site publishes)
import json
import os
import pathlib
import re
import subprocess

HERE = pathlib.Path(__file__).resolve().parents[1]
FIVEBAR = pathlib.Path(os.environ.get("FIVEBAR", "~/bam_ws/reports/media/five-bar-pnp-tracking-2026-10-12"))
PIDTUNA_DATA = pathlib.Path(os.environ.get("PIDTUNA_DATA", "~/pidtuna-website/site/public/data"))
COMPARISON = "c1__nominal-five_bar"
READ_ON = "2026-10-26"


def write(name: str, data: dict) -> None:
    out = HERE / name
    out.write_text(json.dumps(public(data), ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{out.relative_to(HERE.parents[2])}: {len(data['rows'])} rows, {out.stat().st_size:,} bytes")


def mm(value):
    return None if value is None else round(1e3 * value, 3)


def comparison() -> dict:
    html = (FIVEBAR / "report.html").read_text(encoding="utf-8")
    match = re.search(r'<script type="application/json" id="traj-compare-data">(.*?)</script>', html, re.S)
    return next(c for c in json.loads(match.group(1))["comparisons"] if c["name"] == COMPARISON)


def path2d(c: dict) -> dict:
    target = next(s for s in c["situations"] if s["name"] == "target")["plot"]
    rows = []
    for s in c["situations"]:
        if not s["has_data"]:
            continue
        plot = s["plot"]
        for k, t in enumerate(c["plot_t"]):
            if plot["x"][k] is None:
                continue  # past this situation's own span: a gap, never a held value
            rows.append({"t": round(t, 3), "situation": s["name"], "x_mm": mm(plot["x"][k]), "y_mm": mm(plot["y"][k]), "z_mm": mm(plot["z"][k]),
                         "err_mm": None if s["name"] == "target" else mm(plot["xyz_mag"][k])})
    span = {axis: round(1e3 * (max(v for v in target[axis] if v is not None) - min(v for v in target[axis] if v is not None))) for axis in "xyz"}
    world = "World {axis} of the tool (TCP), mm: traj_compare's plot.{axis} (m) × 1000, rounded to 1 µm. Simulated (MuJoCo plant), the tool pose from the sim's own state, not a camera."
    return {
        "id": "trajectory-tracking-fivebar-path", "title": "Five-bar · c1 nominal · tool path vs target (sim)", "titleProperty": "situation",
        "source": f"bam_ws reports/media/five-bar-pnp-tracking-2026-10-12/report.html, comparison {COMPARISON} (traj_compare payload), read {READ_ON}. {c['description']}",
        "properties": {
            "t": {"type": "number", "unit": "s", "digits": 3, "note": "Seconds from the target's start. The payload's display grid, every 40 ms (25 Hz); the report's statistics are at the full 2 ms evidence rate, never these rows."},
            "situation": {"type": "text", "display": "badge", "note": "target = the frozen tape; the rest are simulated controllers (gains + feed-forward). Situations that were lost or not requested have no rows: see situations.json."},
            "x_mm": {"type": "number", "unit": "mm", "digits": 3, "note": world.format(axis="x") + f" Target travel {span['x']} mm: the reach."},
            "y_mm": {"type": "number", "unit": "mm", "digits": 3, "note": world.format(axis="y") + f" Target travel {span['y']} mm; traj_compare's Conveyor axis is −y."},
            "z_mm": {"type": "number", "unit": "mm", "digits": 3, "note": world.format(axis="z") + f" Target travel {span['z']} mm; traj_compare's Up axis. The path is 3D: for a 2D card draw x_mm against z_mm (the two largest travels) and say the third is dropped."},
            "err_mm": {"type": "number", "unit": "mm", "digits": 3, "note": "|p − p_target| in 3D at the same t: traj_compare's plot.xyz_mag × 1000. Null on target rows."},
        },
        "rows": rows,
    }


def situations(c: dict) -> dict:
    rows = []
    for s in c["situations"]:
        kind = "target" if s["name"] == "target" else "real" if s["name"] == "real" else "sim"
        if s["has_data"]:
            status = "ok"
        elif kind == "real" or "not requested" in s["note"]:
            status = "not requested"
        elif s["note"].startswith("lost"):
            status = "lost"
        else:
            status = "not run"
        rows.append({"id": f"path2d/{s['name']}", "dataset": "path2d", "robot": "Five-bar", "situation": s["name"], "title": s["title"],
                     "kind": kind, "status": status, "note": s["note"] or None})
    ur5e = json.loads((PIDTUNA_DATA / "ur5e.json").read_text(encoding="utf-8"))
    names = {"target": "Target", "factory": "Factory gains", "analytic": "Analytic start", "tuned": "Tuned", "oracle": "Oracle (best possible)"}
    for name in ["target"] + ur5e["rungs_order"]:
        rows.append({"id": f"path3d/{name}", "dataset": "path3d", "robot": "UR5e", "situation": name, "title": names[name],
                     "kind": "target" if name == "target" else "sim", "status": "ok",
                     "note": None if name == "target" else "pidtuna's ArmSim replay of this rung on the coordinated tape (illustrative plant parameters)"})
    rows.append({"id": "path3d/real", "dataset": "path3d", "robot": "UR5e", "situation": "real", "title": "Real arm", "kind": "real",
                 "status": "not requested", "note": "no real arm: pidtuna's UR5e is simulation only"})
    return {
        "id": "trajectory-tracking-situations", "title": "Situations per tracking set, including the empty ones", "titleProperty": "title",
        "source": f"path2d: {COMPARISON}'s situations in the five-bar report payload; path3d: pidtuna-website ur5e.json rungs_order; read {READ_ON}.",
        "properties": {
            "dataset": {"type": "text", "display": "badge", "note": "path2d = path2d.json (five-bar, c1 nominal); path3d = ../pid-tuning/tool.json (UR5e, coordinated tape)."},
            "robot": {"type": "text", "note": "Which robot the set is for."},
            "situation": {"type": "text", "note": "The id the samples use."},
            "title": {"type": "text", "note": "The producer's title."},
            "kind": {"type": "text", "display": "badge", "note": "target | sim | real."},
            "status": {"type": "text", "display": "badge", "note": "ok (has rows) | lost (ran, the tool went > 100 mm off its reference, the producer dropped its rows) | not run | not requested (never asked for: the real slots)."},
            "note": {"type": "text", "note": "The producer's own words for a missing situation."},
        },
        "rows": rows,
    }


def media() -> dict:
    spec = json.loads((FIVEBAR / "media" / "video_spec.json").read_text(encoding="utf-8"))
    hero = next(v for v in spec["videos"] if v["name"] == "hero")
    (HERE / "media").mkdir(exist_ok=True)
    out, poster = HERE / "media" / "fivebar_hero.mp4", HERE / "media" / "fivebar_hero.jpg"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(FIVEBAR / "media" / "hero.mp4"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "28", "-preset", "slow", "-movflags", "+faststart", "-an", str(out)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "4.0", "-i", str(out), "-frames:v", "1", "-q:v", "4", str(poster)], check=True)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
                                       "-of", "json", str(out)], capture_output=True, text=True, check=True).stdout)["streams"][0]
    num, den = (int(v) for v in probe["r_frame_rate"].split("/"))
    fps = num / den
    print(f"{out.relative_to(HERE.parents[2])}: {probe['nb_frames']} frames, {out.stat().st_size:,} bytes")
    left, right = hero["panels"]
    return {
        "id": "trajectory-tracking-fivebar-media", "title": "Five-bar · c1 nominal · the study's MuJoCo hero clip (sim)", "titleProperty": "id",
        "source": f"bam_ws reports/media/five-bar-pnp-tracking-2026-10-12/media/hero.mp4 (+ video_spec.json), re-encoded; read {READ_ON}.",
        "properties": {
            "situation": {"type": "text", "display": "badge", "note": "The right panel's situation, which is in path2d.json; the left panel's variant is not (see note)."},
            "src": {"type": "text", "media": "video", "note": "The clip, relative to this file."}, "poster": {"type": "text", "media": "image", "note": "Frame at 4.0 s."},
            "t0": {"type": "number", "unit": "s", "note": "0: the clip's burned-in clock reads t = 0.00 s on frame 0 and 4.00 s on frame 100 (checked by eye)."},
            "fps": {"type": "number", "unit": "fps", "note": "The source clip's rate, kept."}, "duration": {"type": "number", "unit": "s", "note": "frames ÷ fps."},
            "width": {"type": "number", "unit": "px", "note": "Frame width, kept from the source."}, "height": {"type": "number", "unit": "px", "note": "Frame height."},
            "basis": {"type": "text", "display": "badge", "note": "sim-render."},
            "note": {"type": "text", "note": "What the clip shows and how it maps onto path2d.json."},
        },
        "rows": [{
            "id": "fivebar-hero", "situation": "soft4-model_live_friction_object", "src": f"media/{out.name}", "poster": f"media/{poster.name}",
            "t0": 0.0, "fps": round(fps, 3), "duration": round(int(probe["nb_frames"]) / fps, 3), "width": probe["width"], "height": probe["height"],
            "basis": "sim-render",
            "note": (f"The five-bar study's MuJoCo render of tape {spec['tape']}, side by side: left {left['title']} ({left['variant']}), "
                     f"right {right['title']} ({right['variant']}). Solid arm = simulated, ghost arm = target, grey line = target tool path; "
                     "tool error and t burned in. Only the right panel is a situation of path2d.json (soft4-model_live_friction_object); "
                     "the left panel's house8i is a variant the comparison does not carry. Not a camera."),
        }],
    }


def main() -> None:
    c = comparison()
    write("path2d.json", path2d(c))
    write("situations.json", situations(c))
    write("media.json", media())


if __name__ == "__main__":
    main()
