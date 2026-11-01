"""Source precedence (docs/CONTRACT.md §36, docs/peps/0015-source-precedence.md), measured in headless Chromium on the
built kit, against an oracle computed here from the fixture's own JSON (never from the kit's code).

    ~/psu-atlas/.venv/bin/python tests/browser/source_precedence_checks.py [OUT_DIR]     # after npm run build

The fixture (tests/browser/fixtures/source-precedence/) is a MADE-UP actuator whose fields have values from four sources
(a bench test, the maker's datasheet, a shop listing and a supplier chat with no public URL), declared out of ladder
order, with conflicts; and a made-up CRM contact (the second consumer). What is measured:
  - the Nominal value of every row is pick(): the row's override, else the first source in precedence order with a value
  - the "Nominal source" column: one source is a plain link (a private one a plain label); 2+ sources a pill on the value
  - an override (the pill's menu, by mouse and by keyboard) changes that row only and is in the URL (picks=)
  - the Sources view (a tab on both toolbars): one column per source, in precedence order; dragging a header (and Alt+arrows
    on it) reorders precedence for every row, the nominals following the oracle; conflicts marked exactly where conflict()
    says; another view returns to the normal columns
  - "changed from default · Reset" and "N chosen by hand · Clear" appear and clear; the state survives a reload, from the
    URL and from the per-viewer storage; the event; stated values never altered
  - light and dark at 1280 and 390 px: no sideways page scroll, the conflict tint visible and its text readable
Serves the repo root on a free 127.0.0.1 port, stops that server when done, writes OUT_DIR/source-precedence-checks.json
and screenshots (default reports/media/source-precedence) and exits 1 if any check fails.
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
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "source-precedence"
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "browser" / "fixtures" / "source-precedence"
PAGE = "/tests/browser/fixtures/source-precedence/part.html"
WAIT = 30000
checks: list[dict] = []

PART = json.loads((FIX / "part.json").read_text(encoding="utf-8"))
CONTACT = json.loads((FIX / "contact.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the oracle, from the fixture's JSON alone
def empty(v):
    return v is None or v == "" or v == []


def ladder_order(data):
    rank = {r["id"]: i for i, r in enumerate(data.get("ladder") or [])}
    ids = list(data["sources"].keys())
    return sorted(ids, key=lambda s: (rank.get(data["sources"][s].get("rung"), len(rank)), ids.index(s)))


def entries(cell):
    """{source: entry} for the entries that state a value, the first per source, in the cell's order."""
    out = {}
    for e in (cell or {}).get("sources") or []:
        if e.get("source") and e["source"] not in out and not empty(e.get("value")):
            out[e["source"]] = e
    return out


def prec(cell, order):
    st = entries(cell)
    for s in list(order) + [s for s in st if s not in order]:
        if s in st:
            return s
    return None


def pick(cell, order, ov, rid):
    st = entries(cell)
    o = (ov or {}).get(rid)
    return o if o in st else prec(cell, order)


def key(e, cell):
    return json.dumps([e.get("value"), e.get("unit", cell.get("unit"))], sort_keys=True)


def conflict(cell):
    st = entries(cell)
    return len({key(e, cell) for e in st.values()}) > 1


def move(order, s, to):
    rest = [x for x in order if x != s]
    rest.insert(max(0, min(to, len(rest))), s)
    return rest


def multi(row, prop="nominal"):
    c = row.get(prop)
    return isinstance(c, dict) and isinstance(c.get("sources"), list) and len(c["sources"]) > 0


def expected(data, order, ov, prop="nominal", unit_prop="unit"):
    """{row id: {text, source}} the Nominal column must read: the picked entry's text, a space and the row's unit."""
    out = {}
    for r in data["rows"]:
        c = r.get(prop)
        unit = r.get(unit_prop) if unit_prop else None
        if multi(r, prop):
            s = pick(c, order, ov, r["id"])
            if s is None:
                out[r["id"]] = {"text": "—", "source": None}
                continue
            e = entries(c)[s]
            text = e.get("text") if isinstance(e.get("text"), str) else str(e.get("value"))
            out[r["id"]] = {"text": text + (" " + unit if unit else ""), "source": data["sources"][s]["name"] if s in data["sources"] else s}
        else:
            text = c.get("text") if isinstance(c, dict) and isinstance(c.get("text"), str) else str(c.get("value") if isinstance(c, dict) else c)
            out[r["id"]] = {"text": text + (" " + unit if unit else ""), "source": c.get("source") if isinstance(c, dict) else None}
    return out


DEFAULT = ladder_order(PART)
S = PART["sources"]
ROWS = {r["id"]: r for r in PART["rows"]}
MULTI2 = sorted(r["id"] for r in PART["rows"] if multi(r) and len(entries(r["nominal"])) >= 2)
SINGLE = sorted(r["id"] for r in PART["rows"] if multi(r) and len(entries(r["nominal"])) == 1)
CONFLICTS = sorted(r["id"] for r in PART["rows"] if multi(r) and conflict(r["nominal"]))

# ---------------------------------------------------------------- what the page says
SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"
NOMINALS = """() => Object.fromEntries([...document.querySelectorAll('#part tbody tr[data-id]')].map((tr) => {
  const td = tr.querySelector('td[data-col="nominal"]');
  const host = td && (td.matches('[data-provenance]') ? td : td.querySelector('[data-provenance]'));
  let source = null; try { source = host ? JSON.parse(host.getAttribute('data-provenance')).source || null : null; } catch { source = 'unreadable'; }
  const c = td && td.cloneNode(true);
  if (c) for (const x of c.querySelectorAll('.dv-src-dd, .dv-src-pin')) x.remove();
  return [tr.dataset.id, { text: c ? c.textContent.replace(/\\s+/g, ' ').trim() : null, source }];
}))"""
SRC_CELLS = """() => Object.fromEntries([...document.querySelectorAll('#part tbody tr[data-id]')].map((tr) => {
  const td = tr.querySelector('td[data-col$="@source"]');
  if (!td) return [tr.dataset.id, null];
  const a = td.querySelector('a.dv-src-link'), label = td.querySelector('.dv-src-label'), dd = tr.querySelector('button.dv-src-dd');
  return [tr.dataset.id, { a: a ? { text: a.textContent.trim(), href: a.getAttribute('href') } : null, label: label ? label.textContent.trim() : null,
    dd: dd ? { text: dd.textContent.replace(/\\s+/g, ' ').trim(), conflict: dd.hasAttribute('data-conflict'), expanded: dd.getAttribute('aria-expanded') } : null,
    pin: !!tr.querySelector('.dv-src-pin'), anyA: td.querySelectorAll('a').length }];
}))"""
SOURCE = '[data-col^="nominal@"]:not([data-col="nominal@source"])'
MATRIX = """() => { const SOURCE = '[data-col^="nominal@"]:not([data-col="nominal@source"])'; return {
  heads: [...document.querySelectorAll(`#part thead th${SOURCE}`)].map((th) => th.dataset.col.slice(8)),
  headText: Object.fromEntries([...document.querySelectorAll(`#part thead th${SOURCE}`)].map((th) => [th.dataset.col.slice(8), { label: (th.querySelector('.dv-th-label') || {}).textContent || null }])),
  nominalSource: !!document.querySelector('#part thead th[data-col="nominal@source"]'),
  rows: Object.fromEntries([...document.querySelectorAll('#part tbody tr[data-id]')].map((tr) => [tr.dataset.id, { conflict: !!tr.querySelector('button.dv-src-dd[data-conflict]'),
    cells: Object.fromEntries([...tr.querySelectorAll(`td${SOURCE}`)].map((td) => [td.dataset.col.slice(8), { state: td.dataset.srcState || null, text: td.textContent.replace(/\\s+/g, ' ').trim(), override: td.hasAttribute('data-override') }])) }])),
}; }"""
STATUS = "() => { const s = document.querySelector('#part .dv-status'); return s ? s.textContent.replace(/\\s+/g, ' ').trim() : ''; }"
HASH = "() => Object.fromEntries(new URLSearchParams(location.hash.slice(1)))"


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def settle(page, n=3):
    for _ in range(n):
        page.evaluate(SETTLE)


def open_page(page, base, query="", hash_=""):
    page.goto(f"{base}{PAGE}{('?' + query) if query else ''}{('#' + hash_) if hash_ else ''}")
    page.wait_for_function("() => window.kitReady && window.v && window.v.dataset.view && window.v.querySelector('tbody tr[data-id]')", timeout=WAIT)
    settle(page)


def sources_view(page, on):
    page.evaluate(f"() => window.v.selectView('{'Sources' if on else 'Datasheet'}')")
    settle(page)


def nominal_ok(tag, what, page, order, ov, data=PART):
    want = expected(data, order, ov)
    got = page.evaluate(NOMINALS)
    bad = {k: {"want": want[k], "got": got.get(k)} for k in want if got.get(k) != want[k]}
    check(f"{tag}: {what}: every row's Nominal is pick() (value as stated, its unit, its source's name)", not bad and set(got) == set(want), bad or None)
    return got


def menu_items(page):
    return page.evaluate("""() => { const m = document.querySelector('.dv-itemmenu[role=menu]'); if (!m) return null;
      return { items: [...m.querySelectorAll('[role=menuitemradio]')].map((b) => ({ source: b.dataset.source, checked: b.getAttribute('aria-checked'), text: b.textContent.replace(/\\s+/g, ' ').trim() })),
        back: !!m.querySelector('[data-src-back]'), focused: m.contains(document.activeElement) }; }""")


def run_interactions(page, base, tag, shots):
    """The full sequence: default, override (mouse and keyboard), the Sources view, drag, keys, reset, clear, reload."""
    page.evaluate("() => { window.__events = []; window.v.addEventListener('data-views-precedence', (e) => window.__events.push(e.detail)); }")
    # ---- default
    check(f"{tag}: the oracle's default order is the ladder's, not the declaration's", DEFAULT == ["bench", "datasheet", "listing", "chat"] and list(S) != DEFAULT, DEFAULT)
    pre = page.evaluate("() => window.v.precedence")
    check(f"{tag}: el.precedence: order and default are the ladder order; no overrides", pre and pre.get("order") == DEFAULT and pre.get("default") == DEFAULT and pre.get("ov") == {}, pre)
    nominal_ok(tag, "default", page, DEFAULT, {})
    head = page.evaluate("() => (document.querySelector('#part thead th[data-col=\"nominal@source\"]') || {}).textContent")
    check(f"{tag}: one \"Nominal source\" column, right after the Nominal", (head or "").strip() == "Nominal source" and page.evaluate(
        "() => { const ths = [...document.querySelectorAll('#part thead tr.dv-hleaf th')].map((t) => t.dataset.col); return ths.indexOf('nominal@source') === ths.indexOf('nominal') + 1; }"), head)
    cells = page.evaluate(SRC_CELLS)
    with_dd = sorted(k for k, c in cells.items() if c and c["dd"])
    check(f"{tag}: a dropdown on exactly the rows with 2+ sources ({len(MULTI2)})", with_dd == MULTI2, {"got": with_dd, "want": MULTI2})
    for rid in SINGLE:
        s = next(iter(entries(ROWS[rid]["nominal"])))
        url = S[s].get("url") or ""
        c = cells.get(rid) or {}
        if url.startswith("https://"):
            check(f"{tag}: {rid}: one source is a plain link to it ({S[s]['name']})", c.get("a") == {"text": S[s]["name"], "href": url} and not c.get("dd"), c)
        else:
            check(f"{tag}: {rid}: one private source (no public URL) is a plain label, no <a>", c.get("label") == S[s]["name"] and c.get("anyA") == 0 and not c.get("dd"), c)
    enc = cells.get("encoder") or {}
    check(f"{tag}: a plain §22 cell (one source, no sources list) shows its own source as a link", enc.get("a") == {"text": "Acme datasheet rev C", "href": "https://example.com/acme/qdd80-datasheet-rev-c.pdf"} and not enc.get("dd"), enc)
    flagged = sorted(k for k, c in cells.items() if c and c["dd"] and c["dd"]["conflict"])
    check(f"{tag}: the dropdowns of exactly the rows whose sources disagree are marked ({', '.join(CONFLICTS)})", flagged == CONFLICTS, {"got": flagged, "want": CONFLICTS})
    st = page.evaluate(STATUS)
    check(f"{tag}: the default state says nothing about precedence in the status line", "changed from default" not in st and "chosen by hand" not in st, st)
    check(f"{tag}: the default state writes nothing to the URL", not ({"sources", "picks"} & set(page.evaluate(HASH))), page.evaluate(HASH))
    shots.append(f"{tag}-default.png")
    page.screenshot(path=str(OUT / shots[-1]), full_page=False)

    # ---- an override with the mouse: rated_current -> the shop listing
    before = page.evaluate(NOMINALS)
    page.locator('#part tbody tr[data-id="rated_current"] button.dv-src-dd').click()
    page.wait_for_selector(".dv-itemmenu[role=menu]", timeout=WAIT)
    m = menu_items(page)
    want_items = [s for s in DEFAULT if s in entries(ROWS["rated_current"]["nominal"])]
    check(f"{tag}: the dropdown lists every source of the row, in precedence order, the shown one checked",
          m and [i["source"] for i in m["items"]] == want_items and [i["checked"] for i in m["items"]] == ["true" if s == pick(ROWS["rated_current"]["nominal"], DEFAULT, {}, "rated_current") else "false" for s in want_items], m)
    shots.append(f"{tag}-dropdown.png")
    page.screenshot(path=str(OUT / shots[-1]), full_page=False)
    page.locator('.dv-itemmenu [role=menuitemradio][data-source="listing"]').click()
    settle(page)
    ov = {"rated_current": "listing"}
    after = nominal_ok(tag, "override rated_current -> listing", page, DEFAULT, ov)
    moved = sorted(k for k in after if after.get(k) != before.get(k))
    check(f"{tag}: the override changes only that row", moved == ["rated_current"], moved)
    check(f"{tag}: the override is in the URL (picks=rated_current:listing)", page.evaluate(HASH).get("picks") == "rated_current:listing", page.evaluate(HASH))
    cells = page.evaluate(SRC_CELLS)
    check(f"{tag}: the overridden row is pinned, and only it", sorted(k for k, c in cells.items() if c and c["pin"]) == ["rated_current"], {k: c["pin"] for k, c in cells.items() if c})
    st = page.evaluate(STATUS)
    check(f"{tag}: the status line says \"1 chosen by hand\" with a Clear button", "1 chosen by hand" in st and page.locator("#part .dv-status button[data-sources-clear]").count() == 1, st)
    ev = page.evaluate("() => window.__events.slice(-1)[0] || null")
    check(f"{tag}: data-views-precedence fired with the new picks", ev and ev.get("ov") == ov and ev.get("order") == DEFAULT, ev)

    # ---- an override with the keyboard: max_speed, Enter, arrows to the second source, Enter; then Escape returns focus
    page.locator('#part tbody tr[data-id="max_speed"] button.dv-src-dd').focus()
    page.keyboard.press("Enter")
    page.wait_for_selector(".dv-itemmenu[role=menu]", timeout=WAIT)
    m = menu_items(page)
    check(f"{tag}: keyboard: Enter opens the dropdown with focus inside it", m and m["focused"], m)
    page.keyboard.press("Escape")
    settle(page, 1)
    focus_back = page.evaluate("() => { const a = document.activeElement; return !!(a && a.matches('button.dv-src-dd') && a.closest('tr[data-id=\"max_speed\"]')); }")
    check(f"{tag}: keyboard: Escape closes it and gives focus back to its button", page.locator(".dv-itemmenu").count() == 0 and focus_back, focus_back)
    page.keyboard.press("Enter")
    page.wait_for_selector(".dv-itemmenu[role=menu]", timeout=WAIT)
    order_ms = [s for s in DEFAULT if s in entries(ROWS["max_speed"]["nominal"])]
    first = menu_items(page)["items"][0]["source"]
    # a source with an address has its link as a menu item of its own, right after its row (§36): the arrows walk those too
    for _ in range(4):
        page.keyboard.press("ArrowDown")
        if page.evaluate("() => document.activeElement.dataset.source") == order_ms[1]:
            break
    page.keyboard.press("Enter")
    settle(page)
    ov["max_speed"] = order_ms[1]
    check(f"{tag}: keyboard: arrows and Enter pick the second source for that row", first == order_ms[0] and page.evaluate("() => window.v.precedence.ov") == ov, page.evaluate("() => window.v.precedence.ov"))
    nominal_ok(tag, "keyboard override max_speed", page, DEFAULT, ov)
    check(f"{tag}: the status line says \"2 chosen by hand\"", "2 chosen by hand" in page.evaluate(STATUS), page.evaluate(STATUS))

    # ---- Back to precedence from the dropdown
    page.locator('#part tbody tr[data-id="max_speed"] button.dv-src-dd').click()
    page.wait_for_selector(".dv-itemmenu [data-src-back]", timeout=WAIT)
    page.locator(".dv-itemmenu [data-src-back]").click()
    settle(page)
    del ov["max_speed"]
    check(f"{tag}: Back to precedence clears that row's pick only", page.evaluate("() => window.v.precedence.ov") == ov, page.evaluate("() => window.v.precedence.ov"))

    # ---- the Sources view
    sources_view(page, True)
    mx = page.evaluate(MATRIX)
    check(f"{tag}: Sources: one column per source, in precedence order, in place of the Nominal source column",
          mx["heads"] == DEFAULT and not mx["nominalSource"], {"heads": mx["heads"], "nominalSource": mx["nominalSource"]})
    for s in DEFAULT:
        h = mx["headText"].get(s) or {}
        check(f"{tag}: Sources: {s}'s header names it", (h.get("label") or "").strip() == S[s]["name"], h)
    def matrix_ok(what, order, ov_now):
        mx = page.evaluate(MATRIX)
        rows_conf = sorted(k for k, r in mx["rows"].items() if r["conflict"])
        check(f"{tag}: {what}: rows marked as in conflict are exactly conflict()'s", rows_conf == CONFLICTS, {"got": rows_conf, "want": CONFLICTS})
        bad = []
        for rid, r in ROWS.items():
            if not multi(r):
                continue
            st_ = entries(r["nominal"])
            shown = pick(r["nominal"], order, ov_now, rid)
            for s in DEFAULT:
                cell = mx["rows"].get(rid, {}).get("cells", {}).get(s)
                if s not in st_:
                    want = "none"
                elif s == shown:
                    want = "shown"
                elif key(st_[s], r["nominal"]) != key(st_[shown], r["nominal"]):
                    want = "differs"
                else:
                    want = "agrees"
                text_ok = cell is not None and (cell["text"].startswith(st_[s]["text"]) if s in st_ else True)
                override_ok = cell is not None and (cell["override"] == (want == "shown" and ov_now.get(rid) == s))
                if not cell or cell["state"] != want or not text_ok or not override_ok:
                    bad.append({"row": rid, "source": s, "want": want, "got": cell})
        check(f"{tag}: {what}: every source cell is shown / differs / agrees / none as the oracle says, its value as stated", not bad, bad[:4] or None)
    matrix_ok("Sources", DEFAULT, ov)
    shots.append(f"{tag}-manage.png")
    page.screenshot(path=str(OUT / shots[-1]), full_page=False)

    # ---- drag a header, the ordinary drag: the supplier chat to the front (on a phone, where the table scrolls in its box, one place up:
    # onto its neighbour, the two headers on screen together)
    wide = page.evaluate("() => window.innerWidth") >= 700
    target = "bench" if wide else "listing"
    page.locator('#part thead th[data-col="nominal@chat"]').scroll_into_view_if_needed()
    settle(page, 1)
    src = page.locator('#part thead th[data-col="nominal@chat"]').bounding_box()
    dst = page.locator(f'#part thead th[data-col="nominal@{target}"]').bounding_box()
    # the drop lands on what is under the pointer: on a phone the frozen first column lies over the left of the columns scrolled under it
    edge = max(dst["x"], page.locator('#part thead th[data-col="field"]').bounding_box()["x"] + page.locator('#part thead th[data-col="field"]').bounding_box()["width"]) + 4
    page.mouse.move(src["x"] + src["width"] / 2, src["y"] + 6)
    page.mouse.down()
    steps = 12
    for i in range(1, steps + 1):
        x = src["x"] + src["width"] / 2 + (edge - (src["x"] + src["width"] / 2)) * i / steps
        page.mouse.move(x, src["y"] + 6)
    page.mouse.up()
    settle(page)
    order = move(DEFAULT, "chat", DEFAULT.index(target))
    got = page.evaluate("() => window.v.precedence.order")
    check(f"{tag}: dragging the chat's header onto the {target}'s puts it there for every row: {order}", got == order, got)
    check(f"{tag}: ... the source columns follow", page.evaluate(MATRIX)["heads"] == order, page.evaluate(MATRIX)["heads"])
    nominal_ok(tag, "after the drag", page, order, ov)
    matrix_ok("after the drag", order, ov)
    check(f"{tag}: the order is in the URL (sources={','.join(order)})", page.evaluate(HASH).get("sources") == ",".join(order), page.evaluate(HASH))
    st = page.evaluate(STATUS)
    check(f"{tag}: the status line says \"changed from default · Reset\"", "changed from default" in st and page.locator("#part .dv-status button[data-sources-reset]").count() == 1, st)
    ev = page.evaluate("() => window.__events.slice(-1)[0] || null")
    want_changed = sorted(rid for rid, r in ROWS.items() if multi(r) and entries(r["nominal"]).get(pick(r["nominal"], DEFAULT, ov, rid)) is not None
                          and pick(r["nominal"], DEFAULT, ov, rid) != pick(r["nominal"], order, ov, rid)
                          and key(entries(r["nominal"])[pick(r["nominal"], DEFAULT, ov, rid)], r["nominal"]) != key(entries(r["nominal"])[pick(r["nominal"], order, ov, rid)], r["nominal"]))
    want_held = sorted(rid for rid, r in ROWS.items() if multi(r) and ov.get(rid) in entries(r["nominal"])
                       and key(entries(r["nominal"])[prec(r["nominal"], DEFAULT)], r["nominal"]) != key(entries(r["nominal"])[prec(r["nominal"], order)], r["nominal"]))
    check(f"{tag}: the event names the rows whose value changed and the rows an override held", ev and sorted(ev.get("changed") or []) == want_changed and sorted(ev.get("held") or []) == want_held,
          {"got": ev and {"changed": ev.get("changed"), "held": ev.get("held")}, "want": {"changed": want_changed, "held": want_held}})
    shots.append(f"{tag}-dragged.png")
    page.screenshot(path=str(OUT / shots[-1]), full_page=False)

    # ---- the keyboard's way: the datasheet one place up, Alt+← on its header
    page.locator('#part thead th[data-col="nominal@datasheet"]').focus()
    page.keyboard.press("Alt+ArrowLeft")
    settle(page)
    order = move(order, "datasheet", order.index("datasheet") - 1)
    check(f"{tag}: Alt+← on a header moves a source one place up: {order}", page.evaluate("() => window.v.precedence.order") == order, page.evaluate("() => window.v.precedence.order"))
    still = page.evaluate("() => { const a = document.activeElement; return !!(a && a.closest && a.closest('th[data-col=\"nominal@datasheet\"]')); }")
    check(f"{tag}: ... and the focus stays on that source's header, so the next press moves it again", still, still)
    nominal_ok(tag, "after Alt+←", page, order, ov)

    # ---- another view: the normal columns, the order kept
    sources_view(page, False)
    mx = page.evaluate(MATRIX)
    check(f"{tag}: the Datasheet view has the Nominal source column, no source columns, the order kept",
          mx["nominalSource"] and not mx["heads"] and page.evaluate("() => window.v.precedence.order") == order, mx["heads"])

    # ---- the state survives a reload: from the URL, then from the per-viewer storage
    page.reload()
    page.wait_for_function("() => window.kitReady && window.v && window.v.dataset.view && window.v.querySelector('tbody tr[data-id]')", timeout=WAIT)
    settle(page)
    got = page.evaluate("() => window.v.precedence")
    check(f"{tag}: a reload keeps the order and the picks (the URL)", got and got["order"] == order and got["ov"] == ov, got)
    nominal_ok(tag, "after a reload", page, order, ov)
    stored = page.evaluate("() => Object.keys(localStorage).filter((k) => k.startsWith('data-ui/sources/'))")
    check(f"{tag}: the state is kept in this viewer's storage too (data-ui/sources/…)", len(stored) == 1, stored)
    query = urllib.parse.urlparse(page.url).query
    open_page(page, base, query)
    got = page.evaluate("() => window.v.precedence")
    check(f"{tag}: opened again with no hash, the page reads the viewer's own state", got and got["order"] == order and got["ov"] == ov, got)

    # ---- Reset and Clear
    page.locator("#part .dv-status button[data-sources-reset]").click()
    settle(page)
    got = page.evaluate("() => window.v.precedence")
    st = page.evaluate(STATUS)
    check(f"{tag}: Reset puts the default order back and clears its note and its URL key", got["order"] == DEFAULT and "changed from default" not in st and "sources" not in page.evaluate(HASH), {"order": got["order"], "status": st})
    check(f"{tag}: ... and keeps the picks", got["ov"] == ov, got["ov"])
    page.locator("#part .dv-status button[data-sources-clear]").click()
    settle(page)
    got = page.evaluate("() => window.v.precedence")
    st = page.evaluate(STATUS)
    check(f"{tag}: Clear removes every pick, its note and its URL key", got["ov"] == {} and "chosen by hand" not in st and "picks" not in page.evaluate(HASH), {"ov": got["ov"], "status": st})
    nominal_ok(tag, "back to the default", page, DEFAULT, {})
    stored = page.evaluate("() => Object.keys(localStorage).filter((k) => k.startsWith('data-ui/sources/')).map((k) => localStorage.getItem(k))")
    check(f"{tag}: the default state leaves nothing in storage", stored == [] or all(json.loads(x) in (None, {}) for x in stored), stored)

    # ---- truthful: every stated value as the fixture states it, after every move
    raw = page.evaluate("() => window.v.data.rows.map((r) => [r.id, r.nominal && r.nominal.sources ? r.nominal.sources : null])")
    want_raw = [[r["id"], r["nominal"].get("sources") if isinstance(r["nominal"], dict) else None] for r in PART["rows"]]
    check(f"{tag}: no stated value was altered: every source entry is exactly the fixture's", raw == want_raw, None if raw == want_raw else raw[:2])


def run_toolbar(page, base, tag, full):
    """The Sources view is a view: on both toolbars it is reached the way any view is."""
    views = page.evaluate("() => window.v.presets.map((p) => p.name)")
    check(f"{tag}: the {'full' if full else 'bar'} toolbar: Sources follows the file's views", views == ["Datasheet", "Flat", "Cards", "Sources"], views)
    gone = page.evaluate("() => document.querySelectorAll('#part [data-sources], #part [data-bar=\"sources\"]').length + ('manageSources' in window.v ? 1 : 0)")
    check(f"{tag}: no Manage sources: no button, no property", gone == 0, gone)
    sources_view(page, True)
    check(f"{tag}: opened, the source columns drawn", page.evaluate(MATRIX)["heads"] == DEFAULT, page.evaluate(MATRIX)["heads"])
    sources_view(page, False)
    check(f"{tag}: and Datasheet again is the normal view", page.evaluate(MATRIX)["nominalSource"], page.evaluate(MATRIX))


CONTRAST = """(sel) => {
  const parse = (c) => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const over = (top, under) => ({ r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1 });
  const bgOf = (el) => { const layers = []; for (let n = el; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let acc = { r: 255, g: 255, b: 255, a: 1 }; if (matchMedia('(prefers-color-scheme: dark)').matches && !layers.some((l) => l.a >= 1)) acc = { r: 0, g: 0, b: 0, a: 1 };
    for (const l of layers.reverse()) acc = over(l, acc); return acc; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const el = document.querySelector(sel); if (!el) return null;
  const bg = bgOf(el), fg = over(parse(getComputedStyle(el).color), bg);
  const L1 = lum(fg), L2 = lum(bg);
  return { ratio: (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05), bg: [bg.r, bg.g, bg.b].map(Math.round), fg: [fg.r, fg.g, fg.b].map(Math.round) };
}"""


def run_theme(page, base, tag, shots):
    """Light or dark, wide or a phone: the default view and Sources drawn with tokens, readable, no sideways scroll."""
    nominal_ok(tag, "default", page, DEFAULT, {})
    overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    check(f"{tag}: the page never scrolls sideways (the table scrolls in its own box)", overflow <= 0, overflow)
    dd = page.evaluate(CONTRAST, '#part tbody tr[data-id="peak_torque"] button.dv-src-dd')
    check(f"{tag}: the conflict dropdown's text is readable (contrast ≥ 4.5)", dd and dd["ratio"] >= 4.5, dd)
    sources_view(page, True)
    overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    check(f"{tag}: Sources: the page still never scrolls sideways", overflow <= 0, overflow)
    differs = page.evaluate(CONTRAST, '#part tbody tr[data-id="peak_torque"] td[data-src-state="differs"]')
    agrees = page.evaluate(CONTRAST, '#part tbody tr[data-id="rated_torque"] td[data-src-state="agrees"]')
    check(f"{tag}: a differing source's cell is tinted (its background is not the agreeing cell's)", differs and agrees and differs["bg"] != agrees["bg"], {"differs": differs, "agrees": agrees})
    check(f"{tag}: ... and its text stays readable (contrast ≥ 4.5)", differs and differs["ratio"] >= 4.5, differs)
    shown = page.evaluate(CONTRAST, '#part tbody tr[data-id="peak_torque"] td[data-src-state="shown"]')
    check(f"{tag}: the shown source's cell is readable (contrast ≥ 4.5)", shown and shown["ratio"] >= 4.5, shown)
    # WHY computed, not only the attribute: a broken stylesheet rule beside it once left the state right and the outline gone
    ring = page.evaluate("() => getComputedStyle(document.querySelector('#part tbody tr[data-id=\"peak_torque\"] td[data-src-state=\"shown\"]')).boxShadow")
    check(f"{tag}: the shown source's cell is outlined", ring and ring != "none", ring)
    matrix_state = page.evaluate(MATRIX)
    check(f"{tag}: Sources draws its columns in the ladder order", matrix_state["heads"] == DEFAULT, matrix_state["heads"])
    shots.append(f"{tag}-manage.png")
    page.screenshot(path=str(OUT / shots[-1]), full_page=False)
    sources_view(page, False)


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
                open_page(page, base, "toolbar=bar")
                page.evaluate("() => localStorage.clear()")
                open_page(page, base, "toolbar=bar")
                run_theme(page, base, tag, shots)
                if (width, scheme) in ((1280, "light"), (390, "dark")):
                    run_interactions(page, base, tag, shots)
                    open_page(page, base, "toolbar=bar")
                    run_toolbar(page, base, f"{tag} bar", False)
                    page.evaluate("() => localStorage.clear()")
                    open_page(page, base, "toolbar=full")
                    run_toolbar(page, base, f"{tag} full", True)
                if (width, scheme) == (1280, "light"):
                    # ---- the second consumer: a CRM contact, its own ladder (their own words first), "Value source"
                    page.evaluate("() => localStorage.clear()")
                    page.goto(f"{base}{PAGE}?src=contact.base&id=part")
                    page.wait_for_function("() => window.kitReady && window.v && window.v.querySelector('tbody tr[data-id]')", timeout=WAIT)
                    settle(page)
                    corder = ladder_order(CONTACT)
                    got = page.evaluate("() => window.v.precedence")
                    check(f"{tag}: contact: the default order is its own ladder's ({corder})", got and got["order"] == corder, got)
                    head = page.evaluate("() => (document.querySelector('#part thead th[data-col=\"value@source\"]') || {}).textContent")
                    check(f"{tag}: contact: the column is named after its value column (\"Value source\")", (head or "").strip() == "Value source", head)
                    want = expected(CONTACT, corder, {}, prop="value", unit_prop=None)
                    got_vals = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#part tbody tr[data-id]')].map((tr) => { const c = tr.querySelector('td[data-col="value"]').cloneNode(true); for (const x of c.querySelectorAll('.dv-src-dd, .dv-src-pin')) x.remove(); return [tr.dataset.id, c.textContent.replace(/\\s+/g, ' ').trim()]; }))""")
                    check(f"{tag}: contact: every Value is pick() (their mail's surname, not the note's)", got_vals == {k: v["text"] for k, v in want.items()}, {"got": got_vals, "want": {k: v["text"] for k, v in want.items()}})
                    cells = page.evaluate(SRC_CELLS)
                    role = cells.get("role") or {}
                    check(f"{tag}: contact: a one-source field links to its note (a relative path), no dropdown", role.get("a") and role["a"]["text"] == "Org note" and not role.get("dd"), role)
                    # ---- data with no multi-source cell: nothing changes
                    page.evaluate("""() => { document.querySelector('#part').remove(); const v = document.createElement('data-views'); v.id = 'part'; v.setAttribute('no-url', ''); v.setAttribute('toolbar', 'bar');
                      document.body.append(v); v.base = { views: [{ type: 'table', name: 'T', order: ['field', 'nominal'] }] };
                      v.data = { properties: { field: { type: 'text' }, nominal: { type: 'number' } }, rows: [{ id: 'a', field: 'A', nominal: { value: 1, source: 'x' } }, { id: 'b', field: 'B', nominal: 2 }] }; window.v = v; }""")
                    page.wait_for_function("() => window.v.querySelector('tbody tr[data-id]')", timeout=WAIT)
                    settle(page)
                    plain = page.evaluate("""() => ({ col: !!document.querySelector('#part th[data-col$="@source"]'), views: window.v.presets.map((p) => p.name),
                      prec: window.v.precedence, status: document.querySelector('#part .dv-status').textContent })""")
                    check(f"{tag}: data with no multi-source cell: no Nominal source column, no Sources view, precedence null", not plain["col"] and plain["views"] == ["T"] and plain["prec"] is None, plain)
                check(f"{tag}: no page error", not errors, errors[:3])
                ctx.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "source-precedence-checks.json").write_text(json.dumps({"checks": checks, "shots": shots}, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} source-precedence checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
