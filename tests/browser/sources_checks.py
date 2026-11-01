"""The "where this value comes from" popover (docs/CONTRACT.md §22), measured in headless Chromium.

    ~/psu-atlas/.venv/bin/python tests/browser/sources_checks.py [OUT_DIR]     # after npm run build

Serves dist/site on a free 127.0.0.1 port (plain/sources.html: a <data-value>, a photo, a file link and a table of rich
cells, with dist/sources.js beside the kit), stops it when done, writes OUT_DIR/sources-checks.json and the light, dark
and phone screenshots (default reports/media/sources) and exits 1 if any check fails. Uses the Ctx harness of checks.py;
its own file so a lane editing checks.py never meets it (tools/test-all.mjs runs both).
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[1] / "reports" / "media" / "sources"
OUT.mkdir(parents=True, exist_ok=True)
import checks as harness  # noqa: E402  (its argv/OUT handling is read at import; main() is not run)

harness.OUT = OUT
check = harness.check
PAGE = "plain/sources.html"
MENU = ".dv-srcmenu"
CITATION = "5.5 N·m — aifitlab.com, https://www.aifitlab.com/products/8541438771336, accessed 2026-10-22. Record aifitlab-8541438771336 · specs.rated_torque_nm."

# every popover fact in one read: its text, its box, who has focus, its colours
READ = """() => { const m = document.querySelector('.dv-srcmenu'); if (!m) return null;
  const r = m.getBoundingClientRect(), cs = getComputedStyle(m), a = document.activeElement;
  return { text: m.innerText, role: m.getAttribute('role'), label: m.getAttribute('aria-label'), count: document.querySelectorAll('.dv-srcmenu').length,
    box: { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }, vw: document.documentElement.clientWidth, vh: document.documentElement.clientHeight,
    bg: cs.backgroundColor, fg: cs.color, focusIn: m.contains(a), focus: a ? (a === document.body ? 'body' : (a.textContent || a.id || a.tagName).trim().slice(0, 30)) : null,
    acts: [...m.querySelectorAll('.dv-srcmenu-act')].map((e) => e.textContent.trim()), hrefs: [...m.querySelectorAll('a')].map((e) => e.getAttribute('href')),
    ownScroll: m.scrollHeight > m.clientHeight + 1 }; }"""


def luminance(css):
    r, g, b = [int(x) for x in css[css.index("(") + 1:css.index(")")].replace("/", ",").split(",")[:3]]
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def open_by_right_click(ctx, page, selector):
    page.locator(selector).first.click(button="right")
    return ctx.until(page, "() => !!document.querySelector('.dv-srcmenu')")


def closed(ctx, page):
    return ctx.until(page, "() => !document.querySelector('.dv-srcmenu')")


# what a contextmenu event ends up as, seen by a listener registered after sources.js's own
SPY = """() => { window.__ctx = []; document.addEventListener('contextmenu', (e) => window.__ctx.push({ id: e.target.id || e.target.className, prevented: e.defaultPrevented, shift: e.shiftKey })); }"""


def run(ctx):
    # ---- light, desktop: right-click a <data-value>
    page = ctx.page(PAGE, width=1280, height=800)
    page.evaluate("window.__opened = []; document.addEventListener('data-sources-open', (e) => window.__opened.push({ on: e.target.className || e.target.id, source: e.detail.source, value: e.detail.value }))")
    page.evaluate(SPY)
    opened = open_by_right_click(ctx, page, "#torque .dv-value")
    got = page.evaluate(READ)
    ev = page.evaluate("window.__opened")
    check("sources: right-click on a <data-value> opens the popover (role=dialog, labelled), one only",
          opened and got["role"] == "dialog" and got["label"] == "Where this value comes from" and got["count"] == 1, got and {k: got[k] for k in ("role", "label", "count")})
    t = got["text"] if got else ""
    check("sources: it shows the value with its unit, the basis line, the source, the URL host, the accessed date with its age, the record and the note",
          all(s in t for s in ["5.5 N·m", "STATED", "seller", "a seller's listing", "aifitlab.com", "www.aifitlab.com/products/8541438771336", "2026-10-22 (", "days ago)",
                               "aifitlab-8541438771336 · specs.rated_torque_nm", "Listing says rated, not peak", "Shift + right-click for the browser's menu"])
          and "undefined" not in t and "null" not in t, t.replace("\n", " | "))
    check("sources: its actions are Open URL ↗, Source page and Copy citation, the first two real links (target _blank for the URL)",
          got["acts"] == ["Open URL ↗", "Source page", "Copy citation"] and page.locator(".dv-srcmenu a.dv-srcmenu-act").first.get_attribute("target") == "_blank"
          and page.locator(".dv-srcmenu a.dv-srcmenu-act").first.get_attribute("rel") == "noopener", got["acts"])
    check("sources: opening fires data-sources-open on the value with the provenance as its detail",
          len(ev) == 1 and ev[0]["source"] == "aifitlab.com" and ev[0]["value"] == "5.5", ev)
    check("sources: a mouse open keeps focus where it was (the keyboard path moves it in)", not got["focusIn"], got["focus"])
    ctx.shot(page, "sources-light-1280")
    page.keyboard.press("Escape")
    check("sources: Escape closes it", closed(ctx, page))
    open_by_right_click(ctx, page, "#torque .dv-value")
    page.mouse.click(40, 700)
    check("sources: a click outside closes it", closed(ctx, page))
    open_by_right_click(ctx, page, "#torque .dv-value")
    page.evaluate("window.dispatchEvent(new Event('resize'))")
    check("sources: a window resize closes it", closed(ctx, page))
    open_by_right_click(ctx, page, "#torque .dv-value")
    page.evaluate("window.dispatchEvent(new Event('scroll'))")
    page.evaluate("document.dispatchEvent(new Event('scroll'))")
    check("sources: a scroll closes it", closed(ctx, page))

    # ---- only one at a time; a second right-click moves it
    open_by_right_click(ctx, page, "#torque .dv-value")
    page.dispatch_event("#photo", "contextmenu", {"clientX": 700, "clientY": 100})
    ctx.until(page, "() => document.querySelector('.dv-srcmenu') && document.querySelector('.dv-srcmenu').innerText.includes('Photo of')")
    two = page.evaluate(READ)
    check("sources: a second open replaces the first (one popover, now the photo's)", two["count"] == 1 and "Photo of the AiFitLab 8541" in two["text"] and "Accessed" in two["text"], two["text"].replace("\n", " | "))
    page.keyboard.press("Escape")

    # ---- the native menu is left alone
    page.evaluate("window.__ctx.length = 0")
    page.locator("#torque .dv-value").first.click(button="right", modifiers=["Shift"])
    page.locator("#unmarked").click(button="right")
    seen = page.evaluate("window.__ctx")
    check("sources: Shift + right-click and a right-click on an unmarked element leave the native menu (default not prevented, no popover)",
          not page.locator(MENU).count() and len(seen) == 2 and not seen[0]["prevented"] and seen[0]["shift"] and not seen[1]["prevented"], seen)
    page.locator("#torque .dv-value").first.click(button="right")
    seen = page.evaluate("window.__ctx")
    check("sources: a plain right-click on a marked value does prevent the native menu", seen[-1]["prevented"], seen[-1])
    page.keyboard.press("Escape")

    # ---- host-marked photo and file link
    open_by_right_click(ctx, page, "#photo")
    photo = page.evaluate(READ)
    check("sources: a host's <img data-provenance> opens it too (value, source, URL, accessed, record; no basis line)",
          photo and all(s in photo["text"] for s in ["Photo of the AiFitLab 8541", "aifitlab.com", "2026-10-22", "aifitlab-8541438771336 · photo"]) and "STATED" not in photo["text"], photo and photo["text"].replace("\n", " | "))
    page.keyboard.press("Escape")

    # ---- keyboard: Shift+F10 on a focused link with provenance
    page.focus("#datasheet")
    page.evaluate("window.__ctx.length = 0")
    page.keyboard.press("Shift+F10")
    key = ctx.until(page, "() => !!document.querySelector('.dv-srcmenu')")
    kb = page.evaluate(READ)
    check("sources: Shift+F10 on a focused link with provenance opens it under the link, focus moves to its first action",
          key and kb["focusIn"] and kb["focus"] == "Open URL ↗" and "GIM4305 datasheet (PDF)" in kb["text"] and "STATED" in kb["text"] and "steadywin.cn" in kb["text"],
          kb and {"focus": kb["focus"], "text": kb["text"][:60]})
    link = page.evaluate("(() => { const r = document.getElementById('datasheet').getBoundingClientRect(); return { l: r.left, b: r.bottom } })()")
    check("sources: ... and sits just under the link (measured)", kb and abs(kb["box"]["l"] - link["l"]) <= 2 and 0 <= kb["box"]["t"] - link["b"] <= 12, {"menu": [round(kb["box"]["l"]), round(kb["box"]["t"])], "link": [round(link["l"]), round(link["b"])]})
    page.keyboard.press("ArrowRight")
    second = page.evaluate(READ)["focus"]
    page.keyboard.press("Tab")
    third = page.evaluate(READ)["focus"]
    page.keyboard.press("Shift+Tab")
    back = page.evaluate(READ)["focus"]
    check("sources: arrows and Tab move between the actions and wrap inside the dialog", second == "Copy citation" and third == "Open URL ↗" and back == "Copy citation", [second, third, back])
    page.keyboard.press("Escape")
    check("sources: Escape closes it and returns focus to the link", closed(ctx, page) and page.evaluate("document.activeElement.id") == "datasheet")
    page.keyboard.press("ContextMenu")
    check("sources: the ContextMenu key opens it too", ctx.until(page, "() => !!document.querySelector('.dv-srcmenu')"))
    page.keyboard.press("Escape")
    # a selection's anchor is used first
    page.focus("#datasheet")
    page.evaluate("(() => { const r = document.createRange(); r.selectNodeContents(document.querySelector('#torque .dv-value')); const s = getSelection(); s.removeAllRanges(); s.addRange(r); })()")
    page.focus("#datasheet")
    page.keyboard.press("Shift+F10")
    sel = ctx.until(page, "() => !!document.querySelector('.dv-srcmenu')")
    check("sources: with a text selection inside a value, Shift+F10 opens that value's, not the focused link's", sel and "Listing says rated" in page.evaluate(READ)["text"])
    page.keyboard.press("Escape")
    # ...but focus that moves after the selection wins (a right-click leaves a word selected; tabbing on means the new element)
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.focus("#datasheet")
    page.keyboard.press("Shift+F10")
    later = ctx.until(page, "() => !!document.querySelector('.dv-srcmenu')")
    check("sources: focus that moved after the selection wins over the stale selection", later and "Listing says rated" not in page.evaluate(READ)["text"], later and page.evaluate(READ)["text"][:60])
    page.keyboard.press("Escape")
    page.evaluate("getSelection().removeAllRanges()")
    page.focus("#unmarked")
    page.evaluate("document.getElementById('unmarked').tabIndex = 0")
    page.focus("#unmarked")
    page.keyboard.press("Shift+F10")
    page.wait_for_timeout(300)
    check("sources: Shift+F10 on an element with no provenance opens nothing", not page.locator(MENU).count())

    # ---- copy citation (clipboard stubbed to read what is written; then the textarea fallback)
    page.evaluate("(() => { window.__copied = null; Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (t) => { window.__copied = t; } } }); })()")
    open_by_right_click(ctx, page, "#torque .dv-value")
    page.get_by_role("button", name="Copy citation").click()
    ok = ctx.until(page, "() => window.__copied !== null")
    label = page.get_by_role("button").filter(has_text="Copied").count()
    check("sources: Copy citation writes `value unit — source, URL, accessed date. Record id.` and the button reads Copied", ok and page.evaluate("window.__copied") == CITATION and label == 1, page.evaluate("window.__copied"))
    reset = ctx.until(page, "() => [...document.querySelectorAll('.dv-srcmenu-act')].some((e) => e.textContent === 'Copy citation')", timeout=4000)
    check("sources: ... and goes back to Copy citation after 1.5 s", reset)
    page.keyboard.press("Escape")
    page.evaluate("(() => { Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined }); window.__fallback = null; document.addEventListener('copy', () => { window.__fallback = getSelection().toString(); }); })()")
    open_by_right_click(ctx, page, "#torque .dv-value")
    page.get_by_role("button", name="Copy citation").click()
    ctx.until(page, "() => window.__fallback !== null", timeout=4000)
    check("sources: without navigator.clipboard the textarea + execCommand fallback copies the same text and removes its textarea",
          page.evaluate("window.__fallback") == CITATION and page.get_by_role("button").filter(has_text="Copied").count() == 1 and page.evaluate("document.querySelectorAll('textarea').length") == 0, page.evaluate("window.__fallback"))
    page.keyboard.press("Escape")

    # ---- a table's rich cells
    page.wait_for_selector("data-views td[data-provenance]")
    marked = page.evaluate("document.querySelectorAll('data-views td[data-provenance]').length")
    cells = page.evaluate("document.querySelectorAll('data-views td.dv-num').length")
    open_by_right_click(ctx, page, "data-views td[data-provenance*='steadywin']")
    cell = page.evaluate(READ)
    check("sources: a table's rich cell opens it with its value, source, URL and record", cell and all(s in cell["text"] for s in ["1.9 N·m", "steadywin.cn", "www.steadywin.cn/en/product/gim4305-10", "steadywin-gim4305 · specs.peak_torque_nm"]), cell and cell["text"].replace("\n", " | "))
    check("sources: in the table the 4 rich cells (two rows x torque and mass) carry data-provenance and the plain row's 2 numbers do not", marked == 4 and cells == 6, {"marked": marked, "cells": cells})
    page.keyboard.press("Escape")
    ctx.until(page, "() => !document.querySelector('.dv-srcmenu')")
    page.locator("data-views td.dv-num:not([data-provenance])").first.click(button="right")
    page.wait_for_timeout(300)
    check("sources: a right-click on the plain row's number opens nothing", not page.locator(MENU).count())

    # ---- the API: provenanceOf, opts.resolve, destroy
    api = page.evaluate("""async () => { const m = await import('../kit/sources.js'); const el = document.querySelector('#torque .dv-value');
      const own = m.provenanceOf(el), none = m.provenanceOf(document.getElementById('unmarked')), inner = m.provenanceOf(document.querySelector('#datasheet'));
      const handle = m.attachSourcesMenu(document, { resolve: (e) => (e.id === 'unmarked' ? { value: 'Hosted', source: 'the host' } : null) });
      window.__handle = handle; return { own: own && own.source, none, inner: inner && inner.value, closeDestroy: typeof handle.close + typeof handle.destroy }; }""")
    check("sources: provenanceOf returns the closest [data-provenance] parsed, null for none", api["own"] == "aifitlab.com" and api["none"] is None and api["inner"] == "GIM4305 datasheet (PDF)" and api["closeDestroy"] == "functionfunction", api)
    page.locator("#unmarked").click(button="right")
    resolved = ctx.until(page, "() => !!document.querySelector('.dv-srcmenu')") and "the host" in page.evaluate(READ)["text"]
    check("sources: opts.resolve(el) supplies provenance for an element without the attribute", resolved)
    page.keyboard.press("Escape")
    page.evaluate("window.__handle.destroy()")
    page.locator("#unmarked").click(button="right")
    page.wait_for_timeout(300)
    check("sources: destroy() detaches that attachment", not page.locator(MENU).count())
    page.context.close()

    # ---- the clamp: a click at the viewport's bottom-right corner stays inside it
    page = ctx.page(PAGE, width=1280, height=800)
    page.evaluate("document.getElementById('torque').firstElementChild.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 1278, clientY: 798 }))")
    ctx.until(page, "() => !!document.querySelector('.dv-srcmenu')")
    c = page.evaluate(READ)
    b = c["box"]
    check("sources: opened at the bottom-right corner it is clamped inside the viewport (measured)", 0 <= b["l"] and b["r"] <= c["vw"] and 0 <= b["t"] and b["b"] <= c["vh"] and b["w"] <= 360.5, {k: round(v) for k, v in b.items()})
    page.context.close()

    # ---- dark
    page = ctx.page(PAGE, width=1280, height=800, dark=True)
    open_by_right_click(ctx, page, "#torque .dv-value")
    d = page.evaluate(READ)
    check("sources: dark theme: the popover is a dark surface with light text", d and luminance(d["bg"]) < 0.25 and luminance(d["fg"]) > 0.75, d and [d["bg"], d["fg"]])
    ctx.shot(page, "sources-dark-1280")
    page.context.close()
    page = ctx.page(PAGE, width=1280, height=800)
    open_by_right_click(ctx, page, "#torque .dv-value")
    li = page.evaluate(READ)
    check("sources: light theme: the popover is a light surface with dark text", li and luminance(li["bg"]) > 0.9 and luminance(li["fg"]) < 0.25, li and [li["bg"], li["fg"]])
    page.context.close()
    page = ctx.page(PAGE, width=1280, height=800, dark=True)
    page.evaluate("document.documentElement.dataset.theme = 'light'")
    open_by_right_click(ctx, page, "#torque .dv-value")
    forced = page.evaluate(READ)
    check("sources: html[data-theme=light] wins over a dark system scheme (as tokens.css does)", forced and luminance(forced["bg"]) > 0.9, forced and forced["bg"])
    page.context.close()

    # ---- phone, 375 px: full width minus 16 px gutters, inside the viewport; long-press
    page = ctx.page(PAGE, width=375, height=700, mobile=True)
    page.evaluate("window.__opened = 0; document.addEventListener('data-sources-open', () => { window.__opened++; })")
    page.evaluate("""(() => { const el = document.querySelector('#torque .dv-value'); const r = el.getBoundingClientRect();
      const o = { bubbles: true, pointerType: 'touch', pointerId: 7, isPrimary: true, clientX: r.left + 4, clientY: r.top + 4 };
      window.__press = (type, dx = 0) => el.dispatchEvent(new PointerEvent(type, { ...o, clientX: o.clientX + dx })); window.__press('pointerdown'); })()""")
    page.wait_for_timeout(300)
    early = page.locator(MENU).count()
    opened = ctx.until(page, "() => !!document.querySelector('.dv-srcmenu')", timeout=3000)
    m = page.evaluate(READ)
    bx = m["box"]
    check("sources: a 550 ms touch long-press opens it (not before 300 ms)", opened and early == 0 and page.evaluate("window.__opened") == 1, {"early": early})
    check("sources: at 375 px it is the full width minus 16 px gutters and inside the viewport (measured)",
          abs(bx["l"] - 16) <= 1 and abs(bx["r"] - (m["vw"] - 16)) <= 1 and bx["t"] >= 0 and bx["b"] <= m["vh"] and m["vw"] == 375, {k: round(v) for k, v in bx.items()})
    ctx.shot(page, "sources-light-375")
    # the click that ends the press is swallowed once
    page.evaluate("window.__press('pointerup'); window.__clicks = []; window.addEventListener('click', (e) => window.__clicks.push(e), true);")
    page.evaluate("document.querySelector('#torque .dv-value').click()")
    swallowed = page.evaluate("window.__clicks.map((e) => e.defaultPrevented)")
    check("sources: the click that follows a long-press is suppressed", swallowed and swallowed[0] is True, swallowed)
    page.keyboard.press("Escape")
    ctx.until(page, "() => !document.querySelector('.dv-srcmenu')")
    page.evaluate("window.__press('pointerdown'); window.__press('pointermove', 14)")
    page.wait_for_timeout(750)
    moved = page.locator(MENU).count()
    page.evaluate("window.__press('pointerup')")
    page.evaluate("window.__press('pointerdown')")
    page.wait_for_timeout(250)
    page.evaluate("window.__press('pointerup')")
    page.wait_for_timeout(600)
    lifted = page.locator(MENU).count()
    check("sources: a long-press cancelled by a >10 px move, or by lifting early, opens nothing", moved == 0 and lifted == 0, {"moved": moved, "lifted": lifted})
    page.context.close()

    page = ctx.page(PAGE, width=375, height=700, dark=True, mobile=True)
    open_by_right_click(ctx, page, "#torque .dv-value")
    ctx.shot(page, "sources-dark-375")
    page.context.close()


def main() -> int:
    site = harness.SITE
    if not (site / "plain" / "sources.html").exists():
        print("dist/site is not built: npm --prefix ~/data-ui run build")
        return 1
    port = harness.free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(site)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/index.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = harness.Ctx(browser, base)
            run(ctx)
            check("sources: nothing loaded from another site", not ctx.foreign, ctx.foreign[:3])
            check("sources: no script errors", not ctx.errors, ctx.errors[:3])
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    (OUT / "sources-checks.json").write_text(json.dumps(harness.checks, indent=1, ensure_ascii=False), encoding="utf-8")
    passed = sum(c["ok"] for c in harness.checks)
    print(f"{passed}/{len(harness.checks)} sources checks pass; screenshots in {OUT}")
    return 0 if passed == len(harness.checks) else 1


if __name__ == "__main__":
    sys.exit(main())
