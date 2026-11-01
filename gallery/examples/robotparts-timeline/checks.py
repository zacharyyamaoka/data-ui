"""Browser checks for this case (run by tests/browser/checks.py): the timeline view on robotparts' releases and
lanes. Bars and points on the axis, lanes in groupOrder, nested lanes, colour by a property, a bar opens its record,
the wheel zooms, light / dark at 1280 and 390 px."""

V = "#example"
CASE = "robotparts-timeline"


def _open(ctx, path, view, **kw):
    """ctx.page() waits for the status line; then wait for the view the element says it drew."""
    page = ctx.page(path, **kw)
    page.wait_for_selector(f"{V}[data-view='{view}'] .vis-item", timeout=15000)
    page.wait_for_timeout(300)
    return page


def _frame(page):
    """Scroll the view to the top of the window, below the site's sticky header, for a screenshot."""
    page.evaluate("""() => {
      const el = document.querySelector('#example'), bar = document.querySelector('header.top, .top');
      window.scrollTo(0, el.getBoundingClientRect().top + scrollY - (bar ? bar.offsetHeight : 0) - 8);
    }""")
    page.wait_for_timeout(150)


def run(ctx, path):
    check = ctx.check
    page = _open(ctx, path, "timeline")
    ranges = page.locator(f"{V} .vis-item.vis-range").count()
    points = page.locator(f"{V} .vis-item.vis-point").count()
    check("timeline: 24 merged branches as bars, 6 releases as points", (ranges, points) == (24, 6), f"{ranges} bars, {points} points")
    lanes = [t.split()[0] for t in page.locator(f"{V} .vis-labelset .vis-label").all_inner_texts()]
    check("timeline: groupBy lanes in the view's groupOrder", lanes == ["release", "integration", "contract", "main", "lane"], lanes)
    colours = page.evaluate("[...document.querySelectorAll('#example .vis-item.vis-range')].map(e => e.style.getPropertyValue('--dv-item'))")
    check("timeline: color: release gives each release's lanes their own series colour", len(set(colours)) == 6, sorted(set(colours)))
    item = page.locator(f"{V} .vis-item.vis-point:has-text('2026.10.22.2')")
    item.click()
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    title = page.inner_text(f"{V} .dv-peek h2")
    selected = page.locator(f"{V} .vis-item.dv-tl-item.vis-selected:not(.vis-dot)").count()
    check("timeline: a click opens the record and selects the item", title == "2026.10.22.2" and selected == 1, title)
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    bar = f"{V} .vis-item.vis-range"
    w0 = page.locator(bar).first.bounding_box()["width"]
    centre = page.locator(f"{V} .vis-panel.vis-center").bounding_box()
    page.mouse.move(centre["x"] + centre["width"] * 0.1, centre["y"] + 40)
    for _ in range(4):
        page.mouse.wheel(0, -240)
        page.wait_for_timeout(120)
    page.wait_for_timeout(300)
    w1 = page.locator(bar).first.bounding_box()["width"]
    check("timeline: the wheel zooms the axis", w1 > w0 * 1.3, f"first bar {w0:.0f} px -> {w1:.0f} px")
    page.click(f"{V} .dv-tab[data-name='By release']")
    page.wait_for_timeout(600)
    nested = page.locator(f"{V} .vis-labelset .vis-label.vis-nested-group").count()
    tops = page.locator(f"{V} .vis-labelset .vis-label.vis-nesting-group").count()
    check("timeline: subGroupBy nests kind lanes under each release", tops == 6 and nested >= 12, f"{tops} releases, {nested} nested lanes")
    page.click(f"{V} .dv-tab[data-name='All']")
    page.wait_for_timeout(300)
    check("timeline: the same rows as a table", page.locator(f"{V} tbody tr.dv-row").count() == 30)
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            page = _open(ctx, path, "timeline", width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            scheme = "dark" if dark else "light"
            drawn = page.locator(f"{V} .vis-item.dv-tl-item:not(.vis-dot)").count()
            label = page.eval_on_selector(f"{V} .vis-labelset .vis-label", "el => getComputedStyle(el).color")
            scroll = page.evaluate("document.scrollingElement.scrollWidth")
            fg = page.eval_on_selector(V, "el => getComputedStyle(el).color")
            check(f"timeline, {scheme}, {width} px: drawn in the theme's colours, no sideways page scroll", drawn == 30 and label == fg and scroll <= width, f"{drawn} items, lane label {label}, scrollWidth {scroll}")
            _frame(page)
            ctx.shot(page, f"{CASE}-{scheme}-{width}")
            page.context.close()
