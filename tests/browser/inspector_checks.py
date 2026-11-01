"""The inspector: one property per row (docs/CONTRACT.md "the inspector"). Written first, red, and not edited after the code landed.

    ~/psu-atlas/.venv/bin/python tests/browser/inspector_checks.py [OUT_DIR]     # after npm run build

Zach, 2026-10-31: "I don't like how when I look at the inspector menu its not a 1:1 coorespondance with the fields I am seeing";
"Desired is notions: pattern where you have 1 property per cell"; "And then you have control over what property visibilty in the
inspector or in the row".
What is measured, in headless Chromium on the built kit, with the real mouse:
  - 1:1, on three gallery cases and a fixture: the inspector's labels equal the table's drawn headers, in order, then the hidden ones
  - one property per row (each row one label and one value, each below the last); no chips row; no tabs
  - "N more properties" collapses the hidden rows (0 px) and expands them in place: the title does not move, the panes below do
  - the two settings are separate, both ways, set from the inspector and from Property visibility; hide when empty
  - saved in the view, in the .base text a persistView host gets, and read back from that text
  - the slot below the properties: every value behind it, the host's peekExtra, the source popover on a field
  - Add a property only with acceptProperty; the boundary drags, is remembered, folds
  - the record view reads the same; a sectioned view keeps its sections; a source-per-column dataset reads well at 390 px
Serves the repo root on a free port, stops it when done, writes OUT_DIR/inspector-checks.json, exits 1 if a check fails.
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
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "inspector"
OUT.mkdir(parents=True, exist_ok=True)
PAGE = "/tests/browser/fixtures/inspector/page.html"
WAIT = 20000
checks: list[dict] = []


def check(name, ok, detail=None):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {json.dumps(detail, default=str)[:400]}"))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


HEADERS = """(sel) => {
  const el = document.querySelector(sel);
  const ths = [...el.querySelectorAll('.dv-stage thead tr.dv-hleaf th')].filter((t) => !t.classList.contains('dv-selcol'));
  // the label, not the unit span the header adds after it (an inspector row carries the unit beside the value)
  const label = (t) => { const c = (t.querySelector('.dv-th') || t).cloneNode(true); for (const u of c.querySelectorAll('.dv-unit, button')) u.remove(); return c.textContent; };
  return ths.map((t) => label(t).replace(/[↑↓▲▼]/g, '').replace(/\\s+/g, ' ').trim()).filter(Boolean);
}"""
LABELS = """([sel, scope]) => {
  const root = document.querySelector(sel).querySelector(scope);
  const rows = [...root.querySelectorAll('tr[data-p]')];
  return rows.map((r) => ({ label: r.querySelector('th').textContent.replace(/\\s+/g, ' ').trim(), id: r.dataset.p, h: r.getBoundingClientRect().height, top: r.getBoundingClientRect().top }));
}"""


def open_first(page, sel):
    if page.evaluate("(s) => document.querySelector(s).editing", sel):
        # WHY by the element's call on an editing sheet: a click there types in the cell; the row's way in is its Open
        page.evaluate("(s) => { const e = document.querySelector(s); e.openPeek(e.model.rows.find((r) => r.id !== undefined).id); }", sel)
    else:
        # at the cell's left: a value with several sources has its pill in the cell, and a click there is the pill's
        page.click(f"{sel} .dv-stage tbody tr[data-id] td:nth-child(2)", position={"x": 6, "y": 6})
    page.wait_for_selector(f"{sel} .dv-peek:not([hidden]) .dv-open-rec", timeout=WAIT)


def view(page, sel, name):
    page.click(f"{sel} .dv-tab[data-name='{name}']")
    page.wait_for_function("([s, n]) => { const t = document.querySelector(s + ` .dv-tab[data-name='${n}']`); return t && (t.classList.contains('dv-on') || t.getAttribute('aria-selected') === 'true' || t.getAttribute('aria-current')); }", arg=[sel, name], timeout=WAIT)
    page.wait_for_timeout(150)


def expand(page, sel, scope=".dv-peek"):
    b = page.locator(f"{sel} {scope} [data-prop-more]")
    if b.count() and b.get_attribute("aria-expanded") == "false":
        b.click()


def one_to_one(page, sel, tag, title):
    """The check of the claim: every drawn header but the title, in order, then every hidden property, in order."""
    open_first(page, sel)
    head = page.evaluate(HEADERS, sel)
    want_title = page.evaluate("(s) => { const e = document.querySelector(s); return e.model.columns[e.data.titleProperty].label; }", sel)
    head_rest = [h for h in head if h != want_title]
    hidden = page.evaluate("""(s) => {
      const e = document.querySelector(s), c = e.model.columns, v = e.view;
      const order = v.order && v.order.length ? v.order : Object.keys(c).filter((k) => !c[k].hidden);
      const units = new Set(Object.values(c).map((p) => p.unit).filter(Boolean));
      const held = e.data.detail ? e.data.detail.property : null;
      return Object.keys(c).filter((k) => !order.includes(k) && !c[k].hidden && !units.has(k) && k !== e.data.titleProperty && k !== held).map((k) => c[k].label);
    }""", sel)
    peek = page.evaluate(LABELS, [sel, ".dv-peek"])
    shown = [x["label"] for x in peek if x["h"] > 0]
    check(f"{tag}: the inspector's rows are the table's columns, same labels, same order", shown == head_rest, {"inspector": shown, "columns": head_rest})
    expand(page, sel)
    peek = page.evaluate(LABELS, [sel, ".dv-peek"])
    every = [x["label"] for x in peek if x["h"] > 0]
    check(f"{tag}: expanded, the hidden properties follow, in the data's order", every == head_rest + hidden, {"inspector": every, "want": head_rest + hidden})
    tops = [x["top"] for x in peek if x["h"] > 0]
    check(f"{tag}: one property per row, each below the last", all(b > a for a, b in zip(tops, tops[1:])), tops)
    shape = page.evaluate("""(s) => { const p = document.querySelector(s + ' .dv-peek');
      return { chips: p.querySelectorAll('.dv-open-chips, .dv-open-chip').length, tabs: p.querySelectorAll('[role=tab], [role=tablist], .dv-open-tabs').length,
               cells: [...p.querySelectorAll('tr[data-p]')].every((r) => r.querySelectorAll('th').length === 1 && r.querySelectorAll('td').length === 1) }; }""", sel)
    check(f"{tag}: no chips row, no tabs, one label and one value a row", shape == {"chips": 0, "tabs": 0, "cells": True}, shape)
    page.keyboard.press("Escape")


def gallery(browser, base):
    for case, name, sel, title in (("gim4305-datasheet", "Datasheet", "#example", "field"),
                                   ("gim4305-datasheet", "Datasheet only", "#example", "field"),
                                   ("gim4305-datasheet", "Measured vs datasheet", "#example", "field"),
                                   ("robotparts-actuators", "All, flat", "#example", "model"),
                                   ("notion-table", "All", "#example", "task")):
        page = browser.new_page(viewport={"width": 1500, "height": 900})
        page.goto(f"{base}/dist/site/gallery/{case}/index.html")
        page.wait_for_selector(f"{sel}[data-view]", timeout=WAIT)
        page.wait_for_selector(f"{sel} .dv-stage tbody tr[data-id]", timeout=WAIT)
        if page.evaluate("(s) => document.querySelector(s).view.name", sel) != name:
            view(page, sel, name)
        one_to_one(page, sel, f"{case} · {name}", title)
        page.close()


def fixture(browser, base):
    sel = "#insp"
    url = base + PAGE

    def fresh(query="", width=1400, height=900):
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(url + query)
        page.wait_for_selector(f"{sel}[data-view]", timeout=WAIT)
        return page

    page = fresh()
    one_to_one(page, sel, "fixture · Nominal", "field")

    # collapsed and expanded, in place
    open_first(page, sel)
    page.wait_for_selector(f"{sel} [data-prop-more]")
    more = page.locator(f"{sel} .dv-peek [data-prop-more]")
    check("the hidden ones collapse behind 'N more properties'", more.inner_text().strip() == "5 more properties", more.inner_text())
    before = page.evaluate("""(s) => { const p = document.querySelector(s + ' .dv-peek'); return { title: p.querySelector('h2').getBoundingClientRect().top, hidden: [...p.querySelectorAll('tr[data-p=datasheet]')].map((r) => r.getBoundingClientRect().height), slot: p.querySelector('.dv-peek-slot').getBoundingClientRect().top, node: (window.__node = p.querySelector('.dv-open-rec'), 1) }; }""", sel)
    check("collapsed, a hidden property takes 0 px", before["hidden"] == [0], before)
    more.click()
    after = page.evaluate("""(s) => { const p = document.querySelector(s + ' .dv-peek'); const b = p.querySelector('[data-prop-more]'); const r = p.querySelector('tr[data-p=datasheet]').getBoundingClientRect(); return { title: p.querySelector('h2').getBoundingClientRect().top, row: r.height, rowBottom: r.bottom, button: b.getBoundingClientRect().top, slot: p.querySelector('.dv-peek-slot').getBoundingClientRect().top, same: window.__node === p.querySelector('.dv-open-rec'), expanded: b.getAttribute('aria-expanded'), text: b.textContent.trim() }; }""", sel)
    check("it expands in place: the title stays, the rows take height, the panes move down, nothing redraws", abs(after["title"] - before["title"]) < 0.5 and after["row"] > 10 and after["slot"] > before["slot"] and after["same"] and after["expanded"] == "true", {"before": before, "after": after})
    check("the rows open above the button, which then folds them", after["rowBottom"] <= after["button"] + 1 and after["text"] == "Hide 5 properties", after)
    page.locator(f"{sel} .dv-peek").click(position={"x": 200, "y": 8})
    page.keyboard.press("ArrowDown")
    page.wait_for_function("(s) => document.querySelector(s).peeked.id === 'rated'", arg=sel, timeout=WAIT)
    check("stepping to the next record keeps them open", page.locator(f"{sel} .dv-peek [data-prop-more]").get_attribute("aria-expanded") == "true")
    empties = page.evaluate("(s) => document.querySelector(s + ' .dv-peek tr[data-p=note] td').textContent.trim()", sel)
    check("an empty value is its row, a dash, not a missing line", empties == "—", empties)
    page.close()

    # separate, set from the inspector
    page = fresh("?persist=1&src=parts.base")
    page.evaluate("sessionStorage.clear()")
    page.reload()
    page.wait_for_selector(f"{sel}[data-view]", timeout=WAIT)
    open_first(page, sel)
    page.hover(f"{sel} .dv-peek tr[data-p=section]")
    page.click(f"{sel} .dv-peek tr[data-p=section] [data-prop-vis]")
    page.wait_for_selector(".dv-pop:not([hidden]) [data-vis=hide]")
    page.click(".dv-pop [data-vis=hide]")
    page.wait_for_function("(s) => !![...document.querySelectorAll(s + ' .dv-peek tr[data-p=section]')].find((r) => r.getBoundingClientRect().height === 0)", arg=sel, timeout=WAIT)
    head = page.evaluate(HEADERS, sel)
    check("hidden in the inspector, it stays a column in the row", "Section" in head, head)
    labels = [x["label"] for x in page.evaluate(LABELS, [sel, ".dv-peek"]) if x["h"] > 0]
    check("hidden in the inspector, it is behind N more", "Section" not in labels and page.locator(f"{sel} .dv-peek [data-prop-more]").inner_text().strip() == "6 more properties", labels)
    page.wait_for_function("() => window.saved.length > 0", timeout=WAIT)
    text = page.evaluate("() => window.saved.at(-1).text")
    check("saved in the view: the .base text says record.visibility", "visibility:" in text and "section: hide" in text and "record:" in text, text[:900])
    # the row, from the same menu
    expand(page, sel)
    page.hover(f"{sel} .dv-peek tr[data-p=nominal]")
    page.click(f"{sel} .dv-peek tr[data-p=nominal] [data-prop-vis]")
    page.wait_for_selector(".dv-pop:not([hidden]) [data-vis-row]")
    page.click(".dv-pop [data-vis-row]")
    page.wait_for_function("(s) => !document.querySelector(s).view.order.includes('nominal')", arg=sel, timeout=WAIT)
    page.wait_for_timeout(120)
    head = page.evaluate(HEADERS, sel)
    check("from the same menu, the row: the column leaves the table", "Nominal" not in head, head)
    page.wait_for_function("() => /order: \\[\\s*field,\\s*section\\s*\\]/.test(window.saved.at(-1).text)", timeout=WAIT)
    page.reload()
    page.wait_for_selector(f"{sel}[data-view]", timeout=WAIT)
    open_first(page, sel)
    head = page.evaluate(HEADERS, sel)
    shown = [x["label"] for x in page.evaluate(LABELS, [sel, ".dv-peek"]) if x["h"] > 0]
    check("a reload from that .base text: both settings came back, each its own", head == ["Field", "Section"] and "Section" not in shown, {"head": head, "shown": shown})
    page.close()

    # read back from the file, each setting doing its own thing
    page = fresh()
    view(page, sel, "Set apart")
    open_first(page, sel)
    head = page.evaluate(HEADERS, sel)
    peek = page.evaluate(LABELS, [sel, ".dv-peek"])
    shown = [x["label"] for x in peek if x["h"] > 0]
    check("read from the .base: section hides in the inspector and stays a column", "Section" in head and "Section" not in shown, {"head": head, "shown": shown})
    check("read from the .base: citation shows in the inspector with no column", "Citation" not in head and "Citation" in shown, {"head": head, "shown": shown})
    check("read from the .base: hideEmpty, the peak row has no weight, so it is behind N more", "Weight" not in shown, shown)
    page.keyboard.press("Escape")
    page.click(f"{sel} .dv-stage tbody tr[data-id='rated'] td:nth-child(2)")
    page.wait_for_function("(s) => { const e = document.querySelector(s); return e.peeked && e.peeked.id === 'rated'; }", arg=sel, timeout=WAIT)
    page.wait_for_timeout(100)
    shown = [x["label"] for x in page.evaluate(LABELS, [sel, ".dv-peek"]) if x["h"] > 0]
    check("read from the .base: hideEmpty, the rated row has a weight, so it shows", "Weight" in shown, shown)
    page.close()

    # Property visibility: both controls, one place
    page = fresh()
    open_first(page, sel)
    page.evaluate("(s) => document.querySelector(s).openMenu('properties')", sel)
    page.wait_for_selector(f"{sel} .dv-prop[data-id=section] [data-k=inspector]", state="attached", timeout=WAIT)
    page.select_option(f"{sel} .dv-prop[data-id=section] [data-k=inspector]", "hide")
    page.wait_for_function("(s) => { const e = document.querySelector(s); return e.view.record && e.view.record.visibility && e.view.record.visibility.section === 'hide'; }", arg=sel, timeout=WAIT)
    page.wait_for_timeout(120)
    shown = [x["label"] for x in page.evaluate(LABELS, [sel, ".dv-peek"]) if x["h"] > 0]
    check("Property visibility sets the inspector too, and the open inspector follows", "Section" not in shown, shown)
    page.close()

    # the column changes while the inspector is open
    page = fresh()
    open_first(page, sel)
    page.evaluate("(s) => document.querySelector(s).setView({ order: ['field', 'section', 'datasheet', 'nominal'] })", sel)
    page.wait_for_timeout(200)
    shown = [x["label"] for x in page.evaluate(LABELS, [sel, ".dv-peek"]) if x["h"] > 0]
    check("reorder the columns: the open inspector follows at once", shown == ["Section", "Datasheet", "Nominal"], shown)
    page.close()

    # a source per column
    page = fresh()
    view(page, sel, "Every source")
    open_first(page, sel)
    shown = [x["label"] for x in page.evaluate(LABELS, [sel, ".dv-peek"]) if x["h"] > 0]
    check("a dataset with one plain column per source: each source is its row, in the view's order", shown == ["Datasheet", "Citation", "Chat", "Nominal"], shown)
    page.close()
    page = fresh("", width=390, height=800)
    page.click(f"{sel} .dv-stage tbody tr[data-id] td:nth-child(1)")
    page.wait_for_selector(f"{sel} .dv-peek:not([hidden]) [data-prop-more]", timeout=WAIT)
    page.click(f"{sel} .dv-peek [data-prop-more]")
    wide = page.evaluate("""(s) => { const p = document.querySelector(s + ' .dv-peek'); const w = p.getBoundingClientRect().width; return { scroll: p.scrollWidth - p.clientWidth, page: document.documentElement.scrollWidth - innerWidth, over: [...p.querySelectorAll('tr[data-p]')].filter((r) => r.getBoundingClientRect().right > w + 1).length }; }""", sel)
    check("at 390 px the rows fit: no sideways scroll, no row past the edge", wide == {"scroll": 0, "page": 0, "over": 0}, wide)
    page.close()

    # the slot
    page = fresh("?extra=1")
    open_first(page, sel)
    slot = page.evaluate("""(s) => { const p = document.querySelector(s + ' .dv-peek'); const rows = [...p.querySelectorAll('tr[data-p]')].filter((r) => r.getBoundingClientRect().height); const last = rows.at(-1).getBoundingClientRect().bottom; const s2 = p.querySelector('.dv-peek-slot'); return { text: s2.textContent, top: s2.getBoundingClientRect().top, last, entries: s2.querySelectorAll('.dv-entry').length, foot: !!s2.querySelector('.dv-peek-extra .host-foot') }; }""", sel)
    check("the slot sits below the properties, and holds every value behind it and the host's peekExtra", slot["top"] >= slot["last"] and slot["entries"] == 2 and slot["foot"] and "Every value behind it" in slot["text"], slot)
    page.close()

    # Add a property
    page = fresh()
    open_first(page, sel)
    check("Add a property: not there without acceptProperty", page.locator(f"{sel} .dv-peek [data-prop-add]").count() == 0)
    page.close()
    page = fresh("?accept=1")
    open_first(page, sel)
    add = page.locator(f"{sel} .dv-peek [data-prop-add]")
    check("Add a property: there with acceptProperty", add.count() == 1 and "Add a property" in add.inner_text(), add.count())
    add.click()
    page.wait_for_selector(".dv-pop:not([hidden]) [data-col-addform]")
    page.fill(".dv-pop [name=name]", "Backlash")
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.properties.length === 1", timeout=WAIT)
    page.wait_for_function("(s) => !!document.querySelector(s + ' .dv-peek tr[data-p=backlash]')", arg=sel, timeout=WAIT)
    check("Add a property: it goes through the host's hook, and is a row", page.evaluate("() => window.properties[0].op") == "add")
    page.close()

    # the boundary
    page = fresh()
    open_first(page, sel)
    page.wait_for_selector(f"{sel} > .dv-peek + .dv-splitter", state="visible", timeout=WAIT)
    box = page.locator(f"{sel} > .dv-peek + .dv-splitter").bounding_box()
    w0 = page.evaluate("(s) => document.querySelector(s + ' .dv-peek').getBoundingClientRect().width", sel)
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 100)
    page.mouse.down()
    page.mouse.move(box["x"] - 90, box["y"] + 100, steps=6)
    page.mouse.up()
    w1 = page.evaluate("(s) => document.querySelector(s + ' .dv-peek').getBoundingClientRect().width", sel)
    check("the boundary drags: measured", abs((w1 - w0) - 90) < 6, [w0, w1])
    page.reload()
    page.wait_for_selector(f"{sel}[data-view]", timeout=WAIT)
    open_first(page, sel)
    w2 = page.evaluate("(s) => document.querySelector(s + ' .dv-peek').getBoundingClientRect().width", sel)
    check("the width is remembered through a reload", abs(w2 - w1) < 2, [w1, w2])
    page.click(f"{sel} .dv-peek .dv-close")
    check("it folds away", page.evaluate("(s) => document.querySelector(s + ' .dv-peek').hidden", sel) is True)
    page.close()

    # the record view
    page = fresh()
    view(page, sel, "Record")
    page.wait_for_selector(f"{sel} .dv-record-sheet tr[data-p]", timeout=WAIT)
    rows = page.evaluate(LABELS, [sel, ".dv-record-sheet"])
    check("record view: the same list, the view's order, the rest behind N more", [x["label"] for x in rows if x["h"] > 0] == ["Nominal", "Section"], rows)
    m = page.locator(f"{sel} .dv-record-sheet [data-prop-more]")
    check("record view: 'N more properties'", m.count() == 1 and m.inner_text().strip() == "5 more properties", m.inner_text() if m.count() else None)
    m.click()
    rows = page.evaluate(LABELS, [sel, ".dv-record-sheet"])
    check("record view: expands in place, every property", [x["label"] for x in rows if x["h"] > 0] == ["Nominal", "Section", "Datasheet", "Citation", "Chat", "Note", "Weight"], rows)
    check("record view: no tabs", page.locator(f"{sel} .dv-record-sheet [role=tab]").count() == 0)
    view(page, sel, "Record set apart")
    page.wait_for_function("(s) => [...document.querySelectorAll(s + ' .dv-record-sheet tr[data-p]')].some((r) => r.dataset.p === 'chat' && r.getBoundingClientRect().height)", arg=sel, timeout=WAIT)
    rows = [x["label"] for x in page.evaluate(LABELS, [sel, ".dv-record-sheet"]) if x["h"] > 0]
    check("record view: record.visibility reads the same", "Chat" in rows and "Section" not in rows, rows)
    page.close()

    # an existing sectioned view
    page = fresh()
    view(page, sel, "Sectioned")
    open_first(page, sel)
    sec = page.evaluate("""(s) => { const p = document.querySelector(s + ' .dv-peek'); return { head: [...p.querySelectorAll('.dv-peek-section')].map((h) => h.textContent), rows: [...p.querySelectorAll('tr[data-p]')].filter((r) => r.getBoundingClientRect().height).map((r) => r.dataset.p) }; }""", sel)
    check("a view with record.sections keeps its sections; the rest wait behind N more", sec == {"head": ["The value"], "rows": ["nominal", "datasheet"]} and page.locator(f"{sel} .dv-peek [data-prop-more]").count() == 1, sec)
    page.close()

    # the source column a view adds, through the generic seam
    page = browser.new_page(viewport={"width": 1500, "height": 900})
    page.goto(f"{base}/tests/browser/fixtures/source-precedence/part.html")
    page.wait_for_selector("data-views[data-view]", timeout=WAIT)
    sel2 = "#" + page.evaluate("document.querySelector('data-views').id")
    open_first(page, sel2)
    head = page.evaluate(HEADERS, sel2)
    title = page.evaluate("(s) => { const e = document.querySelector(s); return e.model.columns[e.data.titleProperty].label; }", sel2)
    shown = [x["label"] for x in page.evaluate(LABELS, [sel2, ".dv-peek"]) if x["h"] > 0]
    check("a column the view adds ('Nominal source') is a row, where the table draws it", shown == [h for h in head if h != title] and any(h.endswith(" source") for h in shown), {"head": head, "shown": shown})
    page.keyboard.press("Escape")
    page.evaluate("(s) => { document.querySelector(s).selectView('Sources'); }", sel2)
    page.wait_for_timeout(300)
    open_first(page, sel2)
    page.wait_for_timeout(150)
    head = page.evaluate(HEADERS, sel2)
    shown = [x["label"] for x in page.evaluate(LABELS, [sel2, ".dv-peek"]) if x["h"] > 0]
    n_src = page.evaluate("(s) => document.querySelector(s).precedence.order.length", sel2)
    at = [next((i for i, h in enumerate(head) if x in h), -1) for x in shown]
    check("the Sources view: a row per source column, in the table's order", -1 not in at and at == sorted(at) and len(set(at)) == len(at) and len(shown) >= n_src, {"head": head, "shown": shown})
    page.close()


def main() -> int:
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + PAGE, timeout=1)
                break
            except Exception:  # noqa: BLE001 - not up yet
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for name, fn in (("gallery", gallery), ("fixture", fixture)):
                try:
                    fn(browser, base)
                except Exception as err:  # noqa: BLE001 - a miss is a red line, with the rest of the checks still run
                    check(f"{name}: ran to the end", False, repr(err)[:600])
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "inspector-checks.json").write_text(json.dumps(checks, indent=1, default=str), encoding="utf-8")
    bad = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(bad)} of {len(checks)} inspector checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
