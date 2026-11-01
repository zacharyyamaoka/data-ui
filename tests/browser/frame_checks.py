"""The frame= checks (docs/CONTRACT.md §12): how a <data-views> sits in its page, measured in headless Chromium.

    ~/psu-atlas/.venv/bin/python tests/browser/frame_checks.py [OUT_DIR]     # after npm run build

Serves the repo root on a free 127.0.0.1 port (tests/browser/fixtures/frame.html, dist/, gallery/), stops it when done,
writes OUT_DIR/frame-checks.json (default reports/media/frame) and exits 1 if any check fails. Every claim is a number
read from the page (getComputedStyle, getBoundingClientRect, scrollHeight), never the presence of a class: a frame
that only looked right would fail here. Kept out of tests/browser/checks.py so a lane editing that file never meets
this one (tools/test-all.mjs runs both).
"""

from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "frame"
OUT.mkdir(parents=True, exist_ok=True)
checks: list[dict] = []
FRAMES = ["boxed", "flush", "tabs", "sheet", "page", "bleed"]


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# one read of everything a frame decides: the box, who scrolls the rows, where the band and the column header are
MEASURE = """() => {
  const v = document.getElementById('v'), pane = document.getElementById('pane'), cs = getComputedStyle(v);
  const rows = v.querySelector('.dv-scroll'), head = v.querySelector(':scope > .dv-head'), status = v.querySelector(':scope > .dv-status');
  const thead = v.querySelector('.dv-table thead');
  const box = (e) => { if (!e) return null; const r = e.getBoundingClientRect(); return {x: r.left, y: r.top, w: r.width, h: r.height, b: r.bottom}; };
  const paneScrolls = getComputedStyle(pane).overflowY !== 'visible';
  return {
    frame: v.dataset.frame, scroll: v.dataset.scroll || null, border: parseFloat(cs.borderTopWidth), radius: parseFloat(cs.borderTopLeftRadius),
    height: v.getBoundingClientRect().height,
    rowsScroll: rows ? {sh: rows.scrollHeight, ch: rows.clientHeight, oy: getComputedStyle(rows).overflowY} : null,
    pane: paneScrolls ? {top: pane.getBoundingClientRect().top, st: pane.scrollTop, sh: pane.scrollHeight, ch: pane.clientHeight, x: pane.getBoundingClientRect().left, w: pane.getBoundingClientRect().width}
                      : {top: 0, st: scrollY, sh: document.scrollingElement.scrollHeight, ch: innerHeight, x: pane.getBoundingClientRect().left, w: pane.getBoundingClientRect().width},
    v: box(v), head: box(head), status: box(status), thead: box(thead),
    drawn: v.querySelectorAll('tbody tr[data-i]').length,
    firstRow: (v.querySelector('tbody tr[data-i]') || {}).dataset?.i ?? null,
    hbar: (() => { const h = v.querySelector('.dv-hbar'); return h ? {shown: !h.hidden && h.getBoundingClientRect().height > 0, b: h.getBoundingClientRect().bottom} : null; })(),
    headBg: head ? getComputedStyle(head).backgroundColor : null, bg: cs.backgroundColor,
    theadBg: thead ? getComputedStyle(thead.querySelector('th:nth-child(2)')).backgroundColor : null,
  }; }"""


def open_page(browser, base, frame, width=1280, height=900, dark=False, window=False, fallback=False):
    context = browser.new_context(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light")
    if fallback:
        # a browser without scroll-driven animations (Firefox today): CSS.supports says no and the @supports block is
        # neutralised, so the scroll listener alone must keep the column header under the band
        context.add_init_script("""(() => { const s = CSS.supports.bind(CSS); CSS.supports = (a, b) => /animation-timeline/.test(String(a) + String(b ?? '')) ? false : s(a, b);
          document.addEventListener('DOMContentLoaded', () => { const st = document.createElement('style'); st.textContent = 'data-views .dv-table thead { animation: none !important; }'; document.head.append(st); }); })()""")
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{base}/tests/browser/fixtures/frame.html?frame={frame}{'&window' if window else ''}")
    page.wait_for_selector("#v .dv-status")
    page.wait_for_function("() => document.querySelector('#v .dv-status').textContent.trim() && document.querySelector('#v tbody tr[data-i]')", timeout=15000)
    page.wait_for_timeout(300)
    return page


def scroll_to(page, y, window=False):
    page.evaluate(f"() => {{ {'window.scrollTo(0, ' + str(y) + ')' if window else 'document.getElementById(\"pane\").scrollTop = ' + str(y)}; }}")
    page.wait_for_timeout(250)
    return page.evaluate(MEASURE)


def run(browser, base):
    errors = []
    for dark in (False, True):
        for frame in FRAMES:
            page = open_page(browser, base, frame, dark=dark)
            m = page.evaluate(MEASURE)
            tag = f"{frame}, {'dark' if dark else 'light'}"
            page_scroll = frame in ("page", "bleed")
            if frame == "boxed":
                check(f"frame {tag}: the box is today's: a 1 px border, its own scroll (rows scroll inside, the pane does not grow)",
                      m["border"] == 1 and m["rowsScroll"]["oy"] == "auto" and m["rowsScroll"]["sh"] > 5 * m["rowsScroll"]["ch"] and m["pane"]["sh"] < 3 * m["pane"]["ch"],
                      {"border": m["border"], "rows": m["rowsScroll"], "pane": m["pane"]["sh"]})
            else:
                check(f"frame {tag}: no box (0 px border, no radius)", m["border"] == 0 and m["radius"] == 0, {"border": m["border"], "radius": m["radius"]})
            if frame in ("flush", "tabs", "sheet"):
                check(f"frame {tag}: the views keep their own scroll (the rows scroll inside; the pane stays page-sized)",
                      m["scroll"] is None and m["rowsScroll"]["oy"] == "auto" and m["rowsScroll"]["sh"] > 5 * m["rowsScroll"]["ch"] and m["pane"]["sh"] < 3 * m["pane"]["ch"],
                      {"rows": m["rowsScroll"], "pane": m["pane"]["sh"]})
            if frame in ("flush", "tabs", "page"):
                # the tabs' first label starts on the page's text edge (the h1's), not 8 px inside a box
                edge = page.evaluate("() => [document.querySelector('#pane h1').getBoundingClientRect().left, document.querySelector('#v .dv-tab .dv-tab-name, #v .dv-tab').getBoundingClientRect().left]")
                check(f"frame {tag}: the first tab starts on the page's text edge", abs(edge[0] - edge[1]) <= 1, edge)
            if frame == "sheet":
                check(f"frame {tag}: a tinted header band instead of a line", m["headBg"] != m["bg"] and m["theadBg"] == m["headBg"], {"head": m["headBg"], "bg": m["bg"], "thead": m["theadBg"]})
            if frame == "tabs":
                # zebra by row number: the same row keeps its stripe after the window of drawn rows moves
                stripe = """() => Object.fromEntries([...document.querySelectorAll('#v tbody tr.dv-row[data-i]')].slice(0, 6).map(tr => [tr.dataset.i, getComputedStyle(tr.querySelector('td:nth-child(2)')).backgroundColor]))"""
                before = page.evaluate(stripe)
                page.evaluate("() => { const s = document.querySelector('#v .dv-scroll'); s.scrollTop = 30 * 37; }")
                page.wait_for_timeout(250)
                after = page.evaluate(stripe)
                both = {**before, **after}
                odd = {c for k, c in both.items() if int(k) % 2}
                even = {c for k, c in both.items() if not int(k) % 2}
                # every odd row one colour, every even row another, before and after the drawn window moved past row 37
                check(f"frame {tag}: zebra rows stripe by row number and keep their stripe as rows recycle",
                      len(odd) == 1 and len(even) == 1 and odd != even and set(before) != set(after), {"before": before, "after": after})
            if page_scroll:
                check(f"frame {tag}: the page scrolls the rows (no inner vertical scroll; the pane holds the whole table)",
                      m["scroll"] == "page" and m["rowsScroll"]["oy"] == "hidden" and m["rowsScroll"]["sh"] <= m["rowsScroll"]["ch"] + 1 and m["pane"]["sh"] > 20 * m["pane"]["ch"],
                      {"rows": m["rowsScroll"], "pane": [m["pane"]["sh"], m["pane"]["ch"]]})
                s = scroll_to(page, 3000)
                band_bottom = s["status"]["b"]
                check(f"frame {tag}: scrolled 3,000 px, the tabs and toolbar stick to the pane's top edge",
                      abs(s["head"]["y"] - s["pane"]["top"]) <= 1, {"head": s["head"]["y"], "pane": s["pane"]["top"]})
                check(f"frame {tag}: the column header sits right under the band (getBoundingClientRect)",
                      abs(s["thead"]["y"] - band_bottom) <= 1, {"thead": round(s["thead"]["y"], 1), "band bottom": round(band_bottom, 1)})
                check(f"frame {tag}: 1,149 rows stay virtualised under page scroll (under 80 drawn, and they are the rows on screen)",
                      0 < s["drawn"] < 80 and int(s["firstRow"]) > 50, {"drawn": s["drawn"], "first drawn row": s["firstRow"]})
                check(f"frame {tag}: the wide table's sideways scrollbar is pinned to the pane's bottom edge",
                      s["hbar"] and s["hbar"]["shown"] and abs(s["hbar"]["b"] - (s["pane"]["top"] + s["pane"]["ch"])) <= 1, s["hbar"])
                bottom = scroll_to(page, 10 ** 7)
                check(f"frame {tag}: at the end of the page the column header stays inside the table (never over the content after it)",
                      bottom["thead"]["b"] <= bottom["v"]["b"] + 1, {"thead bottom": round(bottom["thead"]["b"]), "views bottom": round(bottom["v"]["b"])})
                scroll_to(page, 3000)
                page.click("#v tbody tr.dv-row >> nth=6")
                page.wait_for_selector("#v .dv-peek:not([hidden])")
                peek = page.evaluate("() => { const r = document.querySelector('#v .dv-peek').getBoundingClientRect(), p = document.getElementById('pane').getBoundingClientRect(); return {peek: [r.top, r.bottom, r.right], pane: [p.top, p.bottom, p.right]}; }")
                check(f"frame {tag}: the side peek covers the pane's visible height, not the top of a 34,000 px table",
                      all(abs(a - b) <= 1 for a, b in zip(peek["peek"], peek["pane"])), peek)
                page.keyboard.press("Escape")
                page.click("#v .dv-btn[data-menu=sort]")
                at = page.evaluate("() => [document.querySelector('#v .dv-pop').getBoundingClientRect().top, document.querySelector('#v .dv-btn[data-menu=sort]').getBoundingClientRect().bottom]")
                page.evaluate("() => { document.getElementById('pane').scrollTop += 600; }")
                page.wait_for_timeout(250)
                later = page.evaluate("() => [document.querySelector('#v .dv-pop').getBoundingClientRect().top, document.querySelector('#v .dv-btn[data-menu=sort]').getBoundingClientRect().bottom]")
                check(f"frame {tag}: an open menu stays under its stuck button while the page scrolls", abs(later[0] - at[0]) <= 1 and abs(later[1] - at[1]) <= 1, {"open": at, "after 600 px": later})
                page.keyboard.press("Escape")
            if frame == "bleed":
                check(f"frame {tag}: edge to edge of the pane (across its 20 px padding, --data-bleed)",
                      abs(m["v"]["x"] - m["pane"]["x"]) <= 1 and abs(m["v"]["w"] - m["pane"]["w"]) <= 1, {"views": [m["v"]["x"], m["v"]["w"]], "pane": [m["pane"]["x"], m["pane"]["w"]]})
            if frame == "page":
                check(f"frame {tag}: content width (inside the pane's padding)", abs(m["v"]["x"] - (m["pane"]["x"] + 20)) <= 1, {"views x": m["v"]["x"], "pane x": m["pane"]["x"]})
            errors += page.errors
            page.context.close()

    # a frame changes live: page -> boxed -> page, the same view, no reload
    page = open_page(browser, base, "page")
    name = page.evaluate("() => document.getElementById('v').origin.name")
    page.evaluate("() => document.getElementById('v').setAttribute('frame', 'boxed')")
    page.wait_for_timeout(600)
    boxed = page.evaluate(MEASURE)
    page.evaluate("() => document.getElementById('v').setAttribute('frame', 'page')")
    page.wait_for_timeout(600)
    again = page.evaluate(MEASURE)
    check("frame switch: page -> boxed -> page on a live element re-makes the view on the new scroller and keeps the view",
          boxed["border"] == 1 and boxed["scroll"] is None and boxed["rowsScroll"]["sh"] > 5 * boxed["rowsScroll"]["ch"]
          and again["scroll"] == "page" and again["pane"]["sh"] > 20 * again["pane"]["ch"] and page.evaluate("() => document.getElementById('v').origin.name") == name,
          {"boxed": [boxed["border"], boxed["scroll"]], "page": [again["scroll"], again["pane"]["sh"]], "view": name})
    # a new tab under a page frame starts at the view's top, not at the old view's scroll position
    scroll_to(page, 20000)
    page.click("#v .dv-tab >> nth=1")
    page.wait_for_timeout(800)
    tab = page.evaluate("() => { const v = document.getElementById('v'), p = document.getElementById('pane'); return {st: p.scrollTop, stage: v.querySelector('.dv-stage').getBoundingClientRect().top - p.getBoundingClientRect().top, band: parseFloat(v.style.getPropertyValue('--dv-band-h'))}; }")
    check("frame page: a new tab opened from deep in the rows starts at its own top, just under the band", 0 <= tab["stage"] - tab["band"] <= 2, tab)
    errors += page.errors
    page.context.close()

    # the window as the scroller (a page with one scroll, e.g. a phone layout)
    page = open_page(browser, base, "page", window=True)
    s = scroll_to(page, 3000, window=True)
    check("frame page, window scroll: the band sticks to the window's top and the header under it",
          abs(s["head"]["y"]) <= 1 and abs(s["thead"]["y"] - s["status"]["b"]) <= 1 and 0 < s["drawn"] < 80,
          {"head": s["head"]["y"], "thead": s["thead"]["y"], "band bottom": s["status"]["b"], "drawn": s["drawn"]})
    errors += page.errors
    page.context.close()

    # a resize across the host's breakpoint moves the scroll from the pane to the window: the frame follows it
    page = open_page(browser, base, "page")
    page.set_viewport_size({"width": 700, "height": 900})
    page.wait_for_timeout(700)
    s = scroll_to(page, 3000, window=True)
    check("frame page, resized from 1280 to 700 px (the pane stops scrolling, the window starts): the band and header follow the window",
          abs(s["head"]["y"]) <= 1 and abs(s["thead"]["y"] - s["status"]["b"]) <= 1 and 0 < s["drawn"] < 80,
          {"head": s["head"]["y"], "thead": s["thead"]["y"], "band bottom": s["status"]["b"], "drawn": s["drawn"]})
    errors += page.errors
    page.context.close()

    # no scroll-driven animations: the scroll listener pins the header instead
    page = open_page(browser, base, "page", fallback=True)
    s = scroll_to(page, 3000)
    page.wait_for_timeout(200)
    s = page.evaluate(MEASURE)
    check("frame page, no scroll-driven animations (Firefox): the scroll listener keeps the header under the band",
          abs(s["thead"]["y"] - s["status"]["b"]) <= 1, {"thead": s["thead"]["y"], "band bottom": s["status"]["b"]})
    errors += page.errors
    page.context.close()

    # a phone: the page frames still never scroll the page sideways
    for frame in ("page", "bleed"):
        context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        page = context.new_page()
        page.goto(f"{base}/tests/browser/fixtures/frame.html?frame={frame}&window")
        page.wait_for_selector("#v tbody tr[data-i]", timeout=15000)
        page.wait_for_timeout(300)
        sw = page.evaluate("document.scrollingElement.scrollWidth")
        check(f"frame {frame}, 390 px phone: no sideways page scroll", sw <= 390, f"scrollWidth {sw}")
        context.close()

    check("frame checks: no script errors", not errors, errors[:3])


def main() -> int:
    if not (ROOT / "dist" / "data-ui.js").exists():
        print("dist/ is not built: npm --prefix ~/data-ui run build")
        return 1
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/tests/browser/fixtures/frame.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            run(browser, base)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    (OUT / "frame-checks.json").write_text(json.dumps(checks, indent=1, ensure_ascii=False), encoding="utf-8")
    passed = sum(c["ok"] for c in checks)
    print(f"{passed}/{len(checks)} frame checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
