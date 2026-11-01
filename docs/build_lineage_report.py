#!/usr/bin/env python3
"""Build reports/data-ui-lineage-2026-10-27.html: the lineage view's review page (light and dark, no network).

    python3 docs/build_lineage_report.py --media MEDIA_DIR --checks CHECKS.json --mutations MUTATIONS.json \
        --npm NPM_TEST.log --out ~/data-ui/reports/data-ui-lineage-2026-10-27.html

Every number on the page comes from a file a run wrote (the browser checks' checks.json, the mutation run's
mutations.json, `npm test`'s log) or from running the view's own layout.js on the cases' data here; the hero clip and
stills are docs/capture_lineage.py's recordings of the built site. The media stay files beside the page (referenced
relative to it, in the gitignored reports/media/), so the page itself is a small text page.
WHY a big type scale (17 px body): Zach said earlier reports were too small to read."""

from __future__ import annotations

import argparse
import html
import json
import os
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
e = html.escape

KEYS = [
    ("parents", "a property listing parent ids", "required", "the only source of edges; first id = tree parent, the rest are splices (dashed)"),
    ("x", "a property", "the depth", "one column / ring per distinct value, in order (rounds, rungs, generations)"),
    ("xLabel", "a property", "the x value", "the column's name (R5 for round_n 5)"),
    ("image", "a property", "none", "a picture per mark; a row with none draws its label"),
    ("label", "a property", "titleProperty", "the mark's label and the path panel's names; cut with … to the column, full text on hover"),
    ("focus", "a row id", "none", "it and every ancestor (over all parents) are the trunk; the path panel lists them"),
    ("kept", "{property: [values]}", "none: nothing extinct", "alive = kept, on the trunk, or has an alive child; everything else is extinct"),
    ("extinct", "show | collapse", "collapse", "show: hairline stubs; collapse: each fan folds into +N (counted by subtree)"),
    ("layout", "rectangular | radial", "rectangular", "x left to right, or a ring per x value"),
]

STOCK = [
    ("Tree layout (leaf spacing, parent at the mean)", "donor: d3-hierarchy inside React (layout.ts)", "d3-hierarchy 3.1.2 hierarchy + cluster", "heaviest child in the middle; separation 1 / 1.4"),
    ("Splice curves", "donor: d3-shape", "d3-shape 3.2.0 linkHorizontal, linkRadial", "dashed, from each extra parent's mark to the child's"),
    ("Pan, zoom, pinch", "donor: hand-rolled wheel zoom and drag (index.tsx)", "d3-zoom 3.0.0 on d3-selection 3.0.0", "wheel zooms about the pointer; drag pans 1:1; pinch on touch"),
    ("Side panel", "donor: a fold-only card panel", "data-ui core makeResizable (§11)", "drag, remembered width, double-click reset, keyboard, fold"),
    ("Record detail", "donor: its own Card.tsx", "data-ui core peek (§13, §14)", "click opens; parents are trail links"),
    ("Filters, search, facets", "none (one brand at a time)", "data-ui core row model and rail", "the tree is drawn from input.rows"),
    ("Rendering", "React 19 components (Tree.tsx)", "unchanged (ours): SVG markup in the view's element", "no React in this bundle (79 KB)"),
]


def counts():
    """Per brand / the ladder: rows -> marks + groups, from the view's own layout.js on the cases' data."""
    js = r"""
import('./packages/views/lineage/src/layout.js').then(({ lineageSpec, buildLineage }) => {
  const fs = require('fs');
  const out = [];
  const p = JSON.parse(fs.readFileSync('gallery/examples/brand-lineage/proposals.json'));
  const spec = lineageSpec({ lineage: { parents: 'parents', x: 'round_n', focus: 'robotparts/r16-02', kept: { status: ['picked', 'liked'] } } });
  for (const b of ['robotparts', 'ObjectDB', 'BAM', 'Jidoka']) {
    const rows = p.rows.filter((r) => r.brand === b);
    const c = buildLineage(rows, spec).counts, s = buildLineage(rows, spec, { extinct: 'show' }).counts;
    out.push({ name: b, rows: rows.length, marks: c.shown, groups: c.groups, folded: c.hidden, edges: s.edges, splices: s.splices });
  }
  const l = JSON.parse(fs.readFileSync('gallery/examples/model-lineage/ladder.json'));
  const ls = lineageSpec({ lineage: { parents: 'parents', x: 'rung', focus: 'm4-ripple-c1', kept: { status: ['measured'] } } });
  const c = buildLineage(l.rows, ls).counts, s = buildLineage(l.rows, ls, { extinct: 'show' }).counts;
  out.push({ name: 'model ladder', rows: l.rows.length, marks: c.shown, groups: c.groups, folded: c.hidden, edges: s.edges, splices: s.splices });
  console.log(JSON.stringify(out));
});"""
    done = subprocess.run(["node", "-e", js], cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    return json.loads(done.stdout)


CSS = """
:root { --bg: #ffffff; --fg: #17181a; --muted: #5d6066; --rule: #e4e5e8; --subtle: #f5f6f7; --accent: #1f5fd1; --good: #1d7a43; --bad: #b42318; color-scheme: light; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg: #0e0f11; --fg: #e8e9eb; --muted: #9a9ea6; --rule: #2a2c31; --subtle: #17191c; --accent: #7aa7ff; --good: #5cc98a; --bad: #ff8a80; color-scheme: dark; } }
:root[data-theme="dark"] { --bg: #0e0f11; --fg: #e8e9eb; --muted: #9a9ea6; --rule: #2a2c31; --subtle: #17191c; --accent: #7aa7ff; --good: #5cc98a; --bad: #ff8a80; color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 17px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1480px; margin: 0 auto; padding: 32px 16px 80px; }
h1 { font-size: 32px; margin: 0 0 6px; } h2 { font-size: 24px; margin: 44px 0 10px; border-top: 1px solid var(--rule); padding-top: 24px; }
h3 { font-size: 18px; margin: 22px 0 6px; }
.verdict { font-size: 20px; margin: 8px 0 18px; } .muted { color: var(--muted); }
code { font: 14px ui-monospace, "SF Mono", Menlo, monospace; background: var(--subtle); padding: 1px 5px; border-radius: 4px; }
pre { font: 14px ui-monospace, Menlo, monospace; background: var(--subtle); padding: 12px 14px; border-radius: 8px; overflow-x: auto; white-space: pre-wrap; word-break: break-all; }
video, img { max-width: 100%; height: auto; border: 1px solid var(--rule); border-radius: 8px; display: block; background: #fff; }
figure { margin: 0; } figcaption { color: var(--muted); font-size: 15px; margin: 6px 0 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 560px), 1fr)); gap: 20px; }
.pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 16px; }
.wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 15px; } th, td { text-align: left; vertical-align: top; padding: 7px 10px; border-bottom: 1px solid var(--rule); }
th { background: var(--subtle); font-weight: 600; } td.num { text-align: right; font-variant-numeric: tabular-nums; }
.ok { color: var(--good); font-weight: 600; } .no { color: var(--bad); font-weight: 600; }
ul.tight li { margin: 4px 0; }
.cmd { display: block; }
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", required=True)
    ap.add_argument("--checks", required=True)
    ap.add_argument("--mutations", required=True)
    ap.add_argument("--npm", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sha", default="")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    media = pathlib.Path(a.media)
    rel = os.path.relpath(media, out.parent)
    m = lambda name: f"{rel}/{name}"
    checks = json.loads(pathlib.Path(a.checks).read_text())
    muts = json.loads(pathlib.Path(a.mutations).read_text())
    npm = pathlib.Path(a.npm).read_text(errors="replace")
    summary = npm[npm.rfind("== summary"):].strip() if "== summary" in npm else "(no summary in the log)"
    passed = sum(c["ok"] for c in checks)
    browser = re.findall(r"(\d+)/(\d+) browser checks pass", npm)
    unit = re.findall(r"^# (pass|fail) (\d+)", npm, re.M)
    npm_ok = "FAIL" not in summary
    cs = counts()
    rp = next(c for c in cs if c["name"] == "robotparts")

    rows_counts = "".join(f"<tr><td>{e(c['name'])}</td><td class=num>{c['rows']}</td><td class=num>{c['marks']}</td><td class=num>{c['groups']}</td>"
                          f"<td class=num>{c['folded']}</td><td class=num>{c['edges']}</td><td class=num>{c['splices']}</td></tr>" for c in cs)
    keys = "".join(f"<tr><td><code>{e(k)}</code></td><td>{e(v)}</td><td>{e(d)}</td><td>{e(w)}</td></tr>" for k, v, d, w in KEYS)
    stock = "".join(f"<tr><td>{e(a1)}</td><td>{e(b)}</td><td>{e(c)}</td><td>{e(d)}</td></tr>" for a1, b, c, d in STOCK)
    check_rows = "".join(f"<tr><td class={'ok' if c['ok'] else 'no'}>{'PASS' if c['ok'] else 'FAIL'}</td><td>{e(c['name'])}</td>"
                         f"<td><code>{e(str(c.get('value'))[:180])}</code></td></tr>" for c in checks)
    def caught(x):
        names = [e(r) for r in x["red"][:3]] + [f"unit: {e(r)}" for r in x.get("unit_red", [])[:2]]
        return "<br>".join(names) or "<span class=no>survived</span>"

    mut_rows = "".join(f"<tr><td>{e(x['mutation'])}</td><td class=num>{len(x['red'])} / {x['total']}</td><td class=num>{len(x.get('unit_red', []))}</td>"
                       f"<td>{caught(x)}</td></tr>" for x in muts)
    killed = sum(1 for x in muts if x["red"] or x.get("unit_red"))

    def fig(name, cap, alt):
        return f'<figure><img src="{m(name)}" alt="{e(alt)}" loading="lazy"><figcaption>{cap}</figcaption></figure>'

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>data-ui lineage view</title><style>{CSS}</style></head><body><main>
<h1>Lineage: a tree of life in data-ui</h1>
<p class="verdict"><b>{"Built and proved" if npm_ok and passed == len(checks) else "Built, with failures listed below"}: <code>type: lineage</code> draws any rows that name their parents as a tree of life, with every data-ui filter, search and peek for free.</b> On <code>lane/lineage</code>{f" @ <code>{e(a.sha)}</code>" if a.sha else ""}, <b>not merged</b>; {passed}/{len(checks)} measured lineage checks pass, {killed}/{len(muts)} mutations caught, <code>npm test</code> {"green" if npm_ok else "<span class=no>not green</span>"}.</p>
<p class="muted">Cases: <code>brand-lineage</code> (Brandbook's 319 real proposals; robotparts {rp['rows']} rows fold to {rp['marks']} marks + {rp['groups']} "+N") and <code>model-lineage</code> (the GIM4305-10 model ladder M0→M5, label marks, to prove the view is generic). Focus: robotparts' shipped R16-02.</p>

<h2>Toggling extinct, then clicking through to a proposal</h2>
<video autoplay muted loop playsinline controls poster="{m('robotparts-collapse-light.png')}"><source src="{m('hero.mp4')}" type="video/mp4"><img src="{m('hero.gif')}" alt="The robotparts tree: Show extinct grows it from 24 marks to 205, Fit, fold again, click R16-02, the peek opens, follow its parent."></video>
<p class="muted">Recorded headlessly from the built gallery page (the red dot is the pointer). The robotparts tab opens folded (13 alive marks, the bold trunk R1 → R16-02, eleven "+N"); Show extinct draws all 205; Fit; fold again; click R16-02 and the peek opens with its round, status, note and its report's path; its parent is a link, and following it opens the proposal it came from (the peek's trail). <a href="{m('hero.gif')}">GIF</a></p>

<h2>Try it</h2>
<pre class="cmd">PORT=4617 npm --prefix ~/data-ui/.wt/lineage run serve</pre>
<p class="muted">then open <code>http://127.0.0.1:4617/gallery/brand-lineage/</code> (and <code>/gallery/model-lineage/</code>). It serves the lane's built <code>dist/site</code>; lives on lane <code>lane/lineage</code>, gone from this path after merge or sweep.</p>

<h2>The decision: a new <code>type: lineage</code>, not a layout of <code>graph</code></h2>
<ul class="tight">
<li><b>Its keys mean nothing to a graph:</b> an ordinal x axis, a focus trunk, kept and extinct, rings. A graph with these as options would be two views behind one name.</li>
<li><b>A different stock part:</b> d3-hierarchy's <code>cluster</code> on SVG (what the donor measured), not dagre in React Flow; the bundle is 79 KB with no React.</li>
<li><b><code>layout</code> was taken:</b> the schema's <code>layout</code> is the graph's <code>{{algorithm, direction}}</code> object, so <code>layout: radial</code> beside it would be one key with two meanings. And Bases' <code>order</code> is the visible properties, so the x axis is <code>x</code>.</li>
<li><b>One block, as <code>kpi:</code> and <code>chart:</code> are:</b> <code>lineage: {{…}}</code>, written into CONTRACT §21 and <code>schemas/view.schema.json</code> (<code>$defs.lineage</code>); both checkers check every property in it against the data.</li>
</ul>
<h3>The keys</h3>
<div class="wrap"><table><tr><th>key</th><th>value</th><th>default</th><th>does</th></tr>{keys}</table></div>
<pre>views:
  - type: lineage
    name: robotparts
    filters: 'brand == "robotparts"'
    lineage:
      parents: parents
      x: round_n
      xLabel: round
      image: thumb
      label: name
      focus: robotparts/r16-02
      kept: {{ status: [picked, liked] }}
      extinct: collapse
      layout: rectangular</pre>

<h2>Light and dark</h2>
<div class="grid">
{fig('robotparts-collapse-light.png', 'robotparts, folded: the trunk R1 → R2 → R8 → R9 → R11 → R16-02 in the accent; the path panel on the right (drag its edge, ⟩ folds it).', 'robotparts lineage light')}
{fig('robotparts-collapse-dark.png', 'The same, dark: the marks keep paper-white wells (the case skin), as logo-rounds does.', 'robotparts lineage dark')}
{fig('robotparts-radial-light.png', 'robotparts radial, every proposal: a ring per round, each ring far enough out that its closest marks stay apart; dashed splices from rounds 13 and 14.', 'radial light')}
{fig('robotparts-radial-dark.png', 'Radial, dark.', 'radial dark')}
{fig('robotparts-show-light.png', 'Show extinct: all 205 marks; extinct lines are hairline stubs.', 'show extinct')}
{fig('robotparts-peek-light.png', 'Click a mark: the shared peek, its parents as links, its report path as plain text.', 'peek')}
{fig('every-brand-light.png', 'Every brand: 319 rows as one forest; the rail filters it like any view.', 'every brand')}
{fig('model-ladder-light.png', 'Not a brand: the actuator model ladder with label marks; x is the rung; the c1 soft-friction twin splices in M2.', 'model ladder light')}
{fig('model-radial-dark.png', 'The ladder, radial and dark; focus on the splice, so the trunk takes both parents.', 'model radial dark')}
</div>
<h3>Phone, 390 px</h3>
<div class="pair">{fig('phone-light.png', 'Light: the path panel stacks under the tree; no sideways scroll.', 'phone light')}{fig('phone-dark.png', 'Dark.', 'phone dark')}</div>

<h2>The real data, folded</h2>
<div class="wrap"><table><tr><th>data</th><th>rows</th><th>marks (collapse)</th><th>+N groups</th><th>rows folded</th><th>tree edges</th><th>splice curves</th></tr>{rows_counts}</table></div>
<p class="muted">From <code>packages/views/lineage/src/layout.js</code> run on each case's data while this page was built. Kept = Zach's picked or liked (brands), measured (models). Brandbook's donor measured 288 → 56 on synthetic data; robotparts' real tree folds harder because only 13 of 205 proposals were picked or liked or lie on the trunk. Jidoka has no pick or like yet, so all 10 fold into one "+10". Data: Brandbook <code>brands.json</code> 2026-10-26 23:51 (319 proposals), copied, thumbnails extracted to files (1.3 MB); report paths are plain text, never links.</p>

<h2>Stock parts</h2>
<div class="wrap"><table><tr><th>Element</th><th>Before</th><th>Off-the-shelf part</th><th>Behaviour that must survive</th></tr>{stock}</table></div>

<h2>Proof</h2>
<h3>Measured browser checks ({passed}/{len(checks)})</h3>
<p class="muted">Committed before the view (fd6e17e), so they failed first. Each compares the page (getBoundingClientRect; a path's own ends through getScreenCTM) with an oracle computed in Python from the case JSON, never from the view's code.</p>
<div class="wrap"><table><tr><th></th><th>check</th><th>measured</th></tr>{check_rows}</table></div>
<h3>Mutation tests: do the checks go red? ({killed}/{len(muts)} caught)</h3>
<p class="muted">Each bug was put into the committed source, rebuilt, run against both cases' browser checks and the layout's unit tests, then reverted. "+N counts children" is caught only by the unit test: no folded row in these two cases has folded descendants of its own, so the real data cannot tell the two counts apart; the unit test's hand-made forest can. The first mutation run exposed a hole in the overlap check (a collision shrank both marks to nothing), so "every mark stays visible" was added; it then caught real 1.3 px marks on inner radial rings, now fixed (each ring sized for its closest pair).</p>
<div class="wrap"><table><tr><th>bug put into the view</th><th>browser checks red</th><th>unit tests red</th><th>what caught it</th></tr>{mut_rows}</table></div>
<h3><code>npm test</code></h3>
<pre>{e(summary)}</pre>
<p class="muted">{f"Whole-suite browser checks: {browser[-1][0]}/{browser[-1][1]}." if browser else ""} {"Unit: " + ", ".join(f"{k} {v}" for k, v in unit) if unit else ""}</p>

<h2>Where it stands</h2>
<h3>Done and proved</h3>
<ul class="tight">
<li><code>type: lineage</code> (packages/views/lineage), CONTRACT §21, the schema and both checkers, the peek's relation trail for <code>lineage.parents</code>.</li>
<li>Edges only from <code>parents</code>, measured equal to the data's pairs in both layouts, filtered and unfiltered; splices dashed; the trunk; extinct stubs and "+N" counts; pan and zoom; the path panel's drag, memory, reset and fold; light and dark at 1280 and 390 px.</li>
<li>Two cases: <code>brand-lineage</code> (real Brandbook data) and <code>model-lineage</code> (the model ladder).</li>
</ul>
<h3>Left</h3>
<ul class="tight">
<li>Merge: the data-ui integrator's call. §21 may need renumbering if §15-§19 land differently. Shared files touched (each a few lines): <code>schemas/view.schema.json</code>, <code>packages/core/src/check.js</code>, <code>tools/check_views.py</code>, <code>packages/core/src/open.js</code>, <code>package.json</code> + lock (declares four d3 packages already installed).</li>
<li>Not next but possible: a "kept" picker in the Layout menu (today <code>kept</code> is written in the file), and a minimap for 1,000+ row trees.</li>
</ul>
<h3>Needs Zach</h3>
<ul class="tight">
<li><b>Default <code>extinct</code>:</b> collapse (the robotparts tab opens at 24 marks, not 205). Recommendation: keep collapse as the default. If you say nothing, it stays.</li>
<li><b>Report links:</b> per the orchestrator, the round's report shows as a plain path (never a <code>file://</code> link) on the published case. Recommendation: keep it that way until reports are hosted. If you say nothing, it stays.</li>
</ul>
<h3>Deliberately not done</h3>
<ul class="tight">
<li>No edge to the forest's root and no "stem" lines between trees: they would be inferred edges.</li>
<li>Brandbook's <code>brands.json</code> was read, never edited; the model ladder's parents are authored in <code>make.py</code> with the sentence that names each one, and M5.dcmotor stays a root because no source names its base.</li>
<li>No Codex or auditor pass: none was asked for.</li>
</ul>
</main></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(out, len(page.encode()), "bytes")


if __name__ == "__main__":
    main()
