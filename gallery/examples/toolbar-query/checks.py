"""Browser checks for this case (run by tests/browser/checks.py): the query bar and selection of docs/CONTRACT.md §15.
Every count is checked against a hand count over the case's data file, every place against getBoundingClientRect:
autocomplete (properties, then values with counts), a typed clause and a rail tick being the same token, filter and
URL; errors; shift / ctrl ranges in the table and the gallery; the bulk bar and its actions (Compare, Export CSV,
Copy IDs); the table's freeze and wrap; the gallery's maxColumns; the box at 390 px, light and dark."""

import csv
import io
import json
import pathlib

V = "#example"
DATA = json.loads((pathlib.Path(__file__).resolve().parent.parent / "robotparts-actuators" / "actuators.json").read_text())
ROWS = DATA["rows"]


def value(cell):
    return cell.get("value") if isinstance(cell, dict) else cell


def status(page):
    return page.inner_text(f"{V} .dv-status").split(" · ")[0]


def options(page):
    return page.evaluate("""() => [...document.querySelectorAll('#example .dv-suggest-item')].map((li) => ({
      kind: [...li.classList].find((c) => c.startsWith('dv-s-')).slice(5), label: li.querySelector('.dv-s-label').textContent,
      count: li.querySelector('.dv-s-count') ? Number(li.querySelector('.dv-s-count').textContent.replace(/,/g, '')) : null }))""")


def reset(page):
    page.evaluate("() => { const el = document.querySelector('#example'); el.clearSelection(); el.filters = null; el.search(''); el.selectView('Rows'); }")
    CTX.frames(page, 3)


def box(page, sel):
    return page.evaluate(f"(() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return null; const r = e.getBoundingClientRect(); return {{ left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height }}; }})()")


CTX = None  # the run's ctx (tests/browser/checks.py): its until() and frames() replace fixed pauses


def run(ctx, path):
    global CTX
    CTX = ctx
    check = ctx.check
    page = ctx.page(path)
    q = page.locator(f"{V} .dv-qinput")

    # ---- autocomplete: properties, then the values of brand with their counts (a hand count over the data)
    q.click()
    page.keyboard.type("bran")
    CTX.frames(page, 3)
    props = options(page)
    typing = status(page)
    ctx.shot(page, "toolbar-query-suggest-properties")
    page.keyboard.type("d:")
    CTX.frames(page, 3)
    vals = options(page)
    ctx.shot(page, "toolbar-query-suggest-values")
    hand = {}
    for r in ROWS:
        hand[r["brand"]] = hand.get(r["brand"], 0) + 1
    top = sorted(hand.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
    check("query: typing bran suggests the Brand property (without searching for 'bran' yet), then brand: suggests its values with counts (top 12, = a hand count)",
          props and props[0]["kind"] == "property" and props[0]["label"] == "Brand" and typing.startswith("1,149 of 1,149") and [(v["label"], v["count"]) for v in vals if v["kind"] == "value"] == top,
          {"first property": props[0]["label"] if props else None, "rows while typing": typing, "values": [(v["label"], v["count"]) for v in vals[:4]], "hand": top[:4]})
    combo = page.evaluate("() => { const i = document.querySelector('#example .dv-qinput'); return [i.getAttribute('role'), i.getAttribute('aria-expanded'), document.getElementById(i.getAttribute('aria-controls')).getAttribute('role')]; }")
    page.keyboard.press("ArrowDown")
    active = page.evaluate("() => { const i = document.querySelector('#example .dv-qinput'); const a = document.getElementById(i.getAttribute('aria-activedescendant')); return a && a.getAttribute('aria-selected'); }")
    check("query: the box is a combobox over a listbox; ArrowDown moves aria-activedescendant", combo == ["combobox", "true", "listbox"] and active == "true", {"roles": combo, "active selected": active})
    page.keyboard.press("Enter")
    CTX.frames(page, 3)
    brand, n = top[0]
    tokens = page.locator(f"{V} .dv-qtoken").all_inner_texts()
    ticked = page.is_checked(f"data-facets input[data-p=brand][data-value='{brand}']")
    url = page.evaluate("new URLSearchParams(location.search).get('brand')")
    st = status(page)
    check(f"query: ArrowDown + Enter picks {brand}: the rows narrow to its {n}, the rail ticks it, a token shows, the URL reads ?brand=",
          st.startswith(f"{n} of 1,149") and ticked and len(tokens) == 1 and f"Brand is {brand}" in tokens[0] and url == brand and q.input_value() == "",
          {"status": st, "rail": ticked, "tokens": tokens, "brand param": url, "box": q.input_value()})
    page.locator(f"{V} .dv-qinput").blur()
    ctx.shot(page, "toolbar-query-tokens")
    page.reload()
    page.wait_for_selector(f"{V} .dv-qtoken", timeout=15000)
    CTX.until(page, "() => document.querySelector('data-facets input[type=checkbox]')")
    CTX.frames(page, 3)
    check("query: reloading the URL restores the token, the rail and the row count",
          status(page).startswith(f"{n} of 1,149") and page.is_checked(f"data-facets input[data-p=brand][data-value='{brand}']") and len(page.locator(f"{V} .dv-qtoken").all_inner_texts()) == 1,
          {"status": status(page), "tokens": page.locator(f"{V} .dv-qtoken").all_inner_texts()})
    second = top[1][0]
    page.check(f"data-facets input[data-p=brand][data-value='{second}']")
    CTX.frames(page, 3)
    tokens = page.locator(f"{V} .dv-qtoken").all_inner_texts()
    check("query: a rail tick of a second brand shows in the box at once, in the same token (one filter, two editors)",
          len(tokens) == 1 and brand in tokens[0] and second in tokens[0] and status(page).startswith(f"{n + top[1][1]} of 1,149"), {"tokens": tokens, "status": status(page)})
    page.locator(f"{V} .dv-qtoken-x").first.click()
    CTX.frames(page, 3)
    check("query: ✕ on a token removes its clause (and the rail unticks)", status(page).startswith("1,149 of 1,149") and not page.is_checked(f"data-facets input[data-p=brand][data-value='{brand}']"), status(page))

    # ---- a typed number clause: exactly the rows a hand count gives
    reset(page)
    q.click()
    page.keyboard.type("peak_torque:>20")
    page.keyboard.press("Enter")
    CTX.frames(page, 3)
    want = sum(1 for r in ROWS if isinstance(value(r.get("peak_torque")), (int, float)) and value(r["peak_torque"]) > 20)
    check("query: peak_torque:>20 filters to exactly the hand count, and is the filter expression peak_torque > 20",
          status(page).startswith(f"{want:,} of 1,149") and page.evaluate("JSON.stringify(document.querySelector('#example').filters)") == '{"and":["peak_torque > 20"]}',
          {"status": status(page), "hand count": want, "filters": page.evaluate("JSON.stringify(document.querySelector('#example').filters)")})
    page.keyboard.type("gim nope:1 ")
    page.keyboard.press("Enter")
    CTX.frames(page, 3)
    bad = page.evaluate("() => ({ marks: [...document.querySelectorAll('#example .dv-qbad')].map((e) => e.textContent), err: document.querySelector('#example .dv-qerr').hidden ? '' : document.querySelector('#example .dv-qerr').textContent, query: document.querySelector('#example').query, filters: JSON.stringify(document.querySelector('#example').filters) })")
    check("query: a clause that does not parse is underlined red with its reason and not applied; the words still search",
          bad["marks"] == ["nope:1"] and "no property" in bad["err"] and bad["query"] == "gim" and bad["filters"] == '{"and":["peak_torque > 20"]}', bad)

    # ---- selection: shift ranges, ctrl adds, shift+ctrl adds a range
    reset(page)
    check("query: words set from outside (search('')) replace the box's text, even while it has focus", q.input_value() == "", q.input_value())
    page.wait_for_selector(f"{V} tbody tr.dv-row .dv-selbox")
    row = lambda i: page.locator(f"{V} tbody tr.dv-row").nth(i)
    order = page.evaluate("[...document.querySelectorAll('#example tbody tr.dv-row')].map((tr) => tr.dataset.id)")
    row(2).locator(".dv-selbox").click()
    row(7).locator(".dv-selbox").click(modifiers=["Shift"])
    a = page.evaluate("[document.querySelector('#example').selection.length, document.querySelectorAll('#example tr.dv-sel').length]")
    row(11).locator("td").nth(2).click(modifiers=["Control"])
    b = page.evaluate("[document.querySelector('#example').selection.length, document.querySelectorAll('#example tr.dv-sel').length]")
    row(14).locator("td").nth(2).click(modifiers=["Shift", "Control"])
    c = page.evaluate("[document.querySelector('#example').selection.length, document.querySelectorAll('#example tr.dv-sel').length]")
    picked = page.evaluate("document.querySelector('#example').selection")
    check("select: row 3's checkbox then shift-click row 8 selects 6; ctrl-click row 12 makes 7; shift+ctrl-click row 15 makes 10, in drawn order",
          a == [6, 6] and b == [7, 7] and c == [10, 10] and picked == order[2:8] + order[11:15] and not page.locator(f"{V} .dv-peek:not([hidden])").count(),
          {"after shift": a, "after ctrl": b, "after shift+ctrl": c})
    bulk = box(page, f"{V} .dv-bulk")
    text = page.inner_text(f"{V} .dv-bulk")
    head = page.evaluate("(() => { const h = document.querySelector('#example .dv-selall'); return [h.checked, h.indeterminate]; })()")
    page.keyboard.press("Escape")
    CTX.frames(page, 3)
    gone = box(page, f"{V} .dv-bulk")
    check("select: the bulk bar appears with 'N selected' (the header box indeterminate) and Escape clears it",
          bulk["height"] > 0 and "10 selected" in text and head == [False, True] and gone["height"] == 0 and page.evaluate("document.querySelector('#example').selection.length") == 0,
          {"bar height": bulk["height"], "text": text.split("\n")[0], "header": head, "after Escape": gone["height"]})

    # ---- the bulk actions: Compare, Export CSV, Copy IDs
    for i in range(3):
        row(i).locator(".dv-selbox").click()
    three = page.evaluate("document.querySelector('#example').selection")
    CTX.frames(page, 3)
    ctx.shot(page, "toolbar-query-bulk-3")
    events = page.evaluate("() => { window.__acts = []; document.querySelector('#example').addEventListener('data-views-action', (e) => window.__acts.push([e.detail.id, e.detail.ids.length])); }")
    page.click(f"{V} .dv-bulk-act:has-text('Compare')")
    page.wait_for_selector(f"{V} .dv-view-compare [data-remove]", timeout=15000)
    shown = page.evaluate("[...document.querySelectorAll('#example .dv-view-compare [data-remove]')].map((b) => b.dataset.remove)")
    check("bulk: Compare with 3 selected switches to the compare view of exactly those 3 (after a data-views-action event)",
          sorted(shown) == sorted(three) and page.evaluate("document.querySelector('#example').view.type") == "compare" and page.evaluate("window.__acts") == [["compare", 3]],
          {"compared": shown, "selected": three})
    page.evaluate("document.querySelector('#example').selectView('Rows')")
    page.wait_for_selector(f"{V} tbody tr.dv-row .dv-selbox")
    page.evaluate(f"document.querySelector('#example').select({json.dumps(order[:4])})")
    CTX.frames(page, 3)
    with page.expect_download() as dl:
        page.click(f"{V} .dv-bulk-act:has-text('Export CSV')")
    got = dl.value
    body = pathlib.Path(got.path()).read_bytes().decode("utf-8")  # bytes: read_text would turn the CRLFs into LFs
    table = list(csv.reader(io.StringIO(body, newline="")))
    props = DATA["properties"]
    labels = {"model": "Model", "brand": "Brand", "form": "Form", "drivetrain": "Drivetrain", "peak_torque": "Peak torque", "rated_torque": "Rated torque", "mass": "Mass", "price": "Price from", "buses": "Bus"}
    view_order = ["model", "brand", "form", "drivetrain", "peak_torque", "rated_torque", "mass", "price", "buses"]
    want_head = [labels[p] + (f" ({props[p]['unitText']})" if props[p].get("unitText") else "") for p in view_order]
    by_id = {r["id"]: r for r in ROWS}
    check("bulk: Export CSV downloads rows.csv: the view's visible properties with units in the headers, one line per selected row (RFC 4180, CRLF)",
          got.suggested_filename == "rows.csv" and table[0] == want_head and len(table) == 5 and [t[0] for t in table[1:]] == [by_id[i]["model"] for i in order[:4]] and "\r\n" in body,
          {"file": got.suggested_filename, "header": table[0][:5], "lines": len(table) - 1, "crlf": "\r\n" in body})
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=ctx.base)
    page.click(f"{V} .dv-bulk-act:has-text('Copy IDs')")
    CTX.frames(page, 3)
    clip = page.evaluate("navigator.clipboard.readText()")
    check("bulk: Copy IDs puts the selected ids on the clipboard, one per line, and says so", clip == "\n".join(order[:4]) and "Copied 4" in page.inner_text(f"{V} .dv-bulk-msg"), {"clipboard": clip.split("\n")})
    page.context.close()

    pick_closes_checks(ctx, path)
    stripe_checks(ctx, path)
    label_checks(ctx, path)
    table_label_checks(ctx, path)
    gallery_checks(ctx, path)
    table_layout_checks(ctx, path)
    phone_checks(ctx, path)
    # the bar is one row in this preset too (dropdown, query-tokens rail, popover; §15 note 2026-10-26)
    import importlib.util as _u, pathlib as _p
    _spec = _u.spec_from_file_location("toolbar_bar_checks", _p.Path(__file__).resolve().parents[1] / "toolbar-bar" / "checks.py")
    bar = _u.module_from_spec(_spec)
    _spec.loader.exec_module(bar)
    bar.CTX = ctx
    bar.one_row(ctx, path, ctx.check, "toolbar-query")


def pick_closes_checks(ctx, path):
    """A pick commits the clause and closes the list, so the pill row under the bar is visible and clickable; typing,
    ArrowDown or Space reopen it with the next properties."""
    check = ctx.check
    page = ctx.page(path)
    page.evaluate("document.querySelector('#example').setAttribute('filters', 'pills rail')")
    page.wait_for_selector(f"{V} .dv-qinput")
    page.locator(f"{V} .dv-qinput").click()
    page.keyboard.type("brand:")
    CTX.frames(page, 3)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    CTX.frames(page, 3)
    got = page.evaluate("""() => {
      const s = document.querySelector('#example .dv-suggest'), pill = document.querySelector('#example .dv-pill');
      const r = s.getBoundingClientRect(), p = pill ? pill.getBoundingClientRect() : null;
      const hit = p ? document.elementFromPoint(p.left + p.width / 2, p.top + p.height / 2) : null;
      return { suggest: Math.round(r.height), hidden: s.hidden, expanded: document.querySelector('#example .dv-qinput').getAttribute('aria-expanded'),
        pill: p ? Math.round(p.height) : 0, text: pill ? pill.textContent : null, onPill: !!(hit && pill.contains(hit)), focus: document.activeElement.className }; }""")
    page.keyboard.press("ArrowDown")
    CTX.frames(page, 3)
    again = page.evaluate("(() => { const s = document.querySelector('#example .dv-suggest'); return [s.hidden, [...s.querySelectorAll('.dv-suggest-item')].slice(0, 1).map((li) => li.className)]; })()")
    ctx.shot(page, "toolbar-query-pick-closes")
    check("query: a pick commits the clause and closes the suggestions (height 0); the new pill is visible and unobscured; ArrowDown reopens on the next property",
          got["suggest"] == 0 and got["hidden"] and got["expanded"] == "false" and got["pill"] > 0 and got["onPill"] and "dv-qinput" in got["focus"]
          and again[0] is False and again[1] and "dv-s-property" in again[1][0], {**got, "after ArrowDown": again})
    page.context.close()


# Each drawn row's cells, as painted: a cell's own background, else the first ancestor's that is not transparent (what
# shows through it), with its opacity. A row reads as one band when every cell paints the same colour at opacity 1.
ROW_PAINT = """(sel) => {
  const paint = (td) => { for (let e = td; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor; if (c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') return c; } return 'none'; };
  return [...document.querySelectorAll(sel)].map((tr) => ({ i: tr.dataset.i, cls: tr.className, colors: [...new Set([...tr.children].map(paint))],
    faded: [...tr.children].filter((td) => getComputedStyle(td).opacity !== '1').map((td) => td.dataset.col || td.className) })); }"""


def stripe_checks(ctx, path):
    """Zebra rows (frame="bleed" and "tabs") are one band per row: the frozen first column, the checkbox column and an
    empty cell paint what their row paints, scrolled sideways too, and so does a selected, hovered or group row."""
    check = ctx.check
    for frame in ("bleed", "tabs"):
        for dark in (False, True):
            page = ctx.page(path, width=1000, height=800, dark=dark)
            page.evaluate(f"document.querySelector('#example').setAttribute('frame', '{frame}')")
            page.wait_for_selector(f"{V} tbody tr.dv-row[data-id]")
            CTX.frames(page, 3)
            rows = f"{V} tbody tr.dv-row:not(.dv-pad)"
            plain = page.evaluate(ROW_PAINT, rows)[:12]
            stripes = len({r["colors"][0] for r in plain if len(r["colors"]) == 1})
            page.locator(f"{V} .dv-scroll").evaluate("(el) => { el.scrollLeft = 300; }")
            CTX.frames(page, 3)
            scrolled = page.evaluate(ROW_PAINT, rows)[:12]
            page.evaluate("(() => { const el = document.querySelector('#example'); el.select([el.model.rows[1].id, el.model.rows[2].id]); })()")
            CTX.frames(page, 3)
            selected = page.evaluate(ROW_PAINT, f"{V} tbody tr.dv-sel")
            box = page.locator(f"{V} tbody tr.dv-row").nth(4).locator("td[data-col=model]").bounding_box()  # the frozen cell: still in view while scrolled
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            # WHY wait for :hover, not a pause: a row redrawn under a still pointer is hovered only when the browser
            # re-hit-tests (its next synthetic mouse move), which a few frames do not always include
            CTX.until(page, "() => document.querySelector('#example tbody tr.dv-row:hover')")
            hovered = page.evaluate(ROW_PAINT, f"{V} tbody tr.dv-row:hover")
            page.evaluate("(() => { const el = document.querySelector('#example'); el.clearSelection(); el.selectView('By brand'); })()")
            page.wait_for_selector(f"{V} tbody tr.dv-group")
            page.mouse.move(2, 2)
            CTX.frames(page, 3)
            groups = page.evaluate(ROW_PAINT, f"{V} tbody tr.dv-group")[:4] + page.evaluate(ROW_PAINT, rows)[:6]
            bad = [{"state": name, **r} for name, list_ in (("plain", plain), ("scrolled", scrolled), ("selected", selected), ("hovered", hovered), ("grouped", groups))
                   for r in list_ if len(r["colors"]) != 1 or r["faded"]]
            ok = not bad and stripes == 2 and len(selected) == 2 and len(hovered) == 1 and len(groups) >= 8
            check(f"stripes, frame={frame}, {'dark' if dark else 'light'}: every cell of a row paints its row's colour at full opacity (frozen, checkbox and empty cells too), striped, scrolled sideways, selected, hovered and grouped",
                  ok, bad[:3] or {"stripe colours": stripes, "selected": len(selected), "hovered": len(hovered), "group rows": len(groups)})
            page.context.close()


def label_checks(ctx, path):
    """robotparts stores slugs and labels them (brand: "steadywin", labels: {steadywin: "Steadywin"}): the box shows the
    label, as the rail does, and typing the label is the stored value."""
    check = ctx.check
    page = ctx.page(path)
    page.evaluate("""() => {
      const el = document.querySelector('#example'), d = el.data, slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-');
      const labels = {};
      for (const r of d.rows) labels[slug(r.brand)] = r.brand;
      el.data = { ...d, properties: { ...d.properties, brand: { ...d.properties.brand, labels } }, rows: d.rows.map((r) => ({ ...r, brand: slug(r.brand) })) };
    }""")
    page.wait_for_selector("data-facets input[data-p=brand][data-value=steadywin]")
    page.locator(f"{V} .dv-qinput").click()
    page.keyboard.type("brand:")
    CTX.frames(page, 3)
    shown = [o["label"] for o in options(page) if o["kind"] == "value"]
    page.keyboard.type("STEADYWIN")
    page.keyboard.press("Enter")
    CTX.frames(page, 3)
    typed = page.evaluate("[document.querySelector('#example').model.rows.map((r) => r.id), JSON.stringify(document.querySelector('#example').filters)]")
    token = page.locator(f"{V} .dv-qtoken").all_inner_texts()
    ticked = page.is_checked("data-facets input[data-p=brand][data-value=steadywin]")
    ctx.shot(page, "toolbar-query-labels")
    page.evaluate("document.querySelector('#example').filters = null")
    CTX.frames(page, 3)
    page.check("data-facets input[data-p=brand][data-value=steadywin]")
    CTX.frames(page, 3)
    railed = page.evaluate("document.querySelector('#example').model.rows.map((r) => r.id)")
    check("labels: a labelled property's suggestions and token show the label (Steadywin), the expression keeps the stored value (steadywin)",
          "Steadywin" in shown and "steadywin" not in shown and token and token[0].startswith("Brand is Steadywin") and typed[1] == '{"and":["brand == \\"steadywin\\""]}',
          {"suggested": shown[:4], "token": token, "filters": typed[1]})
    check("labels: typing the label (any case) filters to exactly the rows the rail tick picks, and ticks that checkbox",
          ticked and len(typed[0]) == 86 and typed[0] == railed, {"typed": len(typed[0]), "rail": len(railed), "ticked": ticked})
    page.context.close()


def table_label_checks(ctx, path):
    """A labelled property's table cells show the label, as the rail, pills and tokens do (robotparts' form:
    direct_drive -> "Direct drive"); the stored value stays in the cell's title. Plain text and badge cells both."""
    check = ctx.check
    page = ctx.page(path)
    page.evaluate("""() => {
      const el = document.querySelector('#example'), d = el.data;
      const labels = {}; for (const r of d.rows) if (r.form) labels[r.form] = 'Label ' + r.form;
      el.data = { ...d, properties: { ...d.properties, form: { ...d.properties.form, labels } } };
      el.selectView('Rows');
    }""")
    CTX.frames(page, 3)
    got = page.evaluate("""() => [...document.querySelectorAll('#example td[data-col="form"]')].slice(0, 8).map((td) => [td.textContent.trim(), td.title])""")
    page.evaluate("document.querySelector('#example').setView({display: {form: 'badge'}})")
    CTX.frames(page, 3)
    badges = page.evaluate("""() => [...document.querySelectorAll('#example td[data-col="form"] .dv-badge')].slice(0, 8).map((b) => b.textContent.trim())""")
    check("labels: table cells (plain text and badge) show a labelled property's label; the stored value stays in the title",
          got and all(t.startswith("Label ") and t == "Label " + title for t, title in got) and badges and all(b.startswith("Label ") for b in badges),
          {"cells": got[:3], "badges": badges[:3]})
    page.context.close()


def gallery_checks(ctx, path):
    check = ctx.check
    page = ctx.page(path, width=1440)
    page.evaluate("document.querySelector('#example').selectView('Gallery')")
    page.wait_for_selector(f"{V} .dv-cards-card", timeout=15000)
    lefts = """() => { const cards = [...document.querySelectorAll('#example .dv-cards-card')].map((c) => c.getBoundingClientRect());
      const top = Math.min(...cards.map((r) => Math.round(r.top))); return [...new Set(cards.filter((r) => Math.round(r.top) === top).map((r) => Math.round(r.left)))].length; }"""
    free = page.evaluate(lefts)
    page.evaluate("document.querySelector('#example').setView({ maxColumns: 3 })")
    CTX.frames(page, 3)
    capped = page.evaluate(lefts)
    ctx.shot(page, "toolbar-query-gallery-max3")
    check("gallery: maxColumns 3 holds on a 1440 px page (3 card columns in the first row); with no cap there are more", capped == 3 and free > 3, {"no cap": free, "maxColumns 3": capped})
    cards = page.locator(f"{V} .dv-cards-card")
    cards.nth(0).hover()
    cards.nth(0).locator(".dv-selbox").click()
    cards.nth(4).hover()
    cards.nth(4).locator(".dv-selbox").click(modifiers=["Shift"])
    cards.nth(7).click(modifiers=["Control"])
    page.mouse.move(2, 2)
    # the checks fade in (.12 s): wait for the tenth card's check to be fully shown, not for a fixed time
    CTX.until(page, "() => getComputedStyle(document.querySelectorAll('#example .dv-cards-card')[9].querySelector('.dv-cards-check')).opacity === '1'")
    got = page.evaluate("[document.querySelector('#example').selection.length, document.querySelectorAll('#example .dv-cards-card.dv-sel').length, getComputedStyle(document.querySelectorAll('#example .dv-cards-card')[9].querySelector('.dv-cards-check')).opacity]")
    check("gallery: a card's check, shift-click for the range, ctrl-click to add: 6 selected cards, and every check shows once any is selected",
          got[:2] == [6, 6] and got[2] == "1" and not page.locator(f"{V} .dv-peek:not([hidden])").count(), got)
    page.context.close()


def table_layout_checks(ctx, path):
    check = ctx.check
    page = ctx.page(path, width=1000, height=800)
    page.wait_for_selector(f"{V} tbody tr.dv-row")
    first = f"{V} tbody tr.dv-row:first-child td:nth-child(2)"
    def lefts():
        a = box(page, first)["left"]
        page.locator(f"{V} .dv-scroll").evaluate("(el) => { el.scrollLeft = 300; }")
        CTX.frames(page, 3)
        b = box(page, first)["left"]
        page.locator(f"{V} .dv-scroll").evaluate("(el) => { el.scrollLeft = 0; }")
        CTX.frames(page, 3)
        return round(a), round(b)
    frozen = lefts()
    page.evaluate("document.querySelector('#example').setView({ freeze: 0 })")
    CTX.frames(page, 3)
    loose = lefts()
    sel = box(page, f"{V} tbody tr.dv-row:first-child td.dv-selcol")
    check("table: freeze 1 (the default) keeps the first data column put while the table scrolls sideways; freeze 0 lets it scroll",
          frozen[0] == frozen[1] and loose[1] <= loose[0] - 250 and sel["width"] > 0,
          {"freeze 1 (before, after)": frozen, "freeze 0 (before, after)": loose})
    # WHY form, not model: beside the checkboxes the name column is never drawn under 120 px (CONTRACT §15 note, a
    # narrow table), so a squeezed column to wrap is another one
    page.evaluate("document.querySelector('#example').setView({ freeze: 1, columnSize: { form: 60 } })")
    CTX.frames(page, 3)
    cell = f"{V} tbody tr.dv-row:first-child td[data-col=form]"
    clipped = box(page, cell)["height"]
    page.evaluate("document.querySelector('#example').setView({ wrap: true })")
    CTX.frames(page, 3)
    wrapped = box(page, cell)["height"]
    pad = page.evaluate("[...document.querySelectorAll('#example tbody tr.dv-row')].slice(0, 6).map((tr) => Math.round(tr.getBoundingClientRect().height))")
    check("table: wrap makes a long cell's row grow (its text wraps instead of ending in …), and the rows below follow it",
          clipped <= 31 and wrapped > clipped + 8, {"before": clipped, "wrapped": wrapped, "first rows": pad})
    page.context.close()


def _still(page):
    """The element's CSS transitions have ended (the search box's width, .18 s), then a painted frame: measured at the
    end state, never mid-way under load (toolbar-bar checks.py still())."""
    CTX.until(page, "() => !document.getAnimations().some((a) => a.playState === 'running' && a.effect && a.effect.target instanceof Element && a.effect.target.closest('#example'))")
    CTX.frames(page, 3)


def phone_checks(ctx, path):
    check = ctx.check
    for dark in (False, True):
        page = ctx.page(path, width=390, height=844, dark=dark, mobile=True)
        # on a phone the one-row bar folds the box to its Search icon (§15 note 2026-10-26): a tap opens it
        icon = page.locator(f"{V} .dv-bar [data-bar=search]")
        if icon.is_visible():
            icon.click()
            CTX.until(page, "() => document.activeElement === document.querySelector('#example .dv-qinput')")
            _still(page)
        page.locator(f"{V} .dv-qinput").click()
        page.keyboard.type("bra")
        _still(page)
        got = page.evaluate("""() => { const s = document.querySelector('#example .dv-suggest').getBoundingClientRect(), q = document.querySelector('#example .dv-qbox').getBoundingClientRect();
          return { sw: document.scrollingElement.scrollWidth, s: [Math.round(s.left), Math.round(s.right), Math.round(s.top), Math.round(s.bottom)], q: [Math.round(q.left), Math.round(q.right)],
            hidden: document.querySelector('#example .dv-suggest').hidden, items: document.querySelectorAll('#example .dv-suggest-item').length }; }""")
        ctx.shot(page, f"toolbar-query-390-{'dark' if dark else 'light'}")
        ok = got["sw"] <= 390 and not got["hidden"] and got["items"] > 0 and got["s"][0] >= 0 and got["s"][1] <= 390 and got["s"][3] <= 844 and got["q"][1] <= 390
        check(f"query at 390 px, {'dark' if dark else 'light'}: no sideways scroll; the box fits and its suggestions open inside the viewport", ok, got)
        page.context.close()
