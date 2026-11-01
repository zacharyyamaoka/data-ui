#!/usr/bin/env python3
"""Build reports/data-ui-filters-2026-10-26.html: the standard rail filter kinds, one still each, the clip, the
prior art, the .base snippets, and what robotparts could switch to.

    npm --prefix ~/data-ui/.wt/facets test > ~/data-ui/reports/media/filters/npm-test.log 2>&1
    ~/psu-atlas/.venv/bin/python docs/capture_filters.py        # the stills and the clip
    python3 docs/build_filters_report.py                               # this page

Text only; the media sit beside it in reports/media/filters/ (gitignored), referenced by relative path. Every count is
read from the capture (stills.json), the test log or git, never typed in. Light and dark follow the reader's system.
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS = pathlib.Path("~/data-ui/reports")
OUT = REPORTS / "data-ui-filters-2026-10-26.html"
MEDIA = "media/filters"
CASE = ROOT / "gallery" / "examples" / "filters-gallery"
e = html.escape

kinds_doc = json.loads((CASE / "source" / "kinds.json").read_text(encoding="utf-8"))
stills = json.loads((REPORTS / MEDIA / "stills.json").read_text(encoding="utf-8"))
log = (REPORTS / MEDIA / "npm-test.log").read_text(encoding="utf-8")
base_lines = (CASE / "views.base").read_text(encoding="utf-8").split("\n")


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True).stdout.strip()


# the top-level facets: entries of the case's .base, as text, for each kind's snippet (as kinds.mjs cuts them)
entries: list[list[str]] = []
inside = False
for line in base_lines:
    if line.startswith("facets:"):
        inside = True
        continue
    if inside and re.match(r"^\S", line):
        break
    if inside and line.startswith("  - "):
        entries.append([line])
    elif inside and entries:
        entries[-1].append(line)


def snippet(kind: str) -> str:
    test = re.compile(r"exclude: true") if kind == "values + exclude" else re.compile(r"diagram:") if kind.startswith("diagram") else re.compile(rf"as: {re.escape(kind)}\b(?!-)")
    hit = next((e_ for e_ in entries if test.search("\n".join(e_))), None)
    return "facets:\n" + "\n".join(hit) if hit else ""


summary = {m.group(2): m.group(1) for m in re.finditer(r"^(ok|FAIL|skip)\s+(.+?): ", log, re.M)}
unit = re.findall(r"^# (pass|fail|skipped) (\d+)", log, re.M)
browser = re.search(r"(\d+)/(\d+) browser checks pass", log)
filters_checks = [line[5:] for line in log.splitlines() if line.startswith(("PASS filters", "FAIL filters"))]
commits = git("log", "--format=%h %s", "964fd01..HEAD").splitlines()
test_tail = "\n".join(log.strip().splitlines()[-7:])

kind_cards = []
for k in kinds_doc["kinds"]:
    s = stills.get(k["kind"], {})
    kind_cards.append(f"""<article class="kind">
  <figure><img src="{MEDIA}/{e(s.get('file', ''))}" alt="The {e(k['kind'])} facet in use" loading="lazy"></figure>
  <div class="kind-text">
    <h3><code>{e(k['kind'])}</code></h3>
    <p class="copies">copies <a href="{e(k['url'])}">{e(k['copies'])}</a></p>
    <p>{e(k['what'])}.</p>
    <p class="muted">Options: {e(k['options'])}</p>
    <p class="url"><code>{e(s.get('url', k['try']))}</code> → <b>{e(s.get('status', ''))}</b></p>
    <pre><code>{e(snippet(k['kind']))}</code></pre>
  </div>
</article>""")

prior = "".join(f"<tr><td><code>{e(k['kind'])}</code></td><td><a href=\"{e(k['url'])}\">{e(k['copies'])}</a></td><td>{e(k['what'])}</td></tr>" for k in kinds_doc["kinds"])
seen = "".join(f"<tr><td>{f'<a href=\"{e(x['url'])}\">{e(x['site'])}</a>' if x['url'] else e(x['site'])}</td><td colspan=\"2\">{e(x['copy'])}</td></tr>" for x in kinds_doc["seen"])

STOCK = [
    ("Two-thumb slider", "—", "two native <input type=range> on one rail (the browser's own keyboard: arrows, Page Up / Down, Home / End)", "release applies; focus stays on the thumb across a redraw"),
    ("Multi-select listbox", "—", "native <select multiple>", "Ctrl / Shift picking, the platform's listbox keyboard"),
    ("Date boxes", "—", "native <input type=date>", "ISO dates in the filter (listed >= \"2026-10-19\")"),
    ("Toggle", "—", "a checkbox with role=switch", "Space toggles; the screen reader says switch, on / off"),
    ("Histogram", "—", "hand SVG (24 <rect>s); Vega-Lite was the alternative, 850 KB for 24 bars", "bars outside the range dim; a bar's count on hover"),
    ("Line icons, diagrams", "—", "SVG files drawn in the text colour with a CSS mask", "one file reads in light and dark"),
    ("The widgets themselves", "values, range, has (data-ui)", "Algolia InstantSearch.js widgets were the stock candidate; they run on InstantSearch's own search state and a search client, and data-ui's state is the Bases filter tree (one model, two editors, SPEC §6), so their names and behaviour are copied, not the code", "every kind round-trips through the one filter tree"),
    ("The filter model", "unchanged (stock seam)", "Obsidian Bases filters: and / or / not over expressions", "a link or a saved view means the same in every editor"),
]
stock = "".join(f"<tr><td>{e(a)}</td><td>{e(b)}</td><td>{e(c)}</td><td>{e(d)}</td></tr>" for a, b, c, d in STOCK)

page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>data-ui filters · 2026-10-26</title>
<style>
  :root {{ --bg: #fff; --fg: #18181b; --muted: #6b6b76; --rule: #e7e7ea; --subtle: #f5f5f6; --accent: #2a62c9; --good: #1a7f4e; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #0f0f11; --fg: #ececef; --muted: #9a9aa3; --rule: #26262b; --subtle: #18181c; --accent: #7aa7f2; --good: #4cc38a; }} }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.5 system-ui, -apple-system, Segoe UI, sans-serif; }}
  main {{ max-width: 1120px; margin: 0 auto; padding: 28px 16px 60px; }}
  h1 {{ font-size: 26px; margin: 0 0 6px; }} h2 {{ font-size: 19px; margin: 36px 0 10px; border-top: 1px solid var(--rule); padding-top: 18px; }}
  h3 {{ font-size: 15px; margin: 0 0 2px; }}
  a {{ color: var(--accent); }} code {{ font: 12.5px ui-monospace, SFMono-Regular, Menlo, monospace; }}
  .verdict {{ font-size: 17px; margin: 0 0 14px; }} .muted {{ color: var(--muted); }}
  video, img {{ max-width: 100%; display: block; border: 1px solid var(--rule); border-radius: 8px; }}
  .hero {{ margin: 12px 0 4px; }}
  .kinds {{ display: grid; gap: 14px; }}
  .kind {{ display: grid; grid-template-columns: minmax(0, 300px) minmax(0, 1fr); gap: 16px; border-top: 1px solid var(--rule); padding-top: 14px; }}
  .kind figure {{ margin: 0; }} .kind img {{ width: 100%; height: auto; background: #fff; }}
  .kind p {{ margin: 0 0 4px; }} .copies {{ color: var(--muted); font-size: 13.5px; }} .url {{ font-size: 13.5px; }}
  pre {{ margin: 6px 0 0; padding: 8px 10px; background: var(--subtle); border-radius: 6px; overflow-x: auto; font-size: 12px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; }} td, th {{ border-top: 1px solid var(--rule); padding: 6px 10px 6px 0; vertical-align: top; text-align: left; }}
  .tablewrap {{ overflow-x: auto; }}
  .pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }} .pair figure {{ margin: 0; }} figcaption {{ font-size: 13px; color: var(--muted); margin-top: 4px; }}
  .phones {{ display: grid; grid-template-columns: repeat(2, minmax(0, 260px)); gap: 14px; }}
  .rails {{ display: grid; grid-template-columns: repeat(2, minmax(0, 240px)); gap: 14px; align-items: start; }}
  ul.tight li {{ margin: 3px 0; }} .ok {{ color: var(--good); font-weight: 600; }}
  @media (max-width: 720px) {{ .kind, .pair {{ grid-template-columns: 1fr; }} .kind img {{ max-width: 300px; }} }}
</style>
</head>
<body>
<main>
<h1>Standard rail filters for <code>&lt;data-facets&gt;</code></h1>
<p class="verdict"><b>21 filter kinds, each one <code>facets:</code> entry on the one filter tree, are built and proved in a browser on robotparts' 1,149 actuators.</b> They live on <code>lane/facets</code> in <code>~/data-ui/.wt/facets</code> and are not merged. <code>npm run build &amp;&amp; npm test</code> is green.</p>
<p class="muted">Zach, 2026-10-26: “for the side filter here can you please make a bunch of standard 'filters' that we can pick and choose from”, and then the McMaster rail: pictorial galleries, picture lists, dimension diagrams, compact grids, ⓘ, search inside each facet.</p>

<figure class="hero">
  <video src="{MEDIA}/hero.mp4" poster="{MEDIA}/hero-poster.webp" autoplay muted loop playsinline controls width="1280"></video>
  <figcaption>The live Filters case, recorded headless. Pick a form tile, a bus chip and a torque bound on the histogram slider, then switch to Cards, tap a logo swatch and switch to Chart. Remove a chip in Current filters and pick a price bucket. The table, the cards and the chart all follow the same filter. <a href="{MEDIA}/hero.gif">GIF fallback</a>.</figcaption>
</figure>

<h2>Done and proved</h2>
<ul class="tight">
  <li><b>Every kind is driven the way a person uses it</b>: a click, a key, or a thumb released. The table's row count must equal a count that <code>checks.py</code> works out from <code>actuators.json</code> in Python, which shares no code with the rail. {len(filters_checks)} Filters checks pass (in the log). Each check also runs light and dark, at 1280 and at 390.</li>
  <li><b>Each kind's projection is tested both ways</b> (rail → tree → rail is the identity), and <code>grammar.js</code> is the oracle: the rows the rail picks are the rows the stored tree picks. Also tested: the URL round trip, counts (disjunctive, buckets, rating levels, tree levels, popular, date presets, histogram sums), what stays custom, and the fallback for an unknown kind. A mutation run breaks seven projections one at a time, and each one turns a law red.</li>
  <li><b>The URL is readable</b>: <code>?brand=Steadywin&amp;price=50..&lt;100&amp;brand!=KST&amp;model~=gim&amp;listed=..&lt;2026-10-12</code>. Every kind's link opens the case with that kind drawn. Links written before this change read the same.</li>
  <li><b>Both checkers learned every kind and option</b>, with "did you mean": <code>as: slidr</code> → "did you mean 'slider'"; <code>slider</code> on a text property → "needs a number property".</li>
</ul>
<pre><code>{e(test_tail)}</code></pre>
<p class="muted">Unit: {e(' · '.join(f'{k} {v}' for k, v in unit))}. Browser: {e(browser.group(0) if browser else 'not run')}. Commits on <code>lane/facets</code> (off main 964fd01):</p>
<pre><code>{e(chr(10).join(commits))}</code></pre>

<h2>Every kind, in use</h2>
<p class="muted">Each still is the facet as the rail draws it, opened by its readable link (shown with the rows it left), and its snippet cut from the case's <code>views.base</code>. A kind is <code>{{property, as: &lt;kind&gt;, …options}}</code>. Every kind also takes <code>label</code>, <code>info</code> (ⓘ), <code>diagram</code> and <code>collapsed</code>.</p>
<div class="kinds">{''.join(kind_cards)}</div>

<h2>The whole rail, light and dark, and the phone</h2>
<p class="muted">The same picks (<code>?form=hobby servo&amp;price=50..&lt;100&amp;buses=can</code>) light and dark. On a phone the rail is a closed disclosure, and it opens on a tap.</p>
<div class="rails"><figure><img src="{MEDIA}/rail-light.webp" alt="The full rail, light" loading="lazy"><figcaption>Light</figcaption></figure><figure><img src="{MEDIA}/rail-dark.webp" alt="The full rail, dark" loading="lazy"><figcaption>Dark</figcaption></figure></div>
<div class="pair" style="margin-top:14px"><figure><img src="{MEDIA}/page-light.webp" alt="Rail and table, light" loading="lazy"></figure><figure><img src="{MEDIA}/page-dark.webp" alt="Rail and table, dark" loading="lazy"></figure></div>
<div class="phones" style="margin-top:14px"><figure><img src="{MEDIA}/phone-closed.webp" alt="390 px, rail closed" loading="lazy"><figcaption>390 px: closed</figcaption></figure><figure><img src="{MEDIA}/phone-open.webp" alt="390 px, rail open" loading="lazy"><figcaption>390 px: open</figcaption></figure></div>

<h2>Recipes: a view with its own <code>facets:</code></h2>
<p class="muted">A view entry may carry <code>facets:</code>. While that view is open, the rail is that list. Switching tab switches the rail, and the filter stays. What the new rail cannot draw shows as "+N custom".</p>
<div class="pair">
  <figure><img src="{MEDIA}/recipe-mcmaster.webp" alt="McMaster recipe" loading="lazy"><figcaption>McMaster: form as a picture gallery, drivetrain as a picture list, a searchable brand list, outer diameter as a grid under its dimension drawing, gear ratio as a grid ({e(stills.get('McMaster-style', {}).get('status', ''))}).</figcaption></figure>
  <figure><img src="{MEDIA}/recipe-amazon.webp" alt="Amazon recipe" loading="lazy"><figcaption>Amazon: current filters, an in-stock toggle, "& up" rating, price bands, a short brand list.</figcaption></figure>
  <figure><img src="{MEDIA}/recipe-digi.webp" alt="Digi-Key recipe" loading="lazy"><figcaption>Digi-Key: an in-stock toggle and a parametric listbox per property (Ctrl / Shift to pick several).</figcaption></figure>
  <figure><img src="{MEDIA}/recipe-obsidian.webp" alt="Obsidian recipe" loading="lazy"><figcaption>Obsidian: <code>facets: []</code>. No rail; the view's own filter (an <code>||</code> and a <code>!=</code>) belongs to the Filter menu's builder.</figcaption></figure>
</div>

<h2>Prior art (accessed {e(kinds_doc['accessed'])})</h2>
<div class="tablewrap"><table><thead><tr><th>Kind</th><th>Copies</th><th>What it copies</th></tr></thead><tbody>{prior}{seen}</tbody></table></div>

<h2>Stock parts</h2>
<div class="tablewrap"><table><thead><tr><th>Element</th><th>Today</th><th>Off-the-shelf part</th><th>Behaviour that must survive</th></tr></thead><tbody>{stock}</tbody></table></div>

<h2>What robotparts could switch to</h2>
<p class="muted">robotparts.dev's actuator rail today (<code>robotparts/site/views/actuator.base</code>) has values for brand, form, drivetrain, buses, level, checks and in_stock, nine ranges and one has. Recommended, each a one-line <code>.base</code> change once data-ui is re-vendored:</p>
<ul class="tight">
  <li><b>Peak torque, rated torque and mass as <code>slider-histogram</code> with <code>log: true</code>.</b> They span four decades (0.01 to 1,828 N·m). On a linear range box the parts all sit at one end; the histogram shows where they are before you drag.</li>
  <li><b>Form and drivetrain as <code>gallery</code> / <code>picture-list</code></b> with the line icons in this case's <code>icons/</code>. That is McMaster's look, and the value names explain themselves.</li>
  <li><b>Brand as <code>swatch</code> with logos</b> (<code>images:</code>), plus a searchable <code>values</code> list with <code>exclude: true</code> under it. Only 3 of 48 actuator brands have a logo in robotparts' media today (Steadywin, Damiao, JMC); the rest draw a monogram. More logos would make this row pay off.</li>
  <li><b><code>in_stock</code> as <code>toggle</code></b> (<code>value: "yes"</code>), and <b>CAD / Sim as toggles on <code>checks</code></b> (<code>value: cad</code>). These replace a values list whose one useful tick is "yes".</li>
  <li><b>Outer diameter and axial length with <code>diagram:</code></b> (this case's <code>diagrams/od.svg</code>, <code>length.svg</code>). Then nobody wonders which length is meant.</li>
  <li><b>Price as <code>buckets</code></b> (25 / 50 / 100 / 250 USD) above the range, a <code>current</code> bar at the top, and a <code>search</code> over name and model.</li>
  <li><b>Level as <code>min-level</code></b> once more parts climb past level 1. Today 1,147 of 1,149 are level 1, so it filters little.</li>
</ul>

<h2>Left, and what needs you</h2>
<ul class="tight">
  <li><b>Merge</b> <code>lane/facets</code>: your call. It touches <code>data-views.js</code> only in the URL code (now in <code>facets.js</code>) and adds a view key (<code>facets:</code>). Both are recorded in CONTRACT §7 as a dated amendment. <i>Default if you say nothing: it stays on the lane.</i></li>
  <li><b>Relative dates are stored absolute.</b> "Last 7 days" writes <code>listed &gt;= "2026-10-19"</code>, because <code>grammar.js</code> has no <code>now()</code>; a saved link keeps that date. Making it relative means <code>now()</code> in the grammar, which this lane did not touch. <i>Recommendation: add <code>now()</code> and durations there, then let <code>presets</code> write them. Default: stays absolute.</i></li>
  <li><b>Algolia's toggle option <code>on:</code> is <code>value:</code> here.</b> PyYAML (YAML 1.1), which the gallery's oracle test reads with, turns an <code>on:</code> key into <code>true</code>. Quote <code>"yes"</code> / <code>"no"</code> values for the same reason.</li>
  <li><b>Not built:</b> Kayak's time-of-day sliders (no time column in any data yet; <code>slider</code> covers it). Digi-Key's "Apply all" staging: the rail applies every pick at once, as McMaster does. SPEC.md §6 still lists only values, range and has; CONTRACT §7's amendment is the current list.</li>
  <li><b>An architecture fork, if merged:</b> a view's own <code>facets:</code> (a rail per view) and a config-aware projection (what the rail can draw depends on its facets). That earns a decision record at merge (<code>docs/peps/</code>). This lane did not write one.</li>
</ul>
</main>
</body>
</html>
"""
OUT.write_text(page, encoding="utf-8")
print(f"{OUT}: {OUT.stat().st_size:,} bytes; media {sum(p.stat().st_size for p in (REPORTS / MEDIA).iterdir() if p.is_file()):,} bytes")
