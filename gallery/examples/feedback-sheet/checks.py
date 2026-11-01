"""Browser checks for this case (run by tests/browser/checks.py): the sheet draws its media cells, light and dark at 1280 and
390 px. The editing, add row and persistence measures are tests/browser/editable_cells_checks.py."""

V = "#example"


def run(ctx, path):
    check = ctx.check
    for width, dark, mobile, name in ((1280, False, False, "light-1280"), (1280, True, False, "dark-1280"), (390, False, True, "light-390"), (390, True, True, "dark-390")):
        page = ctx.page(path, width=width, height=900, dark=dark, mobile=mobile)
        page.wait_for_selector(f"{V} td.dv-d-media", timeout=15000)
        n = page.locator(f"{V} .dv-mc-thumb").count()
        check(f"feedback-sheet {name}: words and thumbnails in the cells, the add row above them", n >= 1 and page.locator(f"{V} tr.dv-addrow [data-add-col] .dv-ed-box").count() == 4, n)
        over = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(f"feedback-sheet {name}: no sideways page scroll", over <= 0, over)
        ctx.shot(page, f"feedback-sheet-{name}")
        page.close()
