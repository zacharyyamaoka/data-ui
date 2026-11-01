"""Judge round 2's findings on lane/types (reports/media/audits/2026-10-26-table-headers-judge-r2.md), measured.
Run by tests/browser/types_checks.py: --only=r2 for all of them, or --only=r2:<name> for one."""

from __future__ import annotations

import json
import re

TYPES = "gallery/property-types/index.html"
MODELS = "gallery/robotparts-models/index.html"
REGISTRY = {}


def item(name):
    def wrap(fn):
        REGISTRY[name] = fn
        return fn
    return wrap


@item("exact")
def exact(pages, check, tab):
    """#4: a typed cell's hover and the peek say the stored value exactly."""
    page = pages.open(TYPES)
    tab(page, "Every type")
    got = page.evaluate("""() => { const v = document.querySelector('#example'); const td = (c) => v.querySelector(`tbody tr.dv-row td[data-col=${c}]`);
      const titles = (c) => [td(c).getAttribute('title'), ...[...td(c).querySelectorAll('[title]')].map((e) => e.getAttribute('title'))];
      return { completion: titles('completion'), budget: titles('budget'), due: titles('due'), edited: titles('edited') }; }""")
    stored = page.evaluate("() => { const r = document.querySelector('#example').data.rows[0]; return [r.completion, r.budget, r.due, r.edited]; }")
    # the cell's hover is the stored value; a drawing's own hover (a bar's share) may explain more but must say it too
    ok = got["completion"][0] == "0.25" and got["budget"][0] == "12,000" and got["due"][0] == stored[2] and got["edited"][0] == stored[3] \
        and all(t and t.startswith("0.25") for t in got["completion"][1:]) and all(t and "$" not in t for t in got["budget"])
    check("r2 #4: a typed cell's hover is the stored value exactly (0.25, not 25.00%; 12,000, not $12,000; the ISO date), never the formatted text", ok, {"titles": got, "stored": stored})
    # this page is editable, so a click on the name edits it (§37): the row's Open is the way to the peek (§38)
    page.locator("#example tbody tr.dv-row td[data-col=name] [data-row-open]").first.click()
    page.wait_for_selector("#example .dv-peek:not([hidden])")
    peek = page.evaluate("""() => { const f = (p) => document.querySelector(`#example .dv-peek tr[data-p=${p}] td`); return { budget: f('budget')?.textContent, completion: f('completion')?.textContent, due: f('due')?.textContent }; }""")
    check("r2 #4: the peek (the detail) shows the stored value beside the formatted one ($12,000 · 12,000; 25.00% · 0.25; the ISO date)",
          peek["budget"] and "12,000" in peek["budget"].replace("$12,000", "") and peek["completion"] and "0.25" in peek["completion"] and peek["due"] and stored[2] in peek["due"], peek)
    page.context.close()


@item("yaml")
def yaml_roundtrip(pages, check, tab):
    """#1-#3, #12: the file's text after column-menu edits, read by PyYAML (an independent reader), is the element's
    .base, the preset's new order is in it, every comment of the original is still there; an edit that cannot be
    placed changes nothing."""
    import yaml
    page = pages.open(TYPES)
    tab(page, "Every type")
    events = []
    page.expose_function("_baseEvent", lambda d: events.append(d))
    page.evaluate("() => document.querySelector('#example').addEventListener('data-views-base', (e) => window._baseEvent(e.detail))")
    original = page.evaluate("() => document.querySelector('#example').baseText")
    page.evaluate("""() => { const v = document.querySelector('#example');
      v.editProperty({ action: 'set', id: 'status', patch: { displayName: 'Stage', icon: 'flag' } });
      v.editProperty({ action: 'insert', at: 'owner', side: 'left', type: 'status' });
      v.editProperty({ action: 'duplicate', id: 'priority' });
      v.editProperty({ action: 'set', id: 'completion', patch: { showAs: 'ring', divideBy: null } }); }""")
    page.wait_for_timeout(300)
    st = page.evaluate("() => { const v = document.querySelector('#example'); return { text: v.baseText, base: v.base, view: v.view, index: v.presets.findIndex((p) => p.name === v.view.name) }; }")
    doc = yaml.safe_load(st["text"])
    # every comment, inline ones included (judge r3 #7)
    comments = [l[l.index(" #") + 1:].strip() if " #" in l else l.strip() for l in original.splitlines() if l.strip().startswith("#") or " #" in l]
    lost = [c for c in comments if c not in st["text"]]
    ok = doc["properties"] == st["base"]["properties"] and doc["views"][st["index"]]["order"] == st["view"]["order"] \
        and "property" in doc["views"][st["index"]]["order"] and "priority_copy" in doc["views"][st["index"]]["order"] and not lost \
        and events and events[-1]["text"] == st["text"] and events[2]["order"] == doc["views"][st["index"]]["order"] and events[-1]["order"] is None \
        and events[1]["action"] == "insert" and events[1]["order"] and events[1]["order"].index("property") == events[1]["order"].index("owner") - 1 \
        and {k: v for k, v in doc.items() if k not in ("properties", "views")} == {k: v for k, v in yaml.safe_load(original).items() if k not in ("properties", "views")}
    check("r2 #1-#3, #12: after rename, insert, duplicate and an option edit, PyYAML reads the file's text as exactly the element's properties and the preset's new order; every original comment and other key stays; the event carries that text",
          ok, {"props equal": doc["properties"] == st["base"]["properties"], "order": doc["views"][st["index"]].get("order"), "view order": st["view"]["order"], "lost comments": lost[:3], "events": len(events)})
    # a flow-style properties: mapping with inline and multi-line comments: insert, edit, delete; every comment stays
    flow = ('data: projects.json\nproperties: {  # the properties\n  name: { displayName: Project name },  # the title\n  # status, Notion style\n'
            '  status: { displayName: Status, type: status }  # dot + label\n}  # end of properties\n' + original[original.index('views:'):])
    page.evaluate("(t) => { document.querySelector('#example').baseText = t; }", flow)
    page.evaluate("""() => { const v = document.querySelector('#example');
      v.editProperty({ action: 'insert', at: 'owner', side: 'right', type: 'text' });
      v.editProperty({ action: 'set', id: 'status', patch: { icon: 'flag' } }); }""")
    page.wait_for_timeout(300)
    t2 = page.evaluate("() => document.querySelector('#example').baseText")
    d2 = yaml.safe_load(t2)
    kept = all(c in t2 for c in ["# the properties", "# the title", "# status, Notion style", "# dot + label", "# end of properties"])
    check("r3 #1, #7: a flow-style properties: mapping with inline and multi-line comments takes an insert and an edit; PyYAML reads the edits and every comment stays",
          kept and d2["properties"]["status"].get("icon") == "flag" and any(k.startswith("property") for k in d2["properties"]),
          {"kept": kept, "status": d2["properties"].get("status"), "keys": list(d2["properties"])[:6]})
    refused = page.evaluate("""() => { const v = document.querySelector('#example'); const before = JSON.stringify(v.base.properties); v.baseText = 'properties: [\\n';
      try { v.editProperty({ action: 'set', id: 'owner', patch: { icon: 'user' } }); return { threw: false }; } catch (e) { return { threw: true, msg: e.message, same: JSON.stringify(v.base.properties) === before, text: v.baseText }; } }""")
    check("r2 #1: an edit the file's text cannot take throws, says why, and changes nothing (properties and text as they were)",
          refused.get("threw") and refused.get("same") and refused.get("text") == "properties: [\n", refused)
    page.context.close()


@item("sheet")
def sheet(pages, check, tab):
    """round 1 #1 leftover: frame="sheet" keeps every column divider."""
    import types_checks as T
    bad = {}
    for dark in (False, True):
        page = pages.open(MODELS, frame="sheet", dark=dark)
        for name in ["Parameters · with CI", "What each rung adds · columns"]:
            tab(page, name)
            d = page.evaluate(T.DIVIDERS)
            if d["missing"]:
                bad[f"{name} {'dark' if dark else 'light'}"] = d["missing"][:6]
        page.context.close()
    check("r1 #1 (sheet): frame=\"sheet\" draws a 1 px divider on every cell edge too, light and dark", not bad, bad or None)


# every header text element of the leaves: is it cut (scrollWidth > clientWidth) or outside its cell?
CUT = """() => { const v = document.querySelector('#example'); const out = [];
  for (const th of v.querySelectorAll('.dv-table thead th[data-col]')) { const r = th.getBoundingClientRect();
    for (const e of th.querySelectorAll('.dv-th-label, .dv-unit')) { const b = e.getBoundingClientRect();
      if (e.scrollWidth > e.clientWidth + 1 || b.left < r.left - 0.5 || b.right > r.right + 0.5) out.push([th.dataset.col, e.className, e.textContent, Math.round(b.width), Math.round(r.width)]); } }
  return out; }"""


@item("titles")
def titles(pages, check, tab):
    """round 1 #2 leftover: distribution titles and their (× floor) captions are never cut (Benches, a stats runs column)."""
    cut = {}
    page = pages.open(MODELS)
    for name in ["Benches", "Benches · every actuator", "What each rung adds · columns"]:
        tab(page, name)
        c = page.evaluate(CUT)
        if c:
            cut[name] = c[:5]
    page.context.close()
    check("r1 #2: no distribution title or '(× floor)' caption is cut or leaves its cell (Benches, every actuator, a runs column)", not cut, cut or None)


@item("minw")
def minw(pages, check, tab):
    """round 1 #6 leftover: a column's minimum is measured from its formatted values and its header, not constants."""
    bad = {}
    for path, name in [(MODELS, "Parameters · with CI"), (TYPES, "Every type"), (MODELS, "Benches")]:
        page = pages.open(path)
        tab(page, name)
        page.evaluate("() => { const v = document.querySelector('#example'); const keys = [...v.querySelectorAll('.dv-table thead th[data-col]')].map((t) => t.dataset.col); v.setView({ columnSize: Object.fromEntries(keys.map((k) => [k, 20])) }); }")
        page.wait_for_timeout(400)
        res = page.evaluate("""() => { const v = document.querySelector('#example'); const out = [];
          const right = (td) => td.classList.contains('dv-num') || td.querySelector('.dv-slots');
          for (const td of [...v.querySelectorAll('.dv-table tbody tr.dv-row td[data-col]')].slice(0, 400)) {
            if (!right(td)) continue;
            for (const e of td.querySelectorAll('.dv-v, svg.dv-dist, .dv-c')) { const a = e.getBoundingClientRect(), b = td.getBoundingClientRect(); if (a.width && (a.left < b.left - 0.5 || a.right > b.right + 0.5 || e.scrollWidth > e.clientWidth + 1)) out.push(['cell', td.dataset.col, e.className.baseVal ?? e.className, e.textContent.slice(0, 20)]); }
          }
          return out.slice(0, 8); }""")
        if res:
            bad[name] = {"values cut": res}
        page.context.close()
    # WHY no header text any more (robotparts adopting the kit, 2026-10-31: a source's name made a 603 px column that would not drag): a
    # header's words widen a column nobody has sized, and hold no drag; they end in an ellipsis, whole on hover (CONTRACT §28)
    check("r1 #6: with every column set to 20 px, no number, count or strip is cut: each column's minimum is what it holds", not bad, bad or None)


LONG = "A very long project name that has to wrap over several lines in its cell, and then keeps going well past three lines of text so it must be clamped"


@item("wrap")
def wrap(pages, check, tab):
    """#7, #12: Wrap in view keeps every row at the height the virtualiser placed it at, with long text and many tags."""
    page = pages.open(TYPES)
    tab(page, "Every type")
    page.evaluate(f"""() => {{ const v = document.querySelector('#example'); const d = JSON.parse(JSON.stringify(v.data)); const L = {json.dumps(LONG)};
      d.rows.forEach((r, i) => {{ if (i % 2 === 0) {{ r.name = L; r.tags = ['ai', 'tables', 'web', 'api', 'mobile', 'growth', 'calendar', 'design', 'a11y', 'notes', 'search']; }} }});
      v.data = d; }}""")
    page.wait_for_timeout(300)
    out = {}
    for label, patch in [("tall (default)", {"wrap": ["name", "tags"]}), ("short rows", {"wrap": ["name", "tags"], "rowHeight": "short"}), ("medium rows", {"wrap": ["name", "tags"], "rowHeight": "medium"})]:
        page.evaluate(f"() => document.querySelector('#example').setView({json.dumps(patch)})")
        page.wait_for_timeout(400)
        out[label] = page.evaluate("""() => { const v = document.querySelector('#example'); const rows = [...v.querySelectorAll('.dv-table tbody tr.dv-row')];
          const h = rows.map((r) => Math.round(r.getBoundingClientRect().height * 10) / 10);
          const gaps = rows.slice(1).map((r, i) => Math.round(r.getBoundingClientRect().top - rows[i].getBoundingClientRect().bottom));
          const spill = []; for (const td of v.querySelectorAll('tbody tr.dv-row td.dv-wrapcol')) { const b = td.getBoundingClientRect();
            for (const e of td.querySelectorAll(':scope > *')) { const a = e.getBoundingClientRect(); if (a.bottom > b.bottom + 0.5 || a.top < b.top - 0.5) spill.push([td.dataset.col, Math.round(a.height), Math.round(b.height)]); } }
          return { heights: [...new Set(h)], gaps: [...new Set(gaps)], spill: spill.slice(0, 4), wrapped: v.querySelectorAll('tbody td.dv-wrapcol').length }; }""")
    want = {"tall (default)": 64, "short rows": 30, "medium rows": 44}
    ok = all(o["heights"] == [want[k]] and o["gaps"] in ([0], []) and not o["spill"] and o["wrapped"] > 4 for k, o in out.items())
    check("r2 #7, #12: Wrap in view with long names and eleven tags: every row is exactly its virtual height (64 / 30 / 44 px), rows abut, and no wrapped content leaves its cell (measured)", ok, out)
    page.context.close()


@item("keys")
def keys(pages, check, tab):
    """#8: arrow keys work inside fields; the icon button and the icon grid are reachable by keyboard."""
    page = pages.open(TYPES)
    tab(page, "Every type")
    page.locator("#example thead th[data-col=completion]").focus()
    page.keyboard.press("Enter")
    page.wait_for_selector(".dv-colmenu")
    page.keyboard.press("Shift+Tab")
    icon_btn = page.evaluate("document.activeElement.classList.contains('dv-cm-iconbtn')")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    on_icons = page.evaluate("document.querySelector('.dv-colmenu').dataset.page")
    page.keyboard.press("ArrowDown")
    grid = page.evaluate("document.activeElement.classList.contains('dv-cm-icon') ? document.activeElement.dataset.act : document.activeElement.className")
    page.keyboard.press("Escape")
    page.click(".dv-colmenu [data-act='page:edit']")
    page.focus(".dv-colmenu select[data-opt=showAs]")
    before = page.evaluate("document.querySelector('.dv-colmenu select[data-opt=showAs]').value")
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(300)
    after = page.evaluate("() => { const s = document.querySelector('.dv-colmenu select[data-opt=showAs]'); return [s ? s.value : null, document.activeElement && document.activeElement.dataset.opt]; }")
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    page.locator("#example thead th[data-col=name]").focus()
    page.keyboard.press("Enter")
    page.wait_for_selector(".dv-colmenu")
    page.keyboard.press("ArrowLeft")
    caret = page.evaluate("() => { const i = document.querySelector('.dv-colmenu [data-k=displayName]'); return [document.activeElement === i, i.selectionStart]; }")
    check("r2 #8: the icon button is reachable (Shift+Tab from the name), Enter opens the icons, ↓ moves into the icon grid; ↓ in a select changes it and keeps focus; ← moves the caret in the name field",
          icon_btn and on_icons == "icon" and str(grid).startswith("icon:") and before == "bar" and after[0] == "ring" and after[1] == "showAs" and caret[0] is True,
          {"icon button": icon_btn, "page": on_icons, "grid": grid, "select": [before, after], "caret": caret})
    page.context.close()


@item("clear")
def clear(pages, check, tab):
    """#9: Unfreeze freezes nothing (freeze: false); the last visible column cannot be hidden."""
    page = pages.open(TYPES)
    tab(page, "All")
    page.locator("#example thead th[data-col=name]").click()
    page.wait_for_selector(".dv-colmenu")
    label = page.evaluate("document.querySelector('.dv-colmenu [data-act=freeze] .dv-cm-label').textContent")
    page.click(".dv-colmenu [data-act=freeze]")
    page.wait_for_timeout(300)
    st = page.evaluate("() => { const v = document.querySelector('#example'); return [v.view.freeze, [...v.querySelector('tbody tr.dv-row').children].filter((td) => getComputedStyle(td).position === 'sticky').length]; }")
    page.evaluate("() => document.querySelector('#example').setView({ order: ['name'] })")
    page.wait_for_timeout(300)
    page.locator("#example thead th[data-col=name]").click()
    page.wait_for_selector(".dv-colmenu")
    hide = page.evaluate("() => { const b = document.querySelector('.dv-colmenu [data-act=hide]'); return b ? [b.disabled, b.getAttribute('aria-disabled')] : null; }")
    page.evaluate("() => { const b = document.querySelector('.dv-colmenu [data-act=hide]'); if (b) b.click(); }")
    page.wait_for_timeout(300)
    order = page.evaluate("document.querySelector('#example').view.order")
    check("r2 #9: the first column (frozen by default) offers Unfreeze, which writes freeze: false and leaves no column stuck; the last visible column's Hide is disabled and does nothing",
          label == "Unfreeze" and st == [False, 0] and hide and hide[0] is True and order == ["name"], {"label": label, "after unfreeze": st, "hide": hide, "order": order})
    page.context.close()


CONTRAST = """() => {
  const parse = (c) => { const m = /color\\(srgb ([\\d.e-]+) ([\\d.e-]+) ([\\d.e-]+)(?: \\/ ([\\d.]+))?\\)/.exec(c); if (m) return [+m[1] * 255, +m[2] * 255, +m[3] * 255, m[4] === undefined ? 1 : +m[4]];
const p = /rgba?\\(([^)]+)\\)/.exec(c)[1].split(',').map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const bgOf = (e) => { while (e) { const c = parse(getComputedStyle(e).backgroundColor); if (c[3] > 0.99) return c; e = e.parentElement; } return [255, 255, 255, 1]; };
  const lum = (c) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const out = [];
  for (const u of document.querySelectorAll('#example .dv-table thead .dv-unit')) {
    const fg = parse(getComputedStyle(u).color), bg = bgOf(u.closest('th'));
    const a = lum(fg), b = lum(bg); out.push(Math.round(100 * (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)) / 100);
  }
  return out; }"""


@item("contrast")
def contrast(pages, check, tab):
    """#10, #12: unit captions read at 4.5:1 or better, light and dark, with the kit's stock tokens and with robotparts' skin."""
    got = {}
    for dark in (False, True):
        for skin in (True, False):
            page = pages.open(MODELS, dark=dark)
            if not skin:
                # the kit's stock tokens: the page without robotparts' skin
                page.evaluate("() => document.querySelectorAll('.data-ui-skin').forEach((e) => e.classList.remove('data-ui-skin'))")
                page.wait_for_timeout(200)
            for name in ["Benches", "Parameters · with CI", "Leaderboard"]:
                tab(page, name)
                got[f"{name} {'dark' if dark else 'light'} {'skin' if skin else 'stock'}"] = page.evaluate(CONTRAST)
            page.context.close()
    worst = min(min(v) for v in got.values() if v)
    check("r2 #10, #12: every unit caption in the headers has at least 4.5:1 contrast with its header, light and dark, stock tokens and a host skin (measured from computed colours)",
          worst >= 4.5 and all(got.values()), {k: min(v) if v else None for k, v in got.items()})


@item("scroll")
def scroll(pages, check, tab):
    """#12: at 375 and 390 px the table scrolls sideways inside its box: the page does not, the last column comes fully
    into view, and nothing is left stuck over it."""
    bad = {}
    for width in (375, 390):
        for path, name in [(TYPES, "Every type"), (MODELS, "Parameters · with CI")]:
            page = pages.open(path, width=width, height=812, mobile=True)
            tab(page, name)
            r = page.evaluate("""() => { const v = document.querySelector('#example'); const s = v.querySelector('.dv-scroll');
              const before = [s.scrollWidth, s.clientWidth]; s.scrollLeft = s.scrollWidth; const box = s.getBoundingClientRect();
              const heads = [...v.querySelectorAll('.dv-table thead th[data-col]')]; const last = heads.reduce((a, b) => (a.getBoundingClientRect().right > b.getBoundingClientRect().right ? a : b));
              const lb = last.getBoundingClientRect();
              const stuck = [...v.querySelector('tbody tr.dv-row').children].filter((td) => getComputedStyle(td).position === 'sticky').reduce((w, td) => w + td.getBoundingClientRect().width, 0);
              return { page: document.scrollingElement.scrollWidth, inner: before, scrolled: s.scrollLeft, lastIn: lb.left >= box.left - 1 && lb.right <= box.right + 1, stuck: Math.round(stuck), box: Math.round(box.width) }; }""")
            if not (r["page"] <= width and r["inner"][0] > r["inner"][1] and r["scrolled"] > 0 and r["lastIn"] and r["stuck"] <= r["box"] / 2):
                bad[f"{name} @ {width}"] = r
            page.context.close()
    check("r2 #12: at 375 and 390 px the table scrolls sideways in its own box (the page never does), its last column scrolls fully into view, and frozen columns take at most half the box", not bad, bad or None)


# ---------------------------------------------------------------------------------------------- judge round 3
# a cell's drawing (direct text by Range, every element of a typed drawing) must lie inside the cell
INSIDE = """(fit) => { const v = document.querySelector('#example'); const out = [];
  for (const td of v.querySelectorAll('.dv-table tbody tr.dv-row td[data-col]')) {
    const t = [...td.classList].find((c) => c.startsWith('dv-t-'));
    const typed = t ? t.slice(5) : null;
    const numeric = td.classList.contains('dv-num');
    if (!(numeric || (typed && fit.includes(typed)))) continue;
    const b = td.getBoundingClientRect(); const inner = [b.left + 1, b.right - 1];
    const rects = [];
    // a pill, person or relation cell (r5 #4): its first pill or chip whole and inside; the rest may end in an ellipsis
    const box = td.querySelector('.dv-opts, .dv-people, .dv-rels');
    if (box && box.firstElementChild) {
      const f = box.firstElementChild;
      if (f.scrollWidth > f.clientWidth + 1) { out.push([td.dataset.col, typed, 'first pill cut', f.scrollWidth, Math.round(b.width)]); continue; }
      rects.push(['first pill', f.getBoundingClientRect()]);
    } else { const r = document.createRange(); r.selectNodeContents(td); rects.push(['text', r.getBoundingClientRect()]); }
    // what a pill row hides behind its ellipsis (the pills after the first) is not drawn: only the first is measured
    for (const e of td.querySelectorAll('svg, .dv-rate, .dv-progress-track, .dv-progress-num, .dv-check, .dv-toggle, time, .dv-dur, .dv-idcell, .dv-v, .dv-c')) if (!(box && box.contains(e) && !box.firstElementChild.contains(e))) rects.push([e.getAttribute('class') || e.tagName, e.getBoundingClientRect()]);
    for (const [what, a] of rects) if (a.width > 0 && (a.left < inner[0] - 0.5 || a.right > inner[1] + 0.5)) { out.push([td.dataset.col, typed || 'number', String(what).slice(0, 24), Math.round(a.width), Math.round(b.width)]); break; }
  }
  return out.slice(0, 10); }"""
FIT = ["number", "currency", "percent", "rating", "duration", "date", "created_time", "edited_time", "checkbox", "id", "rollup", "formula",
       "select", "multi_select", "status", "person", "relation"]


@item("r3-minw")
def r3_minw(pages, check, tab):
    """r3 #4, #7: with every column at 20 px, every number (direct text, measured by Range) and every fixed-size typed
    drawing (rating, progress, duration, dates, checkbox, ID) still lies inside its cell; also after a drag inwards."""
    bad = {}
    page = pages.open(TYPES)
    tab(page, "Every type")
    page.evaluate("() => { const v = document.querySelector('#example'); v.editProperty({ action: 'set', id: 'rating', patch: { max: 10 } }); }")
    page.wait_for_timeout(300)
    page.evaluate("() => { const v = document.querySelector('#example'); const keys = [...v.querySelectorAll('.dv-table thead th[data-col]')].map((t) => t.dataset.col); v.setView({ columnSize: Object.fromEntries(keys.map((k) => [k, 20])) }); }")
    page.wait_for_timeout(400)
    got = page.evaluate(INSIDE, FIT)
    if got:
        bad["Every type, all columns at 20 px"] = got
    page.evaluate("() => document.querySelector('#example').setView({ columnSize: null })")
    page.wait_for_timeout(300)
    h = page.locator("#example thead th[data-col=rating] .dv-resize").bounding_box()
    page.mouse.move(h["x"] + 2, h["y"] + 5)
    page.mouse.down()
    page.mouse.move(h["x"] - 400, h["y"] + 5, steps=6)
    page.mouse.up()
    page.wait_for_timeout(300)
    got = page.evaluate(INSIDE, FIT)
    if got:
        bad["rating dragged 400 px inwards"] = got
    page.context.close()
    page = pages.open(MODELS)
    for name in ["Parameters", "Leaderboard", "Runs"]:
        tab(page, name)
        page.evaluate("() => { const v = document.querySelector('#example'); const keys = [...v.querySelectorAll('.dv-table thead th[data-col]')].map((t) => t.dataset.col); v.setView({ columnSize: Object.fromEntries(keys.map((k) => [k, 20])) }); }")
        page.wait_for_timeout(400)
        got = page.evaluate(INSIDE, FIT)
        if got:
            bad[name] = got
    page.context.close()
    check("r3 #4, #7: at 20 px (and after a 400 px drag), every number (by Range) and every fixed-size typed drawing (a 10-star rating, bars, durations, dates, checks, IDs) lies inside its cell", not bad, bad or None)


@item("r3-title")
def r3_title(pages, check, tab):
    """r3 #5, #7: a deliberately wide distribution title stays centred over its strip and inside its cell."""
    page = pages.open(MODELS, editable=True)
    tab(page, "What each rung adds")
    page.evaluate("() => document.querySelector('#example').editProperty({ action: 'set', id: 'delta_mrad', patch: { displayName: 'A deliberately wide distribution title, longer than its strip' } })")
    page.wait_for_timeout(400)
    r = page.evaluate("""() => { const v = document.querySelector('#example'); const th = v.querySelector('.dv-table thead th[data-col=delta_mrad]');
      const t = th.querySelector('.dv-th-text').getBoundingClientRect(), c = th.getBoundingClientRect();
      const m = [...v.querySelectorAll('.dv-table tbody td[data-col=delta_mrad] .dv-m')].map((e) => e.getBoundingClientRect()).filter((x) => x.width)[0];
      const lab = th.querySelector('.dv-th-label');
      return { dx: Math.round(((t.left + t.right) / 2 - (m.left + m.right) / 2) * 10) / 10, inside: t.left >= c.left - 0.5 && t.right <= c.right + 0.5, cut: lab.scrollWidth > lab.clientWidth + 1, title: Math.round(t.width), cell: Math.round(c.width) }; }""")
    check("r3 #5, #7: a 60-character distribution title is centred over its strip (within 1 px), inside its cell and not cut",
          abs(r["dx"]) <= 1 and r["inside"] and not r["cut"], r)
    page.context.close()


@item("r3-peek")
def r3_peek(pages, check, tab):
    """r3 #6: the second click of a double-click that lands on the peek opens the record's page only on the peek's
    background, for the record that peek shows; never on an input, a button or a link, nor when the peek moved on.
    WHY the gap is measured: the product counts a second click within 800 ms of the first; on a loaded machine the
    test's own staging (wait for the peek, place the target) can take longer, and then every case — the negatives
    included — would say nothing. A case staged too slowly is staged again (up to 4 tries) and its gap reported."""
    ACT = "gallery/robotparts-actuators/index.html"
    res = {}
    for case in ["background", "input", "button", "link", "moved on"]:
        for attempt in range(1, 5):
            page = pages.open(ACT, width=1440, height=900)
            page.context.route("https://robotparts.dev/**", lambda r: r.fulfill(status=200, body="<html><body>part</body></html>", content_type="text/html"))
            tab(page, "All, flat")
            cell = page.locator("#example tbody tr[data-id] td").nth(4)
            b = cell.bounding_box()
            x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
            page.evaluate("() => { window.__first = null; document.addEventListener('click', (e) => { if (window.__first === null) window.__first = e.timeStamp; }, { capture: true }); }")
            page.mouse.click(x, y)
            page.wait_for_selector("#example .dv-peek:not([hidden])")
            page.wait_for_timeout(50)
            target = page.evaluate("""([case_, x, y]) => { const peek = document.querySelector('#example .dv-peek');
              let t = peek;
              if (case_ === 'input') { t = document.createElement('input'); peek.prepend(t); }
              if (case_ === 'button') { t = peek.querySelector('button'); }
              if (case_ === 'link') { t = document.createElement('a'); t.href = '#peek-link-test'; t.textContent = 'a link'; peek.prepend(t); }
              if (case_ === 'moved on') { const ids = [...document.querySelectorAll('#example tbody tr[data-id]')].map((r) => r.dataset.id); document.querySelector('#example').openPeek(ids[3]); }
              window.__t = t; return t ? t.tagName : null; }""", [case, x, y])
            gap = page.evaluate("""([x, y]) => { const t = window.__t; const gap = performance.now() - window.__first;
              t.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, detail: 2, clientX: x, clientY: y, view: window })); return Math.round(gap); }""", [x, y])
            page.wait_for_timeout(700)
            res[case] = {"url": page.url.split("/")[-2] if "robotparts.dev" in page.url else page.url.split("#")[-1][:40], "left": "robotparts.dev" in page.url,
                         "target": target, "gap ms": gap, "tries": attempt}
            page.context.close()
            if gap < 700:
                break
    staged = all(r["gap ms"] < 700 for r in res.values())
    ok = staged and res["background"]["left"] and not any(res[c]["left"] for c in ["input", "button", "link", "moved on"])
    check("r3 #6: a double-click's second click on the peek's background opens the record's page; on an input, a button or a link in the peek, or after the peek moved to another record, it does not (each staged inside the 800 ms window)",
          ok, res)



# ---------------------------------------------------------------------------------------------- judge round 4
@item("r4-formula")
def r4_formula(pages, check, tab):
    """r4 #3: a formula column holds its text and its ƒ mark: at a saved 20 px width and after a 400 px drag inwards."""
    page = pages.open(TYPES)
    tab(page, "Every type")
    page.evaluate("""() => { const v = document.querySelector('#example'); const d = JSON.parse(JSON.stringify(v.data));
      d.properties.score = { type: 'number' }; d.rows.forEach((r, i) => { r.score = 123456789012345.67 - i; }); v.data = d;
      v.editProperty({ action: 'set', id: 'score', patch: { displayName: 'X', type: 'formula', derived: 'budget × rating' } });
      v.setView({ order: ['name', 'score', 'status'] }); }""")
    page.wait_for_timeout(400)
    bad = {}
    page.evaluate("() => { const v = document.querySelector('#example'); v.setView({ columnSize: { name: 20, score: 20, status: 20 } }); }")
    page.wait_for_timeout(400)
    got = page.evaluate(INSIDE, FIT)
    w = page.evaluate("() => Math.round(document.querySelector('#example thead th[data-col=score]').getBoundingClientRect().width)")
    if got:
        bad["saved 20 px"] = got
    page.evaluate("() => document.querySelector('#example').setView({ columnSize: null })")
    page.wait_for_timeout(300)
    h = page.locator("#example thead th[data-col=score] .dv-resize").bounding_box()
    page.mouse.move(h["x"] + 2, h["y"] + 5)
    page.mouse.down()
    page.mouse.move(h["x"] - 400, h["y"] + 5, steps=6)
    page.mouse.up()
    page.wait_for_timeout(300)
    got = page.evaluate(INSIDE, FIT)
    if got:
        bad["dragged 400 px inwards"] = got
    check("r4 #3: a formula column showing 123,456,789,012,345.67 and its ƒ mark keeps them inside the cell at a saved 20 px width and after a 400 px drag",
          not bad, bad or {"width": w})
    page.context.close()


PILLS = """() => {
  const v = document.querySelector('#example'); const host = document.createElement('div'); v.append(host);
  const colors = ['default', 'gray', 'brown', 'orange', 'yellow', 'green', 'blue', 'purple', 'pink', 'red'];
  host.innerHTML = colors.map((c) => `<span class="dv-opt dv-c-${c}">Option</span><span class="dv-statuspill dv-c-${c}"><span class="dv-dot"></span>Status</span>`).join('');
  const parse = (c) => { const m = /color\\(srgb ([\\d.e-]+) ([\\d.e-]+) ([\\d.e-]+)(?: \\/ ([\\d.]+))?\\)/.exec(c); if (m) return [+m[1] * 255, +m[2] * 255, +m[3] * 255, m[4] === undefined ? 1 : +m[4]];
    const p = /rgba?\\(([^)]+)\\)/.exec(c)[1].split(',').map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const lum = (c) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const out = {};
  for (const e of host.children) { const cs = getComputedStyle(e); const a = lum(parse(cs.color)), b = lum(parse(cs.backgroundColor));
    out[e.className] = Math.round(100 * (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)) / 100; }
  host.remove(); return out; }"""


@item("r4-pills")
def r4_pills(pages, check, tab):
    """r4 #6: every option colour's pill text (select and status) reads at 4.5:1 or better on its own fill, light and dark."""
    got = {}
    for dark in (False, True):
        page = pages.open(TYPES, dark=dark)
        got["dark" if dark else "light"] = page.evaluate(PILLS)
        page.context.close()
    low = {f"{t} {k}": v for t, d in got.items() for k, v in d.items() if v < 4.5}
    check("r4 #6: all ten option colours, as select and status pills, read at 4.5:1 or better on their fill, light and dark (measured)",
          not low, low or {t: min(d.values()) for t, d in got.items()})


@item("rollup-settings")
def rollup_settings(pages, check, tab):
    """The column menu's "All roll-up settings…" opens the roll-up settings, visible, with the dimensions to keep: the
    Display panel's Roll up page under §15's bar (toolbar="bar"), the toolbar's Roll up menu under the older one."""
    got = {}
    for label, attrs in [("bar", {"toolbar": "bar", "view": "By status"}), ("older toolbar", None)]:
        page = pages.open(TYPES, attrs=attrs)
        if attrs is None:
            tab(page, "By status")
        page.wait_for_function("() => document.querySelector('#example').view.name === 'By status'", timeout=20000)
        page.locator("#example thead th[data-col=owner]").click()
        page.wait_for_selector(".dv-colmenu")
        page.click(".dv-colmenu [data-act='page:rollup']")
        page.click(".dv-colmenu [data-act='roll:settings']")
        page.wait_for_timeout(600)
        got[label] = page.evaluate("""() => { const b = document.querySelector('#example .dv-set-rollup') || [...document.querySelectorAll('#example .dv-pop:not([hidden])')].find((e) => e.querySelector('[data-dim]'));
          const box = b && b.getBoundingClientRect();
          return { where: b ? b.className : null, visible: !!(box && box.width > 0 && box.height > 0), dims: b ? b.querySelectorAll('[data-dim]').length : 0, menuClosed: !document.querySelector('.dv-colmenu') }; }""")
        page.context.close()
    ok = all(r["visible"] and r["dims"] >= 2 and r["menuClosed"] for r in got.values()) and "dv-set-rollup" in (got["bar"]["where"] or "")
    check("the column menu's 'All roll-up settings…' opens the roll-up settings, visible, with their dimensions: the Display panel's page under the bar, the Roll up menu under the older toolbar",
          ok, got)



# ---------------------------------------------------------------------------------------------- judge round 5
@item("r5-rich-typed")
def r5_rich_typed(pages, check, tab):
    """A rich cell (a rolled-up value with its min–max and basis) drawn by a type (Runs as a bar) keeps its range and its
    basis mark beside the drawing (found by the table-oracle review: they were dropped)."""
    page = pages.open(MODELS)
    tab(page, "Leaderboard")
    r = page.evaluate("""() => { const tds = [...document.querySelectorAll('#example tbody td[data-col=n_runs]')];
      const rows = document.querySelector('#example').model.rows; const ids = [...document.querySelectorAll('#example tbody tr[data-i]')];
      return tds.slice(0, 6).map((td) => { const vis = (e) => e && e.getBoundingClientRect().width > 0;
        return { text: td.textContent.trim(), bar: vis(td.querySelector('.dv-progress-track')), range: vis(td.querySelector('.dv-range')), mark: vis(td.querySelector('.dv-basis')) }; }); }""")
    ok = r and all(x["bar"] and x["range"] and x["mark"] and re.match(r"^\d+\d+–\d+~$", x["text"]) for x in r)
    check("a rolled-up Runs cell drawn as a bar keeps its range and basis mark beside it, visible (models Leaderboard)", ok, r[:3])
    page.context.close()


LONG_VALUE = "Calibration awaiting hospital procurement approval"
PILLISH = """() => { const v = document.querySelector('#example'); const out = [];
  for (const td of v.querySelectorAll('.dv-table tbody tr.dv-row td[data-col]')) {
    const t = ([...td.classList].find((c) => c.startsWith('dv-t-')) || '').slice(5);
    if (!['select', 'status', 'multi_select', 'person', 'relation'].includes(t)) continue;
    const box = td.querySelector('.dv-opts, .dv-people, .dv-rels'); if (!box) continue;
    const b = td.getBoundingClientRect(), first = box.firstElementChild.getBoundingClientRect();
    // whole: inside the cell, and its own text not cut (a shrink-wrapped row of chips split the cut between them)
    const whole = first.left >= b.left + 1 - 0.5 && first.right <= b.right - 1 + 0.5 && box.firstElementChild.scrollWidth <= box.firstElementChild.clientWidth + 1;
    const over = box.scrollWidth > box.clientWidth + 1;
    const ell = getComputedStyle(box).textOverflow === 'ellipsis' && box.getBoundingClientRect().right <= b.right + 0.5;
    if (!whole || (over && !ell)) out.push([td.dataset.col, t, Math.round(first.width), Math.round(b.width), over, ell]);
  }
  return out.slice(0, 8); }"""


@item("r5-pills-minw")
def r5_pills_minw(pages, check, tab):
    """r5 #4: select, status, multi-select, person and relation columns hold their widest pill (or avatar and name, or
    chip) whole at a saved 20 px width and after a 400 px drag; more than fits ends in an ellipsis, never a silent crop."""
    page = pages.open(TYPES)
    tab(page, "Every type")
    page.evaluate(f"""() => {{ const v = document.querySelector('#example'); const d = JSON.parse(JSON.stringify(v.data)); const L = {json.dumps(LONG_VALUE)};
      d.rows[0].status = L; d.rows[0].priority = L; d.rows[0].owner = L; d.rows[0].tags = [L, 'ai', 'web', 'api'];
      d.rows[1].name = L; d.rows[0].depends_on = [d.rows[1].id]; v.data = d; v.setView({{ order: ['status', 'priority', 'tags', 'owner', 'depends_on'] }}); }}""")
    page.wait_for_timeout(400)
    bad = {}
    page.evaluate("() => document.querySelector('#example').setView({ columnSize: { status: 20, priority: 20, tags: 20, owner: 20, depends_on: 20 } })")
    page.wait_for_timeout(400)
    got = page.evaluate(PILLISH)
    if got:
        bad["saved 20 px"] = got
    page.evaluate("() => document.querySelector('#example').setView({ columnSize: null })")
    page.wait_for_timeout(300)
    for col in ["status", "tags", "owner"]:
        h = page.locator(f"#example thead th[data-col={col}] .dv-resize").bounding_box()
        page.mouse.move(h["x"] + 2, h["y"] + 5)
        page.mouse.down()
        page.mouse.move(h["x"] - 400, h["y"] + 5, steps=6)
        page.mouse.up()
        page.wait_for_timeout(250)
    got = page.evaluate(PILLISH)
    if got:
        bad["dragged 400 px inwards"] = got
    check("r5 #4: a 50-character status, select, person and relation value stays whole at a saved 20 px width and after a drag; a multi-select's overflow ends in an ellipsis",
          not bad, bad or None)
    page.context.close()


@item("r5-wrap-true")
def r5_wrap_true(pages, check, tab):
    """r5 #5: under §15's wrap: true the column menu shows Wrap checked; unchecking one column keeps every other column
    wrapping (a list of them); checking it again is wrap: true again."""
    page = pages.open(TYPES)
    tab(page, "All")
    page.evaluate("() => document.querySelector('#example').setView({ wrap: true })")
    page.wait_for_timeout(300)
    page.locator("#example thead th[data-col=name]").click()
    page.wait_for_selector(".dv-colmenu")
    checked = page.evaluate("() => !!document.querySelector('.dv-colmenu [data-act=wrap] .dv-cm-check')")
    page.click(".dv-colmenu [data-act=wrap]")
    page.wait_for_timeout(300)
    off = page.evaluate("() => document.querySelector('#example').view.wrap")
    page.locator("#example thead th[data-col=name]").click()
    page.wait_for_selector(".dv-colmenu")
    unchecked = page.evaluate("() => !document.querySelector('.dv-colmenu [data-act=wrap] .dv-cm-check')")
    page.click(".dv-colmenu [data-act=wrap]")
    page.wait_for_timeout(300)
    back = page.evaluate("() => document.querySelector('#example').view.wrap")
    # the same seam from the other side: §15's Layout settings read the same keys — "Wrap cell text" is every cell, so
    # a column list is not it; "Freeze columns" under §28's freeze: <property> names that property, never "None"
    page.keyboard.press("Escape")
    page.evaluate("() => document.querySelector('#example').setView({ wrap: ['status'], freeze: 'owner' })")
    page.wait_for_timeout(300)
    page.evaluate("() => { const el = document.querySelector('#example'); el._settingsUi ? el._settingsUi.open('layout') : el.openMenu('layout'); }")
    page.wait_for_timeout(400)
    layout = page.evaluate("""() => { const el = document.querySelector('#example');
      const vis = (n) => n && n.getClientRects().length;
      const box = [...el.querySelectorAll('input[type=checkbox][data-opt]')].find(vis);
      const sel = [...el.querySelectorAll('select[data-opt]')].find((s) => vis(s) && [...s.options].some((o) => o.value === '1'));
      return { wrapToggle: box ? box.checked : null, freeze: sel ? sel.selectedOptions[0].textContent.trim() : null }; }""")
    check("r5 #5: wrap: true shows Wrap checked; unchecking Name keeps status, owner, priority and completion wrapping; checking it again is wrap: true; under wrap: [status] the Layout toggle 'Wrap cell text' is off, and under freeze: owner 'Freeze columns' names Owner",
          checked and off == ["status", "owner", "priority", "completion"] and unchecked and back is True and layout["wrapToggle"] is False and "Owner" in (layout["freeze"] or ""),
          {"checked": checked, "after uncheck": off, "unchecked shown": unchecked, "after check": back, "layout": layout})
    page.context.close()


@item("r5-link-keys")
def r5_link_keys(pages, check, tab):
    """r5 #6: Enter on a focused URL, email or phone link in a cell does what the link does; the row is not opened and
    the key is not cancelled."""
    page = pages.open(TYPES)
    # the URL's popup never reaches the network (a matcher, so the local gallery server is untouched)
    page.context.route(lambda u: "notion." in u, lambda r: r.fulfill(status=200, body="<html>ok</html>", content_type="text/html"))
    tab(page, "Every type")
    page.evaluate("() => { window.__keys = []; window.addEventListener('keydown', (e) => { if (e.key === 'Enter') window.__keys.push(e.defaultPrevented); }); }")
    res = {}
    for col in ["url", "email", "phone"]:
        sel = f"#example tbody tr.dv-row td[data-col={col}] a"
        page.locator(sel).first.focus()
        popup = None
        if col == "url":
            # WHY expect_page: the popup's page event lands after a fixed wait, so it was credited to the next link
            with page.context.expect_page(timeout=5000) as pi:
                page.keyboard.press("Enter")
            popup = pi.value
        else:
            page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        res[col] = {"prevented": page.evaluate("() => window.__keys[window.__keys.length - 1]"),
                    "peek": page.evaluate("() => !document.querySelector('#example .dv-peek').hidden"),
                    "popup": popup.url if popup else None}
        if popup:
            popup.close()
        if res[col]["peek"]:
            page.keyboard.press("Escape")
    # the same bug's sibling: a List line holding a typed link (list/src/index.js had the identical Enter handler)
    page.evaluate("() => document.querySelector('#example').setView({ type: 'list', order: ['name', 'email', 'phone'] })")
    page.wait_for_timeout(500)
    line_link = page.locator("#example .dv-list-line a").first
    if line_link.count():
        line_link.focus()
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        res["list"] = {"prevented": page.evaluate("() => window.__keys[window.__keys.length - 1]"),
                       "peek": page.evaluate("() => !document.querySelector('#example .dv-peek').hidden")}
    else:
        res["list"] = {"prevented": None, "peek": None, "note": "no link in a list line"}
    ok = all(r["prevented"] is False and not r["peek"] for r in res.values()) and "notion.so" in (res["url"]["popup"] or "")
    check("r5 #6: Enter on a cell's URL, email and phone link, and on a List line's link, is the link's: not cancelled, the row not opened, the URL opened",
          ok, res)
    page.context.close()


@item("r5-pill-cap")
def r5_pill_cap(pages, check, tab):
    """r5 #4, the far side: a pill or chip longer than the 400 px cap, and a long URL or email in a narrow column, end
    their own text in an ellipsis inside the cell (never a silent crop); the cell's title holds the whole value."""
    page = pages.open(TYPES)
    tab(page, "Every type")
    huge = "Calibration awaiting hospital procurement approval and a second sign-off from the biomedical engineering lead"
    page.evaluate(f"""() => {{ const v = document.querySelector('#example'); const d = JSON.parse(JSON.stringify(v.data)); const L = {json.dumps(huge)};
      d.rows[0].status = L; d.rows[0].owner = L; d.rows[0].url = 'https://example.com/' + 'a-very-long-path/'.repeat(8); d.rows[0].email = 'someone.with.a.long.address@' + 'subdomain.'.repeat(4) + 'example.com';
      v.data = d; v.setView({{ columnSize: {{ status: 20, owner: 20, url: 120, email: 120 }} }}); }}""")
    page.wait_for_timeout(500)
    got = page.evaluate("""() => { const v = document.querySelector('#example'); const out = {};
      for (const [col, sel] of [['status', '.dv-statuspill'], ['owner', '.dv-person'], ['url', '.dv-urlcell'], ['email', '.dv-urlcell']]) {
        const td = v.querySelector(`.dv-table tbody tr.dv-row td[data-col=${col}]`); const n = td && td.querySelector(sel);
        if (!n) { out[col] = null; continue; }
        const b = td.getBoundingClientRect(), r = n.getBoundingClientRect();
        out[col] = { cell: Math.round(b.width), inside: r.left >= b.left - 0.5 && r.right <= b.right + 0.5, cut: n.scrollWidth > n.clientWidth + 1,
                     // text-overflow draws only in a block container: a flex item's text (inline-flex) is cropped with no ellipsis
                     ellipsis: getComputedStyle(n).textOverflow === 'ellipsis' && getComputedStyle(n).overflow.includes('hidden') && !/flex|grid/.test(getComputedStyle(n).display), title: (td.title || '').length };
      }
      return out; }""")
    # the detail view shows the same values whole: the peek's fields wrap, and never push its table past the peek
    page.evaluate("() => document.querySelector('#example').openPeek(document.querySelector('#example').data.rows[0].id)")
    page.wait_for_timeout(600)
    got["peek"] = page.evaluate("""() => { const pk = document.querySelector('#example .dv-peek'), t = pk && pk.querySelector('.dv-fields');
      return t ? { table: Math.round(t.getBoundingClientRect().width), peek: Math.round(pk.clientWidth), label: Math.round(t.querySelector('th').getBoundingClientRect().width) } : null; }""")
    pk = got.pop("peek")
    ok = all(g and g["inside"] and g["cut"] and g["ellipsis"] and g["title"] > 40 for g in got.values()) and got["status"]["cell"] <= 420 \
        and pk and pk["table"] <= pk["peek"] and pk["label"] >= 0.3 * pk["table"]
    got["peek"] = pk
    check("r5 #4: a 110-character status and person cap their column near 400 px and end in an ellipsis inside it; a long URL and email in a 120 px column end in one too; the title holds each whole; the peek wraps them inside its width",
          ok, got)
    page.context.close()


CELL_LINES = """(col) => { const td = document.querySelector(`#example .dv-table tbody tr.dv-row td[data-col=${col}]`); if (!td) return null;
  // the row's Open button (§38) sits on its own top in the cell's corner: it is not a line of the value
  const open = td.querySelector('.dv-row-open'); if (open) open.style.display = 'none';
  const r = document.createRange(); r.selectNodeContents(td);
  const tops = new Set([...r.getClientRects()].filter((x) => x.width > 0).map((x) => Math.round(x.top)));
  if (open) open.style.display = '';
  return { lines: tops.size, wrapcol: td.classList.contains('dv-wrapcol'), box: !!td.querySelector('.dv-wrapbox'), ws: getComputedStyle(td).whiteSpace }; }"""


@item("r6-wrap-excluded")
def r6_wrap_excluded(pages, check, tab):
    """r6 #2: a column taken out of the wrap list stays on one line though the rows went tall for the others; a listed
    column wraps; rowHeight: medium (rows the view asked to be tall) still wraps every cell."""
    page = pages.open(TYPES)
    tab(page, "All")
    long = "New Database View Types for the hospital procurement team and its calibration backlog review"
    page.evaluate(f"""() => {{ const v = document.querySelector('#example'); const d = JSON.parse(JSON.stringify(v.data));
      d.rows[0].name = {json.dumps(long)}; d.rows[0].status = 'Calibration awaiting hospital procurement approval'; v.data = d; v.setView({{ wrap: true }}); }}""")
    page.wait_for_timeout(400)
    page.locator("#example thead th[data-col=name]").click()
    page.wait_for_selector(".dv-colmenu")
    page.click(".dv-colmenu [data-act=wrap]")
    page.wait_for_timeout(400)
    wrap = page.evaluate("() => document.querySelector('#example').view.wrap")
    name = page.evaluate(CELL_LINES, "name")
    status = page.evaluate(CELL_LINES, "status")
    page.evaluate("() => document.querySelector('#example').setView({ wrap: ['status'], rowHeight: 'medium' })")
    page.wait_for_timeout(400)
    medium = page.evaluate(CELL_LINES, "name")
    # the menu says what the cell does: under tall rows Name wraps, so Wrap is shown checked, with why, and not offered
    page.locator("#example thead th[data-col=name]").click()
    page.wait_for_selector(".dv-colmenu")
    menu = page.evaluate("""() => { const b = document.querySelector('.dv-colmenu [data-act=wrap]');
      return b ? { checked: !!b.querySelector('.dv-cm-check'), disabled: b.disabled, hint: (b.querySelector('.dv-cm-hint') || {}).textContent || '' } : null; }""")
    ok = (isinstance(wrap, list) and "name" not in wrap and name and name["lines"] == 1 and not name["wrapcol"] and not name["box"] and name["ws"] == "nowrap"
          and status and status["wrapcol"] and medium and medium["wrapcol"] and medium["lines"] > 1
          and menu and menu["checked"] and menu["disabled"] and menu["hint"])
    check("r6 #2: after unchecking Name under wrap: true, Name's long title stays on one line (no wrap class, nowrap) while Status still wraps; rowHeight: medium wraps every cell, and Name's menu then shows Wrap checked with why",
          ok, {"wrap": wrap, "name": name, "status": status, "name at rowHeight medium": medium, "menu at medium": menu})
    page.context.close()


@item("r6-rel-keys")
def r6_rel_keys(pages, check, tab):
    """r6 #3: each relation chip is a control of its own: Tab from its row reaches the first chip, Tab again the second;
    Enter on a chip opens that related record in the peek (not the row's record), in the Table and in the List."""
    page = pages.open(TYPES)
    tab(page, "Every type")
    rows = page.evaluate("""() => { const v = document.querySelector('#example'); const d = JSON.parse(JSON.stringify(v.data));
      // not the next rows: Tab or Enter falling through to a row must not pass for a chip
      d.rows[0].depends_on = [d.rows[4].id, d.rows[6].id]; v.data = d;
      return [d.rows[0], d.rows[4], d.rows[6]].map((r) => ({ id: r.id, name: r.name })); }""")
    res = {}
    for kind, line_sel in [("table", "#example .dv-table tbody tr.dv-row[data-i='0']"), ("list", "#example .dv-list-line[data-i='0']")]:
        page.evaluate(f"() => document.querySelector('#example').setView({{ type: '{kind}', order: ['name', 'depends_on'] }})")
        page.wait_for_timeout(600)
        got = []
        for nth in (1, 2):
            if page.evaluate("() => !document.querySelector('#example .dv-peek').hidden"):
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
            page.locator(line_sel).first.focus()
            for _ in range(nth):
                page.keyboard.press("Tab")
            focus = page.evaluate("() => { const a = document.activeElement; return a ? { cls: a.className, rel: a.dataset ? a.dataset.rel || null : null, tag: a.tagName } : null; }")
            page.keyboard.press("Enter")
            page.wait_for_timeout(500)
            peek = page.evaluate("() => { const p = document.querySelector('#example .dv-peek'); return p && !p.hidden ? (p.querySelector('h2') || {}).textContent || '' : null; }")
            got.append({"focus": focus, "peek": peek})
        res[kind] = got
        if page.evaluate("() => !document.querySelector('#example .dv-peek').hidden"):
            page.keyboard.press("Escape")
    want = [rows[1], rows[2]]
    ok = all(len(g) == 2 and all(x["focus"] and x["focus"]["rel"] == w["id"] and x["peek"] == w["name"] for x, w in zip(g, want)) for g in res.values())
    check("r6 #3: Tab reaches each of a cell's two relation chips in turn, and Enter on each opens its own related record in the peek — Table and List",
          ok, {"want": want, **res})
    page.context.close()


FOCUSED_CHIP = """() => { const a = document.activeElement; const td = a && a.closest('td'); if (!td || !a.matches('.dv-rel')) return null;
  const c = td.getBoundingClientRect(), r = a.getBoundingClientRect();
  return { rel: a.dataset.rel, inside: r.left >= c.left - 0.5 && r.right <= c.right + 0.5, clip: getComputedStyle(a.parentElement).textOverflow }; }"""


@item("r6-rel-focus-visible")
def r6_rel_focus_visible(pages, check, tab):
    """r6 #3, what a keyboard user sees: a relation chip that Tab reaches is wholly visible in its cell, even when it sat
    behind the cell's ellipsis; when focus leaves, the chip row is back at its start."""
    page = pages.open(TYPES)
    tab(page, "Every type")
    page.evaluate("""() => { const v = document.querySelector('#example'); const d = JSON.parse(JSON.stringify(v.data));
      d.rows[6].name = 'Data Export API for every hospital procurement system and its calibration backlog';
      d.rows[0].depends_on = [d.rows[4].id, d.rows[6].id]; v.data = d; v.setView({ order: ['name', 'depends_on', 'status', 'owner'] }); }""")
    page.wait_for_timeout(500)
    page.locator("#example .dv-table tbody tr.dv-row[data-i='0']").focus()
    page.keyboard.press("Tab")
    first = page.evaluate(FOCUSED_CHIP)
    page.keyboard.press("Tab")
    second = page.evaluate(FOCUSED_CHIP)
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Shift+Tab")
    back = page.evaluate("() => document.querySelector('#example .dv-table tbody tr.dv-row[data-i=\"0\"] .dv-rels').scrollLeft")
    ok = first and first["inside"] and second and second["inside"] and back == 0
    check("r6 #3: Tab to a relation chip that sat behind the cell's ellipsis shows it whole inside its cell; leaving puts the chip row back at its start",
          ok, {"first": first, "second": second, "scrollLeft after leaving": back})
    page.context.close()


@item("r7-list-focus")
def r7_list_focus(pages, check, tab):
    """r7 #3: in a long List, a relation button that has the keyboard keeps it while the list scrolls and redraws (a
    small scroll, and Tab after Tab across the viewport's bottom edge); Enter then opens that chip's own record."""
    page = pages.open(TYPES, width=1200, height=700)
    tab(page, "Every type")
    page.evaluate("""() => { const v = document.querySelector('#example'); const d = JSON.parse(JSON.stringify(v.data));
      const base = d.rows; const rows = [];
      for (let i = 0; i < 300; i++) { const r = JSON.parse(JSON.stringify(base[i % base.length])); r.id = 'L' + i; r.name = 'Line ' + i; rows.push(r); }
      for (let i = 0; i < 300; i++) rows[i].depends_on = ['L' + ((i + 7) % 300), 'L' + ((i + 11) % 300)];
      d.rows = rows; v.data = d; v.setView({ type: 'list', order: ['name', 'depends_on'] }); }""")
    page.wait_for_timeout(800)
    focused = """() => { const a = document.activeElement; return a && a.matches && a.matches('.dv-rel') ? { rel: a.dataset.rel, line: a.closest('[data-i]') && a.closest('[data-i]').dataset.i } : { tag: a ? a.tagName : null, cls: a ? String(a.className).slice(0, 40) : null }; }"""
    page.locator("#example .dv-list-line[data-i='2']").focus()
    page.keyboard.press("Tab")
    start = page.evaluate(focused)
    # a small scroll that keeps the line on screen: the virtualizer redraws every line
    page.mouse.move(600, 400)
    page.mouse.wheel(0, 60)
    page.wait_for_timeout(400)
    after_scroll = page.evaluate(focused)
    steps = []
    for _ in range(40):
        page.keyboard.press("Tab")
        page.wait_for_timeout(60)
        steps.append(page.evaluate(focused))
    # Tab visits each line (a line is focusable) and its chips: focus is lost only when it falls to the page
    for _ in range(3):
        if "rel" in steps[-1]:
            break
        page.keyboard.press("Tab")
        page.wait_for_timeout(60)
        steps.append(page.evaluate(focused))
    lost = [s for s in steps if "rel" not in s and s.get("tag") in ("BODY", None)]
    last = steps[-1]
    page.keyboard.press("Enter")
    page.wait_for_timeout(600)
    peek = page.evaluate("() => { const p = document.querySelector('#example .dv-peek'); return p && !p.hidden ? (p.querySelector('h2') || {}).textContent || '' : null; }")
    want = ("Line " + last["rel"][1:]) if "rel" in last else None
    ok = start.get("rel") and after_scroll == start and not lost and int(last.get("line", 0)) > 12 and peek == want
    check("r7 #3: a relation button in a 300-line List keeps the keyboard through a scroll and 40 Tabs past the viewport's edge; Enter opens that chip's own record",
          ok, {"start": start, "after a 60 px scroll": after_scroll, "lost focus at": lost[:3], "last": last, "peek": peek, "want": want})
    page.context.close()
