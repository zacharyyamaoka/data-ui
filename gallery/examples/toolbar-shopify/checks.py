"""Browser checks for the bar, Shopify's way (views="dropdown" promote=""; docs/CONTRACT.md §15): exactly three elements
on the bar, Display holding everything, the bulk band over the header. Run by tests/browser/checks.py; measured."""

import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location("toolbar_bar_checks", pathlib.Path(__file__).resolve().parents[1] / "toolbar-bar" / "checks.py")
bar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bar)
V = bar.V

CONTROLS = """() => { const bar = document.querySelector('#example > .dv-bar');
  const shown = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !e.closest('[hidden]') && getComputedStyle(e).visibility !== 'hidden'; };
  // the bar's elements: the view selector, the search (box or icon) and the tools, each counted once
  const parts = [...bar.querySelectorAll('.dv-bar-views > *, .dv-bar-tools > *')].filter(shown).map((e) => e.dataset.bar || e.className);
  const box = bar.querySelector('.dv-bar-query input'); if (box && shown(box)) parts.push('query');
  return parts; }"""


def run(ctx, path):
    bar.CTX = ctx
    check = ctx.check
    for dark, width in ((False, 1280), (True, 1280), (False, 375), (True, 375)):
        page = ctx.page(path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=width < 400)
        got = page.evaluate(CONTROLS)
        check(f"Shopify preset ({'dark' if dark else 'light'}, {width}): exactly three elements on the bar: the view chip, the search, Display",
              len(got) == 3 and "views" in got and "display" in got and ("query" in got or "search" in got), got)
        ctx.shot(page, f"toolbar-shopify-{'dark' if dark else 'light'}-{width}")
        page.context.close()
    page = ctx.page(path, width=1280)
    page.click(f"{V} [data-bar=display]")
    page.wait_for_selector(f"{V} .dv-settings:not([hidden])", timeout=3000)
    rows = page.evaluate(f"[...document.querySelectorAll('{V} .dv-settings .dv-set-row')].map((r) => r.dataset.page || r.dataset.act)")
    check("Shopify preset: Display holds everything (Layout, Frame, Property visibility, Filter, Sort, Group, the copies)",
          all(x in rows for x in ("layout", "frame", "properties", "filter", "sort", "group")), rows)
    page.context.close()
    bar.one_row(ctx, path, check, "toolbar-shopify")
