"""The Examples redesign's review report: five layouts beside the library pages they copy, the hero clip, the checks.

    python3 ~/data-ui/docs/build_gallery_report.py

Reads reports/media/gallery/ (hero.mp4, shots/*.webp, prior-art/*.webp, first-screen.json, gallery-checks.json; all
gitignored, made by the lane's capture runs) and writes reports/data-ui-gallery-2026-10-26.html, a small text page
that links that media. Paths are the main checkout's, so the report opens from there whichever worktree built it.
"""

from __future__ import annotations

import html
import json
import pathlib

REPORTS = pathlib.Path("~/data-ui/reports")
MEDIA = REPORTS / "media" / "gallery"
OUT = REPORTS / "data-ui-gallery-2026-10-26.html"
SITE = pathlib.Path(__file__).resolve().parents[1] / "dist" / "site"  # the build the screenshots came from
ACCESSED = "2026-10-26"

LIBS = "media/gallery/prior-art-libs/"
PROPOSALS = [
    {"key": "index", "n": 1, "name": "Index", "art": "Observable / D3 gallery grid + Vega-Lite's contents by type",
     "refs": [("observable-plot-gallery.webp", "Observable Plot gallery", "https://observablehq.com/@observablehq/plot-gallery"), ("vega-lite-examples.webp", "Vega-Lite examples: the nested contents", "https://vega.github.io/vega-lite/examples/")],
     "art_note": "Observable: category headings over uniform thumbnails with a one-line title, 5 columns. Vega-Lite: a nested table of contents (category, then example) above thumbnail sections by chart type.",
     "what": "Search and the App/View filters on top, then a contents box listing every view type and every example in it, then a section per type with uniform 16:10 pictures, the title and one line under each. Group by app is one click. The slider starts at 5.",
     "why": "Zach's pick. The grid is round one's, which he liked; the contents box reads the whole catalogue in one glance, and each name jumps to its picture.",
     "cost": "The contents box pushes the first pictures down, and once you scroll the navigation is gone. ECharts keeps it in a sidebar instead."},
    {"key": "echarts", "n": 3, "name": "ECharts", "art": "Apache ECharts examples",
     "refs": [("echarts-examples.webp", "Apache ECharts examples", "https://echarts.apache.org/examples/en/index.html")],
     "art_note": "A sidebar of chart types (Line, Bar, Pie...) beside a dense grid of image thumbnails, the name under each; 4 columns at 1440. No density control.",
     "what": "A sidebar with search, the types (each with its count, the one on screen marked) and the App/View filters, all resizable and foldable. Beside it, a dense grid in a section per type, with the title under each picture. The slider starts at 5.",
     "why": "The table of contents by type stays in view while the pictures scroll, which gives the most pictures per screen with the navigation never out of reach.",
     "cost": "The sidebar takes 210 px. There is no one-line summary: it is the tooltip, and the whole README is on the case page."},
    {"key": "shadcn", "n": 2, "name": "shadcn", "art": "shadcn/ui blocks and charts",
     "refs": [("shadcn-blocks.webp", "shadcn/ui blocks", "https://ui.shadcn.com/blocks"), ("shadcn-charts.webp", "shadcn/ui charts", "https://ui.shadcn.com/charts/area")],
     "art_note": "One block per row as a live preview with a Preview / Code toggle, the install command and viewport sizes; charts the same, by chart type. Not a thumbnail grid.",
     "what": "Two big cards per row, each with a title, a 2-line summary, Preview | .base and Open. Preview is the live kit, mounted when the card scrolls near. .base is the case's own file, with Copy. The views sit as tabs underneath. The slider starts at 2.",
     "why": "The .base file is to data-ui what code is to shadcn: you see the live result and the file that makes it, side by side, and copy it.",
     "cost": "2 cases in the first screen, so it is the opposite of 'many at a glance'. Each live preview loads that view's code."},
    {"key": "antd", "n": 4, "name": "Ant Design", "art": "Ant Design components overview",
     "refs": [("antd-overview.webp", "Ant Design components overview", "https://ant.design/components/overview")],
     "art_note": "A big search box, then category headings with a count, then bordered cards with the component's name on top and an illustration inset; 4 columns.",
     "what": "A larger search box, then bordered cards with the name in a header strip and the picture inset on a grey well, in a section per type with a count badge. The slider starts at 5.",
     "why": "The card frame makes each example an object you pick, the way a component catalogue reads, and the search is the main way in.",
     "cost": "The frames take room, so 8 cases fit in the first screen, and there is no summary line."},
    {"key": "storybook", "n": 5, "name": "Storybook", "art": "Storybook component docs",
     "refs": [("storybook-docs-primer.webp", "Primer React's Storybook", "https://primer.style/react/storybook/?path=/story/components-actionlist--default")],
     "art_note": "A searchable tree (component, then story) on the left, a live canvas, and Controls/Docs; Carbon's and Primer's docs are built this way.",
     "what": "A tree sidebar (type, then example, then each view, linked) with search, the canvas grid in the middle, and a Docs panel on the right for the example under the pointer: its whole summary, what it shows and a picture per view. Both panels drag, keep their width and fold away. The slider starts at 4.",
     "why": "Every view of every example is one click from the tree, and you read the README without leaving the page.",
     "cost": "The two panels take about 570 px; 10 cases fit in the first screen, and on a phone it drops both panels."},
]
OTHER = [("vega-lite-examples-grid.webp", "Vega-Lite examples: a section of thumbnails", "https://vega.github.io/vega-lite/examples/"), ("mui-x-datagrid.webp", "MUI X Data Grid", "https://mui.com/x/react-data-grid/"), ("mantine.webp", "Mantine UI", "https://ui.mantine.dev/"),
         ("radix-themes-playground.webp", "Radix Themes playground", "https://www.radix-ui.com/themes/playground"), ("tremor-blocks-grid.webp", "Tremor blocks", "https://blocks.tremor.so/blocks"),
         ("ag-grid-examples.webp", "AG Grid examples", "https://www.ag-grid.com/example/"), ("tanstack-table-examples.webp", "TanStack Table examples", "https://tanstack.com/table/v8/docs/framework/react/examples/basic"),
         ("recharts-examples.webp", "Recharts examples", "https://recharts.github.io/en-US/examples/"),
         ("nivo.webp", "Nivo", "https://nivo.rocks/"), ("shadcn-component-page.webp", "shadcn/ui component page (Preview / Code)", "https://ui.shadcn.com/docs/components/base/data-table"),
         ("catalyst.webp", "Catalyst (Tailwind)", "https://catalyst.tailwindui.com/docs")]


def esc(s) -> str:
    return html.escape(str(s))


def main() -> None:
    first = json.loads((MEDIA / "first-screen.json").read_text())
    checks = json.loads((MEDIA / "gallery-checks.json").read_text())
    passed = sum(c["ok"] for c in checks)
    rows_json = json.loads((SITE / "gallery" / "gallery.json").read_text())["rows"]
    n_cases = len(rows_json)
    pics = list((SITE / "gallery" / "thumbs").rglob("*.webp"))
    pics_mb = sum(f.stat().st_size for f in pics) / 1024 / 1024
    pics_max = max(f.stat().st_size for f in pics) // 1024
    cats = {}
    for r in rows_json:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    cards = []
    for p in sorted(PROPOSALS, key=lambda q: q["n"]):
        f = first[f"{p['key']}-light-1440"]
        phone = first[f"{p['key']}-light-390"]
        art = "".join(f'<figure><img src="{LIBS}{img}" alt="{esc(label)}" loading="lazy"><figcaption>{esc(label)} · <a href="{esc(url)}">{esc(url)}</a> · accessed {ACCESSED}</figcaption></figure>' for img, label, url in p["refs"])
        rec = ' <span class="rec">the default · Zach\'s pick</span>' if p["key"] == "index" else ""
        cards.append(f"""<section class="prop" id="{p['key']}">
<h2>{p['n']}. {esc(p['name'])} <span class="muted">· {esc(p['art'])}</span>{rec}</h2>
<p class="first"><b>First screen at 1440 px: {f['fully']} of {n_cases} cases fully visible, {f['cols']} columns.</b> At 390 px: {phone['cols']} column{'s' if phone['cols'] != 1 else ''}, no sideways scroll.</p>
<p>{esc(p['what'])}</p>
<ul><li><b>Why it scans:</b> {esc(p['why'])}</li><li><b>What it costs:</b> {esc(p['cost'])}</li><li><b>The library:</b> {esc(p['art_note'])}</li></ul>
<div class="trio" style="--n:{2 + len(p['refs'])}">
<figure><img src="media/gallery/shots/{p['key']}-light-1440.webp" alt="{esc(p['name'])}, light, 1440 px" loading="lazy"><figcaption>data-ui · {esc(p['name'])} · light · 1440</figcaption></figure>
<figure><img src="media/gallery/shots/{p['key']}-dark-1440.webp" alt="{esc(p['name'])}, dark, 1440 px" loading="lazy"><figcaption>data-ui · {esc(p['name'])} · dark · 1440</figcaption></figure>
{art}
</div>
<details><summary>Phone, 390 px</summary><img class="phone" src="media/gallery/shots/{p['key']}-light-390.webp" alt="{esc(p['name'])} at 390 px" loading="lazy"></details>
</section>""")
    rows = "".join(f'<li class="{"ok" if c["ok"] else "bad"}"><b>{"PASS" if c["ok"] else "FAIL"}</b> {esc(c["name"])} <span class="muted">{esc(c["value"]) if c["value"] is not None else ""}</span></li>' for c in checks)
    others = "".join(f'<figure><img src="{LIBS}{img}" alt="{esc(label)}" loading="lazy"><figcaption>{esc(label)} · <a href="{esc(url)}">{esc(url)}</a> · accessed {ACCESSED}</figcaption></figure>' for img, label, url in OTHER)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>data-ui Examples redesign</title>
<style>
:root {{ color-scheme: light; --bg: #fff; --fg: #0a0a0a; --muted: #6b6b6b; --card: #fafafa; --border: #e5e5e5; --ok: #15803d; --bad: #dc2626; --accent: #2a78d6; }}
@media (prefers-color-scheme: dark) {{ :root {{ color-scheme: dark; --bg: #0a0a0a; --fg: #fafafa; --muted: #a3a3a3; --card: #141414; --border: #2a2a2a; --ok: #4ade80; --bad: #f87171; --accent: #3987e5; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 1320px; margin: 0 auto; padding: 28px 16px 60px; }}
h1 {{ font-size: 28px; margin: 0 0 8px; }} h2 {{ font-size: 20px; margin: 0 0 6px; }}
.verdict {{ font-size: 17px; border-left: 4px solid var(--accent); padding: 10px 14px; background: var(--card); border-radius: 0 10px 10px 0; }}
.muted {{ color: var(--muted); font-weight: 400; }}
video, img {{ max-width: 100%; display: block; border: 1px solid var(--border); border-radius: 10px; }}
.prop {{ border-top: 1px solid var(--border); padding: 26px 0 10px; }}
.rec {{ font-size: 12px; background: var(--accent); color: #fff; border-radius: 999px; padding: 2px 9px; vertical-align: middle; }}
.trio {{ display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: 12px; }}
.others {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }}
figure {{ margin: 0; }} figcaption {{ font-size: 12px; color: var(--muted); margin-top: 4px; overflow-wrap: anywhere; }}
.phone {{ max-width: 300px; margin-top: 8px; }}
.checks {{ list-style: none; padding: 0; font-size: 13.5px; }} .checks li {{ padding: 3px 0; border-bottom: 1px solid var(--border); overflow-wrap: anywhere; }}
.checks .ok b {{ color: var(--ok); }} .checks .bad b {{ color: var(--bad); }}
.box {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; }} td, th {{ text-align: left; border-bottom: 1px solid var(--border); padding: 6px 8px; vertical-align: top; }}
.tablewrap {{ overflow-x: auto; }}
code {{ font-size: .9em; }}
@media (max-width: 800px) {{ .trio {{ grid-template-columns: minmax(0, 1fr); }} }}
</style></head><body><main>
<p class="muted">data-ui · lane/gallery · {ACCESSED} · round 2: library examples pages</p>
<h1>Examples, as pictures</h1>
<p class="verdict"><b>Gallery is now Examples. Index is the default, as Zach decided: round one's grid of real pictures with Vega-Lite's contents on top, grouped by view type (by app is one click). The 1–8 column slider stays. shadcn's live preview with a .base tab, ECharts, Ant Design and Storybook stay behind the switcher.</b> It is on <code>lane/gallery</code> and not merged. All {passed}/{len(checks)} gallery checks pass, and every <code>npm test</code> step is green. The existing browser checks crashed Chromium once at a load average of 63, then passed 431/431 when rerun alone. The URL stays <code>gallery/</code>, so links and the deploy's checks hold. The pictures are {len(pics)} WebP files, {pics_mb:.1f} MB in all, the largest {pics_max} KB, captured by <code>site/capture-thumbs.py</code> and never committed.</p>

<h2>The default layout in use</h2>
<p class="muted">Real headless Chromium on the built site, Index layout: drag the slider from 2 to 6 columns, filter to Vibe Tracks (the contents narrow to the 4 types left), hover a picture to flip through its views, open the example on that view.</p>
<video src="media/gallery/hero.mp4" poster="media/gallery/hero-poster.webp" autoplay muted loop playsinline controls></video>
<p class="muted">No video? <a href="media/gallery/hero.gif">The GIF</a>.</p>

<h2 style="margin-top:28px">What every layout shares</h2>
<ul>
<li><b>Grouped by view type by default:</b> {', '.join(f'{k} {v}' for k, v in cats.items())}. One click on Group switches to by app (robotparts, Vibe Tracks...), and the choice is remembered. A case sits in its first view's type unless its README says <code>- **Category:** Analyses</code>. Two cases are filed by hand: the experiment tracker and the side-by-side are Analyses. 3D and the other types appear when a case names them.</li>
<li><b>A real picture per view, in the page's theme,</b> captured from the built site (<code>&lt;data-views view=… toolbar=none&gt;</code> at 720×450, 2×). Hover flips through the case's views, and clicking opens the view you are on. A missing picture is drawn live.</li>
<li><b>The column slider:</b> a range input with − and + buttons, the arrow keys, Home and End, ctrl or ⌘ + wheel, and a two-finger pinch. It is remembered per layout. On a narrow screen it draws as many columns as fit and says "3 of 6". None of the {len(PROPOSALS) + len(OTHER)} library pages has one; the nearest are Radix's scaling and AG Grid's row-count picker.</li>
<li><b>Search plus compact App/View filters.</b> The chips' choice stays in the URL (<code>?app=…&amp;type=…</code>).</li>
<li><b>Every example has a page.</b> A check fetches every card's link and finds its title there.</li>
<li><b>The temporary switcher</b> sits bottom right, is remembered and is never a URL flag. The default is Index.</li>
</ul>

{''.join(cards)}

<section class="prop"><h2>The other libraries looked at</h2>
<p>All accessed {ACCESSED}. Tailwind UI's blocks redirect to a login, so there is no capture. Round one's picks (Dribbble, Apple Photos, Pinterest, Sketchfab) are dropped, as Zach asked. The Vega-Lite grid section is below.</p>
<ul>
<li><b>MUI X, Mantine and TanStack Table</b> keep one example per docs page, with code beside it.</li>
<li><b>Nivo</b> has the densest grid: 6 columns and 22 tiles in the first screen.</li>
<li><b>Recharts and Tremor</b> show live chart cards, 3 per row.</li>
<li><b>AG Grid</b> runs one live grid with scenario tabs.</li>

</ul>
<div class="others">{others}</div></section>

<section class="prop"><h2>Off-the-shelf parts</h2>
<div class="tablewrap"><table><tr><th>Element</th><th>Before</th><th>Stock part</th><th>Behaviour that must survive</th></tr>
<tr><td>Thumbnail capture</td><td>text cards</td><td>Playwright (Chromium) + Pillow WebP</td><td>A picture is the real kit on the real data</td></tr>
<tr><td>A missing picture; shadcn's Preview</td><td>—</td><td>The landing page's live <code>&lt;data-views&gt;</code> mount</td><td>A new case shows before anyone captures it</td></tr>
<tr><td>Sidebar and Docs widths</td><td>—</td><td>The kit's <code>makeResizable</code> (resize.js)</td><td>Drag, ←/→, double-click reset, remembered</td></tr>
<tr><td>Contents tree, sections</td><td>—</td><td><code>&lt;details&gt;</code>, in-page anchors, IntersectionObserver</td><td>Jump to a type; the one on screen marked</td></tr>
<tr><td>.base pane, Copy</td><td>case page only</td><td>site.js's own <code>.file</code> Copy button</td><td>The source shown is the file on disk</td></tr>
<tr><td>Column control</td><td>fixed grid</td><td><code>&lt;input type=range&gt;</code> + CSS grid <code>repeat(var(--cols))</code></td><td>Keyboard and touch, remembered</td></tr>
</table></div></section>

<section class="prop"><h2>Checks ({passed}/{len(checks)})</h2>
<p class="muted"><code>tests/browser/gallery_checks.py</code> is its own file, run by <code>npm test</code>. Two checks have been seen red. The picture check went red when I corrupted one cached picture (round one). The ECharts sidebar check went red until the handle followed the sticky sidebar on scroll.</p>
<ul class="checks">{rows}</ul></section>

<section class="prop"><h2>Decisions for Zach</h2>
<div class="box"><ul>
<li><b>The layouts behind the switcher:</b> Index is the default, as you decided. The other four stay until you say which to delete; each is one CSS block and one line in <code>LAYOUTS</code>. My runner-up is ECharts, which keeps the same contents as a sidebar that never scrolls away.</li>
<li><b>The categories:</b> the ten you named, filled by each case's first view, plus two by hand. Silence keeps them. A case's README can move it with <code>- **Category:**</code>.</li>
<li><b>Kept on purpose:</b> the URL stays <code>gallery/</code>, because the deploy's checks and every link use it. Only the nav label and the page say Examples. The landing page's "Open the gallery" button is the integrator's page, so I left it.</li>
<li><b>Found in the kit, not fixed here:</b> <code>makeResizable</code> re-places its handle only on resize, so a sticky panel's handle drifts on scroll. The page sends the kit a resize event on scroll. The fix belongs in core (re-place on scroll).</li>
</ul></div></section>
</main></body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(OUT, f"{OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
