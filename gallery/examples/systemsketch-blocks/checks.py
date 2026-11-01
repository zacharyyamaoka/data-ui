"""Browser checks for this case (run by tests/browser/checks.py): a SystemSketch board as a graph. Every block and
connection drawn, the six connections between the mission BT and the motion controller each with its own label
spot, a TB preset grouped by block type, a block opens its record, light / dark at 1280 and 390 px."""

V = "#example"
CASE = "systemsketch-blocks"


def _open(ctx, path, view, **kw):
    """ctx.page() waits for the status line; then wait for the view the element says it drew."""
    page = ctx.page(path, **kw)
    page.wait_for_selector(f"{V}[data-view='{view}']", timeout=15000)
    page.wait_for_timeout(300)
    return page


def _frame(page):
    """Scroll the view to the top of the window, below the site's sticky header, for a screenshot."""
    page.evaluate("""() => {
      const el = document.querySelector('#example'), bar = document.querySelector('header.top, .top');
      window.scrollTo(0, el.getBoundingClientRect().top + scrollY - (bar ? bar.offsetHeight : 0) - 8);
    }""")
    page.wait_for_timeout(150)


def run(ctx, path):
    check = ctx.check
    page = _open(ctx, path, "graph")
    nodes = page.locator(f"{V} .react-flow__node-dvrow").count()
    edges = page.locator(f"{V} .react-flow__edge").count()
    labels = page.locator(f"{V} .dv-graph-elabel").all_inner_texts()
    check("systemsketch: 8 blocks as nodes, 13 connections as edges named by their output port", nodes == 8 and edges == 13 and {"move.goal", "pose.reply", "detections", "frame"} <= set(labels), f"{nodes} nodes, {edges} edges, {len(labels)} labels")
    spots = page.evaluate("""() => {
      const pair = new Set(['move.cancel', 'move.goal', 'pose.query', 'move.feedback', 'move.result', 'pose.reply']);
      return [...document.querySelectorAll('#example .dv-graph-elabel')].filter((e) => pair.has(e.textContent))
        .map((e) => { const r = e.getBoundingClientRect(); return `${Math.round(r.x)},${Math.round(r.y)}`; });
    }""")
    check("graph: parallel edges between one pair spread apart, each label in its own spot", len(spots) == 6 and len(set(spots)) == 6, spots)
    page.click(f"{V} .react-flow__node[data-id='perception']")
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    peek = page.inner_text(f"{V} .dv-peek")
    check("systemsketch: a block opens its record with its ports", "Perception" in peek and "image: Image" in peek, page.inner_text(f"{V} .dv-peek h2"))
    page.keyboard.press("Escape")
    page.click(f"{V} .dv-tab[data-name='By block type']")
    page.wait_for_timeout(500)
    groups = page.locator(f"{V} .dv-graph-grouplabel").all_inner_texts()
    cam, per = (page.locator(f"{V} .react-flow__node[data-id='{n}']").bounding_box() for n in ("camera", "perception"))
    check("systemsketch: grouped by block type (4 subflows), laid out top to bottom", len(groups) == 4 and per["y"] > cam["y"], [g.split()[0] for g in groups])
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            page = _open(ctx, path, "graph", width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            scheme = "dark" if dark else "light"
            drawn = page.locator(f"{V} .react-flow__node-dvrow").count()
            scroll = page.evaluate("document.scrollingElement.scrollWidth")
            minimap = page.locator(f"{V} .react-flow__minimap").count()
            check(f"systemsketch, {scheme}, {width} px: the graph draws, minimap only on wide screens, no sideways page scroll",
                  drawn == 8 and scroll <= width and minimap == (0 if mobile else 1), f"{drawn} nodes, minimap {minimap}, scrollWidth {scroll}")
            _frame(page)
            ctx.shot(page, f"{CASE}-{scheme}-{width}")
            page.context.close()
