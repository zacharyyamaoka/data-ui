"""Browser checks for the bar, Obsidian's way (views="dropdown" filters="expanded" display="panel"; docs/CONTRACT.md
§15), run by tests/browser/checks.py. The words' active state is read from the page, after a real pick in a menu."""

import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location("toolbar_bar_checks", pathlib.Path(__file__).resolve().parents[1] / "toolbar-bar" / "checks.py")
bar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bar)
V = bar.V


def words(page):
    return [w.strip() for w in page.locator(f"{V} .dv-bar-tools [data-bar=menu]").all_inner_texts()]


def run(ctx, path):
    bar.CTX = ctx
    check = ctx.check
    for dark in (False, True):
        page = ctx.page(path, width=1280, dark=dark)
        w = words(page)
        b = bar.boxes(page)
        check(f"expanded ({'dark' if dark else 'light'}, 1280): Sort · Group · Filter · Properties are words in the bar, Sort reads what is set; the views are one chip",
              [x.split(":")[0].split()[0] for x in w] == ["Sort", "Group", "Filter", "Properties"] and w[0] == "Sort: Peak torque"
              and b["chip"] and not b["chip"]["hidden"] and (b["tabs"] is None or b["tabs"]["hidden"]) and b["bar"]["height"] <= 52, {"words": w})
        ctx.shot(page, f"toolbar-obsidian-{'dark' if dark else 'light'}-1280")
        page.context.close()

    page = ctx.page(path, width=1280)
    word = page.locator(f"{V} [data-bar=menu][data-name=sort]")
    word.click()
    page.wait_for_selector(f"{V} .dv-pop:not([hidden]) .dv-rule select[data-k=p]", timeout=3000)
    a, pop = word.bounding_box(), page.locator(f"{V} .dv-pop").bounding_box()
    page.select_option(f"{V} .dv-pop .dv-rule select[data-k=p]", "mass")
    bar.settle(page)
    check("expanded: the Sort word opens the Sort menu under itself; picking Mass makes the word read 'Sort: Mass'",
          words(page)[0] == "Sort: Mass" and abs(pop["y"] - (a["y"] + a["height"])) <= 10, {"words": words(page), "menu top - word bottom": round(pop["y"] - a["y"] - a["height"])})
    page.keyboard.press("Escape")
    page.click(f"{V} [data-bar=menu][data-name=group]")
    page.wait_for_selector(f"{V} .dv-pop:not([hidden]) select[data-k=g0]", timeout=3000)
    page.select_option(f"{V} .dv-pop select[data-k=g0]", "brand")
    bar.settle(page)
    groups = page.evaluate("(document.querySelector('#example').model.groups || []).length")
    check("expanded: Group by Brand groups the rows and the word reads 'Group: Brand'", words(page)[1] == "Group: Brand" and groups > 5, {"words": words(page), "groups": groups})
    page.keyboard.press("Escape")
    page.check("data-facets input[data-p=brand][data-value=Steadywin]")
    bar.settle(page)
    check("expanded: a rail pick counts on the Filter word's badge (no pill row: filters has no 'pills')",
          words(page)[2].split() == ["Filter", "1"] and not bar.pills(page), {"words": words(page), "pills": bar.pills(page)})
    ctx.shot(page, "toolbar-obsidian-words-light-1280")
    # the chip's › opens Configure view (Bases): the name, the Layout grid with the layout's options, Copy as .base entry
    bar.open_view_menu(page)
    page.click(f"{V} .dv-pop .dv-vm-row[data-name='Brand × form'] .dv-vm-config")
    page.wait_for_selector(f"{V} .dv-pop .dv-vm-name", timeout=3000)
    # the pivot's code (and so its options()) loads on first use: the page draws them once the pivot has drawn
    page.wait_for_function("document.querySelector('#example').dataset.view === 'pivot'", timeout=15000)
    page.wait_for_selector(f"{V} .dv-pop [data-opt]", timeout=5000)
    got = page.evaluate(f"""(() => {{ const p = document.querySelector('{V} .dv-pop');
      return {{ name: p.querySelector('.dv-vm-name').value, layouts: p.querySelectorAll('.dv-layout').length, on: (p.querySelector('.dv-layout.dv-on') || {{}}).dataset?.type,
        options: p.querySelectorAll('[data-opt]').length, copy: !!p.querySelector('[data-act=copy-base]'), del: !!p.querySelector('[data-act=delete]') }}; }})()""")
    check("view menu: a view's › opens it and its Configure view: the name, the Layout grid (Pivot marked), the pivot's options and Copy as .base entry; no Delete on a preset",
          got["name"] == "Brand × form" and got["layouts"] >= 12 and got["on"] == "pivot" and got["options"] >= 4 and got["copy"] and not got["del"]
          and page.evaluate("document.querySelector('#example').origin.name") == "Brand × form", got)
    ctx.shot(page, "toolbar-obsidian-configure-light-1280")
    page.context.close()

    bar.narrow_390(ctx, path, check, "toolbar-obsidian", shoot="toolbar-obsidian")

    bar.one_row(ctx, path, check, "toolbar-obsidian")
