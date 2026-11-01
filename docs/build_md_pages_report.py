"""Build the notes page's review report: docs/capture_md_pages.py's take and stills, the checks, the round trips and the mutation run.

    python3 docs/build_md_pages_report.py <capture dir> <checks json> <trips json> <mutations json> <gate line> <out.html>

Encodes the take with ffmpeg (one cut, no speed change). Pictures and the video go in reports/media/md-pages-2026-10-31/ beside the page, which stays text-only.
"""
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

CAP, CHECKS, TRIPS, MUTS, GATE, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5], Path(sys.argv[6])
MEDIA = OUT.parent / "media" / OUT.stem
MEDIA.mkdir(parents=True, exist_ok=True)
esc = html.escape


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


marks = json.loads((CAP / "marks.json").read_text(encoding="utf-8"))
end = marks["hand edit"] + 1.3
ff("-ss", "0.3", "-to", str(end), "-i", str(CAP / "raw" / "hero.webm"), "-vf", "fps=24,format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-movflags", "+faststart", "-an", str(MEDIA / "hero.mp4"))
ff("-i", str(MEDIA / "hero.mp4"), "-vf", "fps=6,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=none", str(MEDIA / "hero.gif"))
for f in CAP.glob("*.png"):
    ff("-i", str(f), "-c:v", "libwebp", "-quality", "80", str(MEDIA / f"{f.stem}.webp"))
checks = json.loads(CHECKS.read_text(encoding="utf-8"))
trips = json.loads(TRIPS.read_text(encoding="utf-8"))
muts = json.loads(MUTS.read_text(encoding="utf-8"))
ok = sum(c["ok"] for c in checks)
killed = sum(m["killed"] for m in muts)
t = lambda k: sum(v[k] for v in trips.values())
before = (CAP / "files" / "before.md").read_text(encoding="utf-8")
after = (CAP / "files" / "after-section.md").read_text(encoding="utf-8")
hand = (CAP / "files" / "after-hand.md").read_text(encoding="utf-8")
fr = (Path(__file__).resolve().parents[1] / "gallery" / "md-pages" / "frdparrc" / "vibetracks.1.md").read_text(encoding="utf-8")
first1, first2, first3 = ((CAP / "files" / f"first-{n}.md").read_text(encoding="utf-8") for n in ("1-row", "2-cells", "3-page"))
wiki = (CAP / "files" / "wikilinks.md").read_text(encoding="utf-8").split("# Linked", 1)[1]
wiki = "# Linked" + wiki
saved = ", ".join(f"{c['value']} s {c['name'].split('saved outside ')[1].split(' reaches')[0]}" for c in checks if "saved outside" in c["name"])
fr5 = (Path(__file__).resolve().parents[1] / "gallery" / "md-pages" / "frdparrc" / "vibetracks.5.md").read_text(encoding="utf-8")


def fig(name, caption, cls=""):
    return f'<figure class="{cls}"><a href="media/{OUT.stem}/{name}.webp"><img src="media/{OUT.stem}/{name}.webp" alt="{esc(caption)}" loading="lazy"></a><figcaption>{esc(caption)}</figcaption></figure>'


def rows(items):
    return "".join(f'<li class="{"good" if c["ok"] else "bad"}">{esc(c["name"])}</li>' for c in items)


page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Notes as Pages</title>
<style>
:root {{ color-scheme: light dark; --bg:#fff; --fg:#18181b; --mut:#5f5f68; --line:#e4e4e7; --sub:#f4f4f5; --acc:#2563eb; --good:#15803d; --bad:#b91c1c; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#18181b; --fg:#f4f4f5; --mut:#a1a1aa; --line:#3f3f46; --sub:#27272a; --acc:#7aa7ff; --good:#4ade80; --bad:#f87171; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width: 1040px; margin: 0 auto; padding: 28px 16px 80px; }}
h1 {{ font-size: 28px; line-height: 1.2; margin: 0 0 8px; }} h2 {{ font-size: 21px; margin: 40px 0 8px; }} h3 {{ font-size: 16px; margin: 22px 0 6px; }}
p, li {{ max-width: 76ch; }} .lede {{ color: var(--mut); }}
a {{ color: var(--acc); }}
video, img {{ display: block; max-width: 100%; height: auto; border: 1px solid var(--line); border-radius: 8px; }}
figure {{ margin: 14px 0; }} figcaption {{ color: var(--mut); font-size: 14px; margin-top: 4px; }}
.two {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }}
.phones {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }}
pre {{ margin: 0; padding: 10px 12px; overflow-x: auto; background: var(--sub); border-radius: 6px; font: 12.5px/1.45 ui-monospace, Menlo, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }}
.num {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 14px 0; }}
.num div {{ padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; }} .num b {{ display: block; font-size: 20px; }} .num span {{ color: var(--mut); font-size: 13px; }}
.note {{ padding: 10px 14px; border-left: 3px solid var(--acc); background: var(--sub); border-radius: 0 6px 6px 0; }}
ul.checks {{ columns: 2 320px; font-size: 13.5px; padding-left: 18px; }} ul.checks li {{ break-inside: avoid; }} li.bad {{ color: var(--bad); font-weight: 600; }}
details {{ margin: 10px 0; }} summary {{ cursor: pointer; }}
</style></head><body><main>
<h1>Notes as a table and as pages</h1>
<p class="lede"><b>A folder of .md files is now a table with Notion-style pages, and each column is one H1.</b> Start in the table, expand on the page, or open the note in Obsidian: it is one file throughout. On <code>lane/md-pages</code>, not merged. Delete, rename and "add a property" from the page are not built.</p>

<video src="media/{OUT.stem}/hero.mp4" poster="media/{OUT.stem}/table-light.webp" controls muted loop autoplay playsinline><img src="media/{OUT.stem}/hero.gif" alt="The take as a GIF"></video>
<p class="lede">One take, no speed change. Open a row, turn Copied from into a section (the preview says 14 of 14 files), drag Desired above it, then a real write to the file from outside the browser lands on the open page.</p>

<div class="num"><div><b>{GATE}</b><span>npm test</span></div><div><b>{ok} of {len(checks)}</b><span>browser checks, real server, real mouse</span></div><div><b>{t("sameBytes")} of {t("trips")}</b><span>property to section and back, byte-identical</span></div><div><b>{t("selfSame")} of {t("selfWrites")}</b><span>values set to themselves: same file</span></div><div><b>{killed} of {len(muts)}</b><span>mutations caught</span></div></div>

<h2>This replaced H1-H4</h2>
<p class="note">Your change mid-build: "If I saw each column is associated with an H1 then its simpler... and then you see all of the sub headers inside the cell basically". The first build gave a property a place of <code>top</code> or <code>h1</code>..<code>h4</code>. That is gone. A place is <code>top</code> or <code>section</code>, a section is always one H1, and everything under it, H2 and H3 included, is that one cell.</p>
<div class="two">{fig("frdparrc-table", "The generated table. DP's cell is that section's sub-headings, H3s indented, the source's (1) (2) (3) kept; '… +1' counts what six lines left out. Sections with no sub-headings show their first lines; empty ones show a dash.")}{fig("frdparrc-page", "Clicking an outline cell opens that section on the page, box open, because the cell is derived.")}</div>
<ul>
<li><b>Cell display, per column in the .base:</b> <code>outline</code> (a section's default, and it falls back to first lines when there are no sub-headings), <code>preview</code> (first lines always). The demo's "DP as first lines" tab is <code>display: {{ dp: preview }}</code>.</li>
<li><b>The row height decides how much shows:</b> short 1 line, medium 3, tall 6, extra 10, unset 3. Thumbnails take two lines' room, and with no room a picture reads [image]. What does not fit is counted (<code>… +4</code>) or ends in an ellipsis, never clipped silently.</li>
<li><b>Editing:</b> only a cell showing a generated outline opens the page. A section with no sub-headings is the value itself, so it edits in place.</li>
</ul>

<h2>Start in the table, expand on the page</h2>
<p>Your case: "fill it in top level, and then when I need to expand on it more. I basically go to the page view.. its all one linked piece of information! vs a summary and something else". The cell and the page are one value in one file. The browser proof walks this and reads the file at each step.</p>
<div class="two"><div><h3>1. A new row in the table</h3><pre>{esc(first1)}</pre></div><div><h3>2. Two cells typed in</h3><pre>{esc(first2)}</pre></div><div><h3>3. An H2 added on the page</h3><pre>{esc(first3)}</pre></div></div>
<div class="two">{fig("first-cells", "Step 2: both sections typed in their cells, still their words, still editable in the cell.")}{fig("first-outline", "Step 3 back in the table: DP's cell is now its outline; Risks has no sub-headings, so it stays its words.")}</div>

<h2>Open in Obsidian, and wikilinks</h2>
<p>Run with <code>--vault &lt;name&gt; --vault-root &lt;path&gt;</code> and a folder inside that vault gets <b>Open in Obsidian</b> on each page and in each row's right-click menu, an <code>obsidian://open</code> link to that file. Outside it, or with no option, the control is not there at all, never greyed. There is no wikilink autocomplete: that is what opening in Obsidian is for.</p>
<p><code>[[note]]</code>, <code>[[note|alias]]</code>, <code>[[note#heading]]</code> and <code>![[image.png]]</code> stay byte for byte in the file and render as links and pictures. A click opens the note in Obsidian. With no vault, a link to a note in this table opens it here, and anything else stays its words.</p>
<p class="note"><b>A file edited in Obsidian must reach the table within about a second.</b> Measured from outside the browser, both ways an editor saves: {saved}. I have not run this with Obsidian itself: the links were read from the page and not clicked, so that nothing took your screen. One real click is worth trying.</p>
<div class="two">{fig("obsidian", "Open in Obsidian on the page, and each wikilink form in a section. The vault name and this Linked section exist only in a temp copy, written for this picture.")}<div><h3>The same section in the file</h3><pre>{esc(wiki)}</pre></div></div>

<h2>The file stays yours</h2>
<p>The move in the take, on one real note. Only these lines changed, in each of the 14 files. Nothing else was re-serialised: every edit is a splice of the original text.</p>
<div class="two"><div><h3>Before</h3><pre>{esc(before)}</pre></div><div><h3>After "Copied from → Section"</h3><pre>{esc(after)}</pre></div></div>
<details><summary>The FRDPARRC note, in plain text</summary><pre>{esc(fr)}</pre></details>
<details><summary>An FR with nothing to say yet: empty sections stay empty</summary><pre>{esc(fr5)}</pre></details>

<h2>Three calls I made</h2>
<h3>Non-text types: allowed as a section, data stays put</h3>
<p>A number, date, checkbox, select, list or link can be drawn as a section, but its value stays typed in the frontmatter and 0 files change. The preview says so. The block is the heading and its typed control, no place to write, and it still sorts and filters. Your guess was right: only words move. Refusing would cost you the layout; moving it would let one typed "about 12" turn a number column into words.</p>
{fig("type-preview", "The honest preview for a select.")}
<h3>Block order: a layout rule, no file rewritten</h3>
<p>Reordering changes the <code>page:</code> key in the .base, one place. A view preference should not make an N-file diff and a sync of every note, a person's note keeps the order they wrote, and notes need not hold the same headings. The cost: Obsidian's outline keeps the file's order. A new section is written where the layout says.</p>
<h3>Rule for headings</h3>
<p>Only an H1 starts a section. Everything before the first H1, an H2 included, is <code>page</code>, always last on the page. A heading twice is <code>x</code> and <code>x_2</code>, so nothing is dropped. A value holding an H1 refuses to move into a section and names the file; an H2 inside moves with it.</p>

<h2>What it looks like</h2>
<div class="two">{fig("table-light", "Feedback, light: first lines, a thumbnail where the row has room.")}{fig("table-dark", "Dark.")}{fig("page-light", "The page, light: title, properties, blocks, free text last. Comment-free.")}{fig("page-dark", "Dark.")}</div>
<div class="phones">{fig("table-390-light", "Table at 390 px.")}{fig("page-390-light", "Page at 390 px, light.")}{fig("table-390-dark", "Table, dark.")}{fig("page-390-dark", "Page, dark.")}</div>
<div class="two">{fig("preview", "The preview before any file changes.")}{fig("frdparrc-full", "The full-page open: ⤢, and full=1 in the link.")}</div>

<h2>Proof</h2>
<ul>
<li><b>Round trips over the real rows:</b> {trips["feedback"]["notes"]} feedback notes and {trips["frdparrc"]["notes"]} FRDPARRC notes, every text property to its other place and back: {t("sameBytes")} of {t("trips")} byte-identical, {t("valuesSame")} of {t("valuesCompared")} other values unchanged while moved.</li>
<li><b>Hand edit:</b> on the open page in under 0.2 s (browser check). The first version took 1.2 and 2.3 s, because Node's recursive watcher on Linux loses a file replaced by a rename, so the server now watches each folder.</li>
<li><b>Server:</b> 127.0.0.1 only; wrong Host, wrong or missing Origin, a plain-form content type, <code>..</code>, encoded dots, a dot folder and a symlink out are all refused, tested on a real socket.</li>
</ul>
<details><summary>All {len(checks)} browser checks</summary><ul class="checks">{rows(checks)}</ul></details>
<details><summary>The {len(muts)} mutations</summary><ul class="checks">{"".join(f'<li class="{"good" if m["killed"] else "bad"}">{esc(m["mutation"])}: {m["failed"]} failing</li>' for m in muts)}</ul></details>

<h2>Left, and what needs you</h2>
<ul>
<li><b>Not built:</b> delete, rename, add a property from the page. A rename belongs to Obsidian, which keeps links right. Next if you want them.</li>
<li><b>Not tested in the real Obsidian app:</b> a click on an <code>obsidian://</code> link, and whether Obsidian keeps the <code>page:</code> key when it rewrites a .base. The notes themselves are plain markdown, read here in plain text.</li>
<li><b>A hand-typed <code># Cost</code> over <code>12</code> reads as words</b> and sorts as text. By the rule; says so in the contract.</li>
<li><b>Privacy:</b> one real feedback screenshot names a private supplier contact. I kept the case off the site (it sits beside gallery/examples/) and added it to the public export's keep-out list. If you want it out of main's history too, say so before landing; the default is to land it, since the repo has no public remote.</li>
<li><b>Demo words I added:</b> <code>copied_from</code>, the Tests/Method/Result labels, the first line of vibetracks.1's DP, and its sub-headings, which are commit 4ec339f's words cut short. The rest is copied. Feedback rows grew from 11 to 14 while I built: the originals gained three.</li>
</ul>
</main></body></html>
"""
OUT.write_text(page, encoding="utf-8")
print(OUT, f"{OUT.stat().st_size} bytes", sum(f.stat().st_size for f in MEDIA.iterdir()) // 1024, "KB media")
