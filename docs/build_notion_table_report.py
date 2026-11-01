"""Build the notion table's review page: one self-contained HTML, its hero video, stills and proof inside it.

Usage, after docs/capture_notion_table.py and the checks have run:
    python3 docs/build_notion_table_report.py <capture dir> <checks json> <out.html>

Encodes the take with ffmpeg (one cut, no speed change, as the capture wrote it), and reads the commits, the red and green marks and the
proof that no check moved after its red commit from git itself, so the page cannot disagree with the history. Fails if the page
comes out over 1.9 MB (the desktop preview's limit for a page with media).
"""
import base64
import html
import json
import re
import subprocess
import sys
from pathlib import Path

CAP, CHECKS, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
ROOT = Path(__file__).resolve().parents[1]
LIMIT = 1_900_000
RULER = ["tests/browser/notion_table_checks.py", "tests/unit/sheet-css.test.mjs", "tests/unit/edit-history.test.mjs", "tests/unit/sheet-paste.test.mjs", "tests/unit/sheet-columns.test.mjs"]


def run(*args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


def data_uri(path, mime):
    return f"data:{mime};base64,{base64.b64encode(Path(path).read_bytes()).decode()}"


def encode():
    """The take as an mp4 and a GIF fallback, cut to its first mark and its last."""
    marks = json.loads((CAP / "marks.json").read_text(encoding="utf-8"))
    raw = sorted((CAP / "raw").glob("*.webm"))[-1]
    start, end = max(0, marks["view"] - 0.6), marks["undone"] + 0.2
    mp4, gif = CAP / "hero.mp4", CAP / "hero.gif"
    run("ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-to", str(end), "-i", str(raw), "-vf", "fps=20,format=yuv420p",
        "-c:v", "libx264", "-profile:v", "high", "-preset", "veryslow", "-crf", "24", "-tune", "animation", "-movflags", "+faststart", "-an", str(mp4))
    run("ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf", "fps=3,scale=520:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=48:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle", str(gif))
    return mp4, gif, end - start


def still(name, width):
    out = CAP / f"{name}.webp"
    run("ffmpeg", "-y", "-loglevel", "error", "-i", str(CAP / f"{name}.png"), "-vf", f"scale={width}:-1:flags=lanczos", "-c:v", "libwebp", "-quality", "72", str(out))
    return data_uri(out, "image/webp")


def history():
    """The lane's commits, oldest first: sha, subject, whether it is a red, and how it touched the frozen checks."""
    # the lane starts at the commit before its first: found by its subject, so a rebase cannot leave this behind
    first = run("git", "log", "--format=%h", "--grep=^docs: CONTRACT §[0-9]* and PEP 0016", "-1").strip()
    log = run("git", "log", "--reverse", "--format=%h%x09%s", f"{first}^..HEAD")
    rows = []
    for line in log.strip().splitlines():
        sha, subject = line.split("\t", 1)
        stat = run("git", "show", "--numstat", "--format=", sha)
        touched = []
        for s in stat.strip().splitlines():
            added, removed, path = s.split("\t")
            if path in RULER:
                touched.append((path, int(added), int(removed)))
        rows.append({"sha": sha, "subject": subject, "red": subject.startswith("test(") and "failing first" in subject, "ruler": touched})
    return rows


def kind(row):
    """What a commit is, in the table's second column."""
    if row["red"]:
        return "<span class=red>red</span>"
    if row["subject"].startswith("test(perf oracle)"):
        return "<span class=doc>golden</span>"
    return "<span class=green>green</span>" if row["subject"].startswith(("feat(", "fix(", "perf(")) else "<span class=doc>docs</span>"


def frozen_proof(rows):
    """True when every commit that touches a ruler file is a red commit, and only adds to it."""
    bad = [r["sha"] for r in rows if r["ruler"] and not (r["red"] and all(removed == 0 for _, _, removed in r["ruler"]))]
    return bad


def main():
    mp4, gif, seconds = encode()
    results = json.loads(CHECKS.read_text(encoding="utf-8"))
    passed = sum(1 for c in results if c["ok"])
    rows = history()
    bad = frozen_proof(rows)
    head = run("git", "rev-parse", "--short", "HEAD").strip()
    groups = {}
    for c in results:
        key = re.split(r"[ :]", c["name"], maxsplit=1)[0]
        groups[key] = groups.get(key, 0) + 1
    words = {"toggle": "Edit / View", "delete": "Deleting rows", "undo": "Undo and redo", "paste": "Pasting a block", "sourced": "Values from sources", "columns": "Columns", "surfaces": "Where things are drawn", "blank": "From nothing", "filter": "Filter by hand", "case": "The gallery page", "looks": "First-look fixes"}
    shots = [("view", "View: a read-only table, to the byte. The page itself opens in Edit for a fresh viewer."), ("edit", "Edit: the add row, editable cells, the header's menu on hover."), ("paste", "A real Ctrl+V into a blank row: one undo step."),
             ("menu", "The column menu: name, type, filter, Hide, Delete, Add a property. No side panel."), ("filter", "Filter by hand: a choice list on the one filter, with its pill."), ("blank", "New blank table: one Name column, and nothing dead about it."), ("toast", "A row deleted with no dialog: the toast holds Undo."), ("wide-dark", "Dark, from the same tokens.")]
    figs = "".join(f'<figure><img src="{still(n, 760)}" alt="{html.escape(t)}" loading="lazy"><figcaption>{html.escape(t)}</figcaption></figure>' for n, t in shots)
    phone = still("phone-dark", 300)
    commit_rows = "".join(
        f'<tr><td><code>{r["sha"]}</code></td><td>{kind(r)}</td><td>{html.escape(r["subject"][:118])}{"…" if len(r["subject"]) > 118 else ""}</td><td class=num>{" ".join(f"+{a} −{d}" for _, a, d in r["ruler"])}</td></tr>'
        for r in rows)
    tiles = "".join(f'<li><b>{n}</b><span>{html.escape(words.get(k, k))}</span></li>' for k, n in groups.items() if k in words)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Notion table review</title>
<style>
:root {{ color-scheme: light dark; --bg:#fff; --fg:#191919; --muted:#5f5f5f; --rule:#e4e4e4; --soft:#f5f5f4; --accent:#1f6feb; --ok:#1a7f4b; --bad:#b3261e; --warn-bg:#fff6e0; --warn-rule:#e9c46a; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#16171a; --fg:#ececec; --muted:#a4a4a4; --rule:#2e3036; --soft:#1f2125; --accent:#79b1ff; --ok:#5fcf97; --bad:#ff8f86; --warn-bg:#2c2513; --warn-rule:#6e5a24; }} }}
:root[data-theme="dark"] {{ --bg:#16171a; --fg:#ececec; --muted:#a4a4a4; --rule:#2e3036; --soft:#1f2125; --accent:#79b1ff; --ok:#5fcf97; --bad:#ff8f86; --warn-bg:#2c2513; --warn-rule:#6e5a24; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 980px; margin: 0 auto; padding: 28px 16px 56px; }}
h1 {{ font-size: 25px; line-height: 1.25; margin: 0 0 6px; letter-spacing: -.01em; }}
h2 {{ font-size: 17px; margin: 34px 0 8px; }}
p {{ margin: 8px 0; }}
.lede {{ color: var(--muted); margin: 0 0 16px; }}
.hero video, .hero img {{ display: block; width: 100%; height: auto; border: 1px solid var(--rule); border-radius: 8px; background: #000; }}
.hero figcaption {{ color: var(--muted); font-size: 13px; margin-top: 6px; }}
figure {{ margin: 0; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
.grid img {{ display: block; width: 100%; height: auto; border: 1px solid var(--rule); border-radius: 6px; }}
.grid figcaption {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
.split {{ display: grid; grid-template-columns: minmax(0, 1fr) 190px; gap: 20px; align-items: start; }}
.split img {{ width: 100%; height: auto; border: 1px solid var(--rule); border-radius: 10px; }}
@media (max-width: 640px) {{ .split {{ grid-template-columns: 1fr; }} .split img {{ max-width: 200px; }} }}
.need {{ background: var(--warn-bg); border: 1px solid var(--warn-rule); border-radius: 8px; padding: 12px 14px; margin: 18px 0; }}
.need h2 {{ margin-top: 0; }}
ul {{ padding-left: 20px; margin: 8px 0; }}
li {{ margin: 4px 0; }}
ul.tiles {{ list-style: none; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; }}
ul.tiles li {{ border: 1px solid var(--rule); border-radius: 8px; padding: 8px 10px; margin: 0; }}
ul.tiles b {{ display: block; font-size: 20px; font-variant-numeric: tabular-nums; }}
ul.tiles span {{ color: var(--muted); font-size: 13px; }}
.scroll {{ overflow-x: auto; border: 1px solid var(--rule); border-radius: 8px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ padding: 6px 9px; border-bottom: 1px solid var(--rule); text-align: left; vertical-align: top; }}
tr:last-child td {{ border-bottom: 0; }}
th {{ background: var(--soft); font-weight: 600; }}
td.num {{ white-space: nowrap; font-variant-numeric: tabular-nums; color: var(--muted); }}
code {{ font: 12.5px ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--soft); padding: 1px 4px; border-radius: 4px; overflow-wrap: anywhere; }}
td:first-child code {{ white-space: nowrap; overflow-wrap: normal; }}
.red {{ color: var(--bad); font-weight: 600; }} .green {{ color: var(--ok); font-weight: 600; }} .doc {{ color: var(--muted); }}
</style></head>
<body><main>
<h1>A table you can build by hand, with a way back from every edit</h1>
<p class="lede">data-ui on <code>main</code> @ <code>{head}</code>. Edit / View, delete, undo and redo, paste a block, columns from the header, filter by hand and start from nothing, plus the lost multi-source edit fixed. It is all on the gallery page below, ready to play with.</p>

<figure class="hero">
<video autoplay muted loop playsinline controls preload="auto" width="1024">
<source src="{data_uri(mp4, 'video/mp4')}" type="video/mp4">
<img src="{data_uri(gif, 'image/gif')}" alt="The hero as a GIF: turning on Edit, editing a cell, pasting a block, adding a column, filtering, deleting a row, then Undo.">
</video>
<figcaption>{seconds:.0f} seconds from the real page in headless Chromium, one take with the real mouse, keyboard and clipboard: turn on Edit, edit a cell, paste a block, add a column, filter by hand, delete a row, Undo. The red dot is the pointer. Made-up data.</figcaption>
</figure>

<h2>Open it</h2>
<p>The page to play with is the <code>notion-table</code> gallery case: <code>/gallery/notion-table/</code> on the docs site. It opens in Edit, on eight made-up rows with some cells blank. What you type stays in this browser. New blank table starts from nothing; Reset to the sample goes back.</p>

<h2>What you get</h2>
<div class="split"><div>
<ul>
<li><b>Edit / View.</b> <code>edit-toggle</code> adds a quiet switch, in both toolbars and in "…" when narrow. It opens in View, remembers per viewer, sits in the URL and fires an event. <code>editable</code> alone behaves as it did.</li>
<li><b>Delete.</b> Right-click, the menu key or the bulk bar. No dialog: a toast holds Undo. <code>acceptDelete</code> decides.</li>
<li><b>Undo and redo.</b> Ctrl/Cmd+Z, Shift for redo, through the same hooks with the old values. A refusal stays on the stack and says so. An open text editor keeps its own key.</li>
<li><b>Paste a block.</b> From Excel, Sheets or Notion: across and down, locked cells skipped and counted, one undo step. <code>acceptBatch</code> makes it one call.</li>
<li><b>Columns.</b> Add (seven types), rename, retype, hide, delete, from the header. A retype rewrites no stored value; what does not fit is drawn as written.</li>
<li><b>Filter by hand.</b> In View and Edit: a control fitted to the column, on the one filter and its pills. A column added a minute ago is in the list; a value typed a moment ago is a choice. A row edited out of the filter stays until the view refreshes, with a note and a Refresh.</li>
<li><b>From nothing.</b> One Name column and no rows is a live table: type rows in, add columns of every type, paste a block into the add row. It never reaches a dead state.</li>
<li><b>A lost edit, fixed, on every page.</b> An edit to a multi-source cell used to vanish while a host might save it. It is now refused before any hook, keeping the typed words.</li>
</ul>
</div><figure><img src="{phone}" alt="The column menu at 390 px in dark mode, inside the window."></figure></div>

<h2>The real page</h2>
<div class="grid">{figs}</div>

<h2>Proof</h2>
<p><b>{passed} of {len(results)}</b> browser checks pass, with real input, each expected value worked out from the fixture's JSON.</p>
<p><b>One golden moved, by decision.</b> A new gallery case changes <code>perf-oracle.golden.json</code> by construction, because the corpus digests every case the site lists. The coordinator took that decision, for that file only. It is regenerated from main's code, in its own commit with the proofs: this lane's code over the old gallery digests the old golden, and main's code and this lane's agree on the new one. <code>table-oracle.golden.json</code> and the §37 checks did not move.</p>
<ul class="tiles">{tiles}</ul>
<p><b>The ruler stayed frozen:</b> {"every commit that touches a check is its red commit and only adds lines; no green commit touches one." if not bad else "VIOLATED by " + html.escape(", ".join(bad))} Each check was run against the work in progress before its red commit, to shake out harness bugs; those fixes are listed in the hand-off.</p>
<div class="scroll"><table><thead><tr><th>Commit</th><th></th><th>What</th><th>Checks</th></tr></thead><tbody>{commit_rows}</tbody></table></div>

<h2>Open, and not done</h2>
<ul>
<li><b>Open decision:</b> should a hand edit of a multi-source value become a new top-ranked "hand" source? Today it is refused (PEP 0016).</li>
<li><b>What the checks missed, and the eyes caught:</b> three drawing bugs, found by looking at these frames with every check green: a frozen cell 32 px off, a 200 px checkbox column, stretched filter boxes. All three are fixed, each with a measured check.</li>
<li><b>Not built:</b> row drag-reorder, fill handle, formulas, relations, comments, real-time multi-user.</li>
<li><b>Not verified:</b> a clipboard from real Excel, Sheets or Notion. The checks write the formats those apps are documented to use; no real app ran here. Nor a Mac's Cmd key: it is a simulated Meta key in Chromium on Linux.</li>
</ul>
</main></body></html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    size = OUT.stat().st_size
    print(f"wrote {OUT} ({size / 1e6:.2f} MB)")
    if size > LIMIT:
        sys.exit(f"over the {LIMIT / 1e6:.1f} MB limit")
    if bad:
        sys.exit(f"the ruler moved: {bad}")


main()
