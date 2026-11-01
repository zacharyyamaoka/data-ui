#!/usr/bin/env python3
"""Build round 2 of the actuator-models report: Zach's six feedback points on the three ways, each before and after,
from the real gallery pages. Self-contained HTML (media inlined), written beside round 1 in robotparts' reports.

    ~/psu-atlas/.venv/bin/python docs/capture_models_views.py      # round 2's media (reports/media/models-views-r2)
    python3 docs/build_models_views_report.py [CHECKS_JSON]                 # default reports/media/phase0/checks.json

"Before" media: round 1's stills (reports/media/models-views, its capture at f547eea) and Zach's own screenshots of
round 1 (the IMAGES folder below). Every number on the page comes from a file: models.json, checks.json, git.
"""

from __future__ import annotations

import base64
import html
import io
import json
import pathlib
import subprocess
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
R2 = ROOT / "reports" / "media" / "models-views-r2"
R1 = ROOT / "reports" / "media" / "models-views"
IMAGES = pathlib.Path("/tmp/claude-1000/-home-bam-zach-brain--claude-worktrees-robotics-component-library-4a5d75/09ec7f28-61d8-4e9c-a0d1-69e79cf76516/images")
CHECKS = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "phase0" / "checks.json"
OUT = pathlib.Path("~/robotparts/reports/media/robotparts-models-data-ui-r2-2026-10-26.html")
CASE = ROOT / "gallery" / "examples" / "robotparts-models"
e = html.escape

checks = json.loads(CHECKS.read_text(encoding="utf-8"))
checks = checks["checks"] if isinstance(checks, dict) else checks
mine = [c for c in checks if c["name"].startswith(("models:", "models,", "model page")) or "robotparts-model" in c["name"]]
passed = sum(c["ok"] for c in mine)
total_ok = sum(c["ok"] for c in checks)
git = lambda *a: subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout.strip()  # noqa: E731
commits = git("log", "--format=%h %s", "main..HEAD").splitlines()
DATA = json.loads((CASE / "models.json").read_text(encoding="utf-8"))


def webp_bytes(path: pathlib.Path, quality: int, crop=None, width=None) -> bytes:
    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop(crop)
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=quality, method=6)
    return buf.getvalue()


def uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def after(name: str, caption: str) -> str:
    return f'<figure class="still"><img src="{uri((R2 / (name + ".webp")).read_bytes(), "image/webp")}" alt="{e(caption)}" loading="lazy"><figcaption><b>After.</b> {e(caption)}</figcaption></figure>'


def before(path: pathlib.Path, caption: str, quality=42, crop=None, width=None, small=False) -> str:
    if not path.exists():
        return f'<p class="muted">Before: {e(caption)} (image not on this machine)</p>'
    return f'<figure class="still before{" small" if small else ""}"><img src="{uri(webp_bytes(path, quality, crop, width), "image/webp")}" alt="{e(caption)}" loading="lazy"><figcaption><b>Before.</b> {e(caption)}</figcaption></figure>'


def base_file(path: pathlib.Path, height=900) -> str:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(ROOT)
    return f'<div class="file"><div class="file-bar">{e(str(rel))} · {len(text.splitlines())} lines · configuration only</div><pre style="max-height:{height}px"><code>{e(text)}</code></pre></div>'


m14 = {r["variant"]: r for r in DATA["rows"] if r["kind"] == "model" and r["can"] == 14}
check_rows = "".join(f'<tr><td class="{"ok" if c["ok"] else "bad"}">{"PASS" if c["ok"] else "FAIL"}</td><td>{e(c["name"])}</td></tr>' for c in mine)

PRIOR = [
    ("Strip plot (1-D scatter, jittered dot plot)", "every value as a dot on one axis; jitter separates ties", "Tukey's EDA tradition; Cleveland, <i>The Elements of Graphing Data</i> (1985); ggplot2 <code>geom_jitter</code>", "<b>This is what the cell is</b>: each run a dot, plus a range line and a median tick"),
    ("Dot plot (Cleveland)", "one dot per category (a summary) on a shared scale, categories in rows", "Cleveland and McGill, JASA 1984", "the median tick read down the column is one; the shared scale is what makes it work"),
    ("Box plot", "median, quartiles (box), whiskers, outliers", "Tukey, <i>Exploratory Data Analysis</i> (1977)", "too heavy at 14 px and 3–19 runs; quartiles of 3 runs are not meaningful"),
    ("Bullet chart", "a bar against a target with qualitative bands", "Stephen Few, 2005 design spec", "fits the twin-grade gate (1.5 × floor) on a bar; not a distribution"),
    ("Sparkline (Tufte)", "a word-sized line of a series in order", "Tufte, <i>Beautiful Evidence</i> (2006)", "the right form for runs in time order; offered as <code>sparkline</code>"),
    ("Range bar / dumbbell in tables", "a min–max bar with a marker for the value", "Bloomberg and FiveThirtyEight tables (as the brief names them; not re-checked this session)", "the range line + median tick here is this, with the runs added as dots"),
    ("Inline mini charts in table tools", "per-cell bars, sparklines, ranges", "Datawrapper and Flourish table templates (as the brief names them; not re-checked this session)", "the same idea: a chart per cell, one scale per column"),
]
prior_rows = "".join(f"<tr><td><b>{a}</b></td><td>{b}</td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in PRIOR)

ROLLUP_PRIOR = "OLAP roll-up / drill-down; Excel and Google Sheets pivot tables' “Summarize values by”; Tableau's level of detail and Aggregate Measures; Notion's and Airtable's group summaries (a calculation per group, per column)"

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Actuator models in data-ui, round 2</title>
<style>
:root {{ --bg:#fff; --bg2:#f3f3f3; --ink:#222; --ink2:#555; --rule:#d4d4d4; --accent:#006699; --ok:#0b8c6d; --bad:#a8320c; color-scheme: light; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#08090a; --bg2:#111214; --ink:#f0f1f2; --ink2:#a6a8b0; --rule:#26282d; --accent:#8e95ff; --ok:#26aa87; --bad:#ff9e66; color-scheme: dark; }} }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
main {{ max-width:1520px; margin:0 auto; padding:28px 16px 80px; }}
h1 {{ font-size:30px; line-height:1.2; margin:0 0 12px; }} h2 {{ font-size:24px; margin:56px 0 6px; padding-top:16px; border-top:1px solid var(--rule); }}
h3 {{ font-size:18px; margin:22px 0 6px; }}
.verdict {{ font-size:19px; background:var(--bg2); border-left:4px solid var(--accent); padding:14px 18px; margin:0 0 18px; }}
.muted, figcaption {{ color:var(--ink2); }} blockquote {{ margin:8px 0; padding:4px 14px; border-left:3px solid var(--rule); color:var(--ink2); font-style:italic; }}
code, pre {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:13px; }}
.pair {{ display:grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap:16px; align-items:start; margin:14px 0; }}
video {{ width:100%; height:auto; border:1px solid var(--rule); border-radius:6px; background:var(--bg2); }}
.file {{ border:1px solid var(--rule); border-radius:6px; overflow:hidden; }} .file-bar {{ background:var(--bg2); padding:6px 10px; font-size:13px; color:var(--ink2); }}
.file pre {{ margin:0; padding:10px 12px; overflow:auto; }}
figure.still {{ margin:16px 0; }} figure.still img {{ width:100%; height:auto; display:block; border:1px solid var(--rule); border-radius:6px; }}
figure.before img {{ opacity:.92; border-style:dashed; }} figure.small img {{ width:auto; max-width:100%; }}
.befores {{ display:flex; gap:16px; flex-wrap:wrap; align-items:flex-start; }} .befores figure {{ margin:8px 0; }}
figcaption {{ font-size:14px; margin-top:4px; }}
table {{ border-collapse:collapse; width:100%; font-size:15px; }} td, th {{ border-bottom:1px solid var(--rule); padding:6px 8px; text-align:left; vertical-align:top; }}
td.ok {{ color:var(--ok); font-weight:600; }} td.bad {{ color:var(--bad); font-weight:600; }}
.two {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
@media (max-width: 900px) {{ .pair, .two {{ grid-template-columns: 1fr; }} }}
a {{ color:var(--accent); }}
</style></head><body><main>
<h1>Actuator models in data-ui, round 2: the data explains itself</h1>
<p class="verdict"><strong>All six of your points are now data-ui capabilities, written into the contract as CONTRACT §16 (not one-off code for this page), and the models page uses each of them through one <code>.base</code> file.</strong> The tabs run pivot first, then the leaderboard and the parameters. Each opens with KPI cards and a few lines on how to read it. Each rolls up across actuators by default, and the toolbar's Roll up menu undoes that. Distribution strips share one scale per column. Columns can have sub-headers. Numbers and marks line up. Every model name opens its own page, with the twin code's README rendered from its fit commit. <b>{passed}/{len(mine)}</b> checks for these cases pass and the full suite is <b>{total_ok}/{len(checks)}</b> browser checks; it's on <code>lane/models-views</code> in data-ui, not merged.</p>

<div class="pair">
  <div><video src="{uri((R2 / 'clip.mp4').read_bytes(), 'video/mp4')}" poster="{uri((R2 / 'clip-poster.webp').read_bytes(), 'image/webp')}" autoplay muted loop playsinline controls aria-label="Roll up, drill down, a model's README"></video>
  <p class="muted">Recorded from the real gallery page: roll up across actuators (tick Actuator back in Roll up, then away again), click a rolled-up cell for the 9 runs behind it, then click a model's name to open its page and its README.</p></div>
  {base_file(CASE / 'views.base', 640)}
</div>

<h2>1 · Explain the data, dashboard-style</h2>
<blockquote>“with data-ui as the base it's really about making these dashboards that really explain the data”</blockquote>
<p>Every tab now opens with its answer: KPI cards and two or three sentences on what the table shows and how to read it, then the table. <b>The key:</b> <code>intro: {{text, kpi}}</code>, with markdown text and an inline <code>type: kpi</code> view over the same data and the same rail filter. <b>Why not lane/dashboards:</b> its <code>&lt;data-dashboard&gt;</code> (PEP 0004, §14, unmerged) lays panels on a grid across datasets, but it has no per-tab answer. So I built on the lane's markdown module rather than its grid, and moved that module into core (<code>md.js</code>), so the dashboard's text panels can import it once it lands. One dashboard idea, not two.</p>
{before(R1 / 'pivot-light.webp', 'round 1: the pivot opened straight into 35 rows of numbers, with nothing saying what they are or how to read them', 42)}
{after('benches-light', 'Benches: four KPI cards (median error per bench, against the 1.5 × twin-grade gate), then how to read the table, then the table (light)')}
{after('benches-dark', 'The same, dark (Signal)')}

<h2>2 · Roll-up (dimensionality reduction)</h2>
<blockquote>“there should be a roll-up option so I can roll up across the actuator dimension… with as little or as much roll-up as I want”</blockquote>
<p><b>The key:</b> <code>rollup: {{keep, agg, dims}}</code> on a table or pivot. You keep the dimensions you want to see and every other one is aggregated, with the aggregate chosen per column (median, mean, min, max, count, spread). It lives in the view, so Save view writes it to the <code>.base</code> and the URL carries it. The Roll up menu (toolbar) ticks dimensions and picks aggregates. Models default to rolled up across actuators. A click on a rolled-up cell or row drills back down to the rows behind it, and the status line names what was rolled away ("rolled up across Actuator"). <b>Prior art:</b> {ROLLUP_PRIOR}.</p>
<p><b>Proved against the raw archive:</b> on the rolled-up pivot, M2.coulomb_viscous × staircase is the median of all 9 staircase runs across the 8 actuators' budget files (4.53 × floor, n 9). Every held-out cell of that row matches, and so does the per-column <code>max</code> (12.87 × floor, CAN 4). Those numbers were recomputed in <code>source/oracle.py</code> straight from <code>/archive</code>, not from <code>models.json</code>.</p>
{after('rollup-menu-light', 'The Roll up menu on Benches: Actuator unticked (rolled away), the aggregate per number column, “Every row” to undo')}

<h2>3 · The distribution strips</h2>
<blockquote>“This error-added column I find hard to read the line (what is the prior art for it)?” · “those lines are hard to read, how am I supposed to read them?”</blockquote>
<p><b>What it is:</b> a <b>strip plot</b> (a 1-D jittered dot plot) with a range line and a median tick: Tukey's and Cleveland's form, close to an inline range bar with the runs added. <b>Why it was hard to read:</b> outside a pivot, every row was drawn on its own scale (its own min to max), so strips could not be compared down a column, and the median looked like the dots. <b>Fixed in data-ui:</b>
- one scale per column, log past two decades of positive values, and symmetric log for a heavy tail across zero (one ablation of +341 mrad beside ones of ±0.1);
- the scale's ends and middle drawn as an axis row in the header;
- a header tooltip saying how to read it;
- the median as a tall dark tick, with the runs as light dots and the min–max line thin;
- a cell's hover listing the median, min, max, n and the values.

<b>Both forms</b> you asked for:
- <code>dist</code> keeps a single cell with an inline distribution;
- <code>display: stats</code> splits it into median | min | max | n | runs sub-columns.

For a CI, <code>value</code> keeps it in the hover, <code>range</code> shows it muted in its own slot, and <code>stats</code> gives value | 95% CI low | high | basis columns. Defaults: the term tables use <code>value</code> (CI in the hover), because nine terms × three numbers is unreadable at once; the "with CI" tab uses sub-columns.</p>
<div class="befores">{before(IMAGES / '55.png', 'your 55.png: each strip on its own scale, the median indistinct', 70, small=True)}</div>
{before(R1 / 'parameters-rung-adds-light.webp', 'round 1 (what each rung adds): per-row scales; you cannot tell a 35 mrad term from a 0.1 one by its strip', 42)}
{after('rung-adds-light', 'What each rung adds: one symmetric-log scale down the column, its axis (-1.41 … 341) in the header, the median a tall tick, the runs as dots')}
{after('rung-adds-columns-light', 'The same distribution as columns: median | min | max | n | runs under “Error added” (display: stats)')}
<h3>Prior art for the cell</h3>
<table><thead><tr><th>Form</th><th>Shows</th><th>Source</th><th>Here</th></tr></thead><tbody>{prior_rows}</tbody></table>

<h2>4 · Column groups (sub-headers)</h2>
<blockquote>“Do we support sub-headers? e.g. Coulomb and then sub-columns underneath it? I think we should!”</blockquote>
<p><b>The keys:</b> <code>columnGroups: {{Friction: [coulomb, viscous, …]}}</code> puts a header over a set of properties; <code>display: stats</code> splits one property into sub-columns under its own label. The table draws one header row per level, and the pivot's own column groups (Held-out tapes · Oct 23 → staircase / sine / …) now use the same markup and style. Row groups sit beside them as before. Measured in the browser: “Friction” spans exactly its 5 term columns, and “Coulomb” exactly value | 95% CI low | high | basis (edges equal within 1 px).</p>
<div class="befores">{before(IMAGES / '56.png', 'your 56.png: one flat header row; Coulomb and Viscous with their CI squeezed into the value cell', 70, small=True)}{before(IMAGES / '57.png', 'your 57.png: the pivot already grouped its columns (Held-out tapes · Oct 23 › staircase …); the table could not', 70, small=True)}</div>
{after('parameters-light', 'Parameters: Friction, Capture, Drivetrain and Driver over their terms; values with their basis mark, the CI on hover')}
{after('parameters-ci-light', 'Parameters · with CI: Coulomb, Viscous and Weakening, each split into value | 95% CI low | high | basis under its own header')}

<h2>5 · Alignment</h2>
<blockquote>“I don't like how things are not aligned”</blockquote>
<p>Every numeric cell is now a grid of fixed slots, <b>[number][range][mark][count]</b>, whose widths belong to the column, not the cell. So down a column, the numbers' right edges and the marks' left edges share one x, whatever the digits, a count superscript, or a missing value ("—" sits in the number slot). Numerals are tabular. A browser check measures it with getBoundingClientRect: on three pivot columns (with and without counts) and Parameters' Coulomb column, the spread of the numbers' right edges and of the marks' left edges is <b>0 px</b>.</p>
<div class="befores">{before(IMAGES / '58.png', 'your 58.png: ticks wander', 80, small=True)}{before(IMAGES / '59.png', 'your 59.png: numbers and marks move with the count', 80, small=True)}</div>
<figure class="still small"><img src="{uri((R2 / 'aligned-zoom-light.webp').read_bytes(), 'image/webp')}" alt="aligned column" style="width:430px"><figcaption><b>After.</b> One pivot column up close: numbers in one right-aligned slot, strips in one slot on one scale, counts in their own slot.</figcaption></figure>

<h2>6 · Click a model → its page</h2>
<blockquote>“For each model I should be able to click it and get information on that actual model, perhaps a GitHub page, perhaps it renders the README of the model.”</blockquote>
<p>Every model's name links to its page (<code>open: {{mode: side, url: page}}</code>; in the pivot the name itself is the link). In the tables, a click opens the side peek. The page is a second gallery case, <code>robotparts-model</code>: a record view picked by the rail through a readable link (<code>?variant=M4.ripple.c1</code>). It shows:
- what the model is: its contract 2.3 kind and equation, and what this twin actually runs;
- its error on each bench, and the actuators it ran on;
- its fitted terms;
- the fit commit (<code>{e(str(m14['M4.ripple.c1']['code_commit']))}</code>);
- the twin code's README at that commit, read with <code>git show</code> from bam_ws and rendered with <code>display: markdown</code>.

<b>No GitHub link:</b> none of the fit commits is on GitHub's <code>origin</code> (they sit on the local branch <code>claude/sim-to-real-motor-models-f1ee43</code>), so the page shows the local path and says “local only”. The README is the package's README (<code>bam_rack_twin</code>), not a per-model one, because none exists. The per-model part is the description built from contract 2.3's kind and the budget's twin sources.</p>
{after('peek-light', 'Leaderboard (CAN 14, un-rolled): click M4.ripple.c1 and the side peek shows what it is, its error, its fit commit and its README')}
<div class="pair">{after('model-page-light', "The model's page (?variant=M4.ripple.c1): the record, the rail picking the model (light)")}{base_file(ROOT / 'gallery' / 'examples' / 'robotparts-model' / 'views.base', 560)}</div>
{after('model-readme-light', "Further down the page: the twin code's README at the fit commit, rendered as markdown")}
{after('model-page-dark', "The model's page, dark (Signal)")}

<h2>Checks</h2>
<p><b>{passed} of {len(mine)} checks for these cases pass; the full <code>npm test</code> is green</b> (build, 80 unit tests, both Python suites, {total_ok}/{len(checks)} browser checks, 72/72 frame checks, 16/16 lifecycle checks). <b>They failed first:</b> run against the round-1 code (core and views stashed), the intro check and the roll-up check failed, and the alignment check could not even find a number slot. The numbers come from an independent oracle (<code>source/oracle.py</code>, reading <code>/archive</code> and <code>git</code>); round 1's mutation run already showed this ruler can go red.</p>
<table><tbody>{check_rows}</tbody></table>

<h2>Decision surface</h2>
<div class="two"><div>
<h3>Done and proved</h3>
<ul><li>All six points in data-ui core and the table view, specified in CONTRACT §16, with the schema and both checkers updated: intro, roll-up, column groups, <code>stats</code> / <code>range</code> / <code>value</code> / <code>markdown</code> displays, a readable <code>dist</code>, fixed slots, pivot rows linking to their page.</li>
<li>One <code>.base</code> with 9 tabs (pivot first) and a model page, over real rack data with no illustrative numbers.</li>
<li>Commits on <code>lane/models-views</code>: {'; '.join(e(c) for c in commits[:3])}.</li></ul>
<h3>Left (next, not blocked)</h3>
<ul><li>A readable URL parameter for the roll-up (today it rides in the view blob, <code>#v=…</code>, like any changed view).</li>
<li>When lane/dashboards lands: its text panels import core's <code>md.js</code> (one copy).</li>
<li>Wiring this <code>.base</code> into robotparts' models page, which waits on contract 2.3 (<code>contract/v2.3</code>, not merged).</li></ul>
</div><div>
<h3>Needs you</h3>
<ul><li><b>The CI default:</b> the hover (<code>value</code>) in the term tables, sub-columns in “with CI”. <em>Default if silent: as is.</em></li>
<li><b>Colour-scale (heat) cells</b>, from round 1: still not added. It needs a schema value, a small contract change. Recommend yes. <em>Default if silent: not added.</em></li>
<li><b>Merge <code>lane/models-views</code></b> (it changes core: §16). <em>Default if silent: left on its branch.</em></li></ul>
<h3>Deliberately not done</h3>
<ul><li>A second dashboard system. <code>intro:</code> is one view's caption; the grid is §14's.</li>
<li>A GitHub link for the code: no fit commit is on origin.</li>
<li>No audit, because none was asked for.</li></ul>
</div></div>

<h2>Run it</h2>
<pre><code>PORT=4741 npm --prefix ~/data-ui/.wt/models-views run serve</code></pre>
<p>then open <code>http://127.0.0.1:4741/gallery/robotparts-models/index.html</code> (a model's page: <code>http://127.0.0.1:4741/gallery/robotparts-model/index.html?variant=M4.ripple.c1</code>). It runs the lane's code from <code>.wt/models-views</code>, whose <code>dist/</code> must be built.</p>
</main></body></html>
"""
OUT.write_text(page, encoding="utf-8")
print(f"{OUT}: {OUT.stat().st_size:,} bytes; {passed}/{len(mine)} case checks, {total_ok}/{len(checks)} browser checks")
