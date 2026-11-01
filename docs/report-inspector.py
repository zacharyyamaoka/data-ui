#!/usr/bin/env python3
"""Build reports/media/inspector-2026-10-31.html (in the main checkout) from the real built kit: hero video, stills, Zach's own picture as the before.

    ~/psu-atlas/.venv/bin/python docs/report-inspector.py FACTS.json     # after npm run build; FACTS: {sha, counts, journey, hostnote}
"""
import base64, html, json, pathlib, subprocess, sys, tempfile, time
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path("~/data-ui/reports/media/inspector-2026-10-31.html")
IMAGES = pathlib.Path("~/zach_brain/Sources/Images")
FACTS = json.loads(pathlib.Path(sys.argv[1]).read_text())
TMP = pathlib.Path(tempfile.mkdtemp())
V = "#example"
PORT = 47217


def jpeg(src, name, width):
    out = TMP / name
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", f"scale={width}:-2", "-q:v", "5", str(out)], check=True)
    return out


def uri(path, mime):
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def capture(browser, base):
    ctx = browser.new_context(viewport={"width": 1360, "height": 720}, color_scheme="dark", record_video_dir=str(TMP), record_video_size={"width": 1360, "height": 720})
    g = ctx.new_page()
    g.goto(f"{base}/dist/site/gallery/gim4305-datasheet/index.html")
    g.wait_for_selector(f"{V} .dv-stage tbody tr[data-id]")
    g.locator(V).scroll_into_view_if_needed()
    g.wait_for_timeout(700)
    g.click(f"{V} .dv-stage tbody tr[data-id] td:nth-child(2)")
    g.wait_for_selector(f"{V} .dv-open-rec")
    g.wait_for_timeout(1500)
    g.screenshot(path=str(TMP / "after.png"))
    g.click(f"{V} .dv-peek [data-prop-more]")
    g.wait_for_timeout(1300)
    g.screenshot(path=str(TMP / "open.png"))
    g.hover(f"{V} .dv-peek tr[data-p=section]")
    g.wait_for_timeout(400)
    g.click(f"{V} .dv-peek tr[data-p=section] [data-prop-vis]")
    g.wait_for_timeout(900)
    g.click(".dv-pop [data-vis=show]")
    g.wait_for_timeout(1200)
    g.hover(f"{V} .dv-peek tr[data-p=board]")
    g.click(f"{V} .dv-peek tr[data-p=board] [data-prop-vis]")
    g.wait_for_timeout(900)
    g.screenshot(path=str(TMP / "menu.png"))
    g.click(".dv-pop [data-vis=hide]")
    g.wait_for_timeout(1200)
    g.hover(f"{V} .dv-peek tr[data-p=derived]")
    g.click(f"{V} .dv-peek tr[data-p=derived] [data-prop-vis]")
    g.wait_for_timeout(700)
    g.click(".dv-pop [data-vis-row]")
    g.wait_for_timeout(1500)
    path = pathlib.Path(g.video.path())
    ctx.close()
    g2 = browser.new_page(viewport={"width": 1500, "height": 660}, color_scheme="dark")
    g2.goto(f"{base}/tests/browser/fixtures/source-precedence/part.html")
    g2.wait_for_selector("data-views tbody tr[data-id]")
    g2.click("data-views tbody tr[data-id] td:nth-child(2)")
    g2.wait_for_selector(".dv-open-rec")
    g2.wait_for_timeout(400)
    g2.screenshot(path=str(TMP / "source.png"))
    g2.close()
    g3 = browser.new_page(viewport={"width": 1400, "height": 640}, color_scheme="dark")
    g3.goto(f"{base}/tests/browser/fixtures/inspector/page.html?src=parts.base")
    g3.wait_for_selector("#insp .dv-stage tbody tr[data-id]")
    g3.click("#insp .dv-tab[data-name='Every source']")
    g3.wait_for_timeout(300)
    g3.click("#insp .dv-stage tbody tr[data-id] td:nth-child(2)")
    g3.wait_for_selector("#insp .dv-open-rec")
    g3.wait_for_timeout(300)
    g3.screenshot(path=str(TMP / "columns.png"))
    g3.close()
    m = browser.new_context(viewport={"width": 390, "height": 760}, color_scheme="light", device_scale_factor=2, is_mobile=True, has_touch=True).new_page()
    m.goto(f"{base}/dist/site/gallery/gim4305-datasheet/index.html")
    m.wait_for_selector(f"{V} .dv-stage tbody tr[data-id]")
    m.evaluate(f"document.querySelector('{V}').openPeek(document.querySelector('{V}').model.rows[0].id)")
    m.wait_for_selector(f"{V} .dv-open-rec")
    m.wait_for_timeout(300)
    m.screenshot(path=str(TMP / "phone.png"))
    return path


def page(img, video, gif):
    f = FACTS
    fig = lambda key, cap: f'<figure><img src="{img[key]}" alt="{html.escape(cap)}"><figcaption>{cap}</figcaption></figure>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Inspector</title>
<style>
:root {{ --bg:#fff; --fg:#1b1d21; --mute:#5d6470; --line:#e2e4e8; --code:#f3f4f6; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#121316; --fg:#ececee; --mute:#a0a5ae; --line:#2b2e34; --code:#1d1f24; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.55 system-ui,sans-serif; }}
main {{ max-width:1080px; margin:0 auto; padding:28px 16px 60px; }}
h1 {{ font-size:25px; margin:0 0 6px; }} h2 {{ font-size:18px; margin:34px 0 8px; }}
.lead {{ font-size:16.5px; }} .mute {{ color:var(--mute); }}
img, video {{ max-width:100%; display:block; border:1px solid var(--line); border-radius:8px; }}
figure {{ margin:14px 0; }} figcaption {{ color:var(--mute); font-size:13px; margin-top:5px; }}
.two {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:14px; align-items:start; }}
code, pre {{ background:var(--code); border-radius:4px; font-size:13px; }} code {{ padding:1px 4px; }} pre {{ padding:10px 12px; overflow:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }} td, th {{ border-bottom:1px solid var(--line); text-align:left; padding:5px 8px; vertical-align:top; }}
</style></head><body><main>
<h1>The inspector is one property per row</h1>
<p class="lead"><b>{html.escape(f["verdict"])}</b></p>
<p class="mute">Zach, Oct 31: "I don't like how when I look at the inspector menu its not a 1:1 coorespondance with the fields I am seeing".</p>
<video controls autoplay muted loop playsinline width="1360" poster="{img["after"]}"><source src="{video}" type="video/mp4"><img src="{gif}" alt="The inspector: open a row, expand N more properties, set a property's visibility"></video>
<p class="mute">Recorded from the real GIM4305 gallery case: open a row; 7 more properties opens in place; Section set to Always show, Board to Always hide, then Derived out of the row, so its column leaves.</p>
<h2>Before and after</h2>
<div class="two">{fig("before", "Before, his screenshot: chips, Specs and Sources tabs, then a different list")}{fig("after", "After: the table's columns, same labels, same order, then Every value behind it")}</div>
<div class="two">{fig("notion", "The target, his Notion picture: each property shown or hidden apart from the table, N more property")}{fig("open", "Here: 7 more properties, opened in place")}</div>
<h2>Its other cases</h2>
<div class="two">{fig("menu", "One menu for both settings: the inspector and the row")}{fig("source", "A column the table adds, Nominal source, is a row where the table draws it")}</div>
<div class="two">{fig("columns", "One plain column per source, as the coming source lane writes it: each is a row, in the view's order")}<figure><img src="{img["phone"]}" alt="Phone" style="max-width:300px"><figcaption>390 px: full screen, no sideways scroll</figcaption></figure></div>
<h2>The grammar</h2>
<pre>views:
  - type: table
    order: [field, nominal, section]      # the row, as ever
    record:
      visibility:                         # the inspector, apart from the row
        section: hide                     # a column, not in the inspector
        citation: show                    # in the inspector, not a column
        weight: hideEmpty                 # only when it has a value</pre>
<p>Three words, Notion's. A property with no word follows its column, so every existing file is 1:1 with nothing added. Hosts get the slot they already had: <code>el.peekExtra</code>, now under the properties in both surfaces.</p>
<h2>Done and proved</h2>
<table>{"".join(f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td></tr>" for a, b in f["proof"])}</table>
<h2>What a host must change</h2>
<ul>{"".join(f"<li>{html.escape(x)}</li>" for x in f["hosts"])}</ul>
<h2>Left, and what needs you</h2>
<ul>{"".join(f"<li>{html.escape(x)}</li>" for x in f["left"])}</ul>
<h2>Deliberately not done</h2>
<ul>{"".join(f"<li>{html.escape(x)}</li>" for x in f["not"])}</ul>
</main></body></html>"""


def main():
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1", "--directory", str(ROOT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            raw = capture(b, f"http://127.0.0.1:{PORT}")
            b.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    mp4, gif = TMP / "hero.mp4", TMP / "hero.gif"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-vf", "scale=1100:-2", "-c:v", "libx264", "-crf", "33", "-preset", "veryslow", "-pix_fmt", "yuv420p", "-an", str(mp4)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-vf", "fps=4,scale=560:-2", str(gif)], check=True)
    img = {"before": jpeg(IMAGES / "Pasted image 20261031110116.png", "before.jpg", 760), "notion": jpeg(IMAGES / "Pasted image 20261031110250.png", "notion.jpg", 760)}
    for k in ("after", "open", "menu", "source", "columns"):
        img[k] = jpeg(TMP / f"{k}.png", f"{k}.jpg", 760)
    img["phone"] = jpeg(TMP / "phone.png", "phone.jpg", 420)
    OUT.write_text(page({k: uri(v, "image/jpeg") for k, v in img.items()}, uri(mp4, "video/mp4"), uri(gif, "image/gif")), encoding="utf-8")
    print(OUT, OUT.stat().st_size, "bytes; video", mp4.stat().st_size, "gif", gif.stat().st_size)


main()
