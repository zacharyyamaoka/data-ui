"""Build the admin-look report: one HTML page beside its media in the MAIN checkout's gitignored reports/media/admin-look/
(written there by docs/capture_admin_look.py), so the page and its pictures move together.

    python3 docs/build_admin_look_report.py ~/data-ui/reports/media/admin-look RESULTS.json REFS_DIR

RESULTS.json: {"commit", "npm_test": [[step, result]...], "case_checks": "36/36", "unit": "8/8", "notes": [...]}, what the
run printed. REFS_DIR holds Zach's four screenshots (1.webp Deals, 2.webp Organizations, 3.webp the summary crop,
4.webp Organizations zoomed); they are copied in as ref-1.webp … ref-4.webp."""

import html
import json
import pathlib
import shutil
import sys

OUT = pathlib.Path(sys.argv[1])
RESULTS = json.loads(pathlib.Path(sys.argv[2]).read_text())
REFS = pathlib.Path(sys.argv[3])
E = html.escape
for i in range(1, 5):
    shutil.copyfile(REFS / f"{i}.webp", OUT / f"ref-{i}.webp")
CAPTURE = json.loads((OUT / "capture.json").read_text())

MATCHES = [
    "Two cards on a grey well: the summary card, then the table card, 16 px apart, 12 px corners, a 1 px ring",
    "Summary: four equal cells, hairlines between them, a semibold label over a dotted underline, the value under it; hover gives the definition",
    "The view chip “All ⇅” / “Pipeline ⇅”: bordered, 32 px, semibold, no layout icon; it switches the file's saved views",
    "“Search and filter” rests as a quiet line; a click opens the bordered box “Searching all deals”, Cancel at the right and the “+ Organization” chip row (screenshot 1)",
    "A grey header row with a select-all box, sortable columns with “↑” on the sorted one",
    "Rows with a checkbox, the first column semibold, an initials chip coloured by kind (green customers, blue prospects, red competitors)",
    "Pill tags, two then “+2”; grey kind badges; stage “Contacted” in the info colour",
    "Numbers right-aligned; dates “Apr 10” this year, “Jul 25, 2023” otherwise",
    "The floating pager “‹ 1–14 ›” under the card, outside it, both arrows off on one page",
    "The dark nav in both themes: brand, Search Ctrl K, Deals with its count 4, the open section's subs (Pipeline · Won · Lost; Organizations · People · Activities), the Views group",
]
DIFFS = [
    "<b>Display</b> stays at the bar's right (Tycoon's bar has none); in data-ui every setting lives there (CONTRACT §15: the view selector and Display never leave the row). It hides while the search is open.",
    "<b>Empty cells read “—”</b> where Tycoon leaves them blank: data-ui never draws a missing value as nothing (truthful rendering); the reason is the title.",
    "<b>Value</b>: “20 ○” with the unit CAD in the header and the estimate mark, where Tycoon writes “20 CAD (guess)” in italics.",
    "<b>Row height</b> 44 px (Bases' <code>rowHeight: medium</code>); Polaris' rows are 37 px. A 37 px step would be one more Bases-incompatible value.",
    "<b>“Contacted”</b> is a 14 % tint of the series blue with blue text; Polaris' info badge is a pale-blue fill with dark text (stronger in dark mode).",
    "<b>Avatar letters</b> use <code>--data-on-accent</code>, dark in Polaris' dark theme, so they read dark on the coloured chip; Tycoon's are white.",
    "<b>The brand mark</b> is the rail's light tile with a bolt; Shopify's store avatar is a green tile.",
    "<b>The font</b> is the system stack (Inter only if installed): data-ui never loads fonts from another origin.",
    "<b>The query box's hint list</b> (data-ui's query builder) still opens once you type; Polaris has none.",
]
STOCK = [
    ("Metric strip", "<code>ui.tsx</code> <code>MetricStrip</code>, metrics computed per page in <code>indexes.tsx</code>", "<code>&lt;data-summary for&gt;</code> + top-level <code>summary:</code> (new, proposed)", "one card, hairlines, dotted label with its definition, a sparkline only for a real series, numbers from the rows"),
    ("Index table", "<code>IndexPage.tsx</code> + <code>table.ts</code> + <code>s6.css</code> (Polaris IndexTable look)", "<code>&lt;data-views&gt;</code> table view, <code>frame=\"card\"</code> (new), <code>selectable</code>", "sort, select, range select, bulk band, primary column bold, one line per row"),
    ("Saved views picker", "<code>s6-view-picker</code>", "the bar's view chip (<code>views=\"dropdown\" promote=\"\"</code>), CONTRACT §15", "the file's views, switch, save"),
    ("Search and filter", "<code>s6-search-field</code>, <code>s6-facets</code>", "<code>search=\"expand\"</code> (new) over the query bar and <code>facets:</code>", "quiet line, “Searching all …”, Cancel, “+ facet” chips writing the one filter"),
    ("Avatar, tags, dates", "per-column renderers in <code>indexes.tsx</code>", "<code>display: avatar | date</code>, <code>maxBadges</code> (new)", "initials coloured by kind, +N with every tag in the title, the stored date one hover away"),
    ("Pager", "<code>s6-pagination</code>", "the table's <code>pageSize</code> (new)", "“‹ 1–50 ›”, disabled ends, resets on a new filter"),
    ("Sidebar", "<code>Sidebar.tsx</code> (shadcn sidebar)", "<code>&lt;data-rail mode=\"wide\"&gt;</code> + <code>data-badge</code>, <code>data-parent</code> (new)", "dark nav, counts, sub-items for the open section, collapse, drag-resizable, remembered"),
    ("Routing, detail pages, Home, dialogs", "<code>ShopifyShell.tsx</code>, <code>DetailPage.tsx</code>, <code>Home.tsx</code>", "unchanged (stock seam): the host's router; the peek stands in for a detail page", "the app's own pages"),
]


def fig(src, cap, cls=""):
    return f'<figure class="{cls}"><a href="{src}"><img src="{src}" alt="{E(cap)}" loading="lazy"></a><figcaption>{cap}</figcaption></figure>'


def pair(ref, mine, what):
    return f'<div class="pair">{fig(ref, f"Tycoon S6 (Zach, {what})")}{fig(mine, f"data-ui, <code>admin-shopify/app</code> ({what})")}</div>'


body = f"""
<header>
<p class="crumb">data-ui · lane/admin-look · {E(RESULTS.get('date', '2026-10-28'))}</p>
<h1>Tycoon's admin look, rebuilt on data-ui</h1>
<p class="verdict"><b>A summary card and a Shopify-style table card now come from one <code>.base</code> file, and the gallery case reproduces Tycoon's Deals and Organizations screens</b> — on <code>lane/admin-look</code> at <code>{E(RESULTS.get('commit', '?'))}</code>, not merged; every new key, element and frame is a <b>proposed</b> CONTRACT §32 (a barrier change the integrator decides).</p>
</header>

<section>
<h2>The flow, recorded from the real page</h2>
<video src="hero.mp4" autoplay muted loop playsinline controls poster="organizations-dark.jpg"></video>
<p class="muted">Hover a summary label (its definition), Search and filter → “+ Kind” → Customer (3 rows, the totals stay 14) → Cancel; the rail to Deals; the chip to Won (the rail follows). <a href="hero.gif">GIF fallback</a>. Recorded headless from <code>dist/site/gallery/admin-shopify/app/</code> with invented data.</p>
</section>

<section>
<h2>Beside his screenshots (dark, 2000 × 1010)</h2>
{pair('ref-1.webp', 'search-dark.jpg', 'Deals with the search open / Organizations with + Kind open')}
{pair('ref-1.webp', 'pipeline-dark.jpg', 'Deals')}
{pair('ref-2.webp', 'organizations-dark.jpg', 'Organizations')}
{pair('ref-3.webp', 'summary-dark.jpg', 'the summary card')}
{pair('ref-4.webp', 'organizations-dark.jpg', 'Organizations, zoomed')}
</section>

<section>
<h2>Light, phone and the kit's own gallery page</h2>
<div class="grid3">{fig('organizations-light.jpg', 'Organizations, light')}{fig('pipeline-light.jpg', 'Deals, light')}{fig('phone.jpg', '390 px, the rail folded to icons, the summary two by two', 'phone')}</div>
{fig('gallery-light.jpg', 'The case page on the site: the same views.base, its rail of facets, the summary card over the card-framed table')}
</section>

<section class="two">
<div><h2>What matches</h2><ul>{''.join(f'<li>{m}</li>' for m in MATCHES)}</ul></div>
<div><h2>What differs, and why</h2><ul>{''.join(f'<li>{d}</li>' for d in DIFFS)}</ul></div>
</section>

<section>
<h2>The two cards, as config</h2>
<pre><code>{E(RESULTS.get('config', ''))}</code></pre>
<p class="muted">Page: <code>&lt;data-summary for="list"&gt;</code> then <code>&lt;data-views id="list" src="views.base" toolbar="bar" views="dropdown" promote="" frame="card" search="expand" selectable status="off"&gt;</code>, inside <code>&lt;data-rail mode="wide" theme="dark"&gt;</code>. The only page script is a 20-line hash router that swaps the <code>.base</code> file between Customers and Deals.</p>
</section>

<section>
<h2>Tycoon S6 part by part</h2>
<table><thead><tr><th>Element</th><th>Tycoon S6 today</th><th>data-ui part</th><th>Behaviour that must survive</th></tr></thead>
<tbody>{''.join(f'<tr><td>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td></tr>' for a, b, c, d in STOCK)}</tbody></table>
</section>

<section>
<h2>Proof</h2>
<ul>{''.join(f'<li><b>{E(step)}</b>: {E(res)}</li>' for step, res in RESULTS.get('npm_test', []))}</ul>
<p>Case checks (gallery/examples/admin-shopify/checks.py): <b>{E(RESULTS.get('case_checks', '?'))}</b>. Unit (tests/unit/summary.test.mjs): <b>{E(RESULTS.get('unit', '?'))}</b>, and two deliberate mutations of the cell model fail it.</p>
<p class="muted">What the recording saw: {E(json.dumps(CAPTURE, ensure_ascii=False))}</p>
</section>

<section>
<h2>Next</h2>
<ul>{''.join(f'<li>{n}</li>' for n in RESULTS.get('notes', []))}</ul>
</section>
"""

page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin look on data-ui</title>
<style>
  :root {{ --bg: #fafafa; --fg: #1b1b1f; --muted: #66666e; --rule: #e3e3e6; --card: #fff; color-scheme: light dark; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #141416; --fg: #e8e8ea; --muted: #a0a0a8; --rule: #2e2e33; --card: #1c1c20; }} }}
  body {{ margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
  main {{ max-width: 1240px; margin: 0 auto; padding: 24px 16px 64px; }}
  h1 {{ font-size: 28px; margin: 4px 0 8px; }} h2 {{ font-size: 19px; margin: 32px 0 10px; }}
  .crumb, .muted {{ color: var(--muted); font-size: 13px; }}
  .verdict {{ font-size: 16px; max-width: 80ch; }}
  video, img {{ max-width: 100%; display: block; border-radius: 8px; border: 1px solid var(--rule); }}
  figure {{ margin: 0; }} figcaption {{ color: var(--muted); font-size: 12.5px; margin-top: 4px; }}
  .pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 18px; }}
  .grid3 {{ display: grid; grid-template-columns: 1fr 1fr 220px; gap: 12px; margin-bottom: 12px; align-items: start; }}
  .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; background: var(--card); }}
  th, td {{ border: 1px solid var(--rule); padding: 6px 8px; text-align: left; vertical-align: top; }}
  pre {{ background: var(--card); border: 1px solid var(--rule); border-radius: 8px; padding: 12px; overflow: auto; font-size: 12.5px; }}
  code {{ font-size: .92em; }}
  @media (max-width: 760px) {{ .pair, .grid3, .two {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body><main>{body}</main></body>
</html>
"""
dest = OUT / "admin-look-2026-10-28.html"
dest.write_text(page, encoding="utf-8")
print(dest, f"{dest.stat().st_size / 1024:.0f} KB")
