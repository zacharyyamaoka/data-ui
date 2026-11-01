"""Browser checks for this case (run by tests/browser/checks.py): the freshness table grouped by kind, its stale
badges and preset, the list view of the same rows with fold, the record view as a source page; light and dark at
1280 and 390 px."""

V = "#example"


def open_page(ctx, path, width=1280, height=900, dark=False, mobile=False):
    """ctx.page, then until the view's own code has drawn (the host sets data-view after it)."""
    page = ctx.page(path, width=width, height=height, dark=dark, mobile=mobile)
    page.wait_for_selector(f"{V}[data-view]", timeout=15000)
    return page


def tab(page, name):
    page.click(f"{V} .dv-tab[data-name='{name}']")
    page.wait_for_selector(f"{V} .dv-view")
    page.wait_for_timeout(250)


def run(ctx, path):
    check = ctx.check
    page = open_page(ctx, path)
    page.evaluate("localStorage.clear()")
    status = page.inner_text(f"{V} .dv-status")
    check("sources: 43 sources grouped by kind, 9 kinds", "43 of 43 rows · 9 groups" in status, status.split(" · Unfold")[0])
    tab(page, "Needs refresh")
    status = page.inner_text(f"{V} .dv-status")
    stale = page.locator(f"{V} td[data-col='stale_kinds'] .dv-badge.dv-h8").count()
    check("preset 'Needs refresh': the 15 sources whose prices or software readings aged out, each badge in the warning slot",
          status.startswith("15 of 43 rows") and stale >= 15, f"{status.split(' · ')[0]}; {stale} red badges")
    tab(page, "List")
    groups = page.locator(f"{V} .dv-list-group").count()
    lines = page.locator(f"{V} .dv-list-line").count()
    badge = page.locator(f"{V} .dv-list-line .dv-list-prop[data-col='freshness'] .dv-badge").count()
    height = page.evaluate("document.querySelector('#example .dv-list').getBoundingClientRect().height")
    # WHY the list's height, not a count of lines: only the lines on screen are in the DOM (virtualised)
    check("list: 43 lines under 9 headings, 30 px each (only the visible ones in the DOM), freshness a badge inline",
          height == (43 + 9) * 30 and groups < 9 + 43 and badge == lines, f"list {height:.0f} px; {groups} headings and {lines} lines in the DOM")
    page.click(f"{V} .dv-status [data-fold=closed]")
    page.wait_for_timeout(150)
    folded = page.locator(f"{V} .dv-list-line").count()
    page.locator(f"{V} .dv-list-group").first.click()
    page.wait_for_timeout(150)
    check("list: Fold all leaves the headings; a heading unfolds its own group", folded == 0 and page.locator(f"{V} .dv-list-line").count() == 3,
          f"{folded} lines folded, {page.locator(f'{V} .dv-list-line').count()} after opening atlas")
    page.locator(f"{V} .dv-list-line").first.click()
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    check("list: a line opens the host's side peek", page.inner_text(f"{V} .dv-peek h2") == "actuator-atlas", page.inner_text(f"{V} .dv-peek h2"))
    page.keyboard.press("Escape")
    tab(page, "Source page")
    sections = page.locator(f"{V} .dv-record-section h3").all_inner_texts()
    check("record: a source page in four sections", sections == ["The source", "Freshness", "Links", "Refresh"], sections)
    page.evaluate("localStorage.clear()")
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            name = f"{'dark' if dark else 'light'}, {width} px"
            page = open_page(ctx, path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            sw = page.evaluate("document.scrollingElement.scrollWidth")
            check(f"sources, {name}: the table draws, no sideways page scroll", page.locator(f"{V} tbody tr.dv-row").count() > 5 and sw <= width, f"scrollWidth {sw}")
            page.locator(V).scroll_into_view_if_needed()  # the shot shows the views, not the README above them
            ctx.shot(page, f"robotparts-sources-{'dark' if dark else 'light'}-{width}")
            tab(page, "List")
            sw = page.evaluate("document.scrollingElement.scrollWidth")
            check(f"sources list, {name}: lines draw, no sideways page scroll", page.locator(f"{V} .dv-list-line").count() > 5 and sw <= width, f"scrollWidth {sw}")
            page.locator(V).scroll_into_view_if_needed()  # the shot shows the views, not the README above them
            ctx.shot(page, f"robotparts-sources-list-{'dark' if dark else 'light'}-{width}")
            page.context.close()
