"""Browser checks for this case (run by tests/browser/checks.py): the compare view (best marks, differences only, add
and remove, the photo slider), the record view as a part page, light and dark at 1280 and 390 px."""

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


def heads(page):
    return page.locator(f"{V} .dv-cmp thead th[data-r] .dv-cmp-open").all_inner_texts()


def run(ctx, path):
    check = ctx.check
    page = open_page(ctx, path)
    page.evaluate("localStorage.clear()")
    check("compare: four actuators side by side, one column each", heads(page) == ["Steadywin GIM4305-10", "Steadywin GIM6010-8", "CubeMars AK60-6 V3.0", "MyActuator RMD-X6-7"], heads(page))
    best = page.locator(f"{V} tr[data-p='peak_torque'] td.dv-cmp-best").all_inner_texts()
    check("compare: the best peak torque (higher is better) is marked, and only it", len(best) == 1 and best[0].startswith("11"), best)
    best_mass = page.locator(f"{V} tr[data-p='mass'] td.dv-cmp-best").all_inner_texts()
    check("compare: the lightest mass (lower is better) is marked", len(best_mass) == 1 and best_mass[0].startswith("150"), best_mass)
    page.wait_for_selector(f"{V} img-comparison-slider.rendered", timeout=5000)
    imgs = page.evaluate("[...document.querySelectorAll('#example .dv-cmp-photos img')].map(i => i.complete && i.naturalWidth > 0)")
    check("compare: each column's robotparts photo loads from this site, and two of them sit in the slider",
          imgs == [True] * 4 and page.locator(f"{V} img-comparison-slider img").count() == 2, imgs)
    all_rows = page.locator(f"{V} tr.dv-cmp-row").count()
    tab(page, "Differences only")
    diff_rows = page.locator(f"{V} tr.dv-cmp-row").count()
    hidden = page.inner_text(f"{V} tr.dv-cmp-hidden") if page.locator(f"{V} tr.dv-cmp-hidden").count() else ""
    check("differences only hides the properties that read the same on every row, and says how many",
          0 < diff_rows < all_rows and page.locator(f"{V} tr.dv-cmp-same").count() == 0 and str(all_rows - diff_rows) in hidden, f"{diff_rows} of {all_rows} rows; {hidden}")
    tab(page, "Side by side")
    page.click(f"{V} [data-remove='aifitlab-8649843966088']")
    page.wait_for_timeout(250)
    after = heads(page)
    url = page.evaluate("location.hash")
    check("a column's ✕ removes it, and the pick is the view's compare.rows (in the URL)", len(after) == 3 and "MyActuator RMD-X6-7" not in after and "&v=" in url, after)
    page.select_option(f"{V} [data-add]", "aifitlab-8542620287112")
    page.wait_for_timeout(250)
    check("+ Add a row adds a column", heads(page)[-1] == "Steadywin GIM8108-8", heads(page))
    tab(page, "Pick your own")
    empty = page.inner_text(f"{V} .dv-cmp tbody")
    page.select_option(f"{V} [data-add]", "aifitlab-8682649092232")
    page.wait_for_timeout(200)
    page.select_option(f"{V} [data-add]", "aifitlab-8541438771336")
    page.wait_for_timeout(250)
    check("compare.rows: selection starts empty and fills as you pick", "Pick 2 to 6 rows" in empty and heads(page) == ["CubeMars AK70-10", "Steadywin GIM4305-10"], heads(page))
    tab(page, "Part page")
    sections = page.locator(f"{V} .dv-record-section h3").all_inner_texts()
    title = page.inner_text(f"{V} .dv-record-head h2")
    page.click(f"{V} [data-step='1']")
    page.wait_for_timeout(150)
    check("record: the part page in its four sections, its photo and a source line under each value; › steps to the next part",
          sections == ["Torque and speed", "Size", "Electrical", "In the catalog"] and title == "Steadywin GIM4305-10"
          and page.inner_text(f"{V} .dv-record-head h2") == "Steadywin GIM6010-8" and page.locator(f"{V} .dv-record-image img").count() == 1
          and "aifitlab.com" in page.inner_text(f"{V} tr[data-p='peak_torque'] .dv-record-meta"), sections)
    page.evaluate("localStorage.clear()")
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            name = f"{'dark' if dark else 'light'}, {width} px"
            page = open_page(ctx, path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            sw = page.evaluate("document.scrollingElement.scrollWidth")
            box = page.locator(f"{V} .dv-cmp-scroll").bounding_box()
            check(f"compare, {name}: four columns drawn, no sideways page scroll, the table scrolls in its box",
                  len(heads(page)) == 4 and sw <= width and box["width"] <= width, f"scrollWidth {sw}")
            page.locator(V).scroll_into_view_if_needed()  # the shot shows the views, not the README above them
            ctx.shot(page, f"robotparts-compare-{'dark' if dark else 'light'}-{width}")
            tab(page, "Part page")
            pick = page.locator(f"{V} .dv-record-pick select").is_visible()
            check(f"record, {name}: rows listed beside the sheet on a desktop, a select on a phone",
                  pick == (width < 700) and page.locator(f"{V} .dv-record-list").is_visible() == (width >= 700), "select" if pick else "list")
            page.locator(V).scroll_into_view_if_needed()  # the shot shows the views, not the README above them
            ctx.shot(page, f"robotparts-compare-record-{'dark' if dark else 'light'}-{width}")
            page.context.close()
