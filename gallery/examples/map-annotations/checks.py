"""Browser checks for map-annotations (docs/CONTRACT.md §42): a callout per figure, its dot on the facility's point, its label carrying the published figure. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-annotations"

ROWS = rows(HERE, "facts.json")


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    n = page.locator(f"{V} .dv-map-callout").count()
    check("callouts: one per published figure", n == len(ROWS), f"{n} vs {len(ROWS)}")
    off = page.evaluate("""(s) => { const el = document.querySelector(s), m = el.dvMap, c = m.getCanvas().getBoundingClientRect();
      return [...el.querySelectorAll('.dv-map-callout')].map((co) => { const d = co.querySelector('.dv-map-dot').getBoundingClientRect(); return [d.x + d.width / 2 - c.x, d.y + d.height / 2 - c.y]; }); }""", scope(False))
    want = page.evaluate("([s, pts]) => { const m = document.querySelector(s).dvMap; return pts.map((p) => { const q = m.project([p[1], p[0]]); return [q.x, q.y]; }); }", [scope(False), [val(r["location"]) for r in ROWS]])
    worst = max(min(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for b in want) for a in off)
    check("callouts: every leader's dot sits on its facility's point (≤ 2 px)", worst <= 2, f"worst {worst:.2f} px")
    texts = page.locator(f"{V} .dv-map-bubble").all_inner_texts()
    first = ROWS[0]
    check("callouts: a label carries its figure exactly as stored, with its unit", any(first["facility"] in t and f"{first['figure']:,} {first['unit']}" in t for t in texts), texts[:3])
    page.locator(f"{V} .dv-map-bubble", has_text=first["facility"]).first.click()
    n, title = peek_rows(page)
    check("callouts: a click on a label opens its row", first["facility"] in title, title)
    page.context.close()
    themes(ctx, path, CASE)
