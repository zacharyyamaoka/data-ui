"""PEP 0010 P2 (docs/peps/0010-robotics-playback.md §11): coverage. The `voxels` view (CONTRACT §32 reserved its keys; P2
builds it), trajectory3d's every run at `opacity: auto` (exactly 1/n over a family's n paths: no floor), the workspace
outline, bands and rules from a property in `timeseries` and `plot` (sim2real gap #6), and the coverage panels of the
Servo and Robot arm templates, measured in headless Chromium on the built kit against numpy oracles. Written red,
before the code.

    ~/psu-atlas/.venv/bin/python tests/browser/p2_checks.py [OUT_DIR]     # after npm run build

Oracles (numpy, outside the view): the fixture tests/browser/fixtures/p2/ (make_fixture.py: 137 runs of a synthetic
tool path, limits as columns), the cases' own files (gallery/examples/robotics-servo/coverage_samples.csv and its schema
sidecar; gallery/examples/robotics-arm/grid.json, media/workspace.glb, poses.json, samples.json), and the rack's own
full-rate runs read-only from /archive/datasets/bam_rig/rack_2026-10-2{3,4,5} (every runs/*.npz with ≥ 20 samples and its
json: can_id, kind). CAN 12 and CAN 14 report output radians throughout Oct 23-25 (bam_rack_twin's deployment.json
config_history: output_per_board 1.0), so a full-rate angle is numpy.degrees of the npz's q, a velocity of its qd.

THE VOXEL GRID (what these checks pin, CONTRACT §32 leaves it open): rows binned in the view. Raw rows (value count,
time, runs) are binned on cells anchored at the frame's origin: along each axis cell k spans [k·cell, (k + 1)·cell),
the edges being the float64 products k·cell (numpy.histogramdd's rule: a value on an edge is in the cell it starts).
Pre-gridded rows (value: <property>) are anchored on their own lattice: origin = the smallest centre − cell / 2 per
axis, edges origin + k·cell. value: count is rows per cell, time Σ w ÷ hz, runs the distinct runs; a property's
summary (Average by default) over the rows in the cell. A row missing a coordinate is skipped. `slice: {axis, at}`
picks the cells whose index along the axis holds `at`; `at: all` bins the rows with that axis dropped (a 2D histogram of
the projection: count and time sum through the depth, runs counts the distinct runs per column). One sequential ramp
over [min(0, smallest), largest] of the 3D grid (of the projection with at: all); one family's rows (style.families'
property has one value) take that family's hue, any other grey; light runs light → dark, dark the other way.

The card's hook, `.dv-scene3d`'s `scene3d` (P1b's calls stay: camera(), renders(), problem(), counts()…), adds:
  calls()          renderer.info.render.calls of the card's last frame (read before the view cube is drawn)
  drawables()      [{role, kind, items}]: the scene's visible drawn objects (role: line, target, markers, points,
                   workspace-fill, workspace-edges, grid, voxels-solid, voxels-faded, voxels-slice, …)
  frame()          draw the card now (after a DOM change the checks make, e.g. hiding the cube); returns renders()
  trajectory3d:
    paths()        {<series>: the paths its line layer draws}
    opacity()      {<series>: {paths, material, attribute: [distinct], alpha: [distinct]}}: each path's alpha as the
                   shader multiplies it, the line material's opacity × the path's dvAlpha (float32 buffer)
  scene3d / trajectory3d / voxels:
    workspace()    {state: none | loading | ready | failed, fill: [[x, y, z]…], edges: [[x, y, z]…]}: the outline's
                   fill and edge vertices in world units, read back from its buffers (unit scale applied)
  voxels:
    cells()        {cell, origin: [x, y, z], value, cells: [[i, j, k, value]…]}: every cell holding rows
    slice()        {axis, at, k, all, plane: [a, b], i0, j0, width, height, values: [[…]…] (height rows of width,
                   null empty), mode: 2d | 3d}: the slice as drawn (the 2D texture's values)
    ramp()         {lo: '#rrggbb', hi: '#rrggbb', domain: [a, b], family: <name> | null}
    boxes()        [{c: [x, y, z], s: [x, y, z], solid}]: each cell's box, read back from its instance matrix
DOM (voxels): [data-slice-step="-1" | "1"] (one cell back or on), [data-slice] (a range over the cells), [data-slice-all].
A timeseries' Vega view holds the dataset `guides` ({guide: 'rule:<i>' | 'band:<i>', series, x, value | lo, hi}: every
point of a rule or band read from a property; a constant spans the data's x), and the live plot's view element carries
`plotView.guides` ([{guide, series, points | lo, hi}]).

Serves the repo root (the fixture, /dist/, the cases' files) and dist/site (the case pages) on free 127.0.0.1 ports,
stops both when done, writes OUT_DIR/p2-checks.json (default reports/media/robotics-p2) with its screenshots, and exits
1 if any check fails. The deployment-size coverage file (every rack run, ≤ 150,000 rows) is not a case file: it is
generated into tests/browser/fixtures/p2/data/ (never committed) by the Servo template's own producer the first time.
"""

from __future__ import annotations

import base64
import contextlib
import csv
import glob
import json
import math
import os
import pathlib
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.request

import numpy as np
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "robotics-p2"
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "browser" / "fixtures" / "p2"
PAGE = "/tests/browser/fixtures/p2/p2.html"
MANY_BASE = "/tests/browser/fixtures/p2/many.base"
LIMITS_BASE = "/tests/browser/fixtures/p2/limits.base"
EX = ROOT / "gallery" / "examples"
SERVO, ARM = EX / "robotics-servo", EX / "robotics-arm"
ARCHIVE = pathlib.Path("/archive/datasets/bam_rig")
DEPLOY_DIR = FIX / "data"
DEPLOY_CSV = DEPLOY_DIR / "coverage_samples.csv"
PRODUCER = SERVO / "source" / "build_coverage.py"
WAIT = 45000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
CELL = 25.0
checks: list[dict] = []


def check(name, ok, value=None, soft=False):
    checks.append({"name": name, "ok": bool(ok), "value": value, **({"soft": True} if soft else {})})
    print(("SOFT " if soft else "PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str)[:500]}]" if value is not None else ""), flush=True)


def budget(name, ms, limit, value=None):
    """A speed budget that knows the machine it ran on (tests/browser/checks.py's rule): enforced while the 1-minute
    load average is under the CPU count; above it a miss is SOFT with the load beside it, never a silent pass."""
    load, cpus = os.getloadavg()[0], os.cpu_count() or 1
    note = f"{ms:.1f} ms (budget {limit} ms); load {load:.1f} on {cpus} CPUs" + (f"; {value}" if value else "")
    if ms <= limit or load <= cpus:
        check(name, ms <= limit, note)
    else:
        check(name, True, note + " -- OVERLOADED: budget not enforced on this run", soft=True)


@contextlib.contextmanager
def guard(what):
    """A section that cannot run (nothing drawn to measure, a file missing) is one failing check in its own words."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(directory):
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(directory)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            urllib.request.urlopen(base + "/", timeout=1)
            break
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.1)
    return proc, base


def f32(x):
    """x as a float32 holds it (the GPU buffers' type)."""
    return struct.unpack("f", struct.pack("f", x))[0]


# ------------------------------------------------------------------------------------------------- files
def table(path):
    """A trajectory-contract table: JSON {schema, rows}, or CSV with its <name>.schema.json sidecar, as row dicts with
    numbers as numbers and empty cells None."""
    path = pathlib.Path(path)
    if path.suffix == ".json":
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc["rows"] if isinstance(doc, dict) else doc
    side = json.loads(path.with_name(path.stem + ".schema.json").read_text(encoding="utf-8"))
    kinds = {f["name"]: f.get("type") for f in side["schema"]["fields"]}
    out = []
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            row = {}
            for k, v in r.items():
                if v is None or v == "":
                    row[k] = None
                elif kinds.get(k) in ("number", "integer"):
                    row[k] = float(v)
                else:
                    row[k] = v
            out.append(row)
    return out


def sidecar(path):
    path = pathlib.Path(path)
    return json.loads(path.with_name(path.stem + ".schema.json").read_text(encoding="utf-8"))


def decimals_of(path, field):
    for f in sidecar(path)["schema"]["fields"]:
        if f["name"] == field:
            return f.get("decimals")
    return None


# ------------------------------------------------------------------------------------------------- voxel oracles
def edges(values, cell, origin=0.0):
    """Cell edges origin + k·cell covering the values (the float64 products, as the view computes them), with the first
    k: (edges, k0)."""
    lo = math.floor((min(values) - origin) / cell) - 1
    hi = math.floor((max(values) - origin) / cell) + 2
    ks = np.arange(lo, hi + 1)
    return origin + ks * cell, lo


def bin_index(values, e, k0):
    """numpy.histogramdd's cell for each value on edges e (searchsorted right − 1), as absolute k."""
    return np.searchsorted(e, np.asarray(values, float), side="right") - 1 + k0


def oracle_cells(rows, value="count", hz=None, cell=CELL, drop=None, property=None, summary="Average", origin=(0.0, 0.0, 0.0)):
    """{(i, j, k): value} over the rows with x, y, z (k = 0 when `drop` is 'z', and so on), by numpy.histogramdd for count
    and time; distinct runs and summaries per cell by numpy's own grouping. `drop` is the slice-all projection."""
    keep = [r for r in rows if all(isinstance(r.get(c), (int, float)) for c in ("x_mm", "y_mm", "z_mm"))]
    P = np.array([[r["x_mm"], r["y_mm"], r["z_mm"]] for r in keep], float)
    axes = [a for a in range(3) if "xyz"[a] != drop]
    ed = [edges(P[:, a], cell, origin[a]) for a in range(3)]
    out = {}
    if value in ("count", "time"):
        w = np.array([r.get("w", 1) if r.get("w") is not None else 1 for r in keep], float)
        H, _ = np.histogramdd(P[:, axes], bins=[ed[a][0] for a in axes])
        Hw, _ = np.histogramdd(P[:, axes], bins=[ed[a][0] for a in axes], weights=w)
        for idx in zip(*np.nonzero(H)):
            key = [0, 0, 0]
            for n, a in enumerate(axes):
                key[a] = int(idx[n]) + ed[a][1]
            out[tuple(key)] = float(H[idx]) if value == "count" else float(Hw[idx]) / hz
        return out
    I = np.stack([bin_index(P[:, a], ed[a][0], ed[a][1]) if a in axes else np.zeros(len(P), int) for a in range(3)], axis=1)
    groups = {}
    for n, r in enumerate(keep):
        groups.setdefault(tuple(int(x) for x in I[n]), []).append(r)
    for key, rs in groups.items():
        if value == "runs":
            out[key] = float(len({r["run"] for r in rs}))
        else:
            vals = np.array([r[property] for r in rs if isinstance(r.get(property), (int, float))], float)
            if not vals.size:
                continue
            out[key] = float({"Average": np.mean, "Median": np.median, "Min": np.min, "Max": np.max, "Sum": np.sum}[summary](vals))
    return out


def compare_cells(got, want, *, rel=0.0):
    """got: the hook's [[i, j, k, value]…]; want: {(i, j, k): value}. Every cell, exactly (or within rel)."""
    g = {(int(c[0]), int(c[1]), int(c[2])): c[3] for c in got or []}
    bad = []
    for key in sorted(set(g) | set(want)):
        a, b = g.get(key), want.get(key)
        if a is None or b is None or (abs(a - b) > rel * max(abs(b), 1e-300) if rel else a != b):
            bad.append({"cell": key, "drawn": a, "numpy": b})
    return bad


# ------------------------------------------------------------------------------------------------- colour
def hex_rgb(h):
    h = (h or "").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else None


def lab(rgb):
    """sRGB 0-255 -> CIELAB (D65)."""
    def lin(c):
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116  # noqa: E731
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(a, b):
    """CIE76 ΔE between two sRGB colours (0-255 tuples)."""
    return math.dist(lab(a), lab(b))


def oklab(rgb):
    """sRGB 0-255 -> OKLab (Björn Ottosson's matrices). WHY OKLab for hue: CIELAB bends blue toward purple as it lightens
    (a pale tint of slot 1 reads 20° off in Lab, 6° in OKLCH), and a ramp keeps its hue in OKLCH."""
    def lin(c):
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    l_ = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m_ = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s_ = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(x) ** (1 / 3), x) for x in (l_, m_, s_))
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_, 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def hue_deg(rgb):
    """OKLCH hue in degrees."""
    _, a, b = oklab(rgb)
    return math.degrees(math.atan2(b, a)) % 360


def chroma(rgb):
    """OKLCH chroma (0 is grey; data-ui's slot 1 is 0.16)."""
    _, a, b = oklab(rgb)
    return math.hypot(a, b)


def hue_gap(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def rgb_text(text):
    m = re.findall(r"[\d.]+", text or "")
    return tuple(round(float(c)) for c in m[:3]) if len(m) >= 3 else None


# ------------------------------------------------------------------------------------------------- the camera
def mul(m, v):
    return [sum(m[col * 4 + row] * v[col] for col in range(4)) for row in range(4)]


def project(cam, p):
    """CSS px relative to the canvas of world point p, through the card's camera (column-major 4x4 matrices)."""
    clip = mul(cam["proj"], mul(cam["view"], [p[0], p[1], p[2], 1.0]))
    x, y = clip[0] / clip[3], clip[1] / clip[3]
    return ((x + 1) / 2 * cam["width"], (1 - y) / 2 * cam["height"])


def px_box(cam, pts):
    ps = [project(cam, p) for p in pts]
    return [min(p[0] for p in ps), min(p[1] for p in ps), max(p[0] for p in ps), max(p[1] for p in ps)]


# ------------------------------------------------------------------------------------------------- the glTF oracle
def glb_vertices(path):
    """Every vertex of every mesh primitive of a .glb, in its scene's world frame (node TRS / matrix applied), metres."""
    data = pathlib.Path(path).read_bytes()
    assert data[:4] == b"glTF", "not a binary glTF"
    off, doc, binc = 12, None, b""
    while off < len(data):
        n, kind = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + n]
        if kind == 0x4E4F534A:
            doc = json.loads(chunk.decode("utf-8"))
        elif kind == 0x004E4942:
            binc = chunk
        off += 8 + n
    def matrix(node):
        if "matrix" in node:
            return np.array(node["matrix"], float).reshape(4, 4).T
        t = node.get("translation", [0, 0, 0])
        x, y, z, w = node.get("rotation", [0, 0, 0, 1])
        s = node.get("scale", [1, 1, 1])
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        M = np.eye(4)
        M[:3, :3] = R * np.array(s, float)
        M[:3, 3] = t
        return M
    def positions(mesh):
        out = []
        for prim in mesh["primitives"]:
            acc = doc["accessors"][prim["attributes"]["POSITION"]]
            view = doc["bufferViews"][acc["bufferView"]]
            start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
            stride = view.get("byteStride", 12)
            for i in range(acc["count"]):
                out.append(struct.unpack_from("<fff", binc, start + i * stride))
        return np.array(out, float)
    pts = []
    def walk(i, parent):
        node = doc["nodes"][i]
        M = parent @ matrix(node)
        if "mesh" in node:
            P = positions(doc["meshes"][node["mesh"]])
            pts.append((M @ np.c_[P, np.ones(len(P))].T).T[:, :3])
        for c in node.get("children", []):
            walk(c, M)
    scene = doc["scenes"][doc.get("scene", 0)]
    for i in scene["nodes"]:
        walk(i, np.eye(4))
    return np.vstack(pts)


# ------------------------------------------------------------------------------------------------- the rack
def run_id(npz: pathlib.Path) -> str:
    """The trajectory contract's run id for a rack run, as the Servo template writes it (source/build.py's rule, plus
    the stem's words after its kind so tape_fast, tape_medium and tape_slow stay three runs): day/folder/session, e.g.
    10-24/dataset/can14/s01, 10-23/session_01c/s05-fast."""
    rel = npz.relative_to(ARCHIVE)
    day = rel.parts[0].removeprefix("rack_2026-")
    folder = [p for p in rel.parts[1:-1] if p != "runs"]
    parts = npz.stem.split("_")
    tail = "-".join(parts[3:])
    return "/".join([day, *folder, parts[0] + (f"-{tail}" if tail else "")])


def rack_runs(cans=None):
    """Every rack run of Oct 23-25 with ≥ 20 samples: [{npz, run, can, kind}], read-only."""
    out = []
    for meta_path in sorted(glob.glob(str(ARCHIVE / "rack_2026-10-2[345]" / "**" / "runs" / "*.json"), recursive=True)):
        try:
            meta = json.loads(pathlib.Path(meta_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        npz = pathlib.Path(meta_path).with_suffix(".npz")
        if not npz.exists() or (cans is not None and meta.get("can_id") not in cans):
            continue
        with np.load(npz) as a:
            if a["t"].size < 20:
                continue
        out.append({"npz": npz, "run": run_id(npz), "can": meta.get("can_id"), "kind": meta.get("kind") or "?"})
    return out


def full_rate_extremes(runs, field, digits):
    """{kind: (min, max)} of a channel over every run at the full logged rate, in the file's unit and rounding."""
    out = {}
    for r in runs:
        with np.load(r["npz"]) as a:
            v = np.degrees(np.asarray(a["q" if field == "q_deg" else "qd"], float))
        v = v[np.isfinite(v)]
        if not v.size:
            continue
        lo, hi = round(float(v.min()), digits), round(float(v.max()), digits)
        a, b = out.get(r["kind"], (lo, hi))
        out[r["kind"]] = (min(a, lo), max(b, hi))
    return out


# ------------------------------------------------------------------------------------------------- page helpers
SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 40))))"
HOOK = "(sel) => { const r = document.querySelector(sel + ' .dv-scene3d'); return r && r.scene3d ? r.scene3d : null; }"
DRAWN = f"(sel) => {{ const h = ({HOOK})(sel); try {{ return !!h && h.renders() > 0; }} catch (e) {{ return false; }} }}"
MOUNT_VIEWS = """([id, src, view]) => {
  for (const old of document.querySelectorAll('data-dashboard, data-views')) old.remove();
  const v = document.createElement('data-views');
  v.id = id; v.className = 'boxed';
  v.setAttribute('toolbar', 'none');
  v.setAttribute('no-url', '');
  if (view) v.setAttribute('view', view);
  v.setAttribute('src', src);
  document.body.append(v);
  return true;
}"""
MOUNT_DASH = """([id, src]) => {
  for (const old of document.querySelectorAll('data-dashboard, data-views')) old.remove();
  const d = document.createElement('data-dashboard');
  d.id = id; d.setAttribute('no-url', '');
  d.setAttribute('src', src);
  document.body.append(d);
  return true;
}"""


def settle(page, n=2):
    for _ in range(n):
        page.evaluate(SETTLE)


def wait(page, js, arg=None, timeout=WAIT):
    try:
        page.wait_for_function(js, arg=arg, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001 -- the state never came: the caller's check says so
        return False


def hook(page, sel, call, *args):
    """A call on the card's hook; null when the card or the call is missing (the check then FAILs in its own words)."""
    return page.evaluate(f"([sel, args]) => {{ const h = ({HOOK})(sel); try {{ return h ? h.{call}(...args) : null; }} catch (e) {{ return null; }} }}", [sel, list(args)])


def new_page(browser, *, width=1280, dark=False):
    mobile = width < 500
    context = browser.new_context(viewport={"width": width, "height": 1000 if width > 500 else 844}, color_scheme="dark" if dark else "light",
                                  device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(f"console: {m.text}") if m.type == "error" else None)
    return page


def open_fixture(browser, base, **kw):
    page = new_page(browser, **kw)
    page.goto(f"{base}{PAGE}")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    return page


def mount_views(page, src, view, sel="#v"):
    page.evaluate(MOUNT_VIEWS, [sel.lstrip("#"), src, view])
    ok = wait(page, DRAWN, sel)
    settle(page)
    return ok


def set_block(page, sel, kind, block):
    """host.setView on the card's <data-views>, merging `block` into its `kind` entry (the controls' own path)."""
    page.evaluate("""([sel, kind, block]) => { const el = document.querySelector(sel).closest('data-views') || document.querySelector(sel);
      const v = el.view || {}; el.setView({ [kind]: { ...(v[kind] || {}), ...block } }); }""", [sel, kind, block])
    settle(page, 3)


def view_entry(page, sel):
    return page.evaluate("(sel) => { const el = document.querySelector(sel).closest('data-views') || document.querySelector(sel); return el && el.view ? JSON.parse(JSON.stringify(el.view)) : null; }", sel)


def canvas_pixels(page, sel):
    """The card canvas's every pixel: {w, h, dpr, data (base64 RGBA, unpremultiplied as getImageData gives it)}."""
    return page.evaluate("""(sel) => { const c = document.querySelector(sel + ' .dv-scene3d canvas'); if (!c || !c.width) return null;
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let s = '';
      for (let i = 0; i < d.length; i += 32768) s += String.fromCharCode.apply(null, d.subarray(i, i + 32768));
      return { w: c.width, h: c.height, dpr: c.width / c.clientWidth, data: btoa(s) }; }""", sel)


def pixel_at(px, x, y, r=1):
    """The median colour (RGB) of the (2r+1)² device pixels around CSS point (x, y), from canvas_pixels()."""
    a = np.frombuffer(base64.b64decode(px["data"]), np.uint8).reshape(px["h"], px["w"], 4)
    cx, cy = int(round(x * px["dpr"])), int(round(y * px["dpr"]))
    R = max(1, int(round(r * px["dpr"])))
    patch = a[max(0, cy - R): cy + R + 1, max(0, cx - R): cx + R + 1].reshape(-1, 4)
    patch = patch[patch[:, 3] > 200]
    if not len(patch):
        return None
    return tuple(int(v) for v in np.median(patch[:, :3], axis=0))


def ink_box(px, alpha=8, skip=None):
    """The CSS-px bounding box [x0, y0, x1, y1] of every pixel with alpha ≥ `alpha` (pixel edges, not centres), leaving
    out the rect `skip` [x, y, w, h] (CSS px)."""
    a = np.frombuffer(base64.b64decode(px["data"]), np.uint8).reshape(px["h"], px["w"], 4)
    mask = a[:, :, 3] >= alpha
    if skip:
        k = px["dpr"]
        x0, y0 = int(skip[0] * k), int(skip[1] * k)
        mask[max(0, y0): int((skip[1] + skip[3]) * k) + 1, max(0, x0): int((skip[0] + skip[2]) * k) + 1] = False
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    k = px["dpr"]
    return [xs.min() / k, ys.min() / k, (xs.max() + 1) / k, (ys.max() + 1) / k]


def no_sideways(page, width):
    return page.evaluate("() => document.scrollingElement.scrollWidth") <= width


def shot(page, name, sel=None):
    try:
        if sel:
            page.locator(sel).first.scroll_into_view_if_needed()
            settle(page)
            page.locator(sel).first.screenshot(path=str(OUT / f"{name}.png"))
        else:
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    except Exception as e:  # noqa: BLE001 -- a missing picture is not a failed behaviour; say so
        print(f"(screenshot {name} not taken: {e})")


# ------------------------------------------------------------------------------------------------- many runs, opacity
def many_runs(browser, base):
    rows = table(FIX / "runs137.json")
    runs = sorted({r["run"] for r in rows})
    sel = "#v"
    page = open_fixture(browser, base)
    drew = mount_views(page, MANY_BASE, "Many")
    check("many runs: the trajectory3d card draws the 137-run fixture (a frame rendered)", drew, hook(page, sel, "renders"))
    paths = hook(page, sel, "paths") or {}
    calls = hook(page, sel, "calls")
    drawn = hook(page, sel, "drawables") or []
    lines = [d for d in drawn if d.get("role") == "line"]
    check(f"many runs: {len(runs)} runs draw {len(runs)} paths, all in one line layer (one LineSegments2)",
          len(runs) == 137 and paths.get("real") == 137 and len(lines) == 1, {"paths": paths, "line layers": lines})
    check("many runs: the card's frame costs ≤ 1 draw call per drawn layer, and the layers do not grow with the runs (renderer.info.render.calls ≤ the visible drawables ≤ 8)",
          isinstance(calls, int) and 0 < calls <= len(drawn) <= 8, {"calls": calls, "drawables": [(d.get("role"), d.get("kind"), d.get("items")) for d in drawn]})
    op = (hook(page, sel, "opacity") or {}).get("real") or {}
    alphas = op.get("alpha") or []
    want = f32(1 / 137)
    ok = op.get("paths") == 137 and len(alphas) == 1 and abs(alphas[0] - want) <= want * 2 ** -22
    check("opacity: auto is exactly 1/n with no floor: each of the 137 paths' alpha, the line material's opacity × its dvAlpha read back from the buffers, is 1/137 within float32's rounding (0.0073 < the old 0.04 floor)",
          ok, {"paths": op.get("paths"), "material": op.get("material"), "attribute": op.get("attribute"), "alpha": alphas, "1/137": 1 / 137})
    shot(page, "p2-many-runs-light-1280", sel)
    # a filter to 37 runs re-counts: 1/37 each, still one line layer
    page.evaluate("(sel) => document.querySelector(sel).setView({ filters: 'run <= \"m/r037\"' })", sel)
    wait(page, f"(sel) => {{ const h = ({HOOK})(sel); const p = h && h.paths(); return !!p && p.real === 37; }}", sel, timeout=15000)
    op = (hook(page, sel, "opacity") or {}).get("real") or {}
    a37 = op.get("alpha") or []
    check("opacity: a filter that leaves 37 runs re-counts n: every path at 1/37 (float32)",
          op.get("paths") == 37 and len(a37) == 1 and abs(a37[0] - f32(1 / 37)) <= f32(1 / 37) * 2 ** -22, {"paths": op.get("paths"), "alpha": a37})
    check("many runs: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- voxels: cells
def voxels_cells(browser, base):
    rows = table(FIX / "runs137.json")
    sel = "#v"
    page = open_fixture(browser, base)
    for view, value, kw in (("Count", "count", {}), ("Time", "time", {"hz": 10}), ("Runs", "runs", {})):
        drew = mount_views(page, MANY_BASE, view)
        got = hook(page, sel, "cells") or {}
        want = oracle_cells(rows, value, **kw)
        bad = compare_cells(got.get("cells"), want)
        check(f"voxels {value}: the card draws (a frame rendered)", drew, hook(page, sel, "renders"))
        check(f"voxels {value}: every cell equals numpy.histogramdd's on 25 mm cells anchored at the origin "
              f"({'rows' if value == 'count' else 'Σ w ÷ 10 Hz' if value == 'time' else 'distinct runs'} per cell; {len(want)} cells), exactly",
              got.get("cell") == CELL and got.get("origin") == [0, 0, 0] and not bad and len(want) > 50,
              bad[:4] or {"cells": len(want), "max": max(want.values()) if want else None})
    # 3D: a box per cell at 0.8 × the cell, solid without a slice; with one, the slice's cells solid and the rest faded
    mount_views(page, MANY_BASE, "Count")
    want = oracle_cells(rows, "count")
    boxes = hook(page, sel, "boxes") or []
    centre = lambda key: [(key[a] + 0.5) * CELL for a in range(3)]  # noqa: E731
    by = {tuple(round(c / CELL - 0.5) for c in b["c"]): b for b in boxes}
    off = [k for k in want if k not in by or max(abs(a - b) for a, b in zip(by[k]["c"], centre(k))) > 1e-3
           or max(abs(s - 0.8 * CELL) for s in by[k]["s"]) > 1e-3]
    check("voxels 3D: one box per cell, centred on it, 0.8 × the cell on each side (read back from the instance matrices), all solid without a slice",
          len(boxes) == len(want) and not off and all(b.get("solid") for b in boxes), {"boxes": len(boxes), "cells": len(want), "off": off[:3]})
    drawn = hook(page, sel, "drawables") or []
    vox = [d for d in drawn if str(d.get("role", "")).startswith("voxels")]
    calls = hook(page, sel, "calls")
    check(f"voxels 3D: {len(want)} cells draw in ≤ 2 instanced layers (solid, faded) and the frame in ≤ 1 call per drawn layer",
          0 < len(vox) <= 2 and isinstance(calls, int) and calls <= len(drawn) <= 8, {"voxel layers": vox, "calls": calls, "drawables": len(drawn)})
    set_block(page, sel, "voxels", {"slice": {"axis": "z", "at": 137.5}})
    boxes = hook(page, sel, "boxes") or []
    k5 = math.floor(137.5 / CELL)
    wrong = [b["c"] for b in boxes if bool(b.get("solid")) != (math.floor(b["c"][2] / CELL) == k5)]
    check("voxels 3D: with slice {axis: z, at: 137.5} the cells of z 125-150 mm are solid and every other cell faded",
          boxes and not wrong and any(b.get("solid") for b in boxes) and any(not b.get("solid") for b in boxes), {"wrong": wrong[:3], "boxes": len(boxes)})
    shot(page, "p2-voxels-3d-light-1280", sel)
    check("voxels cells: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- voxels: the slice
def slice_values(sl):
    """The hook's slice as {(i, j): value} over its plane (null left out)."""
    out = {}
    for r, line in enumerate(sl.get("values") or []):
        for c, v in enumerate(line):
            if v is not None:
                out[(sl["i0"] + c, sl["j0"] + r)] = v
    return out


def voxels_slice(browser, base, *, width=1280, dark=False):
    rows = table(FIX / "runs137.json")
    sel = "#v"
    page = open_fixture(browser, base, width=width, dark=dark)
    tag = f"{'dark' if dark else 'light'} {width}"
    drew = mount_views(page, MANY_BASE, "Slice")
    cells = oracle_cells(rows, "count")
    k = math.floor(137.5 / CELL)
    want = {(i, j): v for (i, j, kk), v in cells.items() if kk == k}
    sl = hook(page, sel, "slice") or {}
    got = slice_values(sl)
    bad = [{"cell": key, "drawn": got.get(key), "numpy": want.get(key)} for key in sorted(set(got) | set(want)) if got.get(key) != want.get(key)]
    cam = hook(page, sel, "camera") or {}
    check(f"voxels slice ({tag}): seen from the top (orthographic) the heatmap is the slice z = {k} (125-150 mm) of numpy.histogramdd, cell by cell",
          drew and cam.get("ortho") and sl.get("mode") == "2d" and sl.get("axis") == "z" and sl.get("k") == k and sl.get("plane") == ["x", "y"] and not bad and want,
          bad[:4] or {"cells": len(want), "k": sl.get("k"), "mode": sl.get("mode")})
    # the ramp's end: the largest cell of the grid, in the slice that holds it, drawn as the ramp's last colour
    gmax = max(cells, key=lambda key: cells[key])
    set_block(page, sel, "voxels", {"slice": {"axis": "z", "at": (gmax[2] + 0.5) * CELL}})
    ramp = hook(page, sel, "ramp") or {}
    cam = hook(page, sel, "camera") or {}
    px = canvas_pixels(page, sel)
    at = project(cam, [(gmax[0] + 0.5) * CELL, (gmax[1] + 0.5) * CELL, (gmax[2] + 0.5) * CELL]) if cam else None
    rgb = pixel_at(px, *at) if px and at else None
    hi = hex_rgb(ramp.get("hi"))
    de = delta_e(rgb, hi) if rgb and hi else None
    check(f"voxels slice ({tag}): the largest cell ({cells[gmax]:g} rows at {gmax}) is drawn in the ramp's end colour within ΔE 3 (CIE76, the canvas pixel at its centre)",
          de is not None and de <= 3 and ramp.get("domain") and ramp["domain"][1] == cells[gmax], {"pixel": rgb, "ramp hi": ramp.get("hi"), "ΔE": de and round(de, 2), "domain": ramp.get("domain")})
    lo = hex_rgb(ramp.get("lo"))
    tk = page.evaluate("(sel) => document.querySelector(sel).tokens()", sel)
    slot1 = rgb_text((tk or {}).get("series", [None])[0])
    light_to_dark = lo and hi and lab(lo)[0] > lab(hi)[0]
    check(f"voxels ramp ({tag}): one hue, the real family's (slot 1's OKLCH hue within 12°, not grey), {'dark near the surface to light' if dark else 'light to dark'}",
          lo and hi and slot1 and hue_gap(hue_deg(hi), hue_deg(slot1)) <= 12 and chroma(hi) >= 0.03 and (not light_to_dark if dark else light_to_dark) and ramp.get("family") == "real",
          {"lo": ramp.get("lo"), "hi": ramp.get("hi"), "slot 1": slot1, "family": ramp.get("family"), "hue": hi and round(hue_deg(hi), 1), "slot hue": slot1 and round(hue_deg(slot1), 1)})
    shot(page, f"p2-voxels-slice-{'dark' if dark else 'light'}-{width}", sel)
    check(f"voxels slice ({tag}): the page never scrolls sideways", no_sideways(page, width), page.evaluate("() => document.scrollingElement.scrollWidth"))
    if width == 1280 and not dark:
        # one cell on: the ▶ button steps the slice to the next cell, written to the view entry
        set_block(page, sel, "voxels", {"slice": {"axis": "z", "at": 137.5}})
        page.locator(f"{sel} [data-slice-step='1']").first.click()
        wait(page, f"(sel) => {{ const h = ({HOOK})(sel); const s = h && h.slice(); return !!s && s.k === {k + 1}; }}", sel, timeout=10000)
        settle(page, 2)
        entry = ((view_entry(page, sel) or {}).get("voxels") or {}).get("slice") or {}
        sl = hook(page, sel, "slice") or {}
        want6 = {(i, j): v for (i, j, kk), v in cells.items() if kk == k + 1}
        got6 = slice_values(sl)
        check("voxels slice: ▶ steps one cell (the view entry's slice.at moves from 137.5 to 162.5 mm, the cell 150-175 mm) and the heatmap is that slice of numpy.histogramdd",
              sl.get("k") == k + 1 and entry.get("at") == 162.5 and entry.get("axis") == "z" and got6 == want6, {"entry": entry, "k": sl.get("k"), "cells": [len(got6), len(want6)]})
        # at: all: a 2D histogram of the projection (count sums through the depth)
        set_block(page, sel, "voxels", {"slice": {"axis": "z", "at": "all"}})
        sl = hook(page, sel, "slice") or {}
        flat = oracle_cells(rows, "count", drop="z")
        wantall = {(i, j): v for (i, j, _), v in flat.items()}
        gotall = slice_values(sl)
        bad = [{"cell": key, "drawn": gotall.get(key), "numpy": wantall.get(key)} for key in sorted(set(gotall) | set(wantall)) if gotall.get(key) != wantall.get(key)]
        check("voxels slice: at: all is numpy.histogram2d of the projection (z dropped), cell by cell",
              sl.get("all") is True and not bad and wantall, bad[:4] or {"cells": len(wantall)})
        ramp = hook(page, sel, "ramp") or {}
        check("voxels slice: at: all's ramp spans the projection's own cells [0, max]", (ramp.get("domain") or [None, None])[1] == max(wantall.values()), ramp.get("domain"))
    check(f"voxels slice ({tag}): no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- the workspace
def workspace(browser, base, *, width=1280):
    glb = ARM / "media" / "workspace.glb"
    sel = "#v"
    page = open_fixture(browser, base, width=width)
    tag = f"light {width}"
    with guard(f"workspace ({tag})"):
        V = glb_vertices(glb) * 1000.0
        drew = mount_views(page, MANY_BASE, "Hull")
        wait(page, f"(sel) => {{ const h = ({HOOK})(sel); const w = h && h.workspace(); return !!w && (w.state === 'ready' || w.state === 'failed'); }}", sel, timeout=20000)
        settle(page, 2)
        ws = hook(page, sel, "workspace") or {}
        cam = hook(page, sel, "camera") or {}
        # WHY hide the cube: it is composited into the card's own canvas, at its corner
        page.evaluate("(sel) => { const c = document.querySelector(sel + ' [data-cube]'); if (c) c.hidden = true; }", sel)
        hook(page, sel, "frame")
        settle(page, 1)
        cam = hook(page, sel, "camera") or {}
        px = canvas_pixels(page, sel)
        want = px_box(cam, [[V[:, 0].min(), V[:, 1].min(), 0], [V[:, 0].max(), V[:, 1].max(), 0]]) if cam else None
        got = ink_box(px) if px else None
        err = max(abs(a - b) for a, b in zip(got, want)) if got and want else None
        check(f"workspace ({tag}): the model loads and draws (a translucent fill and its edges)", drew and ws.get("state") == "ready" and ws.get("fill"), {"state": ws.get("state")})
        check(f"workspace ({tag}): from the top, the outline's drawn bounding box (every inked canvas pixel) equals the hull of the model's vertices projected through the card's camera within 1 px",
              cam.get("ortho") and err is not None and err <= 1.0, {"drawn px": got and [round(v, 2) for v in got], "oracle px": want and [round(v, 2) for v in want], "worst px": err and round(err, 3)})
        shot(page, f"p2-workspace-top-light-{width}", sel)
    check(f"workspace ({tag}): no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- rules and bands
GUIDES = """(sel) => { const el = document.querySelector(sel); const v = el && el.querySelector('.dv-view-timeseries') && el.querySelector('.dv-view-timeseries').vegaView;
  const view = v || (el && (el.querySelector('.dv-timeseries-plot') || {}).parentElement || {}).vegaView;
  if (!view) return null;
  let data = null; try { data = view.data('guides'); } catch (e) { return { missing: String(e) }; }
  const y = view.scale('y'); const items = [];
  const walk = (n) => { if (!n) return; for (const i of n.items || []) { if (i.datum && i.datum.guide !== undefined && (n.marktype === 'line' || n.marktype === 'rule' || n.marktype === 'area' || n.marktype === 'rect')) items.push({ mark: n.marktype, guide: i.datum.guide, value: i.datum.value, lo: i.datum.lo, y: i.y, y2: i.y2 }); if (i.items) walk(i); } };
  walk(view.scenegraph().root);
  return { data: data.map((d) => ({ guide: d.guide, series: d.series ?? null, x: d.x, value: d.value ?? null, lo: d.lo ?? null, hi: d.hi ?? null })), items, ys: items.map((i) => [i.value ?? i.lo, y(i.value ?? i.lo)]) };
}"""


def step_points(rows, prop, x="t"):
    """A property over x as a step line: the first point, each change, the last x."""
    pts = sorted({(r[x], r[prop]) for r in rows if isinstance(r.get(prop), (int, float))})
    out = []
    for xv, v in pts:
        if not out or out[-1][1] != v:
            out.append([xv, v])
    if out and pts[-1][0] != out[-1][0]:
        out.append([pts[-1][0], pts[-1][1]])
    return out


def rules_bands(browser, base):
    rows = table(FIX / "limits.json")
    a_rows = [r for r in rows if r["device"] == "A"]
    sel = "#v"
    page = open_fixture(browser, base)
    page.evaluate(MOUNT_VIEWS, ["v", LIMITS_BASE, "Limit"])
    wait(page, "(sel) => { const el = document.querySelector(sel); const t = el && el.querySelector('.dv-view-timeseries'); return !!t && !!t.vegaView; }", sel)
    settle(page, 3)
    g = page.evaluate(GUIDES, sel) or {}
    data = g.get("data") or []
    rule = [d for d in data if d["guide"] == "rule:0"]
    band = [d for d in data if d["guide"] == "band:0"]
    xs = [r["t"] for r in a_rows]
    check("rules from a property: device A's own lim_hi (a constant over its rows) is one rule at 40 across the data's x (the guides dataset)",
          rule and {d["value"] for d in rule} == {40} and min(d["x"] for d in rule) == min(xs) and max(d["x"] for d in rule) == max(xs), rule[:4] or g)
    check("bands from a property: [lim_lo, lim_hi] is a band from −40 to 40", band and {(d["lo"], d["hi"]) for d in band} == {(-40, 40)}, band[:4] or g)
    off = [p for p in (g.get("ys") or []) if p[0] is not None]
    yv = page.evaluate("(sel) => { const el = document.querySelector(sel); const t = el.querySelector('.dv-view-timeseries'); const v = t && t.vegaView; return v ? v.scale('y')(40) : null; }", sel)
    rule_items = [i for i in (g.get("items") or []) if i["guide"] == "rule:0"]
    check("rules from a property: the drawn rule sits at the y scale's 40 within 0.5 px (Vega's scenegraph)",
          rule_items and yv is not None and all(abs(i["y"] - yv) <= 0.5 for i in rule_items), {"items": rule_items[:3], "y(40)": yv})
    shot(page, "p2-rules-limit-light-1280", sel)
    # a limit that changes over time is a step line through its values
    page.evaluate(MOUNT_VIEWS, ["v", LIMITS_BASE, "Cap"])
    wait(page, "(sel) => { const el = document.querySelector(sel); const t = el && el.querySelector('.dv-view-timeseries'); return !!t && !!t.vegaView; }", sel)
    settle(page, 3)
    g = page.evaluate(GUIDES, sel) or {}
    pts = [[d["x"], d["value"]] for d in (g.get("data") or []) if d["guide"] == "rule:0"]
    want = step_points(a_rows, "cap")
    check(f"rules from a property: a cap that changes at t = 5 s is a step line through its values {want}", pts == want, {"drawn": pts, "file": want})
    # per series: each device's own limit
    page.evaluate(MOUNT_VIEWS, ["v", LIMITS_BASE, "Every device"])
    wait(page, "(sel) => { const el = document.querySelector(sel); const t = el && el.querySelector('.dv-view-timeseries'); return !!t && !!t.vegaView; }", sel)
    settle(page, 3)
    g = page.evaluate(GUIDES, sel) or {}
    per = {}
    for d in g.get("data") or []:
        if d["guide"] == "rule:0":
            per.setdefault(d["series"], set()).add(d["value"])
    check("rules from a property: with series: device each series draws its own device's limit (A 40, B 60)", per == {"A": {40}, "B": {60}}, {k: sorted(v) for k, v in per.items()})
    # the live plot (uPlot) reads the same keys
    page.evaluate(MOUNT_VIEWS, ["v", LIMITS_BASE, "Plot"])
    wait(page, "(sel) => { const el = document.querySelector(sel); const p = el && el.querySelector('.dv-view-plot'); return !!p && !!p.plotView && !!p.uplot; }", sel)
    settle(page, 3)
    pg = page.evaluate("""(sel) => { const p = document.querySelector(sel + ' .dv-view-plot'); const v = p && p.plotView; const u = p && p.uplot;
      if (!v || !u) return null; return { guides: JSON.parse(JSON.stringify(v.guides || null)), y40: u.valToPos(40, 'y', true), left: u.bbox.left, width: u.bbox.width }; }""", sel) or {}
    gl = {d.get("guide"): d for d in (pg.get("guides") or [])}
    r0 = (gl.get("rule:0") or {}).get("points") or []
    r1 = (gl.get("rule:1") or {}).get("points") or []
    b0 = gl.get("band:0") or {}
    check("plot: rules from a property: lim_hi a constant 40, cap the step line through its values; band [lim_lo, lim_hi] −40 … 40",
          r0 and {p[1] for p in r0} == {40} and r1 == want and {p[1] for p in b0.get("lo") or []} == {-40} and {p[1] for p in b0.get("hi") or []} == {40},
          {"rule:0": r0[:3], "rule:1": r1, "band:0": {k: (b0.get(k) or [])[:2] for k in ("lo", "hi")}})
    ink = page.evaluate("""([sel, y, left, width]) => { const p = document.querySelector(sel + ' .dv-view-plot canvas'); if (!p) return null;
      const d = p.getContext('2d').getImageData(Math.round(left), Math.round(y), Math.round(width), 1).data; let n = 0;
      for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 60) n++; return n; }""", [sel, pg.get("y40"), pg.get("left"), pg.get("width")]) if pg.get("y40") is not None else None
    check("plot: the constant rule is inked on the canvas along y = 40 (dashed: at least a fifth of the plot's width)",
          ink is not None and pg.get("width") and ink >= pg["width"] / 5, {"inked px": ink, "plot px": pg.get("width")})
    shot(page, "p2-rules-plot-light-1280", sel)
    check("rules and bands: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- the Servo template
D = "#example"
SERVO_KEYS = ["runs", "playback", "angle", "angle-coverage", "velocity-coverage", "phase-space"]
PANEL = "(k) => document.querySelector(`#example .dd-panel[data-panel='${k}']`)"
VEGA = f"(k) => {{ const p = ({PANEL})(k); const e = p && p.querySelector('.dv-view-chart'); return e && e.vegaView ? e.vegaView : null; }}"
READY = f"""(keys) => {{
  const d = document.querySelector('#example'); if (!d || !d.dash) return false;
  for (const k of keys) {{ const p = ({PANEL})(k); if (!p) return false; const v = p.querySelector('data-views'); if (!v || !v.dataset.view) return false;
    const c = p.querySelector('.dv-view-chart'); if (c && !c.vegaView) return false;
    const r = p.querySelector('.dv-scene3d'); if (r && !(r.scene3d && r.scene3d.renders() > 0)) return false; }}
  return true; }}"""
# a binned histogram's points from Vega's scenegraph: [[start, end, sum]…] (the fields Vega-Lite names bin_*_<f>, *_end, sum_w)
HIST = f"""([k, f]) => {{ const v = ({VEGA})(k); if (!v) return null; const out = new Map();
  const walk = (n) => {{ for (const i of n.items || []) {{ const d = i.datum; if (d) {{ const s = Object.keys(d).find((x) => x.startsWith('bin_') && x.endsWith('_' + f));
    if (s && d[s + '_end'] !== undefined && d.sum_w !== undefined) out.set(d[s], [d[s], d[s + '_end'], d.sum_w, i.y]); }} if (i.items) walk(i); }} }};
  walk(v.scenegraph().root); return [...out.values()].sort((a, b) => a[0] - b[0]); }}"""
BOX = f"""([k, f]) => {{ const v = ({VEGA})(k); if (!v) return null; const out = {{}};
  const walk = (n) => {{ for (const i of n.items || []) {{ const d = i.datum; if (d && d['lower_whisker_' + f] !== undefined) out[d.kind] = [d['lower_whisker_' + f], d['upper_whisker_' + f]]; if (i.items) walk(i); }} }};
  walk(v.scenegraph().root); return out; }}"""


def open_case(browser, base, case, keys, *, width=1280, dark=False):
    page = new_page(browser, width=width, dark=dark)
    page.goto(f"{base}/gallery/{case}/index.html")
    with contextlib.suppress(Exception):
        page.wait_for_selector(f"{D} .dd-panel[data-panel]", timeout=WAIT)
        for k in keys:
            page.locator(f"{D} .dd-panel[data-panel='{k}']").scroll_into_view_if_needed(timeout=5000)
    ok = wait(page, READY, keys)
    settle(page, 3)
    return page, ok


def rail_radio(dataset, key, value):
    return f"{D} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[type=radio][data-value='{value}']"


def checked(page, dataset, key):
    return page.evaluate("([s]) => { const i = document.querySelector(s); return i ? i.dataset.value : null; }",
                         [f"{D} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[type=radio]:checked"])


def hist_check(page, key, field, rows, device, label):
    got = page.evaluate(HIST, [key, field]) or []
    sel_rows = [r for r in rows if r["device"] == device and isinstance(r.get(field), (int, float))]
    if not got:
        check(f"{label}: the histogram draws (its binned sums in Vega's scenegraph)", False, None)
        return
    e = np.array([g[0] for g in got] + [got[-1][1]], float)
    contiguous = all(abs(got[i][1] - got[i + 1][0]) < 1e-9 for i in range(len(got) - 1))
    vals = np.array([r[field] for r in sel_rows], float)
    w = np.array([r["w"] for r in sel_rows], float)
    H, _ = np.histogram(vals, bins=e, weights=w)
    drawn = np.array([g[2] for g in got], float)
    inside = ((vals >= e[0]) & (vals <= e[-1])).all()
    check(f"{label}: every bar's height equals numpy.histogram(…, weights=w) on the drawn bins ({len(got)} bins over {len(sel_rows)} rows of {device})",
          contiguous and inside and np.array_equal(drawn, H), {"bins": len(got), "worst": float(np.max(np.abs(drawn - H))) if len(H) == len(drawn) else None,
                                                              "Σ drawn": float(drawn.sum()), "Σ numpy": float(H.sum()), "Σ w": float(w.sum())})


def servo(browser, base):
    cov = SERVO / "coverage_samples.csv"
    with guard("servo coverage"):
        rows = table(cov)
        runs_file = table(SERVO / "runs.json")
        newest = max(runs_file, key=lambda r: r["started"])
        device0 = newest["devices"][0]
        page, ok = open_case(browser, base, "robotics-servo", SERVO_KEYS)
        check("servo: the coverage panels draw beside the playback ones (angle-coverage, velocity-coverage, phase-space)", ok, None)
        check(f"servo: the coverage rail opens on the newest run's servo ({device0})", checked(page, "coverage", "device") == device0, checked(page, "coverage", "device"))
        arch = rack_runs({12, 14})
        have = {}
        for r in rows:
            have.setdefault(r["device"], set()).add(r["run"])
        want_runs = {f"CAN {c}": {r["run"] for r in arch if r["can"] == c} for c in (12, 14)}
        check("servo coverage: the file covers every CAN 12 and CAN 14 rack run of Oct 23-25 with ≥ 20 samples (runs read from the archive)",
              have == want_runs, {d: [len(have.get(d, ())), len(want_runs[d])] for d in want_runs})
        check("servo coverage: ≤ 150,000 rows, weights 0 or 1", len(rows) <= 150000 and {r["w"] for r in rows} <= {0.0, 1.0}, {"rows": len(rows)})
        for device in (device0, "CAN 14" if device0 != "CAN 14" else "CAN 12"):
            if device != device0:
                page.locator(rail_radio("coverage", "device", device)).check()
                wait(page, f"(d) => {{ const p = ({PANEL})('angle-coverage'); const v = p && p.querySelector('data-views'); return !!v && v.model && v.model.rows.length && v.model.rows.every((r) => (r.device && r.device.value || r.device) === d); }}", device)
                settle(page, 4)
            hist_check(page, "angle-coverage", "q_deg", rows, device, f"servo {device} angle coverage")
            got = page.evaluate(BOX, ["velocity-coverage", "qd_deg_s"]) or {}
            digits = decimals_of(cov, "qd_deg_s")
            want = full_rate_extremes([r for r in arch if f"CAN {r['can']}" == device], "qd_deg_s", digits) if digits is not None else {}
            bad = {k: [got.get(k), list(want.get(k) or [])] for k in set(got) | set(want) if not got.get(k) or tuple(got[k]) != tuple(want.get(k) or ())}
            check(f"servo {device} velocity coverage: each run kind's whisker ends equal the full-rate npz min and max of qd (deg/s, the file's {digits} decimals), exactly",
                  got and want and not bad, bad or {k: got[k] for k in sorted(got)})
        check("servo: no page error", not page.errors, page.errors[:3])
        page.context.close()


def deployment(browser, root_base):
    """Every rack run at the deployment's size (≤ 150,000 rows): the Servo template's own panels over it, a device pick."""
    with guard("deployment coverage"):
        if not DEPLOY_CSV.exists():
            DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.run([sys.executable, "-B", "-I", str(PRODUCER), "--deployment", str(DEPLOY_DIR)], timeout=3600, check=False)
        rows = table(DEPLOY_CSV)
        arch = rack_runs()
        have = {r["run"] for r in rows}
        check("deployment coverage: the file covers every rack run of Oct 23-25 with ≥ 20 samples (1,000; the archive's own list)",
              have == {r["run"] for r in arch} and len(arch) >= 1000, {"file": len(have), "archive": len(arch)})
        check("deployment coverage: 140,000 to 150,000 rows (PEP 0010 §4.4's budget, the rack at its display rate)", 140000 <= len(rows) <= 150000, len(rows))
        # the template's views.base, its files read in place, its coverage file swapped for this one
        text = (SERVO / "views.base").read_text(encoding="utf-8")
        rel = "../../../../../gallery/examples/robotics-servo/"
        text = re.sub(r"(?<![\w/.-])([\w-]+\.(?:json|csv))\b", lambda m: m.group(1) if m.group(1) == "coverage_samples.csv" else rel + m.group(1), text)
        (DEPLOY_DIR / "servo.base").write_text(text, encoding="utf-8")
        page = new_page(browser)
        page.goto(f"{root_base}{PAGE}")
        page.wait_for_function("() => window.kitReady", timeout=WAIT)
        page.evaluate(MOUNT_DASH, ["example", "/tests/browser/fixtures/p2/data/servo.base"])
        keys = ["angle-coverage", "velocity-coverage", "phase-space"]
        for k in keys:
            with contextlib.suppress(Exception):
                page.locator(f"{D} .dd-panel[data-panel='{k}']").scroll_into_view_if_needed(timeout=5000)
        ready = wait(page, READY, keys, timeout=120000)
        settle(page, 4)
        check("deployment coverage: the template's coverage panels draw over 150,000 rows", ready, None)
        devices = sorted({r["device"] for r in rows}, key=lambda d: -sum(1 for r in rows if r["device"] == d))
        times = []
        for device in [d for d in devices if d != checked(page, "coverage", "device")][:3]:
            n = sum(1 for r in rows if r["device"] == device)
            page.evaluate("""([keys, n]) => { window.__p2 = { start: null, done: {} };
              document.addEventListener('click', (e) => { if (window.__p2.start === null) window.__p2.start = e.timeStamp; }, { capture: true, once: true });
              for (const k of keys) { const v = document.querySelector(`#example .dd-panel[data-panel='${k}'] data-views`);
                v.addEventListener('data-views-render', function on(e) { if (e.detail && e.detail.rows === n) { window.__p2.done[k] = performance.now(); v.removeEventListener('data-views-render', on); } }); } }""", [keys, n])
            page.locator(rail_radio("coverage", "device", device)).click()
            done = wait(page, "(keys) => window.__p2 && keys.every((k) => window.__p2.done[k] !== undefined)", keys, timeout=30000)
            # the frame after the last panel's render: when the reader sees it
            ms = page.evaluate("() => new Promise((r) => requestAnimationFrame(() => { const p = window.__p2; r(p.start === null ? null : performance.now() - p.start); }))") if done else None
            last = page.evaluate("() => { const p = window.__p2; return p.start === null ? null : Math.max(...Object.values(p.done)) - p.start; }") if done else None
            times.append((device, n, last, ms))
            settle(page, 3)
            budget(f"deployment coverage: a click on {device} in the rail redraws every coverage panel ({', '.join(keys)}; {n:,} of {len(rows):,} rows) in ≤ 300 ms, click to the last panel's render",
                   last if last is not None else 1e9, 300, f"to the next frame {ms and round(ms, 1)} ms")
        hist_check(page, "angle-coverage", "q_deg", rows, times[-1][0] if times else devices[0], "deployment angle coverage after the picks")
        check("deployment coverage: no page error", not page.errors, page.errors[:3])
        page.context.close()


# ------------------------------------------------------------------------------------------------- the Robot arm template
ARM_KEYS = ["runs", "playback", "path-3d", "coverage", "reach", "joint-range"]


def arm(browser, base):
    with guard("arm coverage"):
        poses = table(ARM / "poses.json")
        samples = table(ARM / "samples.json")
        grid = table(ARM / "grid.json")
        side = json.loads((ARM / "grid.json").read_text(encoding="utf-8"))
        cell = float(side.get("cell_mm") or (side.get("schema") or {}).get("cell_mm"))
        page, ok = open_case(browser, base, "robotics-arm", ARM_KEYS)
        check("arm: the coverage panels draw beside the playback ones (coverage, reach, joint-range)", ok, None)
        # every run at opacity auto: 1/n over each family's paths, n from poses.json
        fam = {}
        for r in poses:
            fam.setdefault(r["source"], set()).add((r["situation"], r["run"], r["body"]))
        sel = f"{D} .dd-panel[data-panel='coverage']"
        op = hook(page, sel, "opacity") or {}
        got = {}
        for s, v in op.items():
            src = next((r["source"] for r in poses if r["situation"] == s), None)
            got.setdefault(src, set()).update(v.get("alpha") or [])
        want = {f: f32(1 / len(p)) for f, p in fam.items()}
        bad = {f: [sorted(got.get(f, ())), want[f]] for f in want if len(got.get(f, ())) != 1 or abs(next(iter(got[f])) - want[f]) > want[f] * 2 ** -22}
        check("arm coverage: every run of every situation at opacity auto, each family's paths at exactly 1/n of that family (n from poses.json)",
              op and not bad, bad or {f: round(1 / len(p), 6) for f, p in fam.items()})
        V = glb_vertices(ARM / "media" / "workspace.glb") * 1000.0
        wait(page, f"(s) => {{ const h = ({HOOK})(s); const w = h && h.workspace(); return !!w && (w.state === 'ready' || w.state === 'failed'); }}", sel, timeout=20000)
        ws = hook(page, sel, "workspace") or {}
        cam = hook(page, sel, "camera") or {}
        pts = (ws.get("fill") or []) + (ws.get("edges") or [])
        got_box = px_box(cam, pts) if cam and pts else None
        want_box = px_box(cam, [[V[:, 0].min(), V[:, 1].min(), 0], [V[:, 0].max(), V[:, 1].max(), 0]]) if cam else None
        err = max(abs(a - b) for a, b in zip(got_box, want_box)) if got_box and want_box else None
        check("arm coverage: from the top, the workspace outline's bounding box (its buffers, through the card's camera) equals the model's projected hull within 1 px",
              cam.get("ortho") and err is not None and err <= 1.0, {"drawn px": got_box and [round(v, 2) for v in got_box], "oracle px": want_box and [round(v, 2) for v in want_box], "worst": err and round(err, 4)})
        # the reach map: pre-gridded cells, anchored on their own lattice, Average per cell
        rsel = f"{D} .dd-panel[data-panel='reach']"
        origin = tuple(min(r[c] for r in grid) - cell / 2 for c in ("x_mm", "y_mm", "z_mm"))
        want_cells = oracle_cells(grid, "property", property="value", cell=cell, origin=origin)
        gc = hook(page, rsel, "cells") or {}
        bad = compare_cells(gc.get("cells"), want_cells, rel=1e-12)
        check(f"arm reach: every cell of BAM Reach's map equals numpy's Average of grid.json's value per {cell:g} mm cell on the rows' own lattice ({len(want_cells)} cells)",
              gc.get("cell") == cell and not bad and want_cells, bad[:4] or {"cells": len(want_cells)})
        sl = hook(page, rsel, "slice") or {}
        k = sl.get("k")
        want_sl = {(i, j): v for (i, j, kk), v in want_cells.items() if kk == k}
        got_sl = slice_values(sl)
        bad = [key for key in set(got_sl) | set(want_sl) if key not in got_sl or key not in want_sl or abs(got_sl[key] - want_sl[key]) > 1e-12 * max(1, abs(want_sl[key]))]
        zc = origin[2] + (k + 0.5) * cell if k is not None else None
        check(f"arm reach: the 2D slice (z ≈ {zc and round(zc, 1)} mm, the mock's 143 mm) is that slice of the oracle, cell by cell",
              sl.get("mode") == "2d" and sl.get("axis") == "z" and zc is not None and abs(zc - 142.887) < cell / 2 and not bad and want_sl, {"k": k, "bad": bad[:4], "cells": len(want_sl)})
        ramp = hook(page, rsel, "ramp") or {}
        lo, hi = hex_rgb(ramp.get("lo")), hex_rgb(ramp.get("hi"))
        check("arm reach: no family in the rows, so the ramp is grey (OKLCH chroma < 0.02 at both ends; never red or green outside verdict)",
              lo and hi and chroma(lo) < 0.02 and chroma(hi) < 0.02 and ramp.get("family") is None, {**ramp, "chroma": lo and hi and [round(chroma(lo), 4), round(chroma(hi), 4)]})
        mx = max(want_sl, key=lambda key: want_sl[key]) if want_sl else None
        if mx and ramp.get("domain") and want_sl[mx] == ramp["domain"][1]:
            cam = hook(page, rsel, "camera") or {}
            px = canvas_pixels(page, rsel)
            at = project(cam, [origin[0] + (mx[0] + 0.5) * cell, origin[1] + (mx[1] + 0.5) * cell, zc]) if cam else None
            rgb = pixel_at(px, *at) if px and at else None
            de = delta_e(rgb, hi) if rgb and hi else None
            check("arm reach: the slice's largest cell is drawn in the ramp's end colour within ΔE 3", de is not None and de <= 3, {"pixel": rgb, "hi": ramp.get("hi"), "ΔE": de and round(de, 2)})
        # each joint's range over every run: whisker ends equal samples.json's min and max per joint
        got = page.evaluate(BOX.replace("d.kind", "d.device"), ["joint-range", "q_deg"]) or {}
        want = {}
        for r in samples:
            if isinstance(r.get("q_deg"), (int, float)):
                a, b = want.get(r["device"], (r["q_deg"], r["q_deg"]))
                want[r["device"]] = (min(a, r["q_deg"]), max(b, r["q_deg"]))
        bad = {k: [got.get(k), want.get(k)] for k in set(got) | set(want) if not got.get(k) or tuple(got[k]) != tuple(want.get(k) or ())}
        check("arm joint range: each joint's whisker ends equal samples.json's min and max of q_deg over every run, exactly", got and not bad, bad or got)
        check("arm: no page error", not page.errors, page.errors[:3])
        page.context.close()


# ------------------------------------------------------------------------------------------------- light, dark, phones
def looks(browser, base):
    for case, keys in (("robotics-servo", ["angle-coverage", "velocity-coverage", "phase-space"]), ("robotics-arm", ["coverage", "reach", "joint-range"])):
        for dark in (False, True):
            for width in (1280, 390):
                tag = f"{case}, {width} px, {'dark' if dark else 'light'}"
                with guard(tag):
                    page, ok = open_case(browser, base, case, keys, width=width, dark=dark)
                    check(f"{tag}: every coverage panel draws", ok, None)
                    check(f"{tag}: the page never scrolls sideways", no_sideways(page, width), page.evaluate("() => document.scrollingElement.scrollWidth"))
                    for k in keys:
                        r = page.evaluate(f"(k) => {{ const p = ({PANEL})(k); if (!p) return null; const b = p.getBoundingClientRect(); return [b.left, b.right, b.width, b.height]; }}", k)
                        check(f"{tag}: panel {k} sits inside the page ({r and [round(v) for v in r]})", r and r[0] >= -0.5 and r[1] <= width + 0.5 and r[2] > 100 and r[3] > 100, r)
                    if case == "robotics-arm":
                        rsel = f"{D} .dd-panel[data-panel='reach']"
                        ramp = hook(page, rsel, "ramp") or {}
                        lo, hi = hex_rgb(ramp.get("lo")), hex_rgb(ramp.get("hi"))
                        check(f"{tag}: the reach ramp runs {'dark to light' if dark else 'light to dark'} (its low end near the surface)",
                              lo and hi and ((lab(lo)[0] < lab(hi)[0]) if dark else (lab(lo)[0] > lab(hi)[0])), ramp)
                    with contextlib.suppress(Exception):
                        page.evaluate("(k) => { const p = document.querySelector(`#example .dd-panel[data-panel='${k}']`); if (p) window.scrollTo(0, p.getBoundingClientRect().top + window.scrollY - 40); }", keys[0])
                        settle(page, 2)
                        page.screenshot(path=str(OUT / f"p2-{case}-coverage-{'dark' if dark else 'light'}-{width}.png"))
                    check(f"{tag}: no page error", not page.errors, page.errors[:3])
                    page.context.close()


def main() -> int:
    root, root_base = serve(ROOT)
    site, site_base = serve(ROOT / "dist" / "site")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for name, fn in (("many runs", lambda: many_runs(browser, root_base)), ("voxels cells", lambda: voxels_cells(browser, root_base)),
                             ("voxels slice light 1280", lambda: voxels_slice(browser, root_base)),
                             ("voxels slice dark 1280", lambda: voxels_slice(browser, root_base, dark=True)),
                             ("voxels slice light 390", lambda: voxels_slice(browser, root_base, width=390)),
                             ("voxels slice dark 390", lambda: voxels_slice(browser, root_base, width=390, dark=True)),
                             ("workspace 1280", lambda: workspace(browser, root_base)), ("workspace 390", lambda: workspace(browser, root_base, width=390)),
                             ("rules and bands", lambda: rules_bands(browser, root_base)),
                             ("servo", lambda: servo(browser, site_base)), ("deployment", lambda: deployment(browser, root_base)),
                             ("arm", lambda: arm(browser, site_base)), ("looks", lambda: looks(browser, site_base))):
                with guard(name):
                    fn()
            browser.close()
    finally:
        for proc in (root, site):
            proc.terminate()
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
    passed = sum(1 for c in checks if c["ok"])
    (OUT / "p2-checks.json").write_text(json.dumps({"checks": checks, "passed": passed, "total": len(checks)}, indent=1, default=str), encoding="utf-8")
    print(f"\n{passed}/{len(checks)} P2 checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
