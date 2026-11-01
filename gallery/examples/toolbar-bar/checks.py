"""Browser checks for the bar (docs/CONTRACT.md §15; run by tests/browser/checks.py): toolbar="bar" with views="auto",
filters="pills rail", display="panel" and selectable. Every claim is measured in the page (getBoundingClientRect,
scrollWidth, the status line, the URL), never only looked for in the DOM. WHY measured: Zach asked for resizable
panels twice before two releases shipped fixed ones (.claude/feedback.md); the bar's layout claims get the same ruler.

The helpers at the top are shared with the toolbar-notion and toolbar-obsidian cases (they load this file)."""

import pathlib
import re

V = "#example"

# every box the bar's checks read, in one call
BOXES = """() => {
  const box = (sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect();
    return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height, hidden: !!e.closest('[hidden]') || !r.width,
      sw: e.scrollWidth, cw: e.clientWidth }; };
  return { bar: box('#example .dv-bar'), views: box('#example .dv-bar-views'), query: box('#example .dv-bar-query'), tools: box('#example .dv-bar-tools'),
    chip: box('#example .dv-viewchip'), tabs: box('#example .dv-viewtabs'), pills: box('#example .dv-pills'), el: box('#example'),
    settings: box('#example .dv-settings'), handle: box('#example .dv-settings + .dv-splitter'), rail: box('.demo > data-facets'),
    display: box('#example [data-bar=display]'), sw: document.scrollingElement.scrollWidth, iw: innerWidth,
    stored: Object.fromEntries(Object.keys(localStorage).filter((k) => k.startsWith('data-ui/')).map((k) => [k, localStorage.getItem(k)])) };
}"""


def boxes(page):
    return page.evaluate(BOXES)


def status(page):
    return page.inner_text(f"{V} .dv-status")


def rows_shown(page):
    """The rows the filters let through, from the status line: "86 of 1,149 rows" -> 86; a pivot's
    "2 rows × 5 columns · from 311 of 1,149 records" -> 311."""
    s = status(page)
    m = re.search(r"from ([\d,]+) of", s) or re.match(r"\s*([\d,]+) of", s)
    return int(m.group(1).replace(",", "")) if m else -1


CTX = None  # the run's ctx (tests/browser/checks.py): set by run(), and by the cases that load this file


def settle(page):
    """After an action that redraws synchronously (a tick, a click, a key): let the browser paint (ctx.frames), not a
    fixed pause. Where the outcome is asynchronous the checks wait for its state with until() instead."""
    CTX.frames(page, 3)


def until(page, predicate, arg=None):
    """Wait for a state the page reaches (ctx.until); the check that follows reports a miss in its own words."""
    return CTX.until(page, predicate, arg)


STILL = """() => !document.getAnimations().some((a) => a.playState === 'running' && a.effect && a.effect.target instanceof Element && a.effect.target.closest('#example'))"""


def still(page):
    """Wait for the element's CSS transitions to end (document.getAnimations), then a painted frame: a width that
    animates (search="icon"'s box, .18 s) is measured at its end state, never mid-way under load (a 2026-10-26 run
    read the opening box at 88 px)."""
    until(page, STILL)
    settle(page)


def pills(page):
    return page.locator(f"{V} .dv-pills:not([hidden]) .dv-pill").all_inner_texts()


def drag(page, handle, dx):
    x, y = handle["left"] + handle["width"] / 2, handle["top"] + min(120, handle["height"] / 2)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y, steps=12)
    page.mouse.up()
    settle(page)
    return boxes(page)


def open_view_menu(page):
    page.click(f"{V} .dv-viewchip")
    page.wait_for_selector(f"{V} .dv-pop:not([hidden]) .dv-vm-find", timeout=3000)


def narrow_390(ctx, path, check, name, shoot=None):
    """At 390 px, light and dark: the page never scrolls sideways and the bar is one row (§15 note 2026-10-26: it never
    wraps; the query box folds to its icon and the tools to icons and "…" instead), every control inside it."""
    for dark in (False, True):
        page = ctx.page(path, width=390, height=844, mobile=True, dark=dark)
        b = boxes(page)
        r = page.evaluate(ROW)
        ok = (b["sw"] <= 390 and b["bar"]["right"] <= b["el"]["right"] + 0.5 and b["bar"]["height"] <= 50 and r["mids"]
              and max(r["mids"]) - min(r["mids"]) <= 1 and not r["outside"] and not r["clipped"] and b["bar"]["sw"] <= b["bar"]["cw"] + 1)
        check(f"{name} at 390 px ({'dark' if dark else 'light'}): no sideways scroll, the bar is one row with every control on it, none clipped",
              ok, {"scrollWidth": b["sw"], "bar": [round(b["bar"]["width"]), round(b["bar"]["height"])], "spread": r["mids"] and round(max(r["mids"]) - min(r["mids"]), 1), "outside": r["outside"], "clipped": r["clipped"]})
        if shoot:
            ctx.shot(page, f"{shoot}-{'dark' if dark else 'light'}-390")
        page.context.close()


VIEWS_BUTTON = f"{V} .dv-bar-views :is([data-bar=views], [data-bar=more]:not([hidden]))"

def run(ctx, path):
    global CTX
    CTX = ctx
    check = ctx.check

    # ---- at rest: one quiet row; the 10 views don't fit as tabs at 1280, so auto shows the chip
    for dark in (False, True):
        page = ctx.page(path, width=1280, dark=dark)
        b = boxes(page)
        check(f"bar at rest ({'dark' if dark else 'light'}, 1280): one row, no pill row (no filter yet), the old toolbar hidden",
              b["bar"] and b["bar"]["height"] <= 52 and (b["pills"] is None or b["pills"]["hidden"]) and page.locator(f"{V} .dv-head").is_hidden(),
              {"bar height": b["bar"] and round(b["bar"]["height"]), "pills": b["pills"] and b["pills"]["hidden"]})
        ctx.shot(page, f"toolbar-bar-{'dark' if dark else 'light'}-1280")
        page.context.close()

    page = ctx.page(path, width=1280)
    # ---- views="auto" on one row (§15 note 2026-10-26): the tabs are elastic first ("N more" takes what does not fit),
    # and fold to the chip only when even the open tab and "N more" have no room; re-decided as the bar's width changes
    ten = boxes(page)
    more = page.locator(f"{V} .dv-viewtabs [data-bar=more]")
    check("views=auto: the case's 10 views at 1280 px show as the tabs that fit and 'N more…' (not the chip), and the strip does not overflow",
          ten["tabs"] and not ten["tabs"]["hidden"] and (ten["chip"] is None or ten["chip"]["hidden"]) and more.is_visible() and ten["tabs"]["sw"] <= ten["tabs"]["cw"] + 1,
          {"tabs": ten["tabs"] and [ten["tabs"]["sw"], ten["tabs"]["cw"]], "more": more.inner_text() if more.count() else None})
    page.evaluate("(() => { const el = document.querySelector('#example'); el.presets = el.presets.slice(0, 4); })()")
    until(page, "() => document.querySelectorAll('#example .dv-viewtabs [role=tab]').length === 4")
    settle(page)
    four = boxes(page)
    check("views=auto: with four views at 1280 px every one is a tab, no 'N more', and the strip does not overflow",
          four["tabs"] and not four["tabs"]["hidden"] and four["tabs"]["sw"] <= four["tabs"]["cw"] + 1 and (four["chip"] is None or four["chip"]["hidden"])
          and page.locator(f"{V} .dv-viewtabs [role=tab]:visible").count() == 4 and not more.is_visible(),
          {"tabs": four["tabs"] and [four["tabs"]["sw"], four["tabs"]["cw"]], "count": page.locator(f"{V} .dv-viewtabs [role=tab]:visible").count()})
    page.evaluate("(() => { const el = document.querySelector('#example'); el.style.width = '240px'; el.style.justifySelf = 'start'; })()")
    until(page, "() => document.querySelector('#example .dv-viewchip')")
    settle(page)
    narrow = boxes(page)
    check("views=auto: narrowed to a 240 px element (its own width, not the window's) the four views fold into the chip, on the one row",
          narrow["chip"] and not narrow["chip"]["hidden"] and (narrow["tabs"] is None or narrow["tabs"]["hidden"]) and narrow["bar"]["height"] <= 50,
          {"element": round(narrow["el"]["width"]), "bar height": round(narrow["bar"]["height"]), "chip": bool(narrow["chip"] and not narrow["chip"]["hidden"])})
    page.evaluate("(() => { const el = document.querySelector('#example'); el.style.width = ''; })()")
    until(page, "() => document.querySelector('#example .dv-viewtabs')")
    settle(page)
    back = boxes(page)
    check("views=auto: widened again, the tabs come back", back["tabs"] and not back["tabs"]["hidden"], bool(back["tabs"] and not back["tabs"]["hidden"]))
    page.context.close()

    # ---- the view chip's menu: find box, a ✓ on the current view, Add view -> the type grid (the chip pinned: at 1280
    # this case's ten views are tabs and "N more", which opens the same menu)
    page = ctx.page(path, width=1280)
    page.evaluate("document.querySelector('#example').setAttribute('views', 'dropdown')")
    until(page, "() => document.querySelector('#example .dv-viewchip')")
    chip = page.locator(f"{V} .dv-viewchip")
    hover_before = page.evaluate("getComputedStyle(document.querySelector('#example .dv-viewchip .dv-chev')).color")
    chip.hover()
    # the chevron's colour eases in (.12 s): wait for it to change, not for a fixed time
    until(page, "(was) => getComputedStyle(document.querySelector('#example .dv-viewchip .dv-chev')).color !== was", hover_before)
    hover_after = page.evaluate("getComputedStyle(document.querySelector('#example .dv-viewchip .dv-chev')).color")
    check("view chip: the up/down chevron lights on hover (its colour changes)", hover_before != hover_after, [hover_before, hover_after])
    open_view_menu(page)
    all_rows = page.locator(f"{V} .dv-pop .dv-vm-row:visible").count()
    current = page.locator(f"{V} .dv-pop .dv-vm-row.dv-vm-on").get_attribute("data-name")
    has_check = page.locator(f"{V} .dv-pop .dv-vm-row.dv-vm-on .dv-vm-check svg").count() == 1 and page.locator(f"{V} .dv-pop .dv-vm-check svg").count() == 1
    page.fill(f"{V} .dv-pop .dv-vm-find", "brand")
    settle(page)
    found = page.locator(f"{V} .dv-pop .dv-vm-row:visible").all_inner_texts()
    check("view menu: typing in its find box narrows the list ('brand' leaves the three brand views)",
          all_rows == 10 and len(found) == 3 and all("rand" in t for t in found), {"all": all_rows, "brand": found})
    check("view menu: the ✓ sits on the current view, and only there", current == "Rows" and has_check, current)
    ctx.shot(page, "toolbar-bar-view-menu-light-1280")
    page.fill(f"{V} .dv-pop .dv-vm-find", "")
    page.click(f"{V} .dv-pop .dv-vm-add")
    page.wait_for_selector(f"{V} .dv-pop .dv-layouts", timeout=3000)
    grid = page.evaluate(f"[...document.querySelectorAll('{V} .dv-pop .dv-layout')].map((b) => b.textContent.trim())")
    ctx.shot(page, "toolbar-bar-add-view-light-1280")
    page.click(f"{V} .dv-pop .dv-layout[data-type=cards]")
    page.wait_for_function("document.querySelector('#example').dataset.view === 'cards'", timeout=15000)
    settle(page)
    got = page.evaluate("(() => { const el = document.querySelector('#example'); return { view: el.dataset.view, type: el.view.type, name: el.origin.name, kind: el.origin.kind }; })()")
    check("Add view: the grid lists the layouts (Gallery, Board, …); Gallery adds a cards view as a user view and selects it",
          grid[:4] == ["Table", "Gallery", "List", "Board"] and got["view"] == "cards" and got["type"] == "cards" and got["kind"] == "user"
          and page.locator(f"{V} .dv-viewchip .dv-viewchip-name").inner_text().strip() == got["name"], {"grid": grid[:8], **got})
    page.context.close()

    # ---- pills <-> rail <-> URL: one state, both ways
    page = ctx.page(path, width=1280)
    page.check("data-facets input[data-p=brand][data-value=Steadywin]")
    settle(page)
    p1, n1 = pills(page), rows_shown(page)
    check("pills <- rail: ticking Steadywin in the rail shows a 'Brand: Steadywin' pill at once, and the rows narrow to 86",
          len(p1) == 1 and "Brand" in p1[0] and "Steadywin" in p1[0] and n1 == 86, {"pills": p1, "rows": n1})
    page.check("data-facets input[data-p=brand][data-value=KST]")
    settle(page)
    p2, n2 = pills(page), rows_shown(page)
    check("pills <- rail: a second brand joins the same pill ('Brand: Steadywin, KST') and the rows add up (86 + 95)", len(p2) == 1 and "KST" in p2[0] and "Steadywin" in p2[0] and n2 == 86 + 95, {"pills": p2, "rows": n2})
    count_word = page.inner_text(f"{V} [data-bar=menu][data-name=filter]")
    check("pills: the Filter button carries the count", "1" in count_word, count_word)
    search = page.evaluate("location.search")
    ctx.shot(page, "toolbar-bar-pills-light-1280")
    page.reload()
    page.wait_for_selector(f"{V} .dv-status")
    until(page, "() => document.querySelector('data-facets input[type=checkbox]') && document.querySelector('#example .dv-view')")
    settle(page)
    p3 = pills(page)
    check("pills <-> URL: the URL carries ?brand=…, and reloading it restores the pill and the rail",
          "brand=" in search and "Steadywin" in search and p3 == p2 and page.is_checked("data-facets input[data-p=brand][data-value=Steadywin]") and rows_shown(page) == n2,
          {"search": search, "pills": p3, "rows": rows_shown(page)})
    page.click(f"{V} .dv-pill .dv-pill-x")
    settle(page)
    p4, n4 = pills(page), rows_shown(page)
    check("pills -> rail: a pill's ✕ unticks the rail's checkboxes, every row comes back and the URL drops brand=",
          not p4 and n4 == 1149 and not page.is_checked("data-facets input[data-p=brand][data-value=Steadywin]") and not page.is_checked("data-facets input[data-p=brand][data-value=KST]")
          and "brand=" not in page.evaluate("location.search"), {"pills": p4, "rows": n4})
    # a custom clause (one the rail cannot draw) shows verbatim and goes with its ✕
    page.evaluate("document.querySelector('#example').filters = { and: ['peak_torque > 20 || mass < 100'] }")
    settle(page)
    p5, n5 = pills(page), rows_shown(page)
    page.click(f"{V} .dv-pill .dv-pill-x")
    settle(page)
    check("pills: a custom clause shows verbatim as its own pill, and its ✕ removes it", len(p5) == 1 and "peak_torque > 20 || mass < 100" in p5[0] and n5 < 1149 and rows_shown(page) == 1149, {"pills": p5, "rows": n5})

    # ---- the rail toggle: hides and shows <data-facets for=example>, the views take the width, remembered
    a = boxes(page)
    page.click(f"{V} [data-bar=menu][data-name=filter]")
    settle(page)
    b = boxes(page)
    page.reload()
    page.wait_for_selector(f"{V} .dv-status")
    until(page, "() => document.querySelector('data-facets input[type=checkbox]') && document.querySelector('#example .dv-view')")
    settle(page)
    c = boxes(page)
    page.click(f"{V} [data-bar=menu][data-name=filter]")
    settle(page)
    d = boxes(page)
    check("filters=rail: the one Filter button hides the rail, the views widen into its place, the choice survives a reload, and it shows it again",
          not a["rail"]["hidden"] and b["rail"]["hidden"] and b["el"]["width"] > a["el"]["width"] + 150 and c["rail"]["hidden"] and c["stored"].get("data-ui/rail-open/example") == "false"
          and not d["rail"]["hidden"] and abs(d["el"]["width"] - a["el"]["width"]) <= 1,
          {"views": [round(a["el"]["width"]), round(b["el"]["width"]), round(d["el"]["width"])], "stored": c["stored"].get("data-ui/rail-open/example")})
    page.context.close()

    # ---- display="panel": Notion's View settings, a resizable side panel inside the element
    page = ctx.page(path, width=1280)
    page.click(f"{V} [data-bar=display]")
    page.wait_for_selector(f"{V} .dv-settings.dv-settings-panel:not([hidden])", timeout=3000)
    settle(page)
    a = boxes(page)
    rows = page.evaluate(f"[...document.querySelectorAll('{V} .dv-settings .dv-set-row')].map((r) => r.dataset.page || r.dataset.act)")
    # CONTRACT §34 (2026-10-29): View settings ends with Add to dashboard…, a deliberate tenth row ("Display holds everything")
    check("settings panel: Display opens Notion's rows (Layout, Frame, Property visibility, Filter, Sort, Group, Roll up on a table, Copy link, Copy as .base, Add to dashboard…) on the element's right edge at 320 px",
          rows == ["layout", "frame", "properties", "filter", "sort", "group", "rollup", "copy-link", "copy-base", "add-dashboard"] and abs(a["settings"]["width"] - 320) <= 1
          and abs(a["settings"]["right"] - (a["el"]["right"] - 1)) <= 1.5 and a["settings"]["top"] >= a["bar"]["bottom"] - 1, {"rows": rows, "width": round(a["settings"]["width"])})
    ctx.shot(page, "toolbar-bar-settings-light-1280")
    h = a["handle"]
    check("settings panel: it has a drag handle on its left edge", h and not h["hidden"] and abs(h["left"] + h["width"] / 2 - a["settings"]["left"]) <= 1.5,
          {"handle": h and round(h["left"] + h["width"] / 2), "edge": round(a["settings"]["left"])})
    b = drag(page, h, -120)
    check("settings panel: dragging its edge 120 px left widens it by 120 px (getBoundingClientRect)", abs(b["settings"]["width"] - a["settings"]["width"] - 120) <= 2,
          f"{a['settings']['width']:.0f} -> {b['settings']['width']:.0f} px")
    want = round(b["settings"]["width"])
    page.reload()
    page.wait_for_selector(f"{V} .dv-status")
    until(page, "() => document.querySelector('data-facets input[type=checkbox]') && document.querySelector('#example .dv-view')")
    settle(page)
    page.click(f"{V} [data-bar=display]")
    page.wait_for_selector(f"{V} .dv-settings.dv-settings-panel:not([hidden])", timeout=3000)
    settle(page)
    c = boxes(page)
    check("settings panel: the width is remembered across a reload (data-ui/panel-width/settings:example)",
          abs(c["settings"]["width"] - want) <= 1 and "data-ui/panel-width/settings:example" in c["stored"], f"{want} -> {c['settings']['width']:.0f} px")
    e = drag(page, c["handle"], 2000)
    f = drag(page, e["handle"], -3000)
    check("settings panel: min 260 px and max 640 px hold", abs(e["settings"]["width"] - 260) <= 1 and abs(f["settings"]["width"] - 640) <= 1, f"{e['settings']['width']:.0f} / {f['settings']['width']:.0f} px")
    page.locator(f"{V} .dv-settings + .dv-splitter").dblclick()
    settle(page)
    g = boxes(page)
    check("settings panel: a double-click on the handle resets it to 320 px and forgets the stored width",
          abs(g["settings"]["width"] - 320) <= 1 and "data-ui/panel-width/settings:example" not in g["stored"], f"{g['settings']['width']:.0f} px")
    # the sub-pages are the toolbar's own menu bodies, with a ‹ back
    page.click(f"{V} .dv-settings .dv-set-row[data-page=sort]")
    settle(page)
    sub = page.locator(f"{V} .dv-settings [data-add]").count() == 1 and page.locator(f"{V} .dv-settings .dv-set-back").count() == 1
    page.click(f"{V} .dv-settings .dv-set-back")
    settle(page)
    root = page.locator(f"{V} .dv-settings .dv-set-row").count()
    page.click(f"{V} .dv-settings .dv-set-row[data-page=layout]")
    settle(page)
    grid = page.locator(f"{V} .dv-settings .dv-layout").count()
    page.click(f"{V} .dv-settings .dv-layout[data-type=pivot]")
    page.wait_for_function("document.querySelector('#example').dataset.view === 'pivot'", timeout=15000)
    page.wait_for_selector(f"{V} .dv-settings [data-opt]", timeout=5000)
    settle(page)
    opts = page.locator(f"{V} .dv-settings [data-opt]").count()
    on = page.locator(f"{V} .dv-settings .dv-layout.dv-on").get_attribute("data-type")
    check("settings panel: Sort › is the toolbar's Sort menu with a ‹ back; Layout › is the type grid, and picking Pivot there shows the pivot's own options()",
          sub and root == 10 and grid >= 12 and on == "pivot" and opts >= 4, {"sort page": sub, "root rows": root, "grid": grid, "on": on, "options": opts})
    # Escape order: an open menu first, then the panel
    page.locator(VIEWS_BUTTON).first.click()
    settle(page)
    page.keyboard.press("Escape")
    settle(page)
    one = [page.locator(f"{V} .dv-pop").is_visible(), page.locator(f"{V} .dv-settings").is_visible()]
    page.keyboard.press("Escape")
    settle(page)
    two = [page.locator(f"{V} .dv-pop").is_visible(), page.locator(f"{V} .dv-settings").is_visible()]
    check("Escape: closes the open menu first, then the settings panel", one == [False, True] and two == [False, False], {"after one": one, "after two": two})
    page.context.close()

    # ---- display="popover" (Linear's): the same rows in a popover under the button, no side panel
    page = ctx.page(path, width=1280)
    page.evaluate("document.querySelector('#example').setAttribute('display', 'popover')")
    settle(page)
    page.click(f"{V} [data-bar=display]")
    page.wait_for_selector(f"{V} .dv-settings:not([hidden])", timeout=3000)
    settle(page)
    a = boxes(page)
    pop = page.evaluate(f"(() => {{ const s = document.querySelector('{V} .dv-settings'); return [s.classList.contains('dv-settings-pop'), s.classList.contains('dv-settings-panel'), s.querySelectorAll('.dv-set-row').length]; }})()")
    check("display=popover: Display opens a popover under its button with the same rows, not a side panel (and no drag handle)",
          pop[0] and not pop[1] and pop[2] == 10 and a["settings"]["top"] >= a["display"]["bottom"] - 1 and a["settings"]["bottom"] < a["el"]["bottom"]
          and (a["handle"] is None or a["handle"]["hidden"]), {"classes": pop, "top": round(a["settings"]["top"]), "button bottom": round(a["display"]["bottom"])})
    ctx.shot(page, "toolbar-bar-popover-light-1280")
    page.mouse.click(40, 40)
    settle(page)
    check("display=popover: a click outside closes it", not page.locator(f"{V} .dv-settings").is_visible())
    page.context.close()

    # ---- the reader's Frame (CONTRACT §12 frame=, §15 note 2026-10-26): a row in View settings sets the attribute live,
    # remembers the pick per element, and "Reset to page default" forgets it; settings-frame="off" hides the row
    page = ctx.page(path, width=1280)
    host_frame = page.get_attribute(V, "frame")

    def frame_page():
        page.click(f"{V} [data-bar=display]")
        page.wait_for_selector(f"{V} .dv-settings:not([hidden]) .dv-set-row[data-page=frame]", timeout=3000)
        page.click(f"{V} .dv-settings .dv-set-row[data-page=frame]")
        page.wait_for_selector(f"{V} .dv-settings .dv-frame[data-frame=flush]", timeout=3000)

    frame_page()
    listed = page.evaluate(f"[...document.querySelectorAll('{V} .dv-settings .dv-frame')].map((b) => [b.dataset.frame, (b.querySelector('.dv-frame-hint') || {{}}).textContent || ''])")
    page.click(f"{V} .dv-settings .dv-frame[data-frame=flush]")
    settle(page)
    picked = [page.get_attribute(V, "frame"), page.evaluate("(() => { try { return localStorage.getItem('data-ui/frame/example'); } catch { return null; } })()")]
    ctx.shot(page, "toolbar-bar-frame-light-1280")
    page.reload()
    page.wait_for_selector(f"{V} .dv-status")
    until(page, "() => document.querySelector('data-facets input[type=checkbox]') && document.querySelector('#example .dv-view')")
    settle(page)
    again = page.get_attribute(V, "frame")
    frame_page()
    page.click(f"{V} .dv-settings .dv-frame-reset")
    settle(page)
    reset = [page.get_attribute(V, "frame"), page.evaluate("(() => { try { return localStorage.getItem('data-ui/frame/example'); } catch { return 'error'; } })()")]
    # card: docs/CONTRACT.md §43, the seventh frame (frame.js FRAMES)
    check("frame: View settings › Frame lists the seven frames with a hint each; picking flush sets frame='flush' live and remembers it; a reload keeps it; Reset to page default removes it",
          [f for f, _ in listed] == ["boxed", "flush", "tabs", "sheet", "page", "bleed", "card"] and all(len(h) > 10 for _, h in listed)
          and picked[0] == "flush" and picked[1] is not None and "flush" in picked[1] and again == "flush" and reset == [host_frame, None],
          {"listed": [f for f, _ in listed], "picked": picked, "after reload": again, "after reset": reset})
    page.keyboard.press("Escape")
    page.evaluate("document.querySelector('#example').setAttribute('settings-frame', 'off')")
    settle(page)
    page.click(f"{V} [data-bar=display]")
    page.wait_for_selector(f"{V} .dv-settings:not([hidden])", timeout=3000)
    hidden_rows = page.locator(f"{V} .dv-settings .dv-set-row[data-page=frame]").count()
    check("frame: settings-frame='off' hides the Frame row", hidden_rows == 0, hidden_rows)
    page.context.close()

    # ---- keyboard: "/" focuses the table's query box (not the page's header search)
    page = ctx.page(path, width=1280)
    page.mouse.click(5, 300)
    page.keyboard.press("/")
    settle(page)
    focused = page.evaluate("!!document.activeElement.closest('#example .dv-bar-query')")
    check("keyboard: '/' focuses the bar's query box when focus is not in a text field", focused, focused)
    # openMenu by name anchors to the bar's own controls, never to the hidden full toolbar's buttons
    page.keyboard.press("Escape")
    page.evaluate("document.querySelector('#example').openMenu('filter')")
    settle(page)
    anchor = page.locator(f"{V} .dv-bar [data-bar=menu][data-name=filter]").bounding_box()
    menu = page.locator(f"{V} .dv-pop").bounding_box()
    page.keyboard.press("Escape")
    page.evaluate("document.querySelector('#example').openMenu('sort')")
    settle(page)
    sort_page = page.locator(f"{V} .dv-settings:visible .dv-set-body [data-add]").count()
    page.keyboard.press("Escape")
    settle(page)
    check("openMenu: 'filter' opens under the bar's Filter button; 'sort' (no Sort word on this bar) opens View settings at its Sort page",
          menu and abs(menu["y"] - (anchor["y"] + anchor["height"]) - 6) <= 2 and menu["x"] + menu["width"] >= anchor["x"] and sort_page == 1,
          {"menu top - button bottom": menu and round(menu["y"] - anchor["y"] - anchor["height"]), "sort page": sort_page})

    # ---- attributes are live: views="tabs" from script keeps the filters, the view and the query
    page.check("data-facets input[data-p=brand][data-value=Steadywin]")
    settle(page)
    page.evaluate("document.querySelector('#example').selectView('By brand')")
    settle(page)
    before = [rows_shown(page), pills(page), page.evaluate("document.querySelector('#example').origin.name")]
    page.evaluate("document.querySelector('#example').setAttribute('views', 'tabs')")
    settle(page)
    after = [rows_shown(page), pills(page), page.evaluate("document.querySelector('#example').origin.name")]
    tabs = page.locator(f"{V} .dv-viewtabs [role=tab]").count()
    check("live attributes: setting views='tabs' from script draws the tabs and keeps the filter, its pill and the open view",
          tabs >= 1 and before == after and after[0] == 86 and page.locator(f"{V} .dv-viewtabs [aria-selected=true]").inner_text().strip().endswith("By brand"), {"tabs": tabs, "before": before, "after": after})

    # ---- "Show only selected": el._onlySelected narrows the model to the selection; groups and counts follow
    page.evaluate("""(() => { const el = document.querySelector('#example'); el.select(el.model.rows.slice(0, 3).map((r) => r.id)); el._onlySelected = true; el._render(); })()""")
    settle(page)
    st = status(page)
    groups = page.evaluate("document.querySelector('#example').model.groups.map((g) => g.rows.length)")
    check("show only selected: the view narrows to the 3 selected rows, its groups follow, and the status line says so",
          rows_shown(page) == 3 and "showing 3 selected" in st and groups == [3], {"status": st, "groups": groups})
    page.evaluate("(() => { const el = document.querySelector('#example'); el._onlySelected = false; el.clearSelection(); el._render(); })()")
    settle(page)
    check("show only selected: turned off, every filtered row is back", rows_shown(page) == 86, status(page))
    page.context.close()

    narrow_390(ctx, path, check, "toolbar-bar", shoot="toolbar-bar")
    frame_bleed(ctx, path, check)
    label_pills(ctx, path, check)
    bulk_reasons(ctx, path, check)
    with_open_modes(ctx, path, check)
    layout_options(ctx, path, check)
    pinned_panes(ctx, path, check)
    band_rows_reachable(ctx, path, check)
    scroll_selection(ctx, path, check)
    one_filter(ctx, path, check)
    promoted_is_display(ctx, path, check)
    labels_first(ctx, path, check)
    bulk_band(ctx, path, check)
    time_groups_on_the_bar(ctx, check)
    trail_beside_the_bar(ctx, check)
    # a selectable card's check never covers its title (cards with a photo, the placeholder, no image)
    card_titles_clear(ctx, check)
    # View settings' handle under a page frame as the page scrolls (resize.js, main c343fc8)
    settings_handle_scrolls(ctx, check)
    # CONTRACT §16 (explain the data: intro, roll-up) under the bar
    explain_beside_the_bar(ctx, check)
    # Zach's 96.png: a narrow table with open: expand, here and on the actuators' "Expand in place" (robotparts /psu/'s shape)
    narrow_expand(ctx, check, path, "toolbar-bar, open=expand", "(() => { const el = document.querySelector('#example'); el.setAttribute('open', 'expand'); })()")
    # robotparts' shape: frame="bleed", the bar, selectable, and a name column dragged to 64 px (96.png's "Advan…")
    narrow_expand(ctx, check, "gallery/robotparts-actuators/index.html", "robotparts-actuators 'Expand in place', bleed, the bar, selectable, the name dragged to 64 px",
                  "(() => { const el = document.querySelector('#example'); for (const [k, v] of [['frame', 'bleed'], ['toolbar', 'bar'], ['selectable', '']]) el.setAttribute(k, v); el.selectView('Expand in place'); el.setView({ columnSize: { model: 64 } }); })()")
    one_row(ctx, path, check, "toolbar-bar")
    one_row(ctx, path, check, "toolbar-bar", dark=True)
    one_row(ctx, path, check, "toolbar-bar, frame=tabs", frame="tabs")
    one_row(ctx, path, check, "toolbar-bar, record pane open", peek=True, setup="(() => { const el = document.querySelector('#example'); el.select(el.model.rows.slice(0, 2).map((r) => r.id)); })()")


def label_pills(ctx, path, check):
    """robotparts stores slugs and labels them (brand: "steadywin", labels: {steadywin: "Steadywin"}), as lane B's
    label checks do: a pill reads the label, exactly as the rail does, never the stored slug."""
    page = ctx.page(path, width=1280)
    page.evaluate("""() => {
      const el = document.querySelector('#example'), d = el.data, slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-');
      const labels = {};
      for (const r of d.rows) labels[slug(r.brand)] = r.brand;
      el.data = { ...d, properties: { ...d.properties, brand: { ...d.properties.brand, labels } }, rows: d.rows.map((r) => ({ ...r, brand: slug(r.brand) })) };
    }""")
    page.wait_for_selector("data-facets input[data-p=brand][data-value=steadywin]")
    page.check("data-facets input[data-p=brand][data-value=steadywin]")
    page.check("data-facets input[data-p=brand][data-value=kst]")
    settle(page)
    rail = [page.locator(f"data-facets input[data-p=brand][data-value={v}]").locator("xpath=..").locator(".df-label").inner_text().strip() for v in ("steadywin", "kst")]
    got = pills(page)
    check("pills: a labelled property's pill reads the rail's labels ('Brand: Steadywin, KST'), not the stored slugs",
          got == [f"Brand: {', '.join(rail)}"] and rail == ["Steadywin", "KST"], {"pills": got, "rail": rail})
    page.context.close()


# the band under frame="bleed" (CONTRACT §12, the page scrolls the rows): every box read in viewport pixels
BAND = """() => { const v = document.querySelector('#example'); const box = (s) => { const e = v.querySelector(s); if (!e) return null;
  const r = e.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, width: r.width, height: r.height, shown: !e.hidden && r.height > 0 }; };
  return { bar: box(':scope > .dv-bar'), sub: box(':scope > .dv-subbar'), status: box(':scope > .dv-status'), settings: box(':scope > .dv-settings'),
    suggest: box('.dv-suggest'), thead: box('.dv-table thead'), frame: v.getAttribute('frame'), scroll: v.dataset.scroll || null,
    sticky: parseFloat(getComputedStyle(v).getPropertyValue('--dv-sticky-top')) || 0, scrollY, ih: innerHeight,
    barBg: getComputedStyle(v.querySelector(':scope > .dv-bar')).backgroundColor, subtle: getComputedStyle(v).getPropertyValue('--dv-subtle').trim() }; }"""


def header_bottom(page):
    """Where the docs site's own header ends while it sticks (0 when it does not stick): site/site.css sets
    --data-sticky-top to it (CONTRACT §12), so a page frame's bar sticks right under it, not behind it."""
    return page.evaluate("""(() => { const h = document.querySelector('body > header, .top'); if (!h) return 0; const p = getComputedStyle(h).position;
      return p === 'sticky' || p === 'fixed' ? h.getBoundingClientRect().bottom : 0; })()""")


def frame_bleed(ctx, path, check):
    """toolbar="bar" under frame="bleed", picked live from View settings › Frame: the view keeps its filters and its
    selection; scrolled 1,500 px, the bar sticks at the sticky top with the pill / bulk row right under it, then the
    status line; View settings opens right under the stuck bar and stays inside the window."""
    for dark in (False, True):
        page = ctx.page(path, width=1280, dark=dark)
        page.check("data-facets input[data-p=brand][data-value=Steadywin]")
        settle(page)
        page.evaluate("(() => { const el = document.querySelector('#example'); el.select(el.model.rows.slice(0, 2).map((r) => r.id)); })()")
        settle(page)
        before = [rows_shown(page), page.evaluate("document.querySelector('#example').selection.length"), page.evaluate("JSON.stringify(document.querySelector('#example').filters)")]
        page.click(f"{V} [data-bar=display]")
        page.wait_for_selector(f"{V} .dv-settings:not([hidden]) .dv-set-row[data-page=frame]", timeout=3000)
        page.click(f"{V} .dv-settings .dv-set-row[data-page=frame]")
        page.click(f"{V} .dv-settings .dv-frame[data-frame=bleed]")
        page.wait_for_function("document.querySelector('#example').dataset.scroll === 'page'", timeout=5000)
        settle(page)
        after = [rows_shown(page), page.evaluate("document.querySelector('#example').selection.length"), page.evaluate("JSON.stringify(document.querySelector('#example').filters)")]
        if not dark:
            check("frame: the Frame row picks bleed live (data-scroll=page) and the view keeps its filters, rows and selection",
                  after == before and before[0] == 86 and before[1] == 2, {"before": before, "after": after})
        page.keyboard.press("Escape")
        page.keyboard.press("Escape")
        settle(page)
        page.mouse.move(640, 600)
        page.mouse.wheel(0, 1500)
        until(page, "() => scrollY >= 1400")
        settle(page)
        b = page.evaluate(BAND)
        b["header"] = header_bottom(page)
        ok = (b["frame"] == "bleed" and b["scrollY"] >= 1400 and b["header"] > 40 and abs(b["bar"]["top"] - b["header"]) <= 1 and b["sub"]["shown"]
              and abs(b["sub"]["top"] - b["bar"]["bottom"]) <= 1 and abs(b["status"]["top"] - b["sub"]["bottom"]) <= 1
              and b["thead"]["top"] >= b["status"]["bottom"] - 1 and b["barBg"] != "rgba(0, 0, 0, 0)")
        check(f"frame=bleed + bar ({'dark' if dark else 'light'}): scrolled 1,500 px, the bar sticks right under the site's sticky header (site.css --data-sticky-top), the bulk / pill row right under it, then the status line and the column header, on the tinted band",
              ok, {k: (round(v["top"]), round(v["bottom"])) if isinstance(v, dict) and v else v for k, v in b.items() if k in ("bar", "sub", "status", "thead", "scrollY", "sticky", "header", "barBg")})
        ctx.shot(page, f"toolbar-bar-bleed-{'dark' if dark else 'light'}-1280")
        page.click(f"{V} [data-bar=display]")
        page.wait_for_selector(f"{V} .dv-settings:not([hidden])", timeout=3000)
        settle(page)
        s = page.evaluate(BAND)
        if not dark:
            # the band's bottom: the bar, its pill row and (two rows are selected) the bulk band over the column header
            bulk = page.evaluate("(() => { const b = document.querySelector('#example > .dv-bulk'); return b && !b.hidden ? b.getBoundingClientRect().bottom : 0; })()")
            band = max(s["sub"]["bottom"] if s["sub"] and s["sub"]["shown"] else s["bar"]["bottom"], bulk)
            check("frame=bleed + bar: View settings opens right under the stuck band (the bar, its pill row and the bulk band) and is pinned inside the window (as the peek is)",
                  abs(s["settings"]["top"] - band) <= 1.5 and s["sub"]["shown"] and s["settings"]["bottom"] <= s["ih"] + 0.5 and s["settings"]["height"] > 300,
                  {"settings": [round(s["settings"]["top"]), round(s["settings"]["bottom"])], "band bottom": round(band), "bar bottom": round(s["bar"]["bottom"]), "window": s["ih"]})
            ctx.shot(page, "toolbar-bar-bleed-settings-light-1280")
            page.keyboard.press("Escape")
            settle(page)
            page.click(f"{V} .dv-bar-query input")
            page.keyboard.type("bra")
            settle(page)
            q = page.evaluate(BAND)
            check("frame=bleed + bar: the query box's suggestions open right under the stuck bar, above the rows",
                  q["suggest"] and q["suggest"]["shown"] and q["suggest"]["top"] >= q["bar"]["top"] and q["suggest"]["top"] <= q["bar"]["bottom"] + 4
                  and page.evaluate("(() => { const s = document.querySelector('#example .dv-suggest').getBoundingClientRect(); const e = document.elementFromPoint(s.left + 20, s.top + 12); return !!(e && e.closest('.dv-suggest')); })()"),
                  {"suggest top": q["suggest"] and round(q["suggest"]["top"]), "bar": [round(q["bar"]["top"]), round(q["bar"]["bottom"])]})
        page.context.close()
    # a kept pick is put on the element while it starts; frame.js frames it once, so the view is made once, not twice
    made = []
    for kept in (None, "bleed"):
        page = ctx.browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
        page.add_init_script("""(() => { window.__made = 0; const make = document.createElement.bind(document);
          new MutationObserver((list) => { for (const m of list) for (const n of m.addedNodes) if (n.nodeType === 1 && n.classList.contains('dv-view')) window.__made++; })
            .observe(document, { childList: true, subtree: true }); })()""" + (f"; try {{ localStorage.setItem('data-ui/frame/example', '{kept}'); }} catch {{}}" if kept else ""))
        errors = []
        page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
        page.goto(f"{ctx.base}/{path}")
        page.wait_for_selector(f"{V} .dv-view")
        # a second make would come with the view's own draw: wait for that draw, then a few frames more
        page.wait_for_function("() => document.querySelector('#example').dataset.view", timeout=30000)
        page.evaluate("() => new Promise((done) => { let k = 10; const step = () => (k-- ? requestAnimationFrame(step) : done()); step(); })")
        made.append([page.evaluate("window.__made"), page.get_attribute(V, "frame"), page.evaluate("document.querySelector('#example').dataset.scroll || null"), errors[:1]])
        page.context.close()
    check("frame: a kept pick (bleed) is in place from the start and the view is made once, as without one",
          made[0][0] == 1 and made[1][0] == 1 and made[1][1] == "bleed" and made[1][2] == "page" and not made[0][3] and not made[1][3], made)

    page = ctx.page(path, width=390, height=844, mobile=True)
    page.evaluate("document.querySelector('#example').setAttribute('frame', 'bleed')")
    settle(page)
    page.mouse.wheel(0, 1500)
    until(page, "() => scrollY >= 1400")
    settle(page)
    b = page.evaluate(BAND)
    hb = header_bottom(page)
    sw = page.evaluate("document.scrollingElement.scrollWidth")
    check("frame=bleed + bar at 390 px: the two-line bar sticks at the top (the site's header scrolls away on a phone) and the page never scrolls sideways",
          abs(b["bar"]["top"] - hb) <= 1 and abs(b["bar"]["top"] - b["sticky"]) <= 1 and abs(b["status"]["top"] - b["bar"]["bottom"]) <= 1 and sw <= 390,
          {"bar": [round(b["bar"]["top"]), round(b["bar"]["bottom"])], "header bottom": hb, "status top": round(b["status"]["top"]), "scrollWidth": sw})
    ctx.shot(page, "toolbar-bar-bleed-light-390")
    page.context.close()


def bulk_reasons(ctx, path, check):
    """An action out of its min / max range is disabled with the reason in its title, and the reason follows the count:
    at 1 selected 'at least 2', at 5 'at most 4' (the bulk bar's redraw key carried only `disabled`, so it kept the
    first reason)."""
    page = ctx.page(path, width=1280)
    page.evaluate("document.querySelector('#example').actions = [{ id: 'pair', label: 'Compare up to 4', min: 2, max: 4, run() {} }]")
    title = lambda: page.evaluate("(() => { const b = document.querySelector('#example .dv-bulk .dv-bulk-act'); return b ? [b.disabled, b.title] : null; })()")
    page.evaluate("(() => { const el = document.querySelector('#example'); el.select(el.model.rows.slice(0, 1).map((r) => r.id)); })()")
    settle(page)
    one = title()
    page.evaluate("(() => { const el = document.querySelector('#example'); el.select(el.model.rows.slice(0, 5).map((r) => r.id)); })()")
    settle(page)
    five = title()
    page.evaluate("(() => { const el = document.querySelector('#example'); el.select(el.model.rows.slice(0, 3).map((r) => r.id)); })()")
    settle(page)
    three = title()
    check("bulk bar: an action's disabled reason follows the count (1: at least 2; 5: at most 4; 3: enabled)",
          one == [True, "Select at least 2 rows"] and five == [True, "Select at most 4 rows"] and three and three[0] is False, {"1": one, "5": five, "3": three})
    page.context.close()


# the side pane (open modes, CONTRACT §13) and View settings, measured
PANES = """() => { const v = document.querySelector('#example'); const box = (s) => { const e = v.querySelector(s); if (!e || e.hidden) return null;
  const r = e.getBoundingClientRect(); return r.width ? { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width } : null; };
  return { peek: box(':scope > .dv-peek'), settings: box(':scope > .dv-settings'), bar: box(':scope > .dv-bar'), split: v.classList.contains('dv-split'),
    peeked: v.peeked && v.peeked.id, selection: v.selection.length, bulk: !!box(':scope > .dv-bulk') }; }"""


def with_open_modes(ctx, path, check):
    """The bar beside open modes (CONTRACT §13): View settings and the side pane never cover each other (split: side by
    side; an overlay pane: the newer one closes the other); selecting rows works while a record is open; Escape closes
    the settings, then the pane, then the selection; the bar stays usable over expand's bands."""
    # split: the element is at least splitAt (1100 px) wide at a 1600 px window
    page = ctx.page(path, width=1600, height=900)
    page.evaluate("(() => { const el = document.querySelector('#example'); el.openPeek(el.model.rows[2].id); })()")
    until(page, "() => document.querySelector('#example').classList.contains('dv-split')")
    page.click(f"{V} [data-bar=display]")
    page.wait_for_selector(f"{V} .dv-settings:not([hidden])", timeout=3000)
    settle(page)
    a = page.evaluate(PANES)
    check("open modes, split: View settings opens beside the record pane, not over it (their boxes are disjoint), both under the bar",
          a["split"] and a["peek"] and a["settings"] and a["settings"]["right"] <= a["peek"]["left"] + 1 and a["settings"]["top"] >= a["bar"]["bottom"] - 1
          and a["peek"]["top"] >= a["bar"]["bottom"] - 1, {k: a[k] for k in ("peek", "settings", "split")})
    ctx.shot(page, "toolbar-bar-open-split-settings-light-1600")
    # selection while the record is open: two checkboxes, the second with shift
    boxes_ = page.locator(f"{V} tbody tr.dv-row .dv-selbox")
    boxes_.nth(4).click()
    boxes_.nth(6).click(modifiers=["Shift"])
    settle(page)
    b = page.evaluate(PANES)
    check("open modes, split: selecting rows (a checkbox, then shift) works while a record is open; the bulk bar shows and the pane keeps its record",
          b["selection"] == 3 and b["bulk"] and b["peeked"] == a["peeked"] and b["peek"] is not None, {k: b[k] for k in ("selection", "bulk", "peeked")})
    order = []
    for _ in range(3):
        page.keyboard.press("Escape")
        settle(page)
        c = page.evaluate(PANES)
        order.append([bool(c["settings"]), bool(c["peek"]), c["selection"]])
    check("open modes: Escape closes View settings, then the record pane, then clears the selection", order == [[False, True, 3], [False, False, 3], [False, False, 0]], order)
    page.context.close()
    # overlay: at 1280 the element is under splitAt, so the pane covers the list; the newer surface closes the other
    page = ctx.page(path, width=1280)
    page.evaluate("(() => { const el = document.querySelector('#example'); el.openPeek(el.model.rows[2].id); })()")
    until(page, "() => !document.querySelector('#example .dv-peek').hidden")
    page.click(f"{V} [data-bar=display]")
    page.wait_for_selector(f"{V} .dv-settings:not([hidden])", timeout=3000)
    settle(page)
    d = page.evaluate(PANES)
    page.evaluate("(() => { const el = document.querySelector('#example'); el.openPeek(el.model.rows[3].id); })()")
    settle(page)
    e = page.evaluate(PANES)
    check("open modes, overlay: View settings and the overlay pane never cover each other: opening the settings closes the pane, opening a record closes the settings",
          not d["split"] and d["settings"] and d["peek"] is None and e["peek"] and e["settings"] is None, {"settings opened": [bool(d["settings"]), bool(d["peek"])], "record opened": [bool(e["settings"]), bool(e["peek"])]})
    page.context.close()
    # expand under a page frame: a band scrolled under the stuck bar; the bar's controls are still the ones hit
    page = ctx.page(path, width=1280)
    page.evaluate("(() => { const el = document.querySelector('#example'); el.setAttribute('open', 'expand'); el.setAttribute('frame', 'bleed'); })()")
    until(page, "() => document.querySelector('#example').dataset.open === 'expand' && document.querySelector('#example').dataset.scroll === 'page'")
    settle(page)
    page.locator(f"{V} tbody tr.dv-row td[data-col=brand]").nth(3).click()
    until(page, "() => document.querySelector('#example tr.dv-open-band')")
    settle(page)
    # a row's selection checkbox selects; it never toggles that row's band (the click is the selection's, not the record's)
    page.locator(f"{V} tbody tr.dv-row .dv-selbox").nth(6).click()
    settle(page)
    picked = page.evaluate("[document.querySelector('#example').selection.length, document.querySelectorAll('#example tr.dv-open-band').length]")
    check("open modes, expand: a row's selection checkbox selects the row and opens no band (one band, the one opened before)", picked == [1, 1], picked)
    # the bar sticks once the page scrolls, so the band is brought under it in a few steps
    for _ in range(4):
        page.evaluate("(() => { const band = document.querySelector('#example tr.dv-open-band').getBoundingClientRect(); const bar = document.querySelector('#example > .dv-bar').getBoundingClientRect(); scrollBy(0, band.top - bar.top - 10); })()")
        settle(page)
    hit = page.evaluate("""(() => { const v = document.querySelector('#example'), bar = v.querySelector(':scope > .dv-bar').getBoundingClientRect(), band = v.querySelector('tr.dv-open-band').getBoundingClientRect();
      const at = (sel) => { const r = v.querySelector(sel).getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!(e && e.closest(sel)); };
      return { under: band.top < bar.bottom && band.bottom > bar.top, chip: at(':is(.dv-viewchip, .dv-vtab-more:not([hidden]))'), display: at('[data-bar=display]'), query: at('.dv-bar-query input') }; })()""")
    page.locator(VIEWS_BUTTON).first.click()
    menu = page.locator(f"{V} .dv-pop:not([hidden]) .dv-vm-find").count()
    check("open modes, expand under frame=bleed: with a band scrolled under the stuck bar, the bar's chip, query box and Display are still what a click hits, and the chip opens its menu",
          hit["under"] and hit["chip"] and hit["display"] and hit["query"] and menu == 1, {**hit, "menu": menu})
    ctx.shot(page, "toolbar-bar-open-expand-bleed-light-1280")
    page.context.close()


def layout_options(ctx, path, check):
    """Layout settings say what the view does: the Gallery's Image property reads photo (a hidden property the view
    draws), and Max columns shows its number, or 'no cap' while unset."""
    page = ctx.page(path, width=1280)
    page.evaluate("document.querySelector('#example').selectView('Gallery')")
    until(page, "() => document.querySelector('#example').dataset.view === 'cards'")
    page.click(f"{V} [data-bar=display]")
    page.click(f"{V} .dv-settings .dv-set-row[data-page=layout]")
    page.wait_for_selector(f"{V} .dv-settings [data-opt]", timeout=5000)
    settle(page)
    got = page.evaluate("""(() => { const s = document.querySelector('#example .dv-settings'); const opt = (label) => [...s.querySelectorAll('label')].find((l) => l.textContent.trim().startsWith(label));
      const img = opt('Image property'), cols = opt('Max columns');
      return { image: img && img.querySelector('select').value, imageText: img && img.querySelector('select').selectedOptions[0].textContent, cols: cols && (cols.querySelector('output') || {}).textContent }; })()""")
    slider = page.locator(f"{V} .dv-settings label:has-text('Max columns') input[type=range]")
    slider.evaluate("(el) => { el.value = 4; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }")
    settle(page)
    after = page.evaluate("(() => { const l = [...document.querySelectorAll('#example .dv-settings label')].find((x) => x.textContent.trim().startsWith('Max columns')); return [(l.querySelector('output') || {}).textContent, document.querySelector('#example').view.maxColumns]; })()")
    check("layout settings: the Gallery's Image property reads its photo property (hidden from the table, drawn on the cards); Max columns reads 'no cap', then 4 once set",
          got["image"] == "photo" and got["cols"] == "no cap" and after == ["4", 4], {**got, "after": after})
    page.context.close()


def pinned_panes(ctx, path, check):
    """Under frame="bleed" the page scrolls and the pane and the settings panel are fixed to the window; with the
    case's heading above the element, the bar sits well below the scroller's top at scroll 0. Neither may cover the
    bar: each starts at the bar's bottom wherever the bar is (robotparts' report, 2026-10-26: an overlay record pane
    covered Filters, Filter and Display). Measured at scroll 0 and 1,500 px scrolled, light and dark."""
    probe = """(() => { const v = document.querySelector('#example'), bar = v.querySelector(':scope > .dv-bar').getBoundingClientRect();
      const pane = (s) => { const e = v.querySelector(s); if (!e || e.hidden) return null; const r = e.getBoundingClientRect(); return r.width ? Math.round(r.top) : null; };
      const hits = (sel) => { const r = v.querySelector(sel).getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!(e && e.closest(sel)); };
      return { bar: Math.round(bar.bottom), peek: pane(':scope > .dv-peek'), settings: pane(':scope > .dv-settings'), display: hits('[data-bar=display]'),
        filter: hits('[data-bar=menu][data-name=filter]'), split: v.classList.contains('dv-split'), y: Math.round(scrollY) }; })()"""
    for dark in (False, True):
        page = ctx.page(path, width=1280, dark=dark)
        page.evaluate("document.querySelector('#example').setAttribute('frame', 'bleed')")
        until(page, "() => document.querySelector('#example').dataset.scroll === 'page'")
        settle(page)
        page.evaluate("(() => { const el = document.querySelector('#example'); el.openPeek(el.model.rows[1].id); })()")
        until(page, "() => !document.querySelector('#example .dv-peek').hidden")
        settle(page)
        top = page.evaluate(probe)
        page.mouse.move(400, 600)
        page.mouse.wheel(0, 1500)
        until(page, "() => scrollY >= 1400")
        settle(page)
        down = page.evaluate(probe)
        ok = all(not x["split"] and x["peek"] is not None and x["peek"] >= x["bar"] - 1 and x["display"] and x["filter"] for x in (top, down)) and top["bar"] > 200
        check(f"frame=bleed, overlay record pane ({'dark' if dark else 'light'}): at scroll 0 (the bar below the heading) and 1,500 px scrolled, the pane starts at the bar's bottom, and Display and Filter take their clicks",
              ok, {"scroll 0": top, "scrolled": down})
        if not dark:
            ctx.shot(page, "toolbar-bar-bleed-overlay-scrolled-light-1280")
            page.evaluate("scrollTo(0, 0)")
            until(page, "() => scrollY === 0")
            settle(page)
            ctx.shot(page, "toolbar-bar-bleed-overlay-top-light-1280")
            # the settings panel, the same way (it closes the overlay pane: they never cover each other)
            page.click(f"{V} [data-bar=display]")
            page.wait_for_selector(f"{V} .dv-settings:not([hidden])", timeout=3000)
            settle(page)
            s0 = page.evaluate(probe)
            page.mouse.move(400, 600)
            page.mouse.wheel(0, 1500)
            until(page, "() => scrollY >= 1400")
            settle(page)
            s1 = page.evaluate(probe)
            check("frame=bleed, View settings panel: at scroll 0 and 1,500 px scrolled it starts at the bar's bottom, and Display and Filter take their clicks",
                  all(x["settings"] is not None and x["settings"] >= x["bar"] - 1 and x["display"] and x["filter"] for x in (s0, s1)) and s0["bar"] > 200, {"scroll 0": s0, "scrolled": s1})
        page.context.close()


def band_rows_reachable(ctx, path, check):
    """The pinned surfaces start at the bottom of the whole band, not the bar's: with the bulk bar (a selection) or the
    pill row (a filter) showing under the bar, every one of their controls takes its clicks while a record is open in
    the overlay pane, under frame="bleed" with the heading above, at scroll 0 and 1,500 px scrolled; and the band is
    re-measured when that row appears with the pane already open (robotparts on d90f3ba: the pane covered "Open in
    tabs", "Clear selection" and "Show only selected")."""
    probe = """(sel) => { const v = document.querySelector('#example'); const sub = v.querySelector(':scope > .dv-subbar').getBoundingClientRect();
      const peek = v.querySelector(':scope > .dv-peek'), pr = peek && !peek.hidden ? peek.getBoundingClientRect() : null;
      const controls = [...v.querySelectorAll(sel)].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !e.closest('[hidden]'); });
      const missed = controls.filter((e) => { const r = e.getBoundingClientRect(); const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !(hit && (hit === e || e.contains(hit))); })
        .map((e) => (e.textContent || e.getAttribute('aria-label') || e.className).trim().slice(0, 24));
      return { controls: controls.length, missed, sub: [Math.round(sub.top), Math.round(sub.bottom)], pane: pr ? Math.round(pr.top) : null, y: Math.round(scrollY) }; }"""
    page = ctx.page(path, width=1280)
    page.evaluate("document.querySelector('#example').setAttribute('frame', 'bleed')")
    until(page, "() => document.querySelector('#example').dataset.scroll === 'page'")
    page.evaluate("(() => { const el = document.querySelector('#example'); el.openPeek(el.model.rows[1].id); })()")
    until(page, "() => !document.querySelector('#example .dv-peek').hidden")
    settle(page)
    got = {}
    # the bulk bar appears while the pane is open
    page.evaluate("(() => { const el = document.querySelector('#example'); el.select(el.model.rows.slice(0, 3).map((r) => r.id)); })()")
    until(page, "() => !document.querySelector('#example .dv-bulk').hidden")
    settle(page)
    bulk = "#example .dv-bulk :is(button, input, [role=switch])"
    got["bulk, scroll 0"] = page.evaluate(probe, bulk)
    page.mouse.move(400, 600)
    page.mouse.wheel(0, 1500)
    until(page, "() => scrollY >= 1400")
    settle(page)
    got["bulk, scrolled"] = page.evaluate(probe, bulk)
    # then the pill row instead (the selection cleared, a rail pick), still with the pane open
    page.evaluate("(() => { const el = document.querySelector('#example'); el.clearSelection(); el.filters = { and: ['brand == \"Steadywin\"'] }; el.openPeek(el.model.rows[1].id); })()")
    until(page, "() => document.querySelector('#example .dv-pills .dv-pill')")
    settle(page)
    pills = "#example .dv-pills :is(button)"
    got["pills, scrolled"] = page.evaluate(probe, pills)
    page.evaluate("scrollTo(0, 0)")
    until(page, "() => scrollY === 0")
    settle(page)
    got["pills, scroll 0"] = page.evaluate(probe, pills)
    ok = all(g["controls"] >= 3 and not g["missed"] and g["pane"] is not None and g["pane"] >= g["sub"][1] - 1 for g in got.values())
    check("frame=bleed, overlay record pane: with the bulk bar or the pill row under the bar (shown while the pane is open), the pane starts under them and every bulk and pill control takes its click, at scroll 0 and 1,500 px scrolled",
          ok, got)
    ctx.shot(page, "toolbar-bar-bleed-overlay-pills-light-1280")
    page.context.close()


# ---- the bar is ALWAYS one row (§15 note 2026-10-26): it degrades as its own width shrinks, never wraps
WIDTHS = (1440, 1100, 900, 700, 520, 375)
# the priority table (bar.js DEGRADE), as the order in which tools drop their label and then move into "…"
ICON_ORDER = ["properties", "group", "sort", "filter", "display"]
MENU_ORDER = ["reset", "add", "properties", "group", "sort", "save", "filter"]

ROW = """() => { const v = document.querySelector('#example'), bar = v.querySelector(':scope > .dv-bar'), br = bar.getBoundingClientRect();
  const shown = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !e.closest('[hidden]') && getComputedStyle(e).visibility !== 'hidden'; };
  const controls = [...bar.querySelectorAll('button, input')].filter((e) => !e.closest('.dv-suggest, .dv-pop') && shown(e));
  const labels = [...bar.querySelectorAll('.dv-bar-label, .dv-vtab > span:not(.dv-i), .dv-viewchip-name, .dv-vtab-more')].filter(shown);
  return { h: Math.round(br.height * 10) / 10,
    mids: controls.map((e) => { const r = e.getBoundingClientRect(); return Math.round((r.top + r.height / 2) * 10) / 10; }),
    outside: controls.filter((e) => { const r = e.getBoundingClientRect(); return r.left < br.left - 0.5 || r.right > br.right + 0.5 || r.top < br.top - 0.5 || r.bottom > br.bottom + 0.5; }).map((e) => e.getAttribute('aria-label') || e.textContent.trim().slice(0, 20)),
    // a clipped label is a fault, except the open tab's, which shrinks with an ellipsis and keeps its full name as title
    clipped: [...controls, ...labels].filter((e) => e.scrollWidth > e.clientWidth + 1 && !(e.closest('.dv-vtab') && e.closest('.dv-vtab').title === e.closest('.dv-vtab').dataset.name))
      .map((e) => e.getAttribute('aria-label') || e.textContent.trim().slice(0, 20)),
    // + (Add view) counts as a tool: it can move into "…" too
    tools: [...bar.querySelectorAll('[data-tool]')].map((t) => t.dataset.tool).filter((id) => id !== 'overflow' && id !== 'search').concat(bar.querySelector('.dv-bar-views [data-bar=add-view]') ? ['add'] : []),
    visible: [...bar.querySelectorAll('[data-tool]')].filter(shown).map((t) => t.dataset.tool).concat([...bar.querySelectorAll('.dv-bar-views [data-bar=add-view]')].filter(shown).map(() => 'add')),
    iconic: [...bar.querySelectorAll('[data-tool].dv-iconic')].filter(shown).map((t) => t.dataset.tool),
    views: v.querySelector('.dv-bar-views .dv-viewchip') ? (v.querySelector('.dv-viewchip.dv-compact') ? 'compact' : 'chip') : 'tabs',
    sw: document.scrollingElement.scrollWidth }; }"""


def _sized(page, w):
    page.evaluate("""(w) => { const d = document.querySelector('.demo'); d.style.gridTemplateColumns = 'minmax(0, 1fr)';
      const r = d.querySelector('data-facets'); if (r) r.style.display = 'none';
      const el = document.querySelector('#example'); el.style.width = w + 'px'; el.style.justifySelf = 'start'; }""", w)
    until(page, "(w) => Math.abs(document.querySelector('#example').getBoundingClientRect().width - w) < 1", w)
    still(page)


def _overflow(page):
    """Open "…" by keyboard, read its items, walk them with the arrows, close it with Escape."""
    btn = page.locator(f"{V} .dv-bar [data-bar=overflow]")
    if not btn.is_visible():
        return {"items": [], "keys": True}
    btn.focus()
    page.keyboard.press("Enter")
    page.wait_for_selector(f"{V} .dv-pop:not([hidden]) .dv-overflow", timeout=3000)
    items = page.evaluate(f"[...document.querySelectorAll('{V} .dv-pop .dv-overflow [data-run]')].map((b) => b.dataset.run)")
    first = page.evaluate("document.activeElement && document.activeElement.dataset.run")
    page.keyboard.press("ArrowDown")
    second = page.evaluate("document.activeElement && document.activeElement.dataset.run")
    page.keyboard.press("Escape")
    settle(page)
    closed = page.evaluate(f"document.querySelector('{V} .dv-pop').hidden")
    return {"items": items, "keys": first == items[0] and (len(items) < 2 or second == items[1]) and closed}


def one_row(ctx, path, check, name, dark=False, setup=None, frame=None, peek=False):
    """At bar widths 1440, 1100, 900, 700, 520 and 375 px the bar is one row of the same height, every control on it
    (same vertical centre), nothing clipped or cut, every tool reachable (shown, or in "…", opened and walked by keyboard),
    and what is iconised or in "…" grows in the priority table's order as the bar narrows."""
    page = ctx.page(path, width=1700, height=900, dark=dark)
    if frame:
        page.evaluate(f"document.querySelector('#example').setAttribute('frame', '{frame}')")
        settle(page)
    if setup:
        page.evaluate(setup)
        settle(page)
    if peek:
        page.evaluate("(() => { const el = document.querySelector('#example'); el.openPeek(el.model.rows[1].id); })()")
        until(page, "() => !document.querySelector('#example .dv-peek').hidden")
    rows, bad = {}, []
    for w in WIDTHS:
        _sized(page, w)
        r = page.evaluate(ROW)
        r["menu"] = _overflow(page)
        rows[w] = r
        reach = set(r["tools"]) <= set(r["visible"]) | set(r["menu"]["items"])
        if not (r["mids"] and max(r["mids"]) - min(r["mids"]) <= 1 and not r["outside"] and not r["clipped"] and reach and r["menu"]["keys"] and r["sw"] <= 1700):
            bad.append({"w": w, "spread": round(max(r["mids"]) - min(r["mids"]), 1) if r["mids"] else None, "outside": r["outside"], "clipped": r["clipped"],
                        "unreachable": sorted(set(r["tools"]) - set(r["visible"]) - set(r["menu"]["items"])), "keys": r["menu"]["keys"]})
    heights = [rows[w]["h"] for w in WIDTHS]
    # monotonic, in the priority order: each narrower width's iconised / menu set holds the wider one's
    order_ok = True
    for a, b in zip(WIDTHS, WIDTHS[1:]):
        ia, ib = set(rows[a]["iconic"]) | set(rows[a]["menu"]["items"]), set(rows[b]["iconic"]) | set(rows[b]["menu"]["items"])
        ma, mb = set(rows[a]["menu"]["items"]), set(rows[b]["menu"]["items"])
        if not (ia <= ib and ma <= mb):
            order_ok = False
    for w in WIDTHS:
        present = rows[w]["tools"]
        menu = rows[w]["menu"]["items"]
        want_menu = [t for t in MENU_ORDER if t in present][:len(menu)]
        dropped = set(rows[w]["iconic"]) | set(menu)
        want_icon = [t for t in ICON_ORDER if t in present]
        if sorted(menu) != sorted(want_menu) or any(t in dropped and want_icon.index(t) > 0 and want_icon[want_icon.index(t) - 1] not in dropped for t in want_icon):
            order_ok = False
    views = [rows[w]["views"] for w in WIDTHS]
    check(f"one row ({name}{', ' + ('dark' if dark else 'light')}): at bar widths 1440-375 px the bar is one row of one height, every control on it, none clipped or cut, every tool shown or in '…' (opened and walked by keyboard)",
          not bad and max(heights) - min(heights) <= 1 and max(heights) <= 50, {"heights": heights, "bad": bad[:3]})
    check(f"one row ({name}{', ' + ('dark' if dark else 'light')}): as the bar narrows, what is iconised and what is in '…' only grows, in the priority order; the views fold tabs -> chip, never back",
          order_ok and [VIEWS_RANK[x] for x in views] == sorted(VIEWS_RANK[x] for x in views),
          {w: {"icons": rows[w]["iconic"], "menu": rows[w]["menu"]["items"], "views": rows[w]["views"]} for w in WIDTHS})
    if not dark and name == "toolbar-bar":
        for w in WIDTHS:
            _sized(page, w)
            page.locator(f"{V} .dv-bar").screenshot(path=str(ctx_out(ctx) / f"bar-width-after-{w}.png"))
    page.context.close()


VIEWS_RANK = {"tabs": 0, "chip": 1, "compact": 2}


def ctx_out(ctx):
    """tests/browser/checks.py's shots folder (reports/media/phase0 by default), where ctx.shot writes."""
    import sys
    mod = sys.modules.get(ctx.__class__.__module__)
    return getattr(mod, "OUT", None) or pathlib.Path(__file__).resolve().parents[3] / "reports" / "media" / "phase0"


def scroll_selection(ctx, path, check):
    """Keyed virtual rows (main's table: a scroll builds only the rows that come into the window and keeps the rest)
    with a selection: after scrolls down and back, a selection made while scrolled, and a clear while scrolled, every
    drawn row's checkbox, dv-sel class and aria-selected match the element's selection exactly, light and dark."""
    marks = """() => { const v = document.querySelector('#example'), sel = new Set(v.selection);
      const rows = [...v.querySelectorAll('tbody tr.dv-row[data-id]')];
      const wrong = rows.filter((tr) => { const on = sel.has(tr.dataset.id); const box = tr.querySelector('.dv-selbox');
        return !box || box.checked !== on || tr.classList.contains('dv-sel') !== on || tr.getAttribute('aria-selected') !== String(on); }).map((tr) => tr.dataset.id);
      return { drawn: rows.length, checked: rows.filter((tr) => tr.querySelector('.dv-selbox').checked).length, selected: sel.size, wrong }; }"""
    scroll = lambda page, y: page.evaluate("(y) => { const s = document.querySelector('#example .dv-scroll'); s.scrollTop = y; s.dispatchEvent(new Event('scroll')); }", y)
    for dark in (False, True):
        page = ctx.page(path, width=1280, dark=dark)
        boxes_ = page.locator(f"{V} tbody tr.dv-row .dv-selbox")
        boxes_.nth(2).click()
        boxes_.nth(5).click(modifiers=["Shift"])
        settle(page)
        got = {"start": page.evaluate(marks)}
        for name, y in (("down 2,000", 2000), ("up to 300", 300)):
            scroll(page, y)
            settle(page)
            got[name] = page.evaluate(marks)
        # select while scrolled (rows kept across the next scroll and rows built by it), then come back
        scroll(page, 900)
        settle(page)
        page.evaluate("(() => { const el = document.querySelector('#example'); const ids = [...document.querySelectorAll('#example tbody tr.dv-row[data-id]')].slice(3, 6).map((tr) => tr.dataset.id); el.select(ids, { mode: 'add' }); })()")
        settle(page)
        got["added at 900"] = page.evaluate(marks)
        scroll(page, 700)
        settle(page)
        got["back to 700"] = page.evaluate(marks)
        page.evaluate("document.querySelector('#example').clearSelection()")
        settle(page)
        scroll(page, 0)
        settle(page)
        got["cleared, top"] = page.evaluate(marks)
        ok = all(not g["wrong"] and g["drawn"] > 10 for g in got.values()) and got["start"]["selected"] == 4 and got["added at 900"]["selected"] == 7 and got["cleared, top"]["checked"] == 0
        check(f"keyed rows + selection ({'dark' if dark else 'light'}): after scrolls, a selection made while scrolled and a clear, every drawn row's checkbox, dv-sel and aria-selected match the selection",
              ok, got)
        page.context.close()


# ---- Zach's feedback, 2026-10-26 (§15 note "one Filter, promote, labels, the bulk band")
FILTER_ENTRIES = """() => { const bar = document.querySelector('#example > .dv-bar');
  return [...bar.querySelectorAll('[data-bar]')].filter((b) => /filter/i.test((b.getAttribute('aria-label') || '') + ' ' + b.dataset.bar + ' ' + (b.dataset.name || '') + ' ' + b.textContent)
    && !b.closest('.dv-bar-query')).map((b) => b.dataset.bar + ':' + (b.dataset.name || '') + ':' + (b.getAttribute('aria-label') || b.textContent.trim())); }"""


def one_filter(ctx, path, check):
    """"Why do you have Filter twice? Filters and Filter?" One filter entry point on the bar at most, in every combination
    of views, filters and promote; with filters="… rail" it is the Filter button and it shows / hides the rail."""
    page = ctx.page(path, width=1280)
    combos, bad = 0, []
    for views in ("tabs", "dropdown"):
        for filters in (None, "pills", "pills rail", "rail", "expanded", "query-tokens", "query-tokens rail"):
            for promote in (None, "", "filter", "sort group filter properties"):
                page.evaluate("""([v, f, p]) => { const el = document.querySelector('#example'); el.setAttribute('views', v);
                  if (f === null) el.removeAttribute('filters'); else el.setAttribute('filters', f);
                  if (p === null) el.removeAttribute('promote'); else el.setAttribute('promote', p); }""", [views, filters, promote])
                settle(page)
                got = page.evaluate(FILTER_ENTRIES)
                combos += 1
                if len(got) > 1:
                    bad.append({"views": views, "filters": filters, "promote": promote, "entries": got})
    check(f"one Filter: across {combos} combinations of views, filters and promote, the bar never has two filter entry points", not bad and combos == 56, bad[:3])
    # the Filter button drives the rail under filters="pills rail" (the case's own attributes)
    page.evaluate("(() => { const el = document.querySelector('#example'); el.setAttribute('views', 'auto'); el.setAttribute('filters', 'pills rail'); el.removeAttribute('promote'); })()")
    settle(page)
    before = page.evaluate("[document.querySelector('.demo > data-facets').hidden, document.querySelector('#example [data-bar=menu][data-name=filter]').getAttribute('aria-pressed')]")
    page.click(f"{V} [data-bar=menu][data-name=filter]")
    settle(page)
    after = page.evaluate("[document.querySelector('.demo > data-facets').hidden, document.querySelector('#example [data-bar=menu][data-name=filter]').getAttribute('aria-pressed')]")
    check("one Filter: with filters='pills rail' the one Filter button shows and hides the rail (aria-pressed follows)", before == [False, "true"] and after == [True, "false"], {"before": before, "after": after})
    ctx.shot(page, "fb-filter-after-check")
    page.context.close()


def promoted_is_display(ctx, path, check):
    """Display holds everything; a promoted section is the same control: a sort or a filter changed in View settings
    shows on its bar word at once, and one changed from the bar shows in View settings."""
    page = ctx.page(path, width=1280)
    page.evaluate("(() => { const el = document.querySelector('#example'); el.setAttribute('filters', 'pills'); el.setAttribute('promote', 'sort filter'); })()")
    settle(page)
    word = lambda name: page.locator(f"{V} .dv-bar [data-bar=menu][data-name={name}]").inner_text().strip()
    # View settings -> bar: the Sort page's first rule to Mass, a filter expression added on the Filter page
    page.click(f"{V} [data-bar=display]")
    page.click(f"{V} .dv-settings .dv-set-row[data-page=sort]")
    page.select_option(f"{V} .dv-settings .dv-rule select[data-k=p]", "mass")
    settle(page)
    sort_word = word("sort")
    page.click(f"{V} .dv-settings .dv-set-back")
    page.click(f"{V} .dv-settings .dv-set-row[data-page=filter]")
    page.fill(f"{V} .dv-settings input[data-k=expr]", "price < 100")
    page.click(f"{V} .dv-settings [data-addexpr]")
    settle(page)
    filter_word = page.evaluate("document.querySelector('#example .dv-bar [data-name=filter] .dv-bar-count') && document.querySelector('#example .dv-bar [data-name=filter] .dv-bar-count').textContent")
    page.keyboard.press("Escape")
    settle(page)
    # bar -> View settings: the Sort word's menu back to Peak torque; the Filter word's menu removes the view's filter
    page.click(f"{V} .dv-bar [data-bar=menu][data-name=sort]")
    page.select_option(f"{V} .dv-pop .dv-rule select[data-k=p]", "peak_torque")
    settle(page)
    page.keyboard.press("Escape")
    page.click(f"{V} .dv-bar [data-bar=menu][data-name=filter]")
    page.locator(f"{V} .dv-pop [data-del][data-scope=view]").first.click()
    settle(page)
    page.keyboard.press("Escape")
    page.click(f"{V} [data-bar=display]")
    settle(page)
    root = page.evaluate("Object.fromEntries([...document.querySelectorAll('#example .dv-settings .dv-set-row[data-page]')].map((r) => [r.dataset.page, r.querySelector('.dv-set-value').textContent]))")
    check("promote: Display holds everything and a promoted section is the same control (a sort and a filter set in View settings show on the bar words; set from the bar, they show in View settings)",
          sort_word == "Sort: Mass" and filter_word == "1" and root.get("sort") == "Peak torque" and root.get("filter") == "" and word("sort") == "Sort: Peak torque",
          {"sort word after the panel": sort_word, "filter count after the panel": filter_word, "panel after the bar": root, "sort word": word("sort")})
    ctx.shot(page, "fb-display-after-check")
    page.context.close()


def labels_first(ctx, path, check):
    """Labels hide before anything collapses: as the bar narrows 1440 -> 300 px in 20 px steps, the first change is a
    label dropping to its icon; only later does anything move into '…', the search fold or the views fold. And
    labels='icons' has every label off at full width."""
    page = ctx.page(path, width=1700)
    page.evaluate("(() => { const el = document.querySelector('#example'); el.setAttribute('views', 'dropdown'); el.setAttribute('promote', 'sort group filter properties'); })()")
    seq = []
    for w in range(1440, 299, -20):
        _sized(page, w)
        r = page.evaluate(ROW)
        r["menuBtn"] = page.evaluate("(() => { const b = document.querySelector('#example .dv-bar [data-bar=overflow]'); return !!b && !b.hidden; })()")
        r["searchIcon"] = page.evaluate("(() => { const b = document.querySelector('#example .dv-bar [data-bar=search]'); return !!b && !b.hidden; })()")
        seq.append((w, bool(r["iconic"]), r["menuBtn"] or r["searchIcon"] or r["views"] != "chip"))
    first_label = next((w for w, lab, _ in seq if lab), None)
    first_fold = next((w for w, _, fold in seq if fold), None)
    page.evaluate("document.querySelector('#example').setAttribute('labels', 'icons')")
    _sized(page, 1440)
    icons = page.evaluate(ROW)
    check("labels: as the bar narrows the first change is a label dropping to its icon, before anything moves into '…' or folds; labels='icons' has them all off at 1440 px",
          first_label is not None and (first_fold is None or first_fold < first_label) and sorted(icons["iconic"]) == sorted([t for t in icons["visible"] if t in ("sort", "group", "filter", "properties", "display")]) and icons["iconic"],
          {"first label drop at": first_label, "first fold at": first_fold, "labels=icons iconic": icons["iconic"]})
    page.context.close()


BULK_BAND = """() => { const v = document.querySelector('#example'), band = v.querySelector(':scope > .dv-bulk'), head = v.querySelector('.dv-view thead'), bar = v.querySelector(':scope > .dv-bar');
  const r = (e) => { if (!e) return null; const b = e.getBoundingClientRect(); return { top: Math.round(b.top), bottom: Math.round(b.bottom), left: Math.round(b.left), right: Math.round(b.right), h: Math.round(b.height) }; };
  const hb = head && head.getBoundingClientRect(), bb = band && band.getBoundingClientRect();
  const hit = hb && bb ? document.elementFromPoint((Math.max(hb.left, bb.left) + Math.min(hb.right, bb.right, innerWidth)) / 2, hb.top + hb.height / 2) : null;
  const card = v.querySelector('.dv-cards-card');
  return { band: band && !band.hidden ? r(band) : null, head: r(head), covered: !!(hit && hit.closest('.dv-bulk')), card: r(card),
    bandBg: band ? getComputedStyle(band).backgroundColor : null, barBg: getComputedStyle(bar).backgroundColor, elBg: getComputedStyle(v).backgroundColor,
    headBg: head ? getComputedStyle(head.querySelector('th')).backgroundColor : null, only: !!v.querySelector('.dv-bulk .dv-bulk-only'),
    onlyRight: (() => { const o = v.querySelector('.dv-bulk .dv-bulk-only'); return o && band ? Math.round(band.getBoundingClientRect().right - o.getBoundingClientRect().right) : null; })() }; }"""


def bulk_band(ctx, path, check):
    """The bulk bar is Shopify's band: while rows are selected it takes the column header row's place (same top, the
    header covered), tinted apart from both the bar and the header, with "Show only selected" at its right; on the
    gallery it is the same band at the top of the view, the cards below it. Light, dark, 375."""
    for dark, width in ((False, 1280), (True, 1280), (False, 375)):
        page = ctx.page(path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=width < 400)
        page.evaluate("(() => { const el = document.querySelector('#example'); el.select(el.model.rows.slice(0, 3).map((r) => r.id)); })()")
        until(page, "() => !document.querySelector('#example > .dv-bulk').hidden")
        settle(page)
        t = page.evaluate(BULK_BAND)
        bar_bg = t["barBg"] if t["barBg"] not in ("rgba(0, 0, 0, 0)", "transparent") else t["elBg"]
        ok = (t["band"] and t["head"] and abs(t["band"]["top"] - t["head"]["top"]) <= 1 and t["band"]["h"] >= t["head"]["h"] - 1 and t["covered"]
              and t["bandBg"] not in (bar_bg, t["headBg"]) and t["only"])
        check(f"bulk band ({'dark' if dark else 'light'}, {width}): it takes the header row's place (same top, the header covered), tinted apart from the bar and the header, Show only selected on it",
              ok, {k: t[k] for k in ("band", "head", "covered", "bandBg", "headBg", "onlyRight")} | {"barBg": bar_bg})
        if not dark and width == 1280:
            ctx.shot(page, "fb-bulk-after-check")
            page.evaluate("document.querySelector('#example').selectView('Gallery')")
            until(page, "() => document.querySelector('#example .dv-cards-card')")
            settle(page)
            g = page.evaluate(BULK_BAND)
            check("bulk band on the gallery: the same band at the top of the view, the first cards below it",
                  g["band"] and g["card"] and g["card"]["top"] >= g["band"]["bottom"] - 1 and g["bandBg"] == t["bandBg"], {"band": g["band"], "first card": g["card"]})
        page.context.close()



LONG = """() => { const bar = document.querySelector('#example > .dv-bar');
  const shown = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !e.closest('[hidden]') && getComputedStyle(e).visibility !== 'hidden'; };
  const controls = [...bar.querySelectorAll('button, input')].filter((e) => !e.closest('.dv-suggest, .dv-pop') && shown(e));
  const covered = controls.filter((e) => { const r = e.getBoundingClientRect(); const x = Math.min(r.left + r.width / 2, innerWidth - 1), y = r.top + r.height / 2;
    const hit = document.elementFromPoint(x, y); return !(hit && (hit === e || e.contains(hit))); }).map((e) => e.getAttribute('aria-label') || e.textContent.trim().slice(0, 24));
  const outside = controls.filter((e) => { const r = e.getBoundingClientRect(), b = bar.getBoundingClientRect(); return r.left < b.left - 0.5 || r.right > b.right + 0.5; }).map((e) => e.getAttribute('aria-label') || e.textContent.trim().slice(0, 24));
  const tabs = [...bar.querySelectorAll('.dv-viewtabs [data-bar=tab]')].filter(shown).map((t) => t.dataset.name);
  const more = bar.querySelector('[data-bar=more]'), add = bar.querySelector('[data-bar=add-view]');
  return { covered, outside, tabs, more: !!more && shown(more), add: !!add && shown(add), chip: !!bar.querySelector('.dv-viewchip') }; }"""


def long_names(ctx, path, check, views="tabs"):
    """Very long view names (robotparts' Config page: "Defaults at the latest firmware") at bar widths 375 and 320: no
    control of the bar is covered by another (elementFromPoint at each one's centre hits it), nothing sticks out, and
    every view is reachable (a tab, or in "N more"'s menu) as is Add view (+, or in "…")."""
    page = ctx.page(path, width=1280)
    page.evaluate("""(v) => { const el = document.querySelector('#example'); el.setAttribute('views', v);
      el.presets = el.presets.map((x, i) => ({ ...x, name: ['Defaults at the latest firmware', 'Measured on the bench, February', 'Everything the seller lists'][i % 3] + (i > 2 ? ' ' + i : '') })); }""", views)
    until(page, "() => document.querySelector('#example .dv-bar-views').textContent.includes('Defaults')")
    names = page.evaluate("document.querySelector('#example').presets.map((v) => v.name)")
    got = {}
    for w in (375, 320):
        _sized(page, w)
        r = page.evaluate(LONG)
        listed = []
        if r["more"] or r["chip"]:
            page.locator(f"{V} .dv-bar-views :is([data-bar=more], [data-bar=views])").first.click()
            page.wait_for_selector(f"{V} .dv-pop:not([hidden]) .dv-vm-row", timeout=3000)
            listed = page.evaluate(f"[...document.querySelectorAll('{V} .dv-pop .dv-vm-row')].map((r) => r.dataset.name)")
            page.keyboard.press("Escape")
            settle(page)
        menu = _overflow(page)["items"]
        r["reachable"] = sorted(set(r["tabs"]) | set(listed)) == sorted(names)
        r["add reachable"] = r["add"] or "add" in menu or r["chip"]
        got[w] = r
    ok = all(not g["covered"] and not g["outside"] and g["reachable"] and g["add reachable"] for g in got.values())
    check(f"long view names (views={views}) at bar widths 375 and 320: no bar control is covered or sticks out, every view is reachable (a tab or in 'N more'), and so is Add view (+ or in '…')",
          ok, {w: {k: g[k] for k in ("covered", "outside", "tabs", "reachable", "add reachable")} for w, g in got.items()})
    page.context.close()



def time_groups_on_the_bar(ctx, check):
    """Time groups (CONTRACT §14) through the bar: on ml-experiments' "Runs by week" under toolbar="bar" with Group
    promoted, the Group word reads "by week", its menu and View settings' Group page are the same body (both offer
    "Dates by"), and a grain picked in View settings shows on the word."""
    page = ctx.page("gallery/ml-experiments/index.html", width=1280)
    page.evaluate("(() => { const el = document.querySelector('#example'); el.setAttribute('toolbar', 'bar'); el.setAttribute('promote', 'group'); })()")
    until(page, "() => document.querySelector('#example .dv-bar [data-name=group]')")
    page.evaluate("document.querySelector('#example').selectView('Runs by week')")
    until(page, "() => /by week/.test(document.querySelector('#example .dv-bar [data-name=group]').textContent)")
    word = lambda: page.locator(f"{V} .dv-bar [data-bar=menu][data-name=group]").inner_text().strip()
    w1 = word()
    page.click(f"{V} .dv-bar [data-bar=menu][data-name=group]")
    settle(page)
    in_menu = page.evaluate(f"[...document.querySelectorAll('{V} .dv-pop label')].some((l) => l.textContent.trim().startsWith('Dates by'))")
    page.keyboard.press("Escape")
    page.click(f"{V} [data-bar=display]")
    page.click(f"{V} .dv-settings .dv-set-row[data-page=group]")
    settle(page)
    in_panel = page.evaluate(f"[...document.querySelectorAll('{V} .dv-settings .dv-set-body label')].some((l) => l.textContent.trim().startsWith('Dates by'))")
    page.locator(f"{V} .dv-settings .dv-set-body label:has-text('Dates by') select").first.select_option("month")
    settle(page)
    w2 = word()
    check("time groups on the bar: the promoted Group reads 'by week'; its menu and View settings' Group page both offer 'Dates by'; a grain picked in View settings shows on the word",
          "by week" in w1 and in_menu and in_panel and "by month" in w2, {"word": w1, "menu": in_menu, "panel": in_panel, "after": w2})
    page.context.close()


def trail_beside_the_bar(ctx, check):
    """The peek's trail (CONTRACT §14) beside the bar: on rack-wiring under toolbar="bar", following two wires in the
    split pane keeps a 3-crumb trail with the pane under the bar and beside the bulk band (never under it); Escape closes View settings, then steps back along
    the trail, then closes the peek, then clears the selection."""
    page = ctx.page("gallery/rack-wiring/index.html", width=1700, height=900)
    page.evaluate("(() => { const el = document.querySelector('#example'); el.setAttribute('toolbar', 'bar'); el.setAttribute('selectable', ''); })()")
    until(page, "() => document.querySelector('#example .dv-bar [data-bar=display]')")
    page.evaluate("(() => { const el = document.querySelector('#example'); const t = el.presets.find((v) => v.type === 'table'); if (t) el.selectView(t.name); })()")
    until(page, "() => document.querySelector('#example').dataset.view === 'table'")
    page.evaluate("(() => { const el = document.querySelector('#example'); el.select(['psu', 'clamp']); el.openPeek('psu'); })()")
    until(page, "() => !document.querySelector('#example .dv-peek').hidden")
    for to in ("clamp", "xt30_junction"):
        page.click(f"{V} .dv-peek .dv-fields a[data-open-rel='{to}']")
        until(page, "(id) => (document.querySelector('#example .dv-peek .dv-open-rec') || {}).dataset?.id === id", to)
    settle(page)
    got = page.evaluate("""(() => { const v = document.querySelector('#example'), peek = v.querySelector('.dv-peek');
      const crumbs = [...peek.querySelectorAll('.dv-open-trail li')].filter((li) => li.querySelector('button, [aria-current]')).length;
      const band = v._barUi.bandBottom();
      const pb = peek.getBoundingClientRect(), bulk = v.querySelector(':scope > .dv-bulk'), bb = bulk && !bulk.hidden ? bulk.getBoundingClientRect() : null;
      return { crumbs, split: v.classList.contains('dv-split'), paneTop: Math.round(pb.top), paneLeft: Math.round(pb.left), band: Math.round(band),
        bar: Math.round(v.querySelector(':scope > .dv-bar').getBoundingClientRect().bottom), bulkRight: bb && Math.round(bb.right) }; })()""")
    page.click(f"{V} [data-bar=display]")
    page.wait_for_selector(f"{V} .dv-settings:not([hidden])", timeout=3000)
    steps = []
    for _ in range(5):
        page.keyboard.press("Escape")
        settle(page)
        steps.append(page.evaluate("""(() => { const v = document.querySelector('#example'), peek = v.querySelector('.dv-peek'); const s = v.querySelector('.dv-settings');
          return [!!s && !s.hidden, peek.hidden ? null : (peek.querySelector('.dv-open-rec') || {}).dataset?.id || null, v.selection.length]; })()"""))
    check("peek trail beside the bar: following two wires keeps a 3-crumb trail in the split pane, under the bar and beside the bulk band; Escape closes View settings, steps back the trail twice, closes the peek, then clears the selection",
          got["crumbs"] == 3 and got["split"] and got["paneTop"] >= got["bar"] - 1 and got["bulkRight"] is not None and got["bulkRight"] <= got["paneLeft"] + 1
          and steps == [[False, "xt30_junction", 2], [False, "clamp", 2], [False, "psu", 2], [False, None, 2], [False, None, 0]], {"pane": got, "escape steps": steps})
    page.context.close()


NAME_MIN = 120  # px: the name column beside the checkboxes (packages/views/table/src/index.js NAME_MIN)
BOX_MIN = 280  # px: the element's least width (packages/core/styles/base.css)
# What a narrow table shows: the open band (sticky, as wide as the scroll box's visible width), what in it overflows its
# box, whether that has an ellipsis and a title, the name column's width, and the first rows' cells and headers likewise
NARROW = """(() => { const v = document.querySelector('#example'), s = v.querySelector('.dv-stage .dv-scroll');
  const sb = s.getBoundingClientRect(), visL = sb.left + s.clientLeft, visR = visL + s.clientWidth;
  const inn = v.querySelector('tr.dv-open-band .dv-open-bandin'), ib = inn && inn.getBoundingClientRect();
  const r = (x) => Math.round(x);
  const said = (e) => { const t = (e.getAttribute('title') || (e.closest('[title]') || {}).title || '').trim(); return !!t; };
  const clipped = (e) => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible';
  const untold = (e) => clipped(e) && !(getComputedStyle(e).textOverflow === 'ellipsis' && said(e));
  const bad = [], outside = [];
  if (inn) for (const e of inn.querySelectorAll('*')) {
    const b = e.getBoundingClientRect();
    if (b.width && (b.right > ib.right + 1 || b.left < ib.left - 1)) outside.push(e.tagName.toLowerCase() + '.' + e.className + ' ' + r(b.left) + '–' + r(b.right));
    if (untold(e)) bad.push('band ' + e.tagName.toLowerCase() + ' ' + (e.textContent || '').trim().slice(0, 24));
  }
  for (const e of [...v.querySelectorAll('.dv-table thead th .dv-th, .dv-table tbody tr.dv-row:nth-child(-n+8) > td')]) if (untold(e)) bad.push('cell ' + (e.textContent || '').trim().slice(0, 24));
  const sel = v.querySelector('.dv-table thead tr:last-child th.dv-selcol'), name = sel && sel.nextElementSibling;
  return { el: r(v.getBoundingClientRect().width), vis: [r(visL), r(visR)], band: ib && [r(ib.left), r(ib.right)], outside: outside.slice(0, 4), bad: bad.slice(0, 6),
    name: name ? r(name.getBoundingClientRect().width) : null, sel: !!sel, sideways: s.scrollWidth > s.clientWidth + 1 }; })()"""


def narrow_expand(ctx, check, path, label, setup):
    """Zach's 96.png (robotparts /psu/, open: expand, a narrow box): the expand band sticks to the scroll box's visible
    left and width and lays its fields out inside it; nothing in it, the headers or the cells is clipped without an
    ellipsis and a title; the name column beside the checkboxes keeps NAME_MIN; the element keeps BOX_MIN."""
    cases = [(w, dark, None) for w in (1280, 900, 375) for dark in (False, True)] + [(1280, False, 360), (1280, True, 360), (1280, False, 200)]
    for w, dark, squeeze in cases:
        page = ctx.page(path, width=w, dark=dark)
        page.evaluate(setup)
        until(page, "() => document.querySelector('#example .dv-table tbody tr.dv-row')")
        if squeeze:
            # beside the rail, the element squeezed (the host's grid gives it `squeeze` px)
            page.evaluate("""(w) => { const d = document.querySelector('.demo'); d.style.gridTemplateColumns = `auto ${w}px`; }""", squeeze)
            settle(page)
        page.evaluate("""(() => { const v = document.querySelector('#example'); const tr = v.querySelector('.dv-table tbody tr.dv-row[data-id]'); v._open.toggleBand(tr.dataset.id); })()""")
        until(page, "() => { const b = document.querySelector('#example tr.dv-open-band .dv-open-bandin'); return b && b.getBoundingClientRect().height > 40; }")
        settle(page)
        got = page.evaluate(NARROW)
        page.evaluate("(() => { const s = document.querySelector('#example .dv-stage .dv-scroll'); s.scrollLeft = s.scrollWidth; })()")
        settle(page)
        right = page.evaluate(NARROW)
        name = f"{label}, {'dark' if dark else 'light'}, {w}" + (f", squeezed to {squeeze} px beside the rail" if squeeze else "")
        ok = (got["band"] and abs(got["band"][0] - got["vis"][0]) <= 1 and abs(got["band"][1] - got["vis"][1]) <= 1
              and right["band"] and abs(right["band"][0] - right["vis"][0]) <= 1 and abs(right["band"][1] - right["vis"][1]) <= 1
              and not got["outside"] and not got["bad"] and not right["bad"] and got["sel"] and got["name"] >= NAME_MIN and got["el"] >= min(BOX_MIN, w))
        check(f"narrow table ({name}): the expand band spans the scroll box's visible width (scrolled to either end), its fields fit or end in an ellipsis with a title, cells and headers too; the name column beside the checkboxes ≥ {NAME_MIN} px; the element ≥ {BOX_MIN} px",
              ok, {"at the start": got, "scrolled right": {k: right[k] for k in ("vis", "band", "bad")}})
        if squeeze == 360 or (w == 375 and not dark):
            ctx.shot(page, f"{path.split('/')[1]}-narrow-expand-{'dark' if dark else 'light'}-{squeeze or w}")
        page.context.close()


MODELS = "gallery/robotparts-models/index.html"
MODELS_SETUP = "(() => { const el = document.querySelector('#example'); el.setAttribute('toolbar', 'bar'); el.setAttribute('selectable', ''); el.selectView('Leaderboard'); })()"


def explain_beside_the_bar(ctx, check):
    """CONTRACT §16 (explain the data) under the bar: on robotparts-models' Leaderboard (an intro with KPI cards, rolled
    up across actuators) the bar is one row at every width with the intro present; the intro sits under the bar; View
    settings offers Roll up (the old toolbar's button is hidden under the bar) and opens its page; with rows selected,
    View settings and the record pane start under the bar's band (the intro ends it: the bulk band lies over the column
    header below the intro), and the bulk band stops at their left edge, so none of its controls is under them."""
    one_row(ctx, MODELS, check, "robotparts-models, intro and roll-up", setup=MODELS_SETUP)
    BOXES = """(() => { const v = document.querySelector('#example'), r = (s) => { const e = v.querySelector(s); if (!e || e.hidden) return null; const b = e.getBoundingClientRect(); return { top: Math.round(b.top), bottom: Math.round(b.bottom), left: Math.round(b.left), right: Math.round(b.right) }; };
      return { band: Math.round(v._barUi.bandBottom()), bar: r(':scope > .dv-bar'), intro: r('.dv-intro'), bulk: r(':scope > .dv-bulk'), settings: r(':scope > .dv-settings'), pane: r(':scope > .dv-peek'),
        split: v.classList.contains('dv-split'), rollRow: !!v.querySelector('.dv-settings [data-page=rollup]') }; })()"""
    for w in (1280, 900):
        page = ctx.page(MODELS, width=w)
        page.evaluate(MODELS_SETUP)
        until(page, "() => { const i = document.querySelector('#example .dv-intro'); return i && !i.hidden && document.querySelector('#example .dv-intro-cards') && document.querySelector('#example .dv-table tbody tr.dv-row[data-id]'); }")
        settle(page)
        page.evaluate("(() => { const v = document.querySelector('#example'); v.select(v.model.rows.slice(0, 2).map((r) => r.id)); })()")
        until(page, "() => !document.querySelector('#example > .dv-bulk').hidden")
        settle(page)
        page.click(f"{V} [data-bar=display]")
        page.wait_for_selector(f"{V} .dv-settings:not([hidden])", timeout=3000)
        settle(page)
        a = page.evaluate(BOXES)
        page.click(f"{V} .dv-settings [data-page=rollup]")
        page.wait_for_selector(f"{V} .dv-settings [data-dim]", timeout=3000)
        dims = page.evaluate("[...document.querySelectorAll('#example .dv-settings [data-dim]')].map((c) => [c.dataset.dim, c.checked])")
        page.keyboard.press("Escape")
        settle(page)
        page.locator(f"{V} tbody tr.dv-row").nth(2).locator("td").nth(3).click()
        until(page, "() => !document.querySelector('#example .dv-peek').hidden")
        settle(page)
        b = page.evaluate(BOXES)
        under = lambda box, band: box and band - 1 <= box["top"] <= band + 1
        ok = (a["bar"]["bottom"] - a["bar"]["top"] <= 50 and a["intro"]["top"] >= a["bar"]["bottom"] - 1 and a["band"] == a["bar"]["bottom"]
              and under(a["settings"], a["band"]) and a["bulk"]["right"] <= a["settings"]["left"] + 1 and a["rollRow"] and dims and ["actuator", False] in dims
              and (b["split"] or (under(b["pane"], b["band"]) and b["bulk"]["right"] <= b["pane"]["left"] + 1)))
        check(f"explain the data under the bar ({w}): the intro sits under the one-row bar; View settings and the record pane start right under the bar, the bulk band (below the intro) stops at their left edge; View settings offers Roll up, its page lists the dimensions with actuator rolled away",
              ok, {"settings open": a, "dims": dims, "pane open": b})
        if w == 1280:
            ctx.shot(page, "toolbar-bar-explain-light-1280")
        page.context.close()


SETTINGS_EDGE = """(() => { const v = document.querySelector('#example'), s = v.querySelector(':scope > .dv-settings'), h = v.querySelector(':scope > .dv-settings + .dv-splitter');
  const a = s.getBoundingClientRect(), b = h.getBoundingClientRect();
  return { y: Math.round(scrollY), left: a.left, top: a.top, height: a.height, width: a.width, handle: b.left + b.width / 2, handleTop: b.top, handleH: b.height, hidden: h.hidden }; })()"""


def settings_handle_scrolls(ctx, check):
    """View settings' drag handle (core resize.js makeResizable) under frame="page|bleed" and the bar: the panel is
    fixed to the window and follows the band as the page scrolls, and the handle stays on its left edge (main c343fc8
    re-places a handle on scroll), at the panel's top and height; dragged there, the panel widens by what was dragged."""
    for frame in ("page", "bleed"):
        page = ctx.page("gallery/toolbar-bar/index.html", width=1280, height=900)
        page.evaluate(f"(() => {{ document.querySelector('#example').setAttribute('frame', '{frame}'); localStorage.removeItem('data-ui/panel-width/settings:example'); }})()")
        until(page, "() => document.querySelector('#example').dataset.scroll === 'page' && document.querySelector('#example .dv-view')")
        settle(page)
        page.click(f"{V} [data-bar=display]")
        page.wait_for_selector(f"{V} .dv-settings.dv-settings-panel:not([hidden])", timeout=3000)
        settle(page)
        at = []
        for y in (500, 1400, 200):
            page.evaluate(f"scrollTo(0, {y})")
            settle(page)
            at.append(page.evaluate(SETTINGS_EDGE))
        s = at[-1]
        page.mouse.move(s["handle"], s["top"] + 40)
        page.mouse.down()
        page.mouse.move(s["handle"] - 60, s["top"] + 40, steps=8)
        page.mouse.up()
        settle(page)
        d = page.evaluate(SETTINGS_EDGE)
        on = lambda x: not x["hidden"] and abs(x["handle"] - x["left"]) <= 1.5 and abs(x["handleTop"] - x["top"]) <= 1.5 and abs(x["handleH"] - x["height"]) <= 1.5
        check(f"settings handle ({frame}): scrolled to 500, 1400 and back to 200 px, View settings' handle stays on the panel's left edge at its top and height, and a drag there widens it by 60 px",
              all(on(x) for x in at) and at[0]["y"] >= 400 and on(d) and abs(d["width"] - s["width"] - 60) <= 2,
              {"scrolls": [{"y": x["y"], "handle-edge": round(x["handle"] - x["left"], 1), "top": round(x["handleTop"] - x["top"], 1), "h": round(x["handleH"] - x["height"], 1)} for x in at],
               "dragged": round(d["width"] - s["width"])})
        page.context.close()


# a selectable card's check (§15, .dv-cards-check: top left, over the image) against its title's text, measured with a
# Range over the title's characters, never the title box (a block as wide as the card)
CARD_CLEAR = """(() => { const v = document.querySelector('#example'); const out = [];
  // the cards in the window (elementFromPoint sees only those), the first 16
  const inView = (c) => { const r = c.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth; };
  for (const c of [...v.querySelectorAll('.dv-cards-card')].filter(inView).slice(0, 16)) {
    const k = c.querySelector('.dv-cards-check'), t = c.querySelector('.dv-cards-title'); if (!k || !t) continue;
    const range = document.createRange(); range.selectNodeContents(t); const tr = range.getBoundingClientRect(), kr = k.getBoundingClientRect();
    if (!tr.width || !kr.width) continue;
    const overlap = kr.left < tr.right && kr.right > tr.left && kr.top < tr.bottom && kr.bottom > tr.top;
    const hit = document.elementFromPoint(tr.left + 2, tr.top + tr.height / 2);
    out.push({ img: !!c.querySelector('.dv-cards-img:not(.dv-cards-noimg)'), placeholder: !!c.querySelector('.dv-cards-noimg'), shown: getComputedStyle(k).opacity === '1',
      check: [Math.round(kr.left), Math.round(kr.right), Math.round(kr.top), Math.round(kr.bottom)], title: [Math.round(tr.left), Math.round(tr.top), Math.round(tr.bottom)],
      clear: !overlap, hit: !!(hit && !hit.closest('.dv-cards-check') && hit.closest('.dv-cards-title')) });
  }
  return out; })()"""


def card_titles_clear(ctx, check):
    """With `selectable`, a card's check never covers its title: on cards with a photo, with the no-photo placeholder,
    and on cards with no image at all (the view's image unset: the check then sits in the title's row), in light and
    dark, at 1280 and 390 px; once a card is selected every check shows, so every card is measured with its check on."""
    for w, dark in ((1280, False), (1280, True), (390, False), (390, True)):
        page = ctx.page("gallery/toolbar-bar/index.html", width=w, height=900 if w > 400 else 844, dark=dark, mobile=w < 400)
        page.evaluate("(() => { const el = document.querySelector('#example'); el.selectView('Gallery'); })()")
        until(page, "() => document.querySelector('#example .dv-cards-card .dv-cards-check')")
        found = {}
        for label, setup in (("with images", "null"), ("no image", "{ image: null }")):
            if setup != "null":
                page.evaluate(f"document.querySelector('#example').setView({setup})")
                until(page, "() => document.querySelector('#example .dv-cards-card') && !document.querySelector('#example .dv-cards-img')")
            page.evaluate("(() => { const v = document.querySelector('#example'); v.clearSelection(); v.select([v.model.rows[0].id]); })()")
            until(page, "() => document.querySelector('#example .dv-cards-card.dv-sel')")
            found[label] = []
            # the first card, then (with images) the first placeholder card, scrolled into the window and measured there
            for first in (".dv-cards-card", ".dv-cards-card:has(.dv-cards-noimg)"):
                if not page.evaluate(f"(() => {{ const c = document.querySelector('#example {first}'); if (c) c.scrollIntoView({{ block: 'center' }}); return !!c; }})()"):
                    continue
                still(page)
                found[label] += page.evaluate(CARD_CLEAR)
            ctx.shot(page, f"toolbar-bar-cards-check-{label.replace(' ', '-')}-{'dark' if dark else 'light'}-{w}")
        kinds = {"photo": any(c["img"] for c in found["with images"]), "bare": bool(found["no image"]) and not any(c["img"] or c["placeholder"] for c in found["no image"])}
        if w > 400:  # at 390 no placeholder card is drawn near the top (virtualised); the placeholder is measured at 1280
            kinds["placeholder"] = any(c["placeholder"] for c in found["with images"])
        bad = [c for cs in found.values() for c in cs if not (c["shown"] and c["clear"] and c["hit"])]
        check(f"cards ({'dark' if dark else 'light'}, {w}): with selectable, no card's check covers its title (the title's text clears the check's box, and its first letters are the title's under the pointer): cards with a photo, with the placeholder and with no image",
              all(kinds.values()) and not bad, {"kinds": kinds, "measured": {k: len(v) for k, v in found.items()}, "bad": bad[:3]})
        page.context.close()
