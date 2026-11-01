"""Record the notes page's hero video and stills from the real server, with the real mouse and keyboard (docs/CONTRACT.md §46).

    ~/psu-atlas/.venv/bin/python docs/capture_md_pages.py <out dir>      # after npm run build

Copies gallery/md-pages to a temp folder, starts tools/serve-md.mjs on a free port from 4531 up, records one take, stops the server.
Writes <out dir>/raw/*.webm, stills, marks.json, and before/after copies of the notes the take changed. The hand edit in the take is a real write to the
note from outside the browser. docs/build_md_pages_report.py encodes and embeds them.
"""
import json
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(sys.argv[1])
(OUT / "raw").mkdir(parents=True, exist_ok=True)
(OUT / "files").mkdir(parents=True, exist_ok=True)
V = "#notes"
W, H = 1280, 720
ROW = "fb-f8f638df"
marks = {}


def free_port():
    for port in range(4531, 4600):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit("no free port")


CURSOR = """addEventListener('DOMContentLoaded', () => {
  const d = document.createElement('div');
  d.style.cssText = 'position:fixed;left:-40px;top:-40px;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;background:rgba(220,38,38,.35);border:2px solid rgba(220,38,38,.9);z-index:2147483647;pointer-events:none;transition:transform .12s';
  document.body.appendChild(d);
  addEventListener('mousemove', (e) => { d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => { d.style.transform = 'scale(.6)'; }, true);
  addEventListener('mouseup', () => { d.style.transform = ''; }, true);
});"""


def glide(page, x, y, steps=18):
    page.mouse.move(x, y, steps=steps)


def box(page, sel):
    b = page.locator(sel).first.bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def click(page, sel, pause=350):
    x, y = box(page, sel)
    glide(page, x, y)
    page.wait_for_timeout(180)
    page.mouse.click(x, y)
    page.wait_for_timeout(pause)


def hero(browser, url, tmp):
    fb = tmp / "feedback"
    note = fb / f"{ROW}.md"
    shutil.copy(note, OUT / "files" / "before.md")
    shutil.copy(fb / "views.base", OUT / "files" / "before.base")
    ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(OUT / "raw"), record_video_size={"width": W, "height": H}, color_scheme="light")
    ctx.add_init_script(CURSOR)
    page = ctx.new_page()
    t0 = time.monotonic()
    mark = lambda name: marks.__setitem__(name, round(time.monotonic() - t0, 2))
    page.goto(f"{url}/?db=feedback")
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    page.wait_for_timeout(900)
    mark("table")
    page.locator(f'{V} tr.dv-row[data-id="{ROW}"] td[data-col="name"]').first.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    x, y = box(page, f'{V} tr.dv-row[data-id="{ROW}"] td[data-col="name"]')
    glide(page, x, y)
    page.wait_for_timeout(200)
    page.mouse.click(x, y)
    page.wait_for_selector(f"{V} .dv-peek .dv-page-blocks", timeout=8000)
    page.wait_for_timeout(1100)
    mark("page open")
    page.locator(f"{V} .dv-peek").evaluate("(p) => p.scrollTo(0, 0)")
    click(page, f"{V} .dv-peek [data-page-hidden]", 500)
    click(page, f'{V} .dv-peek .dv-page-off[data-page-entry="copied_from"] [data-page-menu]', 500)
    page.screenshot(path=str(OUT / "menu.png"))
    click(page, f'{V} .dv-pop [data-place-to="section"]', 900)
    mark("preview")
    page.screenshot(path=str(OUT / "preview.png"))
    page.wait_for_timeout(900)
    click(page, f"{V} .dv-pop [data-place-go]", 1100)
    page.wait_for_selector(f'{V} .dv-peek [data-page-block="copied_from"]', timeout=6000)
    mark("moved")
    shutil.copy(note, OUT / "files" / "after-section.md")
    page.wait_for_timeout(600)
    # drag the Desired block above Copied from
    page.locator(f'{V} .dv-peek [data-page-block="desired"]').scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    head = page.locator(f'{V} .dv-peek [data-page-block="copied_from"]').bounding_box()
    page.locator(f"{V} .dv-peek").evaluate("(p) => p.scrollTo(0, 150)")
    page.wait_for_timeout(300)
    page.locator(f'{V} .dv-peek [data-page-block="desired"] .dv-page-head').hover()
    g = page.locator(f'{V} .dv-peek [data-page-block="desired"] [data-page-grip]').bounding_box()
    head = page.locator(f'{V} .dv-peek [data-page-block="copied_from"]').bounding_box()
    glide(page, g["x"] + g["width"] / 2, g["y"] + g["height"] / 2)
    page.mouse.down()
    page.mouse.move(g["x"] + 6, head["y"] + 30, steps=26)
    page.wait_for_timeout(350)
    page.mouse.move(g["x"] + 6, head["y"] + 3, steps=8)
    page.wait_for_timeout(250)
    page.mouse.up()
    page.wait_for_timeout(1000)
    mark("dragged")
    # a hand edit, from outside the browser
    text = note.read_text(encoding="utf-8")
    note.write_text(text.replace("Desired is notions", "EDITED IN OBSIDIAN: Desired is notions"), encoding="utf-8")
    page.wait_for_function(f"document.querySelector('{V} .dv-peek [data-page-block=\"desired\"]').innerText.includes('EDITED IN OBSIDIAN')", timeout=4000)
    mark("hand edit")
    page.wait_for_timeout(1400)
    # back to the frontmatter with the same two clicks
    ctx.close()
    video = next((OUT / "raw").glob("*.webm"))
    video.rename(OUT / "raw" / "hero.webm")
    shutil.copy(note, OUT / "files" / "after-hand.md")
    shutil.copy(fb / "views.base", OUT / "files" / "after.base")
    (OUT / "marks.json").write_text(json.dumps(marks, indent=1), encoding="utf-8")


def stills(browser, url, tmp):
    for name, w, h, dark, mobile in (("light", 1400, 860, False, False), ("dark", 1400, 860, True, False), ("390-light", 390, 844, False, True), ("390-dark", 390, 844, True, True)):
        ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme="dark" if dark else "light", has_touch=mobile, is_mobile=mobile)
        page = ctx.new_page()
        page.goto(f"{url}/?db=feedback")
        page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / f"table-{name}.png"))
        page.locator(f'{V} tr.dv-row[data-id="fb-f8f638df"] .dv-row-open').evaluate("(b) => b.click()")
        page.wait_for_selector(f"{V} .dv-peek .dv-page-blocks", timeout=8000)
        page.wait_for_timeout(450)
        page.screenshot(path=str(OUT / f"page-{name}.png"))
        ctx.close()
    ctx = browser.new_context(viewport={"width": 1400, "height": 860}, color_scheme="light")
    page = ctx.new_page()
    page.goto(f"{url}/?db=frdparrc")
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / "frdparrc-table.png"))
    page.locator(f'{V} tr.dv-row[data-id="vibetracks.1"] td[data-col="dp"]').first.click()
    page.wait_for_selector(f"{V} .dv-peek .dv-page-blocks", timeout=8000)
    page.wait_for_timeout(450)
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    page.locator(f"{V} .dv-peek").evaluate("(p) => p.scrollTo(0, 0)")
    page.wait_for_timeout(150)
    page.screenshot(path=str(OUT / "frdparrc-page.png"))
    page.locator(f"{V} [data-page-full]").click()
    page.wait_for_timeout(350)
    page.screenshot(path=str(OUT / "frdparrc-full.png"))
    # a type that does not fit, shown as the reader sees it
    page.locator(f"{V} [data-page-full]").click()
    page.wait_for_timeout(200)
    entry = page.locator(f'{V} .dv-peek [data-page-entry="status"]')
    entry.hover()
    entry.locator("[data-page-menu]").click()
    page.locator(f'{V} .dv-pop [data-place-to="section"]').click()
    page.wait_for_selector(f"{V} .dv-pop [data-place-note]", timeout=4000)
    page.wait_for_timeout(200)
    page.screenshot(path=str(OUT / "type-preview.png"))
    ctx.close()


def table_first(browser, url, tmp):
    """The same note at each step: a new row, two cells, an H2 on the page, the outline back in the table."""
    words = "Starts as a row in the table"
    note = tmp / "frdparrc" / f"{words}.md"
    row = f'{V} tr.dv-row[data-id="{words}"]'
    ctx = browser.new_context(viewport={"width": 1400, "height": 860}, color_scheme="light")
    page = ctx.new_page()
    page.goto(f"{url}/?db=frdparrc")
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    page.locator(f"{V} button", has_text="FRDPARRC").first.click()
    page.wait_for_selector(f'{V} th[data-col="risks"]', timeout=5000)
    page.locator(f'{V} tr.dv-addrow [data-add-col="fr"] textarea').first.click()
    page.keyboard.type(words)
    for _ in range(14):
        if note.exists():
            break
        page.keyboard.press("Enter")
        page.wait_for_timeout(120)
    page.wait_for_selector(row, timeout=4000)
    shutil.copy(note, OUT / "files" / "first-1-row.md")
    for col, value in (("dp", "A first idea, typed in the cell"), ("risks", "It may be slow")):
        page.locator(f'{row} td[data-col="{col}"]').first.click()
        page.locator(f"{V} .dv-celledit textarea").first.wait_for(timeout=4000)
        page.keyboard.type(value)
        page.keyboard.press("Enter")
        page.wait_for_timeout(350)
    shutil.copy(note, OUT / "files" / "first-2-cells.md")
    page.screenshot(path=str(OUT / "first-cells.png"))
    page.locator(f'{row} td[data-col="name"]').first.click()
    page.wait_for_selector(f"{V} .dv-peek .dv-page-blocks", timeout=8000)
    page.wait_for_timeout(200)
    page.locator(f'{V} .dv-peek [data-page-block="dp"] [data-page-read]').click(position={"x": 40, "y": 8})
    ta = page.locator(f'{V} .dv-peek [data-page-block="dp"] textarea')
    ta.wait_for(timeout=3000)
    ta.press("Control+End")
    page.keyboard.type("\n\n## Option A\n\nThe words behind it\n\n## Option B")
    page.locator(f"{V} .dv-peek header h2").click()
    page.wait_for_timeout(450)
    shutil.copy(note, OUT / "files" / "first-3-page.md")
    page.screenshot(path=str(OUT / "first-page.png"))
    page.locator(f"{V} .dv-peek .dv-close").click()
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / "first-outline.png"))
    ctx.close()


def links(browser, url, tmp):
    """Every wikilink form in a section. The section is written here for the picture, in the temp copy, not in the case."""
    note = tmp / "feedback" / "fb-25f0fb32.md"
    picture = "3f7b8dc77d66ece3cee0997329e3ea4b.png"
    note.write_text(note.read_text(encoding="utf-8").rstrip("\n") + f"\n\n# Linked\n\nSee [[Some Note]], [[Some Note|the alias]] and [[Some Note#A heading]].\n\n![[{picture}]]\n", encoding="utf-8")
    shutil.copy(note, OUT / "files" / "wikilinks.md")
    time.sleep(0.4)
    ctx = browser.new_context(viewport={"width": 1400, "height": 860}, color_scheme="light")
    page = ctx.new_page()
    page.goto(f"{url}/?db=feedback")
    page.wait_for_selector(f"{V} tr.dv-row", timeout=15000)
    page.locator(f'{V} tr.dv-row[data-id="fb-25f0fb32"] td[data-col="name"]').first.click()
    page.wait_for_selector(f'{V} .dv-peek [data-page-block="linked"]', timeout=8000)
    page.wait_for_timeout(450)
    page.screenshot(path=str(OUT / "obsidian.png"))
    ctx.close()


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="md-pages-capture-"))
    for name in ("feedback", "frdparrc"):
        shutil.copytree(ROOT / "gallery" / "md-pages" / name, tmp / name)
    port = free_port()
    server = subprocess.Popen(["node", str(ROOT / "tools" / "serve-md.mjs"), str(tmp / "feedback"), str(tmp / "frdparrc"), "--port", str(port), "--vault", "Demo vault", "--vault-root", str(tmp)], stdout=subprocess.PIPE, text=True)
    (OUT / "server.pid").write_text(str(server.pid))
    url = f"http://127.0.0.1:{port}"
    try:
        server.stdout.readline()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            hero(browser, url, tmp)
            stills(browser, url, tmp)
            table_first(browser, url, tmp)
            links(browser, url, tmp)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
        shutil.rmtree(tmp, ignore_errors=True)
    print(marks)


main()
