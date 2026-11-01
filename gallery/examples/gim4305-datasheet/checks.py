"""Browser checks for this case (run by tests/browser/checks.py): the table lane's datasheet checks, ported from
robotparts lane/tables @ ab5ba92 capture.py onto the gallery page."""

V = "#example"


def status(page):
    return page.inner_text(f"{V} .dv-status")


def tab(page, name):
    page.click(f"{V} .dv-tab[data-name='{name}']")
    page.wait_for_timeout(200)


def menu(page, name):
    page.click(f"{V} [data-menu='{name}']")
    page.wait_for_timeout(150)


def row_cell(page, field, col):
    return page.locator(f"{V} tbody tr.dv-row:has(td:first-child:text-is('{field}')) td[data-col='{col}']")


def run(ctx, path):
    check = ctx.check
    page = ctx.page(path)
    page.evaluate("localStorage.clear()")
    height = page.locator(f"{V} tbody tr.dv-row").first.bounding_box()["height"]
    check("datasheet: one single-line row per field, grouped by section", "50 of 50 rows · 9 groups" in status(page) and height <= 31,
          f"{status(page).split(' · Unfold')[0]}; row height {height:.0f} px")
    page.locator(f"{V} .dv-scroll").evaluate("el => el.scrollTo(0, 620)")
    page.wait_for_timeout(200)
    th = page.locator(f"{V} thead th").first.bounding_box()
    box = page.locator(f"{V} .dv-scroll").bounding_box()
    check("datasheet: header stays on top while the rows scroll (sticky)", abs(th["y"] - box["y"]) < 1.5, f"header top {th['y']:.0f} px, scroll box top {box['y']:.0f} px")
    page.locator(f"{V} .dv-scroll").evaluate("el => el.scrollTo(0, 900)")
    page.wait_for_timeout(150)
    row_cell(page, "Coulomb friction", "measured").click()
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    n_behind = page.locator(f"{V} .dv-peek .dv-entries li").count()
    n_hot = page.locator(f"{V} .dv-peek .dv-entries li.dv-active").count()
    values = page.locator(f"{V} .dv-peek .dv-entries .dv-entry-line").all_inner_texts()
    check("datasheet: a measured value opens every value behind it, the measured ones marked", n_behind >= 3 and n_hot >= 3, f"{n_behind} values, {n_hot} marked")
    check("datasheet: CAN 14's coulomb friction reads the corrected 0.0551 N·m, saying what it supersedes",
          any("0.0551" in v and "CAN 14" in v for v in values) and not any("0.0448" in v for v in values) and "Supersedes the 0.0448" in page.inner_text(f"{V} .dv-peek"),
          [v.split(chr(10))[0][:40] for v in values])
    page.keyboard.press("Escape")
    check("datasheet: Esc closes the peek", page.locator(f"{V} .dv-peek").is_hidden())
    page.locator(f"{V} .dv-scroll").evaluate("el => el.scrollTo(0, 0)")

    tab(page, "Measured vs datasheet")
    check("preset 'Measured vs datasheet' filters to measured fields", "of 50 rows" in status(page) and not status(page).startswith("50 of"), status(page).split("·")[0].strip())
    dists = page.locator(f"{V} td[data-col=measured] svg.dv-dist").count()
    check("display: dist draws each measured value's spread in its cell", dists >= 1, f"{dists} cells")
    tab(page, "Datasheet only")
    inline = page.locator(f"{V} td[data-col='nominal'] .dv-u").count()
    check("units next to the values (stored as units: inline)", inline > 5, f"{inline} cells carry their unit")

    tab(page, "Datasheet")
    menu(page, "group")
    page.select_option(f"{V} .dv-pop [data-k=g0]", "status")
    page.select_option(f"{V} .dv-pop [data-k=g1]", "section")
    page.wait_for_timeout(150)
    page.keyboard.press("Escape")
    nested = page.locator(f"{V} tr.dv-group.dv-depth1").count()
    check("nested group-by: Status › Section from the Group menu", nested > 3, f"{nested} sub-group rows")
    url = page.evaluate("location.hash")
    check("the changed view is in the URL", "view=datasheet" in url and "&v=" in url, url[:60] + "…")
    page.goto(f"{ctx.base}/{path}{url}")
    page.wait_for_selector(f"{V} tbody tr[data-i]")
    page.wait_for_timeout(200)
    check("opening that URL restores the view", page.locator(f"{V} tr.dv-group.dv-depth1").count() == nested, page.inner_text(f"{V} [data-menu=group]"))
    page.click(f"{V} .dv-status [data-fold=closed]")
    page.wait_for_timeout(100)
    folded = page.locator(f"{V} tbody tr.dv-row").count()
    check("Fold all leaves only group rows", folded == 0, f"{page.locator(f'{V} tr.dv-group').count()} group rows, {folded} field rows")
    menu(page, "properties")
    page.select_option(f"{V} .dv-pop .dv-prop[data-id=measured] [data-k=display]", "dist")
    page.keyboard.press("Escape")
    page.click(f"{V} .dv-status [data-fold=open]")
    page.locator(f"{V} thead th[data-col='measured']").drag_to(page.locator(f"{V} thead th[data-col='nominal']"))
    page.wait_for_timeout(150)
    heads = page.locator(f"{V} thead th").all_inner_texts()
    check("drag a header onto another to reorder", heads.index("Measured (median)") < heads.index("Nominal (datasheet)"), " | ".join(heads[:4]))
    menu(page, "save")
    page.fill(f"{V} .dv-pop [data-k=name]", "Status first")
    page.click(f"{V} .dv-pop [data-new]")
    page.wait_for_timeout(150)
    saved = page.evaluate("JSON.parse(localStorage.getItem('data-views/gim4305-10-datasheet')).views.map(v => v.name)")
    check("save as my preset (localStorage, a tab of its own)", saved == ["Status first"] and page.locator(f"{V} .dv-tab[data-kind=user]").count() == 1, saved)
    menu(page, "more")
    yaml_text = page.inner_text(f"{V} .dv-yaml")
    check("the view is a .base entry (⋯ shows it)", "groupBy:" in yaml_text and "subGroupBy:" in yaml_text, yaml_text.splitlines()[1].strip())
    page.keyboard.press("Escape")
    page.evaluate("localStorage.clear()")
    page.context.close()

    phone = ctx.page(path, width=390, height=844, mobile=True)
    sw = phone.evaluate("document.scrollingElement.scrollWidth")
    check("phone (390 px): no sideways page scroll; the table scrolls inside its box", sw <= 390, f"page scrollWidth {sw}")
    phone.locator(f"{V} tbody tr.dv-row").nth(1).tap()
    phone.wait_for_timeout(200)
    check("phone: a tap opens the peek, full width", phone.locator(f"{V} .dv-peek").is_visible() and phone.locator(f"{V} .dv-peek").bounding_box()["width"] >= 300)
    ctx.shot(phone, "datasheet-phone-peek")
    phone.context.close()
