"""Browser checks for this case (run by tests/browser/checks.py): Vibe Tracks' decision records as a table, newest
first, and as the graph of what each depends on, drawn by both engines (CONTRACT §30, graph layout engines).
Every count is measured on the drawn SVG / canvas (node groups and edge paths), against decisions.json read here: 15
records, 23 declared edges. A Mermaid node opens the peek by click and by Enter; labels are the titles as written; a
React Flow reader never downloads Mermaid; light and dark at 1280 and 390 px."""

import json
import pathlib

V = "#example"
ROWS = json.loads((pathlib.Path(__file__).parent / "decisions.json").read_text(encoding="utf-8"))
TITLE = {r["id"]: r["title"] for r in ROWS}
EDGES = sum(len(r["depends_on"]) for r in ROWS)  # 23: the oracle's hand-read edges

# what each engine drew, measured: node groups and edge paths in the SVG / React Flow's own node and edge elements
MERMAID = """() => {
  const svg = document.querySelector('#example .dv-graph-mermaid svg');
  if (!svg) return null;
  const nodes = [...svg.querySelectorAll('g.node')];
  return { nodes: nodes.length, edges: svg.querySelectorAll('.edgePaths path.flowchart-link').length,
    labels: nodes.map((g) => [g.getAttribute('data-row'), g.querySelector('.nodeLabel') ? g.querySelector('.nodeLabel').textContent : null]),
    focusable: nodes.filter((g) => g.getAttribute('tabindex') === '0' && g.getAttribute('role') === 'button' && g.getAttribute('aria-label')).length,
    cursor: nodes.length ? getComputedStyle(nodes[0]).cursor : null,
    fill: nodes.length ? getComputedStyle(nodes[0].querySelector('rect, path, polygon')).fill : null,
    sw: document.scrollingElement.scrollWidth, svgWidth: svg.getBoundingClientRect().width,
    box: (() => { const b = svg.parentElement; return { cw: b.clientWidth, sw: b.scrollWidth, overflow: getComputedStyle(b).overflow }; })() };
}"""
FLOW = """() => ({ nodes: document.querySelectorAll('#example .react-flow__node-dvrow').length,
  edges: document.querySelectorAll('#example .react-flow__edge').length })"""
PEEK = "() => { const p = document.querySelector('#example .dv-peek'); return p && !p.hidden ? { id: (p.querySelector('.dv-open-rec') || {}).dataset?.id || null, title: (p.querySelector('.dv-open-rec h2') || {}).textContent || null } : null; }"
LOADED = "() => performance.getEntriesByType('resource').map((e) => e.name.split('/').pop()).filter((n) => n.startsWith('graph'))"
LEFTOVER = "() => [...document.body.children].filter((e) => /^[di]?dv-mermaid-/.test(e.id)).map((e) => e.id)"


def _open(ctx, path, **kw):
    page = ctx.page(path, **kw)
    page.wait_for_selector(f"{V}[data-view]", timeout=20000)
    return page


def _tab(ctx, page, name):
    ctx.drawn(page, lambda: page.click(f"{V} .dv-tab[data-name='{name}']"))


def _map(ctx, page):
    _tab(ctx, page, "Map")
    ctx.until(page, "() => document.querySelectorAll('#example .dv-graph-mermaid svg g.node').length > 0")
    return page.evaluate(MERMAID)


def _frame(page):
    """Scroll the view to the top of the window, below the site's sticky header, for a screenshot."""
    page.evaluate("""() => {
      const el = document.querySelector('#example'), bar = document.querySelector('header.top, .top');
      window.scrollTo(0, el.getBoundingClientRect().top + scrollY - (bar ? bar.offsetHeight : 0) - 8);
    }""")
    page.wait_for_timeout(150)


def run(ctx, path):
    check = ctx.check
    page = _open(ctx, path, width=1280, height=900)
    first = page.locator(f"{V} tbody tr").first
    check("decisions: the table is newest first; its first row is 0013 (2026-10-26)",
          first.get_attribute("data-id") == "vibetracks:0013" and "0013" in first.inner_text(), first.inner_text().replace("\n", " ")[:80])

    _tab(ctx, page, "Tree")
    ctx.until(page, "() => document.querySelectorAll('#example .react-flow__edge').length > 0")
    flow = page.evaluate(FLOW)
    loaded = page.evaluate(LOADED)
    check(f"decisions Tree (engine flow): React Flow draws 15 nodes and {EDGES} edges", flow == {"nodes": len(ROWS), "edges": EDGES}, flow)
    check("decisions Tree: a React Flow reader downloads no Mermaid code (graph.js and its shared d3 chunks only)",
          "graph.js" in loaded and not any("mermaid" in n or "flowDiagram" in n or "elk" in n for n in loaded), loaded)

    got = _map(ctx, page)
    loaded = page.evaluate(LOADED)
    check(f"decisions Map (engine mermaid): the SVG draws exactly 15 node groups and {EDGES} edge paths",
          got and got["nodes"] == len(ROWS) and got["edges"] == EDGES, got and {k: got[k] for k in ("nodes", "edges")})
    check("decisions Map: Mermaid is fetched on first use, as its own chunks, with dagre (no 1.5 MB ELK chunk)",
          any(n.startswith("graph-mermaid.core-") for n in loaded) and not any("elk" in n for n in loaded), [n for n in loaded if "chunk" not in n])
    wrong = [(rid, text) for rid, text in got["labels"] if TITLE.get(rid) != text]
    check("decisions Map: every node's label is its row's title as written (quotes, colons, apostrophes kept)",
          len(got["labels"]) == len(ROWS) and not wrong, wrong[:2] or f"{len(got['labels'])} labels")
    check("decisions Map: nodes are keyboard reachable buttons named by their title, with a pointer cursor",
          got["focusable"] == len(ROWS) and got["cursor"] == "pointer", {k: got[k] for k in ("focusable", "cursor")})
    status = page.inner_text(f"{V} .dv-status")
    check("decisions Map: the status line counts the same graph as the Tree", f"15 nodes · {EDGES} edges" in status, status)

    page.locator(f"{V} .dv-graph-mermaid g.node[data-row='vibetracks:0011']").click()
    ctx.until(page, "() => !document.querySelector('#example .dv-peek').hidden")
    peek = page.evaluate(PEEK)
    check("decisions Map: clicking 0011's node opens its record in the shared peek",
          peek == {"id": "vibetracks:0011", "title": TITLE["vibetracks:0011"]}, peek)
    active = page.evaluate("() => [...document.querySelectorAll('#example .dv-graph-mermaid g.node.dv-active')].map((g) => g.getAttribute('data-row'))")
    check("decisions Map: the open record's node is marked", active == ["vibetracks:0011"], active)
    page.keyboard.press("Escape")
    ctx.until(page, "() => document.querySelector('#example .dv-peek').hidden")
    page.locator(f"{V} .dv-graph-mermaid g.node[data-row='vibetracks:0007']").focus()
    page.keyboard.press("Enter")
    ctx.until(page, "() => !document.querySelector('#example .dv-peek').hidden")
    peek = page.evaluate(PEEK)
    check("decisions Map: focusing 0007's node and pressing Enter opens its peek", peek == {"id": "vibetracks:0007", "title": TITLE["vibetracks:0007"]}, peek)
    page.keyboard.press("Escape")
    ctx.until(page, "() => document.querySelector('#example .dv-peek').hidden")
    _frame(page)
    ctx.shot(page, "vibetracks-decisions-map-peek-before")
    page.locator(f"{V} .dv-graph-mermaid g.node[data-row='vibetracks:0011']").click()
    ctx.until(page, "() => !document.querySelector('#example .dv-peek').hidden")
    ctx.frames(page)
    ctx.shot(page, "vibetracks-decisions-map-peek")
    page.keyboard.press("Escape")

    # the last update wins: Map then Tree at once (Mermaid's async render must not land over the newer flow drawing),
    # and switching away from Map leaves no Mermaid element in the view or in document.body
    page.click(f"{V} .dv-tab[data-name='Newest first']")
    ctx.until(page, "() => !document.querySelector('#example .dv-view-graph')")
    page.click(f"{V} .dv-tab[data-name='Map']")
    page.click(f"{V} .dv-tab[data-name='Tree']")
    ctx.until(page, "() => document.querySelectorAll('#example .react-flow__edge').length > 0")
    page.wait_for_timeout(800)
    after = page.evaluate("() => ({ flow: document.querySelectorAll('#example .react-flow__node-dvrow').length, mermaid: document.querySelectorAll('#example .dv-graph-mermaid').length, view: document.querySelector('#example .dv-tab[aria-selected=true]').dataset.name })")
    check("decisions: Map then Tree at once draws the Tree only (an older Mermaid render never lands)",
          after == {"flow": len(ROWS), "mermaid": 0, "view": "Tree"} and page.evaluate(LEFTOVER) == [], {**after, "left in body": page.evaluate(LEFTOVER)})

    # truthful labels end to end: titles full of Mermaid, markdown and HTML syntax render as text, nothing executes
    weird = ['say "hi" [b] (c) {d}', "<script>window.__dvPwned = 1</script>", "C# #35; a;b", "`code` and **bold** <b>x</b>", "a --> b | end", "two\nlines"]
    page.evaluate("""(titles) => {
      const el = document.querySelector('#example');
      el.data = { id: 'weird', titleProperty: 'title', properties: { title: { type: 'text' }, depends_on: { type: 'list' } },
        rows: titles.map((t, i) => ({ id: 'w' + i, title: t, depends_on: i ? ['w' + (i - 1), 'not-a-row'] : [] })) };
    }""", weird)
    _map(ctx, page)
    ctx.until(page, "() => document.querySelectorAll('#example .dv-graph-mermaid g.node').length === 6")
    got = page.evaluate(MERMAID)
    labels = [text for _, text in sorted(got["labels"], key=lambda x: int(x[0][1:]))]
    status = page.inner_text(f"{V} .dv-status")
    check("decisions Map: titles holding \" [ ] ( ) { } <script> # ; ` and a newline render literally; nothing runs",
          labels == [t.replace("\n", "") for t in weird] and got["edges"] == 5 and not page.evaluate("() => window.__dvPwned || document.querySelector('#example svg script')")
          and "5 edges to rows not shown" in status, {"labels": labels, "edges": got["edges"], "status": status})
    page.context.close()

    fills = {}
    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            name = f"{'dark' if dark else 'light'}, {width} px"
            page = _open(ctx, path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            got = _map(ctx, page)
            fills[(dark, width)] = got["fill"]
            check(f"decisions Map, {name}: 15 nodes, {EDGES} edges; the graph scrolls inside the view, never the page",
                  got["nodes"] == len(ROWS) and got["edges"] == EDGES and got["sw"] <= width and got["box"]["overflow"] == "auto",
                  {k: got[k] for k in ("nodes", "edges", "sw", "svgWidth", "box")})
            _frame(page)
            if width == 1280:
                ctx.shot(page, f"vibetracks-decisions-map-{'dark' if dark else 'light'}-{width}")
            _tab(ctx, page, "Tree")
            ctx.until(page, "() => document.querySelectorAll('#example .react-flow__edge').length > 0")
            flow = page.evaluate(FLOW)
            sw = page.evaluate("document.scrollingElement.scrollWidth")
            check(f"decisions Tree, {name}: 15 nodes, {EDGES} edges, no sideways page scroll", flow == {"nodes": len(ROWS), "edges": EDGES} and sw <= width, {**flow, "sw": sw})
            if width == 1280:
                _frame(page)
                ctx.shot(page, f"vibetracks-decisions-tree-{'dark' if dark else 'light'}-{width}")
            page.context.close()
    check("decisions Map: a node's fill follows the theme (dark differs from light), from the host's tokens",
          fills[(False, 1280)] != fills[(True, 1280)] and fills[(False, 1280)] == fills[(False, 390)] and fills[(True, 1280)] == fills[(True, 390)], fills and {f"{'dark' if d else 'light'} {w}": f for (d, w), f in fills.items()})
