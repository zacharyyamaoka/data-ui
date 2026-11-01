#!/usr/bin/env python3
"""Build the analyses review report (data-ui PEP 0007, CONTRACT §19, lane/analyses).

    python3 docs/build_analyses_report.py

Reads ~/data-ui/reports/media/data-ui-analyses-2026-10-26/ (the hero video recorded from the built gallery,
stills, robotparts' before/after) and writes one self-contained page beside it,
~/data-ui/reports/media/data-ui-analyses-2026-10-26.html (media inlined; reports/media/ is gitignored).
"""

from __future__ import annotations

import base64
import html
import pathlib

REPORTS = pathlib.Path("~/data-ui/reports/media")
MEDIA = REPORTS / "data-ui-analyses-2026-10-26"
OUT = REPORTS / "data-ui-analyses-2026-10-26.html"
ROOT = pathlib.Path(__file__).resolve().parents[1]

CHECKER = """$ data-ui check tests/fixtures/analysis/bad.md
bad.md:1: error: question: is required
bad.md:3: error: status: must be one of draft, open, decided, superseded (it is maybe)
bad.md:5: error: decision: p9 is not one of parts:
bad.md:11: error: ```base: 'prise' is not a property of parts.json (did you mean 'price'?)
bad.md:14: error: ![[missing.base]]: no such file (looked beside the analysis)
bad.md:16: error: ```base: data data/nope.json: no such file
checked 1 analysis: 6 errors, 0 warnings"""


def uri(name: str, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode((MEDIA / name).read_bytes()).decode()


def e(text) -> str:
    return html.escape(str(text), quote=True)


def fig(name: str, alt: str, caption: str) -> str:
    return f'<figure><img src="{uri(name, "image/webp")}" alt="{e(alt)}"><figcaption>{caption}</figcaption></figure>'


def main():
    example = (ROOT / "gallery" / "examples" / "analyses" / "sim-to-real-twin.md").read_text(encoding="utf-8")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>data-ui Analyses</title>
<style>
:root {{ --bg: #fff; --bg2: #f3f4f6; --ink: #1a1a1a; --ink2: #555; --rule: #d9d9d9; --accent: #1a1a1a; --ok: #1f7a3a; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg: #0a0a0a; --bg2: #1a1a1a; --ink: #ececec; --ink2: #a3a3a3; --rule: #333; --accent: #ececec; --ok: #6fd08f; }} }}
:root[data-theme="dark"] {{ --bg: #0a0a0a; --bg2: #1a1a1a; --ink: #ececec; --ink2: #a3a3a3; --rule: #333; --accent: #ececec; --ok: #6fd08f; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px 64px; }}
h1 {{ font-size: 28px; margin: 0 0 6px; line-height: 1.2; }}
h2 {{ font-size: 20px; margin: 40px 0 10px; padding-top: 10px; border-top: 1px solid var(--rule); }}
.verdict {{ font-size: 17px; margin: 10px 0 14px; padding: 12px 16px; border-left: 5px solid var(--accent); background: var(--bg2); }}
.mut {{ color: var(--ink2); }}
code, pre {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }}
pre {{ background: var(--bg2); padding: 12px 14px; overflow-x: auto; border-radius: 4px; line-height: 1.45; }}
video, img {{ max-width: 100%; height: auto; display: block; border: 1px solid var(--rule); border-radius: 4px; }}
figure {{ margin: 0; min-width: 0; }}
figcaption {{ font-size: 13px; color: var(--ink2); margin-top: 4px; }}
.two {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; align-items: start; }}
.tw {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
th, td {{ border: 1px solid var(--rule); padding: 6px 9px; text-align: left; vertical-align: top; }}
th {{ background: var(--bg2); }}
td code, li code, p code {{ overflow-wrap: anywhere; }}
.tiers {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: stretch; margin: 12px 0; }}
.tier {{ flex: 1 1 220px; border: 1px solid var(--rule); border-radius: 6px; padding: 10px 12px; }}
.tier b {{ display: block; font-size: 16px; }}
.tier.new {{ border: 2px solid var(--accent); }}
.kpis {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }}
.kpi {{ border: 1px solid var(--rule); border-radius: 4px; padding: 8px 12px; flex: 1 1 150px; }}
.kpi b {{ display: block; font-size: 22px; }}
@media (max-width: 760px) {{ .two {{ grid-template-columns: minmax(0, 1fr); }} h1 {{ font-size: 23px; }} }}
</style></head><body><main>
<p class="mut">data-ui · lane/analyses (from lane/dashboards-land) · 2026-10-26 · PEP 0007 (proposed) · CONTRACT §19</p>
<h1>Analyses: data-ui's third tier</h1>
<p class="verdict"><strong>data-ui now has views → dashboards → analyses.</strong> <code>&lt;data-analysis&gt;</code> draws a W&amp;B-style report from one Markdown file:
its contents column comes from the headings, it embeds live views and whole dashboards, and it has a decision box.
<code>&lt;data-analyses&gt;</code> lists the reports as a data-ui view. <code>data-ui check x.md</code> validates a file for an agent.
robotparts.dev now runs on the kit, and its same checks pass. On <code>lane/analyses</code> (2077550), not merged; it lands after
<code>lane/dashboards-land</code>.</p>
<div class="kpis">
<div class="kpi"><b>126/127</b>unit tests (1 skipped), 10 new</div>
<div class="kpi"><b>544/544</b>whole browser suite; the case's own 34/34</div>
<div class="kpi"><b>3/3</b>Python twin + checker tests</div>
<div class="kpi"><b>67 · 20 · 213</b>robotparts browser · real round trip · site tests, on the kit</div>
</div>

<div class="tiers">
<div class="tier"><b>Views</b><code>&lt;data-views&gt;</code>: one dataset, many views (.base)</div>
<div class="tier"><b>Dashboards</b><code>&lt;data-dashboard&gt;</code>: many views over linked datasets (.base + <code>layout:</code>, §17)</div>
<div class="tier new"><b>Analyses</b><code>&lt;data-analysis&gt;</code> / <code>&lt;data-analyses&gt;</code>: prose + views + dashboards + a decision (.md, §19)</div>
</div>

<h2>The journey</h2>
<p class="mut">Recorded from the built gallery. The list (Table first), the Gallery, the sim-to-real analysis, jumps through the contents, a
click inside the embedded dashboard that narrows every panel, then the decision.</p>
<video controls autoplay muted loop playsinline><source src="{uri("analyses-hero.mp4", "video/mp4")}" type="video/mp4">
<img src="{uri("analyses-hero.gif", "image/gif")}" alt="The analyses list, an analysis, its dashboard and its decision"></video>

<h2>The gallery case: three analyses on real data</h2>
{fig("list.webp", "The analyses list", "<code>&lt;data-analyses&gt;</code>: one row per analysis file, from its frontmatter; Table, Gallery and Board by status")}
<div class="two">
{fig("shoulder.webp", "The shoulder actuator analysis", "The shoulder actuator: a <code>```base</code> fence filtered by <code>this.parts</code>, the catalog's own rows")}
{fig("pid.webp", "The PID gains analysis", "pidtuna's robots: simulated data, marked <code>[!illustrative]</code>; tuning loses on the lever (4.1721 vs 1.7372)")}
{fig("dashboard-dark.webp", "An embedded dashboard in dark mode", "Dark: the whole sim-to-real dashboard embedded with one line, <code>![[../sim-to-real/views.base]]</code>")}
{fig("phone.webp", "390 px", "390 px: the contents fold above; no sideways scroll (measured)")}
</div>

<h2>The format, in one file</h2>
<pre>{e(example)}</pre>

<h2>The element's surface (CONTRACT §19)</h2>
<div class="tw"><table>
<tr><th>Piece</th><th>What it is</th></tr>
<tr><td><code>&lt;data-analysis src="x.md"&gt;</code> or <code>.text</code></td><td>The report. Contents column (sticky, drag-resizable, remembered, §11), header, body, problems by line. A new <code>.text</code> redraws and keeps every unchanged block.</td></tr>
<tr><td>Host hooks</td><td><code>resolveLink(target)</code>: what <code>[[target]]</code> opens, and the part chips' photos. <code>missingLink</code>. <code>readFile(path)</code>: a synced folder's files. <code>source</code>: the header's pill, note and file line. <code>dir</code>, <code>embeds</code>, <code>heading="2"</code>.</td></tr>
<tr><td><code>&lt;data-analyses src="index.json"&gt;</code>, <code>.rows</code> or <code>base=</code></td><td>The list: a <code>&lt;data-views&gt;</code> over the frontmatter, defaulting to Table, Gallery and Board by status. <code>.data</code> and <code>.model</code> pass through.</td></tr>
<tr><td><code>data-ui check x.md [--root DIR] [--embeds DIR]</code></td><td>The frontmatter's rules, then every fence and embed through the <code>.base</code> checker, at their lines in the .md.</td></tr>
<tr><td><code>dist/python/data_ui_analysis.py</code></td><td>The Python twin for build scripts (<code>read_analysis</code>, <code>blocks_of</code>, <code>analysis_row</code>, <code>build_index</code>); a test holds it equal to format.js.</td></tr>
</table></div>
<p>An agent's broken file, as the checker reports it:</p>
<pre>{e(CHECKER)}</pre>

<h2>robotparts on the kit: before and after</h2>
<p>robotparts' <code>static/analysis.js</code> now keeps only what is robotparts' own: part links with photos, the folder, whose
file a report is, the list's photo mosaic and a part's mentions. The renderer is the vendored kit. The same 67 browser checks
and the 20-check real folder-sync round trip pass. Pixel diffs of the same screenshots before and after:</p>
<div class="tw"><table>
<tr><th>Page</th><th>Pixels that differ</th><th>Why</th></tr>
<tr><td>/analysis/ list, signed in and out, light and dark, 375 px</td><td>0.00%</td><td>identical</td></tr>
<tr><td>A report (shoulder actuator), light and dark</td><td>0.10%</td><td>the contents indent relative to the shallowest heading, so <code>##</code> sections are now flush</td></tr>
<tr><td>A part's Analysis tab (dark)</td><td>0.08–0.09%</td><td>the same indentation</td></tr>
<tr><td>A part's Analysis tab (light, after the drag check)</td><td>6.56%</td><td>the contents' width is now remembered per element (<code>stock-toc</code>), so a drag on a report no longer widens a part tab</td></tr>
</table></div>
{fig("robotparts-before-after.webp", "robotparts part tab before and after", "robotparts' GIM4305-10 Analysis tab: before (its own renderer), after (data-ui's element)")}

<h2>Found on the way</h2>
<ul>
<li><strong>A schema error the old checker missed.</strong> robotparts' examples and its 1,561 generated stock analyses used <code>compare: rows: all</code>, which data-ui's schema does not allow. <code>data-ui check x.md</code> caught it. Fixed, and robotparts' tests now run the kit's checker (they skip when a data-ui checkout has no analyses tier).</li>
<li><strong>For the integrator: a core cards issue.</strong> A card with no image puts its selection box over the first letters of the title (visible in the Gallery tab above). The analyses list opens on Table because of it. Not patched here: <code>packages/core</code> and the cards view are outside this lane.</li>
<li>Adding a gallery case changes the perf oracle's corpus. Its golden was regenerated from the base commit dc087c3, with <code>packages/core</code> untouched: the same proof lane/dashboards-land used.</li>
</ul>

<h2>What's left, and what needs you</h2>
<ul>
<li><strong>Merge order (the integrator's):</strong> lane/dashboards-land, then lane/analyses, then robotparts re-vendors from data-ui main. Adding the "Analyses" section on data-ui.dev beside Views and Dashboards is also the integrator's.</li>
<li><strong>Not done:</strong> in-page editing (the file is the editor), comments, publishing, and a frontmatter JSON schema for editors.</li>
</ul>
</main></body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(f"{OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
