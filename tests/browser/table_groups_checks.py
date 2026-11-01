"""Column resize and nested groups on every table (docs/peps/, CONTRACT), measured in headless Chromium with a real mouse on
tests/browser/fixtures/table-groups/ against an oracle over its own JSON.

    ~/psu-atlas/.venv/bin/python tests/browser/table_groups_checks.py [OUT_DIR]     # after npm run build

WHY (Zach, Oct 31): "I don't like how I cannot resize these columns for example I may want to read what is more inside
here.." and "We should be able to support multiple nested things. For example here servo.pid_position should be within
servo! not on the same flat level". Widths are getBoundingClientRect, never a stored number alone.
Serves the repo root on a free 127.0.0.1 port, stops it when done, exits 1 if any check fails.
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
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "table-groups"
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "browser" / "fixtures" / "table-groups"
PAGE = "/tests/browser/fixtures/table-groups/page.html"
DATA = json.loads((FIX / "params.json").read_text(encoding="utf-8"))
checks: list[dict] = []


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


# ---------------------------------------------------------------- the oracle, from the JSON alone
def tree():
    """[(kind, label, depth, count)] in drawn order: first-seen top levels; direct rows, then child groups first-seen sorted
    as the data meets them; "No section" last, as an undefined level sorts."""
    root = {"kids": {}, "rows": []}
    none = []
    for r in DATA["rows"]:
        if not r.get("section"):
            none.append(r)
            continue
        at = root
        for seg in r["section"].split("."):
            at = at["kids"].setdefault(seg, {"kids": {}, "rows": []})
        at["rows"].append(r)

    def size(n):
        return len(n["rows"]) + sum(size(k) for k in n["kids"].values())

    out = []

    def walk(n, depth):
        for r in n["rows"]:
            out.append(("row", r["name"], depth, None))
        for seg, k in n["kids"].items():
            out.append(("group", seg, depth, size(k)))
            walk(k, depth + 1)

    for seg, k in root["kids"].items():
        out.append(("group", seg, 0, size(k)))
        walk(k, 1)
    out.append(("group", "No section", 0, len(none)))
    out.extend(("row", r["name"], 1, None) for r in none)
    return out


# ---------------------------------------------------------------- the page
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def settle(page):
    page.wait_for_timeout(120)


def open_page(browser, base, view="Nested", selectable=False, width=1280):
    page = browser.new_page(viewport={"width": width, "height": 800})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    q = f"?view={view}" + ("&selectable=1" if selectable else "")
    page.goto(base + PAGE + q, wait_until="load")
    page.wait_for_function("() => window.v && window.v.view && document.querySelector('.dv-view') && window.v.view.name === new URLSearchParams(location.search).get('view')", timeout=20000)
    page.wait_for_timeout(300)
    return page


TH = "thead th[data-col=\"{}\"]"


def width(page, col):
    return page.evaluate("(s) => document.querySelector(s).getBoundingClientRect().width", TH.format(col))


def edge(page, col):
    return page.evaluate("(s) => { const t = document.querySelector(s); t.scrollIntoView({ inline: 'nearest', block: 'nearest' }); const r = t.getBoundingClientRect(); return { x: r.right - 2, y: r.top + r.height / 2 }; }", TH.format(col))


def drag(page, col, dx):
    at = edge(page, col)
    page.mouse.move(at["x"], at["y"])
    page.mouse.down()
    for k in range(1, 9):
        page.mouse.move(at["x"] + dx * k / 8, at["y"])
    page.mouse.up()
    settle(page)


def double(page, col):
    at = edge(page, col)
    page.mouse.dblclick(at["x"], at["y"])
    settle(page)


def rows(page):
    return page.evaluate("""() => [...document.querySelectorAll('tbody tr[data-i]')].map((tr) => {
      const g = tr.classList.contains('dv-group');
      return [g ? 'group' : 'row', g ? tr.querySelector('.dv-gname').textContent : tr.querySelector('td[data-col="name"]').textContent.trim(),
        Number(tr.dataset.depth ?? -1), g ? Number(tr.querySelector('.dv-count').textContent) : null,
        tr.querySelector(g ? '.dv-gname' : 'td[data-col="name"]').getBoundingClientRect().left + (g ? 0 : parseFloat(getComputedStyle(tr.querySelector('td[data-col="name"]')).paddingLeft))];
    })""")


def group_row(page, label):
    return page.locator("tbody tr.dv-group", has=page.locator(".dv-gname", has_text=label)).first


# ---------------------------------------------------------------- PART A
def part_a(browser, base):
    page = open_page(browser, base)
    cols = page.evaluate("() => [...document.querySelectorAll('thead th[data-col]')].map((t) => t.dataset.col)")
    check("every header draws a handle, the Nominal source column's too (Zach's bug: it had none)", page.evaluate("() => [...document.querySelectorAll('thead th[data-col]')].every((t) => t.querySelector('.dv-resize'))"), cols)
    check("the source column is the one under test", "nominal@source" in cols, cols)
    for col in cols:
        w0 = width(page, col)
        drag(page, col, 70)
        w1 = width(page, col)
        check(f"drag: {col} widens by the pointer's 70 px ({w0:.0f} -> {w1:.0f})", abs(w1 - w0 - 70) <= 1)
    stored = page.evaluate("() => window.v.view.columnSize")
    check("drag: the width is in the view's columnSize, under the column's key", abs(stored.get("nominal@source", 0) - width(page, "nominal@source")) <= 1, stored)
    w = width(page, "nominal@source")
    page.evaluate("() => window.v.selectView('Flat')")
    settle(page)
    page.evaluate("() => window.v.selectView('Nested')")
    page.wait_for_timeout(300)
    # a view's changes are its own: columnSize is the view's while it is open; the redraw must draw that width
    page.evaluate("(n) => window.v.setView({ columnSize: { ...window.v.view.columnSize, 'nominal@source': n } })", w)
    settle(page)
    check(f"remembered: columnSize draws the source column at {w:.0f}", abs(width(page, "nominal@source") - w) <= 1, width(page, "nominal@source"))
    page.close()

    # hover affordance, measured
    page = open_page(browser, base)
    at = edge(page, "nominal@source")
    page.mouse.move(at["x"], at["y"])
    page.wait_for_timeout(200)
    h = page.evaluate("""(s) => { const t = document.querySelector(s), h = t.querySelector('.dv-resize') || t, g = document.querySelector('.dv-resize-guide'), r = t.getBoundingClientRect(), b = h === t ? { width: 0 } : h.getBoundingClientRect(), tb = document.querySelector('.dv-table').getBoundingClientRect();
      const gb = g && g.getBoundingClientRect(), cs = g && getComputedStyle(g);
      return { cursor: getComputedStyle(h).cursor, hit: b.width, right: r.right, line: gb ? gb.left + gb.width / 2 : null, lh: gb ? gb.height : 0, tall: tb.height, shown: !!g && cs.display !== 'none' && cs.opacity !== '0', w: gb ? gb.width : 0 }; }""", TH.format("nominal@source"))
    check("hover: the cursor says col-resize", h["cursor"] == "col-resize", h)
    check("hover: the handle is at least 10 px to hit", h["hit"] >= 10, h["hit"])
    check("hover: a line shows on the boundary, down the table", h["shown"] and h["line"] is not None and abs(h["line"] - h["right"]) <= 2 and h["lh"] >= min(h["tall"], 400) - 2 and h["w"] >= 2, h)
    page.mouse.move(400, 500)
    page.wait_for_timeout(200)
    check("hover: the line goes when the pointer leaves", page.evaluate("() => { const g = document.querySelector('.dv-resize-guide'); return !g || getComputedStyle(g).display === 'none'; }"))

    # a press with no move, a narrowing drag that ends on the header
    page.evaluate("() => { window.__sort = 0; window.v.addEventListener('data-views-change', () => { window.__sort = (window.v.view.sort || []).length; }); }")
    at = edge(page, "note")
    page.mouse.move(at["x"], at["y"])
    page.mouse.down()
    page.mouse.up()
    settle(page)
    check("a press that does not move stores nothing", not page.evaluate("() => window.v.view.columnSize"), page.evaluate("() => window.v.view.columnSize"))
    drag(page, "note", -400)
    check("narrowing past the minimum stops at the column's own floor, well short of the pointer", 48 <= width(page, "note") <= 96, width(page, "note"))
    check("a drag that ends on the header is not a sort", not page.evaluate("() => (window.v.view.sort || []).length"), page.evaluate("() => window.v.view.sort"))

    # double-click fits, off-screen rows included
    drag(page, "nominal@source", -120)
    w0 = width(page, "nominal@source")
    double(page, "nominal@source")
    w1 = width(page, "nominal@source")
    fit = page.evaluate("""() => { const a = [...document.querySelectorAll('td[data-col="nominal@source"] .dv-src-in > :is(.dv-src-link, .dv-src-label)')]; return a.map((n) => [n.textContent.length, n.scrollWidth - n.clientWidth]); }""")
    check(f"double-click: the source column fits its longest value ({w0:.0f} -> {w1:.0f}), nothing cut", w1 > w0 and all(c[1] <= 0 for c in fit), fit)
    check("double-click: stored as the view's width", abs(page.evaluate("() => window.v.view.columnSize['nominal@source']") - w1) <= 1)
    check("double-click: no sort", not page.evaluate("() => (window.v.view.sort || []).length"))
    w2 = width(page, "value")
    double(page, "value")
    check("double-click: a number column fits too, within sense", 40 <= width(page, "value") <= w2 + 1, width(page, "value"))
    page.close()

    # the longest value sits below the fold of a tall table
    page = open_page(browser, base)
    page.evaluate("""() => { const d = window.v.data; const pad = Array.from({ length: 900 }, (_, i) => ({ id: 'p' + i, name: 'p' + i, section: 'servo', value: i, note: 'x' })); window.v.data = { ...d, rows: [...pad, ...d.rows.map((r) => r.id === 'mass' ? { ...r, note: 'the one long note '.repeat(12) } : r)] }; }""")
    page.wait_for_timeout(300)
    double(page, "note")
    check("double-click: the fit reads rows the virtualiser has not drawn", width(page, "note") > 700, width(page, "note"))
    page.close()

    # the pill keeps working as the column narrows: it is part of the formula's cell (CONTRACT §36), so the column's floor holds it whole
    page = open_page(browser, base)
    page.evaluate("() => { const w = {}; for (const t of document.querySelectorAll('thead th[data-col]')) w[t.dataset.col] = 150; window.v.setView({ columnSize: w }); }")
    settle(page)
    for target in (320, 220, 160, 96, 56):
        page.evaluate("(n) => window.v.setView({ columnSize: { ...window.v.view.columnSize, nominal: n } })", target)
        settle(page)
        m = page.evaluate("""() => { const b = document.querySelector('button.dv-src-dd'), td = b.closest('td'), t = td.getBoundingClientRect(), r = b.getBoundingClientRect(), car = b.querySelector('.dv-src-car').getBoundingClientRect();
          return { td: t.width, tdr: t.right, right: r.right, width: r.width, car: car.right, cut: b.scrollWidth - b.clientWidth, col: td.dataset.col }; }""")
        check(f"pill at a {target} px column: inside its cell, its caret too", m["col"] == "nominal" and m["right"] <= m["tdr"] and m["car"] <= m["right"] + 0.5 and m["width"] >= 18, m)
        check(f"pill at a {target} px column: whole: the column's floor holds the value and the pill", m["cut"] <= 0, m)
        page.locator("button.dv-src-dd").first.click()
        page.wait_for_timeout(120)
        n = page.locator(".dv-src-pop [role=menuitemradio]").count()
        check(f"pill at a {target} px column: it opens its sources", n == 2, n)
        page.keyboard.press("Escape")
        settle(page)
    page.close()

    # one step to the full value
    page = open_page(browser, base)
    full = DATA["sources"]["list"]["name"]
    name = page.locator('td[data-col="nominal@source"] .dv-src-label').first
    name.hover()
    page.wait_for_timeout(500)
    t = page.evaluate("() => { const t = document.querySelector('.dv-cliptip'); if (!t) return null; const r = t.getBoundingClientRect(); return { text: t.textContent, w: r.width, right: r.right, vw: innerWidth }; }")
    check("cut off: hovering the source name shows all of it", bool(t) and t["text"] == full and t["right"] <= t["vw"], t)
    page.screenshot(path=str(OUT / "tip.png"))
    page.mouse.move(5, 5)
    page.wait_for_timeout(200)
    check("cut off: it goes when the pointer leaves", page.evaluate("() => !document.querySelector('.dv-cliptip')"))
    note = page.locator('td[data-col="note"]').first
    want = DATA["rows"][0]["note"]
    note.hover()
    page.wait_for_timeout(500)
    check("cut off: a plain text cell too", page.evaluate("() => (document.querySelector('.dv-cliptip') || {}).textContent") == want, page.evaluate("() => (document.querySelector('.dv-cliptip') || {}).textContent"))
    page.mouse.move(5, 5)
    page.wait_for_timeout(200)
    page.locator('td[data-col="value"]').first.hover()
    page.wait_for_timeout(500)
    check("a cell that fits shows nothing extra", page.evaluate("() => !document.querySelector('.dv-cliptip')"))
    check("no page errors", not page.errors, page.errors)
    page.close()

    # the Sources view: its source columns, and the header drag beside the handle
    page = open_page(browser, base)
    page.evaluate("() => { window.v.selectView('Sources'); }")
    page.wait_for_timeout(300)
    cols = page.evaluate("() => [...document.querySelectorAll('thead th[data-col^=\"nominal@\"]')].map((t) => t.dataset.col)")
    order0 = page.evaluate("() => window.v.precedence.order")
    w0 = width(page, cols[0])
    drag(page, cols[0], 60)
    check("Sources: a source column resizes", abs(width(page, cols[0]) - w0 - 60) <= 1, width(page, cols[0]))
    check("Sources: the handle is not a reorder, so no precedence moved", page.evaluate("() => window.v.precedence.order") == order0)
    page.close()

    # selectable: the frozen first column and a page width
    page = open_page(browser, base, selectable=True)
    w0 = width(page, "name")
    drag(page, "name", 50)
    check("selectable: the frozen first column resizes", abs(width(page, "name") - w0 - 50) <= 1, width(page, "name"))
    page.close()


# ---------------------------------------------------------------- PART B
def part_b(browser, base):
    page = open_page(browser, base)
    want = tree()
    got = rows(page)
    check("nested: the rows, their depth and rolled-up counts are the JSON's", [tuple(r[:4]) for r in got] == want, [r[:4] for r in got])
    lefts = {}
    for r in got:
        lefts.setdefault((r[0], r[2]), []).append(r[4])
    g0, g1, g2 = (lefts[("group", d)][0] for d in (0, 1, 2))
    check(f"indent: each level sits 16 px in, measured ({g0:.0f}, {g1:.0f}, {g2:.0f})", abs(g1 - g0 - 16) <= 1 and abs(g2 - g1 - 16) <= 1)
    r2 = lefts[("row", 2)][0]
    r3 = lefts[("row", 3)][0]
    check(f"indent: a row sits one level in from its group's left ({r2:.0f}, {r3:.0f})", abs(r3 - r2 - 16) <= 1)
    page.screenshot(path=str(OUT / "nested.png"))

    check("the title on a nested group is its whole path", group_row(page, "limits").locator(".dv-gname").get_attribute("title") == "servo.pid_position.limits")

    # fold per level
    group_row(page, "pid_position").click()
    settle(page)
    names = [r[1] for r in rows(page)]
    check("fold: a nested group hides what is under it, its siblings stay", "limits" not in names and "kp" not in names and "clamp" not in names and "fw" in names and "bus_voltage" in names, names)
    check("fold: the parent's count does not move", group_row(page, "servo").locator(".dv-count").text_content() == "9")
    group_row(page, "servo").click()
    settle(page)
    names = [r[1] for r in rows(page)]
    check("fold: the parent hides every level under it", "fw" not in names and "bus_voltage" not in names, names)
    group_row(page, "servo").click()
    settle(page)
    names = [r[1] for r in rows(page)]
    check("fold: unfolding the parent keeps the child as it was", "fw" in names and "kp" not in names, names)
    page.locator("[data-fold=closed]").first.click()
    settle(page)
    check("Fold all: only the top level", [r[1] for r in rows(page)] == ["servo", "motor", "No section"], [r[1] for r in rows(page)])
    page.locator("[data-fold=open]").first.click()
    settle(page)
    check("Unfold all: every level", len(rows(page)) == len(want), len(rows(page)))

    # keyboard
    group_row(page, "pid_position").focus()
    page.keyboard.press("ArrowLeft")
    settle(page)
    check("keys: Left folds a group", group_row(page, "pid_position").get_attribute("aria-expanded") == "false")
    page.keyboard.press("ArrowLeft")
    settle(page)
    check("keys: Left on a folded group goes to its parent", page.evaluate("() => document.activeElement.querySelector('.dv-gname')?.textContent") == "servo", page.evaluate("() => document.activeElement.textContent"))
    group_row(page, "pid_position").focus()
    page.keyboard.press("ArrowRight")
    settle(page)
    check("keys: Right unfolds", group_row(page, "pid_position").get_attribute("aria-expanded") == "true")
    check("aria: a group's level is its depth", group_row(page, "limits").get_attribute("aria-level") == "3")
    page.close()

    # sorting within a level
    page = open_page(browser, base, view="Sorted")
    got = [r[1] for r in rows(page) if r[0] == "row"]
    by = {r["name"]: r["value"] for r in DATA["rows"]}
    direct = [n for n in got if next(r for r in DATA["rows"] if r["name"] == n).get("section") == "servo.pid_position"]
    check("sort: rows sort inside their level", [by[n] for n in direct] == sorted((by[n] for n in direct), reverse=True), direct)
    check("sort: rows stay at their level", tuple(r[1] for r in rows(page))[0:1] == ("servo",) and rows(page)[1][0] == "row")
    page.close()

    # selection: the range follows what is drawn
    page = open_page(browser, base, selectable=True)
    page.locator('tr[data-id="bus_voltage"] .dv-selbox').click()
    page.locator('tr[data-id="kp"] .dv-selbox').click(modifiers=["Shift"])
    settle(page)
    sel = page.evaluate("() => window.v.selection")
    check("selection: shift takes the drawn range, across levels", sorted(sel) == sorted(["bus_voltage", "max_current", "encoder_note", "fw_version", "fw_build", "kp"]), sel)
    page.close()

    # virtualisation, deep
    page = open_page(browser, base)
    page.evaluate("""() => { const d = window.v.data; window.v.data = { ...d, rows: Array.from({ length: 5000 }, (_, i) => ({ id: 'r' + i, name: 'r' + i, value: i, section: ['a', 'b' + (i % 7), 'c' + (i % 5), 'd' + (i % 3), 'e', 'f'].slice(0, 1 + (i % 6)).join('.') })) }; }""")
    page.wait_for_timeout(500)
    n = page.evaluate("() => document.querySelectorAll('tbody tr[data-i]').length")
    check("virtual: 5,000 rows six levels deep draw a window", 0 < n < 150, n)
    page.evaluate("() => { const s = document.querySelector('.dv-scroll'); s.scrollTop = s.scrollHeight; }")
    page.wait_for_timeout(300)
    last = page.evaluate("() => { const a = [...document.querySelectorAll('tbody tr[data-i]')]; return Number(a[a.length - 1].dataset.i) + 1; }")
    total = page.evaluate("() => window.v.model.rows.length")
    check("virtual: the scroll reaches the end, groups counted", last > total, [last, total])
    top = page.evaluate("() => window.v.model.groups[0].rows.length")
    check("virtual: the top group rolls up all 5,000", top == 5000, top)
    page.close()

    # siblings
    page = open_page(browser, base, view="Outline")
    txt = page.evaluate("() => document.querySelector('.dv-view').innerText")
    check("list: nested groups", "pid_position" in txt and "servo.pid_position" not in txt, txt[:160])
    lines = page.evaluate("""() => { const pick = (t) => [...document.querySelectorAll('.dv-view *')].filter((e) => e.children.length === 0 && e.textContent.trim() === t)[0].getBoundingClientRect().left; return ['servo', 'pid_position', 'limits'].map(pick); }""")
    check("list: each level indents", lines[0] < lines[1] < lines[2], lines)
    page.close()
    page = open_page(browser, base, view="Sections")
    txt = page.evaluate("() => document.querySelector('.dv-view').innerText")
    check("cards: H1 the top level, H2 the next", "servo" in txt and "pid_position" in txt and "servo.pid_position" not in txt, txt[:160])
    page.close()
    page = open_page(browser, base, view="Board")
    txt = page.evaluate("() => document.querySelector('.dv-view').innerText")
    check("kanban: a column per whole value, unchanged", "servo.pid_position" in txt, txt[:160])
    page.close()

    # backward compatible, and the menu keeps it
    page = open_page(browser, base, view="Flat")
    labels = [r[1] for r in rows(page) if r[0] == "group"]
    check("no path: the flat levels Zach's screenshot shows", "servo.pid_position" in labels and "servo.fw" in labels, labels)
    page.evaluate("() => window.v.openMenu('group')")
    settle(page)
    sel = page.locator("select[data-k=p0]")
    check("Group menu: a reader can nest the same property", sel.count() == 1)
    sel.select_option("dotted")
    settle(page)
    check("Group menu: the view gains path: dotted", page.evaluate("() => window.v.view.groupBy") == {"property": "section", "path": "dotted"}, page.evaluate("() => window.v.view.groupBy"))
    page.locator("select[data-k=fold]").select_option("closed")
    settle(page)
    check("Group menu: another change keeps the path", page.evaluate("() => window.v.view.groupBy.path") == "dotted")
    page.close()


def main():
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
            part_a(browser, base)
            part_b(browser, base)
            browser.close()
    finally:
        server.terminate()
        server.wait()
    failed = [c for c in checks if not c["ok"]]
    (OUT / "table-groups-checks.json").write_text(json.dumps(checks, indent=1, default=str), encoding="utf-8")
    print(f"{len(checks) - len(failed)} of {len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
