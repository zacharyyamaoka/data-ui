#!/usr/bin/env python3
"""Build reports/data-ui-types-2026-10-26.html (in the main checkout): property types, Notion's column menu, the table's
lines. Every picture is captured from the real built site, never drawn for the report.

    ~/psu-atlas/.venv/bin/python docs/build_types_report.py [--before DIR] [--no-capture]

--before DIR: a built checkout of main before this lane (its dist/site), for the before/after of the lines and the
alignment. The media go to <main>/reports/media/types/ (gitignored); the page links them, so it stays a text page.
The checks' own JSON (tests/browser/types_checks.py, run first) is read back so the page never claims a pass the run
did not make.
"""

from __future__ import annotations

import html
import json
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAIN = pathlib.Path(subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True).stdout.strip()).parent
OUT = MAIN / "reports" / "data-ui-types-2026-10-26.html"
MEDIA = MAIN / "reports" / "media" / "types"
NOTION = pathlib.Path("/tmp/claude-1000/-home-bam-zach-brain--claude-worktrees-robotics-component-library-4a5d75/09ec7f28-61d8-4e9c-a0d1-69e79cf76516/images")
ARGS = sys.argv[1:]
BEFORE = pathlib.Path(ARGS[ARGS.index("--before") + 1]) if "--before" in ARGS else None
e = html.escape


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(directory: pathlib.Path):
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(directory)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(base + "/index.html", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    return proc, base


# a visible pointer for the hero clip (Playwright's video has none): a dot that follows the mouse and pulses on click
POINTER = """(() => { const add = () => { const d = document.createElement('div'); d.id = '__ptr';
  d.style.cssText = 'position:fixed;z-index:99999;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;background:rgba(37,99,235,.35);border:2px solid rgba(37,99,235,.9);pointer-events:none;transition:transform .12s;left:-40px;top:-40px';
  document.body.append(d);
  addEventListener('mousemove', (e) => { d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => { d.style.transform = 'scale(.6)'; }, true);
  addEventListener('mouseup', () => { d.style.transform = ''; }, true); };
  if (document.body) add(); else addEventListener('DOMContentLoaded', add); })()"""


def page_of(browser, base, path, width=1440, height=900, dark=False, mobile=False, editable=False, video=None):
    opts = dict(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light", device_scale_factor=1 if video else 2 if mobile else 1.5,
                is_mobile=mobile, has_touch=mobile)
    if video:
        opts.update(record_video_dir=str(video), record_video_size={"width": width, "height": height})
    ctx = browser.new_context(**opts)
    if editable:
        ctx.add_init_script("document.addEventListener('DOMContentLoaded', () => document.querySelector('#example')?.setAttribute('editable', ''));")
    if video:
        ctx.add_init_script(POINTER)
    page = ctx.new_page()
    page.goto(f"{base}/{path}")
    page.wait_for_selector("#example[data-view]", timeout=30000)
    page.wait_for_function("() => document.querySelector('#example tbody tr[data-i]')", timeout=30000)
    page.wait_for_timeout(500)
    return page


def tab(page, name):
    page.click(f"#example .dv-tab[data-name='{name}']")
    page.wait_for_function(f"() => document.querySelector('#example').view.name === {json.dumps(name)} && document.querySelector('#example tbody tr[data-i]')")
    page.wait_for_timeout(500)


def table_shot(page, name, rows=None, extra_h=0):
    """The view (tabs to the last drawn row, or `rows` rows), as one picture."""
    box = page.evaluate("""(rows) => { const v = document.querySelector('#example'); const a = v.getBoundingClientRect();
      const trs = [...v.querySelectorAll('.dv-table tbody tr.dv-row, .dv-table tbody tr.dv-group')]; const last = rows ? trs[Math.min(rows, trs.length) - 1] : trs[trs.length - 1];
      const foot = v.querySelector('.dv-table tfoot'); const b = foot ? foot.getBoundingClientRect().bottom : last.getBoundingClientRect().bottom;
      const t = v.querySelector('.dv-table'); return { x: a.left, y: a.top, w: Math.min(a.width, t.getBoundingClientRect().right - a.left + 2), h: b - a.top + 2 }; }""", rows)
    page.screenshot(path=str(MEDIA / name), clip={"x": box["x"], "y": box["y"], "width": box["w"], "height": box["h"] + extra_h}, type="jpeg", quality=88)


def capture():
    from playwright.sync_api import sync_playwright
    MEDIA.mkdir(parents=True, exist_ok=True)
    # Zach's Notion screenshots, as he sent them
    for n, ext in [("90", "webp"), ("91", "png"), ("92", "png")]:
        src = NOTION / f"{n}.{ext}"
        if src.exists():
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-q:v", "3", str(MEDIA / f"notion-{n}.jpg")], check=True)
    proc, base = serve(ROOT / "dist" / "site")
    before = serve(BEFORE / "dist" / "site") if BEFORE else None
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            T = "gallery/property-types/index.html"
            M = "gallery/robotparts-models/index.html"
            A = "gallery/robotparts-actuators/index.html"
            # ours beside Notion's: the Projects table, the type picker, the column menu
            page = page_of(b, base, T, width=1180, editable=True)
            table_shot(page, "ours-projects.jpg", rows=4)
            page.locator("#example thead th[data-col=status]").click()
            page.wait_for_selector(".dv-colmenu")
            page.wait_for_timeout(300)
            r = page.evaluate("() => { const m = document.querySelector('.dv-colmenu').getBoundingClientRect(); const th = document.querySelector('#example thead th[data-col=status]').getBoundingClientRect(); return {x: th.left - 10, y: th.top - 6, w: m.right - th.left + 20, h: m.bottom - th.top + 14}; }")
            page.screenshot(path=str(MEDIA / "ours-menu.jpg"), clip={"x": r["x"], "y": r["y"], "width": r["w"], "height": r["h"]}, type="jpeg", quality=90)
            page.click(".dv-colmenu [data-act='page:type']")
            page.wait_for_timeout(300)
            r = page.evaluate("() => { const m = document.querySelector('.dv-colmenu').getBoundingClientRect(); return {x: m.left - 8, y: m.top - 8, w: m.width + 16, h: m.height + 16}; }")
            page.screenshot(path=str(MEDIA / "ours-types.jpg"), clip={"x": r["x"], "y": r["y"], "width": r["w"], "height": r["h"]}, type="jpeg", quality=90)
            page.click(".dv-colmenu [data-act=back]")
            page.click(".dv-colmenu [data-act='page:icon']")
            page.wait_for_timeout(300)
            r = page.evaluate("() => { const m = document.querySelector('.dv-colmenu').getBoundingClientRect(); return {x: m.left - 8, y: m.top - 8, w: m.width + 16, h: m.height + 16}; }")
            page.screenshot(path=str(MEDIA / "ours-icons.jpg"), clip={"x": r["x"], "y": r["y"], "width": r["w"], "height": r["h"]}, type="jpeg", quality=90)
            page.keyboard.press("Escape")
            page.keyboard.press("Escape")
            page.locator("#example thead th[data-col=completion]").click()
            page.click(".dv-colmenu [data-act='page:edit']")
            page.wait_for_timeout(300)
            r = page.evaluate("() => { const m = document.querySelector('.dv-colmenu').getBoundingClientRect(); return {x: m.left - 8, y: m.top - 8, w: m.width + 16, h: m.height + 16}; }")
            page.screenshot(path=str(MEDIA / "ours-edit.jpg"), clip={"x": r["x"], "y": r["y"], "width": r["w"], "height": r["h"]}, type="jpeg", quality=90)
            page.context.close()
            # every type, light and dark, in two halves (19 columns)
            for dark in (False, True):
                page = page_of(b, base, T, width=2560, height=900, dark=dark)
                tab(page, "Every type")
                table_shot(page, f"every-type-{'dark' if dark else 'light'}.jpg")
                page.context.close()
            page = page_of(b, base, T, width=375, height=812, mobile=True)
            page.evaluate("() => document.querySelector('#example').scrollIntoView()")
            page.wait_for_timeout(300)
            page.screenshot(path=str(MEDIA / "phone-375.jpg"), type="jpeg", quality=85)
            page.locator("#example thead th[data-col=status]").click()
            page.wait_for_timeout(400)
            page.screenshot(path=str(MEDIA / "phone-375-menu.jpg"), type="jpeg", quality=85)
            page.context.close()
            # the lines and the alignment, before (main) and after (this lane), on the review's own views
            for label, srv in [("after", base)] + ([("before", before[1])] if before else []):
                page = page_of(b, srv, M, width=1440, height=1000)
                for name, slug in [("Parameters · with CI", "ci"), ("What each rung adds · columns", "columns"), ("Benches", "benches")]:
                    tab(page, name)
                    # WHY a 160 px offset: the site's sticky top bar would otherwise cover the column headers these shots are about
                    page.evaluate("() => { const v = document.querySelector('#example'); v.querySelector('.dv-table').scrollIntoView({ block: 'start' }); window.scrollBy(0, -160); }")
                    page.wait_for_timeout(300)
                    r = page.evaluate("() => { const v = document.querySelector('#example'); const t = v.querySelector('.dv-table thead').getBoundingClientRect(); const s = v.querySelector('.dv-scroll').getBoundingClientRect(); return {x: s.left, y: t.top - 2, w: s.width, h: t.height + 8 * 30 + 6}; }")
                    page.screenshot(path=str(MEDIA / f"{label}-{slug}.jpg"), clip={"x": r["x"], "y": r["y"], "width": r["w"], "height": r["h"]}, type="jpeg", quality=90)
                page.context.close()
            # robotparts with types
            page = page_of(b, base, A, width=1440)
            tab(page, "All, flat")
            table_shot(page, "actuators.jpg", rows=12)
            page.context.close()
            page = page_of(b, base, M, width=1440)
            tab(page, "Leaderboard")
            table_shot(page, "models-leaderboard.jpg", rows=12)
            tab(page, "Benches")
            page.click("#example [data-about]")
            page.wait_for_timeout(300)
            r = page.evaluate("() => { const v = document.querySelector('#example').getBoundingClientRect(); const p = document.querySelector('#example .dv-pop').getBoundingClientRect(); return {x: v.left, y: v.top, w: v.width, h: Math.max(p.bottom, v.top + 420) - v.top + 10}; }")
            page.screenshot(path=str(MEDIA / "models-about.jpg"), clip={"x": r["x"], "y": r["y"], "width": r["w"], "height": min(r["h"], 900)}, type="jpeg", quality=88)
            page.keyboard.press("Escape")
            col = page.evaluate("() => document.querySelector('#example thead th[data-col^=\"@\"]').dataset.col")
            for shape in ["strip", "box", "violin"]:
                page.evaluate(f"() => document.querySelector('#example').setView({{ dist: {json.dumps({'x_floor': shape})} }})")
                page.wait_for_timeout(400)
                r = page.evaluate(f"""() => {{ const th = document.querySelector(`#example thead th[data-col="${{CSS.escape({json.dumps(col)})}}"]`).getBoundingClientRect();
                  const s = document.querySelector('#example .dv-table thead').getBoundingClientRect(); return {{x: th.left - 1, y: s.top, w: th.width * 3 + 2, h: s.height + 9 * 30}}; }}""")
                page.screenshot(path=str(MEDIA / f"dist-{shape}.jpg"), clip={"x": r["x"], "y": r["y"], "width": r["w"], "height": r["h"]}, type="jpeg", quality=92)
            page.context.close()
            hero(b, base)
            b.close()
    finally:
        proc.terminate()
        if before:
            before[0].terminate()


def hero(b, base):
    """The hero clip: open the column menu → Change type to Status → pick an icon and a name → Calculate → Roll up."""
    tmp = MEDIA / "_video"
    shutil.rmtree(tmp, ignore_errors=True)
    page = page_of(b, base, "gallery/property-types/index.html", width=1280, height=720, editable=True, video=tmp)
    tab(page, "By status")
    page.evaluate("() => { const v = document.querySelector('#example'); v.scrollIntoView({ block: 'start' }); window.scrollBy(0, -8); }")
    page.wait_for_timeout(700)

    def go(sel, wait=650):
        box = page.locator(sel).first.bounding_box()
        page.mouse.move(box["x"] + min(40, box["width"] / 2), box["y"] + box["height"] / 2, steps=14)
        page.wait_for_timeout(220)
        page.mouse.down()
        page.mouse.up()
        page.wait_for_timeout(wait)

    go("#example thead th[data-col=priority]", 900)
    go(".dv-colmenu [data-act='page:type']", 800)
    go(".dv-colmenu [data-act='type:status']", 1100)
    go(".dv-colmenu [data-act='page:icon']", 700)
    go(".dv-colmenu [data-act='icon:flag']", 700)
    go(".dv-colmenu [data-k=displayName]", 200)
    page.keyboard.press("Control+A")
    page.keyboard.type("Urgency", delay=110)
    page.wait_for_timeout(300)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    go("#example thead th[data-col=priority]", 700)
    go(".dv-colmenu [data-act='page:calc']", 700)
    go(".dv-colmenu [data-act='calc:Unique']", 1300)
    go("#example thead th[data-col=owner]", 700)
    go(".dv-colmenu [data-act='page:rollup']", 900)
    go(".dv-colmenu [data-act='roll:away']", 2200)
    video = page.video.path()
    page.context.close()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", "scale=1280:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-movflags", "+faststart", "-an", str(MEDIA / "hero.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(MEDIA / "hero.mp4"), "-vf", "fps=10,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer", str(MEDIA / "hero.gif")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-0.3", "-i", str(MEDIA / "hero.mp4"), "-frames:v", "1", "-q:v", "3", str(MEDIA / "hero-poster.jpg")], check=True)
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------------------------------------- the page
def checks():
    f = ROOT / "reports" / "media" / "types" / "types-checks.json"
    return json.loads(f.read_text()) if f.exists() else []


def unit_counts():
    unit = sorted(str(f.relative_to(ROOT)) for f in (ROOT / "tests" / "unit").glob("*.test.mjs"))
    done = subprocess.run(["node", "--test", *unit, "tools/facets.test.mjs"], cwd=ROOT, capture_output=True, text=True)
    out = done.stdout
    get = lambda k: next((l.split()[-1] for l in out.splitlines() if l.startswith(f"# {k}")), "?")
    return get("pass"), get("fail")


def git(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout.strip()


def build():
    cs = checks()
    passed = sum(c["ok"] for c in cs)
    upass, ufail = unit_counts()
    head = git("rev-parse", "--short", "HEAD")
    main_head = git("rev-parse", "--short", "main")
    commits = git("log", "--oneline", "main..HEAD").splitlines()
    # the table-oracle review's own findings (docs/review_table_oracle.py, run against a built main): never claimed, read
    review = json.loads((MEDIA / "oracle-review.json").read_text()) if (MEDIA / "oracle-review.json").exists() else {}
    statuses = [v.get("status", "") for v in review.values()]
    problems = sum(len(v.get("problems", [])) for v in review.values())
    review_line = (f"{problems} problem(s) over {len(review)} views ({statuses.count('declared changes only')} with only declared changes, "
                   f"{sum(1 for x in statuses if x.startswith('new'))} new)") if review else "no review on file"
    # each round's fixes, from the lane's own commit subjects
    subjects = git("log", "--format=%s", "main..HEAD").splitlines()
    def round_items(tag):
        out = []
        for subj in reversed(subjects):
            if subj.startswith("fix") and (f"judge {tag}" in subj or f"({tag} " in subj or f"{tag} #" in subj):
                out.append(subj.split(":", 1)[1].strip() if ":" in subj else subj)
        return "".join(f"<li>{e(x)}</li>" for x in out)
    fig = lambda src, cap, cls="": f'<figure class="{cls}"><img src="media/types/{src}" alt="{e(cap)}" loading="lazy"><figcaption>{cap}</figcaption></figure>'
    pair = lambda a, b: f'<div class="pair">{a}{b}</div>'
    rows = "".join(f'<tr class="{"ok" if c["ok"] else "bad"}"><td>{"PASS" if c["ok"] else "FAIL"}</td><td>{e(c["name"])}</td><td><code>{e(json.dumps(c.get("value"), ensure_ascii=False)[:180]) if c.get("value") is not None else ""}</code></td></tr>' for c in cs)
    types_table = [
        ("Text", "wrap", "text", "plain text; Wrap in view"), ("Number", "format (commas, plain, percent, currency), decimals, abbreviate; show as number / bar / ring with colour, divide-by, show number", "number", "Intl.NumberFormat; bar and ring"),
        ("Select / Multi-select", "options with Notion's 10 colours (list or map), sort", "select, multi_select", "rounded pills"), ("Status", "options in 3 groups (to-do, in progress, complete), show as select or checkbox", "status", "dot + label in a round pill"),
        ("Date", "date format (full, short, M/D/Y, D/M/Y, ISO, relative), time (hidden, 12 h, 24 h)", "date", "Intl.DateTimeFormat, RelativeTimeFormat"), ("Person", "—", "person", "avatar with initials + name"),
        ("Files & media", "—", "files", "thumbnails; a file chip"), ("Checkbox", "show as check or toggle", "checkbox", "box with a tick / switch"),
        ("URL / Email / Phone", "URL with or without https://", "url, email, phone", "real links: href, mailto:, tel:"), ("Rating", "max 1–10, icon (star, heart, flag, circle), colour", "rating", "filled and empty icons"),
        ("Currency / Percent", "ISO currency, decimals; show as bar or ring", "currency, percent", "$70.00, 25.00%"), ("Duration", "stored in ms / s / min / h; h:mm, h:mm:ss, h:mm:ss.SSS, human", "duration", "1:05:05"),
        ("Relation", "—", "relation", "the related record's title; a click opens it in the peek"), ("Rollup / Formula", "decimals; rollup show as bar or ring", "rollup, formula", "derived: Σ / ƒ mark, never editable"),
        ("ID / Created / Edited time", "prefix; date format", "id, created_time, edited_time", "PRJ-7; 3 days ago"),
    ]
    tt = "".join(f"<tr><td>{a}</td><td>{e(b)}</td><td><code>{c}</code></td><td>{e(d)}</td></tr>" for a, b, c, d in types_table)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>data-ui · property types</title>
<style>
:root {{ --bg:#fff; --fg:#1f2328; --muted:#5f6670; --rule:#e3e6ea; --card:#f6f8fa; --good:#1a7f37; --bad:#cf222e; --accent:#2563eb; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0d1117; --fg:#e6edf3; --muted:#9aa4af; --rule:#30363d; --card:#161b22; --good:#3fb950; --bad:#f85149; --accent:#58a6ff; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:17px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:1480px; margin:0 auto; padding:28px 24px 80px; }}
h1 {{ font-size:34px; margin:0 0 6px; }} h2 {{ font-size:25px; margin:48px 0 10px; border-top:1px solid var(--rule); padding-top:22px; }} h3 {{ font-size:19px; margin:24px 0 8px; }}
.verdict {{ font-size:21px; background:var(--card); border:1px solid var(--rule); border-radius:12px; padding:16px 20px; }}
.verdict b {{ color:var(--good); }} .muted {{ color:var(--muted); }}
figure {{ margin:0; }} figure img, video {{ max-width:100%; border:1px solid var(--rule); border-radius:8px; display:block; background:#fff; }}
figcaption {{ color:var(--muted); font-size:14.5px; margin-top:6px; }}
.pair {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; align-items:start; margin:14px 0; }}
.three {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }}
.scrollx {{ overflow-x:auto; }} .scrollx img {{ max-width:none; height:420px; }}
table.t {{ border-collapse:collapse; width:100%; font-size:15px; }} table.t td, table.t th {{ border-bottom:1px solid var(--rule); padding:6px 8px; text-align:left; vertical-align:top; }}
tr.ok td:first-child {{ color:var(--good); font-weight:600; }} tr.bad td:first-child {{ color:var(--bad); font-weight:700; }}
code {{ font-size:13px; }} ul {{ margin:6px 0; }} li {{ margin:3px 0; }}
.phone {{ display:flex; gap:20px; }} .phone img {{ width:300px; }}
@media (max-width:760px) {{ .pair, .three {{ grid-template-columns:1fr; }} main {{ padding:16px; }} .phone {{ flex-direction:column; }} }}
</style></head><body><main>
<h1>Property types and Notion's column menu</h1>
<p class="muted">data-ui · lane <code>lane/types</code> @ <code>{head}</code> · 2026-10-26, through judge round 6 on 2026-10-27 · not merged</p>
<div class="verdict"><b>Done and measured:</b> data-ui columns now have a first-class <i>type</i> (Notion's, plus rating,
currency, percent, duration, relation, rollup, ID), each with its own formatting options; every header shows its type icon;
a header click opens Notion's column menu (rename, icon, edit property, change type, filter, sort, calculate, roll up,
freeze, hide, wrap, insert, duplicate, delete), with file edits written back into the <code>.base</code> text; the six
header/divider findings and every judge finding of rounds 2–6 are fixed, each with a check that failed first.
<b>{passed}/{len(cs)}</b> types checks pass (measured, light and dark, 375 px); the unit suite passes (<b>{upass}</b> tests,
{ufail} failing); the table-oracle review against main finds {review_line}. On <code>lane/types</code>, merged with main
<code>{main_head}</code>, not merged into it.</div>

<h2>The flow, live</h2>
<p>Open a column's menu → Change type to Status → pick an icon and a name → Calculate → Roll up across Owner. Recorded from the built gallery page.</p>
<video src="media/types/hero.mp4" poster="media/types/hero-poster.jpg" autoplay muted loop playsinline controls width="1280"><img src="media/types/hero.gif" alt="The hero flow as a GIF"></video>
<p class="muted">No video? <a href="media/types/hero.gif">the GIF</a>.</p>

<h2>Notion beside data-ui</h2>
<h3>The table</h3>
{pair(fig("notion-90.jpg", "Notion (Zach's 90.webp): status pills, person, priority tags, completion % with a bar, a type icon on each header."), fig("ours-projects.jpg", "data-ui, the property-types case: the same four projects from one <code>.base</code> file; Status, Person, Select, Percent shown as a bar, type icons."))}
<h3>The type picker</h3>
{pair(fig("notion-91.jpg", "Notion's Select type grid (91.png)."), fig("ours-types.jpg", "data-ui's Change type page: Notion's twelve in Notion's order, then the advanced ones."))}
<h3>The column menu</h3>
{pair(fig("notion-92.jpg", "Notion's column-header menu (92.png)."), fig("ours-menu.jpg", "data-ui's: name and icon, Edit property, Change type, Filter, Sort, Calculate, Roll up, Freeze, Hide, Wrap in view, Insert, Duplicate, Delete."))}
{pair(fig("ours-icons.jpg", "The icon picker: an icon set drawn after Lucide's shapes, or any emoji."), fig("ours-edit.jpg", "Edit property for a percent: decimals, show as bar or ring, colour, divide-by, show number, and a description (the header's tooltip)."))}

<h2>Every type</h2>
<p>The "Every type" view, all 19 columns, light and dark (scroll sideways). The stored values never change; only how they are drawn.</p>
<div class="scrollx">{fig("every-type-light.jpg", "Light.")}</div>
<div class="scrollx">{fig("every-type-dark.jpg", "Dark.")}</div>
<table class="t"><thead><tr><th>Type</th><th>Formatting options</th><th><code>type:</code></th><th>Drawn as</th></tr></thead><tbody>{tt}</tbody></table>
<p class="muted">The prior-art sweep behind this list (Notion, Airtable, Coda, Sheets, Excel, Baserow, NocoDB, Grist, Obsidian Bases; 37 sources, cited): vault note <code>World Model/Chunks &amp; Concepts/C - Table property types and cell formatting (prior art).md</code>.</p>

<h2>Lines and alignment, before and after</h2>
<p>The Codex review's six findings, on its own views. Left: main before this lane. Right: this lane.</p>
{pair(fig("before-ci.jpg", "Before: no dividers inside Coulomb's sub-columns; numbers 18 px short of their headers; basis header right, values left."), fig("after-ci.jpg", "After: a divider on every edge, under the groups too; each number ends at its header's edge; basis left; the unit once, on Coulomb (N·m)."))}
{pair(fig("before-columns.jpg", "Before: 'runs' sits right-aligned against the whole cell; 'Added × floor' glued; empty slots push numbers in."), fig("after-columns.jpg", "After: 'runs' centred over its strip; header and number edges meet."))}
{pair(fig("before-benches.jpg", "Before: 'sine × floor' reads as one name; titles off their strips."), fig("after-benches.jpg", "After: 'sine (× floor)', centred over the strip; every cell edge drawn."))}
<p>Frozen columns: the header freezes exactly what the body freezes (no spanning blank), Notion's <b>Freeze</b> sets how many, and on a phone they never take more than half the width. A distribution column can't be drawn or dragged narrower than its content.</p>

<h2>Distributions: strip, box, violin</h2>
<div class="three">{fig("dist-strip.jpg", "Strip (default): every run a dot, the median a tick.")}{fig("dist-box.jpg", "Box: the quartiles, whiskers to min and max.")}{fig("dist-violin.jpg", "Violin: where the runs bunch, mirrored, in the column's own (log) scale.")}</div>

<h2>robotparts with types</h2>
{fig("actuators.jpg", "Actuators: form, drivetrain and bus as pills, price as USD, torque density as a bar against the densest in view, level as robotparts' 5-step evidence ladder.")}
{fig("models-leaderboard.jpg", "Actuator models leaderboard: coloured rungs, twin-grade as a status, runs as bars, header icons and tooltips that say what × floor means.")}
{fig("models-about.jpg", "The intro text is no longer a paragraph wedged between the cards and the rows: it is the tab's About note, one click away (ⓘ About this view).")}

<h2>375 px</h2>
<div class="phone">{fig("phone-375.jpg", "The table at 375 px: no sideways page scroll.")}{fig("phone-375-menu.jpg", "The column menu fits the screen.")}</div>

<h2>Judge rounds 2–6</h2>
<p>Codex judged the lane five more times; every finding got a failing check first, then the fix. The newest round first.</p>
<h3>Round 6</h3>
{fig("r6-rel-rest.jpg", "A relation cell with two related records, at rest: the second sits behind the cell's ellipsis.")}
{fig("r6-rel-tab.jpg", "Tab twice from the row: the second record's chip is a button now, scrolled into view and marked as focused.")}
{fig("r6-rel-focus.jpg", "Enter: that record opens in the peek, not the row's.")}
{fig("r6-wrap.jpg", "Name taken out of Wrap in view: its long title stays on one line (ending in …) though the rows went tall for Status, which wraps.")}
<ul>{round_items("r6")}</ul>
<p class="muted">Round 6 also hardened the oracle review (it had still approved a dropped or duplicated row, a replaced merged heading, reordered columns and currency reverted to plain text): every one of those is now a failing case in <code>tools/test_review_table_oracle.py</code>.</p>
<h3>Round 5</h3>
{fig("r5-pills-before.jpg", "Before (the lane at fee10b0): a 50-character status, select, tag and person, every column saved at 20 px: each pill cut mid-word, no sign of it.")}
{fig("r5-pills-after.jpg", "After (9b4e250): each cell's first pill or chip whole (its column's minimum, on render and on drag, capped at 400 px); eight tags end in a drawn ellipsis; the Link column too.")}
{fig("r5-peek-after.jpg", "The peek shows every pill and chip, wrapped; the long URL card ends in an ellipsis (the field below has it whole).")}
<ul>{round_items("r5")}</ul>
<h3>Round 4</h3><ul>{round_items("r4")}</ul>
<h3>Round 3</h3><ul>{round_items("r3")}</ul>
<h3>Round 2</h3><ul>{round_items("r2")}</ul>
<p class="muted">The table oracle's golden is the lane's own drawing, accepted only after <code>docs/review_table_oracle.py</code> compared every table and pivot view against main's build: rows by identity, columns, groups, units and every typed cell against an independent formatter. It found two real regressions this lane had made (a rich typed cell lost its range and basis mark; a rich number column hid its range), both fixed before the golden was kept.</p>

<h2>Checks ({passed}/{len(cs)})</h2>
<p class="muted"><code>tests/browser/types_checks.py</code> (+ <code>types_cases.py</code>), every claim a number read from the page. The six review findings were written first and failed first (1/11) before the fix.</p>
<table class="t"><tbody>{rows}</tbody></table>

<h2>Decisions</h2>
<ul>
<li><b>A type is display, not storage.</b> The <code>.base</code> type lands as the column's <code>kind</code>; the data's storage type (which filters, sorts and groups read) is untouched. A percent 0.25 reads "25.00%" (Notion's convention) and its hover says 0.25.</li>
<li><b>The unit: a muted "(× floor)" after the name</b>, the engineering-table header convention ("Torque (N·m)"), said once over a stats column's parts, in the tooltip too. Authored labels such as "Added × floor" stay as written.</li>
<li><b>Header click opens the menu</b> (Notion's); shift-click still sorts at once.</li>
<li><b>File edits only on an <code>editable</code> host.</b> They land in <code>el.base</code>, in <code>el.baseText</code> line by line (comments kept; ⋯ Copy the whole file) and in a <code>data-views-base</code> event. Insert adds a typed <code>.base</code> property with no data ("—" and why); Duplicate reads the same values (<code>from:</code>); Delete removes a file-only property or hides a data property everywhere (its data untouched).</li>
<li><b>Intro text</b> became the view's About note; <code>before:</code> / <code>after:</code> are real Markdown blocks above the tabs and below the rows; property descriptions are header tooltips.</li>
<li><b>Wrap in view</b> makes the view's rows tall (three lines): the rows are virtualised at one height.</li>
</ul>

<h2>What is left, and what needs you</h2>
<ul>
<li><b>Merge:</b> on <code>lane/types</code>, {len(commits)} commit(s) past main <code>{main_head}</code>, not merged. The coordinator's judge rounds decide when it is ready; landing is your call.</li>
<li><b>Done since round 1:</b> "All roll-up settings…" now opens §15's Display panel at its Roll up page (toolbar-mix landed), the older toolbar's Roll up menu without the bar.</li>
<li><b>Not done in this lane:</b> the List and Cards views show a relation's record id ("p1") where the table shows its title; that predates this lane (they never pass a title lookup).</li>
<li><b>Not done on purpose:</b> editing a cell's value in place (the data changes at its source; host.propose stays the one path); Notion's grouped Status board and Formula editing (formulas are not evaluated in v1).</li>
</ul>
</main></body></html>"""
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    if "--no-capture" not in ARGS:
        capture()
    build()
