"""The popover that lists every source of a value several sources state (docs/CONTRACT.md §36, its amendment "the source
popover"; docs/peps/0015-source-precedence.md), measured in headless Chromium on the built kit against an oracle
(tests/browser/source_popover_oracle.mjs: the fixtures' own JSON with precedence.js's pick() and conflict(), never the
popover's code).

    ~/psu-atlas/.venv/bin/python tests/browser/source_popover_checks.py [OUT_DIR]     # after npm run build

RobotParts asked for it: right-clicking a value its sources disagree on (or the value's item menu) should show every
source; the value's pill opens the same menu. Fixtures: tests/browser/fixtures/source-popover/ (page.html;
part.base reads the source-precedence fixture's part.json unchanged: a made-up actuator, four sources, one private;
parts.base / parts.json: a record per part, two such values per row, a numeric column, an undeclared source, an entry's
own unit and address, a relative address). What is measured:
  - where it opens: a right-click on such a value in the table, the cards, the record page and the side peek, and the
    ContextMenu key and Shift+F10 on the focused row, card or field (the record's and the peek's are tab stops); a touch
    long-press (sources.js hands it over); never on Shift + right-click
  - one row per source that states the value, in precedence order (role menuitemradio, the nominal one checked), each
    with its name, its rung's label, its value as stated (text and unit), its basis, note and date; its link (a
    menuitem, a new tab) only when the address is a link target, a private address as plain text; the nominal row
    marked "nominal", a disagreeing one "differs" (tinted as a source's column tints it), a hand-picked one pinned
  - picking a row calls el.setPrecedence({ov: {<row>: <source>}}) (the dropdown's path; the precedence's own source
    clears the pick), the value follows pick(), and "Back to precedence" appears with a pick and clears it; a pick is
    the row's, and the popover says so when the row has another such value
  - the keyboard: focus moves into it, arrows, Home and End move through its items, Enter picks, Escape closes it and
    gives focus back; the contextmenu a menu key may raise after it is swallowed
  - a value with one source or none, and a plain cell, keep today's menu: the "where this value comes from" popover, the
    peek field's own item menu, or the browser's
  - light and dark at 1280 and 390 px: inside the viewport (a sheet on a phone), no sideways scroll on the page or in it,
    readable text (contrast >= 4.5) on the nominal, a disagreeing and an agreeing row, the differs tint visible
Serves the repo root on a free 127.0.0.1 port, stops that server when done, writes OUT_DIR/source-popover-checks.json
and screenshots (default reports/media/source-popover) and exits 1 if any check fails.
"""

from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "source-popover"
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "browser" / "fixtures"
PART_JSON = FIX / "source-precedence" / "part.json"
PARTS_JSON = FIX / "source-popover" / "parts.json"
PAGE = "/tests/browser/fixtures/source-popover/page.html"
WAIT = 30000
checks: list[dict] = []

PART = json.loads(PART_JSON.read_text(encoding="utf-8"))
PARTS = json.loads(PARTS_JSON.read_text(encoding="utf-8"))


def oracle(path, order=None, ov=None):
    """The oracle's answer for one precedence state (source_popover_oracle.mjs)."""
    out = subprocess.run(["node", str(ROOT / "tests" / "browser" / "source_popover_oracle.mjs"), str(path), json.dumps({"order": order, "ov": ov or {}})],
                         capture_output=True, text=True, cwd=str(ROOT), check=True)
    return json.loads(out.stdout)


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"
READY = "() => window.kitReady && window.v && window.v.dataset.view && window.v.querySelector('.dv-view') && window.v.querySelector('.dv-view').children.length"


def settle(page, n=3):
    for _ in range(n):
        page.evaluate(SETTLE)


def fresh(page, base, query=""):
    """The page with no state: no hash, nothing kept in this viewer's storage, the first view."""
    url = f"{base}{PAGE}{('?' + query) if query else ''}"
    page.goto(url)
    page.wait_for_function(READY, timeout=WAIT)
    page.evaluate("() => localStorage.clear()")
    page.goto(url)
    page.wait_for_function(READY, timeout=WAIT)
    settle(page)
    # every call into el.setPrecedence (the dropdown's path, CONTRACT §36), and whether each contextmenu was taken
    page.evaluate("""() => { const v = window.v; window.__calls = []; const orig = v.setPrecedence;
      v.setPrecedence = function (p) { window.__calls.push(JSON.parse(JSON.stringify(p))); return orig.call(this, p); };
      window.__menus = []; window.addEventListener('contextmenu', (e) => window.__menus.push({ prevented: e.defaultPrevented, button: e.button }));
      window.__srcopen = 0; document.addEventListener('data-sources-open', () => { window.__srcopen += 1; }); }""")


def view(page, name, ready):
    """Open the preset `name` and wait for its drawing (`ready`: a selector inside the element)."""
    page.evaluate("(n) => window.v.selectView(n)", name)
    page.wait_for_function("([n, sel]) => window.v.view && window.v.view.name === n && window.v.querySelector(sel)", arg=[name, ready], timeout=WAIT)
    settle(page)


POP = """() => {
  const m = document.querySelector('.dv-itemmenu.dv-src-pop');
  if (!m) return null;
  const t = (el) => (el ? el.textContent.replace(/\\s+/g, ' ').trim() : null);
  const items = [...m.querySelectorAll('[role^="menuitem"], [role="separator"]')].map((el) => {
    const role = el.getAttribute('role');
    const base = { tag: el.tagName.toLowerCase(), role };
    if (role === 'separator') return { ...base, kind: 'sep' };
    if (el.matches('[data-src-back]')) return { ...base, kind: 'back', text: t(el) };
    if (role === 'menuitemradio') {
      const b = el.querySelector('.dv-src-pop-basis');
      return { ...base, kind: 'radio', source: el.dataset.source || null, checked: el.getAttribute('aria-checked'), state: el.dataset.srcState || null,
        name: t(el.querySelector('.dv-src-pop-name')), rung: t(el.querySelector('.dv-src-pop-rung')), val: t(el.querySelector('.dv-src-pop-val')),
        nominal: t(el.querySelector('.dv-src-pop-nominal')), differs: t(el.querySelector('.dv-src-pop-differs')), pin: !!el.querySelector('.dv-src-pin'),
        basis: b ? b.dataset.basis || null : null, basisText: t(b), asof: t(el.querySelector('.dv-src-pop-asof')), note: t(el.querySelector('.dv-src-pop-note')),
        addr: t(el.querySelector('.dv-src-pop-addr')), anchors: el.querySelectorAll('a').length };
    }
    if (el.matches('a[data-src-link]')) return { ...base, kind: 'link', source: el.dataset.srcLink, href: el.href, target: el.target, rel: el.rel, text: t(el) };
    return { ...base, kind: 'other', text: t(el), add: el.hasAttribute('data-add-dashboard') };
  });
  const r = m.getBoundingClientRect();
  const focus = document.activeElement;
  const out = [...m.querySelectorAll('[role^="menuitem"]')].filter((el) => { const b = el.getBoundingClientRect(); return b.left < r.left - 0.5 || b.right > r.right + 0.5; }).length;
  return { label: m.getAttribute('aria-label'), role: m.getAttribute('role'), title: t(m.querySelector('.dv-itemmenu-title')), note: t(m.querySelector('.dv-itemmenu-note')),
    items, focused: m.contains(focus) ? [...m.querySelectorAll('[role^="menuitem"]')].indexOf(focus) : -1,
    rect: { left: r.left, right: r.right, top: r.top, bottom: r.bottom }, scrollW: m.scrollWidth, clientW: m.clientWidth, vw: document.documentElement.clientWidth, vh: innerHeight,
    pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth, sheet: m.classList.contains('dv-sheet'), outside: out,
    menus: document.querySelectorAll('.dv-itemmenu').length };
}"""
SRCMENU = "() => { const m = document.querySelector('.dv-srcmenu'); return m ? m.textContent.replace(/\\s+/g, ' ').trim() : null; }"


def pop(page):
    return page.evaluate(POP)


def wait_pop(page, timeout=3000):
    try:
        page.wait_for_selector(".dv-itemmenu.dv-src-pop", timeout=timeout)
    except Exception:  # noqa: BLE001 - absent is a result
        return None
    settle(page, 1)
    return pop(page)


def close(page):
    """Shut whatever popover is open with a press outside it (never Escape: with no menu open, Escape steps the side peek
    back or closes it)."""
    page.evaluate("() => document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, composed: true }))")
    try:
        page.wait_for_function("() => !document.querySelector('.dv-itemmenu') && !document.querySelector('.dv-srcmenu')", timeout=3000)
    except Exception:  # noqa: BLE001
        pass
    settle(page, 1)


SCROLL_IDLE = """(sel) => new Promise((resolve) => {
  const el = document.querySelector(sel);
  if (!el) { resolve(false); return; }
  // WHY centred: a table's frozen first column covers whatever is scrolled to the box's left edge
  el.scrollIntoView({ block: 'center', inline: 'center' });
  let last = performance.now();
  const on = () => { last = performance.now(); };
  addEventListener('scroll', on, true);
  const tick = () => { if (performance.now() - last > 150) { removeEventListener('scroll', on, true); resolve(true); } else requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
})"""


def right_click(page, selector, shift=False):
    """A right-click on the element, centred in its scroll boxes first and only once they stop scrolling (WHY: the
    "where this value comes from" popover closes on any scroll, by design). A missing element is a FAIL."""
    loc = page.locator(selector).first
    try:
        loc.wait_for(state="attached", timeout=3000)
    except Exception:  # noqa: BLE001 - absent is a result
        check(f"right-click: {selector} is there to right-click", False, None)
        return False
    page.evaluate(SCROLL_IDLE, selector)
    loc.click(button="right", modifiers=["Shift"] if shift else None)
    settle(page, 1)
    return True


def click(page, selector, what):
    """Click an item of the open popover (or any element): a missing one is a FAIL, never a crash."""
    loc = page.locator(selector).first
    try:
        loc.wait_for(state="visible", timeout=3000)
    except Exception:  # noqa: BLE001 - absent is a result
        check(f"{what}: {selector} is there to click", False, None)
        return False
    loc.click()
    settle(page)
    return True


def focus(page, selector, what):
    """Focus an element (a row, a card, a field); a missing one is a FAIL."""
    loc = page.locator(selector).first
    try:
        loc.wait_for(state="attached", timeout=3000)
    except Exception:  # noqa: BLE001
        check(f"{what}: {selector} is there to focus", False, None)
        return False
    loc.focus()
    return True


def last_menu(page):
    return page.evaluate("() => window.__menus.slice(-1)[0] || null")


def calls(page):
    return page.evaluate("() => window.__calls.slice()")


def label_of(url):
    return url[len("https://"):] if url.startswith("https://") else url[len("http://"):] if url.startswith("http://") else url


def popover_ok(tag, what, p, want, *, title=None, prop_label=None, data_url=None, own=None):
    """The open popover against the oracle's answer for one value (`want`: its rows[row][property])."""
    if not p:
        check(f"{tag}: {what}: the source popover opens", False, None)
        return
    radios = [i for i in p["items"] if i["kind"] == "radio"]
    srcs = want["sources"]
    ent = want["entries"]
    check(f"{tag}: {what}: a menu (role=menu) named \"Sources of …\", with one menuitemradio per source that states the value, in precedence order",
          p["role"] == "menu" and (p["label"] or "").startswith("Sources of") and (title is None or title in (p["label"] or "")) and [r["source"] for r in radios] == srcs,
          {"label": p["label"], "got": [r["source"] for r in radios], "want": srcs})
    check(f"{tag}: {what}: exactly the nominal row is checked (pick(): {want['nominal']}, {want['via']})",
          [r["checked"] for r in radios] == ["true" if s == want["nominal"] else "false" for s in srcs], [r["checked"] for r in radios])
    check(f"{tag}: {what}: each row's state is shown / differs / agrees as the oracle says",
          [r["state"] for r in radios] == [ent[s]["state"] for s in srcs], {"got": [r["state"] for r in radios], "want": [ent[s]["state"] for s in srcs]})
    marks_bad = [r["source"] for r in radios if (r["nominal"] == "nominal") != (r["source"] == want["nominal"])
                 or (r["differs"] == "differs") != (ent[r["source"]]["state"] == "differs")
                 or (r["nominal"] not in (None, "nominal")) or (r["differs"] not in (None, "differs"))
                 or r["pin"] != (r["source"] == want["nominal"] and want["via"] == "override")]
    check(f"{tag}: {what}: \"nominal\" on the row in use, \"differs\" on each that disagrees, the pin only on a row picked by hand", not marks_bad,
          marks_bad or None)
    rows_bad = []
    for r in radios:
        e = ent.get(r["source"]) or {}
        val = e["text"] + (" " + e["unit"] if e.get("unit") else "")
        ok = (r["name"] == e["name"] and r["rung"] == e["rungLabel"] and r["val"] == val and r["basis"] == e["basis"]
              and (e["basis"] is None or e["basis"] in (r["basisText"] or "")) and r["note"] == e["note"]
              and ((r["asof"] is None) if e["asOf"] is None else (r["asof"] or "").endswith(e["asOf"]))
              and r["addr"] == e["addr"] and r["anchors"] == 0)
        if not ok:
            rows_bad.append({"source": r["source"], "got": {k: r[k] for k in ("name", "rung", "val", "basis", "basisText", "asof", "note", "addr", "anchors")},
                             "want": {"name": e["name"], "rung": e["rungLabel"], "val": val, "basis": e["basis"], "asOf": e["asOf"], "note": e["note"], "addr": e["addr"]}})
    check(f"{tag}: {what}: each row says its source's name and rung, the value as stated with its unit, its basis, note and date, a private address as text",
          not rows_bad, rows_bad[:3] or None)
    # the links: a menu item of its own right after its source's row, only for an address that is a link target
    seq = [i for i in p["items"] if i["kind"] in ("radio", "link")]
    links_bad = []
    for k, it in enumerate(seq):
        if it["kind"] != "radio":
            continue
        e = ent.get(it["source"]) or {}
        nxt = seq[k + 1] if k + 1 < len(seq) else None
        has = nxt is not None and nxt["kind"] == "link" and nxt["source"] == it["source"]
        if e.get("link"):
            href = urllib.parse.urljoin(data_url, e["link"]) if data_url else e["link"]
            if not (has and nxt["role"] == "menuitem" and nxt["href"] == href and nxt["target"] == "_blank" and "noopener" in (nxt["rel"] or "")
                    and (nxt["text"] or "").startswith(label_of(e["link"]))):
                links_bad.append({"source": it["source"], "want": href, "got": nxt})
        elif has:
            links_bad.append({"source": it["source"], "want": None, "got": nxt})
    stray = [i for i in p["items"] if i["kind"] == "link" and not (ent.get(i["source"]) or {}).get("link")]
    check(f"{tag}: {what}: a source whose address is a link target has its link (a menuitem, a new tab, labelled by the address) right after its row; no other has one",
          not links_bad and not stray, (links_bad + stray)[:3] or None)
    back = [i for i in p["items"] if i["kind"] == "back"]
    check(f"{tag}: {what}: \"Back to precedence\" is there exactly when the row is picked by hand, first",
          (len(back) == 1 and p["items"][0]["kind"] == "back" and back[0]["role"] == "menuitem" and "Back to precedence" in (back[0]["text"] or "")) if want["via"] == "override" else not back,
          back or None)
    roles_bad = [i for i in p["items"] if i["kind"] != "sep" and i["role"] not in ("menuitem", "menuitemradio")]
    check(f"{tag}: {what}: every item is a menuitem or a menuitemradio (and the title says what it lists)",
          not roles_bad and (p["title"] or "").find(f"{len(srcs)} sources") >= 0 and (title is None or title in (p["title"] or "")) and (prop_label is None or prop_label in (p["title"] or "")),
          {"title": p["title"], "roles": roles_bad[:2]})
    check(f"{tag}: {what}: it says a pick is the row's exactly when the row has another value with several sources",
          bool(p["note"]) == bool(want["rowWide"]) and (not p["note"] or "every value" in p["note"]), p["note"])
    if own is not None:
        rest = p["items"][[k for k, i in enumerate(p["items"]) if i["kind"] in ("radio", "link")][-1] + 1:]
        check(f"{tag}: {what}: the element's own items follow its sources, after a separator ({own})",
              len(rest) >= 2 and rest[0]["kind"] == "sep" and any(i["kind"] == "other" and i["add"] for i in rest[1:]), rest)


def cell_text(page, selector):
    return page.evaluate("(s) => { const el = document.querySelector(s); if (!el) return null; const c = el.cloneNode(true); for (const x of c.querySelectorAll('.dv-src-dd, .dv-src-pin')) x.remove(); return c.textContent.replace(/\\s+/g, ' ').trim(); }", selector)


def nominal_text(want, rid, prop):
    w = want["rows"][rid][prop]
    if w["nominal"] is None:
        return "—"
    e = w["entries"][w["nominal"]]
    return e["text"] + (" " + e["unit"] if e.get("unit") else "")


def unchanged(tag, page, selector, what, expect_srcmenu):
    """A right-click on a value with one source or none, or a plain cell: today's menu, never the source popover."""
    page.evaluate("() => { window.__srcopen = 0; }")
    right_click(page, selector)
    page.wait_for_timeout(250)
    p = pop(page)
    sm = page.evaluate(SRCMENU)
    lm = last_menu(page)
    if expect_srcmenu:
        check(f"{tag}: {what}: keeps today's menu, the \"where this value comes from\" popover ({expect_srcmenu}), no source popover",
              p is None and sm is not None and expect_srcmenu in sm and page.evaluate("() => window.__srcopen") == 1, {"pop": bool(p), "srcmenu": sm})
    else:
        check(f"{tag}: {what}: keeps today's menu (the browser's): no source popover, no provenance popover, nothing prevented",
              p is None and sm is None and lm and not lm["prevented"], {"pop": bool(p), "srcmenu": sm, "menu": lm})
    close(page)


def run_table(page, base, tag, shots):
    """The Datasheet table: every value with two or more sources, picks by mouse and keyboard, today's menus beside it."""
    fresh(page, base, "toolbar=bar")
    data_url = page.evaluate("() => window.v.dataUrl")
    want = oracle(PART_JSON)
    rows = want["rows"]
    many = sorted(rid for rid, ps in rows.items() if ps["nominal"]["popover"])
    marked = page.evaluate("() => [...window.v.querySelectorAll('.dv-view [data-src-row]')].map((n) => [n.dataset.srcRow, n.dataset.srcP, n.tagName.toLowerCase()])")
    check(f"{tag}: table: exactly the values two or more sources state are marked (a td each, data-src-row / data-src-p)",
          sorted(m[0] for m in marked) == many and all(m[1] == "nominal" and m[2] == "td" for m in marked), {"got": marked, "want": many})
    title = {r["id"]: r["field"] for r in PART["rows"]}
    for rid in many:
        right_click(page, f'#pop tbody tr[data-id="{rid}"] td[data-col="nominal"]')
        p = wait_pop(page)
        popover_ok(tag, f"table, right-click {rid}", p, rows[rid]["nominal"], title=title[rid], prop_label="Nominal", data_url=data_url)
        lm = last_menu(page)
        check(f"{tag}: table, {rid}: the right-click is the popover's (prevented), and the \"where this value comes from\" popover stays shut",
              lm and lm["prevented"] and page.evaluate(SRCMENU) is None and (p or {}).get("menus") == 1, {"menu": lm, "srcmenu": page.evaluate(SRCMENU)})
        if rid == "peak_torque":
            page.mouse.move(1, 1)
            shots.append(f"{tag}-table-popover.png".replace(" ", "-"))
            page.screenshot(path=str(OUT / shots[-1]), full_page=False)
        close(page)
    # a right-click on the value's text itself (inside the cell) opens it too
    right_click(page, '#pop tbody tr[data-id="max_speed"] td[data-col="nominal"] .dv-value')
    check(f"{tag}: table: a right-click on the value's own text opens it as well", wait_pop(page) is not None and page.evaluate(SRCMENU) is None, None)
    close(page)

    # ---- today's menus, unchanged: one source, a plain §22 cell, no source at all, a plain text cell
    unchanged(tag, page, '#pop tbody tr[data-id="kt"] td[data-col="nominal"] .dv-value', "table, kt (one source)", "Acme datasheet rev C")
    unchanged(tag, page, '#pop tbody tr[data-id="protection"] td[data-col="nominal"] .dv-value', "table, protection (one private source)", "Supplier chat")
    unchanged(tag, page, '#pop tbody tr[data-id="encoder"] td[data-col="nominal"] .dv-value', "table, encoder (a plain cell with one source)", "Acme datasheet rev C")
    unchanged(tag, page, '#pop tbody tr[data-id="backlash"] td[data-col="nominal"]', "table, backlash (no source states it)", None)
    unchanged(tag, page, '#pop tbody tr[data-id="peak_torque"] td[data-col="field"]', "table, the Field cell beside it", None)
    # Shift + right-click: the browser's own menu, always
    right_click(page, '#pop tbody tr[data-id="peak_torque"] td[data-col="nominal"]', shift=True)
    page.wait_for_timeout(250)
    lm = last_menu(page)
    check(f"{tag}: table: Shift + right-click is the browser's own menu (nothing opens, nothing prevented)", pop(page) is None and page.evaluate(SRCMENU) is None and lm and not lm["prevented"], lm)
    close(page)
    # the value's pill opens this same menu: one menu, not two
    click(page, '#pop tbody tr[data-id="peak_torque"] button.dv-src-dd', tag)
    check(f"{tag}: table: the value's pill opens the same menu", page.evaluate("() => !!document.querySelector('.dv-itemmenu.dv-src-pop')"), None)
    close(page)

    # ---- a pick with the mouse: rated_current -> the shop listing; the value follows pick(); the row is pinned
    page.evaluate("() => { window.__events = []; window.v.addEventListener('data-views-precedence', (e) => window.__events.push(e.detail)); }")
    right_click(page, '#pop tbody tr[data-id="rated_current"] td[data-col="nominal"]')
    wait_pop(page)
    click(page, '.dv-src-pop [role=menuitemradio][data-source="listing"]', tag)
    ov = {"rated_current": "listing"}
    after = oracle(PART_JSON, want["order"], ov)
    check(f"{tag}: pick by mouse: one call, el.setPrecedence({{ov: {{rated_current: 'listing'}}}}) (the dropdown's path)", calls(page) == [{"ov": ov}], calls(page))
    check(f"{tag}: pick by mouse: the popover closes", page.evaluate("() => !document.querySelector('.dv-itemmenu')"), None)
    got = {rid: cell_text(page, f'#pop tbody tr[data-id="{rid}"] td[data-col="nominal"]') for rid in rows}
    want_txt = {rid: nominal_text(after, rid, "nominal") for rid in rows}
    check(f"{tag}: pick by mouse: every row's Nominal is pick()'s (only rated_current moved, to the listing's 10 A)", got == want_txt, {k: (got[k], want_txt[k]) for k in got if got[k] != want_txt[k]} or None)
    check(f"{tag}: pick by mouse: the URL and the event carry it", page.evaluate("() => location.hash").find("picks=rated_current:listing") >= 0
          and page.evaluate("() => (window.__events.slice(-1)[0] || {}).ov") == ov, page.evaluate("() => location.hash"))
    right_click(page, '#pop tbody tr[data-id="rated_current"] td[data-col="nominal"]')
    p = wait_pop(page)
    popover_ok(tag, "table, rated_current picked by hand", p, after["rows"]["rated_current"]["nominal"], title="Rated phase current", prop_label="Nominal", data_url=data_url)
    shots.append(f"{tag}-table-picked.png".replace(" ", "-"))
    page.mouse.move(1, 1)
    page.screenshot(path=str(OUT / shots[-1]), full_page=False)
    # clicking the row already in use changes nothing
    n = len(calls(page))
    click(page, '.dv-src-pop [role=menuitemradio][data-source="listing"]', tag)
    check(f"{tag}: clicking the row already in use calls nothing and closes the popover", len(calls(page)) == n and pop(page) is None, calls(page)[n:])
    # Back to precedence clears this row's pick only
    right_click(page, '#pop tbody tr[data-id="rated_current"] td[data-col="nominal"]')
    wait_pop(page)
    click(page, ".dv-src-pop [data-src-back]", tag)
    check(f"{tag}: Back to precedence: el.setPrecedence({{ov: {{rated_current: null}}}}), the pick gone", calls(page)[-1:] == [{"ov": {"rated_current": None}}] and page.evaluate("() => window.v.precedence.ov") == {},
          calls(page)[-1:])
    # picking precedence's own source while picked by hand clears the pick (the dropdown's rule), never pins it
    page.evaluate("() => window.v.setPrecedence({ ov: { rated_current: 'chat' } })")
    settle(page)
    right_click(page, '#pop tbody tr[data-id="rated_current"] td[data-col="nominal"]')
    wait_pop(page)
    click(page, '.dv-src-pop [role=menuitemradio][data-source="datasheet"]', tag)
    check(f"{tag}: picking precedence's own source (the datasheet) clears the pick: {{ov: {{rated_current: null}}}}", calls(page)[-1:] == [{"ov": {"rated_current": None}}] and page.evaluate("() => window.v.precedence.ov") == {},
          calls(page)[-1:])

    # ---- the keyboard: the focused row, the ContextMenu key, arrows, Home, End, Enter; Escape; Shift+F10; the echo
    focus(page, '#pop tbody tr[data-id="max_speed"]', tag)
    page.keyboard.press("ContextMenu")
    # the contextmenu a menu key can raise right after it (button 0) is the open menu's: swallowed, the menu kept
    echo = page.evaluate("""() => { const m = document.querySelector('.dv-src-pop'); if (!m) return null; m.__mark = 1;
      const e = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, button: 0, clientX: 30, clientY: 30 });
      document.activeElement.dispatchEvent(e); return e.defaultPrevented; }""")
    p = wait_pop(page)
    kept = page.evaluate("() => { const m = document.querySelector('.dv-src-pop'); return !!m && m.__mark === 1 && m.contains(document.activeElement) && document.querySelectorAll('.dv-itemmenu').length === 1; }")
    check(f"{tag}: keyboard: the contextmenu a menu key raises after it is swallowed; the same menu stays, focus in it", echo and kept, {"prevented": echo, "kept": kept})
    popover_ok(tag, "keyboard (ContextMenu on the max_speed row)", p, rows["max_speed"]["nominal"], title="Max speed", data_url=data_url)
    seq = [i["kind"] + ":" + str(i.get("source")) for i in (p or {}).get("items", []) if i["kind"] in ("radio", "link", "back")]
    check(f"{tag}: keyboard: focus starts on the first item", p and p["focused"] == 0, p and p["focused"])
    page.keyboard.press("ArrowDown")
    f1 = pop(page)["focused"] if pop(page) else None
    page.keyboard.press("End")
    f_end = pop(page)["focused"] if pop(page) else None
    page.keyboard.press("Home")
    f_home = pop(page)["focused"] if pop(page) else None
    check(f"{tag}: keyboard: ArrowDown moves to the next item (the datasheet's link), End to the last, Home to the first", f1 == 1 and f_end == len(seq) - 1 and f_home == 0,
          {"seq": seq, "down": f1, "end": f_end, "home": f_home})
    target = seq.index("radio:chat") if "radio:chat" in seq else -1
    for _ in range(target):
        page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    settle(page)
    check(f"{tag}: keyboard: Enter on the chat's row picks it: el.setPrecedence({{ov: {{max_speed: 'chat'}}}})", target > 0 and calls(page)[-1:] == [{"ov": {"max_speed": "chat"}}], {"seq": seq, "calls": calls(page)[-1:]})
    back_to = page.evaluate("() => { const a = document.activeElement; return a ? [a.tagName, a.closest('tr[data-id]') ? a.closest('tr[data-id]').dataset.id : null] : null; }")
    check(f"{tag}: keyboard: after a pick the popover is closed and focus is back on the row", pop(page) is None and back_to == ["TR", "max_speed"], back_to)
    nominal = cell_text(page, '#pop tbody tr[data-id="max_speed"] td[data-col="nominal"]')
    check(f"{tag}: keyboard: the row now shows the chat's 3000 rpm", nominal == nominal_text(oracle(PART_JSON, want["order"], {"max_speed": "chat"}), "max_speed", "nominal"), nominal)
    page.keyboard.press("Shift+F10")
    p = wait_pop(page)
    check(f"{tag}: keyboard: Shift+F10 opens it too, the chat checked and pinned", p is not None and [i["source"] for i in p["items"] if i["kind"] == "radio" and i["checked"] == "true"] == ["chat"]
          and any(i["kind"] == "radio" and i["pin"] for i in p["items"]), p and [(i.get("source"), i.get("checked"), i.get("pin")) for i in p["items"] if i["kind"] == "radio"])
    page.keyboard.press("Escape")
    settle(page, 1)
    back_to = page.evaluate("() => { const a = document.activeElement; return a ? [a.tagName, a.closest('tr[data-id]') ? a.closest('tr[data-id]').dataset.id : null] : null; }")
    check(f"{tag}: keyboard: Escape closes it and gives focus back to the row", pop(page) is None and back_to == ["TR", "max_speed"], back_to)
    focus(page, '#pop tbody tr[data-id="kt"]', tag)
    page.keyboard.press("ContextMenu")
    page.wait_for_timeout(250)
    check(f"{tag}: keyboard: on a row whose value has one source the key keeps today's popover", pop(page) is None and (page.evaluate(SRCMENU) or "").find("Acme datasheet rev C") >= 0, page.evaluate(SRCMENU))
    close(page)

    # ---- a touch long-press (sources.js's own, handed to the popover: iOS raises no contextmenu)
    page.evaluate("() => { window.v.setPrecedence({ ov: null }); }")
    settle(page)
    press = """(sel) => { const el = document.querySelector(sel); el.scrollIntoView({ block: 'center' }); const r = el.getBoundingClientRect();
      const o = { bubbles: true, composed: true, pointerType: 'touch', pointerId: 9, isPrimary: true, clientX: r.left + 4, clientY: r.top + 4 };
      window.__press = (type, dx = 0) => el.dispatchEvent(new PointerEvent(type, { ...o, clientX: o.clientX + dx })); window.__press('pointerdown'); }"""
    page.evaluate(press, '#pop tbody tr[data-id="peak_torque"] td[data-col="nominal"] .dv-value')
    page.wait_for_timeout(300)
    early = pop(page) is not None
    page.wait_for_timeout(500)
    p = pop(page)
    check(f"{tag}: long-press: a 550 ms touch press on such a value opens the source popover (not before 300 ms), never the provenance popover",
          not early and p is not None and page.evaluate(SRCMENU) is None, {"early": early, "pop": bool(p)})
    page.evaluate("() => window.__press('pointerup')")
    clicked = page.evaluate("""(sel) => { const el = document.querySelector(sel); const e = new MouseEvent('click', { bubbles: true, cancelable: true }); el.dispatchEvent(e); return e.defaultPrevented; }""",
                            '#pop tbody tr[data-id="peak_torque"] td[data-col="nominal"] .dv-value')
    settle(page, 1)
    check(f"{tag}: long-press: the click that ends it is swallowed (no peek opens)", clicked and page.evaluate("() => window.v.peeked") is None, {"prevented": clicked, "peek": page.evaluate("() => !!window.v.peeked")})
    close(page)
    page.evaluate(press, '#pop tbody tr[data-id="kt"] td[data-col="nominal"] .dv-value')
    page.wait_for_timeout(800)
    check(f"{tag}: long-press on a value with one source: today's provenance popover", pop(page) is None and page.evaluate(SRCMENU) is not None, page.evaluate(SRCMENU))
    page.evaluate("() => window.__press('pointerup')")
    close(page)
    page.evaluate(press, '#pop tbody tr[data-id="peak_torque"] td[data-col="nominal"] .dv-value')
    page.evaluate("() => window.__press('pointermove', 14)")
    page.wait_for_timeout(800)
    check(f"{tag}: long-press: a press that moves more than 10 px opens nothing", pop(page) is None and page.evaluate(SRCMENU) is None, None)
    page.evaluate("() => window.__press('pointerup')")
    close(page)


def run_views(page, base, tag, shots):
    """The cards, the record page and the side peek: the same popover, the same picks."""
    fresh(page, base, "toolbar=bar")
    data_url = page.evaluate("() => window.v.dataUrl")
    want = oracle(PART_JSON)
    rows = want["rows"]
    many = sorted(rid for rid, ps in rows.items() if ps["nominal"]["popover"])

    # ---- cards
    view(page, "Cards", ".dv-cards-card[data-id]")
    cards = page.evaluate("""() => ({ drawn: [...window.v.querySelectorAll('.dv-view .dv-cards-card[data-id]')].map((c) => c.dataset.id),
      marked: [...window.v.querySelectorAll('.dv-view [data-src-row]')].map((n) => [n.dataset.srcRow, n.dataset.srcP, n.classList.contains('dv-cards-prop'), !!n.closest('.dv-cards-card[data-id="' + n.dataset.srcRow + '"]')]) })""")
    check(f"{tag}: cards: of the cards drawn, exactly the values two or more sources state are marked (the card's property line)",
          sorted(m[0] for m in cards["marked"]) == sorted(set(cards["drawn"]) & set(many)) and "peak_torque" in cards["drawn"] and all(m[1] == "nominal" and m[2] and m[3] for m in cards["marked"]), cards)
    right_click(page, '#pop .dv-cards-card[data-id="peak_torque"] [data-src-p="nominal"]')
    popover_ok(tag, "cards, right-click peak_torque", wait_pop(page), rows["peak_torque"]["nominal"], title="Peak torque", prop_label="Nominal", data_url=data_url)
    page.mouse.move(1, 1)
    shots.append(f"{tag}-cards-popover.png".replace(" ", "-"))
    page.screenshot(path=str(OUT / shots[-1]), full_page=False)
    click(page, '.dv-src-pop [role=menuitemradio][data-source="datasheet"]', tag)
    after = oracle(PART_JSON, want["order"], {"peak_torque": "datasheet"})
    check(f"{tag}: cards: a pick calls el.setPrecedence({{ov: {{peak_torque: 'datasheet'}}}})", calls(page)[-1:] == [{"ov": {"peak_torque": "datasheet"}}], calls(page)[-1:])
    shown = cell_text(page, '#pop .dv-cards-card[data-id="peak_torque"] [data-src-p="nominal"] .dv-value')
    check(f"{tag}: cards: the card shows the datasheet's value now ({after['rows']['peak_torque']['nominal']['entries']['datasheet']['text']})",
          (shown or "").startswith(after["rows"]["peak_torque"]["nominal"]["entries"]["datasheet"]["text"]), shown)
    focus(page, '#pop .dv-cards-card[data-id="mass"]', tag)
    page.keyboard.press("ContextMenu")
    p = wait_pop(page)
    popover_ok(tag, "cards, the ContextMenu key on the focused mass card", p, rows["mass"]["nominal"], title="Mass", data_url=data_url)
    check(f"{tag}: cards: focus is in it", p and p["focused"] == 0, p and p["focused"])
    page.keyboard.press("Escape")
    settle(page, 1)
    check(f"{tag}: cards: Escape gives focus back to the card", page.evaluate("() => { const a = document.activeElement; return !!a && a.matches('.dv-cards-card[data-id=\"mass\"]'); }"), None)
    unchanged(tag, page, '#pop .dv-cards-card[data-id="kt"] .dv-cards-prop .dv-value', "cards, kt (one source)", "Acme datasheet rev C")

    # ---- the record page
    page.evaluate("() => window.v.setPrecedence({ ov: null })")
    view(page, "Record", ".dv-record-sheet .dv-record-field")
    page.locator('#pop .dv-record-pick select, #pop .dv-record-item[data-id="rated_current"]').first.wait_for(state="attached", timeout=WAIT)
    if page.locator('#pop .dv-record-item[data-id="rated_current"]').is_visible():
        click(page, '#pop .dv-record-item[data-id="rated_current"]', tag)
    else:
        page.locator("#pop .dv-record-pick select").select_option("rated_current")
    settle(page)
    field = page.evaluate("() => { const f = window.v.querySelector('.dv-record-field[data-p=\"nominal\"]'); return f ? { row: f.dataset.srcRow || null, p: f.dataset.srcP || null, tab: f.getAttribute('tabindex') } : null; }")
    check(f"{tag}: record: the Nominal field of rated_current is marked and a tab stop", field == {"row": "rated_current", "p": "nominal", "tab": "0"}, field)
    right_click(page, '#pop .dv-record-field[data-p="nominal"]')
    popover_ok(tag, "record, right-click rated_current's Nominal", wait_pop(page), rows["rated_current"]["nominal"], title="Rated phase current", prop_label="Nominal", data_url=data_url)
    page.mouse.move(1, 1)
    shots.append(f"{tag}-record-popover.png".replace(" ", "-"))
    page.screenshot(path=str(OUT / shots[-1]), full_page=False)
    click(page, '.dv-src-pop [role=menuitemradio][data-source="chat"]', tag)
    check(f"{tag}: record: a pick calls el.setPrecedence({{ov: {{rated_current: 'chat'}}}}) and the sheet shows the chat's 11 A",
          calls(page)[-1:] == [{"ov": {"rated_current": "chat"}}] and (cell_text(page, '#pop .dv-record-field[data-p="nominal"] td .dv-value') or "").startswith("11"),
          {"calls": calls(page)[-1:], "shown": cell_text(page, '#pop .dv-record-field[data-p="nominal"] td')})
    focus(page, '#pop .dv-record-field[data-p="nominal"]', tag)
    page.keyboard.press("ContextMenu")
    p = wait_pop(page)
    popover_ok(tag, "record, the ContextMenu key on the focused field", p, oracle(PART_JSON, want["order"], {"rated_current": "chat"})["rows"]["rated_current"]["nominal"], title="Rated phase current", data_url=data_url)
    page.keyboard.press("Escape")
    settle(page, 1)
    check(f"{tag}: record: Escape gives focus back to the field", page.evaluate("() => { const a = document.activeElement; return !!a && a.matches('.dv-record-field[data-p=\"nominal\"]'); }"), None)
    if page.locator('#pop .dv-record-item[data-id="kt"]').is_visible():
        click(page, '#pop .dv-record-item[data-id="kt"]', tag)
    else:
        page.locator("#pop .dv-record-pick select").select_option("kt")
    settle(page)
    kt = page.evaluate("() => { const f = window.v.querySelector('.dv-record-field[data-p=\"nominal\"]'); return f ? [f.hasAttribute('data-src-row'), f.getAttribute('tabindex')] : null; }")
    check(f"{tag}: record: a field with one source is not marked and no tab stop", kt == [False, None], kt)
    unchanged(tag, page, '#pop .dv-record-field[data-p="nominal"] td .dv-value', "record, kt (one source)", "Acme datasheet rev C")

    # ---- the side peek (from the table)
    page.evaluate("() => window.v.setPrecedence({ ov: null })")
    view(page, "Datasheet", "tbody tr[data-id]")
    page.evaluate("() => window.v.openPeek('rated_current', { column: 'nominal' })")
    page.wait_for_selector('#pop .dv-peek .dv-peek-field[data-p="nominal"]', timeout=WAIT)
    settle(page)
    field = page.evaluate("() => { const f = window.v.querySelector('.dv-peek .dv-peek-field[data-p=\"nominal\"]'); return f ? { row: f.dataset.srcRow || null, p: f.dataset.srcP || null, tab: f.getAttribute('tabindex') } : null; }")
    check(f"{tag}: peek: the Nominal field is marked and a tab stop", field == {"row": "rated_current", "p": "nominal", "tab": "0"}, field)
    right_click(page, '#pop .dv-peek .dv-peek-field[data-p="nominal"] td')
    popover_ok(tag, "peek, right-click rated_current's Nominal", wait_pop(page), rows["rated_current"]["nominal"], title="Rated phase current", prop_label="Nominal", data_url=data_url, own="Add to dashboard…")
    page.mouse.move(1, 1)
    shots.append(f"{tag}-peek-popover.png".replace(" ", "-"))
    page.screenshot(path=str(OUT / shots[-1]), full_page=False)
    click(page, '.dv-src-pop [role=menuitemradio][data-source="listing"]', tag)
    peek_val = cell_text(page, '#pop .dv-peek .dv-peek-field[data-p="nominal"] td .dv-value')
    table_val = cell_text(page, '#pop tbody tr[data-id="rated_current"] td[data-col="nominal"]')
    check(f"{tag}: peek: a pick calls el.setPrecedence({{ov: {{rated_current: 'listing'}}}}); the peek and the table behind it show the listing's 10 A",
          calls(page)[-1:] == [{"ov": {"rated_current": "listing"}}] and (peek_val or "").startswith("10") and table_val == "10 A", {"calls": calls(page)[-1:], "peek": peek_val, "table": table_val})
    focus(page, '#pop .dv-peek .dv-peek-field[data-p="nominal"]', tag)
    page.keyboard.press("ContextMenu")
    p = wait_pop(page)
    popover_ok(tag, "peek, the ContextMenu key on the focused field", p, oracle(PART_JSON, want["order"], {"rated_current": "listing"})["rows"]["rated_current"]["nominal"], title="Rated phase current", data_url=data_url, own="Add to dashboard…")
    page.keyboard.press("Escape")
    settle(page, 1)
    check(f"{tag}: peek: Escape closes the popover (not the peek) and gives focus back to the field",
          pop(page) is None and page.evaluate("() => !!window.v.peeked && document.activeElement && document.activeElement.matches('.dv-peek .dv-peek-field[data-p=\"nominal\"]')"), None)
    page.evaluate("() => window.v.openPeek('kt', { column: 'nominal' })")
    page.wait_for_selector('#pop .dv-peek .dv-peek-field[data-p="nominal"]', timeout=WAIT)
    settle(page)
    unchanged(tag, page, '#pop .dv-peek .dv-peek-field[data-p="nominal"] td .dv-value', "peek, kt (one source)", "Acme datasheet rev C")
    right_click(page, '#pop .dv-peek .dv-peek-field[data-p="nominal"] th')
    settle(page, 1)
    own = page.evaluate("() => { const m = document.querySelector('.dv-itemmenu'); return m ? { pop: m.classList.contains('dv-src-pop'), add: !!m.querySelector('[data-add-dashboard]'), radios: m.querySelectorAll('[role=menuitemradio]').length } : null; }")
    check(f"{tag}: peek: a one-source field's label keeps its own item menu (Add to dashboard…), no sources in it", own == {"pop": False, "add": True, "radios": 0}, own)
    close(page)


def run_parts(page, base, tag, shots):
    """A record per part: two values with several sources in a row (a pick is the row's), a numeric column, an
    undeclared source, an entry's own unit and address, a relative address resolved against the data file."""
    fresh(page, base, "src=parts.base&toolbar=bar")
    data_url = page.evaluate("() => window.v.dataUrl")
    want = oracle(PARTS_JSON)
    rows = want["rows"]
    pops = sorted((rid, p) for rid, ps in rows.items() for p, w in ps.items() if w["popover"])
    marked = sorted(page.evaluate("() => [...window.v.querySelectorAll('.dv-view [data-src-row]')].map((n) => [n.dataset.srcRow, n.dataset.srcP])"))
    check(f"{tag}: parts: exactly the values two or more sources state are marked, in both columns", [tuple(m) for m in marked] == pops, {"got": marked, "want": pops})
    names = {r["id"]: r["name"] for r in PARTS["rows"]}
    labels = {p: PARTS["properties"][p]["label"] for p in PARTS["properties"]}
    for rid, prop in pops:
        right_click(page, f'#pop tbody tr[data-id="{rid}"] td[data-col="{prop}"]')
        p = wait_pop(page)
        popover_ok(tag, f"parts, right-click {rid}.{prop}", p, rows[rid][prop], title=names[rid], prop_label=labels[prop], data_url=data_url)
        if (rid, prop) == ("qdd-a", "mass"):
            page.mouse.move(1, 1)
            shots.append(f"{tag}-parts-popover.png".replace(" ", "-"))
            page.screenshot(path=str(OUT / shots[-1]), full_page=False)
        close(page)
    unchanged(tag, page, '#pop tbody tr[data-id="qdd-b"] td[data-col="mass"]', "parts, qdd-b mass (one source)", "Maker's page")
    unchanged(tag, page, '#pop tbody tr[data-id="qdd-c"] td[data-col="torque"]', "parts, qdd-c torque (a plain cell with one source)", "Maker's page")
    unchanged(tag, page, '#pop tbody tr[data-id="qdd-c"] td[data-col="mass"]', "parts, qdd-c mass (a plain number)", None)
    # a pick from the second column is the row's: both of qdd-a's values follow pick()
    right_click(page, '#pop tbody tr[data-id="qdd-a"] td[data-col="mass"]')
    wait_pop(page)
    click(page, '.dv-src-pop [role=menuitemradio][data-source="maker"]', tag)
    after = oracle(PARTS_JSON, want["order"], {"qdd-a": "maker"})
    got = {p: cell_text(page, f'#pop tbody tr[data-id="qdd-a"] td[data-col="{p}"]') for p in ("torque", "mass")}
    want_txt = {p: nominal_text(after, "qdd-a", p) for p in ("torque", "mass")}
    check(f"{tag}: parts: a pick on the Mass calls el.setPrecedence({{ov: {{'qdd-a': 'maker'}}}}), and the row's two values follow pick() ({want_txt})",
          calls(page)[-1:] == [{"ov": {"qdd-a": "maker"}}] and got == want_txt, {"calls": calls(page)[-1:], "got": got})
    right_click(page, '#pop tbody tr[data-id="qdd-a"] td[data-col="torque"]')
    popover_ok(tag, "parts, qdd-a torque after the row's pick", wait_pop(page), after["rows"]["qdd-a"]["torque"], title="QDD A", prop_label="Peak torque", data_url=data_url)
    close(page)
    view(page, "Record", ".dv-record-sheet .dv-record-field")
    right_click(page, '#pop .dv-record-field[data-p="mass"]')
    popover_ok(tag, "parts, record: right-click the Mass field", wait_pop(page), after["rows"]["qdd-a"]["mass"], title="QDD A", prop_label="Mass", data_url=data_url)
    close(page)


CONTRAST = """(el) => {
  const parse = (c) => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const over = (top, under) => ({ r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1 });
  const bgOf = (n0) => { const layers = []; for (let n = n0; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let acc = { r: 255, g: 255, b: 255, a: 1 }; if (matchMedia('(prefers-color-scheme: dark)').matches && !layers.some((l) => l.a >= 1)) acc = { r: 0, g: 0, b: 0, a: 1 };
    for (const l of layers.reverse()) acc = over(l, acc); return acc; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  if (!el) return null;
  const bg = bgOf(el), fg = over(parse(getComputedStyle(el).color), bg);
  const L1 = lum(fg), L2 = lum(bg);
  return { ratio: (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05), bg: [bg.r, bg.g, bg.b].map(Math.round), lum: L2 };
}"""


def run_theme(page, base, tag, shots, dark):
    """Light or dark, wide or a phone: the popover inside the viewport, no sideways scroll, readable, the tint visible."""
    fresh(page, base, "toolbar=bar")
    differs_bg = None
    for rid in ("peak_torque", "rated_torque"):
        right_click(page, f'#pop tbody tr[data-id="{rid}"] td[data-col="nominal"]')
        p = wait_pop(page)
        if not p:
            check(f"{tag}: {rid}: the popover opens", False, None)
            continue
        page.mouse.move(1, 1)
        page.evaluate("() => { const m = document.querySelector('.dv-src-pop'); if (m) { m.tabIndex = -1; m.focus(); } }")
        settle(page, 1)
        p = pop(page)
        r = p["rect"]
        inside = r["left"] >= -0.5 and r["top"] >= -0.5 and r["right"] <= p["vw"] + 0.5 and r["bottom"] <= p["vh"] + 0.5
        check(f"{tag}: {rid}: the popover is inside the viewport, no sideways scroll on the page or inside it, every item inside its box",
              inside and p["pageOverflow"] <= 0 and p["scrollW"] <= p["clientW"] + 1 and p["outside"] == 0,
              {"rect": r, "vw": p["vw"], "pageOverflow": p["pageOverflow"], "scrollW": p["scrollW"], "clientW": p["clientW"], "outside": p["outside"]})
        if p["vw"] < 480:
            check(f"{tag}: {rid}: on a phone it is a sheet with 8 px gutters", p["sheet"] and abs(r["left"] - 8) <= 1 and abs(p["vw"] - r["right"] - 8) <= 1, r)
        menu_bg = page.evaluate(CONTRAST, page.query_selector(".dv-src-pop"))
        check(f"{tag}: {rid}: the popover is drawn in the {'dark' if dark else 'light'} scheme's tokens", menu_bg and ((menu_bg["lum"] < 0.25) if dark else (menu_bg["lum"] > 0.7)), menu_bg)
        parts = [(sel, page.evaluate(CONTRAST, page.query_selector(sel))) for sel in (
            ".dv-src-pop [role=menuitemradio][data-src-state='shown'] .dv-src-pop-name",
            ".dv-src-pop [role=menuitemradio][data-src-state='shown'] .dv-src-pop-val",
            ".dv-src-pop [role=menuitemradio][data-src-state='shown'] .dv-src-pop-nominal",
            ".dv-src-pop [role=menuitemradio][data-src-state='shown'] .dv-src-pop-rung",
            ".dv-src-pop [role=menuitemradio][data-src-state='shown'] .dv-src-pop-asof",
            ".dv-src-pop a[data-src-link]",
            ".dv-itemmenu.dv-src-pop .dv-itemmenu-title",
        ) + ((".dv-src-pop [role=menuitemradio][data-src-state='differs'] .dv-src-pop-name",
              ".dv-src-pop [role=menuitemradio][data-src-state='differs'] .dv-src-pop-val",
              ".dv-src-pop [role=menuitemradio][data-src-state='differs'] .dv-src-pop-differs",
              ".dv-src-pop [role=menuitemradio][data-src-state='differs'] .dv-src-pop-rung",
              ".dv-src-pop [role=menuitemradio][data-src-state='differs'] .dv-src-pop-asof",
              ".dv-src-pop [role=menuitemradio][data-src-state='differs'] .dv-src-pop-addr") if rid == "peak_torque" else
             (".dv-src-pop [role=menuitemradio][data-src-state='agrees'] .dv-src-pop-name",
              ".dv-src-pop [role=menuitemradio][data-src-state='agrees'] .dv-src-pop-val",
              ".dv-src-pop [role=menuitemradio][data-src-state='agrees'] .dv-src-pop-rung"))]
        weak = [(s, c) for s, c in parts if not c or c["ratio"] < 4.5]
        check(f"{tag}: {rid}: every line of the {'nominal and disagreeing' if rid == 'peak_torque' else 'nominal and agreeing'} rows reads at contrast >= 4.5", not weak, weak[:3] or None)
        if rid == "peak_torque":
            differs_bg = page.evaluate(CONTRAST, page.query_selector(".dv-src-pop [role=menuitemradio][data-src-state='differs']"))
            shots.append(f"{tag}-theme.png".replace(" ", "-"))
            page.screenshot(path=str(OUT / shots[-1]), full_page=False)
        else:
            agrees_bg = page.evaluate(CONTRAST, page.query_selector(".dv-src-pop [role=menuitemradio][data-src-state='agrees']"))
            check(f"{tag}: a disagreeing row is tinted (its background is not an agreeing row's), as a source's column tints it",
                  differs_bg and agrees_bg and differs_bg["bg"] != agrees_bg["bg"], {"differs": differs_bg, "agrees": agrees_bg})
        close(page)


def main() -> int:
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    shots: list[str] = []
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + PAGE, timeout=1)
                break
            except Exception:  # noqa: BLE001 - not up yet
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for width, scheme in ((1280, "light"), (390, "dark"), (1280, "dark"), (390, "light")):
                tag = f"{width} px {scheme}"
                ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
                page = ctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                scenarios = [("theme", lambda: run_theme(page, base, tag, shots, scheme == "dark"))]
                if (width, scheme) in ((1280, "light"), (390, "dark")):
                    scenarios += [("table", lambda: run_table(page, base, tag, shots)), ("cards, record and peek", lambda: run_views(page, base, tag, shots)),
                                  ("parts", lambda: run_parts(page, base, tag, shots))]
                for name, run in scenarios:
                    try:
                        run()
                    except Exception as err:  # noqa: BLE001 - a scenario that stops is a FAIL, and the next one runs
                        check(f"{tag}: the {name} checks ran to the end", False, f"{type(err).__name__}: {str(err).splitlines()[0][:300]}")
                check(f"{tag}: no page error", not errors, errors[:3])
                ctx.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "source-popover-checks.json").write_text(json.dumps({"checks": checks, "shots": shots}, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} source-popover checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
