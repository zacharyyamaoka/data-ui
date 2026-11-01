"""robot lane: the meshed robot in the 3D card (docs/peps/0005-dashboard-cards.md §2b `scene3d.robot`), measured.

Oracle: robot.json (each link's world position <link>_x/_y/_z and wxyz quaternion <link>_qw… per situation, every
0.04 s; pid-tuning/source/build_robot.py, MuJoCo FK) and its `robot.tool` (the tool site's offset in wrist_3_link,
from ur5e_bare.xml). Expected poses are interpolated here, in Python: positions linearly, orientations by slerp,
written out below without three. The page lends only what it drew: each link node's world matrix (decomposed by three)
through the card's hook, its camera, and the [data-marker] rings. The catalog's card and pid-tuning's both run."""

import bisect
import json
import math
import pathlib

HERE = pathlib.Path(__file__).parent
CATALOG = ("gallery/dashboard-cards/index.html", "tool-path-3d-paths", HERE / "robot.json")
PID = ("gallery/pid-tuning/index.html", "tool-path-3d-sim-fk", HERE.parent / "pid-tuning" / "robot.json")
SEEKS = (1.234, 3.71, 6.013)   # off the 0.04 s grid, so the card must interpolate
GLB = "ur5e_links.glb"

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

HOOK = "(k) => { const r = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`); return r && r.scene3d; }"


def open_page(ctx, path, width=1440, height=900, dark=False, mobile=False, glb=None):
    """A page with every WebGL context counted and every GLB request listed; `glb` (a route handler) stands in for the
    model's server (a delay, a 404)."""
    context = ctx.browser.new_context(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light",
                                      device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    context.add_init_script(COUNT_WEBGL)
    page = context.new_page()
    page.glb_requests = []
    page.on("request", lambda r: page.glb_requests.append(r.url) if r.url.endswith(GLB) else None)
    if glb:
        page.route(f"**/{GLB}", glb)
    else:
        page.on("pageerror", lambda e: ctx.errors.append(f"{path}: {e}"))
        page.on("console", lambda m: ctx.errors.append(f"{path}: console {m.text}") if m.type == "error" else None)
    page.goto(f"{ctx.base}/{path}")
    return page


def hook(page, key, call):
    # a card without the hook's call (before this lane) reads as null, so the check reports FAIL instead of crashing
    return page.evaluate(f"(k) => {{ const h = ({HOOK})(k); try {{ return h ? h.{call} : null; }} catch (e) {{ return null; }} }}", key)


def robot_ready(ctx, page, key, timeout=20000):
    """Scroll the card in and wait until its meshes are posed and drawn (state ready and a frame since)."""
    page.locator(f"#example .dd-panel[data-panel='{key}']").scroll_into_view_if_needed()
    return ctx.until(page, f"(k) => {{ const h = ({HOOK})(k); const r = h && h.robot && h.robot(); return !!r && r.state === 'ready' && r.drawn; }}", key, timeout=timeout)


def series_rows(rows):
    by = {}
    for r in rows:
        by.setdefault(r["situation"], []).append(r)
    for s in by.values():
        s.sort(key=lambda r: r["t"])
    return by


def around(rows, t):
    ts = [r["t"] for r in rows]
    if t <= ts[0]:
        return rows[0], rows[0], 0.0
    if t >= ts[-1]:
        return rows[-1], rows[-1], 0.0
    i = bisect.bisect_right(ts, t)
    a, b = rows[i - 1], rows[i]
    return a, b, (t - a["t"]) / (b["t"] - a["t"])


def slerp(qa, qb, f):
    """Spherical linear interpolation of two wxyz quaternions (each normalised first), the short way round."""
    na, nb = math.sqrt(sum(c * c for c in qa)), math.sqrt(sum(c * c for c in qb))
    qa, qb = [c / na for c in qa], [c / nb for c in qb]
    d = sum(x * y for x, y in zip(qa, qb))
    if d < 0:
        qb, d = [-c for c in qb], -d
    if d > 1 - 1e-12:
        return qa
    theta = math.acos(min(1.0, d))
    s = math.sin(theta)
    wa, wb = math.sin((1 - f) * theta) / s, math.sin(f * theta) / s
    return [wa * x + wb * y for x, y in zip(qa, qb)]


def pose(rows, link, t):
    a, b, f = around(rows, t)
    p = [a[f"{link}_{c}"] + (b[f"{link}_{c}"] - a[f"{link}_{c}"]) * f for c in "xyz"]
    q = slerp([a[f"{link}_q{c}"] for c in "wxyz"], [b[f"{link}_q{c}"] for c in "wxyz"], f)
    return p, q


def rotate(q, v):
    w, x, y, z = q
    m = [[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
         [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
         [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]]
    return [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]


def project(cam, p):
    def mul(m, v):
        return [sum(m[col * 4 + row] * v[col] for col in range(4)) for row in range(4)]
    clip = mul(cam["proj"], mul(cam["view"], [p[0], p[1], p[2], 1.0]))
    x, y = clip[0] / clip[3], clip[1] / clip[3]
    return ((x + 1) / 2 * cam["width"], (1 - y) / 2 * cam["height"])


def markers(page, key):
    return page.evaluate("""(k) => {
      const root = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`);
      if (!root) return null;
      const c = root.querySelector('canvas').getBoundingClientRect();
      return Object.fromEntries([...root.querySelectorAll('[data-marker]')].filter((m) => !m.hidden).map((m) => {
        const r = m.getBoundingClientRect();
        return [m.dataset.series, [r.left + r.width / 2 - c.left, r.top + r.height / 2 - c.top]];
      })); }""", key)


def stats(page):
    return page.evaluate("() => globalThis.__dataUiGL ? globalThis.__dataUiGL.stats() : null")


def poses_match(ctx, page, key, doc, seek, label):
    """At each seek, every link node of every series' robot (the ghost too) against the oracle's pose at t; then the tool
    site (wrist_3_link's pose times the site's offset) against the series' path marker on screen."""
    check = ctx.check
    by = series_rows(doc["rows"])
    links, tool = doc["robot"]["links"], doc["robot"]["tool"]
    bad, worst_p, worst_q, n = [], 0.0, 0.0, 0
    offs, worst_px = [], 0.0
    for t in SEEKS:
        seek(page, t)
        got = hook(page, key, "robot()") or {}
        nodes = got.get("links") or {}
        cam = hook(page, key, "camera()")
        dots = markers(page, key) or {}
        for s, rows in by.items():
            for link in links:
                want_p, want_q = pose(rows, link, t)
                node = (nodes.get(s) or {}).get(link)
                if not node:
                    bad.append({"t": t, "series": s, "link": link, "node": None})
                    continue
                dp = max(abs(a - b) for a, b in zip(node["p"], want_p))
                dq = min(max(abs(a - b) for a, b in zip(node["q"], want_q)), max(abs(a + b) for a, b in zip(node["q"], want_q)))
                worst_p, worst_q, n = max(worst_p, dp), max(worst_q, dq), n + 1
                if dp > 1e-6 or dq > 1e-6:
                    bad.append({"t": t, "series": s, "link": link, "dp": dp, "dq": dq})
            node = (nodes.get(s) or {}).get(tool["link"])
            if node and cam and s in dots:
                site = [a + b for a, b in zip(node["p"], rotate(node["q"], tool["pos"]))]
                px = project(cam, site)
                gap = math.dist(px, dots[s])
                worst_px = max(worst_px, gap)
                if gap > 1.0:
                    offs.append({"t": t, "series": s, "site px": px, "marker px": dots[s], "gap": round(gap, 3)})
            else:
                offs.append({"t": t, "series": s, "node": bool(node), "marker": dots.get(s)})
    want = len(SEEKS) * len(by) * len(links)
    check(f"robot{label}: after seek({', '.join(map(str, SEEKS))}) every link node of every series' robot ({len(by)} series × {len(links)} links, the ghost too) has robot.json's pose at t: position lerped within 1e-6 m and orientation slerped within 1e-6 (exact at the rows; between rows ≤ 1.34 mm from true FK, max 1.335 mm over 104,804 link samples: pid-tuning/source/measure_robot_interp.py)",
          not bad and n == want, bad[:4] or {"nodes": n, "worst m": worst_p, "worst quat": worst_q})
    check(f"robot{label}: the tool site (wrist_3_link's drawn pose × robot.json's site offset {tool['pos']}) lands on its series' path marker within 1 px at every seek",
          not offs, offs[:4] or {"worst px": round(worst_px, 3)})


def run(ctx, path, h):
    check, seek, ready = ctx.check, h["seek"], h["ready"]
    catalog = json.loads(CATALOG[2].read_text(encoding="utf-8"))
    pid = json.loads(PID[2].read_text(encoding="utf-8"))
    key = CATALOG[1]

    # ---- cold load: first frame with the meshes, one context, poses
    page = open_page(ctx, path)
    ready(page)
    # the catalog's other 3D card (the stick robot) live first, so the page holds two 3D scenes on its one context
    page.locator("#example .dd-panel[data-panel='tool-path-3d']").scroll_into_view_if_needed()
    other = ctx.until(page, f"(k) => {{ const h = ({HOOK})(k); return !!h && h.renders() > 0; }}", "tool-path-3d")
    t0 = page.evaluate("() => performance.now()")
    ok = robot_ready(ctx, page, key)
    info = hook(page, key, "robot()") or {}
    check("robot: the catalog's 3D card loads the GLB and draws its meshes (state ready, a frame drawn with them)", ok,
          {k: info.get(k) for k in ("state", "url", "error", "series", "readyMs")})
    if info.get("readyMs") is not None:
        ctx.budget("robot: first frame with the meshes, cold GLB (ms from scrolling the card in)", info["readyMs"] - t0, 5000)
    seek(page, 2.0)
    tris = (hook(page, key, "robot()") or {}).get("triangles")
    glb_tris = 121783
    robots = len(series_rows(catalog["rows"]))
    check(f"robot: the frame draws every robot's meshes ({robots} robots, the ghost included, × {glb_tris:,} GLB triangles)",
          tris is not None and tris >= robots * glb_tris, {"triangles in the last frame": tris})
    joints = hook(page, key, "joints()") or {}
    check("robot: with the meshes up the stick robot is gone (no stick joints drawn)", ok and not any(joints.values()), joints)
    st = stats(page)
    got = page.evaluate("() => window.__webglContexts")
    check("robot: ONE WebGL context on the page with the robot on (both 3D cards live, getContext counted before load)",
          other and got == 1 and st and st["contexts"] == 1 and st["scenes"] == 2, {"other card drawn": other, "webglContexts": got, "stats": st})
    poses_match(ctx, page, key, catalog, seek, "")

    # ---- render on demand with the robot on
    seek(page, 2.5)
    ctx.frames(page)
    r0 = stats(page)
    page.wait_for_timeout(1000)
    r1 = stats(page)
    seek(page, 2.9)
    r2 = stats(page)
    check("robot: render on demand holds with the meshes (no render over 1 s idle; a seek renders again)",
          r0 and r1 and r2 and r1["renders"] == r0["renders"] and r2["renders"] > r1["renders"],
          {"idle": [r0 and r0["renders"], r1 and r1["renders"]], "after seek": r2 and r2["renders"]})

    # ---- one fetch with two robot cards: a second panel of the same view, drawn by the dashboard itself
    page.evaluate("""() => { const d = document.querySelector('#example'); const b = d._fileBase;
      const panels = [...b.layout.panels, { view: 'Tool path 3D (paths)', w: 6, h: 4, key: 'robot-twin' }];
      d.load({ ...b, layout: { ...b.layout, panels } }, d.datasets, { keepState: true }); }""")
    ready(page)
    twin = [robot_ready(ctx, page, k) for k in (key, "robot-twin")]
    st = stats(page)
    got = page.evaluate("() => window.__webglContexts")
    check("robot: the GLB is fetched once with two robot cards on the page (a second panel added and every panel redrawn), still on one WebGL context",
          all(twin) and len(page.glb_requests) == 1 and got == 1 and st and st["contexts"] == 1 and st["scenes"] >= 2,
          {"ready": twin, "GLB requests": page.glb_requests, "stats": st})
    seek(page, SEEKS[1])
    ctx.shot(Card(page.locator(f"#example .dd-panel[data-panel='{key}']")), "robot-light-1440")
    page.context.close()

    # ---- dark
    page = open_page(ctx, path, dark=True)
    ready(page)
    ok = robot_ready(ctx, page, key)
    seek(page, SEEKS[1])
    ctx.frames(page)
    ctx.shot(Card(page.locator(f"#example .dd-panel[data-panel='{key}']")), "robot-dark-1440")
    check("robot, dark: the meshes draw in the dark theme", ok, (hook(page, key, "robot()") or {}).get("state"))
    page.context.close()

    # ---- 390 px
    page = open_page(ctx, path, width=390, height=844, mobile=True)
    ready(page)
    ok = robot_ready(ctx, page, key)
    seek(page, SEEKS[1])
    ctx.frames(page)
    got = page.evaluate(f"""(k) => {{ const r = document.querySelector(`#example .dd-panel[data-panel='${{k}}'] .dv-scene3d`);
      const c = r && r.querySelector('canvas').getBoundingClientRect();
      return {{ sw: document.scrollingElement.scrollWidth, left: c && c.left, right: c && c.right, height: c && c.height }}; }}""", key)
    ctx.shot(Card(page.locator(f"#example .dd-panel[data-panel='{key}']")), "robot-light-390")
    page.context.close()
    check("robot, 390 px: the robot card draws its meshes inside the viewport and the page never scrolls sideways",
          ok and got["sw"] <= 390 and got["left"] is not None and got["left"] >= 0 and got["right"] <= 390 and got["height"] > 200, got)

    # ---- the stick while the GLB loads, and for good when it fails
    held = []
    page = open_page(ctx, path, glb=lambda route: held.append(route))
    ready(page)
    page.locator(f"#example .dd-panel[data-panel='{key}']").scroll_into_view_if_needed()
    asked = ctx.until(page, f"(k) => {{ const h = ({HOOK})(k); return !!h && h.renders() > 0; }}", key)
    seek(page, SEEKS[0])
    loading = hook(page, key, "robot()") or {}
    sticks = hook(page, key, "joints()") or {}
    check("robot: while the GLB is still on its way the card draws the stick robot (8 joints per series) and says loading",
          asked and loading.get("state") == "loading" and sticks and all(len(v) == 8 for v in sticks.values()),
          {"state": loading.get("state"), "joints": {k: len(v) for k, v in sticks.items()}, "held": len(held)})
    for route in held:
        route.abort()
    page.context.close()
    page = open_page(ctx, path, glb=lambda route: route.fulfill(status=404, body="not here"))
    ready(page)
    page.locator(f"#example .dd-panel[data-panel='{key}']").scroll_into_view_if_needed()
    failed = ctx.until(page, f"(k) => {{ const h = ({HOOK})(k); const r = h && h.robot && h.robot(); return !!r && r.state === 'failed'; }}", key)
    seek(page, SEEKS[0])
    sticks = hook(page, key, "joints()") or {}
    note = page.evaluate("(k) => { const e = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d-note`); return e && !e.hidden ? e.textContent : null; }", key)
    check("robot: when the GLB fails (404) the card keeps the stick robot (8 joints per series) and says why in its foot",
          failed and sticks and all(len(v) == 8 for v in sticks.values()) and bool(note), {"joints": {k: len(v) for k, v in sticks.items()}, "note": note})
    page.context.close()

    # ---- pid-tuning's card: the same measure on its four situations
    page = open_page(ctx, PID[0])
    ready(page)
    ok = robot_ready(ctx, page, PID[1])
    check("robot, pid-tuning: its Tool path 3D card draws the meshed robot", ok, (hook(page, PID[1], "robot()") or {}).get("state"))
    poses_match(ctx, page, PID[1], pid, seek, ", pid-tuning")
    seek(page, SEEKS[1])
    ctx.shot(Card(page.locator(f"#example .dd-panel[data-panel='{PID[1]}']")), "robot-pid-light-1440")
    page.context.close()


class Card:
    """ctx.shot(page, name) calls page.screenshot(path=, full_page=); this hands it one card's panel instead."""

    def __init__(self, locator):
        self.locator = locator

    def screenshot(self, path, full_page=False):
        self.locator.screenshot(path=path)
