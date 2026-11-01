"""The Camera template's data (PEP 0010 P4, docs/peps/0010-robotics-playback.md §6, the camera.png mock): the 1-DOF rack's
two RealSense cameras over six recording sessions of Oct 23 2026, as the trajectory contract's tables
(gallery/robotics/CONTRACT.md): runs.json, samples.csv (+ samples.schema.json), media.json, devices.json and
media/<session>.mp4|jpg beside this folder. The frame stamps and the footage are real; there is no depth and no
hyperspectral capture, so media.json has no `depth` or `band` row and those cards say so.

    python3 -B -I gallery/examples/robotics-camera/source/build.py        (numpy + /usr/bin/ffmpeg; the archive is read-only)

Inputs (read-only): RACK (default /archive/datasets/bam_rig), rack_2026-10-23/<session>/cameras/cam_<serial>.npz
(`hw_ms`: one hardware stamp per frame, in the RealSense global time domain, ms; `wall`: the host clock) and
cam_<serial>.mp4 (the same frames, in order: the build checks the count), plus the session's plans/ file for its purpose.

What it writes:
  - samples.csv: EVERY frame interval of both cameras in the six sessions the mock drew (01a, 01c, 02, 04, 05, 06: the
    first six whose camera files read), one row per interval: t (s from the session's first frame, either camera), run (the
    session), device (the camera), frame_dt_ms = hw_ms[k] − hw_ms[k−1], written exactly (the shortest decimal that
    reads back as the same float64), so a histogram of the file IS numpy's histogram of np.diff(hw_ms).
  - media.json + media/: one clip per CAN 14 session (01a, 01c, 02) from camera 218622274411, the camera that sees CAN
    14's plate: resampled on a uniform 30 fps grid over the recording (each grid frame the camera frame whose hw stamp is
    nearest, so frame k's clock time is exactly t0 + k / 30), cropped to CAN 14's plate, brightened (gamma 0.5), CAN 14's
    tag boxed in orange (the sim-to-real case's crop and tag box, from the 10-24 tag detection). WHY only CAN 14's: PEP
    0010 §13 Q5's default publishes no camera footage beyond CAN 14's; the other sessions and camera 218622276036 give
    stamps only.
  - runs.json: the three sessions with a clip (the rail's Session picker); devices.json: the two cameras.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import pathlib
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

import numpy as np

CASE = pathlib.Path(__file__).resolve().parents[1]
RACK = pathlib.Path(os.environ.get("RACK", "/archive/datasets/bam_rig"))
DAY = "rack_2026-10-23"
SESSIONS = ("session_01a", "session_01c", "session_02", "session_04", "session_05", "session_06")
CLIPS = ("session_01a", "session_01c", "session_02")     # CAN 14's sessions (plans/session_01a_can14_backlash.json …)
CAMERAS = ("218622274411", "218622276036")
CLIP_CAMERA = "218622274411"   # sees CAN 14's tag (the deployment record's camera map; sim-to-real's clips)
TAG_BOX = (552, 444, 648, 537)  # CAN 14's tag, full-resolution pixels (rack_2026-10-24 dataset/can14 clips.json tag_box)
CROP = (330, 200, 640, 400)     # x, y, width, height: the left plate with CAN 14's tag
FPS = 30
CRF = 30
LOCAL = ZoneInfo("America/Vancouver")
DEPLOYMENT = "1-DOF rack"
NOMINAL_MS = 1000.0 / 30


def device(serial: str) -> str:
    return f"RealSense {serial}"


def run_id(session: str) -> str:
    return f"{DAY.removeprefix('rack_2026-')}/{session}"


def purpose(session: str) -> str:
    """The session's plan, by its file name: plans/session_01a_can14_backlash.json -> "backlash" (CAN 14)."""
    sid = session.removeprefix("session_")
    for p in sorted((RACK / DAY / "plans").glob(f"session_{sid}_*.json")):
        rest = p.stem.removeprefix(f"session_{sid}_")
        m = re.match(r"can(\d+)_(.*)", rest)
        return (m.group(2).replace("_", " "), int(m.group(1))) if m else (rest.replace("_", " "), None)
    return ("recording", None)


def load(session: str, serial: str) -> dict:
    path = RACK / DAY / session / "cameras" / f"cam_{serial}.npz"
    with np.load(path) as a:   # WHY by key: frames.npy is 2.4 GB uncompressed; only the stamps are read
        return {"hw": np.asarray(a["hw_ms"], float), "wall": np.asarray(a["wall"], float), "fps": int(a["fps"]), "path": path}


def frames_in(video: pathlib.Path) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames",
                          "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True).stdout
    return int(out)


def clip(session: str, cam: dict, t_origin_ms: float) -> dict:
    """The session's clip from CLIP_CAMERA on a uniform FPS grid in hw time; frame k at t0 + k / FPS (s)."""
    video = RACK / DAY / session / "cameras" / f"cam_{CLIP_CAMERA}.mp4"
    stamps = cam["hw"]
    assert frames_in(video) == stamps.size, f"{video}: frame count != stamps"
    grid = np.arange(stamps[0], stamps[-1] + 1e-9, 1000.0 / FPS)
    nearest = np.abs(stamps[None, :] - grid[:, None]).argmin(axis=1) if grid.size * stamps.size < 4e7 else np.array([int(np.abs(stamps - g).argmin()) for g in grid])
    worst = float(np.max(np.abs(stamps[nearest] - grid)))
    x, y, w, h = CROP
    decoded = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"crop={w}:{h}:{x}:{y},lutyuv=y=gammaval(0.5)",
                              "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    block = np.frombuffer(decoded, np.uint8).reshape(-1, h, w)
    assert len(block) == stamps.size, f"{video}: decoded {len(block)} of {stamps.size} frames"
    x0, y0, x1, y1 = TAG_BOX[0] - x, TAG_BOX[1] - y, TAG_BOX[2] - x, TAG_BOX[3] - y
    out = CASE / "media" / f"{session}.mp4"
    out.parent.mkdir(exist_ok=True)
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(CRF), "-preset", "slow", "-movflags", "+faststart", "-an", str(out)],
                           stdin=subprocess.PIPE)
    for index in nearest:
        image = np.repeat(block[index][:, :, None], 3, axis=2)
        for band in range(2):   # the tag box, 2 px, orange
            image[y0 + band, x0:x1] = image[y1 - band, x0:x1] = (245, 140, 40)
            image[y0:y1, x0 + band] = image[y0:y1, x1 - band] = (245, 140, 40)
        enc.stdin.write(image.tobytes())
    enc.stdin.close()
    if enc.wait():
        raise SystemExit(f"ffmpeg failed on {out}")
    poster = out.with_suffix(".jpg")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out), "-frames:v", "1", "-q:v", "5", str(poster)], check=True)
    t0 = (grid[0] - t_origin_ms) / 1000.0
    repeats = int(grid.size - len(set(nearest.tolist())))
    print(f"{out.name}: {grid.size} frames, {out.stat().st_size:,} bytes, t0 {t0:.4f} s, worst stamp gap {worst:.1f} ms, {repeats} repeats")
    return {"src": f"media/{out.name}", "poster": f"media/{poster.name}", "t0": round(t0, 4), "frames": int(grid.size), "worst_ms": worst, "repeats": repeats,
            "camera_frames": int(stamps.size)}


def write(path: pathlib.Path, title: str, source: str, fields: list[dict], rows: list[dict]) -> None:
    one = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"), allow_nan=False)  # noqa: E731
    head = one({"title": title, "source": source, "schema": {"fields": fields}})
    path.write_text(head[:-1] + ',"rows":[\n' + ",\n".join(one(r) for r in rows) + "\n]}\n", encoding="utf-8")


def main() -> int:
    src = (f"/archive/datasets/bam_rig {DAY}: each session's cameras/cam_<serial>.npz (hw_ms) and .mp4; "
           "written by gallery/examples/robotics-camera/source/build.py")
    lines, runs, media, labels = [], [], [], {}
    for session in SESSIONS:
        cams = {s: load(session, s) for s in CAMERAS}
        origin = min(c["hw"][0] for c in cams.values())   # t = 0 at the session's first frame, either camera
        rid = run_id(session)
        what, can = purpose(session)
        labels[rid] = f"{session.replace('session_', 's')} · {what}{f' · CAN {can}' if can else ''} · 10-23"
        for serial, c in cams.items():
            hw = c["hw"]
            dt = np.diff(hw)
            assert np.all(dt > 0), f"{session} {serial}: stamps go backwards"
            for k in range(1, hw.size):
                # WHY repr: the shortest text that reads back as the same float64, so the file's interval is numpy's
                lines.append(f"{round((hw[k] - origin) / 1000.0, 4)},{rid},real,real,{device(serial)},{float(dt[k - 1])!r}")
        if session in CLIPS:
            cam = cams[CLIP_CAMERA]
            made = clip(session, cam, origin)
            started = datetime.datetime.fromtimestamp(min(c["wall"][0] for c in cams.values()), tz=datetime.timezone.utc).astimezone(LOCAL)
            span = max((c["hw"][-1] - origin) / 1000.0 for c in cams.values())
            mean_hz = (cam["hw"].size - 1) / ((cam["hw"][-1] - cam["hw"][0]) / 1000.0)
            runs.append({"run": rid, "deployment": DEPLOYMENT, "started": started.isoformat(timespec="seconds"), "when": started.strftime("%b %d %H:%M"),
                         "duration_s": round(span, 4), "kind": what, "devices": [device(s) for s in CAMERAS], "situations": ["real"],
                         "rate_hz": round(mean_hz, 2), "display_hz": round(mean_hz, 2), "label": labels[rid],
                         "basis": "real: the cameras' own hardware stamps and footage", "note": f"the session's plan: {what} on CAN {can}"})
            media.append({"id": f"{session}-rgb", "run": rid, "camera": device(CLIP_CAMERA), "kind": "rgb", "situation": "real", "label": f"RealSense {CLIP_CAMERA} · {session}",
                          "src": made["src"], "poster": made["poster"], "t0": made["t0"], "fps": FPS, "duration": round(made["frames"] / FPS, 4),
                          "width": CROP[2], "height": CROP[3], "basis": "real-camera", "max_stamp_gap_s": round(made["worst_ms"] / 1000.0, 4),
                          "note": (f"Camera {CLIP_CAMERA} (RealSense, 30 fps nominal), {made['camera_frames']} recorded frames resampled to a uniform 30 fps "
                                   f"grid in hardware time ({made['repeats']} grid frames reuse their neighbour's picture); cropped to CAN 14's plate, "
                                   "brightened (gamma 0.5), its tag boxed in orange. Real footage, not a render.")})
    header = "t,run,situation,source,device,frame_dt_ms\n"
    (CASE / "samples.csv").write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    # WHY `path`: the .base names this sidecar, which names its rows (CONTRACT §3), so every reader types the CSV alike
    sidecar = {"title": "Samples: every frame interval of the rack's two RealSense cameras, six sessions of Oct 23",
               "source": src, "path": "samples.csv",
               "description": "One row per frame interval: frame_dt_ms = hw_ms[k] − hw_ms[k−1] (the camera's hardware stamps, written exactly); t is frame k's time from the session's first frame.",
               "schema": {"fields": [
                   {"name": "t", "type": "number", "unit": "s", "description": "frame k's time, seconds from the session's first frame (either camera)"},
                   {"name": "run", "type": "string", "title": "Session", "labels": labels},
                   {"name": "situation", "type": "string"}, {"name": "source", "type": "string", "title": "Family"},
                   {"name": "device", "type": "string", "title": "Camera"},
                   {"name": "frame_dt_ms", "type": "number", "unit": "ms", "title": "Frame interval", "description": "the interval since the camera's previous frame (hardware stamps)"}]}}
    (CASE / "samples.schema.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write(CASE / "runs.json", "Runs: the three CAN 14 recording sessions of Oct 23 with a published clip", src, [
        {"name": "run", "type": "string", "title": "Session", "labels": labels, "description": "day/session under the rack's archive"},
        {"name": "deployment", "type": "string", "title": "Deployment"},
        {"name": "started", "type": "datetime", "title": "Started at"},
        {"name": "when", "type": "string", "title": "Started"},
        {"name": "duration_s", "type": "number", "unit": "s", "title": "Duration", "decimals": 1},
        {"name": "kind", "type": "string", "title": "Plan", "description": "the session's plan (rack_2026-10-23/plans/)"},
        {"name": "devices", "type": "array", "title": "Cameras"},
        {"name": "situations", "type": "array", "title": "Situations"},
        {"name": "rate_hz", "type": "number", "unit": "Hz", "title": "Frame rate", "decimals": 2, "description": "the clip camera's mean frame rate over the session"},
        {"name": "display_hz", "type": "number", "unit": "Hz", "title": "Shown at", "decimals": 2, "description": "every interval is written"},
        {"name": "label", "type": "string", "title": "Label"},
        {"name": "basis", "type": "string", "title": "Basis"},
        {"name": "note", "type": "string", "title": "Note"},
    ], runs)
    write(CASE / "media.json", "Media: CAN 14's plate, as camera 218622274411 saw it, one clip per session", src, [
        {"name": "id", "type": "string"},
        {"name": "run", "type": "string", "title": "Session", "labels": labels},
        {"name": "camera", "type": "string", "title": "Camera"},
        {"name": "kind", "type": "string", "title": "Stream", "description": "rgb, depth or band: only rgb exists"},
        {"name": "situation", "type": "string"},
        {"name": "label", "type": "string"},
        {"name": "src", "type": "string", "media": "video", "description": "the clip, relative to this file"},
        {"name": "poster", "type": "string", "media": "image", "description": "its first frame"},
        {"name": "t0", "type": "number", "unit": "s", "description": "the clock's t at frame 0: frame k is at t0 + k / fps, by construction of the resample"},
        {"name": "fps", "type": "number", "unit": "fps"},
        {"name": "duration", "type": "number", "unit": "s"},
        {"name": "width", "type": "number", "unit": "px"},
        {"name": "height", "type": "number", "unit": "px"},
        {"name": "basis", "type": "string", "display": "badge"},
        {"name": "max_stamp_gap_s", "type": "number", "unit": "s", "description": "the farthest any grid frame's picture is from its grid time (camera drops)"},
        {"name": "note", "type": "string"},
    ], media)
    write(CASE / "devices.json", "Devices: the rack's two RealSense cameras", src, [
        {"name": "device", "type": "string"}, {"name": "type", "type": "string"}, {"name": "label", "type": "string"},
        {"name": "parent", "type": "string"}, {"name": "order", "type": "integer"},
    ], [{"device": device(s), "type": "camera", "label": f"RealSense {s}" + (" · sees CAN 14's plate (its footage is published)" if s == CLIP_CAMERA else " · stamps only"),
         "parent": DEPLOYMENT, "order": i + 1} for i, s in enumerate(CAMERAS)])
    sizes = {p.name: p.stat().st_size for p in sorted(CASE.rglob("*")) if p.is_file() and "source" not in p.parts}
    print(json.dumps({"intervals": len(lines), "runs": len(runs), "clips": len(media), "bytes": sizes, "total": sum(sizes.values())}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
