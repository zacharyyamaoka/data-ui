"""Browser checks for the analyses case (docs/peps/0007-analyses.md). Oracles from the files on disk: the .md files'
frontmatter and headings, the sibling cases' JSON and .base files."""

import json
import pathlib
import re

HERE = pathlib.Path(__file__).parent
FILES = sorted(p for p in HERE.glob("*.md") if re.fullmatch(r"[a-z0-9][a-z0-9-]*", p.stem))


def front(path):
    text = path.read_text(encoding="utf-8")
    head = text.split("\n---", 1)[0]
    title = re.search(r"^title: (.+)$", head, re.M).group(1)
    return text, title


def ready(page, timeout=30000):
    page.wait_for_function("() => document.querySelector('#analysis-body') && document.querySelector('#analysis-body').dataset.state === 'ready'", timeout=timeout)


def run(ctx, path):
    page = ctx.page(path, width=1280, height=900)
    page.wait_for_function("() => { const el = document.getElementById('example'); return el && el.model && el.model.rows; }", timeout=30000)
    rows = page.evaluate("() => document.getElementById('example').data.rows.map((r) => ({ title: r.title, url: r.url }))")
    want = sorted(front(p)[1] for p in FILES)
    ctx.check("analyses list: one row per analysis file on disk, titled from its frontmatter", sorted(r["title"] for r in rows) == want, {"rows": rows, "files": want})
    table = page.locator("#example tr.dv-row").count()
    ctx.check("analyses list: the Table (the first view) has a row per analysis", table == len(FILES), table)
    page.click("#example .dv-tab:has-text('Gallery')")
    page.wait_for_selector("#example .dv-cards-card", timeout=20000)
    cards = page.locator("#example .dv-cards-card").count()
    ctx.check("analyses list: the Gallery draws a card per analysis", cards == len(FILES), cards)
    page.click("#example .dv-cards-card >> nth=0")
    page.wait_for_url(re.compile(r"/gallery/analyses/[a-z0-9-]+\.html$"), timeout=20000)
    ready(page)
    ctx.check("analyses list: a card opens its analysis page", page.locator("data-analysis .an-head").count() == 1, page.url)
    page.context.close()

    for md in FILES:
        text, title = front(md)
        for dark in (False, True):
            for width in (1280, 390):
                page = ctx.page(f"gallery/analyses/{md.stem}.html", width=width, height=900 if width > 400 else 844, dark=dark, mobile=width < 400)
                ready(page)
                page.wait_for_function("() => [...document.querySelectorAll('#analysis [data-embed]')].every((f) => f.querySelector('data-views, data-dashboard, .an-err'))", timeout=30000)
                tag = f"{md.stem} {'dark' if dark else 'light'} {width}"
                got = page.evaluate("""() => ({ sw: document.scrollingElement.scrollWidth, bg: getComputedStyle(document.body).backgroundColor,
                  toc: [...document.querySelectorAll('#analysis .an-toc a')].map((a) => a.textContent), errs: document.querySelectorAll('#analysis .an-err').length,
                  title: document.querySelector('#analysis .an-title').textContent })""")
                headings = [re.sub(r"[*`]", "", h) for h in re.findall(r"^#{1,2} (.+)$", text.split("\n---", 1)[1].split("\n---", 1)[-1], re.M)]
                want_toc = ["Top"] + headings + (["Decision"] if "> [!decision]" in text else [])
                ctx.check(f"{tag}: the contents are the file's headings and its decision", got["toc"] == want_toc, {"toc": got["toc"], "want": want_toc})
                ctx.check(f"{tag}: every view drew, no sideways scroll, the theme followed", got["errs"] == 0 and got["sw"] <= width and got["title"] == title.strip('"')
                          and (got["bg"] == "rgb(10, 10, 10)") == dark, got)
                if md.stem == "shoulder-actuator" and not dark and width == 1280:
                    parts = re.findall(r"^  - (\S+)$", text.split("\n---", 1)[0], re.M)
                    data = json.loads((HERE.parent / "robotparts-actuators" / "actuators.json").read_text(encoding="utf-8"))
                    data = data["rows"] if isinstance(data, dict) else data
                    oracle = sorted(r["id"] for r in data if r["id"] in parts)
                    shown = sorted(page.evaluate("() => document.querySelector('#analysis [data-embed=\"0\"] data-views').model.rows.map((r) => r.id)"))
                    ctx.check("shoulder-actuator: the fence filtered by this.parts keeps exactly the parts the note names", shown == oracle, {"shown": shown, "oracle": oracle})
                    toc = page.locator("#analysis .an-toc")
                    before = toc.bounding_box()["width"]
                    handle = page.locator("#analysis .dv-splitter").first.bounding_box()
                    page.mouse.move(handle["x"] + handle["width"] / 2, handle["y"] + 40)
                    page.mouse.down()
                    page.mouse.move(handle["x"] + handle["width"] / 2 + 80, handle["y"] + 40, steps=8)
                    page.mouse.up()
                    after = toc.bounding_box()["width"]
                    ctx.check("analysis page: the contents column drags wider (measured)", after - before > 60, {"before": before, "after": after})
                    ctx.shot(page, "analysis-shoulder-light-1280")
                if md.stem in ("sim-to-real-twin", "pid-gains") and not dark and width == 1280:
                    case = "sim-to-real" if md.stem == "sim-to-real-twin" else "pid-tuning"
                    panels = len(re.findall(r"^    - ", (HERE.parent / case / "views.base").read_text(encoding="utf-8").split("\nlayout:", 1)[1].split("\nviews:", 1)[0], re.M))
                    page.wait_for_function("() => document.querySelector('#analysis data-dashboard .dd-panel')", timeout=30000)
                    shown = page.evaluate("() => document.querySelectorAll('#analysis data-dashboard .dd-panel').length")
                    ctx.check(f"{md.stem}: the whole {case} dashboard is embedded with one line, every panel", shown == panels, {"shown": shown, "panels": panels})
                    ctx.shot(page, f"analysis-{md.stem}-light-1280")
                page.context.close()
