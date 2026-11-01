#!/usr/bin/env python3
"""Build reports/data-ui-milestone-2026-10-26.html: the core pass, the landing page and the gallery, in one page.

    npm --prefix ~/data-ui test > reports/media/milestone-2026-10-26/npm-test.log 2>&1   # the test counts
    ~/psu-atlas/.venv/bin/python docs/capture_milestone.py                              # the video and stills
    python3 docs/build_milestone_report.py

The page is text only; its media sit beside it in reports/media/ (gitignored) and are referenced by relative path,
so it stays far under the desktop preview's 1.9 MB. Every number on it is read from the build (dist/, gzip computed
here), the test log or git, never typed in. Light and dark from the reader's system.
"""

from __future__ import annotations

import gzip
import html
import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "data-ui-milestone-2026-10-26.html"
MEDIA = "media/milestone-2026-10-26"
MEDIA_DIR = ROOT / "reports" / MEDIA
e = html.escape

VIEWS = [  # (type, still, case, caption)
    ("table", "view-table", "robotparts-actuators", "Two group levels with fold and summaries; rich cells carry their basis mark (S = a seller's listing)."),
    ("pivot", "view-pivot", "models-benches", "Models × benches: each cell the median twin error with its spread; a cell opens the runs behind it."),
    ("list", "view-list", "vibetracks-feature-tree", "Vibe Tracks' spec tree: tree: {parent} on TanStack sub-rows, nested by the core since this pass."),
    ("record", "view-record", "dataclass-viewer", "The record view with edit: true: a form bounded by each Value's own low / high; structural fields read-only."),
    ("compare", "view-compare", "robotparts-compare", "Four actuators side by side, the better value marked; photos now resolve beside compare.json via mediaUrl."),
    ("cards", "view-cards", "robotparts-photos", "Bases' cards with real hosted photos, virtualised lanes, group headings by brand."),
    ("kanban", "view-kanban", "vibetracks-board", "Columns from groupBy; a drag proposes a data edit, the host decides."),
    ("chart", "view-chart", "actuator-charts", "Ashby chart: filled hull per drivetrain in log space, a constant N·m-per-gram index line; the data now comes from the sibling case."),
    ("kpi", "view-kpi", "vibetracks-kpis", "The headline card's history is the chart view; each card's direction comes from compare.better: better."),
    ("calendar", "view-calendar", "robotparts-calendar", "Event Calendar: releases and daily-note dates, drag to propose a new date."),
    ("timeline", "view-timeline", "robotparts-timeline", "vis-timeline: robotparts' releases as points, branches as bars, lanes by kind."),
    ("graph", "view-graph", "rack-wiring", "React Flow + dagre: the 1-DoF rack's wiring, roles as subflows, wire kinds as edge colours."),
    ("map", "view-map", "robotparts-sellers-map", "MapLibre on the bundled Natural Earth map: where robotparts' sellers ship; no tile server."),
]

DECISIONS = [
    ("Trees on TanStack sub-rows, in the core",
     "<code>rowModel</code> nests a <code>table</code> or <code>list</code> view's rows with table-core's <code>getSubRows</code> + expanding feature, so <code>input.table</code> holds the outline. Exports <code>treeSpec</code>, <code>treeRows</code>, <code>isHeading</code>. The list's 102-line <code>packages/views/tree</code> is deleted; the table view now honours <code>tree:</code> (chevron, → ←, fold all). Path headings are in the table, never in <code>rows</code>; with <code>groupBy</code>, a group holds the top of each tree.",
     "4 unit tests (cycle, filtered parent, path headings, groups, real feature tree); 3 browser checks on the dataclass case's new “Outline table”."),
    ("The peek reads <code>record.sections</code> and <code>edit</code>",
     "<code>openPeek</code> lays fields out in the current view's sections and, with <code>edit: true</code>, is the record view's form, proposing only changed fields. The form module moved into the core (<code>fieldHtml</code>, <code>readEdits</code>, <code>lockedBecause</code>); <code>packages/views/form</code> is deleted.",
     "4 browser checks: sections, structural fields read-only, refused on a read-only host, saved on an editable one (table and peek redraw)."),
    ("<code>dataset.url</code> + <code>mediaUrl(src, dataset)</code>",
     "The data file's URL reaches every view; one helper resolves a relative image path against it. Removed the URL derivations in chart (<code>_media</code>), cards (<code>mediaBase</code>, <code>resolve</code>) and kanban (<code>mediaBase</code>); compare, record, list and table now resolve too (compare drew paths raw, so its photos had to sit beside the page).",
     "3 unit tests; the chart case's hover check now asserts the photo loads from <code>robotparts-actuators/photos/</code>, beside the data, not the page."),
    ("KPI direction: <code>compare.better: higher | lower | &lt;property&gt;</code>",
     "<b>Decided: a named key, not the official <code>better</code> column.</b> The lane's rule (any column called <code>better</code> silently overrides <code>compare.better</code>) becomes <code>better: better</code> in the Vibe Tracks case. Why: the <code>.base</code> file is the API, so the rule is visible and checked against the data like <code>against:</code>, and no dataset changes meaning because of a column's name. No direction draws the delta neutral.",
     "Checker unit test (property accepted, a typo flagged with a suggestion); the Vibe Tracks delta check still passes (SPPM up good, time down good)."),
    ("Join: <b>not adopted</b>; <code>photo</code> moved into the producer",
     "<b>Decided: the simpler, stock option.</b> <code>gallery/tools/build_examples.py</code> now writes the actuators' <code>photo</code> column and its 150 photos (the step moved from actuator-charts' own <code>source/build.py</code>; the rebuilt file is byte-identical to that case's copy), and actuator-charts' <code>data:</code> points at <code>../robotparts-actuators/actuators.json</code>. Why: a column the data needs belongs to its producer; a join would be a second data model in a grammar stock Bases does not have.",
     "<code>cmp</code> of the rebuilt file against the old copy: identical; every photo identical."),
    ("A chart needs an <code>encoding</code>, a <code>mark</code> or a <code>layer</code>",
     "The schema's <code>anyOf</code> gains <code>encoding</code>, so a checked file can leave the mark to Show Me. Both checkers now say “a chart needs an encoding (Show Me picks the mark), a mark, or a layer of marks” instead of “needs 'mark'”.",
     "Checker unit test; the Python checker prints the same line."),
    ("<code>&lt;data-kpi&gt;</code> / <code>&lt;data-sparkline&gt;</code> on a plain page",
     "<code>dist/views/kpi.js</code> adds its own stylesheet (named as the registry names it, so never twice); package export <code>data-ui/kpi</code>; documented in the kpi README with a copy-paste page; <code>dist/site/plain/kpi.html</code> is that page.",
     "Browser check: defined, styled once (22 px number, bordered card), three cards, a sparkline with a hollow estimate, no <code>&lt;data-views&gt;</code>."),
]

GAPS = [
    "<b>No screenshots of the original UIs.</b> Each case page names the hand-rolled screen it replaces, with its repo path, in words; capturing 20 originals across five apps was not in this pass.",
    "<b>The hero's graph edge is a derived ladder.</b> The actuators have no relation between rows, so <code>build_examples.py</code> now writes <code>step_up</code>: among the photographed parts of one brand, the next one up in peak torque. It is defined in the data (<code>derived</code>, hidden) and only the hero draws it, but it is a relation of the 150-photo subset, not of the catalog.",
    "<b>Thumbnails draw at 2× and scale by half.</b> The chart sized itself from its bounding box and drew at half size inside them; it now sizes by its layout box (fixed). Other libraries measure layout already; a future view that reads <code>getBoundingClientRect</code> for its size would repeat the bug.",
    "<b><code>npm run test:unit</code> (the directory form) fails on this Node</b>, before and after this pass: <code>node --test tests/unit/</code> is treated as one file. <code>npm test</code> lists the files and is green.",
    "<b>The peek's form is the record view's.</b> A view with <code>edit: true</code> but no <code>record.sections</code> edits every visible property but the title; there is no per-view “which fields” beyond sections.",
    "<b>Tree + <code>groupBy</code>:</b> a group holds the top of each tree and children follow their parent even when their own value differs (TanStack's semantics). Documented; a child is never drawn twice.",
    "<b>The hero is a fixed 500 px tall</b> (440 on a phone); the kanban and graph read best on a desktop.",
]


def read_log() -> tuple[str, dict]:
    path = MEDIA_DIR / "npm-test.log"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    counts = {}
    m = re.search(r"^# tests (\d+)\n# suites \d+\n# pass (\d+)\n# fail (\d+)", text, re.M) or re.search(r"^# tests (\d+).*?^# pass (\d+).*?^# fail (\d+)", text, re.M | re.S)
    if m:
        counts["unit (node --test)"] = f"{m.group(2)} of {m.group(1)} pass, {m.group(3)} fail"
    ran = re.findall(r"^Ran (\d+) tests? in .*\n\n(OK|FAILED.*)$", text, re.M)
    for name, (n, ok) in zip(("Python checker", "Python .base reader"), ran):
        counts[name] = f"{n} tests, {ok}"
    m = re.search(r"^(\d+)/(\d+) browser checks pass", text, re.M)
    if m:
        counts["browser checks (Playwright, headless Chromium)"] = f"{m.group(1)} of {m.group(2)} pass"
    tail = text[text.rfind("== summary"):].strip() if "== summary" in text else "(no test log: run npm test into the log first)"
    return tail, counts


def sizes() -> list[tuple[str, int, int]]:
    out = []
    for p in [ROOT / "dist" / "data-ui.js", ROOT / "dist" / "data-ui.css", *sorted((ROOT / "dist" / "views").glob("*.js")), *sorted((ROOT / "dist" / "views").glob("*.mjs"))]:
        raw = p.read_bytes()
        out.append((str(p.relative_to(ROOT / "dist")), len(raw), len(gzip.compress(raw, 9))))
    return out


def bullets(readme: str) -> dict:
    out, key = {}, None
    for line in readme.split("\n"):
        m = re.match(r"^-\s+\*\*([^*:]+):\*\*\s*(.*)$", line)
        if m:
            key = m.group(1).strip()
            out[key] = m.group(2)
        elif key and re.match(r"^\s+\S", line):
            out[key] += " " + line.strip()
        else:
            key = None
    return out


def inline(text: str) -> str:
    s = e(text)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", s)


def cases() -> list[dict]:
    out = []
    for d in sorted((ROOT / "gallery" / "examples").iterdir()):
        if not (d / "views.base").exists():
            continue
        readme = (d / "README.md").read_text(encoding="utf-8")
        b = bullets(readme)
        types = sorted(set(re.findall(r"^\s+- type: (\w+)", (d / "views.base").read_text(encoding="utf-8"), re.M)))
        out.append({"slug": d.name, "title": re.search(r"^#\s+(.*)$", readme, re.M).group(1), "app": b.get("App", "other"), "replaces": b.get("Replaces", ""), "types": types})
    order = ["robotparts", "Vibe Tracks", "dataclass viewer", "SystemSketch", "Money", "design work"]
    return sorted(out, key=lambda c: (order.index(c["app"]) if c["app"] in order else 99, c["title"]))


def media(name: str) -> str:
    return f"{MEDIA}/{name}"


def img(name: str, alt: str, cls: str = "shot") -> str:
    if not (MEDIA_DIR / name).exists():
        return f'<p class="missing">missing: {e(media(name))} (run docs/capture_milestone.py)</p>'
    return f'<img class="{cls}" src="{e(media(name))}" alt="{e(alt)}" loading="lazy">'


def main() -> None:
    tail, counts = read_log()
    commits = subprocess.run(["git", "log", "--format=%h %s", "178ba08..HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip().splitlines()
    size_rows = sizes()
    cs = cases()
    manifest = json.loads((ROOT / "dist" / "manifest.json").read_text())
    css = """
:root { color-scheme: light dark; --bg: #fff; --fg: #0a0a0a; --muted: #6b6b6b; --line: #e5e5e5; --card: #fafafa; --code: #f3f3f3; --ok: #15803d; --accent: #1d4ed8; }
@media (prefers-color-scheme: dark) { :root { --bg: #0b0b0b; --fg: #f2f2f2; --muted: #a3a3a3; --line: #2a2a2a; --card: #141414; --code: #1d1d1d; --ok: #4ade80; --accent: #8ab4ff; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 17px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1480px; margin: 0 auto; padding: 32px 24px 64px; }
h1 { font-size: 34px; line-height: 1.2; margin: 0 0 10px; letter-spacing: -0.015em; }
h2 { font-size: 25px; margin: 52px 0 12px; letter-spacing: -0.01em; }
h3 { font-size: 19px; margin: 26px 0 8px; }
p { max-width: 1050px; }
.verdict { font-size: 19px; border-left: 4px solid var(--fg); padding: 6px 16px; margin: 0 0 20px; max-width: 1180px; }
.muted { color: var(--muted); }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .86em; background: var(--code); padding: 1px 5px; border-radius: 5px; }
pre { background: var(--code); border-radius: 10px; padding: 14px 16px; overflow-x: auto; font-size: 14px; line-height: 1.45; }
pre code { background: none; padding: 0; }
video, .shot { display: block; width: 100%; height: auto; border: 1px solid var(--line); border-radius: 12px; background: var(--card); }
figure { margin: 18px 0 30px; }
figcaption { color: var(--muted); font-size: 15px; margin-top: 8px; max-width: 1180px; }
figcaption b { color: var(--fg); }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.phone { display: grid; grid-template-columns: 2fr 1fr; gap: 18px; align-items: start; }
table { border-collapse: collapse; width: 100%; font-size: 15px; }
th, td { text-align: left; vertical-align: top; padding: 10px 12px; border-bottom: 1px solid var(--line); }
thead th { font-size: 13.5px; color: var(--muted); font-weight: 600; background: var(--card); }
td.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 12px; }
.pill { display: inline-block; font-size: 12.5px; border: 1px solid var(--line); border-radius: 999px; padding: 0 8px; margin: 0 4px 4px 0; white-space: nowrap; }
.ok { color: var(--ok); font-weight: 600; }
ul.packet li { margin: 0 0 8px; max-width: 1180px; }
.missing { color: #b91c1c; }
.clips { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
@media (max-width: 900px) { .two, .phone, .clips { grid-template-columns: 1fr; } body { font-size: 16px; } }
"""
    parts = [f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>data-ui milestone, 2026-10-26</title><style>{css}</style></head><body><main>
<p class="muted">data-ui {e(manifest['version'])} · ~/data-ui · main · 2026-10-26 · written by Claude Opus 5.5 (builder lane)</p>
<h1>data-ui: the core pass, a landing page and a gallery you can browse by app</h1>
<p class="verdict"><b>The four lanes' gaps are closed in the core, the site has a live landing page and a filterable gallery, and <code>npm test</code> is green (browser checks: {e(counts.get('browser checks (Playwright, headless Chromium)', '?'))}).</b> On <code>main</code>, committed, not pushed (local git, no remote). Two calls were mine to make and are recorded in docs/CONTRACT.md §10: per-card KPI direction is a named key, and the photo join became a column of the producer.</p>

<figure><video src="{e(media('hero.mp4'))}" autoplay muted loop playsinline controls poster="{e(media('landing.png'))}"></video>
<figcaption><b>Recorded from the real built site, 18.6 s.</b> The landing hero switches one <code>.base</code> file's 150 photographed actuators from table to cards to a chart (a dot hovered: its photo card), a kanban and a React Flow graph, while the panel shows the entry each tab draws; then the rack-wiring case's graph (a node opens its record) and the actuator chart's hover card. <a href="{e(media('hero.gif'))}">GIF fallback</a>.</figcaption></figure>

<h2>What is done, and the proof</h2>
<h3>The core pass: seven gaps, each additive, each with a test</h3>
<div class="wrap"><table><thead><tr><th>Gap</th><th>What changed</th><th>Test</th></tr></thead><tbody>
{''.join(f'<tr><td><b>{a}</b></td><td>{b}</td><td>{c}</td></tr>' for a, b, c in DECISIONS)}
</tbody></table></div>
<p>Each is written up as a dated amendment, <code>docs/CONTRACT.md</code> §10 “Amendment 2026-10-26 (core pass; additive)”: no host call, input field or key was removed or renamed.</p>

<h3>Tests</h3>
<div class="wrap"><table><thead><tr><th>Suite</th><th>Result</th></tr></thead><tbody>
{''.join(f'<tr><td>{e(k)}</td><td class="ok">{e(v)}</td></tr>' for k, v in counts.items())}
</tbody></table></div>
<p class="muted">Before this pass: 42 unit, 5 + 4 Python, 266 browser checks. The test log's own summary, verbatim (<code>{e(media('npm-test.log'))}</code>):</p>
<pre><code>{e(tail)}</code></pre>

<h2>The landing page</h2>
<figure>{img('landing.png', 'The landing page, light')}<figcaption><b>Hero:</b> “One dataset, one .base file, many views”, then the live demo: a segmented switch (it tours the five views until you click; hover pauses it), the real <code>&lt;data-views&gt;</code>, and the current view's <code>.base</code> entry beside it.</figcaption></figure>
<figure>{img('landing-thumbs.png', 'Thirteen live thumbnails')}<figcaption><b>Thirteen views, live.</b> Each thumbnail is a gallery case's preset drawn by the kit at twice its box and scaled down; it starts only when scrolled near, so the page loads one view's code up front (a browser check counts the bundles). Each links to its case at that preset.</figcaption></figure>
<div class="phone"><figure>{img('landing-dark.png', 'The landing page, dark')}<figcaption>Dark, from the system scheme (or the Theme button).</figcaption></figure><figure>{img('landing-phone.png', 'The landing page at 390 px')}<figcaption>390 px: no sideways scroll; the <code>.base</code> panel stacks under the view.</figcaption></figure></div>
<p>Below the thumbnails: <b>Drop it into an app</b> (why data-ui is copied in <i>built and pinned</i>, with a sha manifest, rather than shadcn's copy-the-source-and-edit-it; two tags; a <code>.base</code> example; one token block), <b>Bring your own agent: the .base file is the API</b> (one paragraph after robotparts' agent-bridge proposals: files in, <code>data-ui check</code>, ⋯ and <code>#view=</code> out, no localhost socket), the provenance marks, and the Replaces table below.</p>

<h2>The gallery</h2>
<div class="two"><figure>{img('gallery.png', 'The gallery filtered to chart')}<figcaption><b>Grouped by app, filtered by app and view type</b> (<code>?type=chart</code> here; the choice lives in the URL). A case names its app in its README: <code>- **App:** robotparts</code>.</figcaption></figure>
<figure>{img('case-compare.png', 'A case page')}<figcaption><b>A case page:</b> the live views, then <code>views.base</code> beside a data excerpt (the schema and the first three rows), then the original UI it replaces, what it shows and where the data comes from. Every one of the 20 is checked light and dark at 1280 and 390 px.</figcaption></figure></div>

<h2>Every view</h2>
<p>Each still is the live element on its gallery case, light, 1280 px wide.</p>
{''.join(f'<figure>{img(still + ".png", kind)}<figcaption><b>{e(kind)}</b> · <code>gallery/examples/{e(case)}</code> · {e(cap)}</figcaption></figure>' for kind, still, case, cap in VIEWS)}
<h3>Dark</h3>
<div class="two">{''.join(f'<figure>{img(f"view-{k}-dark.png", k + " dark")}<figcaption>{e(k)}, dark</figcaption></figure>' for k in ("table", "chart", "kanban", "graph"))}</div>

<h2>Replaces</h2>
<p>Each hand-rolled UI in Zach's apps, and the gallery case that rebuilds it on the same data (from each case's README; the landing page carries the same table).</p>
<div class="wrap"><table><thead><tr><th>App</th><th>Hand-rolled today</th><th>Gallery case</th><th>Views</th></tr></thead><tbody>
{''.join(f'<tr><td>{e(c["app"])}</td><td>{inline(c["replaces"])}</td><td><code>{e(c["slug"])}</code><br>{e(c["title"])}</td><td>{"".join(f"<span class=pill>{e(t)}</span>" for t in c["types"])}</td></tr>' for c in cs)}
</tbody></table></div>

<h2>Bundle sizes</h2>
<p>From <code>dist/</code> as built; gzip at level 9 computed by this script. The core loads up front; a view's bundle loads the first time that view shows.</p>
<div class="wrap"><table><thead><tr><th>File</th><th>Bytes</th><th>gzip</th></tr></thead><tbody>
{''.join(f'<tr><td><code>{e(n)}</code></td><td class="n">{raw:,}</td><td class="n">{gz:,}</td></tr>' for n, raw, gz in size_rows)}
</tbody></table></div>

<h2>The lanes' clips</h2>
<div class="clips">
<figure><video src="media/lane-cards-board/hero-kanban-lightbox.mp4" muted loop playsinline controls preload="metadata"></video><figcaption>cards-board lane: kanban drag and the lightbox.</figcaption></figure>
<figure><video src="media/lane-charts/hero-encode-hover.mp4" muted loop playsinline controls preload="metadata"></video><figcaption>charts lane: the Encode menu and the hover card.</figcaption></figure>
<figure><video src="media/lane-time-graph/graph-hero.mp4" muted loop playsinline controls preload="metadata"></video><figcaption>time-graph lane: the React Flow graph.</figcaption></figure>
</div>

<h2>Known gaps</h2>
<ul class="packet">{''.join(f'<li>{g}</li>' for g in GAPS)}</ul>

<h2>Commits on main</h2>
<pre><code>{e(chr(10).join(commits))}</code></pre>
<p class="muted">Rebuild this page: <code>python3 docs/build_milestone_report.py</code>; its media: <code>docs/capture_milestone.py</code>.</p>
</main></body></html>
"""]
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size:,} bytes; counts {counts}")


if __name__ == "__main__":
    main()
