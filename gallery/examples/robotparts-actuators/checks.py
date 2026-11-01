"""Browser checks for this case (run by tests/browser/checks.py): the table lane's actuator and pivot checks, ported
from robotparts lane/tables @ ab5ba92 capture.py, plus the rail (<data-facets>), the propose() contract, the
planned-type notice, the resizable peek and rail (docs/CONTRACT.md §11) and how a record opens (`open: expand | side |
link`, the amendment 2026-10-26 (open modes)), measured with getBoundingClientRect."""

V = "#example"


def status(page):
    return page.inner_text(f"{V} .dv-status")


def tab(page, name):
    """Open a view by its tab and wait until it has drawn (a state, not a pause: tests/browser/checks.py Ctx.drawn)."""
    page.ctx.drawn(page, lambda: page.click(f"{V} .dv-tab[data-name='{name}']"))


def run(ctx, path):
    check = ctx.check
    page = ctx.page(path)
    drawn = page.locator(f"{V} tbody tr[data-i]").count()
    check("actuators: 1,149 rows grouped by brand, only the visible ones drawn (virtualized)", "1,149 of 1,149" in status(page) and drawn < 90,
          f"{status(page).split('·')[0].strip()}; {drawn} rows in the DOM")
    ms = page.evaluate("""() => new Promise((done) => {
      const el = document.querySelector('#example');
      const t = performance.now();
      el.addEventListener('data-views-render', () => done(performance.now() - t), { once: true });
      el.querySelector(".dv-tab[data-name='Brand › form']").click();
    })""")
    # WHY load-aware: a fixed 100 ms flaked on this box under load (2026-10-26 review); ctx.budget enforces it while the
    # machine has CPUs to spare and reports it SOFT, with the load, when it does not
    ctx.budget("actuators: switching to the nested Brand › form preset re-groups and draws 1,149 rows in under 100 ms", ms, 100, "click to drawn")
    page.locator(f"{V} tr.dv-group:has-text('CubeMars')").first.click()
    ctx.until(page, "() => document.querySelectorAll('#example tr.dv-group.dv-depth1').length >= 1")
    check("folded groups open one by one", page.locator(f"{V} tr.dv-group.dv-depth1").count() >= 1)
    tab(page, "Torque density")
    page.locator(f"{V} .dv-scroll").evaluate("el => el.scrollTo(0, el.scrollHeight)")
    ctx.until(page, "() => [...document.querySelectorAll('#example tbody tr.dv-row')].some((r) => +r.dataset.i >= 1000)")
    last = page.locator(f"{V} tbody tr.dv-row").last.get_attribute("data-i")
    check("virtualization reaches the last row", int(last) >= 1000, f"last drawn row index {last}")
    tab(page, "Geared CAN under $150")
    check("Bases filter expressions (drivetrain, buses.contains, price)", "of 1,149" in status(page) and not status(page).startswith("1,149"), status(page).split("·")[0].strip())
    tab(page, "All, flat")
    # a header click opens Notion's column menu (CONTRACT §28); its Sort page sorts
    def sort_by(direction):
        page.click(f"{V} thead th[data-col='mass']")
        page.click(".dv-colmenu [data-act='page:sort']")
        ctx.drawn(page, lambda: page.click(f".dv-colmenu [data-act='sort:{direction}']"))
    sort_by("ASC")
    first = page.locator(f"{V} tbody tr.dv-row").first.inner_text()
    sort_by("DESC")
    heaviest = page.locator(f"{V} tbody tr.dv-row td[data-col='mass']").first.inner_text()
    check("the column menu sorts (rich cells by value); the heaviest is kilograms in grams, not 140,000 g", "140,000" not in heaviest, f"lightest row: {first.split(chr(9))[0]}; heaviest mass {heaviest}")

    # ---- the pivot: a cell lists the records behind it
    tab(page, "Brand × form")
    cell = page.locator(f"{V} tr.dv-row:has(td:first-child:text-is('CubeMars')) td.dv-num:not(.dv-none)").first
    count = int(cell.inner_text().split()[0].replace(",", ""))
    cell.click()
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    runs = page.locator(f"{V} .dv-peek .dv-peektable tbody tr").count()
    check("pivot: clicking a cell lists the records behind it", runs == count and count > 0, f"{runs} records listed for a cell reading {count}")
    page.keyboard.press("Escape")
    check("pivot: Layout shows the pivot's own settings (the plugin's options)", True if _layout_has_options(page) else False)

    # ---- the rail
    tab(page, "By brand")
    ctx.drawn(page, lambda: page.check("data-facets input[data-p=brand][data-value=Steadywin]"))
    st = status(page)
    kst = page.locator("data-facets input[data-value=KST]").locator("xpath=..").inner_text()
    check("rail: ticking a brand filters every view; other brands keep their counts (disjunctive)", st.startswith("86 of 1,149") and "95" in kst, f"{st.split('·')[0].strip()}; KST {kst.split()[-1]}")
    check("rail: the selection is a readable URL", "brand=Steadywin" in page.evaluate("location.search"), page.evaluate("location.search"))
    tab(page, "Brand × form")
    check("rail: the selection survives a layout switch (the pivot reads the same 86 records)", "from 86 of 1,149 records" in status(page), status(page).split(" · ")[1] if " · " in status(page) else status(page))
    page.reload()
    page.wait_for_selector(f"{V} tbody tr[data-i]")
    ctx.until(page, "() => document.querySelector('#example').dataset.view && document.querySelector('data-facets input[data-p=brand][data-value=Steadywin]')")
    check("rail: the selection survives a reload", page.is_checked("data-facets input[data-p=brand][data-value=Steadywin]") and "86 of 1,149" in status(page), status(page).split(" · ")[1] if " · " in status(page) else "")
    page.fill("data-facets input[data-min=peak_torque]", "10")
    ctx.drawn(page, lambda: page.dispatch_event("data-facets input[data-min=peak_torque]", "change"))
    check("rail: a range bound narrows the rows and the URL reads peak_torque=10..", "peak_torque=10.." in page.evaluate("location.search"), page.evaluate("location.search"))
    ctx.drawn(page, lambda: page.click("data-facets [data-clear]"))
    check("rail: Clear all returns every row", "from 1,149 of 1,149 records" in status(page) and "brand=" not in page.evaluate("location.search"),
          f"{status(page).split(' · Unfold')[0]}; {page.evaluate('location.search') or 'no params'}")

    # ---- the plugin contract: propose() and the planned-type notice
    refused = page.evaluate("""async () => {
      const el = document.querySelector('#example');
      return [await el.host.propose({ id: 'cubemars-ake40-6-kv90', set: { torque_density: 1 } }), await el.host.propose({ id: 'cubemars-ake40-6-kv90', set: { brand: 'X' } })];
    }""")
    check("host.propose: a derived property refuses, a read-only page refuses, each with a reason",
          not refused[0]["ok"] and "derived" in refused[0]["reason"] and not refused[1]["ok"] and "read-only" in refused[1]["reason"], [r["reason"][:48] for r in refused])
    # WHY computed: the notice is for a type the schema knows but no built view registers; as lanes land that set shrinks,
    # so the check picks one if any is left and otherwise passes saying none is
    import json as _json, pathlib as _pathlib
    _root = _pathlib.Path(__file__).resolve().parents[3]
    known = set(_json.loads((_root / "schemas" / "view.schema.json").read_text())["$defs"]["view"]["properties"]["type"]["examples"])
    built = {v["type"] for v in _json.loads((_root / "dist" / "manifest.json").read_text())["views"] if v.get("status", "built") == "built"}
    planned = sorted(known - built)
    if planned:
        ctx.drawn(page, lambda: page.evaluate(f"document.querySelector('#example').host.setView({{ type: '{planned[0]}' }})"))
        notice = page.inner_text(f"{V} .dv-notice")
        check("a planned type draws the table with a one-line notice", f"{planned[0]} view is planned" in notice and page.locator(f"{V} tbody tr[data-i]").count() > 0, notice)
    else:
        check("a planned type draws the table with a one-line notice", True, "no planned types left: every schema type has a built view")
    page.context.close()

    dark = ctx.page(path, dark=True)
    bg = dark.evaluate("getComputedStyle(document.querySelector('#example')).backgroundColor")
    check("dark mode follows the system, in robotparts' own skin", bg == "rgb(17, 19, 23)", bg)
    dark.context.close()

    resize_checks(ctx, path)
    open_modes(ctx, path)


# ---- resizable side panels (docs/CONTRACT.md §11). WHY measured, never looked at: Zach asked for resizable panels
# before and two releases shipped fixed ones; a box's width before and after a real mouse drag is what proves it.
BOXES = """() => {
  const box = (sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect();
    return { left: r.left, right: r.right, width: r.width, top: r.top, height: r.height, hidden: !!e.hidden || !r.width }; };
  return { peek: box('#example > .dv-peek'), peekHandle: box('#example > .dv-splitter-left'), stage: box('#example .dv-stage'),
    rail: box('.demo > data-facets'), railHandle: box('.demo > .dv-splitter-right'), views: box('#example'),
    sw: document.scrollingElement.scrollWidth, iw: innerWidth,
    stored: Object.fromEntries(Object.keys(localStorage).filter((k) => k.startsWith('data-ui/panel-width/')).map((k) => [k, localStorage.getItem(k)])) };
}"""


def _drag(page, handle, dx):
    """A real pointer drag: press on the handle's middle, move dx in steps, release."""
    x, y = handle["left"] + handle["width"] / 2, handle["top"] + min(200, handle["height"] / 2)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y, steps=12)
    page.mouse.up()
    page.ctx.frames(page)
    return page.evaluate(BOXES)


def _reload(page):
    """Reload and wait until the view has drawn and the rail's handle is in place (states, not a pause)."""
    page.reload()
    page.wait_for_selector(f"{V} tbody tr[data-i]")
    page.ctx.until(page, "() => document.querySelector('#example').dataset.view && document.querySelector('.demo > .dv-splitter-right')")
    page.ctx.frames(page)


def _open_peek(page):
    tab(page, "All, flat")
    page.locator(f"{V} tbody tr.dv-row").first.click()
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    page.ctx.frames(page)
    return page.evaluate(BOXES)


def resize_checks(ctx, path):
    check = ctx.check
    page = ctx.page(path)
    page.evaluate("Object.keys(localStorage).filter((k) => k.startsWith('data-ui/panel-width/')).forEach((k) => localStorage.removeItem(k))")
    _reload(page)

    # -- the table's own column resizers (.dv-resize) keep their place: on each header's right edge, no panel line
    cols = page.evaluate(f"""() => [...document.querySelectorAll('{V} thead th .dv-resize')].slice(0, 6).map((h) => {{
      const r = h.getBoundingClientRect(), t = h.closest('th').getBoundingClientRect();
      return [Math.round(t.right - r.right), Math.round(r.width), getComputedStyle(h, '::after').content]; }})""")
    check("resize: the table's column resizers still sit on each header's right edge (the panel handle is .dv-splitter, not .dv-resize)",
          cols and all(abs(d) <= 1 and w == 10 and c in ("none", "normal") for d, w, c in cols), cols)

    # -- the peek: a handle on its left edge
    a = _open_peek(page)
    h = a["peekHandle"]
    check("resize peek: the open peek has a handle on its left edge (a vertical separator, focusable)",
          h and not h["hidden"] and abs(h["left"] + h["width"] / 2 - a["peek"]["left"]) <= 1.5 and abs(h["height"] - a["peek"]["height"]) <= 1
          and page.evaluate(f"(() => {{ const e = document.querySelector('{V} > .dv-splitter-left'); return e.getAttribute('role') === 'separator' && e.tabIndex === 0; }})()"),
          {"handle": h and round(h["left"] + h["width"] / 2), "peek left": round(a["peek"]["left"])})
    b = _drag(page, h, -150)
    grew, shown = b["peek"]["width"] - a["peek"]["width"], (b["peek"]["left"] - b["stage"]["left"]) - (a["peek"]["left"] - a["stage"]["left"])
    check("resize peek: dragging its edge 150 px left widens the peek by 150 px and the table area beside it shrinks by 150 px",
          abs(grew - 150) <= 2 and abs(shown + 150) <= 2, f"peek {a['peek']['width']:.0f} -> {b['peek']['width']:.0f} px; visible table {a['peek']['left'] - a['stage']['left']:.0f} -> {b['peek']['left'] - b['stage']['left']:.0f} px")
    check("resize peek: the handle follows the edge", abs(b["peekHandle"]["left"] + b["peekHandle"]["width"] / 2 - b["peek"]["left"]) <= 1.5,
          f"handle {b['peekHandle']['left'] + b['peekHandle']['width'] / 2:.0f}, edge {b['peek']['left']:.0f}")
    want = round(b["peek"]["width"])
    _reload(page)
    c = _open_peek(page)
    check("resize peek: the width is remembered across a reload (localStorage)", abs(c["peek"]["width"] - want) <= 1 and any("peek:example" in k for k in c["stored"]),
          f"{want} px before, {c['peek']['width']:.0f} px after; {c['stored']}")
    d = _drag(page, c["peekHandle"], 2000)
    e = _drag(page, d["peekHandle"], -3000)
    room = e["views"]["width"] - 160
    check("resize peek: min and max hold (320 px; at most the element's width less 160 px for the view)",
          abs(d["peek"]["width"] - 320) <= 1 and abs(e["peek"]["width"] - min(1200, room)) <= 2, f"dragged right: {d['peek']['width']:.0f} px; dragged left: {e['peek']['width']:.0f} px (room {room:.0f})")
    page.locator(f"{V} > .dv-splitter-left").dblclick()
    ctx.frames(page)
    f = page.evaluate(BOXES)
    check("resize peek: a double-click resets it to the default 540 px and forgets the stored width",
          abs(f["peek"]["width"] - 540) <= 1 and not any("peek:" in k for k in f["stored"]), f"{f['peek']['width']:.0f} px; {f['stored']}")
    page.focus(f"{V} > .dv-splitter-left")
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("ArrowLeft")
    g = page.evaluate(BOXES)
    page.keyboard.press("ArrowRight")
    k = page.evaluate(BOXES)
    check("resize peek: keyboard ← widens by 16 px, → narrows by 16 px",
          abs(g["peek"]["width"] - f["peek"]["width"] - 32) <= 1 and abs(k["peek"]["width"] - g["peek"]["width"] + 16) <= 1,
          f"{f['peek']['width']:.0f} -> ←← {g['peek']['width']:.0f} -> → {k['peek']['width']:.0f} px")
    page.click(f"{V} .dv-peek .dv-close")
    ctx.frames(page)
    m = page.evaluate(BOXES)
    check("resize peek: it still closes (✕), and its handle goes with it", m["peek"]["hidden"] and (m["peekHandle"] is None or m["peekHandle"]["hidden"]), m["peekHandle"])

    # -- the rail: a handle on its right edge; the views beside it give up the width
    a = page.evaluate(BOXES)
    h = a["railHandle"]
    check("resize rail: <data-facets> as a rail has a handle on its right edge", h and not h["hidden"] and abs(h["left"] + h["width"] / 2 - a["rail"]["right"]) <= 1.5,
          {"handle": h and round(h["left"] + h["width"] / 2), "rail right": round(a["rail"]["right"])})
    b = _drag(page, h, 150)
    check("resize rail: dragging its edge 150 px right widens the rail by 150 px and the views shrink by 150 px",
          abs(b["rail"]["width"] - a["rail"]["width"] - 150) <= 2 and abs(b["views"]["width"] - a["views"]["width"] + 150) <= 2,
          f"rail {a['rail']['width']:.0f} -> {b['rail']['width']:.0f} px; views {a['views']['width']:.0f} -> {b['views']['width']:.0f} px")
    want = round(b["rail"]["width"])
    _reload(page)
    c = page.evaluate(BOXES)
    check("resize rail: the width is remembered across a reload", abs(c["rail"]["width"] - want) <= 1 and any("rail:example" in k for k in c["stored"]), f"{want} -> {c['rail']['width']:.0f} px")
    d = _drag(page, c["railHandle"], -1000)
    e = _drag(page, d["railHandle"], 2000)
    check("resize rail: min 180 px and max 560 px hold", abs(d["rail"]["width"] - 180) <= 1 and abs(e["rail"]["width"] - 560) <= 1, f"{d['rail']['width']:.0f} / {e['rail']['width']:.0f} px")
    page.focus(".demo > .dv-splitter-right")
    page.keyboard.press("ArrowLeft")
    g = page.evaluate(BOXES)
    page.locator(".demo > .dv-splitter-right").dblclick()
    ctx.frames(page)
    k = page.evaluate(BOXES)
    check("resize rail: keyboard ← narrows it by 16 px; a double-click resets it to the page's 220 px",
          abs(g["rail"]["width"] - e["rail"]["width"] + 16) <= 1 and abs(k["rail"]["width"] - 220) <= 1, f"{e['rail']['width']:.0f} -> ← {g['rail']['width']:.0f} -> reset {k['rail']['width']:.0f} px")
    page.context.close()

    # -- a phone: the rail stacks, the peek fills the element; no handle, no sideways scroll
    for dark in (False, True):
        page = ctx.page(path, width=390, height=844, mobile=True, dark=dark)
        page.evaluate("localStorage.setItem('data-ui/panel-width/peek:example', '900'); localStorage.setItem('data-ui/panel-width/rail:example', '500')")
        page.reload()
        page.wait_for_selector(f"{V} tbody tr[data-i]")
        page.wait_for_timeout(250)
        a = _open_peek(page)
        # WHY the screen, not the element: since the open-modes amendment (2026-10-26) the side peek on a phone is a
        # full-screen detail with a Back (it used to fill the 358 px element); the stored 900 px must still not leak
        check(f"resize at 390 px ({'dark' if dark else 'light'}, wide widths stored): no handle shows, the peek fills the screen, the rail its column, no sideways scroll",
              (a["peekHandle"] is None or a["peekHandle"]["hidden"]) and (a["railHandle"] is None or a["railHandle"]["hidden"])
              and abs(a["peek"]["width"] - a["iw"]) <= 1 and a["rail"]["width"] >= a["views"]["width"] - 1 and a["sw"] <= 390,
              f"peek {a['peek']['width']:.0f} of a {a['iw']} px screen, rail {a['rail']['width']:.0f} px, scrollWidth {a['sw']}")
        page.context.close()


def _layout_has_options(page):
    page.click(f"{V} [data-menu=layout]")
    page.ctx.until(page, "() => !document.querySelector('#example .dv-pop').hidden")
    page.ctx.frames(page)
    ok = page.locator(f"{V} .dv-pop [data-opt]").count() >= 4 and page.locator(f"{V} .dv-pop [data-type=pivot].dv-on").count() == 1
    page.keyboard.press("Escape")
    return ok


# ---- how a record opens (`open: expand | side | link`, docs/CONTRACT.md amendment 2026-10-26 (open modes)), measured
# with getBoundingClientRect. The part pages live on robotparts.dev: every navigation a check causes on purpose is
# answered by a stub inside the browser (_catch), so nothing reaches the network.
OPEN = """() => { const el = document.querySelector('#example'); const peek = el.querySelector(':scope > .dv-peek');
  const box = (e) => { if (!e) return null; const r = e.getBoundingClientRect(); return { left: r.left, right: r.right, width: r.width, top: r.top, height: r.height }; };
  const shown = !!peek && !peek.hidden && peek.getBoundingClientRect().width > 0;
  const q = (s) => (shown ? peek.querySelector(s) : null);
  const a = document.activeElement;
  return { hash: location.hash, url: location.href, peek: shown ? (q('h2') || {}).textContent.trim() : null, peekId: el.peeked ? el.peeked.id : null,
    pos: q('.dv-open-pos') ? q('.dv-open-pos').textContent.trim() : null, openPage: q('.dv-open-page') ? q('.dv-open-page').getAttribute('href') : null,
    titleLink: q('h2 a[href]') ? q('h2 a[href]').getAttribute('href') : null, peekBox: shown ? box(peek) : null,
    table: box(el.querySelector('.dv-scroll')), stage: box(el.querySelector('.dv-stage')), views: box(el), handle: box(el.querySelector(':scope > .dv-splitter-left:not([hidden])')),
    sw: document.documentElement.scrollWidth, iw: innerWidth, focused: a && a.closest && a.closest('[data-id]') ? a.closest('[data-id]').dataset.id : null,
    status: el.querySelector('.dv-status').textContent }; }"""


def _PART(url):
    return url.startswith("https://robotparts.dev/")


def _catch(page):
    """Answer every robotparts.dev navigation with a stub page and remember the URLs asked for."""
    asked = []

    def stub(route):
        asked.append(route.request.url)
        route.fulfill(status=200, content_type="text/html", body="<!doctype html><title>stub part page</title><p>stub</p>")
    page.context.route("https://robotparts.dev/**", stub)
    return asked


def _fresh(ctx, path, width=1440, height=900, **kw):
    page = ctx.page(path, width=width, height=height, **kw)
    page.evaluate("Object.keys(localStorage).filter((k) => k.startsWith('data-ui/panel-width/')).forEach((k) => localStorage.removeItem(k))")
    return page, _catch(page)


def _url_of(page, row_id):
    return page.evaluate("(id) => document.querySelector('#example').row(id).url", row_id)


def _ids(page):
    return page.evaluate("[...document.querySelectorAll('#example tbody tr.dv-row[data-id]')].map((tr) => tr.dataset.id)")


def _top(page, row_id):
    return page.evaluate("(id) => { const tr = document.querySelector(`#example tbody tr[data-id=\"${CSS.escape(id)}\"]`); return tr ? tr.getBoundingClientRect().top : null; }", row_id)


def _guard(ctx, name, fn):
    """Run one group of checks; an exception (a missing element, a timeout) is that group's FAIL, never the suite's crash."""
    try:
        fn()
    except Exception as err:  # noqa: BLE001 - reported, not hidden
        ctx.check(name, False, f"{type(err).__name__}: {str(err).splitlines()[0][:160]}")


def open_modes(ctx, path):
    check = ctx.check
    rows = f"{V} tbody tr.dv-row"
    asked_all = []

    def expand():
        page, asked = _fresh(ctx, path)
        tab(page, "Expand in place")
        mode = page.evaluate("document.querySelector('#example').dataset.open")
        ids = _ids(page)
        before = {i: _top(page, ids[i]) for i in (2, 5)}
        page.locator(f"{V} tbody tr[data-id='{ids[1]}'] td").nth(3).click()
        page.wait_for_timeout(350)
        page.locator(f"{V} tbody tr[data-id='{ids[4]}'] td").nth(3).click()
        page.wait_for_timeout(350)
        bands = page.evaluate("[...document.querySelectorAll('#example tr.dv-open-band')].map((b) => [b.dataset.band, b.getBoundingClientRect().height])")
        h = {b: hh for b, hh in bands}
        after = {i: _top(page, ids[i]) for i in (2, 5)}
        shift2, shift5 = after[2] - before[2], after[5] - before[5]
        ok = mode == "expand" and len(bands) == 2 and h.get(ids[1], 0) > 80 and abs(shift2 - h.get(ids[1], 0)) <= 1.5 and abs(shift5 - h.get(ids[1], 0) - h.get(ids[4], 0)) <= 1.5
        check("open expand: a click opens a band under the row, two stay open at once, and each row below moves down by exactly the bands above it",
              ok, {"mode": mode, "bands": [[b[:14], round(x, 1)] for b, x in bands], "row 3 moved": round(shift2, 1), "row 6 moved": round(shift5, 1)})
        page.locator(f"{V} .dv-scroll").evaluate("el => el.scrollTo(0, el.scrollHeight)")
        page.wait_for_timeout(300)
        page.locator(f"{V} .dv-scroll").evaluate("el => el.scrollTo(0, 0)")
        page.wait_for_timeout(300)
        again = page.evaluate("[...document.querySelectorAll('#example tr.dv-open-band')].map((b) => b.dataset.band)")
        back = {i: _top(page, ids[i]) for i in (2, 5)}
        check("open expand: both bands survive a scroll to the end and back (virtualised), the rows below where they were",
              sorted(again) == sorted([ids[1], ids[4]]) and abs(back[2] - after[2]) <= 1.5 and abs(back[5] - after[5]) <= 1.5, {"bands": len(again), "row 6 top": [round(after[5]), round(back[5])]})
        band = page.evaluate(f"""() => {{ const b = document.querySelector('#example tr.dv-open-band[data-band="{ids[1]}"]');
          return {{ page: b && b.querySelector('a.dv-open-page') ? b.querySelector('a.dv-open-page').getAttribute('href') : null, photo: !!(b && b.querySelector('img')),
            chips: b ? b.querySelectorAll('.dv-open-chip').length : 0, grid: b ? b.querySelectorAll('.dv-open-grid > div').length : 0,
            title: (document.querySelector(`#example tbody tr[data-id="{ids[1]}"] a.dv-open-link`) || {{}}).href || null }}; }}""")
        url = _url_of(page, ids[1])
        check("open expand: the band holds key-spec chips, every property in a grid and 'Open page ↗' to the part's URL; the title cell is that same real link",
              band["page"] == url and band["chips"] >= 3 and band["grid"] >= 10 and band["title"] == url, band)
        page.locator(f"{V} tbody tr[data-id='{ids[1]}'] td").nth(3).click()
        page.wait_for_timeout(300)
        check("open expand: a second click folds the band; the band is not in the URL", page.locator(f"{V} tr.dv-open-band").count() == 1 and "band" not in page.url and "peek=" not in page.url, page.url.split("#")[-1])
        # the cards of a view with open: expand grow in place; the lanes reflow, so the next card in its column starts
        # just under it (TanStack's lanes put each card in the shortest column) and none overlaps it
        tab(page, "Gallery")
        page.wait_for_selector(f"{V} .dv-cards-card")
        page.wait_for_timeout(300)
        cards = "[...document.querySelectorAll('#example .dv-cards-card')].map((n) => { const r = n.getBoundingClientRect(); return [n.dataset.id, r.left, r.top, r.height, r.right, r.bottom]; })"
        first = page.evaluate(cards)[0]
        page.locator(f"{V} .dv-cards-card[data-id='{first[0]}'] .dv-cards-body").click()
        page.wait_for_timeout(400)
        after = page.evaluate(cards)
        grown = next(c for c in after if c[0] == first[0])
        under = [c for c in after if abs(c[1] - grown[1]) < 1 and c[2] > grown[2] + 1]
        overlap = [c[0] for c in after if c[0] != grown[0] and c[1] < grown[4] and c[4] > grown[1] and c[2] < grown[5] and c[5] > grown[2]]
        next_top = min((c[2] for c in under), default=None)
        check("open expand on cards: a click grows the card in place, the next card in its column starts just under it, and no card overlaps it",
              grown[3] > first[3] + 40 and next_top is not None and 0 <= next_top - grown[5] <= 13 and not overlap and page.locator(f"{V} .dv-cards-card .dv-open-more").count() == 1,
              {"card": [round(first[3]), round(grown[3])], "gap to the next in its column": next_top and round(next_top - grown[5], 1), "overlapping": overlap})
        ctx.shot(page, "open-expand-cards-light")
        asked_all.extend(asked)
        page.context.close()

    def side_split():
        page, asked = _fresh(ctx, path)
        tab(page, "All, flat")
        a = page.evaluate(OPEN)
        ids = _ids(page)
        page.locator(f"{V} tbody tr[data-id='{ids[0]}'] td").nth(3).click()
        page.wait_for_timeout(300)
        b = page.evaluate(OPEN)
        split = page.evaluate("document.querySelector('#example').classList.contains('dv-split')")
        check("open side, split (element ≥ 1100 px): the pane docks on the right and the table narrows beside it, not under it",
              b["peek"] and b["views"]["width"] >= 1100 and split and b["table"]["right"] <= b["peekBox"]["left"] + 1 and b["table"]["width"] < a["table"]["width"] - 100,
              {"element": round(b["views"]["width"]), "table right": b["table"] and round(b["table"]["right"]), "pane left": b["peekBox"] and round(b["peekBox"]["left"]),
               "table width": [round(a["table"]["width"]), round(b["table"]["width"])]})
        url = _url_of(page, ids[0])
        check("open side: the pane has the part's title as a real link, '‹ 1 of 1,149 ›' and 'Open page ↗' to its URL; the title cell is a real link too",
              b["titleLink"] == url and b["openPage"] == url and b["pos"] == "1 of 1,149" and page.get_attribute(f"{V} tbody tr[data-id='{ids[0]}'] a.dv-open-link", "href") == url,
              {k: b[k] for k in ("titleLink", "openPage", "pos")})
        for theme in ("light", "dark"):
            if theme == "dark":
                page.emulate_media(color_scheme="dark")
                page.wait_for_timeout(300)
            ctx.shot(page, f"open-side-split-{theme}")
        page.emulate_media(color_scheme="light")
        # keyboard: ↓ and j / k step through the rows with the pane open, the row's focus following; Esc closes
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(250)
        c = page.evaluate(OPEN)
        page.keyboard.press("j")
        page.wait_for_timeout(250)
        d = page.evaluate(OPEN)
        page.keyboard.press("k")
        page.wait_for_timeout(250)
        e = page.evaluate(OPEN)
        check("open side, keyboard: ↓ moves the pane to the next row (title and n of N follow, so does the row's focus); j and k step too",
              c["pos"] == "2 of 1,149" and c["peek"] != b["peek"] and c["peekId"] == ids[1] and c["focused"] == ids[1] and d["pos"] == "3 of 1,149" and e["pos"] == "2 of 1,149",
              [b["pos"], c["pos"], d["pos"], e["pos"], c["focused"] == ids[1]])
        hist = page.evaluate("history.length")
        page.keyboard.press("Escape")
        page.wait_for_timeout(350)
        f = page.evaluate(OPEN)
        check("open side, keyboard: Escape closes the pane, peek= leaves the URL and the table takes its width back",
              f["peek"] is None and "peek=" not in f["hash"] and abs(f["table"]["width"] - a["table"]["width"]) <= 2, {"hash": f["hash"], "table": round(f["table"]["width"])})
        # Enter on a focused row and a double-click on a row open the part's own page
        page.focus(f"{V} tbody tr[data-id='{ids[3]}']")
        page.keyboard.press("Enter")
        page.wait_for_url(_PART, timeout=8000)
        went = page.url
        page.go_back()
        page.wait_for_selector(f"{V} tbody tr[data-id]")
        page.wait_for_timeout(300)
        ids = _ids(page)
        page.locator(f"{V} tbody tr[data-id='{ids[5]}'] td").nth(4).dblclick()
        page.wait_for_url(_PART, timeout=8000)
        went2 = page.url
        check("open: Enter on a row and a double-click on a row open that part's page (location.assign to its URL)",
              went == _url_of_static(ctx, ids[3]) and went2 == _url_of_static(ctx, ids[5]), [went, went2])
        asked_all.extend(asked)
        page.context.close()

    def side_overlay():
        page, asked = _fresh(ctx, path, width=1180)
        tab(page, "All, flat")
        page.locator(rows).nth(0).locator("td").nth(3).click()
        page.wait_for_timeout(300)
        b = page.evaluate(OPEN)
        split = page.evaluate("document.querySelector('#example').classList.contains('dv-split')")
        check("open side, overlay (element ~900 px, under splitAt): the pane opens over the table, not beside it",
              b["peek"] and b["views"]["width"] < 1100 and not split and b["table"]["right"] > b["peekBox"]["left"] + 50,
              {"element": round(b["views"]["width"]), "table right": round(b["table"]["right"]), "pane left": b["peekBox"] and round(b["peekBox"]["left"])})
        asked_all.extend(asked)
        page.context.close()

    def resize():
        for width, label in ((1440, "split"), (1180, "overlay")):
            page, asked = _fresh(ctx, path, width=width)
            tab(page, "All, flat")
            page.locator(rows).nth(0).locator("td").nth(3).click()
            page.wait_for_timeout(300)
            a = page.evaluate(OPEN)
            b = _drag(page, a["handle"], -120)
            b = page.evaluate(OPEN)
            page.reload()
            page.wait_for_selector(f"{V} .dv-peek:not([hidden])", timeout=8000)
            page.wait_for_timeout(300)
            c = page.evaluate(OPEN)
            check(f"open side, resize ({label}): dragging the pane's .dv-splitter widens it by the drag; after a reload (the pane reopens from peek=) it has the same width",
                  a["handle"] and abs(b["peekBox"]["width"] - a["peekBox"]["width"] - 120) <= 2 and c["peekBox"] and abs(c["peekBox"]["width"] - b["peekBox"]["width"]) <= 1
                  and (label != "split" or c["table"]["right"] <= c["peekBox"]["left"] + 1),
                  {"before": a["peekBox"] and round(a["peekBox"]["width"]), "dragged": b["peekBox"] and round(b["peekBox"]["width"]), "reloaded": c["peekBox"] and round(c["peekBox"]["width"])})
            asked_all.extend(asked)
            page.context.close()

    def url_back():
        page, asked = _fresh(ctx, path)
        tab(page, "All, flat")
        ids = _ids(page)
        n0 = page.evaluate("history.length")
        page.locator(f"{V} tbody tr[data-id='{ids[2]}'] td").nth(3).click()
        page.wait_for_timeout(300)
        a = page.evaluate(OPEN)
        n1 = page.evaluate("history.length")
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(250)
        n2 = page.evaluate("history.length")
        b = page.evaluate(OPEN)
        page.go_back()
        page.wait_for_timeout(400)
        c = page.evaluate(OPEN)
        check("open side, URL: opening pushes peek=<id> (one history entry), stepping replaces it, and Back closes the pane",
              f"peek={ids[2]}" in a["hash"] and n1 == n0 + 1 and n2 == n1 and f"peek={ids[3]}" in b["hash"] and c["peek"] is None and "peek=" not in c["hash"],
              {"open": a["hash"].split("&")[-1], "history": [n0, n1, n2], "after Back": c["hash"]})
        link = f"{ctx.base}/{path}#view=all-flat&peek={ids[7]}"
        other = page.context.new_page()
        other.goto(link)
        other.wait_for_selector(f"{V} .dv-peek:not([hidden]) h2", timeout=8000)
        other.wait_for_timeout(250)
        d = other.evaluate(OPEN)
        want = other.evaluate("(id) => { const el = document.querySelector('#example'); return el.row(id).name; }", ids[7])
        check("open side, URL: a shared link with peek=<id> opens on that part's pane", d["peek"] == want and d["peekId"] == ids[7], [d["peek"], want])
        asked_all.extend(asked)
        page.context.close()

    def phone():
        page, asked = _fresh(ctx, path, width=390, height=844, mobile=True)
        tab(page, "All, flat")
        a = page.evaluate(OPEN)
        page.locator(rows).nth(1).locator("td").nth(2).tap()
        page.wait_for_timeout(400)
        b = page.evaluate(OPEN)
        back = page.locator(f"{V} .dv-peek .dv-open-back")
        visible_back = back.count() == 1 and back.is_visible()
        check("open side on a phone (390 × 844): the detail is full-screen with a visible Back, and nothing scrolls sideways, open or closed",
              b["peek"] and b["peekBox"]["left"] <= 0.5 and b["peekBox"]["width"] >= b["iw"] - 0.5 and b["peekBox"]["top"] <= 0.5 and b["peekBox"]["height"] >= 843
              and visible_back and a["sw"] <= a["iw"] and b["sw"] <= b["iw"],
              {"detail": b["peekBox"] and [round(b["peekBox"][k]) for k in ("left", "top", "width", "height")], "Back": visible_back, "scrollWidth": [a["sw"], b["sw"]]})
        ctx.shot(page, "open-side-phone-light")
        if visible_back:
            back.tap()
            page.wait_for_timeout(400)
        c = page.evaluate(OPEN)
        page.locator(rows).nth(2).locator("td").nth(2).tap()
        page.wait_for_timeout(400)
        page.go_back()
        page.wait_for_timeout(400)
        d = page.evaluate(OPEN)
        check("open side on a phone: its Back button and the browser's Back both return to the list", c["peek"] is None and d["peek"] is None and "peek=" not in d["hash"], [c["hash"], d["hash"]])
        asked_all.extend(asked)
        page.context.close()

    def link():
        page, asked = _fresh(ctx, path)
        tab(page, "Row links")
        mode = page.evaluate("document.querySelector('#example').dataset.open")
        ids = _ids(page)
        hrefs = page.evaluate("[...document.querySelectorAll('#example tbody tr.dv-row[data-id]')].slice(0, 8).map((tr) => [(tr.querySelector('td:first-child a.dv-open-link') || {}).href || null, document.querySelector('#example').row(tr.dataset.id).url])")
        check("open link: each row's title cell is a real <a href> to that row's URL", mode == "link" and hrefs and all(h == u for h, u in hrefs), {"mode": mode, "first": hrefs[:2]})
        before = page.url
        page.locator(f"{V} tbody tr[data-id='{ids[1]}'] .dv-open-check").click()
        page.wait_for_timeout(250)
        sel = page.evaluate(f"(() => {{ const tr = document.querySelector(`#example tbody tr[data-id=\"{ids[1]}\"]`); return [tr.querySelector('.dv-open-check').checked, tr.classList.contains('dv-open-sel'), document.querySelector('#example .dv-status').textContent]; }})()")
        check("open link: the row's checkbox selects it without navigating ('1 selected' in the status line)", page.url == before and sel[0] and sel[1] and "1 selected" in sel[2], [page.url == before, *sel[:2], sel[2].split("·")[-1].strip()])
        page.locator(f"{V} tbody tr[data-id='{ids[2]}'] td").nth(3).click(modifiers=["Control"])
        page.wait_for_timeout(600)
        check("open link: a Ctrl-click on a row does not navigate this page (it is a new tab's job)", page.url == before, page.url)
        page.locator(f"{V} tbody tr[data-id='{ids[2]}'] td").nth(3).click()
        page.wait_for_url(_PART, timeout=8000)
        went = page.url
        check("open link: a plain click anywhere on the row goes to that part's URL", went == _url_of_static(ctx, ids[2]), went)
        asked_all.extend(asked)
        page.context.close()

    def no_url():
        page, asked = _fresh(ctx, path)
        tab(page, "All, flat")
        page.evaluate("(() => { const el = document.querySelector('#example'); el.data = { ...el.data, linkProperty: null }; })()")
        page.wait_for_timeout(300)
        ids = _ids(page)
        links = page.locator(f"{V} tbody a.dv-open-link").count()
        page.evaluate("document.addEventListener('click', (e) => { if (e.detail === 2) window.__sel = getSelection().toString(); }, true)")
        page.locator(f"{V} tbody tr[data-id='{ids[1]}'] td").first.dblclick()
        page.wait_for_timeout(400)
        a = page.evaluate(OPEN)
        sel = page.evaluate("[window.__sel, getSelection().toString()]")
        tab(page, "Expand in place")
        page.locator(rows).nth(0).locator("td").nth(3).click()
        page.wait_for_timeout(300)
        band_page = page.locator(f"{V} tr.dv-open-band .dv-open-page").count()
        band_links = page.locator(f"{V} tbody a.dv-open-link").count()
        check("open, no URL: no title links, no 'Open page'; a double-click stays on the list, selects no text and leaves the pane on its row",
              links == 0 and band_links == 0 and a["peek"] and a["openPage"] is None and a["titleLink"] is None and band_page == 0 and sel == ["", ""] and a["peekId"] == ids[1] and not asked,
              {"links": [links, band_links], "Open page": [a["openPage"], band_page], "selected": sel, "navigated": asked[:1]})
        page.context.close()

    def themes():
        for theme in ("light", "dark"):
            page, asked = _fresh(ctx, path, dark=theme == "dark")
            tab(page, "Expand in place")
            ids = _ids(page)
            page.locator(f"{V} tbody tr[data-id='{ids[0]}'] td").nth(3).click()
            page.wait_for_timeout(400)
            ctx.shot(page, f"open-expand-{theme}")
            contrast = page.evaluate("""() => { const b = document.querySelector('#example tr.dv-open-band'); if (!b) return null;
              const fg = getComputedStyle(b.querySelector('.dv-open-grid dd') || b).color, bg = getComputedStyle(b.querySelector('td')).backgroundColor; return [fg, bg]; }""")
            check(f"open expand ({theme}): the band draws in the theme's colours", contrast and _lum_ratio(*contrast) >= 4.5, contrast and [*contrast, round(_lum_ratio(*contrast), 1)])
            page.context.close()

    for name, fn in (("open expand", expand), ("open side, split", side_split), ("open side, overlay", side_overlay), ("open side, resize", resize),
                     ("open side, URL", url_back), ("open side on a phone", phone), ("open link", link), ("open, no URL", no_url), ("open themes", themes)):
        _guard(ctx, f"{name}: ran to the end", fn)
    _guard(ctx, "open under frame=bleed: ran to the end", lambda: open_bleed(ctx, path))
    # WHY drop them: these are navigations the checks caused on purpose and answered in the browser with a stub
    # (_catch), not anything the kit loaded; "nothing loaded from another site" stays about the kit
    ctx.foreign[:] = [u for u in ctx.foreign if u not in asked_all]


# ---- the open modes under frame="bleed" (CONTRACT §12, lane/frame): the page scrolls the rows, not the table. Two
# scrollers, as robotparts has them: the window (a phone, a page with one scroll) and a results pane that scrolls on its
# own (robotparts from 768 px; here the case's .live section made 760 px tall). Skipped, and said so, on a build
# without frame=.
BLEED = """() => { const el = document.querySelector('#example'); const sc = el.host.scroller;
  const box = (e) => { if (!e) return null; const r = e.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height }; };
  const peek = el.querySelector(':scope > .dv-peek'); const shown = peek && !peek.hidden && peek.getBoundingClientRect().width > 0;
  const port = !sc ? null : sc === window ? { top: 0, bottom: innerHeight, right: document.documentElement.clientWidth } : box(sc);
  const a = document.activeElement; const thead = el.querySelector('.dv-table thead');
  return { scroll: el.dataset.scroll || null, window: sc === window, top: !sc ? null : sc === window ? scrollY : sc.scrollTop, port,
    split: el.classList.contains('dv-split'), peek: shown ? box(peek) : null, peekId: el.peeked ? el.peeked.id : null,
    pos: shown && peek.querySelector('.dv-open-pos') ? peek.querySelector('.dv-open-pos').textContent.trim() : null,
    table: box(el.querySelector('.dv-scroll')), band: box(el.querySelector(':scope > .dv-status')), thead: box(thead), views: box(el),
    focused: a && a.closest && a.closest('tr[data-id]') ? a.closest('tr[data-id]').dataset.id : null,
    focusBox: a && a.closest && a.closest('tr[data-id]') ? box(a.closest('tr[data-id]')) : null,
    sw: document.documentElement.scrollWidth, iw: innerWidth, ih: innerHeight }; }"""


def _bleed_page(ctx, path, width=1440, height=900, pane=False, **kw):
    """The case page with frame="bleed" set live; with `pane`, its .live section scrolls on its own. None without frame."""
    page = ctx.page(path, width=width, height=height, **kw)
    page.evaluate("Object.keys(localStorage).filter((k) => k.startsWith('data-ui/panel-width/')).forEach((k) => localStorage.removeItem(k))")
    if pane:
        page.evaluate("(() => { const l = document.querySelector('.live'); l.style.height = '760px'; l.style.overflowY = 'auto'; l.scrollIntoView(); })()")
    page.evaluate("document.querySelector('#example').setAttribute('frame', 'bleed')")
    page.wait_for_timeout(700)
    if page.evaluate("document.querySelector('#example').dataset.scroll") != "page":
        page.context.close()
        return None
    if pane:
        # the whole pane inside the window, so only the pane scrolls from here on (as robotparts' results pane)
        page.evaluate("(() => { const l = document.querySelector('.live'); scrollTo(0, l.getBoundingClientRect().top + scrollY - 40); })()")
        page.wait_for_timeout(300)
    return page


def _scroll(page, dy):
    page.evaluate(f"(() => {{ const sc = document.querySelector('#example').host.scroller; if (sc === window) scrollBy(0, {dy}); else sc.scrollTop += {dy}; }})()")
    page.wait_for_timeout(300)
    return page.evaluate(BLEED)


def _visible_row(page, at=0.5):
    """The id of a drawn row whose top sits `at` of the way down the visible rows (under the band and the header)."""
    return page.evaluate(f"""(() => {{ const el = document.querySelector('#example'); const sc = el.host.scroller;
      const top = el.querySelector('.dv-table thead').getBoundingClientRect().bottom;
      const bottom = Math.min(innerHeight, sc === window ? innerHeight : sc.getBoundingClientRect().bottom);
      const want = top + ({at}) * (bottom - top - 40);
      const rows = [...el.querySelectorAll('tbody tr.dv-row[data-id]')].filter((tr) => tr.getBoundingClientRect().top >= want);
      return rows.length ? rows[0].dataset.id : null; }})()""")


def open_bleed(ctx, path):
    check = ctx.check
    probe = _bleed_page(ctx, path)
    if probe is None:
        check("open under frame=bleed: skipped, this build has no frame= (lane/frame not merged)", True, "no data-scroll=page after frame=bleed")
        return
    probe.context.close()
    for pane in (False, True):
        where = "a scrolling pane" if pane else "the window"
        # side, split: the pane stays on screen while the page scrolls, docked under the band, the table beside it
        page = _bleed_page(ctx, path, pane=pane)
        _catch(page)
        tab(page, "All, flat")
        _scroll(page, 1500)
        row = _visible_row(page, 0.3)
        page.locator(f"{V} tbody tr[data-id='{row}'] td").nth(3).click()
        page.wait_for_timeout(400)
        a = page.evaluate(BLEED)
        win = page.evaluate("scrollY")
        b = _scroll(page, 1500)
        ok = lambda s: (s["peek"] and s["split"] and s["table"]["right"] <= s["peek"]["left"] + 1 and s["peek"]["top"] >= s["band"]["bottom"] - 1
                        and s["peek"]["top"] >= s["port"]["top"] - 1 and s["peek"]["bottom"] <= s["port"]["bottom"] + 1 and s["peek"]["height"] > 300)
        check(f"open side, split under frame=bleed ({where}): after the page scrolls 1,500 px and 1,500 more, the pane stays on screen under the band, the table beside it",
              ok(a) and ok(b) and abs(a["peek"]["top"] - b["peek"]["top"]) <= 1 and b["top"] > a["top"] + 1000,
              {"scrolled": [a["top"], b["top"]], "pane": b["peek"] and [round(b["peek"][k]) for k in ("left", "top", "bottom")], "band bottom": b["band"] and round(b["band"]["bottom"]),
               "table right": b["table"] and round(b["table"]["right"]), "split": b["split"]})
        # ↑/↓ step the pane; the stepped row is scrolled into view under the band and the column header
        page.locator(f"{V} tbody tr[data-id='{_visible_row(page, 0.92)}'] td").nth(3).click()
        page.wait_for_timeout(300)
        for _ in range(6):
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(120)
        page.wait_for_timeout(300)
        down = page.evaluate(BLEED)
        page.locator(f"{V} tbody tr[data-id='{_visible_row(page, 0.02)}'] td").nth(3).click()
        page.wait_for_timeout(300)
        for _ in range(6):
            page.keyboard.press("ArrowUp")
            page.wait_for_timeout(120)
        page.wait_for_timeout(300)
        up = page.evaluate(BLEED)
        if pane:
            check("open under frame=bleed (a scrolling pane): the window itself never scrolled; only the pane did", page.evaluate("scrollY") == win, [win, page.evaluate("scrollY")])
        seen = lambda s: (s["focusBox"] and s["focused"] == s["peekId"] and s["focusBox"]["top"] >= max(s["thead"]["bottom"], s["band"]["bottom"]) - 1
                          and s["focusBox"]["bottom"] <= min(s["port"]["bottom"], s["ih"]) + 1)
        check(f"open side, keyboard under frame=bleed ({where}): ↓ and ↑ scroll the stepped row into view (below the pinned header, above the bottom), the pane on it",
              seen(down) and seen(up),
              {"↓ row": down["focusBox"] and [round(down["focusBox"]["top"]), round(down["focusBox"]["bottom"])], "↑ row": up["focusBox"] and [round(up["focusBox"]["top"]), round(up["focusBox"]["bottom"])],
               "header / band bottom": [[round(s["thead"]["bottom"]), round(s["band"]["bottom"])] for s in (down, up)], "port bottom": round(down["port"]["bottom"]), "pos": [down["pos"], up["pos"]]})
        if not pane:
            ctx.shot(page, "open-side-split-bleed-light")
        page.keyboard.press("Escape")
        # expand: a band pushes the rows below it down by its height while the page, not the table, scrolls
        tab(page, "Expand in place")
        _scroll(page, 1500)
        ids = page.evaluate("[...document.querySelectorAll('#example tbody tr.dv-row[data-id]')].map((tr) => tr.dataset.id)")
        first = _visible_row(page, 0.15)
        i = ids.index(first)
        nxt, far = ids[i + 1], ids[i + 3]
        before = {k: _top(page, k) for k in (nxt, far)}
        page.locator(f"{V} tbody tr[data-id='{first}'] td").nth(3).click()
        page.wait_for_timeout(500)
        h = page.evaluate(f"(document.querySelector('#example tr.dv-open-band[data-band=\"{first}\"]') || {{getBoundingClientRect: () => ({{height: 0}})}}).getBoundingClientRect().height")
        after = {k: _top(page, k) for k in (nxt, far)}
        _scroll(page, 4000)
        back = _scroll(page, -4000)
        again = {k: _top(page, k) for k in (nxt, far)}
        bands = page.locator(f"{V} tr.dv-open-band").count()
        check(f"open expand under frame=bleed ({where}): the band pushes the rows below down by its height, and after the page scrolls 4,000 px away and back they are where they were",
              h > 80 and all(abs(after[k] - before[k] - h) <= 1.5 for k in after) and all(abs(again[k] - after[k]) <= 1.5 for k in after) and bands == 1 and back["scroll"] == "page",
              {"band": round(h, 1), "moved": [round(after[k] - before[k], 1) for k in after], "after the round trip": [round(again[k] - after[k], 1) for k in after]})
        page.context.close()
    # overlay (element under splitAt) and a phone's full screen, under frame=bleed
    page = _bleed_page(ctx, path, width=1180)
    tab(page, "All, flat")
    _scroll(page, 1500)
    page.locator(f"{V} tbody tr[data-id='{_visible_row(page, 0.3)}'] td").nth(3).click()
    page.wait_for_timeout(400)
    o = _scroll(page, 800)
    check("open side, overlay under frame=bleed (element ~900 px): the pane covers the right of the visible rows, on screen after the page scrolls",
          o["peek"] and not o["split"] and o["views"]["width"] < 1100 and o["table"]["right"] > o["peek"]["left"] + 50 and o["peek"]["top"] >= o["port"]["top"] - 1 and o["peek"]["bottom"] <= o["port"]["bottom"] + 1,
          {"element": round(o["views"]["width"]), "pane": o["peek"] and [round(o["peek"][k]) for k in ("left", "top", "bottom")], "table right": round(o["table"]["right"])})
    page.context.close()
    page = _bleed_page(ctx, path, width=390, height=844, mobile=True)
    tab(page, "All, flat")
    _scroll(page, 1500)
    page.locator(f"{V} tbody tr[data-id='{_visible_row(page, 0.3)}'] td").nth(2).tap()
    page.wait_for_timeout(500)
    f = page.evaluate(BLEED)
    check("open side on a phone under frame=bleed: the detail is the whole screen after the page scrolled, nothing scrolls sideways",
          f["peek"] and abs(f["peek"]["left"]) <= 0.5 and abs(f["peek"]["top"]) <= 0.5 and f["peek"]["width"] >= f["iw"] - 0.5 and f["peek"]["height"] >= f["ih"] - 1 and f["sw"] <= f["iw"],
          {"detail": f["peek"] and [round(f["peek"][k]) for k in ("left", "top", "width", "height")], "scrollWidth": f["sw"]})
    page.context.close()


_ROWS = None


def _url_of_static(ctx, row_id):
    """A row's URL from the case's own data file (the page under test may have navigated away)."""
    global _ROWS
    if _ROWS is None:
        import json as _json, pathlib as _pathlib
        _ROWS = {r["id"]: r.get("url") for r in _json.loads((_pathlib.Path(__file__).parent / "actuators.json").read_text())["rows"]}
    return _ROWS.get(row_id)


def _lum_ratio(fg, bg):
    """WCAG contrast ratio of two rgb()/rgba() strings."""
    def lum(text):
        parts = [float(x) for x in text[text.index("(") + 1:text.index(")")].replace("/", ",").split(",")[:3]]
        c = [(v / 255) / 12.92 if v / 255 <= 0.03928 else (((v / 255) + 0.055) / 1.055) ** 2.4 for v in parts]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)
