"""Build the dashboards report: reports/data-ui-dashboards-2026-10-26.html in the MAIN checkout, its media in
reports/media/dashboards/ (written by docs/capture_dashboards.py). Self-contained except for that media folder.

    python3 docs/build_dashboards_report.py ~/data-ui/reports/data-ui-dashboards-2026-10-26.html CHECKS.json

CHECKS.json is the browser run's checks.json (tests/browser/checks.py writes it); the unit counts are passed in it
under "unit" by the caller when known."""

import html
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(sys.argv[1])
CHECKS = json.loads(pathlib.Path(sys.argv[2]).read_text()) if len(sys.argv) > 2 else {}
M = "media/dashboards"
E = html.escape

CASES = [
    ("vibetracks-dashboard", "Vibe Tracks · track overview", "Every real track, its headline KPI with history, the check runs rolled up through child tracks, the newest runs. Three linked datasets, one rail."),
    ("vibetracks-runs", "Vibe Tracks · run explorer", "The run as the atomic record: ratio-of-sums cards, every run over time, a leaderboard that is the tree's roll-up, and table / pivot / grouped table as tabs."),
    ("vibetracks-track", "Vibe Tracks · one track", "A track's own page: the rail's Track picker is the dashboard variable; cards, history, runs and points follow. Opens on Vibe Tracks itself."),
    ("pid-tuning", "PID tuning results", "pidtuna's factory → analytic → tuned → oracle ladder on nine simulated robots (illustrative), gains against error, and the one real sim-vs-rack check."),
    ("sim-to-real", "Sim-to-real · rack motor twins", "Eight real motors: twin error against the floor, the model ladders on their two rulers, error run by run, improvement rounds, every model-card term."),
    ("trajectory-tracking", "Trajectory tracking", "Real runs against two twins per motor and speed, the 10-09 target-vs-sim study (real slots “not requested”, never 0), and links to traj_compare's own reports."),
]

STOCK = [
    ("Home track rows (Calm Rows, hierarchy, fold chevron)", "<code>home/static/views.js</code>, <code>cards.js</code>", "a <code>type: table</code> panel with <code>tree: {parent}</code>", "the hierarchy; fold a parent; health and state as calm badges"),
    ("KPI tiles and the headline's progress chart", "<code>kpi-panel.js</code> (<code>VT.ui.kpiTile</code>), <code>kpi-chart.js</code> (<code>&lt;vt-kpi-progress&gt;</code>, ECharts)", "<code>type: kpi</code> (<code>&lt;data-kpi&gt;</code>, <code>&lt;data-sparkline&gt;</code>); history as a <code>type: chart</code> (Vega-Lite)", "the producer's number, never recomputed; basis badge; “computed from N runs”; delta coloured by <code>better</code>, not by sign; hollow estimates"),
    ("Parent roll-up", "<code>vt state</code>'s <code>rollup</code> (state-word counts, waiting, worked time)", "a dataset <code>rollup:</code> (Sum / Ratio of the newest run per suite, through the tree)", "a parent shows its children's numbers, labelled derived with n and how; vt state keeps computing state words (not replaced)"),
    ("Results pivot", "FINOS Perspective (PEP 0006), <code>pivot.js</code>", "<code>type: pivot</code> (TanStack) and grouped tables as a panel's tabs", "group-by tree, sort by value, the records behind a cell in the peek; ratio-of-sums cells need pivot <code>Ratio</code> (gap)"),
    ("One filter for the page", "per-view toolbars; the sidebar's track selection", "a <code>&lt;data-facets&gt;</code> per dataset, joined by <code>links:</code>; a <code>select</code> facet as the dashboard variable", "every panel agrees; disjunctive counts; the state in a shareable URL"),
    ("Click a chart to narrow the rest", "none (each chart was its own island)", "a view's <code>select:</code> (Superset/Mosaic cross-filter), chips to clear", "the emitting panel keeps its rows; every other panel narrows through the links"),
    ("Side-peek drill-down", "<code>VT.peek</code> (PEP 0006)", "the dashboard's one drill peek (a <code>&lt;data-views&gt;</code> peek)", "right edge, full height, resizable and remembered, Esc closes; breadcrumb stack and expand-to-page not yet (gap)"),
    ("Hover cards on chart marks", "Fusion-style entity cards from facet catalogs", "the chart view's hover card (<code>hover: {title, fields, image}</code>)", "title, values with units and basis; entity catalog cards (summary, image, page) are a gap"),
    ("Agents tab, sessions, sync, custom HTML tabs", "the app's own chrome", "unchanged (stock seam)", "data-ui draws data, not app chrome; custom tabs stay sandboxed iframes"),
]

GAPS = {
    "Vibe Tracks": [
        "Breadcrumb drill stack and expand-to-full-page (PEP 0006): the dashboard peek opens one level. lane/open-modes is building expand/side/link modes on <code>&lt;data-views&gt;</code>; the dashboard's drill will inherit them.",
        "Pivot <code>Ratio</code> (<code>value.per</code>) is in CONTRACT §5 but not in grammar.js's pivot, so the runs pivot shows Sum / Average; roll-ups and KPI cards do compute Σ/Σ.",
        "No time bucketing (week, month) for a pivot's columns or a chart's x: a producer has to write the bucket column.",
        "<code>bench_version</code> separators and the oracle ceiling from data: <code>guides:</code> takes constants, not a per-series value.",
        "A filter on a linked dataset keeps only the rows on the link column, not their ancestors in a tree (a parent with no runs of its own drops out of the leaderboard when the runs are filtered).",
        "KPI deltas print float noise (<code>+0.1483999…</code>): the kpi view formats the delta with no precision. lane/models-views has a <code>delta.js</code> in flight. A <code>decimals</code> hint pads integers (<code>195.0000</code>), so there is no per-value significant-digits option either.",
        "Live updating: <code>reload()</code> re-reads the files, but nothing watches them or receives a push from <code>vt serve</code>.",
        "The test-history grid (PEP 0012, tests × commits): the producer's <code>history_grid.json</code> is not on disk for any track, so nothing to draw yet; a pivot over it would serve.",
    ],
    "PID tuning": [
        "Overshoot and settling time do not exist in either source: pidtuna scores stop p90, tracking RMS, max error and ringing.",
        "Time-series overlays (step responses per rung, the tapes in pidtuna's JSON) across rows: the chart view draws one dataset's rows, not a curve stored inside a row.",
        "Video panels for the MuJoCo replays: cards can show images; there is no video panel.",
        "Mixed units on one axis (mrad joints, mm belt axes): a unit is per cell, and a chart cannot split its axis by unit; the text panel says so.",
    ],
    "Sim-to-real": [
        "Two rulers (10-23 budget runs, 10-24 held-out dataset) must sit in two charts; there is no per-series “ruler” annotation.",
        "Model-fit figures and the report's video stay in the motor-models report; an image/video panel would bring them in.",
        "The rounds' metrics differ round to round, so only the held-out-median rounds are charted.",
    ],
    "Trajectory tracking": [
        "Target / sim / real curves overlaid on one time axis: traj_compare draws them; data-ui has no time-series overlay of stored arrays.",
        "Embedding traj_compare's HTML as a panel (an iframe panel type); a browser won't open <code>file://</code> links from an http page, so the reports table lists their paths.",
        "The 10-09 study's real slots were never run (“no rack board commissioned”): shown as missing with that reason.",
    ],
    "The dashboard itself": [
        "Drag-to-arrange panels (gridstack.js is the part to take); today the file is the editor.",
        "Text panels with live numbers in them (Evidence's inline values).",
        "Copy the whole dashboard as a <code>.base</code> from the page (each panel's ⋯ copies its own view).",
        "A full-screen button per panel.",
        "Obsidian at runtime with the new keys (the reader's code says it keeps unknown keys; not opened headlessly here).",
        "The Python checker (<code>tools/check_views.py</code>) knows the new keys from the schema but not the <code>from:</code> and link rules; the Node checker does.",
    ],
}


def base_text(case):
    return (ROOT / "gallery" / "examples" / case / "views.base").read_text(encoding="utf-8")


def summary():
    rows = CHECKS.get("browser") or []
    dash = [c for c in rows if any(c["name"].startswith(p) for p in ("dashboard", "run explorer", "one track", "pid", "sim-to-real", "trajectory", "vibetracks-runs", "vibetracks-track", "pid-tuning"))]
    return {"browser_pass": sum(c["ok"] for c in rows), "browser_total": len(rows), "dash_pass": sum(c["ok"] for c in dash), "dash_total": len(dash),
            "unit": CHECKS.get("unit", "")}


def main():
    s = summary()
    cases = []
    for slug, title, blurb in CASES:
        cases.append(f"""
<section class="case" id="{slug}">
  <h3>{E(title)}</h3>
  <p class="muted">{E(blurb)}</p>
  <div class="shot-tabs" role="tablist"><button class="on" data-mode="light">Light</button><button data-mode="dark">Dark</button></div>
  <div class="pair">
    <figure class="shot"><a href="{M}/{slug}-light.jpg" class="light"><img src="{M}/{slug}-light.jpg" alt="{E(title)}, light" loading="lazy"></a><a href="{M}/{slug}-dark.jpg" class="dark" hidden><img src="{M}/{slug}-dark.jpg" alt="{E(title)}, dark" loading="lazy"></a>
      <figcaption>The real <code>&lt;data-dashboard&gt;</code> at 1440 px on <code>gallery/examples/{slug}/</code>. Click to open full size.</figcaption></figure>
    <div class="file"><div class="file-bar"><code>gallery/examples/{slug}/views.base</code></div><pre>{E(base_text(slug))}</pre></div>
  </div>
</section>""")
    stock = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in STOCK)
    gaps = "".join(f"<h3>{E(k)}</h3><ul>{''.join(f'<li>{g}</li>' for g in v)}</ul>" for k, v in GAPS.items())
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>data-ui dashboards</title>
<style>
:root {{ --bg:#fff; --fg:#18181b; --muted:#5f5f6b; --line:#e4e4e7; --sub:#f6f6f7; --accent:#2563eb; --good:#1f7a45; --warn:#9a5b00; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#111113; --fg:#ececef; --muted:#a1a1aa; --line:#2a2a2e; --sub:#1b1b1f; --accent:#7aa7ff; --good:#6fbf8b; --warn:#e0a640; }} }}
:root[data-theme="dark"] {{ --bg:#111113; --fg:#ececef; --muted:#a1a1aa; --line:#2a2a2e; --sub:#1b1b1f; --accent:#7aa7ff; --good:#6fbf8b; --warn:#e0a640; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
main {{ max-width:1880px; margin:0 auto; padding:28px 24px 80px; }}
.narrow {{ max-width:1000px; }}
h1 {{ font-size:28px; margin:0 0 6px; letter-spacing:-.01em; }} h2 {{ font-size:21px; margin:44px 0 10px; padding-top:12px; border-top:1px solid var(--line); }} h3 {{ font-size:16px; margin:26px 0 6px; }}
.verdict {{ font-size:18px; margin:8px 0 14px; }} .muted {{ color:var(--muted); }} code {{ font:12.5px ui-monospace,Menlo,Consolas,monospace; background:var(--sub); padding:1px 4px; border-radius:4px; }}
ul {{ padding-left:20px; }} li {{ margin:3px 0; }} a {{ color:var(--accent); }}
.hero video, .hero img {{ width:100%; max-width:1280px; border:1px solid var(--line); border-radius:8px; display:block; }}
.pair {{ display:grid; grid-template-columns:minmax(0,1.9fr) minmax(0,1fr); gap:16px; align-items:start; }}
.shot img {{ width:100%; border:1px solid var(--line); border-radius:8px; display:block; }} figure {{ margin:0; }} figcaption {{ color:var(--muted); font-size:13px; margin-top:4px; }}
.file {{ border:1px solid var(--line); border-radius:8px; overflow:hidden; position:sticky; top:12px; }} .file-bar {{ padding:6px 10px; background:var(--sub); border-bottom:1px solid var(--line); }}
.file pre {{ margin:0; padding:10px 12px; font:12px/1.45 ui-monospace,Menlo,Consolas,monospace; max-height:calc(100vh - 80px); overflow:auto; white-space:pre; }}
.shot-tabs button {{ font:inherit; font-size:13px; padding:3px 12px; border:1px solid var(--line); background:var(--bg); color:var(--muted); border-radius:999px; cursor:pointer; margin:0 4px 8px 0; }}
.shot-tabs button.on {{ color:var(--fg); background:var(--sub); font-weight:600; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }} th, td {{ text-align:left; vertical-align:top; padding:7px 9px; border-bottom:1px solid var(--line); }} th {{ background:var(--sub); }}
.tablewrap {{ overflow-x:auto; }}
.kv {{ display:grid; grid-template-columns:max-content 1fr; gap:4px 18px; }} .kv b {{ font-weight:600; }}
.ok {{ color:var(--good); font-weight:600; }}
.toc {{ display:flex; flex-wrap:wrap; gap:4px 14px; }} .toc a {{ white-space:nowrap; }}
.phone {{ display:grid; grid-template-columns:260px 1fr; gap:20px; align-items:start; }} .phone img {{ width:260px; border:1px solid var(--line); border-radius:12px; }}
@media (max-width: 1100px) {{ .pair, .phone {{ grid-template-columns:minmax(0,1fr); }} .file {{ position:static; }} }}
</style></head><body><main>
<h1>data-ui dashboards</h1>
<p class="verdict"><b>data-ui can now draw a dashboard from one <code>.base</code> file.</b> Each dashboard places several views and KPI cards on a grid over linked datasets, with one rail for all of them, click-to-cross-filter, roll-ups through a tree, and the whole state in the URL. Six real-data dashboards are rebuilt on it: three for Vibe Tracks, plus PID tuning, sim-to-real and trajectory tracking. The work is <b>on <code>lane/dashboards</code>, not merged</b>. Vibe Tracks' live app is untouched; these dashboards are gallery cases, not yet wired into it.</p>
<p class="muted">Checks: {s['dash_pass']}/{s['dash_total']} dashboard browser checks and {s['browser_pass']}/{s['browser_total']} browser checks overall; {E(str(s['unit']))}. Every expected number is computed by the check from the case's JSON, never read from the page.</p>
<p class="toc"><a href="#hero">Hero</a><a href="#grammar">The grammar</a><a href="#surfaces">The six dashboards</a><a href="#stock">Stock parts</a><a href="#gaps">Gap list</a><a href="#decide">Decisions</a></p>

<h2 id="hero">The real Vibe Tracks dashboard: filter, cross-filter, drill (17 s)</h2>
<div class="hero"><video src="{M}/hero.mp4" autoplay muted loop playsinline controls poster="{M}/vibetracks-dashboard-light.jpg"></video></div>
<p class="muted">Recorded headless from <code>gallery/vibetracks-dashboard/</code> on the built site:</p>
<ul class="muted">
<li>tick <i>health = green</i> in the rail: Tracks shows 11 of 18, and the runs and KPI cards narrow through their links;</li>
<li>click the <i>Vibe Tracks</i> bar in the chart: every other panel narrows to that track, while the chart keeps all 86 runs;</li>
<li>click a run: the dashboard's one side peek opens at the right edge.</li>
</ul>
<p class="muted">No video? <a href="{M}/hero.gif">GIF fallback</a>.</p>

<section class="narrow">
<h2 id="grammar">The grammar: <code>layout:</code> inside the <code>.base</code></h2>
<p>A panel is an ordinary <code>views:</code> entry, so every view type, menu, the checker and ⋯ Copy as <code>.base</code> work on it unchanged. Five keys are new:</p>
<ul>
<li><code>datasets:</code> names the data files.</li>
<li><code>links:</code> says how their rows relate.</li>
<li><code>layout.panels</code> places views (tabs inside a panel when it lists several) and markdown text on a 12-column grid.</li>
<li><code>from:</code> on a view picks its dataset.</li>
<li><code>select:</code> on a view makes a click on it filter the rest.</li>
</ul>
<p>Obsidian opens the same file and shows the panels as tabs. Weighted criteria picked it: 96 against 68 for a separate <code>.dashboard</code> file (Grafana and W&amp;B style), 66 for markdown with <code>```base</code> fences (Evidence, Observable, Quarto), and 49 for hand-placed elements. The full PEP is <code>docs/peps/0004-dashboards.md</code>, and the contract is CONTRACT §17.</p>
<div class="kv">
<b>Links</b><span>semi-joins, never new columns: they reach each panel as an ordinary Bases filter on the link column, visible in that panel's Filter menu (CONTRACT §10's “no join” still holds)</span>
<b>Cross-filter</b><span>Superset's and Mosaic's rule: the emitting panel ignores its own selection; chips above the grid clear it</span>
<b>Roll-ups</b><span><code>rollup: {{from, latest, values}}</code> on a dataset, summed through its <code>tree:</code>, drawn as derived cells (“Sum of passed over 3 newest runs of this row and its 9 children · from rows”). The independent check: BAM Robotics = 855 of 859, computed in Python</span>
<b>Layout engine</b><span>CSS grid alone (0 bytes); reflows to one column under 900 px. gridstack.js stays the part to take if drag-to-arrange is wanted</span>
<b>Bytes</b><span><code>dist/dashboard.js</code> 25 KB, about 10 KB gzipped, loaded only by a page with a dashboard; no new dependency</span>
<b>Side panels</b><span>the rail drags and remembers its width (measured: +80 px drag = +80 px, kept after reload); the drill peek has its own handle</span>
</div>
<h3>On a phone (390 px)</h3>
<div class="phone"><img src="{M}/phone.jpg" alt="The track overview at 390 px"><p class="muted">The panels stack into one column and the rail becomes a closed disclosure. Measured on all six cases, light and dark: page scrollWidth ≤ 390, and every panel is as wide as the grid.</p></div>
</section>

<h2 id="surfaces">The six dashboards, each beside its file</h2>
{''.join(cases)}

<section class="narrow">
<h2 id="stock">Stock parts: Vibe Tracks today → data-ui</h2>
<div class="tablewrap"><table><thead><tr><th>Element</th><th>Today in Vibe Tracks</th><th>data-ui part</th><th>Behaviour that must survive</th></tr></thead><tbody>{stock}</tbody></table></div>

<h2 id="gaps">Gap list: what data-ui still can't do for each surface</h2>
{gaps}

<h2 id="decide">Done, left, and what needs you</h2>
<h3>Done and proved</h3>
<ul>
<li><code>&lt;data-dashboard&gt;</code> and its model (<code>packages/dashboard/</code>), with 14 unit tests. Two mutation runs (breaking exclude-self, breaking Ratio) turn the tests red.</li>
<li>The Node checker knows the dashboard keys: a wrong dataset, view, link column or roll-up property gets a line-numbered error. It caught a comma inside a view name and two panels mixing datasets in my own files.</li>
<li>Six real-data gallery cases, each with browser checks that measure the page: the rail filters every panel, a click on a chart bar cross-filters, a roll-up equals the independent value, the URL round-trips, there is no sideways scroll at 390 px, and light and dark both pass.</li>
</ul>
<h3>Needs you (each with my default if you say nothing)</h3>
<ul>
<li><b>Merge <code>lane/dashboards</code>?</b> It touches shared files in small seams:
  <ul>
  <li><code>build.mjs</code>: one entry;</li>
  <li><code>site/build-site.mjs</code>: the case page renders <code>&lt;data-dashboard&gt;</code>;</li>
  <li><code>site/site.js</code>: one lazy import;</li>
  <li><code>check.js</code> and the schema: additive.</li>
  </ul>
  Expect textual conflicts with lane/frame, lane/toolbar-mix and lane/open-modes in those files. <i>Default: it waits for you; I merge nothing.</i></li>
<li><b>Wire Vibe Tracks' own page to these dashboards?</b> That means vendoring <code>dist/</code> into <code>vibetracks/home/static/vendor/</code> and replacing the home's KPI section with the track-overview dashboard. <i>Default: not started; the live app was untouched by this lane, as asked.</i></li>
<li><b>Public-safety of the rack data.</b> I treated motor-twin errors and pidtuna's sim results as public-safe gallery data (data-ui has no remote). Grasping is the only track whose figures are left out. <i>Default: keep it so; say if the rack numbers should leave the gallery too.</i></li>
</ul>
<h3>Deliberately not done</h3>
<ul>
<li>No changes inside <code>&lt;data-views&gt;</code>, the views or the toolbar (peer lanes own them). The dashboard drives panels only through their public surface.</li>
<li>No audit was run (you didn't ask). Worth a <code>/llm-judge</code>: the semi-join and roll-up semantics are a new contract other apps will build on.</li>
<li>No join that adds columns, no formulas, no DuckDB: links filter, and producers compute.</li>
</ul>
</section>
</main>
<script>
document.querySelectorAll('.case').forEach((c) => c.querySelectorAll('.shot-tabs button').forEach((b) => b.addEventListener('click', () => {{
  c.querySelectorAll('.shot-tabs button').forEach((x) => x.classList.toggle('on', x === b));
  c.querySelector('a.light').hidden = b.dataset.mode !== 'light'; c.querySelector('a.dark').hidden = b.dataset.mode !== 'dark';
}})));
</script>
</body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT} ({len(page) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
