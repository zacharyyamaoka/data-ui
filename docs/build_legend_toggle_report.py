"""The interactive-legend review report: a hero clip of the real 8-motor card, before/after stills, the three decisions
and the check counts.

    ~/psu-atlas/.venv/bin/python ~/data-ui/.wt/legend-toggle/docs/build_legend_toggle_report.py [NPM_TEST_LOG]

Captures from the lane's built site (dist/site, after npm run build) in headless Chromium: the sim-to-real case's own
views.base plus the two 8-motor time series cards tests/browser/legend_checks.py adds over its runs.json (real data),
recorded with Playwright's video and cut to the card with ffmpeg (muted mp4 + GIF). Writes the media to
reports/media/legend-toggle/ (gitignored) and reports/data-ui-legend-toggle-2026-10-28.html, a small text page that links
it. Paths are the main checkout's, so the report opens from there whichever worktree built it. The check counts come from
reports/media/legend/legend-checks.json (the lane's run of legend_checks.py) and, when given, the npm test log.
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

LANE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LANE / "tests" / "browser"))
_argv, sys.argv = sys.argv, sys.argv[:1]   # legend_checks reads argv[1] as its output folder at import
import legend_checks as L  # noqa: E402  the same variant .base and oracles as the checks
sys.argv = _argv

REPORTS = pathlib.Path("~/data-ui/reports")
MEDIA = REPORTS / "media" / "legend-toggle"
OUT = REPORTS / "data-ui-legend-toggle-2026-10-28.html"
SITE = LANE / "dist" / "site"
CHECKS = LANE / "reports" / "media" / "legend" / "legend-checks.json"
TS = L.panel("ts8")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def box(page, sel):
    return page.evaluate("(s) => { const r = document.querySelector(s).getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }", sel)


def ydomain(page, sel):
    return page.evaluate("(s) => document.querySelector(s + ' .dv-view').vegaView.scale('y').domain()", sel)


def capture(base):
    MEDIA.mkdir(parents=True, exist_ok=True)
    routes = {f"{base}/gallery/sim-to-real/views.base": L.variant_base()}
    found = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        # ---- stills: all shown, one hidden (the outlier), isolated; the time series card and the type: chart
        page = L.dashboard_page(browser, base, routes)
        ladder = page.evaluate("() => [...document.querySelectorAll('#example .dd-panel')].find((s) => /Model ladder/.test(s.getAttribute('aria-label') || '')).dataset.panel")
        lad = L.panel(ladder)
        lad_err = {m: max(L.cell(x["error"]) for x in L.MODELS if x["motor"] == m and x["family"] != "friction") for m in L.LADDER}
        lad_top, lad_low = max(lad_err, key=lad_err.get), min(lad_err, key=lad_err.get)
        ts_low = min(L.MOTORS, key=lambda m: max(L.twin[m]))
        for sel, name, hide, iso in ((TS, "ts", L.OUTLIER, ts_low), (lad, "chart", lad_top, lad_low)):
            page.locator(sel).scroll_into_view_if_needed()
            L.settle(page, 4)
            y = {"all": ydomain(page, sel)}
            page.locator(sel).screenshot(path=str(MEDIA / f"{name}-all.png"))
            L.key_btn(page, sel, hide).click()
            L.settle(page, 4)
            y["hidden"] = ydomain(page, sel)
            page.locator(sel).screenshot(path=str(MEDIA / f"{name}-hidden.png"))
            page.locator(f"{sel} .dv-legend-reset").click()
            L.settle(page)
            L.key_btn(page, sel, iso).dblclick()
            L.settle(page, 4)
            y["isolated"] = ydomain(page, sel)
            page.locator(sel).screenshot(path=str(MEDIA / f"{name}-isolated.png"))
            L.key_btn(page, sel, iso).dblclick()
            L.settle(page)
            found[name] = {"y": y, "hidden": hide, "isolated": iso}
        found["url"] = page.url.split("#", 1)[1] if "#" in page.url else ""
        page.context.close()

        # ---- the hero: Playwright's video of the whole page, cut to the card with ffmpeg
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="legend-video-"))
        context = browser.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(tmp), record_video_size={"width": 1440, "height": 900})
        context.route(f"{base}/gallery/sim-to-real/views.base", lambda route: route.fulfill(status=200, body=routes[f"{base}/gallery/sim-to-real/views.base"], content_type="text/plain"))
        page = context.new_page()
        born = time.monotonic()   # Playwright's video starts with the page
        page.goto(f"{base}/gallery/sim-to-real/")
        L.ready(page)
        page.evaluate("(s) => { const r = document.querySelector(s).getBoundingClientRect(); window.scrollBy(0, r.top - 120); }", TS)
        L.settle(page, 4)
        t0 = time.monotonic()
        page.wait_for_timeout(1200)
        crop = box(page, TS)
        steps = [("click", L.OUTLIER), ("click", "CAN 15"), ("reset", None), ("dblclick", ts_low), ("dblclick", ts_low), ("alt", "CAN 14"), ("alt", "CAN 14")]
        for what, name in steps:
            if what == "reset":
                page.locator(f"{TS} .dv-legend-reset").click()
            elif what == "dblclick":
                L.key_btn(page, TS, name).dblclick()
            elif what == "alt":
                L.key_btn(page, TS, name).click(modifiers=["Alt"])
            else:
                L.key_btn(page, TS, name).click()
            page.wait_for_timeout(1500)
        lead = time.monotonic() - t0
        start = t0 - born
        video = pathlib.Path(page.video.path())
        context.close()
        browser.close()
    x, y, w, h = (int(round(v)) for v in crop)
    w -= w % 2
    h -= h % 2
    total = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout.strip() or 0)
    # WHY from the page's birth, not back from the end: closing the context adds a tail of unknown length
    start = max(0.0, min(start, total - lead))
    vf = f"crop={w}:{h}:{x}:{y}"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{lead:.2f}", "-i", str(video), "-vf", vf, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", "-movflags", "+faststart", str(MEDIA / "hero.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(MEDIA / "hero.mp4"), "-vf", "fps=8,scale=760:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=none", str(MEDIA / "hero.gif")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.5", "-i", str(MEDIA / "hero.mp4"), "-frames:v", "1", str(MEDIA / "hero-poster.png")], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    (MEDIA / "capture.json").write_text(json.dumps(found, indent=1) + "\n", encoding="utf-8")
    return found


def npm_steps(log: pathlib.Path | None):
    """[(step, result, counts)] from the npm test log: each step's own count line."""
    if not log or not log.exists():
        return []
    text = log.read_text(encoding="utf-8", errors="replace")
    parts = re.split(r"\n== ", "\n" + text)
    counts = {}
    for p in parts[1:]:
        name = p.split(":", 1)[0].strip()
        body = p
        m = re.findall(r"^(\d+)/(\d+) [^\n]*pass", body, re.M)
        unit = re.search(r"^# pass (\d+)\s*\n# fail (\d+)", body, re.M)
        py = re.search(r"^Ran (\d+) tests?", body, re.M)
        if m:
            counts[name] = f"{m[-1][0]}/{m[-1][1]}"
        elif unit:
            counts[name] = f"{unit.group(1)} pass, {unit.group(2)} fail"
        elif py:
            counts[name] = f"{py.group(1)} tests" + (" OK" if re.search(r"^OK", body, re.M) else "")
    summary = re.findall(r"^(ok  |FAIL|skip) ([^:]+): (.*)$", text.split("== summary", 1)[-1], re.M)
    return [(name, res, counts.get(name, "")) for _ok, name, res in summary]


def main():
    log = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/index.html", timeout=1)
                break
            except Exception:  # noqa: BLE001 - not up yet
                time.sleep(0.1)
        found = capture(base)
    finally:
        server.terminate()
        server.wait(timeout=5)
    checks = json.loads(CHECKS.read_text(encoding="utf-8")) if CHECKS.exists() else []
    passed = sum(c["ok"] for c in checks)
    steps = npm_steps(log)
    esc = html.escape
    fmt = lambda d: "[" + ", ".join(f"{v:.3g}" for v in d) + "]"
    rows = "".join(f'<li class="{"ok" if c["ok"] else "bad"}"><b>{"PASS" if c["ok"] else "FAIL"}</b> {esc(c["name"])}</li>' for c in checks)
    npm_rows = "".join(f"<tr><td>{esc(n)}</td><td>{esc(r)}</td><td>{esc(c)}</td></tr>" for n, r, c in steps) or '<tr><td colspan="3">npm test log not given</td></tr>'
    npm_ok = steps and all(r.startswith("pass") for _n, r, _c in steps)
    ts, ch = found["ts"], found["chart"]
    mb = lambda f: (MEDIA / f).stat().st_size / 1e6

    def trio(name, d, label):
        return f"""<div class="trio">
<figure><img src="media/legend-toggle/{name}-all.png" alt="{label}, every series shown"><figcaption>All shown · y {fmt(d['y']['all'])}</figcaption></figure>
<figure><img src="media/legend-toggle/{name}-hidden.png" alt="{label}, {esc(d['hidden'])} hidden"><figcaption>{esc(d['hidden'])} hidden (click) · y {fmt(d['y']['hidden'])}</figcaption></figure>
<figure><img src="media/legend-toggle/{name}-isolated.png" alt="{label}, {esc(d['isolated'])} isolated"><figcaption>{esc(d['isolated'])} isolated (double-click) · y {fmt(d['y']['isolated'])}</figcaption></figure></div>"""

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>data-ui interactive legends</title>
<style>
:root {{ color-scheme: light; --bg: #fff; --fg: #0a0a0a; --muted: #6b6b6b; --card: #fafafa; --border: #e5e5e5; --ok: #15803d; --bad: #dc2626; --accent: #2a78d6; }}
@media (prefers-color-scheme: dark) {{ :root {{ color-scheme: dark; --bg: #0a0a0a; --fg: #fafafa; --muted: #a3a3a3; --card: #141414; --border: #2a2a2a; --ok: #4ade80; --bad: #f87171; --accent: #3987e5; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 1200px; margin: 0 auto; padding: 28px 16px 60px; }}
h1 {{ font-size: 28px; margin: 0 0 8px; }} h2 {{ font-size: 20px; margin: 28px 0 6px; }}
.verdict {{ font-size: 17px; border-left: 4px solid var(--accent); padding: 10px 14px; background: var(--card); border-radius: 0 10px 10px 0; }}
.muted {{ color: var(--muted); }}
video, img {{ max-width: 100%; display: block; border: 1px solid var(--border); border-radius: 10px; background: #fff; }}
.trio {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 10px 0 18px; }}
figure {{ margin: 0; }} figcaption {{ font-size: 12px; color: var(--muted); margin-top: 4px; overflow-wrap: anywhere; }}
.box {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; margin: 10px 0; }}
.checks {{ list-style: none; padding: 0; font-size: 13px; columns: 2; column-gap: 24px; }} .checks li {{ padding: 2px 0; break-inside: avoid; overflow-wrap: anywhere; }}
.checks .ok b {{ color: var(--ok); }} .checks .bad b {{ color: var(--bad); }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; }} td, th {{ text-align: left; border-bottom: 1px solid var(--border); padding: 5px 8px; vertical-align: top; }}
.tablewrap {{ overflow-x: auto; }}
code {{ font-size: .9em; overflow-wrap: anywhere; }}
@media (max-width: 800px) {{ .trio {{ grid-template-columns: minmax(0, 1fr); }} .checks {{ columns: 1; }} }}
</style></head><body><main>
<p class="muted">data-ui · lane/legend-toggle · 2026-10-28 · not merged</p>
<h1>Every chart legend toggles its series</h1>
<p class="verdict"><b>Click a legend entry to hide or show its series; double-click or Alt + click to show only it, again to show all; Reset brings everything back.</b> On by default in every data-ui chart with a series legend (type: chart, both time series cards, trajectory, scene3d, the playback range's overview), with the hidden set in the URL. On <code>lane/legend-toggle</code>, not merged. {passed}/{len(checks)} legend checks pass{'; every npm test step is green' if npm_ok else ''}.</p>

<h2>The 8-motor card, toggled</h2>
<p class="muted">Recorded headlessly from the real sim-to-real dashboard (its runs.json: full-twin RMS per run, one line per motor), the simple time series card. Hide {esc(L.OUTLIER)} (the outlier) and y drops to the rest; hide CAN 15; Reset; double-click {esc(ts['isolated'])} to isolate it and again to restore; Alt + click CAN 14 twice.</p>
<video src="media/legend-toggle/hero.mp4" poster="media/legend-toggle/hero-poster.png" autoplay muted loop playsinline controls></video>
<p class="muted">No video? <a href="media/legend-toggle/hero.gif">The GIF</a> ({mb('hero.gif'):.1f} MB; the mp4 is {mb('hero.mp4'):.2f} MB).</p>

<h2>Before and after</h2>
<p class="muted">The time series card (8 motors, runs.json). The y domain under each is read from Vega's own scale.</p>
{trio('ts', ts, 'Time series card')}
<p class="muted">The case's own <code>type: chart</code> "Model ladder (10-23 runs)": x model, y error (log), colour motor. Vega's colour legend is replaced by the same buttons (before this lane this card drew no colour legend at all on the dashboard).</p>
{trio('chart', ch, 'Model ladder chart')}

<h2>Three decisions</h2>
<div class="box"><ul>
<li><b>Axes:</b> y rescales to the series still shown; x stays put; a quiet Reset appears beside the legend whenever something is hidden. <i>Why:</i> a hidden outlier must not flatten the rest (Plotly's, Grafana's and uPlot's default). Trajectory refits both axes (its equal aspect ties them); scene3d keeps its camera (no y axis).</li>
<li><b>URL format:</b> <code>l=&lt;name&gt;,&lt;name&gt;</code> on a <code>&lt;data-views&gt;</code>, <code>l.&lt;panel&gt;=</code> in a dashboard (beside <code>s.</code> and <code>p.</code>), <code>l.&lt;dashboard&gt;.&lt;panel&gt;=</code> with several dashboards on a page (the clock's key; none with <code>no-url</code>). Each name URI-encoded, so commas, spaces and unicode survive; absent means all shown. Written with replaceState like the rest of the view state; Back / Forward re-apply the set of the entry they land on. This run's last URL: <code>#{esc(found['url'])}</code>. <i>Why replaceState, not a history entry per click:</i> the dashboard's selections, tabs and clock already replace, and a Back that undid legend clicks one by one would trap the reader on the page.</li>
<li><b><code>type: chart</code> approach:</b> Vega's own colour legend is off and the HTML button legend draws instead; the hidden set is a Vega param (<code>dvHidden</code>) that a <code>filter</code> transform on every series layer reads, set with <code>view.signal(...).runAsync()</code>, never a re-embed. An invisible layer, on only while something is hidden, holds every row's x and colour, so x and the colours never move. <i>Why not Vega-Lite's legend-bound selection (the stock path):</i> its legend is canvas, so no buttons, focus, aria-pressed, Tab, Enter or Space; it has no double-click isolate or Reset; and it dims rather than filters, so y would keep the hidden series' range.</li>
</ul></div>

<h2>The seam (docs/CONTRACT.md §31)</h2>
<p>Views get <code>input.hiddenSeries</code> and call <code>host.setHiddenSeries(names)</code>; the element keeps the set (<code>el.hiddenSeries</code>, event <code>data-views-legend</code>) and the URL; the dashboard listens per panel. The rule, the URL codec and the button control are one module, <code>packages/core/src/legend.js</code>; <code>plotkit.js</code> re-exports <code>legendClick</code> so nothing that imported it breaks. A double-click's two clicks never leave a toggle behind: the first click toggles at once, the second isolates from the state before the pair.</p>

<h2>Checks</h2>
<div class="tablewrap"><table><tr><th>npm test step</th><th>Result</th><th>Count</th></tr>{npm_rows}</table></div>
<p class="muted"><code>tests/browser/legend_checks.py</code> ({passed}/{len(checks)}), red first: before the views were wired, 5 of 19 passed, every legend button check failing for want of a button. <code>tests/unit/legend.test.mjs</code> (8 tests) failed on the missing module, then on the dashboard hash not carrying <code>l.</code>.</p>
<ul class="checks">{rows}</ul>
</main></body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(OUT, f"{OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
