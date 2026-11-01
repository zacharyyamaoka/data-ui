"""The dashboard editor's paths its frozen ruler (dash_editor_checks.py) does not walk: Add, a note, Duplicate, Plots, Visible, the rail
while editing, a per-pick dashboard, two dashboards on a page, a host that calls load() itself, the window crossing the narrow
width. Written after the code, so these are no red-first ruler; the same real mouse and keyboard, the same text oracle.

    $DATA_UI_PYTHON tests/browser/dash_editor_more_checks.py [OUT_DIR]     # after npm run build

Serves the repo root on a free 127.0.0.1 port, stops it when done, writes OUT_DIR/dash-editor-more-checks.json (default
reports/media/dash-editor) and exits 1 if any check fails.
"""

from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

import dash_editor_checks as e  # noqa: E402  its helpers, its fixture and its oracle; importing it runs nothing

check, guard, rev, settle, text, same_text, OPT, ROW, P, BAR, D = e.check, e.guard, e.rev, e.settle, e.text, e.same_text, e.OPT, e.ROW, e.P, e.BAR, e.D
SERVO = e.SERVO
WAIT = e.WAIT


def adding(pages):
    page = pages.open(e.PAGE)
    e.edit(page)
    page.locator(ROW("angle")).click()
    r = rev(page)
    page.locator(BAR("edit-add")).click()
    page.locator('.dde-menu [data-dde="add-view-samples"]').click()
    settle(page, r, "add a view")
    t = text(page)
    rem, _ = e.changed(SERVO, t)
    check("add: a new view only adds lines", not rem, rem[:3])
    names = e.layout_names(t)
    check("add: it lands right after the selected panel", names[names.index("Angle") + 1] == "New panel", names)
    check("add: it is selected, in the outline and the options pane", page.input_value(OPT("title")) == "New panel")
    js, py, out = e.checkers(t)
    check("add: both checkers accept it", js and py, out)
    r = rev(page)
    page.locator(BAR("edit-add")).click()
    page.locator('.dde-menu [data-dde="add-note"]').click()
    settle(page, r, "add a note")
    page.wait_for_selector(OPT("text"), timeout=WAIT)
    r = rev(page)
    page.fill(OPT("text"), "Hello **there**")
    page.locator(OPT("w")).focus()
    settle(page, r, "type a note")
    check("add: a note's text lands in the file and draws", "- text: Hello **there**" in text(page) or "'Hello **there**'" in text(page), text(page)[text(page).index("A note") if "A note" in text(page) else 0:][:60])
    check("add: the note draws its markdown", page.locator(f"{D} .dd-text strong", has_text="there").count() == 1)
    page.context.close()
    page = pages.open(e.PAGE)
    e.edit(page)
    page.locator(ROW("angle")).click()
    page.wait_for_selector(OPT("duplicate"), timeout=WAIT)
    r = rev(page)
    page.locator(OPT("duplicate")).click()
    settle(page, r, "duplicate")
    t = text(page)
    names = e.layout_names(t)
    check("duplicate: the copy sits right after it, the same width, under its own name", names[names.index("Angle") + 1] == "Angle (2)" and "w: 6" in [l for l in t.splitlines() if "Angle (2)" in l and "view:" in l][0], names)
    check("duplicate: the copy is selected", page.locator(f'{OUTLINE_SEL()}[aria-selected="true"]').get_attribute("data-key").startswith("angle"))
    js, py, out = e.checkers(t)
    check("duplicate: both checkers accept it", js and py, out)
    page.context.close()
    page = pages.open(e.PAGE)
    e.edit(page)
    page.locator(ROW("angle")).click()
    page.wait_for_selector(OPT("signal"), timeout=WAIT)
    r = rev(page)
    page.select_option(OPT("signal"), "tau_nm")
    settle(page, r, "plots")
    same_text("plots: a new signal changes one token", text(page), SERVO.replace("timeseries: { x: t, 'y': q_deg,", "timeseries: { x: t, 'y': tau_nm,"))
    r = rev(page)
    page.keyboard.press("Control+z")
    settle(page, r, "undo")
    r = rev(page)
    page.locator(OPT("visible")).uncheck()
    settle(page, r, "hide by the box")
    check("visible: the box hides the panel, and the options stay on it", page.locator(P("angle")).count() == 0 and not page.locator(OPT("visible")).is_checked())
    r = rev(page)
    page.locator(OPT("visible")).check()
    settle(page, r, "show by the box")
    same_text("visible: and shows it again, to the byte", text(page), SERVO)
    page.context.close()


def OUTLINE_SEL():
    return f"{e.OUTLINE} .dde-row[data-key]"


def rail(pages):
    page = pages.open(e.PAGE)
    e.edit(page)
    page.locator(BAR("edit-filters")).click()
    page.wait_for_selector(f"{D} .dd-rail", state="visible", timeout=WAIT)
    page.wait_for_timeout(200)
    before = page.evaluate("() => JSON.stringify(document.querySelector('#servo').state.rail)")
    page.locator(f"{D} .dd-rail input").nth(2).click()
    page.wait_for_timeout(300)
    after = page.evaluate("() => JSON.stringify(document.querySelector('#servo').state.rail)")
    check("rail: a pick works while editing", before != after)
    same_text("rail: a pick is a reader's state, not an edit of the file", text(page), SERVO)
    check("rail: nothing to save", page.locator(BAR("edit-save")).is_disabled())
    page.context.close()


def per_pick(pages):
    """A dashboard whose dataset is read one run at a time (CONTRACT §33): its wait line stays one, in its panel's box."""
    ctx = pages.browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    page = ctx.new_page()
    page.on("pageerror", lambda x: pages.errors.append(str(x)))
    page.goto(pages.base + "/dist/site/gallery/robotics-deployments/index.html")
    page.wait_for_selector('#example[data-view="dashboard"]', timeout=WAIT)
    page.wait_for_timeout(600)
    page.evaluate("() => document.querySelector('#example').setAttribute('editor', '')")
    page.locator('#example [data-act="edit"]').click()
    page.wait_for_selector(f"#example[data-editing] {e.OUTLINE} .dde-row", timeout=WAIT)
    page.wait_for_timeout(600)
    m = page.evaluate("""() => [...document.querySelectorAll('#example .dd-panel[data-wait]')].map((s) => s.querySelectorAll('.dd-wait').length)""")
    check("per-pick: a panel waiting for a pick keeps one wait line while editing", all(n == 1 for n in m), m)
    page.evaluate("() => document.querySelector('#example').reload()")
    page.wait_for_timeout(900)
    m = page.evaluate("""() => [...document.querySelectorAll('#example .dd-panel[data-wait]')].map((s) => s.querySelectorAll('.dd-wait').length)""")
    check("per-pick: and after a reload", all(n == 1 for n in m), m)
    ctx.close()


def two(pages):
    page = pages.browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce").new_page()
    page.on("pageerror", lambda x: pages.errors.append(str(x)))
    page.goto(pages.base + e.URL + "two.html")
    page.wait_for_selector("#a [data-act=edit]", timeout=WAIT)
    page.wait_for_selector("#b [data-act=edit]", timeout=WAIT)
    page.locator("#a [data-act=edit]").click()
    page.wait_for_selector(f"#a[data-editing] {e.OUTLINE} .dde-row", timeout=WAIT)
    page.wait_for_timeout(300)
    rows = page.locator(f"#a {e.OUTLINE} .dde-row[data-key]")
    rows.first.click()
    r = page.evaluate("() => +(document.querySelector('#a').dataset.ddeRev || 0)")
    page.keyboard.press("Alt+ArrowDown")
    page.wait_for_function(f"() => +(document.querySelector('#a').dataset.ddeRev || 0) > {r}", timeout=WAIT)
    page.locator("#b").focus()
    page.keyboard.press("Control+s")
    page.wait_for_timeout(300)
    check("two dashboards: a key belongs to the one the focus is in", page.locator(f"#a {e.OPTIONS} .dde-diff").count() == 0)
    page.context.close()


def load_host(pages):
    page = pages.open(e.URL + "host-load.html")
    check("load(): a host that sets baseText is offered Edit", page.locator(BAR("edit")).count() == 1)
    e.edit(page)
    page.locator(ROW("angle")).click()
    e.set_opt(page, "w", 4)
    same_text("load(): it edits the text it was given", text(page), SERVO.replace(e.L_ANGLE, e.L_ANGLE.replace("w: 6", "w: 4")))
    page.context.close()
    page = pages.open(e.URL + "host-load.html?text=0")
    check("load(): with no text, no Edit: a parsed document has lost its comments", page.locator(BAR("edit")).count() == 0)
    page.context.close()


def narrow(pages):
    page = pages.open(e.PAGE)
    e.edit(page)
    page.locator(ROW("angle")).click()
    e.set_opt(page, "w", 4)
    draft = text(page)
    page.set_viewport_size({"width": 600, "height": 800})
    page.wait_for_function(f"() => document.querySelector('{D}').hasAttribute('data-dde-narrow')", timeout=WAIT)
    page.wait_for_function(f"() => !document.querySelector('{D} .dd-grid').classList.contains('grid-stack')", timeout=WAIT)
    page.wait_for_timeout(300)
    check("narrow: under 700 px the grid lets go, the draft stays, no sideways scroll", text(page) == draft and page.evaluate(e.SCROLL) <= 600, page.evaluate(e.SCROLL))
    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_selector(f"{D} .dd-grid.grid-stack .dd-panel.grid-stack-item", timeout=WAIT)
    page.wait_for_timeout(300)
    a = e.rect(page, P("angle"))
    g = e.rect(page, f"{D} .dd-grid")
    check("narrow: wide again, the grid is back, with the draft's width", text(page) == draft and abs(a["w"] - g["w"] / 3) <= 3, {"panel": a["w"], "grid": g["w"]})
    page.context.close()


def main() -> int:
    proc, base = e.serve(e.ROOT, e.PAGE)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            pages = e.Pages(browser, base)
            for name, journey in (("adding", adding), ("rail", rail), ("per-pick", per_pick), ("two dashboards", two), ("load()", load_host), ("narrow", narrow)):
                with guard(name):
                    journey(pages)
            check("no page errors in any journey", not pages.errors, pages.errors[:3])
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    (e.OUT / "dash-editor-more-checks.json").write_text(json.dumps(e.checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in e.checks if not c["ok"]]
    print(f"\n{len(e.checks) - len(failed)} of {len(e.checks)} checks pass")
    return 1 if failed or not e.checks else 0


if __name__ == "__main__":
    sys.exit(main())
