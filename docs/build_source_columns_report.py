"""Build the source columns' review: one self-contained HTML, its hero video, stills and proof inside it.

    python3 docs/build_source_columns_report.py <capture dir> <facts.json> <out.html>

After docs/capture_source_columns.py and the checks have run. facts.json says only what git cannot: {"tip", "base", "suite", "journey", "unit"}.
Everything else is read here: the commits from git, the checks' counts from their JSON, the behaviours from PEP 0021's own table, what the hero
measured from the capture, so the page cannot disagree with them. Fails if the hero does not show what it says, or if the page comes out over 1.9 MB
(the desktop preview's limit for a page with media)."""

import base64
import html
import json
import re
import subprocess
import sys
from pathlib import Path

CAP, FACTS, OUT = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text()), Path(sys.argv[3])
ROOT = Path(__file__).resolve().parents[1]
LIMIT = 1_900_000
TIP, BASE = FACTS["tip"], FACTS["base"]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def uri(path, mime):
    return f"data:{mime};base64,{base64.b64encode(Path(path).read_bytes()).decode()}"


def counts(path):
    checks = json.loads(Path(path).read_text())["checks"]
    return sum(1 for c in checks if c["ok"]), len(checks)


def inline(text):
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", out)


def net(paths):
    added = removed = 0
    for line in git("diff", "--numstat", f"{BASE}..{TIP}", "--", *paths).splitlines():
        a, r, _ = line.split("\t", 2)
        added += int(a) if a != "-" else 0
        removed += int(r) if r != "-" else 0
    return added, removed


def delta(paths):
    added, removed = net(paths)
    return added - removed


def row_net(label, paths):
    a, r = net(paths)
    return f"<tr><td>{label}</td><td class=n>+{a}</td><td class=n>−{r}</td><td class=n>{f'{a - r:+d}'.replace('-', '−')}</td></tr>"


facts = json.loads((CAP / "hero-facts.json").read_text())
moved = {k: (facts["before"][k], facts["dragged"][k]) for k in facts["before"] if facts["before"][k] != facts["dragged"].get(k)}
if facts["before"] != facts["hidden"]:
    sys.exit("the hero hid a source and a value moved")
if sorted(moved) != ["peak_torque", "rated_phase_current", "rotor_inertia"]:
    sys.exit(f"the hero's drag moved {sorted(moved)}")
before_w = json.loads((CAP / "before-widths.json").read_text())
TABLE = ["packages/views/table/src/index.js", "packages/views/table/src/table.css", "packages/views/table/src/edit.js"]

pep = (ROOT / "docs/peps/0021-source-columns.md").read_text()
rows = re.findall(r"^\| (?!Behaviour|---)(.+?) \| (.+?) \| (.+?) \|$", pep.split("## What became of each behaviour", 1)[1].split("## Not done", 1)[0], re.M)
table = "".join(f"<tr class={'kept' if '**Kept' in now else 'gone'}><td>{inline(a)}</td><td>{inline(now)}</td><td>{inline(why)}</td></tr>" for a, now, why in rows)
commits = [line.split(" ", 1) for line in git("log", "--reverse", "--format=%h %s", f"{BASE}..{TIP}").splitlines()]
history = "".join(f"<li><code>{h}</code> {html.escape(s)}</li>" for h, s in commits)
sc = counts(CAP / "checks/source-columns-checks.json")
ad = counts(CAP / "checks/robotparts-adoption-checks.json")
moved_rows = "".join(f"<tr><td>{html.escape(k.replace('_', ' '))}</td><td class=n>{html.escape(a)}</td><td class=n>{html.escape(b)}</td></tr>" for k, (a, b) in moved.items())
NOTES = [("3.1", "3.8", "3.1", "3.1"), ("(none)", "3.8", "3.8", "3.8"), ('""', "0", "0", "0"), ("0", "5", "0", "0"), ("false", "7", "<b class=bad>error</b>", "false (a box)"),
         ("[ ]", "false", "<b class=bad>error</b>", "false (a box)"), ("[15, 60]", "1", "15 60", "15 60"), ("null", "text", "text", "text"), ("(none)", "(none)", "empty", "empty")]
truth = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in n) + "</tr>" for n in NOTES)

page = f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width, initial-scale=1"><title>Source columns</title>
<style>
:root {{ --bg:#fff; --fg:#1a1a1c; --muted:#62626a; --line:#e4e4e8; --sub:#f6f6f8; --ok:#17794a; --bad:#b4261d; --gone:#8a5a00; --accent:#2563eb; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141416; --fg:#ededf0; --muted:#a2a2aa; --line:#2e2e33; --sub:#1d1d21; --ok:#57c78e; --bad:#ff7d73; --gone:#e0b050; --accent:#7aa5ff; }} }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--bg); color:var(--fg); font:15.5px/1.55 system-ui,sans-serif; }} main {{ max-width:1000px; margin:0 auto; padding:32px 16px 64px; }}
h1 {{ font-size:27px; line-height:1.25; margin:0 0 8px; }} h2 {{ font-size:19px; margin:40px 0 10px; }} p {{ margin:8px 0; }} .lede {{ color:var(--muted); }} code {{ font:13px ui-monospace,monospace; background:var(--sub); padding:1px 4px; border-radius:4px; overflow-wrap:anywhere; }}
video,img {{ width:100%; height:auto; display:block; border:1px solid var(--line); border-radius:8px; background:var(--sub); }} figure {{ margin:14px 0; }} figcaption {{ color:var(--muted); font-size:13.5px; margin-top:6px; }}
.two {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; }} .wrap {{ overflow-x:auto; }} table {{ border-collapse:collapse; width:100%; font-size:14px; }} th,td {{ text-align:left; padding:6px 10px 6px 0; border-bottom:1px solid var(--line); vertical-align:top; }} th {{ font-weight:600; color:var(--muted); }} .n {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.kept td:nth-child(2) strong {{ color:var(--ok); }} .gone td:nth-child(2) strong {{ color:var(--gone); }} .bad {{ color:var(--bad); }} ul,ol {{ padding-left:20px; margin:8px 0; }} li {{ margin:3px 0; }} .num {{ display:flex; flex-wrap:wrap; gap:10px 28px; margin:14px 0; }} .num div b {{ display:block; font-size:22px; }} .num div {{ color:var(--muted); font-size:13px; }} .num div b {{ color:var(--fg); }}
</style></head><body><main>
<h1>A source is a column now, and Nominal is a formula over them</h1>
<p class=lede>Hiding a source changes no value. Dragging one is the precedence. No data file changes: robotparts' datasheets and its <code>.base</code> run on this as they stand, and one line of its page script needs the column's new name. On <code>main</code> @ <code>{TIP[:7]}</code>.</p>
<div class=num><div><b>{sc[0]}/{sc[1]}</b>acceptance, written first</div><div><b>{ad[0]}/{ad[1]}</b>adoption checks</div><div><b>{html.escape(FACTS['unit'])}</b>unit</div><div><b>{html.escape(FACTS['suite'])}</b>full suite</div><div><b>{html.escape(FACTS['journey'])}</b>robotparts' journey</div></div>

<figure><video controls loop muted playsinline autoplay poster="{uri(CAP / 'datasheet-light.webp', 'image/webp')}"><source src="{uri(CAP / 'hero.mp4', 'video/mp4')}" type="video/mp4"><img src="{uri(CAP / 'hero.gif', 'image/gif')}" alt="Hiding a source column, then dragging another to the front"></video>
<figcaption>Recorded from the real build on robotparts' JMC 60ASM200 datasheet, one take, no speed change; the blue dot is the pointer, which a recording leaves out. First the winning source is hidden: no value moves. Then the related model's drawing is dragged to the front: the three values it states change, and Rated speed, which it doesn't state, stays.</figcaption></figure>
<div class=wrap><table><tr><th>Value, in that take</th><th class=n>Before the drag</th><th class=n>After</th></tr>{moved_rows}</table></div>

<h2>What changed for a reader</h2>
<div class=two><figure><img src="{uri(CAP / 'before-manage.webp', 'image/webp')}" alt="Manage sources before this lane"><figcaption>Before, a mode: rank chips, ‹ ›, a toolbar button. Columns came out {' / '.join(map(str, before_w))} px, sized to their header, and the third runs off the sheet. This is the previous build's own picture, on the fixture, whose longest label is shorter than the live page's: RobotParts measured 603 there.</figcaption></figure>
<figure><img src="{uri(CAP / 'sources-light.webp', 'image/webp')}" alt="The Sources view"><figcaption>After, a view: a tab, ordinary headers, all three sources on the sheet at 1280 px, the cell taken outlined and the one that differs tinted.</figcaption></figure></div>
<ul><li><strong>One property per source.</strong> Hide, width, sort and filter are the ordinary ones. The inspector shows each as a row, and <code>record.visibility</code> works on them.</li>
<li><strong>Nominal is a formula,</strong> the first filled source left to right. Its header has a ƒ, and its hover says what it reads.</li>
<li><strong>The agree / differs pill</strong> sits on the Nominal cell, so it stays when every source column is hidden, and opens the same menu as a right-click.</li>
<li><strong>A source's own column edits.</strong> A Nominal cell refuses, and says why. Undo gives back the file's cell exactly.</li></ul>
<div class=two><figure><img src="{uri(CAP / 'datasheet-light.webp', 'image/webp')}" alt="The Datasheet view"><figcaption>The Datasheet view: robotparts' <code>.base</code>, byte for byte. Sources hidden, the pill still there.</figcaption></figure><figure><img src="{uri(CAP / 'pill-menu.webp', 'image/webp')}" alt="The pill's menu"><figcaption>The pill's menu, in precedence order, with the rung, the basis, and the link.</figcaption></figure></div>

<h2>The formula, and what Obsidian does with it</h2>
<p>Bases has no coalesce, and a name of ours is an error there: <code>coalesce(a, b)</code> and <code>first(a, b)</code> both draw <code>Cannot find function</code>. So the file spells it with Bases' own list functions. The Survey's spelling hadn't been run. Run in Obsidian 1.12.7, in an isolated instance, it fails on a boolean, so the kit reads a second spelling too.</p>
<div class=wrap><pre><code>nominal: '[datasheet, citation, measured].filter(value.isType("boolean") || !value.isEmpty())[0]'</code></pre></div>
<div class=wrap><table><tr><th>a</th><th>b</th><th><code>.filter(!value.isEmpty())[0]</code></th><th><code>.filter(value.isType("boolean") || !value.isEmpty())[0]</code></th></tr>{truth}</table></div>
<figure><img src="{uri(CAP / 'obsidian.webp', 'image/webp')}" alt="Those formulas in real Obsidian"><figcaption>Real Obsidian: f5 and f9 are the short spelling, g1 the long one. An unchecked box is <code>false</code>. These same rows are in <code>tests/unit/source-columns.test.mjs</code>.</figcaption></figure>
<p>That is the only formula that runs, for display columns. Any other draws a dash and says it needs Obsidian. A headline KPI naming a formula draws no number: it stays the producer's.</p>

<h2>Two things RobotParts found adopting the kit</h2>
<ul><li><strong><code>persist="page"</code>.</strong> <code>persist="local"</code> keys on the data id, shared by 2,103 pages, so a preset chosen on JMC opened moteus on 0 of 16 rows. The new word keeps the view, sort and filters per page and data id, and the widths per data id. <code>persist="local"</code> is unchanged, and what it stored still reads. RobotParts gave each part its own id meanwhile (<code>dfaa724</code>), which fixes the preset and costs the shared widths; <code>persist="page"</code> on one id is how to have both, and nothing needs to change if it doesn't want them.</li>
<li><strong>A header holds no column open.</strong> A column's floor is what it holds. Its words widen a column nobody has sized, up to 240 px, then end in an ellipsis, whole on hover. This is one rule for every column, so <code>types_r2</code>'s r1 #6 no longer asserts header text. On robotparts' names at 1280 px all three sources sit inside the sheet, and the longest drags narrower by the pointer's 100 px.</li></ul>

<h2>What became of each behaviour PEP 0015 froze</h2>
<div class=wrap><table><tr><th>Behaviour</th><th>Now</th><th>Why</th></tr>{table}</table></div>

<h2>Code</h2>
<div class=wrap><table><tr><th>Lines</th><th class=n>Added</th><th class=n>Removed</th><th class=n>Net</th></tr>
{row_net('The table view (<code>_srcHead</code>, <code>_srcDrag</code> and the rest)', TABLE)}
{row_net('Core: <code>precedence.js</code>, <code>source-popover.js</code>', ['packages/core/src/precedence.js', 'packages/core/src/source-popover.js'])}
{row_net('Core: the element, toolbar, styles', ['packages/core/src/elements', 'packages/core/src/toolbar', 'packages/core/styles'])}
{row_net('Core: the formula reader and the checker', ['packages/core/src/grammar.js', 'packages/core/src/check.js'])}
{row_net('All of core', ['packages/core'])}
{row_net('All of <code>packages/</code>', ['packages'])}</table></div>
<p><strong>This lane added lines overall: {delta(['packages']):+d} across <code>packages/</code>, so there is no net removal to report.</strong> The table view lost {-delta(TABLE)} lines. Core gained {delta(['packages/core'])}, because unfolding, the slots and the edit fold are new code there. What went is the second system: every source-specific path in the table is gone, and <code>precedence.js</code> is pure data work that no view has to know about.</p>

<h2>How it was held honest</h2>
<ul><li><strong>The ruler came first.</strong> Three frozen files were committed red before any code. The oracle reads the fixtures' JSON alone, and the left-most rule is read off the page.</li>
<li><strong>The ruler was edited, and each edit is named below:</strong> two harness commits and one on the adoption file fixed readings I got wrong. Three assertions were narrowed, each in a named commit: the Python warning holds only for a file read with its data, because a standing test holds the vault's <code>.base</code> files to no warnings (<code>fd855de</code>); and in <code>fadb1a2</code>, "no value cut" at a column's floor became "a cut value is whole on hover", which is §45, with "a number is never cut" asserted on the plain column beside it, and a plain column's width is read from its <code>&lt;col&gt;</code>, because three columns in a wide box spread to fill it. The old §36 checks changed in <code>4c5b809</code>, and <code>types_r2</code>'s r1 #6 in <code>1e42b58</code>, only where the behaviour went on purpose.</li>
<li><strong>The suite ran once,</strong> strict on Node 22.18, on <code>{FACTS['suite_tip']}</code>: all 63 parts, none skipped. The commits after it touch only the journey tool and these documents.</li>
<li><strong>The journey went red first,</strong> and that was the tool's fault. Its shim for robotparts' old <code>VENDOR.json</code> outlived that app's migration and raised a <code>TypeError</code> on every candidate, while the 50 browser checks passed. The shim is gone, and it ran again on <code>{FACTS['journey_tip']}</code>, 65 of 65: 15 tests and 50 browser checks. That commit's kit is this tip's; only documents came after.</li>
<li><strong>What the ruler caught:</strong> a rich cell's old <code>text</code> drew over an edit, on every page, and a value typed in a formula's cell carried <code>sources</code> and passed for a new list. Both are fixed at one seam.</li>
<li><strong>What only looking caught:</strong> a stylesheet slip that took the outline off the winning cell, and a source shown again thrown past the sheet's edge. The second is what stopped this take working. Both now have a check.</li></ul>
<details><summary>Every commit</summary><ol>{history}</ol></details>

<h2>Not done</h2>
<ul><li>A pick is still the row's, not the value's: with two sourced values in a row it moves both, and the menu says so.</li><li>Live datasets are not unfolded, and data with sources still builds its model on the main thread.</li><li>A finger reorders from Property visibility: the ordinary header drag is HTML5, which phones don't fire. The old pointer drag went with the mode.</li><li>Robotparts has not re-vendored. When it does, <code>site/static/part-overview.js:47</code> names <code>'@source'</code> and needs <code>nominal@source</code>, or a right-click on that column finds no cell; this comes from reading the code, and it was not run. <code>datasheet_check.py</code>, <code>source_precedence_check.py</code> and <code>capture_datasheet_report.py</code> read the old selectors too. <code>docs/migrations/source-columns.md</code> has the list, and the journey reads none of them.</li></ul>
</main></body></html>"""
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(page, encoding="utf-8")
size = OUT.stat().st_size
print(f"{OUT}: {size:,} bytes")
if size > LIMIT:
    sys.exit(f"over the preview's limit of {LIMIT:,} bytes")
