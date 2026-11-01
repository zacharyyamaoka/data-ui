"""Editing in the table, the add row, media cells and kept view changes (docs/CONTRACT.md §37), measured in headless Chromium on
the built kit.

    ~/psu-atlas/.venv/bin/python tests/browser/editable_cells_checks.py [OUT_DIR]     # after npm run build

Each check drives a real <data-views> with the real mouse and keyboard: click a cell, type, Enter; Esc; Tab; a refused edit; drag a
column edge and read getBoundingClientRect; drag a header onto another; reload and measure they stayed, through persist="local"
and through the page's persistView hook, whose text is parsed back; paste a file; a view switch. Serves the repo root on a free
127.0.0.1 port, stops that server when done, writes OUT_DIR/editable-cells-checks.json (default reports/media/editable-cells) and
exits 1 if any check fails.
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
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "editable-cells"
OUT.mkdir(parents=True, exist_ok=True)
PAGE = "/tests/browser/fixtures/editable-cells.html"
V = "#sheet"
checks: list[dict] = []

BASE = """
sharedColumns: true
properties:
  note: { displayName: Note }
views:
  - type: table
    name: Table
    order: [pol, note, owner, size, when]
    columnSize: { pol: 44, note: 260, owner: 120, size: 90, when: 110 }
    addRow: true
  - type: table
    name: Open
    filters: owner == "Ana"
    order: [pol, note, owner, size, when]
    columnSize: { pol: 44, note: 260, owner: 120, size: 90, when: 110 }
"""
DATA = {
    "id": "sheet", "title": "Sheet", "titleProperty": "note",
    "properties": {
        "pol": {"type": "text", "cycle": True, "constraints": {"enum": ["-", "+"]}},
        "note": {"type": "text", "display": "media"},
        "owner": {"type": "text"},
        "size": {"type": "number", "addRow": False},
        "when": {"type": "date", "readOnly": True},
    },
    "rows": [
        {"id": "a", "pol": "-", "note": {"value": "first words", "attachments": []}, "owner": "Ana", "size": 3, "when": "2026-10-01"},
        {"id": "b", "pol": "+", "note": {"value": "second", "attachments": [{"url": "data:image/gif;base64,R0lGODlhAQABAAAAACw=", "kind": "image", "name": "dot"}]}, "owner": "Bo", "size": 5, "when": "2026-10-02"},
        {"id": "c", "pol": "-", "note": {"value": "third", "attachments": []}, "owner": "Ana", "size": 8, "when": "2026-10-03"},
    ],
}

MOUNT = """async ([text, data, opts]) => {
  await customElements.whenDefined('data-views');
  const core = await import('/dist/data-ui.js');
  const v = document.createElement('data-views');
  v.id = 'sheet'; v.setAttribute('no-url', ''); v.setAttribute('editable', '');
  if (opts.persist) v.setAttribute('persist', 'local');
  if (opts.counts) v.setAttribute('view-counts', '');
  window.__writes = []; window.__adds = []; window.__files = [];
  const kept = sessionStorage.getItem('sheet-text');
  const doc = kept || text;
  if (opts.hook) v.persistView = async (w) => { window.__writes.push(w); sessionStorage.setItem('sheet-text', w.text); return { ok: true }; };
  if (opts.refuse) v.acceptEdit = async ({ set }) => ('owner' in set ? { ok: false, reason: 'Owners are set elsewhere.' } : { ok: false, reason: 'no' });
  if (opts.add) v.acceptAdd = async ({ set }) => { window.__adds.push(set); return { ok: true, id: 'n1' }; };
  if (opts.files) v.acceptFile = async ({ file }) => { window.__files.push(file.name); return { ok: true, attachment: { url: 'data:image/gif;base64,R0lGODlhAQABAAAAACw=', kind: 'image', name: file.name } }; };
  document.body.append(v);
  v.baseText = doc;
  v.base = core.parseBase(doc);
  v.data = JSON.parse(JSON.stringify(data));
}"""

SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def open_sheet(browser, base, width=1280, **opts):
    context = browser.new_context(viewport={"width": width, "height": 800})
    page = context.new_page()
    page.goto(base + PAGE)
    return context, page, lambda: mount(page, opts)


def mount(page, opts):
    page.evaluate(MOUNT, [BASE, DATA, opts])
    page.wait_for_selector(f"{V} tbody tr[data-i]", timeout=15000)
    page.evaluate(SETTLE)


def cell(page, row, col):
    return page.locator(f'{V} tbody tr[data-id="{row}"] td[data-col="{col}"]')


def text_of(page, row, col):
    return cell(page, row, col).inner_text().strip()


def rowvalue(page, row, col):
    return page.evaluate("([r, c]) => { const x = document.querySelector('#sheet').row(r)[c]; return x && typeof x === 'object' ? x.value : x; }", [row, col])


def width_of(page, col):
    return page.evaluate("(c) => document.querySelector(`#sheet thead th[data-col=\"${c}\"]`).getBoundingClientRect().width", col)


def heads(page):
    return page.evaluate("() => [...document.querySelectorAll('#sheet thead tr.dv-hleaf th[data-col]')].map((t) => t.dataset.col)")


def drag_edge(page, col, dx):
    box = page.locator(f'{V} thead th[data-col="{col}"] .dv-resize').bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx / 2, y, steps=4)
    page.mouse.move(x + dx, y, steps=4)
    page.mouse.up()
    page.evaluate(SETTLE)


def drag_head(page, col, onto):
    page.locator(f'{V} thead th[data-col="{col}"]').drag_to(page.locator(f'{V} thead th[data-col="{onto}"]'))
    page.evaluate(SETTLE)


def run(browser, base):
    # ---- editing: click, type, Enter; Esc; Tab; a locked cell; a refusal
    context, page, go = open_sheet(browser, base)
    go()
    cell(page, "a", "owner").click()
    page.keyboard.type("Noor")
    page.keyboard.press("Enter")
    page.evaluate(SETTLE)
    check("edit: click a text cell, type, Enter commits through propose and redraws it", text_of(page, "a", "owner") == "AnaNoor" and page.locator(f"{V} .dv-celledit").count() == 0, text_of(page, "a", "owner"))
    cell(page, "a", "owner").click()
    page.keyboard.type("nothing")
    page.keyboard.press("Escape")
    page.evaluate(SETTLE)
    check("edit: Esc cancels and leaves the value", rowvalue(page, "a", "owner") == "AnaNoor" and page.locator(f"{V} .dv-celledit").count() == 0)
    cell(page, "b", "note").click()
    page.keyboard.press("End")
    page.keyboard.type(" more")
    page.locator(f"{V} .dv-status").click()
    page.evaluate(SETTLE)
    check("edit: leaving a media cell commits its words and keeps its attachment", rowvalue(page, "b", "note") == "second more" and page.evaluate("document.querySelector('#sheet').row('b').note.attachments.length") == 1, rowvalue(page, "b", "note"))
    cell(page, "a", "owner").click()
    page.keyboard.press("Tab")
    page.evaluate(SETTLE)
    ed = page.evaluate("() => { const e = document.querySelector('#sheet .dv-celledit input, #sheet .dv-celledit textarea'); return e && e.name; }")
    check("edit: Tab moves to the next editable cell in the row", ed == "size", ed)
    page.keyboard.type("13")
    page.keyboard.press("Tab")
    page.evaluate(SETTLE)
    check("edit: a number commits as a number; Tab past the last editable cell wraps to the next row", rowvalue(page, "a", "size") == 13 and page.evaluate("document.activeElement.name") in ("note", "pol"), rowvalue(page, "a", "size"))
    page.keyboard.press("Escape")
    box = cell(page, "c", "note").bounding_box()
    cell(page, "c", "note").click()
    over = page.locator(f"{V} .dv-celledit").bounding_box()
    check("edit: the editor sits exactly over its cell", abs(over["x"] - box["x"]) < 2 and abs(over["y"] - box["y"]) < 2, [round(over["x"] - box["x"]), round(over["y"] - box["y"])])
    page.keyboard.press("Escape")
    cell(page, "a", "when").click()
    page.evaluate(SETTLE)
    check("edit: a readOnly cell opens no editor; its click opens the record", page.locator(f"{V} .dv-celledit").count() == 0 and page.locator(f"{V} .dv-peek:not([hidden])").count() == 1)
    page.keyboard.press("Escape")
    before = rowvalue(page, "a", "pol")
    cell(page, "a", "pol").click()
    page.evaluate(SETTLE)
    check("edit: a cycle column flips on a click, no editor", rowvalue(page, "a", "pol") != before and page.locator(f"{V} .dv-celledit").count() == 0, rowvalue(page, "a", "pol"))
    refused = page.evaluate("() => document.querySelector('#sheet').propose({ id: 'a', set: { when: '2026-01-01' } })")
    check("edit: a readOnly property still refuses at propose", refused["ok"] is False and "read-only" in refused["reason"], refused)
    typing = cell(page, "c", "owner")
    typing.click()
    page.keyboard.type("half a thou")
    page.evaluate("() => { const v = document.querySelector('#sheet'); v.data = JSON.parse(JSON.stringify(v.data)); }")
    page.evaluate(SETTLE)
    still = page.evaluate("() => [document.activeElement.value, document.querySelectorAll('#sheet .dv-celledit').length]")
    check("edit: new data arriving mid-word keeps the editor, what is typed and the focus", still == ["Anahalf a thou", 1], still)
    page.keyboard.press("Escape")
    context.close()

    context, page, go = open_sheet(browser, base, refuse=True)
    go()
    cell(page, "a", "owner").click()
    page.keyboard.type("x")
    page.keyboard.press("Enter")
    page.wait_for_selector(f"{V} .dv-celledit .dv-ed-msg:not(:empty)")
    msg = page.locator(f"{V} .dv-celledit .dv-ed-msg").inner_text()
    check("edit: a host's refusal keeps the editor, what was typed, and says why", msg == "Owners are set elsewhere." and page.evaluate("document.activeElement.value").endswith("x"), msg)
    page.keyboard.press("Escape")
    context.close()

    # ---- the add row and files through the page's hooks
    context, page, go = open_sheet(browser, base, add=True, files=True)
    go()
    box = page.locator(f'{V} tr.dv-addrow [name="note"]')
    box.click()
    page.keyboard.type("a new row")
    page.evaluate("""() => {
      const data = new DataTransfer(); data.items.add(new File([new Uint8Array(8)], 'shot.png', { type: 'image/png' }));
      document.querySelector('#sheet tr.dv-addrow [name="note"]').dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
    }""")
    page.wait_for_selector(f"{V} tr.dv-addrow .dv-ed-thumb")
    typed = page.evaluate("document.querySelector('#sheet tr.dv-addrow [name=\"note\"]').value")
    check("add: a pasted file goes to acceptFile and shows in the box, the words kept", page.evaluate("window.__files") == ["shot.png"] and typed == "a new row", typed)
    page.locator(f"{V} tr.dv-addrow [data-add-step]").click()
    page.evaluate("() => document.querySelector('#sheet tr.dv-addrow [name=\"owner\"]').focus()")
    page.keyboard.type("Lee")
    page.keyboard.press("Enter")
    page.evaluate("() => document.querySelector('#sheet tr.dv-addrow [data-add-go]').click()")
    page.wait_for_function("window.__adds.length === 1")
    add = page.evaluate("window.__adds[0]")
    check("add: the row files through acceptAdd with its cells", add.get("note", {}).get("value") == "a new row" and len(add["note"]["attachments"]) == 1 and add.get("pol") == "+" and add.get("owner") == "Lee", add)
    page.evaluate(SETTLE)
    check("add: a property with addRow: false has no cell in the add row", page.locator(f"{V} tr.dv-addrow [name=\"size\"]").count() == 0)
    check("add: the row clears after it is filed", page.evaluate("document.querySelector('#sheet tr.dv-addrow [name=\"note\"]').value") == "" and page.locator(f"{V} tr.dv-addrow .dv-ed-thumb").count() == 0)
    cell(page, "a", "note").click()
    page.evaluate("""() => {
      const data = new DataTransfer(); data.items.add(new File([new Uint8Array(8)], 'more.png', { type: 'image/png' }));
      document.activeElement.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
    }""")
    page.wait_for_selector(f"{V} .dv-celledit .dv-ed-thumb")
    page.keyboard.press("Enter")
    page.evaluate(SETTLE)
    check("media: a file pasted into a cell commits with the cell and draws a thumbnail", page.evaluate("document.querySelector('#sheet').row('a').note.attachments.length") == 1 and cell(page, "a", "note").locator(".dv-mc-thumb").count() == 1)
    cell(page, "a", "note").locator(".dv-mc-thumb").click()
    page.wait_for_selector("dialog.dv-mediabox[open]")
    check("media: a thumbnail opens large", page.locator("dialog.dv-mediabox img").count() == 1)
    page.keyboard.press("Escape")
    cell(page, "c", "note").hover()
    page.wait_for_timeout(120)
    add_btn = cell(page, "c", "note").locator(".dv-mc-add")
    check("media: the quiet add shows on hover", add_btn.inner_text() == "+ image or video" and float(add_btn.evaluate("e => getComputedStyle(e).opacity")) > 0.9)
    context.close()

    # ---- a record as a page (CONTRACT §38)
    context, page, go = open_sheet(browser, base, files=True)
    go()
    cell(page, "a", "owner").hover()
    row_open = cell(page, "a", "note").locator(".dv-row-open")
    cell(page, "a", "note").hover()
    row_open.click()
    page.wait_for_selector(f"{V} .dv-peek [data-page-sec='note']")
    short = page.locator(f"{V} .dv-peek table.dv-fields").bounding_box()
    sec = page.locator(f"{V} .dv-peek [data-page-sec='note']").bounding_box()
    peek = page.locator(f"{V} .dv-peek").bounding_box()
    check("page: Open on a row opens it; the short properties sit above the long one", short["y"] + short["height"] <= sec["y"] + 1, [short["y"], sec["y"]])
    check("page: a long property is a full-width section, not a field row", sec["width"] >= peek["width"] - 60 and page.locator(f"{V} .dv-peek table.dv-fields [data-p='note']").count() == 0, [sec["width"], peek["width"]])
    check("page: its heading is the property's name, larger than the small labels", page.locator(f"{V} .dv-peek h2.dv-page-h").inner_text() == "Note" and float(page.locator(f"{V} .dv-peek h2.dv-page-h").evaluate("e => parseFloat(getComputedStyle(e).fontSize)")) >= 16)
    area = page.locator(f"{V} .dv-peek [data-page-sec='note'] textarea")
    area.click()
    page.keyboard.press("End")
    page.keyboard.type(" and a page")
    page.keyboard.press("Enter")
    page.keyboard.type("line two")
    page.locator(f"{V} .dv-peek header").click()
    page.evaluate(SETTLE)
    check("page: the section is its own editor; leaving it commits, Enter is a new line", rowvalue(page, "a", "note") == "first words and a page\nline two", rowvalue(page, "a", "note"))
    check("page: the table shows the edit", "line two" in text_of(page, "a", "note"))
    area.click()
    page.keyboard.type("no")
    page.keyboard.press("Escape")
    page.evaluate(SETTLE)
    check("page: Esc puts back what the row says", rowvalue(page, "a", "note").endswith("line two") and not area.input_value().endswith("no"))
    context.close()

    # ---- kept: persist="local" over no-url; a real reload
    context, page, go = open_sheet(browser, base, persist=True)
    go()
    w0 = width_of(page, "owner")
    drag_edge(page, "owner", 80)
    w1 = width_of(page, "owner")
    check("resize: dragging a column edge widens it, measured", abs(w1 - w0 - 80) <= 2, [w0, w1])
    drag_head(page, "size", "owner")
    order = heads(page)
    check("reorder: a header dragged onto another moves there", order.index("size") < order.index("owner"), order)
    page.locator(f'{V} thead th[data-col="size"]').click(modifiers=["Shift"])
    page.evaluate(SETTLE)
    page.locator(f'{V} .dv-tab[data-name="Open"]').click()
    page.evaluate(SETTLE)
    check("views: a tab switches the view", page.locator(f"{V} tbody tr[data-i]").count() == 2, page.locator(f"{V} tbody tr[data-i]").count())
    page.locator(f'{V} .dv-tab[data-name="Table"]').click()
    page.wait_for_timeout(300)
    page.reload()
    mount(page, {"persist": True})
    check('persist="local": the width came back on reload', abs(width_of(page, "owner") - w1) <= 1, width_of(page, "owner"))
    check('persist="local": the order came back', heads(page) == order, heads(page))
    check('persist="local": the sort came back', page.evaluate("document.querySelector('#sheet').view.sort[0].property") == "size")
    page.locator(f'{V} .dv-tab[data-name="Open"]').click()
    page.wait_for_timeout(300)
    page.reload()
    mount(page, {"persist": True})
    check('persist="local": the view picked came back', page.evaluate("document.querySelector('#sheet').origin.name") == "Open")
    context.close()

    # ---- kept: the page's hook writes the file's text
    context, page, go = open_sheet(browser, base, hook=True, counts=True)
    go()
    tabs = page.locator(f"{V} .dv-tab").all_inner_texts()
    check("view-counts: each view tab says how many rows it has", tabs == ["Table 3", "Open 2"], tabs)
    drag_edge(page, "owner", 60)
    page.wait_for_function("window.__writes.length >= 1")
    w = page.evaluate("window.__writes[window.__writes.length - 1]")
    doc = page.evaluate("async (t) => (await import('/dist/data-ui.js')).parseBase(t)", w["text"])
    check("hook: a resize reaches persistView as the file's new text", doc["views"][0]["columnSize"]["owner"] == 180, doc["views"][0]["columnSize"])
    check("hook: sharedColumns carries the width into the other table view", doc["views"][1]["columnSize"]["owner"] == 180 and doc["views"][1]["filters"] == 'owner == "Ana"', doc["views"][1]["columnSize"])
    check("hook: the file's other keys stay", doc["sharedColumns"] is True and doc["properties"]["note"]["displayName"] == "Note")
    drag_head(page, "size", "owner")
    page.locator(f'{V} .dv-tab[data-name="Open"]').click()
    page.wait_for_function("window.__writes.some((w) => /defaultView: Open/.test(w.text))")
    order = heads(page)
    width = width_of(page, "owner")
    page.reload()
    mount(page, {"hook": True, "counts": True})
    check("hook: the view picked came back from the text", page.evaluate("document.querySelector('#sheet').origin.name") == "Open")
    check("hook: width and order came back from the text", abs(width_of(page, "owner") - width) <= 1 and heads(page) == order, [width_of(page, "owner"), heads(page)])
    check("hook: nothing dirty after a write: no Reset or Save view", page.locator(f"{V} .dv-dirty").is_hidden())
    text = page.evaluate("document.querySelector('#sheet').baseText").replace("owner: 180", "owner: 222").replace("defaultView: Open\n", "defaultView: Table\n")
    page.evaluate("async (t) => { const v = document.querySelector('#sheet'); v.baseText = t; v.base = (await import('/dist/data-ui.js')).parseBase(t); }", text)
    page.evaluate(SETTLE)
    check("hook: a hand edit of the text shows: its width and its default view", page.evaluate("document.querySelector('#sheet').origin.name") == "Table" and abs(width_of(page, "owner") - 222) <= 1, width_of(page, "owner"))
    page.wait_for_timeout(350)
    check("hook: taking in a hand edit writes nothing back", all("222" not in x["text"] for x in page.evaluate("window.__writes")))
    context.close()

    # ---- a read-only page stays as it was
    context, page, _ = open_sheet(browser, base)
    page.evaluate("""async ([text, data]) => {
      const core = await import('/dist/data-ui.js');
      const v = document.createElement('data-views');
      v.id = 'sheet'; v.setAttribute('no-url', '');
      document.body.append(v); v.base = core.parseBase(text); v.data = data;
    }""", [BASE, DATA])
    page.wait_for_selector(f"{V} tbody tr[data-i]")
    page.evaluate(SETTLE)
    page.locator(f"{V} tbody tr[data-i]").nth(0).locator("td").nth(2).click()
    page.evaluate(SETTLE)
    check("read-only page: no add row, a click opens the record, no editor", page.locator(f"{V} tr.dv-addrow").count() == 0 and page.locator(f"{V} .dv-celledit").count() == 0 and page.locator(f"{V} .dv-peek:not([hidden])").count() == 1)
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
            run(browser, base)
            browser.close()
    finally:
        server.terminate()
        server.wait()
    (OUT / "editable-cells-checks.json").write_text(json.dumps(checks, indent=1), encoding="utf-8")
    bad = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(bad)}/{len(checks)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
