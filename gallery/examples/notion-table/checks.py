"""Browser checks for this case (run by tests/browser/checks.py): the playground opens in Edit, partly filled, light and dark at 1280 and
390 px. Everything it does is measured in tests/browser/notion_table_checks.py, this page included."""

V = "#example"


def run(ctx, path):
    check = ctx.check
    for width, dark, mobile, name in ((1280, False, False, "light-1280"), (1280, True, False, "dark-1280"), (390, False, True, "light-390"), (390, True, True, "dark-390")):
        page = ctx.page(path, width=width, height=900, dark=dark, mobile=mobile)
        page.wait_for_selector(f"{V} tbody tr[data-i]", timeout=15000)
        check(f"notion-table {name}: it opens in Edit, on its eight rows", page.evaluate("document.querySelector('#example').editing") is True and page.evaluate("document.querySelector('#example').data.rows.length") == 8)
        check(f"notion-table {name}: the add row and the column menu are there", page.locator(f"{V} tr.dv-addrow").count() == 1 and page.locator(f"{V} [data-col-menu]").count() > 0)
        over = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(f"notion-table {name}: no sideways page scroll", over <= 0, over)
        ctx.shot(page, f"notion-table-{name}")
        page.close()
