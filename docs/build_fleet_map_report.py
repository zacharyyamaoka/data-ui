"""Builds the fleet map's review report: ~/data-ui/reports/media/fleet-map-2026-10-30.html.

    python3 docs/build_fleet_map_report.py

One self-contained page: every image is a WebP data URI (downscaled and cropped here with Pillow), the hero is an H.264
mp4 data URI with a GIF inside it as the fallback, and the CSS and the few lines of JS are inline. It opens from disk with
no server or network. It lives in reports/media/ (gitignored) because it inlines media.

Reads only measured inputs, never the code under test, from reports/media/fleet-map/:
- hero.mp4, hero.gif, marks.json, recorded by docs/capture_fleet_hero.py from the built page;
- the stills and fleet-map-checks.json that tests/browser/fleet_map_checks.py writes on the final commit;
- red-browser.log, red-unit.log (the frozen checks on the kit before any change), mutations.json (each mutation of the kit
  or the served data, and the checks that went red on it), carry-over.json (this lane's map diff applied to lane/map);
- full-suite.log, the final commit's `node tools/test-all.mjs`;
- git, in this worktree.
"""

import base64
import html
import io
import json
import re
import subprocess
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
MEDIA = Path("~/data-ui/reports/media")
HERE = MEDIA / "fleet-map"
OUT = MEDIA / "fleet-map-2026-10-30.html"
BASE = "d5ede93"
SIZE_LIMIT = 1_900_000
e = html.escape
SIZES = {}


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True).stdout.strip()


def webp(path, name, *, width=900, crop=None, quality=55):
    image = Image.open(path).convert("RGB")
    if crop:
        image = image.crop(crop)
    if image.width > width:
        image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=quality, method=6)
    data = buffer.getvalue()
    SIZES[name] = len(data)
    return f"data:image/webp;base64,{base64.b64encode(data).decode()}", image.width, image.height


def fig(name, alt, caption, *, width=900, crop=None, quality=55, cls=""):
    path = HERE / name
    if not path.exists():
        return f'<figure class="missing">missing: {e(str(path))}</figure>'
    uri, w, h = webp(path, name, width=width, crop=crop, quality=quality)
    return (f'<figure class="{cls}"><button class="zoom" type="button" aria-label="Enlarge: {e(alt)}"><img src="{uri}" width="{w}" height="{h}" alt="{e(alt)}"></button>'
            f"<figcaption>{caption}</figcaption></figure>")


def data_uri(path, mime):
    data = Path(path).read_bytes()
    SIZES[Path(path).name] = len(data)
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def counted(path):
    """(passed, total) of a checks log's last 'N/M … pass' line."""
    if not Path(path).exists():
        return None
    found = re.findall(r"(\d+)/(\d+) [^\n]*checks pass", Path(path).read_text(encoding="utf-8", errors="replace"))
    return (int(found[-1][0]), int(found[-1][1])) if found else None


def full_suite():
    """The final commit's run: its summary lines, the unit and Python counts, and every browser step's N/M."""
    path = HERE / "full-suite.log"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    summary = re.findall(r"^(ok  |FAIL|skip) ([^:\n]+): (.*)$", text, re.M)
    units = re.findall(r"^# (tests|pass|fail) (\d+)$", text, re.M)
    python = [int(n) for n in re.findall(r"^Ran (\d+) tests? in", text, re.M)]
    browser = [(int(a), int(b)) for a, b in re.findall(r"^(\d+)/(\d+) [^\n]*checks pass", text, re.M)]
    return {"summary": summary, "units": {k: int(v) for k, v in units}, "python": sum(python), "browser": browser}


CSS = """
:root{--bg:#fbfbfa;--fg:#1c1c1a;--muted:#62625e;--card:#fff;--line:#e4e4e0;--chip:#f1f1ee;--accent:#2455c3;--good:#1f7a3a;--good-bg:#e6f3ea;--bad:#b3261e;--bad-bg:#fbeaea;--code:#f3f3f0}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111110;--fg:#ededea;--muted:#a3a39e;--card:#1a1a18;--line:#2e2e2b;--chip:#232320;--accent:#8fb0ff;--good:#7fd199;--good-bg:#17301f;--bad:#f2a6a0;--bad-bg:#3a1d1b;--code:#20201e}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1000px;margin:0 auto;padding:28px 16px 60px}
h1{font-size:30px;line-height:1.2;margin:4px 0 10px;letter-spacing:-.01em}h2{font-size:22px;line-height:1.25;margin:38px 0 8px}h3{font-size:16px;margin:16px 0 4px}
p{margin:6px 0}a{color:var(--accent)}code{font:.88em ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--code);padding:1px 5px;border-radius:5px;overflow-wrap:anywhere}
pre{font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--code);padding:12px 14px;border-radius:8px;overflow:auto;margin:8px 0}
.eyebrow{color:var(--muted);font-size:13px}.verdict{font-size:18px;line-height:1.45;font-weight:600;margin:0 0 4px}.qual{color:var(--muted);margin:0 0 14px}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:16px 0}@media (max-width:760px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;min-width:0}.stat b{display:block;font-size:21px;line-height:1.2;font-variant-numeric:tabular-nums}.stat span{color:var(--muted);font-size:13px}
.hero{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px}.hero video,.hero img{display:block;width:auto;max-width:100%;height:auto;max-height:86vh;margin:0 auto;border-radius:6px;background:#000}
.chapters{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 2px}.chapters button{font:inherit;font-size:13px;background:var(--chip);color:var(--fg);border:1px solid var(--line);border-radius:999px;padding:3px 10px;cursor:pointer}.chapters b{color:var(--muted);font-weight:500;margin-right:4px;font-variant-numeric:tabular-nums}
.note{font-size:13px;color:var(--muted);margin:8px 2px 2px}
.figs{display:grid;gap:12px;grid-template-columns:1fr 1fr;margin-top:10px}@media (max-width:760px){.figs{grid-template-columns:1fr}}.figs>*{min-width:0}figure{margin:0;min-width:0}
figure .zoom{display:block;width:100%;padding:0;border:1px solid var(--line);border-radius:8px;background:var(--bg);cursor:zoom-in;overflow:hidden}figure img{display:block;width:100%;height:auto}figcaption{font-size:13px;color:var(--muted);margin-top:5px}
.phone{max-width:300px}.missing{padding:20px;border:1px dashed var(--bad);color:var(--bad)}
.tablewrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px;margin:8px 0}table{border-collapse:collapse;width:100%;font-size:14px;min-width:560px}th,td{text-align:left;padding:7px 12px;border-bottom:1px solid var(--line);vertical-align:top}thead th{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600}tbody tr:last-child>*{border-bottom:0}td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;font-size:12px;border-radius:999px;padding:1px 8px;font-weight:600;white-space:nowrap}.pill.ok{background:var(--good-bg);color:var(--good)}.pill.bad{background:var(--bad-bg);color:var(--bad)}
ul{margin:4px 0;padding-left:20px}li{margin:3px 0}dialog{border:0;padding:0;background:transparent;max-width:96vw;max-height:94vh}dialog::backdrop{background:rgba(0,0,0,.75)}dialog img{display:block;max-width:96vw;max-height:94vh;width:auto;height:auto;border-radius:6px;cursor:zoom-out}footer{color:var(--muted);font-size:13px;margin-top:40px}
"""
JS = r"""
const dlg=document.getElementById('zoom'),big=dlg.querySelector('img');
document.addEventListener('click',(ev)=>{const b=ev.target.closest('button.zoom');if(b){const i=b.querySelector('img');big.src=i.src;big.alt=i.alt;dlg.showModal();}});
dlg.addEventListener('click',()=>dlg.close());
const v=document.getElementById('hero');
document.querySelectorAll('[data-seek]').forEach((b)=>b.addEventListener('click',()=>{v.currentTime=+b.dataset.seek;v.play();}));
"""


def build():
    head = git("rev-parse", "--short", "HEAD")
    subjects = git("log", "--reverse", "--format=%h\x1f%s", f"{BASE}..HEAD").splitlines()
    marks = json.loads((HERE / "marks.json").read_text(encoding="utf-8"))
    final = json.loads((HERE / "fleet-map-checks.json").read_text(encoding="utf-8"))
    passed = sum(1 for item in final if item["ok"])
    red = counted(HERE / "red-browser.log")
    red_unit = (HERE / "red-unit.log").read_text(encoding="utf-8") if (HERE / "red-unit.log").exists() else ""
    red_unit_pass, red_unit_fail = [int(x) for x in re.findall(r"^# (?:pass|fail) (\d+)$", red_unit, re.M)] if red_unit else (0, 0)
    mutations = json.loads((HERE / "mutations.json").read_text(encoding="utf-8"))
    caught = sum(1 for m in mutations if m["failed"])
    carry = json.loads((HERE / "carry-over.json").read_text(encoding="utf-8"))
    suite = full_suite()
    browser_total = sum(b for _, b in suite["browser"]) if suite else None
    browser_passed = sum(a for a, _ in suite["browser"]) if suite else None
    suite_ok = bool(suite) and not any(mark == "FAIL" for mark, _, _ in suite["summary"])
    origin = marks["open: the rack is picked, real"]["at"] - 0.2
    chapters = [(marks[k]["at"] - origin, label) for k, label in (
        ("a click on a marker: its runs, its newest run, its plot", "a robot on the map"), ("a counted marker asks which robot", "a counted marker asks"),
        ("the second robot at that site", "the robot it names"), ("an older run", "an older run"), ("play", "play"), ("the table tab: the pick is marked", "the table tab"),
        ("back on the map: its marker is marked", "back on the map"))]
    mp4 = data_uri(HERE / "hero.mp4", "video/mp4")
    gif = data_uri(HERE / "hero.gif", "image/gif")
    chips = "".join(f'<button type="button" data-seek="{t:.1f}"><b>{t:04.1f}s</b>{e(label)}</button>' for t, label in chapters)
    crop = (36, 226, 1244, 1000)   # the Deployments panel and the runs under it, on a 1280 x 1000 shot
    H = []
    H.append(f"""<p class="eyebrow">data-ui · lane/fleet-map · 2026-10-30</p>
<h1>Fleet map: click a robot, see its runs, play one</h1>
<p class="verdict">Every deployment is one list you can navigate, and the map is one tab of it: click a robot and its runs list, its newest run loads, and you can play it.</p>
<p class="qual">On <code>main</code> @ <code>{head}</code>; not deployed. One real rack among 11 synthetic robots, labelled so everywhere. The Clank button is not built: this lane is the website example and what data-ui lacked.</p>
<div class="stats">
<div class="stat"><b>{passed}/{len(final)}</b><span>frozen browser checks, final commit</span></div>
<div class="stat"><b>{red[0]}/{red[1]}</b><span>the same checks on main's kit, the red</span></div>
<div class="stat"><b>{caught}/{len(mutations)}</b><span>deliberate breakages the checks caught</span></div>
<div class="stat"><b>{'all green' if suite_ok else 'see below'}</b><span>full suite, {browser_passed if suite else '?'}/{browser_total if suite else '?'} browser checks</span></div>
</div>""")
    H.append(f"""<section><div class="hero">
<video id="hero" autoplay muted loop playsinline controls preload="auto" width="860">
<source src="{mp4}" type="video/mp4">
<img src="{gif}" alt="The hero as a GIF: a click on a robot on the map, its runs list and its plot redraws; a counted marker asks which robot; a run plays; the pick is marked in the table tab and back on the map.">
</video>
<div class="chapters">{chips}</div>
<p class="note">A real recording of the built page, one take: the head trimmed and the frame cropped to the dashboard, no speed change, nothing drawn on top. The red ring is a pointer the script adds, because a headless recording shows no cursor. The page opens on the real rack; every robot after it is synthetic, and its plot's legend says so.</p>
</div>
<p>To open it yourself: <code>npm --prefix ~/data-ui run serve</code>, then <code>/gallery/robotics-fleet/index.html</code> at the address it prints.</p></section>""")
    figures = [
        fig("picked-robot.png", "The map with Gantry C1 picked: a ring on its marker, its three runs below", "A picked robot wears a ring, not a colour: colour is its status. Its runs are below, newest first and picked.", crop=crop),
        fig("chooser.png", "A chooser over a counted marker listing Sorter A1 in green and Sorter A2 in red", "A counted marker asks which robot, and shows each one's own status: the marker alone would hide that one of these two is in fault.", crop=crop),
        fig("table-tab.png", "The Table tab with the picked robot's row marked", "The same rows as a table: the same pick, marked, in the URL.", crop=crop),
        fig("cards-tab.png", "The Cards tab with one card marked", "And as cards. The mark reaches them too: it did not before.", crop=crop),
        fig("chooser-dark-1280.png", "The map in dark, the chooser open", "Dark: the ring and the chooser take the kit's tokens.", crop=crop),
        fig("chooser-dark-390.png", "The map at 390 px, dark, the chooser open", "A phone, 390 px: a real tap, the chooser on screen, no sideways scroll.", width=420, crop=(40, 290, 740, 1400), cls="phone"),
    ]
    H.append(f"""<section><h2>The page</h2><div class="figs">{"".join(figures)}</div></section>""")
    H.append("""<section><h2>What was actually missing</h2>
<p>The plan named one gap. Measured on main, that one was not there and others were, and the fourth row would have broken the flow you asked for: the first robot worked, the second did not.</p>
<div class="tablewrap"><table><thead><tr><th>Going in</th><th>Measured on main</th><th>What landed</th></tr></thead><tbody>
<tr><td>A marker click cannot pick a robot</td><td>It already could: a marker calls <code>host.open</code>, which a dashboard turns into a selection. Ctrl / cmd too.</td><td>Nothing needed. The checks hold it.</td></tr>
<tr><td>A picked marker is not marked</td><td>True, and cards had the same gap. A table on a dashboard is marked by a stylesheet, not <code>selected(set)</code>, so nothing reached a map.</td><td><code>el.picked</code> on <code>&lt;data-views&gt;</code>, read by <code>selected(set)</code> and <code>input.selected</code>; a ring on the marker, <code>aria-pressed</code>; the card's mark.</td></tr>
<tr><td>A counted marker picks an arbitrary row</td><td>It picked every row at the point.</td><td>A chooser on MapLibre's Popup, keyboard included. Rows sharing one value need no question.</td></tr>
<tr><td>Not in the brief</td><td>The second robot you click keeps the first robot's run: no file loads and the playback says "the picks leave no run". <code>robotics-deployments</code> has one deployment, so it never showed.</td><td>A <code>selected:</code> panel whose selection names no row picks again by its preset, in the same pick and history entry.</td></tr>
<tr><td>Not in the brief</td><td>Space on a focused marker went to the playback clock.</td><td>The map's controls join the clock's list of controls that keep their keys.</td></tr>
</tbody></table></div></section>""")
    red_pill = '<span class="pill bad">red</span>'
    rows = "".join(f"<tr><td><code>{e(sha)}</code></td><td>{e(subject)}</td><td>{red_pill if 'failing first' in subject else ''}</td></tr>" for sha, subject in (line.split("\x1f") for line in subjects))
    mutation_rows = "".join(f"<tr><td>{e(m['mutation'])}</td><td class='num'>{len(m['failed'])}</td><td>{e(m['failed'][0]) if m['failed'] else 'NOT CAUGHT'}</td></tr>" for m in mutations)
    H.append(f"""<section><h2>Proof</h2>
<ul>
<li><b>The ruler was frozen before the kit changed.</b> <code>tests/browser/fleet_map_checks.py</code> and <code>tests/unit/fleet-map.test.mjs</code> are unchanged since their red commit (<code>git diff</code> of both, red to final, is empty). On main's kit: browser {red[0]} pass, {red[1] - red[0]} fail; unit {red_unit_pass} pass, {red_unit_fail} fail. Final: {passed}/{len(final)} (more checks than the red's {red[1]}: a section that could not run counted as one failure there).</li>
<li><b>Oracles are outside the kit.</b> A robot's runs, a run's t span and its plotted points come from the case's JSON. Where a marker stands is Web Mercator worked out in the check: every marker lands within 1.5 px. Clicks are real mouse, keyboard and touch events at each thing's on-screen position.</li>
<li><b>The checks can fail.</b> Each row below broke one behaviour in a scratch copy of <code>cb1a26c</code> (a 4 s ceiling on each wait) and the frozen checks went red on that behaviour, including the "no <code>select:</code>" guards that passed from the start. The two fixes after that commit have their own red-first tests.</li>
<li><b>Goldens.</b> The perf digests are written by main's kit over the new case, per their own rule; the table oracle's 110 keys did not move.</li>
{f'<li><b>Full suite on the final commit:</b> {suite["units"].get("pass", "?")}/{suite["units"].get("tests", "?")} unit, {suite["python"]} Python, {browser_passed}/{browser_total} browser checks.</li>' if suite else ''}
</ul>
<h3>Commits</h3><div class="tablewrap"><table><tbody>{rows}</tbody></table></div>
<h3>Deliberate breakages</h3><div class="tablewrap"><table><thead><tr><th>Broken on purpose</th><th>Checks red</th><th>The first one</th></tr></thead><tbody>{mutation_rows}</tbody></table></div></section>""")
    H.append(f"""<section><h2>Carrying this to lane/map</h2>
<p>Measured by applying this lane's map diff to a scratch checkout of <code>lane/map</code> @ <code>{e(carry['lane_map'])}</code>, then building it.</p>
<ul>
<li><code>map.css</code> lands clean ({carry['css_added']} lines).</li>
<li><code>index.js</code>: {carry['conflicts']} conflicts, each "keep both": the header and imports (keep lane/map's), <code>destroy()</code> (add <code>this._closeChooser()</code>), <code>selected()</code> and <code>_paintSel()</code> beside <code>_helpers</code>, and <code>update()</code> (add <code>this._sel = input.selected || new Set()</code>). The chooser, <code>rowColour</code> and the <code>_drawMarkers</code> hunk land clean.</li>
<li>One word by hand: add <code>Popup</code> to lane/map's <code>const {{ Map: MapLibre, Marker, … }} = maplibre</code>.</li>
<li>Result: +{carry['added']} / -{carry['removed']} in <code>index.js</code>, and it builds. Behaviour there is not verified: lane/map is 200+ commits behind main, so it has no <code>el.picked</code> until it is rebased.</li>
<li><b>What will not carry by itself:</b> lane/map's WebGL layers. A click on a region or hexagon already picks its rows, but the mark reaches only HTML markers; a region needs <code>setFeatureState</code> in <code>_paintSel</code>. That is why the mark is <code>selected(set)</code> and not a stylesheet: CSS cannot reach a WebGL feature. Its §32 also needs renumbering, as §33 already notes.</li>
</ul></section>""")
    H.append("""<section><h2>Judgment calls</h2><ul>
<li><b><code>el.picked</code>, not <code>el.select()</code>.</b> Reusing the selection would have drawn a bulk bar whose Clear cannot clear a dashboard's pick, fired <code>data-views-select</code> and redrawn views. The plan's "<code>host.select</code>, like the table" is not how a table picks on a dashboard (that is <code>host.open</code>), so the click path stayed.</li>
<li><b>The chooser is a popup at the point, not the peek's list.</b> The plan preferred reusing that list. It is a read-only table under one arbitrary row's fields, across the page from the marker, and making it pick would have reached into core; the popup is one block in the map's own file, which also keeps the carry-over small.</li>
<li><b>Presets settle only for panels that write <code>selected:</code>.</b> Any other panel keeps a stale selection, as before. Wider would be a behaviour change for every dashboard.</li>
<li><b>Order:</b> the case went in first, then the red, because the checks' oracle is the case's JSON. One ruler bug was found and fixed before the freeze, by running it on main: a wait compared a view's name with its type. Two gaps found reviewing my own code after the checks went green (a live dataset, a word in a search) got new test files, not edits to the frozen ones.</li>
<li><b>The rack's status and point are this case's.</b> The archive holds no live status, so it says idle, and its point is Vancouver's city centre, never the bench's address. The README says so.</li>
<li><b>A sentence, not a legend, says what the colours mean.</b> Main's map has no legend and lane/map brings one.</li>
</ul></section>""")
    H.append("""<section><h2>What is left</h2><ul>
<li><b>Needs you: lane/map.</b> Still held for your pick. Recommendation: when it lands, carry this as above. If you say nothing, nothing moves.</li>
<li><b>Needs you: should Space always play on a page with a clock?</b> Two older gaps sit beside this flow: click a run with the mouse and press Space, and it unpicks the run (on main too, in <code>robotics-deployments</code>); after a marker click focus is on the page, so Space scrolls. Space on a focused tab or chip also plays instead of activating it. <code>:focus-visible</code> cannot separate these, because Chromium turns it on as the key arrives. Recommendation: on a clock dashboard, Space plays and Enter picks. Default if you say nothing: leave them; Enter works on all of these.</li>
<li><b>Next, not blocked:</b> the Clank button you imagined. This case is what it opens.</li>
<li><b>Not verified:</b> a real phone or GPU (headless Chromium with software WebGL and an emulated touch screen), Firefox and Safari.</li>
<li><b>Deliberately not done:</b> no deploy; no legend; no new PEP (additive, CONTRACT §39); lane/map not merged or depended on.</li>
</ul></section>""")
    body = "\n".join(H)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fleet map</title><style>{CSS}</style></head>
<body><main>{body}<footer>Built by docs/build_fleet_map_report.py from measured files. Media inlined: {sum(SIZES.values()) / 1024:.0f} KB before encoding.</footer></main>
<dialog id="zoom"><img alt=""></dialog><script>{JS}</script></body></html>"""
    OUT.write_text(page, encoding="utf-8")
    size = OUT.stat().st_size
    print(f"{OUT}: {size:,} bytes; {SIZES}")
    if size > SIZE_LIMIT:
        raise SystemExit(f"over {SIZE_LIMIT:,} bytes")


if __name__ == "__main__":
    build()
