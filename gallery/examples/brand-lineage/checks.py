"""Browser checks for the lineage view (run by tests/browser/checks.py), on Brandbook's real proposals. Every claim is
measured in the page (getBoundingClientRect, and a path's own points through getScreenCTM) against an oracle computed
here, in Python, from proposals.json: never from the view's code.

  edges      the drawn edges (tree + dashed splices) are exactly the data's parent pairs among the shown rows
  geometry   every edge starts on its parent's mark and ends on its child's
  trunk      the bold trunk is the focus row and every ancestor (over all parents), drawn wider than a branch
  extinct    collapse shows exactly the alive rows, and the "+N" groups add up to the rows folded away
  layouts    rectangular: one column per x value, left to right; radial: one ring per x value, outward
  peek       a click on a mark opens its record; "Focus selection" moves the trunk; a "+N" lists its rows
  filters    the rail's brand filter and the search box thin the nodes to the matching rows
  panel      the path panel's edge drags (measured), is remembered across a reload, double-click resets, it folds
  pan/zoom   the wheel zooms about the pointer and a drag pans, measured on a mark
  theme      light and dark, 1280 and 390 px, never a sideways page scroll

`lineage_oracle` and `measure` are imported by the model-lineage case's checks too."""

import json
import pathlib

V = "#example"
HERE = pathlib.Path(__file__).resolve().parent


def lineage_oracle(rows, parents="parents", kept=None, focus=None):
    """From the rows alone: the edges the data declares, the trunk and which rows are alive."""
    ids = {r["id"] for r in rows}
    ps = {r["id"]: [p for p in (r.get(parents) or []) if p in ids and p != r["id"]] for r in rows}
    edges = {(p, c) for c, lst in ps.items() for p in lst}
    tree = {(lst[0], c) for c, lst in ps.items() if lst}
    splices = edges - tree
    kids = {}
    for p, c in edges:
        kids.setdefault(p, []).append(c)
    trunk = set()
    if focus in ids:
        trunk, todo = {focus}, [focus]
        while todo:
            for p in ps[todo.pop()]:
                if p not in trunk:
                    trunk.add(p)
                    todo.append(p)
    keep = {r["id"] for r in rows if kept and any(r.get(k) in v for k, v in kept.items())}
    alive, memo = set(), {}

    def live(i, seen=()):
        if i in memo:
            return memo[i]
        if i in seen:
            return False
        memo[i] = i in keep or i in trunk or any(live(c, seen + (i,)) for c in kids.get(i, []))
        return memo[i]

    for r in rows:
        if not kept or live(r["id"]):
            alive.add(r["id"])
    return {"ids": ids, "parents": ps, "edges": edges, "tree": tree, "splices": splices, "trunk": trunk, "alive": alive}


def _tree_only(rows, focus):
    """The focus and its tree-parent chain only (the first listed parent): what a wrong trunk would draw."""
    first = {r["id"]: (r.get("parents") or [None])[0] for r in rows}
    out, cur = set(), focus
    while cur and cur not in out:
        out.add(cur)
        cur = first.get(cur)
    return out


MEASURE = """() => {
  const root = document.querySelector('#example .dv-lineage');
  if (!root) return null;
  const svg = root.querySelector('svg.dv-lineage-svg');
  const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height }; };
  const nodes = [...root.querySelectorAll('g.dv-lineage-node')].map((g) => ({ id: g.dataset.id, group: g.classList.contains('dv-group'),
    golden: g.classList.contains('dv-golden'), extinct: g.classList.contains('dv-extinct'), focus: g.classList.contains('dv-focus'),
    count: Number(g.dataset.count || 0), col: g.dataset.x, image: !!g.querySelector('image'), label: (g.querySelector('.dv-lineage-label') || {}).textContent || '',
    ...box(g.querySelector('.dv-lineage-dot')) }));
  const pt = (path, at) => { const p = path.getPointAtLength(at); const m = path.getScreenCTM(); return { x: m.a * p.x + m.c * p.y + m.e, y: m.b * p.x + m.d * p.y + m.f }; };
  const edges = [...root.querySelectorAll('path.dv-lineage-edge, path.dv-lineage-splice')].map((p) => {
    const cs = getComputedStyle(p); const len = p.getTotalLength();
    return { from: p.dataset.from, to: p.dataset.to, splice: p.classList.contains('dv-lineage-splice'), golden: p.classList.contains('dv-golden'),
      extinct: p.classList.contains('dv-extinct'), dash: cs.strokeDasharray, width: parseFloat(cs.strokeWidth) * (p.getScreenCTM().a || 1),
      s: pt(p, 0), e: pt(p, len) };
  });
  const r = svg.getBoundingClientRect();
  return { nodes, edges, svg: { left: r.left, top: r.top, width: r.width, height: r.height },
    layout: root.dataset.layout, extinct: root.dataset.extinct, status: (document.querySelector('#example .dv-status') || {}).textContent || '' };
}"""


def measure(page):
    return page.evaluate(MEASURE)


def open_view(ctx, path, name=None, width=1440, height=900, dark=False, mobile=False, query=""):
    page = ctx.page(path + query, width=width, height=height, dark=dark, mobile=mobile)
    if name:
        ctx.drawn(page, lambda: page.click(f"{V} .dv-tab[data-name='{name}']"))
    page.wait_for_selector(f"{V} .dv-lineage g.dv-lineage-node", timeout=20000)
    page.locator(V).evaluate("el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 8)")
    ctx.frames(page)
    return page


def set_extinct(ctx, page, show):
    btn = page.locator(f"{V} .dv-lineage-bar [data-act=extinct]")
    if (btn.get_attribute("aria-pressed") == "true") != show:
        ctx.drawn(page, lambda: btn.click())


def set_layout(ctx, page, layout):
    btn = page.locator(f"{V} .dv-lineage-bar [data-act=layout][data-layout={layout}]")
    if btn.get_attribute("aria-pressed") != "true":
        ctx.drawn(page, lambda: btn.click())


def edge_checks(check, label, m, o):
    """Edges equal the data's pairs; each starts on its parent's mark and ends on its child's; splices dashed."""
    drawn = {(e["from"], e["to"]) for e in m["edges"] if not e["to"].startswith("+")}
    shown = {n["id"] for n in m["nodes"] if not n["group"]}
    want = {(p, c) for p, c in o["edges"] if p in shown and c in shown}
    check(f"{label}: the drawn edges are exactly the data's parent pairs among the shown rows (no inferred edge, none missing)",
          drawn == want and len(drawn) == len([e for e in m["edges"] if not e["to"].startswith("+")]),
          f"{len(drawn)} drawn, {len(want)} in the data; extra {sorted(drawn - want)[:3]}, missing {sorted(want - drawn)[:3]}")
    at = {n["id"]: n for n in m["nodes"]}
    off = []
    for e in m["edges"]:
        a, b = at.get(e["from"]), at.get(e["to"])
        if not a or not b:
            off.append((e["from"], e["to"], "no node"))
            continue
        ds = max(abs(e["s"]["x"] - a["x"]), abs(e["s"]["y"] - a["y"]))
        de = max(abs(e["e"]["x"] - b["x"]), abs(e["e"]["y"] - b["y"]))
        if ds > 1.5 or de > 1.5:
            off.append((e["from"], e["to"], round(ds, 1), round(de, 1)))
    check(f"{label}: every edge starts on its parent's mark and ends on its child's (path ends vs mark centres, ≤ 1.5 px)", not off and m["edges"], off[:3])
    marks = [n for n in m["nodes"]]
    clash = [(a["id"], b["id"]) for i, a in enumerate(marks) for b in marks[i + 1:]
             if abs(a["x"] - b["x"]) < min(a["w"], b["w"]) * 0.9 and abs(a["y"] - b["y"]) < min(a["h"], b["h"]) * 0.9]
    check(f"{label}: no two marks sit on one spot (measured mark boxes)", not clash, clash[:3])
    # WHY with the overlap check: a mark sized to its neighbour gap would shrink to nothing on a collision and hide it
    sizes = sorted(max(n["w"], n["h"]) for n in marks)
    check(f"{label}: every mark stays visible (the smallest at least a fifth of the largest)", sizes and sizes[0] >= sizes[-1] / 5,
          f"smallest {sizes[0]:.2f} px, largest {sizes[-1]:.2f} px" if sizes else None)
    sp = [e for e in m["edges"] if e["splice"]]
    want_sp = {(p, c) for p, c in o["splices"] if p in shown and c in shown}
    check(f"{label}: a splice's extra parents are the dashed links, exactly; tree edges are solid",
          {(e["from"], e["to"]) for e in sp} == want_sp and all(e["dash"] not in ("none", "") for e in sp)
          and all(e["dash"] in ("none", "") for e in m["edges"] if not e["splice"]),
          f"{len(sp)} dashed ({sp[0]['dash'] if sp else '-'}), {len(want_sp)} splice pairs in the data")


def trunk_checks(check, label, m, o):
    golden = {n["id"] for n in m["nodes"] if n["golden"]}
    focus = [n["id"] for n in m["nodes"] if n["focus"]]
    widths = [e["width"] for e in m["edges"] if e["golden"] and not e["splice"]]
    branch = [e["width"] for e in m["edges"] if not e["golden"] and not e["extinct"] and not e["splice"]]
    ext = [e["width"] for e in m["edges"] if e["extinct"] and not e["splice"]]  # WHY: a trunk may leave no living branch (every alive line on it)
    gedges = {(e["from"], e["to"]) for e in m["edges"] if e["golden"]}
    want_g = {(p, c) for p, c in o["edges"] if p in o["trunk"] and c in o["trunk"]}
    check(f"{label}: the trunk is the focus row and its every ancestor, over all parents; its edges are the edges among them, drawn ≥ 2x a branch's width",
          golden == o["trunk"] and len(focus) == 1 and gedges == want_g and widths and (not branch or min(widths) >= 2 * max(branch))
          and (not ext or min(widths) >= 2 * max(ext)) and (branch or ext),
          f"{len(golden)} golden marks ({len(o['trunk'])} in the oracle), focus {focus}, {len(gedges)} trunk edges, widths {min(widths) if widths else '-'} vs branch {max(branch) if branch else '-'} / extinct {max(ext) if ext else '-'} px")


def run(ctx, path):
    check = ctx.check
    data = json.loads((HERE / "proposals.json").read_text(encoding="utf-8"))
    rows = data["rows"]
    rp = [r for r in rows if r["brand"] == "robotparts"]
    kept = {"status": ["picked", "liked"]}
    o = lineage_oracle(rp, kept=kept, focus="robotparts/r16-02")

    # ---- the robotparts tab: collapse first (the .base default), then every row
    page = open_view(ctx, path)
    rail_err = page.evaluate("[...document.querySelectorAll('data-facets .df-warn, data-facets .dv-err')].map((e) => e.textContent)")
    check("lineage rail: the case's facets draw with no error (brand, status, round_kind, score, name)", not rail_err and page.locator("data-facets").count() == 1, rail_err)
    m = measure(page)
    groups = [n for n in m["nodes"] if n["group"]]
    rows_shown = {n["id"] for n in m["nodes"] if not n["group"]}
    folded = sum(n["count"] for n in groups)
    check("lineage collapse: exactly the alive rows show (kept, on the trunk, or with an alive descendant); the '+N' groups add up to the rows folded away",
          m["extinct"] == "collapse" and rows_shown == o["alive"] and folded == len(rp) - len(o["alive"]) and all(n["count"] > 0 for n in groups),
          f"{len(rp)} rows -> {len(rows_shown)} marks + {len(groups)} groups standing for {folded} (oracle: {len(o['alive'])} alive, {len(rp) - len(o['alive'])} extinct)")
    check("lineage collapse: each '+N' reads its count", all(n["label"].strip() == f"+{n['count']}" for n in groups), [n["label"] for n in groups][:6])
    edge_checks(check, "lineage collapse", m, o)
    trunk_checks(check, "lineage collapse", m, o)
    collapsed_nodes = len(m["nodes"])

    set_extinct(ctx, page, True)
    m = measure(page)
    check("lineage show extinct: every one of robotparts' rows is a mark, no groups; the toggle says so",
          m["extinct"] == "show" and {n["id"] for n in m["nodes"]} == o["ids"] and page.get_attribute(f"{V} .dv-lineage-bar [data-act=extinct]", "aria-pressed") == "true",
          f"{collapsed_nodes} -> {len(m['nodes'])} marks ({len(rp)} rows)")
    edge_checks(check, "lineage show extinct", m, o)
    trunk_checks(check, "lineage show extinct", m, o)
    ext_w = [e["width"] for e in m["edges"] if e["extinct"]]
    br_w = [e["width"] for e in m["edges"] if not e["extinct"] and not e["golden"] and not e["splice"]]
    ext_n = [n for n in m["nodes"] if n["extinct"]]
    check("lineage show extinct: an extinct line is a thin stub (narrower than a living branch) and its marks are the extinct rows",
          ext_w and br_w and max(ext_w) < min(br_w) and {n["id"] for n in ext_n} == o["ids"] - o["alive"],
          f"extinct {max(ext_w) if ext_w else '-'} px < branch {min(br_w) if br_w else '-'} px; {len(ext_n)} extinct marks")
    # rectangular: one column per x value, left to right
    measured = {}
    for n in m["nodes"]:
        measured.setdefault(float(n["col"]), []).append(n["x"])
    order = sorted(measured)
    mids = [sum(measured[k]) / len(measured[k]) for k in order]
    width = max(max(v) - min(v) for v in measured.values())
    check("lineage rectangular: one column per round (every mark of a round on one x, ≤ 1 px), the rounds left to right, evenly spaced",
          m["layout"] == "rectangular" and width <= 1 and all(b > a for a, b in zip(mids, mids[1:])) and len(order) == len({r["round_n"] for r in rp})
          and max(b - a for a, b in zip(mids, mids[1:])) - min(b - a for a, b in zip(mids, mids[1:])) <= 1,
          f"{len(order)} columns, widest spread {width:.2f} px, centres {[round(x) for x in mids[:5]]}…")

    # ---- radial
    set_layout(ctx, page, "radial")
    m = measure(page)
    root = page.evaluate("() => { const r = document.querySelector('#example g.dv-lineage-root .dv-lineage-dot').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }")
    rings = {}
    for n in m["nodes"]:
        rings.setdefault(float(n["col"]), []).append(((n["x"] - root["x"]) ** 2 + (n["y"] - root["y"]) ** 2) ** 0.5)
    radii = [sum(v) / len(v) for k, v in sorted(rings.items())]
    ring_spread = max(max(v) - min(v) for v in rings.values())
    check("lineage radial: one ring per round around the root (every mark of a round at one radius, ≤ 1 px), the rounds outward",
          m["layout"] == "radial" and ring_spread <= 1 and all(b > a + 5 for a, b in zip(radii, radii[1:])),
          f"{len(radii)} rings, widest spread {ring_spread:.2f} px, radii {[round(r) for r in radii[:4]]}…")
    edge_checks(check, "lineage radial", m, o)
    trunk_checks(check, "lineage radial", m, o)
    set_layout(ctx, page, "rectangular")

    # ---- pan and zoom (measured on the focus mark)
    def focus_box():
        return page.evaluate("() => { const r = document.querySelector('#example g.dv-lineage-node.dv-focus .dv-lineage-dot').getBoundingClientRect(); return [r.left, r.top, r.width]; }")
    page.click(f"{V} .dv-lineage-bar [data-act=fit]")
    ctx.frames(page, 4)
    a = focus_box()
    page.mouse.move(a[0] + a[2] / 2, a[1] + a[2] / 2)
    page.mouse.wheel(0, -600)
    page.wait_for_timeout(300)
    b = focus_box()
    page.mouse.move(b[0] - 60, b[1] + 200)
    page.mouse.down()
    page.mouse.move(b[0] + 40, b[1] + 160, steps=6)
    page.mouse.up()
    ctx.frames(page, 3)
    c = focus_box()
    check("lineage pan and zoom: the wheel zooms in about the pointer (the mark grows, stays under it); a drag pans by the drag",
          b[2] > a[2] * 1.3 and abs((b[0] + b[2] / 2) - (a[0] + a[2] / 2)) < 3 and abs((c[0] - b[0]) - 100) <= 2 and abs((c[1] - b[1]) + 40) <= 2,
          f"size {a[2]:.1f} -> {b[2]:.1f} px; drag moved it ({c[0] - b[0]:.1f}, {c[1] - b[1]:.1f}) for (100, -40)")
    page.click(f"{V} .dv-lineage-bar [data-act=fit]")
    ctx.frames(page, 4)

    # ---- click a mark: the peek opens on it; Focus selection moves the trunk
    # WHY r4-15: a splice (R2-10 and R1-02) whose second parent is off its tree parent's chain, so its trunk is wrong
    # unless the ancestry follows every parent
    target = "robotparts/r4-15"
    check("lineage focus target: r4-15's ancestry over all parents is larger than over tree parents alone (so the next check can tell them apart)",
          len(lineage_oracle(rp, focus=target)["trunk"]) > len(_tree_only(rp, target)), sorted(lineage_oracle(rp, focus=target)["trunk"]))
    page.locator(f"{V} g.dv-lineage-node[data-id='{target}']").scroll_into_view_if_needed()
    page.evaluate("(id) => document.querySelector(`#example g.dv-lineage-node[data-id=\"${id}\"]`).dispatchEvent(new MouseEvent('click', {bubbles: true}))", target)
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])", timeout=5000)
    ctx.frames(page, 2)
    row = next(r for r in rp if r["id"] == target)
    # CONTRACT §44: report_path is not in this view's order, so it waits behind "N more properties"
    page.click(f"{V} .dv-peek [data-prop-more]")
    peek = page.inner_text(f"{V} .dv-peek")
    rel = page.locator(f"{V} .dv-peek .dv-open-rel").count()
    check("lineage click: a mark opens its record in the peek: its name, its round, its report's path as plain text (not a link), its parents as record links",
          row["name"] in peek and row["round"] in peek and (row["report_path"] in peek if isinstance(row["report_path"], str) else True)
          and page.locator(f"{V} .dv-peek a[href^='file:']").count() == 0 and rel >= len(row["parents"]),
          f"{target}: '{row['name']}', {rel} relation links, report {'shown' if isinstance(row['report_path'], str) and row['report_path'] in peek else 'missing'}")
    sel = page.evaluate("(id) => document.querySelector(`#example g.dv-lineage-node[data-id=\"${id}\"]`).classList.contains('dv-selected')", target)
    check("lineage click: the peeked mark is marked selected", sel, sel)
    ctx.drawn(page, lambda: page.click(f"{V} .dv-lineage-bar [data-act=focus]"))
    m = measure(page)
    o2 = lineage_oracle(rp, kept=kept, focus=target)
    golden = {n["id"] for n in m["nodes"] if n["golden"]}
    # the changed view rides in the hash as v=<base64url JSON> (grammar.js encodeView)
    hashed = page.evaluate("""() => { const v = new URLSearchParams(location.hash.slice(1)).get('v'); if (!v) return null;
      const b = v.replace(/-/g, '+').replace(/_/g, '/'); return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(b + '==='.slice((b.length + 3) % 4)), (c) => c.charCodeAt(0)))); }""")
    in_hash = bool(hashed) and (hashed.get("lineage") or {}).get("focus") == target
    check("lineage focus from a selection: 'Focus selection' writes focus: <id> to the view (the URL's v= carries it) and the trunk becomes that row's ancestry",
          golden == o2["trunk"] and [n["id"] for n in m["nodes"] if n["focus"]] == [target] and in_hash,
          f"{len(golden)} golden ({len(o2['trunk'])} in the oracle); v= says focus {(hashed or {}).get('lineage', {}).get('focus') if hashed else None}")
    page.keyboard.press("Escape")
    page.context.close()

    # ---- the "+N" group lists its rows
    page = open_view(ctx, path)
    grp = page.evaluate("() => { const g = document.querySelector('#example g.dv-lineage-node.dv-group'); return g && {id: g.dataset.id, n: Number(g.dataset.count)}; }")
    page.evaluate("(id) => document.querySelector(`#example g.dv-lineage-node[data-id=\"${id}\"]`).dispatchEvent(new MouseEvent('click', {bubbles: true}))", grp["id"])
    page.wait_for_selector(f"{V} .dv-peek:not([hidden]) .dv-peektable", timeout=5000)
    n_rows = page.locator(f"{V} .dv-peek .dv-peektable tbody tr").count()
    check("lineage '+N': a click lists the N folded rows in the peek", n_rows == grp["n"], f"{grp['id']}: {n_rows} rows listed for +{grp['n']}")
    page.context.close()

    # ---- filters: the rail and the search box thin the tree like any view
    page = open_view(ctx, path, "Every brand")
    m0 = measure(page)
    ctx.drawn(page, lambda: page.check("data-facets input[data-p=brand][data-value=BAM]"))
    m1 = measure(page)
    bam = [r for r in rows if r["brand"] == "BAM"]
    ob = lineage_oracle(bam)
    edge_checks(check, "lineage filtered to BAM", m1, ob)
    check("lineage filters: the rail's brand = BAM leaves exactly BAM's 53 marks (every brand's 319 before)",
          len(m0["nodes"]) == len(rows) and {n["id"] for n in m1["nodes"]} == {r["id"] for r in bam} and "53 of 319" in m1["status"],
          f"{len(m0['nodes'])} -> {len(m1['nodes'])} marks; {m1['status'][:40]}")
    ctx.drawn(page, lambda: page.click("data-facets [data-clear]"))
    page.fill(f"{V} .dv-search", "stud")
    ctx.until(page, "() => document.querySelectorAll('#example g.dv-lineage-node').length < 319")
    ctx.frames(page, 3)
    m2 = measure(page)
    n_status = int(m2["status"].split(" of ")[0].replace(",", "")) if " of " in m2["status"] else -1
    check("lineage filters: the search box thins the marks to the rows it matches (as many marks as the status line's rows)",
          0 < len(m2["nodes"]) == n_status < len(rows), f"'stud': {len(m2['nodes'])} marks, status '{m2['status'][:30]}'")
    page.context.close()

    # ---- the path panel: drag (measured), remembered, reset, fold
    page = open_view(ctx, path, width=1440)
    box = """() => { const b = (s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { left: r.left, right: r.right, width: r.width, hidden: !r.width }; };
      return { panel: b('#example .dv-lineage-panel'), handle: b('#example .dv-lineage .dv-splitter-left'), stage: b('#example .dv-lineage-stage'),
        steps: document.querySelectorAll('#example .dv-lineage-panel .dv-lineage-step').length,
        stored: Object.keys(localStorage).filter((k) => k.includes('lineage')) }; }"""
    a = page.evaluate(box)
    check("lineage panel: the path panel lists the focus's ancestry, oldest first, and has a drag handle on its left edge",
          a["panel"] and a["handle"] and not a["handle"]["hidden"] and abs(a["handle"]["left"] + a["handle"]["width"] / 2 - a["panel"]["left"]) <= 1.5 and a["steps"] == len(o["trunk"]),
          f"panel {a['panel'] and round(a['panel']['width'])} px, {a['steps']} steps ({len(o['trunk'])} in the trunk)")
    h = a["handle"]
    y = page.evaluate("() => { const r = document.querySelector('#example .dv-lineage .dv-splitter-left').getBoundingClientRect(); return r.top + r.height / 2; }")
    page.mouse.move(h["left"] + h["width"] / 2, y)
    page.mouse.down()
    page.mouse.move(h["left"] + h["width"] / 2 - 120, y, steps=8)
    page.mouse.up()
    ctx.frames(page, 3)
    b = page.evaluate(box)
    check("lineage panel: dragging its edge 120 px left widens the panel by 120 px and the tree's stage shrinks by 120 px",
          abs(b["panel"]["width"] - a["panel"]["width"] - 120) <= 2 and abs(a["stage"]["width"] - b["stage"]["width"] - 120) <= 2,
          f"panel {a['panel']['width']:.0f} -> {b['panel']['width']:.0f}; stage {a['stage']['width']:.0f} -> {b['stage']['width']:.0f}")
    want = b["panel"]["width"]
    page.reload()
    page.wait_for_selector(f"{V} .dv-lineage g.dv-lineage-node", timeout=20000)
    ctx.frames(page, 3)
    c = page.evaluate(box)
    check("lineage panel: the width is remembered across a reload", abs(c["panel"]["width"] - want) <= 1 and c["stored"], f"{c['panel']['width']:.0f} px, keys {c['stored']}")
    page.locator(f"{V} .dv-lineage .dv-splitter-left").dblclick()
    ctx.frames(page, 3)
    d = page.evaluate(box)
    check("lineage panel: a double-click resets it to its default width", abs(d["panel"]["width"] - a["panel"]["width"]) <= 1, f"{d['panel']['width']:.0f} px")
    page.click(f"{V} .dv-lineage-panel [data-act=fold]")
    ctx.frames(page, 3)
    e = page.evaluate(box)
    check("lineage panel: it folds to a strip (the handle goes) and the stage takes the room; unfolding brings it back",
          e["panel"]["width"] < 48 and (e["handle"] is None or e["handle"]["hidden"]) and e["stage"]["width"] > d["stage"]["width"] + d["panel"]["width"] - 50,
          f"folded {e['panel']['width']:.0f} px, stage {d['stage']['width']:.0f} -> {e['stage']['width']:.0f}")
    page.click(f"{V} .dv-lineage-panel [data-act=fold]")
    ctx.frames(page, 3)
    f = page.evaluate(box)
    check("lineage panel: unfolded again at its width", abs(f["panel"]["width"] - d["panel"]["width"]) <= 1, f"{f['panel']['width']:.0f} px")
    page.context.close()

    # ---- light and dark, 1280 and 390
    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            p = open_view(ctx, path, width=width, height=900 if not mobile else 844, dark=dark, mobile=mobile)
            got = p.evaluate("""() => { const root = document.querySelector('#example .dv-lineage');
              const trunk = document.querySelector('#example path.dv-lineage-edge.dv-golden');
              const well = document.querySelector('#example .dv-lineage-well');
              const r = root.getBoundingClientRect();
              return { sw: document.scrollingElement.scrollWidth, bg: getComputedStyle(root).backgroundColor, fg: getComputedStyle(root).color,
                trunk: trunk && getComputedStyle(trunk).stroke, well: well && getComputedStyle(well).fill, w: r.width, h: r.height,
                marks: [...document.querySelectorAll('#example g.dv-lineage-node .dv-lineage-dot')].filter((d) => { const b = d.getBoundingClientRect(); return b.right > r.left && b.left < r.right && b.bottom > r.top && b.top < r.bottom; }).length }; }""")
            lum = lambda rgb: sum(int(x) for x in rgb[rgb.index("(") + 1:rgb.index(")")].split(",")[:3]) / 3
            ok = got["sw"] <= width and got["w"] <= width and got["h"] > 200 and got["marks"] > 5 and (lum(got["bg"]) < 80) == dark and (lum(got["fg"]) > 160) == dark \
                and got["well"] == "rgb(255, 255, 255)" and got["trunk"] not in (None, got["fg"])
            check(f"lineage, {'dark' if dark else 'light'}, {width} px: the tree draws in the theme (background, text, a trunk in the accent), paper-white wells, no sideways page scroll",
                  ok, {k: got[k] for k in ("sw", "bg", "trunk", "well", "marks")})
            ctx.shot(p, f"brand-lineage-{'dark' if dark else 'light'}-{width}")
            p.context.close()
