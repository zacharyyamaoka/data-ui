"""Browser checks for the raw source view (`type: source`, docs/CONTRACT.md §24), run by tests/browser/checks.py.

Over this case's CSV and the object-db-shelf case's JSON (its public sample, each row read from its public Markdown note), all measured in
the page, never assumed from the DOM:
  - every column: the header is the union of the rows' keys, hidden and undeclared ones included;
  - literals: "  padded  " with its spaces, "1.50" kept as text, null, "", an absent key, a rich cell as its JSON;
  - the source panel: a CSV record's lines verbatim (a quoted field over two lines, CRLF kept) under its header line,
    and an object's Markdown note byte for byte, fetched from this site;
  - Copy and Export CSV: N+1 records, read back by Python's csv module; the download is named <dataset id>.csv;
  - "Only rows in the current filter"; Enter opens a row's panel, Escape closes it;
  - the panel's edge drags (getBoundingClientRect), is remembered and resets on a double-click;
  - 2,196 rows x 52 columns: few rows in the DOM, the page never scrolls sideways, scrolling keeps its frames;
  - 390 px and dark."""

import csv
import io
import json
import pathlib

V = "#example"
HERE = pathlib.Path(__file__).resolve().parent
SHELF = HERE.parent / "object-db-shelf"

GRID = """() => { const v = document.querySelector('#example');
  const names = [...v.querySelectorAll('.dv-source-th .dv-source-name')].map((e) => e.textContent);
  const types = [...v.querySelectorAll('.dv-source-th .dv-source-type')].map((e) => e.textContent);
  const keys = new Set(); for (const r of v.data.rows) for (const k of Object.keys(r)) keys.add(k);
  return { names, types, union: [...keys], drawn: v.querySelectorAll('.dv-source-row').length, cells: v.querySelectorAll('.dv-source-row .dv-source-td').length,
    info: v.querySelector('.dv-source-meta').innerText }; }"""

CELL = """async ([i, key]) => { const v = document.querySelector('#example');
  const names = [...v.querySelectorAll('.dv-source-th .dv-source-name')].map((e) => e.textContent);
  const k = names.indexOf(key); const sc = v.querySelector('.dv-source-scroll');
  // the columns are virtualised too: bring this one on screen (its left edge just right of the pinned gutter), then read it
  sc.scrollLeft = k * 168; sc.scrollTop = Math.max(0, i * 28 - 28);
  for (let n = 0; n < 3; n++) await new Promise((r) => requestAnimationFrame(r));
  const td = v.querySelector(`.dv-source-row[data-i="${i}"] [data-k="${k}"]`);
  sc.scrollLeft = 0;
  return td ? { text: td.textContent, kind: td.className.replace(/.*dv-source-(\\w+).*/, '$1'), title: td.getAttribute('title') } : null; }"""

PANEL = """() => { const p = document.querySelector('#example .dv-source-panel'); const r = p.getBoundingClientRect();
  const t = (s) => { const e = p.querySelector(s); return e ? e.textContent : null; };
  return { hidden: p.hidden, width: r.width, left: r.left, header: t('.dv-source-header-text'), record: t('.dv-source-record-text'),
    file: t('.dv-source-file-text'), lnums: [...p.querySelectorAll('.dv-source-lnums')].map((e) => e.textContent), where: t('.dv-source-where') }; }"""

STUB_CLIPBOARD = """() => { window.__copied = null;
  Object.defineProperty(navigator.clipboard, 'writeText', { configurable: true, value: (t) => { window.__copied = t; return Promise.resolve(); } }); }"""


def records(text):
    return list(csv.reader(io.StringIO(text, newline="")))


def lum(rgb):
    c = [int(x) for x in rgb.replace("rgba(", "").replace("rgb(", "").replace(")", "").split(",")[:3]]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def open_source(ctx, path, **kw):
    page = ctx.page(path + "#view=raw-source", **kw)
    ctx.until(page, "() => document.querySelectorAll('#example .dv-source-row').length > 0")
    return page


def click_source(ctx, page, i):
    page.locator(f"{V} .dv-source-row[data-i='{i}'] .dv-source-open").click()
    ctx.until(page, "() => !document.querySelector('#example .dv-source-panel').hidden")
    ctx.frames(page)


def run(ctx, path):
    check = ctx.check
    shelf_path = path.replace("raw-source", "object-db-shelf")

    # ---- the CSV: columns, literals, panel, keyboard
    page = open_source(ctx, path)
    page.evaluate("localStorage.clear()")
    g = page.evaluate(GRID)
    check("raw source (CSV): the columns are the union of the rows' keys in first-seen order, the auto-assigned id and the two keys the schema does not declare included",
          g["names"] == g["union"] == ["id", "sku", "name", "price", "qty", "note", "colour"] and g["types"][0].startswith("undeclared") and "assigned by data-ui" in g["types"][0]
          and g["types"][5] == g["types"][6] == "undeclared" and g["types"][3] == "text",
          f"{g['names']}; types {g['types']}")
    want = {(1, "name"): ("  padded  ", "string"), (0, "price"): ("1.50", "string"), (2, "qty"): ("null", "null"), (2, "note"): ("null", "null"),
            (3, "note"): ("   ", "string"), (2, "name"): ('"Quoted" washer', "string"), (0, "qty"): ("100", "number"), (0, "name"): ("Bolt, M3 x 8", "string")}
    got = {k: page.evaluate(CELL, list(k)) for k in want}
    bad = {f"{k[0]}.{k[1]}": got[k] for k in want if not got[k] or (got[k]["text"], got[k]["kind"]) != want[k] or got[k]["title"] != want[k][0]}
    two = page.evaluate(CELL, [1, "note"])
    check("raw source (CSV): each stored literal shows exactly (\"  padded  \" with its spaces, \"1.50\" as text, null, three spaces, a quoted name); a value with a line break shows its first line and an ellipsis, whole in its title",
          not bad and two["text"] == "two…" and two["title"] == "two\nlines", bad or f"padded {json.dumps(got[(1, 'name')]['text'])}; price {got[(0, 'price')]['text']}; multi-line {json.dumps(two)}")
    info = g["info"]
    check("raw source (CSV): the info strip names the data file, the .base file, the format, the bytes on disk, the rows and the columns",
          "raw-source/parts.csv" in info and "raw-source/views.base" in info and "CSV" in info and f"{(HERE / 'parts.csv').stat().st_size} bytes" in info
          and "5 loaded" in info and "Columns\n7" in info.replace("\t", "\n"), info.replace("\n", " · "))

    click_source(ctx, page, 1)
    p = page.evaluate(PANEL)
    raw = (HERE / "parts.csv").read_bytes().decode()
    expect = raw.split("\r\n")[2] + "\r\n" + raw.split("\r\n")[3]
    check("raw source (CSV): a row's Source opens the panel: the header line (1) and the record's two lines (3-4) verbatim, the quoted field's CR LF kept",
          not p["hidden"] and p["header"] == "sku,name,price,qty,note,colour" and p["record"] == expect and p["lnums"] == ["1", "3\n4"],
          f"record {json.dumps(p['record'])}; line numbers {p['lnums']}")
    page.locator(f"{V} .dv-source-row[data-i='3']").focus()
    page.keyboard.press("Enter")
    ctx.frames(page)
    on_enter = page.evaluate(PANEL)
    page.keyboard.press("Escape")
    ctx.frames(page)
    closed = page.evaluate(PANEL)["hidden"]
    check("raw source (CSV): Enter on a focused row opens its record (line 6), Escape closes the panel",
          on_enter["record"] == "A-4,Nut M3,1.0,7,   ,silver" and on_enter["lnums"][1] == "6" and closed, f"{json.dumps(on_enter['record'])}; closed: {closed}")

    # ---- copy and export
    page.evaluate(STUB_CLIPBOARD)
    page.click(f"{V} .dv-source-copy")
    ctx.until(page, "() => window.__copied !== null")
    copied = records(page.evaluate("window.__copied"))
    with page.expect_download() as info_dl:
        page.click(f"{V} .dv-source-export")
    dl = info_dl.value
    exported = records(pathlib.Path(dl.path()).read_text(encoding="utf-8"))
    check("raw source (CSV): Copy gives 6 CSV records (the header + 5 rows, as the grid writes them); Export downloads parts.csv with the same 6",
          len(copied) == 6 and copied[0] == ["id", "sku", "name", "price", "qty", "note", "colour"] and copied[2][2] == "  padded  " and copied[2][5] == "two\nlines"
          and copied[3][4] == "null" and copied[1][3] == "1.50" and dl.suggested_filename == "parts.csv" and exported == copied,
          f"copy: {len(copied)} records, row 2 {copied[2] if len(copied) > 2 else None}; export: {dl.suggested_filename}, {len(exported)} records")

    # ---- only the rows in the current filter
    ctx.drawn(page, lambda: page.fill(f"{V} .dv-search input", "Nut"))
    every = page.evaluate(GRID)["drawn"]
    ctx.drawn(page, lambda: page.check(f"{V} .dv-source-filtered"))
    g2 = page.evaluate(GRID)
    page.evaluate("window.__copied = null")
    page.click(f"{V} .dv-source-copy")
    ctx.until(page, "() => window.__copied !== null")
    some = records(page.evaluate("window.__copied"))
    ctx.drawn(page, lambda: page.uncheck(f"{V} .dv-source-filtered"))
    back = page.evaluate(GRID)["drawn"]
    check("raw source (CSV): with a search, every row as loaded stays by default; \"Only rows in the current filter\" shows (and copies) the 1 match; unticked, all 5 again",
          every == 5 and g2["drawn"] == 1 and "1 in the current filter" in g2["info"] and len(some) == 2 and some[1][1] == "A-4" and back == 5,
          f"search on: {every} rows; ticked: {g2['drawn']}, copy {len(some)} records; unticked: {back}")
    page.context.close()

    # ---- the object library (JSON): every key, rich cells, the Markdown note
    page = open_source(ctx, shelf_path)
    page.evaluate("localStorage.clear()")
    g = page.evaluate(GRID)
    hidden = ["mesh", "soft_thumbnail", "thumbnail", "colour_rgb", "id"]
    rows = json.loads((SHELF / "objects.json").read_text(encoding="utf-8"))["rows"]
    union = list(dict.fromkeys(k for r in rows for k in r))
    check(f"raw source (objects): every column present: the header is the union of the {len(rows)} rows' keys, hidden properties (mesh, soft_thumbnail, thumbnail, colour_rgb, id) included",
          g["names"] == g["union"] == union and all(h in g["names"] for h in hidden) and f"{len(rows):,} loaded" in g["info"] and "runtime shape" in g["info"],
          f"{len(g['names'])} columns of {len(union)} keys; hidden ones present: {[h for h in hidden if h in g['names']]}")
    mass = page.evaluate(CELL, [0, "mass_g"])
    mixes = page.evaluate(CELL, [0, "mixes"])
    brand = page.evaluate(CELL, [0, "brand"])
    check("raw source (objects): a rich cell is its compact JSON (no unit, no basis mark), a list is [], a null is null",
          mass["text"] == json.dumps(rows[0]["mass_g"], separators=(",", ":"), ensure_ascii=False) and mixes["text"] == json.dumps(rows[0]["mixes"]) and brand["text"] == "null" and brand["kind"] == "null",
          f"mass_g {mass['text']}; mixes {mixes['text']}; brand {brand['text']}")
    click_source(ctx, page, 0)
    ctx.until(page, "() => { const e = document.querySelector('#example .dv-source-file-text'); return e && e.textContent !== 'Loading…'; }")
    p = page.evaluate(PANEL)
    oid = rows[0]["id"]
    note = (SHELF / "notes" / f"{oid}.md").read_text(encoding="utf-8")
    fetched = [u for u in page.evaluate("performance.getEntriesByType('resource').map((e) => e.name)") if "/notes/" in u]
    check("raw source (objects): a row's Source shows the object's Markdown note (origin.url notes/{id}.md) byte for byte: first line ---, then id: <id>; fetched once, from this site",
          p["file"] == note and p["file"].split("\n")[0] == "---" and f"id: {oid}" in p["file"] and fetched == [f"{ctx.base}/gallery/object-db-shelf/notes/{oid}.md"],
          f"{len(p['file'] or '')} chars; first lines {json.dumps((p['file'] or '').split(chr(10))[:2])}; fetched {fetched}")

    # ---- the panel's edge (Zach's standing rule: every side panel resizes; measured)
    w0 = p["width"]
    handle = page.locator(f"{V} .dv-source-body > .dv-splitter")
    hb = handle.bounding_box()
    page.mouse.move(hb["x"] + hb["width"] / 2, hb["y"] + 200)
    page.mouse.down()
    page.mouse.move(hb["x"] + hb["width"] / 2 - 120, hb["y"] + 200, steps=8)
    page.mouse.up()
    ctx.frames(page)
    w1 = page.evaluate(PANEL)["width"]
    page.reload()
    ctx.until(page, "() => document.querySelectorAll('#example .dv-source-row').length > 0")
    click_source(ctx, page, 0)
    w2 = page.evaluate(PANEL)["width"]
    hb = page.locator(f"{V} .dv-source-body > .dv-splitter").bounding_box()
    page.mouse.dblclick(hb["x"] + hb["width"] / 2, hb["y"] + 200)
    ctx.frames(page)
    w3 = page.evaluate(PANEL)["width"]
    check("raw source: dragging the panel's edge 120 px left widens it ~120 px, the width is remembered across a reload, a double-click resets it",
          110 <= w1 - w0 <= 130 and abs(w2 - w1) <= 1 and abs(w3 - w0) <= 1, f"{w0:.0f} → dragged {w1:.0f} → reloaded {w2:.0f} → reset {w3:.0f} px")
    page.evaluate("localStorage.clear()")
    ctx.shot(page, "raw-source-objects-panel-light")

    # ---- 2,196 rows x 52 columns, set from script (the library's size), with the literals JSON can hold
    page.evaluate("""() => { const v = document.querySelector('#example'); const base = v.data.rows; const rows = [];
      for (let i = 0; i < 2196; i++) { const b = base[i % base.length]; const r = { ...b, id: `${b.id}#${i}` }; for (let k = 0; k < 17; k++) r[`extra_${k}`] = i * k; rows.push(r); }
      rows[1].literal = '  sp  '; rows[2].literal = ''; rows[3].literal = null; rows[4]._private = 'x'; rows[5].literal = -0; rows[6].literal = 1.5;
      // WHY counted, not typed: the case's data gains columns (mesh_view, 2026-10-26); the union of keys is the oracle
      window.__expectedCols = new Set(rows.flatMap((r) => Object.keys(r))).size;
      v.data = { id: 'stress', title: 'stress', titleProperty: 'name', properties: v.data.properties, rows }; }""")
    ctx.until(page, "() => /2,196 loaded/.test(document.querySelector('#example .dv-source-meta').textContent)")
    ctx.frames(page)
    g = page.evaluate(GRID)
    lit = {k: page.evaluate(CELL, [i, "literal"]) for k, i in (("absent", 0), ("spaces", 1), ("empty", 2), ("null", 3), ("minus0", 5), ("num", 6))}
    expected = page.evaluate("window.__expectedCols")
    check("raw source (2,196 rows x ~50 columns): every key of every row is a column (a _ key and keys only some rows have included), only the rows and columns on screen in the DOM; \"\" , null and an absent key told apart",
          len(g["names"]) == expected and "_private" in g["names"] and g["drawn"] <= 60 and g["cells"] <= g["drawn"] * 14 and lit["absent"]["text"] == "" and lit["absent"]["title"] == "absent"
          and lit["spaces"]["text"] == "  sp  " and (lit["empty"]["text"], lit["empty"]["kind"]) == ('""', "empty") and (lit["null"]["text"], lit["null"]["kind"]) == ("null", "null")
          and lit["minus0"]["text"] == "-0" and lit["num"]["text"] == "1.5",
          f"{len(g['names'])} columns; {g['drawn']} rows and {g['cells']} cells in the DOM; " + "; ".join(f"{k} {json.dumps(v['text'])} ({v['kind']})" for k, v in lit.items()))
    m = page.evaluate("""async () => { const sc = document.querySelector('#example .dv-source-scroll'); const raf = () => new Promise((r) => requestAnimationFrame(r));
      await raf(); const gaps = []; let last = performance.now();
      for (let k = 0; k < 120; k++) { sc.scrollTop += 480; sc.scrollLeft = (k % 20) * 300; await raf(); const now = performance.now(); gaps.push(now - last); last = now; }
      sc.scrollTop = sc.scrollHeight / 2; await raf(); await raf();
      const r = sc.getBoundingClientRect(); const at = document.elementFromPoint(r.left + 40, r.top + r.height / 2); const row = at && at.closest('.dv-source-row');
      const head = sc.querySelector('.dv-source-head').getBoundingClientRect().height;
      const want = Math.floor((sc.scrollTop + r.height / 2 - head) / 28);
      gaps.sort((a, b) => a - b);
      return { p95: gaps[Math.floor(gaps.length * 0.95)], median: gaps[gaps.length >> 1], max: gaps[gaps.length - 1], row: row ? Number(row.dataset.i) : null, want,
        sideways: document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth, inner: sc.scrollWidth - sc.clientWidth, drawn: sc.querySelectorAll('.dv-source-row').length }; }""")
    check("raw source (2,196 x 52): scrolled to the middle, the row under the viewport's centre is the one its offset says; the grid scrolls sideways inside itself, the page never does",
          m["row"] is not None and abs(m["row"] - m["want"]) <= 1 and m["sideways"] <= 0 and m["inner"] > 5000 and m["drawn"] <= 60,
          f"row {m['row']} (expected {m['want']}); page overflow {m['sideways']} px; grid overflow {m['inner']} px; {m['drawn']} rows in the DOM")
    ctx.budget("raw source (2,196 x 52): scrolling 120 frames down and sideways, the 95th-percentile frame", m["p95"], 50,
               f"median {m['median']:.1f} ms, max {m['max']:.1f} ms")
    page.context.close()

    # ---- dark (tokens only), with the panel open: the screenshots
    for dark in (False, True):
        page = open_source(ctx, shelf_path, width=1280, height=800, dark=dark)
        click_source(ctx, page, 1)
        ctx.until(page, "() => { const e = document.querySelector('#example .dv-source-file-text'); return e && e.textContent !== 'Loading…'; }")
        colours = page.evaluate("""() => { const s = (q, p) => getComputedStyle(document.querySelector(q))[p];
          return { cell: s('#example .dv-source-td', 'backgroundColor'), text: s('#example .dv-source-td', 'color'), panel: s('#example .dv-source-panel', 'backgroundColor'),
            bg: getComputedStyle(document.querySelector('#example')).getPropertyValue('--dv-bg').trim() }; }""")
        ok = (lum(colours["cell"]) < 60 and lum(colours["text"]) > 150) if dark else (lum(colours["cell"]) > 200 and lum(colours["text"]) < 100)
        check(f"raw source, {'dark' if dark else 'light'}: the grid and the panel follow the theme's tokens", ok and colours["cell"] == colours["panel"], colours)
        ctx.shot(page, f"raw-source-panel-{'dark' if dark else 'light'}")
        page.context.close()

    # ---- 390 px, light and dark
    for dark in (False, True):
        page = open_source(ctx, path, width=390, height=844, mobile=True, dark=dark)
        before = page.evaluate("() => { const sc = document.querySelector('#example .dv-source-scroll'); return { page: document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth, inner: sc.scrollWidth - sc.clientWidth }; }")
        page.locator(f"{V} .dv-source-row[data-i='1'] .dv-source-open").tap()
        ctx.until(page, "() => !document.querySelector('#example .dv-source-panel').hidden")
        ctx.frames(page)
        p = page.evaluate(PANEL)
        body = page.evaluate("document.querySelector('#example .dv-source-body').getBoundingClientRect().width")
        handle = page.evaluate("document.querySelector('#example .dv-source-body > .dv-splitter').hidden")
        after = page.evaluate("document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth")
        ctx.shot(page, f"raw-source-390{'-dark' if dark else ''}")
        page.locator(f"{V} .dv-source-close").tap()
        ctx.frames(page)
        shut = page.evaluate(PANEL)["hidden"]
        check(f"raw source at 390 px{' (dark)' if dark else ''}: no sideways page scroll; the grid scrolls sideways inside the view; the panel fills the view (no handle) and ✕ closes it",
              before["page"] <= 0 and after <= 0 and before["inner"] > 300 and abs(p["width"] - body) <= 1 and p["width"] <= 390 and handle and p["record"] and shut,
              f"page overflow {before['page']} / {after} px; grid overflow {before['inner']} px; panel {p['width']:.0f} of {body:.0f} px; handle hidden {handle}")
        page.context.close()
