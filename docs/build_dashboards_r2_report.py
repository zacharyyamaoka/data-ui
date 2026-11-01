"""Builds the round-2 dashboards report: ~/data-ui/reports/data-ui-dashboards-r2-2026-10-26.html.

    python3 docs/build_dashboards_r2_report.py

Reads only measured inputs:
- media under reports/media/dashboards-r2/ (docs/capture_dashboards_r2.py: hero, per-dashboard shots, onion; the
  playback lane's clips; the plot and robot lanes' screenshots copied in);
- reports/media/dashboards-r2/paint.json (docs/measure_dashboards.py);
- reports/media/dashboards-r2/checks.json (the npm test summary lines);
- git (commits and diff stat of lane/dashboard-cards against main).
Media are referenced by relative path (media/dashboards-r2/...), never inlined, so the page stays a small text file."""

import html
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAIN = Path("~/data-ui")
OUT = MAIN / "reports" / "data-ui-dashboards-r2-2026-10-26.html"
MEDIA = MAIN / "reports" / "media" / "dashboards-r2"
R1 = MAIN / "reports" / "media" / "dashboards"
REL = "media/dashboards-r2"
e = html.escape


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True).stdout.strip()


def load(name, default):
    p = MEDIA / name
    return json.loads(p.read_text()) if p.exists() else default


def img(name, alt, cls=""):
    if not (MEDIA / name).exists():
        return f'<div class="missing">missing: {e(name)}</div>'
    return f'<img class="{cls}" src="{REL}/{e(name)}" alt="{e(alt)}" loading="lazy">'


def video(name, poster=None, cls=""):
    if not (MEDIA / name).exists():
        return f'<div class="missing">missing: {e(name)}</div>'
    p = f' poster="{REL}/{e(poster)}"' if poster and (MEDIA / poster).exists() else ""
    kind = "video/webm" if name.endswith(".webm") else "video/mp4"
    return f'<video class="{cls}" controls muted loop playsinline preload="metadata"{p}><source src="{REL}/{e(name)}" type="{kind}"></video>'


DASHBOARDS = [
    ("pid-tuning", "PID tuning", "UR5e replay (sim): KPI tiles for the tuned rung, the playback bar, joint angle vs target, the MuJoCo replay, error over time, factory-vs-tuned wipe, tool path 3D with the meshed robot and XZ, the lever tape, gates and saturation, and round 1's nine robots below."),
    ("sim-to-real", "Sim to real", "The CAN 14 rack (real hardware): twin gap, repeat floor, twin ÷ floor gauge against the 1.5 gate; angle real vs twin over a real camera clip; the gap over time; tape A vs tape B (two real repeats) as the overlay; model error by rung."),
    ("trajectory-tracking", "Trajectory tracking", "Five-bar (sim) tool path in x–z with a tolerance tube and colour by error, the same path in 3D, error over time beside the study's render, the UR5e path with the robot, and the one real trajectory there is: the rack's joint, real vs twin."),
    ("vibetracks-dashboard", "Vibe Tracks · overview", "KPI tiles with ▲▼ and sparklines per track, a 30-day pass/fail tracker, runs per week as a line, a runs leaderboard, KPI histories as lines; runs refresh every 5 s."),
    ("vibetracks-runs", "Vibe Tracks · runs", "Pass-rate tiles, a checks-passing gauge, runs per week, check runs per track, every run over time, the leaderboard."),
    ("vibetracks-track", "Vibe Tracks · one track", "The track's KPI tiles, its gauge and 30-day row, KPI history as small multiples, pass rate by suite, runs per week."),
]

CARDS = [
    ("kpi", "Stat / KPI tile", "value, ▲▼ delta coloured by which way is better, sparkline, compact numbers (26.5K), significant figures", "ours (SVG), Tremor's look"),
    ("gauge", "Progress / gauge", "bar or arc, bands, target tick", "ours (SVG)"),
    ("bullet", "Bullet", "value bar, target tick, qualitative bands, one per row", "ours (SVG)"),
    ("barlist", "Bar list / leaderboard", "ranked rows, bar ∝ value, +N more", "ours (CSS), Tremor BarList"),
    ("tracker", "Status / tracker grid", "a block per row coloured by state, one row per group", "ours (CSS), Tremor Tracker"),
    ("timeseries", "Time series", "multi-series line/area/step, bands, rules, annotations, log/symlog, brush-zoom, shared crosshair, playhead", "Vega-Lite"),
    ("timeseries · interactive", "Interactive plot", "Rerun/Foxglove plot: pan, zoom x/y/box, reset, click moves the cursor, legend hide / Alt-isolate, ? help, maximise", "uPlot 1.6.32 (lazy, 28.6 KB gz)"),
    ("chart", "Bar / histogram / scatter / heatmap", "any Vega-Lite; frameless under chrome: minimal; a date or week x is a line by default", "Vega-Lite"),
    ("trajectory", "Trajectory 2D", "path vs target, equal aspect, colour by error, trail to t, tolerance tube, moving marker", "Vega-Lite + overlay"),
    ("scene3d", "3D scene", "3D paths, markers, a stick robot or a meshed robot (GLB) posed per row, one WebGL context per page", "three.js 0.186.1"),
    ("video", "Video", "native <video>, lazy, follows the clock; a primary video drives it", "browser"),
    ("video-compare", "Video overlay", "wipe slider, onion skin with an opacity slider, difference blend, side by side", "browser + CSS"),
    ("image", "Image", "Bases' image: property with caption:", "browser"),
    ("playback", "Playback (the clock's control)", "7 variants: bar, rerun, rerun-streams, youtube, tracks, foxglove, range; switcher", "ours"),
    ("table · map · cards", "Existing views as cards", "unchanged, wearing the dashboard's surface", "TanStack, MapLibre, …"),
    ("text panel", "Markdown", "headings, lists, links, code", "md.js"),
]

STYLE = [
    ("theme", "auto | light | dark", "auto"), ("surface", "filled | outline | transparent", "filled (tiles on a quieter page)"),
    ("radius", "px", "12"), ("pad", "px", "16"), ("gap", "px", "12"), ("title", "inside | top | none", "inside"),
    ("density", "comfortable | compact", "comfortable"), ("chrome", "minimal | full", "minimal (no domain, ticks or vertical grid)"),
    ("numbers", "{digits, compact}", "none (rounding is declared, never silent)"), ("palette", "{series name: colour}", "a stable slot per name"),
]

PLAYBACK = [
    ("bar", "Today's bar", "Rerun-ish: start, ±1 frame, play, loop, speed, readout, scrub track with ticks, a range lane, the zoom window"),
    ("rerun", "P1 · Rerun (simple)", "Rerun's toolbar copied: play (blue), step ▸ with its 8-item menu and keys (←/→ 0.1 s, Shift ±1 s, Ctrl next/prev event, Ctrl+Shift start/end), loop menu, timeline picker, speed field, time field"),
    ("rerun-streams", "P1 · Rerun (streams)", "the toolbar plus the STREAMS tree, a ruler, per-entity event bars, the playhead across rows; Shift-drag sets the loop"),
    ("youtube", "P2 · YouTube", "a bar that thickens on hover, a real-frame thumbnail on hover, chapters from the target's moves, the buffered range, a gear menu, J/K/L, ←/→, , ."),
    ("tracks", "P3 · Video editor (Premiere / DaVinci / CapCut)", "timecode, a work-area lane, one filmstrip track per clip (real frames), one sparkline track per series, a playhead across tracks"),
    ("foxglove", "P4 · Foxglove", "the scrubber with loaded ranges, SEC / ELAPSED time display, seek back / play / forward, speed, loop"),
    ("range", "P5 · Grafana-style range", "a minimap of the main series with a brush that sets every time series' zoom window"),
]


def main():
    paint = load("paint.json", {})
    checks = load("checks.json", {})
    head = git("rev-parse", "--short", "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    log = git("log", "--oneline", "--no-merges", "main..HEAD")
    stat = git("diff", "--shortstat", "main...HEAD")

    dash_rows = []
    for slug, title, what in DASHBOARDS:
        base = (REPO / "gallery" / "examples" / slug / "views.base")
        base_text = base.read_text() if base.exists() else ""
        p = paint.get(slug, {})
        fup = f"{p.get('first_useful_paint_ms', '—')} ms" if p else "—"
        before = f'<figure><figcaption>Round 1</figcaption><img src="media/dashboards/{slug}-light.jpg" alt="{e(title)} round 1" loading="lazy"></figure>' if (R1 / f"{slug}-light.jpg").exists() else ""
        dash_rows.append(f"""
<section class="dash" id="{slug}">
  <h3>{e(title)} <small>first useful paint {e(fup)}</small></h3>
  <p class="lede">{e(what)}</p>
  <div class="pair">
    <figure><figcaption>Light</figcaption>{img(f"{slug}-light.jpg", title + " light")}</figure>
    <figure><figcaption>Dark</figcaption>{img(f"{slug}-dark.jpg", title + " dark")}</figure>
  </div>
  <details><summary>Its <code>views.base</code> ({len(base_text.splitlines())} lines) and round 1</summary>
    <div class="pair"><pre class="base"><code>{e(base_text)}</code></pre>{before}</div>
  </details>
</section>""")

    pb_rows = "".join(f"""<figure class="clip"><figcaption><b>{e(label)}</b> <code>variant: {e(v)}</code><br><span>{e(desc)}</span></figcaption>{video(f"playback/{v}.webm")}</figure>""" for v, label, desc in PLAYBACK)
    card_rows = "".join(f"<tr><td><code>{e(t)}</code></td><td>{e(n)}</td><td>{e(d)}</td><td>{e(s)}</td></tr>" for t, n, d, s in CARDS)
    style_rows = "".join(f"<tr><td><code>{e(k)}</code></td><td>{e(v)}</td><td>{e(dft)}</td></tr>" for k, v, dft in STYLE)
    paint_rows = "".join(f"<tr><td>{e(k)}</td><td>{v.get('first_useful_paint_ms')}</td><td>{v.get('spread_ms', ['', ''])[0]}–{v.get('spread_ms', ['', ''])[1]}</td><td>{v.get('media_ready_ms') or '—'}</td></tr>" for k, v in paint.items())
    check_rows = "".join(f"<li><code>{e(line)}</code></li>" for line in checks.get("lines", []))

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboards round 2</title>
<style>
:root {{ --bg:#fff; --fg:#18181b; --muted:#5f5f6b; --line:#e4e4e7; --sub:#f6f6f7; --accent:#2563eb; --good:#1f7a45; --warn:#9a5b00; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#111113; --fg:#ececef; --muted:#a1a1aa; --line:#2a2a2e; --sub:#1b1b1f; --accent:#7aa7ff; --good:#6fbf8b; --warn:#e0a640; }} }}
:root[data-theme="dark"] {{ --bg:#111113; --fg:#ececef; --muted:#a1a1aa; --line:#2a2a2e; --sub:#1b1b1f; --accent:#7aa7ff; --good:#6fbf8b; --warn:#e0a640; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
main {{ max-width:1500px; margin:0 auto; padding:28px 16px 80px; }}
h1 {{ font-size:26px; letter-spacing:-.01em; margin:0 0 6px; }} h2 {{ font-size:20px; margin:42px 0 10px; border-top:1px solid var(--line); padding-top:22px; }}
h3 {{ font-size:16px; margin:26px 0 6px; }} h3 small {{ color:var(--muted); font-weight:400; font-size:13px; margin-left:8px; }}
.verdict {{ font-size:18px; font-weight:600; margin:6px 0 14px; max-width:110ch; }}
.lede {{ color:var(--muted); max-width:110ch; margin:4px 0 10px; }}
p, li {{ max-width:110ch; }}
img, video {{ max-width:100%; height:auto; display:block; border-radius:10px; border:1px solid var(--line); background:var(--sub); }}
.hero video {{ width:100%; }}
.pair {{ display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:14px; align-items:start; }}
.grid3 {{ display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:14px; }}
figure {{ margin:0; }} figcaption {{ font-size:13px; color:var(--muted); margin:0 0 6px; }} figcaption b {{ color:var(--fg); }}
table {{ border-collapse:collapse; width:100%; font-size:14px; margin:8px 0 16px; }} th, td {{ text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ font-weight:600; background:var(--sub); }}
code {{ font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace; background:var(--sub); padding:1px 5px; border-radius:4px; }}
pre.base {{ margin:0; max-height:520px; overflow:auto; background:var(--sub); border:1px solid var(--line); border-radius:10px; padding:12px; font:12px/1.45 ui-monospace,monospace; }}
pre.base code {{ background:none; padding:0; }}
details {{ margin:8px 0; }} summary {{ cursor:pointer; color:var(--accent); }}
.missing {{ padding:20px; border:1px dashed var(--line); border-radius:10px; color:var(--warn); font-size:13px; }}
.tag {{ display:inline-block; font-size:12px; padding:1px 8px; border-radius:99px; background:var(--sub); border:1px solid var(--line); color:var(--muted); }}
.ok {{ color:var(--good); }} .warn {{ color:var(--warn); }}
.diagram {{ width:100%; max-width:980px; }}
.diagram text {{ fill:var(--fg); font:13px system-ui,sans-serif; }} .diagram .m {{ fill:var(--muted); font-size:11.5px; }}
.diagram rect {{ fill:var(--sub); stroke:var(--line); }} .diagram .clock {{ fill:color-mix(in srgb, var(--accent) 18%, var(--bg)); stroke:var(--accent); }}
.diagram path, .diagram line {{ stroke:var(--muted); fill:none; }}
@media (max-width: 900px) {{ .pair, .grid3 {{ grid-template-columns:minmax(0,1fr); }} table {{ display:block; overflow-x:auto; }} }}
</style></head><body><main>
<h1>data-ui dashboards, round 2</h1>
<p class="verdict">Dashboards now have a catalog of 16 card types (time series, an interactive plot, video, video overlay, 2D trajectory, 3D with a meshed robot, stat tiles, gauge, bullet, bar list, tracker, playback) on one synced clock, a declared look that is one integrated surface, and the six dashboards are rebuilt on real data and media — on <code>{e(branch)}</code> @ <code>{e(head)}</code>, not merged (dashboards themselves landed on main as CONTRACT §17).</p>
<p class="lede">Real camera video exists only for the 1-DOF rack (CAN 14). There is no sim render of the rack and no real UR5e or five-bar run, so the sim-vs-real overlay compares two real repeats of the same tape, and every sim clip says it is a MuJoCo render.</p>

<div class="hero"><figure><figcaption>Hero (24 s, from the real built page): the PID-tuning dashboard playing — the MuJoCo replay, both time series' playheads, the XZ path and the 3D robot move on one clock — then the overlay goes wipe → onion → difference → side.</figcaption>{video("hero.mp4", "hero-poster.jpg")}</figure>
<p class="lede">GIF fallback: <a href="{REL}/hero.gif">hero.gif</a></p></div>

<h2>The card catalog</h2>
<p class="lede">Every card on real rows (gallery case <code>dashboard-cards</code>): pidtuna's UR5e replay (sim) and Zach's Vibe Tracks runs. A card is a view type, so a card is placed by <code>layout:</code> exactly as a table is (PEP 0005).</p>
<div class="pair"><figure><figcaption>Light</figcaption>{img("dashboard-cards-light.jpg", "catalog light")}</figure><figure><figcaption>Dark</figcaption>{img("dashboard-cards-dark.jpg", "catalog dark")}</figure></div>
<table><thead><tr><th>type</th><th>card</th><th>draws</th><th>stock part</th></tr></thead><tbody>{card_rows}</tbody></table>

<h2>How sync and "Open in Rerun" work</h2>
<svg class="diagram" viewBox="0 0 980 300" role="img" aria-label="One clock, many followers">
  <rect class="clock" x="380" y="20" width="220" height="64" rx="10"/><text x="490" y="47" text-anchor="middle">Clock (one per dashboard)</text><text class="m" x="490" y="68" text-anchor="middle">t · range · window · hover · rate · loop</text>
  <rect x="20" y="20" width="250" height="64" rx="10"/><text x="145" y="47" text-anchor="middle">Playback card / keys / #t= link</text><text class="m" x="145" y="68" text-anchor="middle">seek · play · step · setRange</text>
  <line x1="270" y1="52" x2="380" y2="52"/><path d="M372 47 L380 52 L372 57"/>
  <rect x="710" y="20" width="250" height="64" rx="10"/><text x="835" y="47" text-anchor="middle">Primary video</text><text class="m" x="835" y="68" text-anchor="middle">requestVideoFrameCallback → drive(t)</text>
  <line x1="710" y1="52" x2="600" y2="52"/><path d="M608 47 L600 52 L608 57"/>
  <line x1="490" y1="84" x2="490" y2="130"/>
  <line x1="110" y1="130" x2="870" y2="130"/>
  <g>
   <line x1="110" y1="130" x2="110" y2="170"/><rect x="20" y="170" width="180" height="70" rx="10"/><text x="110" y="198" text-anchor="middle">Time series</text><text class="m" x="110" y="218" text-anchor="middle">playhead moved by scale(t)</text>
   <line x1="300" y1="130" x2="300" y2="170"/><rect x="210" y="170" width="180" height="70" rx="10"/><text x="300" y="198" text-anchor="middle">Trajectory 2D</text><text class="m" x="300" y="218" text-anchor="middle">marker + trail at t</text>
   <line x1="490" y1="130" x2="490" y2="170"/><rect x="400" y="170" width="180" height="70" rx="10"/><text x="490" y="198" text-anchor="middle">3D (one WebGL)</text><text class="m" x="490" y="218" text-anchor="middle">links posed at t</text>
   <line x1="680" y1="130" x2="680" y2="170"/><rect x="590" y="170" width="180" height="70" rx="10"/><text x="680" y="198" text-anchor="middle">Follower videos</text><text class="m" x="680" y="218" text-anchor="middle">seek; jump &gt;0.1 s, nudge ±5 %</text>
   <line x1="870" y1="130" x2="870" y2="170"/><rect x="780" y="170" width="180" height="70" rx="10"/><text x="870" y="198" text-anchor="middle">Open in Rerun</text><text class="m" x="870" y="218" text-anchor="middle">same datasets → .rrd</text>
  </g>
  <text class="m" x="490" y="275" text-anchor="middle">Events are synchronous: on a seek every follower is placed in the same task. Nothing re-runs Vega or rebuilds DOM per tick.</text>
</svg>
<ul>
<li><b>One writer of t.</b> <code>clock:</code> in the .base (data, time, rate, loop, fps) spans it; <code>#t=</code> and <code>#tr=</code> keep the instant and range in the URL. Keys: Space, ←/→, Shift±1 s, J/K/L, [ ], Home/End. Measured: paused, the videos, both playheads and the 3D marker show the clock's t with spread 0.0 s; playing, at the primary's presented frames the clock is that frame (0 s), playheads and 3D within 0.3 ms, a follower within its 0.1 s policy (0.02 s).</li>
<li><b>Open in Rerun</b> (<code>rerun: {{rrd, sdk: 0.40.0}}</code>): <code>tools/rerun_export.py</code> (rerun-sdk through <code>uv run</code>, a build-time extra) writes a .rrd from the same datasets with a blueprint mirroring the layout (time series, 3D paths/markers/skeleton, videos as AssetVideo with frame references, KPI tables as notes). The button opens Rerun's hosted viewer (no account), copies <code>uvx --from rerun-sdk==0.40.0 rerun &lt;url&gt;</code>, or downloads the file. A round-trip test reads the .rrd back and compares every sample with the case JSON (mutation-tested). Not exported: bar list, gauge, bullet, tracker and Vega charts (Rerun has no such views), dashes, the wipe (side by side in Rerun). The hosted viewer needs the .rrd served with <code>Access-Control-Allow-Origin: https://app.rerun.io</code>; a local <code>http.server</code> lacks it (docs/RERUN.md).</li>
</ul>

<h2>Styling: one surface, declared once</h2>
<p class="lede"><code>style:</code> in the .base, overridable per panel (<code>style:</code> on a layout panel) or per view. A card never draws its own box inside a dashboard.</p>
<table><thead><tr><th>key</th><th>values</th><th>default</th></tr></thead><tbody>{style_rows}</tbody></table>
<p>Numbers: <code>digits</code> (significant figures; an integer part is never cut) and <code>compact</code> (26,513 → 26.5K) on a property, a card's <code>format:</code> or <code>style.numbers</code>; the stored value stays on hover. This fixed the raw <code>0.9964028776978417</code> on the Vibe Tracks KPIs. Zach's rule, now a default: change over time is a line (a date or week x with no mark draws a line; a count is 0 in an empty week; <code>gaps: true</code> breaks it; bars stay <code>mark: bar</code>).</p>
<div class="pair"><figure><figcaption>Video overlay, onion mode with its opacity slider (light)</figcaption>{img("onion-light.png", "onion light")}</figure><figure><figcaption>Dark</figcaption>{img("onion-dark.png", "onion dark")}</figure></div>

<h2>The six dashboards, rebuilt</h2>
<p class="lede">KPI tiles across the top, the playback bar, time series and media below, analysis tables last. Each is a .base file only; each image is the real built page at 1440 px.</p>
{''.join(dash_rows)}

<h2>Playback bar: five proposals</h2>
<p class="lede">All seven variants drive the same clock through one registry (<code>registerPlaybackVariant(name, {{label, create(host, el, clock, ctx)}})</code>), so the RobotDx live tier can add an eighth. A <code>switcher: true</code> drop-down at a card's bottom-right switches live and remembers the pick. Try them on the <code>playback-proposals</code> gallery case. Clips are 6.5–10 s from that page (play, pause, scrub; YouTube hovers for thumbnails; range brushes).</p>
<div class="grid3">{pb_rows}</div>
<p>What a live tier with rewind needs from the clock (documented in <code>packages/views/playback/README.md</code>, clock.js unchanged): a shared <code>clock.live</code> + <code>setLive()</code> cleared by any seek, <code>clock.edge</code> (newest t) separate from a declared span, wall-clock play pinned at rate 1 while live, and the URL writing <code>live</code> instead of <code>#t=</code>.</p>

<h2>Interactive plot (Rerun / Foxglove style)</h2>
<p class="lede"><code>timeseries: {{interactive: true}}</code>. Chosen by measurement, 4 series × 10,000 points in headless Chromium: Vega-Lite 6.5 pan redraw 57.7 ms median (p95 84.7) vs uPlot 0.9 ms (p95 2.1); first draw 301–377 ms vs 18–38 ms; Vega-Lite also cannot bind per-axis zoom to modifiers, cannot isolate with Alt-click, and cannot follow an outside zoom window. uPlot loads only when a card says <code>interactive: true</code> (28.6 KB gzipped): PEP 0001's dense-time-series exception, like React Flow for graphs.</p>
<div class="grid3">
<figure><figcaption>Light</figcaption>{img("plot-light.png", "plot light")}</figure>
<figure><figcaption>The ? help (Rerun's list)</figcaption>{img("plot-help-light.png", "plot help")}</figure>
<figure><figcaption>Alt-click isolates a series</figcaption>{img("plot-isolated-light.png", "plot isolated")}</figure>
<figure><figcaption>Box zoom</figcaption>{img("plot-boxzoom-light.png", "box zoom")}</figure>
<figure><figcaption>Maximised (dark)</figcaption>{img("plot-maximised-dark.png", "maximised")}</figure>
<figure><figcaption>390 px</figcaption>{img("plot-390.png", "plot phone")}</figure>
</div>

<h2>The 3D viewer: three.js, a build-time GLB — not R3F or viser</h2>
<p class="lede">Zach asked: "For the 3D viewer, are we not using react-three-fiber, viser, or even our own viser libraries?"</p>
<table><thead><tr><th>Option (weighted /100)</th><th>Score</th><th>Why</th></tr></thead><tbody>
<tr><td>three.js on the one shared WebGL context + meshes baked at build time</td><td><b>95</b></td><td>static and same-origin, many cards on one context, follows the clock per tick, 148 KB gz for three; meshes come from Python like ViserUrdf and traj_compare's RobotDisplay do</td></tr>
<tr><td>the same + mujoco-wasm kinematics in the page</td><td>83</td><td>exact MJCF in the browser, but 10 MB of wasm for what Python already computes</td></tr>
<tr><td>react-three-fiber + drei</td><td>68</td><td>332 KB gz and a second copy of React (each view bundle is separate); one WebGL context per card unless every card lives under one page-filling drei <code>&lt;View&gt;</code></td></tr>
<tr><td>viser static embed (<code>as_html</code> / <code>?playbackPath=</code>)</td><td>54</td><td>its own 120 Hz wall clock, seekable only from its own slider (no time API), an iframe and a context per card; "experimental"</td></tr>
<tr><td>Zach's viser apps (viser-3d-viewer, viser-ui, clank-viser)</td><td>46</td><td>all need a live Python server; the reusable part is their Python (ViserUrdf ships each link as a GLB)</td></tr>
<tr><td>Rerun web viewer embedded</td><td>37</td><td>54 MB wasm on another origin; stays the "Open in Rerun" button</td></tr>
</tbody></table>
<p>viser's own client is React 19 + R3F + drei on three 0.186, the same three we ship: R3F and viser are not alternatives to three.js but layers over it. What looked primitive was the 8-point stick robot, so the spike adds <code>scene3d.robot: {{model, links, ghost}}</code>: a UR5e GLB exported at build time from MuJoCo Menagerie (7 body nodes, verified to MuJoCo's own mesh placement within 1.5e-8 m), posed per row from MuJoCo forward kinematics: exact at its 25 Hz rows, and between rows the card's lerp/slerp is within 1.34 mm of true forward kinematics (max 1.335 mm over 104,804 link samples, 95th percentile 0.42 mm; measured by <code>measure_robot_interp.py</code>). Change my mind if clicks or edits must reach Python or a live stream is needed: then viser-3d-viewer in a Clank pane.</p>
<div class="pair"><figure><figcaption>Meshed UR5e on the clock (light)</figcaption>{img("robot-light.png", "robot light")}</figure><figure><figcaption>Dark</figcaption>{img("robot-dark.png", "robot dark")}</figure></div>

<h2>Live data</h2>
<p><code>datasets.&lt;name&gt;.refresh: 5s</code> re-fetches the file; panels update in place. Measured on the Vibe Tracks overview with a served file that gains one run: the runs panels went 47 → 48 rows in 3.1 s, while the selection chip, the table's scroll position (160 px), the rail and the page scroll stayed identical; <code>data-dashboard-refresh</code> fired once, and an unchanged poll fires nothing.</p>
<h2>Arrange</h2>
<p>An Arrange button turns the grid into gridstack 14 (MIT, framework-free, its own lazily loaded bundle): drag and resize panels; Done keeps the reader's arrangement (localStorage) and redraws the grid; Copy layout writes the .base with the new <code>layout:</code>; Reset layout restores the file's. Measured: dragging "Gate margin" onto "Stop error" puts it first, survives a reload, and the .base text follows.</p>

<h2>Performance: first useful paint</h2>
<p class="lede">From navigation start until every non-media panel above the fold has drawn, median of 5 cold loads in headless Chromium at 1440 × 1000, on the gallery's case page (which also lists the .base and data, so this is an upper bound). Video and WebGL below the fold start when scrolled near, by design. Measured on lane/dashboard-cards @ 50932e9 (before the round-1 fixes) at a load average of 11 (other agents were working); the spread is the 5 runs' min–max.</p>
<table><thead><tr><th>dashboard</th><th>first useful paint (ms)</th><th>spread (ms)</th><th>first video frame (ms)</th></tr></thead><tbody>{paint_rows}</tbody></table>

<h2>Checks</h2>
<ul>{check_rows}</ul>

<h2>Judge round 1: ten findings, fixed</h2>
<p class="lede">Codex judge round 1 on d2857da returned FIX. Each finding was fixed with a test that failed first; lane head dd48b2d is green on the full suite.</p>
<ol>
<li>A buffering primary video keeps the clock (no 250 ms timeout); it hands t back only by <code>release(id)</code> or an explicit fallback after a 3 s stall, and t never jumps backward.</li>
<li>Every seek starts a new seek generation; a frame callback armed before the seek is ignored and the video re-arms on <code>seeked</code>.</li>
<li>Exactly one video drives t: <code>clock.primary</code>, else the first <code>video.primary</code> card; <code>setDriver</code> enforces it; a <code>clock.primary</code> that names no video card is a checker error (decision record: PEP 0008).</li>
<li>Paused seeks under 1 ms are applied (1 → 1.0009 moves every video).</li>
<li><code>#t=</code> edits after load are followed (hashchange); several dashboards on a page use <code>#t.&lt;id&gt;=</code>.</li>
<li>A loop range is intersected with the span; an empty intersection is no range.</li>
<li><code>.rrd</code> files are served with <code>Access-Control-Allow-Origin: https://app.rerun.io</code> (npm run serve and the deployed site's <code>_headers</code>); the hosted 0.40.0 viewer loaded the recording headless (Chrome asks the reader to allow local network access).</li>
<li>The Rerun round-trip oracle checks the timeline name and kind, counts and paired samples; four mutation tests prove it catches each.</li>
<li>The robot claim is qualified: exact at robot.json's rows, within 1.34 mm of true forward kinematics between them (max 1.335 mm over 104,804 measured link samples).</li>
<li>The playing-sync check asserts every participant, enforces 1/30 s (primary), 1 ms (drawn) and 0.1 s + a frame (followers), puts a 2 s deadline on every wait, and proves itself by failing on an injected hidden playhead, late follower and dropped marker.</li>
</ol>

<h2>Judge round 2: six findings, fixed</h2>
<p class="lede">Codex judge round 2 on dd48b2d returned FIX (reports/media/audits/2026-10-28-dashboards-judge-r2.md). Each fix starts from the judge's own repro as a test that failed first; the lane head below is green on the full suite.</p>
<ol>
<li><b>A loop wrap is a seek.</b> The wall-time and fallback wraps ran through <code>seek(t, {{source: 'play'}})</code>, which keeps the seek generation, so the frame callback armed at 9.9 s pulled t from 0.4 back to 9.933 (reproduced exactly). Every wrap now fires source <code>loop</code> and bumps <code>gen</code>; the clip seeks to the wrap point and re-arms on <code>seeked</code>. Sibling path: the fallback's own jump to t also cancels the pending callback, so a pre-jump frame cannot end the fallback.</li>
<li><b>The driver is one card instance.</b> Two panels showing <code>Video</code> gave both clips the id <code>Video</code>: both drove, and either one's <code>ended</code> released the other. The dashboard now designates <code>&lt;panel key&gt;/&lt;view name&gt;</code> for the first panel in layout order (<code>driverInstance</code>); in the browser only that panel's &lt;video&gt; asks for frames, and the second one ending leaves it driving.</li>
<li><b>Back / Forward is a fresh load.</b> An absent t is the clock's home (where a fresh clock sits), an absent or empty tr is no range, a malformed value leaves that part alone (<code>clockNavigation</code>), and applying a navigation writes nothing back. The browser check compares every Back / Forward step against a fresh page at that URL.</li>
<li><b>URL scopes are unique.</b> Two id-less dashboards with one src are <code>views-base</code> and <code>views-base-2</code> in document order, and keep 2 s and 7 s across a reload; a repeated id is listed under the later dashboard's problems, warned in the console, and numbered.</li>
<li><b>The robot measurement covers its whole grid.</b> Joint inputs are interpolated between the 100 Hz samples and the sample count is asserted (104,804 link samples, not 16,548); the claim is “within 1.34 mm (max 1.335 mm, p95 0.42 mm)” everywhere it appears.</li>
<li><b>No home paths in published data.</b> Producers write repository-relative provenance (<code>gallery/tools/public_paths.py</code>), and a unit test scans every published case file; six files owned by main are listed in a ratchet (a new hit fails, and so does a listed file once it is clean).</li>
</ol>

<h2>Judge round 3: six findings, fixed</h2>
<p class="lede">Codex judge round 3 on 5b17576 returned FIX (reports/media/audits/2026-10-28-dashboards-judge-r3.md). Each fix started red from the judge's repro; the lane head below is green on the full suite, and every changed producer was re-run under its documented command.</p>
<ol>
<li><b>Producers import their helper.</b> The round-2 line pointed at <code>gallery/gallery/tools</code>; all 12 producers failed. <code>tools/test_producer_imports.py</code> imports the helper through each producer's own <code>sys.path</code> line under <code>python3 -I</code>. All 13 changed producers re-ran (exit 0): sim-to-real, trajectory-tracking and dashboard-cards reproduce their JSON byte for byte; pid-tuning reproduces it from pidtuna-website 1414ae6, the snapshot its source names (today's pidtuna data has moved on, as has Vibe Tracks' local bundle); the robot measurement gives 104,804 samples, max 1.3354 mm.</li>
<li><b>One placement rule for t.</b> An untouched clock sits at <code>home()</code> and follows it as the cards report their spans; a seek or a link's t is kept and re-clamped. A fresh load and Back / Forward both call <code>clock.restore()</code>. The judge's case (#tr=2,6, then spans [5,10] and [0,10]) now ends at 2 both ways, and a unit test checks 6 links × 4 orders of arrival.</li>
<li><b>The home-path gate fails closed.</b> It uses the publisher's own text extensions and refuse pattern (now one shared module), and a baseline of 187 exact occurrences in 17 files owned elsewhere, never whole files. A new hit in a baselined file, a new file with a <code>file://</code> URI, a bare <code>/home/alice</code>, a <code>.py</code> and a <code>.svg</code> each turn it red; the old gate stayed green on all five.</li>
<li><b>The driver is a card on screen.</b> A video on a tab that isn't open is never designated, the choice is re-made on every tab change, and when no open tab shows the chosen video the clock plays on wall time with a quiet note on the playback bar.</li>
<li><b>The duplicate-id problem survives a reload.</b> The problem is attached on every parse; the console warning stays once.</li>
<li><b>Repeated sources need explicit ids</b> (the coordinator's call). No positional <code>-2</code>/<code>-3</code> keys: a repeated or slug-colliding src without an id, or a repeated id, keeps its clock out of the URL, lists the problem, and <code>data-ui check page.html</code> reports each tag at its line.</li>
</ol>

<h2>Where it lives</h2>
<p><code>{e(branch)}</code> @ <code>{e(head)}</code> — {e(stat)} against main. Not merged: the data-ui integrator merges to main.</p>
<details><summary>Commits on the lane ({len(log.splitlines())}, merges left out)</summary><pre class="base"><code>{e(log)}</code></pre></details>

<h2>Real media: found and missing</h2>
<ul>
<li><b>Real camera:</b> the CAN 14 rack only (RealSense, cut from the raw recordings on a 30 fps grid, t0 = −0.3 s, the worst frame-stamp gap recorded per clip): a staircase run and a tape A / tape B repeat pair. The sine run's camera kept 53 frames over 6.5 s, so it has no clip.</li>
<li><b>Sim renders:</b> five MuJoCo 3.17 renders of pidtuna's UR5e replay (one per rung, one fixed camera, 30 fps, t0 0) and the five-bar study's own render.</li>
<li><b>Missing:</b> no sim render of the rack (bam_rack_twin has a renderer but CAN 14's joint is not in the CAD export); no real UR5e or five-bar data anywhere, so their "real" slots are declared "not requested"; no twin-replayed rack trajectories beyond traj_compare's own sim_identified situations.</li>
</ul>

<h2>Decisions for Zach</h2>
<ul>
<li><b>Default playback variant.</b> Recommendation: <code>rerun</code> (P1 simple) as the default, with <code>rerun-streams</code> for analysis pages. Default if you say nothing: keep <code>bar</code> as the default and leave the switcher on the catalog and proposals pages only.</li>
<li><b>Merge the cards lane.</b> Recommendation: hand <code>{e(branch)}</code> to the integrator once its full suite is green (it lands CONTRACT §25, PEP 0005, the cards, the rebuilt dashboards). Default: I report the sha and the integrator decides.</li>
<li><b>Ship the robot GLB.</b> 1.5 MB on disk, Menagerie's BSD-3 notice beside it. Recommendation: keep it in the pid-tuning case; run gltfpack/meshopt later if the page budget needs it. Default: as is.</li>
</ul>
<h2>Deliberately not done</h2>
<ul>
<li>No sim render of the rack was faked; the overlay compares real repeats.</li>
<li>No React layer for 3D (see the evaluation); no viser embed.</li>
<li>Weekly/monthly grouping and the peek breadcrumb trail were left to the other builder (they are on main as §14).</li>
<li>The live tier with rewind is the RobotDx agent's; the playback registry and the clock notes are its hooks.</li>
</ul>
</main></body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(OUT, f"{OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
