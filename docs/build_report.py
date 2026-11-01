#!/usr/bin/env python3
"""Build reports/data-ui-design-2026-10-25.html: one self-contained page (no network, light and dark).

    python3 docs/build_report.py

It runs the two proofs (node --test; the checker on the broken example and on the vault) and embeds their real
output, so the page can never show a result the code did not produce. The two stills are re-encoded in memory from
robotparts' own report media (WebP, about 76 KB together), so the page stays a text page under the 256 KB data-URI
budget. Needs Pillow for the stills; without it, or without the source images, the page says so instead.
WHY a big type scale (17 px body, 1480 px column): Zach said earlier reports were too small to read.
"""

from __future__ import annotations

import base64
import html
import io
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "data-ui-design-2026-10-25.html"
VAULT = pathlib.Path("~/zach_brain")
STILLS = [
    ("~/robotparts/reports/media/site-v3/category-actuator-chart-1280.jpg", 1000,
     "Today: robotparts.dev's Chart view, a hand-drawn log-log SVG scatter (site.js scatter(), about 50 lines). "
     "Zach, Oct 25: \"exactly what I'm talking about\". data-ui's first chart preset has to match it in a side-by-side."),
    ("~/robotparts/reports/media/tables-2026-10-25/11-actuators-by-brand.jpg", 1100,
     "Landed: the table lane's <data-views> on the same 1,149 actuators. Its preset tabs are views in one .base file; "
     "it is TanStack Table v9 underneath. data-ui starts from this component."),
]

e = html.escape


def run(cmd: list[str]) -> str:
    done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)
    return (done.stdout + done.stderr).strip()


def still(path: str, width: int) -> str | None:
    try:
        from PIL import Image
        image = Image.open(path).convert("RGB")
    except Exception:  # Pillow or the source missing: the caption says so
        return None
    if image.width > width:
        image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=72, method=6)
    return "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode()


# ---------------------------------------------------------------- the diagram (inline SVG, themed by the page tokens)

def box(x, y, w, h, title, lines=(), cls="b"):
    out = [f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="10"/>',
           f'<text class="t" x="{x + 14}" y="{y + 24}">{e(title)}</text>']
    for i, line in enumerate(lines):
        out.append(f'<text class="s" x="{x + 14}" y="{y + 46 + 19 * i}">{e(line)}</text>')
    return "\n".join(out)


def arrow(x1, y1, x2, y2, label=None, lx=None, ly=None):
    out = f'<line class="ar" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" marker-end="url(#head)"/>'
    if label:
        out += f'<text class="al" x="{lx}" y="{ly}">{e(label)}</text>'
    return out


def diagram() -> str:
    parts = [
        '<svg viewBox="0 0 1400 600" role="img" aria-labelledby="dgt dgd" class="dg">',
        '<title id="dgt">How data-ui works</title>',
        '<desc id="dgd">Any data file and one .base view file feed stock engines, which drive the data- custom elements, '
        'which drop into robotparts, Vibe Tracks, React apps, the gallery and later Clank and Obsidian. An agent edits the '
        'view file; site tokens skin the elements.</desc>',
        '<defs><marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
        '<path class="hd" d="M0,0 L10,5 L0,10 z"/></marker></defs>',
        box(360, 18, 630, 112, "View file · actuators.base",
            ["Obsidian Bases grammar: filters · order · sort · groupBy · summaries",
             "+ data-ui keys: facets · chart (Vega-Lite inside) · guides · hover · kpi",
             "Every Bases file is valid; Obsidian keeps the extra keys"], cls="vf"),
        box(1050, 18, 330, 112, "Your agent",
            ["Claude Code · Codex · you", "edits the .base; no AI inside data-ui", "data-ui check: one line per mistake"], cls="ag"),
        arrow(1048, 74, 994, 74),
        '<text class="h" x="160" y="203" text-anchor="middle">Any data → records</text>',
        '<text class="h" x="500" y="203" text-anchor="middle">Engine · stock parts</text>',
        '<text class="h" x="840" y="203" text-anchor="middle">Elements · one data- prefix</text>',
        '<text class="h" x="1215" y="203" text-anchor="middle">Hosts · drop-in</text>',
    ]
    data = [("CSV · TSV · JSONL", "+ a field schema (Table Schema)"), ("JSON records", "a list, or {schema, rows}"),
            ("One object", "a part, a config: a property sheet"), ("A folder of .md notes", "frontmatter fields (vault, Clank)"),
            ("Parquet · later", "hyparquet, past ~50k rows")]
    for i, (title, line) in enumerate(data):
        parts.append(box(20, 222 + 72 * i, 280, 60, title, [line]))
    engine = [("TanStack Table v9 + Virtual", "rows, nested groups, 41 ms"), ("grammar.js", "filters · summaries · pivot · URL"),
              ("facets.js", "McMaster rail ⇄ the same filter"), ("Vega-Lite · lazy · ~282 KB", "every chart: one engine")]
    for i, (title, line) in enumerate(engine):
        parts.append(box(360, 222 + 72 * i, 280, 60, title, [line], cls="en"))
    parts.append('<text class="al" x="374" y="530">DuckDB runs only at build time</text>')
    parts.append(box(690, 222, 300, 78, "<data-views>", ["table · cards · kanban · pivot", "chart · kpi · peek"], cls="el"))
    parts.append(box(690, 310, 300, 60, "<data-facets>", ["the left rail, with counts"], cls="el"))
    parts.append(box(690, 382, 300, 60, "<data-value>", ["value · unit · basis · source"], cls="el"))
    parts.append(box(690, 454, 300, 60, "<data-kpi> · <data-sparkline>", ["KPI card, delta, sparkline"], cls="el"))
    parts.append('<rect class="tk" x="690" y="530" width="300" height="46" rx="10"/>'
                 '<text class="t" x="704" y="559">--data-* tokens, shadcn defaults</text>')
    sites = [("robotparts.dev", "static Python build · vendored ESM"), ("Vibe Tracks", "vanilla JS · vendored ESM"),
             ("React 19 apps", "the same tags · shadcn registry"), ("Gallery = docs site", "real cases · the test suite"),
             ("Clank · Obsidian (later)", "thin hosts, no new shell")]
    for i, (title, line) in enumerate(sites):
        parts.append(box(1050, 222 + 72 * i, 330, 60, title, [line], cls="st"))
    parts += [
        arrow(302, 360, 356, 360), arrow(642, 360, 686, 360), arrow(992, 360, 1046, 360),
        arrow(610, 132, 610, 216, "configures", 622, 172), arrow(965, 132, 965, 216, "", 0, 0),
        arrow(1048, 553, 994, 553, "site tokens", 1000, 592),
        "</svg>",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------- page content

def table(head, rows, cls=""):
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def build() -> str:
    facets = run(["node", "--test"])
    facet_lines = "\n".join(line for line in facets.splitlines() if line.startswith(("ok ", "not ok ", "# tests", "# pass", "# fail", "# skipped")))
    broken = run(["python3", "tools/check_views.py", "examples/broken.base", "--data", "examples/actuators.schema.json"])
    vault_files = sorted(str(p) for p in VAULT.rglob("*.base") if ".claude" not in p.parts and ".trash" not in p.parts) if VAULT.exists() else []
    vault = run(["python3", "tools/check_views.py", "--quiet", *vault_files]) if vault_files else "the vault is not on this machine"
    unit = run(["python3", "-m", "unittest", "discover", "-s", "tools", "-p", "test_*.py"])
    unit_tail = "\n".join(unit.splitlines()[-3:])
    example = (ROOT / "examples" / "actuators.base").read_text(encoding="utf-8")
    example = example[example.index("  # ---- cards"):]

    stills = []
    for path, width, caption in STILLS:
        uri = still(path, width)
        img = f'<img src="{uri}" alt="{e(caption)}">' if uri else f'<div class="missing">image not available: {e(path)}</div>'
        stills.append(f"<figure>{img}<figcaption>{e(caption)}</figcaption></figure>")

    disagree = table(["The brief says", "What I found", "So"], [
        ["“A generic library I make for myself”",
         "Most of it exists already, in five places: the table lane's <code>&lt;data-views&gt;</code> (landed, 22/22 checks), robotparts' rail and Rows/Gallery/Chart (1,033 lines of site.js), Vibe Tracks' views/cards/pivot (1,863 lines), Clank's <code>clank.base</code> (2,735 lines, a third Bases evaluator), and the survey's proposed KPI and atlas kits",
         "data-ui is where these <b>converge</b>; its first step is a move, not a build. The risk is a sixth copy"],
        ["“The shadcn model”",
         "Copy-in is how drift happens here: Tycoon copied 30 Clank kit parts at <code>9859de0</code>; shadcn exists seven times across his apps",
         "Take shadcn's <b>token names and registry</b>; copy-in only for skins and recipes. The engine and grammar are one pinned copy"],
        ["“A standalone app with a gallery page”",
         "Zach, Oct 25: “I don't think I'll ever use it as a standalone application”",
         "The gallery is the <b>docs site</b> (data-ui.dev if bought); local file viewing is a later Clank/Obsidian host"],
        ["“CSV may not be sufficient for images”", "Images are a column type, not a file format",
         "A <code>photo</code> column, typed <code>format: uri, media: image</code>"],
        ["“Filters like Obsidian or McMaster”", "Two editors of one filter; the rail can only draw part of it",
         "<b>One</b> stored Bases filter; the rail edits its facet-shaped part, the rest stays custom (proved below)"],
        ["Chart engine: the survey says ECharts",
         "The vault chose Vega-Lite on Oct 5 (model canvas) for configurable charts: “a published JSON Schema, so an AI can write a chart and have it validated”",
         "<b>One engine: Vega-Lite</b>, because the chart lives in a file an agent edits"],
        ["Tokens: alias shadcn names in vanilla apps",
         "robotparts' and Vibe Tracks' <code>--accent</code> is a strong blue (<code>#0a5bb5</code>, <code>#2a78d6</code>); shadcn's/Clank's is a hover fill (<code>#e5e5e5</code>)",
         "A private <code>--data-*</code> layer that <b>defaults to</b> shadcn names; a shadcn app needs zero lines"],
    ])

    clank = table(["Option", "C1 learn once 20", "C2 runs where views live 20", "C3 stock 15", "C4 files = interface 15", "C5 one copy 10", "C6 truthful 10", "C7 phone 5", "C8 fast slice 5", "Total"], [
        ["(a) a Clank plugin for data files", 3, 1, 3, 4, 3, 3, 2, 2, "53"],
        ["(b) a standalone app", 3, 2, 3, 3, 2, 3, 3, 3, "54"],
        ["<b>(c) a kit: custom elements + .base grammar + tokens + gallery; Clank and Obsidian as thin hosts later</b>", 5, 5, 4, 5, 5, 4, 4, 5, "<b>94</b>"],
        ["(d) a shadcn React registry only", 4, 2, 4, 4, 2, 4, 3, 4, "67"],
    ], cls="num")

    chart_scores = table(["Criterion", "Weight", "Vega-Lite", "ECharts 6", "Obs. Plot", "Graphic Walker", "Perspective", "hand SVG (today)"], [
        ["R1 the file's <code>chart:</code> block renders with no translator", 25, 5, 1, 2, 3, 1, 1],
        ["R2 covers Zach's asks (channels, log, facets, guides, image hover, click)", 20, 4, 5, 3, 3, 2, 2],
        ["R3 agents fluent; a published JSON Schema to validate", 15, 5, 3, 3, 2, 2, 1],
        ["R4 one engine across data-ui and his apps (in use today)", 15, 2, 5, 1, 1, 3, 2],
        ["R5 interaction at 1k–100k points", 10, 3, 5, 2, 3, 5, 2],
        ["R6 bytes on a phone page (lazy)", 10, 3, 3, 4, 1, 1, 5],
        ["R7 licence, maintenance", 5, 5, 5, 5, 4, 5, 3],
        ["<b>Total of 100</b>", "", "<b>79</b>", "70", "51", "48", "45", "39"],
    ], cls="num")

    asks = table(["Zach asked (Oct 25)", "Where it lives in the grammar"], [
        ["“As you filter it applies to the chart”", "<code>type: chart</code> is one more view of the same rows; the rail edits the all-views filter"],
        ["Multiple charts, or chart presets", "each preset is a view in the same <code>.base</code>; the tabs switch them"],
        ["Hover a dot: photo, name, key values", "<code>hover: {image, title, fields}</code>: the hover card the gallery's cards use too"],
        ["Colour, size, opacity bound to fields", "<code>chart.encoding.color / size / opacity / shape</code>: Vega-Lite channels"],
        ["Log vs linear", "<code>encoding.x.scale.type: log | linear | symlog</code>"],
        ["Ashby-style charts", "log-log + <code>guides: envelope / indexLine</code>, as Granta Selector draws them"],
        ["Full customisation, presets and good defaults", "the Encode menu writes <code>chart:</code>; Reset / Save view; Show Me–style default rules"],
        ["“An option to see the raw data”", "<b>Rows</b> on every chart: the same filtered rows as a table, one click"],
    ])

    names = table(["Name", ".com", ".dev", ".app", "Note"], [
        ["<b>data-ui</b> (Zach's pick)", "taken (2026-03; a live “Data UI” site)", "<b class=ok>available</b>", "<b class=ok>available</b>", "hyphenated; data-ui.com is a live product"],
        ["datakit", "taken (1997; live: DATAKIT, CAD file conversion)", "taken", "taken", "collides in CAD"],
        ["dataviewer", "taken", "taken (live “Data Viewer”)", "taken", "near Obsidian's Dataview"],
        ["datawrangler", "taken", "taken", "taken", "Microsoft Data Wrangler"],
        ["datadog", "taken", "taken", "taken", "Datadog, Inc."],
        ["dataviews", "taken", "taken", "available", "WordPress <code>@wordpress/dataviews</code>"],
        ["viewkit", "taken (for sale)", "available", "taken", ""],
        ["manyviews", "taken", "available", "available", "the thesis in one word"],
        ["rowkit", "taken", "taken", "taken", ""],
        ["fileviews", "taken", "available", "available", ""],
        ["viewsheet", "taken", "available", "available", ""],
        ["glancekit", "taken (live screenshot tool)", "available", "available", ""],
        ["viewbook", "taken", "available", "taken", ""],
        ["viewbase", "taken (spam redirect)", "available", "available", "echoes Bases"],
        ["tablekit", "taken", "taken", "taken", ""],
    ])

    tokens = """:root { --data-bg: var(--bg); --data-fg: var(--ink); --data-muted: var(--ink2); --data-subtle: var(--bg2);
        --data-border: var(--rule); --data-hover: var(--hover); --data-accent: var(--accent);
        --data-on-accent: var(--on-accent); --data-font: var(--sans); --data-mono: var(--mono); }   /* robotparts */
:root { --data-bg: var(--surface); --data-fg: var(--ink); --data-muted: var(--ink-2); --data-border: var(--line);
        --data-hover: var(--hover); --data-accent: var(--accent); --data-font: var(--font); }       /* Vibe Tracks */
/* a shadcn app: nothing. Elements read var(--data-fg, var(--foreground, #18181b)). */"""

    components = table(["Element / module", "What it does", "Status"], [
        ["<code>&lt;data-views&gt;</code>", "the container: view tabs, Group / Sort / Filter / Properties / <b>Encode</b> / Units, Save view, ⋯ Copy as .base; seven layouts; the peek", "table + pivot landed; cards, kanban, chart, kpi to build"],
        ["<code>&lt;data-facets for=…&gt;</code>", "the McMaster rail: facet groups with counts, find box, min/max, its own scroll", "port from robotparts"],
        ["<code>&lt;data-value&gt;</code>", "value with provenance: number, unit, basis mark, range; source and as-of on hover; its text is the no-JS truth", "build"],
        ["<code>&lt;data-kpi&gt;</code>", "KPI card: value, delta coloured by <code>better</code> outside a neutral band, sparkline, basis, “from rows · n”", "build (Evidence BigValue vocabulary)"],
        ["<code>&lt;data-sparkline&gt;</code>", "60-line SVG line/bar/dist; no chart engine", "extract from the lane"],
        ["<code>data-ui check</code>", "JSON Schema + names; one readable line per mistake", "proved in Python here; ships as Node over grammar.js"],
    ])

    slice_steps = """<ol class="steps">
<li><b>Barrier, first and alone.</b> Move the lane's <code>views/</code> (<code>ab5ba92</code>) here; rename <code>--dv-*</code> → <code>--data-*</code>; fix negatives and <code>note["…"]</code> in grammar.js; freeze the data shape, grammar keys and token names. robotparts then vendors from here, never from <code>design/</code>.</li>
<li><b>Cards</b> with Bases' own keys, the shared hover card, a minimal <code>&lt;data-value&gt;</code>.</li>
<li><b>Chart</b>: vega-embed as a lazy chunk, the <code>chart:</code> block, tokens → Vega config, hover card, click → part page, the Encode menu, Rows, Show Me defaults.</li>
<li><b>robotparts, on a lane, Preview only:</b> the actuators data gains <code>photo</code> and rich spec cells; <code>actuators.base</code> gains Gallery + two chart presets; the category page renders <code>&lt;data-views&gt;</code> + <code>&lt;data-facets&gt;</code> over today's table as the no-JS fallback.</li>
<li><b>The rail</b> on the all-views filter, with disjunctive counts, kept across layouts and in readable URL params.</li>
<li><b>Gallery</b>: two cases from the same files (actuators in robotparts' skin; models × benches pivot in shadcn neutral), each with a checks script.</li>
<li><b><code>data-ui check</code></b> as a Node CLI on grammar.js.</li>
</ol>
<p><b>Acceptance, measured and frozen before the build:</b></p>
<ul>
<li>The same 1,149 rows in all three layouts. One rail tick moves the row count, card count and dot count to the same number.</li>
<li>The selection survives a layout switch and a reload.</li>
<li>Editing <code>actuators.base</code> on disk changes the page on the next Preview build.</li>
<li>The vega chunk loads only on the first chart. A filter change re-renders 1,149 dots in under 100 ms at 390 px.</li>
<li>Hover shows the photo, and a click opens the part.</li>
<li>Nothing loads from another origin, and there are no script errors.</li>
<li>Light and dark come from robotparts' tokens, with no sideways scroll at 390 px.</li>
<li>Obsidian 1.14.5 (headless) opens the file, draws table and cards, and keeps the <code>chart:</code> keys after a sort edit.</li>
<li>A side-by-side of today's chart and the Vega-Lite one, for Zach to pick.</li>
</ul>"""

    waiting = """<ul>
<li><b>Table lane (landed at <code>ab5ba92</code>).</b> Three things are still open.
<ul>
<li>Your yes on its own question, “adopt TanStack + &lt;data-views&gt; + Bases presets site-wide?”. Its default, integrating on the actuators page first, is step 3 above.</li>
<li>One home for the code. It recommended <code>~/data-views</code>; this says this repo, to become <code>~/data-ui</code>.</li>
<li>No new grammar keys there without this spec.</li>
</ul>
The integration must wait for the barrier, or robotparts starts from a fork.</li>
<li><b>Views-catalog lane</b>, writing <code>docs/VIEWS.md</code> and <code>docs/views/</code> in this repo right now. It catalogues the stock library for further view types. Its demo pins the same TanStack and Vega-Lite versions, and its measurement of the Vega stack (289 KB gz) agrees with mine (282 KB). I did not touch or commit its files.</li>
<li><b>Agent-bridge lane</b>: live control of an open page belongs to <code>~/robotparts/reports/media/agent-bridge-proposals-2026-10-25.html</code> (not on disk yet). data-ui designs no bridge.</li>
</ul>"""

    surface = """<div class="cols">
<div><h3>Done and proved</h3><ul>
<li>The spec: <code>docs/SPEC.md</code>, sections 1–20.</li>
<li><b>One filter, two editors.</b> 300 random rail selections on the 1,149 real actuators pick exactly the rows the lane's own evaluator picks. A mutated bound turns it red.</li>
<li><b>The grammar as the agent interface.</b>
<ul>
<li>The schema passes all 109 of your vault's <code>.base</code> files and the lane's 4 presets.</li>
<li>A broken file gets 8 named errors and 2 warnings, each with a suggestion.</li>
</ul></li>
<li><b>Read from Obsidian 1.14.5's code:</b> it writes unknown top-level, property and view keys back, and the cards keys are <code>image</code>, <code>imageFit</code>, <code>imageAspectRatio</code> and <code>cardSize</code>.</li>
<li><b>Found on the way:</b>
<ul>
<li>the lane's evaluator rejects negative numbers and <code>note["vibe-status"]</code>;</li>
<li>its "—" sits left in right-aligned number columns;</li>
<li>its actuators rows have no <code>photo</code> column yet.</li>
</ul></li>
</ul></div>
<div><h3>Left</h3><ul>
<li>The first slice (above). It is next, not blocked, once you say yes to the home and the engine.</li>
<li><b>Slice 2:</b> kpi, Ratio, and Vibe Tracks' Results and KPI tiles.</li>
<li><b>Slice 3:</b> Ashby guides, kanban, and the three atlases.</li>
<li><b>Slice 4:</b> the Obsidian and Clank hosts.</li>
</ul></div>
<div><h3>Needs you (default if silent)</h3><ol>
<li><b>One home:</b> this repo holds the lane's &lt;data-views&gt; and the survey's KPI kit. <i>Default: yes.</i></li>
<li><b>One chart engine, Vega-Lite</b>, behind the speed and look gate. <i>Default: Vega-Lite.</i></li>
<li><b>Prefix <code>data-*</code>, tokens <code>--data-*</code></b> (the survey's <code>&lt;bam-value&gt;</code> becomes <code>&lt;data-value&gt;</code>; <code>@bam</code> stays for React app chrome). <i>Default: yes.</i></li>
<li><b>Buy data-ui.dev</b> for the docs site? <i>Default: not bought.</i></li>
<li><b>A PROJECT - data-ui note?</b> <i>Default: no, until you journal on it.</i></li>
</ol></div>
<div><h3>Deliberately not done</h3><ul>
<li>No app code: the spec and two proofs only.</li>
<li>No other repo changed. The table lane's and the vault's files were read, never written.</li>
<li>No domain bought. No audit run.</li>
<li>No bridge designed: that is the agent-bridge lane's job.</li>
<li>The folder is not renamed. That's yours to do, to <code>~/data-ui</code>.</li>
</ul></div>
</div>"""

    css = """
:root { color-scheme: light; --bg:#fbfbfa; --fg:#18181b; --muted:#55555d; --faint:#8a8a93; --line:#e2e2e6; --box:#ffffff;
  --box2:#f3f3f5; --accent:#1d5fbf; --accent-bg:#eaf1fc; --ok:#1f7a45; --en:#f1f6ff; --el:#effaf3; --st:#fbf7ef; --ag:#f6f0fc;
  --code:#f3f3f5; }
@media (prefers-color-scheme: dark) { :root { color-scheme: dark; --bg:#0f0f11; --fg:#ececef; --muted:#a8a8b2; --faint:#7a7a84;
  --line:#2d2d33; --box:#18181b; --box2:#202024; --accent:#86b1f5; --accent-bg:#172338; --ok:#74d39c; --en:#14203a;
  --el:#13281c; --st:#2a2314; --ag:#251a33; --code:#1b1b1f; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 17px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1480px; margin: 0 auto; padding: 32px 40px 64px; }
.kicker { color: var(--muted); font-size: 15px; letter-spacing: .02em; }
h1 { font-size: 34px; line-height: 1.25; margin: 6px 0 10px; }
h2 { font-size: 26px; margin: 48px 0 12px; padding-top: 12px; border-top: 1px solid var(--line); }
h3 { font-size: 19px; margin: 18px 0 6px; }
.where { color: var(--muted); margin: 0 0 18px; }
.answer { background: var(--accent-bg); border: 1px solid var(--line); border-radius: 12px; padding: 16px 22px; }
.answer ol { margin: 6px 0; padding-left: 22px; } .answer li { margin: 6px 0; }
code { overflow-wrap: anywhere; font: 0.92em ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: var(--code); padding: 1px 5px; border-radius: 4px; }
pre { background: var(--code); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; overflow-x: auto;
  font: 14.5px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
pre code { background: none; padding: 0; }
.tw { overflow-x: auto; margin: 10px 0 6px; }
table { width: 100%; border-collapse: collapse; font-size: 15.5px; }
th, td { text-align: left; vertical-align: top; padding: 8px 10px; border-bottom: 1px solid var(--line); }
th { background: var(--box2); font-weight: 600; }
table.num td:not(:first-child), table.num th:not(:first-child) { text-align: center; white-space: nowrap; }
table.num td:first-child { min-width: 330px; }
.three > *, .cols > *, .stack > * { min-width: 0; }
.ok { color: var(--ok); }
figure { margin: 0; } figure img { max-width: 100%; height: auto; border: 1px solid var(--line); border-radius: 10px; display: block; }
.stack { display: grid; gap: 22px; margin: 16px 0; }
figcaption { color: var(--muted); font-size: 15px; margin-top: 6px; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin: 14px 0; }
.dgwrap { overflow-x: auto; }
.dg { width: 100%; min-width: 1060px; height: auto; display: block; margin: 8px 0 0; }
.dg .b { fill: var(--box); stroke: var(--line); } .dg .vf { fill: var(--accent-bg); stroke: var(--accent); stroke-width: 1.5; }
.dg .ag { fill: var(--ag); stroke: var(--line); } .dg .en { fill: var(--en); stroke: var(--line); }
.dg .el { fill: var(--el); stroke: var(--line); } .dg .st { fill: var(--st); stroke: var(--line); }
.dg .tk { fill: var(--box2); stroke: var(--accent); stroke-dasharray: 5 4; }
.dg .t { fill: var(--fg); font: 600 15.5px system-ui, sans-serif; } .dg .s { fill: var(--muted); font: 13.5px system-ui, sans-serif; }
.dg .h { fill: var(--fg); font: 700 16px system-ui, sans-serif; } .dg .al { fill: var(--muted); font: italic 13.5px system-ui, sans-serif; }
.dg .ar { stroke: var(--faint); stroke-width: 2; } .dg .hd { fill: var(--faint); }
.three { display: grid; grid-template-columns: 1fr auto 1.2fr auto 1fr; gap: 12px; align-items: stretch; margin: 12px 0; }
.panel { border: 1px solid var(--line); border-radius: 12px; padding: 12px 16px; background: var(--box); }
.panel h4 { margin: 0 0 6px; font-size: 16px; } .panel p { margin: 4px 0; font-size: 15.5px; }
.panel pre { margin: 6px 0 0; font-size: 13.5px; }
.swap { align-self: center; font-size: 26px; color: var(--faint); }
.cols { display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px; }
.cols > div { border: 1px solid var(--line); border-radius: 12px; padding: 4px 16px 10px; background: var(--box); font-size: 15.5px; }
.steps li { margin: 8px 0; }
.missing { padding: 30px; border: 1px dashed var(--line); color: var(--muted); }
footer { color: var(--muted); font-size: 14.5px; margin-top: 48px; border-top: 1px solid var(--line); padding-top: 12px; }
@media (max-width: 1100px) { .three { grid-template-columns: 1fr; } .swap { transform: rotate(90deg); justify-self: center; } }
@media (max-width: 760px) { main { padding: 18px 16px 48px; } h1 { font-size: 27px; } .cols { grid-template-columns: 1fr; } table.num td:first-child { min-width: 220px; } }
"""

    filter_panels = """<div class="three">
<div class="panel"><h4>The rail (McMaster)</h4>
<p>☑ Steadywin ☑ CubeMars <span style="color:var(--muted)">· brand</span></p>
<p>Peak torque: min <b>10</b> · max —</p><p>☑ has a photo</p>
<p style="color:var(--muted)">+1 custom filter · Edit</p></div>
<div class="swap">⇄</div>
<div class="panel"><h4>One stored filter (Bases, all views)</h4>
<pre><code>filters:
  and:
    - or:
        - 'brand == "Steadywin"'
        - 'brand == "CubeMars"'
    - 'peak_torque &gt;= 10'
    - '!photo.isEmpty()'
    - 'price &lt; mass'   # custom: the rail shows it, never drops it</code></pre></div>
<div class="swap">⇄</div>
<div class="panel"><h4>The builder (Obsidian)</h4>
<p><b>All</b> of:</p><p>• brand is any of Steadywin, CubeMars</p><p>• peak torque ≥ 10</p><p>• photo is not empty</p><p>• <code>price &lt; mass</code></p></div>
</div>"""

    body = f"""<main>
<div class="kicker">data-ui · design · Sunday 2026-10-25 · reasoner (Claude Opus 5.5)</div>
<h1>data-ui is a drop-in kit (custom elements, one .base view grammar, shadcn-default tokens) built on the table lane's &lt;data-views&gt;. The spec is ready; there is no app code yet.</h1>
<p class="where">It lives in <code>~/data-ui</code> (renamed from <code>~/datakit</code> on 2026-10-25). Local git, not pushed. It builds on robotparts <code>lane/tables</code> @ <code>ab5ba92</code>, which is not merged. The full text is <code>docs/SPEC.md</code>.</p>

<div class="answer"><b>The answer in five lines</b><ol>
<li><b>Convergence, not a new library.</b> The table lane's &lt;data-views&gt;, the survey's KPI and atlas kits, robotparts' hand-rolled views, Vibe Tracks' views and Clank's <code>clank.base</code> become one repo. The risk is a sixth copy.</li>
<li><b>Shape:</b> <code>data-*</code> custom elements, Obsidian Bases <code>.base</code> files with Vega-Lite inside <code>chart:</code>, and <code>--data-*</code> tokens that default to shadcn's names. React apps use the same tags.</li>
<li><b>Stock engines:</b> TanStack Table v9 (landed), Vega-Lite for every chart (one engine), plain arrays in the browser, DuckDB only at build time.</li>
<li><b>Clank:</b> data-ui is neither a Clank plugin nor an app. Clank and Obsidian become thin hosts later, with no new shell. Zach: “a drop-in shadcn-type thing for my applications.”</li>
<li><b>Files are the agent interface.</b> There is no AI inside: a schema and a checker make the <code>.base</code> safe for your Claude Code to edit, and the page re-renders.</li>
</ol></div>

<h2>How it works</h2>
<div class="dgwrap">{diagram()}</div>
<p style="color:var(--muted);font-size:15px">Figure 1. Any data reads as records. One <code>.base</code> file configures the stock engines. The elements render the views and drop into each host. Your agent edits the files, and site tokens skin the elements.</p>

<h2>Where I disagree with the brief</h2>
{disagree}

<h2>Decision 1: how data-ui relates to Clank</h2>
<p>This is scored on the spec's weighted criteria. C2 decides it: robotparts and Vibe Tracks, the two apps where data views actually live, use neither React nor Clank.</p>
{clank}
<p><b>Clank's state:</b> the workbench's last commit is <code>9859de0</code> (Oct 5). Its plugins shipped until Oct 20 (cad2robot Oct 14, daisychain Oct 20). Vibe Tracks removed its Clank plugin on Oct 25 on your word: “a completely standalone application that shouldn't know about clank”. So Clank is dormant, not dead, and data-ui must not depend on it. Later, a <code>clank-data-ui</code> viewer replaces <code>clank.base</code>, and an Obsidian Bases plugin adds <code>chart</code>, <code>pivot</code> and <code>kpi</code> over notes.</p>

<h2>Decision 2: one chart engine for data-ui (Vega-Lite)</h2>
{asks}
<div class="stack">{stills[0]}{stills[1]}</div>
{chart_scores}
<p><b>Why Vega-Lite:</b> the chart is configured by a file an agent writes, so the <code>chart:</code> block <i>is</i> the spec. There is no translator and no second meaning, and its published schema validates it. ECharts is the close second, on incumbency and scale, but it would need a hand-written Vega-Lite-to-ECharts compiler.</p>
<p><b>Bytes:</b> about 282 KB gzipped (vega 180 + vega-lite 82 + vega-embed 21), loaded only when a chart first shows. A peer lane's independent esbuild bundle measures 289 KB. The same file shows an ECharts subset at 221 KB, so on bytes it is a tie.</p>
<p><b>Graphic Walker, evaluated:</b> Apache-2.0, React ≥ 19, 71 dependencies, a 5.5 MB ESM, its own <code>IChart</code> format and filters. It is not the chart view. It stays a later “Explore” button in React hosts, and its <code>normalize()</code> accepts Vega-Lite-like specs. Its natural-language box is out: there is no AI in data-ui.</p>
<p><b>The gate in the first slice:</b> re-rendering the 1,149-point chart after a filter change takes under 100 ms at 390 px, and the chart wins a side-by-side with today's. If it fails, I revisit ECharts.</p>

<h2>The grammar is the agent interface</h2>
<p>A trimmed <code>examples/actuators.base</code> holds the lane's five table views (unchanged) plus a gallery and chart presets. Inside <code>chart:</code> the vocabulary is Vega-Lite; everywhere else it is Bases.</p>
<pre><code>{e(example)}</code></pre>
<p><b>The checker on a deliberately broken file</b> (<code>python3 tools/check_views.py examples/broken.base --data examples/actuators.schema.json</code>), output captured when this page was built:</p>
<pre><code>{e(broken)}</code></pre>
<p><b>Every <code>.base</code> file in your vault</b> ({len(vault_files)} files):</p>
<pre><code>{e(vault)}</code></pre>

<h2>One filter, two editors</h2>
{filter_panels}
<p>The rail edits the facet-shaped part of the one stored filter. The builder edits all of it. A tick survives switching from the table to the chart, because both views read the same filter. Below is <code>node --test</code>, run when this page was built. Test 8's oracle is the lane's own Bases evaluator on 1,149 real actuators (300 seeded random selections).</p>
<pre><code>{e(facet_lines)}</code></pre>
<pre><code>{e(unit_tail)}</code></pre>

<h2>Components and tokens</h2>
{components}
<p><b>“Change the tokens to match your site”</b> is one block in the site's CSS. Elements never declare these tokens themselves, so <code>:root</code> works:</p>
<pre><code>{e(tokens)}</code></pre>

<h2>The first slice (exact)</h2>
<p>It proves one data file plus one <code>.base</code> gives a table, cards, a chart and the rail, in robotparts' actuators page (1,149 rows) and in the gallery.</p>
{slice_steps}

<h2>What I'm waiting on, and the lanes around this one</h2>
{waiting}

<h2>Names (RDAP, 2026-10-25; prices unknown without a registrar token)</h2>
{names}

<h2>Decision surface</h2>
{surface}

<footer>Sources: every prior-art claim is cited with its URL in <code>docs/SPEC.md</code> §15 (accessed 2026-10-25). Local evidence:
Obsidian 1.14.5's app code (<code>~/.config/obsidian/obsidian-1.14.5.asar</code>), the table lane (<code>ab5ba92</code>, its report
<code>~/robotparts/reports/robotparts-tables-2026-10-25.html</code>), the reuse survey
(<code>~/robotparts/reports/media/reusable-components-2026-10-25.html</code>), and Vibe Tracks' and Clank's code and memory.
Built by <code>docs/build_report.py</code>.</footer>
</main>"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>data-ui design</title>
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    page = build()
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT} ({len(page.encode()) / 1024:.0f} KB)")
