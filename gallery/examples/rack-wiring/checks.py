"""Browser checks for this case (run by tests/browser/checks.py): the graph view on the rack's wiring. The React
island loads only when a graph shows, wires keep their colours, a node and a subflow open the peek, the canvas pans
and zooms, a TB layout runs top to bottom, and light / dark at 1280 and 390 px. The peek's trail follows the wires
(`feeds`, the file's `edges:` property) from record to record: split, overlay and a phone's full screen."""

import json
import pathlib

V = "#example"
CASE = "rack-wiring"


def _open(ctx, path, view, **kw):
    """ctx.page() waits for the status line; then wait for the view the element says it drew."""
    page = ctx.page(path, **kw)
    page.wait_for_selector(f"{V}[data-view='{view}']", timeout=15000)
    page.wait_for_timeout(300)
    return page


def _views_loaded(page):
    return page.evaluate("performance.getEntriesByType('resource').map(e => e.name.split('/').pop()).filter(n => /^(table|graph|calendar|timeline|map)\\.js$/.test(n))")


def _tab(page, name):
    page.click(f"{V} .dv-tab[data-name='{name}']")
    page.wait_for_timeout(500)


def _box(page, node_id):
    return page.locator(f"{V} .react-flow__node[data-id='{node_id}']").bounding_box()


def _frame(page):
    """Scroll the view to the top of the window, below the site's sticky header, for a screenshot."""
    page.evaluate("""() => {
      const el = document.querySelector('#example'), bar = document.querySelector('header.top, .top');
      window.scrollTo(0, el.getBoundingClientRect().top + scrollY - (bar ? bar.offsetHeight : 0) - 8);
    }""")
    page.wait_for_timeout(150)


def _empty_pane_point(page):
    """A visible point where the pane itself is on top (no node, edge, control or minimap), to drag from."""
    page.locator(f"{V} .react-flow").scroll_into_view_if_needed()
    return page.evaluate("""() => {
      const pane = document.querySelector('#example .react-flow__pane');
      const r = pane.getBoundingClientRect();
      for (let fy = 0.15; fy < 0.9; fy += 0.05) for (let fx = 0.3; fx < 0.8; fx += 0.05) {
        const x = r.left + r.width * fx, y = r.top + r.height * fy;
        if (y > innerHeight - 10) continue;
        if (document.elementFromPoint(x, y) === pane) return [x, y];
      }
      return [r.left + r.width / 2, r.top + 20];
    }""")


RACK = {r["id"]: r for r in json.loads((pathlib.Path(__file__).parent / "rack.json").read_text(encoding="utf-8"))["rows"]}
CHAIN = ["psu", "clamp", "xt30_junction"]  # the supply wires to the regen clamp, the clamp to the XT30 junction


def _trail(page):
    """The peek as drawn: its record, its crumbs (text, current?) and the URL's peek= / trail=, each measured."""
    return page.evaluate("""() => {
      const el = document.querySelector('#example'), peek = el.querySelector('.dv-peek');
      const pr = peek.getBoundingClientRect();
      const crumbs = [...peek.querySelectorAll('.dv-open-trail li')].filter((li) => li.querySelector('button, [aria-current]'));
      const h = new URLSearchParams(location.hash.slice(1));
      return { open: !peek.hidden, id: peek.hidden ? null : (peek.querySelector('.dv-open-rec') || {}).dataset?.id || null,
        crumbs: crumbs.map((li) => li.textContent.trim()), current: crumbs.map((li) => !!li.querySelector('[aria-current=page]')),
        inside: crumbs.every((li) => { const r = li.getBoundingClientRect(); return r.width > 0 && r.left >= pr.left - 0.5 && r.right <= pr.right + 0.5 && r.top >= pr.top - 0.5; }),
        peek: h.get('peek'), trail: h.getAll('trail'), split: el.classList.contains('dv-split'), full: el.classList.contains('dv-full'),
        overflow: peek.scrollWidth > peek.clientWidth + 1 };
    }""")


def _follow(ctx, page, to):
    """Click the wire to `to` in the open record's fields (a relation link) and wait for the peek to show it."""
    page.click(f"{V} .dv-peek .dv-fields a[data-open-rel='{to}']")
    ctx.until(page, "(id) => (document.querySelector('#example .dv-peek .dv-open-rec') || {}).dataset?.id === id", to)
    ctx.frames(page)


def _walk(ctx, page):
    """Open the supply's row, then follow its wires: supply -> clamp -> XT30 junction."""
    page.click(f"{V} tr.dv-row[data-id='{CHAIN[0]}'] td:nth-child(2)")
    ctx.until(page, "() => !document.querySelector('#example .dv-peek').hidden")
    for to in CHAIN[1:]:
        _follow(ctx, page, to)
    return _trail(page)


def peek_trail(ctx, path):
    """Notion's side peek keeps the path of pages opened from inside it; so does this one: a relation (`feeds`) in a
    record opens the record it names in the same peek, the trail shows every step, a crumb jumps back, Escape and Back
    step back one level before closing, the URL holds peek= and trail= (and round-trips on reload), and ⤢ opens the
    current record's page."""
    check = ctx.check
    names = [RACK[i]["name"] for i in CHAIN]
    for label, width, mobile in (("split", 1600, False), ("overlay", 1000, False), ("phone", 390, True)):
        page = ctx.page(f"{path}#view=parts", width=width, height=900 if width > 400 else 844, mobile=mobile)
        page.wait_for_selector(f"{V}[data-view='table'] tr.dv-row[data-id='psu']", timeout=15000)
        got = _walk(ctx, page)
        where = {"split": got["split"] and not got["full"], "overlay": not got["split"] and not got["full"], "phone": got["full"]}[label]
        check(f"peek trail ({label}): following the wires supply -> clamp -> XT30 junction keeps a 3-crumb trail, the last one current, inside the pane",
              where and got["id"] == CHAIN[-1] and got["crumbs"] == names and got["current"] == [False, False, True] and got["inside"] and not got["overflow"], got)
        check(f"peek trail ({label}): the URL's peek= is the current record and trail= the steps before it",
              got["peek"] == CHAIN[-1] and got["trail"] == CHAIN[:-1], {"peek": got["peek"], "trail": got["trail"]})
        if label == "phone":
            back = []
            for _ in range(3):
                page.click(f"{V} .dv-peek .dv-open-back")
                ctx.frames(page)
                t = _trail(page)
                back.append((t["open"], t["id"], len(t["crumbs"])))
            check("peek trail (phone): ‹ Back steps back one record at a time (XT30 -> clamp -> supply), then returns to the list",
                  back == [(True, "clamp", 2), (True, "psu", 0), (False, None, 0)], back)
            page.context.close()
            continue
        page.click(f"{V} .dv-peek .dv-open-trail li:first-child button")
        ctx.frames(page)
        t = _trail(page)
        check(f"peek trail ({label}): the first crumb jumps back to the supply, and the trail is trimmed to it",
              t["open"] and t["id"] == "psu" and t["crumbs"] == [] and t["peek"] == "psu" and t["trail"] == [], t)
        _follow(ctx, page, "clamp")
        _follow(ctx, page, "xt30_junction")
        steps = []
        for _ in range(3):
            page.keyboard.press("Escape")
            ctx.frames(page)
            t = _trail(page)
            steps.append((t["open"], t["id"], len(t["crumbs"]), t["peek"]))
        check(f"peek trail ({label}): Escape steps back one record at a time, then closes the peek (and takes peek= out of the URL)",
              steps == [(True, "clamp", 2, "clamp"), (True, "psu", 0, "psu"), (False, None, 0, None)], steps)
        if label == "split":
            got = _walk(ctx, page)
            url = page.url
            page.reload()
            page.wait_for_selector(f"{V}[data-view='table'] tr.dv-row", timeout=15000)
            ctx.until(page, "() => !document.querySelector('#example .dv-peek').hidden")
            ctx.frames(page)
            t = _trail(page)
            check("peek trail: a reload of that URL reopens the same record with the same 3-crumb trail",
                  page.url == url and t["id"] == CHAIN[-1] and t["crumbs"] == names, {"before": got["crumbs"], "after": t["crumbs"], "url": url == page.url})
            expand = page.evaluate("""() => { const a = document.querySelector('#example .dv-peek header a.dv-open-expand');
              return a ? { href: a.href, label: a.getAttribute('aria-label'), tag: a.tagName } : null; }""")
            check("peek trail: ⤢ is a real link to the current record's page (its url), labelled 'Open as page'",
                  expand == {"href": RACK[CHAIN[-1]]["url"], "label": "Open as page", "tag": "A"}, expand)
            ctx.shot(page, "rack-wiring-peek-trail-light-1600")
        page.context.close()


def run(ctx, path):
    check = ctx.check
    peek_trail(ctx, path)

    # ---- React loads only when a graph shows: open on the table preset, then switch
    page = _open(ctx, f"{path}#view=parts", "table")
    before = _views_loaded(page)
    _tab(page, "Wiring")
    page.wait_for_selector(f"{V}[data-view='graph'] .react-flow__node", timeout=15000)
    after = _views_loaded(page)
    check("graph: React (inside graph.js) loads only when a graph shows", "graph.js" not in before and "graph.js" in after, f"table preset loaded {before}; after the switch {after}")
    page.context.close()

    page = _open(ctx, path, "graph")
    nodes = page.locator(f"{V} .react-flow__node-dvrow").count()
    groups = page.locator(f"{V} .react-flow__node-dvgroup").count()
    edges = page.locator(f"{V} .react-flow__edge").count()
    check("rack: 10 parts as nodes, 9 wires as edges, 5 role subflows", (nodes, edges, groups) == (10, 9, 5), f"{nodes} nodes, {edges} edges, {groups} subflows")
    strokes = page.evaluate("""() => {
      const out = {};
      for (const g of document.querySelectorAll('#example .react-flow__edge')) {
        const id = g.dataset.id;
        out[id] = getComputedStyle(g.querySelector('.react-flow__edge-path')).stroke;
      }
      return out;
    }""")
    power, can, phases = strokes["psu->clamp#0"], strokes["fdcanusb->ph3_junction#0"], strokes["r4_11->motor_r4_11#0"]
    labels = sorted(set(page.locator(f"{V} .dv-graph-elabel").all_inner_texts()))
    check("rack: power, CAN and phase wires each keep their own colour and label", len({power, can, phases}) == 3 and labels == ["CAN", "phases", "power"], f"power {power}, CAN {can}, phases {phases}; labels {labels}")
    status = page.inner_text(f"{V} .dv-status")
    check("rack: the status line counts nodes and edges", "10 nodes · 9 edges" in status, status)

    page.click(f"{V} .react-flow__node[data-id='psu']")
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    title = page.inner_text(f"{V} .dv-peek h2")
    active = page.locator(f"{V} .react-flow__node[data-id='psu'] .dv-graph-node.dv-active").count()
    check("graph: a click on a node opens its record and marks the node", "CNCTOPBAOS" in title and active == 1, title)
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    page.click(f"{V} .dv-graph-grouplabel:has-text('Power')")
    page.wait_for_selector(f"{V} .dv-peek:not([hidden]) .dv-peektable")
    listed = page.locator(f"{V} .dv-peek .dv-peektable tbody tr").count()
    check("graph: a subflow's label lists the rows in it", listed == 3, f"{listed} records listed for Power")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    viewport = f"{V} .react-flow__viewport"
    t0 = page.eval_on_selector(viewport, "el => el.style.transform")
    x, y = _empty_pane_point(page)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 120, y - 40, steps=8)
    page.mouse.up()
    page.wait_for_timeout(200)
    t1 = page.eval_on_selector(viewport, "el => el.style.transform")
    page.click(f"{V} .react-flow__controls-zoomin")
    page.wait_for_timeout(400)
    t2 = page.eval_on_selector(viewport, "el => el.style.transform")
    scale = lambda t: float(t.split("scale(")[1].rstrip(")"))
    check("graph: the canvas pans by drag and zooms from its controls", t1 != t0 and scale(t2) > scale(t1), f"{t0} -> {t1} -> zoom {scale(t2):.3f}")
    check("graph: a minimap at desktop width", page.locator(f"{V} .react-flow__minimap").count() == 1)

    _tab(page, "Power path")
    page.wait_for_selector(f"{V} .react-flow__node[data-id='psu']")
    ys = {n: _box(page, n)["y"] for n in ("psu", "clamp", "xt30_junction", "r4_11", "motor_r4_11")}
    order = sorted(ys, key=ys.get)
    check("graph: layout direction TB draws the power path top to bottom", order == ["psu", "clamp", "xt30_junction", "r4_11", "motor_r4_11"], order)
    _tab(page, "Parts")
    check("rack: the same rows as a table", page.locator(f"{V} tbody tr.dv-row").count() == 10)
    page.context.close()

    # ---- light and dark, desktop and phone
    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            page = _open(ctx, path, "graph", width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            scheme = "dark" if dark else "light"
            drawn = page.locator(f"{V} .react-flow__node-dvrow").count()
            bg = page.eval_on_selector(f"{V} .react-flow__node[data-id='psu'] .dv-graph-node", "el => getComputedStyle(el).backgroundColor")
            scroll = page.evaluate("document.scrollingElement.scrollWidth")
            ok = drawn == 10 and scroll <= width and (bg != "rgb(255, 255, 255)" if dark else bg == "rgb(255, 255, 255)")
            check(f"rack, {scheme}, {width} px: the graph draws in the theme, no sideways page scroll", ok, f"{drawn} nodes, card {bg}, scrollWidth {scroll}")
            _frame(page)
            ctx.shot(page, f"{CASE}-{scheme}-{width}")
            page.context.close()
