"""Browser checks for the trajectory-tracking dashboard (PEP 0004, cards PEP 0005). Oracles from rack.json, cells.json,
path2d.json, situations.json, stats.json, media.json, ../pid-tuning/tool.json and ../sim-to-real/samples.json; every
number on the page is measured (Vega's own scales, getBoundingClientRect, the clock, the video element, the 3D card's
hook) and compared with those files, never with the dashboard's model."""

import bisect
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from dashboard_helpers import D, counts, ready, rows  # noqa: E402

RACK = rows(HERE, "rack.json")
CELLS = rows(HERE, "cells.json")
PATH = rows(HERE, "path2d.json")
SITUATIONS = rows(HERE, "situations.json")
STATS = rows(HERE, "stats.json")
MEDIA = rows(HERE, "media.json")
UR5E = rows(HERE.parent / "pid-tuning", "tool.json")
RACKJOINT = [r for r in rows(HERE.parent / "sim-to-real", "samples.json") if r["run"] == "sine 10-23" and r["situation"] != "target"]
PALETTE = {"target": "#8b9099", "house8-model_live_friction_object": "#2a78d6", "soft4-model_live_friction_object": "#eb6834", "stiff32-none": "#1baf7a",
           "real": "#e34948", "sim_identified": "#2a78d6", "sim_identified_plus": "#1baf7a"}   # the .base's style.palette
FRAME = 1 / 25   # the clock's fps (the path grid and the clip are 25 Hz)

# a data point in page px through a panel's own Vega scales
AT = """([key, pts]) => {
  const el = document.querySelector(`#example .dd-panel[data-panel="${key}"] .dv-view`);
  const v = el.vegaView, r = el.querySelector('canvas').getBoundingClientRect(), p = v.padding(), o = [p.left + v.origin()[0], p.top + v.origin()[1]];
  return pts.map(([x, y]) => [r.left + o[0] + v.scale('x')(x), y === null ? null : r.top + o[1] + v.scale('y')(y)]); }"""
CENTRES = """([key, sel]) => [...document.querySelectorAll(`#example .dd-panel[data-panel="${key}"] ${sel}`)]
  .filter((e) => !e.hidden && getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden')
  .map((e) => { const b = e.getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2, series: e.dataset.series || null }; })"""
# the drawn line series of a Vega panel: {series: stroke}
LINES = """(key) => { const el = document.querySelector(`#example .dd-panel[data-panel="${key}"] .dv-view`); const out = {};
  const walk = (n) => { if (!n) return; if (n.marktype === 'line') for (const i of n.items || []) { const s = i.datum && i.datum.series; if (s && i.stroke) out[s] = i.stroke; }
    for (const i of n.items || []) if (i.items) walk(i); };
  walk(el.vegaView.scenegraph().root); return out; }"""
SCENE = "(k) => { const r = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`); return r && r.scene3d ? r.scene3d.markers() : null; }"


def sig3(v):
    return f"{v:.3g}"


def by_series(data, key="situation"):
    out = {}
    for r in data:
        out.setdefault(r[key], []).append(r)
    for s in out.values():
        s.sort(key=lambda r: r["t"])
    return out


def interp(srows, t, cols):
    """The row of one series at time t, linearly interpolated by its t column (the oracle for a marker)."""
    ts = [r["t"] for r in srows]
    i = bisect.bisect_left(ts, t)
    if i <= 0:
        return [srows[0][c] for c in cols]
    if i >= len(srows):
        return [srows[-1][c] for c in cols]
    a, b = srows[i - 1], srows[i]
    f = (t - a["t"]) / (b["t"] - a["t"]) if b["t"] != a["t"] else 0
    return [a[c] + (b[c] - a[c]) * f for c in cols]


def seek(page, t):
    page.evaluate("(t) => document.querySelector('#example').clock.seek(t)", t)
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")


def wake(ctx, page):
    """Scroll once through the page so the lazy cards (video, WebGL) start, then wait for the clip's metadata."""
    for y in range(0, page.evaluate("document.body.scrollHeight"), 500):
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(120)
    page.evaluate("window.scrollTo(0, 0)")
    ctx.until(page, "() => [...document.querySelectorAll('#example video[data-t0]')].every((v) => v.readyState >= 1)", timeout=20000)
    ctx.until(page, """() => ['five-bar-tool-path-3d-sim', 'ur5e-tool-path-3d-sim'].every((k) => { const r = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`);
      return r && r.scene3d && Object.keys(r.scene3d.markers()).length; })""", timeout=20000)
    ctx.until(page, """() => ['five-bar-tool-path-x-z-sim', 'tool-error-over-time-sim', 'rack-joint-real-vs-twin-real-hardware'].every((k) => {
      const el = document.querySelector(`#example .dd-panel[data-panel="${k}"] .dv-view`); return el && el.vegaView && el.dataset.drawn; })""", timeout=20000)


def run(ctx, path):
    page = ctx.page(path, width=1440, height=1000)
    ready(page)
    got = counts(page)
    missing = sum((c["rms_error"] or {}).get("value") is None for c in CELLS)
    status = page.inner_text(f"{D} [data-panel=target-vs-sim-10-09] .dv-status")
    ctx.check("trajectory: 134 real run comparisons, 48 study cells of which the 24 real ones show as missing (not requested), never 0",
              got["real-vs-twins-per-motor"] == len(RACK) and got["study-cells"] == len(CELLS) and missing == 24 and f"{missing} without" in status, {"got": got, "status": status})
    sims = [r for r in PATH if r["situation"] != "target"]
    ctx.check("trajectory cards: each panel holds its oracle rows: the five-bar path 824 (2D and 3D), its error 618 (no target), the UR5e tape 1,980, the rack's sine 10-23 without target 1,818, 14 situations",
              got["five-bar-tool-path-x-z-sim"] == got["five-bar-tool-path-3d-sim"] == len(PATH) and got["tool-error-over-time-sim"] == len(sims)
              and got["ur5e-tool-path-3d-sim"] == len(UR5E) and got["rack-joint-real-vs-twin-real-hardware"] == len(RACKJOINT) and got["situations"] == len(SITUATIONS), got)

    # ---- the KPI tiles, against the JSON
    worst = {}
    for r in sims:
        worst[r["situation"]] = max(worst.get(r["situation"], -math.inf), r["err_mm"])
    bl = page.evaluate("""() => [...document.querySelectorAll("#example .dd-panel[data-panel='worst-tool-error'] .dv-barlist-row")].map((r) => ({
      label: r.querySelector('.dv-barlist-label').textContent.trim(), text: r.querySelector('.dv-barlist-value').textContent.trim(),
      w: r.querySelector('.dv-barlist-bar').getBoundingClientRect().width, track: r.querySelector('.dv-barlist-track').getBoundingClientRect().width }))""")
    want = sorted(worst.items(), key=lambda kv: kv[1])   # better: lower -> smallest first
    top = max(worst.values())
    ctx.check("KPI worst tool error: one bar per simulated situation with rows, smallest first (better lower), each the max of its err_mm in path2d.json to 3 significant figures, bar = value / max",
              [(b["label"], b["text"]) for b in bl] == [(k, sig3(v)) for k, v in want] and all(abs(b["w"] - b["track"] * worst[b["label"]] / top) <= 1 for b in bl),
              {"drawn": [(b["label"], b["text"], round(b["w"]), round(b["track"])) for b in bl], "oracle": [(k, sig3(v)) for k, v in want]})
    ran = [r for r in STATS if r["tcp_rms_moving_mm"] is not None]
    best = min(ran, key=lambda r: r["tcp_rms_moving_mm"])
    kpi = page.evaluate("""(key) => [...document.querySelectorAll(`#example .dd-panel[data-panel='${key}'] data-kpi`)].map((k) => ({
      num: k.querySelector('.dv-kpi-num').textContent.trim(), exact: k.querySelector('.dv-kpi-num').dataset.exact, label: k.querySelector('.dv-kpi-label').textContent.trim() }))""", "best-controller-rms")
    ctx.check("KPI best controller: the tile shows the report's own TCP RMS (moving, full rate) of the controller with the lowest one in stats.json (house8 + best model, 12.7 mm), as written",
              best["situation"] == "house8-model_live_friction_object" and len(kpi) == 1 and kpi[0]["num"] == sig3(best["tcp_rms_moving_mm"]) == str(best["tcp_rms_moving_mm"]),
              {"drawn": kpi, "oracle": [best["situation"], best["tcp_rms_moving_mm"]]})
    lost = [r for r in SITUATIONS if r["robot"] == "Five-bar" and r["status"] == "lost"]
    kl = page.evaluate("""(key) => [...document.querySelectorAll(`#example .dd-panel[data-panel='${key}'] data-kpi`)].map((k) => k.querySelector('.dv-kpi-num').textContent.trim())""", "controllers-lost")
    ctx.check("KPI controllers lost: the count of five-bar situations whose status is lost in situations.json (3), and none of them has a row in path2d.json",
              kl == [str(len(lost))] and not ({r["situation"] for r in lost} & {r["situation"] for r in PATH}), {"drawn": kl, "oracle": [r["situation"] for r in lost]})
    tones = {"ok": "good", "lost": "bad", "not requested": "muted", "not run": "warn"}
    # the colour each tone token resolves to inside the card (a throwaway element wearing var(--dv-tone-<tone>))
    probe = page.evaluate("""() => { const host = document.querySelector("#example .dd-panel[data-panel='situations-by-status'] .dv-view-tracker"); const out = {};
      for (const t of ['good', 'bad', 'muted', 'warn']) { const i = document.createElement('i'); i.style.cssText = `position:absolute;width:1px;height:1px;background:var(--dv-tone-${t})`;
        host.append(i); out[t] = getComputedStyle(i).backgroundColor; i.remove(); }
      return out; }""")
    st = page.evaluate("""() => [...document.querySelectorAll("#example .dd-panel[data-panel='situations-by-status'] .dv-tracker-row")].map((r) => ({
      label: r.querySelector('.dv-tracker-label').textContent.trim(), blocks: [...r.querySelectorAll('.dv-tracker-block')].map((b) => ({ bg: getComputedStyle(b).backgroundColor, title: b.title })) }))""")
    want_rows = {}
    for r in SITUATIONS:
        want_rows.setdefault(r["robot"], []).append(r)
    bad = [(x["label"], r["situation"], r["status"], b["title"]) for x in st for b, r in zip(x["blocks"], want_rows.get(x["label"], []))
           if b["bg"] != probe[tones[r["status"]]] or r["status"] not in b["title"]]
    reals = [b for x in st for b, r in zip(x["blocks"], want_rows.get(x["label"], [])) if r["kind"] == "real"]
    ctx.check("status card: one row per robot (Five-bar 8, UR5e 6 situations), each block its status's tone in situations.json order; both real slots are muted 'not requested', declared, not dropped",
              {x["label"]: len(x["blocks"]) for x in st} == {k: len(v) for k, v in want_rows.items()} and not bad and len(reals) == 2
              and all(b["bg"] == probe["muted"] and "not requested" in b["title"] for b in reals) and len({probe[t] for t in ("good", "bad", "muted")}) == 3,
              {"rows": [(x["label"], len(x["blocks"])) for x in st], "bad": bad[:3], "reals": reals})
    text = page.inner_text(f"{D} .dd-panel-text")
    real_rows = page.evaluate("""() => [...document.querySelectorAll("#example .dd-panel[data-panel='situations'] tr")].map((tr) => tr.textContent).filter((t) => /not requested/.test(t)).length""")
    ctx.check("the text panel says real tool paths do not exist yet and that the paths are different motions on one time axis; the situations table shows the 2 real slots as not requested",
              "Real tool paths do not exist yet" in text and "different motions on one time axis" in text and real_rows == 2, {"rows": real_rows})

    # ---- the time series draw the right series, in the palette's colours
    wake(ctx, page)
    lines = page.evaluate(LINES, "tool-error-over-time-sim")
    rack_lines = page.evaluate(LINES, "rack-joint-real-vs-twin-real-hardware")
    ctx.check("time series: Tool error over time draws exactly the three controllers with rows (no target, no lost one), each in the palette's colour",
              sorted(lines) == sorted({r["situation"] for r in sims}) and all(lines[s].lower() == PALETTE[s] for s in lines), lines)
    ctx.check("time series: the rack joint draws real and both twins for the sine 10-23 run (real hardware), each in the palette's colour",
              sorted(rack_lines) == sorted({r["situation"] for r in RACKJOINT}) == ["real", "sim_identified", "sim_identified_plus"] and all(rack_lines[s].lower() == PALETTE[s] for s in rack_lines), rack_lines)

    # ---- the clip
    clip = MEDIA[0]
    v = page.evaluate("""() => { const v = document.querySelector("#example .dd-panel[data-panel='five-bar-mujoco-render-sim'] video[data-t0]"); const b = v.closest('.dd-panel').querySelector('.dv-media-basis');
      return { src: v.dataset.src, t0: Number(v.dataset.t0), dur: v.duration, basis: b && b.dataset.basis, text: b && b.textContent.trim() }; }""")
    ctx.check("video: the five-bar panel plays the study's own MuJoCo clip (media.json's src, t0 0, 9.2 s) and labels it sim render",
              v["src"].endswith("/trajectory-tracking/" + clip["src"]) and v["t0"] == clip["t0"] and abs(v["dur"] - clip["duration"]) < 0.1 and v["basis"] == "sim-render" and "sim" in v["text"].lower(), v)

    # ---- one clock: span, and every card on the same instant after three seeks
    c = page.evaluate("() => { const c = document.querySelector('#example').clock; return { start: c.start, end: c.end }; }")
    ctx.check("clock: spans path2d.json's t (0 to 8.19 s), the declared clock data", c["start"] == 0 and abs(c["end"] - max(r["t"] for r in PATH)) < 1e-9, c)
    fivebar = by_series(PATH)
    ur5e = by_series(UR5E)
    misses, n = [], 0
    for t in (1.52, 4.0, 6.2):
        seek(page, t)
        ctx.until(page, "() => [...document.querySelectorAll('#example video[data-t0]')].every((v) => !v.seeking)", timeout=8000)
        page.wait_for_timeout(60)
        now = page.evaluate("() => { const v = document.querySelector('#example video[data-t0]'); return { t: document.querySelector('#example').clock.t, video: v.currentTime + Number(v.dataset.t0) }; }")
        n += 1
        if abs(now["video"] - t) > FRAME:
            misses.append({"t": t, "video": now["video"]})
        for key in ("tool-error-over-time-sim", "rack-joint-real-vs-twin-real-hardware"):
            [[wx, _]] = page.evaluate(AT, [key, [[t, None]]])
            ph = page.evaluate(CENTRES, [key, "[data-playhead]"])
            n += 1
            if len(ph) != 1 or abs(ph[0]["x"] - wx) > 1:
                misses.append({"t": t, "playhead": key, "want": round(wx, 1), "got": [round(p["x"], 1) for p in ph]})
        dots = page.evaluate(CENTRES, ["five-bar-tool-path-x-z-sim", "[data-marker]"])
        for name, srows in fivebar.items():
            x, z = interp(srows, t, ["x_mm", "z_mm"])
            [[wx, wy]] = page.evaluate(AT, ["five-bar-tool-path-x-z-sim", [[x, z]]])
            mine = [d for d in dots if d["series"] == name]
            n += 1
            if len(mine) != 1 or abs(mine[0]["x"] - wx) > 1.5 or abs(mine[0]["y"] - wy) > 1.5:
                misses.append({"t": t, "2d marker": name, "want": [round(wx, 1), round(wy, 1)], "got": [[round(d["x"], 1), round(d["y"], 1)] for d in mine]})
        for key, sets, cols, tol in (("five-bar-tool-path-3d-sim", fivebar, ["x_mm", "y_mm", "z_mm"], 0.05), ("ur5e-tool-path-3d-sim", ur5e, ["px", "py", "pz"], 5e-5)):
            world = page.evaluate(SCENE, key) or {}
            for name, srows in sets.items():
                n += 1
                if name not in world or math.dist(world[name], interp(srows, t, cols)) > tol:
                    misses.append({"t": t, "3d marker": f"{key}:{name}", "want": [round(x, 4) for x in interp(srows, t, cols)], "got": world.get(name)})
    ctx.check("one clock: after seek(1.52 / 4.0 / 6.2) the clip (within one 25 fps frame), both time series' playheads (Vega's x(t), 1 px), the 2D markers (oracle row at t, 1.5 px) and both 3D cards' markers (oracle position at t) all show the same instant",
              not misses and n == 3 * (1 + 2 + len(fivebar) + len(fivebar) + len(ur5e)), misses[:4] or f"{n} measured")
    ctx.shot(page, "trajectory-tracking-cards-1440")

    # ---- the rails: the five-bar's situation facet narrows its four panels only; the rack facet keeps working
    page.check("data-facets[data-dataset=path2d] input[data-p=situation][data-value='house8-model_live_friction_object']")
    page.wait_for_timeout(700)
    got = counts(page)
    one = [r for r in PATH if r["situation"] == "house8-model_live_friction_object"]
    bl = page.evaluate("""() => [...document.querySelectorAll("#example .dd-panel[data-panel='worst-tool-error'] .dv-barlist-label")].map((e) => e.textContent.trim())""")
    ctx.check("five-bar rail: situation = house8 + best model narrows the 2D path, 3D path, error over time and the bar list to its 206 rows; the UR5e, rack joint and situations panels keep theirs",
              got["five-bar-tool-path-x-z-sim"] == got["five-bar-tool-path-3d-sim"] == got["tool-error-over-time-sim"] == len(one) and bl == ["house8-model_live_friction_object"]
              and got["ur5e-tool-path-3d-sim"] == len(UR5E) and got["rack-joint-real-vs-twin-real-hardware"] == len(RACKJOINT) and got["situations"] == len(SITUATIONS) and got["real-vs-twins-per-motor"] == len(RACK),
              {"got": got, "bars": bl})
    page.uncheck("data-facets[data-dataset=path2d] input[data-p=situation][data-value='house8-model_live_friction_object']")
    page.check("data-facets[data-dataset=rack] input[data-p=motor][data-value='CAN 14']")
    page.wait_for_timeout(700)
    got = counts(page)
    ctx.check("trajectory rail: motor = CAN 14 narrows every rack panel to its 38 comparisons; the unlinked sim study keeps 48",
              got["real-vs-twins-per-motor"] == sum(r["motor"] == "CAN 14" for r in RACK) and got["error-against-the-floor"] == got["real-vs-twins-per-motor"] and got["study-cells"] == len(CELLS), got)
    page.context.close()
    themes(ctx, path, "trajectory-tracking")


def themes(ctx, path, name):
    """Light and dark at 1440 and 390 px: one column and no sideways scroll on a phone, side by side on a desktop, and
    the tiles follow the theme. WHY measured on the tile (.dd-panel), not on its <data-views>: under the one-surface
    look (PEP 0005 §5) the dashboard paints the tile and the view inside it is transparent in both themes."""
    for dark in (False, True):
        for width, mobile in ((1440, False), (390, True)):
            p = ctx.page(path, width=width, height=1000 if width > 400 else 844, dark=dark, mobile=mobile)
            ready(p)
            m = p.evaluate("""() => { const g = document.querySelector('#example .dd-grid').getBoundingClientRect();
              const ps = [...document.querySelectorAll('#example .dd-panel')].map((e) => Math.round(e.getBoundingClientRect().width));
              const lum = (c) => { const [r, g, b] = c.match(/[\\d.]+/g).map(Number), k = c.startsWith('color(') ? 1 : 255; return (0.2126 * r + 0.7152 * g + 0.0722 * b) / k; };
              const tiles = [...document.querySelectorAll('#example .dd-panel:not(.dd-panel-text)')].map((e) => getComputedStyle(e).backgroundColor);
              return { scroll: document.scrollingElement.scrollWidth, grid: Math.round(g.width), widths: ps, tiles: [...new Set(tiles)], lum: tiles.map(lum) }; }""")
            tag = f"{name} {'dark' if dark else 'light'}, {width} px"
            if width == 390:
                ctx.check(f"{tag}: one column and no sideways page scroll", m["scroll"] <= 390 and all(abs(w - m["grid"]) <= 1 for w in m["widths"]), m["widths"])
            else:
                ctx.check(f"{tag}: panels side by side, no sideways scroll", len(set(m["widths"])) > 1 and m["scroll"] <= width, m["widths"])
            ctx.check(f"{tag}: every tile follows the theme (tile luminance {'< 0.25' if dark else '> 0.85'})",
                      all((l < 0.25) if dark else (l > 0.85) for l in m["lum"]), m["tiles"])
            p.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + window.scrollY - 70)")
            p.wait_for_timeout(200)
            ctx.shot(p, f"{name}-{'dark' if dark else 'light'}-{width}")
            p.context.close()
