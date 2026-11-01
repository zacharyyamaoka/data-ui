"""Source columns (docs/CONTRACT.md §36, docs/peps/0021-source-columns.md), measured in headless Chromium on the built kit, against an
oracle computed here from the fixtures' own JSON (never from the kit's code).

    ~/psu-atlas/.venv/bin/python tests/browser/source_columns_checks.py [OUT_DIR]     # after npm run build

Zach, 2026-10-31: "its just like a column roll up where the left most take precencde. And then to hide them it simply like a view with
thoose columns hidden. The roll up itsself is also then just like a formula.. almost like FIRST Value(of cells, x, y, ...)". "Desired is
notions: pattern where you have 1 property per cell".

FROZEN: committed before the code, so the code answers to it and not the other way round. Nothing here is edited to make a check pass.

The fixtures: source-precedence/part.json and part.base, UNCHANGED (the data file a producer wrote for §36, four sources declared out of
ladder order); source-popover/parts.json (two values with several sources); source-column/servo.json and derived.json; and
source-columns/: jmc.json (robotparts' published JMC 60ASM200-5-1024C datasheet, with its contact's name taken out), jmc.base (robotparts'
site/views/datasheet.base, byte for byte), plain.json and plain.base (no `sources` list at all: plain columns and a formula in Bases'
syntax). What is measured:
  - no mode: no Manage sources, no el.manageSources; a "Sources" view, a tab, one property per source, an ordinary header
  - left-most wins, read off the page alone: every row's Nominal is the first filled source cell to its right
  - a source column is ordinary: hide (Nominal does not move), width, sort, filter, Property visibility
  - dragging a header is precedence, for every row and every view; a hidden source keeps its place; Reset; the URL; storage
  - "<label> source" is an ordinary column; sourceColumn true and false; a derived value names its source
  - the pill: on the formula cell, with the sources hidden, derived from them; a row's pick; right-click and keys
  - a formula in a .base: Bases' syntax, a precedence that lands back in the file's text, a formula data-ui does not run says so
  - editing: an edit goes to that source's column, a formula cell refuses, nothing silently lost, undo restores the file's cell
  - the inspector, 1:1, and record.visibility on source columns
  - robotparts' real datasheet, with its own .base
  - old links and old storage; data with no sources unchanged; light and dark at 1280 and 390 px
Serves the repo root on a free 127.0.0.1 port, stops that server when done, writes OUT_DIR/source-columns-checks.json and exits 1 if
any check fails.
"""

from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "source-columns-checks"
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "browser" / "fixtures"
PAGE = "/tests/browser/fixtures/source-columns/page.html"
WAIT = 15000
checks: list[dict] = []

PART = json.loads((FIX / "source-precedence" / "part.json").read_text(encoding="utf-8"))
PARTS = json.loads((FIX / "source-popover" / "parts.json").read_text(encoding="utf-8"))
JMC = json.loads((FIX / "source-columns" / "jmc.json").read_text(encoding="utf-8"))
PLAIN = json.loads((FIX / "source-columns" / "plain.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the oracle, from the JSON alone
def empty(v):
    return v is None or v == "" or v == []


def ladder_order(data):
    rank = {r["id"]: i for i, r in enumerate(data.get("ladder") or [])}
    ids = list(data["sources"].keys())
    return sorted(ids, key=lambda s: (rank.get(data["sources"][s].get("rung"), len(rank)), ids.index(s)))


def multi(cell):
    return isinstance(cell, dict) and isinstance(cell.get("sources"), list) and len(cell["sources"]) > 0


def entries(cell):
    """{source: entry} for the entries that state a value, the first per source, in the cell's order."""
    out = {}
    for e in (cell.get("sources") if isinstance(cell, dict) else None) or []:
        if e.get("source") and e["source"] not in out and not empty(e.get("value")):
            out[e["source"]] = e
    return out


def winner(cell, order, ov=None, rid=None):
    st = entries(cell)
    if ov and ov.get(rid) in st:
        return ov[rid]
    for s in list(order) + [s for s in st if s not in order]:
        if s in st:
            return s
    return None


def key(e, cell):
    return json.dumps([e.get("value"), e.get("unit", cell.get("unit"))], sort_keys=True)


def conflict(cell):
    st = entries(cell)
    return len({key(e, cell) for e in st.values()}) > 1


def written(e):
    """A value as its source wrote it: its text, else its value."""
    if isinstance(e.get("text"), str) and e["text"]:
        return e["text"]
    v = e.get("value")
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f"{v:,g}" if abs(v) < 1e6 else str(v)
    return str(v)


def with_unit(text, row, cell):
    unit = row.get("unit") or (cell.get("unit") if isinstance(cell, dict) else None)
    return f"{text} {unit}" if unit else text


def nominal_text(data, row, order, ov=None, prop="nominal"):
    c = row.get(prop)
    if multi(c):
        s = winner(c, order, ov, row["id"])
        return "—" if s is None else with_unit(written(entries(c)[s]), row, c)
    if isinstance(c, dict):
        return with_unit(written(c), row, c)
    return "—" if empty(c) else with_unit(str(c), row, None)


def stated_by(data, row, s, prop="nominal"):
    """What source `s`'s column reads for this row: its entry; a plain §22 cell naming that source is that source's statement."""
    c = row.get(prop)
    if multi(c):
        return entries(c).get(s)
    if isinstance(c, dict) and c.get("source") in (s, data["sources"][s]["name"]) and not empty(c.get("value")):
        return c
    return None


def pill(cell, order, ov=None, rid=None):
    """The agree / differs fact: what the pill says, or None for a value fewer than two sources state."""
    st = entries(cell)
    if len(st) < 2:
        return None
    shown = winner(cell, order, ov, rid)
    others = len(st) - 1
    nd = sum(1 for s, e in st.items() if s != shown and key(e, cell) != key(st[shown], cell))
    return f"+{others} · {nd} differ{'s' if nd == 1 else ''}" if nd else f"+{others} agree{'s' if others == 1 else ''}"


def in_place(order, visible):
    """The order with the visible sources in their new order, in the places they held; a hidden source keeps its place."""
    slots = iter(visible)
    want = set(visible)
    return [next(slots) if s in want else s for s in order]


DEFAULT = ladder_order(PART)
S = PART["sources"]
ROWS = {r["id"]: r for r in PART["rows"]}
MULTI2 = sorted(r["id"] for r in PART["rows"] if multi(r["nominal"]) and len(entries(r["nominal"])) >= 2)
CONFLICTS = sorted(r["id"] for r in PART["rows"] if multi(r["nominal"]) and conflict(r["nominal"]))
COL = {s: f"nominal@{s}" for s in S}


# ---------------------------------------------------------------- what the page says
SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"
HEADS = "() => [...document.querySelectorAll('#v thead tr.dv-hleaf th[data-col]')].map((t) => t.dataset.col)"
# every drawn row's cells as the reader reads them: the pill and the pin are not the value
CELLS = """() => Object.fromEntries([...document.querySelectorAll('#v tbody tr[data-id]')].map((tr) => [tr.dataset.id, Object.fromEntries([...tr.querySelectorAll('td[data-col]')].map((td) => {
  const c = td.cloneNode(true);
  for (const x of c.querySelectorAll('.dv-src-dd, .dv-src-pin, .dv-sr, .dv-src-derived, .dv-basis, .dv-row-open')) x.remove();
  return [td.dataset.col, c.textContent.replace(/\\s+/g, ' ').trim()];
}))]))"""
PILLS = """() => Object.fromEntries([...document.querySelectorAll('#v tbody tr[data-id]')].map((tr) => { const b = tr.querySelector('button.dv-src-dd');
  return [tr.dataset.id, b ? { text: b.textContent.replace(/[▾\\s]+/g, ' ').trim(), conflict: b.hasAttribute('data-conflict'), col: b.closest('td').dataset.col } : null]; }))"""
STATES = """() => Object.fromEntries([...document.querySelectorAll('#v tbody tr[data-id]')].map((tr) => [tr.dataset.id, Object.fromEntries([...tr.querySelectorAll('td[data-src-state]')].map((td) => [td.dataset.col, td.dataset.srcState]))]))"""
STATUS = "() => { const s = document.querySelector('#v .dv-status'); return s ? s.textContent.replace(/\\s+/g, ' ').trim() : ''; }"
HASH = "() => Object.fromEntries(new URLSearchParams(location.hash.slice(1)))"
OPEN_MENU = ".dv-itemmenu[role=menu]"


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def settle(page, n=3):
    for _ in range(n):
        page.evaluate(SETTLE)


def wait_rows(page):
    page.wait_for_function("() => window.kitReady && window.v && window.v.dataset.view && window.v.querySelector('tbody tr[data-id]')", timeout=WAIT)
    settle(page)


def fresh(browser, base, query="", width=1280, height=900, dark=False, hash_="", mobile=False):
    """A new context (no storage) on the fixture page."""
    context = browser.new_context(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light", has_touch=mobile, is_mobile=mobile)
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
    context.set_default_timeout(WAIT)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base}{PAGE}{('?' + query) if query else ''}{('#' + hash_) if hash_ else ''}")
    wait_rows(page)
    return context, page, errors


def view_named(page, name):
    page.evaluate("(n) => window.v.selectView(n)", name)
    settle(page)


def heads(page):
    return page.evaluate(HEADS)


def cells(page):
    return page.evaluate(CELLS)


def head(page, col):
    return page.locator(f'#v thead th[data-col="{col}"]')


def cell(page, row, col):
    return page.locator(f'#v tbody tr[data-id="{row}"] td[data-col="{col}"]')


def tab(page, name):
    """A view's tab in the toolbar the page draws (the other toolbar's tab strip is in the DOM, hidden)."""
    return page.locator('#v [role=tab]:visible', has_text=name)


def tabs_of(page):
    return page.evaluate("() => [...document.querySelectorAll('#v [role=tab]')].filter((t) => t.offsetParent !== null).map((t) => t.textContent.trim())")


def on_value(page, row, col):
    """A click on a cell's value, at its left: the pill sits in the same cell, and a click on it opens its menu."""
    cell(page, row, col).click(position={"x": 12, "y": 10})


def menu_hide(page, col):
    """Hide, from the header's own menu: a click on the header, the item in Notion's column menu."""
    head(page, col).click()
    page.wait_for_selector('.dv-colmenu [data-act="hide"], [data-act="hide"]', timeout=WAIT)
    page.locator('[data-act="hide"]').first.click()
    settle(page)


def drag_header(page, col, onto):
    head(page, col).drag_to(head(page, onto))
    settle(page)


def left_most_holds(tag, page, what):
    """From the page alone: the Nominal is the first filled cell among the source columns as drawn, left to right."""
    hs = heads(page)
    drawn = [c for c in hs if c.startswith("nominal@") and c != "nominal@source"]
    bad = {}
    for rid, row in cells(page).items():
        firsts = [row[c] for c in drawn if row.get(c) not in (None, "", "—")]
        if firsts and row.get("nominal") != firsts[0]:
            bad[rid] = {"nominal": row.get("nominal"), "first": firsts[0]}
    check(f"{tag}: {what}: read off the page, every Nominal is the first filled source cell left to right", drawn and not bad, bad or drawn)


def nominals_are(tag, page, data, order, what, ov=None):
    want = {r["id"]: nominal_text(data, r, order, ov) for r in data["rows"]}
    got = {k: v.get("nominal") for k, v in cells(page).items()}
    bad = {k: {"want": want[k], "got": got.get(k)} for k in want if got.get(k) != want[k]}
    check(f"{tag}: {what}: every Nominal is the oracle's", not bad and set(got) == set(want), bad or None)


# ---------------------------------------------------------------- no mode
def no_mode(browser, base):
    context, page, errors = fresh(browser, base)
    tag = "no mode"
    check(f"{tag}: the Datasheet view draws no source column", heads(page) == ["field", "nominal", "nominal@source"], heads(page))
    gone = page.evaluate("""() => ({ button: document.querySelectorAll('#v [data-bar="sources"], #v [data-sources]').length, prop: 'manageSources' in window.v,
      synthetic: document.querySelectorAll('#v th[data-src], #v [data-src-move], #v .dv-src-rank').length })""")
    check(f"{tag}: no Manage sources anywhere: no button, no el.manageSources, no special header", gone == {"button": 0, "prop": False, "synthetic": 0}, gone)
    check(f"{tag}: the file's views, then a Sources view, as a tab", tabs_of(page) == ["Datasheet", "Flat", "Cards", "Sources"], tabs_of(page))
    check(f"{tag}: el.presets says so too; a saved view like any other", [p["name"] for p in page.evaluate("() => window.v.presets")] == ["Datasheet", "Flat", "Cards", "Sources"])
    tab(page, "Sources").click()
    settle(page)
    want = ["field", "nominal"] + [COL[s] for s in DEFAULT]
    check(f"{tag}: the Sources tab: one property per source, best first, after the value they roll up to", heads(page) == want, heads(page))
    labels = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#v thead tr.dv-hleaf th[data-col]')].map((t) => [t.dataset.col, t.querySelector('.dv-th-label').textContent.trim()]))""")
    check(f"{tag}: each column is labelled with its source's name", all(labels.get(COL[s]) == S[s]["name"] for s in DEFAULT), labels)
    shape = page.evaluate("""(col) => { const t = document.querySelector(`#v thead th[data-col="${col}"]`);
      return { sort: t.dataset.sort, drag: t.getAttribute('draggable'), resize: !!t.querySelector('.dv-resize'), scope: t.getAttribute('scope') }; }""", COL["bench"])
    check(f"{tag}: a source's header is an ordinary one: a sort key, draggable, a resize handle", shape == {"sort": COL["bench"], "drag": "true", "resize": True, "scope": "col"}, shape)
    head(page, COL["bench"]).click()
    page.wait_for_selector('[data-act="hide"]', timeout=WAIT)
    check(f"{tag}: a click on it opens the ordinary column menu", page.locator('[data-act="page:filter"]').count() == 1 and page.locator('[data-act="page:sort"]').count() == 1)
    page.keyboard.press("Escape")
    settle(page, 1)
    # ---- the view is a view: Back to the Datasheet, the columns go, and Nominal is what it was
    before = {k: v["nominal"] for k, v in cells(page).items()}
    tab(page, "Datasheet").click()
    settle(page)
    check(f"{tag}: the Datasheet tab again: the source columns are simply not in this view", heads(page) == ["field", "nominal", "nominal@source"], heads(page))
    check(f"{tag}: no value changed", {k: v["nominal"] for k, v in cells(page).items()} == before)
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()


# ---------------------------------------------------------------- one property per source
def source_cells(browser, base):
    context, page, errors = fresh(browser, base)
    tag = "columns"
    view_named(page, "Sources")
    got = cells(page)
    bad = []
    for r in PART["rows"]:
        for s in DEFAULT:
            e = stated_by(PART, r, s)
            want = "—" if e is None else with_unit(written(e), r, r["nominal"])
            if got[r["id"]].get(COL[s]) != want:
                bad.append({"row": r["id"], "source": s, "want": want, "got": got[r["id"]].get(COL[s])})
    check(f"{tag}: every source cell is its source's own statement, as written, its unit beside it", not bad, bad[:4] or None)
    check(f"{tag}: a value keeps its own words: the chat's \"3.8 Nm\"", got["peak_torque"][COL["chat"]].startswith("3.8 Nm"), got["peak_torque"][COL["chat"]])
    check(f"{tag}: a plain §22 cell sits under the source it names", got["encoder"][COL["datasheet"]] == "14-bit magnetic" and got["encoder"][COL["bench"]] == "—", got["encoder"])
    left_most_holds(tag, page, "default")
    nominals_are(tag, page, PART, DEFAULT, "default")
    rows = page.evaluate("() => window.v.data.rows.map((r) => [r.id, r.nominal && r.nominal.sources ? r.nominal.sources : null])")
    want_rows = [[r["id"], r["nominal"].get("sources") if isinstance(r["nominal"], dict) else None] for r in PART["rows"]]
    check(f"{tag}: truthful: every stated entry is exactly the fixture's, and el.data keeps them on the nominal", rows == want_rows, None if rows == want_rows else rows[:2])
    states = page.evaluate(STATES)
    bad = []
    for r in PART["rows"]:
        if not multi(r["nominal"]):
            continue
        st = entries(r["nominal"])
        shown = winner(r["nominal"], DEFAULT)
        for s in DEFAULT:
            want = "none" if s not in st else "shown" if s == shown else "differs" if key(st[s], r["nominal"]) != key(st[shown], r["nominal"]) else "agrees"
            if states.get(r["id"], {}).get(COL[s]) != want:
                bad.append({"row": r["id"], "source": s, "want": want, "got": states.get(r["id"], {}).get(COL[s])})
    check(f"{tag}: agree / differs stays visible on the source cells: shown, differs, agrees, none, as the oracle says", not bad, bad[:4] or None)
    # ---- two values with several sources: a column per value and source, each labelled so the two read apart
    context.close()
    context, page, errors2 = fresh(browser, base, "src=../source-popover/parts.base")
    order = page.evaluate("() => window.v.precedence.order")
    view_named(page, "Sources")
    hs = heads(page)
    want = ["name", "torque"] + [f"torque@{s}" for s in order if any(s in entries(r["torque"]) for r in PARTS["rows"])] + ["mass"] + [f"mass@{s}" for s in order if any(s in entries(r["mass"]) for r in PARTS["rows"])]
    check(f"{tag}: two values with several sources: a column per value and source, each after its own value", hs == want, {"got": hs, "want": want})
    labels = page.evaluate("() => [...document.querySelectorAll('#v thead tr.dv-hleaf th[data-col] .dv-th-label')].map((t) => t.textContent.trim())")
    check(f"{tag}: ... labels that read apart", len(set(labels)) == len(labels), labels)
    check(f"{tag}: no page error", not errors and not errors2, (errors + errors2)[:3])
    context.close()


def hide_and_ordinary(browser, base):
    context, page, errors = fresh(browser, base)
    tag = "ordinary"
    view_named(page, "Sources")
    before = {k: v["nominal"] for k, v in cells(page).items()}
    pills = page.evaluate(PILLS)
    # ---- hide, from the header's own menu: the top source, which is the one most rows read
    menu_hide(page, COL["bench"])
    check(f"{tag}: Hide takes the column out of this view, and out of its order", COL["bench"] not in heads(page) and COL["bench"] not in page.evaluate("() => window.v.view.order"), heads(page))
    check(f"{tag}: hiding a source changes no value: it is only a view", {k: v["nominal"] for k, v in cells(page).items()} == before, None)
    check(f"{tag}: ... and no precedence", page.evaluate("() => window.v.precedence.order") == DEFAULT, page.evaluate("() => window.v.precedence.order"))
    check(f"{tag}: ... and the row's agree / differs fact stays, read from every source, hidden ones too", page.evaluate(PILLS) == pills, page.evaluate(PILLS))
    st = page.evaluate(STATUS)
    check(f"{tag}: ... and says nothing changed", "changed from default" not in st and "changed" not in st, st)
    nominals_are(tag, page, PART, DEFAULT, "with the top source hidden")
    # ---- show it again, as Property visibility does (the end of the order): it comes back in its place
    page.evaluate("(c) => window.v.setView({ order: [...window.v.view.order, c] })", COL["bench"])
    settle(page)
    check(f"{tag}: showing a source puts it back in its place; it is no reorder", heads(page) == ["field", "nominal"] + [COL[s] for s in DEFAULT] and page.evaluate("() => window.v.precedence.order") == DEFAULT, heads(page))
    # ---- the real Property visibility lists it
    page.evaluate("(c) => window.v.setView({ order: window.v.view.order.filter((x) => x !== c) })", COL["chat"])
    settle(page)
    page.locator('#v [data-bar="display"]').click()
    page.wait_for_selector('#v .dv-set-row[data-page="properties"], .dv-set-row[data-page="properties"]', timeout=WAIT)
    page.locator('.dv-set-row[data-page="properties"]').click()
    settle(page, 1)
    listed = page.evaluate("""() => [...document.querySelectorAll('.dv-prop[data-id], [data-prop-id]')].map((x) => x.dataset.id || x.dataset.propId)""")
    check(f"{tag}: Property visibility offers every source column, shown and hidden", all(COL[s] in listed for s in DEFAULT), listed)
    page.keyboard.press("Escape")
    settle(page, 1)
    page.evaluate("(c) => window.v.setView({ order: [...window.v.view.order, c] })", COL["chat"])
    settle(page)
    # ---- width: the handle, the view's columnSize, under the column's own key
    box = page.locator(f'#v thead th[data-col="{COL["datasheet"]}"] .dv-resize').bounding_box()
    w0 = head(page, COL["datasheet"]).bounding_box()["width"]
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + 60, box["y"] + box["height"] / 2, steps=5)
    page.mouse.up()
    settle(page)
    w1 = head(page, COL["datasheet"]).bounding_box()["width"]
    stored = page.evaluate("(c) => (window.v.view.columnSize || {})[c]", COL["datasheet"])
    check(f"{tag}: a source column resizes, measured, stored in columnSize under its own id", abs(w1 - w0 - 55) <= 8 and stored and abs(stored - w1) <= 1, {"w0": w0, "w1": w1, "stored": stored})
    check(f"{tag}: ... and a resize is no reorder", page.evaluate("() => window.v.precedence.order") == DEFAULT)
    # ---- sort: ordinary, shift-click, and by the source's own value, not the nominal's
    page.evaluate("() => window.v.setView({ groupBy: null })")
    settle(page)
    head(page, COL["datasheet"]).click(modifiers=["Shift"])
    settle(page)
    check(f"{tag}: shift-click sorts by the source's column", page.evaluate("() => window.v.view.sort") == [{"property": COL["datasheet"], "direction": "ASC"}], page.evaluate("() => window.v.view.sort"))
    ids = page.evaluate("() => [...document.querySelectorAll('#v tbody tr[data-id]')].map((t) => t.dataset.id)")
    nums = [e["value"] for e in (stated_by(PART, ROWS[i], "datasheet") for i in ids) if e and isinstance(e.get("value"), (int, float))]
    check(f"{tag}: ... the rows really are in that column's order", nums == sorted(nums) and len(nums) >= 5, nums)
    # ---- filter: an ordinary expression on the column, as the Filter menu writes it for a name like this
    page.evaluate("""(c) => window.v.setView({ sort: null, filters: `note[${JSON.stringify(c)}] > 300` })""", COL["bench"])
    settle(page)
    want = sorted(r["id"] for r in PART["rows"] if isinstance((stated_by(PART, r, "bench") or {}).get("value"), (int, float)) and stated_by(PART, r, "bench")["value"] > 300)
    got = sorted(page.evaluate("() => [...document.querySelectorAll('#v tbody tr[data-id]')].map((t) => t.dataset.id)"))
    check(f"{tag}: a filter on a source column keeps the rows the oracle keeps", got == want and len(got) >= 1, {"got": got, "want": want})
    check(f"{tag}: ... and its text is plain Bases: note[\"…\"], which Obsidian reads", 'note["nominal@bench"]' in json.dumps(page.evaluate("() => window.v.view.filters")) or 'note[\\"nominal@bench\\"]' in json.dumps(page.evaluate("() => window.v.view.filters")), page.evaluate("() => window.v.view.filters"))
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()


# ---------------------------------------------------------------- dragging is precedence
def drag_is_precedence(browser, base):
    context, page, errors = fresh(browser, base)
    tag = "drag"
    page.evaluate("() => { window.__events = []; window.v.addEventListener('data-views-precedence', (e) => window.__events.push(e.detail)); }")
    view_named(page, "Sources")
    drag_header(page, COL["chat"], COL["bench"])
    order = ["chat", "bench", "datasheet", "listing"]
    check(f"{tag}: the ordinary header drag: the chat before the bench", heads(page) == ["field", "nominal"] + [COL[s] for s in order], heads(page))
    check(f"{tag}: ... that IS the precedence: el.precedence follows the columns", page.evaluate("() => window.v.precedence.order") == order, page.evaluate("() => window.v.precedence.order"))
    left_most_holds(tag, page, "after the drag")
    nominals_are(tag, page, PART, order, "after the drag")
    check(f"{tag}: it is in the URL (sources=)", page.evaluate(HASH).get("sources") == ",".join(order), page.evaluate(HASH))
    st = page.evaluate(STATUS)
    check(f"{tag}: the status line says so, with Reset, and what it did", "Precedence changed from default" in st and page.locator("#v .dv-status button[data-sources-reset]").count() == 1 and "changed" in st, st)
    ev = page.evaluate("() => window.__events.slice(-1)[0] || null")
    want_changed = sorted(r["id"] for r in PART["rows"] if multi(r["nominal"]) and winner(r["nominal"], DEFAULT) and winner(r["nominal"], order) != winner(r["nominal"], DEFAULT)
                          and key(entries(r["nominal"])[winner(r["nominal"], DEFAULT)], r["nominal"]) != key(entries(r["nominal"])[winner(r["nominal"], order)], r["nominal"]))
    check(f"{tag}: the event names the order and the rows whose value changed", ev and ev.get("order") == order and sorted(ev.get("changed") or []) == want_changed, ev)
    # ---- every view reads the same nominal
    tab(page, "Datasheet").click()
    settle(page)
    nominals_are(tag, page, PART, order, "the Datasheet tab, no source column in it")
    check(f"{tag}: the pills follow it there, with the columns hidden", page.evaluate(PILLS).get("rated_current", {}).get("text") == pill(ROWS["rated_current"]["nominal"], order), page.evaluate(PILLS).get("rated_current"))
    tab(page, "Cards").click()
    page.wait_for_selector("#v .dv-cards-card", timeout=WAIT)
    settle(page)
    card = page.evaluate("""() => [...document.querySelectorAll('#v .dv-cards-card')].map((c) => c.textContent.replace(/\\s+/g, ' ').trim()).find((t) => t.includes('Rated phase current'))""")
    check(f"{tag}: Cards read the same nominal", card and written(entries(ROWS["rated_current"]["nominal"])[winner(ROWS["rated_current"]["nominal"], order)]) in card, card)
    # ---- a hidden source keeps its place when the others move
    tab(page, "Sources").click()
    settle(page)
    check(f"{tag}: back on Sources the columns are in the new order, whichever view moved them", heads(page) == ["field", "nominal"] + [COL[s] for s in order], heads(page))
    menu_hide(page, COL["bench"])
    drag_header(page, COL["listing"], COL["chat"])
    want = in_place(order, ["listing", "chat", "datasheet"])
    check(f"{tag}: a hidden source keeps its place while the others move", page.evaluate("() => window.v.precedence.order") == want, {"got": page.evaluate("() => window.v.precedence.order"), "want": want})
    nominals_are(tag, page, PART, want, "with a source hidden, after a drag")
    page.evaluate("(c) => window.v.setView({ order: [...window.v.view.order, c] })", COL["bench"])
    settle(page)
    check(f"{tag}: shown again, it is where it was", heads(page) == ["field", "nominal"] + [COL[s] for s in want], heads(page))
    order = want
    # ---- a reload: the URL, then this viewer's storage
    page.reload()
    wait_rows(page)
    check(f"{tag}: a reload keeps it (the URL)", page.evaluate("() => window.v.precedence.order") == order, page.evaluate("() => window.v.precedence.order"))
    nominals_are(tag, page, PART, order, "after a reload")
    stored = page.evaluate("() => Object.keys(localStorage).filter((k) => k.startsWith('data-ui/sources/'))")
    check(f"{tag}: it is kept in this viewer's storage, the key it always was", len(stored) == 1, stored)
    page.goto(f"{base}{PAGE}")
    wait_rows(page)
    check(f"{tag}: opened again with no hash, it comes from storage", page.evaluate("() => window.v.precedence.order") == order, page.evaluate("() => window.v.precedence.order"))
    view_named(page, "Sources")
    check(f"{tag}: ... and the columns follow", heads(page) == ["field", "nominal"] + [COL[s] for s in order], heads(page))
    # ---- Reset
    page.locator("#v .dv-status button[data-sources-reset]").click()
    settle(page)
    check(f"{tag}: Reset: the default order, the columns with it", page.evaluate("() => window.v.precedence.order") == DEFAULT and heads(page) == ["field", "nominal"] + [COL[s] for s in DEFAULT], heads(page))
    check(f"{tag}: ... the status line and the URL clean, storage empty", "changed from default" not in page.evaluate(STATUS) and "sources" not in page.evaluate(HASH)
          and page.evaluate("() => Object.keys(localStorage).filter((k) => k.startsWith('data-ui/sources/')).length") == 0, page.evaluate(STATUS))
    nominals_are(tag, page, PART, DEFAULT, "after Reset")
    # ---- the same drag on any view: a saved view that names two sources, by hand
    page.evaluate("""() => window.v.addView({ type: 'table', name: 'Two sources', order: ['field', 'nominal@datasheet', 'nominal', 'nominal@chat'] })""")
    settle(page)
    check(f"{tag}: a source need not sit beside the value; the file names the slots", heads(page) == ["field", "nominal@datasheet", "nominal", "nominal@chat"], heads(page))
    drag_header(page, "nominal@chat", "nominal@datasheet")
    got = page.evaluate("() => window.v.precedence.order")
    check(f"{tag}: dragging a source past another changes those two, every other source keeps its place", got == in_place(DEFAULT, ["chat", "datasheet"]), got)
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()


def old_state(browser, base):
    tag = "old links"
    order = ["chat", "bench", "datasheet", "listing"]
    context, page, errors = fresh(browser, base, hash_="sources=" + ",".join(order) + "&picks=rated_current:listing")
    got = page.evaluate("() => window.v.precedence")
    check(f"{tag}: a link from before opens the same state", got["order"] == order and got["ov"] == {"rated_current": "listing"}, got)
    nominals_are(tag, page, PART, order, "from the link", ov={"rated_current": "listing"})
    context.close()
    context, page, errors2 = fresh(browser, base, "no-url")
    path = urllib.parse.urlparse(page.url).path
    page.evaluate("([p, o]) => localStorage.setItem(`data-ui/sources/${p}/acme-qdd80`, JSON.stringify({ order: o, ov: { max_speed: 'chat' } }))", [path, order])
    page.reload()
    wait_rows(page)
    got = page.evaluate("() => window.v.precedence")
    check(f"{tag}: what a returning reader kept still comes back", got["order"] == order and got["ov"] == {"max_speed": "chat"}, got)
    check(f"{tag}: no page error", not errors and not errors2, (errors + errors2)[:3])
    context.close()


# ---------------------------------------------------------------- the "<label> source" column is a column
def source_column(browser, base):
    context, page, errors = fresh(browser, base, "persist=local")
    tag = "Nominal source"
    t = head(page, "nominal@source").inner_text().strip()
    check(f"{tag}: an existing .base keeps its column, right after the value", heads(page) == ["field", "nominal", "nominal@source"] and t == "Nominal source", t)
    links = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#v tbody tr[data-id]')].map((tr) => { const td = tr.querySelector('td[data-col="nominal@source"]'); const a = td.querySelector('a');
      return [tr.dataset.id, { a: a ? a.getAttribute('href') : null, text: td.textContent.replace(/\\s+/g, ' ').trim(), label: !!td.querySelector('.dv-src-label') }]; }))""")
    bad = {}
    for r in PART["rows"]:
        if not multi(r["nominal"]):
            continue
        s = winner(r["nominal"], DEFAULT)
        if s is None:
            continue
        url = (entries(r["nominal"])[s].get("sourceUrl")) or S[s].get("url") or ""
        want = {"a": url, "text": S[s]["name"], "label": False} if url.startswith("https://") else {"a": None, "text": S[s]["name"], "label": True}
        if links.get(r["id"]) != want:
            bad[r["id"]] = {"want": want, "got": links.get(r["id"])}
    check(f"{tag}: names the source that won: a link, a private one a plain label", not bad, bad or None)
    # ---- ordinary: sort and filter it, hide it
    page.evaluate("() => window.v.setView({ groupBy: null, filters: 'note[\"nominal@source\"] == \"Supplier chat\"' })")
    settle(page)
    want = sorted(r["id"] for r in PART["rows"] if multi(r["nominal"]) and winner(r["nominal"], DEFAULT) == "chat")
    got = sorted(page.evaluate("() => [...document.querySelectorAll('#v tbody tr[data-id]')].map((t) => t.dataset.id)"))
    check(f"{tag}: an ordinary filter on it keeps the rows that source won", got == want and len(got) >= 1, {"got": got, "want": want})
    page.evaluate("() => window.v.setView({ groupBy: { property: 'section' }, filters: null })")
    settle(page)
    menu_hide(page, "nominal@source")
    check(f"{tag}: hide it from its header: gone", "nominal@source" not in heads(page), heads(page))
    page.reload()
    wait_rows(page)
    check(f"{tag}: a kept view keeps it hidden (persist=local)", "nominal@source" not in heads(page), heads(page))
    check(f"{tag}: ... the agree / differs fact does not go with it", sorted(k for k, v in page.evaluate(PILLS).items() if v) == MULTI2, page.evaluate(PILLS))
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()
    # ---- the two declarations, on data that says so
    for flag, want_col in ((True, True), (False, False)):
        context, page, errors = fresh(browser, base, "no-url")
        page.evaluate("""(flag) => fetch('../source-precedence/part.json').then((r) => r.json()).then((d) => { d.sourceColumn = flag; window.v.data = d; })""", flag)
        wait_rows(page)
        check(f"{tag}: sourceColumn: {str(flag).lower()} on several-source data: {'the column' if want_col else 'no column'} in a view that does not name it", ("nominal@source" in heads(page)) == want_col, heads(page))
        view_named(page, "Sources")
        check(f"{tag}: sourceColumn: {str(flag).lower()}: the Sources view is there either way", COL["bench"] in heads(page), heads(page))
        check(f"{tag}: sourceColumn: {str(flag).lower()}: no page error", not errors, errors[:3])
        context.close()
    context, page, errors = fresh(browser, base, "src=../source-column/servo.base&no-url")
    check(f"{tag}: sourceColumn: true on one-source data: the column, after the first column that names a source", heads(page) == ["field", "section", "nominal", "nominal@source"], heads(page))
    tabs = tabs_of(page)
    check(f"{tag}: ... nothing to roll up: no Sources view, no pill, el.precedence null", tabs == ["Datasheet"] and page.locator("#v button.dv-src-dd").count() == 0 and page.evaluate("() => window.v.precedence") is None, tabs)
    context.close()
    context, page, errors = fresh(browser, base, "src=../source-column/derived.base&no-url")
    marks = page.evaluate("""() => [...document.querySelectorAll('#v td[data-col="nominal@source"] .dv-src-derived')].map((m) => m.textContent.trim())""")
    derived = json.loads((FIX / "source-column" / "derived.json").read_text(encoding="utf-8"))
    want = sum(1 for r in derived["rows"] if isinstance(r.get("nominal"), dict) and (r["nominal"].get("basis") == "derived" or any(e.get("basis") == "derived" for e in entries(r["nominal"]).values())) and (r["nominal"].get("source") or r["nominal"].get("sourceUrl") or r["nominal"].get("sourcePage") or r["nominal"].get("sources")))
    check(f"{tag}: basis: derived: the column names what it came from, with the quiet word", marks and all(m == "derived" for m in marks) and len(marks) >= 1 and len(marks) <= want, {"marks": marks, "oracle at most": want})
    check(f"{tag}: no page error (derived)", not errors, errors[:3])
    context.close()


# ---------------------------------------------------------------- the pill
def the_pill(browser, base):
    context, page, errors = fresh(browser, base)
    tag = "pill"
    got = page.evaluate(PILLS)
    want = {r["id"]: pill(r["nominal"], DEFAULT) for r in PART["rows"] if multi(r["nominal"])}
    bad = {k: {"want": want.get(k), "got": got.get(k)} for k in got if (got[k] or {}).get("text") != want.get(k)}
    check(f"{tag}: with the sources hidden, agree / differs on exactly the rows with 2+ sources, as the oracle counts", not bad, bad or None)
    check(f"{tag}: it is a cell of the formula column, nowhere else", all(v["col"] == "nominal" for v in got.values() if v), got)
    check(f"{tag}: marked exactly where the sources disagree", sorted(k for k, v in got.items() if v and v["conflict"]) == CONFLICTS, got)
    # ---- a row's pick: the pill's menu, a mouse
    page.locator('#v tbody tr[data-id="rated_current"] button.dv-src-dd').click()
    page.wait_for_selector(OPEN_MENU, timeout=WAIT)
    items = page.evaluate("""() => [...document.querySelectorAll('.dv-itemmenu[role=menu] [role=menuitemradio]')].map((b) => ({ source: b.dataset.source, checked: b.getAttribute('aria-checked') }))""")
    st = [s for s in DEFAULT if s in entries(ROWS["rated_current"]["nominal"])]
    check(f"{tag}: its menu lists the sources in precedence order, the one in use checked", [i["source"] for i in items] == st and [i["checked"] for i in items] == ["true" if s == st[0] else "false" for s in st], items)
    before = {k: v["nominal"] for k, v in cells(page).items()}
    page.locator('.dv-itemmenu [role=menuitemradio][data-source="listing"]').click()
    settle(page)
    ov = {"rated_current": "listing"}
    nominals_are(tag, page, PART, DEFAULT, "a pick for one row", ov=ov)
    after = {k: v["nominal"] for k, v in cells(page).items()}
    check(f"{tag}: a pick changes that row only", sorted(k for k in after if after[k] != before[k]) == ["rated_current"], after)
    check(f"{tag}: it is in the URL, and the row says chosen by hand", page.evaluate(HASH).get("picks") == "rated_current:listing" and page.locator('#v tbody tr[data-id="rated_current"] td[data-col="nominal"] .dv-src-pin').count() == 1, page.evaluate(HASH))
    check(f"{tag}: the status line: 1 chosen by hand · Clear", "1 chosen by hand" in page.evaluate(STATUS) and page.locator("#v .dv-status button[data-sources-clear]").count() == 1, page.evaluate(STATUS))
    check(f"{tag}: the focus is back on the row's pill", page.evaluate("""() => { const a = document.activeElement; return !!(a && a.matches('button.dv-src-dd') && a.closest('tr[data-id="rated_current"]')); }"""))
    view_named(page, "Sources")
    states = page.evaluate(STATES)["rated_current"]
    check(f"{tag}: on Sources the picked cell reads shown, and is marked as a pick", states[COL["listing"]] == "shown" and cell(page, "rated_current", COL["listing"]).get_attribute("data-override") is not None, states)
    left = {k: v for k, v in cells(page).items() if k != "rated_current"}
    check(f"{tag}: a pick is that row's own; left-most still holds for every other row", all(left[k]["nominal"] == nominal_text(PART, ROWS[k], DEFAULT) for k in left))
    view_named(page, "Datasheet")
    # ---- by keyboard: Enter opens, Escape gives the focus back, arrows and Enter pick; Back to precedence
    page.locator('#v tbody tr[data-id="max_speed"] button.dv-src-dd').focus()
    page.keyboard.press("Enter")
    page.wait_for_selector(OPEN_MENU, timeout=WAIT)
    check(f"{tag}: keyboard: Enter opens it with the focus inside", page.evaluate("() => document.querySelector('.dv-itemmenu[role=menu]').contains(document.activeElement)"))
    page.keyboard.press("Escape")
    settle(page, 1)
    check(f"{tag}: keyboard: Escape closes it and gives the focus back", page.locator(".dv-itemmenu").count() == 0 and page.evaluate("""() => { const a = document.activeElement; return !!(a && a.matches('button.dv-src-dd') && a.closest('tr[data-id="max_speed"]')); }"""))
    page.keyboard.press("Enter")
    page.wait_for_selector(OPEN_MENU, timeout=WAIT)
    st2 = [s for s in DEFAULT if s in entries(ROWS["max_speed"]["nominal"])]
    # a source with an address has its link as a menu item of its own, right after its row (§36): the arrows walk those too
    for _ in range(4):
        page.keyboard.press("ArrowDown")
        if page.evaluate("() => document.activeElement.dataset.source") == st2[1]:
            break
    page.keyboard.press("Enter")
    settle(page)
    ov["max_speed"] = st2[1]
    check(f"{tag}: keyboard: ArrowDown and Enter pick the second source", page.evaluate("() => window.v.precedence.ov") == ov, page.evaluate("() => window.v.precedence.ov"))
    page.locator('#v tbody tr[data-id="max_speed"] button.dv-src-dd').click()
    page.wait_for_selector(".dv-itemmenu [data-src-back]", timeout=WAIT)
    page.locator(".dv-itemmenu [data-src-back]").click()
    settle(page)
    del ov["max_speed"]
    check(f"{tag}: Back to precedence clears that row's pick only", page.evaluate("() => window.v.precedence.ov") == ov, page.evaluate("() => window.v.precedence.ov"))
    # ---- the right-click is the same menu
    cell(page, "peak_torque", "nominal").click(button="right")
    page.wait_for_selector(".dv-itemmenu.dv-src-pop[role=menu]", timeout=WAIT)
    names = page.evaluate("() => [...document.querySelectorAll('.dv-itemmenu.dv-src-pop .dv-src-pop-name')].map((n) => n.textContent.trim())")
    check(f"{tag}: a right-click on the value lists every source", names == [S[s]["name"] for s in DEFAULT if s in entries(ROWS["peak_torque"]["nominal"])], names)
    page.keyboard.press("Escape")
    settle(page, 1)
    page.locator("#v .dv-status button[data-sources-clear]").click()
    settle(page)
    check(f"{tag}: Clear removes every pick", page.evaluate("() => window.v.precedence.ov") == {} and "chosen by hand" not in page.evaluate(STATUS) and "picks" not in page.evaluate(HASH), page.evaluate(STATUS))
    nominals_are(tag, page, PART, DEFAULT, "after Clear")
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()


# ---------------------------------------------------------------- a formula in a .base
def base_formula(browser, base):
    context, page, errors = fresh(browser, base, "src=plain.base&no-url&hook")
    tag = "formula"
    order = ["datasheet", "citation", "measured"]
    R = {r["id"]: r for r in PLAIN["rows"]}

    def want(ids):
        out = {}
        for rid, r in R.items():
            found = next((r[c] for c in ids if not empty(r.get(c).get("value") if isinstance(r.get(c), dict) else r.get(c))), None)
            found = found.get("value") if isinstance(found, dict) else found
            out[rid] = "—" if found is None else f"{found:g}"
        return out

    check(f"{tag}: formula.nominal is a column, under its displayName", heads(page)[:2] == ["field", "formula.nominal"] and head(page, "formula.nominal").inner_text().strip() == "Nominal", heads(page))
    got = {k: v.get("formula.nominal") for k, v in cells(page).items()}
    check(f"{tag}: the first filled column, in the formula's order; 0 is a value, an empty text is not", got == want(order), {"got": got, "want": want(order)})
    pills = page.evaluate(PILLS)
    check(f"{tag}: the pill reads the columns: 2 differ, agree, none with one column filled",
          pills["all"]["text"] == "+2 · 2 differ" and pills["all"]["conflict"] and pills["agree"]["text"] == "+1 agrees" and not pills["agree"]["conflict"] and pills["later"] is None and pills["none"] is None, pills)
    prov = page.evaluate("""() => { const td = document.querySelector('#v tbody tr[data-id="rich"] td[data-col="formula.nominal"]'); const h = td.matches('[data-provenance]') ? td : td.querySelector('[data-provenance]'); return h ? JSON.parse(h.getAttribute('data-provenance')) : null; }""")
    check(f"{tag}: a rich cell keeps its provenance through the formula", prov and prov.get("sourceUrl") == "https://example.com/acme.pdf" and prov.get("note") == "page 2", prov)
    no = cell(page, "all", "formula.doubled")
    check(f"{tag}: a formula data-ui does not run draws a dash and says why, never a made-up value", no.inner_text().strip() == "—" and "Obsidian" in (no.get_attribute("title") or ""), no.get_attribute("title"))
    tab(page, "Sources").click()
    settle(page)
    check(f"{tag}: the file's own Sources view: no second one is added", tabs_of(page) == ["Datasheet", "Sources", "Cards", "Headline"], tabs_of(page))
    drag_header(page, "citation", "datasheet")
    order = ["citation", "datasheet", "measured"]
    check(f"{tag}: dragging a column the formula reads is its precedence", page.evaluate("() => window.v.precedence.order") == order and heads(page) == ["field"] + order, page.evaluate("() => window.v.precedence"))
    page.wait_for_function("() => window.saved.length > 0", timeout=WAIT)
    settle(page)
    text = page.evaluate("() => window.saved[window.saved.length - 1].text")
    check(f"{tag}: the precedence stays visible text: the file's formula is rewritten, its spelling kept", "'[citation, datasheet, measured].filter(!value.isEmpty())[0]'" in text, text)
    check(f"{tag}: ... and the rest of the file stays as written, comments and all", "# Zach's \"column roll up" in text and "doubled: 'datasheet * 2'" in text and "displayName: Nominal" in text, text)
    tab(page, "Datasheet").click()
    settle(page)
    got = {k: v.get("formula.nominal") for k, v in cells(page).items()}
    check(f"{tag}: Datasheet follows", got == want(order), {"got": got, "want": want(order)})
    # ---- a headline KPI stays the producer's: a formula is for display columns
    view_named(page, "Headline")
    page.wait_for_function("() => document.querySelector('#v .dv-stage').textContent.trim().length > 0", timeout=WAIT)
    settle(page)
    stage = page.evaluate("() => document.querySelector('#v .dv-stage').textContent.replace(/\\s+/g, ' ').trim()")
    check(f"{tag}: a KPI naming a formula draws no number: a headline is the producer's", "—" in stage and not any(ch.isdigit() for ch in stage), stage)
    view_named(page, "Datasheet")
    # ---- the new text alone gives the same page: nothing else holds the precedence
    page.evaluate("""async (text) => { document.querySelector('#v').remove(); localStorage.clear(); const d = await (await fetch('plain.json')).json();
      const v = document.createElement('data-views'); v.id = 'v'; v.setAttribute('no-url', ''); v.setAttribute('toolbar', 'bar'); v.setAttribute('views', 'tabs');
      document.body.append(v); v.baseText = text; v.base = kit.parseBase(text); v.data = d; window.v = v; }""", text)
    wait_rows(page)
    view_named(page, "Datasheet")  # the saved file remembers the view it was saved on (§37's defaultView)
    got = {k: v.get("formula.nominal") for k, v in cells(page).items()}
    check(f"{tag}: the saved text, read again by a new element, gives the same values", got == want(order), {"got": got, "want": want(order)})
    pre = page.evaluate("() => window.v.precedence")
    check(f"{tag}: ... and that order is now the default: nothing to Reset", pre["order"] == order and pre["default"] == order and "changed from default" not in page.evaluate(STATUS), pre)
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()
    # ---- a file that states the precedence of a `sources` list, and a view that gives it
    context, page, errors = fresh(browser, base, "no-url")
    page.evaluate("""() => { const b = window.v.base; window.v.base = { ...b, formulas: { nominal: '[note["nominal@datasheet"], note["nominal@chat"]].filter(value.isType("boolean") || !value.isEmpty())[0]' } }; }""")
    wait_rows(page)
    got = page.evaluate("() => window.v.precedence")
    check(f"{tag}: a formula on a `sources` value states the default, the other sources keeping their ladder places", got["default"] == in_place(DEFAULT, ["datasheet", "chat"]), got)
    nominals_are(tag, page, PART, got["default"], "from the file's formula")
    check(f"{tag}: no page error (sources)", not errors, errors[:3])
    context.close()
    context, page, errors = fresh(browser, base, "no-url")
    page.evaluate("""() => { const b = window.v.base; window.v.base = { ...b, views: [...b.views, { type: 'table', name: 'Chat first', order: ['field', 'nominal@chat', 'nominal@datasheet', 'nominal'] }] }; }""")
    wait_rows(page)
    got = page.evaluate("() => window.v.precedence")
    check(f"{tag}: no formula: a view's left-to-right order is the default", got["default"] == in_place(DEFAULT, ["chat", "datasheet"]), got)
    check(f"{tag}: ... and a file that names source columns gets no second Sources view", tabs_of(page) == ["Datasheet", "Flat", "Cards", "Chat first"], tabs_of(page))
    context.close()
    # ---- `p@*`: the file names every source of a value, whatever they are this time (RobotParts' one .base across a thousand parts)
    context, page, errors = fresh(browser, base, "no-url")
    page.evaluate("""() => { const b = window.v.base; window.v.base = { ...b, views: [{ type: 'table', name: 'All sources', order: ['field', 'nominal', 'nominal@*'] }] }; }""")
    wait_rows(page)
    check(f"{tag}: nominal@* in a view's order is every source of it, in precedence order", heads(page) == ["field", "nominal"] + [COL[s] for s in DEFAULT], heads(page))
    check(f"{tag}: no page error (wildcard)", not errors, errors[:3])
    context.close()


# ---------------------------------------------------------------- editing
def editing(browser, base):
    tag = "edit"

    def held(page, row):
        return page.evaluate("(r) => JSON.parse(JSON.stringify(window.v._rawRow(r).nominal ?? null))", row)

    def type_in(page, row, col, text):
        cell(page, row, col).click()
        page.wait_for_selector("#v .dv-celledit", timeout=WAIT)
        page.keyboard.press("Control+A")
        if text == "":
            page.keyboard.press("Delete")
        else:
            page.keyboard.type(text)
        page.keyboard.press("Enter")
        settle(page)

    context, page, errors = fresh(browser, base, "editable&no-url")
    view_named(page, "Sources")
    # ---- an edit goes to that source's own column
    type_in(page, "peak_torque", COL["bench"], "3.2")
    after = held(page, "peak_torque")
    bench = next(e for e in after["sources"] if e["source"] == "bench")
    check(f"{tag}: typed in the bench's column, it lands on the bench's entry", bench["value"] == 3.2 or bench["value"] == "3.2", after)
    check(f"{tag}: ... the entry's old text does not stay to contradict it, and what the source said about itself does", "text" not in bench and bench.get("asOf") == "2026-10-21", bench)
    others = [e for e in after["sources"] if e["source"] != "bench"]
    check(f"{tag}: ... every other entry is exactly the fixture's", others == [e for e in ROWS["peak_torque"]["nominal"]["sources"] if e["source"] != "bench"], others)
    check(f"{tag}: ... the source's column shows it, and the formula follows, the bench being first", cells(page)["peak_torque"][COL["bench"]] == "3.2 N·m" and cells(page)["peak_torque"]["nominal"] == "3.2 N·m", cells(page)["peak_torque"])
    # ---- a source a row has no value from: a new entry; nothing else moves
    type_in(page, "kt", COL["chat"], "0.2")
    after = held(page, "kt")
    check(f"{tag}: typed in an empty source cell: a new entry, the others kept", [e["source"] for e in after["sources"]] == ["datasheet", "chat"] and after["sources"][0] == ROWS["kt"]["nominal"]["sources"][0], after)
    check(f"{tag}: ... the value is not silently lost: the column shows it; the nominal stays the better source's", cells(page)["kt"][COL["chat"]].startswith("0.2") and cells(page)["kt"]["nominal"].startswith("0.14"), cells(page)["kt"])
    # ---- clearing: the statement is withdrawn; the nominal falls to the next source
    type_in(page, "mass", COL["bench"], "")
    check(f"{tag}: cleared, the source no longer states it, and the next source is nominal", cells(page)["mass"][COL["bench"]] == "—" and cells(page)["mass"]["nominal"].startswith("400"), cells(page)["mass"])
    # ---- a formula cell does not edit: it says why, keeps what was typed, and nothing changed
    was = held(page, "rated_current")
    on_value(page, "rated_current", "nominal")
    page.wait_for_selector("#v .dv-celledit", timeout=WAIT)
    page.keyboard.press("Control+A")
    page.keyboard.type("99")
    page.keyboard.press("Enter")
    settle(page)
    msg = page.locator("#v .dv-celledit .dv-ed-msg").inner_text()
    typed = page.evaluate("document.activeElement.value")
    check(f"{tag}: a formula cell refuses, saying why, with what was typed still there", "comes from its sources" in msg and typed == "99", msg)
    page.keyboard.press("Escape")
    settle(page)
    check(f"{tag}: ... and nothing changed", held(page, "rated_current") == was, held(page, "rated_current"))
    # ---- a plain cell in the same column stays a plain cell
    type_in(page, "encoder", "nominal", "15-bit magnetic")
    check(f"{tag}: a plain cell in the formula's column stays editable: it reads no other column", cells(page)["encoder"]["nominal"].startswith("15-bit"), cells(page)["encoder"])
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()
    # ---- a plain §22 cell: its own source's column is that cell; another source's column keeps it as a statement of its own
    context, page, errors = fresh(browser, base, "editable&no-url")
    view_named(page, "Sources")
    type_in(page, "encoder", COL["datasheet"], "12-bit magnetic")
    was = next(r for r in PART["rows"] if r["id"] == "encoder")["nominal"]
    after = held(page, "encoder")
    check(f"{tag}: a plain cell, in the column of the source it names: the same cell, its value changed", {**was, "value": "12-bit magnetic"} == {**after, **({"text": was["text"]} if "text" in was else {})} and "text" not in after, after)
    type_in(page, "encoder", COL["bench"], "13-bit magnetic")
    after = held(page, "encoder")
    vals = {e["source"]: e["value"] for e in (after.get("sources") or [])} if isinstance(after, dict) else {}
    check(f"{tag}: in another source's column: two statements now; the first is not lost", vals.get("bench") == "13-bit magnetic" and "12-bit magnetic" in vals.values(), after)
    check(f"{tag}: ... both on the page, the pill says they differ", cells(page)["encoder"][COL["bench"]] == "13-bit magnetic" and "12-bit magnetic" in cells(page)["encoder"].values() and page.evaluate(PILLS)["encoder"]["conflict"], cells(page)["encoder"])
    context.close()
    # ---- the host hears the whole cell, under the property it stored
    context, page, errors = fresh(browser, base, "editable&no-url&accept")
    view_named(page, "Sources")
    type_in(page, "peak_torque", COL["bench"], "3.3")
    log = page.evaluate("() => window.edits")
    check(f"{tag}: acceptEdit hears one edit: the row's stored property, whole, sources and all", len(log) == 1 and list(log[0]["set"]) == ["nominal"] and len(log[0]["set"]["nominal"]["sources"]) == 4, log)
    on_value(page, "rated_current", "nominal")
    page.wait_for_selector("#v .dv-celledit", timeout=WAIT)
    page.keyboard.press("Control+A")
    page.keyboard.type("99")
    page.keyboard.press("Enter")
    settle(page)
    check(f"{tag}: a refused formula edit reaches no hook", len(page.evaluate("() => window.edits")) == 1, page.evaluate("() => window.edits"))
    page.keyboard.press("Escape")
    settle(page)
    answer = page.evaluate("""() => window.v.propose({ id: 'rated_current', set: { nominal: 12 } })""")
    check(f"{tag}: a script's edit of a formula cell is refused the same way", answer["ok"] is False and "comes from its sources" in answer["reason"], answer)
    context.close()
    # ---- undo and redo: the cell as the file holds it, to the byte
    context, page, errors = fresh(browser, base, "edit-toggle&no-url")
    page.locator("#v [data-edit-switch]:visible").click()
    settle(page)
    view_named(page, "Sources")
    type_in(page, "peak_torque", COL["bench"], "3.4")
    type_in(page, "kt", COL["chat"], "0.2")
    page.locator("#v .dv-status").click()
    page.keyboard.press("Control+z")
    settle(page)
    page.keyboard.press("Control+z")
    settle(page)
    check(f"{tag}: undo gives back each cell exactly as it was: text, note, every field", held(page, "peak_torque") == ROWS["peak_torque"]["nominal"] and held(page, "kt") == ROWS["kt"]["nominal"], held(page, "peak_torque"))
    page.keyboard.press("Control+Shift+z")
    settle(page)
    check(f"{tag}: redo brings the edit back", cells(page)["peak_torque"][COL["bench"]] == "3.4 N·m", cells(page)["peak_torque"])
    # ---- a block pasted across source columns: each to its own; the formula column is locked, and counted
    page.evaluate("""async () => { await navigator.clipboard.write([new ClipboardItem({ 'text/plain': new Blob(['9\\t8\\n7\\t6\\n'], { type: 'text/plain' }), 'text/html': new Blob(['<table><tbody><tr><td>9</td><td>8</td></tr><tr><td>7</td><td>6</td></tr></tbody></table>'], { type: 'text/html' }) })]); }""")
    cell(page, "rated_torque", COL["bench"]).click()
    page.wait_for_selector("#v .dv-celledit", timeout=WAIT)
    page.keyboard.press("Control+V")
    settle(page)
    page.keyboard.press("Escape")
    settle(page)
    got = cells(page)
    check(f"{tag}: a pasted block lands on each source's own column", got["rated_torque"][COL["bench"]].startswith("9") and got["rated_torque"][COL["datasheet"]].startswith("8") and got["max_speed"][COL["bench"]].startswith("7") and got["max_speed"][COL["datasheet"]].startswith("6"), {k: got[k] for k in ("rated_torque", "max_speed")})
    context.close()


# ---------------------------------------------------------------- the inspector
def inspector(browser, base):
    context, page, errors = fresh(browser, base)
    tag = "inspector"

    def shown(page):
        return page.evaluate("""() => { const p = document.querySelector('#v .dv-peek'); return { rows: [...p.querySelectorAll('table.dv-fields:not(.dv-prop-rest) tr[data-p]')].map((r) => r.dataset.p), rest: [...p.querySelectorAll('.dv-prop-rest tr[data-p]')].map((r) => r.dataset.p) }; }""")

    def values(page):
        return page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#v .dv-peek tr[data-p]')].map((r) => [r.dataset.p, r.querySelector('td').textContent.replace(/\\s+/g, ' ').trim()]))""")

    page.evaluate("() => window.v.openPeek('rated_current')")
    page.wait_for_selector("#v .dv-peek:not([hidden]) tr[data-p]", timeout=WAIT)
    settle(page)
    got = shown(page)
    check(f"{tag}: Datasheet: 1:1 with the columns", got["rows"] == ["nominal", "nominal@source"], got)
    check(f"{tag}: ... the sources wait behind N more properties, one row each", all(COL[s] in got["rest"] for s in DEFAULT), got)
    words = page.locator("#v .dv-peek [data-prop-more]").inner_text().strip()
    check(f"{tag}: ... counted", words.endswith("more properties") and int(words.split()[0]) == len(got["rest"]), words)
    v = values(page)
    check(f"{tag}: each source's row is its own statement", v[COL["listing"]].startswith("10") and v[COL["datasheet"]].startswith("16.0") and v[COL["bench"]] == "—", v)
    check(f"{tag}: the value's row still says agree / differs", "differ" in v["nominal"], v["nominal"])
    # ---- record.visibility works on a source column
    page.evaluate("(c) => window.v.setView({ record: { visibility: { [c]: 'show' } } })", COL["listing"])
    settle(page)
    check(f"{tag}: record.visibility show puts a source in the inspector, with no column", COL["listing"] in shown(page)["rows"] and COL["listing"] not in heads(page), shown(page))
    page.evaluate("() => window.v.setView({ record: null })")
    settle(page)
    page.evaluate("() => window.v.closePeek()")
    settle(page, 1)
    view_named(page, "Sources")
    page.evaluate("() => window.v.openPeek('rated_current')")
    page.wait_for_selector("#v .dv-peek:not([hidden]) tr[data-p]", timeout=WAIT)
    settle(page)
    got = shown(page)
    want = [c for c in heads(page) if c != "field"]
    check(f"{tag}: Sources: 1:1 with the columns, in their order", got["rows"] == want, {"got": got["rows"], "want": want})
    page.evaluate("(c) => window.v.setView({ record: { visibility: { [c]: 'hide' } } })", COL["bench"])
    settle(page)
    got = shown(page)
    check(f"{tag}: record.visibility hide takes it out of the inspector and leaves its column", COL["bench"] not in got["rows"] and COL["bench"] in got["rest"] and COL["bench"] in heads(page), got)
    page.evaluate("() => window.v.setView({ record: null })")
    settle(page)
    # ---- the order follows a drag
    page.evaluate("() => window.v.closePeek()")
    settle(page, 1)
    drag_header(page, COL["chat"], COL["bench"])
    page.evaluate("() => window.v.openPeek('rated_current')")
    page.wait_for_selector("#v .dv-peek:not([hidden]) tr[data-p]", timeout=WAIT)
    settle(page)
    want = [c for c in heads(page) if c != "field"]
    check(f"{tag}: a dragged source moves in the inspector too", shown(page)["rows"] == want, shown(page))
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()


# ---------------------------------------------------------------- robotparts' real datasheet
def robotparts(browser, base):
    tag = "JMC"
    q = "src=jmc.base&data=jmc.json&no-url&views=tabs"
    context, page, errors = fresh(browser, base, q)
    order = ladder_order(JMC)
    R = {r["id"]: r for r in JMC["rows"]}
    text = (FIX / "source-columns" / "jmc.base").read_text(encoding="utf-8")
    check(f"{tag}: robotparts' own .base: no formula, no source column named: it needs no change", "formulas" not in text and "nominal@" not in text, None)
    check(f"{tag}: its views keep the column it asked for, after Nominal", heads(page)[:3] == ["field", "nominal", "nominal@source"], heads(page))
    got = {k: v.get("nominal") for k, v in cells(page).items()}
    check(f"{tag}: by the ladder, a related model's drawing is last: the selection list's values show", (got["peak_torque"], got["rated_phase_current"], got["rotor_inertia"]) == ("1.3 N·m", "10 A", "0.183 kg·cm²"), got)
    nominals = {r["id"]: nominal_text(JMC, r, order) for r in JMC["rows"]}
    bad = {k: {"want": nominals[k], "got": got.get(k)} for k in got if got[k] != nominals[k]}
    check(f"{tag}: every drawn row's Nominal is the oracle's", not bad and len(got) >= 12, bad or len(got))
    pills = page.evaluate(PILLS)
    want = {r["id"]: pill(r["nominal"], order) for r in JMC["rows"] if multi(r.get("nominal"))}
    check(f"{tag}: the pill on exactly its four values: three differ, one agrees", {k: v["text"] for k, v in pills.items() if v} == want and len(want) == 4, pills)
    src = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#v tbody tr[data-id]')].map((tr) => { const td = tr.querySelector('td[data-col="nominal@source"]');
      return [tr.dataset.id, { a: td.querySelector('a') ? td.querySelector('a').getAttribute('href') : null, label: !!td.querySelector('.dv-src-label'), derived: !!td.querySelector('.dv-src-derived') }]; }))""")
    private = [k for k, r in R.items() if isinstance(r.get("nominal"), dict) and "sources" not in r["nominal"] and str(r["nominal"].get("source", "")).endswith("(private)")]
    check(f"{tag}: a private source is a plain label, never a link", private and all(src[k]["label"] and src[k]["a"] is None for k in private if k in src), {k: src.get(k) for k in private[:3]})
    check(f"{tag}: a derived value names what it came from, marked", src["pole_pairs"]["derived"] and src["encoder_lines"]["derived"] and not src["peak_torque"]["derived"], {k: src[k] for k in ("pole_pairs", "encoder_lines", "peak_torque")})
    check(f"{tag}: a value with a public page links to it", src["rated_speed"]["a"] and "jmc-motion.com" in src["rated_speed"]["a"], src["rated_speed"])
    tab(page, "Sources").click()
    settle(page)
    hs = [c for c in heads(page) if c.startswith("nominal@")]
    check(f"{tag}: Sources: its three documents, best first, wherever their ids come from", hs == [f"nominal@{s}" for s in order] and len(hs) == 3, hs)
    check(f"{tag}: ... the rest of the view as it was: Measured, Verdict and the others stay", "measured" in heads(page) and "verdict" in heads(page), heads(page))
    got = cells(page)
    priv = next(s for s in order if s.startswith("private:"))
    check(f"{tag}: one-source rows read under the source they name: rated torque under the selection list", got["rated_torque"][f"nominal@{priv}"] == "0.64 N·m", got["rated_torque"])
    left_most_holds(tag, page, "default")
    drawing = next(s for s in order if "for 60ASM400" in s)
    drag_header(page, f"nominal@{drawing}", hs[0])
    new = [drawing] + [s for s in order if s != drawing]
    check(f"{tag}: a real source id, with spaces, colons and slashes: dragging it first", page.evaluate("() => window.v.precedence.order") == new, page.evaluate("() => window.v.precedence.order"))
    got = cells(page)
    check(f"{tag}: the drawing's values show, and only where it states one", (got["peak_torque"]["nominal"], got["rated_phase_current"]["nominal"], got["rotor_inertia"]["nominal"], got["rated_speed"]["nominal"]) == ("1.28 N·m", "7.5 A", "0.32 kg·cm²", "3,000 rpm"), got["peak_torque"])
    left_most_holds(tag, page, "after the drag")
    page.reload()
    wait_rows(page)
    check(f"{tag}: on a no-url page (robotparts') a reload keeps it, from this viewer's storage", page.evaluate("() => window.v.precedence.order") == new, page.evaluate("() => window.v.precedence.order"))
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()


# ---------------------------------------------------------------- data with no sources
def nothing_changes(browser, base):
    tag = "plain data"
    context, page, errors = fresh(browser, base, "no-url")
    page.evaluate("""() => { const d = { id: 'p', properties: { field: { type: 'text' }, nominal: { type: 'number' } }, rows: [{ id: 'a', field: 'A', nominal: { value: 1, source: 'x' } }, { id: 'b', field: 'B', nominal: 2 }] };
      window.__d = d; window.v.presets = [{ type: 'table', name: 'T', order: ['field', 'nominal'] }]; window.v.data = d; }""")
    wait_rows(page)
    got = page.evaluate("""() => ({ heads: [...document.querySelectorAll('#v thead tr.dv-hleaf th[data-col]')].map((t) => t.dataset.col), keys: Object.keys(window.v.data.properties), row: Object.keys(window.v.data.rows[0]),
      same: window.v.data.rows[0].nominal === window.__d.rows[0].nominal, prec: window.v.precedence, tabs: window.v.presets.length })""")
    check(f"{tag}: no source column, no extra property, no extra view, precedence null", got == {"heads": ["field", "nominal"], "keys": ["field", "nominal"], "row": ["id", "field", "nominal"], "same": True, "prec": None, "tabs": 1}, got)
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()


# ---------------------------------------------------------------- light and dark, wide and a phone
CONTRAST = """(sel) => {
  const parse = (c) => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const over = (top, under) => ({ r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1 });
  const bgOf = (el) => { const layers = []; for (let n = el; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let acc = { r: 255, g: 255, b: 255, a: 1 }; if (matchMedia('(prefers-color-scheme: dark)').matches && !layers.some((l) => l.a >= 1)) acc = { r: 0, g: 0, b: 0, a: 1 };
    for (const l of layers.reverse()) acc = over(l, acc); return acc; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const el = document.querySelector(sel); if (!el) return null;
  const bg = bgOf(el), fg = over(parse(getComputedStyle(el).color), bg);
  const L1 = lum(fg), L2 = lum(bg);
  return { ratio: (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05), bg: [bg.r, bg.g, bg.b].map(Math.round) };
}"""


def themes(browser, base):
    for width, dark in ((1280, False), (1280, True), (390, False), (390, True)):
        tag = f"{width} px {'dark' if dark else 'light'}"
        context, page, errors = fresh(browser, base, width=width, dark=dark, mobile=width < 500)
        over = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(f"{tag}: Datasheet: the page never scrolls sideways", over <= 0, over)
        fit = page.evaluate("""() => { const b = document.querySelector('#v tbody tr[data-id="peak_torque"] button.dv-src-dd'); const td = b.closest('td'); const a = b.getBoundingClientRect(), c = td.getBoundingClientRect(); return { pill: a.right - a.left, right: a.right, cell: c.right, scroll: b.scrollWidth - b.clientWidth }; }""")
        check(f"{tag}: the pill fits its cell, whole, beside the value", fit["right"] <= fit["cell"] + 0.5 and fit["scroll"] <= 0, fit)
        dd = page.evaluate(CONTRAST, '#v tbody tr[data-id="peak_torque"] button.dv-src-dd')
        check(f"{tag}: the pill reads (contrast ≥ 4.5)", dd and dd["ratio"] >= 4.5, dd)
        view_named(page, "Sources")
        over = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(f"{tag}: Sources: the page still never scrolls sideways", over <= 0, over)
        differs = page.evaluate(CONTRAST, '#v tbody tr[data-id="peak_torque"] td[data-src-state="differs"]')
        agrees = page.evaluate(CONTRAST, '#v tbody tr[data-id="rated_torque"] td[data-src-state="agrees"]')
        check(f"{tag}: a source that differs is tinted, one that agrees is not", differs and agrees and differs["bg"] != agrees["bg"], {"differs": differs, "agrees": agrees})
        check(f"{tag}: ... and reads (contrast ≥ 4.5)", differs and differs["ratio"] >= 4.5, differs)
        check(f"{tag}: no page error", not errors, errors[:3])
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
            except Exception:  # noqa: BLE001 - not up yet
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for section in (no_mode, source_cells, hide_and_ordinary, drag_is_precedence, old_state, source_column, the_pill, base_formula, editing, inspector, robotparts, nothing_changes, themes):
                try:
                    section(browser, base)
                except Exception as err:  # noqa: BLE001 - a section that cannot finish is a failed check, and the others still run
                    check(f"{section.__name__}: the section ran to its end", False, repr(err)[:400])
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "source-columns-checks.json").write_text(json.dumps({"checks": checks}, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} source-columns checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
