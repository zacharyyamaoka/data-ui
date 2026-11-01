"""Record the notion table's hero video and stills from the real page, with the real mouse, keyboard and clipboard.

Usage (the repo root served, after npm run build; the page is the gallery case on the built site):
    python3 -m http.server 47631 --bind 127.0.0.1 --directory <repo>
    ~/psu-atlas/.venv/bin/python docs/capture_notion_table.py http://127.0.0.1:47631 <out dir>

Writes <out dir>/raw/*.webm (Playwright's own screencast of the page), <out dir>/marks.json (seconds since the context opened for
each step), and <out dir>/*.png, the stills. docs/build_notion_table_report.py encodes and embeds them. One take, no speed change, and
nothing drawn on top but the pointer: headless video has none, and a reader needs to see where each click lands.
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE, OUT = sys.argv[1].rstrip("/"), Path(sys.argv[2])
(OUT / "raw").mkdir(parents=True, exist_ok=True)
PAGE = f"{BASE}/dist/site/gallery/notion-table/"
V = "#example"
W, H = 1180, 640
marks = {}
t0 = None


def mark(name):
    marks[name] = round(time.monotonic() - t0, 2)
    print(f"{marks[name]:6.2f}s  {name}", flush=True)


def cursor(page):
    page.add_init_script("""
      addEventListener('DOMContentLoaded', () => {
        const d = document.createElement('div'); d.id = '__cur';
        d.style.cssText = 'position:fixed;left:-40px;top:-40px;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;' +
          'background:rgba(220,38,38,.35);border:2px solid rgba(220,38,38,.9);z-index:2147483647;pointer-events:none;transition:transform .12s';
        document.body.appendChild(d);
        addEventListener('mousemove', (e) => { d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; }, true);
        addEventListener('mousedown', () => { d.style.transform = 'scale(.6)'; }, true);
        addEventListener('mouseup', () => { d.style.transform = ''; }, true);
      });""")


def centre(locator):
    b = locator.bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def glide(page, locator, steps=14, button="left"):
    """Move the pointer to an element, visibly, then click it."""
    x, y = centre(locator)
    page.mouse.move(x, y, steps=steps)
    page.wait_for_timeout(180)
    page.mouse.click(x, y, button=button)


def clip(page, block):
    rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in line) + "</tr>" for line in block)
    text = "\n".join("\t".join(line) for line in block) + "\n"
    page.evaluate("""async ([text, html]) => {
      await navigator.clipboard.write([new ClipboardItem({ 'text/plain': new Blob([text], { type: 'text/plain' }), 'text/html': new Blob([html], { type: 'text/html' }) })]);
    }""", [text, f"<table><tbody>{rows}</tbody></table>"])


def cell(page, row, col):
    return page.locator(f'{V} tbody tr[data-id="{row}"] td[data-col="{col}"]')


def settle(page, ms=120):
    page.wait_for_timeout(ms)


def show_page(page):
    """The hint at the top of the window, clear of the site's sticky header."""
    page.evaluate("() => scrollTo(0, document.querySelector('[data-hint]').getBoundingClientRect().top + scrollY - 72)")


def hero(browser):
    global t0
    context = browser.new_context(viewport={"width": W, "height": H}, color_scheme="light", record_video_dir=str(OUT / "raw"), record_video_size={"width": W, "height": H})
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE)
    page = context.new_page()
    t0 = time.monotonic()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    cursor(page)
    # WHY #edit=0: the page opens in Edit for a fresh viewer; the take starts in View, to show the switch
    page.goto(PAGE + "#edit=0")
    page.wait_for_selector(f"{V} tbody tr[data-i]")
    show_page(page)
    settle(page, 700)
    mark("view")
    page.screenshot(path=str(OUT / "view.png"))
    settle(page, 500)

    glide(page, page.locator(f"{V} [data-edit-switch]:visible"))
    settle(page, 700)
    mark("edit")
    page.screenshot(path=str(OUT / "edit.png"))

    # a blank cell: click it, type, Enter
    glide(page, cell(page, "r3", "owner"))
    settle(page, 250)
    page.keyboard.type("Mia", delay=70)
    page.keyboard.press("Enter")
    settle(page, 600)
    mark("cell")

    # a block from a spreadsheet, into the blank row
    clip(page, [["todo", "Kai", "8"], ["doing", "Zed", "13"], ["todo", "Lee", "5"]])
    glide(page, cell(page, "r5", "status"))
    settle(page, 300)
    page.keyboard.press("Control+V")
    settle(page, 500)
    mark("paste")
    page.screenshot(path=str(OUT / "paste.png"))
    settle(page, 1000)

    # a column, from its header's menu
    th = page.locator(f'{V} thead th[data-col="owner"]')
    x, y = centre(th)
    page.mouse.move(x, y, steps=14)
    settle(page, 220)
    glide(page, th.locator("[data-col-menu]"), steps=4)
    page.wait_for_selector(f"{V} .dv-pop.dv-colmenu:not([hidden])")
    settle(page, 450)
    mark("menu")
    page.screenshot(path=str(OUT / "menu.png"))
    menu = page.locator(f"{V} .dv-pop.dv-colmenu")
    glide(page, menu.locator("[data-col-add]"), steps=8)
    settle(page, 240)
    menu.locator('[name="name"]').click()
    page.keyboard.type("Reviewed", delay=55)
    menu.locator('[name="kind"]').select_option("checkbox")
    settle(page, 320)
    glide(page, menu.locator("button[type=submit]"), steps=8)
    settle(page, 450)
    glide(page, cell(page, "r2", "reviewed"))
    settle(page, 550)
    mark("column")

    # a filter by hand, on the column's own control
    th = page.locator(f'{V} thead th[data-col="status"]')
    x, y = centre(th)
    page.mouse.move(x, y, steps=12)
    settle(page, 200)
    glide(page, th.locator("[data-col-menu]"), steps=4)
    page.wait_for_selector(f"{V} .dv-pop.dv-colmenu:not([hidden])")
    settle(page, 300)
    glide(page, page.locator(f"{V} .dv-pop.dv-colmenu [data-col-filter]"), steps=8)
    page.wait_for_selector(f"{V} .dv-pop.dv-colfilter:not([hidden])")
    settle(page, 300)
    glide(page, page.locator(f'{V} .dv-pop.dv-colfilter [data-filter-values] input[value="todo"]'), steps=8)
    settle(page, 700)
    mark("filter")
    page.screenshot(path=str(OUT / "filter.png"))
    page.keyboard.press("Escape")
    settle(page, 500)
    glide(page, page.locator(f"{V} .dv-pill-x"), steps=10)
    settle(page, 600)

    # a row, from its right-click: no dialog, an Undo in the toast
    glide(page, cell(page, "r3", "task"), button="right")
    settle(page, 450)
    mark("rowmenu")
    glide(page, page.locator(".dv-itemmenu [data-row-delete]"), steps=8)
    settle(page, 850)
    mark("deleted")
    page.screenshot(path=str(OUT / "toast.png"))
    glide(page, page.locator(f"{V} .dv-toast [data-toast-undo]"), steps=16)
    settle(page, 1000)
    mark("undone")
    context.close()
    if errors:
        print("PAGE ERRORS:", errors)
    return errors


def stills(browser):
    """The narrow and dark states, for the page under the video."""
    for name, dark, width, height in (("phone-dark", True, 390, 780), ("wide-dark", True, 1180, 640)):
        context = browser.new_context(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light", is_mobile=width < 500, has_touch=width < 500)
        page = context.new_page()
        page.goto(PAGE)
        page.wait_for_selector(f"{V} tbody tr[data-i]")
        show_page(page)
        settle(page, 300)
        if width >= 500:
            page.evaluate("() => document.querySelector('#example').deleteRows(['r2'])")
        else:
            page.locator(f'{V} thead th[data-col="task"] [data-col-menu]').click()
        settle(page, 300)
        page.screenshot(path=str(OUT / f"{name}.png"))
        context.close()
    context = browser.new_context(viewport={"width": W, "height": H}, color_scheme="light")
    page = context.new_page()
    page.goto(PAGE)
    page.wait_for_selector("[data-new-blank]")
    page.locator("[data-new-blank]").click()
    page.wait_for_selector(f'{V} thead th[data-col="name"]')
    show_page(page)
    settle(page, 300)
    page.screenshot(path=str(OUT / "blank.png"))
    context.close()


with sync_playwright() as pw:
    chromium = pw.chromium.launch()
    bad = hero(chromium)
    stills(chromium)
    chromium.close()
(OUT / "marks.json").write_text(json.dumps(marks, indent=1), encoding="utf-8")
sys.exit(1 if bad else 0)
