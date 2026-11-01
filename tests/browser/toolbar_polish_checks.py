"""The bar's open tab and the query box's suggestions on a phone-to-desktop sweep (docs/CONTRACT.md §15), measured in
headless Chromium.

    ~/psu-atlas/.venv/bin/python tests/browser/toolbar_polish_checks.py [OUT_DIR]     # after npm run build

Two defects of robotparts release 2026.10.26.12 (the Mix), on a host shaped like its category page
(tests/browser/fixtures/toolbar-polish.html), at window widths 360, 375, 390, 414, 430, 520 and 1280 px, light and dark:

- the open view's tab: drawn 40-60 px ("R…") at 360-430 px though the row had room, under bar.js's TAB_MIN (88 px).
  While the views are tabs, the open one shows its name in full, or is at least TAB_MIN wide and the only tab left
  (the other tabs fold into "N more" before it shrinks); the bar stays one row;
- the query box's suggestions: the list followed the box (220-235 px at 1280), so property names read "P…", "Price fr…".
  The list sizes to its content: every name shows in full (wrapped when it is longer than the list may grow), the
  list stays inside the window, and each row's full name is its title.

Serves the repo root on a free 127.0.0.1 port, stops it when done, writes OUT_DIR/toolbar-polish-checks.json (default
reports/media/toolbar-polish) and a screenshot per width and scheme, and exits 1 if any check fails. Every claim is a
number read from the page (getBoundingClientRect, scrollWidth against clientWidth), never the presence of a class.
Kept out of tests/browser/checks.py so a lane editing that file never meets this one (tools/test-all.mjs runs both).
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
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "toolbar-polish"
OUT.mkdir(parents=True, exist_ok=True)
checks: list[dict] = []
WIDTHS = (360, 375, 390, 414, 430, 520, 1280)
TAB_MIN = 88  # packages/core/src/toolbar/bar.js: the open tab's floor while there is room
FIXTURE = "tests/browser/fixtures/toolbar-polish.html"


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# the bar: the open tab's box and whether its name is cut, the tabs shown, and the one-row facts (every control's
# vertical centre, none outside the bar, no sideways scroll)
BAR = """() => { const v = document.getElementById('v'), bar = v.querySelector(':scope > .dv-bar'), br = bar.getBoundingClientRect();
  const shown = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !e.closest('[hidden]') && getComputedStyle(e).visibility !== 'hidden'; };
  const tabs = [...bar.querySelectorAll('.dv-bar-views [data-bar=tab]')].filter(shown);
  const cur = tabs.find((t) => t.classList.contains('dv-on') || t.getAttribute('aria-selected') === 'true' || t.getAttribute('aria-current'));
  const label = cur && [...cur.querySelectorAll('span')].find((s) => !s.classList.contains('dv-i') && !s.closest('.dv-i'));
  const controls = [...bar.querySelectorAll('button, input')].filter((e) => !e.closest('.dv-suggest, .dv-pop') && shown(e));
  return { bar: { w: Math.round(br.width), h: Math.round(br.height * 10) / 10 },
    views: v.querySelector('.dv-bar-views .dv-viewchip') ? 'chip' : 'tabs',
    tabs: tabs.map((t) => t.dataset.name || t.textContent.trim()),
    cur: cur ? { name: cur.dataset.name || cur.title || cur.textContent.trim(), w: Math.round(cur.getBoundingClientRect().width * 10) / 10,
      labelShown: !!(label && label.getBoundingClientRect().width > 0), cut: !label || label.scrollWidth > label.clientWidth + 1 } : null,
    more: (bar.querySelector('.dv-bar-views [data-bar=more]:not([hidden])') || {}).textContent || null,
    spread: controls.length ? Math.round((Math.max(...controls.map((e) => { const r = e.getBoundingClientRect(); return r.top + r.height / 2; }))
      - Math.min(...controls.map((e) => { const r = e.getBoundingClientRect(); return r.top + r.height / 2; }))) * 10) / 10 : null,
    outside: controls.filter((e) => { const r = e.getBoundingClientRect(); return r.left < br.left - 0.5 || r.right > br.right + 0.5 || r.top < br.top - 0.5 || r.bottom > br.bottom + 0.5; })
      .map((e) => e.getAttribute('aria-label') || e.textContent.trim().slice(0, 20)),
    sw: document.scrollingElement.scrollWidth, iw: innerWidth }; }"""

# the suggestions as drawn: the box and the list, each property's name and whether it is cut, each row's title
SUGGEST = """() => { const v = document.getElementById('v'), pop = v.querySelector('.dv-suggest'), q = v.querySelector('.dv-query');
  const box = (e) => { const r = e.getBoundingClientRect(); return { left: Math.round(r.left), right: Math.round(r.right), w: Math.round(r.width) }; };
  const items = [...pop.querySelectorAll('.dv-suggest-item.dv-s-property')];
  return { shown: !pop.hidden && pop.getBoundingClientRect().width > 0, box: box(q), pop: box(pop), iw: document.documentElement.clientWidth,
    sw: document.scrollingElement.scrollWidth,
    names: items.map((li) => { const l = li.querySelector('.dv-s-label'); return { name: l.textContent, cut: l.scrollWidth > l.clientWidth + 1 || l.getBoundingClientRect().right > li.getBoundingClientRect().right + 0.5,
      lines: Math.round(l.getBoundingClientRect().height / parseFloat(getComputedStyle(l).lineHeight || '18')), titled: (li.title || '').includes(l.textContent) }; }) }; }"""


def open_page(browser, base, width, dark):
    context = browser.new_context(viewport={"width": width, "height": 844 if width < 768 else 900}, color_scheme="dark" if dark else "light",
                                  device_scale_factor=2 if width < 768 else 1, is_mobile=width < 768, has_touch=width < 768)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{base}/{FIXTURE}")
    page.wait_for_selector("#v .dv-bar", timeout=30000)
    page.wait_for_function("() => document.querySelector('#v .dv-status') && document.querySelector('#v .dv-status').textContent.trim() && document.querySelector('#v').dataset.view", timeout=30000)
    settle(page)
    return page


def settle(page):
    """Let the bar's layout (a ResizeObserver, then a frame) and its transitions finish: no running CSS transition inside
    the element (the search box grows in .18 s), then two painted frames. WHY transitions only: under frame="bleed"
    the column header's scroll-driven animation is always running."""
    page.wait_for_function("() => !document.getAnimations().some((a) => a instanceof CSSTransition && a.playState === 'running' && a.effect && a.effect.target instanceof Element && a.effect.target.closest('#v'))", timeout=10000)
    page.evaluate("() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))")


def open_suggestions(page):
    """Focus the query box as a reader does: its Search icon first when the row folded it, then the box."""
    icon = page.locator("#v .dv-bar [data-bar=search]")
    if icon.count() and icon.first.is_visible():
        icon.first.click()
        settle(page)
    page.locator("#v .dv-qinput").click()
    page.wait_for_function("() => !document.querySelector('#v .dv-suggest').hidden", timeout=5000)
    settle(page)


def run(browser, base):
    errors = []
    before = {}
    for dark in (False, True):
        scheme = "dark" if dark else "light"
        for width in WIDTHS:
            page = open_page(browser, base, width, dark)
            b = page.evaluate(BAR)
            tag = f"{width} px, {scheme}"
            cur = b["cur"]
            before[f"{width}-{scheme}"] = cur and cur["w"]
            one_row = b["bar"]["h"] <= 50 and b["spread"] is not None and b["spread"] <= 1 and not b["outside"] and b["sw"] <= b["iw"]
            check(f"open tab ({tag}): the bar is one row (≤ 50 px, every control on one centre line, none outside it, no sideways scroll)",
                  one_row, {"bar": b["bar"], "spread": b["spread"], "outside": b["outside"], "scrollWidth": b["sw"]})
            if b["views"] == "tabs":
                ok = cur and cur["labelShown"] and (not cur["cut"] or (cur["w"] >= TAB_MIN - 0.5 and len(b["tabs"]) == 1))
                check(f"open tab ({tag}): its name shows in full, or the tab is at least TAB_MIN ({TAB_MIN} px) and the only tab left",
                      ok, {"open": cur, "tabs": b["tabs"], "more": b["more"]})
            else:
                check(f"open tab ({tag}): the views folded to the chip (no tab to measure)", True, {"views": b["views"]})
            page.screenshot(path=str(OUT / f"bar-{width}-{scheme}.png"), clip={"x": 0, "y": 0, "width": width, "height": 200})
            open_suggestions(page)
            s = page.evaluate(SUGGEST)
            cut = [n["name"] for n in s["names"] if n["cut"]]
            check(f"suggestions ({tag}): every property's name shows in full (none cut; a long one wraps)",
                  s["shown"] and s["names"] and not cut, {"cut": cut, "box": s["box"], "list": s["pop"], "names": len(s["names"])})
            check(f"suggestions ({tag}): the list is at least the box's width and stays inside the window (no sideways scroll)",
                  s["shown"] and s["pop"]["w"] >= min(s["box"]["w"], s["iw"] - 16) - 1 and s["pop"]["left"] >= 0 and s["pop"]["right"] <= s["iw"] and s["sw"] <= s["iw"],
                  {"box": s["box"], "list": s["pop"], "window": s["iw"], "scrollWidth": s["sw"]})
            check(f"suggestions ({tag}): each row's full name is one step away (its title)",
                  s["names"] and all(n["titled"] for n in s["names"]), [n["name"] for n in s["names"] if not n["titled"]][:4])
            long = [n for n in s["names"] if n["name"].startswith("Sellers listing")]
            check(f"suggestions ({tag}): the long name is listed and wraps rather than cuts",
                  long and not long[0]["cut"], long[:1])
            page.screenshot(path=str(OUT / f"suggest-{width}-{scheme}.png"))
            errors += page.errors
            page.context.close()
    check("toolbar polish checks: no script errors", not errors, errors[:3])
    return before


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
                urllib.request.urlopen(f"{base}/{FIXTURE}", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            widths = run(browser, base)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    (OUT / "toolbar-polish-checks.json").write_text(json.dumps({"open_tab_px": widths, "checks": checks}, indent=1, ensure_ascii=False), encoding="utf-8")
    passed = sum(c["ok"] for c in checks)
    print(f"{passed}/{len(checks)} toolbar polish checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
