"""data-ui's scenario bench: real data from Zach's apps, loaded and driven in headless Chromium, timed by the browser.

    npm run bench                                   # every scenario (builds dist/ first; bench/run.mjs)
    npm run bench -- --scenario robotparts-actuators,large-table@10000 --runs 3
    <python with playwright> bench/runner.py --help

What it measures and why is bench/KPIS.md. In short, for each scenario it loads the page N times cold (a new browser
context: empty HTTP cache, new renderer) and N times warm (the same context, reloaded), then drives the real
interactions on the warm page (tick a rail value, click a column to sort, switch presets, type a search, open the
peek, scroll). Every number comes from the browser: PerformanceObserver (paint, LCP, long tasks, event timing),
data-ui's User Timing marks (packages/core/src/perf.js), resource timing and CDP's heap metric.

Noise: the machine is shared with other agents. Each scenario records two separate verdicts (bench/trust.py):
  trust      machine interference, measured independently of the app: a fixed-work calibration in the same browser
             before and after, and /proc/stat per CPU before, during and after, less the bench's own process tree;
             "noisy" when the calibration is more than 1.3x this host's best, other work took over half the CPUs the
             bench is pinned to, or their SMT siblings were over half busy. Only this routes a point away from the KPI
             series, and only a time (bench/publish.py). The load average is recorded, as context. Through the
             scenario a sampler records that pressure every 200 ms, and each sample (load, interaction, scroll frame)
             is judged by the windows over its own time: unclean ones are left out of the timing KPIs, and a set with
             too few clean ones is suppressed (judge r2, finding 4).
  stability  the spread of the app's own cold first paints (cv over 0.5 is "unstable"): a result about the app, never
             noise. Its points are published as measured, with the stable_samples gate failing beside them.

WebGL: a map scenario (MapLibre) runs in a second browser on the GPU (ANGLE on Vulkan, GPU_ARGS) when that browser
really gets a hardware renderer, checked by its WebGL renderer string; otherwise it runs on headless Chromium's
SwiftShader. Either way each scenario records `renderer` {kind: gpu|software|none, string, args, webgl}, and publish.py
labels a WebGL scenario's points with it, so a software number is never read as a GPU one. `--webgl software` forces it.

Writes OUT/results-<stamp>.json and OUT/latest.json (default bench/.out/, not in git). Publishing to Vibe Tracks is a
separate step: bench/publish.py. Every server and browser it starts is stopped before it exits.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import gzip
import http.server
import json
import math
import os
import pathlib
import platform
import re
import shutil
import socket
import statistics
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse

from playwright.sync_api import sync_playwright

BENCH = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))
import trust as trustlib  # noqa: E402  (bench/trust.py: the machine and stability verdicts, shared with publish.py)

ROOT = BENCH.parent
SCENARIOS = BENCH / "scenarios"
GEN = BENCH / ".data"
HARNESS = (BENCH / "harness.js").read_text()
STATE = pathlib.Path(os.environ.get("DATA_UI_BENCH_HOME", pathlib.Path.home() / ".local/share/data-ui-bench"))
VIEWPORT = {"width": 1440, "height": 900}
BROWSER_ARGS = ["--no-first-run", "--disable-extensions", "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows"]
# WHY a GPU browser for WebGL scenarios only: headless Chromium's default WebGL is SwiftShader, a CPU rasteriser
# ("ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) ...), SwiftShader driver)", measured 2026-10-26), so a
# map number from it is a CPU number, not what a reader's GPU does. ANGLE on Vulkan reaches this box's RTX 4080 SUPER
# headless. Only the map scenarios get it: the DOM views never touch WebGL, and their series stay comparable.
GPU_ARGS = ["--use-angle=vulkan", "--enable-features=Vulkan", "--enable-gpu", "--ignore-gpu-blocklist"]
SOFTWARE_RENDERERS = ("swiftshader", "llvmpipe", "softpipe", "software", "microsoft basic render")
RENDERER_JS = """() => {
  const gl = document.createElement('canvas').getContext('webgl2') || document.createElement('canvas').getContext('webgl');
  if (!gl) return null;
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  return String(gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER));
}"""


# ------------------------------------------------------------------ statistics
def pct(values, p):
    """Nearest-rank percentile (no interpolation): with n samples, p95 is the ceil(0.95 n)-th smallest."""
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    k = max(1, math.ceil(p / 100 * len(v)))
    return v[k - 1]


def summary(values):
    v = [x for x in values if x is not None]
    if not v:
        return {"n": 0, "p50": None, "p95": None, "min": None, "max": None, "mean": None, "stdev": None, "cv": None}
    mean = statistics.fmean(v)
    sd = statistics.stdev(v) if len(v) > 1 else 0.0
    r = lambda x: None if x is None else round(x, 2)
    return {"n": len(v), "p50": r(pct(v, 50)), "p95": r(pct(v, 95)), "min": r(min(v)), "max": r(max(v)), "mean": r(mean),
            "stdev": r(sd), "cv": round(sd / mean, 3) if mean else None}


# ------------------------------------------------------------------ scenarios
def load_scenarios(wanted: list[str] | None):
    targets = []
    for f in sorted(SCENARIOS.glob("*/scenario.json")):
        s = json.loads(f.read_text())
        s["dir"] = f.parent
        variants = s.get("rows_variants") or [None]
        for n in variants:
            t = dict(s)
            t["target"] = s["id"] if n is None else f"{s['id']}@{n}"
            if n is not None:
                t["rows"] = n
            t["variant"] = n
            targets.append(t)
    if wanted:
        keep = []
        for w in wanted:
            hit = [t for t in targets if t["target"] == w or t["id"] == w]
            if not hit:
                sys.exit(f"no scenario {w!r}; have: {', '.join(t['target'] for t in targets)}")
            keep += [t for t in hit if t not in keep]
        targets = keep
    return targets


def prepare(t):
    """A synthetic variant's data is generated (seeded) into bench/.data/<id>/<n>/ beside a copy of its views.base."""
    if t["variant"] is None:
        t["src"] = f"/scenarios/{t['id']}/{t.get('base', 'views.base')}"
        need = t.get("rebuild_if_missing")
        if need and not (t["dir"] / need["path"]).exists():
            # media kept out of git (Zach's source-only rule): rebuilt from its source, and the data's sha256 is
            # re-checked below, so a source that moved on is reported rather than silently benchmarked
            print(f"  {t['id']}: {need['path']}/ is missing; running {need['run']}", flush=True)
            subprocess.run([sys.executable, str(t["dir"] / need["run"])], check=False)
        prov = t.get("provenance") or {}
        data = next((t["dir"] / line.split(":", 1)[1].strip() for line in (t["dir"] / t.get("base", "views.base")).read_text().splitlines() if line.startswith("data:")), None)
        if prov.get("sha256") and data and data.exists():
            import hashlib
            got = hashlib.sha256(data.read_bytes()).hexdigest()
            t["data_sha_ok"] = got == prov["sha256"]
            if not t["data_sha_ok"]:
                print(f"  WARNING {t['id']}: {data.name} sha256 {got[:12]} differs from the provenance's {prov['sha256'][:12]}", flush=True)
        return
    out = GEN / t["id"] / str(t["variant"])
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(t["dir"] / t.get("base", "views.base"), out / "views.base")
    stamp = out / ".rows"
    if not (stamp.exists() and stamp.read_text().strip() == str(t["variant"]) and any(out.glob("*.json"))):
        subprocess.run([sys.executable, str(t["dir"] / t["generate"]), "--rows", str(t["variant"]), "--out", str(out)], check=True)
        (out / ".rows").write_text(str(t["variant"]))
    t["src"] = f"/gen/{t['id']}/{t['variant']}/views.base"


def uses_webgl(t) -> bool:
    """A scenario whose .base has a map view draws with WebGL (MapLibre); every other view is DOM, SVG or 2D canvas."""
    base = (t["dir"] / t.get("base", "views.base")).read_text()
    return any(re.match(r"\s*-?\s*type:\s*map\s*$", line) for line in base.splitlines())


def webgl_renderer(browser) -> str | None:
    """The WebGL renderer string this browser hands a page (WEBGL_debug_renderer_info's UNMASKED_RENDERER_WEBGL)."""
    ctx = browser.new_context()
    try:
        page = ctx.new_page()
        page.set_content("<!doctype html><title>renderer</title>")
        return page.evaluate(RENDERER_JS)
    finally:
        ctx.close()


def renderer_kind(renderer: str | None) -> str:
    if not renderer:
        return "none"
    return "software" if any(k in renderer.lower() for k in SOFTWARE_RENDERERS) else "gpu"


def page_html(t):
    base = (t["dir"] / t.get("base", "views.base")).read_text()
    rail = any(line.startswith("facets:") for line in base.splitlines())
    view = f' view="{t["view"]}"' if t.get("view") else ""
    # WHY a bare host page, not the gallery's: the gallery page carries the site's chrome and the files panel; this is
    # what a host app ships (robotparts' part page): the kit's css and js, a rail when the .base has facets, the views
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>bench · {t['target']}</title>
<link rel="stylesheet" href="/dist/data-ui.css">
<script type="module" src="/dist/data-ui.js"></script>
<style>html,body{{margin:0;height:100%;font-family:system-ui,sans-serif;background:#fff;color:#111}}
.bench{{display:flex;gap:12px;padding:12px;height:100vh;box-sizing:border-box}} .bench data-facets{{width:260px;flex:none;overflow:auto}}
.bench data-views{{flex:1;min-width:0;--data-height:calc(100vh - 24px)}}</style></head>
<body><div class="bench">{'<data-facets for="s"></data-facets>' if rail else ''}<data-views id="s" src="{t['src']}"{view} no-url></data-views></div></body></html>"""


# ------------------------------------------------------------------ the server (in-process; stopped in finally)
class Handler(http.server.SimpleHTTPRequestHandler):
    pages: dict[str, str] = {}
    dist: pathlib.Path = ROOT / "dist"

    def log_message(self, *a):
        pass

    def end_headers(self):
        # WHY no-cache: the browser revalidates (a 304 when unchanged), as a static host does; a warm load then pays a
        # round trip per file, never a stale file
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def translate_path(self, path):
        p = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        for prefix, root in (("/dist/", self.dist), ("/scenarios/", SCENARIOS), ("/gen/", GEN)):
            if p.startswith(prefix):
                f = (root / p[len(prefix):]).resolve()
                if root.resolve() in f.parents or f == root.resolve():
                    return str(f)
        return str(BENCH / "__none__")

    def do_GET(self):
        p = urllib.parse.urlsplit(self.path).path
        if p.startswith("/page/"):
            body = self.pages.get(p[len("/page/"):], "").encode()
            if not body:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if p == "/blank.html":
            body = b"<!doctype html><title>blank</title>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


Handler.extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".base": "text/yaml", ".js": "text/javascript",
                          ".json": "application/json", ".jsonl": "application/x-ndjson", ".pmtiles": "application/octet-stream"}


@functools.lru_cache(maxsize=None)
def gzip_size(path: str) -> int | None:
    try:
        return len(gzip.compress(pathlib.Path(path).read_bytes(), compresslevel=6))
    except OSError:
        return None


# ------------------------------------------------------------------ one page load
LOAD_JS = """async () => {
  const B = window.__bench;
  const tti = await B.interactive(500, 30000);
  const nav = performance.getEntriesByType('navigation')[0];
  const res = performance.getEntriesByType('resource').map((r) => ({ url: r.name, start: r.startTime, end: r.responseEnd, transfer: r.transferSize, body: r.encodedBodySize, decoded: r.decodedBodySize, type: r.initiatorType }));
  const fcp = B.paints['first-contentful-paint'] ?? null;
  const lcp = B.lcp.length ? B.lcp[B.lcp.length - 1] : null;
  const m = (n) => { const x = B.marks.find((k) => k.name === n); return x ? x.t : null; };
  const firstModel = B.measures.find((x) => x.name === 'data-ui:model');
  const firstRender = B.measures.find((x) => x.name === 'data-ui:render');
  const end = tti ?? performance.now();
  const blocking = B.longtasks.filter((t) => fcp !== null && t.start >= fcp && t.start < end).reduce((s, t) => s + Math.max(0, t.duration - 50), 0);
  const el = document.querySelector('data-views');
  return {
    fcp, lcp: lcp && lcp.t, lcp_tag: lcp && lcp.tag, first_render: B.firstRender, first_useful_paint: B.firstUsefulPaint, tti, tbt: blocking,
    mark_data: m('data-ui:data'), mark_start: m('data-ui:start'), mark_first_render: m('data-ui:first-render'),
    model_ms: firstModel ? firstModel.duration : null, render_ms: firstRender ? firstRender.duration : null,
    rail_ms: B.measures.filter((x) => x.name === 'data-ui:rail').reduce((s, x) => s + x.duration, 0),
    rails: B.measures.filter((x) => x.name === 'data-ui:rail').length,
    longtasks: B.longtasks.length, longtask_ms: B.longtasks.reduce((s, t) => s + t.duration, 0),
    dom_nodes: document.getElementsByTagName('*').length,
    nav_transfer: nav ? nav.transferSize : null, resources: res, errors: B.errors,
    status: el ? (el.querySelector('.dv-status') || {}).textContent || '' : '', view: el && el.dataset.view,
    health: window.__benchHealth(),
  };
}"""

# WHY a health probe on every load and after the interactions: at 150,000 rows the rail threw and drew nothing while
# the table still painted, so every paint KPI "passed". A part that should be on the page and is not is a FAILED run,
# never a fast one (coordinator, 2026-10-26: "silent wins like that 150k one must be impossible").
HEALTH_JS = """window.__benchHealth = () => {
  const B = window.__bench, el = document.querySelector('data-views'), rail = document.querySelector('data-facets');
  const why = [];
  if (!el) why.push('no <data-views> on the page');
  else {
    const err = el.querySelector('.dv-err');
    if (err) why.push('data-views shows an error: ' + err.textContent.trim().slice(0, 160));
    const notice = el.querySelector('.dv-notice:not([hidden])');
    if (notice && notice.textContent.trim()) why.push('view fell back: ' + notice.textContent.trim().slice(0, 160));
    const want = el.view && el.view.type, drew = el.dataset.view;
    if (want && drew && want !== drew) why.push(`asked for a ${want} view, drew a ${drew}`);
    const stage = el.querySelector('.dv-stage');
    if (!stage || !stage.querySelector('.dv-view')) why.push('no view in the stage');
  }
  if (rail) {
    const drawn = B.measures.some((m) => m.name === 'data-ui:rail');
    if (!drawn) why.push('the rail never finished a draw (no data-ui:rail measure)');
    if (!rail.querySelector('.df-box')) why.push('the rail is empty');
  }
  if (B.errors.length) why.push('page error: ' + String(B.errors[0]).slice(0, 160));
  return { ok: why.length === 0, why };
};"""


def heap_mb(cdp):
    try:
        cdp.send("HeapProfiler.collectGarbage")
        metrics = {m["name"]: m["value"] for m in cdp.send("Performance.getMetrics")["metrics"]}
        return round(metrics.get("JSHeapUsedSize", 0) / 2**20, 2)
    except Exception:
        return None


def load_once(page, cdp, url, base_url, errors):
    t0 = time.time()
    m0 = time.monotonic()
    page.goto(url, wait_until="load", timeout=120000)
    r = page.evaluate(LOAD_JS)
    # WHY its own time: the sample is judged by the pressure windows over it (bench/trust.py, judge r2 finding 4);
    # time.monotonic() is CLOCK_MONOTONIC, the clock the Sampler and an injector in another process both read
    r["t0"], r["t1"] = round(m0, 4), round(time.monotonic(), 4)
    r["heap_mb"] = heap_mb(cdp)
    r["wall_s"] = round(time.time() - t0, 2)
    r["errors"] = r["errors"] + errors[:]
    errors.clear()
    files = []
    transfer = gz = raw = 0
    for res in r.pop("resources"):
        path = urllib.parse.urlsplit(res["url"]).path
        local = Handler.translate_path(Handler, path) if res["url"].startswith(base_url) else None
        g = gzip_size(local) if local and os.path.isfile(local) else None
        files.append({"path": path, "start": round(res["start"], 1), "end": round(res["end"], 1), "transfer": res["transfer"], "body": res["body"], "gzip": g})
        transfer += res["transfer"] or 0
        raw += res["decoded"] or 0
        gz += g or 0
    r["files"] = files
    r["bytes_transfer"] = transfer + (r.get("nav_transfer") or 0)
    r["bytes_raw"] = raw
    r["bytes_gzip"] = gz
    # the first-paint chain (Codex: "the model is computed before the view bundle is even requested")
    view_js = [f for f in files if "/dist/views/" in f["path"]]
    data = [f for f in files if f["path"].startswith(("/scenarios/", "/gen/")) and not f["path"].endswith(".base") and f["path"].endswith((".json", ".jsonl", ".csv", ".tsv"))]
    r["chain"] = {
        "core_js_end": next((f["end"] for f in files if f["path"].endswith("/dist/data-ui.js")), None),
        "base_end": next((f["end"] for f in files if f["path"].endswith(".base")), None),
        "data_start": data[0]["start"] if data else None, "data_end": data[0]["end"] if data else None,
        "view_js_start": view_js[0]["start"] if view_js else None, "view_js_end": view_js[0]["end"] if view_js else None,
    }
    return r


# ------------------------------------------------------------------ interactions on a loaded page
def interactions(page, t, log):
    out = []
    ix = t.get("interactions") or {}

    def take(kind, r, **extra):
        if r is None:
            return
        r.update(extra)
        r["kind"] = kind
        out.append(r)

    def timed(run):
        """The interaction's result with its own time (t0, t1: time.monotonic()), judged later by the pressure over it."""
        m0 = time.monotonic()
        r = run()
        if r is not None:
            r["t0"], r["t1"] = round(m0, 4), round(time.monotonic(), 4)
        return r

    def armed(kind, action, wait="data-views-render"):
        def run():
            page.evaluate(f"window.__bench.arm({json.dumps(kind)}, {json.dumps(wait)})")
            action()
            return page.evaluate("window.__bench.result()")
        return timed(run)

    def programmatic(kind, js, wait="data-views-render"):
        return timed(lambda: page.evaluate(f"window.__bench.act({json.dumps(kind)}, () => {{ {js} }}, {json.dumps(wait)})"))

    el = "document.querySelector('data-views')"
    # filter: tick a rail value and untick it (the rail's own checkbox when it shows; else the all-views filter)
    f = ix.get("filter")
    if f:
        sel = f'data-facets input[type=checkbox][data-p="{f["property"]}"][data-value="{f["value"]}"]'
        box = page.locator(sel)
        real = box.count() > 0 and box.first.is_visible()
        for i in range(3):
            for state in ("on", "off"):
                if real:
                    take("filter", armed("filter", lambda: box.first.click()), how="rail checkbox", state=state)
                else:
                    clause = f["property"] + " == " + json.dumps(f["value"])
                    js = f"{el}.filters = {json.dumps({'and': [clause]})};" if state == "on" else f"{el}.filters = null;"
                    take("filter", programmatic("filter", js), how="el.filters", state=state)
    # sort: click the column header twice (descending, ascending) on a table; else setView
    s = ix.get("sort")
    if s:
        th = page.locator(f'data-views th[data-col="{s["property"]}"] .dv-th')
        for i in range(4):
            if th.count() and th.first.is_visible():
                take("sort", armed("sort", lambda: th.first.click()), how="header click")
            else:
                d = s.get("direction", "DESC") if i % 2 == 0 else ("ASC" if s.get("direction", "DESC") == "DESC" else "DESC")
                take("sort", programmatic("sort", f"{el}.setView({{sort: [{{property: {json.dumps(s['property'])}, direction: {json.dumps(d)}}}]}});"), how="setView")
    # search: type the query a key at a time (each keystroke is one interaction), then clear it
    q = ix.get("search")
    if q:
        box = page.locator("data-views .dv-search input")
        if box.count():
            box.first.click()
            for ch in q:
                take("search", armed("search", lambda ch=ch: page.keyboard.press(ch)), how="keystroke")
            take("search", armed("search", lambda: (page.keyboard.press("Control+A"), page.keyboard.press("Backspace"))), how="clear")
    # peek: open a row's record (a table row click; else host.open), Escape between
    if ix.get("peek"):
        n_rows = page.evaluate(f"({el}.model && {el}.model.rows.length) || 0")
        for k in (k for k in (0, 5, 12) if k < n_rows):
            row = page.locator("data-views .dv-view-table tbody tr[data-i]:not(.dv-group)")
            if row.count() > k and row.nth(k).is_visible():
                take("peek", armed("peek", lambda: row.nth(k).locator("td").nth(1 if row.nth(k).locator("td").count() > 1 else 0).click(), "data-views-open"), how="row click")
            else:
                take("peek", programmatic("peek", f"const v = {el}; const r = v.model.rows[{k}]; if (r) v.openPeek(r.id);", "data-views-open"), how="openPeek")
            page.keyboard.press("Escape")
            page.wait_for_timeout(50)
    # presets: click each listed tab in turn, then back to the first view; twice (the first visit pays the bundle)
    presets = ix.get("presets") or []
    if presets:
        first = page.evaluate(f"{el}.origin && {el}.origin.name")
        for cycle in range(2):
            for name in presets + [first]:
                tab = page.locator(f'data-views .dv-tab[data-name="{name}"]')
                if tab.count():
                    take("preset", armed("preset", lambda: tab.first.click()), how="tab click", to=name, cycle=cycle)
    # scroll: the view's scroller, 120 px a frame for 2 s (a fast wheel), frame intervals from rAF
    scroll = None
    if ix.get("scroll"):
        if presets:
            first_tab = page.locator("data-views .dv-tab").first
            first_tab.click()
            page.wait_for_timeout(300)
        m0 = time.monotonic()
        scroll = page.evaluate("window.__bench.scroll(2000, 120)")
        if scroll is not None:
            scroll["t0"], scroll["t1"] = round(m0, 4), round(time.monotonic(), 4)
    return out, scroll


def calibrate(browser):
    """(the fixed-work loop's best of 3 in ms, the CPU lists of the browser's processes while it ran). WHY the CPU lists:
    the control must run with the measured page's affinity. It runs in the same browser, whose processes inherit
    run.mjs's taskset from the runner (checked 2026-10-27: the driver and all six Chromium processes on 4-11); reading
    them while the calibration's renderer is alive proves it per scenario instead of assuming it."""
    ctx = browser.new_context()
    try:
        page = ctx.new_page()
        page.set_content("<!doctype html><title>calibrate</title>")
        page.add_script_tag(content=HARNESS)
        ms = min(page.evaluate("window.__bench.calibrate().ms") for _ in range(3))
        return ms, trustlib.tree_affinity()
    finally:
        ctx.close()


def loadavg():
    try:
        return os.getloadavg()[0]
    except OSError:
        return None


def host_info(browser):
    cpu = ""
    try:
        cpu = next(line.split(":", 1)[1].strip() for line in open("/proc/cpuinfo") if line.startswith("model name"))
    except (OSError, StopIteration):
        pass
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
    return {"hostname": socket.gethostname(), "cpu": cpu, "cpus": os.cpu_count(), "pinned_cpus": affinity, "os": platform.platform(),
            "browser": f"chromium {browser.version}", "viewport": VIEWPORT, "device_scale_factor": 1, "cpu_throttle": None}


def git_sha():
    try:
        sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short=8", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "packages", "build.mjs"], capture_output=True, text=True).stdout.strip()
        branch = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip()
        return sha, bool(dirty), branch
    except Exception:
        return None, None, None


def best_calibration(host, measured):
    """This host's best calibration ever (the quiet-machine reference), kept outside git; updated when beaten."""
    f = STATE / "calibration.json"
    try:
        known = json.loads(f.read_text())
    except (OSError, ValueError):
        known = {}
    best = min([measured] + ([known[host]] if host in known else []))
    known[host] = best
    STATE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(known, indent=1))
    return best


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", action="append", help="a scenario id or variant (large-table@10000); repeat or comma-separate. Default: all")
    ap.add_argument("--runs", type=int, default=7, help="cold and warm loads per scenario (default 7; variants of 100k rows or more run half, at least 3)")
    ap.add_argument("--out", default=str(BENCH / ".out"), help="results directory (default bench/.out)")
    ap.add_argument("--dist", default=str(ROOT / "dist"), help="the data-ui build to measure (default this checkout's dist/)")
    ap.add_argument("--no-interactions", action="store_true")
    ap.add_argument("--label", default="", help="a free note stored with the run (e.g. 'baseline on main 0dbc3d4')")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--sha", default=None, help="the commit the measured build is (with --dist from another checkout); default this checkout's HEAD")
    ap.add_argument("--webgl", choices=("gpu", "software"), default="gpu",
                    help="map (WebGL) scenarios: gpu (default) runs them in a browser on the GPU when it really gets a hardware renderer, "
                         "else software and says so; software forces headless Chromium's SwiftShader")
    args = ap.parse_args()
    wanted = [w for s in (args.scenario or []) for w in s.split(",") if w]
    targets = load_scenarios(wanted or None)
    Handler.dist = pathlib.Path(args.dist).resolve()
    if not (Handler.dist / "data-ui.js").exists():
        sys.exit(f"{Handler.dist}/data-ui.js is missing: run npm run build first")
    for t in targets:
        prepare(t)
        Handler.pages[f"{t['target']}.html"] = page_html(t)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    sha, dirty, branch = git_sha()
    if args.sha:
        sha, dirty, branch = args.sha, False, f"--dist {args.dist}"
    started = dt.datetime.now(dt.timezone.utc)
    results = {"schema": "data-ui-bench/1", "started": started.isoformat(timespec="seconds"), "label": args.label,
               "code": {"sha": sha, "dirty": dirty, "branch": branch, "dist": str(Handler.dist)}, "runs": args.runs, "scenarios": []}
    print(f"data-ui bench: {len(targets)} scenario(s), {args.runs} cold + {args.runs} warm loads each, on {base_url}", flush=True)
    try:
        with sync_playwright() as pw:
            default_browser = pw.chromium.launch(headless=not args.headed, args=BROWSER_ARGS)
            gpu_browser = None
            # what WebGL each browser gets: {"kind": gpu|software|none, "string": the renderer, "args": the extra flags}
            renderers = {"default": {"string": webgl_renderer(default_browser), "args": []}}
            renderers["default"]["kind"] = renderer_kind(renderers["default"]["string"])
            try:
                results["host"] = host_info(default_browser)
                results["host"]["webgl_renderer"] = renderers["default"]
                host = results["host"]["hostname"]
                # the CPUs the trust verdict judges: the ones run.mjs pinned the runner to, and the SMT siblings that
                # share their physical cores (finding 7: the host's 24 CPUs are not what the bench runs on)
                assigned = results["host"]["pinned_cpus"] or list(range(os.cpu_count() or 1))
                siblings = trustlib.read_smt_siblings(assigned)
                results["host"]["smt_siblings"] = siblings
                for t in targets:
                    print(f"\n== {t['target']} ({t.get('rows')} rows)", flush=True)
                    browser, which = default_browser, "default"
                    webgl = uses_webgl(t)
                    if webgl and args.webgl == "gpu":
                        if "gpu" not in renderers:
                            gpu_browser = pw.chromium.launch(headless=not args.headed, args=BROWSER_ARGS + GPU_ARGS)
                            got = webgl_renderer(gpu_browser)
                            renderers["gpu"] = {"string": got, "kind": renderer_kind(got), "args": GPU_ARGS}
                            if renderers["gpu"]["kind"] != "gpu":
                                # WHY fall back, loudly: a flag that silently lands on SwiftShader would label a CPU number "gpu"
                                print(f"  no hardware WebGL with {' '.join(GPU_ARGS)} (got {got!r}): map scenarios run on software", flush=True)
                                gpu_browser.close()
                                gpu_browser = None
                        if gpu_browser is not None:
                            browser, which = gpu_browser, "gpu"
                    renderer = {**renderers[which], "webgl": webgl}
                    if webgl:
                        print(f"  WebGL renderer: {renderer['kind']} ({renderer['string']})", flush=True)
                    runs = args.runs if (t.get("rows") or 0) < 100000 else min(args.runs, max(3, args.runs // 2))
                    before, during0 = trustlib.idle_window(assigned, siblings)
                    # WHY a 200 ms timeline through the scenario (judge r2, finding 4): one averaged "during" window hid a
                    # 1 s burst of full saturation in 20 s (5 %); each sample is judged by the windows over its own time
                    sampler = trustlib.Sampler(assigned, siblings).start()
                    try:
                        (calib0, cpus0), load0 = calibrate(browser), loadavg()
                        cold, warm, inter, scrolls, errs, health_fail = [], [], [], [], [], []
                        for i in range(runs):
                            ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1, color_scheme="light")
                            page_errors: list[str] = []
                            try:
                                page = ctx.new_page()
                                sampler.rescan()  # the new context's renderer, known before its load's window opens
                                page.on("pageerror", lambda e, pe=page_errors: pe.append(str(e)))
                                page.add_init_script(HARNESS)
                                page.add_init_script(HEALTH_JS)
                                cdp = ctx.new_cdp_session(page)
                                cdp.send("Performance.enable")
                                url = f"{base_url}/page/{t['target']}.html"
                                c = load_once(page, cdp, url, base_url, page_errors)
                                cold.append(c)
                                w = load_once(page, cdp, url, base_url, page_errors)
                                warm.append(w)
                                # WHY here, before the interactions: a crash while driving the page must not hide what the loads saw
                                for ph, r in (("cold", c), ("warm", w)):
                                    if r["first_useful_paint"] is None:
                                        health_fail.append(f"{ph} load: no first useful paint")
                                    if not r["health"]["ok"]:
                                        health_fail += [f"{ph} load: {x}" for x in r["health"]["why"]]
                                if not args.no_interactions and w["first_useful_paint"] is not None:
                                    ints, sc = interactions(page, t, print)
                                    inter += [dict(x, run=i) for x in ints]
                                    if sc:
                                        scrolls.append(sc)
                                    after = page.evaluate("window.__benchHealth()")
                                    if not after["ok"]:
                                        health_fail += [f"after interactions: {w}" for w in after["why"]]
                                errs += c["errors"] + w["errors"] + page_errors
                                if page_errors:
                                    health_fail += [f"page error: {x[:160]}" for x in page_errors]
                                print(f"  run {i + 1}/{runs}: first useful paint cold {fmt(c['first_useful_paint'])} warm {fmt(w['first_useful_paint'])} ms; "
                                      f"tti {fmt(c['tti'])}; {c['bytes_gzip'] / 1024:.0f} KB gz; heap {c['heap_mb']} MB", flush=True)
                            except Exception as e:  # a scenario that breaks is a finding, recorded, never a crash of the bench
                                errs.append(f"{type(e).__name__}: {e}")
                                health_fail.append(f"the bench could not drive it: {type(e).__name__}: {str(e)[:160]}")
                                traceback.print_exc()
                            finally:
                                ctx.close()
                        (calib1, cpus1), load1 = calibrate(browser), loadavg()
                    finally:
                        timeline = sampler.stop()
                    during = trustlib.pressure(during0, trustlib.snapshot(), assigned, siblings)
                    after, _ = trustlib.idle_window(assigned, siblings)
                    best = best_calibration(host, min(calib0, calib1))
                    results["scenarios"].append(aggregate(t, cold, warm, inter, scrolls, errs, calib0, calib1, best, load0, load1, runs,
                                                          pressure={"before": before, "during": during, "after": after},
                                                          cpus={"assigned": assigned, "smt_siblings": siblings, "browser": sorted(set(cpus0) | set(cpus1))},
                                                          timeline=timeline))
                    s = results["scenarios"][-1]
                    s["renderer"] = renderer
                    s["verdict"] = "FAILED" if health_fail else "ok"
                    s["failed_because"] = sorted(set(health_fail))[:12]
                    if health_fail:
                        print(f"  => FAILED: {'; '.join(s['failed_because'][:3])}", flush=True)
                    print(f"  => first useful paint p95 cold {fmt(s['load']['cold']['first_useful_paint']['p95'])} ms, warm {fmt(s['load']['warm']['first_useful_paint']['p95'])} ms; "
                          f"interaction p95 {fmt(s['interaction']['all']['p95'])} ms; trust {s['trust']['verdict']} ({', '.join(s['trust']['why']) or 'quiet'}); "
                          f"stability {s['stability']['verdict']}{' (' + s['stability']['why'] + ')' if s['stability']['why'] else ''}", flush=True)
                    tm = s["trust"]["timing"]
                    if any(v["n"] - v["clean"] for v in tm.values()):
                        print("     samples that overlapped interference (left out): "
                              + ", ".join(f"{k} {v['n'] - v['clean']}/{v['n']}" + ("" if v["valid"] else " SUPPRESSED") for k, v in tm.items()), flush=True)
                    pr = s["trust"]["pressure"] or {}
                    if any(pr.values()):
                        f = lambda key, fmt_: "/".join("—" if not pr.get(k) or pr[k][key] is None else fmt_(pr[k][key]) for k in ("before", "during", "after"))
                        print(f"     machine: calibration {s['trust']['calibration_ratio']}x best; other work on CPUs {cpu_list(assigned)} "
                              f"{f('foreign_cpus', lambda x: f'{x:.1f}')} of {len(assigned)} (before/during/after); SMT siblings {cpu_list(siblings) or 'none'} "
                              f"{f('siblings_busy_share', lambda x: f'{100 * x:.0f}%')} busy; browser on {', '.join(s['trust']['browser_cpus'] or ['?'])}", flush=True)
            finally:
                default_browser.close()
                if gpu_browser is not None:
                    gpu_browser.close()
    finally:
        server.shutdown()
        server.server_close()
    results["finished"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    results["verdict"] = "FAILED" if any(s["verdict"] == "FAILED" for s in results["scenarios"]) else "ok"
    results["trust"] = "noisy" if any(s["trust"]["verdict"] == "noisy" for s in results["scenarios"]) else "quiet"
    verdicts = {s["stability"]["verdict"] for s in results["scenarios"]}
    results["stability"] = "unstable" if "unstable" in verdicts else "stable" if verdicts == {"stable"} else "pending"
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%d-%H%M%S")
    (out / f"results-{stamp}.json").write_text(json.dumps(results, indent=1))
    (out / "latest.json").write_text(json.dumps(results, indent=1))
    print(f"\nwrote {out / f'results-{stamp}.json'} (trust: {results['trust']}; stability: {results['stability']}; verdict: {results['verdict']})")
    failed = [s["target"] for s in results["scenarios"] if s["verdict"] == "FAILED"]
    if failed:
        print(f"FAILED: {', '.join(failed)}: their numbers are not published as passing (bench/publish.py)")
        sys.exit(1)


def fmt(x):
    return "—" if x is None else f"{x:.0f}"


def cpu_list(cpus):
    """[4, 5, 6, 7, 16] as "4-7,16", the kernel's own spelling."""
    out, run = [], []
    for c in sorted(cpus or []):
        if run and c == run[-1] + 1:
            run.append(c)
        else:
            if run:
                out.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else str(run[0]))
            run = [c]
    if run:
        out.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else str(run[0]))
    return ",".join(out)


# load keys a busy CPU does not move: summarized over every load, never only the clean ones (bench/trust.py)
INSENSITIVE_LOAD_KEYS = ("heap_mb", "bytes_transfer", "bytes_raw", "bytes_gzip", "dom_nodes")


def aggregate(t, cold, warm, inter, scrolls, errs, calib0, calib1, best, load0, load1, runs, pressure=None, cpus=None, timeline=None):
    """One scenario's record. pressure: {"before"|"during"|"after": trust.pressure()} on the assigned CPUs; cpus:
    {"assigned", "smt_siblings", "browser" (the CPU lists the browser's processes had)}; timeline: the Sampler's
    snapshots, against which every sample with a time ("t0", "t1": time.monotonic()) is judged. Any may be None.

    With a timeline, each sample gets "pressure" and "clean", the timing summaries are over the clean samples of a
    valid set, and the before/after/during windows are context. Without one (no /proc, or a caller from before
    judge r2), the windows judge the whole scenario as before."""
    cpus = cpus or {}
    assigned = list(cpus.get("assigned") or (sorted(timeline[0]["cpu"]) if timeline else []))
    siblings = list(cpus.get("smt_siblings") or [])
    # WHY not the load average (Codex, finding 7): it is the host's, divided by the host's 24 CPUs, so eight saturated
    # assigned CPUs passed as quiet and a build on the other sixteen counted against a run it never touched
    unpinned = [x for x in cpus.get("browser") or [] if cpus.get("assigned") and trustlib.parse_cpu_list(x) != list(cpus["assigned"])]
    # WHY the windows only without a timeline (judge r2, findings 3 and 4): a scenario-long average hides a 1 s burst,
    # and an after-window saw interference the samples never met, yet suppressed them all
    machine = trustlib.machine(calib0, calib1, best, None if timeline else pressure, unpinned)
    measured = [x for x in inter if x.get("ms") is not None]
    sets = {"cold": cold, "warm": warm, "interactions": measured}
    # a scroll run's samples are its frames: frame k ends at the run's start plus its first k rAF intervals (the first
    # rAF comes within a frame of the evaluate, well inside a 200 ms window). WHY not the run: it spans ten windows, so
    # judged whole it was dropped whenever any of them was busy, which on the shared box was every run
    frame_flags = [[True] * len(sc["frames"]) for sc in scrolls]
    if timeline:
        for rows in sets.values():
            for r, j in zip(rows, trustlib.judge_intervals(timeline, [(r.get("t0"), r.get("t1")) for r in rows], assigned, siblings)):
                r["pressure"] = {k: j[k] for k in ("foreign_share", "siblings_busy_share", "windows")}
                r["clean"] = j["clean"]
                if j["why"]:
                    r["interference"] = j["why"]
        for k, sc in enumerate(scrolls):
            spans, at = [], sc.get("t0")
            for f in sc["frames"]:
                spans.append((at, None if at is None else at + f / 1000))
                at = None if at is None else at + f / 1000
            frame_flags[k] = [j["clean"] for j in trustlib.judge_intervals(timeline, spans, assigned, siblings)]
            sc["frames_clean"] = sum(frame_flags[k])
    # each timing set is judged as one: valid (its KPIs go to the series) or suppressed (bench/publish.py keeps them
    # out and fails the timing_valid gate for this build, with the reason)
    timing = {k: trustlib.judge_set(k, [r.get("clean", True) for r in rows] if timeline else [True] * len(rows), machine)
              for k, rows in sets.items() if rows}
    if scrolls:
        timing["scroll"] = trustlib.judge_set("scroll", [c for flags in frame_flags for c in flags], machine)

    def timed(name, rows):
        """The rows a set's timing summaries are over: its clean samples when it is valid; every sample when it is
        suppressed (its points go to the diagnostics, which should show what was measured)."""
        return [r for r in rows if r.get("clean", True)] if (timing.get(name) or {}).get("valid") else rows

    def loads(name, rows):
        keys = ["fcp", "lcp", "first_render", "first_useful_paint", "tti", "tbt", "model_ms", "render_ms", "rail_ms", "heap_mb", "bytes_transfer", "bytes_raw", "bytes_gzip",
                "mark_data", "mark_start", "dom_nodes", "longtask_ms"]
        clean = timed(name, rows)
        agg = {k: summary([r.get(k) for r in (rows if k in INSENSITIVE_LOAD_KEYS else clean)]) for k in keys}
        agg["chain"] = {k: summary([r["chain"].get(k) for r in clean]) for k in (rows[0]["chain"] if rows else {})}
        agg["failed"] = sum(1 for r in rows if r.get("first_useful_paint") is None)
        return agg

    timed_inter = timed("interactions", measured)
    kinds = sorted({x["kind"] for x in inter})
    interaction = {"all": summary([x["ms"] for x in timed_inter])}
    for k in kinds:
        xs = [x for x in timed_inter if x["kind"] == k]
        every = [x for x in inter if x["kind"] == k]
        interaction[k] = {**summary([x["ms"] for x in xs]), "model_ms": summary([x.get("model_ms") for x in xs]), "render_ms": summary([x.get("render_ms") for x in xs]),
                          "rail_ms": summary([x.get("rail_ms") for x in xs]), "dom_added": summary([x.get("dom_added") for x in every]),
                          "longtask_ms": summary([x.get("longtask_ms") for x in xs]), "how": sorted({x.get("how", "") for x in every}),
                          "missed": sum(1 for x in every if x.get("ms") is None), "dropped": sum(1 for x in every if x.get("clean") is False)}
    scroll_ok = (timing.get("scroll") or {}).get("valid")
    frames = [f for sc, flags in zip(scrolls, frame_flags) for f, c in zip(sc["frames"], flags) if c or not scroll_ok]
    scroll = None
    if frames:
        scroll = {**summary(frames), "dropped_pct": round(100 * sum(1 for f in frames if f > 1000 / 60 * 1.5) / len(frames), 1), "frames": len(frames),
                  "longtask_ms": summary([sc["longtask_ms"] for sc in scrolls]), "dom_added": summary([sc["dom_added"] for sc in scrolls])}
    ncpu = os.cpu_count() or 1
    pinned = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else ncpu
    # WHY two verdicts (Codex, finding 6): the cold first paints' spread used to be one of the "noisy" reasons, so an
    # app that really got slow on one load in five was filed as noise and its p95 left the KPI series. The machine is
    # judged only by what is measured apart from the app; the app's spread is a result (bench/trust.py)
    cold_ok = (timing.get("cold") or {}).get("valid", True)
    stability = trustlib.stability([r.get("first_useful_paint") for r in timed("cold", cold)], "quiet" if cold_ok else "noisy")
    suppressed = [k for k, v in timing.items() if not v["valid"]]
    why = list(machine["why"]) + ([f"{k}: {timing[k]['why']}" for k in suppressed] if machine["verdict"] == "quiet" else [])
    return {
        "id": t["id"], "target": t["target"], "title": t.get("title"), "app": t.get("app"), "rows": t.get("rows"), "synthetic": bool(t.get("synthetic")),
        "view": cold[0]["view"] if cold else None, "status_line": cold[0]["status"] if cold else None, "runs": runs,
        "load": {"cold": loads("cold", cold), "warm": loads("warm", warm)}, "interaction": interaction, "scroll": scroll,
        "samples": {"cold": [strip(r) for r in cold], "warm": [strip(r) for r in warm], "interactions": inter,
                    "scroll": [{"t0": sc.get("t0"), "t1": sc.get("t1"), "frames": len(sc["frames"]), "frames_clean": sc.get("frames_clean")} for sc in scrolls]},
        "errors": sorted(set(errs))[:20],
        "trust": {"verdict": "noisy" if machine["verdict"] == "noisy" or suppressed else "quiet", "why": why,
                  "calibration_ms": [round(calib0, 1), round(calib1, 1)], "best_calibration_ms": round(best, 1),
                  "calibration_ratio": machine["calibration_ratio"], "loadavg": [load0, load1], "cpus": ncpu, "pinned_cpus": pinned,
                  "assigned_cpus": cpus.get("assigned"), "smt_siblings": cpus.get("smt_siblings"), "browser_cpus": cpus.get("browser"),
                  "pressure": pressure, "timing": timing,
                  "timeline": trustlib.timeline_summary(timeline, assigned, siblings) if timeline else None},
        "stability": stability,
    }


def strip(r):
    keep = {k: v for k, v in r.items() if k not in ("files",)}
    keep["files"] = r.get("files", [])
    return keep


if __name__ == "__main__":
    main()
