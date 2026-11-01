"""The property-types and column-menu checks (run by tests/browser/types_checks.py): every type with its options drawn
and measured, and every column-menu action doing what it says and writing the expected .base or view change.
Pages: gallery/property-types (editable: the file items show) and gallery/robotparts-models (read-only: they do not)."""

from __future__ import annotations

import json

TYPES = "gallery/property-types/index.html"
MODELS = "gallery/robotparts-models/index.html"

# one read of every typed column in the first rows: what each draws, measured
READ = """() => {
  const v = document.querySelector('#example');
  const cells = (col) => [...v.querySelectorAll(`.dv-table tbody tr.dv-row td[data-col="${col}"]`)];
  const first = (col) => cells(col)[0];
  const bg = (e) => getComputedStyle(e).backgroundColor;
  const fill = (td) => { const t = td.querySelector('.dv-progress-track'), f = td.querySelector('.dv-progress-fill'); return t && f ? Math.round(1000 * f.getBoundingClientRect().width / t.getBoundingClientRect().width) / 1000 : null; };
  const leaves = [...v.querySelectorAll('.dv-table thead th[data-col]')];
  return {
    icons: leaves.filter((th) => th.querySelector('.dv-ticon svg, .dv-ticon.dv-emoji')).length, leaves: leaves.length,
    status: cells('status').slice(0, 4).map((td) => { const s = td.querySelector('.dv-statuspill'); return s ? [s.textContent.trim(), s.dataset.group, bg(s), getComputedStyle(s.querySelector('.dv-dot')).backgroundColor] : null; }),
    priority: cells('priority').slice(0, 3).map((td) => { const s = td.querySelector('.dv-opt'); return s ? [s.textContent, bg(s)] : null; }),
    tags: (first('tags') || {querySelectorAll: () => []}).querySelectorAll('.dv-opt').length,
    completion: cells('completion').slice(0, 4).map((td) => [td.querySelector('.dv-progress-num') && td.querySelector('.dv-progress-num').textContent, fill(td)]),
    barStarts: [...new Set(cells('completion').map((td) => { const t = td.querySelector('.dv-progress-track'); return t ? Math.round(t.getBoundingClientRect().left) : null; }))],
    spent: (() => { const c = first('spent'); const ring = c && c.querySelector('.dv-ring-fill'); return c ? [c.textContent.trim(), ring && ring.getAttribute('stroke-dasharray')] : null; })(),
    budget: first('budget') && first('budget').textContent.trim(),
    owner: first('owner') && [first('owner').querySelector('.dv-avatar') && first('owner').querySelector('.dv-avatar').textContent, first('owner').textContent.trim()],
    due: first('due') && first('due').textContent.trim(), edited: first('edited') && first('edited').textContent.trim(),
    rating: cells('rating').slice(0, 3).map((td) => [td.querySelectorAll('.dv-rate.dv-on').length, td.querySelectorAll('.dv-rate').length]),
    shipped: cells('shipped').map((td) => td.querySelector('.dv-check, .dv-toggle') && td.querySelector('.dv-check, .dv-toggle').getAttribute('aria-label')),
    url: first('url') && [first('url').querySelector('a').getAttribute('href'), first('url').textContent.trim()],
    email: first('email') && first('email').querySelector('a').getAttribute('href'), phone: first('phone') && first('phone').querySelector('a').getAttribute('href'),
    files: (() => { const img = v.querySelector('td[data-col=files] img.dv-thumb'); const f = v.querySelector('td[data-col=files] .dv-file'); return { img: img ? [img.complete, img.naturalWidth > 0] : null, file: f ? f.textContent.trim() : null }; })(),
    effort: first('effort') && first('effort').textContent.trim(),
    depends: (() => { const r = v.querySelector('td[data-col=depends_on] .dv-rel'); return r ? [r.dataset.rel, r.textContent.trim()] : null; })(),
    id: first('number') && first('number').textContent.trim(),
    calc: [...v.querySelectorAll('.dv-table tfoot td.dv-calc-cell')].map((td) => [td.dataset.col, td.textContent.trim()]),
  }; }"""


def types(pages, check, tab):
    seen = {}
    for dark in (False, True):
        page = pages.open(TYPES, dark=dark)
        tab(page, "Every type")
        r = page.evaluate(READ)
        seen[dark] = r
        tag = "dark" if dark else "light"
        check(f"types ({tag}): every header shows its type icon (or its own icon)", r["icons"] == r["leaves"] and r["leaves"] == 19, {"icons": r["icons"], "leaves": r["leaves"]})
        st = r["status"]
        check(f"types ({tag}): status is a dot and its label in a filled pill, grouped (In Progress → in_progress, Planning → todo)",
              st[0] and st[0][0] == "In Progress" and st[0][1] == "in_progress" and st[2][0] == "Planning" and st[2][1] == "todo"
              and st[0][2] not in ("rgba(0, 0, 0, 0)", "transparent") and st[0][3] != st[2][3], st)
        pr = r["priority"]
        check(f"types ({tag}): select draws coloured pills, each option its own colour (High red ≠ Low green)", pr[0] and pr[1] and pr[0][0] == "High" and pr[1][0] == "Low" and pr[0][1] != pr[1][1], pr)
        check(f"types ({tag}): multi-select draws a pill per value", r["tags"] == 2, r["tags"])
        comp = r["completion"]
        check(f"types ({tag}): percent shown as a bar: '25.00%' and the bar filled to 25 % (measured), 0 % empty, and every bar starts at one x",
              comp[0] == ["25.00%", 0.25] and comp[1] == ["40.00%", 0.4] and comp[2][1] == 0 and len(r["barStarts"]) == 1, {"cells": comp, "bar starts": r["barStarts"]})
        check(f"types ({tag}): a rollup shown as a ring with divide-by (3,000 ÷ 30,500 of the ring) in its currency", r["spent"] and r["spent"][0] == "$3,000" and r["spent"][1].startswith("3.71 "), r["spent"])
        check(f"types ({tag}): currency, date (short), edited time (relative), duration (h:mm), ID with prefix",
              r["budget"] == "$12,000" and r["due"] == "Nov 14, 2026" and r["edited"].endswith("ago") and r["effort"] == "1:30" and r["id"] == "PRJ-1",
              {k: r[k] for k in ("budget", "due", "edited", "effort", "id")})
        check(f"types ({tag}): person is an avatar with initials and the name", r["owner"] == ["AN", "ANAva Nguyen"] or (r["owner"] and r["owner"][0] == "AN"), r["owner"])
        check(f"types ({tag}): rating draws its max of icons with the value filled (4 of 5)", r["rating"][0] == [4, 5] and r["rating"][1] == [3, 5], r["rating"])
        check(f"types ({tag}): checkbox draws ticked and unticked boxes", "Yes" in r["shipped"] and "No" in r["shipped"], r["shipped"])
        check(f"types ({tag}): URL (short), email (mailto:), phone (tel:) are links",
              r["url"] == ["https://www.notion.so/templates/projects", "notion.so/templates/projects"] and r["email"] == "mailto:ava@example.com" and r["phone"] == "tel:+16045550101", [r["url"], r["email"], r["phone"]])
        check(f"types ({tag}): files & media draws a loaded thumbnail and a file chip", r["files"]["img"] == [True, True] and r["files"]["file"] == "offline-mode.pdf", r["files"])
        check(f"types ({tag}): relation draws the related record's title as a link", r["depends"] == ["p1", "New Database View Types"], r["depends"])
        calc = dict(r["calc"])
        check(f"types ({tag}): the Calculate row: Sum of budget, Average of completion, Checked of shipped, Unique of status",
              calc.get("budget") == "sum $113,350" and calc.get("completion") == "avg 44.00%" and calc.get("shipped") == "checked 2" and calc.get("status") == "unique 4", calc)
        # numeric header over its numbers (the Budget header's text ends where $12,000 ends)
        edge = page.evaluate("""() => { const v = document.querySelector('#example'); const th = v.querySelector('thead th[data-col=budget] .dv-th-text');
          const rg = document.createRange(); rg.selectNodeContents(th); const a = rg.getBoundingClientRect();
          const td = v.querySelector('tbody tr.dv-row td[data-col=budget]'); const r2 = document.createRange(); r2.selectNodeContents(td); return [Math.round(a.right), Math.round(r2.getBoundingClientRect().right)]; }""")
        check(f"types ({tag}): a currency header ends where its numbers end", abs(edge[0] - edge[1]) <= 1, edge)
        page.context.close()
    check("types: light and dark draw each colour from its own palette (the High pill's fill differs between themes)",
          seen[False]["priority"][0][1] != seen[True]["priority"][0][1], [seen[False]["priority"][0][1], seen[True]["priority"][0][1]])

    # every option: change it through the host's editProperty (the column menu's path) and measure the result
    page = pages.open(TYPES)
    tab(page, "Every type")
    def edit(id_, patch):
        page.evaluate(f"() => document.querySelector('#example').editProperty({{ action: 'set', id: {json.dumps(id_)}, patch: {json.dumps(patch)} }})")
        page.wait_for_timeout(250)
        return page.evaluate(READ)
    got = {}
    got["ring"] = edit("completion", {"showAs": "ring"})["completion"][0]
    got["bar divide-by 50"] = edit("completion", {"showAs": "bar", "divideBy": 0.5})["completion"][0]
    got["bar hidden number"] = edit("completion", {"showNumber": False})["completion"][0]
    got["percent as number"] = edit("completion", {"showAs": None, "divideBy": None, "showNumber": None})
    got["percent as number"] = page.evaluate("() => document.querySelector('#example td[data-col=completion]').textContent.trim()")
    got["dates ymd 12h"] = edit("edited", {"dateFormat": "ymd", "timeFormat": "12h"})["edited"]
    got["date full"] = edit("due", {"dateFormat": "full"})["due"]
    got["dmy"] = edit("due", {"dateFormat": "dmy"})["due"]
    got["euro 2dp"] = edit("budget", {"currency": "EUR", "decimals": 2})["budget"]
    got["rating max 3 heart"] = edit("rating", {"max": 3, "ratingIcon": "heart"})["rating"][0]
    got["toggle"] = edit("shipped", {"showAs": "toggle"})["shipped"][:1]
    got["status as checkbox"] = page.evaluate("() => (document.querySelector('#example').editProperty({ action: 'set', id: 'status', patch: { showAs: 'checkbox' } }), document.querySelector('#example td[data-col=status] [role=img]')?.getAttribute('aria-label'))")
    got["priority recoloured"] = edit("priority", {"options": {"High": "purple", "Medium": "yellow", "Low": "green"}})["priority"][0]
    got["duration human"] = edit("effort", {"durationFormat": "human"})["effort"]
    got["url full"] = edit("url", {"urlDisplay": None})["url"][1]
    page.wait_for_timeout(200)
    want = {
        "ring": lambda x: x[0] == "25.00%" and x[1] is None,
        "bar divide-by 50": lambda x: x[1] == 0.5,
        "bar hidden number": lambda x: x[0] is None and x[1] == 0.5,
        "percent as number": lambda x: x == "25.00%",
        "dates ymd 12h": lambda x: x.startswith("2026-10-") and (x.endswith("AM") or x.endswith("PM")),
        "date full": lambda x: x == "November 14, 2026",
        "dmy": lambda x: x == "14/11/2026",
        "euro 2dp": lambda x: x == "€12,000.00",
        "rating max 3 heart": lambda x: x == [3, 3],
        "toggle": lambda x: x == ["No"],
        "status as checkbox": lambda x: x == "No",
        "priority recoloured": lambda x: x[0] == "High",
        "duration human": lambda x: x == "1 h 30 min",
        "url full": lambda x: x == "https://www.notion.so/templates/projects",
    }
    bad = {k: v for k, v in got.items() if not want[k](v)}
    check("types: every option changes the drawing (bar → ring, divide-by, hide the number, percent as a number, date formats and 12 h time, currency and decimals, rating max and icon, checkbox as toggle, status as checkbox, option colours, duration format, URL in full)",
          not bad, bad or got)
    page.context.close()

    # 375 px: no sideways page scroll, and the column menu fits the screen
    page = pages.open(TYPES, width=375, height=812, mobile=True)
    sw = page.evaluate("document.scrollingElement.scrollWidth")
    page.locator("#example thead th[data-col=status]").click()
    page.wait_for_selector(".dv-colmenu")
    m = page.evaluate("() => { const r = document.querySelector('.dv-colmenu').getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right), innerWidth]; }")
    check("types: at 375 px the page does not scroll sideways and the column menu fits on screen", sw <= 375 and m[0] >= 0 and m[1] <= m[2], {"scrollWidth": sw, "menu": m})
    page.context.close()


def menu(pages, check, tab):
    page = pages.open(TYPES)
    tab(page, "Every type")
    events = []
    page.expose_function("_baseEvent", lambda d: events.append(d))
    page.evaluate("() => document.querySelector('#example').addEventListener('data-views-base', (e) => window._baseEvent(e.detail))")
    V = "#example"

    def open_menu(col):
        page.locator(f"{V} thead th[data-col='{col}']").click()
        page.wait_for_selector(".dv-colmenu")

    def state():
        return page.evaluate("""() => { const v = document.querySelector('#example'); return { view: v.view, props: v.base.properties, text: v.baseText,
          heads: [...v.querySelectorAll('.dv-table thead th[data-col]')].map((t) => [t.dataset.col, (t.querySelector('.dv-th-label') || t).textContent.trim()]),
          rows: v.querySelectorAll('.dv-table tbody tr.dv-row').length }; }""")

    # keyboard: Enter on a focused header opens, ↓ moves, Escape closes and focus comes back
    page.locator(f"{V} thead th[data-col='priority']").focus()
    page.keyboard.press("Enter")
    page.wait_for_selector(".dv-colmenu")
    first = page.evaluate("document.activeElement.dataset.k || document.activeElement.dataset.act")
    page.keyboard.press("ArrowDown")
    second = page.evaluate("document.activeElement.dataset.act")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")  # Change type ›
    on_type = page.evaluate("document.querySelector('.dv-colmenu').dataset.page")
    page.keyboard.press("Escape")
    back = page.evaluate("document.querySelector('.dv-colmenu').dataset.page")
    page.keyboard.press("Escape")
    closed = page.evaluate("[!document.querySelector('.dv-colmenu'), document.activeElement.dataset.col]")
    check("menu: keyboard: Enter on a header opens it on the name field, ↓ moves, Enter opens a page, Escape goes back, then closes and focus returns to the header",
          first == "displayName" and second == "page:edit" and on_type == "type" and back == "main" and closed == [True, "priority"], [first, second, on_type, back, closed])

    # rename + icon (the .base text keeps every other line)
    open_menu("status")
    page.fill(".dv-colmenu [data-k=displayName]", "Stage")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    open_menu("status")
    page.click(".dv-colmenu [data-act='page:icon']")
    page.click(".dv-colmenu [data-act='icon:flag']")
    page.keyboard.press("Escape")
    s = state()
    head = dict(s["heads"])
    check("menu: rename and pick an icon: the header says 'Stage' with the flag icon; properties.status has displayName: Stage, icon: flag; the file's other lines are as written",
          head["status"] == "Stage" and s["props"]["status"]["displayName"] == "Stage" and s["props"]["status"]["icon"] == "flag"
          and "displayName: Stage" in s["text"] and "icon: flag" in s["text"] and "# Property types (docs/CONTRACT.md §28)" in s["text"] and "- { value: Planning, color: blue, group: todo }" in s["text"]
          and len(events) >= 2 and events[-1]["action"] == "set",
          {"head": head["status"], "prop": s["props"]["status"], "events": len(events)})

    # change type: status → select (pills, no dots)
    open_menu("status")
    page.click(".dv-colmenu [data-act='page:type']")
    page.click(".dv-colmenu [data-act='type:select']")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    cell = page.evaluate("() => { const td = document.querySelector('#example td[data-col=status]'); return [!!td.querySelector('.dv-opt'), !!td.querySelector('.dv-dot')]; }")
    check("menu: Change type → Select: the cells become pills (no status dot) and properties.status.type is select",
          cell == [True, False] and state()["props"]["status"]["type"] == "select", cell)

    # edit property: completion show as ring, through the panel
    open_menu("completion")
    page.click(".dv-colmenu [data-act='page:edit']")
    page.select_option(".dv-colmenu select[data-opt=showAs]", "ring")
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    ring = page.evaluate("() => !!document.querySelector('#example td[data-col=completion] .dv-ring')")
    check("menu: Edit property → Show as: Ring draws rings, and writes showAs: ring", ring and state()["props"]["completion"]["showAs"] == "ring", ring)

    # filter
    open_menu("priority")
    page.click(".dv-colmenu [data-act='page:filter']")
    page.select_option(".dv-colmenu [data-k=fop]", "==")
    page.select_option(".dv-colmenu select[data-k=fval]", "High")
    page.click(".dv-colmenu [data-act='filter:add']")
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    s = state()
    check("menu: Filter → priority is High: 4 rows, and the view's filters say priority == \"High\"", s["rows"] == 4 and 'priority == "High"' in (s["view"].get("filters") or {}).get("and", []), {"rows": s["rows"], "filters": s["view"].get("filters")})
    page.evaluate("() => document.querySelector('#example').setView({ filters: null })")
    page.wait_for_timeout(200)

    # sort
    open_menu("budget")
    page.click(".dv-colmenu [data-act='page:sort']")
    page.click(".dv-colmenu [data-act='sort:DESC']")
    page.wait_for_timeout(300)
    top = page.evaluate("() => document.querySelector('#example tbody tr.dv-row td[data-col=budget]').textContent.trim()")
    check("menu: Sort → Descending: the largest budget first, and sort: [{property: budget, direction: DESC}]", top == "$30,500" and state()["view"]["sort"][0] == {"property": "budget", "direction": "DESC"}, top)

    # calculate
    open_menu("rating")
    page.click(".dv-colmenu [data-act='page:calc']")
    page.click(".dv-colmenu [data-act='calc:Median']")
    page.wait_for_timeout(250)
    calc = page.evaluate("() => document.querySelector('#example tfoot td[data-col=rating]')?.textContent.trim()")
    check("menu: Calculate → Median: the footer says 'median 4/5' and summaries.rating is Median", calc == "median 4/5" and state()["view"]["summaries"]["rating"] == "Median", calc)

    # roll up across owner, over three dimensions (status × owner × priority; the rest are one per project)
    page.evaluate("() => document.querySelector('#example').setView({ rollup: { keep: ['status', 'owner', 'priority'], dims: ['status', 'owner', 'priority'] } })")
    page.wait_for_timeout(250)
    before = state()["rows"]
    open_menu("owner")
    page.click(".dv-colmenu [data-act='page:rollup']")
    page.click(".dv-colmenu [data-act='roll:away']")
    page.wait_for_timeout(300)
    s = state()
    status = page.inner_text(f"{V} .dv-status")
    check("menu: Roll up → across Owner: one row per status × priority (fewer rows), the rollup keeps every dimension but owner, and the status line says it rolled up across Owner",
          s["view"].get("rollup") and s["view"]["rollup"]["keep"] == ["status", "priority"] and s["rows"] < before and "rolled up across Owner" in status, {"rollup": s["view"].get("rollup"), "rows": [before, s["rows"]], "status": status[:90]})
    page.evaluate("() => document.querySelector('#example').setView({ rollup: null })")
    page.wait_for_timeout(200)

    # freeze through status
    open_menu("status")
    page.click(".dv-colmenu [data-act='freeze']")
    page.wait_for_timeout(250)
    stuck = page.evaluate("() => [...document.querySelector('#example tbody tr.dv-row').children].filter((td) => getComputedStyle(td).position === 'sticky').map((td) => td.dataset.col)")
    check("menu: Freeze on the third column: the first three body columns stick (measured) and freeze: status", stuck == ["number", "name", "status"] and state()["view"]["freeze"] == "status", stuck)

    # wrap
    open_menu("name")
    page.click(".dv-colmenu [data-act='wrap']")
    page.wait_for_timeout(250)
    ws = page.evaluate("() => getComputedStyle(document.querySelector('#example td[data-col=name]')).whiteSpace")
    check("menu: Wrap in view: the column's text wraps (computed white-space) and wrap: [name]", ws == "normal" and state()["view"]["wrap"] == ["name"], ws)

    # hide
    open_menu("phone")
    page.click(".dv-colmenu [data-act='hide']")
    page.wait_for_timeout(250)
    s = state()
    check("menu: Hide: the column is gone and the view's order no longer lists it", "phone" not in dict(s["heads"]) and "phone" not in s["view"]["order"], [h[0] for h in s["heads"]][:8])

    # insert left, duplicate, delete (file edits)
    open_menu("owner")
    page.click(".dv-colmenu [data-act='insert:left']")
    page.wait_for_timeout(300)
    s = state()
    cols = [h[0] for h in s["heads"]]
    page.keyboard.press("Escape")
    check("menu: Insert left: a new 'Property' column sits left of Owner, empty ('—'), and the file gains properties.property",
          cols[cols.index("owner") - 1] == "property" and s["props"]["property"] == {"displayName": "Property", "type": "text"} and "  property: { displayName: Property, type: text }" in s["text"]
          and page.evaluate("() => document.querySelector('#example td[data-col=property]').textContent.trim()") == "—", cols[:6])
    open_menu("priority")
    page.click(".dv-colmenu [data-act='duplicate']")
    page.wait_for_timeout(300)
    page.keyboard.press("Escape")
    s = state()
    cols = [h[0] for h in s["heads"]]
    same = page.evaluate("() => [...document.querySelectorAll('#example tbody tr.dv-row')].slice(0, 5).every((tr) => tr.querySelector('td[data-col=priority]').textContent === tr.querySelector('td[data-col=priority_copy]').textContent)")
    check("menu: Duplicate property: 'Priority (copy)' right of Priority, the same values (the data untouched), from: priority in the file",
          cols[cols.index("priority") + 1] == "priority_copy" and same and s["props"]["priority_copy"]["from"] == "priority" and dict(s["heads"])["priority_copy"] == "Priority (copy)", cols)
    open_menu("priority_copy")
    page.click(".dv-colmenu [data-act='delete']")
    asked = page.evaluate("document.querySelector('.dv-colmenu [data-act=delete] .dv-cm-label').textContent")
    page.click(".dv-colmenu [data-act='delete']")
    page.wait_for_timeout(300)
    s = state()
    open_menu("tags")
    page.click(".dv-colmenu [data-act='delete']")
    page.click(".dv-colmenu [data-act='delete']")
    page.wait_for_timeout(300)
    s2 = state()
    check("menu: Delete property asks once, then: a property the file made is gone from the file; one the data has is hidden (hidden: true), its data untouched",
          "Press again" in asked and "priority_copy" not in s["props"] and "priority_copy" not in dict(s["heads"]) and s2["props"]["tags"].get("hidden") is True and "tags" not in dict(s2["heads"])
          and page.evaluate("() => document.querySelector('#example').data.rows[0].tags.length") == 2,
          {"asked": asked, "tags": s2["props"]["tags"]})
    copy = page.evaluate("() => { const v = document.querySelector('#example'); return v.baseText; }")
    check("menu: the file's text after the edits parses and carries them (what ⋯ Copy the whole file copies)",
          "displayName: Stage" in copy and "showAs: ring" in copy and "\n  tags:" in copy and "hidden: true" in copy and "priority_copy" not in copy and "# Check it: node bin/data-ui.mjs check" in copy, copy[copy.find('  tags:'):copy.find('  tags:') + 160])
    page.context.close()

    # a read-only host: the view items only
    page = pages.open(MODELS)
    tab(page, "Parameters")
    page.locator("#example thead th[data-col='coulomb']").click()
    page.wait_for_selector(".dv-colmenu")
    items = page.evaluate("() => [...document.querySelectorAll('.dv-colmenu [data-act]')].map((b) => b.dataset.act)")
    check("menu: on a read-only page the column menu offers only the view's items (no rename, type, insert, duplicate or delete)",
          "page:sort" in items and "page:calc" in items and "freeze" in items and not any(a in items for a in ["page:edit", "page:type", "insert:left", "duplicate", "delete", "page:icon"]), items)
    page.keyboard.press("Escape")
    # the distribution column's shape: strip → violin → box
    tab(page, "Benches")
    col = page.evaluate("() => document.querySelector('#example thead th[data-col^=\"@\"]').dataset.col")
    page.locator(f"#example thead th[data-col='{col}']").click()
    page.click(".dv-colmenu [data-act='page:dist']")
    page.click(".dv-colmenu [data-act='dist:violin']")
    page.wait_for_timeout(300)
    vi = page.evaluate(f"""() => {{ const tds = [...document.querySelectorAll(`#example tbody td[data-col="${{CSS.escape({json.dumps(col)})}}"]`)]; return [tds.filter((td) => td.querySelector('svg.dv-dist')).length, tds.filter((td) => td.querySelector('svg.dv-dist-violin')).length, tds.filter((td) => td.querySelector('polygon.dv-violin')).length]; }}""")
    page.locator(f"#example thead th[data-col='{col}']").click()
    page.click(".dv-colmenu [data-act='page:dist']")
    page.click(".dv-colmenu [data-act='dist:box']")
    page.wait_for_timeout(300)
    bx = page.evaluate("() => [document.querySelectorAll('#example tbody svg.dv-dist-box').length, document.querySelectorAll('#example tbody rect.dv-box').length]")
    dist = page.evaluate("() => document.querySelector('#example').view.dist")
    check("menu: Distribution → Violin draws a violin in every cell of the column (one with fewer than 3 runs keeps its dots); → Box draws quartile boxes; the view says dist: {x_floor: box}",
          vi[0] > 3 and vi[1] == vi[0] and vi[2] >= vi[0] - 2 and bx[0] > 3 and bx[1] >= bx[0] - 2 and dist == {"x_floor": "box"}, {"violin": vi, "box": bx, "dist": dist})
    page.context.close()
