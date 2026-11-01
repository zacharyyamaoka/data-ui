"""Browser checks for map-dashboard (docs/CONTRACT.md §42): a district click on the map cross-filters the KPI and the trend chart. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-dashboard"

sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from dashboard_helpers import counts, num, ready as dash_ready  # noqa: E402
ALL = rows(HERE, "../map-bc-disposal/disposal.json")
Y24 = [r for r in ALL if r["year"] == 2024]
TOTAL = sum(val(r["disposal_t"]) for r in Y24 if val(r["disposal_t"]) is not None)
CAP = [r for r in Y24 if r["rd"] == "capital"]
CAP_TREND = [r for r in ALL if r["rd"] == "capital" and r["year"] >= 2012]


def kpi(page):
    return num(page.inner_text(f"{V} data-kpi .dv-kpi-value"))


def run(ctx, path):
    check = ctx.check
    page = ctx.page(path)
    dash_ready(page)
    ready(ctx, page, dash=True)
    check("dashboard: the KPI is the province's 2024 disposal, summed from the rows", kpi(page) == TOTAL, f"{kpi(page)} vs {TOTAL}")
    click_feature(page, "dvl-0", '(p) => p.rd === "capital"', dash=True)
    want = sum(val(r["disposal_t"]) for r in CAP)
    ctx.until(page, "(w) => { const v = document.querySelector('#example data-kpi .dv-kpi-value'); return v && Number(v.textContent.replace(/[^0-9.]/g, '')) === w; }", want)
    check("dashboard: a click on Capital sets the KPI to Capital's 2024 disposal", kpi(page) == want, f"{kpi(page)} vs {want}")
    c = counts(page)
    check("dashboard: and narrows the trend chart to Capital's years since 2012", len(CAP_TREND) in c.values(), f"{c}; oracle {len(CAP_TREND)}")
    page.context.close()
    themes(ctx, path, CASE, dash=True)
