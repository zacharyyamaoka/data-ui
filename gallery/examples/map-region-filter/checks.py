"""Browser checks for map-region-filter (docs/CONTRACT.md §42): a district click on the map filters the table panel to that district's years and clears on a second click. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-region-filter"

sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from dashboard_helpers import counts, ready as dash_ready  # noqa: E402
import json
ALL = rows(HERE, "../map-bc-disposal/disposal.json")
CAPITAL = [r for r in ALL if r["rd"] == "capital"]


def run(ctx, path):
    check = ctx.check
    page = ctx.page(path)
    dash_ready(page)
    ready(ctx, page, dash=True)
    before = counts(page)
    table = [k for k in before if not k.endswith(":cards") and before[k] == len(ALL)]
    check("region filter: the table panel starts with every row", bool(table), before)
    p = click_feature(page, "dvl-0", '(p) => p.rd === "capital"', dash=True)
    ctx.until(page, "(n) => [...document.querySelectorAll('#example .dd-panel data-views .dv-status')].some((s) => s.textContent.startsWith(n + ' of'))", len(CAPITAL))
    after = counts(page)
    sel = page.evaluate("(s) => { const m = document.querySelector(s).dvMap; const f = m.querySourceFeatures('dvl-0').find((f) => f.properties.rd === 'capital'); return f ? m.getFeatureState({ source: 'dvl-0', id: f.id }).sel : null; }", scope(True))
    check("region filter: a click on Capital narrows the table to Capital's years, and the district is highlighted",
          p is not None and table and after[table[0]] == len(CAPITAL) and sel is True, f"{before} -> {after}; oracle {len(CAPITAL)}; highlighted {sel}")
    click_feature(page, "dvl-0", '(p) => p.rd === "capital"', dash=True)
    ctx.until(page, "(n) => [...document.querySelectorAll('#example .dd-panel data-views .dv-status')].some((s) => s.textContent.startsWith(n.toLocaleString('en-US') + ' of'))", len(ALL))
    again = counts(page)
    check("region filter: a second click clears the selection", table and again[table[0]] == len(ALL), again)
    page.context.close()
    themes(ctx, path, CASE, dash=True)
