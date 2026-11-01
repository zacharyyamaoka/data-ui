"""Notes as a table and as pages (docs/CONTRACT.md §46), measured in headless Chromium on the built kit against tools/serve-md.mjs.

    ~/psu-atlas/.venv/bin/python tests/browser/md_pages_checks.py [OUT_DIR]     # after npm run build

Each check drives the real server over a copy of gallery/md-pages in a temp folder, with the real mouse and keyboard, and reads the
result from the files on disk, never back from the kit. Starts the server on a free port from 4531 up, records its pid, stops it when
done, writes OUT_DIR/md-pages-checks.json (default reports/media/md-pages) and exits 1 if any check fails.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASE = ROOT / "gallery" / "md-pages"
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "md-pages"
OUT.mkdir(parents=True, exist_ok=True)
V = "#notes"
checks: list[dict] = []
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000" "1f15c4890000000d49444154789c6360f8cfc0f01f0005000204" "fda1a03a0000000049454e44ae426082")


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("ok  " if ok else "FAIL"), name, "" if value is None else value, flush=True)


def free_port():
    for port in range(4531, 4600):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit("no free port from 4531")


def digests(folder):
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(folder.glob("*.md"))}


def rect(page, sel):
    return page.evaluate("(s) => { const r = document.querySelector(s).getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; }", sel)


def grow(page):
    """The old way, kept as an option: a markdown cell grows in place (el.cellSurface = 'grow'). The Sheet is the default (docs/CONTRACT.md §46)."""
    page.evaluate("() => { document.querySelector('#notes').cellSurface = 'grow'; }")


def blocks(page):
    return page.evaluate(f"[...document.querySelectorAll('{V} .dv-peek [data-page-block]:not([data-page-free])')].map((n) => n.dataset.pageBlock)")


def open_row(page, row_id):
    page.locator(f'{V} tr.dv-row[data-id="{row_id}"]').first.locator(".dv-row-open").evaluate("(b) => b.click()")
    page.wait_for_selector(f'{V} .dv-peek .dv-open-rec[data-id="{row_id}"] .dv-page-blocks', timeout=8000)


def menu(page, property_id, place):
    """Open the property's menu and pick a place: the preview's text."""
    entry = page.locator(f'{V} .dv-peek [data-page-entry="{property_id}"]')
    entry.hover()
    entry.locator("[data-page-menu]").first.click()
    page.locator(f'{V} .dv-pop [data-place-to="{place}"]').click()
    page.wait_for_selector(f"{V} .dv-pop [data-place-note]", timeout=5000)
    return page.locator(f"{V} .dv-pop [data-place-note]").inner_text()


def run(page, url, tmp):
    fb = tmp / "feedback"
    row = "fb-f8f638df"
    note = fb / f"{row}.md"
    n_notes = len(list(fb.glob("*.md")))
    page.goto(f"{url}/?db=feedback")
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)

    # ---- the table: a section column shows its first lines, and takes an edit
    cell = page.locator(f'{V} tr.dv-row[data-id="fb-7c321202"] td[data-col="desired"]').first
    text = cell.inner_text()
    first = (fb / "fb-7c321202.md").read_text(encoding="utf-8").split("# Desired\n\n", 1)[1].split("\n")
    check("table: a section column shows the section's first lines, line for line", text.split("\n")[0].strip() == first[0] and first[1].strip()[:30] in text, text[:80])
    check("table: a cell of a long section is taller than one line", cell.bounding_box()["height"] > 40, cell.bounding_box()["height"])
    thumbs = page.evaluate(f"[...document.querySelectorAll('{V} tr.dv-row[data-id=\"{row}\"] td[data-col=\"observed\"] .dv-sec-thumbs img')].map((i) => i.complete && i.naturalWidth > 0)")
    check("table: a section's picture is a thumbnail, loaded, when the row has room", thumbs == [True], thumbs)

    edit_row = fb / "fb-15f0ae2f.md"
    before_edit = edit_row.read_text(encoding="utf-8")
    grow(page)
    page.locator(f'{V} tr.dv-row[data-id="fb-15f0ae2f"] td[data-col="desired"]').first.click()
    box = page.locator(f"{V} .dv-celledit textarea").first
    box.wait_for(timeout=4000)
    page.keyboard.type("Typed in the table cell")
    page.keyboard.press("Enter")
    page.wait_for_timeout(350)
    after_edit = edit_row.read_text(encoding="utf-8")
    check("table: editing a section's cell writes that section and no other byte", after_edit == before_edit.rstrip("\n") + "\n\nTyped in the table cell\n" or after_edit == before_edit + "\nTyped in the table cell\n", after_edit[-70:])

    # ---- the add row files a note
    n_before = len(list(fb.glob("*.md")))
    add = page.locator(f'{V} tr.dv-addrow [data-add-col="observed"] textarea').first
    add.click()
    page.keyboard.type("Added from the table")
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    for _ in range(4):
        if len(list(fb.glob("*.md"))) > n_before:
            break
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
    added = [f for f in fb.glob("*.md") if f.name.startswith("Added from")]
    check("add row: a new row is a new note, its words under their heading", len(added) == 1 and "# Observed\n\nAdded from the table" in added[0].read_text(encoding="utf-8"), [f.name for f in added])
    for f in added:
        f.unlink()
    page.wait_for_function(f"document.querySelectorAll('{V} tr.dv-row').length === {n_notes}", timeout=4000)

    # ---- sort, group, resize and reorder keep working on a section column
    head = page.locator(f'{V} th[data-col="observed"]').first
    head.click()
    page.wait_for_timeout(150)
    head.click()
    page.wait_for_timeout(250)
    firsts = page.evaluate(f"[...document.querySelectorAll('{V} tr.dv-row td[data-col=\"observed\"]')].map((c) => c.innerText).slice(0, 3)")
    check("table: a section column sorts by its words", any(firsts) and firsts[0] not in ("—", ""), firsts)
    w0 = page.evaluate(f"document.querySelector('{V} th[data-col=\"observed\"]').getBoundingClientRect().width")
    edge = page.locator(f'{V} th[data-col="observed"] .dv-resize, {V} th[data-col="observed"] [class*=resize]').first
    b = edge.bounding_box()
    page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    page.mouse.down()
    page.mouse.move(b["x"] + 60, b["y"] + 4, steps=4)
    page.mouse.up()
    page.wait_for_timeout(250)
    w1 = page.evaluate(f"document.querySelector('{V} th[data-col=\"observed\"]').getBoundingClientRect().width")
    check("table: a section column resizes by the pointer's distance", abs((w1 - w0) - 60) < 6, [w0, w1])
    base_text = (fb / "views.base").read_text(encoding="utf-8")
    check("table: the width lands in the .base", re.search(r"observed: 3[5-6]\d", base_text) is not None, re.findall(r"columnSize:.*", base_text)[0][:80])
    page.locator(f"{V} [data-view-tab], {V} button", has_text="By track").first.click()
    page.wait_for_selector(f"{V} tr.dv-group, {V} tr[class*=group]", timeout=5000)
    check("table: grouped, the same notes are all there", page.locator(f"{V} tr.dv-row").count() == n_notes, page.locator(f"{V} tr.dv-row").count())
    page.locator(f"{V} button", has_text="Table").first.click()
    page.wait_for_selector(f'{V} tr.dv-row[data-id="{row}"]', timeout=5000)

    # ---- the page: title, properties, blocks, the free text last
    open_row(page, row)
    page.wait_for_timeout(400)
    title = rect(page, f"{V} .dv-peek header h2")
    props = rect(page, f"{V} .dv-peek .dv-page-props")
    blk = rect(page, f"{V} .dv-peek .dv-page-blocks")
    free = rect(page, f"{V} .dv-peek [data-page-free]")
    check("page: title, properties, blocks, free text, top to bottom", title["y"] < props["y"] < blk["y"] < free["y"], [title["y"], props["y"], blk["y"], free["y"]])
    check("page: no comments on it", page.locator(f"{V} .dv-peek").get_by_text("Comments").count() == 0)
    check("page: a section's picture is drawn and loaded", page.evaluate(f"[...document.querySelectorAll('{V} .dv-peek .dv-page-block img')].every((i) => i.complete && i.naturalWidth > 0) && document.querySelectorAll('{V} .dv-peek .dv-page-block img').length === 3"))
    order_page = page.evaluate(f"[...document.querySelectorAll('{V} .dv-peek .dv-page-prop[data-page-entry]')].map((n) => n.dataset.pageEntry)")
    order_table = page.evaluate(f"[...document.querySelectorAll('{V} th[data-col]')].map((n) => n.dataset.col)")
    check("page: its property order is its own, not the table's", order_page[:3] == ["status", "track", "filed"] and order_table.index("track") < order_table.index("status"), [order_page, order_table])

    # ---- the free text
    page.locator(f"{V} .dv-peek [data-page-free] [data-page-read]").click(position={"x": 40, "y": 8})
    ta = page.locator(f"{V} .dv-peek [data-page-free] textarea")
    ta.wait_for(timeout=3000)
    page.keyboard.type("Free text on the page")
    page.locator(f"{V} .dv-peek header h2").click()
    page.wait_for_timeout(400)
    text = note.read_text(encoding="utf-8")
    check("page: the free text lands before the first heading", text.index("Free text on the page") < text.index("# Observed") and text.index("Free text on the page") > text.index("---\n", 4), text[150:230])
    check("page: the free text stays last on the page", rect(page, f"{V} .dv-peek [data-page-free]")["y"] > rect(page, f"{V} .dv-peek .dv-page-blocks")["y"])

    # ---- writing in a block
    page.locator(f'{V} .dv-peek [data-page-block="desired"] [data-page-read]').click(position={"x": 30, "y": 8})
    ta = page.locator(f'{V} .dv-peek [data-page-block="desired"] textarea')
    ta.wait_for(timeout=3000)
    held = digests(fb)
    ta.press("Control+End")
    page.keyboard.type("\n\nA line written on the page")
    other = page.locator(f"{V} .dv-peek header h2")
    other.click()
    page.wait_for_timeout(450)
    now = digests(fb)
    check("page: leaving a block saves it, in that one file", [k for k in now if now[k] != held[k]] == [note.name], [k for k in now if now[k] != held[k]])
    check("page: the block's words are at the end of its section", note.read_text(encoding="utf-8").endswith("A line written on the page\n"))
    check("page: the block draws as markdown again", page.locator(f'{V} .dv-peek [data-page-block="desired"] textarea').count() == 0 and "A line written on the page" in page.locator(f'{V} .dv-peek [data-page-block="desired"]').inner_text())

    # ---- a picture pasted into a block
    page.locator(f'{V} .dv-peek [data-page-block="observed"] [data-page-read]').click(position={"x": 40, "y": 6})
    ta = page.locator(f'{V} .dv-peek [data-page-block="observed"] textarea')
    ta.wait_for(timeout=3000)
    page.evaluate("""([b, sel]) => { const bytes = Uint8Array.from(b); const file = new File([bytes], 'pasted shot.png', { type: 'image/png' }); const dt = new DataTransfer(); dt.items.add(file);
      document.querySelector(sel).dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); }""", [list(PNG), f'{V} .dv-peek [data-page-block="observed"] textarea'])
    page.wait_for_function(f"document.querySelector('{V} .dv-peek [data-page-block=\"observed\"] textarea').value.includes('pasted-shot-')", timeout=5000)
    saved = [f for f in (fb / "attachments").iterdir() if f.name.startswith("pasted-shot-")]
    check("page: a pasted picture lands in attachments/, and its link in the block", len(saved) == 1 and saved[0].read_bytes() == PNG, [f.name for f in saved])
    other = page.locator(f"{V} .dv-peek header h2")
    other.click()
    page.wait_for_timeout(450)
    check("page: the file links it as plain markdown", f"(attachments/{saved[0].name})" in note.read_text(encoding="utf-8"))

    # ---- a property's place: preview, cancel, apply, the file changes
    held = digests(fb)
    # text property with data in every file: Copied from, hidden on the page; shown first
    page.locator(f"{V} .dv-peek [data-page-hidden]").click()
    page.wait_for_selector(f'{V} .dv-peek .dv-page-off[data-page-entry="copied_from"]', timeout=3000)
    preview = menu(page, "copied_from", "section")
    check("place: the preview says how many files change, before any does", re.search(rf"in {n_notes} of {n_notes} files", preview) is not None and digests(fb) == held, preview)
    page.locator(f"{V} .dv-pop [data-place-no]").click()
    page.wait_for_timeout(150)
    check("place: Cancel writes nothing", digests(fb) == held)
    menu(page, "copied_from", "section")
    t0 = time.time()
    page.locator(f"{V} .dv-pop [data-place-go]").click()
    page.wait_for_selector(f'{V} .dv-peek [data-page-block="copied_from"]', timeout=6000)
    took = time.time() - t0
    text = note.read_text(encoding="utf-8")
    front = text.split("---")[1]
    check("place: the value left the frontmatter and is a heading in the file", "copied_from" not in front and "# Copied from\n\nfeedback/data-ui.csv" in text, text[:220])
    moved = [k for k, v in digests(fb).items() if v != held[k]]
    check("place: every row's file changed, no other", len(moved) == n_notes, len(moved))
    check("place: the .base says so", "{ property: copied_from, place: section }" in (fb / "views.base").read_text(encoding="utf-8"))
    check("place: done in under 2 s for the folder", took < 2, round(took, 3))
    held = digests(fb)
    menu(page, "copied_from", "top")
    page.locator(f"{V} .dv-pop [data-place-go]").click()
    page.wait_for_selector(f'{V} .dv-peek .dv-page-prop[data-page-entry="copied_from"]', timeout=6000)
    check("place: back in the list, back in the frontmatter", "copied_from: feedback/data-ui.csv" in note.read_text(encoding="utf-8") and "# Copied from" not in note.read_text(encoding="utf-8"))

    # ---- a type that does not fit
    held = digests(fb)
    preview = menu(page, "status", "section")
    check("type: a select as a heading says it stays in the frontmatter, 0 files", "stays in the frontmatter" in preview and "0 files change" in preview, preview)
    page.locator(f"{V} .dv-pop [data-place-go]").click()
    page.wait_for_selector(f'{V} .dv-peek [data-page-block="status"]', timeout=5000)
    check("type: the page draws it as a heading, no file changed", digests(fb) == held)
    sel = page.locator(f'{V} .dv-peek [data-page-block="status"] [data-page-read]').count()
    check("type: it is no place to write: no words box", sel == 0)
    menu(page, "status", "top")
    page.locator(f"{V} .dv-pop [data-place-go]").click()
    page.wait_for_selector(f'{V} .dv-peek .dv-page-prop[data-page-entry="status"]', timeout=5000)

    # ---- reordering blocks: drag and keyboard; the layout's, no note changes
    held = digests(fb)
    page.on("dialog", lambda d: d.dismiss())
    was = blocks(page)
    grip = page.locator(f'{V} .dv-peek [data-page-block="{was[-1]}"] [data-page-grip]')
    page.locator(f'{V} .dv-peek [data-page-block="{was[-1]}"] .dv-page-head').hover()
    g = grip.bounding_box()
    top = page.locator(f'{V} .dv-peek [data-page-block="{was[0]}"]').bounding_box()
    page.mouse.move(g["x"] + g["width"] / 2, g["y"] + g["height"] / 2)
    page.mouse.down()
    page.mouse.move(g["x"] + 2, top["y"] + 40, steps=6)
    page.mouse.move(g["x"] + 2, top["y"] + 4, steps=3)
    page.mouse.up()
    page.wait_for_timeout(350)
    now = blocks(page)
    check("blocks: dragging the last above the first reorders them", now == [was[-1], *was[:-1]], now)
    base_text = (fb / "views.base").read_text(encoding="utf-8")
    check("blocks: the order is in the .base", base_text.index("property: desired") < base_text.index("property: observed"))
    check("blocks: no note changed", digests(fb) == held)
    page.locator(f'{V} .dv-peek [data-page-block="{now[0]}"] [data-page-grip]').focus()
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(250)
    check("blocks: the keyboard moves one too", blocks(page) == [now[1], now[0], *now[2:]], blocks(page))
    check("blocks: the focus stays on it", page.evaluate(f"document.activeElement.closest('[data-page-block]')?.dataset.pageBlock") == now[0])
    page.keyboard.press("ArrowUp")
    page.wait_for_timeout(250)
    check("blocks: the keyboard moves it back; the record did not step", blocks(page) == now and page.locator(f'{V} .dv-open-rec[data-id="{row}"]').count() == 1)
    page.reload()
    page.wait_for_selector(f'{V} .dv-peek .dv-open-rec[data-id="{row}"] .dv-page-blocks', timeout=8000)
    check("blocks: a reload keeps the order", blocks(page) == now, blocks(page))

    # ---- a hand edit reaches the page
    text = note.read_text(encoding="utf-8")
    t0 = time.time()
    note.write_text(text.replace("Desired is notions", "EDITED BY HAND Desired is notions"), encoding="utf-8")
    page.wait_for_function(f"document.querySelector('{V} .dv-peek [data-page-block=\"desired\"]').innerText.includes('EDITED BY HAND')", timeout=4000)
    took = time.time() - t0
    check("hand edit: on the open page within a second", took < 1.0, round(took, 3))
    in_table = page.locator(f'{V} tr.dv-row[data-id="{row}"] td[data-col="desired"]').first.inner_text()
    check("hand edit: in the table too", "EDITED BY HAND" in in_table, in_table[:60])
    t0 = time.time()
    note.write_text(note.read_text(encoding="utf-8") + "\n# Typed by hand\n\nA heading nobody declared\n", encoding="utf-8")
    page.wait_for_selector(f'{V} .dv-peek [data-page-block="typed_by_hand"]', timeout=4000)
    check("hand edit: a heading typed in the file is a block, undeclared", time.time() - t0 < 1.5, round(time.time() - t0, 3))
    check("hand edit: and a column to turn on", page.evaluate(f"!!document.querySelector('{V}').data.properties.typed_by_hand"))

    # ---- the panel: drag, remembered, full page
    peek = rect(page, f"{V} .dv-peek")
    split = page.locator(f"{V} > .dv-splitter").first
    s = split.bounding_box()
    page.mouse.move(s["x"] + s["width"] / 2, s["y"] + 200)
    page.mouse.down()
    page.mouse.move(s["x"] - 120, s["y"] + 200, steps=5)
    page.mouse.up()
    page.wait_for_timeout(250)
    wide = rect(page, f"{V} .dv-peek")
    check("panel: a drag of 120 px widens it 120 px", abs(wide["w"] - peek["w"] - 120) < 8, [peek["w"], wide["w"]])
    page.reload()
    page.wait_for_selector(f'{V} .dv-peek .dv-open-rec[data-id="{row}"] .dv-page-blocks', timeout=8000)
    page.wait_for_timeout(250)
    again = rect(page, f"{V} .dv-peek")
    check("panel: its width comes back on a reload", abs(again["w"] - wide["w"]) < 2, [wide["w"], again["w"]])
    page.locator(f"{V} [data-page-full]").click()
    page.wait_for_timeout(250)
    full = rect(page, f"{V} .dv-peek")
    size = page.viewport_size
    check("page: the full-page open fills the window", abs(full["w"] - size["width"]) < 2 and abs(full["h"] - size["height"]) < 2, [full["w"], full["h"]])
    check("page: its link says so", "full=1" in page.url, page.url)
    entry = page.locator(f'{V} .dv-peek [data-page-entry="desired"]')
    entry.locator(".dv-page-head").hover()
    entry.locator("[data-page-menu]").click()
    box = page.locator(f"{V} .dv-pop").bounding_box()
    hit = page.evaluate(f"(() => {{ const r = document.querySelector('{V} .dv-pop').getBoundingClientRect(); return document.elementFromPoint(r.x + 20, r.y + 20)?.closest('.dv-pop') !== null; }})()")
    check("page: a menu in a full page sits over it", hit, box)
    page.keyboard.press("Escape")
    page.reload()
    page.wait_for_selector(f"{V}.dv-page-full .dv-peek .dv-page-blocks", timeout=8000)
    check("page: a reload of that link opens it full", True)
    page.locator(f"{V} [data-page-full]").click()
    page.wait_for_timeout(200)
    check("page: back to the side panel", rect(page, f"{V} .dv-peek")["w"] < size["width"] - 100)
    page.locator(f"{V} .dv-peek .dv-close").click()


def outline_lines(page, row, col):
    return page.evaluate(f"""[...document.querySelectorAll('{V} tr.dv-row[data-id="{row}"] td[data-col="{col}"] .dv-sec-line')].map((n) => ({{ text: n.firstChild.textContent, more: n.querySelector('.dv-sec-more')?.textContent ?? null, pad: parseFloat(n.style.paddingLeft) }}))""")


def frdparrc(page, url, tmp):
    fr = tmp / "frdparrc"
    note = fr / "vibetracks.1.md"
    source = [re.match(r"(#{2,3}) (.*)", l) for l in note.read_text(encoding="utf-8").split("# DP\n", 1)[1].split("\n# Analysis")[0].split("\n")]
    heads = [(len(m[1]), m[2]) for m in source if m]
    page.goto(f"{url}/?db=frdparrc")
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    grow(page)
    lines = outline_lines(page, "vibetracks.1", "dp")
    check("outline: the cell is the section's sub-headings, in the file's order", [x["text"] for x in lines] == [h[1] for h in heads][:6], [x["text"][:30] for x in lines])
    check("outline: an H3 is indented under its H2", [x["pad"] > 0 for x in lines] == [h[0] == 3 for h in heads][:6], [x["pad"] for x in lines])
    rest = len(heads) - 6
    check("outline: what the row height leaves out is counted", lines[-1]["more"] == f"… +{rest}", lines[-1]["more"])
    check("outline: the H3's number stays as the source writes it", any(x["text"].startswith("(1) ") for x in lines))
    held = digests(fr)
    # §46, Zach 2026-10-31: "when you click it and edit it raw I think you can like see the raw contents inside"
    before = page.evaluate(f"""document.querySelector('{V} tr.dv-row[data-id="vibetracks.1"]').getBoundingClientRect().height""")
    page.locator(f'{V} tr.dv-row[data-id="vibetracks.1"] td[data-col="dp"]').first.click()
    box = page.locator(f"{V} .dv-celledit textarea")
    box.wait_for(timeout=6000)
    raw = box.input_value()
    check("outline: a click edits the raw markdown in the cell: the box holds the whole section, ## marks and all", "### (2) the banner" in raw and raw.lstrip().startswith("Copied from"), raw[:60])
    # §46, Zach 2026-10-31: compact in the table, and editing grows the cell: the rows below move down and nothing is covered
    tall = page.evaluate(f"""(() => {{ const tr = document.querySelector('{V} tr.dv-row[data-id="vibetracks.1"]'), next = tr.nextElementSibling, form = document.querySelector('{V} .dv-celledit'); const f = form.getBoundingClientRect(); return {{ row: tr.getBoundingClientRect().height, form: f.height, bottom: f.bottom, nextTop: next ? next.getBoundingClientRect().top : null, was: {before} }}; }})()""")
    check("outline: the row grows to hold the editor, and the next row starts below it", tall["row"] >= tall["form"] - 1 and tall["row"] > tall["was"] and (tall["nextTop"] is None or tall["nextTop"] >= tall["bottom"] - 1), tall)
    page.keyboard.type("words Esc throws away")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    check("outline: Esc throws away what was typed; nothing is written", digests(fr) == held)
    check("outline: Esc leaves the cell drawing its outline again", len(outline_lines(page, "vibetracks.1", "dp")) >= 3)
    after = page.evaluate(f"""document.querySelector('{V} tr.dv-row[data-id="vibetracks.1"]').getBoundingClientRect().height""")
    check("outline: leaving, the row is compact again", abs(after - before) <= 1, [before, after])
    # a save names one section: only its bytes move
    note = fr / "vibetracks.1.md"
    was = note.read_text(encoding="utf-8")
    page.locator(f'{V} tr.dv-row[data-id="vibetracks.1"] td[data-col="dp"]').first.click()
    box = page.locator(f"{V} .dv-celledit textarea")
    box.wait_for(timeout=6000)
    old = box.input_value()
    box.press("Control+End")
    page.keyboard.type(" Added in the cell.")
    grown = page.evaluate(f"""(() => {{ const tr = document.querySelector('{V} tr.dv-row[data-id="vibetracks.1"]'), f = document.querySelector('{V} .dv-celledit').getBoundingClientRect(); return tr.getBoundingClientRect().height >= f.height - 1 && f.height <= innerHeight; }})()""")
    check("outline: typing keeps the row around the editor, and a long section scrolls inside it", grown)
    page.keyboard.press("Enter")
    page.wait_for_timeout(350)
    now = note.read_text(encoding="utf-8")
    check("a save from the cell changes that section's bytes and no others", now == was.replace(old, old + " Added in the cell.", 1), now[-120:])
    note.write_text(was, encoding="utf-8")
    page.wait_for_timeout(350)
    # the edit surface is one piece: a host's replaces it, and the editor keeps working
    page.evaluate("""() => { const el = document.querySelector('#notes'); window.surfaced = []; el.cellSurface = ({ row, property }) => { window.surfaced.push([String(row.id), property]); return { fit() { window.surfaced.push('fit'); }, close() { window.surfaced.push('close'); } }; }; }""")
    page.locator(f'{V} tr.dv-row[data-id="vibetracks.1"] td[data-col="dp"]').first.click()
    page.locator(f"{V} .dv-celledit textarea").wait_for(timeout=6000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(120)
    used = page.evaluate("window.surfaced")
    page.evaluate("() => { document.querySelector('#notes').cellSurface = 'grow'; }")
    check("el.cellSurface replaces how the cell makes room", used[0] == ["vibetracks.1", "dp"] and "fit" in used and used[-1] == "close", used[:4])
    page.locator(f"{V} button", has_text="Compact").first.click()
    page.wait_for_selector(f'{V} tr.dv-row[data-id="vibetracks.1"]', timeout=5000)
    short = outline_lines(page, "vibetracks.1", "dp")
    check("row height: short shows one line, and counts the rest", len(short) == 1 and short[0]["more"] == f"… +{len(heads) - 1}", short)
    page.locator(f"{V} button", has_text="DP as first lines").first.click()
    page.wait_for_function(f"document.querySelector('{V} tr.dv-row[data-id=\"vibetracks.1\"] td[data-col=\"dp\"] [data-sec-kind]')?.dataset.secKind === 'preview'", timeout=5000)
    check("display: preview in the .base gives that column its first lines", "Copied from Vibe Tracks commit" in page.locator(f'{V} tr.dv-row[data-id="vibetracks.1"] td[data-col="dp"]').first.inner_text())
    page.locator(f"{V} button", has_text="FRDPARRC").first.click()
    page.wait_for_selector(f'{V} tr.dv-row[data-id="vibetracks.5"]', timeout=5000)
    page.wait_for_timeout(400)
    page.reload()
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    check("frdparrc: the table is generated from the notes, one row each", page.locator(f"{V} tr.dv-row").count() == len(list(fr.glob("*.md"))))
    refs = page.locator(f'{V} tr.dv-row[data-id="vibetracks.1"] td[data-col="refs"]').first.inner_text()
    check("frdparrc: # Refs is a column", "feedback:fb-b64dda95" in refs, refs[:70])
    check("frdparrc: an empty section is empty, not invented", page.locator(f'{V} tr.dv-row[data-id="vibetracks.5"] td[data-col="dp"]').first.inner_text().strip() == "—")
    open_row(page, "vibetracks.1")
    check("frdparrc: its five sections are blocks, in order", blocks(page) == ["dp", "analysis", "refs", "risks", "verification"], blocks(page))


def section(text, name):
    """The raw text of one `# Name` section in a note, as the file holds it."""
    return re.search(rf"^# {name}\n(.*?)(?=^# |\Z)", text, re.S | re.M).group(1).strip("\n")


def sheet(page, url, tmp):
    """Zach, 2026-10-31: "Ok go ahead with Sheet": a click on a section cell opens a side panel that follows the cell and autosaves; the panel
    drags and keeps its width; a stale edit is refused with a message. Measured with the real mouse and keyboard, read back from the files."""
    fr = tmp / "frdparrc"
    S = f"{V} .dv-cellsheet"
    page.goto(f"{url}/?db=frdparrc")
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    page.locator(f"{V} button", has_text="FRDPARRC").first.click()
    page.wait_for_selector(f'{V} th[data-col="risks"]', timeout=5000)
    cell = lambda row, col: page.locator(f'{V} tr.dv-row[data-id="{row}"] td[data-col="{col}"]').first
    held = digests(fr)
    check("sheet: no panel before a click", page.locator(S).count() == 0 or not page.locator(S).is_visible())
    cell("vibetracks.1", "dp").click()
    page.wait_for_selector(f"{S} textarea", state="visible", timeout=6000)
    one = (fr / "vibetracks.1.md").read_text(encoding="utf-8")
    raw = page.locator(f"{S} textarea").input_value()
    check("sheet: a click on a section cell opens the panel with that section's raw markdown", raw.strip() == section(one, "DP").strip() and raw.lstrip().startswith("Copied from"), raw[:50])
    check("sheet: the panel names the record", "vibetracks.1" in page.locator(f"{S} .dv-cs-note").inner_text(), page.locator(f"{S} .dv-cs-note").inner_text())
    check("sheet: the cell it is on is marked", page.locator(f'{V} td.dv-cs-on').count() == 1 and page.locator(f'{V} tr.dv-row[data-id="vibetracks.1"] td.dv-cs-on[data-col="dp"]').count() == 1)
    check("sheet: opening it wrote nothing", digests(fr) == held)
    page.evaluate(f"() => {{ const el = document.querySelector('{S}'); window.__hid = 0; new MutationObserver(() => {{ if (el.hidden) window.__hid++; }}).observe(el, {{ attributes: true, attributeFilter: ['hidden'] }}); }}")
    # the table is still a table: the row under the panel did not grow, and nothing is covered
    tr = page.evaluate(f"""(() => {{ const p = document.querySelector('{S}').getBoundingClientRect(), st = document.querySelector('{V} .dv-stage').getBoundingClientRect(); return {{ stageRight: st.right, panelLeft: p.left, panelW: p.width }}; }})()""")
    check("sheet: the table gives up the panel's width", tr["stageRight"] <= tr["panelLeft"] + 1, tr)
    # click a cell in another row: the panel follows, and never closes
    cell("vibetracks.6", "verification").click()
    page.wait_for_function(f"document.querySelector('{S} .dv-cs-note').textContent.includes('vibetracks.6')", timeout=4000)
    six = (fr / "vibetracks.6.md").read_text(encoding="utf-8")
    now = page.locator(f"{S} textarea").input_value()
    check("sheet: a click on a cell in another row moves the panel to it", now.strip() == section(six, "Verification").strip(), [now[:40], section(six, "Verification")[:40]])
    check("sheet: the panel never closed on the way", page.evaluate("window.__hid") == 0 and page.locator(S).is_visible(), page.evaluate("window.__hid"))
    check("sheet: the mark moved with it", page.locator(f'{V} tr.dv-row[data-id="vibetracks.6"] td.dv-cs-on[data-col="verification"]').count() == 1 and page.locator(f'{V} td.dv-cs-on').count() == 1)
    check("sheet: moving without typing wrote nothing", digests(fr) == held)
    # the far column is not behind the panel
    cell("vibetracks.8", "verification").click()
    page.wait_for_function(f"document.querySelector('{S} .dv-cs-note').textContent.includes('vibetracks.8')", timeout=4000)
    page.wait_for_timeout(150)
    clear = page.evaluate(f"""(() => {{ const c = document.querySelector('{V} tr.dv-row[data-id="vibetracks.8"] td[data-col="verification"]').getBoundingClientRect(), p = document.querySelector('{S}').getBoundingClientRect(); return {{ cellRight: c.right, panelLeft: p.left }}; }})()""")
    check("sheet: the cell being edited is scrolled clear of the panel", clear["cellRight"] <= clear["panelLeft"] + 1, clear)
    # type, wait, the file changed: only that section's bytes
    cell("vibetracks.6", "refs").click()
    page.wait_for_function(f"document.querySelector('{V} td.dv-cs-on')?.dataset.col === 'refs'", timeout=4000)
    note = fr / "vibetracks.6.md"
    was = note.read_text(encoding="utf-8")
    old = page.locator(f"{S} textarea").input_value()
    check("sheet: the same row, another column, shows that column", old.strip() == section(was, "Refs").strip(), old[:40])
    page.locator(f"{S} textarea").press("Control+End")
    page.keyboard.type(" Typed in the sheet.")
    check("sheet: it says it is editing", "Editing" in page.locator(f"{S} .dv-cs-state").inner_text())
    check("sheet: nothing is written while the keys are still coming", note.read_text(encoding="utf-8") == was)
    page.wait_for_timeout(1500)
    after = note.read_text(encoding="utf-8")
    check("sheet: it saved by itself, and changed that section's bytes and no others", after == was.replace(old, old + " Typed in the sheet.", 1) and after != was, after[-100:])
    others = {k: v for k, v in digests(fr).items() if k != "vibetracks.6.md"}
    check("sheet: no other note moved", others == {k: v for k, v in held.items() if k != "vibetracks.6.md"})
    check("sheet: it says Saved", page.locator(f"{S} .dv-cs-state").inner_text() == "Saved", page.locator(f"{S} .dv-cs-state").inner_text())
    # a second round in the same panel keeps working (the row it holds is the saved one)
    page.locator(f"{S} textarea").press("Control+End")
    page.keyboard.type(" Twice.")
    page.wait_for_timeout(1500)
    check("sheet: a second autosave in the same panel lands too", note.read_text(encoding="utf-8") == was.replace(old, old + " Typed in the sheet. Twice.", 1), note.read_text(encoding="utf-8")[-60:])
    # a change on disk while the panel is clean: the panel follows it
    saved = note.read_text(encoding="utf-8")
    theirs = saved.replace(" Twice.", " Theirs.", 1)
    note.write_text(theirs, encoding="utf-8")
    page.wait_for_function(f"document.querySelector('{S} textarea').value.includes('Theirs.')", timeout=5000)
    check("sheet: a clean panel follows a change made elsewhere", "Twice." not in page.locator(f"{S} textarea").input_value())
    # a stale edit is refused, with the reason, and neither side is lost
    page.locator(f"{S} textarea").press("Control+End")
    page.keyboard.type(" Mine.")
    elsewhere = theirs.replace(" Theirs.", " Theirs, again.", 1)
    note.write_text(elsewhere, encoding="utf-8")
    page.wait_for_function(f"document.querySelector('{S} .dv-ed-msg').textContent.length > 0", timeout=6000)
    page.wait_for_timeout(1000)
    msg = page.locator(f"{S} .dv-ed-msg").inner_text()
    check("sheet: a stale edit is refused with a clear message", "changed" in msg and "Not saved" == page.locator(f"{S} .dv-cs-state").inner_text(), msg)
    check("sheet: the file keeps what was written elsewhere", note.read_text(encoding="utf-8") == elsewhere)
    check("sheet: what was typed stays in the panel", page.locator(f"{S} textarea").input_value().endswith(" Mine."))
    check("sheet: the two ways out are offered", page.locator(f"{S} [data-cs-act]").count() == 2)
    page.locator(f"{S} [data-cs-act=theirs]").click()
    page.wait_for_timeout(300)
    check("sheet: Use theirs takes the file's text and drops mine", "Theirs, again." in page.locator(f"{S} textarea").input_value() and "Mine." not in page.locator(f"{S} textarea").input_value() and page.locator(f"{S} .dv-ed-msg").inner_text() == "")
    page.locator(f"{S} textarea").press("Control+End")
    page.keyboard.type(" Mine.")
    page.wait_for_timeout(1500)
    check("sheet: after taking theirs the next edit saves", note.read_text(encoding="utf-8").endswith("Mine.\n\n# Analysis" ) or "Theirs, again. Mine." in note.read_text(encoding="utf-8"), note.read_text(encoding="utf-8")[-100:])
    base = note.read_text(encoding="utf-8")
    note.write_text(base.replace("Theirs, again. Mine.", "Theirs, third.", 1), encoding="utf-8")
    page.locator(f"{S} textarea").press("Control+End")
    page.keyboard.type(" Kept.")
    page.wait_for_function(f"document.querySelector('{S} [data-cs-act=mine]')", timeout=6000)
    page.locator(f"{S} [data-cs-act=mine]").click()
    page.wait_for_timeout(1500)
    check("sheet: Keep mine saves over theirs", "Theirs, again. Mine. Kept." in note.read_text(encoding="utf-8") and "third" not in note.read_text(encoding="utf-8"), note.read_text(encoding="utf-8")[-100:])
    note.write_text(was, encoding="utf-8")
    page.wait_for_timeout(600)
    # the panel drags, and keeps its width
    w0 = page.evaluate(f"document.querySelector('{S}').getBoundingClientRect().width")
    hb = page.evaluate(f"(() => {{ const h = document.querySelector('{S} + .dv-splitter'); const r = h.getBoundingClientRect(); return {{ x: r.x + r.width / 2, y: r.y + r.height / 2, hidden: h.hidden }}; }})()")
    check("sheet: its left edge has a drag handle", not hb["hidden"], hb)
    page.mouse.move(hb["x"], hb["y"])
    page.mouse.down()
    page.mouse.move(hb["x"] - 140, hb["y"], steps=8)
    page.mouse.up()
    page.wait_for_timeout(300)
    w1 = page.evaluate(f"document.querySelector('{S}').getBoundingClientRect().width")
    check("sheet: dragging its edge widens it by the drag", abs((w1 - w0) - 140) <= 3, [w0, w1])
    st = page.evaluate(f"document.querySelector('{V} .dv-stage').getBoundingClientRect().right <= document.querySelector('{S}').getBoundingClientRect().left + 1")
    check("sheet: the table makes room for the wider panel", st)
    page.reload()
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    page.locator(f"{V} button", has_text="FRDPARRC").first.click()
    page.wait_for_selector(f'{V} th[data-col="risks"]', timeout=5000)
    cell("vibetracks.1", "dp").click()
    page.wait_for_selector(f"{S} textarea", state="visible", timeout=6000)
    page.wait_for_timeout(300)
    w2 = page.evaluate(f"document.querySelector('{S}').getBoundingClientRect().width")
    check("sheet: its width comes back after a reload", abs(w2 - w1) <= 2, [w1, w2])
    # Esc saves and closes; the table is free again
    page.locator(f"{S} textarea").press("Escape")
    page.wait_for_timeout(300)
    check("sheet: Esc closes the panel and gives the width back", not page.locator(S).is_visible() and page.evaluate(f"document.querySelector('{V} .dv-stage').getBoundingClientRect().right >= innerWidth - 40"))
    check("sheet: the mark is gone", page.locator(f"{V} td.dv-cs-on").count() == 0)
    check("sheet: looking and closing wrote nothing", digests(fr) == held)
    # the other ways stay: a plain text cell still edits in place, and 'grow' still grows
    page.evaluate("() => { document.querySelector('#notes').cellSurface = 'grow'; }")
    cell("vibetracks.1", "dp").click()
    page.locator(f"{V} .dv-celledit textarea").first.wait_for(timeout=4000)
    check("sheet: el.cellSurface = 'grow' keeps the cell growing, and no panel opens", not page.locator(S).is_visible())
    page.keyboard.press("Escape")
    page.evaluate("() => { document.querySelector('#notes').cellSurface = null; document.querySelector('#notes').setAttribute('cell-surface', 'grow'); }")
    cell("vibetracks.1", "dp").click()
    page.locator(f"{V} .dv-celledit textarea").first.wait_for(timeout=4000)
    check("sheet: the cell-surface=\"grow\" attribute does the same", not page.locator(S).is_visible())
    page.keyboard.press("Escape")
    page.evaluate("() => { document.querySelector('#notes').removeAttribute('cell-surface'); }")
    page.wait_for_timeout(200)
    check("sheet: none of that wrote a byte", digests(fr) == held)


def table_first(page, url, tmp):
    """Zach, 2026-10-31: "I can also start as a table view... fill it in top level, and then when I need to expand on it more. I basically go to the page
    view.. its all one linked piece of information! vs a summary and something else". One note, and the file read at every step."""
    fr = tmp / "frdparrc"
    words = "Starts as a row in the table"
    note = fr / f"{words}.md"
    page.goto(f"{url}/?db=frdparrc")
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    grow(page)
    page.locator(f"{V} button", has_text="FRDPARRC").first.click()
    page.wait_for_selector(f'{V} th[data-col="risks"]', timeout=5000)
    page.locator(f'{V} tr.dv-addrow [data-add-col="fr"] textarea').first.click()
    page.keyboard.type(words)
    for _ in range(14):
        if note.exists():
            break
        page.keyboard.press("Enter")
        page.wait_for_timeout(120)
    check("table first: a new row in the add row is a new note on disk", note.exists(), note.name)
    text = note.read_text(encoding="utf-8")
    check("table first: it holds what was typed, and no heading yet", f"fr: {words}" in text and "\n# " not in text, text)
    row = f'{V} tr.dv-row[data-id="{words}"]'
    page.wait_for_selector(row, timeout=4000)

    def fill(col, value):
        page.locator(f'{row} td[data-col="{col}"]').first.click()
        page.locator(f"{V} .dv-celledit textarea").first.wait_for(timeout=4000)
        page.keyboard.type(value)
        page.keyboard.press("Enter")
        page.wait_for_timeout(350)

    fill("dp", "A first idea, typed in the cell")
    text = note.read_text(encoding="utf-8")
    check("table first: typing in an empty section's cell writes that H1 in the file", "# DP\n\nA first idea, typed in the cell\n" in text, text[-60:])
    fill("risks", "It may be slow")
    text = note.read_text(encoding="utf-8")
    check("table first: a second cell, a second H1, in the layout's order", text.index("# DP") < text.index("# Risks") and "# Risks\n\nIt may be slow\n" in text, text[-90:])
    check("table first: sections nobody typed in stay out of the file", "# Analysis" not in text and "# Refs" not in text)

    page.locator(f'{row} td[data-col="name"]').first.click()
    page.wait_for_selector(f'{V} .dv-peek .dv-open-rec[data-id="{words}"] .dv-page-blocks', timeout=8000)
    page.wait_for_timeout(200)
    shown = page.locator(f'{V} .dv-peek [data-page-block="dp"]').inner_text()
    check("table first: the page shows the same words: one piece of information", "A first idea, typed in the cell" in shown, shown[:70])
    page.locator(f'{V} .dv-peek [data-page-block="dp"] [data-page-read]').click(position={"x": 40, "y": 8})
    ta = page.locator(f'{V} .dv-peek [data-page-block="dp"] textarea')
    ta.wait_for(timeout=3000)
    ta.press("Control+End")
    page.keyboard.type("\n\n## Option A\n\nThe words behind it\n\n## Option B")
    page.locator(f"{V} .dv-peek header h2").click()
    page.wait_for_timeout(450)
    text = note.read_text(encoding="utf-8")
    check("table first: an H2 written on the page sits inside the one H1", text.count("\n# DP") == 1 and "## Option A\n\nThe words behind it\n\n## Option B\n" in text and text.index("## Option B") < text.index("# Risks"), text[-130:])
    page.locator(f"{V} .dv-peek .dv-close").click()
    page.wait_for_timeout(250)

    lines = outline_lines(page, words, "dp")
    check("table first: back in the table the cell is its outline", [x["text"] for x in lines] == ["Option A", "Option B"], lines)
    kind = page.evaluate(f"""document.querySelector('{row} td[data-col="risks"] [data-sec-kind]').dataset.secKind""")
    check("table first: the section with no sub-headings is still its words", kind == "preview", kind)
    held = digests(fr)
    page.locator(f'{row} td[data-col="dp"]').first.click()
    box = page.locator(f"{V} .dv-celledit textarea").first
    box.wait_for(timeout=6000)
    check("table first: an outline cell edits its raw markdown in place", "## Option A" in box.input_value(), box.input_value()[:40])
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    page.locator(f'{row} td[data-col="risks"]').first.click()
    box = page.locator(f"{V} .dv-celledit textarea").first
    box.wait_for(timeout=4000)
    check("table first: a section with no sub-headings stays editable in its cell", box.input_value() == "It may be slow", box.input_value())
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    check("table first: looking at both wrote nothing", digests(fr) == held)


def wikilinks(page, url, tmp):
    """[[wikilinks]] in a section: untouched in the file, links on the page. Obsidian itself is never launched: each link's href is read."""
    fb = tmp / "feedback"
    note = fb / "fb-25f0fb32.md"
    picture = sorted(f.name for f in (fb / "attachments").iterdir())[0]
    lines = f"See [[Some Note]], [[Some Note|the alias]], [[Some Note#A heading]] and [[fb-15f0ae2f|a row here]].\n\n![[{picture}]]\n"
    page.goto(f"{url}/?db=feedback")
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    note.write_text(note.read_text(encoding="utf-8").rstrip("\n") + f"\n\n# Linked\n\n{lines}", encoding="utf-8")
    page.wait_for_function(f"!!document.querySelector('{V}').data.properties.linked", timeout=3000)
    open_row(page, "fb-25f0fb32")
    held = note.read_text(encoding="utf-8")
    links = page.evaluate(f"""[...document.querySelectorAll('{V} .dv-peek [data-page-block="linked"] a[data-page-wikilink]')].map((a) => [a.textContent, a.getAttribute('href')])""")
    base = "obsidian://open?vault=Test%20Vault&file="
    check("wikilink: each form renders as a link, with its alias", [x[0] for x in links] == ["Some Note", "the alias", "Some Note#A heading", "a row here"], links)
    check("wikilink: a link opens the note in Obsidian, the #heading kept", links[1][1] == f"{base}Some%20Note" and links[2][1] == f"{base}Some%20Note%23A%20heading", links[:3])
    img = page.evaluate(f"""(() => {{ const i = document.querySelector('{V} .dv-peek [data-page-block="linked"] img'); return i && i.complete && i.naturalWidth > 0; }})()""")
    check("wikilink: ![[image.png]] draws the picture", img is True, img)
    page.locator(f'{V} .dv-peek [data-page-block="linked"] [data-page-read]').click(position={"x": 2, "y": 2})
    ta = page.locator(f'{V} .dv-peek [data-page-block="linked"] textarea')
    ta.wait_for(timeout=3000)
    check("wikilink: the box shows it as written", ta.input_value() == lines.rstrip("\n"), ta.input_value()[:60])
    ta.press("Control+End")
    page.keyboard.type("\n\nOne more line")
    page.locator(f"{V} .dv-peek header h2").click()
    page.wait_for_timeout(450)
    check("wikilink: an edit beside it leaves every form untouched in the file", note.read_text(encoding="utf-8") == held.rstrip("\n") + "\n\nOne more line\n", note.read_text(encoding="utf-8")[-200:])
    opener = page.locator(f"{V} .dv-peek [data-open-elsewhere]")
    want = f"{base}feedback%2Ffb-25f0fb32.md"
    check("Open in Obsidian: on the page, the link to that file", opener.get_attribute("href") == want and opener.inner_text() == "Open in Obsidian", opener.get_attribute("href"))
    page.locator(f"{V} .dv-peek .dv-close").click()
    page.wait_for_timeout(200)
    page.locator(f'{V} tr.dv-row[data-id="fb-25f0fb32"] td[data-col="name"]').first.click(button="right")
    page.locator("[data-row-open-in]").hover()
    item = page.locator(f"{V} [data-row-elsewhere], [data-row-elsewhere]").first
    item.wait_for(timeout=3000)
    check("Open in Obsidian: in the row's Open in menu, the same link, in no new tab", item.get_attribute("href") == want and item.get_attribute("target") is None and item.inner_text() == "Obsidian", item.get_attribute("href"))
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    open_in(page)
    # an edit Obsidian makes reaches the table: both ways an editor saves
    for how, write in (("in place", lambda p, t: p.write_text(t, encoding="utf-8")), ("by rename", lambda p, t: (p.with_name(".tmp-save").write_text(t, encoding="utf-8"), p.with_name(".tmp-save").replace(p)))):
        mark = f"SAVED {how.upper()}"
        text = note.read_text(encoding="utf-8").replace("One more line", mark).replace("SAVED IN PLACE", mark)
        t0 = time.time()
        write(note, text)
        page.wait_for_function(f"""(document.querySelector('{V} tr.dv-row[data-id="fb-25f0fb32"] td[data-col="linked"]')?.innerText || document.querySelector('{V}').data.rows.find((r) => r.id === 'fb-25f0fb32').linked).includes('{mark}')""", timeout=3000)
        took = time.time() - t0
        check(f"a file saved outside {how} reaches the table within a second", took < 1.0, round(took, 3))


def open_in(page):
    """Right-click anywhere on a row, Open in, Side peek: Zach's menu, Notion's shape (docs/CONTRACT.md §46)."""
    row = page.locator(f'{V} tr.dv-row[data-id="fb-25f0fb32"]').first
    cells = row.locator("td").count()
    hits = []
    for i in range(cells):
        td = row.locator("td").nth(i)
        td.click(button="right", position={"x": 4, "y": 4})
        hits.append(page.locator("[data-row-open-in]").count())
        page.keyboard.press("Escape")
        page.wait_for_timeout(40)
    check("Open in: a right-click on every cell of the row, the first and the last included, opens the row's menu", cells > 2 and all(hits), hits)
    row.locator("td").nth(cells - 1).click(button="right", position={"x": 4, "y": 4})
    # the keyboard's way: → opens the submenu, ← comes back, Enter takes an item
    page.locator("[data-row-open-in]").focus()
    page.keyboard.press("ArrowRight")
    page.wait_for_selector(".dv-itemmenu-sub", timeout=2000)
    check("Open in: → opens the submenu, Side peek first and focused", page.evaluate("document.activeElement.textContent") == "Side peek")
    labels = page.locator(".dv-itemmenu-sub [role=menuitem]").all_inner_texts()
    check("Open in: the submenu lists where a row opens and nothing else", labels == ["Side peek", "Obsidian"], labels)
    page.keyboard.press("ArrowLeft")
    check("Open in: ← closes it, focus back on Open in", page.locator(".dv-itemmenu-sub").count() == 0 and "Open in" in page.evaluate("document.activeElement.textContent"))
    page.keyboard.press("Enter")
    page.wait_for_selector(".dv-itemmenu-sub", timeout=2000)
    page.keyboard.press("Enter")
    page.wait_for_selector(f'{V} .dv-peek .dv-open-rec[data-id="fb-25f0fb32"]', timeout=4000)
    check("Open in: Side peek opens that row's page", page.locator(f"{V} .dv-peek").is_visible())
    page.locator(f"{V} .dv-peek .dv-close").click()
    page.wait_for_timeout(120)


def hosted_page(page, url):
    """A host draws the record's page itself: the panel stays the kit's, the body the host's, kept across redraws."""
    page.goto(f"{url}/?db=feedback")
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    page.evaluate("""() => { const el = document.querySelector('#notes'); window.hosted = { mounts: 0, updates: 0, destroyed: 0 };
      el.pageRenderer = (host, { row, id }) => { window.hosted.mounts += 1; host.innerHTML = `<article data-host-page>${id}</article><input aria-label="kept" data-host-input>`;
        return { update() { window.hosted.updates += 1; }, destroy() { window.hosted.destroyed += 1; } }; }; }""")
    page.locator(f'{V} tr.dv-row[data-id="fb-25f0fb32"]').first.locator(".dv-row-open").evaluate("(b) => b.click()")
    page.wait_for_selector(f"{V} .dv-peek [data-host-page]", timeout=4000)
    check("page renderer: the host's page is in the panel, nothing of the kit's own body", page.locator(f"{V} .dv-peek [data-page-block]").count() == 0, page.locator(f"{V} .dv-peek [data-host-page]").inner_text())
    node = page.evaluate_handle(f"document.querySelector('{V} .dv-peek [data-host-page]')")
    page.evaluate("document.querySelector('#notes').refreshPeek()")
    page.wait_for_timeout(100)
    same = page.evaluate(f"(n) => n === document.querySelector('{V} .dv-peek [data-host-page]') && n.isConnected", node)
    check("page renderer: a redraw of the panel keeps the same element, and tells the host", same and page.evaluate("window.hosted.updates") >= 1 and page.evaluate("window.hosted.mounts") == 1, page.evaluate("window.hosted"))
    page.locator(f"{V} .dv-peek [data-host-input]").focus()
    page.keyboard.type("typing")
    page.evaluate("document.querySelector('#notes').refreshPeek()")
    check("page renderer: a redraw never takes the focus from what the host drew", page.evaluate("document.activeElement.dataset.hostInput !== undefined") and page.locator(f"{V} .dv-peek [data-host-input]").input_value() == "typing")
    page.keyboard.press("Tab")
    page.evaluate("document.querySelector('#notes').querySelector('.dv-peek .dv-close').click()")
    page.wait_for_timeout(100)
    check("page renderer: closing the panel lets the host go", page.evaluate("window.hosted.destroyed") == 1)


def list_hints(page, url, tmp):
    """A list cell suggests what its column holds, for the word being typed (§46)."""
    folder = tmp / "tagged"
    page.goto(f"{url}/?db=tagged")
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    page.locator(f'{V} tr.dv-row[data-id="one"] td[data-col="tags"]').first.click()
    box = page.locator(f"{V} .dv-celledit input[list]")
    box.wait_for(timeout=4000)
    box.fill("alpha, b")
    box.dispatch_event("input")
    options = page.evaluate(f"[...document.querySelectorAll('{V} .dv-celledit datalist option')].map((o) => o.value)")
    check("a list cell suggests the column's values for the word being typed, keeping what came before", options == ["alpha, beta"], options)
    box.fill("alpha, beta")
    page.keyboard.press("Enter")
    page.wait_for_function(f"(document.querySelector('{V}').row('one').tags || []).length === 2", timeout=4000)
    check("a list cell saves as a list in the note's frontmatter", "- alpha\n  - beta" in (folder / "one.md").read_text(encoding="utf-8"), (folder / "one.md").read_text(encoding="utf-8")[:60])
    # a list with a fixed set of values: a <select> holds one, so it would drop all but one of them
    page.locator(f'{V} tr.dv-row[data-id="two"] td[data-col="kinds"]').first.click()
    box = page.locator(f"{V} .dv-celledit input[list]")
    box.wait_for(timeout=4000)
    check("a list with a fixed set of values opens as text holding all of them, never a one-value select", box.input_value() == "a, b" and page.locator(f"{V} .dv-celledit select").count() == 0, box.input_value())
    box.fill("a, b, ")
    box.dispatch_event("input")
    options = page.evaluate(f"[...document.querySelectorAll('{V} .dv-celledit datalist option')].map((o) => o.value)")
    check("its suggestions are the set's other values", options == ["a, b, c"], options)
    box.fill("a, b, c")
    page.keyboard.press("Enter")
    page.wait_for_function(f"(document.querySelector('{V}').row('two').kinds || []).length === 3", timeout=4000)
    saved = (folder / "two.md").read_text(encoding="utf-8")
    check("adding a value keeps the others", "- a\n  - b\n  - c" in saved, saved[:70])


def remembered_width(browser, url):
    """A dragged width is kept: a window too narrow for it draws it smaller, and a wider one gives it back (§11)."""
    # WHY 800: the table keeps 160 px, so 900 (room 860) would still fit a 700 px panel
    ctx = browser.new_context(viewport={"width": 800, "height": 700})
    page = ctx.new_page()
    page.goto(f"{url}/?db=feedback")
    page.evaluate("localStorage.setItem('data-ui/panel-width/peek:notes', '700')")
    page.reload()
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    page.locator(f'{V} tr.dv-row[data-id="fb-25f0fb32"]').first.locator(".dv-row-open").evaluate("(b) => b.click()")
    page.wait_for_selector(f"{V} .dv-peek", timeout=4000)
    page.wait_for_timeout(200)
    small = page.evaluate(f"document.querySelector('{V} .dv-peek').getBoundingClientRect().width")
    page.set_viewport_size({"width": 1500, "height": 800})
    page.wait_for_timeout(300)
    big = page.evaluate(f"document.querySelector('{V} .dv-peek').getBoundingClientRect().width")
    check("a stored panel width too wide for the window is drawn smaller, and comes back with the room", small < 700 and abs(big - 700) <= 1, [small, big])
    ctx.close()


def newest_first(page, url, tmp):
    """A folder with dates and no sort in its view reads newest first (§46); a view's own sort wins."""
    folder = tmp / "dated"
    folder.mkdir(exist_ok=True)
    for name, added in (("older", "2026-10-01T09:00:00"), ("newest", "2026-10-31T09:00:00"), ("middle", "2026-10-15T09:00:00")):
        (folder / f"{name}.md").write_text(f"---\nadded: {added}\n---\n\n# Observed\n\n{name}\n", encoding="utf-8")
    return folder


def no_vault(browser, url):
    """The same page with no --vault: hidden, never greyed."""
    page = browser.new_page(viewport={"width": 1400, "height": 860})
    page.goto(f"{url}/?db=feedback")
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    open_row(page, "fb-25f0fb32")
    check("no vault: no Open in Obsidian on the page: not greyed, not there", page.locator(f"{V} [data-open-elsewhere]").count() == 0)
    page.locator(f"{V} .dv-peek .dv-close").click()
    page.wait_for_timeout(200)
    page.locator(f'{V} tr.dv-row[data-id="fb-25f0fb32"] td[data-col="name"]').first.click(button="right")
    page.wait_for_timeout(250)
    page.locator("[data-row-open-in]").hover()
    page.wait_for_selector(".dv-itemmenu-sub", timeout=2000)
    check("no vault: Open in lists Side peek alone: no Obsidian, not greyed", page.locator(".dv-itemmenu-sub [role=menuitem]").all_inner_texts() == ["Side peek"] and page.locator("[data-row-elsewhere]").count() == 0)
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    open_row(page, "fb-25f0fb32")
    tags = page.evaluate(f"""[...document.querySelectorAll('{V} .dv-peek [data-page-block="linked"] [data-page-wikilink]')].map((a) => [a.tagName, a.textContent])""")
    check("no vault: a link to a note of this table is still a link; one to nothing here is its words", ["A", "a row here"] in tags and ["SPAN", "the alias"] in tags, tags)
    page.locator(f'{V} .dv-peek [data-page-note]').click()
    page.wait_for_selector(f'{V} .dv-peek .dv-open-rec[data-id="fb-15f0ae2f"]', timeout=4000)
    check("no vault: clicking it opens that note here", True)
    page.close()


def widths(browser, url, tmp):
    for name, w, h, dark, mobile in (("light-1400", 1400, 860, False, False), ("dark-1400", 1400, 860, True, False), ("light-390", 390, 844, False, True), ("dark-390", 390, 844, True, True)):
        ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme="dark" if dark else "light", has_touch=mobile, is_mobile=mobile)
        page = ctx.new_page()
        page.goto(f"{url}/?db=feedback")
        page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
        page.screenshot(path=str(OUT / f"table-{name}.png"))
        over = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(f"{name}: no sideways page scroll on the table", over <= 0, over)
        page.locator(f'{V} tr.dv-row[data-id="fb-f8f638df"] .dv-row-open').evaluate("(b) => b.click()")
        page.wait_for_selector(f"{V} .dv-peek .dv-page-blocks", timeout=8000)
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / f"page-{name}.png"))
        peek_over = page.evaluate(f"(() => {{ const p = document.querySelector('{V} .dv-peek'); return p.scrollWidth - p.clientWidth; }})()")
        check(f"{name}: no sideways scroll in the page", peek_over <= 0, peek_over)
        ctx.close()


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="md-pages-"))
    for name in ("feedback", "frdparrc"):
        shutil.copytree(CASE / name, tmp / name)
    (tmp / "tagged").mkdir()
    (tmp / "tagged" / "views.base").write_text("properties:\n  tags: { type: multi_select }\n  kinds: { type: multi_select, enum: [a, b, c] }\nviews:\n  - { type: table, name: Table, order: [name, tags, kinds] }\n", encoding="utf-8")
    (tmp / "tagged" / "one.md").write_text("---\ntags:\n  - alpha\n---\n\n# Observed\n\nwords\n", encoding="utf-8")
    (tmp / "tagged" / "two.md").write_text("---\ntags:\n  - beta\n  - gamma\nkinds:\n  - a\n  - b\n---\n\n# Observed\n\nwords\n", encoding="utf-8")
    port = free_port()
    # the temp folder stands in for a vault: the links are read, and Obsidian is never launched
    server = subprocess.Popen(["node", str(ROOT / "tools" / "serve-md.mjs"), str(tmp / "feedback"), str(tmp / "frdparrc"), str(tmp / "tagged"), "--port", str(port), "--vault", "Test Vault", "--vault-root", str(tmp)], stdout=subprocess.PIPE, text=True)
    url = f"http://127.0.0.1:{port}"
    plain = None
    try:
        server.stdout.readline()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1400, "height": 860}, color_scheme="light")
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            run(page, url, tmp)
            frdparrc(page, url, tmp)
            sheet(page, url, tmp)
            table_first(page, url, tmp)
            wikilinks(page, url, tmp)
            hosted_page(page, url)
            check("no page error or console error", not errors, errors[:3])
            ctx.close()
            remembered_width(browser, url)
            page = browser.new_page(viewport={"width": 1200, "height": 700})
            list_hints(page, url, tmp)
            page.close()
            widths(browser, url, tmp)
            plain_port = free_port()
            dated = newest_first(None, None, tmp)
            plain = subprocess.Popen(["node", str(ROOT / "tools" / "serve-md.mjs"), str(tmp / "feedback"), str(dated), "--port", str(plain_port)], stdout=subprocess.PIPE, text=True)
            plain.stdout.readline()
            no_vault(browser, f"http://127.0.0.1:{plain_port}")
            page = browser.new_page(viewport={"width": 1200, "height": 700})
            page.goto(f"http://127.0.0.1:{plain_port}/?db=dated")
            page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
            order = page.evaluate(f"[...document.querySelectorAll('{V} tr.dv-row')].map((r) => r.dataset.id)")
            check("a folder of dated notes with no view of its own reads newest first", order == ["newest", "middle", "older"], order)
            page.close()
            browser.close()
    finally:
        for proc in (server, plain):
            if proc:
                proc.terminate()
                proc.wait(timeout=5)
        shutil.rmtree(tmp, ignore_errors=True)
    (OUT / "md-pages-checks.json").write_text(json.dumps(checks, indent=1), encoding="utf-8")
    bad = [c for c in checks if not c["ok"]]
    print(f"\n{len(checks) - len(bad)} of {len(checks)} checks pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
