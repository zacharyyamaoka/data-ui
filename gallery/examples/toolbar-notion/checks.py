"""Browser checks for the bar, Notion's way (views="tabs" filters="pills" display="panel"; docs/CONTRACT.md §15),
run by tests/browser/checks.py. Measured: the tab strip's scrollWidth against its clientWidth, the status line."""

import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location("toolbar_bar_checks", pathlib.Path(__file__).resolve().parents[1] / "toolbar-bar" / "checks.py")
bar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bar)
V = bar.V


def run(ctx, path):
    bar.CTX = ctx
    check = ctx.check
    for dark in (False, True):
        page = ctx.page(path, width=1280, dark=dark)
        b = bar.boxes(page)
        tabs = page.locator(f"{V} .dv-viewtabs [role=tab]:visible").count()
        more = page.locator(f"{V} .dv-viewtabs [data-bar=more]")
        more_text = more.inner_text().strip() if more.count() else ""
        check(f"tabs ({'dark' if dark else 'light'}, 1280): the views that fit show as tabs, the rest fold into 'N more…', and the strip never overflows",
              b["tabs"] and not b["tabs"]["hidden"] and 1 <= tabs < 10 and more_text == f"{10 - tabs} more…" and b["tabs"]["sw"] <= b["tabs"]["cw"] + 1
              and page.locator(f"{V} .dv-viewtabs [data-bar=add-view]").count() == 1 and (b["chip"] is None or b["chip"]["hidden"]) and b["bar"]["height"] <= 52,
              {"tabs": tabs, "more": more_text, "strip": [b["tabs"]["sw"], b["tabs"]["cw"]] if b["tabs"] else None})
        ctx.shot(page, f"toolbar-notion-{'dark' if dark else 'light'}-1280")
        page.context.close()

    page = ctx.page(path, width=1280)
    page.click(f"{V} .dv-viewtabs [data-bar=more]")
    page.wait_for_selector(f"{V} .dv-pop:not([hidden]) .dv-vm-row", timeout=3000)
    listed = page.locator(f"{V} .dv-pop .dv-vm-row").count()
    last = page.locator(f"{V} .dv-pop .dv-vm-row").last.get_attribute("data-name")
    ctx.shot(page, "toolbar-notion-more-light-1280")
    page.locator(f"{V} .dv-pop .dv-vm-row").last.click()
    bar.settle(page)
    sel = page.locator(f"{V} .dv-viewtabs [aria-selected=true]")
    b = bar.boxes(page)
    check("tabs: 'N more…' lists every view; picking one from the overflow opens it and brings its tab into the strip",
          listed == 10 and page.evaluate("document.querySelector('#example').origin.name") == last and sel.count() == 1 and sel.inner_text().strip().endswith(last)
          and b["tabs"]["sw"] <= b["tabs"]["cw"] + 1, {"listed": listed, "picked": last, "selected tab": sel.inner_text().strip() if sel.count() else None})
    page.click(f"{V} .dv-viewtabs [data-bar=add-view]")
    page.wait_for_selector(f"{V} .dv-pop:not([hidden]) .dv-layouts", timeout=3000)
    check("tabs: + opens the Add view grid of layouts", page.locator(f"{V} .dv-pop .dv-layout").count() >= 12)
    page.keyboard.press("Escape")
    bar.settle(page)
    # pills: the rail is not on this page's bar (no "Filters" toggle), the pills still mirror it
    page.check("data-facets input[data-p=form][data-value='integrated actuator']")
    bar.settle(page)
    p = bar.pills(page)
    check("tabs + pills: a rail pick shows as a pill under the tabs; no rail toggle unless filters has 'rail'",
          len(p) == 1 and p[0].startswith("Form") and "integrated actuator" in p[0] and bar.rows_shown(page) == 311 and page.locator(f"{V} [data-bar=rail]").count() == 0, p)
    page.click(f"{V} [data-bar=display]")
    page.wait_for_selector(f"{V} .dv-settings.dv-settings-panel:not([hidden])", timeout=3000)
    bar.settle(page)
    ctx.shot(page, "toolbar-notion-settings-light-1280")
    page.context.close()

    bar.narrow_390(ctx, path, check, "toolbar-notion", shoot="toolbar-notion")

    # frame="tabs" (CONTRACT §12): the view tabs read as the page's nav (underlined in the accent, no fill), still on the
    # bar's one row with the query box and the tools (§15 note 2026-10-26: the bar never wraps)
    for dark in (False, True):
        page = ctx.page(path, width=1280, dark=dark)
        page.evaluate("document.querySelector('#example').setAttribute('frame', 'tabs')")
        bar.settle(page)
        got = page.evaluate("""(() => { const v = document.querySelector('#example'); const r = (s) => v.querySelector(s).getBoundingClientRect();
          const mid = (s) => { const b = r(s); return b.top + b.height / 2; };
          const strip = v.querySelector('.dv-viewtabs'), on = v.querySelector('.dv-vtab.dv-on');
          return { strip: [strip.scrollWidth, strip.clientWidth], rows: [mid('.dv-vtab.dv-on'), mid('.dv-bar-query input'), mid('[data-bar=display]')].map((x) => Math.round(x)),
            bar: Math.round(r('.dv-bar').height), underline: getComputedStyle(on).borderBottomColor, shown: v.querySelectorAll('.dv-viewtabs [role=tab]:not([hidden])').length,
            onBg: getComputedStyle(on).backgroundColor }; })()""")
        check(f"frame=tabs + views=tabs ({'dark' if dark else 'light'}): the tabs, the query box and the tools share the one row (one height), the open tab underlined with no fill; the strip never overflows",
              max(got["rows"]) - min(got["rows"]) <= 1 and got["bar"] <= 50 and got["underline"] not in ("rgba(0, 0, 0, 0)", "transparent") and got["onBg"] in ("rgba(0, 0, 0, 0)", "transparent")
              and got["strip"][0] <= got["strip"][1] + 1 and got["shown"] >= 3, got)
        ctx.shot(page, f"toolbar-notion-frame-tabs-{'dark' if dark else 'light'}-1280")
        page.context.close()

    bar.one_row(ctx, path, check, "toolbar-notion")
