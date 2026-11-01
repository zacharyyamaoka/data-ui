"""Builds the dashboard editor's review report: ~/data-ui/reports/media/dashboard-editor-2026-10-30.html.

    python3 docs/build_dashboard_editor_report.py [FULL_LOG]

One self-contained page: the hero is an H.264 mp4 data URI with a GIF inside it as the fallback, every still a WebP data URI, the CSS
inline. It opens from disk with no server or network, and lives in reports/media/ (gitignored) because it inlines media.

Reads only measured inputs, never the code under test:
- the hero (reports/media/dash-editor-hero/hero.mp4, hero.gif, marks.json), recorded by docs/capture_dashboard_editor.py from the real
  gallery page;
- the screenshots and dash-editor-checks.json that tests/browser/dash_editor_checks.py wrote (default reports/media/dash-editor);
- mutations.txt beside them (each mutation of the code, and the journey that went red);
- FULL_LOG, the `node tools/test-all.mjs` log of the landed commit, when given;
- git, in this worktree.
"""

import base64
import html
import io
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
MAIN = Path("~/data-ui")
OUT = MAIN / "reports" / "media" / "dashboard-editor-2026-10-30.html"
SHOTS = REPO / "reports" / "media" / "dash-editor"
HERO = MAIN / "reports" / "media" / "dash-editor-hero"
FULL_LOG = Path(sys.argv[1]) if len(sys.argv) > 1 else None
e = html.escape
SIZES = {}


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True).stdout.strip()


def still(name, width=880, crop=None, quality=74):
    """A screenshot as a WebP data URI, downscaled here."""
    im = Image.open(SHOTS / f"{name}.png").convert("RGB")
    if crop:
        im = im.crop(crop)
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=quality, method=6)
    SIZES[name] = len(buf.getvalue())
    return f"data:image/webp;base64,{base64.b64encode(buf.getvalue()).decode()}", im.width, im.height


def data_uri(path, mime):
    b = path.read_bytes()
    SIZES[path.name] = len(b)
    return f"data:{mime};base64,{base64.b64encode(b).decode()}"


def fig(name, caption, **kw):
    src, w, h = still(name, **kw)
    return f'<figure><img src="{src}" width="{w}" height="{h}" alt="{e(caption)}" loading="lazy"><figcaption>{e(caption)}</figcaption></figure>'


def counts():
    checks = json.loads((SHOTS / "dash-editor-checks.json").read_text(encoding="utf-8"))
    ok = sum(1 for c in checks if c["ok"])
    unit = browser = suites = None
    if FULL_LOG and FULL_LOG.exists():
        text = FULL_LOG.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^# pass (\d+)\n(?:.*\n)*?^# fail (\d+)", text, re.M)
        unit = (m.group(1), m.group(2)) if m else None
        lines = re.findall(r"^(ok  |FAIL|skip) ", text, re.M)
        suites = (lines.count("ok  "), lines.count("FAIL"), lines.count("skip"))
    return ok, len(checks), unit, suites


def main():
    mp4 = data_uri(HERO / "hero.mp4", "video/mp4")
    gif = data_uri(HERO / "hero.gif", "image/gif")
    ok, total, unit, suites = counts()
    # the lane is what follows its red commit's parent, however often it was rebased
    red = git("log", "--format=%h", "--diff-filter=A", "--", "tests/browser/dash_editor_checks.py").split()[-1]
    log = git("log", "--reverse", "--format=%h %s", f"{red}~1..HEAD").splitlines()
    commits = "".join(f'<li><code>{e(c[:7])}</code> {"<b>red</b> " if "failing first" in c else ""}{e(c[8:].split(": ", 1)[-1])}</li>' for c in log)
    sha = git("rev-parse", "--short", "HEAD")
    # the ruler: what the red commit added, the runner's line aside; later commits add files beside it, and change none of these
    ruler = [f for f in git("show", "--name-only", "--format=", red).split() if f.startswith("tests/")]
    frozen = git("log", "--format=%h", "--", *ruler).split()
    mutations = (SHOTS / "mutations.txt").read_text(encoding="utf-8").splitlines() if (SHOTS / "mutations.txt").exists() else []
    caught = [m for m in mutations if m.startswith("CAUGHT")]
    mrows = "".join(f"<li>{e(re.sub(r'^CAUGHT ', '', m).split('  [')[0])} <span class=\"m\">{e(m.split('  [')[1].split(']')[0]) if '  [' in m else ''}</span></li>" for m in caught)
    suite = f"{suites[0]} of {sum(suites)} steps of <code>node tools/test-all.mjs</code> green" if suites else "the full suite's result is in the handoff"
    unitline = f", {unit[0]} unit tests" if unit else ""
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard editor</title>
<style>
:root {{ --bg:#fff; --fg:#18181b; --muted:#6b7280; --line:#e4e4e7; --tint:#f4f4f5; --accent:#2563eb; color-scheme:light dark; }}
@media (prefers-color-scheme:dark) {{ :root:not([data-theme="light"]) {{ --bg:#111113; --fg:#ececef; --muted:#9a9aa3; --line:#2c2c31; --tint:#1c1c20; --accent:#7aa2f7; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:960px; margin:0 auto; padding:28px 16px 64px; }}
h1 {{ font-size:24px; margin:0 0 6px; letter-spacing:-.01em; }} h2 {{ font-size:17px; margin:34px 0 8px; }}
p {{ margin:8px 0; }} .lede {{ color:var(--muted); }}
video,img {{ display:block; max-width:100%; height:auto; border-radius:8px; background:var(--tint); }}
figure {{ margin:18px 0; }} figcaption {{ font-size:13px; color:var(--muted); margin-top:6px; }}
.two {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(380px,100%),1fr)); gap:14px; align-items:start; }}
.wide {{ overflow-x:auto; }}
ul {{ margin:8px 0; padding-left:20px; }} li {{ margin:3px 0; }}
code {{ font:13px ui-monospace,SFMono-Regular,Menlo,monospace; background:var(--tint); padding:1px 4px; border-radius:4px; overflow-wrap:anywhere; }}
.m {{ color:var(--muted); font-size:13px; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }} th,td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ font-weight:600; color:var(--muted); }}
</style></head><body><main>
<h1>Dashboard editor</h1>
<p class="lede">One editor on <code>&lt;data-dashboard editor&gt;</code>: Edit mode is the base, the Blueprint is its outline, the queue sits under it. Landed on main at <code>{e(sha)}</code>. {ok} of {total} browser checks{e(unitline)}; {suite}.</p>
<video autoplay muted loop playsinline controls preload="auto" width="1280" height="800" aria-label="Edit, drag a panel, reorder in the outline, place a queued item, Save with the diff">
<source src="{mp4}" type="video/mp4"><img src="{gif}" width="520" height="325" alt="The same take as a GIF">
</video>
<p class="m">The real gallery page (<code>/gallery/robotics-servo/</code>), one take, no speed change: Edit, drag Playback up on the grid, drag Velocity up in the outline, drag a queued item onto the grid, Save shows the diff, Save. The red dot is the pointer.</p>

<h2>One state, three ways to touch it</h2>
<p>The <code>.base</code> text is the only thing edited. A drag on the grid, a row in the outline and a field in the options pane all end in one function of that text, and everything on screen is drawn from it, so a change in one shows in the others at once. A move or a resize draws nothing again: charts, scroll and hover stay.</p>
{fig("task-3-options", "The dashboard is the canvas. Outline and queue on the left, one options pane on the right; a click on a panel or a row selects the same thing.")}
<div class="two">
{fig("task-4-diff", "Save shows the diff first, in the same pane: the change in words, then the lines, wrapped so nothing is cut off. The host has been handed nothing yet.", width=420, crop=(944, 88, 1264, 792))}
{fig("themes-light-390", "390 px: no drag; the panes stack, folded, and Move up / Move down reorder. No sideways scroll in any state.", width=390)}
</div>
{fig("panes-folded", "Every side panel drags, keeps its width, resets on a double-click and folds, by button or Ctrl+B / Ctrl+Alt+B. Measured on whatever panes the page has.")}
{fig("themes-dark-1280", "Dark, from the kit's tokens: the editor's CSS has no colour of its own.")}

<h2>What came from where</h2>
<div class="wide"><table><tr><th>Part</th><th>From</th></tr>
<tr><td>Edit, drag and resize where panels sit, Save with its diff, Exit's question, Save as copy</td><td>V1 Edit mode (Grafana)</td></tr>
<tr><td>The layout as a tree: reorder, hide, group as tabs; the selected panel's properties</td><td>V2 Blueprint (Rerun)</td></tr>
<tr><td>A short list of things waiting, a drag or a click onto the grid</td><td>V4 Saved for later (Amazon)</td></tr>
<tr><td>Nothing: <code>edit-variant</code> and the switcher are gone</td><td>V3 Source, V5 Ask</td></tr></table></div>

<h2>Prior art</h2>
<p>You asked what is out there. They converge on one quiet way in, the canvas staying visible, structure in a tree or grid with the selected thing's settings beside it; the closest to this editor are Retool and Grafana's 2026 sidebar. None keeps a hand-written file's comments through a visual edit. Citations and what could not be verified are in <code>docs/peps/0017-dashboard-editor.md</code>.</p>
<div class="wide"><table><tr><th>Product</th><th>Way in</th><th>Structure</th><th>Selected thing</th><th>Leaving</th></tr>
<tr><td>Grafana</td><td>Edit</td><td>Content outline, a tree</td><td>Docked, resizable sidebar</td><td>Save (with a note), Exit edit</td></tr>
<tr><td>Shopify theme editor</td><td>Customize</td><td>Sidebar tree; hide keeps the section (<code>disabled</code>)</td><td>Settings beside the tree</td><td>Save; undo only until then</td></tr>
<tr><td>Notion</td><td>None: always editable</td><td>Blocks dragged into columns</td><td>Each view's own options</td><td>Not in the docs read</td></tr>
<tr><td>Metabase</td><td>Pencil</td><td>Tabs; a snapping grid</td><td>Hover icons on a card</td><td>Save or Cancel</td></tr>
<tr><td>Retool</td><td>The IDE</td><td>Component tree; 12-column canvas</td><td>Inspector; panels toggle</td><td>Not in the docs read</td></tr>
<tr><td>Home Assistant</td><td>Edit</td><td>Sections; "Imported cards" wait to be placed</td><td>Undo and redo at the top</td><td>Not in the docs read</td></tr></table></div>

<h2>What Arrange became</h2>
<p>The one grid path. <code>arrange.js</code> now exports <code>liveGrid</code>, and Arrange and Edit both come through it, so gridstack loads from one bundle. On a dashboard with no <code>editor</code>, Arrange is what it was, its own checks unchanged. With <code>editor</code>, Edit stands in its place and a reader's kept arrangement is not drawn, because what Edit shows must be what Save writes.</p>

<h2>Calls worth a look</h2>
<ul>
<li><b>A layout is a list.</b> The grid runs in gridstack 14's <code>list</code> mode, so a drag's preview is what the file will draw; panels never rest anywhere the file cannot say. <code>float</code> and <code>top</code> were measured and refused (PEP §2).</li>
<li><b>Hide is one key.</b> <code>hidden: true</code> on the entry, in place, an exact inverse, as Shopify's <code>disabled</code>. That is the one new <code>.base</code> key, so <code>schemas/view.schema.json</code> changed by four lines.</li>
<li><b>The queue is a file the host marks</b> (<code>queue: true</code> in <code>dashboards()</code>), so §34 fills it with no new word. An item leaves that file only on Save.</li>
<li><b>The gallery case is the Servo template opted in, not a new folder.</b> Every new <code>views.base</code> moves <code>perf-oracle.golden.json</code>, and goldens were not to move.</li>
<li><b>No change to packages/core.</b> <code>base.js</code> is bundled into the editor for <code>yamlFlow</code> rather than widening the core's API.</li>
</ul>

<h2>Proof</h2>
<p>The ruler was committed red before any of the code: real mouse and keyboard, expected text built from the fixture's literal lines, and a golden written from main before the editor. Nothing in it changed after: <code>git log</code> over the {len(ruler)} files of that commit lists {len(frozen)} commit{"" if len(frozen) == 1 else "s"}, <code>{e(" ".join(frozen))}</code>.</p>
<ul>{commits}</ul>
<p>{len(caught)} of {len(mutations) if mutations else len(caught)} deliberate breakages of the code turned the ruler red:</p>
<ul>{mrows}</ul>

<h2>Not verified</h2>
<ul>
<li>Touch: no real phone. At 390 px the checks use Chromium's emulation; dragging is off there by design.</li>
<li>Prior art, marked in the PEP: Grafana's Changes tab on its save drawer (its docs do not describe it), whether Shopify's double sidebar or Retool's panels resize, and that Home Assistant's raw editor allows no comments, which is community reports, not its docs.</li>
<li>A real host: the Servo page's host keeps files in this browser's localStorage. No server has answered <code>data-dashboard-save</code> yet.</li>
</ul>
</main></body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    n = OUT.stat().st_size
    print(f"wrote {OUT} ({n / 1e6:.2f} MB)")
    for k, v in SIZES.items():
        print(f"  {k}: {v / 1e3:.0f} KB")
    if n > 1.9e6:
        print("OVER 1.9 MB")


if __name__ == "__main__":
    main()
