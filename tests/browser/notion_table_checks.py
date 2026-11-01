"""The notion table (docs/CONTRACT.md §40, docs/peps/0016-notion-table.md), measured in headless Chromium on the built kit.

    ~/psu-atlas/.venv/bin/python tests/browser/notion_table_checks.py [OUT_DIR]     # after npm run build

Each check drives a real <data-views> over tests/browser/fixtures/notion-table/ with the real mouse, the real keyboard and the real
clipboard (a paste is Ctrl+V on what navigator.clipboard holds). What a check expects is worked out here from the fixture's JSON, never
read back from the kit. Serves the repo root on a free 127.0.0.1 port, stops that server when done, writes
OUT_DIR/notion-table-checks.json (default reports/media/notion-table) and exits 1 if any check fails.

THE RULER IS FROZEN. Each section went in, failing, in its own commit before the code it measures. A section is never changed after
that commit; a later feature's section is inserted above main().
"""

from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "browser" / "fixtures" / "notion-table"
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "notion-table"
OUT.mkdir(parents=True, exist_ok=True)
PAGE = "/tests/browser/fixtures/notion-table/bare.html"
V = "#sheet"
DATA = json.loads((FIX / "rows.json").read_text(encoding="utf-8"))
BASE_TEXT = (FIX / "views.base").read_text(encoding="utf-8")
ROWS = DATA["rows"]
IDS = [r["id"] for r in ROWS]
BY_ID = {r["id"]: r for r in ROWS}
ORDER = ["task", "owner", "ticket", "points", "due", "status", "shipped", "link", "notes", "score"]
checks: list[dict] = []
SECTIONS: list = []

# opts: toggle (edit-toggle), editable, toolbar, selectable, url (leave no-url off), view, text (other .base text), data (other
# rows), setup (a script with `v` the element, run before it draws: a page's hooks), second (a second element #sheet2)
MOUNT = """async ([text, data, opts]) => {
  await new Promise((go) => { const t = setInterval(() => { if (window.kitReady) { clearInterval(t); go(); } }, 5); });
  const make = (id) => {
    const v = document.createElement('data-views');
    v.id = id;
    if (!opts.url) v.setAttribute('no-url', '');
    if (opts.toggle) v.setAttribute('edit-toggle', '');
    if (opts.editable) v.setAttribute('editable', '');
    if (opts.selectable) v.setAttribute('selectable', '');
    if (opts.addRowAttr) v.setAttribute('add-row', '');
    if (opts.toolbar) v.setAttribute('toolbar', opts.toolbar);
    if (opts.view) v.setAttribute('view', opts.view);
    return v;
  };
  const start = (v) => {
    if (opts.setup) new Function('v', opts.setup)(v);
    document.body.append(v);
    v.baseText = text;
    v.base = kit.parseBase(text);
    v.data = JSON.parse(JSON.stringify(data));
  };
  window.__log = [];
  start(make('sheet'));
  if (opts.second) start(make('sheet2'));
}"""

SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"
TABLE_HTML = "(s) => { const v = document.querySelector(s); const t = v.querySelector('.dv-view table'); return t.querySelector('thead').outerHTML + t.querySelector('tbody').outerHTML; }"


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def section(fn):
    SECTIONS.append(fn)
    return fn


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def new_page(browser, base, width=1280, height=820, dark=False, mobile=False, suffix=""):
    context = browser.new_context(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light", has_touch=mobile, is_mobile=mobile)
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
    context.set_default_timeout(4000)
    page = context.new_page()
    page.goto(base + PAGE + suffix)
    return context, page


def mount(page, **opts):
    page.evaluate(MOUNT, [opts.get("text", BASE_TEXT), opts.get("data", DATA), opts])
    page.wait_for_selector(f"{V} tbody tr[data-i]", timeout=15000)
    page.evaluate(SETTLE)


def sheet(browser, base, width=1280, height=820, dark=False, mobile=False, suffix="", **opts):
    context, page = new_page(browser, base, width, height, dark, mobile, suffix)
    mount(page, **opts)
    return context, page


def settle(page):
    page.evaluate(SETTLE)


def cell(page, row, col):
    return page.locator(f'{V} tbody tr[data-id="{row}"] td[data-col="{col}"]')


def stored(page, row, col):
    """What the row holds, as it holds it."""
    return page.evaluate("([r, c]) => { const x = document.querySelector('#sheet').row(r); return x ? x[c] ?? null : '(no row)'; }", [row, col])


def stored_rows(page):
    """Every row as the element holds it, in the data's order, as plain JSON."""
    return page.evaluate("() => JSON.parse(JSON.stringify(document.querySelector('#sheet').data.rows))")


def editor_open(page):
    return page.locator(f"{V} .dv-celledit").count() == 1


def switch(page):
    return page.locator(f"{V} [data-edit-switch]:visible")


def to_edit(page):
    switch(page).click()
    settle(page)


def over(page):
    return page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")


def contrast(page, sel):
    """The contrast of an element's text on the first opaque fill behind it."""
    return page.evaluate("""(sel) => {
      const e = document.querySelector(sel);
      const rgb = (s) => { const c = document.createElement('canvas').getContext('2d'); c.fillStyle = s; c.fillRect(0, 0, 1, 1); return [...c.getImageData(0, 0, 1, 1).data]; };
      const fg = rgb(getComputedStyle(e).color);
      let bg = [255, 255, 255, 255];
      for (let n = e; n; n = n.parentElement) { const b = rgb(getComputedStyle(n).backgroundColor); if (b[3] > 250) { bg = b; break; } }
      const lum = (c) => { const v = c.slice(0, 3).map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
      const a = lum(fg), b = lum(bg);
      return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    }""", sel)


# ------------------------------------------------------------------ 1. the Edit / View toggle
@section
def toggle(browser, base):
    # ---- View is where it opens, and it is a read-only table to the byte
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    sw = switch(page)
    check("toggle: an edit-toggle page has one switch, in the bar", sw.count() == 1 and sw.get_attribute("role") == "switch", sw.count())
    check("toggle: it opens in View", sw.get_attribute("aria-checked") == "false" and page.evaluate("document.querySelector('#sheet').editing") is False)
    view_html = page.evaluate(TABLE_HTML, V)
    check("toggle: View has no add row, no editable cells, no Open, no column menu", page.locator(f"{V} tr.dv-addrow, {V} td.dv-ed, {V} .dv-row-open, {V} [data-col-menu]").count() == 0)
    context.close()
    context, page = sheet(browser, base, toolbar="bar")
    plain_html = page.evaluate(TABLE_HTML, V)
    check("toggle: a page with neither attribute has no switch", page.locator(f"{V} [data-edit-switch]").count() == 0)
    check("toggle: View's table is the HTML of a page with neither attribute, to the byte", view_html == plain_html, [len(view_html), len(plain_html)])
    context.close()

    # ---- into Edit with the real mouse; what Edit does; the event; the URL; memory
    context, page = sheet(browser, base, toggle=True, toolbar="bar", url=True, setup="v.addEventListener('data-views-edit-mode', (e) => window.__log.push(e.detail));")
    page.locator(f'{V} tbody tr[data-i="0"] td[data-col="owner"]').click()
    settle(page)
    check("toggle: in View a click on a cell opens the record, no editor", not editor_open(page) and page.locator(f"{V} .dv-peek:not([hidden])").count() == 1)
    page.keyboard.press("Escape")
    settle(page)
    check("toggle: a fresh page's URL does not mention edit", "edit=" not in page.url, page.url.split("#")[-1])
    to_edit(page)
    check("toggle: the switch says Edit is on", switch(page).get_attribute("aria-checked") == "true" and page.evaluate("document.querySelector('#sheet').editing") is True)
    check("toggle: Edit shows the add row and marks the cells", page.locator(f"{V} tr.dv-addrow").count() == 1 and page.locator(f"{V} td.dv-ed").count() > 0)
    check("toggle: it fires data-views-edit-mode {editing: true}, once", page.evaluate("window.__log") == [{"editing": True}], page.evaluate("window.__log"))
    check("toggle: the URL says edit=1", "edit=1" in page.url.split("#")[-1], page.url.split("#")[-1])
    cell(page, "t1", "owner").click()
    settle(page)
    check("toggle: in Edit a click on a cell opens its editor", editor_open(page))
    page.keyboard.press("End")
    page.keyboard.type("na")
    page.keyboard.press("Enter")
    settle(page)
    check("toggle: Enter commits in memory, as an editable page does", stored(page, "t1", "owner") == BY_ID["t1"]["owner"] + "na", stored(page, "t1", "owner"))
    cell(page, "t2", "owner").click()
    page.keyboard.press("End")
    page.keyboard.type("!")
    switch(page).click()
    settle(page)
    check("toggle: turning Edit off commits the open editor", stored(page, "t2", "owner") == BY_ID["t2"]["owner"] + "!" and not editor_open(page), stored(page, "t2", "owner"))
    check("toggle: back in View the URL drops edit=", "edit=" not in page.url.split("#")[-1], page.url.split("#")[-1])
    check("toggle: and the event says so", page.evaluate("window.__log[window.__log.length - 1]") == {"editing": False})
    refused = page.evaluate("() => document.querySelector('#sheet').propose({ id: 't1', set: { owner: 'x' } })")
    check("toggle: in View propose refuses and says it is View", refused["ok"] is False and "View" in refused["reason"], refused)
    added = page.evaluate("() => document.querySelector('#sheet').addRow({ task: 'x' })")
    check("toggle: in View addRow refuses", added["ok"] is False, added)
    to_edit(page)
    page.reload()
    mount(page, toggle=True, toolbar="bar", url=True)
    check("toggle: the choice is remembered through a reload", page.evaluate("document.querySelector('#sheet').editing") is True and switch(page).get_attribute("aria-checked") == "true")
    to_edit(page)
    page.reload()
    mount(page, toggle=True, toolbar="bar", url=True)
    check("toggle: View is remembered too", page.evaluate("document.querySelector('#sheet').editing") is False)
    context.close()

    # ---- the link wins, a fresh viewer included; #edit=0 beats memory; a hash edited in place; a no-url page keeps storage only
    context, page = sheet(browser, base, toggle=True, toolbar="bar", url=True, suffix="#edit=1")
    check("toggle: a fresh viewer on a link with edit=1 opens in Edit", page.evaluate("document.querySelector('#sheet').editing") is True)
    page.goto(base + PAGE + "#edit=0")
    page.reload()
    mount(page, toggle=True, toolbar="bar", url=True)
    check("toggle: edit=0 in the link opens in View", page.evaluate("document.querySelector('#sheet').editing") is False)
    page.evaluate("location.hash = 'edit=1'")
    settle(page)
    check("toggle: an edited fragment moves the switch", page.evaluate("document.querySelector('#sheet').editing") is True)
    context.close()
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    check("toggle: a no-url page leaves the URL alone", "edit=" not in page.url, page.url)
    page.reload()
    mount(page, toggle=True, toolbar="bar")
    check("toggle: a no-url page still remembers per viewer", page.evaluate("document.querySelector('#sheet').editing") is True)
    context.close()

    # ---- the full toolbar, by keyboard; the setter
    context, page = sheet(browser, base, toggle=True, toolbar="full")
    sw = switch(page)
    check("toggle: the full toolbar has the switch too", sw.count() == 1 and sw.get_attribute("role") == "switch")
    sw.focus()
    page.keyboard.press("Space")
    settle(page)
    check("toggle: Space on the focused switch turns it on (full toolbar)", switch(page).get_attribute("aria-checked") == "true" and page.locator(f"{V} tr.dv-addrow").count() == 1)
    page.evaluate("document.querySelector('#sheet').editing = false")
    settle(page)
    check("toggle: el.editing = false is the switch", switch(page).get_attribute("aria-checked") == "false" and page.locator(f"{V} tr.dv-addrow").count() == 0)
    context.close()
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    switch(page).focus()
    page.keyboard.press("Enter")
    settle(page)
    check("toggle: Enter on the focused switch turns it on (bar)", switch(page).get_attribute("aria-checked") == "true")
    context.close()

    # ---- `editable` alone is §37, to the byte; `edit-toggle` with `editable` still opens in View
    context, page = sheet(browser, base, editable=True, toolbar="bar", selectable=True)
    check("toggle: editable with no edit-toggle has no switch", page.locator(f"{V} [data-edit-switch]").count() == 0)
    check("toggle: editable with no edit-toggle edits as §37 says", page.locator(f"{V} tr.dv-addrow").count() == 1 and page.locator(f"{V} td.dv-ed").count() > 0 and page.evaluate("document.querySelector('#sheet').editing") is True)
    check("toggle: editable alone draws no column menu", page.locator(f"{V} [data-col-menu]").count() == 0)
    context.close()
    context, page = sheet(browser, base, toggle=True, editable=True, toolbar="bar")
    check("toggle: editable with edit-toggle still opens in View", page.evaluate("document.querySelector('#sheet').editing") is False and page.locator(f"{V} tr.dv-addrow").count() == 0)
    context.close()

    # ---- a form stands down in View; the attribute can come and go
    edit_base = BASE_TEXT.replace("    addRow: true\n  - type: table\n    name: Todo", "    addRow: true\n    edit: true\n  - type: table\n    name: Todo", 1)
    context, page = sheet(browser, base, toggle=True, toolbar="bar", text=edit_base)
    page.locator(f'{V} tbody tr[data-i="0"] td[data-col="owner"]').click()
    settle(page)
    check("toggle: a view with edit: true shows no form in View", page.locator(f"{V} .dv-peek-form").count() == 0 and page.locator(f"{V} .dv-peek:not([hidden])").count() == 1)
    context.close()
    context, page = sheet(browser, base, toolbar="bar")
    page.evaluate("document.querySelector('#sheet').setAttribute('edit-toggle', '')")
    settle(page)
    check("toggle: setting the attribute live draws the switch", switch(page).count() == 1)
    page.evaluate("document.querySelector('#sheet').removeAttribute('edit-toggle')")
    settle(page)
    check("toggle: removing it takes the switch away", page.locator(f"{V} [data-edit-switch]").count() == 0)
    context.close()

    # ---- a dashboard panel
    context, page = new_page(browser, base)
    page.wait_for_function("window.kitReady === true")
    page.evaluate("""() => { const d = document.createElement('data-dashboard'); d.id = 'dash'; d.setAttribute('no-url', ''); d.setAttribute('src', '/tests/browser/fixtures/notion-table/dashboard.base'); document.body.append(d); }""")
    page.wait_for_selector("#dash data-views tbody tr[data-i]", timeout=15000)
    settle(page)
    check("toggle: a dashboard panel with editToggle: true has the switch; the other panel has none", page.locator("#dash [data-edit-switch]:visible").count() == 1, page.locator("#dash [data-edit-switch]").count())
    page.locator("#dash [data-edit-switch]:visible").click()
    settle(page)
    check("toggle: the panel's switch turns that panel to Edit", page.locator("#dash td.dv-ed").count() > 0)
    context.close()

    # ---- narrow: the "…" menu, light and dark, no sideways scroll
    for dark, name in ((False, "light"), (True, "dark")):
        context, page = sheet(browser, base, width=390, height=800, dark=dark, mobile=True, toggle=True, toolbar="bar", selectable=True)
        check(f"toggle {name}-390: no sideways page scroll in View", over(page) <= 0, over(page))
        more = page.locator(f"{V} [data-bar=overflow]:visible")
        check(f"toggle {name}-390: the switch has moved into the … menu", more.count() == 1 and page.locator(f"{V} .dv-bar-tools [data-edit-switch]:visible").count() == 0)
        more.click()
        item = page.locator(f'{V} .dv-pop [data-run="edit"]')
        check(f"toggle {name}-390: the menu's item is a checkbox item, off", item.count() == 1 and item.get_attribute("role") == "menuitemcheckbox" and item.get_attribute("aria-checked") == "false")
        item.click()
        settle(page)
        check(f"toggle {name}-390: it turns Edit on", page.evaluate("document.querySelector('#sheet').editing") is True and page.locator(f"{V} tr.dv-addrow").count() == 1)
        check(f"toggle {name}-390: no sideways page scroll in Edit", over(page) <= 0, over(page))
        more = page.locator(f"{V} [data-bar=overflow]:visible")
        more.click()
        check(f"toggle {name}-390: the item now reads on", page.locator(f'{V} .dv-pop [data-run="edit"]').get_attribute("aria-checked") == "true")
        page.keyboard.press("Escape")
        context.close()
    for dark, name in ((False, "light"), (True, "dark")):
        context, page = sheet(browser, base, dark=dark, toggle=True, toolbar="bar")
        ratio = contrast(page, f"{V} .dv-bar-tools [data-edit-switch] .dv-bar-label")
        check(f"toggle {name}-1280: the switch's word reads against the bar", ratio >= 4.5, round(ratio, 2))
        context.close()


# ------------------------------------------------------------------ 2. deleting rows
def row_ids(page):
    return [r["id"] for r in stored_rows(page)]


def row_menu(page, row, col="owner"):
    cell(page, row, col).click(button="right")
    return page.locator(".dv-itemmenu [data-row-delete]")


def toast(page):
    return page.locator(f"{V} .dv-toast:not([hidden])")


@section
def delete(browser, base):
    dialogs = []

    # ---- in memory, from a row's right-click: no dialog, an Undo toast, the row back where it was
    context, page = sheet(browser, base, toggle=True, toolbar="bar", selectable=True, setup="v.addEventListener('data-views-delete', (e) => window.__log.push(e.detail));")
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    to_edit(page)
    item = row_menu(page, "t2")
    check("delete: a row's right-click in Edit offers Delete row", item.count() == 1 and item.inner_text().strip() == "Delete row", item.count())
    item.click()
    settle(page)
    want = [i for i in IDS if i != "t2"]
    check("delete: the row leaves the data; the other rows stay, in order", row_ids(page) == want, row_ids(page))
    check("delete: the row leaves the table", page.locator(f'{V} tbody tr[data-id="t2"]').count() == 0)
    check("delete: no confirm dialog", dialogs == [], dialogs)
    check("delete: a toast says so and holds Undo", toast(page).count() == 1 and "Deleted 1 row" in toast(page).inner_text() and toast(page).locator("[data-toast-undo]").inner_text().strip() == "Undo", toast(page).inner_text() if toast(page).count() else None)
    log = page.evaluate("window.__log")
    check("delete: it fires data-views-delete {ids, result}", len(log) == 1 and log[0]["ids"] == ["t2"] and log[0]["result"]["ok"] is True, log)
    toast(page).locator("[data-toast-undo]").click()
    settle(page)
    check("delete: the toast's Undo puts the row back where it was, every cell as the fixture has it", stored_rows(page) == ROWS, row_ids(page))
    check("delete: the row is back in the table, and the toast has gone or stopped offering Undo", page.locator(f'{V} tbody tr[data-id="t2"]').count() == 1 and page.locator(f"{V} .dv-toast:not([hidden]) [data-toast-undo]").count() == 0)

    # ---- the bulk bar, and a right-click on a selected row
    page.locator(f'{V} tbody tr[data-id="t3"] .dv-selbox').click()
    page.locator(f'{V} tbody tr[data-id="t7"] .dv-selbox').click()
    settle(page)
    item = row_menu(page, "t7")
    check("delete: a right-click on a selected row offers all of them", item.inner_text().strip() == "Delete 2 rows", item.inner_text())
    page.keyboard.press("Escape")
    settle(page)
    if page.locator(f'{V} tbody tr[data-id="t3"].dv-sel').count() == 0:  # Esc may have left the menu or the selection: the check above is the point
        page.locator(f'{V} tbody tr[data-id="t3"] .dv-selbox').click()
        page.locator(f'{V} tbody tr[data-id="t7"] .dv-selbox').click()
        settle(page)
    act = page.locator(f"{V} .dv-bulk .dv-bulk-act", has_text="Delete")
    check("delete: the bulk bar has Delete in Edit", act.count() == 1, page.locator(f"{V} .dv-bulk .dv-bulk-act").all_inner_texts())
    act.click()
    settle(page)
    want = [i for i in IDS if i not in ("t3", "t7")]
    check("delete: the bulk bar's Delete takes every selected row", row_ids(page) == want, row_ids(page))
    check("delete: the toast counts them, and the selection has gone", "Deleted 2 rows" in toast(page).inner_text() and page.evaluate("document.querySelector('#sheet').selection.length") == 0)
    toast(page).locator("[data-toast-undo]").click()
    settle(page)
    check("delete: Undo restores both, each at its own place", stored_rows(page) == ROWS, row_ids(page))
    context.close()

    # ---- the keyboard: Shift+F10 on a focused row, Enter; the focus lands on a row
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    page.locator(f'{V} tbody tr[data-id="t4"]').focus()
    page.keyboard.press("Shift+F10")
    check("delete: Shift+F10 on a focused row opens the menu on Delete row", page.evaluate("document.activeElement.hasAttribute('data-row-delete')"), page.evaluate("document.activeElement.outerHTML.slice(0, 80)"))
    page.keyboard.press("Enter")
    settle(page)
    check("delete: Enter deletes it", "t4" not in row_ids(page), row_ids(page))
    check("delete: the focus lands on the row that took its place", page.evaluate("document.activeElement.dataset.id") == "t5", page.evaluate("document.activeElement.tagName"))
    context.close()

    # ---- View, `editable` alone, a read-only page
    context, page = sheet(browser, base, toggle=True, toolbar="bar", selectable=True)
    page.evaluate("window.addEventListener('contextmenu', (e) => { window.__menu = e.defaultPrevented; })")
    page.locator(f'{V} tbody tr[data-i="1"] td[data-col="owner"]').click(button="right")
    settle(page)
    check("delete: in View a right-click is the browser's own", page.locator(".dv-itemmenu").count() == 0 and page.evaluate("window.__menu") is False, page.evaluate("window.__menu"))
    page.locator(f'{V} tbody tr[data-i="1"] .dv-selbox').click()
    settle(page)
    check("delete: in View the bulk bar has no Delete", page.locator(f"{V} .dv-bulk .dv-bulk-act", has_text="Delete").count() == 0)
    refused = page.evaluate("() => document.querySelector('#sheet').deleteRows(['t1'])")
    check("delete: in View deleteRows refuses", refused["ok"] is False and "View" in refused["reason"], refused)
    context.close()

    context, page = sheet(browser, base, editable=True, toolbar="bar", selectable=True)
    page.evaluate("window.addEventListener('contextmenu', (e) => { window.__menu = e.defaultPrevented; })")
    cell(page, "t2", "owner").click(button="right")
    settle(page)
    check("delete: editable with no edit-toggle keeps the browser's right-click", page.locator(".dv-itemmenu").count() == 0 and page.evaluate("window.__menu") is False)
    page.locator(f'{V} tbody tr[data-id="t2"] .dv-selbox').click()
    settle(page)
    check("delete: editable with no edit-toggle draws no Delete in the bulk bar", page.locator(f"{V} .dv-bulk .dv-bulk-act", has_text="Delete").count() == 0)
    done = page.evaluate("() => document.querySelector('#sheet').deleteRows(['t2'])")
    check("delete: an editable page with no hook deletes in memory from a script", done["ok"] is True and "t2" not in row_ids(page), done)
    context.close()

    context, page = sheet(browser, base, toolbar="bar")
    refused = page.evaluate("() => document.querySelector('#sheet').deleteRows(['t1'])")
    check("delete: a read-only page refuses", refused["ok"] is False and "read-only" in refused["reason"], refused)
    context.close()

    # ---- the page's hook: it decides; a refusal; a host that hands in new data; undo through acceptAdd with the old cells
    refuse = "v.acceptDelete = async ({ ids }) => { window.__log.push(ids); return { ok: false, reason: 'Ask the owner first.' }; };"
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=refuse)
    to_edit(page)
    row_menu(page, "t1").click()
    settle(page)
    check("delete: acceptDelete hears {ids}", page.evaluate("window.__log") == [["t1"]], page.evaluate("window.__log"))
    check("delete: a refusal keeps the row and says why, with no Undo", "t1" in row_ids(page) and "Ask the owner first." in toast(page).inner_text() and toast(page).locator("[data-toast-undo]").count() == 0, toast(page).inner_text())
    context.close()

    keep = """v.acceptDelete = async ({ ids }) => { window.__log.push(['delete', ids]); return { ok: true }; };
      v.acceptAdd = async (a) => { window.__log.push(['add', a]); return { ok: true, id: a.id }; };"""
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=keep)
    to_edit(page)
    row_menu(page, "t1").click()
    settle(page)
    check("delete: a host's ok drops the row from what the element holds", "t1" not in row_ids(page) and page.locator(f'{V} tbody tr[data-id="t1"]').count() == 0)
    toast(page).locator("[data-toast-undo]").click()
    settle(page)
    log = page.evaluate("window.__log")
    add = log[-1][1] if log and log[-1][0] == "add" else {}
    old = {k: v for k, v in BY_ID["t1"].items() if k != "id"}
    check("delete: Undo goes through acceptAdd with the row's id, restore: true and its old cells", add.get("id") == "t1" and add.get("restore") is True and add.get("set") == old, add)
    check("delete: and the row is back where it was", stored_rows(page) == ROWS, row_ids(page))
    context.close()

    pushes = """v.acceptDelete = async ({ ids }) => { const d = v.data; v.data = { ...d, rows: d.rows.filter((r) => !ids.includes(r.id)) }; return { ok: true }; };
      v.acceptAdd = async (a) => { const d = v.data; const row = { ...a.set, id: 'back-' + a.id }; v.data = { ...d, rows: [...d.rows, row] }; return { ok: true, id: row.id }; };"""
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=pushes)
    to_edit(page)
    row_menu(page, "t1").click()
    settle(page)
    check("delete: a host that hands in new data: the row is gone once", row_ids(page) == IDS[1:], row_ids(page))
    toast(page).locator("[data-toast-undo]").click()
    settle(page)
    check("delete: Undo follows a host that answers another id, and draws no second copy", row_ids(page) == IDS[1:] + ["back-t1"], row_ids(page))
    context.close()

    # ---- a read-only row; a row that is not there
    context, page = sheet(browser, base, toggle=True, toolbar="bar", selectable=True)
    to_edit(page)
    row_menu(page, "t5").click()
    settle(page)
    check("delete: a row with _readOnly refuses, and the toast says so", "t5" in row_ids(page) and "read-only" in toast(page).inner_text(), toast(page).inner_text() if toast(page).count() else None)
    page.locator(f'{V} tbody tr[data-id="t5"] .dv-selbox').click()
    page.locator(f'{V} tbody tr[data-id="t1"] .dv-selbox').click()
    settle(page)
    page.locator(f"{V} .dv-bulk .dv-bulk-act", has_text="Delete").click()
    settle(page)
    check("delete: a selection holding one refuses whole: nothing half-deleted", row_ids(page) == IDS, row_ids(page))
    missing = page.evaluate("() => document.querySelector('#sheet').deleteRows(['nope'])")
    check("delete: an id that is no row refuses", missing["ok"] is False and "nope" in missing["reason"], missing)
    context.close()

    # ---- an open record leaves with its row; phone widths, both themes
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    cell(page, "t3", "ticket").click()
    settle(page)
    check("delete: (a locked cell opens the record)", page.locator(f"{V} .dv-peek:not([hidden])").count() == 1)
    page.evaluate("() => document.querySelector('#sheet').deleteRows(['t3'])")
    settle(page)
    check("delete: the record's peek closes with its row", page.locator(f"{V} .dv-peek:not([hidden])").count() == 0)
    context.close()
    for dark, name in ((False, "light"), (True, "dark")):
        context, page = sheet(browser, base, width=390, height=800, dark=dark, mobile=True, toggle=True, toolbar="bar", selectable=True)
        page.evaluate("document.querySelector('#sheet').editing = true")
        settle(page)
        page.evaluate("() => document.querySelector('#sheet').deleteRows(['t1'])")
        settle(page)
        box = toast(page).bounding_box()
        check(f"delete {name}-390: the toast fits the window", box["x"] >= 0 and box["x"] + box["width"] <= 390 and box["y"] + box["height"] <= 800, box)
        check(f"delete {name}-390: no sideways page scroll with the toast up", over(page) <= 0, over(page))
        for sel, what in ((".dv-toast-text", "its words"), ("[data-toast-undo]", "its Undo")):
            ratio = contrast(page, f"{V} .dv-toast {sel}")
            check(f"delete {name}-390: {what} read against the toast", ratio >= 4.5, round(ratio, 2))
        toast(page).locator("[data-toast-undo]").click()
        settle(page)
        check(f"delete {name}-390: Undo by touch restores it", stored_rows(page) == ROWS)
        context.close()


# ------------------------------------------------------------------ 3. undo and redo
def undo_key(page, mod="Control"):
    page.keyboard.press(f"{mod}+z")
    settle(page)


def redo_key(page, mod="Control"):
    page.keyboard.press(f"{mod}+Shift+z")
    settle(page)


def type_into(page, row, col, text):
    cell(page, row, col).click()
    page.keyboard.press("End")
    page.keyboard.type(text)
    page.keyboard.press("Enter")
    settle(page)


def can(page):
    return page.evaluate("() => { const v = document.querySelector('#sheet'); return [v.canUndo, v.canRedo]; }")


# whether the page's own keydown listeners took Ctrl+Z: read at the window, after the document's. An open editor stops the key on
# its way up, so inside one this stays null: "taken" is True here, and nothing else
WATCH_KEY = "window.__taken = null; window.addEventListener('keydown', (e) => { if (e.key.toLowerCase() === 'z') window.__taken = e.defaultPrevented; });"


@section
def undo(browser, base):
    # ---- a cell: Ctrl and Cmd; the focus stays with its row; the order; a new edit ends redo
    context, page = sheet(browser, base, toggle=True, toolbar="bar", selectable=True)
    to_edit(page)
    was = BY_ID["t1"]["owner"]
    type_into(page, "t1", "owner", "X")
    check("undo: (the edit landed)", stored(page, "t1", "owner") == was + "X" and can(page) == [True, False], can(page))
    undo_key(page)
    check("undo: Ctrl+Z puts a cell back", stored(page, "t1", "owner") == was, stored(page, "t1", "owner"))
    check("undo: the table draws it", cell(page, "t1", "owner").inner_text().strip() == was)
    check("undo: the focus stays on its row", page.evaluate("document.activeElement.dataset.id") == "t1", page.evaluate("document.activeElement.tagName"))
    check("undo: then redo is there, and no more undo", can(page) == [False, True], can(page))
    redo_key(page)
    check("undo: Shift+Ctrl+Z puts it forward again", stored(page, "t1", "owner") == was + "X", stored(page, "t1", "owner"))
    undo_key(page, "Meta")
    check("undo: Cmd+Z too", stored(page, "t1", "owner") == was)
    redo_key(page, "Meta")
    check("undo: Shift+Cmd+Z too", stored(page, "t1", "owner") == was + "X")
    type_into(page, "t2", "owner", "Y")
    type_into(page, "t3", "owner", "Z")
    undo_key(page)
    undo_key(page)
    check("undo: steps come back newest first", stored(page, "t3", "owner") == BY_ID["t3"]["owner"] and stored(page, "t2", "owner") == BY_ID["t2"]["owner"] and stored(page, "t1", "owner") == was + "X")
    type_into(page, "t4", "owner", "W")
    check("undo: a new edit ends redo", can(page) == [True, False], can(page))
    context.close()

    # ---- what else undoes: a number, a flip, an enum, a row added, a row deleted
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    cell(page, "t1", "points").click()
    page.keyboard.type("41")
    page.keyboard.press("Enter")
    settle(page)
    check("undo: (a number landed as a number)", stored(page, "t1", "points") == 41)
    undo_key(page)
    check("undo: a number comes back as the number it was", stored(page, "t1", "points") == BY_ID["t1"]["points"], stored(page, "t1", "points"))
    cell(page, "t1", "shipped").click()
    settle(page)
    check("undo: (a checkbox flipped)", stored(page, "t1", "shipped") is True)
    undo_key(page)
    check("undo: a flip comes back", stored(page, "t1", "shipped") is False, stored(page, "t1", "shipped"))
    box = page.locator(f'{V} tr.dv-addrow [name="task"]')
    box.click()
    page.keyboard.type("A new task")
    page.locator(f"{V} tr.dv-addrow [data-add-go]").click()
    page.wait_for_function("document.querySelector('#sheet').data.rows.length === %d" % (len(ROWS) + 1))
    settle(page)
    new_id = page.evaluate("document.querySelector('#sheet').data.rows.find((r) => r.task === 'A new task').id")
    page.locator(f"{V} .dv-status").click()
    undo_key(page)
    check("undo: an added row leaves", page.evaluate("document.querySelector('#sheet').data.rows.length") == len(ROWS) and stored(page, new_id, "task") == "(no row)", new_id)
    redo_key(page)
    check("undo: redo brings it back, the same row", stored(page, new_id, "task") == "A new task" and page.evaluate("document.querySelector('#sheet').data.rows[0].id") == new_id)
    undo_key(page)
    page.evaluate("() => document.querySelector('#sheet').deleteRows(['t2', 't6'])")
    settle(page)
    page.locator(f"{V} .dv-status").click()
    undo_key(page)
    check("undo: Ctrl+Z after a delete brings both back, each where it was", stored_rows(page)[:2] == ROWS[:2] and len(stored_rows(page)) == len(ROWS) and [r["id"] for r in stored_rows(page)] == IDS, [r["id"] for r in stored_rows(page)])
    redo_key(page)
    check("undo: redo deletes them again", [r["id"] for r in stored_rows(page)] == [i for i in IDS if i not in ("t2", "t6")], [r["id"] for r in stored_rows(page)])
    context.close()

    # ---- a page section's edit, through the same stack
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    cell(page, "t1", "ticket").click()
    page.wait_for_selector(f"{V} .dv-peek [data-page-sec='notes'] textarea")
    area = page.locator(f"{V} .dv-peek [data-page-sec='notes'] textarea")
    area.click()
    page.keyboard.press("End")
    page.keyboard.type(" More.")
    page.locator(f"{V} .dv-peek header").click()
    settle(page)
    check("undo: (a record's section committed)", stored(page, "t1", "notes")["value"].endswith(" More."), stored(page, "t1", "notes"))
    page.locator(f"{V} .dv-status").click()
    undo_key(page)
    check("undo: a record's section comes back, as it was stored", stored(page, "t1", "notes") == BY_ID["t1"]["notes"], stored(page, "t1", "notes"))
    context.close()

    # ---- the key is a text editor's own while one is open
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=WATCH_KEY)
    to_edit(page)
    type_into(page, "t1", "owner", "X")
    cell(page, "t2", "owner").click()
    page.keyboard.press("End")
    page.keyboard.type("typing")
    page.keyboard.press("Control+z")
    settle(page)
    check("undo: inside an open editor the key is not taken", page.evaluate("window.__taken") is not True, page.evaluate("window.__taken"))
    check("undo: the editor's own undo ran, and the editor is still open", editor_open(page) and page.evaluate("document.activeElement.value") != BY_ID["t2"]["owner"] + "typing", page.evaluate("document.activeElement.value"))
    check("undo: the sheet's stack did not move", stored(page, "t1", "owner") == BY_ID["t1"]["owner"] + "X" and can(page) == [True, False], can(page))
    page.keyboard.press("Escape")
    settle(page)
    page.locator(f'{V} tr.dv-addrow [name="task"]').click()
    page.keyboard.type("in the add row")
    page.evaluate("window.__taken = null")
    page.keyboard.press("Control+z")
    settle(page)
    check("undo: nor in the add row's box", page.evaluate("window.__taken") is not True and stored(page, "t1", "owner") == BY_ID["t1"]["owner"] + "X")
    page.evaluate("document.activeElement.blur()")
    context.close()
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=WATCH_KEY)
    to_edit(page)
    type_into(page, "t1", "owner", "X")
    page.locator(f"{V} .dv-bar-query input").first.click()
    page.keyboard.type("x")
    page.evaluate("window.__taken = null")
    page.keyboard.press("Control+z")
    settle(page)
    check("undo: nor in the query box", page.evaluate("window.__taken") is False and stored(page, "t1", "owner") == BY_ID["t1"]["owner"] + "X")
    context.close()

    # ---- the focus on the page itself; two sheets on a page
    context, page = sheet(browser, base, toggle=True, toolbar="bar", second=True)
    page.evaluate("for (const v of document.querySelectorAll('data-views')) v.editing = true")
    settle(page)
    type_into(page, "t1", "owner", "X")
    page.locator('#sheet2 tbody tr[data-id="t2"] td[data-col="owner"]').click()
    page.keyboard.press("End")
    page.keyboard.type("Y")
    page.keyboard.press("Enter")
    settle(page)
    page.evaluate("document.activeElement.blur()")
    check("undo: (the focus is on the page, not a row)", page.evaluate("document.activeElement === document.body"))
    undo_key(page)
    two = page.evaluate("() => [document.querySelector('#sheet').row('t1').owner, document.querySelector('#sheet2').row('t2').owner]")
    check("undo: with the focus on the page, the sheet edited last takes the key, and only it", two == [BY_ID["t1"]["owner"] + "X", BY_ID["t2"]["owner"]], two)
    context.close()

    # ---- through the hooks, with the old values
    hook = "v.acceptEdit = async ({ id, set, row }) => { window.__log.push({ id, set }); if (window.__no) return { ok: false, reason: 'The owner is locked this week.' }; Object.assign(row, set); return { ok: true }; };"
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=hook)
    to_edit(page)
    was = BY_ID["t1"]["owner"]
    type_into(page, "t1", "owner", "X")
    undo_key(page)
    check("undo: goes through acceptEdit with the old value", page.evaluate("window.__log") == [{"id": "t1", "set": {"owner": was + "X"}}, {"id": "t1", "set": {"owner": was}}], page.evaluate("window.__log"))
    redo_key(page)
    check("undo: redo goes through it with the new value", page.evaluate("window.__log[2]") == {"id": "t1", "set": {"owner": was + "X"}}, page.evaluate("window.__log"))
    page.evaluate("window.__no = true")
    undo_key(page)
    check("undo: a host's refusal leaves the value", stored(page, "t1", "owner") == was + "X", stored(page, "t1", "owner"))
    check("undo: it says so, with the host's reason", "The owner is locked this week." in toast(page).inner_text(), toast(page).inner_text() if toast(page).count() else None)
    check("undo: and the stack stays true: still undoable, nothing to redo", can(page) == [True, False], can(page))
    page.evaluate("window.__no = false")
    undo_key(page)
    check("undo: once the host agrees the same step undoes", stored(page, "t1", "owner") == was and can(page) == [False, True], can(page))
    page.evaluate("window.__no = true")
    redo_key(page)
    check("undo: a refused redo stays redoable", stored(page, "t1", "owner") == was and can(page) == [False, True] and "The owner is locked this week." in toast(page).inner_text(), can(page))
    context.close()

    # ---- a row that has gone; a host with no way back
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    type_into(page, "t1", "owner", "X")
    page.evaluate("() => { const v = document.querySelector('#sheet'); const d = v.data; v.data = { ...d, rows: d.rows.filter((r) => r.id !== 't1') }; }")
    settle(page)
    page.locator(f"{V} .dv-status").click()
    undo_key(page)
    check("undo: a step whose row has gone says so and leaves the stack", "gone" in toast(page).inner_text() and can(page) == [False, False], can(page))
    context.close()

    only_delete = "v.acceptDelete = async () => ({ ok: true });"
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=only_delete)
    to_edit(page)
    page.evaluate("() => document.querySelector('#sheet').deleteRows(['t1'])")
    settle(page)
    check("undo: a host that takes deletes and no adds: no Undo is offered", page.locator(f"{V} .dv-toast [data-toast-undo]").count() == 0, toast(page).inner_text() if toast(page).count() else None)
    check("undo: and none is on the stack", can(page) == [False, False], can(page))
    context.close()

    no_id = "v.acceptAdd = async () => ({ ok: true });"
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=no_id)
    to_edit(page)
    page.evaluate("() => document.querySelector('#sheet').addRow({ task: 'x' })")
    settle(page)
    check("undo: an add a host answers with no id is not recorded", can(page) == [False, False], can(page))
    context.close()

    only_add = "v.acceptAdd = async () => ({ ok: true, id: 'n1' }); v.acceptEdit = async () => ({ ok: true });"
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=only_add)
    to_edit(page)
    page.evaluate("() => document.querySelector('#sheet').addRow({ task: 'x' })")
    settle(page)
    page.locator(f"{V} .dv-status").click()
    undo_key(page)
    check("undo: a host that takes adds and no deletes: the undo says it cannot, and stays", "cannot" in toast(page).inner_text() and can(page) == [True, False], toast(page).inner_text() if toast(page).count() else None)
    context.close()

    # ---- View, `editable` alone
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=WATCH_KEY)
    to_edit(page)
    type_into(page, "t1", "owner", "X")
    to_edit(page)
    page.locator(f"{V} .dv-status").click()
    page.keyboard.press("Control+z")
    settle(page)
    check("undo: in View the key does nothing and is not taken", page.evaluate("window.__taken") is False and stored(page, "t1", "owner") == BY_ID["t1"]["owner"] + "X")
    no = page.evaluate("() => document.querySelector('#sheet').undo()")
    check("undo: in View undo() refuses", no["ok"] is False and "View" in no["reason"], no)
    to_edit(page)
    page.locator(f"{V} .dv-status").click()
    undo_key(page)
    check("undo: the stack waits for Edit", stored(page, "t1", "owner") == BY_ID["t1"]["owner"])
    context.close()

    context, page = sheet(browser, base, editable=True, toolbar="bar", setup=WATCH_KEY)
    type_into(page, "t1", "owner", "X")
    page.locator(f"{V} .dv-status").click()
    page.keyboard.press("Control+z")
    settle(page)
    check("undo: editable with no edit-toggle keeps no stack and takes no key", page.evaluate("window.__taken") is False and stored(page, "t1", "owner") == BY_ID["t1"]["owner"] + "X" and can(page) == [False, False], can(page))
    context.close()


# ------------------------------------------------------------------ 4. pasting a block
def clip(page, text, html=None):
    """Put text (and an HTML table, as a spreadsheet does) on the real clipboard."""
    page.evaluate("""async ([text, html]) => {
      const parts = { 'text/plain': new Blob([text], { type: 'text/plain' }) };
      if (html) parts['text/html'] = new Blob([html], { type: 'text/html' });
      await navigator.clipboard.write([new ClipboardItem(parts)]);
    }""", [text, html])


def clip_block(page, block):
    """A block as a spreadsheet puts it on the clipboard: tab-separated text, and a table beside it."""
    rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in line) + "</tr>" for line in block)
    clip(page, "\n".join("\t".join(line) for line in block) + "\n", f"<table><tbody>{rows}</tbody></table>")


def paste(page):
    page.keyboard.press("Control+V")
    settle(page)


def as_stored(text, prop):
    """What a pasted cell should become, by CONTRACT §40, worked out here from the fixture's own property."""
    kind = DATA["properties"][prop]["type"]
    t = text.strip()
    if t == "":
        return None
    if kind == "number":
        try:
            return int(t) if t.lstrip("-").isdigit() else float(t)
        except ValueError:
            return text
    if kind == "boolean":
        return {"true": True, "yes": True, "1": True, "false": False, "no": False, "0": False}.get(t.lower(), text)
    return text


def locked_cell(row_id, prop):
    return bool(BY_ID[row_id].get("_readOnly")) or "readOnly" in DATA["properties"][prop] or "derived" in DATA["properties"][prop]


def fill_oracle(block, start_row, start_prop, order=ORDER, ids=IDS):
    """{row: {prop: value}} and how many cells were locked, walking the fixture's rows and columns by position."""
    want, locked = {}, 0
    r0, c0 = ids.index(start_row), order.index(start_prop)
    for r, line in enumerate(block):
        for c, text in enumerate(line):
            if r0 + r >= len(ids) or c0 + c >= len(order):
                continue
            rid, prop = ids[r0 + r], order[c0 + c]
            if locked_cell(rid, prop):
                locked += 1
            else:
                want.setdefault(rid, {})[prop] = as_stored(text, prop)
    return want, locked


def with_fill(want):
    """The fixture's rows with those cells replaced: the whole expected data, every other cell untouched."""
    rows = json.loads(json.dumps(ROWS))
    for row in rows:
        for prop, value in want.get(row["id"], {}).items():
            cell_was = row.get(prop)
            row[prop] = {**cell_was, "value": value} if isinstance(cell_was, dict) else value
    return rows


@section
def block_paste(browser, base):
    # ---- across and down from the open cell, a locked column skipped and counted, one undo step
    block = [["Mia", "NOPE-1", "7"], ["Kai", "NOPE-2", "8.5"], ["Zed", "NOPE-3", "not a number"]]
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    clip(page, "\n".join("\t".join(line) for line in block) + "\n")
    cell(page, "t1", "owner").click()
    paste(page)
    want, locked = fill_oracle(block, "t1", "owner")
    check("paste: tab-separated text fills across and down from the open cell, by position; every other cell untouched", stored_rows(page) == with_fill(want), stored_rows(page)[:3])
    check("paste: the editor has closed", not editor_open(page))
    check("paste: a value that is not a number stays as written, and draws so", stored(page, "t3", "points") == "not a number" and cell(page, "t3", "points").inner_text().strip() == "not a number", stored(page, "t3", "points"))
    text = toast(page).inner_text()
    check("paste: the toast says how many cells, and how many it skipped", "Pasted 6 cells" in text and f"{locked} locked" in text, text)
    check("paste: the toast holds Undo", toast(page).locator("[data-toast-undo]").count() == 1)
    undo_key(page)
    check("paste: one Ctrl+Z takes the whole block back", stored_rows(page) == ROWS and can(page) == [False, True], can(page))
    redo_key(page)
    check("paste: one redo puts it all back", stored_rows(page) == with_fill(want))
    toast_undo = page.evaluate("() => document.querySelector('#sheet').undo()")
    settle(page)
    check("paste: undo() answers ok", toast_undo["ok"] is True and stored_rows(page) == ROWS, toast_undo)
    context.close()

    # ---- a locked row in the way; types; empty cells; a checkbox
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    block = [["One"], ["Two"], ["Three"]]
    clip_block(page, block)
    cell(page, "t4", "owner").click()
    paste(page)
    want, locked = fill_oracle(block, "t4", "owner")
    check("paste: a read-only row is skipped; the rows around it fill", stored_rows(page) == with_fill(want) and locked == 1, stored(page, "t6", "owner"))
    check("paste: and it is counted", "1 locked" in toast(page).inner_text(), toast(page).inner_text())
    undo_key(page)
    block = [["", "", "done", "TRUE"], ["3", "2031-04-01", "doing", "no"]]
    clip_block(page, block)
    cell(page, "t1", "points").click()
    paste(page)
    want, _ = fill_oracle(block, "t1", "points")
    check("paste: an empty cell clears, a number is a number, a date and a word as written, a checkbox reads TRUE and no", stored_rows(page) == with_fill(want), {k: stored(page, "t1", k) for k in ("points", "due", "status", "shipped")})
    context.close()

    # ---- past the last column; past the last row, with and without room
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    block = [["a note", "x", "y"]]
    clip_block(page, block)
    cell(page, "t1", "notes").click()
    paste(page)
    check("paste: a value past the last column is left out and counted", "1 past the last column" in toast(page).inner_text() and "1 locked" in toast(page).inner_text(), toast(page).inner_text())
    undo_key(page)
    block = [["Last"], ["New one"], ["New two"]]
    clip_block(page, block)
    cell(page, "t8", "task").click()
    paste(page)
    rows = stored_rows(page)
    check("paste: past the last row it adds rows, after the last one, in the block's order", [r.get("task") for r in rows[-3:]] == ["Last", "New one", "New two"] and len(rows) == len(ROWS) + 2, [r.get("task") for r in rows[-3:]])
    new_ids = [r["id"] for r in rows[-2:]]
    check("paste: they draw", page.locator(f'{V} tbody tr[data-id="{new_ids[1]}"]').count() == 1)
    undo_key(page)
    check("paste: one undo takes the edit and the new rows", stored_rows(page) == ROWS, len(stored_rows(page)))
    redo_key(page)
    check("paste: one redo brings the same rows back", [r["id"] for r in stored_rows(page)[-2:]] == new_ids, [r["id"] for r in stored_rows(page)[-2:]])
    context.close()
    context, page = sheet(browser, base, toggle=True, toolbar="bar", view="Fixed size")
    to_edit(page)
    block = [["A"], ["B"], ["C"]]
    clip_block(page, block)
    cell(page, "t8", "owner").click()
    paste(page)
    check("paste: a view that says addRow: false does not grow", len(stored_rows(page)) == len(ROWS) and stored(page, "t8", "owner") == "A", len(stored_rows(page)))
    check("paste: and the rows left out are counted", "2 past the last row" in toast(page).inner_text(), toast(page).inner_text())
    context.close()

    # ---- what is a block: words stay words; a column with a table beside it; Excel's quoting; one cell from Excel
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    clip(page, "line one\nline two")
    cell(page, "t2", "notes").click()
    page.keyboard.press("Control+A")
    paste(page)
    check("paste: plain lines stay words in the open editor", editor_open(page) and page.evaluate("document.activeElement.value") == "line one\nline two", page.evaluate("document.activeElement.value"))
    check("paste: and nothing else moved", stored_rows(page) == ROWS)
    page.keyboard.press("Escape")
    settle(page)
    table = "<table><tbody><tr><td>P</td></tr><tr><td>Q</td></tr></tbody></table>"
    clip(page, "P\nQ", table)
    cell(page, "t1", "owner").click()
    paste(page)
    check("paste: lines with a table beside them (a spreadsheet's column) fill down", stored(page, "t1", "owner") == "P" and stored(page, "t2", "owner") == "Q", [stored(page, "t1", "owner"), stored(page, "t2", "owner")])
    undo_key(page)
    clip(page, '"two\nlines"\t"Ana ""B"""\n')
    cell(page, "t1", "task").click()
    paste(page)
    check("paste: a quoted cell holds its line break and its quotes", stored(page, "t1", "task") == "two\nlines" and stored(page, "t1", "owner") == 'Ana "B"', [stored(page, "t1", "task"), stored(page, "t1", "owner")])
    undo_key(page)
    clip(page, "abc\r\n", "<table><tr><td>abc</td></tr></table>")
    cell(page, "t2", "owner").click()
    page.keyboard.press("Control+A")
    paste(page)
    check("paste: one cell from a spreadsheet goes in as its words, no line break", editor_open(page) and page.evaluate("document.activeElement.value") == "abc", repr(page.evaluate("document.activeElement.value")))
    page.keyboard.press("Escape")
    context.close()

    # ---- a focused row, by keyboard; a number cell's control; a file still goes to the cell
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    clip(page, "Row task\tRow owner")
    page.locator(f'{V} tbody tr[data-id="t3"]').focus()
    paste(page)
    check("paste: on a focused row it starts at the row's first editable cell", stored(page, "t3", "task") == "Row task" and stored(page, "t3", "owner") == "Row owner", stored(page, "t3", "task"))
    undo_key(page)
    clip(page, "11\t2031-05-05")
    cell(page, "t1", "points").click()
    paste(page)
    check("paste: from a number cell's control too", stored(page, "t1", "points") == 11 and stored(page, "t1", "due") == "2031-05-05", stored(page, "t1", "points"))
    context.close()
    files = "v.acceptFile = async ({ file }) => { window.__log.push(file.name); return { ok: true, attachment: { url: 'data:image/gif;base64,R0lGODlhAQABAAAAACw=', kind: 'image', name: file.name } }; };"
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=files)
    to_edit(page)
    cell(page, "t1", "notes").click()
    page.evaluate("""() => {
      const data = new DataTransfer(); data.items.add(new File([new Uint8Array(8)], 'shot.png', { type: 'image/png' }));
      document.activeElement.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
    }""")
    page.wait_for_selector(f"{V} .dv-celledit .dv-ed-thumb")
    check("paste: a file goes to the media cell, as §37 says", page.evaluate("window.__log") == ["shot.png"])
    page.keyboard.press("Escape")
    context.close()

    # ---- View and `editable` alone
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    clip(page, "a\tb")
    page.locator(f'{V} tbody tr[data-i="0"]').focus()
    paste(page)
    check("paste: in View nothing happens", stored_rows(page) == ROWS)
    context.close()
    context, page = sheet(browser, base, editable=True, toolbar="bar")
    clip(page, "a\tb")
    cell(page, "t1", "owner").click()
    page.keyboard.press("Control+A")
    paste(page)
    check("paste: editable with no edit-toggle keeps §37: the text goes into the editor", editor_open(page) and stored_rows(page) == ROWS and page.evaluate("document.activeElement.value") == "a\tb", repr(page.evaluate("document.activeElement.value")))
    page.keyboard.press("Escape")
    context.close()

    # ---- one batch: acceptBatch hears one call, all or nothing; undo is one call too
    batch = """v.acceptBatch = async (plan) => { window.__log.push(JSON.parse(JSON.stringify(plan)));
      if (window.__no) return { ok: false, reason: 'The sheet is frozen.' };
      return { ok: true, ids: plan.adds.map((a, i) => a.id || 'host-' + (window.__log.length) + '-' + i) }; };"""
    block = [["M1"], ["M2"], ["M3"]]
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=batch)
    to_edit(page)
    clip_block(page, block)
    cell(page, "t7", "owner").click()
    paste(page)
    log = page.evaluate("window.__log")
    check("paste: with acceptBatch one paste is one call: its edits and its new row", len(log) == 1 and log[0]["edits"] == [{"id": "t7", "set": {"owner": "M1"}}, {"id": "t8", "set": {"owner": "M2"}}] and log[0]["adds"] == [{"set": {"owner": "M3"}, "at": "end"}] and log[0]["deletes"] == [], log)
    check("paste: on its ok the element applies it, the host's id on the new row", stored(page, "t7", "owner") == "M1" and stored(page, "t8", "owner") == "M2" and stored(page, "host-1-0", "owner") == "M3", stored(page, "host-1-0", "owner"))
    undo_key(page)
    log = page.evaluate("window.__log")
    check("paste: undo is one call: the old values, and the new row deleted", len(log) == 2 and log[1]["edits"] == [{"id": "t8", "set": {"owner": BY_ID["t8"]["owner"]}}, {"id": "t7", "set": {"owner": BY_ID["t7"]["owner"]}}] and log[1]["deletes"] == ["host-1-0"] and log[1]["adds"] == [], log[-1])
    check("paste: and the data is the fixture's", stored_rows(page) == ROWS)
    page.evaluate("window.__no = true")
    redo_key(page)
    check("paste: a refused redo changes nothing and says why", stored_rows(page) == ROWS and "The sheet is frozen." in toast(page).inner_text() and can(page) == [False, True], can(page))
    page.evaluate("window.__no = false")
    clip(page, "Z")
    context.close()
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=batch + "window.__no = true;")
    to_edit(page)
    clip_block(page, block)
    cell(page, "t1", "owner").click()
    paste(page)
    check("paste: a refused batch changes nothing, says why, and leaves nothing to undo", stored_rows(page) == ROWS and "The sheet is frozen." in toast(page).inner_text() and can(page) == [False, False], toast(page).inner_text())
    context.close()

    # ---- no acceptBatch: each row through acceptEdit; one refused: reported, and the undo step holds only what landed
    rows_hook = """v.acceptEdit = async ({ id, set, row }) => { window.__log.push({ id, set }); if (id === 't2' && window.__no !== false) return { ok: false, reason: 'Bo signs off on this one.' }; Object.assign(row, set); return { ok: true }; };"""
    block = [["R1"], ["R2"], ["R3"]]
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=rows_hook)
    to_edit(page)
    clip_block(page, block)
    cell(page, "t1", "owner").click()
    paste(page)
    check("paste: with no acceptBatch each row goes through acceptEdit", [x["id"] for x in page.evaluate("window.__log")] == ["t1", "t2", "t3"], page.evaluate("window.__log"))
    check("paste: what a host refuses stays as it was, and the rest lands", [stored(page, i, "owner") for i in ("t1", "t2", "t3")] == ["R1", BY_ID["t2"]["owner"], "R3"], [stored(page, i, "owner") for i in ("t1", "t2", "t3")])
    check("paste: the toast says so, with the reason", "Bo signs off on this one." in toast(page).inner_text(), toast(page).inner_text())
    undo_key(page)
    log = page.evaluate("window.__log")
    check("paste: the undo step holds only what landed", [x["id"] for x in log[3:]] == ["t3", "t1"] and stored_rows(page) == ROWS, log[3:])
    context.close()


# ------------------------------------------------------------------ 5. a value that comes from its sources takes no hand edit
SRC = json.loads((FIX / "sourced.json").read_text(encoding="utf-8"))
SRC_TEXT = (FIX / "sourced.base").read_text(encoding="utf-8")
SRC_BY_ID = {r["id"]: r for r in SRC["rows"]}
# the Parts view's drawn columns: the order, with the Nominal source column after the first multi-source one
SRC_COLUMNS = ["part", "torque", "torque@source", "maker", "mass", "owner"]
LOG_EDITS = "v.acceptEdit = async ({ id, set, row }) => { window.__log.push({ id, set }); Object.assign(row, set); return { ok: true }; };"
LOG_BATCH = "v.acceptBatch = async (plan) => { window.__log.push(JSON.parse(JSON.stringify(plan))); return { ok: true, ids: plan.adds.map((a) => a.id) }; };"


def nominal(cell):
    """The value a reader sees, from the fixture alone: the first source, by the ladder's rungs, that states the cell."""
    if not (isinstance(cell, dict) and "sources" in cell):
        return cell["value"] if isinstance(cell, dict) else cell
    rungs = [r["id"] for r in SRC["ladder"]]
    ranked = sorted(cell["sources"], key=lambda e: rungs.index(SRC["sources"][e["source"]]["rung"]))
    return ranked[0]["value"]


def drawn_value(page, row, col):
    """A cell's value as drawn: the pill beside it in the cell is not the value."""
    return page.evaluate("""([r, c]) => { const t = document.querySelector(`#sheet tbody tr[data-id="${r}"] td[data-col="${c}"]`).cloneNode(true); for (const x of t.querySelectorAll('.dv-src-dd, .dv-src-pin')) x.remove(); return t.textContent.trim(); }""", [row, col])


def held(page, row, col):
    """The cell as loaded, sources and all: where a lost edit would show."""
    return page.evaluate("([r, c]) => { const x = document.querySelector('#sheet')._rawRow(r); return x ? x[c] ?? null : '(no row)'; }", [row, col])


def shown(page, row, col):
    return page.evaluate("([r, c]) => { const x = document.querySelector('#sheet').row(r)[c]; return x && typeof x === 'object' ? x.value : x; }", [row, col])


def sourced_sheet(browser, base, **opts):
    return sheet(browser, base, data=SRC, text=SRC_TEXT, **opts)


def msg(page):
    return page.locator(f"{V} .dv-celledit .dv-ed-msg").inner_text()


def typed(page):
    return page.evaluate("document.activeElement.value")


@section
def sourced(browser, base):
    for label, opts in (("editable", {"editable": True, "setup": LOG_EDITS}), ("edit-toggle", {"toggle": True, "toolbar": "bar", "setup": LOG_EDITS}), ("in memory", {"editable": True})):
        context, page = sourced_sheet(browser, base, **opts)
        if "toggle" in opts:
            to_edit(page)
        want = nominal(SRC_BY_ID["p1"]["torque"])
        check(f"sourced {label}: (the cell shows the fixture's nominal)", drawn_value(page, "p1", "torque") == str(want), drawn_value(page, "p1", "torque"))
        cell(page, "p1", "torque").click()
        page.keyboard.press("Control+A")
        page.keyboard.type("99")
        page.keyboard.press("Enter")
        settle(page)
        check(f"sourced {label}: an edit to a multi-source cell is refused: the editor stays open", editor_open(page))
        check(f"sourced {label}: with a plain reason", "comes from its sources" in msg(page) and "Pick a source from its menu" in msg(page), msg(page))
        check(f"sourced {label}: the typed text survives, in the focused control", typed(page) == "99", typed(page))
        check(f"sourced {label}: no host hook ran", page.evaluate("window.__log") == [], page.evaluate("window.__log"))
        check(f"sourced {label}: the cell as loaded is untouched", held(page, "p1", "torque") == SRC_BY_ID["p1"]["torque"], held(page, "p1", "torque"))
        page.keyboard.press("Escape")
        settle(page)
        check(f"sourced {label}: Esc leaves the shown value as it was", not editor_open(page) and drawn_value(page, "p1", "torque") == str(want) and shown(page, "p1", "torque") == want, cell(page, "p1", "torque").inner_text())
        context.close()

    # ---- a list of one source is the same: the edit would resolve straight back; the other ways out of the editor
    context, page = sourced_sheet(browser, base, toggle=True, toolbar="bar", setup=LOG_EDITS)
    to_edit(page)
    cell(page, "p2", "torque").click()
    page.keyboard.press("Control+A")
    page.keyboard.type("77")
    page.keyboard.press("Enter")
    settle(page)
    check("sourced: a cell with one entry in `sources` is refused too (it would resolve straight back)", editor_open(page) and "comes from its sources" in msg(page) and typed(page) == "77" and page.evaluate("window.__log") == [], msg(page))
    page.keyboard.press("Escape")
    settle(page)
    cell(page, "p1", "torque").click()
    page.keyboard.press("Control+A")
    page.keyboard.type("55")
    page.keyboard.press("Tab")
    settle(page)
    check("sourced: Tab does not walk away from a refusal", editor_open(page) and typed(page) == "55" and "comes from its sources" in msg(page), typed(page))
    switch(page).click()
    settle(page)
    check("sourced: turning Edit off keeps Edit, the editor, the words and the reason", page.evaluate("document.querySelector('#sheet').editing") is True and editor_open(page) and page.locator(f"{V} .dv-celledit input").input_value() == "55", page.evaluate("document.querySelector('#sheet').editing"))
    page.keyboard.press("Escape")
    settle(page)
    no = page.evaluate("() => document.querySelector('#sheet').propose({ id: 'p1', set: { torque: 12 } })")
    check("sourced: a script's value set beside the sources is refused the same way", no["ok"] is False and "comes from its sources" in no["reason"] and page.evaluate("window.__log") == [], no)
    # WHY it lands now (CONTRACT §36): a new list is the data itself, nothing beside it, and an edit of a source's own column arrives as one
    fresh = {"sources": [{"source": "sheet", "value": 1}]}
    yes = page.evaluate("(cell) => document.querySelector('#sheet').propose({ id: 'p1', set: { torque: cell } })", fresh)
    check("sourced: a new list of sources is no hand edit: it lands, and the cell reads it", yes["ok"] is True and held(page, "p1", "torque") == fresh and drawn_value(page, "p1", "torque") == "1", {"answer": yes, "held": held(page, "p1", "torque")})
    context.close()

    # ---- plain, rich and single-source cells stay editable, in the same row
    context, page = sourced_sheet(browser, base, toggle=True, toolbar="bar", setup=LOG_EDITS)
    to_edit(page)
    cell(page, "p1", "maker").click()
    page.keyboard.press("Control+A")
    page.keyboard.type("Hand maker")
    page.keyboard.press("Enter")
    settle(page)
    check("sourced: a §22 cell naming one source stays editable, its other keys kept", not editor_open(page) and held(page, "p1", "maker") == {"value": "Hand maker", "source": "sheet"}, held(page, "p1", "maker"))
    cell(page, "p1", "mass").click()
    page.keyboard.press("Control+A")
    page.keyboard.type("3.75")
    page.keyboard.press("Enter")
    settle(page)
    check("sourced: a plain rich cell stays editable, its other keys kept", held(page, "p1", "mass") == {"value": 3.75, "unit": "kg", "basis": "measured"}, held(page, "p1", "mass"))
    cell(page, "p1", "owner").click()
    page.keyboard.press("Control+A")
    page.keyboard.type("Noor")
    page.keyboard.press("Enter")
    settle(page)
    check("sourced: a plain cell in the same row stays editable", held(page, "p1", "owner") == "Noor" and held(page, "p1", "torque") == SRC_BY_ID["p1"]["torque"])
    cell(page, "p3", "torque").click()
    page.keyboard.press("Control+A")
    page.keyboard.type("31")
    page.keyboard.press("Enter")
    settle(page)
    check("sourced: a plain cell of a column others state by sources stays editable", held(page, "p3", "torque") == 31, held(page, "p3", "torque"))
    check("sourced: those edits reached the host", [list(x["set"]) for x in page.evaluate("window.__log")] == [["maker"], ["mass"], ["owner"], ["torque"]], page.evaluate("window.__log"))
    context.close()

    # ---- the peek's form: the reason, the typed text; nothing reaches the host; a form holding one such field refuses whole
    context, page = sourced_sheet(browser, base, editable=True, setup=LOG_EDITS, view="Form", toolbar="full")
    page.locator(f'{V} tbody tr[data-i="0"] td[data-col="maker"]').click()
    page.wait_for_selector(f"{V} .dv-peek-form")
    field = page.locator(f'{V} .dv-peek-form [name="torque"]')
    field.fill("99")
    page.locator(f'{V} .dv-peek-form [name="owner"]').fill("Noor")
    page.locator(f"{V} .dv-peek-form button[type=submit]").click()
    settle(page)
    words = page.locator(f"{V} .dv-peek-form .dv-form-msg").inner_text()
    check("sourced form: the peek's form says why, naming the field", "Torque comes from its sources" in words, words)
    check("sourced form: the typed text survives", field.input_value() == "99" and page.locator(f'{V} .dv-peek-form [name="owner"]').input_value() == "Noor")
    check("sourced form: no host hook ran; the shown value and the row are as they were", page.evaluate("window.__log") == [] and held(page, "p1", "torque") == SRC_BY_ID["p1"]["torque"] and held(page, "p1", "owner") == "Ana", page.evaluate("window.__log"))
    context.close()

    # ---- a record page: the record view's form, and a long property's own section
    context, page = new_page(browser, base)
    page.evaluate(MOUNT, [SRC_TEXT, SRC, {"editable": True, "setup": LOG_EDITS, "view": "Record", "toolbar": "full"}])  # a record draws no table rows to wait on
    page.wait_for_selector(f'{V} .dv-view [name="torque"]', timeout=15000)
    settle(page)
    field = page.locator(f'{V} .dv-view [name="torque"]')
    field.fill("99")
    page.locator(f"{V} .dv-view button[type=submit]").click()
    settle(page)
    words = page.locator(f"{V} .dv-view .dv-form-msg").inner_text()
    check("sourced record: the record view's form says why, and keeps the words", "comes from its sources" in words and field.input_value() == "99", words)
    check("sourced record: no host hook ran; the value is as it was", page.evaluate("window.__log") == [] and shown(page, "p1", "torque") == nominal(SRC_BY_ID["p1"]["torque"]))
    context.close()
    context, page = sourced_sheet(browser, base, editable=True, setup=LOG_EDITS)
    page.locator(f'{V} tbody tr[data-i="0"] .dv-row-open').evaluate("(b) => b.click()")
    page.wait_for_selector(f"{V} .dv-peek [data-page-sec='note'] textarea")
    area = page.locator(f"{V} .dv-peek [data-page-sec='note'] textarea")
    area.click()
    page.keyboard.press("Control+A")
    page.keyboard.type("Hand words")
    page.locator(f"{V} .dv-peek header").click()
    settle(page)
    words = page.locator(f"{V} .dv-peek [data-page-sec='note'] .dv-ed-msg").inner_text()
    check("sourced page: a long property's section says why, and keeps the words", "comes from its sources" in words and area.input_value() == "Hand words", words)
    check("sourced page: no host hook ran; the value is as it was", page.evaluate("window.__log") == [] and held(page, "p1", "note") == SRC_BY_ID["p1"]["note"] and shown(page, "p1", "note") == nominal(SRC_BY_ID["p1"]["note"]), page.evaluate("window.__log"))
    context.close()

    # ---- a paste counts them as locked and leaves them alone; the batch never carries them
    block = [["Paste A", "9", "skip", "Maker A", "1.5", "Own A"], ["Paste B", "8", "skip", "Maker B", "2.5", "Own B"], ["Paste C", "7", "skip", "Maker C", "3.5", "Own C"]]
    n_locked = sum(1 for r in ("p1", "p2", "p3") for c in ("torque", "torque@source") if c == "torque@source" or (isinstance(SRC_BY_ID[r][c], dict) and "sources" in SRC_BY_ID[r][c]))
    n_filled = sum(len(line) for line in block) - n_locked
    context, page = sourced_sheet(browser, base, toggle=True, toolbar="bar", setup=LOG_BATCH)
    to_edit(page)
    clip_block(page, block)
    cell(page, "p1", "part").click()
    paste(page)
    check("sourced paste: the multi-source cells are left as they were", held(page, "p1", "torque") == SRC_BY_ID["p1"]["torque"] and held(page, "p2", "torque") == SRC_BY_ID["p2"]["torque"])
    check("sourced paste: a plain cell in the same column takes its value", held(page, "p3", "torque") == 7, held(page, "p3", "torque"))
    check("sourced paste: the rows' other cells land", held(page, "p1", "part") == "Paste A" and held(page, "p2", "owner") == "Own B" and held(page, "p1", "maker") == {"value": "Maker A", "source": "sheet"}, held(page, "p1", "maker"))
    check("sourced paste: the toast counts them as skipped", f"Pasted {n_filled} cells" in toast(page).inner_text() and f"{n_locked} locked" in toast(page).inner_text(), toast(page).inner_text())
    log = page.evaluate("window.__log")
    check("sourced paste: the host's batch never carries one", len(log) == 1 and all("torque" not in e["set"] for e in log[0]["edits"] if e["id"] != "p3"), log)
    undo_key(page)
    log = page.evaluate("window.__log")
    check("sourced paste: its undo carries none either, and the data is the fixture's", len(log) == 2 and all("torque" not in e["set"] for e in log[1]["edits"] if e["id"] != "p3") and held(page, "p1", "part") == SRC_BY_ID["p1"]["part"] and held(page, "p3", "torque") == 30, log[-1])
    context.close()

    # ---- a cell that became multi-source after the paste: undo skips and counts it, the rest comes back, the stack stays true
    for label, setup in (("through acceptEdit", LOG_EDITS), ("through acceptBatch", LOG_BATCH), ("in memory", None)):
        opts = {"setup": setup} if setup else {}
        context, page = sourced_sheet(browser, base, toggle=True, toolbar="bar", **opts)
        to_edit(page)
        block = [["Hand maker", "9.5"]]
        clip_block(page, block)
        cell(page, "p3", "maker").click()
        paste(page)
        check(f"sourced undo {label}: (the paste landed)", held(page, "p3", "maker") == "Hand maker" and held(page, "p3", "mass") == 9.5)
        turned = json.loads(json.dumps(SRC))
        later = {"sources": [{"source": "bench", "value": "Bench maker"}]}
        for row in turned["rows"]:
            if row["id"] == "p3":
                row["maker"] = later
                row["mass"] = 9.5
        page.evaluate("(d) => { document.querySelector('#sheet').data = d; }", turned)
        settle(page)
        before = len(page.evaluate("window.__log"))
        page.locator(f"{V} .dv-status").click()
        undo_key(page)
        check(f"sourced undo {label}: the cell that now has sources stays as they say", held(page, "p3", "maker") == later, held(page, "p3", "maker"))
        check(f"sourced undo {label}: the rest of the paste comes back", held(page, "p3", "mass") == SRC_BY_ID["p3"]["mass"], held(page, "p3", "mass"))
        check(f"sourced undo {label}: the toast counts it as skipped", "1 locked" in toast(page).inner_text(), toast(page).inner_text() if toast(page).count() else None)
        check(f"sourced undo {label}: the step has left the undo stack, so the key is not stuck on it", can(page) == [False, True], can(page))
        said = json.dumps(page.evaluate("window.__log")[before:])
        check(f"sourced undo {label}: no hook heard the skipped cell", "maker" not in said, said)
        redo_key(page)
        check(f"sourced undo {label}: redo brings back only what undo took", held(page, "p3", "mass") == 9.5 and held(page, "p3", "maker") == later, held(page, "p3", "maker"))
        context.close()

    # ---- phone width, both themes: the refusal is readable and the page does not scroll sideways
    for dark, name in ((False, "light"), (True, "dark")):
        context, page = sourced_sheet(browser, base, width=390, height=800, dark=dark, mobile=True, editable=True)
        cell(page, "p1", "torque").click()
        page.keyboard.press("Control+A")
        page.keyboard.type("99")
        page.keyboard.press("Enter")
        settle(page)
        check(f"sourced {name}-390: the reason shows, and the page does not scroll sideways", "comes from its sources" in msg(page) and over(page) <= 0, over(page))
        ratio = contrast(page, f"{V} .dv-celledit .dv-ed-msg")
        check(f"sourced {name}-390: the reason reads against the editor", ratio >= 4.5, round(ratio, 2))
        context.close()


# ------------------------------------------------------------------ 6. columns, from the header menu
def heads(page):
    return page.evaluate("() => [...document.querySelectorAll('#sheet thead tr.dv-hleaf th[data-col]')].map((t) => t.dataset.col)")


def head_text(page, col):
    return page.evaluate("(c) => document.querySelector(`#sheet thead th[data-col=\"${c}\"] .dv-th`).textContent.trim()", col)


def col_menu(page, col):
    page.locator(f'{V} thead th[data-col="{col}"]').hover()
    page.locator(f'{V} thead th[data-col="{col}"] [data-col-menu]').click()
    page.wait_for_selector(f"{V} .dv-pop.dv-colmenu:not([hidden])")
    return page.locator(f"{V} .dv-pop.dv-colmenu")


def add_property(page, after, name, kind):
    menu = col_menu(page, after)
    menu.locator("[data-col-add]").click()
    form = menu.locator("[data-col-addform]")
    form.locator('[name="name"]').fill(name)
    form.locator('[name="kind"]').select_option(kind)
    form.locator("button[type=submit]").click()
    settle(page)


def rename(page, col, name):
    menu = col_menu(page, col)
    menu.locator("[data-col-name]").fill(name)
    page.keyboard.press("Enter")
    settle(page)


def retype(page, col, kind):
    menu = col_menu(page, col)
    menu.locator("[data-col-type]").select_option(kind)
    settle(page)
    page.keyboard.press("Escape")
    settle(page)


def definition(page, col):
    return page.evaluate("(c) => JSON.parse(JSON.stringify(document.querySelector('#sheet').data.properties))[c] ?? null", col)


def prop_keys(page):
    return page.evaluate("() => Object.keys(document.querySelector('#sheet').data.properties)")


def drawn(page, row, col):
    return cell(page, row, col).inner_text().strip()


def as_written(value):
    """A stored value as a reader should see it: the characters it was stored with."""
    return "" if value is None else str(value)


@section
def columns(browser, base):
    # ---- the menu: reached by hover, a right-click, the keyboard; Esc gives the focus back; a click on it is not a sort
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    plain = [c for c in ORDER]
    check("columns: every column's header has a menu in Edit", page.locator(f"{V} thead tr.dv-hleaf th[data-col] [data-col-menu]").count() == len(plain), page.locator(f"{V} thead [data-col-menu]").count())
    button = page.locator(f'{V} thead th[data-col="owner"] [data-col-menu]')
    check("columns: it is quiet until the header is hovered", float(button.evaluate("e => getComputedStyle(e).opacity")) < 0.1)
    page.locator(f'{V} thead th[data-col="owner"]').hover()
    page.wait_for_timeout(160)
    check("columns: a hover shows it", float(button.evaluate("e => getComputedStyle(e).opacity")) > 0.9)
    menu = col_menu(page, "owner")
    check("columns: the menu holds the column's name and type", menu.locator("[data-col-name]").input_value() == "Owner" and menu.locator("[data-col-type]").input_value() == "text", menu.locator("[data-col-name]").input_value())
    check("columns: and Hide, Delete, Add a property", all(menu.locator(s).count() == 1 for s in ("[data-col-hide]", "[data-col-delete]", "[data-col-add]")))
    check("columns: a click on it is not a sort", page.evaluate("(document.querySelector('#sheet').view.sort || []).length") == 0)
    page.keyboard.press("Escape")
    settle(page)
    check("columns: Esc closes it and gives the focus back to its button", page.locator(f"{V} .dv-pop:not([hidden])").count() == 0 and page.evaluate("document.activeElement.hasAttribute('data-col-menu')"), page.evaluate("document.activeElement.outerHTML.slice(0, 80)"))
    page.locator(f'{V} thead th[data-col="points"]').click(button="right")
    settle(page)
    check("columns: a right-click on a header opens it", page.locator(f"{V} .dv-pop.dv-colmenu:not([hidden]) [data-col-name]").input_value() == "Points")
    page.keyboard.press("Escape")
    page.locator(f'{V} thead th[data-col="due"] [data-col-menu]').focus()
    page.keyboard.press("Enter")
    settle(page)
    check("columns: a focused menu button opens it with Enter", page.locator(f"{V} .dv-pop.dv-colmenu:not([hidden]) [data-col-name]").input_value() == "Due")
    page.keyboard.press("Escape")
    page.locator(f'{V} thead th[data-col="status"] [data-col-menu]').focus()
    page.keyboard.press("Shift+F10")
    settle(page)
    check("columns: and with Shift+F10", page.locator(f"{V} .dv-pop.dv-colmenu:not([hidden]) [data-col-name]").input_value() == "Status")
    page.keyboard.press("Escape")
    context.close()

    # ---- rename: the display name, never a key
    log = "v.addEventListener('data-views-property', (e) => window.__log.push(e.detail));"
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=log)
    to_edit(page)
    rename(page, "owner", "Lead")
    check("columns: rename changes the header", head_text(page, "owner") == "Lead" and page.locator(f"{V} .dv-pop:not([hidden])").count() == 0, head_text(page, "owner"))
    check("columns: rename changes no stored key or value", stored_rows(page) == ROWS and prop_keys(page) == list(DATA["properties"]), prop_keys(page))
    check("columns: rename writes the .base's display name", page.evaluate("document.querySelector('#sheet').base.properties.owner.displayName") == "Lead")
    check("columns: it fires data-views-property {op, property, result}", page.evaluate("window.__log[0].op") == "rename" and page.evaluate("window.__log[0].property") == "owner" and page.evaluate("window.__log[0].result.ok") is True, page.evaluate("window.__log"))
    undo_key(page)
    check("columns: undo puts the name back", head_text(page, "owner") == "Owner", head_text(page, "owner"))
    redo_key(page)
    check("columns: redo renames it again", head_text(page, "owner") == "Lead")
    rename(page, "points", "Story points")
    check("columns: a column the .base never named renames too", head_text(page, "points").startswith("Story points") and "displayName" not in json.dumps(DATA["properties"]["points"]), head_text(page, "points"))
    undo_key(page)
    check("columns: undo takes that name away again", head_text(page, "points") == "Points" and "points" not in page.evaluate("Object.keys(document.querySelector('#sheet').base.properties)"), head_text(page, "points"))
    context.close()

    # ---- add: each of the seven kinds, a value of each, next to the column it was asked from
    context, page = sheet(browser, base, toggle=True, toolbar="bar", selectable=True)
    to_edit(page)
    add_property(page, "task", "Due date 2", "date")
    check("columns: a new property lands beside the column it was asked from", heads(page)[:2] == ["task", "due_date_2"], heads(page)[:3])
    check("columns: its header reads the name given, and its key comes from it", head_text(page, "due_date_2") == "Due date 2", head_text(page, "due_date_2"))
    check("columns: its type is what was picked", definition(page, "due_date_2")["type"] == "date", definition(page, "due_date_2"))
    check("columns: no row gained or lost a cell", stored_rows(page) == ROWS)
    cell(page, "t1", "due_date_2").click()
    page.locator(f'{V} .dv-celledit input[type="date"]').fill("2031-06-07")
    page.keyboard.press("Enter")
    settle(page)
    check("columns: a date cell takes a date", stored(page, "t1", "due_date_2") == "2031-06-07", stored(page, "t1", "due_date_2"))
    add_property(page, "task", "Words", "text")
    type_into(page, "t1", "words", "hello")
    check("columns: a text cell takes words", stored(page, "t1", "words") == "hello")
    add_property(page, "task", "Cost", "number")
    cell(page, "t1", "cost").click()
    page.keyboard.type("12.5")
    page.keyboard.press("Enter")
    settle(page)
    check("columns: a number cell takes a number", stored(page, "t1", "cost") == 12.5, stored(page, "t1", "cost"))
    add_property(page, "task", "Stage", "select")
    check("columns: a select draws its value as a badge", definition(page, "stage")["display"] == "badge", definition(page, "stage"))
    type_into(page, "t1", "stage", "alpha")
    type_into(page, "t2", "stage", "beta")
    cell(page, "t3", "stage").click()
    settle(page)
    offered = page.evaluate("[...document.querySelectorAll('#sheet .dv-celledit datalist option')].map((o) => o.value)")
    check("columns: a select offers the column's values, as a native list", sorted(offered) == ["alpha", "beta"], offered)
    page.keyboard.type("alpha")
    page.keyboard.press("Enter")
    settle(page)
    check("columns: and takes one", stored(page, "t3", "stage") == "alpha" and cell(page, "t3", "stage").locator(".dv-badge").count() == 1)
    add_property(page, "task", "Signed", "checkbox")
    check("columns: a new checkbox column draws boxes, not dashes", cell(page, "t1", "signed").locator(".dv-check").count() == 1, cell(page, "t1", "signed").inner_html())
    cell(page, "t1", "signed").click()
    settle(page)
    check("columns: a click ticks it", stored(page, "t1", "signed") is True and cell(page, "t1", "signed").locator(".dv-check.dv-on").count() == 1 and not editor_open(page))
    add_property(page, "task", "Site", "link")
    type_into(page, "t1", "site", "https://example.com/made-up")
    check("columns: a link draws a link", cell(page, "t1", "site").locator('a[href="https://example.com/made-up"]').count() == 1, cell(page, "t1", "site").inner_html())
    add_property(page, "task", "Shots", "media")
    type_into(page, "t1", "shots", "some words")
    check("columns: a media column draws its words", "some words" in drawn(page, "t1", "shots") and cell(page, "t1", "shots").get_attribute("class").find("dv-d-media") >= 0, drawn(page, "t1", "shots"))
    check("columns: the add row has a box for a new column", page.locator(f'{V} tr.dv-addrow [name="words"]').count() == 1)
    context.close()

    # ---- undo of an add, with a value in it; names that collide; a name left empty
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    add_property(page, "task", "Notes 2", "text")
    type_into(page, "t1", "notes_2", "kept")
    undo_key(page)
    undo_key(page)
    check("columns: undo of an add takes the column away, and the data is the fixture's", prop_keys(page) == list(DATA["properties"]) and stored_rows(page) == ROWS and "notes_2" not in heads(page), heads(page))
    redo_key(page)
    redo_key(page)
    check("columns: redo brings the column and its value back", stored(page, "t1", "notes_2") == "kept" and "notes_2" in heads(page), stored(page, "t1", "notes_2"))
    add_property(page, "task", "Owner", "text")
    check("columns: a name that is taken gets its own key", "owner_2" in heads(page) and head_text(page, "owner_2") == "Owner", heads(page)[:4])
    menu = col_menu(page, "task")
    menu.locator("[data-col-add]").click()
    menu.locator("[data-col-addform] button[type=submit]").click()
    settle(page)
    check("columns: an empty name adds nothing and says so", menu.locator("[data-col-addform]").count() == 1 and menu.locator("[data-col-msg]").inner_text() != "", menu.locator("[data-col-msg]").inner_text())
    page.keyboard.press("Escape")
    context.close()

    # ---- change type: no stored value moves; what does not fit is drawn as written; a cell of it survives being opened
    for col, kind in (("due", "number"), ("points", "text"), ("points", "date"), ("task", "number"), ("owner", "checkbox"), ("status", "text"), ("due", "link"), ("points", "media"), ("points", "checkbox")):
        context, page = sheet(browser, base, toggle=True, toolbar="bar")
        to_edit(page)
        retype(page, col, kind)
        check(f"columns: {col} to {kind} rewrites no stored value", stored_rows(page) == ROWS, kind)
        bad = [(r["id"], as_written(r[col]), drawn(page, r["id"], col)) for r in ROWS if r[col] is not None and drawn(page, r["id"], col) != as_written(r[col])]
        check(f"columns: {col} to {kind} draws every value as written", bad == [], bad[:3])
        context.close()
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    cell(page, "t4", "due").click()
    settle(page)
    check("columns: a value the column's own control cannot hold opens in a text box, as written", page.evaluate("document.activeElement.tagName") == "TEXTAREA" and page.evaluate("document.activeElement.value") == "soon", page.evaluate("document.activeElement.outerHTML.slice(0, 70)"))
    page.locator(f"{V} .dv-status").click()
    settle(page)
    check("columns: opened and left, it is still what it was", stored(page, "t4", "due") == "soon" and not editor_open(page), stored(page, "t4", "due"))
    retype(page, "due", "number")
    cell(page, "t4", "due").click()
    settle(page)
    check("columns: the same after a retype", page.evaluate("document.activeElement.value") == "soon")
    page.locator(f"{V} .dv-status").click()
    settle(page)
    check("columns: and left alone", stored_rows(page) == ROWS)
    cell(page, "t1", "due").click()
    settle(page)
    check("columns: a value the new type cannot read opens in a text box too", page.evaluate("document.activeElement.value") == BY_ID["t1"]["due"], page.evaluate("document.activeElement.value"))
    page.keyboard.press("Control+A")
    page.keyboard.type("42")
    page.keyboard.press("Enter")
    settle(page)
    check("columns: and what is typed there reads as the new type", stored(page, "t1", "due") == 42, stored(page, "t1", "due"))
    undo_key(page)
    undo_key(page)
    check("columns: undo of a retype restores the definition, to the key", definition(page, "due") == DATA["properties"]["due"] and stored_rows(page) == ROWS, definition(page, "due"))
    retype(page, "status", "text")
    check("columns: a column of choices retyped to text edits as text", definition(page, "status").get("constraints") is None)
    undo_key(page)
    check("columns: and its choices come back", definition(page, "status") == DATA["properties"]["status"])
    context.close()
    display = BASE_TEXT.replace("    addRow: true\n  - type: table\n    name: Todo", "    display: { points: bar }\n    addRow: true\n  - type: table\n    name: Todo", 1)
    context, page = sheet(browser, base, toggle=True, toolbar="bar", text=display)
    to_edit(page)
    retype(page, "points", "link")
    check("columns: a view's own display of a column gives way to its new type", cell(page, "t1", "points").locator(".dv-barfill").count() == 0, cell(page, "t1", "points").inner_html())
    undo_key(page)
    check("columns: and returns with undo", cell(page, "t1", "points").locator(".dv-barfill").count() == 1)
    context.close()

    # ---- a checkbox by keyboard: Tab stops on it in Edit, Space ticks, Enter commits
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    cell(page, "t1", "status").click()
    settle(page)
    page.keyboard.press("Tab")
    settle(page)
    check("columns: Tab stops on a checkbox cell, and does not flip it", page.evaluate("document.activeElement.type") == "checkbox" and stored(page, "t1", "shipped") is False, page.evaluate("document.activeElement.outerHTML.slice(0, 70)"))
    page.keyboard.press("Space")
    page.keyboard.press("Enter")
    settle(page)
    check("columns: Space and Enter tick it", stored(page, "t1", "shipped") is True, stored(page, "t1", "shipped"))
    context.close()

    # ---- hide
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    col_menu(page, "owner").locator("[data-col-hide]").click()
    settle(page)
    check("columns: Hide takes it out of this view", "owner" not in heads(page) and page.evaluate("document.querySelector('#sheet').view.order.includes('owner')") is False, heads(page))
    check("columns: and touches no data", stored_rows(page) == ROWS and "owner" in prop_keys(page))
    undo_key(page)
    check("columns: undo brings it back where it was", heads(page) == ORDER, heads(page))
    redo_key(page)
    page.locator(f'{V} .dv-tab[data-name="Todo"], {V} [data-bar=tab][data-name="Todo"]').first.click()
    settle(page)
    undo_key(page)
    check("columns: undo of a hide in another view says to go back to it, and stays", "Table" in toast(page).inner_text() and can(page)[0] is True, toast(page).inner_text() if toast(page).count() else None)
    context.close()

    # ---- delete: the column and its values; undoable, with a toast; the keys that named it
    sorted_base = BASE_TEXT.replace("    addRow: true\n  - type: table\n    name: Todo", "    sort: [{ property: points, direction: DESC }]\n    addRow: true\n  - type: table\n    name: Todo", 1)
    context, page = sheet(browser, base, toggle=True, toolbar="bar", text=sorted_base)
    to_edit(page)
    col_menu(page, "points").locator("[data-col-delete]").click()
    settle(page)
    check("columns: Delete takes the column away", "points" not in heads(page) and "points" not in prop_keys(page), heads(page))
    check("columns: and its values", all("points" not in r for r in stored_rows(page)))
    check("columns: every other cell is the fixture's", stored_rows(page) == [{k: v for k, v in r.items() if k != "points"} for r in ROWS])
    check("columns: a sort on it goes with it", page.evaluate("(document.querySelector('#sheet').view.sort || []).length") == 0)
    check("columns: a toast holds Undo", "points" in toast(page).inner_text().lower() and toast(page).locator("[data-toast-undo]").count() == 1, toast(page).inner_text())
    toast(page).locator("[data-toast-undo]").click()
    settle(page)
    check("columns: Undo restores the data, to the byte", stored_rows(page) == ROWS)
    check("columns: and the definition, in its place", definition(page, "points") == DATA["properties"]["points"] and prop_keys(page) == list(DATA["properties"]), prop_keys(page))
    check("columns: and the column, in its place, and its sort", heads(page) == ORDER and page.evaluate("document.querySelector('#sheet').view.sort[0].property") == "points", heads(page))
    redo_key(page)
    check("columns: redo deletes it again", "points" not in heads(page))
    undo_key(page)
    check("columns: and undo again restores it", stored_rows(page) == ROWS)
    context.close()

    # ---- what cannot be retyped or deleted
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    menu = col_menu(page, "ticket")
    check("columns: a read-only column cannot be retyped or deleted", menu.locator("[data-col-type]").is_disabled() and menu.locator("[data-col-delete]").is_disabled())
    check("columns: and says why", "read-only" in (menu.locator("[data-col-delete]").get_attribute("title") or ""), menu.locator("[data-col-delete]").get_attribute("title"))
    page.keyboard.press("Escape")
    menu = col_menu(page, "score")
    check("columns: nor a derived one", menu.locator("[data-col-type]").is_disabled() and menu.locator("[data-col-delete]").is_disabled())
    page.keyboard.press("Escape")
    menu = col_menu(page, "task")
    check("columns: the title column cannot be deleted", menu.locator("[data-col-delete]").is_disabled() and not menu.locator("[data-col-type]").is_disabled())
    page.keyboard.press("Escape")
    rename(page, "ticket", "Ticket no.")
    check("columns: a read-only column can still be renamed", head_text(page, "ticket") == "Ticket no.")
    for what, change in (("retype", "{ op: 'retype', property: 'ticket', kind: 'number' }"), ("delete", "{ op: 'delete', property: 'ticket' }"), ("delete the title", "{ op: 'delete', property: 'task' }"), ("an unknown kind", "{ op: 'retype', property: 'owner', kind: 'nope' }"), ("no such property", "{ op: 'rename', property: 'nope', label: 'x' }")):
        no = page.evaluate(f"() => document.querySelector('#sheet').editProperty({change})")
        check(f"columns: a script's {what} refuses", no["ok"] is False and no["reason"], no)
    context.close()

    # ---- the page's hook: what it hears; a refusal; undo through it with the old values
    hook = """v.acceptProperty = async (c) => { window.__log.push(JSON.parse(JSON.stringify(c))); if (window.__no) return { ok: false, reason: 'Ask the data team.' }; return { ok: true }; };"""
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=hook)
    to_edit(page)
    add_property(page, "owner", "Cost", "number")
    say = page.evaluate("window.__log[0]")
    check("columns: acceptProperty hears an add: key, name, kind, definition, where", say == {"op": "add", "property": "cost", "label": "Cost", "kind": "number", "definition": {"type": "number"}, "after": "owner"}, say)
    rename(page, "owner", "Lead")
    say = page.evaluate("window.__log[1]")
    check("columns: a rename: the name and what it was", say == {"op": "rename", "property": "owner", "label": "Lead", "from": "Owner"}, say)
    retype(page, "points", "text")
    say = page.evaluate("window.__log[2]")
    check("columns: a retype: the kind, the definition, the old one", say["op"] == "retype" and say["kind"] == "text" and say["definition"]["type"] == "text" and say["from"] == DATA["properties"]["points"], say)
    col_menu(page, "due").locator("[data-col-delete]").click()
    settle(page)
    say = page.evaluate("window.__log[3]")
    check("columns: a delete: the property", say == {"op": "delete", "property": "due"}, say)
    col_menu(page, "link").locator("[data-col-hide]").click()
    settle(page)
    check("columns: a hide is a view change: the hook hears nothing", len(page.evaluate("window.__log")) == 4, len(page.evaluate("window.__log")))
    page.locator(f"{V} .dv-status").click()
    undo_key(page)
    undo_key(page)
    say = page.evaluate("window.__log[4]")
    want = {r["id"]: r["due"] for r in ROWS}  # a stored null too: the row comes back to the byte
    check("columns: undo of a delete is restore: the definition, the name, every value", say["op"] == "restore" and say["property"] == "due" and say["definition"] == DATA["properties"]["due"] and say["label"] == "Due" and say["values"] == want, say)
    check("columns: and the column is back", "due" in heads(page) and stored(page, "t4", "due") == "soon")
    undo_key(page)
    say = page.evaluate("window.__log[5]")
    check("columns: undo of a retype goes through it with the old definition", say["op"] == "retype" and say["definition"] == DATA["properties"]["points"] and say["kind"] == "number", say)
    undo_key(page)
    say = page.evaluate("window.__log[6]")
    check("columns: undo of a rename goes through it with the old name", say == {"op": "rename", "property": "owner", "label": "Owner", "from": "Lead"}, say)
    undo_key(page)
    say = page.evaluate("window.__log[7]")
    check("columns: undo of an add is a delete through it", say == {"op": "delete", "property": "cost"}, say)
    context.close()

    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=hook + "window.__no = true;")
    to_edit(page)
    menu = col_menu(page, "owner")
    menu.locator("[data-col-name]").fill("Lead")
    page.keyboard.press("Enter")
    settle(page)
    check("columns: a refusal keeps the menu open, says why, and changes nothing", menu.locator("[data-col-msg]").inner_text() == "Ask the data team." and head_text(page, "owner") == "Owner" and menu.locator("[data-col-name]").input_value() == "Lead", menu.locator("[data-col-msg]").inner_text())
    check("columns: and leaves nothing to undo", can(page) == [False, False])
    page.keyboard.press("Escape")
    settle(page)
    context.close()
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=hook)
    to_edit(page)
    col_menu(page, "due").locator("[data-col-delete]").click()
    settle(page)
    page.evaluate("window.__no = true")
    undo_key(page)
    check("columns: a refused undo of a delete says why and stays on the stack", "Ask the data team." in toast(page).inner_text() and "due" not in heads(page) and can(page) == [True, False], can(page))
    context.close()

    # ---- persistView carries what the .base owns; the file's comments and other keys stay
    write = "v.persistView = async (w) => { window.__log.push(w); return { ok: true }; };"
    context, page = sheet(browser, base, toggle=True, toolbar="bar", setup=write)
    to_edit(page)
    rename(page, "owner", "Lead")
    page.wait_for_function("window.__log.length >= 1")
    text = page.evaluate("window.__log[window.__log.length - 1].text")
    doc = page.evaluate("(t) => kit.parseBase(t)", text)
    check("columns: with persistView the display name reaches the file's text", doc["properties"]["owner"]["displayName"] == "Lead", doc["properties"])
    check("columns: and the file's other lines stay", text.startswith("# A made-up launch checklist") and "data: rows.json" in text and [v["name"] for v in doc["views"]] == ["Table", "Todo", "Fixed size"], text[:60])
    rename(page, "points", "Story points")
    page.wait_for_function("window.__log.length >= 2")
    doc = page.evaluate("(t) => kit.parseBase(t)", page.evaluate("window.__log[window.__log.length - 1].text"))
    check("columns: a second name joins the first", doc["properties"]["owner"]["displayName"] == "Lead" and doc["properties"]["points"]["displayName"] == "Story points", doc["properties"])
    col_menu(page, "link").locator("[data-col-hide]").click()
    page.wait_for_function("window.__log.length >= 3")
    doc = page.evaluate("(t) => kit.parseBase(t)", page.evaluate("window.__log[window.__log.length - 1].text"))
    check("columns: Hide reaches the file as the view's order", "link" not in doc["views"][0]["order"] and "link" in doc["views"][1]["order"], doc["views"][0]["order"])
    page.locator(f"{V} .dv-status").click()
    undo_key(page)
    undo_key(page)
    # the two undos are one run of changes, so usually one write (persist batches 200 ms): wait for what they say, not for a count
    page.wait_for_function("window.__log.length >= 4 && !/Story points/.test(window.__log[window.__log.length - 1].text)")
    doc = page.evaluate("(t) => kit.parseBase(t)", page.evaluate("window.__log[window.__log.length - 1].text"))
    check("columns: an undo reaches the file too", "link" in doc["views"][0]["order"] and "points" not in doc["properties"], doc["properties"])
    context.close()

    # ---- View and `editable` alone
    context, page = sheet(browser, base, editable=True, toolbar="bar")
    page.evaluate("window.addEventListener('contextmenu', (e) => { window.__menu = e.defaultPrevented; })")
    page.locator(f'{V} thead th[data-col="owner"]').click(button="right")
    settle(page)
    check("columns: editable with no edit-toggle keeps the browser's right-click on a header", page.locator(f"{V} .dv-pop:not([hidden])").count() == 0 and page.evaluate("window.__menu") is False)
    done = page.evaluate("() => document.querySelector('#sheet').editProperty({ op: 'rename', property: 'owner', label: 'Lead' })")
    settle(page)
    check("columns: an editable page with no hook takes editProperty in memory from a script", done["ok"] is True and head_text(page, "owner") == "Lead", done)
    context.close()
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    no = page.evaluate("() => document.querySelector('#sheet').editProperty({ op: 'rename', property: 'owner', label: 'Lead' })")
    check("columns: in View editProperty refuses", no["ok"] is False and "View" in no["reason"], no)
    context.close()
    context, page = sheet(browser, base, toolbar="bar")
    no = page.evaluate("() => document.querySelector('#sheet').editProperty({ op: 'rename', property: 'owner', label: 'Lead' })")
    check("columns: a read-only page refuses", no["ok"] is False and "read-only" in no["reason"], no)
    context.close()

    # ---- phone width, both themes: the menu fits, the page does not scroll sideways, by touch; the words read
    for dark, name in ((False, "light"), (True, "dark")):
        context, page = sheet(browser, base, width=390, height=800, dark=dark, mobile=True, toggle=True, toolbar="bar")
        page.evaluate("document.querySelector('#sheet').editing = true")
        settle(page)
        button = page.locator(f'{V} thead th[data-col="task"] [data-col-menu]')
        check(f"columns {name}-390: with no hover the menu button shows", float(button.evaluate("e => getComputedStyle(e).opacity")) > 0.5)
        button.click()
        page.wait_for_selector(f"{V} .dv-pop.dv-colmenu:not([hidden])")
        box = page.locator(f"{V} .dv-pop.dv-colmenu").bounding_box()
        check(f"columns {name}-390: the menu fits the window", box["x"] >= 0 and box["x"] + box["width"] <= 390 and box["y"] + box["height"] <= 800, box)
        check(f"columns {name}-390: no sideways page scroll", over(page) <= 0, over(page))
        ratio = contrast(page, f"{V} .dv-pop.dv-colmenu [data-col-hide]")
        check(f"columns {name}-390: its words read", ratio >= 4.5, round(ratio, 2))
        context.close()


# ------------------------------------------------------------------ 7. where things are drawn: measured, not read from the DOM
# WHY its own section: 368 checks read stored values and text, and passed over a Task cell drawn 32 px to the right, on top of Owner. A
# pasted name was in the DOM and on nobody's screen. Text in the DOM proves nothing about what a reader sees.
LINE_UP = """() => {
  const heads = Object.fromEntries([...document.querySelectorAll('#sheet thead tr.dv-hleaf th[data-col]')].map((t) => [t.dataset.col, t.getBoundingClientRect()]));
  const off = [];
  for (const td of document.querySelectorAll('#sheet tbody tr[data-i] td[data-col]')) {
    const h = heads[td.dataset.col], b = td.getBoundingClientRect();
    if (h && (Math.abs(h.left - b.left) > 1 || Math.abs(h.right - b.right) > 1)) off.push([td.closest('tr').dataset.i, td.dataset.col, Math.round(b.left - h.left), Math.round(b.right - h.right)]);
  }
  return off;
}"""
# every cell of the first rows that is in the window answers for its own centre: nothing is drawn over it
ON_TOP = """() => {
  const box = document.querySelector('#sheet .dv-scroll').getBoundingClientRect();
  const hid = [];
  for (const td of document.querySelectorAll('#sheet tbody tr[data-i] td[data-col]')) {
    const b = td.getBoundingClientRect(), x = b.left + b.width / 2, y = b.top + b.height / 2;
    if (x < box.left || x > box.right || y < box.top || y > box.bottom || x > innerWidth || y > innerHeight) continue;
    const at = document.elementFromPoint(x, y);
    if (!at || !td.contains(at)) hid.push([td.closest('tr').dataset.i, td.dataset.col, at && (at.dataset.col || at.tagName)]);
  }
  return hid;
}"""
ADD_ROW_LINE_UP = """() => {
  const heads = [...document.querySelectorAll('#sheet thead tr.dv-hleaf th')];
  return [...document.querySelectorAll('#sheet tr.dv-addrow > td')].map((td, i) => Math.round(td.getBoundingClientRect().left - heads[i].getBoundingClientRect().left)).filter((d) => Math.abs(d) > 1);
}"""


@section
def surfaces(browser, base):
    for width, height, mobile in ((1280, 820, False), (390, 800, True)):
        for label, opts, edit in (
            ("View, selectable", {"toggle": True, "toolbar": "bar", "selectable": True}, False),
            ("Edit, selectable", {"toggle": True, "toolbar": "bar", "selectable": True}, True),
            ("Edit, no checkboxes", {"toggle": True, "toolbar": "bar"}, True),
            ("Edit, full toolbar", {"toggle": True, "toolbar": "full", "selectable": True}, True),
            ("editable alone, selectable", {"editable": True, "toolbar": "bar", "selectable": True}, False),
        ):
            context, page = sheet(browser, base, width=width, height=height, mobile=mobile, **opts)
            if edit:
                page.evaluate("document.querySelector('#sheet').editing = true")
                settle(page)
            name = f"surfaces {label} {width}"
            bad = page.evaluate(LINE_UP)
            check(f"{name}: every cell sits under its own header", bad == [], bad[:4])
            hid = page.evaluate(ON_TOP)
            check(f"{name}: nothing is drawn over a cell in the window", hid == [], hid[:4])
            if edit or opts.get("editable"):
                off = page.evaluate(ADD_ROW_LINE_UP)
                check(f"{name}: the add row's cells sit under the headers", off == [], off[:4])
            check(f"{name}: no sideways page scroll", over(page) <= 0, over(page))
            context.close()

    # the frozen first column, after a sideways scroll: still at the checkboxes' edge, over the cells that pass under it
    context, page = sheet(browser, base, width=700, height=700, toggle=True, toolbar="bar", selectable=True)
    page.evaluate("document.querySelector('#sheet').editing = true")
    settle(page)
    at = page.evaluate("""() => { const s = document.querySelector('#sheet .dv-scroll'); s.scrollLeft = 300; return new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => {
      const box = document.querySelector('#sheet tbody tr[data-id="t1"] td[data-col="task"]').getBoundingClientRect();
      const sel = document.querySelector('#sheet tbody tr[data-id="t1"] td.dv-selcol').getBoundingClientRect();
      r([Math.round(box.left - sel.right), s.scrollLeft]); }))); }""")
    check("surfaces: scrolled sideways in Edit, the frozen column stays against the checkboxes", at[1] > 0 and abs(at[0]) <= 1, at)
    context.close()

    # the editor over a frozen cell; Open inside its own cell; the menu button inside its header; the switch inside the bar
    context, page = sheet(browser, base, toggle=True, toolbar="bar", selectable=True)
    to_edit(page)
    td = cell(page, "t1", "task").bounding_box()
    cell(page, "t1", "task").click()
    settle(page)
    box = page.locator(f"{V} .dv-celledit").bounding_box()
    check("surfaces: the editor opens over a frozen cell, not beside it", abs(box["x"] - td["x"]) < 2 and abs(box["y"] - td["y"]) < 2, [round(box["x"] - td["x"]), round(box["y"] - td["y"])])
    page.keyboard.press("Escape")
    settle(page)
    cell(page, "t2", "task").hover()
    page.wait_for_timeout(120)
    td = cell(page, "t2", "task").bounding_box()
    opened = cell(page, "t2", "task").locator(".dv-row-open").bounding_box()
    check("surfaces: a row's Open sits inside its cell", opened["x"] >= td["x"] and opened["x"] + opened["width"] <= td["x"] + td["width"] + 1, [opened["x"], td["x"], td["width"]])
    page.locator(f'{V} thead th[data-col="points"]').hover()
    th = page.locator(f'{V} thead th[data-col="points"]').bounding_box()
    mark = page.locator(f'{V} thead th[data-col="points"] [data-col-menu]').bounding_box()
    check("surfaces: the column's menu button sits inside its header", mark["x"] >= th["x"] and mark["x"] + mark["width"] <= th["x"] + th["width"] and mark["y"] >= th["y"] and mark["y"] + mark["height"] <= th["y"] + th["height"] + 1, [mark, th])
    bar = page.evaluate("() => { const b = document.querySelector('#sheet .dv-bar'); return b.scrollWidth - b.clientWidth; }")
    check("surfaces: the bar holds the switch on one row", bar <= 1, bar)
    context.close()
    context, page = sheet(browser, base, width=390, height=800, mobile=True, toggle=True, toolbar="full")
    sw = switch(page).bounding_box()
    check("surfaces: at 390 px the full toolbar's switch is in the window", sw["x"] >= 0 and sw["x"] + sw["width"] <= 390, sw)
    context.close()


# ------------------------------------------------------------------ 8. start from nothing
BLANK = {"id": "blank-sheet", "title": "Blank", "titleProperty": "name", "properties": {"name": {"type": "text", "label": "Name"}}, "rows": []}
BLANK_TEXT = "views:\n  - type: table\n    name: Table\n    addRow: true\n"


def blank_sheet(browser, base, width=1280, height=820, dark=False, mobile=False, **opts):
    context, page = new_page(browser, base, width, height, dark, mobile)
    page.evaluate(MOUNT, [opts.get("text", BLANK_TEXT), opts.get("data", BLANK), opts])
    page.wait_for_selector(f"{V} .dv-view table", timeout=15000)
    settle(page)
    return context, page


def new_row(page, text, box="name"):
    """Type a row in with the real keyboard, in the add row's box; its id, read back by what was typed."""
    page.locator(f'{V} tr.dv-addrow [name="{box}"]').click()
    page.keyboard.type(text)
    page.keyboard.press("Enter")
    settle(page)
    return page.evaluate("([b, t]) => { const r = document.querySelector('#sheet').data.rows.find((x) => x[b] === t); return r ? r.id : null; }", [box, text])


def dead(page):
    return page.locator(f"{V} .dv-nocols").count() > 0 or "No columns" in page.locator(f"{V} .dv-view").inner_text()


@section
def blank(browser, base):
    # ---- an empty dataset, one Name column, and nothing dead about it, in View or in Edit
    context, page = blank_sheet(browser, base, toggle=True, toolbar="bar")
    check("blank: (it opens: one column, no rows)", heads(page) == ["name"] and page.evaluate("document.querySelector('#sheet').data.rows.length") == 0, heads(page))
    check("blank: View has no dead No columns state", not dead(page), page.locator(f"{V} .dv-view").inner_text()[:60])
    check("blank: the switch is there", switch(page).count() == 1)
    to_edit(page)
    check("blank: Edit has no dead state either", not dead(page))
    check("blank: Edit says what to do next", "row" in page.locator(f"{V} tbody .dv-empty").inner_text().lower() and "match" not in page.locator(f"{V} tbody .dv-empty").inner_text().lower(), page.locator(f"{V} tbody .dv-empty").inner_text())
    check("blank: the add row has its one box", page.locator(f'{V} tr.dv-addrow [name="name"]').count() == 1)

    # ---- rows typed in; a column of each type added by hand; a value in each
    first = new_row(page, "First thing")
    check("blank: a row typed in lands", stored(page, first, "name") == "First thing" and drawn(page, first, "name").startswith("First thing"), first)
    check("blank: the note about no rows goes", page.locator(f"{V} tbody .dv-empty").count() == 0)
    second = new_row(page, "Second thing")
    check("blank: the box is ready for the next one", page.evaluate("document.activeElement.name") == "name" and second is not None, page.evaluate("document.activeElement.name"))
    for name, kind, key in (("Stage", "select", "stage"), ("Cost", "number", "cost"), ("Due", "date", "due"), ("Signed", "checkbox", "signed"), ("Site", "link", "site"), ("Shots", "media", "shots"), ("Words", "text", "words")):
        add_property(page, "name", name, kind)
        check(f"blank: a {kind} column is added by hand", key in heads(page) and definition(page, key) is not None, heads(page))
    type_into(page, first, "stage", "alpha")
    cell(page, first, "cost").click()
    page.keyboard.type("12.5")
    page.keyboard.press("Enter")
    settle(page)
    cell(page, first, "due").click()
    page.locator(f'{V} .dv-celledit input[type="date"]').fill("2031-06-07")
    page.keyboard.press("Enter")
    settle(page)
    cell(page, first, "signed").click()
    settle(page)
    type_into(page, first, "site", "https://example.com/made-up")
    type_into(page, first, "shots", "some words")
    type_into(page, first, "words", "plain words")
    row = page.evaluate("(i) => JSON.parse(JSON.stringify(document.querySelector('#sheet').row(i)))", first)
    want = {"id": first, "name": "First thing", "stage": "alpha", "cost": 12.5, "due": "2031-06-07", "signed": True, "site": "https://example.com/made-up", "words": "plain words"}
    check("blank: every typed value lands as its column's type", {k: row.get(k) for k in want} == want and row["shots"]["value"] == "some words", row)

    # ---- the add row grows with the columns and files a whole row
    page.locator(f'{V} tr.dv-addrow [name="name"]').click()
    page.keyboard.type("Third thing")
    page.locator(f'{V} tr.dv-addrow [name="cost"]').click()
    page.keyboard.type("not yet known")
    page.locator(f'{V} tr.dv-addrow [name="stage"]').click()
    page.keyboard.type("beta")
    page.locator(f'{V} tr.dv-addrow [name="signed"]').click()
    page.locator(f"{V} tr.dv-addrow [data-add-go]").click()
    settle(page)
    third = page.evaluate("document.querySelector('#sheet').data.rows.find((r) => r.name === 'Third thing')")
    check("blank: the add row files every new column, a number that is not one as written", third and third["stage"] == "beta" and third["cost"] == "not yet known" and third["signed"] is True, third)

    # ---- the last visible column cannot be hidden; every row deleted is still a table
    for col in ("stage", "cost", "due", "signed", "site", "shots", "words"):
        col_menu(page, col).locator("[data-col-hide]").click()
        settle(page)
    check("blank: (only the Name column left)", heads(page) == ["name"], heads(page))
    menu = col_menu(page, "name")
    check("blank: the last column cannot be hidden", menu.locator("[data-col-hide]").is_disabled(), menu.locator("[data-col-hide]").get_attribute("title"))
    page.keyboard.press("Escape")
    no = page.evaluate("() => document.querySelector('#sheet').editProperty({ op: 'hide', property: 'name' })")
    check("blank: nor from a script", no["ok"] is False and no["reason"], no)
    for _ in range(7):
        undo_key(page)
    check("blank: the hidden columns come back with undo", len(heads(page)) == 8, heads(page))
    ids = [r["id"] for r in stored_rows(page)]
    page.evaluate("(l) => document.querySelector('#sheet').deleteRows(l)", ids)
    settle(page)
    check("blank: every row deleted, it is a live empty table", stored_rows(page) == [] and not dead(page) and page.locator(f"{V} tr.dv-addrow").count() == 1, len(stored_rows(page)))
    context.close()

    # ---- a block pasted into the add row of an empty table
    context, page = blank_sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    add_property(page, "name", "Cost", "number")
    block = [["Pasted one", "1"], ["Pasted two", "2.5"], ["Pasted three", "x"]]
    clip_block(page, block)
    page.locator(f'{V} tr.dv-addrow [name="name"]').click()
    paste(page)
    rows = stored_rows(page)
    check("blank: a block pasted into the add row becomes rows, in its order", [[r.get("name"), r.get("cost")] for r in rows] == [["Pasted one", 1], ["Pasted two", 2.5], ["Pasted three", "x"]], rows)
    check("blank: and leaves the box empty", page.locator(f'{V} tr.dv-addrow [name="name"]').input_value() == "")
    undo_key(page)
    check("blank: one undo takes them all", stored_rows(page) == [])
    context.close()

    # ---- no properties at all; a view whose columns are gone: a way forward from each
    context, page = blank_sheet(browser, base, toggle=True, toolbar="bar", data={"id": "none", "title": "Nothing", "properties": {}, "rows": []}, text="views:\n  - type: table\n    name: Table\n    addRow: true\n")
    to_edit(page)
    first_col = page.locator(f"{V} [data-col-first]")
    check("blank: with no column at all, Edit offers to add one", first_col.count() == 1 and not dead(page), page.locator(f"{V} .dv-view").inner_text()[:80])
    first_col.click()
    page.wait_for_selector(f"{V} .dv-pop.dv-colmenu:not([hidden]) [data-col-addform]")
    form = page.locator(f"{V} [data-col-addform]")
    form.locator('[name="name"]').fill("Name")
    form.locator("button[type=submit]").click()
    settle(page)
    check("blank: the first column stands, and names the records", heads(page) == ["name"] and page.evaluate("document.querySelector('#sheet').data.titleProperty") == "name", heads(page))
    one = new_row(page, "It works")
    check("blank: and takes a row", stored(page, one, "name") == "It works")
    context.close()
    gone = "views:\n  - type: table\n    name: Table\n    order: [left_long_ago]\n    addRow: true\n"
    context, page = blank_sheet(browser, base, toggle=True, toolbar="bar", text=gone)
    to_edit(page)
    check("blank: a view whose columns have gone says so, and offers a way on", page.locator(f"{V} [data-col-first]").count() == 1, page.locator(f"{V} .dv-view").inner_text()[:90])
    context.close()

    # ---- phone width, both themes
    for dark, name in ((False, "light"), (True, "dark")):
        context, page = blank_sheet(browser, base, width=390, height=800, dark=dark, mobile=True, toggle=True, toolbar="bar")
        page.evaluate("document.querySelector('#sheet').editing = true")
        settle(page)
        check(f"blank {name}-390: no sideways page scroll, and no dead state", over(page) <= 0 and not dead(page), over(page))
        ratio = contrast(page, f"{V} tbody .dv-empty")
        check(f"blank {name}-390: the words read", ratio >= 4.5, round(ratio, 2))
        context.close()


# ------------------------------------------------------------------ 9. filter by hand
def visible_ids(page):
    """The rows the table draws, in order (a row's id is on it wherever an opener or Edit is on)."""
    return page.evaluate("() => [...document.querySelectorAll('#sheet tbody tr[data-id]')].map((t) => t.dataset.id)")


def filter_panel(page):
    return page.locator(f"{V} .dv-pop.dv-colfilter:not([hidden])")


def open_by_toolbar(page, col):
    """The way that needs no header: the toolbar's Filter menu, in View and Edit."""
    page.locator(f"{V} [data-bar=menu][data-name=filter]:visible, {V} .dv-head [data-menu=filter]:visible").first.click()
    page.wait_for_selector(f"{V} [data-filter-by]")
    page.locator(f"{V} [data-filter-by]").select_option(col)
    page.wait_for_selector(f"{V} .dv-pop.dv-colfilter:not([hidden])")


def tick(page, value):
    filter_panel(page).locator(f'[data-filter-values] input[value="{value}"]').click()
    settle(page)


def pills(page):
    return page.locator(f"{V} .dv-pill-body").all_inner_texts()


def filter_json(page):
    return json.dumps(page.evaluate("() => document.querySelector('#sheet').filters ?? null"))


@section
def hand_filter(browser, base):
    # ---- in View, from a header's right-click: a choice list for a select; the one filter; pills
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    page.locator(f'{V} thead th[data-col="status"]').click(button="right")
    settle(page)
    panel = filter_panel(page)
    check("filter: in View a header's right-click opens the column's filter", panel.count() == 1)
    choices = panel.locator("[data-filter-values] input").evaluate_all("(l) => l.map((i) => i.value)")
    check("filter: a select is a choice list, in the data's own order", choices == DATA["properties"]["status"]["constraints"]["enum"], choices)
    check("filter: nothing else is offered for a choice but is-empty", panel.locator("[data-filter-min], [data-filter-text]").count() == 0 and panel.locator("[data-filter-empty]").count() == 1)
    tick(page, "todo")
    want = [r["id"] for r in ROWS if r["status"] == "todo"]
    check("filter: a tick narrows the rows", visible_ids(page) == want, visible_ids(page))
    check("filter: it is a pill under the bar, in plain words", len(pills(page)) == 1 and "Status" in pills(page)[0] and "todo" in pills(page)[0], pills(page))
    check("filter: it is the one filter state", 'status == \\"todo\\"' in filter_json(page), filter_json(page))
    check("filter: no second system: the filter's text is the kit's own query", "status" in page.evaluate("document.querySelector('#sheet').queryText"), page.evaluate("document.querySelector('#sheet').queryText"))
    tick(page, "doing")
    want = [r["id"] for r in ROWS if r["status"] in ("todo", "doing")]
    check("filter: a second tick widens it", visible_ids(page) == want and len(pills(page)) == 1, pills(page))
    page.keyboard.press("Escape")
    settle(page)
    page.locator(f"{V} .dv-pill-body").click()
    settle(page)
    ticked = filter_panel(page).locator("[data-filter-values] input:checked").evaluate_all("(l) => l.map((i) => i.value)")
    check("filter: a pill opens its column's control, showing what is set", sorted(ticked) == ["doing", "todo"], ticked)
    page.keyboard.press("Escape")
    page.locator(f"{V} .dv-pill-x").click()
    settle(page)
    check("filter: the pill's × clears it", len(visible_ids(page)) == len(ROWS) and filter_json(page) == "null", filter_json(page))
    context.close()

    # ---- the toolbar's way, in View: a range for a number, a text box for words, a date range, a checkbox, is-empty for any
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    open_by_toolbar(page, "points")
    panel = filter_panel(page)
    check("filter: a number is a range", panel.locator("[data-filter-min]").get_attribute("type") == "number" and panel.locator("[data-filter-max]").count() == 1 and panel.locator("[data-filter-values]").count() == 0)
    panel.locator("[data-filter-min]").fill("2")
    panel.locator("[data-filter-max]").fill("5")
    page.keyboard.press("Enter")
    settle(page)
    want = [r["id"] for r in ROWS if isinstance(r["points"], (int, float)) and 2 <= r["points"] <= 5]
    check("filter: the range narrows the rows", visible_ids(page) == want, visible_ids(page))
    check("filter: and reads as one pill", len(pills(page)) == 1 and "Points" in pills(page)[0], pills(page))
    page.evaluate("document.querySelector('#sheet').filters = undefined")
    settle(page)
    open_by_toolbar(page, "points")
    check("filter: el.filters is the only state: cleared there, the control is empty", filter_panel(page).locator("[data-filter-min]").input_value() == "")
    page.keyboard.press("Escape")
    settle(page)
    open_by_toolbar(page, "task")
    filter_panel(page).locator("[data-filter-text]").fill("the")
    page.keyboard.press("Enter")
    settle(page)
    want = [r["id"] for r in ROWS if "the" in r["task"].lower()]
    check("filter: words are a contains box", visible_ids(page) == want, visible_ids(page))
    page.evaluate("document.querySelector('#sheet').filters = undefined")
    settle(page)
    open_by_toolbar(page, "due")
    panel = filter_panel(page)
    check("filter: a date is a date range", panel.locator("[data-filter-min]").get_attribute("type") == "date")
    panel.locator("[data-filter-min]").fill("2031-03-04")
    panel.locator("[data-filter-max]").fill("2031-03-09")
    page.keyboard.press("Enter")
    settle(page)
    want = [r["id"] for r in ROWS if isinstance(r["due"], str) and "2031-03-04" <= r["due"] <= "2031-03-09"]
    check("filter: the dates narrow the rows", visible_ids(page) == want, visible_ids(page))
    page.evaluate("document.querySelector('#sheet').filters = undefined")
    settle(page)
    open_by_toolbar(page, "shipped")
    tick(page, "true")
    want = [r["id"] for r in ROWS if r["shipped"] is True]
    check("filter: a checkbox is checked or not", visible_ids(page) == want, visible_ids(page))
    tick(page, "true")
    tick(page, "false")
    want = [r["id"] for r in ROWS if r["shipped"] is False]
    check("filter: and not checked is not the same as empty", visible_ids(page) == want, visible_ids(page))
    page.keyboard.press("Escape")
    page.evaluate("document.querySelector('#sheet').filters = undefined")
    settle(page)
    for col in ("owner", "points", "due", "status", "shipped", "link", "notes"):
        open_by_toolbar(page, col)
        filter_panel(page).locator("[data-filter-empty]").click()
        settle(page)
        want = [r["id"] for r in ROWS if r[col] is None]
        check(f"filter: is-empty, on {col}", visible_ids(page) == want, visible_ids(page))
        if col == "owner":
            check("filter: is-empty reads as words in its pill", pills(page) == ["Owner is empty"], pills(page))
        page.keyboard.press("Escape")
        page.locator(f"{V} .dv-pill-x").click()
        settle(page)
    context.close()

    # ---- the full toolbar; a page with neither attribute keeps its menus
    context, page = sheet(browser, base, toggle=True, toolbar="full")
    open_by_toolbar(page, "owner")
    filter_panel(page).locator("[data-filter-text]").fill("ana")
    page.keyboard.press("Enter")
    settle(page)
    check("filter: the full toolbar's way too", visible_ids(page) == [r["id"] for r in ROWS if r["owner"] and "ana" in r["owner"].lower()], visible_ids(page))
    context.close()
    context, page = sheet(browser, base, toolbar="bar")
    page.evaluate("window.addEventListener('contextmenu', (e) => { window.__menu = e.defaultPrevented; })")
    page.locator(f'{V} thead th[data-col="status"]').click(button="right")
    settle(page)
    check("filter: a page with neither attribute keeps the browser's right-click on a header", filter_panel(page).count() == 0 and page.evaluate("window.__menu") is False)
    context.close()

    # ---- in Edit, from the column's menu; a new column and a new value in the choices at once
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    menu = col_menu(page, "owner")
    menu.locator("[data-col-filter]").click()
    settle(page)
    check("filter: the column's menu has Filter by this column", filter_panel(page).count() == 1 and filter_panel(page).locator("[data-filter-text]").count() == 1)
    page.keyboard.press("Escape")
    settle(page)
    add_property(page, "task", "Stage", "select")
    open_by_toolbar(page, "stage")
    check("filter: a column added a minute ago is in the toolbar's list", filter_panel(page).count() == 1, page.locator(f"{V} [data-filter-by] option").all_inner_texts() if page.locator(f"{V} [data-filter-by]").count() else None)
    check("filter: with no values yet its list is empty, and is-empty is there", filter_panel(page).locator("[data-filter-values] input").count() == 0 and filter_panel(page).locator("[data-filter-empty]").count() == 1)
    page.keyboard.press("Escape")
    type_into(page, "t1", "stage", "alpha")
    menu = col_menu(page, "stage")
    menu.locator("[data-col-filter]").click()
    settle(page)
    check("filter: a value typed a moment ago is a choice", filter_panel(page).locator("[data-filter-values] input").evaluate_all("(l) => l.map((i) => i.value)") == ["alpha"])
    tick(page, "alpha")
    check("filter: and filters", visible_ids(page) == ["t1"], visible_ids(page))
    page.keyboard.press("Escape")
    settle(page)
    page.locator(f"{V} .dv-pill-x").click()
    settle(page)
    type_into(page, "t2", "stage", "beta")
    page.locator(f'{V} thead th[data-col="stage"]').click(button="right")
    settle(page)
    page.keyboard.press("Escape")
    menu = col_menu(page, "stage")
    menu.locator("[data-col-filter]").click()
    settle(page)
    check("filter: the next value joins it at once", sorted(filter_panel(page).locator("[data-filter-values] input").evaluate_all("(l) => l.map((i) => i.value)")) == ["alpha", "beta"])
    page.keyboard.press("Escape")
    add_property(page, "task", "Cost", "number")
    open_by_toolbar(page, "cost")
    check("filter: a new number column gets the range", filter_panel(page).locator("[data-filter-min]").count() == 1)
    page.keyboard.press("Escape")
    context.close()

    # ---- a row edited out of the filter stays, as Notion's does, until the filter, the search or the view changes, or Refresh
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    page.evaluate("""() => document.querySelector('#sheet').setFacet('status', { values: ['todo'], match: 'equals' })""")
    settle(page)
    want = [r["id"] for r in ROWS if r["status"] == "todo"]
    check("filter: (a filter is on in Edit)", visible_ids(page) == want, visible_ids(page))
    cell(page, "t2", "status").click()
    settle(page)
    page.locator(f"{V} .dv-celledit select").select_option("done")
    settle(page)
    check("filter: a row edited out of the filter stays where it is", stored(page, "t2", "status") == "done" and visible_ids(page) == want, visible_ids(page))
    note = page.locator(f"{V} .dv-status").inner_text()
    check("filter: the status line says it no longer matches", "1" in note and "no longer match" in note, note)
    type_into(page, "t3", "owner", "!")
    check("filter: a later edit leaves it there", visible_ids(page) == want, visible_ids(page))
    page.locator(f"{V} .dv-status [data-rows-refresh]").click()
    settle(page)
    check("filter: Refresh applies the filter again", visible_ids(page) == [i for i in want if i != "t2"], visible_ids(page))
    check("filter: and the note goes", "no longer match" not in page.locator(f"{V} .dv-status").inner_text())
    context.close()
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    page.evaluate("""() => document.querySelector('#sheet').setFacet('status', { values: ['todo'], match: 'equals' })""")
    settle(page)
    cell(page, "t2", "status").click()
    settle(page)
    page.locator(f"{V} .dv-celledit select").select_option("done")
    settle(page)
    undo_key(page)
    check("filter: undo of that edit: it matches again, and the note goes", visible_ids(page) == want and "no longer match" not in page.locator(f"{V} .dv-status").inner_text(), page.locator(f"{V} .dv-status").inner_text())
    redo_key(page)
    page.evaluate("""() => document.querySelector('#sheet').setFacet('status', { values: ['todo', 'doing'], match: 'equals' })""")
    settle(page)
    check("filter: a change of the filter is a refresh", "t2" not in visible_ids(page), visible_ids(page))
    page.evaluate("""() => document.querySelector('#sheet').setFacet('status', { values: ['todo'], match: 'equals' })""")
    settle(page)
    page.locator(f'{V} tr.dv-addrow [name="task"]').click()
    page.keyboard.type("Added under a filter")
    page.locator(f"{V} tr.dv-addrow [data-add-go]").click()
    settle(page)
    added = page.evaluate("document.querySelector('#sheet').data.rows.find((r) => r.task === 'Added under a filter').id")
    check("filter: a row added under a filter it does not match stays too", added in visible_ids(page), visible_ids(page))
    to_edit(page)
    check("filter: leaving Edit refreshes: View shows what matches", added not in page.evaluate("() => document.querySelector('#sheet').model.rows.map((r) => r.id)"), page.evaluate("() => document.querySelector('#sheet').model.rows.length"))
    context.close()
    context, page = sheet(browser, base, editable=True, toolbar="bar")
    page.evaluate("""() => document.querySelector('#sheet').setFacet('status', { values: ['todo'], match: 'equals' })""")
    settle(page)
    cell(page, "t2", "status").click()
    settle(page)
    page.locator(f"{V} .dv-celledit select").select_option("done")
    settle(page)
    check("filter: editable with no edit-toggle stays §37: the row leaves at once", "t2" not in visible_ids(page), visible_ids(page))
    context.close()

    # ---- by keyboard alone; phone width, both themes
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    to_edit(page)
    page.locator(f'{V} thead th[data-col="owner"] [data-col-menu]').focus()
    page.keyboard.press("Enter")
    settle(page)
    page.locator(f"{V} .dv-pop.dv-colmenu [data-col-filter]").focus()
    page.keyboard.press("Enter")
    settle(page)
    check("filter: the keyboard reaches it, and lands in the control", page.evaluate("document.activeElement.hasAttribute('data-filter-text')"), page.evaluate("document.activeElement.outerHTML.slice(0, 70)"))
    page.keyboard.type("bo")
    page.keyboard.press("Enter")
    settle(page)
    check("filter: Enter applies it and closes", filter_panel(page).count() == 0 and visible_ids(page) == [r["id"] for r in ROWS if r["owner"] and "bo" in r["owner"].lower()], visible_ids(page))
    context.close()
    for dark, name in ((False, "light"), (True, "dark")):
        context, page = sheet(browser, base, width=390, height=800, dark=dark, mobile=True, toggle=True, toolbar="bar")
        page.evaluate("document.querySelector('#sheet').editing = true")
        settle(page)
        page.locator(f'{V} thead th[data-col="task"] [data-col-menu]').click()
        page.wait_for_selector(f"{V} .dv-pop.dv-colmenu:not([hidden])")
        page.locator(f"{V} .dv-pop.dv-colmenu [data-col-filter]").click()
        page.wait_for_selector(f"{V} .dv-pop.dv-colfilter:not([hidden])")
        box = filter_panel(page).bounding_box()
        check(f"filter {name}-390: the control fits the window", box["x"] >= 0 and box["x"] + box["width"] <= 390 and box["y"] + box["height"] <= 800, box)
        check(f"filter {name}-390: no sideways page scroll", over(page) <= 0, over(page))
        ratio = contrast(page, f"{V} .dv-pop.dv-colfilter [data-filter-clear]")
        check(f"filter {name}-390: its words read", ratio >= 4.5, round(ratio, 2))
        context.close()


# ------------------------------------------------------------------ 10. the page to play with: the gallery case, on the real site
CASE = "/dist/site/gallery/notion-table/"
X = "#example"


def case_page(browser, base, suffix="", width=1280, height=820, dark=False, mobile=False):
    context = browser.new_context(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light", has_touch=mobile, is_mobile=mobile)
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
    context.set_default_timeout(4000)
    page = context.new_page()
    page.goto(base + CASE + suffix)
    page.wait_for_selector(f"{X} .dv-view table", timeout=15000)
    settle(page)
    return context, page


def xcell(page, row, col):
    return page.locator(f'{X} tbody tr[data-id="{row}"] td[data-col="{col}"]')


def xread(page, row, col):
    return page.evaluate("([r, c]) => { const x = document.querySelector('#example').row(r); return x ? x[c] ?? null : '(no row)'; }", [row, col])


def xrows(page):
    return page.evaluate("() => JSON.parse(JSON.stringify(document.querySelector('#example').data.rows))")


def xheads(page):
    return page.evaluate("() => [...document.querySelectorAll('#example thead tr.dv-hleaf th[data-col]')].map((t) => t.dataset.col)")


def xtype(page, row, col, text):
    xcell(page, row, col).click()
    page.keyboard.press("End")
    page.keyboard.type(text)
    page.keyboard.press("Enter")
    settle(page)


def xreload(page, ready="tbody tr[data-i]"):
    page.wait_for_timeout(350)  # the page's snapshot waits for the run of changes to end
    page.reload()
    page.wait_for_selector(f"{X} {ready}", timeout=15000)
    settle(page)


def xmenu(page, col):
    page.locator(f'{X} thead th[data-col="{col}"]').hover()
    page.locator(f'{X} thead th[data-col="{col}"] [data-col-menu]').click()
    page.wait_for_selector(f"{X} .dv-pop.dv-colmenu:not([hidden])")
    return page.locator(f"{X} .dv-pop.dv-colmenu")


def xadd(page, after, name, kind):
    menu = xmenu(page, after)
    menu.locator("[data-col-add]").click()
    form = menu.locator("[data-col-addform]")
    form.locator('[name="name"]').fill(name)
    form.locator('[name="kind"]').select_option(kind)
    form.locator("button[type=submit]").click()
    settle(page)


@section
def gallery_case(browser, base):
    sample = json.loads((ROOT / "gallery" / "examples" / "notion-table" / "rows.json").read_text(encoding="utf-8"))
    rows, props = sample["rows"], sample["properties"]
    # ---- what it is: partly filled, labelled made-up, opening in Edit, one line of hint
    context, page = case_page(browser, base)
    check("case: a fresh viewer's page opens in Edit", page.evaluate("document.querySelector('#example').editing") is True and page.locator(f"{X} tr.dv-addrow").count() == 1)
    check("case: about eight rows", 6 <= len(rows) <= 10 and xrows(page) == rows, len(rows))
    kinds = {(p["type"], p.get("display")) for p in props.values()}
    check("case: five or six column types", 5 <= len(kinds) <= 6, sorted(map(str, kinds)))
    blank = sum(1 for r in rows for k in props if r.get(k) is None)
    check("case: some cells are blank on purpose", blank >= 6 and page.locator(f"{X} tbody td[data-col] .dv-nil, {X} tbody td[data-col] .dv-check:not(.dv-on)").count() >= blank - 1, blank)
    check("case: it says it is made up", "made-up" in sample["title"].lower() and "made up" in (ROOT / "gallery" / "examples" / "notion-table" / "README.md").read_text(encoding="utf-8"), sample["title"])
    hint = page.locator("[data-hint]")
    line = page.evaluate("() => { const e = document.querySelector('[data-hint]'); return [e.getBoundingClientRect().height, parseFloat(getComputedStyle(e).lineHeight) || 20]; }")
    check("case: a short hint, on one line", hint.count() == 1 and line[0] <= line[1] * 1.6, line)
    check("case: New blank table and Reset to the sample are there", page.locator("[data-new-blank]").count() == 1 and page.locator("[data-reset-sample]").count() == 1)
    check("case: nothing is stored until something changes", page.evaluate("localStorage.getItem('data-ui/notion-table/v1')") is None)

    # ---- a reload keeps what was typed, a column added, a rename, a filter and a deleted row
    xtype(page, "r3", "owner", "Mia")
    xreload(page)
    check("case: a reload keeps what was typed", xread(page, "r3", "owner") == "Mia" and xcell(page, "r3", "owner").inner_text().strip().startswith("Mia"), xread(page, "r3", "owner"))
    xadd(page, "owner", "Reviewed", "checkbox")
    xcell(page, "r1", "reviewed").click()
    settle(page)
    xreload(page)
    check("case: a reload keeps a new column, in its place, with its value and its type", xheads(page)[:4] == ["task", "status", "owner", "reviewed"] and xread(page, "r1", "reviewed") is True and xcell(page, "r1", "reviewed").locator(".dv-check.dv-on").count() == 1, xheads(page))
    menu = xmenu(page, "points")
    menu.locator("[data-col-name]").fill("Effort")
    page.keyboard.press("Enter")
    settle(page)
    xreload(page)
    check("case: a reload keeps a new name", page.locator(f'{X} thead th[data-col="points"] .dv-th').inner_text().strip() == "Effort")
    page.evaluate("() => document.querySelector('#example').deleteRows(['r8'])")
    settle(page)
    xreload(page)
    check("case: a reload keeps a deleted row gone", xread(page, "r8", "task") == "(no row)")
    menu = xmenu(page, "status")
    menu.locator("[data-col-filter]").click()
    page.wait_for_selector(f"{X} .dv-pop.dv-colfilter:not([hidden])")
    page.locator(f'{X} .dv-pop.dv-colfilter [data-filter-values] input[value="todo"]').click()
    settle(page)
    page.keyboard.press("Escape")
    xreload(page)
    shown = page.evaluate("() => document.querySelector('#example').model.rows.map((r) => r.id)")
    check("case: a reload keeps a filter by hand, and its pill", shown == [r["id"] for r in rows if r["status"] == "todo" and r["id"] != "r8"] and page.locator(f"{X} .dv-pill-body").count() == 1, shown)
    context.close()

    # ---- New blank table: scenario 1, on the real page; Reset to the sample
    context, page = case_page(browser, base)
    xtype(page, "r3", "owner", "Mia")
    page.wait_for_timeout(350)
    page.locator("[data-new-blank]").click()
    page.wait_for_selector(f'{X} thead th[data-col="name"]', timeout=15000)
    settle(page)
    check("case: New blank table: one Name column, no rows, in Edit", xheads(page) == ["name"] and xrows(page) == [] and page.evaluate("document.querySelector('#example').editing") is True, xheads(page))
    check("case: and nothing dead about it", "No columns" not in page.locator(f"{X} .dv-view").inner_text() and page.locator(f"{X} tr.dv-addrow").count() == 1)
    page.locator(f'{X} tr.dv-addrow [name="name"]').click()
    page.keyboard.type("My first row")
    page.keyboard.press("Enter")
    settle(page)
    xadd(page, "name", "Priority", "select")
    row = xrows(page)[0]["id"]
    xtype(page, row, "priority", "high")
    xreload(page, 'tbody tr[data-i]')
    check("case: a blank table built by hand survives a reload", [r["name"] for r in xrows(page)] == ["My first row"] and xrows(page)[0]["priority"] == "high" and xheads(page) == ["name", "priority"], xrows(page))
    page.locator("[data-reset-sample]").click()
    page.wait_for_selector(f'{X} tbody tr[data-id="r1"]', timeout=15000)
    settle(page)
    check("case: Reset to the sample brings it back, every cell", xrows(page) == rows and xheads(page) == list(props), xheads(page))
    check("case: and forgets what was kept", page.evaluate("localStorage.getItem('data-ui/notion-table/v1')") is None)
    context.close()

    # ---- the switch still works here; View is remembered; the link can say View
    context, page = case_page(browser, base)
    page.locator(f"{X} [data-edit-switch]:visible").click()
    settle(page)
    check("case: the switch turns it to View", page.evaluate("document.querySelector('#example').editing") is False and page.locator(f"{X} tr.dv-addrow").count() == 0)
    page.reload()
    page.wait_for_selector(f"{X} tbody tr[data-i]", timeout=15000)
    settle(page)
    check("case: a viewer who chose View comes back to View", page.evaluate("document.querySelector('#example').editing") is False)
    context.close()
    context, page = case_page(browser, base, suffix="#edit=0")
    check("case: a link with edit=0 opens in View", page.evaluate("document.querySelector('#example').editing") is False)
    context.close()

    # ---- phone width, both themes
    for dark, name in ((False, "light"), (True, "dark")):
        context, page = case_page(browser, base, width=390, height=800, dark=dark, mobile=True)
        check(f"case {name}-390: no sideways page scroll", over(page) <= 0, over(page))
        box = page.locator("[data-new-blank]").bounding_box()
        check(f"case {name}-390: the buttons are in the window", box["x"] >= 0 and box["x"] + box["width"] <= 390, box)
        ratio = contrast(page, "[data-hint]")
        check(f"case {name}-390: the hint reads", ratio >= 4.5, round(ratio, 2))
        context.close()


# ------------------------------------------------------------------ 11. what the first look at the real page found
SEL_WIDTH = """() => { const c = document.querySelector('#sheet thead th.dv-selcol, #example thead th.dv-selcol'); return c ? c.getBoundingClientRect().width : null; }"""
BOX_AND_WORD = """(sel) => { const l = document.querySelector(sel); const i = l.querySelector('input'); const r = document.createRange(); r.selectNodeContents(l); r.setStartAfter(i);
  const a = i.getBoundingClientRect(), b = r.getBoundingClientRect(); return { box: Math.round(a.width), gap: Math.round(b.left - a.right) }; }"""


@section
def looks(browser, base):
    # ---- the checkbox column is a checkbox wide, however few columns a table has
    for label, kwargs in (("a blank table", {"data": BLANK, "text": BLANK_TEXT}),):
        for edit in (False, True):
            context, page = blank_sheet(browser, base, toggle=True, toolbar="bar", selectable=True, **kwargs)
            if edit:
                to_edit(page)
            width = page.evaluate(SEL_WIDTH)
            mode = "Edit" if edit else "View"
            check(f"looks: {label} in {mode}: the checkbox column stays 32 px", abs(width - 32) <= 1, width)
            head = page.locator(f'{V} thead th[data-col="name"]').bounding_box()
            sel = page.locator(f"{V} thead th.dv-selcol").bounding_box()
            check(f"looks: {label} in {mode}: the first column starts where the checkboxes end", abs(head["x"] - (sel["x"] + sel["width"])) <= 1, [head["x"], sel["x"], sel["width"]])
            view = page.locator(f"{V} .dv-scroll").bounding_box()
            check(f"looks: {label} in {mode}: the table still fills its box", abs((head["x"] + head["width"]) - (view["x"] + view["width"])) <= 2, [head["x"] + head["width"], view["x"] + view["width"]])
            context.close()
    context, page = sheet(browser, base, toggle=True, toolbar="bar", selectable=True, text=BASE_TEXT.replace("    columnSize: { task: 200, owner: 96, ticket: 96, points: 80, due: 110, status: 90, shipped: 76, link: 170, notes: 220, score: 70 }\n", "", 1))
    width = page.evaluate(SEL_WIDTH)
    check("looks: a table with slack and no stored widths: the checkbox column stays 32 px", abs(width - 32) <= 1, width)
    bad = page.evaluate(LINE_UP)
    check("looks: and every cell stays under its header", bad == [], bad[:3])
    context.close()

    # ---- a choice in the filter is a box beside its word; the text boxes still fill their row
    context, page = sheet(browser, base, toggle=True, toolbar="bar")
    page.locator(f'{V} thead th[data-col="status"]').click(button="right")
    settle(page)
    got = page.evaluate(BOX_AND_WORD, f"{V} .dv-colfilter [data-filter-values] label")
    check("looks: a choice's box is a checkbox wide, with its word right beside it", got["box"] <= 20 and 0 <= got["gap"] <= 12, got)
    got = page.evaluate(BOX_AND_WORD, f"{V} .dv-colfilter label.dv-filter-empty")
    check("looks: and Is empty", got["box"] <= 20 and 0 <= got["gap"] <= 12, got)
    page.keyboard.press("Escape")
    to_edit(page)
    menu = col_menu(page, "owner")
    check("looks: the column menu's name box fills its row", menu.locator("[data-col-name]").bounding_box()["width"] >= 140, menu.locator("[data-col-name]").bounding_box()["width"])
    page.keyboard.press("Escape")
    page.locator(f'{V} thead th[data-col="points"]').click(button="right")
    settle(page)
    page.keyboard.press("Escape")
    context.close()


def main() -> int:
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + PAGE, timeout=1)
                break
            except OSError:
                time.sleep(0.05)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for run in SECTIONS:
                try:
                    run(browser, base)
                except Exception as err:  # a section that cannot finish is a failure, and the rest still run
                    check(f"{run.__name__}: ran to its end", False, repr(err)[:300])
                    for context in list(browser.contexts):
                        context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait()
    (OUT / "notion-table-checks.json").write_text(json.dumps(checks, indent=1), encoding="utf-8")
    bad = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(bad)}/{len(checks)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
