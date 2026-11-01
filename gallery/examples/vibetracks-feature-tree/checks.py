"""Browser checks for this case (run by tests/browser/checks.py): the spec tree as an outline (track -> area ->
feature -> test), state badges, the Failing preset keeping a failure's whole path, Fold all, the rail; light and dark
at 1280 and 390 px."""

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


def list_height(page):
    return page.evaluate("document.querySelector('#example .dv-list').getBoundingClientRect().height")


def line(page, title):
    return page.locator(f"{V} .dv-list-line:has(.dv-list-title:text-is('{title}'))")


def run(ctx, path):
    check = ctx.check
    page = open_page(ctx, path)
    page.evaluate("localStorage.clear()")
    track = line(page, "Vibe Tracks")
    check("spec tree: 133 nodes, the track on top with its own count and a failing state",
          list_height(page) == 133 * 30 and track.get_attribute("aria-level") == "1" and "1203/1216" in track.inner_text() and "fail" in track.inner_text(),
          track.inner_text().replace("\n", " "))
    test = page.locator(f"{V} .dv-list-line[aria-level='4']").first
    check("spec tree: a test sits four levels down and reads as its purpose, with its state", "pass" in test.inner_text() or "fail" in test.inner_text(), test.inner_text()[:60])
    page.click(f"{V} .dv-status [data-fold=closed]")
    page.wait_for_timeout(150)
    folded = list_height(page)
    page.keyboard.press("Tab")
    line(page, "Vibe Tracks").focus()
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(150)
    check("Fold all leaves the track; → opens it onto its four areas", folded == 30 and list_height(page) == 5 * 30, f"{folded:.0f} px, then {list_height(page):.0f} px")

    page.click(f"{V} .dv-tab[data-name='Failing']")
    page.wait_for_timeout(300)
    titles = page.locator(f"{V} .dv-list-title").all_inner_texts()
    check("preset 'Failing': the failing tests with their whole path (states roll up, so every ancestor fails too)",
          titles[:3] == ["Vibe Tracks", "Track page", "Track page with KPIs, gates, rungs, activity, sessions and auditor"] and len(titles) == 5, titles)
    page.click(f"{V} .dv-tab[data-name='Spec tree']")
    page.wait_for_timeout(250)
    page.locator("data-facets label:has(.df-label:text-is('no tests')) input").check()
    page.wait_for_timeout(250)
    status = page.inner_text(f"{V} .dv-status")
    check("the rail filters the tree: 'no tests' leaves the features nothing proves yet (their parents filtered out, so they start at the top)",
          status.startswith("32 of 133") and page.locator(f"{V} .dv-list-line[aria-level='2']").count() == 0, status.split(" · ")[0])
    page.evaluate("localStorage.clear()")
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            name = f"{'dark' if dark else 'light'}, {width} px"
            page = open_page(ctx, path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            sw = page.evaluate("document.scrollingElement.scrollWidth")
            check(f"spec tree, {name}: the outline draws, no sideways page scroll", list_height(page) == 133 * 30 and sw <= width, f"scrollWidth {sw}")
            page.locator(V).scroll_into_view_if_needed()  # the shot shows the views, not the README above them
            ctx.shot(page, f"vibetracks-tree-{'dark' if dark else 'light'}-{width}")
            page.context.close()
