"""scene3d lane: the 3D card (docs/peps/0005-dashboard-cards.md §2b `type: scene3d`), measured.

Oracle: tool.json (the tool path px/py/pz and the stick robot s<k>x/y/z per situation, every 0.02 s). Expected 3D
points are interpolated here, in Python, at the clock's t; the page only lends its camera (view and projection
matrices from the card's hook), and the projection is done here too. Every WebGL context the page makes is counted
by an init script that wraps HTMLCanvasElement.prototype.getContext before the page loads."""

import bisect
import re

KEYS = ("tool-path-3d", "tool-path-3d-paths")   # the two scene3d panels (slugs of their view names)
SEEKS = (1.234, 3.71, 6.013)                     # off the 0.02 s grid, so the card must interpolate
JOINTS = 8

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

ROOT = "(k) => document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`)"
HOOK = "(k) => { const r = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`); return r && r.scene3d; }"


def open_page(ctx, path, width=1440, height=900, dark=False, mobile=False):
    context = ctx.browser.new_context(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light",
                                      device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    context.add_init_script(COUNT_WEBGL)
    page = context.new_page()
    page.on("pageerror", lambda e: ctx.errors.append(f"{path}: {e}"))
    page.on("console", lambda m: ctx.errors.append(f"{path}: console {m.text}") if m.type == "error" else None)
    page.goto(f"{ctx.base}/{path}")
    return page


def series_rows(rows):
    by = {}
    for r in rows:
        by.setdefault(r["situation"], []).append(r)
    for s in by.values():
        s.sort(key=lambda r: r["t"])
    return by


def interp(rows, t, cols):
    """Linear interpolation of cols at t over rows sorted by t (clamped at the ends): the oracle."""
    ts = [r["t"] for r in rows]
    if t <= ts[0]:
        return [rows[0][c] for c in cols]
    if t >= ts[-1]:
        return [rows[-1][c] for c in cols]
    i = bisect.bisect_right(ts, t)
    a, b = rows[i - 1], rows[i]
    f = (t - a["t"]) / (b["t"] - a["t"])
    return [a[c] + (b[c] - a[c]) * f for c in cols]


def project(cam, p):
    """CSS px relative to the canvas of world point p, through the card's camera (column-major 4x4 matrices)."""
    def mul(m, v):
        return [sum(m[col * 4 + row] * v[col] for col in range(4)) for row in range(4)]
    clip = mul(cam["proj"], mul(cam["view"], [p[0], p[1], p[2], 1.0]))
    x, y = clip[0] / clip[3], clip[1] / clip[3]
    return ((x + 1) / 2 * cam["width"], (1 - y) / 2 * cam["height"])


def markers(page, key):
    """Each [data-marker]'s centre in CSS px relative to the card's canvas, by series."""
    return page.evaluate("""(k) => {
      const root = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`);
      if (!root) return null;
      const c = root.querySelector('canvas').getBoundingClientRect();
      return Object.fromEntries([...root.querySelectorAll('[data-marker]')].filter((m) => !m.hidden).map((m) => {
        const r = m.getBoundingClientRect();
        return [m.dataset.series, [r.left + r.width / 2 - c.left, r.top + r.height / 2 - c.top]];
      })); }""", key)


def camera(page, key):
    return page.evaluate(f"(k) => {{ const h = ({HOOK})(k); return h ? h.camera() : null; }}", key)


def stats(page):
    return page.evaluate("() => globalThis.__dataUiGL ? globalThis.__dataUiGL.stats() : null")


def live(ctx, page, key):
    """Scroll the card into view and wait for its first frame (WebGL starts only near the viewport)."""
    page.locator(f"#example .dd-panel[data-panel='{key}']").scroll_into_view_if_needed()
    return ctx.until(page, f"(k) => {{ const h = ({HOOK})(k); return !!h && h.renders() > 0; }}", key, timeout=15000)


def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def palette(here):
    m = re.search(r"palette:\s*\{([^}]*)\}", (here / "views.base").read_text(encoding="utf-8"))
    return {k: v for k, v in re.findall(r'(\w+):\s*"(#[0-9a-fA-F]{6})"', m.group(1))} if m else {}


def run(ctx, path, h):
    check, seek, ready, D = ctx.check, h["seek"], h["ready"], h["D"]
    from pathlib import Path
    here = Path(__file__).parent
    by = series_rows(h["rows"]("tool.json"))
    situations = sorted(by)
    pal = palette(here)

    page = open_page(ctx, path)
    ready(page)

    # ---- one WebGL context for both 3D cards
    started = [live(ctx, page, k) for k in KEYS]
    ctx.frames(page)
    got = page.evaluate("() => window.__webglContexts")
    st = stats(page)
    check("scene3d: both 3D cards draw (each has rendered a frame once near the viewport)", all(started), {"started": started, "stats": st})
    check("scene3d: exactly ONE WebGL context on the page with two scene3d cards drawn (getContext counted before load)",
          got == 1 and st and st["contexts"] == 1 and st["scenes"] == 2, {"webglContexts": got, "stats": st})
    ink = page.evaluate("""(k) => { const r = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d canvas`);
      if (!r || !r.width) return null; const d = r.getContext('2d').getImageData(0, 0, r.width, r.height).data; let n = 0;
      for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++; return { inked: n / (r.width * r.height), corner: d[3] }; }""", KEYS[0])
    check("scene3d: the shared frame is copied into the card's own canvas (>1% of it inked) on a transparent background (corner alpha 0)",
          bool(ink) and ink["inked"] > 0.01 and ink["corner"] == 0, ink)

    # ---- the marker per series at the clock's t, against the oracle's interpolated point
    page.locator(f"{D} .dd-panel[data-panel='{KEYS[0]}']").scroll_into_view_if_needed()
    bad, moved, prev, worst = [], [], None, 0.0
    for t in SEEKS:
        seek(page, t)
        cam = camera(page, KEYS[0])
        got = markers(page, KEYS[0]) or {}
        world = page.evaluate(f"(k) => {{ const h = ({HOOK})(k); return h ? h.markers() : null; }}", KEYS[0]) or {}
        for s in situations:
            p3 = interp(by[s], t, ["px", "py", "pz"])
            want = project(cam, p3) if cam else None
            # WHY the world check too: at this card's size a step-hold (the sample before t) lands within 0.74 px of
            # the interpolated point (mutation-tested), so the pixel tolerance alone cannot tell them apart
            off = max(abs(a - b) for a, b in zip(world[s], p3)) if s in world else None
            if s not in got or not want or dist(got[s], want) > 1.5 or off is None or off > 1e-6:
                bad.append({"t": t, "series": s, "marker": got.get(s), "oracle": want, "world offset m": off})
            else:
                worst = max(worst, dist(got[s], want))
        if prev:
            moved.append(all(s in got and s in prev and dist(got[s], prev[s]) > 2 for s in situations))
        prev = got
    check(f"scene3d: after seek({', '.join(map(str, SEEKS))}) each series' marker is at the oracle's interpolated (px, py, pz) (within 1 µm) and its [data-marker] on that point through the card's camera, within 1.5 px",
          not bad and len(situations) == 3, bad[:4] or {"series": situations, "worst px": round(worst, 3)})
    check("scene3d: the markers move between seeks (every series, > 2 px each time)", moved and all(moved), moved)

    # ---- the stick robot at t
    t = SEEKS[1]
    seek(page, t)
    cam = camera(page, KEYS[0])
    joints = page.evaluate(f"(k) => {{ const h = ({HOOK})(k); return h ? h.joints() : null; }}", KEYS[0]) or {}
    got = markers(page, KEYS[0]) or {}
    cols = [f"s{k}{a}" for k in range(JOINTS) for a in "xyz"]
    out, seen = [], {}
    for s in ("factory", "tuned"):
        pts = joints.get(s) or []
        want = interp(by[s], t, cols)
        off = max((abs(pts[k][i] - want[k * 3 + i]) for k in range(min(len(pts), JOINTS)) for i in range(3)), default=None)
        tool = project(cam, pts[-1]) if pts and cam else None
        gap = dist(tool, got[s]) if tool and s in got else None
        seen[s] = {"joints": len(pts), "max offset m": off, "tool vs marker px": gap and round(gap, 3)}
        if len(pts) != JOINTS or off is None or off > 1e-6 or gap is None or gap > 1.0:
            out.append({"series": s, **seen[s]})
    check(f"scene3d: the stick robot draws {JOINTS} joint points for factory and tuned at t={t} (each on the oracle's interpolated s<k>), and its tool point is on the path marker within 1 px",
          not out and len(joints.get("target") or []) == JOINTS, out or {**seen, "target ghost joints": len(joints.get("target") or [])})

    # ---- orbit and reset
    before = markers(page, KEYS[0]) or {}
    canvas = page.locator(f"{D} .dd-panel[data-panel='{KEYS[0]}'] .dv-scene3d canvas")
    after, reset = {}, {}
    if canvas.count():
        box = canvas.bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(cx, cy)
        page.mouse.down()
        for k in range(1, 11):
            page.mouse.move(cx + 9 * k, cy + 3 * k)
        page.mouse.up()
        ctx.frames(page)
        after = markers(page, KEYS[0]) or {}
        page.mouse.dblclick(cx + 90, cy + 30)
        ctx.frames(page)
        reset = markers(page, KEYS[0]) or {}
    orbit = {s: round(dist(before[s], after[s]), 2) for s in situations if s in before and s in after}
    back = {s: round(dist(before[s], reset[s]), 3) for s in situations if s in before and s in reset}
    check("scene3d: an orbit drag moves the camera (every projected marker moves > 5 px)", len(orbit) == 3 and min(orbit.values()) > 5, orbit)
    check("scene3d: a double-click restores the fitted camera (every marker back within 0.5 px)", len(back) == 3 and max(back.values()) < 0.5, back)

    # ---- render on demand only
    r0 = stats(page)
    page.wait_for_timeout(1000)
    r1 = stats(page)
    seek(page, 2.5)
    r2 = stats(page)
    check("scene3d: no render loop (the renders count is unchanged over 1 s idle) and a seek renders once more",
          r0 and r1 and r2 and r1["renders"] == r0["renders"] and r2["renders"] > r1["renders"],
          {"idle": [r0 and r0["renders"], r1 and r1["renders"]], "after seek": r2 and r2["renders"]})

    # ---- theme: palette colours on the paths, grid from the tokens in both themes
    light = page.evaluate(f"(k) => {{ const h = ({HOOK})(k); return h ? h.colors() : null; }}", KEYS[0])
    ctx.shot(Card(page.locator(f"{D} .dd-panel[data-panel='{KEYS[0]}']")), "scene3d-light-1440")
    ctx.shot(Card(page.locator(f"{D} .dd-panel[data-panel='{KEYS[1]}']")), "scene3d-paths-light-1440")
    page.context.close()

    page = open_page(ctx, path, dark=True)
    ready(page)
    for k in KEYS:
        live(ctx, page, k)
    seek(page, SEEKS[1])
    ctx.frames(page)
    dark = page.evaluate(f"(k) => {{ const h = ({HOOK})(k); return h ? h.colors() : null; }}", KEYS[0])
    ctx.shot(Card(page.locator(f"{D} .dd-panel[data-panel='{KEYS[0]}']")), "scene3d-dark-1440")
    ctx.shot(Card(page.locator(f"{D} .dd-panel[data-panel='{KEYS[1]}']")), "scene3d-paths-dark-1440")
    page.context.close()
    want = {s: pal[s].lower() for s in ("factory", "tuned", "target") if s in pal}
    check("scene3d: each path wears the dashboard palette's colour (style.palette), light and dark; the grid follows the theme's tokens",
          bool(light) and bool(dark) and all(light["series"].get(s) == c and dark["series"].get(s) == c for s, c in want.items())
          and light["grid"] != dark["grid"],
          {"light": light, "dark": dark, "palette": want})

    # ---- 390 px: the card fits, no sideways scroll
    page = open_page(ctx, path, width=390, height=844, mobile=True)
    ready(page)
    ok = live(ctx, page, KEYS[0])
    got = page.evaluate(f"""(k) => {{ const r = ({ROOT})(k); const c = r && r.querySelector('canvas').getBoundingClientRect();
      return {{ sw: document.scrollingElement.scrollWidth, left: c && c.left, right: c && c.right, height: c && c.height }}; }}""", KEYS[0])
    ctx.shot(Card(page.locator(f"{D} .dd-panel[data-panel='{KEYS[0]}']")), "scene3d-light-390")
    page.context.close()
    check("scene3d, 390 px: the 3D card draws inside the viewport (canvas within 0..390, > 200 px tall) and the page never scrolls sideways",
          ok and got["sw"] <= 390 and got["left"] is not None and got["left"] >= 0 and got["right"] <= 390 and got["height"] > 200, got)


class Card:
    """ctx.shot(page, name) calls page.screenshot(path=, full_page=); this hands it one card's panel instead."""

    def __init__(self, locator):
        self.locator = locator

    def screenshot(self, path, full_page=False):
        self.locator.screenshot(path=path)
