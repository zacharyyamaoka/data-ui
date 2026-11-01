"""The app rail's checks (docs/CONTRACT.md §27, docs/peps/0009-app-rail.md): <data-rail> in its three styles, measured in
headless Chromium on the BUILT kit (dist/), never a dev reload loop.

    ~/psu-atlas/.venv/bin/python tests/browser/rail_checks.py [OUT_DIR]     # after npm run build

Serves the repo root on a free 127.0.0.1 port (tests/browser/fixtures/rail.html, dist/), stops it when done, writes
OUT_DIR/rail-checks.json and the three styles' stills, light and dark (default reports/media/rail), and exits 1 if any
check fails. Every claim is a number read from the page (getBoundingClientRect, getComputedStyle, localStorage), never
the presence of a class. Ported from Clank's tests/sidebar_styles_smoke.mjs (clank-workbench @ 7ba2041), plus the
side-panel rules of §11 and the seven traps Clank's agent hit; each trap has a check here, named "trap N".
"""

from __future__ import annotations

import json
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "rail"
OUT.mkdir(parents=True, exist_ok=True)
checks: list[dict] = []
PREFIX = "data-ui/rail/fixture"
WIDTH_KEY = "data-ui/panel-width/app-rail:fixture"
DESTS = ["fleet", "dashboards", "runs", "calibration-runs", "hardware", "settings", "help"]


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    # WHY 5600-5699: the lanes' own range (RULES.md), so no run meets Zach's Stable and Preview ports
    for port in range(5640, 5700):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free port in 5640-5699")


# every destination: where its icon, its label and its row are, and whether the label is drawn
DEST_GEOMETRY = """() => {
  const rail = document.getElementById('rail');
  const box = (e) => { const r = e.getBoundingClientRect(); return {l: r.left, r: r.right, t: r.top, b: r.bottom, w: r.width, h: r.height, cx: r.left + r.width / 2, cy: r.top + r.height / 2}; };
  const railBox = box(rail);
  return {
    rail: railBox, mode: rail.getAttribute('mode'),
    dests: [...rail.querySelectorAll('.dv-rail-dest')].map((a) => {
      const icon = a.querySelector('[data-rail-icon]'), label = a.querySelector('.dv-rail-label');
      const ls = getComputedStyle(label), lr = label.getBoundingClientRect();
      return {
        id: a.dataset.id, row: box(a), icon: box(icon), svg: icon.querySelector('svg') ? box(icon.querySelector('svg')) : null,
        label: box(label), labelShown: ls.display !== 'none' && ls.visibility !== 'hidden' && lr.width > 0 && lr.height > 0,
        flex: getComputedStyle(a).flexDirection, title: label.getAttribute('title'), text: label.textContent,
        clipped: label.scrollHeight > label.clientHeight + 1 || label.scrollWidth > label.clientWidth + 1,
        icons: a.querySelectorAll('[data-rail-icon]').length,
      };
    }),
  };
}"""

# one rect per character, grouped by line: where a label really wraps (Clank's trick)
LABEL_LINES = """(id) => {
  const label = document.querySelector(`#rail .dv-rail-dest[data-id="${id}"] .dv-rail-label`);
  const tops = [], text = label.textContent, walker = document.createTreeWalker(label, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) for (let i = 0; i < node.length; i += 1) {
    const range = document.createRange(); range.setStart(node, i); range.setEnd(node, i + 1); tops.push(Math.round(range.getBoundingClientRect().top));
  }
  const lines = [];
  tops.forEach((top, i) => { if (i === 0 || top !== tops[i - 1]) lines.push(''); lines[lines.length - 1] += text[i]; });
  return lines.map((l) => l.trim());
}"""

VISIBLE = """(sel) => { const e = document.querySelector(sel); if (!e) return false; const s = getComputedStyle(e), r = e.getBoundingClientRect();
  return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0; }"""


def open_page(browser, base, dark=False, storage=None, width=1280, height=900, query=""):
    context = browser.new_context(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light")
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    if storage:
        # a fresh context has no storage; this stands in for a person who chose earlier
        page.add_init_script("(s => { for (const [k, v] of Object.entries(s)) if (!localStorage.getItem('__seeded')) localStorage.setItem(k, v); localStorage.setItem('__seeded', '1'); })(" + json.dumps(storage) + ")")
    page.goto(f"{base}/tests/browser/fixtures/rail.html{query}")
    page.wait_for_function("() => window.__ready === true", timeout=15000)
    page.wait_for_selector("#rail .dv-rail-dest", timeout=15000)
    return page


def geometry(page):
    return page.evaluate(DEST_GEOMETRY)


def rail_width(page):
    return page.evaluate("() => document.getElementById('rail').getBoundingClientRect().width")


def wait_width(page, lo, hi, label):
    ok = True
    try:
        page.wait_for_function("([lo, hi]) => { const w = document.getElementById('rail').getBoundingClientRect().width; return w >= lo && w <= hi; }", arg=[lo, hi], timeout=5000)
    except Exception:  # noqa: BLE001 - the check below reports the real width
        ok = False
    return ok


def wait_width_of(page, selector, lo, hi):
    try:
        page.wait_for_function("([s, lo, hi]) => { const w = document.querySelector(s).getBoundingClientRect().width; return w >= lo && w <= hi; }", arg=[selector, lo, hi], timeout=5000)
        return True
    except Exception:  # noqa: BLE001 - the check reports the miss
        return False


def set_style(page, mode):
    page.select_option("#style", mode)
    width = {"collapsed": (47.5, 48.5), "expanded": (71.5, 72.5), "wide": (238, 242)}[mode]
    wait_width(page, *width, mode)
    page.wait_for_timeout(120)


def mode_of(page):
    return page.evaluate("() => document.getElementById('rail').mode")


def stored(page, key):
    return page.evaluate("(k) => localStorage.getItem(k)", key)


def settle(page):
    """Before a still or a measure: pointer off the rail, focus on the page, so no hover or focus ring is mistaken for the state."""
    page.mouse.move(1000, 600)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(150)


def channel(value):
    value = value / 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def parse_color(text):
    nums = [float(n) for n in re.findall(r"[-\d.]+", text.replace("/", " "))]
    if text.startswith("color(srgb"):
        return [n * 255 for n in nums[:3]]
    return nums[:3]


def contrast(a, b):
    la, lb = (0.2126 * channel(c[0]) + 0.7152 * channel(c[1]) + 0.0722 * channel(c[2]) for c in (parse_color(a), parse_color(b)))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def shot(page, name):
    settle(page)
    right = page.evaluate("() => document.getElementById('rail').getBoundingClientRect().right")
    page.screenshot(path=str(OUT / f"{name}.png"), clip={"x": 0, "y": 0, "width": min(1280, right + 360), "height": 900})


def run(browser, base):
    # ---- collapsed: icons only ---------------------------------------------------------------------------------
    page = open_page(browser, base)
    g = geometry(page)
    check("collapsed: a fresh page starts on the icon rail (mode, and the stored value is not written until a choice)", g["mode"] == "collapsed" and stored(page, PREFIX) is None, g["mode"])
    check(f"collapsed: 3rem wide ({g['rail']['w']}px)", abs(g["rail"]["w"] - 48) <= 0.5)
    check(f"trap 7: collapsed: the rail's own destinations are counted, {len(g['dests'])} of {len(DESTS)}, one icon each",
          [d["id"] for d in g["dests"]] == DESTS and all(d["icons"] == 1 for d in g["dests"]) and page.evaluate("() => document.querySelectorAll('#rail svg').length") > len(DESTS),
          [d["id"] for d in g["dests"]])
    worst = max(max(abs(d["icon"]["cx"] - g["rail"]["cx"]) for d in g["dests"]), 0)
    check(f"collapsed: every icon sits on the rail's centre line (worst {worst:.2f}px)", worst <= 0.5)
    check("trap 6: collapsed: no label is drawn (computed display/visibility and measured width and height)", not any(d["labelShown"] for d in g["dests"]), [d["id"] for d in g["dests"] if d["labelShown"]])
    check("collapsed: each icon is 16px", all(abs(d["icon"]["w"] - 16) <= 0.5 and abs(d["icon"]["h"] - 16) <= 0.5 for d in g["dests"]), sorted({round(d["icon"]["w"], 1) for d in g["dests"]}))
    check("collapsed: a destination still names itself (title on the link) for the mouse and aria-label for a screen reader",
          page.evaluate("() => [...document.querySelectorAll('#rail .dv-rail-dest')].every((a) => a.title && a.getAttribute('aria-label') === a.querySelector('.dv-rail-label').textContent.trim())"))
    check("collapsed: no search field and no brand name are drawn", not page.evaluate(VISIBLE, "#rail .dv-rail-search") and not page.evaluate(VISIBLE, "#rail .dv-rail-brand-name"))
    check("collapsed: the resize handle is not shown (a fixed-width style)", not page.evaluate(VISIBLE, "#rail + .dv-splitter"))
    gap = g["dests"][1]["row"]["t"] - g["dests"][0]["row"]["b"]
    check(f"collapsed: rows are 32px, 4px apart inside a group ({gap}px)", all(abs(d["row"]["h"] - 32) <= 0.5 for d in g["dests"]) and abs(gap - 4) <= 0.5)
    shot(page, "collapsed-light")
    errors = list(page.errors)

    # ---- the settings select, and Figma's style ---------------------------------------------------------------
    options = page.evaluate("() => [...document.querySelectorAll('#style option')].map((o) => [o.value, o.textContent])")
    check("settings select: three options, Obsidian / Figma / Shopify, in that order", [o[0] for o in options] == ["collapsed", "expanded", "wide"] and [o[1] for o in options] == ["Obsidian: icon rail", "Figma: labels under icons", "Shopify: wide list"], options)
    check("settings select: shows the rail's mode", page.evaluate("() => document.getElementById('style').value") == "collapsed")
    set_style(page, "expanded")
    g = geometry(page)
    check(f"settings select: picking Figma's style makes the rail 72px ({g['rail']['w']}px) and the stored mode is written at once", abs(g["rail"]["w"] - 72) <= 0.5 and stored(page, PREFIX) == "expanded")
    worst = max(abs(d["icon"]["cx"] - g["rail"]["cx"]) for d in g["dests"])
    check(f"expanded: every icon sits on the rail's centre line (worst {worst:.2f}px)", worst <= 0.5)
    below = [d for d in g["dests"] if not (d["labelShown"] and d["label"]["t"] >= d["icon"]["b"] - 1)]
    check("expanded: every label is drawn BELOW its icon", not below, [d["id"] for d in below])
    off = max(abs(d["label"]["cx"] - d["icon"]["cx"]) for d in g["dests"])
    check(f"expanded: every label is centred under its icon within 0.5px (worst {off:.2f}px)", off <= 0.5)
    check("expanded: icons are 22px and labels stay inside their row", all(abs(d["icon"]["w"] - 22) <= 0.5 for d in g["dests"]) and all(d["label"]["b"] <= d["row"]["b"] + 0.5 and d["label"]["l"] >= d["row"]["l"] - 0.5 and d["label"]["r"] <= d["row"]["r"] + 0.5 for d in g["dests"]),
          sorted({round(d["icon"]["w"], 1) for d in g["dests"]}))
    check("trap 1: expanded: its stacking is its own (rows are columns) and the rail carries no data-state to confuse with another open style",
          all(d["flex"] == "column" for d in g["dests"]) and page.evaluate("() => !document.getElementById('rail').hasAttribute('data-state')"))
    lines = page.evaluate(LABEL_LINES, "calibration-runs")
    check(f"trap 3: expanded: 'CalibrationRuns' breaks at its camelCase seam, never mid-word ({' / '.join(lines)})", lines == ["Calibration", "Runs"], lines)
    whole = {i: page.evaluate(LABEL_LINES, i) for i in ("fleet", "dashboards", "runs", "settings")}
    check(f"trap 3: expanded: a one-word name that fits the column is never split ({whole})", all(len(v) == 1 for v in whole.values()), whole)
    g_by = {d["id"]: d for d in g["dests"]}
    check("trap 3: expanded: every label keeps its full text in title, and none is taller than two lines",
          all(d["title"] == d["text"].strip() and d["label"]["h"] <= 2 * 12.5 for d in g["dests"]), {d["id"]: d["label"]["h"] for d in g["dests"]})
    check("expanded: the long name clamps with an explicit ellipsis and keeps its whole text one hover away",
          g_by["hardware"]["title"] == "Hardware compatibility matrix and wiring" and page.evaluate("() => getComputedStyle(document.querySelector('#rail .dv-rail-dest[data-id=hardware] .dv-rail-label')).webkitLineClamp") == "2")
    check("expanded: no search field and no header collapse button", not page.evaluate(VISIBLE, "#rail .dv-rail-search") and not page.evaluate(VISIBLE, "#rail .dv-rail-collapse"))
    check("expanded: the resize handle is not shown", not page.evaluate(VISIBLE, "#rail + .dv-splitter"))
    shot(page, "expanded-light")

    # ---- Shopify's style ------------------------------------------------------------------------------------------
    set_style(page, "wide")
    g = geometry(page)
    check(f"trap 6: wide: the default width is 238-242px ({g['rail']['w']}px)", 238 <= g["rail"]["w"] <= 242)
    rows = g["dests"]
    check(f"wide: all {len(rows)} labels are drawn to the RIGHT of their icon (min gap {min(d['label']['l'] - d['icon']['r'] for d in rows):.1f}px)",
          all(d["labelShown"] and d["label"]["l"] - d["icon"]["r"] >= 4 for d in rows))
    dy = max(abs(d["label"]["cy"] - d["icon"]["cy"]) for d in rows)
    check(f"trap 6: wide: each label shares its icon's centre line within 0.5px (worst {dy:.2f}px)", dy <= 0.5)
    check("wide: rows are 32px and every icon is 16px", all(abs(d["row"]["h"] - 32) <= 0.5 for d in rows) and all(abs(d["icon"]["w"] - 16) <= 0.5 for d in rows))
    check("trap 1: wide: its rows are rows (flex-direction row), not the 72px rail's columns", all(d["flex"] == "row" for d in rows), sorted({d["flex"] for d in rows}))
    check(f"trap 7: wide: the destination count is still the rail's own {len(rows)}", [d["id"] for d in rows] == DESTS and all(d["icons"] == 1 for d in rows))
    hardware = {d["id"]: d for d in rows}["hardware"]
    check("truthful labels: a name too long for the row ends in an explicit ellipsis and its whole text is the title",
          hardware["clipped"] and hardware["title"] == "Hardware compatibility matrix and wiring" and page.evaluate("() => getComputedStyle(document.querySelector('#rail .dv-rail-dest[data-id=hardware] .dv-rail-label')).textOverflow") == "ellipsis")
    head = page.evaluate("""() => { const r = (s) => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return {l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height}; };
      return {brand: r('#rail .dv-rail-brand'), name: r('#rail .dv-rail-brand-name'), collapse: r('#rail .dv-rail-collapse'), search: r('#rail .dv-rail-search'), first: r('#rail .dv-rail-dest')}; }""")
    check("wide: the brand shows its name, with the collapse button right of it on the same line",
          head["name"] and head["name"]["w"] > 0 and head["collapse"] and head["collapse"]["l"] >= head["brand"]["r"] - 0.5 and head["collapse"]["t"] >= head["brand"]["t"] - 0.5 and head["collapse"]["b"] <= head["brand"]["b"] + 0.5 and head["collapse"]["r"] <= g["rail"]["r"], head)
    check("wide: the search field sits under the brand row and above the first destination", head["search"] and head["brand"]["b"] <= head["search"]["t"] + 0.5 and head["search"]["b"] <= head["first"]["t"], head["search"])
    groups = page.evaluate("() => [...document.querySelectorAll('#rail .dv-rail-group-label')].filter((e) => getComputedStyle(e).display !== 'none').map((e) => e.textContent)")
    check("wide: the groups are headed by their labels (Monitor, Data)", groups == ["Monitor", "Data"], groups)
    check("wide: the current destination carries aria-current=page", page.evaluate("() => [...document.querySelectorAll('#rail [aria-current=page]')].map((a) => a.dataset.id)") == ["fleet"])
    check("wide: the resize handle is shown on the right edge", page.evaluate(VISIBLE, "#rail + .dv-splitter"))
    shot(page, "wide-light")

    # ---- the wide search: a button, never opened by focus ----------------------------------------------------
    check("trap 4: the search field is a read-only role=button", page.evaluate("() => { const i = document.querySelector('#rail .dv-rail-search'); return i.readOnly && i.getAttribute('role') === 'button' && i.getAttribute('aria-haspopup') === 'dialog'; }"))
    page.evaluate("() => { window.__searches = 0; }")
    page.focus("#rail .dv-rail-search")
    page.wait_for_timeout(250)
    check("trap 4: focusing the search field opens nothing", page.evaluate("() => window.__searches") == 0)
    page.focus("#rail .dv-rail-collapse")
    page.keyboard.press("Tab")
    focused = page.evaluate("() => document.activeElement.className")
    page.keyboard.press("Tab")
    after = page.evaluate("() => document.activeElement.className + '|' + (document.activeElement.dataset.id || '')")
    check(f"trap 4: Tab goes through the search field (no focus trap): {focused} then {after}", "dv-rail-search" in focused and "search" not in after and page.evaluate("() => window.__searches") == 0, [focused, after])
    page.click("#rail .dv-rail-search")
    n1 = page.evaluate("() => window.__searches")
    page.focus("#rail .dv-rail-search")
    page.keyboard.press("Enter")
    n2 = page.evaluate("() => window.__searches")
    page.keyboard.press("Space")
    n3 = page.evaluate("() => window.__searches")
    check(f"trap 4: a click, Enter and Space each open it once (data-rail-search: {n1}, {n2}, {n3})", (n1, n2, n3) == (1, 2, 3))
    check("wide: the search shows its shortcut chip", page.evaluate("() => (document.querySelector('#rail .dv-rail-search-keys') || {}).textContent") == "Ctrl K")

    # ---- navigation, keys -------------------------------------------------------------------------------------
    page.evaluate("() => { window.__navigates = []; location.hash = ''; }")
    page.click("#rail .dv-rail-dest[data-id=runs]")
    check("navigate: a click fires data-rail-navigate with the id, follows the link and marks it current",
          page.evaluate("() => window.__navigates") == ["runs"] and page.evaluate("() => location.hash") == "#runs" and page.evaluate("() => document.getElementById('rail').current") == "runs")
    page.click("#rail .dv-rail-dest[data-id=dashboards]")
    check("navigate: preventDefault on the event stops the link (the host routes itself)", page.evaluate("() => window.__navigates.at(-1)") == "dashboards" and page.evaluate("() => location.hash") == "#runs")
    page.focus("#rail .dv-rail-dest[data-id=fleet]")
    page.keyboard.press("ArrowDown")
    first = page.evaluate("() => document.activeElement.dataset.id")
    page.keyboard.press("End")
    last = page.evaluate("() => document.activeElement.dataset.id")
    page.keyboard.press("Home")
    home = page.evaluate("() => document.activeElement.dataset.id")
    check(f"keys: arrows, End and Home move among the destinations ({first}, {last}, {home})", (first, last, home) == ("dashboards", "help", "fleet"))

    # ---- fold, toggle, remembered open style ------------------------------------------------------------------
    page.evaluate("() => { window.__changes = []; }")
    page.click("#rail .dv-rail-collapse")
    wait_width(page, 47.5, 48.5, "collapsed")
    check(f"fold: the collapse button collapses the wide list ({rail_width(page)}px, {mode_of(page)})", mode_of(page) == "collapsed" and abs(rail_width(page) - 48) <= 0.5)
    check("fold: focus moves to the footer toggle rather than falling to the page", page.evaluate("() => document.activeElement.classList.contains('dv-rail-toggle')"))
    page.keyboard.press("Control+Alt+r")
    ok = wait_width(page, 238, 242, "wide")
    check(f"trap 2: Ctrl+Alt+R re-opens the WIDE list, not Figma's: the open style is remembered ({mode_of(page)})", ok and mode_of(page) == "wide")
    page.keyboard.press("Control+Alt+r")
    check("Ctrl+Alt+R again collapses it", wait_width(page, 47.5, 48.5, "collapsed") and mode_of(page) == "collapsed")
    page.click("#rail .dv-rail-toggle")
    check("fold: the footer toggle opens the last open style", wait_width(page, 238, 242, "wide") and mode_of(page) == "wide")
    set_style(page, "expanded")
    page.keyboard.press("Control+Alt+r")
    wait_width(page, 47.5, 48.5, "collapsed")
    page.keyboard.press("Control+Alt+r")
    check(f"trap 2: after Figma's style the toggle goes collapsed and back to Figma's ({mode_of(page)}), never round the three", wait_width(page, 71.5, 72.5, "expanded") and mode_of(page) == "expanded")
    changes = page.evaluate("() => window.__changes.map((c) => c.previous + '>' + c.mode)")
    check(f"events: data-rail-mode-change fired for each change, with previous and mode ({changes})", changes == ["wide>collapsed", "collapsed>wide", "wide>collapsed", "collapsed>wide", "wide>expanded", "expanded>collapsed", "collapsed>expanded"], changes)
    before_keys = mode_of(page)
    page.keyboard.press("Control+Alt+x")
    page.keyboard.press("Alt+r")
    check("keys: other chords do nothing (only Ctrl/Cmd+Alt+R toggles)", mode_of(page) == before_keys, mode_of(page))
    page.evaluate("() => { document.getElementById('rail').setAttribute('hotkey', 'off'); }")
    page.keyboard.press("Control+Alt+r")
    check("keys: hotkey=off leaves Ctrl+Alt+R to the host (a second rail on the page)", mode_of(page) == before_keys, mode_of(page))
    page.evaluate("() => { document.getElementById('rail').removeAttribute('hotkey'); }")

    # ---- persistence ------------------------------------------------------------------------------------------
    page.select_option("#style", "wide")
    page.reload()  # WHY no wait between: the choice is written before the select's change handler returns (trap 5)
    page.wait_for_function("() => window.__ready === true")
    wait_width(page, 238, 242, "wide")
    check(f"trap 5: a style chosen and reloaded straight away survives ({mode_of(page)}, {rail_width(page):.0f}px)", mode_of(page) == "wide" and abs(rail_width(page) - 240) <= 2)
    page.evaluate("() => { document.getElementById('rail').mode = 'collapsed'; }")
    page.reload()
    page.wait_for_function("() => window.__ready === true")
    check("persist: collapsed survives a reload", mode_of(page) == "collapsed")
    page.keyboard.press("Control+Alt+r")
    check("persist: ...and the toggle after that reload still opens the wide list (lastOpen has its own key)", wait_width(page, 238, 242, "wide") and mode_of(page) == "wide")
    page.evaluate("() => { document.getElementById('rail').mode = 'expanded'; window.dispatchEvent(new Event('pagehide')); }")
    check("persist: pagehide rewrites both keys", stored(page, PREFIX) == "expanded" and stored(page, PREFIX + ".lastOpen") == "expanded", [stored(page, PREFIX), stored(page, PREFIX + ".lastOpen")])
    errors += page.errors
    page.context.close()

    page = open_page(browser, base, storage={PREFIX: "sideways"})
    check("persist: an unknown stored mode opens as the icon rail", mode_of(page) == "collapsed")
    page.context.close()
    page = open_page(browser, base, storage={PREFIX: "wide"})
    check("persist: a stored 'wide' is read back on a fresh page", mode_of(page) == "wide" and wait_width(page, 238, 242, "wide"))
    page.context.close()

    # ---- the wide style resizes, remembers, resets and folds (§11) ----------------------------------------------------
    page = open_page(browser, base, storage={PREFIX: "wide"})
    wait_width(page, 238, 242, "wide")
    handle = "#rail + .dv-splitter"
    check("resize: the wide rail has a splitter on its right edge (role=separator, focusable)", page.evaluate("() => { const h = document.querySelector('#rail + .dv-splitter'); return !!h && h.getAttribute('role') === 'separator' && h.tabIndex === 0; }"))
    main_left = lambda: page.evaluate("() => document.querySelector('main').getBoundingClientRect().left")  # noqa: E731
    before, ml_before = rail_width(page), main_left()
    box = page.locator(handle).bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    for step in range(1, 9):
        page.mouse.move(cx + 10 * step, cy)
    page.mouse.up()
    page.wait_for_timeout(120)
    after = rail_width(page)
    check(f"resize: a pointer drag of +80px widens the rail by 80px ({before:.0f} -> {after:.0f})", abs((after - before) - 80) <= 1.5)
    check(f"resize: the page beside it gives way by the same amount (main's left edge {ml_before:.0f} -> {main_left():.0f})", abs((main_left() - ml_before) - (after - before)) <= 1.5)
    stored_width = page.evaluate("(k) => localStorage.getItem(k)", WIDTH_KEY)
    check(f"resize: the width is remembered under {WIDTH_KEY} ({stored_width})", stored_width is not None and abs(float(stored_width) - after) <= 1.5)
    page.reload()
    page.wait_for_function("() => window.__ready === true")
    page.wait_for_timeout(300)
    check(f"resize: a reload keeps the width ({rail_width(page):.0f}px)", abs(rail_width(page) - after) <= 1.5)
    # past the ends: clamped to the 200-400px range
    box = page.locator(handle).bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 500, cy, steps=5)
    page.mouse.up()
    wide_max = rail_width(page)
    box = page.locator(handle).bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx - 700, cy, steps=5)
    page.mouse.up()
    wide_min = rail_width(page)
    check(f"resize: dragged past the ends it stops at the max and the min ({wide_max:.0f} and {wide_min:.0f}px)", abs(wide_max - 400) <= 1 and abs(wide_min - 200) <= 1)
    page.focus(handle)
    page.keyboard.press("ArrowRight")
    check(f"resize: the focused edge moves 16px with the arrow key ({wide_min:.0f} -> {rail_width(page):.0f})", abs(rail_width(page) - wide_min - 16) <= 1)
    # a stored width belongs to the wide style only
    page.evaluate("() => { document.getElementById('rail').mode = 'expanded'; }")
    wait_width(page, 71.5, 72.5, "expanded")
    check(f"resize: Figma's rail ignores the stored width ({rail_width(page):.0f}px) and hides the splitter", abs(rail_width(page) - 72) <= 0.5 and not page.evaluate(VISIBLE, handle))
    page.evaluate("() => { document.getElementById('rail').mode = 'wide'; }")
    page.wait_for_timeout(150)
    check(f"resize: back in the wide style the remembered width returns ({rail_width(page):.0f}px)", abs(rail_width(page) - (wide_min + 16)) <= 1.5)
    box = page.locator(handle).bounding_box()
    page.mouse.dblclick(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(150)
    check(f"resize: a double-click on the edge resets to 15rem and forgets the width ({rail_width(page):.0f}px, stored {page.evaluate('(k) => localStorage.getItem(k)', WIDTH_KEY)})",
          abs(rail_width(page) - 240) <= 1 and page.evaluate("(k) => localStorage.getItem(k)", WIDTH_KEY) is None)
    main_before = page.evaluate("() => document.querySelector('main').getBoundingClientRect().width")
    page.click("#rail .dv-rail-collapse")
    wait_width(page, 47.5, 48.5, "collapsed")
    main_after = page.evaluate("() => document.querySelector('main').getBoundingClientRect().width")
    check(f"resize: it folds: collapsed is 48px and the page takes the room back ({main_before:.0f} -> {main_after:.0f}px)", abs(rail_width(page) - 48) <= 0.5 and main_after > main_before + 150)
    errors += page.errors
    page.context.close()

    # ---- opt-out (§11) ------------------------------------------------------------------------------------------
    page = open_page(browser, base, storage={PREFIX: "wide"})
    wait_width(page, 238, 242, "wide")
    page.evaluate("() => { const r = document.getElementById('rail'); r.remove(); r.setAttribute('data-resizable', 'off'); document.body.prepend(r); }")
    page.wait_for_selector("#rail .dv-rail-dest")
    page.wait_for_timeout(200)
    check("resize: data-resizable=off gives the rail no splitter", page.evaluate("() => !document.querySelector('.dv-splitter')"))
    errors += page.errors
    page.context.close()

    # ---- both themes: the three styles stay legible, and are shot --------------------------------------------------
    for dark in (False, True):
        tag = "dark" if dark else "light"
        page = open_page(browser, base, dark=dark, query="?dark" if dark else "")
        measured = {}
        for mode in ("collapsed", "expanded", "wide"):
            set_style(page, mode)
            settle(page)
            colours = page.evaluate("""() => { const rail = document.getElementById('rail'), a = rail.querySelector('.dv-rail-dest[data-id=runs]'), cur = rail.querySelector('[aria-current=page]');
              const lab = a.querySelector('.dv-rail-label');
              return {bg: getComputedStyle(rail).backgroundColor, fg: getComputedStyle(mode_label()).color, icon: getComputedStyle(a.querySelector('[data-rail-icon]')).color, page: getComputedStyle(document.body).backgroundColor,
                current: getComputedStyle(cur).backgroundColor};
              function mode_label() { return rail.getAttribute('mode') === 'collapsed' ? a.querySelector('[data-rail-icon]') : lab; } }""")
            measured[mode] = colours
            check(f"{tag}: {mode}: label/icon text against the rail's background is at least 4.5:1 ({contrast(colours['fg'], colours['bg']):.1f})", contrast(colours["fg"], colours["bg"]) >= 4.5, colours)
            if mode != "collapsed":
                shot(page, f"{mode}-{tag}")
            else:
                shot(page, f"collapsed-{tag}")
        check(f"{tag}: the rail's background is not the page's, and the current destination has its own fill",
              all(m["bg"] != m["page"] and m["current"] not in (m["bg"], "rgba(0, 0, 0, 0)") for m in measured.values()), measured["wide"])
        errors += page.errors
        page.context.close()

    # ---- the gallery page (site/rail-page.mjs): live demo with its select, and the three styles side by side ------------
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{base}/dist/site/gallery/app-rail/index.html")
    page.wait_for_function("() => document.querySelector('#demo .dv-rail-dest') && document.querySelectorAll('#style option').length === 3")
    widths = page.evaluate("() => [...document.querySelectorAll('.trio data-rail')].map((r) => [r.getAttribute('mode'), r.getBoundingClientRect().width])")
    check(f"gallery page: the three styles side by side are 3rem, 4.5rem and 15rem ({widths})", [w[0] for w in widths] == ["collapsed", "expanded", "wide"] and [round(w[1]) for w in widths] == [48, 72, 240], widths)
    page.select_option("#style", "expanded")
    check("gallery page: its settings select changes the live rail to 72px", wait_width_of(page, "#demo", 71.5, 72.5))
    page.select_option("#style", "wide")
    check("gallery page: ...and to the 240px wide list, whose edge has a drag handle", wait_width_of(page, "#demo", 238, 242) and page.evaluate("() => { const h = document.querySelector('#demo + .dv-splitter'); return !!h && h.getBoundingClientRect().width > 0; }"))
    check("gallery page: no script errors", not page.errors, page.errors[:3])
    context.close()

    check("no script errors or console errors on any page", not errors, errors[:3])


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
                urllib.request.urlopen(base + "/tests/browser/fixtures/rail.html", timeout=1)
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
    (OUT / "rail-checks.json").write_text(json.dumps(checks, indent=1, ensure_ascii=False), encoding="utf-8")
    passed = sum(c["ok"] for c in checks)
    print(f"{passed}/{len(checks)} rail checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
