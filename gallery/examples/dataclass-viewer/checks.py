"""Browser checks for this case (run by tests/browser/checks.py): the outline (tree: {parent}) that folds by click and
by key, the record sheet with each Value's evidence, the form (edit: true) bounded by the Value's own low / high, a
save on this editable page (site.json) and a refusal on a read-only host; light and dark at 1280 and 390 px."""

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


def run(ctx, path):
    check = ctx.check
    page = open_page(ctx, path)
    page.evaluate("localStorage.clear()")
    role = page.get_attribute(f"{V} .dv-list", "role")
    levels = page.evaluate("[...document.querySelectorAll('#example [role=treeitem]')].map(e => e.getAttribute('aria-level'))")
    check("outline: DEMO_FACILITY -> belt / move -> fields, an ARIA tree three levels deep, 16 lines",
          role == "tree" and set(levels) == {"1", "2", "3"} and list_height(page) == 16 * 30, f"{role}, levels {sorted(set(levels))}, {list_height(page):.0f} px")
    belt = page.locator(f"{V} .dv-list-line:has(.dv-list-title:text-is('belt'))")
    belt.locator("[data-toggle]").click()
    page.wait_for_timeout(150)
    folded = list_height(page)
    page.locator(f"{V} .dv-list-line:has(.dv-list-title:text-is('belt'))").focus()
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(150)
    check("outline: the chevron folds belt's 7 fields; → unfolds them", folded == 9 * 30 and list_height(page) == 16 * 30, f"{folded:.0f} px folded, {list_height(page):.0f} px open")
    page.locator(f"{V} .dv-list-line:has(.dv-list-title:text-is('width_m'))").click()
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    check("outline: a field opens the side peek", page.inner_text(f"{V} .dv-peek h2") == "width_m", page.inner_text(f"{V} .dv-peek h2"))
    page.keyboard.press("Escape")
    line = page.inner_text(f"{V} .dv-list-line:has(.dv-list-title:text-is('width_m'))")
    check("outline: a value reads with its range, unit and basis mark (Value(0.9, \"m\", low=0.5, high=1.6, basis=CHOSEN))",
          "0.9" in line and "0.5–1.6" in line and " m" in line and "C" in line, line.replace("\n", " "))

    tab(page, "Field")
    meta = page.inner_text(f"{V} tr[data-p='value'] .dv-record-meta")
    check("record: the sheet says where the value comes from (basis, source, notes)", "chosen" in meta and "SYNTHETIC" in meta and "A chosen design input" in meta, meta[:80])

    tab(page, "Edit")
    box = page.locator(f"{V} input[name='value']")
    bounds = (box.get_attribute("min"), box.get_attribute("max"))
    page.evaluate("window.__proposed = 0; document.querySelector('#example').addEventListener('data-views-propose', () => window.__proposed++)")
    box.fill("2.5")
    page.click(f"{V} .dv-form [type=submit]")
    page.wait_for_timeout(150)
    check("form: the value's input is bounded by its own low / high; 2.5 m is refused by the browser and nothing is proposed",
          bounds == ("0.5", "1.6") and page.evaluate("window.__proposed") == 0 and page.evaluate("!document.querySelector('#example input[name=value]').checkValidity()"), bounds)
    check("form: structural fields (path, file) are shown, never inputs", page.locator(f"{V} .dv-form [name='path'], {V} .dv-form [name='file']").count() == 0
          and "read-only" in page.inner_text(f"{V} tr[data-p='path']"))
    box.fill("1.4")
    page.click(f"{V} .dv-form [type=submit]")
    page.wait_for_function("document.querySelector('#example .dv-form-msg').textContent.startsWith('Saved')")
    cell = page.evaluate("document.querySelector('#example').row('DEMO_FACILITY.belt.width_m').value")
    check("form: this page is editable (site.json); the save lands and the Value keeps its unit, range, basis and source",
          page.get_attribute(V, "editable") is not None and page.evaluate("window.__proposed") == 1
          and cell["value"] == 1.4 and cell["unit"] == "m" and cell["low"] == 0.5 and cell["basis"] == "chosen" and "SYNTHETIC" in cell["source"],
          {k: cell[k] for k in ("value", "unit", "low", "high", "basis")})
    page.evaluate("document.querySelector('#example').removeAttribute('editable')")
    box = page.locator(f"{V} input[name='value']")
    box.fill("1.5")
    page.click(f"{V} .dv-form [type=submit]")
    page.wait_for_selector(f"{V} .dv-form-msg.dv-refused")
    msg = page.inner_text(f"{V} .dv-form-msg")
    check("form: on a read-only host the save is refused, says why, keeps what was typed and draws nothing",
          "read-only" in msg and box.input_value() == "1.5"
          and page.evaluate("document.querySelector('#example').row('DEMO_FACILITY.belt.width_m').value.value") == 1.4, msg)
    tab(page, "Outline")
    check("the edit shows in every view (the outline reads 1.4)", "1.4" in page.inner_text(f"{V} .dv-list-line:has(.dv-list-title:text-is('width_m'))"))

    # ---- the core's side peek reads the view's record.sections and edit (CONTRACT amendment 2026-10-26, core pass)
    tab(page, "Rows")
    page.click(f"{V} tbody tr.dv-row:has(td:text-is('max_speed_m_s'))")
    page.wait_for_selector(f"{V} .dv-peek:not([hidden]) .dv-peek-form")
    sections = page.locator(f"{V} .dv-peek .dv-peek-section").all_inner_texts()
    fields = page.locator(f"{V} .dv-peek .dv-peek-field th").all_inner_texts()
    check("peek: a table row's peek is laid out in the view's record.sections, as the record view is",
          sections == ["Value", "Where it lives"] and fields == ["Value", "Measured by", "Path", "File"], f"{sections} {fields}")
    locked = page.locator(f"{V} .dv-peek [name='path'], {V} .dv-peek [name='file']").count()
    check("peek: with edit: true it is the record view's form; structural fields stay read-only", page.locator(f"{V} .dv-peek input[name='value']").count() == 1 and locked == 0, f"{locked} structural inputs")
    page.fill(f"{V} .dv-peek input[name='value']", "0.75")
    page.click(f"{V} .dv-peek button[type=submit]")
    page.wait_for_selector(f"{V} .dv-peek .dv-form-msg.dv-refused")
    check("peek: the page is read-only again (above), so the peek's save is refused, says why and keeps what was typed",
          "read-only" in page.inner_text(f"{V} .dv-peek .dv-form-msg") and page.input_value(f"{V} .dv-peek input[name='value']") == "0.75"
          and page.evaluate("document.querySelector('#example').row('DEMO_FACILITY.belt.max_speed_m_s').value.value") == 0.4)
    page.evaluate("document.querySelector('#example').setAttribute('editable', '')")
    page.click(f"{V} .dv-peek button[type=submit]")
    page.wait_for_function("() => /Saved/.test(document.querySelector('#example .dv-peek .dv-form-msg').textContent)", timeout=5000)
    cell = page.inner_text(f"{V} tbody tr.dv-row:has(td:text-is('max_speed_m_s')) td[data-col='value']")
    kept = page.evaluate("document.querySelector('#example').row('DEMO_FACILITY.belt.max_speed_m_s').value")
    check("peek: a save proposes the changed field, lands on this editable page, and the table and the peek redraw with it",
          "0.75" in cell and kept["value"] == 0.75 and kept["unit"] == "m/s" and kept["basis"] == "assumed"
          and page.input_value(f"{V} .dv-peek input[name='value']") == "0.75", f"cell {cell!r}, {kept['value']} {kept['unit']}")
    page.keyboard.press("Escape")

    # ---- the table view honours tree: (TanStack sub-rows from the core)
    tab(page, "Outline table")
    def table_rows():
        return page.evaluate("[...document.querySelectorAll('#example tbody tr.dv-row')].map(r => [r.getAttribute('aria-level'), r.querySelector('td').innerText.trim()])")
    rows = table_rows()
    levels = sorted({lvl for lvl, _ in rows})
    check("tree on a table: DEMO_FACILITY -> belt / move -> fields, three levels, every row drawn", len(rows) == 16 and levels == ["1", "2", "3"], f"{len(rows)} rows, levels {levels}")
    page.locator(f"{V} tbody tr.dv-row[aria-level='2'][aria-expanded] .dv-tree-toggle").first.click()
    page.wait_for_timeout(200)
    folded = table_rows()
    check("tree on a table: a parent's chevron folds its rows; Unfold all brings them back", len(folded) < len(rows), f"{len(folded)} rows folded")
    page.click(f"{V} .dv-status [data-fold=open]")
    page.wait_for_timeout(200)
    check("tree on a table: Unfold all", len(table_rows()) == len(rows), f"{len(table_rows())} rows")
    page.evaluate("localStorage.clear()")
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            name = f"{'dark' if dark else 'light'}, {width} px"
            page = open_page(ctx, path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            sw = page.evaluate("document.scrollingElement.scrollWidth")
            check(f"dataclass outline, {name}: the outline draws, no sideways page scroll", list_height(page) == 16 * 30 and sw <= width, f"scrollWidth {sw}")
            page.locator(V).scroll_into_view_if_needed()  # the shot shows the views, not the README above them
            ctx.shot(page, f"dataclass-viewer-{'dark' if dark else 'light'}-{width}")
            tab(page, "Edit")
            sw = page.evaluate("document.scrollingElement.scrollWidth")
            check(f"dataclass form, {name}: the form draws, no sideways page scroll", page.locator(f"{V} .dv-form input[name='value']").is_visible() and sw <= width, f"scrollWidth {sw}")
            page.locator(V).scroll_into_view_if_needed()  # the shot shows the views, not the README above them
            ctx.shot(page, f"dataclass-viewer-form-{'dark' if dark else 'light'}-{width}")
            page.context.close()
