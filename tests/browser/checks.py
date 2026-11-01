"""The browser checks: the built site (dist/site/) in headless Chromium, light and dark, desktop and phone.

    ~/psu-atlas/.venv/bin/python tests/browser/checks.py [SHOTS_DIR]     # after npm run build

Grown from the table lane's 22 behaviour checks (robotparts lane/tables @ ab5ba92, capture.py): the checks of a
gallery case live in its own folder (gallery/examples/<case>/checks.py, a run(ctx) function), so a view lane adds
checks without touching this file. This file holds the site-wide ones and the screenshots. It serves dist/site on a
free 127.0.0.1 port, stops that server when it is done, writes SHOTS_DIR/checks.json (default reports/media/phase0)
and exits 1 if any check fails. A check that fails is reported, never hidden.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
SITE = ROOT / "dist" / "site"
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "phase0"
OUT.mkdir(parents=True, exist_ok=True)
checks: list[dict] = []
# WHY a ceiling, not a pause: on this box load averages of 40-67 are common (2026-10-26 performance review); a wait
# for a state ends as soon as the state arrives, and only a state that never comes costs the whole ceiling
WAIT = 30000
THROTTLE = float(os.environ.get("DATA_UI_CPU_THROTTLE") or 0)


def check(name, ok, value=None, soft=False):
    checks.append({"name": name, "ok": bool(ok), "value": value, **({"soft": True} if soft else {})})
    print(("SOFT " if soft else "PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Ctx:
    """What a case's checks.py gets: the site's URL, a browser, check() and shot()."""

    def __init__(self, browser, base):
        self.browser, self.base, self.check = browser, base, check
        self.foreign: list[str] = []
        self.errors: list[str] = []

    def page(self, path, width=1440, height=900, dark=False, mobile=False):
        context = self.browser.new_context(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light",
                                           device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
        page = context.new_page()
        if THROTTLE:
            # DATA_UI_CPU_THROTTLE=4: every page runs 4x slower, as on a loaded machine, so a check that leans on a pause
            # instead of a state shows itself on demand
            context.new_cdp_session(page).send("Emulation.setCPUThrottlingRate", {"rate": THROTTLE})
        page.ctx = self  # so a case's helpers that take only a page can wait on state (until, drawn, frames)
        page.on("request", lambda r: self.foreign.append(r.url) if not r.url.startswith(self.base) and not r.url.startswith("data:") and not r.url.startswith("blob:") else None)
        page.on("pageerror", lambda e: self.errors.append(f"{path}: {e}"))
        page.on("console", lambda m: self.errors.append(f"{path}: console {m.text}") if m.type == "error" else None)
        page.goto(f"{self.base}/{path}")
        page.wait_for_load_state("networkidle")
        if page.locator("data-views").count():
            # WHY not a table row: a case whose first view is cards, kanban or a chart never draws one
            page.wait_for_selector("data-views .dv-status", timeout=WAIT)
            page.wait_for_function("() => [...document.querySelectorAll('data-views .dv-status')].every(e => e.textContent.trim())", timeout=WAIT)
            # every started <data-views> has drawn its view once (data-view is set by its first data-views-render)
            self.until(page, "() => [...document.querySelectorAll('data-views')].filter((e) => e.querySelector('.dv-status')).every((e) => e.dataset.view)")
        self.frames(page)
        return page

    def until(self, page, predicate, arg=None, timeout=WAIT):
        """Wait for a state instead of a fixed pause: `predicate` is a JS function (of `arg`) that turns truthy. False
        when the state never comes, so the check that reads it reports the miss in its own words."""
        try:
            page.wait_for_function(predicate, arg=arg, timeout=timeout)
            return True
        except PlaywrightTimeout:
            return False

    def drawn(self, page, action, scope="#example", timeout=WAIT):
        """Do `action()` (a click, a key, a filter) and wait for the <data-views> at `scope` to draw again (its next
        data-views-render), then for the frame it paints in."""
        page.evaluate("""(s) => { const el = document.querySelector(s); window.__dvDrawn = false;
          el.addEventListener('data-views-render', () => { window.__dvDrawn = true; }, { once: true }); }""", scope)
        action()
        ok = self.until(page, "() => window.__dvDrawn", timeout=timeout)
        self.frames(page)
        return ok

    @staticmethod
    def frames(page, n=2):
        """Let the browser paint: n animation frames (what a fixed 150-250 ms pause stood in for)."""
        page.evaluate("(n) => new Promise((done) => { const step = (k) => (k ? requestAnimationFrame(() => step(k - 1)) : done()); step(n); })", n)

    def budget(self, name, ms, limit, value=None):
        """A speed budget that knows the machine it ran on. Enforced while the 1-minute load average is under the CPU
        count; above it a miss is reported SOFT with the load beside it (not enforced, never a silent pass). The real
        speed budgets belong to the benchmark lane; these keep a 10x regression visible."""
        load, cpus = os.getloadavg()[0], os.cpu_count() or 1
        busy = load > cpus
        note = f"{ms:.0f} ms (budget {limit} ms); load {load:.1f} on {cpus} CPUs" + (f"; {value}" if value else "")
        if ms < limit or not busy:
            self.check(name, ms < limit, note)
        else:
            self.check(name, True, note + " -- OVERLOADED: budget not enforced on this run", soft=True)

    def shot(self, page, name, full=False):
        page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)


def status(page, scope="data-views"):
    return page.inner_text(f"{scope} .dv-status")


def graph_cases():
    """Every case whose views.base has a graph view, by its README title. WHY read, not listed: a new graph case
    (object-db-taxonomy, 2026-10-26) broke a hand-written list."""
    out = []
    for case in sorted((ROOT / "gallery" / "examples").iterdir()):
        base = case / "views.base"
        if base.exists() and re.search(r"^\s*-?\s*type:\s*graph\b", base.read_text(encoding="utf-8"), re.M):
            readme = case / "README.md"
            title = re.search(r"^#\s+(.*)$", readme.read_text(encoding="utf-8"), re.M).group(1).strip() if readme.exists() else case.name
            out.append(title)
    return sorted(out)


def site_checks(ctx: Ctx):
    # ---- the landing page: the hero shows one .base file's rows through five views, in turn
    page = ctx.page("index.html")
    check("landing: the live hero draws robotparts' 150 photographed actuators (the file's filter over 1,149 rows)", "150 of 1,149 rows" in status(page, "#hero"), status(page, "#hero"))
    value = page.locator("data-value").first
    title = value.locator(".dv-value").get_attribute("title") or ""
    check("landing: <data-value> keeps its text and adds the basis mark and the source on hover",
          "3.82 N·m" in value.inner_text() and value.locator(".dv-basis").inner_text() == "D" and "steadywin.cn" in title, value.inner_text())
    lazy = page.evaluate("performance.getEntriesByType('resource').map(e => e.name).filter(n => n.includes('/kit/views/'))")
    check("landing: only the hero's first view's code loads up front (the thumbnails start when scrolled near)", len(lazy) == 1 and lazy[0].endswith("/kit/views/table.js"), lazy)
    seen = []
    for name, sel in (("Cards", ".dv-view-cards .dv-cards-card img"), ("Chart", ".dv-view-chart canvas"), ("Kanban", ".dv-view-kanban .dv-kanban-card"), ("Graph", ".dv-view-graph .react-flow__node")):
        page.click(f".hero-demo .segmented button[data-name='{name}']")
        page.wait_for_selector(f"#hero {sel}", timeout=15000)
        seen.append((name, page.inner_text("#hero .dv-status").split(" · ")[0], page.get_attribute(f".hero-demo .segmented button[data-name='{name}']", "aria-pressed"), f"name: {name}" in page.inner_text(".hero-yaml")))
    check("landing: the hero's switch draws cards, a chart, a kanban and a graph of the same rows, and shows each view's .base entry",
          all(p == "true" and y for _, _, p, y in seen) and all(n == "150 of 1,149 rows" for _, n, _, _ in seen[:3]), seen)
    check("landing: a click stops the tour (Play to resume)", page.inner_text(".hero-play") == "Play")
    for _ in range(12):
        page.mouse.wheel(0, 700)
        page.wait_for_timeout(250)
    page.wait_for_function("() => [...document.querySelectorAll('.thumb data-views')].length === 13 && [...document.querySelectorAll('.thumb data-views')].every(e => e.dataset.view)", timeout=60000)
    drawn = page.evaluate("[...document.querySelectorAll('.thumb')].map(t => [t.querySelector('code').textContent, t.querySelector('data-views').dataset.view])")
    check("landing: thirteen live thumbnails, each drawing its view type from its gallery case", len(drawn) == 13 and all(a == b for a, b in drawn), drawn)
    rows = page.locator(".replaces-table tbody tr").count()
    cases = sum(1 for p in (ROOT / "gallery" / "examples").iterdir() if (p / "views.base").exists())
    check("landing: the Replaces table has a row per gallery case, each linking to it", rows == cases and page.locator(".replaces-table tbody a[href^='gallery/']").count() == cases, f"{rows} rows for {cases} cases")
    page.context.close()

    # ---- <data-kpi> and <data-sparkline> on a plain page (CONTRACT amendment 2026-10-26, core pass)
    page = ctx.page("plain/kpi.html")
    page.wait_for_selector("data-kpi .dv-kpi-num")
    got = page.evaluate("""() => ({
      defined: !!customElements.get('data-kpi') && !!customElements.get('data-sparkline'), views: document.querySelectorAll('data-views').length,
      styles: document.querySelectorAll('style[data-ui-view="kpi"]').length,
      size: getComputedStyle(document.querySelector('data-kpi .dv-kpi-num')).fontSize,
      border: getComputedStyle(document.querySelector('data-kpi .dv-kpi-card')).borderTopStyle,
      cards: [...document.querySelectorAll('data-kpi .dv-kpi-label')].map((e) => e.textContent),
      spark: document.querySelectorAll('data-sparkline svg path').length, hollow: document.querySelectorAll('data-sparkline .dv-spark-hollow').length })""")
    check("plain page: <data-kpi> and <data-sparkline> work with only data-ui.css and views/kpi.js (styled once, no <data-views>)",
          got["defined"] and got["views"] == 0 and got["styles"] == 1 and got["size"] == "22px" and got["border"] == "solid"
          and got["cards"] == ["Successful picks per minute", "Computation time", "Grasp success"] and got["spark"] == 1 and got["hollow"] == 1, got)
    page.context.close()

    # ---- the peek keeps authored text visible: a long unbroken value wraps inside the panel (never clipped at its edge)
    page = ctx.page("gallery/rack-wiring/index.html")
    url = ("https://github.com/zacharyyamaoka/bam_ws/blob/7157b86a342917bdcc7915113eb906bba12f294f/src/dev/bam_rack_twin/records/"
           "one-dof-test-rack/deployment.json#L216-L221")
    got = page.evaluate("""async (url) => {
      const box = document.createElement('div');
      box.style.cssText = 'position:fixed;top:0;left:0;width:1000px;height:700px;background:#fff;z-index:9999';
      const el = document.createElement('data-views');
      box.append(el);
      document.body.append(box);
      el.base = { views: [{ type: 'table', name: 'Table' }] };
      el.data = { properties: { name: { type: 'text', label: 'Name' }, note: { type: 'text', label: 'Note' }, source: { type: 'text', label: 'Source' } }, titleProperty: 'name',
        detail: { property: 'entries', kind: 'kind', columns: [{ id: 'kind', label: 'Kind' }, { id: 'src', label: 'Source', link: 'src' }, { id: 'method', label: 'Method', block: true }] },
        rows: [{ id: 'a', name: 'Rack', note: 'short', source: url, entries: [{ kind: 'torque', src: url, method: url }] }] };
      for (let i = 0; i < 100 && !(el.dataset.view && el.querySelector('.dv-status')?.textContent.trim()); i++) await new Promise((r) => setTimeout(r, 100));
      el.openPeek('a');
      await new Promise((r) => setTimeout(r, 200));
      const peek = el.querySelector('.dv-peek'), table = peek.querySelector('.dv-fields');
      const cell = [...peek.querySelectorAll('.dv-fields tr')].find((tr) => tr.textContent.includes('github.com')).querySelector('td');
      const note = [...peek.querySelectorAll('.dv-fields tr')].find((tr) => tr.textContent.includes('short')).querySelector('td');
      const behind = [...peek.querySelectorAll('.dv-entry-line span, .dv-entry p')].map((e) => e.getBoundingClientRect().right);
      return { peekRight: peek.getBoundingClientRect().right, peekClient: peek.clientWidth, scroll: peek.scrollWidth, table: table.getBoundingClientRect().width, behindRight: Math.max(...behind),
        cellRight: cell.getBoundingClientRect().right, cellText: cell.textContent.trim() === url, noteWidth: note.getBoundingClientRect().width };
    }""", url)
    check("peek: a long unbroken value wraps inside the panel (the fields table and the entries behind it stay inside the peek, no sideways scroll, whole text kept)",
          got["table"] <= got["peekClient"] + 1 and got["cellRight"] <= got["peekRight"] + 1 and got["behindRight"] <= got["peekRight"] + 1 and got["scroll"] <= got["peekClient"] + 1 and got["cellText"] and got["noteWidth"] > 20,
          {k: (round(v, 1) if isinstance(v, float) else v) for k, v in got.items()})
    page.context.close()

    # ---- a host's own sidebar made resizable by resize.js alone (CONTRACT §11), measured with getBoundingClientRect
    page = ctx.page("plain/resize.html")
    page.evaluate("localStorage.removeItem('data-ui/panel-width/side')")
    page.reload()
    page.wait_for_selector(".layout > .dv-splitter-right:not([hidden])")
    boxes = """() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
      return { side: r('#side').width, main: r('.layout > main').width, handle: r('.dv-splitter').left + r('.dv-splitter').width / 2, edge: r('#side').right,
        styles: document.querySelectorAll('style[data-ui-resize]').length, core: !!customElements.get('data-views'), y: r('#side').top + 20 }; }"""
    a = page.evaluate(boxes)
    page.mouse.move(a["handle"], a["y"])
    page.mouse.down()
    page.mouse.move(a["handle"] + 100, a["y"], steps=10)
    page.mouse.up()
    b = page.evaluate(boxes)
    page.reload()
    page.wait_for_selector(".layout > .dv-splitter-right:not([hidden])")
    c = page.evaluate(boxes)
    check("plain page: resize.js alone makes a host's [data-resizable] sidebar draggable (+100 px, its neighbour -100 px), remembered across a reload",
          abs(a["handle"] - a["edge"]) <= 1.5 and abs(b["side"] - a["side"] - 100) <= 2 and abs(b["main"] - a["main"] + 100) <= 2 and abs(c["side"] - b["side"]) <= 1
          and a["styles"] == 1 and not a["core"], {"before": round(a["side"]), "dragged": round(b["side"]), "reloaded": round(c["side"]), "core loaded": a["core"]})
    page.context.close()

    # ---- a STICKY sidebar: the page scrolls under it, and the handle must stay on its edge (measured, then dragged
    # there). The Examples page found the gap: the handle used to be re-placed only on a window resize.
    page = ctx.page("plain/resize.html")
    page.evaluate("localStorage.removeItem('data-ui/panel-width/side')")
    page.reload()
    page.wait_for_selector(".layout > .dv-splitter-right:not([hidden])")
    page.add_style_tag(content=".layout { align-items: start; } #side { position: sticky; top: 0; } .layout > main { min-height: 3200px; }")
    self_frames = "() => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)))"
    page.evaluate(self_frames)
    sticky = """() => { const s = document.querySelector('#side').getBoundingClientRect(), h = document.querySelector('.layout > .dv-splitter').getBoundingClientRect();
      return { scrolled: scrollY, edge: s.right, top: s.top, handle: h.left + h.width / 2, handleTop: h.top, height: h.height, side: s.height, width: s.width }; }"""
    page.evaluate("scrollTo(0, 900)")
    page.evaluate(self_frames)
    s1 = page.evaluate(sticky)
    page.mouse.move(s1["handle"], s1["top"] + 20)
    page.mouse.down()
    page.mouse.move(s1["handle"] + 60, s1["top"] + 20, steps=8)
    page.mouse.up()
    s2 = page.evaluate(sticky)
    check("resize: on a sticky sidebar the handle follows the edge after the page scrolls 900 px (re-placed on scroll, not only on resize), and drags +60 px there",
          s1["scrolled"] >= 800 and abs(s1["handle"] - s1["edge"]) <= 1.5 and abs(s1["handleTop"] - s1["top"]) <= 1.5 and abs(s1["height"] - s1["side"]) <= 1.5
          and abs(s2["width"] - s1["width"] - 60) <= 2 and abs(s2["handle"] - s2["edge"]) <= 1.5,
          {"scrollY": s1["scrolled"], "handle-edge": round(s1["handle"] - s1["edge"], 1), "handleTop-top": round(s1["handleTop"] - s1["top"], 1), "dragged": round(s2["width"] - s1["width"])})
    page.context.close()

    # ---- the gallery lists every case folder, grouped by app, and filters by app and view type
    cases = sorted(p.name for p in (ROOT / "gallery" / "examples").iterdir() if (p / "views.base").exists())
    page = ctx.page("gallery/index.html")
    listed = page.locator(".cards .card").count()
    groups = page.locator(".app-group h2").all_inner_texts()
    check("gallery: lists every gallery/examples/* folder, grouped by app", listed == len(cases) and len(groups) >= 6, f"{listed} cards for {len(cases)} folders; {groups}")
    page.click(".chips[data-filter=type] .chip[data-value=graph]")
    graph = page.evaluate("[...document.querySelectorAll('.card:not([hidden]) h3')].map(e => e.textContent)")
    # a view no Vibe Tracks case uses (it has a graph case since vibetracks-decisions), for the "nothing matches" state
    page.click(".chips[data-filter=type] .chip[data-value=map]")
    page.click(".chips[data-filter=app] .chip[data-value='Vibe Tracks']")
    none = page.locator(".card:not([hidden])").count()
    page.click(".chips[data-filter=type] .chip[data-value='']")
    vibe = page.locator(".card:not([hidden])").count()
    # WHY counted from the READMEs, not a literal: each new Vibe Tracks case (the dashboards lane added three) is one more card
    vibe_cases = sum("- **App:** Vibe Tracks" in (ROOT / "gallery" / "examples" / c / "README.md").read_text(encoding="utf-8") for c in cases)
    check("gallery: the view and app filters narrow the cases, say when nothing matches, and land in the URL",
          sorted(graph) == graph_cases() and none == 0 and page.is_visible(".empty-note") is False and vibe == vibe_cases and "app=Vibe+Tracks" in page.url,
          f"graph: {graph}; Vibe Tracks x graph: {none}; Vibe Tracks: {vibe}; {page.url.split('/')[-1]}")
    page.context.close()

    # ---- the views page
    page = ctx.page("views/index.html")
    rows = page.locator("table.views tbody tr").count()
    built = page.locator("table.views .status-built").count()
    built_names = page.locator("table.views tr:has(.status-built) td:first-child b").all_inner_texts()
    check("views: every view in docs/VIEWS.md, with its status", rows == 17 and built >= 2 and {"Table", "Pivot"} <= set(built_names) and len(built_names) == built, f"{rows} views, built: {built_names}")
    page.context.close()


def run_case(ctx: Ctx, case: pathlib.Path):
    spec = importlib.util.spec_from_file_location(f"checks_{case.name.replace('-', '_')}", case / "checks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.run(ctx, f"gallery/{case.name}/index.html")


def every_case(ctx: Ctx):
    """Every case page, light and dark, at 1280 and 390 px: its views draw, the .base and the data sit side by side
    (stacked on a phone), the original UI it replaces is named, and the page never scrolls sideways."""
    for case in sorted(p.name for p in (ROOT / "gallery" / "examples").iterdir() if (p / "views.base").exists()):
        bad = []
        for dark in (False, True):
            for width, mobile in ((1280, False), (390, True)):
                page = ctx.page(f"gallery/{case}/index.html", width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
                page.wait_for_selector("#example[data-view]", timeout=20000)
                got = page.evaluate("""() => {
                  const files = [...document.querySelectorAll('.side-by-side > .file')].map((f) => f.getBoundingClientRect());
                  return { sw: document.scrollingElement.scrollWidth, files: files.length, side: files.length === 2 && Math.abs(files[0].top - files[1].top) < 2,
                    original: (document.querySelector('.original') || {}).textContent || '', bg: getComputedStyle(document.body).backgroundColor,
                    view: document.querySelector('#example .dv-view') ? document.querySelector('#example .dv-view').getBoundingClientRect().height : 0 }; }""")
                ok = got["sw"] <= width and got["files"] == 2 and got["side"] == (width > 1000) and len(got["original"].strip()) > 20 and got["view"] > 100 \
                    and (got["bg"] == "rgb(10, 10, 10)") == dark
                if not ok:
                    bad.append({"dark": dark, "width": width, **{k: v for k, v in got.items() if k != "original"}, "original": got["original"][:40]})
                page.context.close()
        check(f"case page {case}: views drawn, .base beside its data, the UI it replaces named; light and dark, 1280 and 390, no sideways scroll", not bad, bad[:2] or None)


def screenshots(ctx: Ctx):
    pages = [("landing", "index.html"), ("actuators", "gallery/robotparts-actuators/index.html"), ("datasheet", "gallery/gim4305-datasheet/index.html")]
    for name, path in pages:
        for dark in (False, True):
            for width, mobile in ((1280, False), (390, True)):
                page = ctx.page(path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
                scroll = page.evaluate("document.scrollingElement.scrollWidth")
                if width == 390:
                    check(f"{name}, {'dark' if dark else 'light'}, 390 px: no sideways page scroll", scroll <= 390, f"scrollWidth {scroll}")
                ctx.shot(page, f"{name}-{'dark' if dark else 'light'}-{width}")
                page.context.close()
    for name, path in [("gallery-index", "gallery/index.html"), ("views", "views/index.html")]:
        page = ctx.page(path, width=1280)
        ctx.shot(page, f"{name}-light-1280", full=True)
        page.context.close()


def main() -> int:
    if not (SITE / "index.html").exists():
        print("dist/site is not built: npm --prefix ~/data-ui run build")
        return 1
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/index.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = Ctx(browser, base)
            site_checks(ctx)
            for case in sorted((ROOT / "gallery" / "examples").iterdir()):
                if (case / "checks.py").exists():
                    run_case(ctx, case)
            every_case(ctx)
            screenshots(ctx)
            check("nothing loaded from another site", not ctx.foreign, ctx.foreign[:3])
            check("no script errors", not ctx.errors, ctx.errors[:3])
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    (OUT / "checks.json").write_text(json.dumps(checks, indent=1, ensure_ascii=False), encoding="utf-8")
    passed = sum(c["ok"] for c in checks)
    soft = [c["name"] for c in checks if c.get("soft")]
    print(f"{passed}/{len(checks)} browser checks pass; screenshots in {OUT}")
    if soft:
        print(f"{len(soft)} speed budget(s) not enforced: the machine was overloaded (SOFT above): " + "; ".join(soft))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
