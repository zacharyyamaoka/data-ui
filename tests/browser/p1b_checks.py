"""PEP 0010 P1b (docs/peps/0010-robotics-playback.md §11): scene3d's stage and Layer 1 primitives, and the trajectory3d
viewer (docs/CONTRACT.md §32), measured in headless Chromium on the built kit. Written red, before the code.

    ~/psu-atlas/.venv/bin/python tests/browser/p1b_checks.py [OUT_DIR]     # after npm run build

The fixture is tests/browser/fixtures/p1b/ (make_fixture.py): one synthetic tool path of 564 samples at 100 Hz per
situation (path.json), one body written in two frames (two-frames.json), and a dashboard's worth of the trajectory
contract on pid-tuning's UR5e forward kinematics in millimetres (arm/, stand-in labels). Every expected number comes
from those files or from the page's own resolved tokens. The page lends only what it drew: the card's camera matrices,
the geometry in its buffers, its materials, the canvas's pixels and the rects of its DOM.

The card's hook, `.dv-scene3d`'s `scene3d` (the legacy calls camera, markers, visible, joints, colors, renders, robot
stay as PEP 0005 built them):
  camera()           {view, proj (column-major 4x4), width, height, position, projection, ortho, animating}
  markers()          {key: [x, y, z]}: each path's "now" marker in world units (key: its series; "<series> · <run>"
                     when a series has several paths); the [data-marker][data-series] ring sits on its projection
  colors()           {grid, series: {name: '#rrggbb'}}: each series' colour as drawn
  window()           {t, lo, hi, show, decay, fade}: the time window the primitives draw now (lo / hi null: unbounded)
  drawn()            {series: {first, last, n}}: the first and last sample of each series' line inside the window
  builds()           primitive geometries built so far (a clock tick builds none)
  size()             {items}: every drawable item (segment, point, cone…) in the card's buffers, inside the window or not
  counts()           {series: {line, points, frames, 'frames-z', arrows, arcs}}: drawn items inside the window
  geometry(s, mode)  what that series draws in that mode, read back from its buffers in world units:
                     {points: [[x, y, z]…], times} or {segments: [[[x, y, z], [x, y, z]]…], times} (times as the shader
                     holds them: float32, so within 1e-6 s)
  robots()           {series: {color: '#rrggbb', opacity, visible}}: each robot's material as set
  problem()          why nothing is drawn (null when something is)
DOM: [data-cube] (the view cube's area: its rect is the drawn cube), [data-tick][data-axis][data-value] (an axis
label; data-axis is the world axis), [data-axis-title], .dv-scene3d-poster; trajectory3d's controls
[data-t3-series="<series>"] [data-mode="line|points|frames|frames-z"] (a click toggles), [data-robot-color] (a select),
[data-robot-opacity] (a range, percent), [data-show] (a select: all | trail), [data-decay] (seconds or inf; change
commits).

Serves the repo root (the fixture and /dist/) and dist/site (the old 3D cases, run through their own checks.py) on free
127.0.0.1 ports, stops both when done, writes OUT_DIR/p1b-checks.json (default reports/media/robotics-p1b) with its
screenshots, and exits 1 if any check fails.
"""

from __future__ import annotations

import base64
import bisect
import contextlib
import importlib.util
import io
import json
import math
import os
import pathlib
import re
import socket
import statistics
import subprocess
import sys
import time
import urllib.request

from PIL import Image  # noqa: F401  (the screenshots' composites are the report's; kept for parity with p0_checks)
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "robotics-p1b"
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "browser" / "fixtures" / "p1b"
PAGE = "/tests/browser/fixtures/p1b/p1b.html"
PATH_BASE = "/tests/browser/fixtures/p1b/path.base"
FRAMES_BASE = "/tests/browser/fixtures/p1b/two-frames.base"
ARM_BASE = "/tests/browser/fixtures/p1b/arm/arm.base"
WAIT = 30000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
checks: list[dict] = []


def rows(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))["rows"]


def check(name, ok, value=None, soft=False):
    checks.append({"name": name, "ok": bool(ok), "value": value, **({"soft": True} if soft else {})})
    print(("SOFT " if soft else "PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def budget(name, ms, limit, value=None):
    """A speed budget that knows the machine it ran on (tests/browser/checks.py's rule): enforced while the 1-minute
    load average is under the CPU count; above it a miss is SOFT with the load beside it, never a silent pass."""
    load, cpus = os.getloadavg()[0], os.cpu_count() or 1
    note = f"{ms:.3f} ms (budget {limit} ms); load {load:.1f} on {cpus} CPUs" + (f"; {value}" if value else "")
    if ms <= limit or load <= cpus:
        check(name, ms <= limit, note)
    else:
        check(name, True, note + " -- OVERLOADED: budget not enforced on this run", soft=True)


@contextlib.contextmanager
def guard(what):
    """A section that cannot run (nothing drawn to measure) is one failing check in its own words, not a crash."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------------------------------------- the oracles
PATH = rows(FIX / "path.json")
FRAMES = rows(FIX / "two-frames.json")
ARM_POSES = rows(FIX / "arm" / "poses.json")


def series_of(rs, situation, run=None):
    out = [r for r in rs if r["situation"] == situation and (run is None or r["run"] == run)]
    return sorted(out, key=lambda r: r["t"])


REAL = series_of(PATH, "real")
REAL_T = [r["t"] for r in REAL]
DT = REAL_T[1] - REAL_T[0]  # one sample: 0.01 s


def markers_at(n, density):
    """traj_compare's density rule (viewer3d.js markerIndices; CONTRACT §32): samples 0, s, 2s, … with s = ⌊n / density⌋
    (at least 1), plus the last."""
    s = max(1, n // density)
    idx = list(range(0, n, s))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return idx


def interp(rs, t, cols=("x_mm", "y_mm", "z_mm")):
    ts = [r["t"] for r in rs]
    if t <= ts[0]:
        return [rs[0][c] for c in cols]
    if t >= ts[-1]:
        return [rs[-1][c] for c in cols]
    i = bisect.bisect_right(ts, t)
    a, b = rs[i - 1], rs[i]
    f = (t - a["t"]) / (b["t"] - a["t"])
    return [a[c] + (b[c] - a[c]) * f for c in cols]


def z_axis(r):
    """The +Z column of a row's rotation (wxyz quaternion, normalised first)."""
    w, x, y, z = (r[f"quat_{c}"] for c in "wxyz")
    n = math.sqrt(w * w + x * x + y * y + z * z)
    w, x, y, z = w / n, x / n, y / n, z / n
    return [2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)]


def mul(m, v):
    return [sum(m[col * 4 + row] * v[col] for col in range(4)) for row in range(4)]


def project(cam, p):
    """CSS px relative to the canvas of world point p, through the card's camera (column-major 4x4 matrices)."""
    clip = mul(cam["proj"], mul(cam["view"], [p[0], p[1], p[2], 1.0]))
    x, y = clip[0] / clip[3], clip[1] / clip[3]
    return ((x + 1) / 2 * cam["width"], (1 - y) / 2 * cam["height"])


def forward(cam):
    """The direction the camera looks, in world coordinates: minus the view matrix's third row."""
    v = cam["view"]
    f = [-v[2], -v[6], -v[10]]
    n = math.sqrt(sum(c * c for c in f)) or 1
    return [c / n for c in f]


def angle_deg(a, b):
    na, nb = math.sqrt(sum(c * c for c in a)), math.sqrt(sum(c * c for c in b))
    d = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b)) / (na * nb)))
    return math.degrees(math.acos(d))


def rgb_hex(text):
    m = re.findall(r"[\d.]+", text or "")
    return "#%02x%02x%02x" % tuple(round(float(c)) for c in m[:3]) if len(m) >= 3 else None


def hex_rgb(h):
    h = (h or "").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else None


def near(a, b, tol):
    return a is not None and b is not None and all(x is not None and y is not None and abs(x - y) <= tol for x, y in zip(a, b))


def ink(pixels, color, alpha=25, dist=80):
    """How many of the sampled pixels are drawn in `color` (unpremultiplied RGB within `dist`, alpha at least `alpha`)."""
    c = hex_rgb(color)
    return sum(1 for p in pixels if p[3] >= alpha and c and math.dist(p[:3], c) <= dist)


# ------------------------------------------------------------------------------------------------- page helpers
COUNT_WEBGL = """(() => {
  const seen = new WeakSet();
  window.__webglContexts = 0;
  const orig = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
    const c = orig.call(this, type, ...rest);
    if (c && /^(webgl2?|experimental-webgl)$/.test(type) && !seen.has(c)) { seen.add(c); window.__webglContexts++; }
    return c;
  };
})()"""

MOUNT_VIEWS = """([id, src, view, noUrl]) => {
  for (const old of document.querySelectorAll('data-dashboard, data-views')) old.remove();
  const v = document.createElement('data-views');
  v.id = id; v.className = 'boxed';
  v.setAttribute('toolbar', 'none');
  if (noUrl) v.setAttribute('no-url', '');
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

SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 30))))"
HOOK = "(sel) => { const r = document.querySelector(sel + ' .dv-scene3d'); return r && r.scene3d ? r.scene3d : null; }"
DRAWN = f"(sel) => {{ const h = ({HOOK})(sel); try {{ return !!h && h.renders() > 0; }} catch (e) {{ return false; }} }}"


def open_page(browser, base, *, width=1280, dark=False, mobile=False, count_gl=False):
    context = browser.new_context(viewport={"width": width, "height": 900 if width > 500 else 844}, color_scheme="dark" if dark else "light",
                                  device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    if count_gl:
        context.add_init_script(COUNT_WEBGL)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.goto(f"{base}{PAGE}")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    return page


def settle(page, n=2):
    for _ in range(n):
        page.evaluate(SETTLE)


def hook(page, sel, call, *args):
    """A call on the card's hook; null when the card or the call is missing (the check then FAILs in its own words)."""
    return page.evaluate(f"([sel, args]) => {{ const h = ({HOOK})(sel); try {{ return h ? h.{call}(...args) : null; }} catch (e) {{ return null; }} }}", [sel, list(args)])


def wait(page, js, arg=None, timeout=WAIT):
    try:
        page.wait_for_function(js, arg=arg, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001 -- the state never came: the caller's check says so
        return False


def mount_views(page, src, view=None, *, no_url=True, sel="#v"):
    page.evaluate(MOUNT_VIEWS, [sel.lstrip("#"), src, view, no_url])
    ok = wait(page, DRAWN, sel)
    settle(page)
    return ok


def mount_dash(page, src, keys):
    page.evaluate(MOUNT_DASH, ["dash", src])
    ok = wait(page, """(keys) => { const d = document.getElementById('dash'); if (!d || !d.dash) return false;
      const els = [...d.querySelectorAll('.dd-panel data-views')]; return els.length && els.every((e) => e.dataset.view); }""", keys)
    for k in keys:
        page.locator(f"#dash .dd-panel[data-panel='{k}']").scroll_into_view_if_needed()
        ok = wait(page, DRAWN, f"#dash .dd-panel[data-panel='{k}']") and ok
    settle(page, 3)
    return ok


def panel(key):
    return f"#dash .dd-panel[data-panel='{key}']"


def seek(page, sel, t):
    page.evaluate("([sel, t]) => { const c = window.kit.clockFor(document.querySelector(sel)); c.pause(); c.seek(t); }", [sel, t])
    settle(page)


def set_view(page, sel, block):
    """host.setView on the card's <data-views>, merging `block` into its trajectory3d entry (the controls' own path)."""
    page.evaluate("""([sel, block]) => { const el = document.querySelector(sel).closest('data-views') || document.querySelector(sel + ' data-views') || document.querySelector(sel);
      const v = el.view || {}; el.setView({ trajectory3d: { ...(v.trajectory3d || {}), ...block } }); }""", [sel, block])
    settle(page, 3)


def view_entry(page, sel):
    return page.evaluate("(sel) => { const el = document.querySelector(sel).closest('data-views') || document.querySelector(sel + ' data-views') || document.querySelector(sel); return el && el.view ? JSON.parse(JSON.stringify(el.view)) : null; }", sel)


def canvas_rect(page, sel):
    return page.evaluate("(sel) => { const c = document.querySelector(sel + ' .dv-scene3d canvas'); if (!c) return null; const r = c.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }", sel)


def pixels(page, sel, pts, r=3):
    """The canvas's pixels (unpremultiplied RGBA) in a (2r+1)² square around each point (CSS px from the canvas)."""
    return page.evaluate("""([sel, pts, r]) => { const c = document.querySelector(sel + ' .dv-scene3d canvas'); if (!c || !c.width) return null;
      const k = c.width / c.clientWidth, g = c.getContext('2d'), R = Math.max(1, Math.round(r * k));
      return pts.map(([x, y]) => { const d = g.getImageData(Math.round(x * k) - R, Math.round(y * k) - R, 2 * R + 1, 2 * R + 1).data; const out = [];
        for (let i = 0; i < d.length; i += 4) out.push([d[i], d[i + 1], d[i + 2], d[i + 3]]); return out; }); }""", [sel, pts, r])


def tokens(page, sel):
    """The page's resolved tokens as the card's <data-views> sees them: the series slots and muted, as #rrggbb."""
    t = page.evaluate("(sel) => { const el = document.querySelector(sel).closest('data-views') || document.querySelector(sel + ' data-views') || document.querySelector(sel); return el.tokens(); }", sel)
    return {"series": [rgb_hex(s) for s in t["series"]], "muted": rgb_hex(t["muted"]), "dark": t.get("dark")}


def cube_click(page, sel, *, tap=False):
    """Click (or tap) the view cube's +Z ball, found from the camera, not from the card: the cube shows the camera's
    rotation (three's ViewHelper), so +Z sits at the view matrix's third column, through the cube's ortho camera
    (−2 … 2) onto [data-cube]'s rect. Then wait for the animation to end."""
    with contextlib.suppress(Exception):
        page.locator(f"{sel} [data-cube]").first.scroll_into_view_if_needed()
        settle(page)
    cam = hook(page, sel, "camera")
    rect = page.evaluate("(sel) => { const e = document.querySelector(sel + ' [data-cube]'); if (!e) return null; const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }", sel)
    if not cam or not rect:
        return None, cam, rect
    v = cam["view"]
    px = rect[0] + (v[8] / 2 + 1) / 2 * rect[2]
    py = rect[1] + (1 - v[9] / 2) / 2 * rect[3]
    if tap:
        page.touchscreen.tap(px, py)
    else:
        page.mouse.click(px, py)
    ok = wait(page, f"(sel) => {{ const h = ({HOOK})(sel); const c = h && h.camera(); return !!c && c.ortho && !c.animating; }}", sel, timeout=10000)
    settle(page, 2)
    return ok, cam, [px, py]


def decode_v(hash_):
    m = re.search(r"(?:^|[#&])v=([^&]*)", hash_ or "")
    if not m:
        return None
    b = m.group(1)
    return json.loads(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode("utf-8"))


def ticks(page, sel):
    return page.evaluate("""(sel) => { const c = document.querySelector(sel + ' .dv-scene3d canvas'); if (!c) return null; const cr = c.getBoundingClientRect();
      return { ticks: [...document.querySelectorAll(sel + ' [data-tick]')].filter((e) => e.getClientRects().length).map((e) => { const r = e.getBoundingClientRect();
        return { axis: e.dataset.axis, value: Number(e.dataset.value), text: e.textContent, cx: r.left + r.width / 2 - cr.left, cy: r.top + r.height / 2 - cr.top }; }),
        titles: [...document.querySelectorAll(sel + ' [data-axis-title]')].filter((e) => e.getClientRects().length).map((e) => e.textContent) }; }""", sel)


def tick_errors(cam, got):
    """Each label's centre against its value's projection along the screen direction its world axis runs (1 unit along
    the axis decides: horizontal → x, vertical → y)."""
    out, worst, per = [], 0.0, {}
    for t in (got or {}).get("ticks", []):
        i = "xyz".index(t["axis"]) if t["axis"] in ("x", "y", "z") else None
        if i is None or not math.isfinite(t["value"]):
            out.append({"bad tick": t})
            continue
        p0, p1 = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        p0[i], p1[i] = t["value"], t["value"] + 1
        a, b = project(cam, p0), project(cam, p1)
        horizontal = abs(b[0] - a[0]) >= abs(b[1] - a[1])
        err = abs(t["cx"] - a[0]) if horizontal else abs(t["cy"] - a[1])
        worst = max(worst, err)
        per[t["axis"]] = per.get(t["axis"], 0) + 1
        if err > 1:
            out.append({"axis": t["axis"], "value": t["value"], "label px": [round(t["cx"], 2), round(t["cy"], 2)], "want px": [round(a[0], 2), round(a[1], 2)], "err": round(err, 3)})
    return out, worst, per


def no_sideways(page, width):
    return page.evaluate("() => document.scrollingElement.scrollWidth") <= width


def shot(page, name, sel=None):
    try:
        if sel:
            page.locator(sel).first.screenshot(path=str(OUT / f"{name}.png"))
        else:
            page.screenshot(path=str(OUT / f"{name}.png"))
    except Exception as e:  # noqa: BLE001 -- a missing picture is not a failed behaviour; say so
        print(f"(screenshot {name} not taken: {e})")


# ------------------------------------------------------------------------------------------------- projection, scale, axes
def projection(browser, base):
    sel = "#v"
    page = open_page(browser, base)
    drew = mount_views(page, PATH_BASE, "Axes", no_url=False)
    check("projection: the trajectory3d card draws the path fixture (a frame rendered)", drew, hook(page, sel, "renders"))
    cam0 = hook(page, sel, "camera")
    check("projection: it opens in perspective (proj[15] == 0), the contract's default", bool(cam0) and cam0["proj"][15] == 0, cam0 and cam0["proj"][15])
    shot(page, "p1b-path-3d-light-1280", f"{sel}")
    ok, before, at = cube_click(page, sel)
    cam = hook(page, sel, "camera")
    fwd = forward(cam) if cam else None
    ang = angle_deg(fwd, [0, 0, -1]) if fwd else None
    check("projection: a click on the view cube's +Z ball makes the camera orthographic (proj[15] == 1) looking along −Z within 0.1°",
          bool(ok) and cam["proj"][15] == 1 and ang is not None and ang <= 0.1, {"clicked px": at, "proj[15]": cam and cam["proj"][15], "forward": fwd, "angle deg": ang})
    up = None
    if cam:
        v = cam["view"]
        up = [v[1], v[5], v[9]]  # the camera's +Y (screen up) in world: the view matrix's second row
    check("projection: top's screen up is +y (CONTRACT §32: top looks along −z, screen up +y)", up is not None and angle_deg(up, [0, 1, 0]) <= 0.1, up)
    got = decode_v(page.evaluate("location.hash"))
    proj = ((got or {}).get("trajectory3d") or {}).get("projection")
    check("projection: the URL's v= holds projection: top (host.setView)", proj == "top", {"v": got})
    shot(page, "p1b-path-top-light-1280", sel)

    # ---- equal scale, by construction: 100 mm on x and on y project the same length on screen
    if cam:
        o, ex, ey = project(cam, [0, 0, 0]), project(cam, [100, 0, 0]), project(cam, [0, 100, 0])
        lx, ly = math.dist(o, ex), math.dist(o, ey)
        check("equal scale: in the top view 100 mm on x and 100 mm on y project within 0.5 px of each other", abs(lx - ly) <= 0.5 and lx > 10,
              {"x px": round(lx, 4), "y px": round(ly, 4), "diff": round(abs(lx - ly), 4)})

    # ---- axes: tick labels at their values' projections
    tk = ticks(page, sel)
    errs, worst, per = tick_errors(cam, tk) if cam else ([{"no camera": True}], None, {})
    check("axes: in the top view every tick label sits at its value's projection within 1 px (x and y, ≥ 3 ticks each)",
          not errs and per.get("x", 0) >= 3 and per.get("y", 0) >= 3, errs[:4] or {"ticks per axis": per, "worst px": round(worst or 0, 3)})
    titles = (tk or {}).get("titles") or []
    check("axes: titled with the axis, the unit and the frame ('x (mm)', 'y (mm)', 'frame: base')",
          any("x (mm)" in t for t in titles) and any("y (mm)" in t for t in titles) and any("frame: base" in t for t in titles), titles)

    # ---- a pan and a zoom keep the scale equal and the labels on their ticks
    rect = canvas_rect(page, sel)
    if rect:
        cx, cy = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
        page.mouse.move(cx, cy)
        page.mouse.wheel(0, -240)
        settle(page, 2)
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.move(cx + 60, cy - 25, steps=6)
        page.mouse.up()
        settle(page, 2)
        cam2 = hook(page, sel, "camera")
        o, ex, ey = project(cam2, [0, 0, 0]), project(cam2, [100, 0, 0]), project(cam2, [0, 100, 0])
        errs, worst, per = tick_errors(cam2, ticks(page, sel))
        fwd2 = forward(cam2)
        check("2D: after a wheel zoom and a drag the view still looks along −Z (nothing rotates), 100 mm on x and y are equal within 0.5 px and every tick label is on its projection within 1 px",
              cam2["proj"][15] == 1 and angle_deg(fwd2, [0, 0, -1]) <= 0.1 and abs(math.dist(o, ex) - math.dist(o, ey)) <= 0.5 and math.dist(o, ex) > math.dist(project(cam, [0, 0, 0]), project(cam, [100, 0, 0])) + 1
              and not errs and per.get("x", 0) >= 2 and per.get("y", 0) >= 2,
              {"x px": round(math.dist(o, ex), 3), "y px": round(math.dist(o, ey), 3), "tick errors": errs[:3], "worst": round(worst or 0, 3)})

    # ---- a reload restores the projection from v=
    page.reload()
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    mount_views(page, PATH_BASE, "Axes", no_url=False)
    cam3 = hook(page, sel, "camera")
    ang3 = angle_deg(forward(cam3), [0, 0, -1]) if cam3 else None
    check("projection: a reload of that URL restores the top view (orthographic, looking along −Z within 0.1°)",
          bool(cam3) and cam3["proj"][15] == 1 and ang3 is not None and ang3 <= 0.1, {"proj[15]": cam3 and cam3["proj"][15], "angle deg": ang3})
    check("projection: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- frames
def frames(browser, base):
    sel = "#v"
    page = open_page(browser, base)
    mount_views(page, FRAMES_BASE, "Path")
    wait(page, "(sel) => { const p = document.querySelector(sel + ' .dv-scene3d-poster'); return !!p && !p.hidden && /base/.test(p.textContent); }", sel, timeout=10000)
    poster = page.evaluate("(sel) => { const p = document.querySelector(sel + ' .dv-scene3d-poster'); return p && !p.hidden && p.getClientRects().length ? p.textContent : null; }", sel)
    counts = hook(page, sel, "counts") or {}
    drawn = sum(v for s in counts.values() for v in s.values() if isinstance(v, (int, float)))
    marks = hook(page, sel, "markers")
    want = sorted({r["frame"] for r in FRAMES})
    check(f"frames: rows of one body in two frames ({', '.join(want)}) draw nothing (no item, no marker) and the card names both",
          poster is not None and all(f in poster for f in want) and drawn == 0 and marks == {} and hook(page, sel, "problem") is not None,
          {"poster": poster, "drawn items": drawn, "markers": marks})
    page.evaluate("(sel) => document.querySelector(sel).setView({ filters: 'frame == \"base\"' })", sel)
    wait(page, f"(sel) => {{ const h = ({HOOK})(sel); const c = h && h.counts(); return !!c && Object.values(c).some((s) => s.line > 0); }}", sel, timeout=10000)
    counts = hook(page, sel, "counts") or {}
    base_rows = [r for r in FRAMES if r["frame"] == "base"]
    check("frames: a filter that leaves one frame draws its path (every segment of base's 201 samples), the message gone",
          (counts.get("real") or {}).get("line") == len(base_rows) - 1 and hook(page, sel, "problem") is None, counts)
    check("frames: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- decay
def decay(browser, base):
    sel = "#v"
    page = open_page(browser, base)
    mount_views(page, PATH_BASE, "Decay")
    seek(page, sel, 3.0)
    w = hook(page, sel, "window") or {}
    d = (hook(page, sel, "drawn") or {}).get("real") or {}
    check("decay: at t = 3.0 with decay 0.5 the window is [2.5, 3.0] (the card's hook)", near([w.get("lo"), w.get("hi")], [2.5, 3.0], 1e-9) if w.get("lo") is not None else False, w)
    check(f"decay: the drawn samples run 2.5 … 3.0 within one sample ({DT:g} s)",
          d.get("first") is not None and 2.5 - 1e-9 <= d["first"] <= 2.5 + DT + 1e-9 and 3.0 - DT - 1e-9 <= d["last"] <= 3.0 + 1e-9, d)
    cam = hook(page, sel, "camera")
    color = (hook(page, sel, "colors") or {}).get("series", {}).get("real")
    probe = {t: project(cam, interp(REAL, t)) for t in (2.0, 2.75, 3.4)} if cam else {}
    px = pixels(page, sel, list(probe.values()), 3) if probe else None
    got = {t: ink(p, color) for t, p in zip(probe, px or [])}
    check("decay: the canvas shows the trail at t = 2.75 and nothing of the path at t = 2.0 (behind the window) or 3.4 (the future), pixels in the series' colour within 3 px of the oracle's projection",
          bool(got) and got[2.75] > 0 and got[2.0] == 0 and got[3.4] == 0, {"inked px": got, "colour": color})
    shot(page, "p1b-decay-light-1280", sel)
    set_view(page, sel, {"decay": "inf"})
    seek(page, sel, 3.0)
    w = hook(page, sel, "window") or {}
    d = (hook(page, sel, "drawn") or {}).get("real") or {}
    cam = hook(page, sel, "camera")
    probe = {t: project(cam, interp(REAL, t)) for t in (0.5, 3.4)} if cam else {}
    px = pixels(page, sel, list(probe.values()), 3) if probe else None
    got = {t: ink(p, color) for t, p in zip(probe, px or [])}
    check("decay: inf starts at t0 (the window has no lower bound; the first drawn sample is the path's first, t = 0) and still ends at t",
          w.get("lo") is None and near([w.get("hi")], [3.0], 1e-9) and d.get("first") == REAL_T[0] and d.get("last") is not None and abs(d["last"] - 3.0) <= DT, {"window": w, "drawn": d})
    check("decay: with inf the canvas shows the path at t = 0.5 and still nothing at 3.4", bool(got) and got[0.5] > 0 and got[3.4] == 0, got)
    check("decay: no page error", not page.errors, page.errors[:3])
    page.context.close()


BIG = """async ([n]) => {
  for (const old of document.querySelectorAll('data-dashboard, data-views')) old.remove();
  const v = document.createElement('data-views'); v.id = 'big'; v.className = 'boxed'; v.setAttribute('no-url', ''); v.setAttribute('toolbar', 'none');
  document.body.append(v);
  const rows = new Array(n);
  for (let k = 0; k < n; k++) { const t = k / 1000;
    rows[k] = { t, run: 'big/r1', situation: 'real', source: 'real', body: 'tool0', frame: 'base', x_mm: -300 + t * 4, y_mm: 120 * Math.sin(t / 3), z_mm: 200 + 40 * Math.cos(t / 7),
      quat_w: 0, quat_x: 1, quat_y: 0, quat_z: 0 }; }
  const num = { type: 'number' }, text = { type: 'text' };
  v.base = { views: [{ type: 'trajectory3d', name: 'Big', trajectory3d: { show: 'trail', decay: 0.5 } }] };
  v.data = { id: 'p1b-big', properties: { t: num, run: text, situation: text, source: text, body: text, frame: text, x_mm: num, y_mm: num, z_mm: num, quat_w: num, quat_x: num, quat_y: num, quat_z: num }, rows };
  return true;
}"""

TICKS = """async ([n]) => {
  const v = document.getElementById('big'); const h = v.querySelector('.dv-scene3d').scene3d; const clock = window.kit.clockFor(v);
  const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  clock.pause();
  await frame();
  const b0 = h.builds(), r0 = h.renders(), ms = [];
  for (let i = 0; i < n; i++) {
    const t = 5 + i * 3.7;
    const a = performance.now();
    clock.seek(t);
    ms.push(performance.now() - a);
    await frame();
  }
  return { ms, builds: [b0, h.builds()], renders: [r0, h.renders()], window: h.window(), gl: globalThis.__dataUiGL ? globalThis.__dataUiGL.stats() : null };
}"""


def tick_cost(browser, base):
    sel = "#big"
    page = open_page(browser, base)
    n = 150000
    page.evaluate(BIG, [n])
    drew = wait(page, DRAWN, sel, timeout=60000)
    settle(page, 3)
    size = hook(page, sel, "size") or {}
    w = page.evaluate(TICKS, [30]) if drew else None
    ms = (w or {}).get("ms") or []
    med = statistics.median(ms) if ms else float("inf")
    check(f"decay at scale: a {n:,}-sample path is in the card's buffers (≥ {n - 1:,} segments) and drawn", drew and (size.get("items") or 0) >= n - 1, size)
    check("decay at scale: 30 clock ticks build no geometry (builds() unchanged) and each one draws (renders up by ≥ 30)",
          bool(w) and w["builds"][0] == w["builds"][1] and w["renders"][1] - w["renders"][0] >= 30, w and {k: w[k] for k in ("builds", "renders", "window")})
    budget(f"decay at scale: a clock tick at {n:,} vertices costs ≤ 2 ms (median of 30 seeks; the uniforms move, nothing is rebuilt)", med, 2,
           ms and f"max {max(ms):.3f} ms; the GPU frame after it {((w or {}).get('gl') or {}).get('renderMs', 0):.1f} ms (EMA)")
    check("decay at scale: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- display modes
def modes(browser, base):
    sel = "#v"
    page = open_page(browser, base)
    mount_views(page, PATH_BASE, "Modes")
    c = (hook(page, sel, "counts") or {}).get("real") or {}
    idx = markers_at(len(REAL), 20)
    check(f"modes: density 20 on the {len(REAL)}-sample path draws exactly {len(idx)} points (stride ⌊{len(REAL)}/20⌋ = {len(REAL) // 20}, plus the last sample)",
          c.get("points") == len(idx) == 22, c)
    g = hook(page, sel, "geometry", "real", "points") or {}
    want = [[REAL[i][k] for k in ("x_mm", "y_mm", "z_mm")] for i in idx]
    pts = g.get("points") or []
    off = max((max(abs(a - b) for a, b in zip(p, q)) for p, q in zip(pts, want)), default=None)
    times = g.get("times") or []
    toff = max((abs(a - REAL[i]["t"]) for a, i in zip(times, idx)), default=None)
    check("modes: the points sit on the marker samples 0, 28, … 560, 563 (positions within 0.01 mm, times within 1e-6 s)",
          len(pts) == len(want) and off is not None and off <= 0.01 and len(times) == len(idx) and toff is not None and toff <= 1e-6,
          {"points": len(pts), "worst mm": off, "worst s": toff, "times": times[:4] + ["…"] + times[-2:]})
    check(f"modes: frames-z draws one Z segment per marker ({len(idx)})", c.get("frames-z") == len(idx), c)
    g = hook(page, sel, "geometry", "real", "frames-z") or {}
    segs = g.get("segments") or []
    bad, worst = [], 0.0
    for (a, b), i in zip(segs, idx):
        start = [REAL[i][k] for k in ("x_mm", "y_mm", "z_mm")]
        ang = angle_deg([q - p for p, q in zip(a, b)], z_axis(REAL[i]))
        worst = max(worst, ang)
        if max(abs(x - y) for x, y in zip(a, start)) > 0.01 or ang > 0.1:
            bad.append({"i": i, "start": a, "want": start, "angle": round(ang, 4)})
    check("modes: each Z segment starts at its marker sample and runs along that sample's +Z (the quaternion's third column) within 0.1°",
          len(segs) == len(idx) and not bad, bad[:3] or {"segments": len(segs), "worst deg": round(worst, 5)})
    set_view(page, sel, {"density": 7})
    c = (hook(page, sel, "counts") or {}).get("real") or {}
    idx7 = markers_at(len(REAL), 7)
    check(f"modes: density 7 draws {len(idx7)} points and {len(idx7)} Z segments (stride {len(REAL) // 7}, plus the last)",
          c.get("points") == len(idx7) and c.get("frames-z") == len(idx7), c)
    set_view(page, sel, {"density": 20, "modes": {"real": ["frames"]}})
    c = (hook(page, sel, "counts") or {}).get("real") or {}
    g = hook(page, sel, "geometry", "real", "frames") or {}
    check(f"modes: frames (full) draws one triad per marker ({len(idx)}: {3 * len(idx)} axis segments) and no line or points",
          c.get("frames") == len(idx) and len(g.get("segments") or []) == 3 * len(idx) and not c.get("line") and not c.get("points"), {"counts": c, "segments": len(g.get("segments") or [])})
    shot(page, "p1b-modes-light-1280", sel)
    check("modes: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- the arm dashboard
ARM_KEYS = ["path-3d", "path-top"]


def pick_device(page, value):
    page.locator(f"#dash .dd-rail data-facets[data-dataset='samples'] section.df-group[data-key='device'] input[type=radio][data-value='{value}']").check()
    settle(page, 4)


def status_rows(page, key):
    t = page.evaluate("(sel) => { const s = document.querySelector(sel + ' data-views .dv-status'); return s ? s.textContent : ''; }", panel(key))
    m = re.search(r"([\d,]+) of ([\d,]+)", t or "")
    return int(m.group(1).replace(",", "")) if m else None


def arm(browser, base):
    page = open_page(browser, base, count_gl=True)
    drew = mount_dash(page, ARM_BASE, ARM_KEYS)
    sel = panel("path-3d")
    check("arm: both trajectory3d cards of the dashboard draw", drew, [hook(page, panel(k), "renders") for k in ARM_KEYS])

    # ---- families: the hue from style.families
    tk = tokens(page, sel)
    col = (hook(page, sel, "colors") or {}).get("series") or {}
    want = {"real": tk["series"][0], "twin": tk["series"][1], "target": tk["muted"], "replay": tk["muted"]}
    check("families: real = slot 1, twin (family sim) = slot 2, target = muted, replay (a family the map does not list) = muted, as drawn",
          all(col.get(s) == c for s, c in want.items()), {"drawn": col, "want": want})
    legend = page.evaluate("(sel) => Object.fromEntries([...document.querySelectorAll(sel + ' .dv-scene3d-legend .dv-legend-key')].map((b) => [b.dataset.legendSeries, b.textContent]))", sel)
    check("families: the legend says the unlisted family is unclassified (and only it)",
          "unclassified" in (legend.get("replay") or "") and not any("unclassified" in (legend.get(s) or "") for s in ("real", "twin", "target")), legend)
    shot(page, "p1b-arm-light-1280")

    # ---- robots: colour and opacity per robot, as the .base sets them, then from the card's menu
    ok = wait(page, f"(sel) => {{ const h = ({HOOK})(sel); const r = h && h.robots(); return !!r && ['real', 'twin', 'target'].every((s) => r[s] && r[s].visible); }}", sel, timeout=WAIT)
    rb = hook(page, sel, "robots") or {}
    want = {"real": (tk["series"][0], 1), "twin": (tk["series"][4], 0.5), "target": (tk["muted"], 0.2)}
    got = {s: (v.get("color"), v.get("opacity")) for s, v in rb.items()}
    check("robots: each robot's material reads back as set: real its series' colour at 1, twin slot 5 at 0.5, target muted at 0.2",
          ok and all(got.get(s) is not None and got[s][0] == c and abs(got[s][1] - o) <= 1e-6 for s, (c, o) in want.items()), {"got": got, "want": want})
    row = f"{sel} [data-t3-series='twin']"
    try:
        page.locator(f"{row} [data-robot-color]").select_option("muted")
        page.evaluate("(s) => { const e = document.querySelector(s); e.value = '30'; e.dispatchEvent(new Event('input', { bubbles: true })); e.dispatchEvent(new Event('change', { bubbles: true })); }", f"{row} [data-robot-opacity]")
        settle(page, 3)
    except Exception as e:  # noqa: BLE001
        print(f"(the robot menu could not be driven: {e})")
    rb = hook(page, sel, "robots") or {}
    entry = ((view_entry(page, sel) or {}).get("trajectory3d") or {}).get("robots", {}).get("series", {}).get("twin")
    check("robots: the card's menu sets twin's robot muted at 30 %: its material reads back muted, 0.3, and the view entry says so (host.setView)",
          (rb.get("twin") or {}).get("color") == tk["muted"] and abs(((rb.get("twin") or {}).get("opacity") or 0) - 0.3) <= 1e-6
          and entry is not None and entry.get("color") == "muted" and abs(entry.get("opacity", 0) - 0.3) <= 1e-6, {"robot": rb.get("twin"), "entry": entry})

    # ---- one WebGL context for the page (two 3D cards, their cubes and the robots)
    st = page.evaluate("() => globalThis.__dataUiGL ? globalThis.__dataUiGL.stats() : null")
    n = page.evaluate("() => window.__webglContexts")
    check("one WebGL context on the page: two trajectory3d cards with view cubes and three robots drawn (getContext counted before load)",
          n == 1 and st and st["contexts"] == 1 and st["scenes"] == 2, {"webglContexts": n, "stats": st})

    # ---- hover: a timeseries hover places the 3D marker on the path at that instant
    pick_device(page, "J3 elbow")
    one = wait(page, f"(sel) => {{ const h = ({HOOK})(sel); const m = h && h.markers(); return !!m && 'real' in m; }}", sel, timeout=10000)
    plot = page.locator(f"{panel('tool-z')} .dv-timeseries-plot")
    plot.scroll_into_view_if_needed()
    box = plot.bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] * 0.5)
    has = wait(page, "() => { const c = document.getElementById('dash').clock; return c.hover !== null; }", timeout=5000)
    settle(page, 2)
    # WHY no scroll from here: the marker's place is read relative to the card's canvas, so the card need not be on
    # screen, and a scroll would move the pointer off the plot (pointerleave clears the hover)
    th = page.evaluate("() => document.getElementById('dash').clock.hover")
    cam = hook(page, sel, "camera")
    mk = page.evaluate("(sel) => { const root = document.querySelector(sel + ' .dv-scene3d'); const c = root && root.querySelector('canvas').getBoundingClientRect(); const m = root && root.querySelector('[data-marker][data-series=\"real\"]'); if (!m || m.hidden) return null; const r = m.getBoundingClientRect(); return [r.left + r.width / 2 - c.left, r.top + r.height / 2 - c.top]; }", sel)
    real = series_of(ARM_POSES, "real", "arm/r1")
    p3 = interp(real, th) if th is not None else None
    want_px = project(cam, p3) if cam and p3 else None
    world = (hook(page, sel, "markers") or {}).get("real")
    check("hover: a hover on the Tool z time series at t_h puts the 3D card's real marker on the path's projection at t_h within 1 px (and its world point on the oracle's within 0.01 mm)",
          one and has and th is not None and mk and want_px and math.dist(mk, want_px) <= 1 and world and max(abs(a - b) for a, b in zip(world, p3)) <= 0.01,
          {"t_h": th, "marker px": mk, "want px": want_px, "world": world, "oracle": p3})
    page.evaluate("() => document.getElementById('dash').clock.setHover(null)")
    settle(page)

    # ---- persistence: the projection, the decay and the modes, set from the card, survive a device switch
    cl, cam_before, _ = cube_click(page, sel)
    try:
        page.locator(f"{sel} [data-show]").select_option("trail")
        page.locator(f"{sel} [data-decay]").fill("0.5")
        page.locator(f"{sel} [data-decay]").press("Enter")
        settle(page, 2)
        page.locator(f"{sel} [data-t3-series='twin'] [data-mode='frames-z']").click()
        settle(page, 3)
    except Exception as e:  # noqa: BLE001
        print(f"(the card's controls could not be driven: {e})")
    e1 = (view_entry(page, sel) or {}).get("trajectory3d") or {}
    rows1 = status_rows(page, "path-3d")
    check("persistence: the cube, the decay field and the twin's Z-only button wrote projection top, show trail, decay 0.5 and twin [line, frames-z] into the view entry",
          bool(cl) and e1.get("projection") == "top" and e1.get("show") == "trail" and e1.get("decay") == 0.5 and "frames-z" in ((e1.get("modes") or {}).get("twin") or []),
          {k: e1.get(k) for k in ("projection", "show", "decay", "modes")})
    pick_device(page, "J4 wrist 1")
    wait(page, "([sel, n]) => { const s = document.querySelector(sel + ' data-views .dv-status'); const m = s && /([\\d,]+) of/.exec(s.textContent); return !!m && Number(m[1].replace(/,/g, '')) !== n; }", [sel, rows1], timeout=10000)
    settle(page, 3)
    rows2 = status_rows(page, "path-3d")
    e2 = (view_entry(page, sel) or {}).get("trajectory3d") or {}
    cam2 = hook(page, sel, "camera")
    w2 = hook(page, sel, "window") or {}
    c2 = (hook(page, sel, "counts") or {}).get("twin") or {}
    check("persistence: a device switch on the rail (J3 elbow → J4 wrist 1: run r1 → r2, the card's rows change) leaves projection, decay and modes unchanged, in the entry and as drawn (orthographic along −Z, the window 0.5 s, twin's Z segments drawn)",
          rows1 is not None and rows2 is not None and rows1 != rows2 and all(e2.get(k) == e1.get(k) for k in ("projection", "show", "decay", "modes"))
          and cam2 and cam2["proj"][15] == 1 and angle_deg(forward(cam2), [0, 0, -1]) <= 0.1 and w2.get("decay") == 0.5 and (c2.get("frames-z") or 0) > 0,
          {"rows": [rows1, rows2], "entry": {k: e2.get(k) for k in ("projection", "show", "decay", "modes")}, "window": w2, "twin": c2})

    # ---- the resizable-panels rule: the card adds no side panel without a draggable boundary
    side = page.evaluate("""(sel) => { const view = document.querySelector(sel + ' .dv-view'); const stage = view && view.querySelector('.dv-scene3d'); if (!stage) return null;
      const s = stage.getBoundingClientRect(); const out = [];
      for (const c of view.children) { if (c.contains(stage) || !c.getClientRects().length) continue; const r = c.getBoundingClientRect();
        const beside = (r.right <= s.left + 1 || r.left >= s.right - 1) && Math.min(r.bottom, s.bottom) - Math.max(r.top, s.top) > 10;
        out.push({ cls: c.className, beside, splitter: !!c.querySelector('.dv-splitter') || !!(c.previousElementSibling && c.previousElementSibling.matches('.dv-splitter')) }); }
      return out; }""", sel)
    check("resizable panels: every block the card adds beside its 3D stage has a draggable boundary (none added: the controls run under the stage)",
          side is not None and all(not s["beside"] or s["splitter"] for s in side), side)
    shot(page, "p1b-arm-after-light-1280")
    check("arm: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- themes and widths
def looks(browser, base):
    for width, dark in ((1280, True), (390, False), (390, True)):
        tag = f"{width} px, {'dark' if dark else 'light'}"
        mobile = width < 500
        sel = "#v"
        page = open_page(browser, base, width=width, dark=dark, mobile=mobile)
        drew = mount_views(page, PATH_BASE, "Axes")
        shot(page, f"p1b-path-3d-{'dark' if dark else 'light'}-{width}", sel)
        ok, _cam, at = cube_click(page, sel, tap=mobile)
        cam = hook(page, sel, "camera")
        ang = angle_deg(forward(cam), [0, 0, -1]) if cam else None
        errs, worst, per = tick_errors(cam, ticks(page, sel)) if cam else ([{"no camera": True}], None, {})
        check(f"{tag}: the card draws; a {'tap' if mobile else 'click'} on the cube's +Z goes orthographic along −Z within 0.1°; every tick label within 1 px of its projection",
              drew and bool(ok) and cam["proj"][15] == 1 and ang <= 0.1 and not errs and per.get("x", 0) >= 2 and per.get("y", 0) >= 2,
              {"angle": ang, "tick errors": errs[:3], "ticks": per, "worst px": worst and round(worst, 3), "at": at})
        check(f"{tag}: the page never scrolls sideways", no_sideways(page, width), page.evaluate("() => document.scrollingElement.scrollWidth"))
        shot(page, f"p1b-path-top-{'dark' if dark else 'light'}-{width}", sel)
        check(f"{tag}: no page error", not page.errors, page.errors[:3])
        page.context.close()
    for width, dark in ((1280, True), (390, False), (390, True)):
        tag = f"arm dashboard, {width} px, {'dark' if dark else 'light'}"
        page = open_page(browser, base, width=width, dark=dark, mobile=width < 500)
        drew = mount_dash(page, ARM_BASE, ARM_KEYS)
        tk = tokens(page, panel("path-3d"))
        col = (hook(page, panel("path-3d"), "colors") or {}).get("series") or {}
        check(f"{tag}: both 3D cards draw, real wears slot 1 of this theme, and the page never scrolls sideways",
              drew and col.get("real") == tk["series"][0] and no_sideways(page, width), {"real": col.get("real"), "slot 1": tk["series"][0]})
        shot(page, f"p1b-arm-{'dark' if dark else 'light'}-{width}")
        check(f"{tag}: no page error", not page.errors, page.errors[:3])
        page.context.close()


# ------------------------------------------------------------------------------------------------- the old 3D cases
def old_cases(browser, site_base):
    """pid-tuning, trajectory-tracking (each case's own checks.py) and dashboard-cards' 3D lanes (checks_scene3d.py,
    checks_robot.py), run exactly as tests/browser/checks.py runs them, on the built site."""
    spec = importlib.util.spec_from_file_location("p1b_site_checks", ROOT / "tests" / "browser" / "checks.py")
    site = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(site)
    ctx = site.Ctx(browser, site_base)
    examples = ROOT / "gallery" / "examples"
    for case in ("pid-tuning", "trajectory-tracking"):
        before = len(site.checks)
        with guard(f"old case {case}"):
            site.run_case(ctx, examples / case)
        for c in site.checks[before:]:
            check(f"old case {case}: {c['name']}", c["ok"], c.get("value"), soft=c.get("soft", False))
    dc = examples / "dashboard-cards"
    hs = importlib.util.spec_from_file_location("p1b_dc_checks", dc / "checks.py")
    helpers = importlib.util.module_from_spec(hs)
    hs.loader.exec_module(helpers)
    for lane in ("checks_scene3d.py", "checks_robot.py"):
        before = len(site.checks)
        with guard(f"old case dashboard-cards {lane}"):
            ms = importlib.util.spec_from_file_location(f"p1b_dc_{lane[:-3]}", dc / lane)
            mod = importlib.util.module_from_spec(ms)
            ms.loader.exec_module(mod)
            mod.run(ctx, "gallery/dashboard-cards/index.html", helpers.HELPERS)
        for c in site.checks[before:]:
            check(f"old case dashboard-cards ({lane}): {c['name']}", c["ok"], c.get("value"), soft=c.get("soft", False))
    check("old cases: no script errors", not ctx.errors, ctx.errors[:3])
    check("old cases: nothing loaded from another site", not ctx.foreign, ctx.foreign[:3])


def serve(directory):
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(directory)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/", timeout=1)
            break
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.1)
    return proc, base


def main() -> int:
    check("fixture: the path has 564 samples at 100 Hz per situation; density 20 gives 22 markers (the PEP's example)",
          len(REAL) == 564 and abs(DT - 0.01) < 1e-9 and len(markers_at(564, 20)) == 22 and len(markers_at(564, 7)) == 9,
          {"samples": len(REAL), "dt": DT, "markers at 20": len(markers_at(564, 20))})
    procs = []
    try:
        root_proc, base = serve(ROOT)
        procs.append(root_proc)
        site_proc, site_base = serve(ROOT / "dist" / "site")
        procs.append(site_proc)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for name, fn in (("projection, scale and axes", projection), ("frames", frames), ("decay", decay), ("decay at scale", tick_cost),
                             ("display modes", modes), ("the arm dashboard", arm), ("themes and widths", looks)):
                with guard(name):
                    fn(browser, base)
            with guard("the old 3D cases"):
                old_cases(browser, site_base)
            browser.close()
    finally:
        for p in procs:
            p.terminate()
            p.wait(timeout=10)
    (OUT / "p1b-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    soft = [c["name"] for c in checks if c.get("soft")]
    print(f"{len(checks) - len(failed)}/{len(checks)} P1b checks pass")
    if soft:
        print(f"{len(soft)} speed budget(s) not enforced: the machine was overloaded (SOFT above)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
