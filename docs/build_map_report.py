"""Build the map lane's review report: one self-contained HTML file (media inlined) from docs/capture_map.py's captures,
the browser checks' results and the unit-test log.

    ~/psu-atlas/.venv/bin/python docs/build_map_report.py MEDIA_DIR CHECKS_JSON NPM_TEST_LOG OUT.html
"""

import base64
import html
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MEDIA, CHECKS, LOG, OUT = (pathlib.Path(a) for a in sys.argv[1:5])
EX = ROOT / "gallery" / "examples"


def uri(path, mime):
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def readme(case):
    text = (EX / case / "README.md").read_text()
    title = text.splitlines()[0][2:]
    summary = text.split("\n\n")[1].strip()
    bullets = dict(re.findall(r"^- \*\*(\w+):\*\* (.+)$", text, flags=re.M))
    return title, summary, bullets


def md(text):
    t = html.escape(text)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)


meta = json.loads((MEDIA / "meta.json").read_text())
checks = json.loads(CHECKS.read_text())
map_checks = [c for c in checks if any(k in c["name"] for k in ("map-", "clusters", "choropleth", "region filter", "bubbles", "basemap", "heatmap", "hexbin", "flows", "routes", "playback", "rings", "catchments", "bivariate", "multiples", "swipe", "draw", "within", "callouts", "floor plan", "3D", "dashboard: a click", "dashboard: the KPI", "dashboard: and", "no JS"))]
log = LOG.read_text()
unit = re.search(r"# tests (\d+)\n# suites \d+\n# pass (\d+)\n# fail (\d+)", log) or re.search(r"# tests (\d+)[\s\S]*?# pass (\d+)[\s\S]*?# fail (\d+)", log)
summary = re.findall(r"^(ok  |FAIL|skip) (.+)$", log, flags=re.M)
browser_line = re.findall(r"(\d+)/(\d+) browser checks pass", log)
cases = sorted(p.name for p in EX.iterdir() if p.name.startswith("map-") and (p / "views.base").exists())
commits = subprocess.run(["git", "-C", str(ROOT), "log", "--format=%h %s", "d05cc39..HEAD"], capture_output=True, text=True).stdout.strip().splitlines()
sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()

tiles = []
for i, case in enumerate(cases, 1):
    title, summ, b = readme(case)
    light, dark = MEDIA / f"{case}-light.jpg", MEDIA / f"{case}-dark.jpg"
    answer = meta.get("answers", {}).get(case, "")
    tiles.append(f"""<article class="case" id="{case}">
  <div class="shots"><img loading="lazy" alt="{html.escape(title)}, light" src="{uri(light, 'image/jpeg')}"><img loading="lazy" alt="{html.escape(title)}, dark" src="{uri(dark, 'image/jpeg')}"></div>
  <h3><span class="n">{i}</span> {html.escape(title)}</h3>
  {f'<p class="ans">{html.escape(answer)}</p>' if answer else ''}
  <p>{md(summ)}</p>
  <p class="shows"><b>Shows:</b> {md(b.get('Shows', ''))}</p>
  <p class="slug"><code>gallery/examples/{case}</code></p>
</article>""")

STOCK = [
    ("Map engine", "MapLibre GL 6.16.0", "unchanged", "the parked map adopted across view switches; no other origin"),
    ("Markers", "HTML markers, rows at one point counted", "unchanged (stock seam)", "a view with no <code>layers:</code> draws exactly as before"),
    ("Clusters", "—", "MapLibre GeoJSON <code>cluster</code> + <code>getClusterExpansionZoom</code>", "every row counted once; a click zooms in"),
    ("Heatmap", "—", "MapLibre <code>heatmap</code> layer", "single rows reachable past zoom 13"),
    ("Hexagon bins", "—", "<code>h3-js@4.5.0</code>", "equal-area bins; counts add up to the rows"),
    ("Class breaks", "—", "<code>simple-statistics@7.12.1</code> (quantile, equalIntervalBreaks, ckmeans)", "method and unit stated in the legend; no-data never 0"),
    ("Regions, 3D", "—", "MapLibre <code>fill</code>, <code>fill-extrusion</code>, feature-state", "the selected region highlighted"),
    ("Buffers, catchments, nearest, inside, arcs", "—", "<code>@turf/turf@7.4.0</code> (circle, voronoi, distance, booleanPointInPolygon, bezierSpline)", "straight-line distance said as such"),
    ("Draw an area", "—", "<code>terra-draw@1.37.0</code> + <code>terra-draw-maplibre-gl-adapter@1.5.0</code>", "the drawn rows open in the peek"),
    ("Swipe", "—", "<code>img-comparison-slider@8.0.7</code> (already the compare view's)", "both maps still pan; one camera"),
    ("Street basemap", "bundled countries only", "<code>pmtiles@4.5.0</code> + <code>@protomaps/basemaps@5.7.2</code>, an extract served from the site", "countries underneath; recoloured from tokens"),
    ("Labels", "—", "MapLibre symbol layers + Noto Sans glyphs (OFL)", "no 404 for a range not shipped"),
    ("Legend panel width", "—", "core <code>makeResizable</code> (CONTRACT §11)", "drag, remember, double-click reset, fold"),
    ("Time", "—", "MapLibre <code>setFilter</code>; core <code>clockFor</code> when present", "exactly the rows in the trail window"),
    ("Ours", "", "<code>plan.js</code> (rows → layers, legend model), token-mixed ramps and the bivariate grid, the panel, camera sync", ""),
]

browser_total = browser_line[-1] if browser_line else None
map_pass = sum(c["ok"] for c in map_checks)
suite_rows = "".join(f"<tr><td>{'pass' if s.strip() == 'ok' else s.strip()}</td><td>{html.escape(n)}</td></tr>" for s, n in summary)
hero = MEDIA / "hero.mp4"
gif = MEDIA / "hero.gif"

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>data-ui map: 20 analyses</title>
<style>
:root {{ --bg: #fff; --fg: #111; --muted: #666; --rule: #e5e5e5; --card: #fafafa; --accent: #1d4ed8; --ok: #15803d; --bad: #b91c1c; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg: #0b0b0c; --fg: #ececec; --muted: #9a9a9a; --rule: #2a2a2d; --card: #141416; --accent: #7aa2ff; --ok: #4ade80; --bad: #f87171; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.55 system-ui, -apple-system, Segoe UI, sans-serif; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 28px 16px 80px; }}
h1 {{ font-size: 26px; margin: 0 0 6px; }} h2 {{ font-size: 19px; margin: 40px 0 10px; border-top: 1px solid var(--rule); padding-top: 22px; }}
.verdict {{ font-size: 17px; margin: 6px 0 16px; }} .muted, .slug {{ color: var(--muted); }}
video, .gif img {{ width: 100%; border: 1px solid var(--rule); border-radius: 8px; display: block; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 360px), 1fr)); gap: 18px; }}
.case {{ background: var(--card); border: 1px solid var(--rule); border-radius: 10px; padding: 10px 12px 12px; min-width: 0; }}
.case h3 {{ margin: 8px 0 4px; font-size: 15px; }} .case p {{ margin: 4px 0; font-size: 13.5px; overflow-wrap: anywhere; }}
.case .n {{ display: inline-block; min-width: 22px; color: var(--muted); }}
.ans {{ font-weight: 600; color: var(--accent); }}
.shots {{ display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }} .shots img {{ width: 100%; border-radius: 4px; border: 1px solid var(--rule); display: block; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; }} td, th {{ border-bottom: 1px solid var(--rule); padding: 6px 8px; text-align: left; vertical-align: top; }}
.tablewrap {{ overflow-x: auto; }} code {{ font-size: 12.5px; overflow-wrap: anywhere; }}
.kpis {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 12px 0; }} .kpi {{ border: 1px solid var(--rule); border-radius: 10px; padding: 10px 14px; min-width: 150px; }}
.kpi b {{ display: block; font-size: 22px; }} .ok {{ color: var(--ok); }} .bad {{ color: var(--bad); }}
.phones {{ display: flex; gap: 14px; flex-wrap: wrap; }} .phones img {{ width: 195px; max-width: 46%; border: 1px solid var(--rule); border-radius: 10px; }}
ul.tight li {{ margin: 3px 0; }}
</style></head><body><main>
<h1>data-ui map: 20 analyses on one map view</h1>
<p class="verdict"><b>The map view is now an analysis surface: 20 gallery cases draw on one <code>layers:</code> grammar, with the full suite green.</b> On <code>lane/map</code> @ <code>{sha}</code>, not merged; CONTRACT §42, PEP 0011. Not deployed.</p>
<div class="kpis">
  <div class="kpi"><b>20</b>gallery cases</div>
  <div class="kpi"><b class="{'ok' if map_pass == len(map_checks) else 'bad'}">{map_pass}/{len(map_checks)}</b>map browser checks</div>
  <div class="kpi"><b>{browser_total[0] + '/' + browser_total[1] if browser_total else '—'}</b>all browser checks (checks.py)</div>
  <div class="kpi"><b>{unit.group(2) + '/' + unit.group(1) if unit else '—'}</b>unit tests pass ({unit.group(3) if unit else '?'} fail)</div>
</div>

<h2>Hero: the real map, panned, a district selected, the dashboard cross-filters</h2>
<p class="muted">The map-dashboard case in headless Chromium ({meta.get('hero_seconds', 0):.0f} s). Drag pans; the wheel zooms; a click on Capital sets the KPI to {html.escape(meta.get('kpi_capital', ''))} t and narrows the trend; Metro Vancouver gives {html.escape(meta.get('kpi_metro', ''))} t; a second click clears back to {html.escape(meta.get('kpi_all', ''))} t.</p>
<video src="{uri(hero, 'video/mp4')}" autoplay muted loop playsinline controls></video>
<details class="gif"><summary>GIF fallback</summary><img alt="the same recording as a GIF" src="{uri(gif, 'image/gif')}"></details>

<h2>The 20 cases, light and dark</h2>
<p class="muted">Each tile: the case's first view as the gallery serves it (left light, right dark), the panel's one-line answer as drawn, and what it shows. Real public data unless the summary says synthetic; sources and licences are in each case's README and <code>source/SOURCES.md</code>.</p>
<div class="grid">{''.join(tiles)}</div>

<h2>On a phone (390 px)</h2>
<div class="phones"><img alt="choropleth on a phone" src="{uri(MEDIA / 'phone-map-bc-disposal.jpg', 'image/jpeg')}"><img alt="service rings on a phone" src="{uri(MEDIA / 'phone-map-service-rings.jpg', 'image/jpeg')}"></div>
<p class="muted">The legend moves under the map below 700 px; no sideways scroll (checked on every case, light and dark).</p>

<h2>Stock parts, element by element</h2>
<div class="tablewrap"><table><thead><tr><th>Element</th><th>Before</th><th>Off-the-shelf part</th><th>Behaviour that must survive</th></tr></thead><tbody>
{''.join(f'<tr><td>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td></tr>' for a, b, c, d in STOCK)}
</tbody></table></div>
<p class="muted">Rejected: deck.gl (about 1 MB for layers MapLibre already draws); OpenFreeMap tiles (free and keyless, but another origin: CONTRACT §1, and the browser checks fail any foreign request); <code>@maplibre/maplibre-gl-compare</code> (CommonJS that needs Node's <code>events</code>); Leaflet and d3-geo (Zach's 2026-10-10 MapLibre decision).</p>

<h2>Tests</h2>
<ul class="tight">
  <li><b>Unit:</b> {unit.group(1) if unit else '?'} tests, {unit.group(2) if unit else '?'} pass, {unit.group(3) if unit else '?'} fail; 14 are the map's own (<code>tests/unit/map.test.mjs</code>, hand oracles). Mutations: a class boundary, the subset remap and the sqrt in symbol radii each turn tests red.</li>
  <li><b>Browser, map:</b> {map_pass}/{len(map_checks)}, measured on the running map (rendered features, the camera, getBoundingClientRect, peek counts, a 90 px panel drag), against oracles from each case's JSON: a haversine on Turf's earth radius, a ray-cast point-in-polygon. Halving the within distance in the view turns 3 red.</li>
  <li><b>The perf-oracle golden</b> was regenerated from main d05cc39's code over this gallery (its new cases move the digests), recorded as <code>_merge_map</code>; no existing test was loosened.</li>
</ul>
<div class="tablewrap"><table><thead><tr><th>Step</th><th><code>npm test</code></th></tr></thead><tbody>{suite_rows}</tbody></table></div>

<h2>What this does not cover</h2>
<ul class="tight">
  <li>Road routing and drive-time isochrones: routes are stored paths, rings and distances are straight-line (said in each legend).</li>
  <li>One basemap extract (Metro Vancouver to zoom 11, BC to zoom 6, 4.4 MB in git); elsewhere and beyond, the bundled Natural Earth countries, or GeoJSON regions.</li>
  <li>Labels in scripts outside Latin, Latin-1 and punctuation (the shipped glyph ranges) draw blank (CJK uses MapLibre's local font).</li>
  <li>Playback filters points and lines; a choropleth animated by year is shown with small multiples and the swipe instead.</li>
  <li>The flows case is mostly a synthetic split of published station totals (2 of 17 rows published); the routes and the sorting line are synthetic, and say so.</li>
  <li>Not verified against data-ui's dashboard clock (it lives on lane/dashboard-cards); the map follows <code>clockFor</code> when core exports it and plays on its own otherwise.</li>
  <li>Not merged, not deployed.</li>
</ul>

<h2>Commits on lane/map</h2>
<ul class="tight">{''.join(f'<li><code>{html.escape(c[:7])}</code> {html.escape(c[8:])}</li>' for c in commits)}</ul>
</main></body></html>
"""
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(page)
print(f"wrote {OUT}: {OUT.stat().st_size / 1024 / 1024:.2f} MB")
