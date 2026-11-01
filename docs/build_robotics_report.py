"""Builds the PEP 0010 review report: ~/data-ui/reports/media/robotics-pep0010-2026-10-29.html.

    python3 docs/build_robotics_report.py

One self-contained page: every image is a WebP data URI (downscaled and cropped here with Pillow), the hero is an
H.264 mp4 data URI with a GIF inside it as the fallback, and the CSS and the few lines of JS are inline. It opens from
disk with no server or network. It lives in reports/media/ (gitignored) because it inlines media.

Reads only measured inputs, never the code under test:
- the lanes' screenshots and check JSONs under ~/data-ui/reports/media/robotics-*/ and the kit-gaps and
  add-to-dash worktrees' reports/media/;
- the mocks (reports/media/robotics-plan/, copies of docs/peps/0010-robotics-playback/*.png);
- the hero (reports/media/robotics-pep0010/hero.mp4, hero.gif, marks.json), recorded by docs/capture_robotics_hero.py;
- the orchestrator's merged-tree run (reports/media/robotics-pep0010/evidence/merged/: summary.txt and each suite's
  check JSON at 6aeab42) and the lanes' handoffs (evidence/handoffs/);
- the full `npm test` log at 006e9d5 (FULL_LOG below): re-run this script after it finishes and the scoreboard's last
  column fills in by itself;
- git, in this worktree.
"""

import base64
import html
import io
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
MAIN = Path("~/data-ui")
MEDIA = MAIN / "reports" / "media"
OUT = MEDIA / "robotics-pep0010-2026-10-29.html"
HERO = MEDIA / "robotics-pep0010"
EVID = HERO / "evidence"
KIT = MAIN / ".wt" / "kit-gaps" / "reports" / "media" / "kit-gaps"
A2D = MAIN / ".wt" / "add-to-dash" / "reports" / "media"
# WHY two places: the run writes into the orchestrator's session scratchpad, which is swept; a finished log is copied
# beside the report's evidence, and the copy wins once it exists
FULL_LOG_SCRATCH = Path("/tmp/claude-1000/-home-bam-zach-brain--claude-worktrees-data-ui-agent-design-9654e7/"
                        "47a5f03e-dbe6-493a-a090-9ff3191a218f/scratchpad/packet-006e9d5.log")
FULL_LOG_COPY = EVID / "full" / "packet-006e9d5.log"
FULL_LOG = FULL_LOG_COPY if FULL_LOG_COPY.exists() else FULL_LOG_SCRATCH
BASE, TIP, MERGED = "56e08be", "006e9d5", "6aeab42"
e = html.escape
SIZES = {}  # name -> bytes inlined, for the size note


# ---------------------------------------------------------------------------------------------------------- sources
# WHY numbered as defined: the page cites a bare number right after each claim and lists them once at the bottom.
SOURCES = []


def src(key, label, where):
    SOURCES.append((key, label, where))


src("pep", "PEP 0010, §11 phases, §13 open questions, §15–§17 what P1a, P3 and P5 settled",
    f"{REPO}/docs/peps/0010-robotics-playback.md")
src("git", f"First-parent history of integrate/packet, {BASE}..{TIP}",
    f"git -C {REPO} log --first-parent --oneline {BASE}..{TIP}")
src("h-packet", "The packet integrator's handoff (dashboard-cards, legend-toggle, live merged onto main)",
    f"{EVID}/handoffs/packet.md")
src("h-reds", "The two reds after the packet merge, cleared (0fd6f9f home paths, d5971e8 docs-site check)",
    f"{EVID}/handoffs/reds.md")
src("h-p0", "P0 lane handoff", f"{EVID}/handoffs/p0.md")
src("j-p0", "P0 checks JSON (merged tree)", f"{EVID}/merged/p0-checks.json")
src("h-p1a", "P1a lane handoff (CONTRACT §32, the fixture, the link rule)", f"{EVID}/handoffs/p1a.md")
src("j-p1b", "P1b checks JSON", f"{MEDIA}/robotics-p1b/p1b-checks.json")
src("h-p1b", "P1b lane handoff", f"{EVID}/handoffs/p1b.md")
src("j-p1cd", "P1c and P1d checks JSONs (lane run, before the colour-spelling fix)",
    f"{MEDIA}/robotics-p1cd/p1c-checks.json, p1d-checks.json")
src("h-p1cd", "P1c + P1d lane handoff", f"{EVID}/handoffs/p1cd.md")
src("j-p4", "P4 checks JSON", f"{MEDIA}/robotics-p4/p4-checks.json")
src("h-p4", "P4 lane handoff", f"{EVID}/handoffs/p4.md")
src("j-p2", "P2 checks JSON", f"{MEDIA}/robotics-p2/p2-checks.json")
src("h-p2", "P2 lane handoff", f"{EVID}/handoffs/p2.md")
src("j-kit", "Kit-gaps checks JSON", f"{KIT}/kit-gaps-checks.json")
src("h-kit", "Kit-gaps lane handoff", f"{EVID}/handoffs/kitgaps.md")
src("j-p3", "P3 checks JSON", f"{MEDIA}/robotics-p3/p3-checks.json")
src("h-p3", "P3 lane handoff; decision record PEP 0013", f"{EVID}/handoffs/p3.md, {REPO}/docs/peps/0013-navigation.md")
src("j-a2d", "Add-to-dashboard checks JSON", f"{A2D}/add-to-dashboard/add-to-dashboard-checks.json")
src("h-a2d", "Add-to-dashboard lane handoff; decision record PEP 0014",
    f"{EVID}/handoffs/addtodash.md, {REPO}/docs/peps/0014-add-to-dashboard.md")
src("j-p5", "P5 checks JSON (merged tree 6aeab42)", f"{EVID}/merged/p5-checks.json")
src("h-p5", "P5 lane handoff", f"{EVID}/handoffs/p5.md")
src("merged", f"The orchestrator's suite-by-suite run on the merged tree {MERGED} (26 browser suites, unit, Python)",
    f"{EVID}/merged/summary.txt, *-checks.json, unit_merged.log, py_merged.log, pyreader_merged.log")
src("full", f"The single full `npm test` (tools/test-all.mjs) at {TIP}", str(FULL_LOG))
src("edits", "The orchestrator's edits to frozen checks", f"git -C {REPO} show 45c87d1 4fb896f 006e9d5 d5971e8")
src("golden", "perf-oracle golden and its derivation notes (_home_paths, _p3_navigation, _p5_gates)",
    f"{REPO}/tests/unit/perf-oracle.golden.json; git show 3b42815 36b707b 412244e d9115cf")
src("table", "Table-oracle golden, derived from the code before (P0 lane)",
    f"git -C {REPO} show 4a58f07; {REPO}/docs/table_oracle_p0_derivation.py")
src("hero", "The hero recording: script, step marks, encode commands",
    f"{REPO}/docs/capture_robotics_hero.py, {HERO}/marks.json")
src("objdb", "ObjectDB branches against main (git merge-base, rev-list)",
    "git -C ~/data-ui branch -v; try/objectdb-kit, lane/object-db, lane/collection")
src("pw", "The shared Playwright cache (only chromium-1248 and older; the venv's Playwright wants 1243)",
    "ls ~/.cache/ms-playwright; the add-to-dashboard handoff's browser note")
src("mocks", "PEP 0010 mocks (proposals, matplotlib)", f"{MEDIA}/robotics-plan/*.png")
NUM = {k: i + 1 for i, (k, _, _) in enumerate(SOURCES)}


def c(*keys):
    """A citation: bare numbers right after the claim, comma-joined."""
    return '<sup class="c">' + ",".join(f'<a href="#s{NUM[k]}">{NUM[k]}</a>' for k in keys) + "</sup>"


# ---------------------------------------------------------------------------------------------------------- media
def webp(path, name, *, width=1200, crop=None, q=58):
    """The image at `path`, cropped (source px) and downscaled, as a WebP data URI."""
    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop(crop)
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=q, method=6)
    data = buf.getvalue()
    SIZES[name] = len(data)
    return f"data:image/webp;base64,{base64.b64encode(data).decode()}", im.width, im.height


def fig(path, alt, caption, *, width=1200, crop=None, q=58, cls=""):
    if not Path(path).exists():
        return f'<figure class="missing">missing: {e(str(path))}</figure>'
    uri, w, h = webp(path, Path(path).name + str(crop or ""), width=width, crop=crop, q=q)
    return (f'<figure class="{cls}"><button class="zoom" type="button" aria-label="Enlarge: {e(alt)}">'
            f'<img src="{uri}" width="{w}" height="{h}" alt="{e(alt)}" decoding="async"></button>'
            f"<figcaption>{caption}</figcaption></figure>")


def data_uri(path, mime):
    b = Path(path).read_bytes()
    SIZES[Path(path).name] = len(b)
    return f"data:{mime};base64,{base64.b64encode(b).decode()}"


# ---------------------------------------------------------------------------------------------------------- tests
def merged_summary():
    """name -> (exit, 'n/m') from the orchestrator's merged-tree run."""
    out = {}
    p = EVID / "merged" / "summary.txt"
    for line in p.read_text().splitlines():
        m = re.match(r"(\S+) exit=(\d+) \d+s :: (\d+)/(\d+)", line)
        if m:
            out[m.group(1)] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    return out


def unit_counts(text):
    g = lambda k: int(m.group(1)) if (m := re.search(rf"^# {k} (\d+)$", text, re.M)) else None  # noqa: E731
    return {"tests": g("tests"), "pass": g("pass"), "fail": g("fail"), "skipped": g("skipped")}


def py_counts(text):
    m = re.search(r"Ran (\d+) tests?", text)
    return (int(m.group(1)) if m else None, bool(re.search(r"^OK", text, re.M)))


# test-all step names (tools/test-all.mjs) -> the merged run's names
STEP = {
    "P0 checks": "p0", "P1b checks": "p1b", "P1c checks": "p1c", "P1d checks": "p1d", "P2 checks": "p2",
    "P3 checks": "p3", "P4 checks": "p4", "kit gaps checks": "kit_gaps", "add-to-dashboard checks": "add_to_dashboard",
    "P5 checks": "p5", "browser checks": "checks", "docs-site checks": "site_docs", "gallery checks": "gallery",
    "legend checks": "legend", "live checks": "live", "table oracle": "table_oracle", "frame checks": "frame",
    "chrome checks": "chrome", "lifecycle checks": "lifecycle", "perf-views checks": "perf_views",
    "perf-core checks": "perf_core", "perf-map checks": "perf_map", "toolbar polish checks": "toolbar_polish",
    "sources checks": "sources", "lineage fit checks": "lineage_fit", "rail checks": "rail",
}


def full_run():
    """The full npm test log: {'finished', 'at', 'steps': {step: text}, 'summary': {step: 'ok'|'FAIL ...'}}."""
    if not FULL_LOG.exists():
        return {"exists": False}
    text = FULL_LOG.read_text(errors="replace")
    parts = re.split(r"^== (.+?)(?::.*)?$", text, flags=re.M)
    steps = {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}
    summary = {}
    if "summary" in steps:
        for line in steps["summary"].splitlines():
            m = re.match(r"(ok  |FAIL|skip) (.+?): (.*)$", line)
            if m:
                summary[m.group(2)] = (m.group(1).strip(), m.group(3))
    names = list(steps)
    at = names[-1] if names else None
    mtime = datetime.fromtimestamp(FULL_LOG.stat().st_mtime).strftime("%H:%M")
    return {"exists": True, "finished": bool(summary), "at": at, "mtime": mtime, "steps": steps, "summary": summary}


def step_count(txt):
    """'n/m' from a browser suite's own last count line."""
    ms = re.findall(r"^(\d+)/(\d+) [^\n]*pass", txt, re.M)
    return (int(ms[-1][0]), int(ms[-1][1])) if ms else None


def lane_counts():
    def n(path):
        d = json.loads(Path(path).read_text())
        rows = d["checks"] if isinstance(d, dict) else d
        return sum(1 for r in rows if r.get("ok")), len(rows)
    return {
        "p0": (n(MAIN / ".wt/p0-blockers/reports/media/p0/p0-checks.json"), "lane tip 7996720"),
        "p1b": (n(MEDIA / "robotics-p1b/p1b-checks.json"), "lane tip 47785cb"),
        "p1c": (n(MEDIA / "robotics-p1cd/p1c-checks.json"), "lane tip bb2c692, before 45c87d1"),
        "p1d": (n(MEDIA / "robotics-p1cd/p1d-checks.json"), "lane tip bb2c692"),
        "p2": (n(MEDIA / "robotics-p2/p2-checks.json"), "lane tip 4726d83"),
        "p4": (n(MEDIA / "robotics-p4/p4-checks.json"), "lane tip 778fac8"),
        "kit_gaps": (n(KIT / "kit-gaps-checks.json"), "after 4fb896f's check fixes"),
        "p3": (n(MEDIA / "robotics-p3/p3-checks.json"), "lane tip f8bcd6e"),
        "add_to_dashboard": (n(A2D / "add-to-dashboard/add-to-dashboard-checks.json"), "lane tip 3413ea1"),
    }


def scoreboard():
    merged = merged_summary()
    full = full_run()
    lanes = lane_counts()
    um = unit_counts((EVID / "merged" / "unit_merged.log").read_text())
    pym = py_counts((EVID / "merged" / "py_merged.log").read_text())
    prm = py_counts((EVID / "merged" / "pyreader_merged.log").read_text())

    def full_cell(step, kind="browser"):
        if not full.get("exists"):
            return '<td class="pend">no log</td>'
        txt = full["steps"].get(step)
        verdict = full["summary"].get(step)
        if txt is None:
            return '<td class="pend">pending</td>'
        if kind == "unit":
            u = unit_counts(txt)
            if u["tests"] is None:
                return '<td class="pend">running</td>'
            cls = "ok" if u["fail"] == 0 else "bad"
            return f'<td class="{cls}">{u["pass"]}/{u["tests"]} <span class="sub">{u["skipped"]} skipped</span></td>'
        if kind == "py":
            n, ok = py_counts(txt)
            if n is None:
                return '<td class="pend">running</td>'
            return f'<td class="{"ok" if ok else "bad"}">{n} {"OK" if ok else "FAIL"}</td>'
        cnt = step_count(txt)
        if cnt is None:
            return '<td class="pend">running</td>' if not full["finished"] else f'<td class="bad">{e(str(verdict))}</td>'
        cls = "ok" if cnt[0] == cnt[1] else "bad"
        return f'<td class="{cls}">{cnt[0]}/{cnt[1]}</td>'

    def mcell(name):
        if name not in merged:
            return '<td class="pend">—</td>'
        ex, a, b = merged[name]
        return f'<td class="{"ok" if a == b else "bad"}">{a}/{b}</td>'

    def lcell(name):
        if name not in lanes:
            return '<td class="na">—</td>'
        (a, b), note = lanes[name]
        return f'<td class="{"ok" if a == b else "bad"}">{a}/{b} <span class="sub">{e(note)}</span></td>'

    robotics = [("P0 blockers", "P0 checks"), ("P1b scene3d + trajectory3d", "P1b checks"),
                ("P1c templates", "P1c checks"), ("P1d compare", "P1d checks"), ("P2 coverage", "P2 checks"),
                ("P4 driver, camera, gripper", "P4 checks"), ("Kit gaps", "kit gaps checks"),
                ("P3 navigation", "P3 checks"), ("Add to dashboard", "add-to-dashboard checks"),
                ("P5 gates", "P5 checks")]
    rest = [("Every gallery case (checks.py)", "browser checks"), ("Docs site", "docs-site checks"),
            ("Gallery index", "gallery checks"), ("Legend toggle", "legend checks"), ("Live", "live checks"),
            ("Table oracle", "table oracle"), ("Frame", "frame checks"), ("Chrome", "chrome checks"),
            ("Lifecycle", "lifecycle checks"), ("Perf: views", "perf-views checks"), ("Perf: core", "perf-core checks"),
            ("Perf: map", "perf-map checks"), ("Toolbar polish", "toolbar polish checks"), ("Sources", "sources checks"),
            ("Lineage fit", "lineage fit checks"), ("Rail", "rail checks")]
    rows = []
    rows.append('<tr class="grp"><th colspan="4">Unit and Python</th></tr>')
    rows.append(f'<tr><th>node --test (unit)</th><td class="na">—</td><td class="ok">{um["pass"]}/{um["tests"]} '
                f'<span class="sub">{um["skipped"]} skipped</span></td>{full_cell("unit (node --test)", "unit")}</tr>')
    rows.append(f'<tr><th>Python checker</th><td class="na">—</td><td class="ok">{pym[0]} OK</td>'
                f'{full_cell("python checker", "py")}</tr>')
    rows.append(f'<tr><th>Python .base reader</th><td class="na">—</td><td class="ok">{prm[0]} OK</td>'
                f'{full_cell("python .base reader", "py")}</tr>')
    rows.append('<tr class="grp"><th colspan="4">PEP 0010 and Add to dashboard suites</th></tr>')
    for label, step in robotics:
        rows.append(f"<tr><th>{e(label)}</th>{lcell(STEP[step])}{mcell(STEP[step])}{full_cell(step)}</tr>")
    rows.append('<tr class="grp"><th colspan="4">Every other browser suite</th></tr>')
    for label, step in rest:
        rows.append(f'<tr><th>{e(label)}</th><td class="na">—</td>{mcell(STEP[step])}{full_cell(step)}</tr>')
    tot = sum(b for _, _, b in merged.values())
    passed = sum(a for _, a, _ in merged.values())
    if not full.get("exists"):
        fstate = "full run: no log found"
    elif full["finished"]:
        fails = [k for k, (v, _) in full["summary"].items() if v == "FAIL"]
        fstate = ("full run finished: every step ok" if not fails else
                  f"full run finished: {len(fails)} step(s) FAIL ({e(', '.join(fails))})")
    else:
        fstate = f"full run pending (at “{e(full['at'])}” when this page was built, log last written {full['mtime']})"
    if full.get("finished"):
        counts = [step_count(full["steps"].get(st, "")) for st in STEP]
        full["browser"] = (sum(a for a, _ in filter(None, counts)), sum(b for _, b in filter(None, counts)))
        full["unit"] = unit_counts(full["steps"].get("unit (node --test)", ""))
        full["py"] = (py_counts(full["steps"].get("python checker", ""))[0] or 0) + (py_counts(full["steps"].get("python .base reader", ""))[0] or 0)
    return "\n".join(rows), passed, tot, len(merged), fstate, full


# ---------------------------------------------------------------------------------------------------------- page
CSS = r"""
:root{--bg:#f7f7f5;--card:#fff;--fg:#1c1c1e;--muted:#65656b;--line:#e3e3df;--chip:#efefec;--accent:#2a78d6;
--good:#17804f;--good-bg:#e5f4ec;--bad:#b4134f;--bad-bg:#fbe7ee;--warn:#9a6a08;--warn-bg:#fbf1dc;--code:#f1f1ee;
color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#121214;--card:#1a1a1d;--fg:#ececef;--muted:#9c9ca4;--line:#2b2b30;
--chip:#232328;--accent:#6aa6ee;--good:#4cc28a;--good-bg:#173126;--bad:#ef6f98;--bad-bg:#3a1a26;--warn:#e0b04f;
--warn-bg:#352a12;--code:#202024;color-scheme:dark}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1120px;margin:0 auto;padding:28px 32px 64px}
@media (max-width:700px){main{padding:18px 16px 48px}}
h1{font-size:30px;line-height:1.15;margin:4px 0 14px;letter-spacing:-.01em}
h2{font-size:21px;margin:44px 0 6px;letter-spacing:-.005em}
h3{font-size:17px;margin:0}
p{margin:8px 0}
a{color:var(--accent)}
code{font:12.5px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--code);padding:1px 5px;border-radius:4px;overflow-wrap:anywhere}
pre{font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--code);padding:12px 14px;border-radius:8px;overflow:auto;margin:10px 0}
.eyebrow{color:var(--muted);font-size:13px;letter-spacing:.02em}
.verdict{font-size:18px;line-height:1.45;font-weight:600;margin:0 0 6px}
.qual{color:var(--muted);margin:0 0 16px}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:18px 0 6px}
@media (max-width:820px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.stat b{display:block;font-size:22px;line-height:1.2;font-variant-numeric:tabular-nums}
.stat span{color:var(--muted);font-size:13px}
nav.toc{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:14px;margin:14px 0 0;padding:10px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
nav.toc a{text-decoration:none}
.lede{color:var(--muted);margin:0 0 14px}
.hero{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.hero video,.hero img{display:block;width:100%;max-width:100%;height:auto;border-radius:6px;background:#000}
.chapters{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 2px}
.chapters button{font:inherit;font-size:13px;background:var(--chip);color:var(--fg);border:1px solid var(--line);border-radius:999px;padding:3px 10px;cursor:pointer}
.chapters button b{font-variant-numeric:tabular-nums;color:var(--muted);font-weight:500;margin-right:4px}
.hero .note{font-size:13px;color:var(--muted);margin:8px 2px 2px}
.phase{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:14px 0}
@media (max-width:700px){.phase{padding:14px}}
.phase header{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 10px;margin-bottom:6px}
.tag{font:600 12px/1 ui-monospace,Menlo,monospace;background:var(--chip);border:1px solid var(--line);border-radius:6px;padding:4px 7px}
.meta{color:var(--muted);font-size:13px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:6px 28px}
@media (max-width:820px){.cols{grid-template-columns:1fr}}
.cols h4{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:10px 0 2px}
ul{margin:4px 0;padding-left:20px}
li{margin:3px 0}
.num{font-variant-numeric:tabular-nums}
.figs{display:grid;gap:12px;margin-top:12px}
.figs.two{grid-template-columns:1fr 1fr}
.figs.narrow{max-width:760px}
.figs.three{grid-template-columns:repeat(3,1fr)}
@media (max-width:820px){.figs.two,.figs.three{grid-template-columns:1fr}}
figure{margin:0;min-width:0}
.figs>*,.cols>*,.stats>*,.dec>*{min-width:0}
figure .zoom{display:block;width:100%;padding:0;border:1px solid var(--line);border-radius:8px;background:var(--bg);cursor:zoom-in;overflow:hidden}
figure img{display:block;width:100%;height:auto}
figcaption{font-size:13px;color:var(--muted);margin-top:5px}
.pill{display:inline-block;font-size:12px;border-radius:999px;padding:1px 8px;font-weight:600}
.pill.ok{background:var(--good-bg);color:var(--good)}
.pill.bad{background:var(--bad-bg);color:var(--bad)}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
.tablewrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:14px;min-width:620px}
th,td{text-align:left;padding:7px 12px;border-bottom:1px solid var(--line);vertical-align:top}
thead th{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600}
tbody th{font-weight:500}
tr.grp th{background:var(--chip);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
td.ok{color:var(--good);font-variant-numeric:tabular-nums;font-weight:600}
td.bad{color:var(--bad);font-variant-numeric:tabular-nums;font-weight:600}
td.pend{color:var(--warn)}
td.na{color:var(--muted)}
td .sub{color:var(--muted);font-weight:400;font-size:12px}
.edits li{margin:8px 0}
.dec{display:grid;gap:12px}
.decision{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px}
.decision h3{margin-bottom:4px}
.decision dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 12px;margin:8px 0 0}
@media (max-width:600px){.decision dl{grid-template-columns:1fr}}
.decision dt{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);padding-top:2px}
.decision dd{margin:0}
details.left{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 14px;margin:8px 0}
details.left summary{cursor:pointer;font-weight:600}
details.left summary span{font-weight:400;color:var(--muted)}
sup.c{font-size:10.5px;line-height:0;margin-left:1px;color:var(--muted)}
sup.c a{color:var(--muted);text-decoration:none}
sup.c a:hover{color:var(--accent)}
ol.sources{font-size:13px;color:var(--muted);padding-left:26px}
ol.sources li{margin:4px 0;overflow-wrap:anywhere}
ol.sources b{color:var(--fg);font-weight:500}
ol.sources li:target{background:var(--warn-bg)}
.missing{padding:20px;border:1px dashed var(--bad);color:var(--bad)}
dialog{border:0;padding:0;background:transparent;max-width:96vw;max-height:94vh}
dialog::backdrop{background:rgba(0,0,0,.75)}
dialog img{display:block;max-width:96vw;max-height:94vh;width:auto;height:auto;border-radius:6px;cursor:zoom-out}
footer{color:var(--muted);font-size:13px;margin-top:40px}
"""

JS = r"""
const dlg=document.getElementById('zoom'),big=dlg.querySelector('img');
document.addEventListener('click',(ev)=>{const b=ev.target.closest('button.zoom');if(b){const i=b.querySelector('img');big.src=i.src;big.alt=i.alt;dlg.showModal();}});
dlg.addEventListener('click',()=>dlg.close());
const v=document.getElementById('hero');
document.querySelectorAll('[data-seek]').forEach((b)=>b.addEventListener('click',()=>{if(!v||!v.currentTime&&v.currentTime!==0)return;v.currentTime=+b.dataset.seek;v.play();}));
"""


def build():
    rows, passed, total, nsuites, fstate, full = scoreboard()
    full_done = full.get("exists") and full.get("finished")
    full_fails = [k for k, (v, _) in full.get("summary", {}).items() if v == "FAIL"] if full_done else []
    first_parent = subprocess.run(["git", "-C", str(REPO), "log", "--first-parent", "--format=%h %s",
                                   f"{BASE}..{TIP}"], capture_output=True, text=True).stdout.strip().splitlines()
    marks = json.loads((HERO / "marks.json").read_text())
    mp4 = data_uri(HERO / "hero.mp4", "video/mp4")
    gif = data_uri(HERO / "hero.gif", "image/gif")
    M = MEDIA
    # output-timeline chapter starts: the take is trimmed to [4.1, 21.0] + [25.1, 28.55] (docs/capture_robotics_hero.py)
    mk = marks["marks"]
    t = lambda s: max(0.0, round(s - 4.1, 1))  # noqa: E731
    chapters = [(0.0, "1 · Play the clock"), (t(mk["cube +Z"]) - 0.4, "2 · View cube +Z → top, orthographic"),
                (t(mk["cube settled"]) + 0.9, "3 · Decay 0.6 → 0.2 → 3 s"),
                (t(mk["decay 3"]) + 1.6, "4 · Compare arrows ×1 → ×30"),
                (round(21.0 - 4.1, 1), "5 · Servo Playback + Gates: a gate cell opens its peek")]

    if full_done and not full_fails:
        fb, fu = full["browser"], full["unit"]
        fline = (f"That run: {fb[0]:,}/{fb[1]:,} browser checks, {fu['pass']}/{fu['tests']} unit tests "
                 f"({fu['skipped']} skipped), {full['py']} Python tests, the Rerun exports and the build{c('full')}.")
    elif full_done:
        fline = (f"The single full <code>npm test</code> at {TIP} finished with {len(full_fails)} step(s) red: "
                 f"{e(', '.join(full_fails))}{c('full')}.")
    else:
        fline = (f"The single full <code>npm test</code> at {TIP} is still running: <b>full run pending</b>{c('full')}; "
                 f"the suite-by-suite run on the merged tree is the evidence until it lands.")

    full_green = bool(full_done and not full_fails)
    miss = (f"The merged tree before it ({MERGED}) missed one check, P5's camera evidence landing: the frozen check read "
            f"the camera's descriptor file as an empty table, and <code>{TIP}</code> fixes the check, not the "
            f"code{c('edits', 'h-p5')}.")
    if full_green:
        verdict_mid = f"One full <code>npm test</code> at {TIP} is green, every step."
        qual_mid = f"{fline} {miss}"
    else:
        verdict_mid = (f"{passed:,} of {total:,} browser checks pass on the merged tree, and the one miss was a wrong "
                       f"check, now fixed.")
        qual_mid = f"{miss} {fline}"
    H = []
    H.append(f"""<header>
<div class="eyebrow">data-ui · PEP 0010 review · 2026-10-29 · built {datetime.now().strftime('%H:%M')}</div>
<h1>Robotics playback, built: five part dashboards, compare, coverage, navigation and gates</h1>
<p class="verdict">PEP 0010 is built end to end: P0 through P5, the kit gaps the templates found, and Add to dashboard.
{verdict_mid} On <code>integrate/packet</code> @ <code>{TIP}</code>, not merged to main
(<code>{BASE}</code>).{c('git', 'full' if full_green else 'merged')}</p>
<p class="qual">{qual_mid} The arm and gripper data are stand-ins, labelled in every row; servo, driver, camera and
deployments are real rack data{c('h-p1cd', 'h-p4', 'h-p5')}.</p>
<div class="stats">
{(f'<div class="stat"><b>{full["browser"][0]:,} / {full["browser"][1]:,}</b><span>browser checks green in one full run at {TIP}, {nsuites} suites{c("full")}</span></div>') if full_done and not full_fails else (f'<div class="stat"><b>{passed:,} / {total:,}</b><span>browser checks green on the merged tree, {nsuites} suites{c("merged")}</span></div>')}
<div class="stat"><b>12</b><span>new gallery cases: 5 templates, a deployments page, 6 Playback + Gates twins{c('git')}</span></div>
<div class="stat"><b>§32–§35</b><span>four CONTRACT sections, PEPs 0013 and 0014 as decision records{c('pep', 'h-p3', 'h-a2d')}</span></div>
<div class="stat"><b>6</b><span>decisions for you, each with a default if you say nothing</span></div>
</div>
<nav class="toc"><a href="#hero-sec">Hero</a><a href="#phases">Per phase</a><a href="#tests">Scoreboard</a>
<a href="#edits">Edits to frozen checks</a><a href="#decisions">Decisions</a><a href="#left">Left and not done</a>
<a href="#sources">Sources</a></nav>
</header>""")

    # ---------------------------------------------------------------- hero
    chap = "".join(f'<button type="button" data-seek="{s:.1f}"><b>{s:04.1f}s</b>{e(lbl)}</button>' for s, lbl in chapters)
    H.append(f"""<section id="hero-sec"><h2>The built thing, running</h2>
<p class="lede">A real recording of the site built at <code>{TIP}</code>: the Robot arm template, then the Servo
"Playback + Gates" twin. Click a chapter to jump.{c('hero')}</p>
<div class="hero">
<video id="hero" autoplay muted loop playsinline controls preload="auto" width="1000" height="800">
<source src="{mp4}" type="video/mp4">
<img src="{gif}" width="440" height="352" alt="The hero recording as a GIF: the arm template playing, the view cube, decay, compare arrows, then a gate cell opening its peek">
</video>
<div class="chapters">{chap}</div>
<p class="note">Playwright's own screencast of headless Chromium on <code>dist/site</code> (the full test run's build of
{TIP}, served from a copy). Two trims and a crop, no speed change, nothing drawn on top: the red ring is a pointer the
script adds so the clicks are visible. The decay control is a typed field in seconds, so the take types 0.2 and 3;
there is no drag handle. Measured during the take: after the cube click the camera is orthographic
(<code>proj[15] = {marks['ortho']['proj15']}</code>); with decay 3 and ×30 the card reads
“{e(marks['arm']['label'])}” and draws {marks['arm']['arrows']} arrows in the window; the gate click opened the peek on
“{e(marks['cell'])}”.{c('hero')}</p>
</div></section>""")

    # ---------------------------------------------------------------- phases
    P = []

    def phase(pid, tag, title, meta, adds, measured, figs="", figcls="two"):
        groups = figs if isinstance(figs, list) else ([(figs, figcls)] if figs else [])
        figs_html = "".join(f'<div class="figs {cls}">{html_}</div>' for html_, cls in groups)
        return (f'<article class="phase" id="{pid}"><header><span class="tag">{tag}</span><h3>{title}</h3>'
                f'<span class="meta">{meta}</span></header><div class="cols"><div><h4>What it adds</h4><ul>'
                + "".join(f"<li>{a}</li>" for a in adds) + '</ul></div><div><h4>Measured</h4><ul class="num">'
                + "".join(f"<li>{m}</li>" for m in measured) + f"</ul></div></div>{figs_html}</article>")

    P.append(phase("packet", "Packet", "The merge packet: dashboard cards, legend toggle, live",
                   "0930c4e · 5ba3053 · 55ae071 · CONTRACT §25, §31, §26",
                   [f"The card catalog on one clock with one driver (PEP 0005, PEP 0008){c('h-packet')}.",
                    f"Every chart's legend toggles its series: click hides, double-click or Alt + click isolates, the hidden set rides in the URL{c('h-packet')}.",
                    f"Live data and rewind: follow, rewind, back to live (PEP 0012){c('h-packet')}.",
                    f"A conflict git did not report: a <code>#t=102.5</code> link on a live clock kept following live. 8eb8480 makes a link to a moment or range pause there, after a red test (6e59822, 0/4 → 4/4){c('h-packet', 'git')}."],
                   [f"Legend 83/83, live 52/52, every gallery case 1201/1201 at the packet tip{c('h-packet')}.",
                    f"Two reds after merge 1, both cleared: published case files carried home paths (0fd6f9f rewrites them to <code>~/</code>), and the docs-site check counted a panel as drawn only at ≥ 100 px (d5971e8){c('h-reds')}."],
                   fig(A2D / "legend/chart-one-hidden.png", "A chart with one series hidden by its legend",
                       f"Legend toggle: one series hidden from the legend, Reset beside it.{c('h-packet')}", width=900)
                   + fig(A2D / "live/live-following.png", "A live dashboard following the newest data",
                         f"Live: following, with the ● LIVE control on the playback bar.{c('h-packet')}", crop=(0, 0, 1280, 560), width=1000)))

    P.append(phase("p0", "P0", "Blockers sim2real hit", "dd53748 · gaps #1, #9, #13, #14 and the table's last row",
                   [f"The clock spans only the rows the filters leave{c('pep')}.",
                    f"A two-clause dataset filter still lists every device with counts; each rail gets its own radio group; a <code>src</code> set after load reloads the panels{c('h-p0')}.",
                    f"A table's scroll length is right from the start, so its last row is reachable{c('h-p0')}."],
                   [f"#1: picking the 4.518 s run spans the clock to [0, 4.518], not [0, 35.993]; the thumb at the run's middle sits at 299.39 px of 598.8 (want 299.39){c('j-p0')}.",
                    f"#9: the picker lists J3 elbow 94, J4 wrist 1 84, J1 74, J2 74 (was J3 alone){c('j-p0')}.",
                    f"#14: the default radio is drawn checked, centre pixel the accent (37, 99, 235){c('j-p0')}.",
                    f"Table: scrollHeight 3990 = header + 132 × 30 px before and after scrolling; the last row draws inside the box{c('j-p0')}.",
                    f"P0 checks 100/100{c('j-p0', 'merged')}."],
                   fig(A2D / "p0/rails-1280-light.png", "Two rails, each default drawn checked",
                       f"Two rails on one page, each with its own radio group and its default drawn checked.{c('j-p0')}",
                       crop=(0, 0, 1280, 440), width=1100), figcls=""))

    arm_yaml = """  - type: trajectory3d
    name: Path 3D
    from: poses
    trajectory3d:
      modes: { real: [line, frames-z], real B: [line], twin: [line], target: [line] }
      compare: { data: diff, pairs: [[real, target], [tuned, target]] }
      robots: { data: links, model: ../pid-tuning/media/ur5e_links.glb, series: { twin: { opacity: 0.5 } } }
      show: trail
      decay: 0.6"""
    P.append(phase("p1a", "P1a", "The contract barrier", "6f4a72e · CONTRACT §32 · gallery/robotics/",
                   [f"<code>scene3d</code> stage keys and seven primitives (points, lines, frames, arrows, arcs, meshes, boxes), <code>trajectory3d</code>, <code>voxels</code> reserved, <code>style.families</code>, layer datasets{c('h-p1a')}.",
                    f"The trajectory contract as rows and column names (gallery/robotics/CONTRACT.md and 13 schemas); data-ui imports no dataclass{c('h-p1a', 'pep')}.",
                    f"<code>difference(a, b)</code> defined exactly, with a fixture both the Python library and the gallery checks read{c('pep')}.",
                    f"Changed PEP 0004's link rule: every direct link between two datasets now filters, ANDed (decision 2){c('pep', 'h-p1a')}."],
                   [f"Fixture: 640 + 640 input rows → 152 pose rows and 304 sample rows, seeded and deterministic{c('h-p1a')}.",
                    f"An independent stdlib <code>difference</code> reproduces every row; nine plausible wrong ones each fail it{c('h-p1a', 'pep')}.",
                    f"traj_compare's interpolation passes once kept to b's span; as landed it writes 18 extrapolated rows, the one change the trajectory library needs{c('pep')}.",
                    f"33 new unit tests; PEP 0004's six dashboard cases 155/155{c('h-p1a')}."],
                   f'<figure><pre>{e(arm_yaml)}</pre><figcaption>The Robot arm template\'s 3D view as the contract spells it (gallery/examples/robotics-arm/views.base).</figcaption></figure>',
                   figcls=""))

    P.append(phase("p1b", "P1b", "Layer 1 primitives and the trajectory viewer", "a0b229b · packages/views/scene3d/",
                   [f"The stage and Layer 1 primitives, drawn from any columns{c('h-p1b')}.",
                    f"<code>trajectory3d</code>: view cube (three's ViewHelper look), projections, decay in seconds, display modes (Line, Points, Frames, Z only), family colours, a meshed UR5e per series{c('h-p1b')}."],
                   [f"Cube +Z click: orthographic, 0.000° off −Z; <code>v=</code> holds <code>projection: top</code> across a reload{c('j-p1b')}.",
                    f"Equal scale: 100 mm on x and on y both 147.7556 px{c('j-p1b')}.",
                    f"Decay 0.5 at t = 3.0 draws exactly [2.5, 3.0]; a clock tick at 150,000 vertices costs 0.200 ms median (budget 2 ms) and rebuilds nothing{c('j-p1b')}.",
                    f"Hover marker 1e-5 px from the oracle's projection; 22 markers at density 20 on 564 samples{c('j-p1b')}.",
                    f"One WebGL context for two cards, two cubes and three robots. 142/142{c('j-p1b', 'merged')}."],
                   [(fig(M / "robotics-p1b/compare-arm-light.png", "Mock beside the built arm dashboard",
                         f"The arm: mock (left, matplotlib) beside the built dashboard (right).{c('mocks', 'h-p1b')}", width=1400), ""),
                    (fig(M / "robotics-p1b/compare-top-light.png", "Mock top view beside the built top view",
                         f"Top view: mock (left) and built (right), orthographic.{c('mocks', 'h-p1b')}", width=1062), "narrow")]))

    P.append(phase("p1cd", "P1c + P1d", "Servo and Robot arm templates, and compare", "8f77c1c · Examples → Robotics · Playback",
                   [f"<b>robotics-servo</b> on 40 real rack runs (13 of CAN 12, 27 of CAN 14) with twin replays; <b>robotics-arm</b> on the UR5e stand-in, labelled{c('h-p1cd')}.",
                    f"Compare: arrows a(t) → b(t) and Z-arcs from the difference rows; a display-only scale (×1 ×10 ×30 ×100) the card labels; EEF and joint error panels{c('h-p1cd')}.",
                    f"One shared <code>difference(a, b)</code> in gallery/robotics/difference.py feeds both templates{c('h-p1cd')}."],
                   [f"A run pick spans the clock to that run: [0, 11.6064], [0, 29.9978], [0, 2.5398] s on the servo; [0, 7.9] and [0, 7.88] on the arm{c('j-p1cd')}.",
                    f"Every arrow end 0.0 mm off the fixture (float32); Z-arc ends worst 0.00018°; at ×20 the length ratio is off by 1.2e-7{c('j-p1cd')}.",
                    f"The error panels equal <code>diff_*.json</code> exactly; hiding real on the rail removes its arrows from every panel{c('h-p1cd')}.",
                    f"P1c 61/61 (53/61 before the colour-spelling fix), P1d 51/51{c('merged', 'j-p1cd')}."],
                   [(fig(M / "robotics-p1cd/compare-servo-dark.png", "Servo mock beside the built Servo template",
                         f"Servo: mock (left) and built (right), dark.{c('mocks', 'h-p1cd')}", width=1400), ""),
                    (fig(M / "robotics-p1cd/fixture-compare-x20-light-1280.png", "Compare arrows at scale 20",
                         f"Compare on the fixture at ×20: every arrow 20× b − a, labelled on the card.{c('j-p1cd')}",
                         crop=(0, 0, 1248, 722), width=1000), "narrow")]))

    P.append(phase("p4", "P4", "BLDC driver, camera, arm + gripper", "73a1f04",
                   [f"<b>robotics-driver</b> on real CAN 12, 13, 14 driver logs (rack 10-23..25){c('h-p4')}.",
                    f"<b>robotics-camera</b> on two real RealSense cameras, six sessions; depth and hyperspectral panels say they are empty until captures exist{c('h-p4')}.",
                    f"<b>robotics-arm-gripper</b>: arm stand-in, gripper illustrative, labelled everywhere{c('h-p4')}."],
                   [f"i_q equals the npz: 138/138 points, worst 4.99e-5 A{c('j-p4')}.",
                    f"Event marks sit at their t within one frame{c('j-p4')}.",
                    f"Frame-interval histogram equals numpy over <code>hw_ms</code>: 13,006 of 13,006 in-range intervals; dropped frames per session 63/42/18/116/90/17 equal numpy{c('j-p4')}.",
                    f"150/150{c('j-p4', 'merged')}."],
                   [(fig(M / "robotics-plan/bldc-driver.png", "BLDC driver mock", f"BLDC driver: the mock.{c('mocks')}", width=900)
                     + fig(M / "robotics-p4/driver-dark-1280.png", "Built BLDC driver template",
                           f"BLDC driver: built, dark, real rack data.{c('h-p4')}", crop=(0, 0, 1232, 1180), width=900), "two"),
                    (fig(M / "robotics-plan/camera.png", "Camera mock", f"Camera: the mock.{c('mocks')}", width=900)
                     + fig(M / "robotics-p4/camera-light-1280.png", "Built camera template",
                           f"Camera: built. RGB clip on the clock, frame intervals, dropped frames per session; depth and hyperspectral empty and saying so.{c('h-p4')}",
                           crop=(0, 0, 1232, 1040), width=900), "two")]))

    P.append(phase("p2", "P2", "Coverage", "5b4e793",
                   [f"<code>voxels</code> with slices and a one-hue ramp; <code>opacity: auto</code> exactly 1/n per family; the workspace outline{c('h-p2')}.",
                    f"Rules and bands from a property; honest histograms (empty bins 0, no stale min or max){c('h-p2')}.",
                    f"Coverage panels in both templates; BAM Reach's map as voxels{c('h-p2')}."],
                   [f"137 runs draw 137 paths in one LineSegments2, 5 draw calls in all{c('j-p2')}.",
                    f"Each path's alpha reads back 0.0072993 = float32(1/137){c('j-p2')}.",
                    f"Voxel count, time and runs equal <code>numpy.histogramdd</code> on all 168 cells; the largest cell's pixel is the ramp end, ΔE 0.0{c('j-p2')}.",
                    f"Workspace outline within 0.809 px of the projected hull; a rail click at 144,644 rows redraws every coverage panel in 124.7–179.8 ms (budget 300){c('j-p2')}.",
                    f"Ceiling: 1/n vanishes in an 8-bit framebuffer above about 200 runs (decision 3). 131/131{c('h-p2', 'merged')}."],
                   fig(M / "robotics-p2/p2-robotics-arm-coverage-light-1280.png", "Arm coverage panels",
                       f"Arm coverage: every run at 1/n over the workspace, the reach map sliced, each joint's range.{c('h-p2')}",
                       crop=(0, 0, 1280, 880), width=1000)
                   + fig(M / "robotics-p2/p2-robotics-servo-coverage-light-1280.png", "Servo coverage panels",
                         f"Servo coverage: angle histogram, velocity box plots, phase space.{c('h-p2')}",
                         crop=(0, 0, 1280, 460), width=1000)))

    P.append(phase("kit", "Kit gaps", "Ten view gaps the template lanes found", "84d47c2",
                   [f"Aggregates stay right after a data swap (a Vega memo bug, fixed at data-ui's seam){c('h-kit')}.",
                    f"Annotations from data, with label collisions resolved; charts follow the clock with a playhead; <code>levels</code> shows a whole recording{c('h-kit')}.",
                    f"Transform-made fields pass both checkers; colour maps take <code>muted</code> and tokens; a <code>parent:</code> facet; media <code>empty:</code> text{c('h-kit')}."],
                   [f"0 stale results across 42 constructs × 4 swaps; 30/30 panel picks equal numpy{c('h-kit')}.",
                    f"The mode strip's playhead at t = 2.286 sits where its own x scale puts t (541.97 px, within 1 px){c('j-kit')}.",
                    f"<code>levels</code> on a recording shows 0..120 s, not the last 30 s{c('j-kit')}.",
                    f"Both checkers: 0 errors on all 54 gallery bases; the Driver facet lists CAN 12: 9, CAN 13: 9, CAN 14: 9 (was CAN 13: 1){c('h-kit')}.",
                    f"230/230 after three orchestrator check fixes{c('j-kit', 'edits')}."],
                   fig(KIT / "driver-marks-light-1280.png", "Fault and mode marks drawn from data",
                       f"Marks from <code>events.json</code> on the driver's i_q and v_bus.{c('h-kit')}", width=1000)
                   + fig(KIT / "levels-whole-light-1280.png", "Levels over a whole recording",
                         f"<code>levels</code> over a whole recording with a playhead.{c('h-kit')}", crop=(0, 0, 1248, 140), width=1000)))

    P.append(phase("p3", "P3", "Navigation", "7f0cefe · CONTRACT §33 · PEP 0013",
                   [f"A per-run dataset, <code>data: runs/{{run}}.json</code>, fetched when exactly one run is picked; \"Pick one run\" otherwise{c('h-p3')}.",
                    f"One-way links, <code>selected: first</code> presets, runs tables that pick on the rail, a pick as a history entry{c('h-p3')}.",
                    f"<b>robotics-deployments</b>: deployments → runs → one run, 24 real rack runs of Oct 28–29{c('h-p3')}."],
                   [f"One pick fetches exactly <code>runs/10-29~gates~36_warm_can13_ff~s08.json</code>; the clock spans [0, 5.4345]{c('j-p3')}.",
                    f"Two picks: \"Pick one run\" in all four per-run panels, 0 fetches{c('j-p3')}.",
                    f"history.length 2 → 3 → 4; Back and Forward restore the pick and t (2.173, 0, 3.55); no file fetched twice{c('j-p3')}.",
                    f"One-way: a Show pick leaves Station counts at S1 2, S2 2, S3 2. 98/98{c('j-p3', 'merged')}."],
                   fig(M / "robotics-p3/deployments-light-1280.png", "Deployments page with one run picked",
                       f"One run picked: its file loads, the clock spans it.{c('j-p3')}", width=800)
                   + fig(M / "robotics-p3/pick-one-light-1280.png", "Deployments page with two runs picked",
                         f"Two runs picked: every per-run panel says \"Pick one run\" and names both.{c('j-p3')}", width=800)))

    P.append(phase("a2d", "§34", "Add to dashboard", "0db2785, merged at 6aeab42 · CONTRACT §34 · PEP 0014",
                   [f"\"Add to dashboard…\" on every view, KPI card, legend series and peek field{c('h-a2d')}.",
                    f"The host saves the file (an event with <code>respondWith</code>); with no host the text goes to the clipboard{c('h-a2d')}.",
                    f"The panel is appended to the dashboard's text, insert-only, with dataset dedup and view renames; <code>hiddenSeries</code> and a per-panel <code>t</code>{c('h-a2d')}."],
                   [f"Round trip draws the same rows: 7 (r17 0.968 … r14 0.56), 12 under a selection, 63 for series J2{c('j-a2d')}.",
                    f"A KPI card reads 0.7638 against the file's mean 0.76375; the text keeps every byte apart from inserted lines{c('j-a2d', 'h-a2d')}.",
                    f"Cost: the core bundle grows 8.8 KB gzip (142.5 → 151.3 KB){c('h-a2d')}.",
                    f"70/70{c('j-a2d', 'merged')}."],
                   fig(A2D / "add-to-dashboard/panel-picker-light-1280.png", "Add to dashboard picker on a dashboard panel",
                       f"The picker on a panel's ⋯: an existing dashboard, a new one, or pinned at this moment.{c('h-a2d')}",
                       crop=(280, 640, 1262, 975), width=980)
                   + fig(A2D / "add-to-dashboard/round-trip-view.png", "The target dashboard after the add",
                         f"The target after an add: the new Runs panel at the bottom, the source's 7 rows in its order.{c('j-a2d')}",
                         crop=(0, 0, 1248, 700), width=980)))

    P.append(phase("p5", "P5", "Diagnostics and gates overlay", "6aeab42 + 006e9d5 · CONTRACT §35",
                   [f"A \"Playback + Gates\" twin of each template and the deployments page (6 cases), each its template's text plus the overlay{c('pep')}.",
                    f"Gate matrix, status cells from one status vocabulary in the core (RobotDx's order: not run ranks worse than warn), <code>limits: {{warn, error}}</code> bands per device, a KPI trend with a property target, a roll-up tree{c('pep', 'h-p5')}.",
                    f"The peek embeds the gate's evidence; a path overlay coloured by error with a tolerance tube; verdict voxels{c('h-p5')}.",
                    f"Gate rows come from RobotDx's diagnostics library over the archive: real for servo, driver, camera and deployment; stand-in for arm and gripper{c('pep')}."],
                   [f"Columns align, worst 0.000 px, over 32 matrix renders; all 2,292 cells carry a glyph and an accessible name{c('j-p5')}.",
                    f"A cell click opens the peek on that gate row, 7 of 7; bands sit within 1 px of each device's own limits, 10 of 10{c('j-p5')}.",
                    f"Stations × gates equals the gate file, 88 cells; the path overlay's 594 segments and the 156 verdict voxels sit on their ramps{c('j-p5')}.",
                    f"411/412 on the merged tree; the miss was the check reading the camera's descriptor file as empty (fixed in {TIP}){c('j-p5', 'edits')}."],
                   [(fig(M / "robotics-p5/servo-gates-peek-light-1280.png", "Servo gates twin with a gate peek open",
                         f"Servo twin: the Run checks matrix, and a cell's peek with its verdict, limit and the evidence chart.{c('h-p5')}",
                         crop=(0, 0, 1232, 1060), width=1100)
                     + fig(M / "robotics-p5/deployments-gates-matrix-light-1280.png", "Stations by gates matrix",
                           f"Deployment twin: Stations × gates from bam_rack_twin's acceptance file.{c('h-p5')}", width=956), ""),
                    (fig(M / "robotics-p5/arm-path-overlay.png", "Path error on the path",
                         f"Arm: path error on the path, ±10 mm tube (stand-in).{c('h-p5')}", crop=(0, 0, 473, 500), width=473)
                     + fig(M / "robotics-p5/arm-verdict-voxels.png", "Reach verdict voxels",
                           f"Arm: reach verdict voxels, ✕ at the bad end, ✓ at the good.{c('h-p5')}", width=472)
                     + fig(M / "robotics-p5/deployments-rollup.png", "Rack roll-up tree",
                           f"Deployment: the rack's roll-up, worst-of per node.{c('h-p5')}", width=392), "three")]))

    H.append('<section id="phases"><h2>Per phase</h2><p class="lede">Each lane merged into '
             f'<code>integrate/packet</code> in this order{c("git")}. Numbers are from the lane\'s check JSON unless '
             'marked; mock beside built where a comparison exists.</p>' + "".join(P) + "</section>")

    # ---------------------------------------------------------------- scoreboard
    H.append(f"""<section id="tests"><h2>Test scoreboard</h2>
<p class="lede">Three runs: each lane's own run at its tip, the orchestrator's suite-by-suite run on the merged tree
<code>{MERGED}</code>{c('merged')}, and one full <code>npm test</code> at <code>{TIP}</code>{c('full')}. Status of the last:
<b>{fstate}</b>.</p>
<div class="tablewrap"><table>
<thead><tr><th>Suite</th><th>Lane run</th><th>Merged tree {MERGED}</th><th>Full run {TIP}</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="lede" style="margin-top:8px">The merged run's P5 miss is the check fixed in {TIP}; the lane column's P1c
53/61 is the colour-spelling check before 45c87d1{c('edits')}. The P5 suite needs the rack archive
(<code>/archive/datasets/bam_rig</code>), as P2 and P4 do{c('h-p4')}.</p></section>""")

    # ---------------------------------------------------------------- edits to frozen checks
    edits = [
        ("45c87d1", "P1c colour spelling",
         f"<code>series_strokes()</code> compares hex to hex: Vega writes a resolved token as <code>rgb(42, 120, 214)</code>, the oracle is <code>#2a78d6</code>, the same colour. The 8 failures were that one spelling; P1c 53/61 → 61/61{c('edits', 'j-p1cd')}."),
        ("4fb896f", "Kit gaps: gap 5's line lookup",
         f"The check found the first <code>x2: {{ field: t_end }}</code> (layer 1, where t_end is made) instead of the swapped one; the checker's error was already on the right line{c('edits', 'h-kit')}."),
        ("4fb896f", "Kit gaps: repeated labels",
         f"The label rule failed any label drawn at one mark and hidden at another, unavoidable with 32 fault marks; now every drawn label must sit on a wanted mark with its text{c('edits', 'h-kit')}."),
        ("4fb896f", "Kit gaps: the driver fixture's second pick",
         f"The fixture now picks the newest run with both kinds of change; two-way links hide a run with none (P3's one-way links later made all 27 listable){c('edits', 'j-p3')}."),
        (TIP, "P5 descriptor path",
         f"<code>load_table</code> follows a descriptor's <code>path</code>: the camera's clock dataset is <code>samples.schema.json</code> naming <code>samples.csv</code>, which the frozen form read as an empty table, so the run's span came back null. P5 411/412 → expected 412/412{c('edits', 'h-p5')}."),
        ("d5971e8", "Docs-site panel check",
         f"A dashboard panel counts as drawn by its content, not a 100 px floor: the cards' 40 px playback bar and 84 px KPI card draw fine. 127/129 → 129/129{c('h-reds')}."),
        ("3b42815 · 36b707b · 412244e · d9115cf", "perf-oracle golden regenerations",
         f"Each derived from the kit before the change over the new gallery, per the golden's own rule (never from the code under test): <code>~/</code> paths in case data; the robotics-deployments case; its archive paths; the six gates twins. Each note shows the old kit over the old gallery reproduces the previous golden exactly{c('golden')}."),
        ("4a58f07", "Table-oracle golden (by the P0 lane)",
         f"79 of 110 entries, the table fix's two declared output changes, applied by spec to 8eb8480's build by <code>docs/table_oracle_p0_derivation.py</code>; the new code then matched all 122 views byte for byte{c('table')}."),
    ]
    H.append('<section id="edits"><h2>Edits to frozen checks</h2><p class="lede">Every checks file was committed red '
             'before its lane\'s code and left to the orchestrator. These are the edits made to them, one line each, '
             f'with why{c("edits", "git")}.</p><ul class="edits">'
             + "".join(f"<li><code>{e(sha)}</code> <b>{e(what)}.</b> {why}</li>" for sha, what, why in edits)
             + f"<li>Also, by lanes in their own commits: new cases added to the perf golden (06fb5eb, bb2c692, cd4eb5d, 778fac8, d66fbee, same derivation){c('golden')}, and the Add-to-dashboard lane moved <code>gallery/examples/toolbar-bar/checks.py</code> from 9 View-settings rows to 10 for its new row{c('h-a2d')}.</li></ul></section>")

    # ---------------------------------------------------------------- decisions
    decisions = [
        ("Merge <code>integrate/packet</code> into data-ui main",
         f"main can fast-forward from {BASE} to {TIP}: the packet is main plus these lanes, merged in order. It also changes every dashboard's Back and Forward (a pick is now a history entry) and grows the core by 8.8 KB gzip{c('git', 'h-p3', 'h-a2d')}.",
         (f"Fast-forward: the full run at {TIP} is green and nothing in it is half-built."
          if full_done and not full_fails else f"Fast-forward once the full run at {TIP} is green; nothing in it is half-built."),
         "Wait for your word. main stays at " + BASE + "; new lanes keep cutting from the packet."),
        ("The link rule: every link between two datasets ANDs",
         f"Before, only the first link between a pair carried. Under that rule the Servo template's Angle error panel showed every device's error under a device pick, and \"hide a series, lose its arrows\" could not pass. None of the six older gallery dashboards has two links between one pair{c('pep', 'h-p1a')}.",
         "Keep. It is what links already promised; one link per pair is unchanged.", "Keep."),
        ("Exactly 1/n opacity, with its ~200-run 8-bit ceiling",
         f"A path's alpha is exactly 1/n with no floor. In an 8-bit framebuffer a single path rounds away above about 200 runs: at 250 runs red and green are lost, at 1,000 (the rack) nothing draws{c('h-p2')}.",
         "Keep 1/n for honest overlap; use voxels with <code>value: runs</code> for whole racks. A float accumulation target is the alternative, not built.",
         "Keep; voxels <code>value: runs</code> for whole racks."),
        ("The view cube's look",
         f"Built with three's <code>ViewHelper</code> (X/Y/Z balls, traj_compare's July choice); clicks go through the contract's face table. The alternative is the labelled Fusion-style cube you asked for on Oct 3 (<code>@mlightcad/three-viewcube</code>), which adds corner and edge views. No key depends on it: a corner view is a <code>{{dir}}</code>{c('pep', 'h-p1b')}.",
         "PEP §13 Q1 recommended the labelled cube; it is a view-only swap.", "three's ViewHelper."),
        ("Reinstall Playwright's Chromium",
         f"At 12:33 another session's install replaced Chromium build 1243 with 1248 in the shared cache. The psu-atlas venv's Playwright wants 1243, so <code>npm test</code> cannot launch a browser on its own; every run today went through scratch symlinks to 1248 that will be swept with the session. Fix: <code>~/psu-atlas/.venv/bin/python -m playwright install chromium</code>, about 170 MB{c('pw', 'h-a2d')}.",
         "Run it.",
         "Not run: it is a 170 MB download into a shared cache. Suites keep running through the symlinks until then."),
        ("The three old ObjectDB branches",
         f"<code>try/objectdb-kit</code>, <code>lane/object-db</code> and <code>lane/collection</code>, 5 commits each that main does not have. Their content landed on main on Oct 27 as public-safe squashes (<code>integrate/objectdb</code>, <code>lane/object-db-public</code>, both in main). Two still have worktrees under <code>.wt/</code>{c('objdb')}.",
         "Delete once ObjectDB is off its old pin; the squashes are what should survive.", "Leave them."),
    ]
    H.append('<section id="decisions"><h2>Decisions for you</h2><p class="lede">Each has a recommendation and the '
             'reversible default taken if you say nothing.</p><div class="dec">'
             + "".join(f'<div class="decision"><h3>{i + 1}. {q}</h3><p>{ctx}</p><dl><dt>Recommend</dt><dd>{rec}</dd>'
                       f'<dt>Default</dt><dd>{dflt}</dd></dl></div>' for i, (q, ctx, rec, dflt) in enumerate(decisions))
             + "</div></section>")

    # ---------------------------------------------------------------- left / not done
    left = [
        ("P0", "h-p0", ["Dashboards without <code>clock.data</code> still never shrink their span on a filter: every card would have to report a keyed extent.",
                        "A plain <code>&lt;data-views&gt;</code> still ignores a view's <code>from:</code>.",
                        "sim2real's two workarounds can go once it re-vendors."]),
        ("P1a", "h-p1a", ["A live dataset used as a layer is a snapshot when the panel draws (documented as not yet).",
                          "The Python checker checks 3D column names against the default dataset only."]),
        ("P1b", "h-p1b", ["The labelled cube (decision 4), \"Open in Rerun\" carrying the trail's time range, the display-frame switch.",
                          "The playback bar's \"· decay 0.6 s\" readout (the playback card was outside the write set).",
                          "On a phone the Path 3D controls strip clips its last row.",
                          "Test pages <code>p1b.html</code> and <code>p2.html</code> set <code>display: block</code> on <code>data-views.boxed</code>, shrinking their stage; frozen, so left."]),
        ("P1c + P1d", "h-p1cd", ["<code>gallery/robotics/CONTRACT.md</code> §5 still says difference is computed in the trajectory library; the shared one now lives in <code>gallery/robotics/difference.py</code> (barrier file, not edited).",
                                 "real and real B share a hue with no line style in the time series."]),
        ("P4", "h-p4", ["Arm + gripper: no Device or Event facets (nothing to drive them). Camera: no Stream or Band facets; depth and hyperspectral wait for real captures.",
                        "The check suite needs <code>/archive/datasets/bam_rig</code>; on a machine without it, it fails by design."]),
        ("P2", "h-p2", ["Real-vs-sim step lines, qdd and τ histograms, the arm's EEF x/y/z panels.",
                        "Lifting one run to full opacity on a pick; Rerun export of voxels; zero-filled bins for coloured histograms; the float target for more than ~200 runs."]),
        ("Kit gaps", "h-kit", ["uPlot cards and <code>levels</code> are not on the shared y gutter; badges in tables, cards and lists take only slot numbers in <code>colors</code>.",
                               "No decision record for <code>parent:</code> yet."]),
        ("P3", "h-p3", ["Filling the run from the per-run dataset's own rail; <code>live:</code> or <code>refresh:</code> on a per-run dataset (both checkers refuse them).",
                        "sim2real's adoption is its own lane; site docs for §33."]),
        ("Add to dashboard", "h-a2d", ["iOS long-press does not open the right-click menus (the ⋯ menus work everywhere).",
                                        "Table cells and record fields have no item menu; the target dashboard is not reloaded after a save; no Python <code>appendPanel</code>."]),
        ("P5", "h-p5", ["Interactive time series (<code>timeseries.interactive</code>) does not draw limits yet; RobotDx's mini child-health bars are not built.",
                        "A peek field whose schema says <code>display: link</code> shows as text (one-line fix).",
                        "RobotDx's own <code>/dx/</code> page moving onto these views is a separate lane."]),
        ("Merge packet", "h-packet", ["The live <code>plot</code> legend is static, not §31's toggle; \"Show only selected\" is ignored on live datasets; ● LIVE shows only on the default playback variant."]),
    ]
    H.append('<section id="left"><h2>What\'s left, and what was not done on purpose</h2>'
             '<p class="lede">None of it blocks the merge. From each lane\'s own "not done" list, checked against '
             f'<code>{TIP}</code> where a file could tell (the §32 <code>max(1/n, 0.04)</code> wording P2 flagged is already gone).</p>'
             + "".join(f'<details class="left"><summary>{e(name)} <span>· {len(items)} item{"s" if len(items) > 1 else ""}</span></summary><ul>'
                       + "".join(f"<li>{it}{c(key)}</li>" for it in items) + "</ul></details>" for name, key, items in left)
             + f"""<p style="margin-top:14px"><b>Deliberately not done in this report:</b> no audit (none was asked for);
no new screenshots beyond the hero, since every lane's own captures are measured evidence; dark-mode screenshots are
shown only where the mock is dark, to keep the page small.</p></section>""")

    # ---------------------------------------------------------------- sources
    H.append('<section id="sources"><h2>Source index</h2><ol class="sources">'
             + "".join(f'<li id="s{i + 1}"><b>{e(label)}</b> · <code>{e(where)}</code></li>' for i, (_, label, where) in enumerate(SOURCES))
             + "</ol>"
             + f'<footer>First-parent commits on the packet, {BASE}..{TIP}:<pre>{e(chr(10).join(first_parent))}</pre>'
             f"Built by <code>docs/build_robotics_report.py</code> in the packet worktree (untracked, not committed).</footer></section>")

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PEP 0010 robotics review</title>
<meta name="description" content="data-ui PEP 0010 robotics playback: what is built on integrate/packet, the evidence, and the decisions left.">
<style>{CSS}</style></head>
<body><main>
{"".join(H)}
</main>
<dialog id="zoom"><img alt=""></dialog>
<script>{JS}</script>
</body></html>"""
    OUT.write_text(page, encoding="utf-8")
    return OUT, len(page.encode())


if __name__ == "__main__":
    out, n = build()
    media = sum(SIZES.values())
    print(f"wrote {out} ({n / 1e6:.2f} MB; {len(SIZES)} media, {media / 1e6:.2f} MB before base64)")
    for k, v in sorted(SIZES.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {v / 1e3:7.1f} KB  {k}")
