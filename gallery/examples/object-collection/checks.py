"""Browser checks for this case (run by tests/browser/checks.py): the grouped gallery (docs/CONTRACT.md §20). Every
heading, tile and rail row is found by scrolling the virtualised grid end to end and measured with
getBoundingClientRect; every label and count is compared with an oracle computed here, in Python, from objects.json
(Python's own loops, and for the size grouping its own bins), never with the kit's grouping."""

import collections
import json
import pathlib

V = "#example"
HERE = pathlib.Path(__file__).parent
DATA = json.loads((HERE / "objects.json").read_text(encoding="utf-8"))
ROWS, PROPS = DATA["rows"], DATA["properties"]
EDGES = [250, 1000, 5000]  # the case's size bins (views.base), sized for its 366-object public sample
NAMES = {"family": "Material", "geometry_class": "Shape", "type_name": "Type", "source": "Source", "bbox_volume_ml": "Size"}


def word(prop, value):
    return (PROPS[prop].get("labels") or {}).get(value, value)


def litres(v):
    return f"{v / 1000:g} L" if v >= 1000 else f"{v:g} mL"


SIZE_LABELS = [f"< {litres(EDGES[0])}"] + [f"{litres(a)} – {litres(b)}" for a, b in zip(EDGES, EDGES[1:])] + [f"≥ {litres(EDGES[-1])}"]


def key_of(grouping, r):
    """The H1 label a row belongs under, by the oracle's own rules."""
    if grouping == "material":
        return word("family", r["family"]) if r["family"] else "No material"
    if grouping == "size":
        v = r["bbox_volume_ml"]
        if not isinstance(v, (int, float)):
            return "No size"
        return SIZE_LABELS[sum(1 for e in EDGES if v >= e)]
    if grouping == "shape":
        return word("geometry_class", r["geometry_class"]) if r["geometry_class"] else "No shape"
    if grouping == "type":
        return r["type_name"] or "No type"
    if grouping == "source":
        return word("source", r["source"]) if r["source"] else "No source"
    raise ValueError(grouping)


def oracle(grouping, rows=ROWS):
    return dict(collections.Counter(key_of(grouping, r) for r in rows))


def areas():
    """{family label: {area: count}} for the rows that have an area (the H2s)."""
    out = collections.defaultdict(collections.Counter)
    for r in ROWS:
        out[word("family", r["family"])]
        if r["area"]:
            out[word("family", r["family"])][r["area"]] += 1
    return out


COLLECT = """async () => {
  const sc = document.querySelector('#example .dv-cards-scroll');
  const heads = new Map(), items = new Map();
  const frames = () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
  const grab = () => {
    const top0 = sc.getBoundingClientRect().top - sc.scrollTop;
    for (const h of sc.querySelectorAll('[role=heading]')) {
      const b = h.getBoundingClientRect();
      const name = h.querySelector('.dv-cards-gname'), count = h.querySelector('.dv-cards-count');
      heads.set(h.getAttribute('aria-level') + ':' + Math.round(b.top - top0), { level: Number(h.getAttribute('aria-level')), top: b.top - top0, bottom: b.bottom - top0,
        label: name ? name.textContent : h.textContent, count: count ? count.textContent : null });
    }
    for (const t of sc.querySelectorAll('.dv-cards-tile, .dv-cards-card')) {
      const b = t.getBoundingClientRect();
      const label = t.querySelector('.dv-cards-tlabel'), count = t.querySelector('.dv-cards-tcount');
      items.set((t.dataset.i || '') + ':' + Math.round(b.top - top0) + ':' + Math.round(b.left), { kind: t.classList.contains('dv-cards-tile') ? 'tile' : 'card',
        top: b.top - top0, left: b.left, label: label ? label.textContent : t.getAttribute('aria-label'), count: count ? count.textContent : null, id: t.dataset.id || null });
    }
  };
  sc.scrollTop = 0; await frames(); grab();
  for (let k = 0; k < 400 && sc.scrollTop + sc.clientHeight < sc.scrollHeight - 1; k++) { sc.scrollTop += Math.max(100, sc.clientHeight - 40); await frames(); grab(); }
  sc.scrollTop = 0; await frames();
  const byTop = (a, b) => a.top - b.top || a.left - b.left;
  return { heads: [...heads.values()].sort(byTop), items: [...items.values()].sort(byTop) };
}"""

NAV = """() => [...document.querySelectorAll('data-facets .df-nav-row:not(.df-nav-clear)')].map((r) => ({
  label: r.querySelector('.df-label').textContent, count: r.querySelector('.df-count').textContent, current: r.getAttribute('aria-current') }))"""


def number(text):
    return int(str(text).strip("()").replace(",", ""))


def h1s(got):
    return [(h["label"], number(h["count"])) for h in got["heads"] if h["level"] == 2]


def open_page(ctx, path, **kw):
    page = ctx.page(path, **kw)
    page.wait_for_selector(f"{V} .dv-view-cards [role=heading]", timeout=20000)
    ctx.until(page, "() => document.querySelector('data-facets .df-nav-row')")
    return page


def switch(ctx, page, grouping):
    ctx.drawn(page, lambda: page.click(f"{V} .dv-cards-switch [data-grouping='{grouping}']"))
    ctx.until(page, "(g) => [...document.querySelectorAll('data-facets .df-nav-row')].length && document.querySelector('data-facets .df-as-nav').dataset.p === g", {"material": "family", "size": "bbox_volume_ml", "shape": "geometry_class", "type": "type_name", "source": "source"}[grouping])
    ctx.frames(page, 4)


def nav_click(ctx, page, label):
    """Click a rail row and wait until the view has drawn and the rail has repainted that row (its aria-current flips)."""
    find = "(l) => [...document.querySelectorAll('data-facets .df-nav-row')].find((x) => x.querySelector('.df-label').textContent === l)"
    before = page.evaluate(f"(l) => {{ const r = ({find})(l); return r ? r.getAttribute('aria-current') : 'missing'; }}", label)
    ctx.drawn(page, lambda: page.evaluate(f"(l) => ({find})(l).click()", label))
    ctx.until(page, f"([l, b]) => {{ const r = ({find})(l); return r && r.getAttribute('aria-current') !== b; }}", [label, before])
    ctx.frames(page, 4)


def run(ctx, path):
    """Each part opens its own pages; a part that throws (a missing element before the feature exists) is one FAIL with
    its error, and the parts after it still run."""
    pages = []

    def opened(p, *a, **kw):
        page = open_page(ctx, p, *a, **kw)
        pages.append(page)
        return page

    parts = (("H1 and H2 nesting", part_a), ("the nav rail", part_b), ("tile drill and keys", part_e), ("the grouping switcher", part_c), ("themes and the phone", part_d))
    for name, part in parts:
        try:
            part(ctx, path, opened)
        except Exception as error:  # noqa: BLE001 -- reported as a failed check, never hidden
            ctx.check(f"collection: {name} ran to the end", False, f"{type(error).__name__}: {str(error)[:300]}")
        finally:
            for page in pages:
                try:
                    page.context.close()
                except Exception:  # noqa: BLE001 -- already closed
                    pass
            pages.clear()


def part_a(ctx, path, opened):
    """H1 and H2 nesting, measured."""
    check = ctx.check
    page = opened(path, width=1440)
    got = page.evaluate(COLLECT)
    want = oracle("material")
    check("collection: one H1 per material, its label and count equal Python's count over objects.json", dict(h1s(got)) == want and len(h1s(got)) == len(want),
          {"drawn": h1s(got), "oracle": want})
    heads = got["heads"]
    tops = [h["top"] for h in heads if h["level"] == 2] + [float("inf")]
    sections = [h for h in heads if h["level"] == 2]
    nest, bare = [], []
    for i, h1 in enumerate(sections):
        inside = [h for h in heads if h["level"] == 3 and tops[i] < h["top"] < tops[i + 1]]
        tiles = [t for t in got["items"] if t["kind"] == "tile" and h1["bottom"] <= t["top"] < tops[i + 1]]
        expect = areas()[h1["label"]]
        nest.append((h1["label"], sorted((h["label"], number(h["count"])) for h in inside), sorted(expect.items())))
        if not expect:
            bare.append((h1["label"], len(inside), len(tiles)))
        elif inside and any(not r["area"] for r in ROWS if word("family", r["family"]) == h1["label"]):
            # the rows with no area (when the material has any: Glass has none) come first, directly under the H1,
            # before the named H2s
            first_h2 = min(h["top"] for h in inside)
            under = [t for t in tiles if t["top"] < first_h2]
            bare.append((h1["label"] + " (no-area part)", 0, len(under)))
    check("collection: every H2 lies between its H1 and the next H1; Plastics, Glass and Paper split into Medical / Food with the oracle's counts",
          all(a == b for _, a, b in nest) and sum(len(a) for _, a, _ in nest) == 6, nest)
    check("collection: a material with no area (Metals, Textiles, …) draws its tiles directly under its H1, with no H2 between; the no-area rows of a split material come before its H2s",
          bare and all(n == 0 and t > 0 for _, n, t in bare), bare)
    sizes = page.evaluate("""() => { const f = (s) => { const e = document.querySelector(s); if (!e) return [0, 0]; const c = getComputedStyle(e); return [parseFloat(c.fontSize), Number(c.fontWeight)]; };
      return { h1: f('#example [role=heading][aria-level="2"]'), h2: f('#example [role=heading][aria-level="3"]') }; }""")
    check("collection: section titles are catalogue-sized (H1 about 22 px, bold; H2 about 15 px, bold)",
          20 <= sizes["h1"][0] <= 26 and sizes["h1"][1] >= 600 and 14 <= sizes["h2"][0] <= 17 and sizes["h2"][1] >= 600, sizes)
    metals = next(i for i, h in enumerate(sections) if h["label"] == "Metals")
    drawn = [(t["label"], number(t["count"])) for t in got["items"] if t["kind"] == "tile" and sections[metals]["bottom"] <= t["top"] < tops[metals + 1]]
    types = collections.Counter(r["type_name"] for r in ROWS if r["family"] == "metal")
    ranked = sorted(types.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    middle = drawn[1:-1] if len(types) > 12 else drawn[1:]
    check("collection: Metals' tiles are 'All Metals (173)', then a tile per type with its count, most first, at most 12, then 'Every Type (N)'",
          drawn[0] == ("All Metals", sum(types.values())) and [n for _, n in middle] == [n for _, n in ranked[:12]] and all(types[label] == n for label, n in middle)
          and (len(types) <= 12 or drawn[-1] == ("Every Type", len(types))), {"drawn": drawn, "oracle": ranked[:13]})


def part_b(ctx, path, opened):
    """The rail filters to one group, McMaster's "Choose a Category"."""
    check = ctx.check
    page = opened(path, width=1440)
    want = oracle("material")
    types = collections.Counter(r["type_name"] for r in ROWS if r["family"] == "metal")
    nav = page.evaluate(NAV)
    check("nav: the rail lists every material with its count in brackets, '(100)'", {r["label"]: number(r["count"]) for r in nav} == want and all(r["count"].startswith("(") for r in nav), nav)
    nav_click(ctx, page, "Metals")
    after = page.evaluate(COLLECT)
    nav = page.evaluate(NAV)
    search = page.evaluate("decodeURIComponent(location.search)")
    check("nav: clicking Metals leaves exactly one H1, the row is aria-current, ?family=metal, and every other row keeps its count",
          [h[0] for h in h1s(after)] == ["Metals"] and [r["label"] for r in nav if r["current"] == "true"] == ["Metals"] and "family=metal" in search
          and {r["label"]: number(r["count"]) for r in nav} == want, {"h1": h1s(after), "current": [r["label"] for r in nav if r["current"] == "true"], "search": search})
    tiles = [t for t in after["items"] if t["kind"] == "tile"]
    check("nav: inside the one material every type is a tile (no 'Every' tile once drilled)", len(tiles) == len(types) + 1 and not any(t["label"].startswith("Every") for t in tiles),
          [t["label"] for t in tiles][:4] + ["…"])
    nav_click(ctx, page, "Metals")
    back = page.evaluate(COLLECT)
    search = page.evaluate("decodeURIComponent(location.search)")
    check("nav: clicking it again brings every material back and clears the param", dict(h1s(back)) == want and "family=" not in search, {"h1": len(h1s(back)), "search": search})
    page = opened(f"{path}?family=metal", width=1440)
    again = page.evaluate(COLLECT)
    nav = page.evaluate(NAV)
    check("nav: a link with ?family=metal opens on Metals alone, its row current", [h[0] for h in h1s(again)] == ["Metals"] and [r["label"] for r in nav if r["current"] == "true"] == ["Metals"],
          {"h1": h1s(again), "current": [r["label"] for r in nav if r["current"] == "true"]})


def part_e(ctx, path, opened):
    """A tile drills to its rows; arrows move between tiles."""
    check = ctx.check
    page = opened(f"{path}?family=metal", width=1440)
    again = page.evaluate(COLLECT)
    first = next(t for t in again["items"] if t["kind"] == "tile" and not t["label"].startswith("All"))
    page.evaluate("[...document.querySelectorAll('#example .dv-cards-tile')].find((t) => t.querySelector('.dv-cards-tlabel').textContent === 'All Metals').focus()")
    page.keyboard.press("ArrowRight")
    focused = page.evaluate("(() => { const a = document.activeElement; const l = a && a.querySelector('.dv-cards-tlabel'); return l ? l.textContent : null; })()")
    check("tiles: the arrow keys move focus from tile to tile", focused == first["label"], focused)
    ctx.drawn(page, lambda: page.keyboard.press("Enter"))
    ctx.frames(page, 4)
    rows = page.evaluate(COLLECT)
    cards = [c for c in rows["items"] if c["kind"] == "card"]
    want_rows = sorted(r["id"] for r in ROWS if r["family"] == "metal" and r["type_name"] == first["label"])
    search = page.evaluate("decodeURIComponent(location.search)")
    check(f"tiles: a tile ({first['label']}) drills through the facet seam: ?type_name=… and the page shows exactly those {len(want_rows)} objects as cards",
          sorted(c["id"] for c in cards) == want_rows and f"type_name={first['label']}" in search.replace("+", " ") and "family=metal" in search,
          {"cards": len(cards), "oracle": len(want_rows), "search": search})


def part_c(ctx, path, opened):
    """The grouping switcher: size, shape, type, source; the rail follows; the hash keeps it."""
    check = ctx.check
    page = opened(path, width=1440)
    nav_click(ctx, page, "Metals")
    for grouping in ("size", "shape", "type", "source"):
        switch(ctx, page, grouping)
        got = page.evaluate(COLLECT)
        want = oracle(grouping)
        hash_ = page.evaluate("location.hash")
        nav = page.evaluate(NAV)
        ordered = [h[0] for h in h1s(got)] == [label for label in SIZE_LABELS + ["No size"] if label in want] if grouping == "size" else True
        check(f"switcher: grouping by {grouping} draws one H1 per {'bin' if grouping == 'size' else NAMES[{'shape': 'geometry_class', 'type': 'type_name', 'source': 'source'}[grouping]].lower()} with the oracle's labels and counts{' in ascending order' if grouping == 'size' else ''}; the hash has group={grouping}",
              dict(h1s(got)) == want and len(h1s(got)) == len(want) and ordered and f"group={grouping}" in hash_,
              {"drawn": h1s(got)[:8], "oracle": list(want.items())[:8], "hash": hash_})
        check(f"switcher: the rail follows the {grouping} grouping (its rows are the H1s{', the bins' if grouping == 'size' else ''})",
              {r["label"]: number(r["count"]) for r in nav} == {k: v for k, v in want.items() if not k.startswith("No ")}, [r["label"] for r in nav][:8])
        if grouping == "size":
            search = page.evaluate("decodeURIComponent(location.search)")
            check("switcher: switching the grouping clears the nav pick on the previous grouping's property (McMaster resets)", "family=" not in search and len(h1s(got)) > 1, search)
            nav_click(ctx, page, "250 mL – 1 L")
            one = page.evaluate(COLLECT)
            search = page.evaluate("decodeURIComponent(location.search)")
            check("nav: a bin row writes its range, ?bbox_volume_ml=250..<1000, and leaves that one bin", "bbox_volume_ml=250..<1000" in search and h1s(one) == [("250 mL – 1 L", want["250 mL – 1 L"])],
                  {"search": search, "h1": h1s(one)})
            page.reload()
            page.wait_for_selector(f"{V} .dv-view-cards [role=heading]", timeout=20000)
            ctx.until(page, "() => document.querySelector('data-facets .df-nav-row[aria-current=true]')")
            kept = page.evaluate(COLLECT)
            check("switcher: a reload keeps group=size and the bin's filter", h1s(kept) == [("250 mL – 1 L", want["250 mL – 1 L"])] and "group=size" in page.evaluate("location.hash")
                  and page.evaluate("document.querySelector('#example').view.grouping") == "size", h1s(kept))
            nav_click(ctx, page, "250 mL – 1 L")


def part_d(ctx, path, opened):
    """Light, dark and a 375 px phone: no sideways scroll, nothing clipped, two tiles a row, readable."""
    check = ctx.check
    for dark in (False, True):
        for width, mobile in ((1440, False), (375, True)):
            page = opened(path, width=width, height=900 if not mobile else 812, dark=dark, mobile=mobile)
            m = page.evaluate("""() => {
              const rgb = (c) => { const x = document.createElement('canvas').getContext('2d'); x.fillStyle = '#000'; x.fillStyle = c; x.fillRect(0, 0, 1, 1); return [...x.getImageData(0, 0, 1, 1).data]; };
              const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
              const bg = (e) => { for (; e; e = e.parentElement) { const c = rgb(getComputedStyle(e).backgroundColor); if (c[3] > 0) return c; } return [255, 255, 255, 255]; };
              const ratio = (e) => { const a = lum(rgb(getComputedStyle(e).color)), b = lum(bg(e)); return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); };
              const h1 = [...document.querySelectorAll('#example [role=heading][aria-level="2"] .dv-cards-gname')];
              const labels = [...document.querySelectorAll('#example .dv-cards-tlabel')];
              const tiles = [...document.querySelectorAll('#example .dv-cards-tile')].map((t) => t.getBoundingClientRect());
              const row = tiles.length ? tiles.filter((b) => Math.abs(b.top - tiles[0].top) < 1).length : 0;
              return { sw: document.scrollingElement.scrollWidth, cw: document.scrollingElement.clientWidth,
                clipped: h1.filter((e) => e.scrollWidth > e.clientWidth + 1).map((e) => e.textContent),
                h1: Math.min(...h1.map(ratio)), tile: Math.min(...labels.map(ratio)), row, n: h1.length, tiles: labels.length }; }""")
            name = f"{'dark' if dark else 'light'}, {width} px"
            check(f"collection {name}: no sideways page scroll, no H1 clipped, {'at least two tiles a row, ' if mobile else ''}H1 and tile labels at contrast 4.5 or more",
                  m["sw"] <= m["cw"] and not m["clipped"] and m["n"] > 0 and m["tiles"] > 0 and m["h1"] >= 4.5 and m["tile"] >= 4.5 and (m["row"] >= 2 if mobile else m["row"] >= 4), m)
            if mobile:
                closed = page.evaluate("!document.querySelector('data-facets details').open")
                check(f"collection {name}: the rail is a closed disclosure on a phone", closed, closed)
            ctx.shot(page, f"object-collection-{'dark' if dark else 'light'}-{width}")
