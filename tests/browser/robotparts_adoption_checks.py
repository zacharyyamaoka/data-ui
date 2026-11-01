"""Two kit issues the RobotParts agent found adopting data-ui at d92c025, measured in headless Chromium on the built kit.

    ~/psu-atlas/.venv/bin/python tests/browser/robotparts_adoption_checks.py [OUT_DIR]     # after npm run build

FROZEN: committed before the code, so the code answers to it and not the other way round.

1. persist="local" keys on the data id, and robotparts' datasheets share one id across 2,103 pages, so the open preset carried between
   pages: a preset chosen on JMC opened moteus with 0 of 16 rows. persist="page" (docs/CONTRACT.md §37) keeps the view on this page and the
   widths with the data, as Source precedence already keys on page path + data id. persist="local" means what it meant.

2. Manage sources' columns came out at 156 / 603 / 284 px, sized to their header text; the 603 px column would not drag narrower, and at
   1280 px the third source started past the sheet's edge. A header's words must not set a minimum that blocks a drag (docs/CONTRACT.md
   §28, §45): measured on robotparts' real source names, on longer ones, and on a plain column that is no source at all.

The pages are one fixture served at many paths, as robotparts serves one template at /actuator/<part>/: same data id, another location.
Serves the repo root on a free 127.0.0.1 port, stops that server when done, writes OUT_DIR/robotparts-adoption-checks.json and exits 1 if
any check fails.
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
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "robotparts-adoption-checks"
OUT.mkdir(parents=True, exist_ok=True)
FIX = "/tests/browser/fixtures/source-columns"
PAGE = ROOT / FIX[1:] / "page.html"
JMC = json.loads((ROOT / FIX[1:] / "jmc.json").read_text(encoding="utf-8"))
QUERY = f"src={FIX}/jmc.base&data={FIX}/jmc.json&no-url"
WAIT = 15000
ROWS = len(JMC["rows"])
checks: list[dict] = []

SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"
STORED = "() => Object.keys(localStorage).filter((k) => k.startsWith('data-views/'))"


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


def context_for(browser, base, width=1280, height=900):
    context = browser.new_context(viewport={"width": width, "height": height})
    context.set_default_timeout(WAIT)
    # one template at many paths, as robotparts serves /actuator/<part>/
    context.route(f"{base}/parts/**", lambda route: route.fulfill(path=str(PAGE), content_type="text/html"))
    return context


def open_part(page, base, part, persist):
    page.goto(f"{base}/parts/{part}/?{QUERY}{'&persist=' + persist if persist else ''}")
    page.wait_for_function("() => window.kitReady && window.v && window.v.dataset.view && window.v.querySelector('thead th[data-col]')", timeout=WAIT)
    settle(page)


def view_name(page):
    return page.evaluate("() => window.v.origin.name")


def rows(page):
    return page.evaluate("() => window.v.model.rows.length")


def pick_tab(page, name):
    page.locator('#v [role=tab]:visible', has_text=name).first.click()
    settle(page)
    page.wait_for_timeout(300)  # a kept change is written after a short wait


def width(page, col):
    return page.locator(f'#v thead th[data-col="{col}"]').bounding_box()["width"]


def drag_edge(page, col, dx):
    box = page.locator(f'#v thead th[data-col="{col}"] .dv-resize').bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx / 2, y, steps=4)
    page.mouse.move(x + dx, y, steps=4)
    page.mouse.up()
    settle(page)
    page.wait_for_timeout(300)


# ---------------------------------------------------------------- 1. persist="page"
def page_scope(browser, base):
    tag = 'persist="page"'
    context = context_for(browser, base)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    open_part(page, base, "jmc", "page")
    check(f"{tag}: the first visit opens the file's first view, every row", view_name(page) == "Datasheet" and rows(page) == ROWS, {"view": view_name(page), "rows": rows(page)})
    pick_tab(page, "Measured vs datasheet")
    check(f"{tag}: (the reported preset: JMC has no measured value, so 0 rows)", rows(page) == 0, rows(page))
    open_part(page, base, "moteus", "page")
    check(f"{tag}: a preset chosen on one page does not carry to the next: the view is the file's first, every row there", view_name(page) == "Datasheet" and rows(page) == ROWS, {"view": view_name(page), "rows": rows(page)})
    open_part(page, base, "jmc", "page")
    check(f"{tag}: back on that page, its own preset is there", view_name(page) == "Measured vs datasheet", view_name(page))
    # ---- a view's other changes are the page's too
    open_part(page, base, "moteus", "page")
    page.evaluate("() => window.v.setView({ sort: [{ property: 'field', direction: 'DESC' }] })")
    settle(page)
    page.wait_for_timeout(300)
    open_part(page, base, "hub", "page")
    check(f"{tag}: a sort is the page's too", not page.evaluate("() => window.v.view.sort || null"), page.evaluate("() => window.v.view.sort || null"))
    # ---- the widths go with the data: drag on one page, read on another
    before = width(page, "field")
    drag_edge(page, "field", 80)
    after = width(page, "field")
    check(f"{tag}: (a drag took)", abs(after - before - 80) <= 2, {"before": before, "after": after})
    open_part(page, base, "gripper", "page")
    check(f"{tag}: the layout is shared: a page never visited has the width dragged on another, measured", abs(width(page, "field") - after) <= 1, {"here": width(page, "field"), "there": after})
    check(f"{tag}: ... and only the layout: it opens on its own view, unsorted", view_name(page) == "Datasheet" and not page.evaluate("() => window.v.view.sort || null"), view_name(page))
    open_part(page, base, "moteus", "page")
    check(f"{tag}: a page with its own kept view has the width too, and keeps its sort", abs(width(page, "field") - after) <= 1 and page.evaluate("() => (window.v.view.sort || [{}])[0].direction") == "DESC", width(page, "field"))
    # ---- the two keys
    keys = page.evaluate(STORED)
    check(f"{tag}: the view is stored under the page's path and the data id", any("/parts/jmc/" in k and "robotparts-datasheet" in k and k.endswith("/state") for k in keys), keys)
    check(f"{tag}: nothing under persist=\"local\"'s key: it would carry between pages", "data-views/robotparts-datasheet/state" not in keys, keys)
    # ---- Reset: this view's widths, for this reader, wherever they kept them
    open_part(page, base, "gripper", "page")
    page.locator('#v [data-bar="reset"]').first.click()
    settle(page)
    page.wait_for_timeout(300)
    check(f"{tag}: Reset gives the column its own width back", abs(width(page, "field") - before) <= 1, {"now": width(page, "field"), "was": before})
    open_part(page, base, "gripper", "page")
    check(f"{tag}: ... and it stays back", abs(width(page, "field") - before) <= 1, width(page, "field"))
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()


def local_unchanged(browser, base):
    tag = 'persist="local"'
    context = context_for(browser, base)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    open_part(page, base, "jmc", "local")
    pick_tab(page, "Datasheet only")
    keys = page.evaluate(STORED)
    check(f"{tag}: the key it always was", "data-views/robotparts-datasheet/state" in keys, keys)
    open_part(page, base, "moteus", "local")
    check(f"{tag}: means what it meant: one state per data id, the preset comes along", view_name(page) == "Datasheet only", view_name(page))
    state = page.evaluate("() => JSON.parse(localStorage.getItem('data-views/robotparts-datasheet/state'))")
    check(f"{tag}: and its shape", state.get("selected") == "Datasheet only" and "Datasheet only" in state.get("views", {}), state and list(state))
    context.close()
    # ---- what a returning reader kept is still read
    context = context_for(browser, base)
    page = context.new_page()
    open_part(page, base, "jmc", "local")
    pick_tab(page, "Datasheet only")
    held = page.evaluate("() => localStorage.getItem('data-views/robotparts-datasheet/state')")
    page.evaluate("() => localStorage.clear()")
    page.evaluate("(s) => localStorage.setItem('data-views/robotparts-datasheet/state', s)", held)
    open_part(page, base, "another", "local")
    check(f"{tag}: a state stored by the build before this one comes back", view_name(page) == "Datasheet only", view_name(page))
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()
    tag = "no persist"
    context = context_for(browser, base)
    page = context.new_page()
    open_part(page, base, "jmc", "")
    pick_tab(page, "Datasheet only")
    drag_edge(page, "field", 40)
    check(f"{tag}: keeps nothing", page.evaluate(STORED) == [], page.evaluate(STORED))
    context.close()


# ---------------------------------------------------------------- 2. a header's words set no floor
HEADS = """() => { const box = document.querySelector('#v .dv-scroll').getBoundingClientRect(); return { right: box.right, cols: [...document.querySelectorAll('#v thead tr.dv-hleaf th[data-col]')].map((t) => { const b = t.getBoundingClientRect(), l = t.querySelector('.dv-th-label'); return { col: t.dataset.col, left: b.left, width: b.width, cut: !!l && l.scrollWidth > l.clientWidth, label: l ? l.textContent.trim() : '' }; }) }; }"""


def long_names(browser, base):
    tag = "long source names"
    context = context_for(browser, base)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    open_part(page, base, "jmc", "")
    pick_tab(page, "Sources")
    got = page.evaluate(HEADS)
    sources = [c for c in got["cols"] if c["col"].startswith("nominal@")]
    names = {s: d["name"] for s, d in JMC["sources"].items()}
    check(f"{tag}: robotparts' three documents, the longest {max(len(n) for n in names.values())} characters long", len(sources) == 3, [c["col"] for c in sources])
    check(f"{tag}: at 1280 px no column is sized to its header: none past 240 px", all(c["width"] <= 240 for c in sources), [round(c["width"]) for c in sources])
    check(f"{tag}: the third source starts inside the sheet", sources[2]["left"] < got["right"], {"left": round(sources[2]["left"]), "sheet right": round(got["right"])})
    check(f"{tag}: all three end inside it, at 1280 px", all(c["left"] + c["width"] <= got["right"] + 1 for c in sources), {"cols": [(round(c["left"]), round(c["width"])) for c in sources], "right": round(got["right"])})
    longest = max(sources, key=lambda c: len(c["label"]))
    check(f"{tag}: a name that does not fit ends in an ellipsis", longest["cut"], longest)
    # ---- the column that came out 603 px: drag it, measured
    col = longest["col"]
    w0 = width(page, col)
    drag_edge(page, col, -100)
    w1 = width(page, col)
    check(f"{tag}: dragged narrower than its header, it goes, by the pointer's 100 px ({w0:.0f} -> {w1:.0f})", abs(w0 - w1 - 100) <= 2, {"from": w0, "to": w1})
    stored = page.evaluate("(c) => (window.v.view.columnSize || {})[c]", col)
    check(f"{tag}: ... stored in columnSize under the column's id", stored and abs(stored - w1) <= 1, stored)
    page.evaluate("() => window.v.setView({ rowHeight: 'short' })")
    settle(page)
    check(f"{tag}: ... and a redraw keeps that width", abs(width(page, col) - w1) <= 1, width(page, col))
    drag_edge(page, col, -400)
    w2 = width(page, col)
    check(f"{tag}: narrower still: the floor is no header's", w2 < w1 and w2 < 100, {"width": w2})
    # §45: a value its column cuts ends in an ellipsis, and is whole one hover away (a right-aligned number is never cut: below, and types_r2's r1 #6)
    wide = page.locator(f'#v tbody tr[data-id="rotor_inertia"] td[data-col="{col}"]')
    wide.hover()
    page.wait_for_timeout(500)
    tip = page.evaluate("() => (document.querySelector('.dv-cliptip') || {}).textContent") or ""
    check(f"{tag}: a value that column now cuts is whole on hover", "0.183" in tip and "kg·cm²" in tip, tip)
    page.mouse.move(5, 5)
    page.wait_for_timeout(200)
    # ---- one step to the whole name
    page.locator(f'#v thead th[data-col="{col}"] .dv-th-label').hover()
    page.wait_for_timeout(500)
    tip = page.evaluate("() => (document.querySelector('.dv-cliptip') || {}).textContent")
    check(f"{tag}: hovering it shows the whole name", bool(tip) and longest["label"] in tip, tip)
    page.mouse.move(5, 5)
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()

    # ---- longer than anything real, and plain columns: no special case
    tag = "long headers"
    context = context_for(browser, base)
    page = context.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    open_part(page, base, "jmc", "")
    long = "A document whose name runs on for a very long way, far past anything a column should give it, and then some more besides "
    page.evaluate("""([long]) => { const s = (k, v) => ({ source: k, value: v });
      window.v.presets = [{ type: 'table', name: 'T', order: ['field', 'value', 'plain'] }];
      window.v.data = { id: 'long', titleProperty: 'field', sources: { a: { name: long + 'A' }, b: { name: long + 'B' }, c: { name: long + 'C' } },
        properties: { field: { type: 'text', label: 'Field' }, value: { type: 'number', label: 'Value' }, plain: { type: 'number', label: long } },
        rows: [{ id: 'r', field: 'R', value: { sources: [s('a', 1), s('b', 2), s('c', 3)] }, plain: 4 }] }; }""", [long])
    page.wait_for_function("() => window.v.querySelector('thead th[data-col=\"plain\"]')", timeout=WAIT)
    settle(page)
    # WHY its <col>: three columns in a wide box spread to fill it (§37), so what is measured is what the column asks for
    asked = page.evaluate("""() => { const i = [...document.querySelectorAll('#v thead tr.dv-hleaf th[data-col]')].findIndex((t) => t.dataset.col === 'plain'); return parseFloat(document.querySelectorAll('#v colgroup col')[i].style.width); }""")
    check(f"{tag}: a plain column that is no source: the same rule: not sized to its header", asked <= 240, asked)
    w = width(page, "plain")
    drag_edge(page, "plain", -100)
    check(f"{tag}: ... and it drags narrower than its header", abs(w - width(page, "plain") - 100) <= 2, width(page, "plain"))
    drag_edge(page, "plain", -600)
    fit = page.evaluate("""() => { const td = document.querySelector('#v tbody td[data-col="plain"]'), v = td.querySelector('.dv-v') || td; return { cell: td.getBoundingClientRect().width, value: v.getBoundingClientRect().right <= td.getBoundingClientRect().right + 0.5 }; }""")
    check(f"{tag}: ... down to what it holds: a number is never cut", fit["value"] and fit["cell"] < 100, fit)
    page.evaluate("() => window.v.selectView('Sources')")
    settle(page)
    got = page.evaluate(HEADS)
    sources = [c for c in got["cols"] if c["col"].startswith("value@") and c["col"] != "value@source"]
    check(f"{tag}: three sources of {len(long) + 1} characters each, at 1280 px: all three inside the sheet", len(sources) == 3 and all(c["left"] + c["width"] <= got["right"] + 1 for c in sources), [(round(c["left"]), round(c["width"])) for c in sources])
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()


# ---------------------------------------------------------------- found recording the hero: a source shown again
def shown_again(browser, base):
    tag = "shown again"
    context = context_for(browser, base)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    open_part(page, base, "jmc", "")
    pick_tab(page, "Sources")
    drawn = page.evaluate("() => [...document.querySelectorAll('#v thead tr.dv-hleaf th[data-col]')].map((t) => t.dataset.col)")
    sources = [c for c in drawn if c.startswith("nominal@")]
    check(f"{tag}: (robotparts' view has columns after its sources)", drawn.index(sources[-1]) < len(drawn) - 1, drawn)
    for hide in sources:
        page.evaluate("(c) => window.v.setView({ order: window.v.view.order.filter((x) => x !== c) })", hide)
        settle(page)
        # as Property visibility shows a column: at the end of the order
        page.evaluate("(c) => window.v.setView({ order: [...window.v.view.order, c] })", hide)
        settle(page)
        now = page.evaluate("() => [...document.querySelectorAll('#v thead tr.dv-hleaf th[data-col]')].map((t) => t.dataset.col)")
        check(f"{tag}: every column where it was, no source thrown past the others ({sources.index(hide) + 1} of {len(sources)})", now == drawn, now)
        check(f"{tag}: ... and the view is the view it was: nothing to Reset ({sources.index(hide) + 1})", page.evaluate("() => window.v.dirty") is False, None)
    check(f"{tag}: no page error", not errors, errors[:3])
    context.close()


def main() -> int:
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{base}{FIX}/page.html", timeout=1)
                break
            except Exception:  # noqa: BLE001 - not up yet
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for section in (page_scope, local_unchanged, long_names, shown_again):
                try:
                    section(browser, base)
                except Exception as err:  # noqa: BLE001 - a section that cannot finish is a failed check, and the others still run
                    check(f"{section.__name__}: the section ran to its end", False, repr(err)[:400])
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "robotparts-adoption-checks.json").write_text(json.dumps({"checks": checks}, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} robotparts-adoption checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
