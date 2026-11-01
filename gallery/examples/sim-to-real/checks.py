"""Browser checks for the sim-to-real dashboard (PEP 0004, PEP 0005). Oracles from the case's JSON files and views.base."""

import contextlib
import pathlib
import re
import sys
from urllib.parse import urljoin

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from dashboard_helpers import D, card, counts, num, ready, rows  # noqa: E402

MOTORS = rows(HERE, "motors.json")
MODELS = rows(HERE, "models.json")
RUNS = rows(HERE, "runs.json")
TERMS = rows(HERE, "terms.json")
SAMPLES = rows(HERE, "samples.json")
MEDIA = rows(HERE, "media.json")
BASE = (HERE / "views.base").read_text(encoding="utf-8")
v = lambda c: c["value"] if isinstance(c, dict) else c
sig3 = lambda x: float(f"{x:.3g}")
c14 = next(m for m in MOTORS if m["motor"] == "CAN 14")
held = sum(r["motor"] == "CAN 14" and r["held_out"] for r in RUNS)
rungs = sorted((m for m in MODELS if m["motor"] == "CAN 14" and m["family"] not in ("friction", "floor")), key=lambda m: m["rung"])

# the rail's default run, as views.base writes it (datasets.samples.filters)
_m = re.search(r"  samples:\n(?:    .*\n)*?    filters: 'run == \"([^\"]+)\"'", BASE)
DEFAULT_RUN = _m.group(1) if _m else None

# a panel's Vega plot: page px of data values through its own scales, and every rule mark's pixel y
AT = """([key, pts]) => {
  const el = document.querySelector(`#example .dd-panel[data-panel="${key}"] .dv-view`);
  const v = el.vegaView, r = el.querySelector('canvas').getBoundingClientRect(), p = v.padding(), o = [p.left + v.origin()[0], p.top + v.origin()[1]];
  return pts.map(([x, y]) => [r.left + o[0] + v.scale('x')(x), y === null ? null : r.top + o[1] + v.scale('y')(y)]); }"""

SERIES = """(key) => {
  const el = document.querySelector(`#example .dd-panel[data-panel="${key}"] .dv-view`);
  if (!el || !el.vegaView) return null;
  const out = {}, rules = [];
  const walk = (node) => {
    if (!node) return;
    if (node.marktype) {
      for (const i of node.items || []) {
        if (node.marktype === 'line' && i.datum && i.datum.series) {
          const s = out[i.datum.series] || (out[i.datum.series] = { n: 0, stroke: i.stroke, dash: i.strokeDash || null });
          s.n += 1;
        }
        if (node.marktype === 'rule' && /^layer_\\d+_marks$/.test(node.name || '')) rules.push(i.y);
        walk(i);
      }
    } else if (node.items) for (const i of node.items) walk(i);
  };
  walk(el.vegaView.scenegraph().root);
  return { series: out, rules, y: el.vegaView.scale('y') ? [el.vegaView.scale('y')(0.522), el.vegaView.scale('y')(-0.522)] : null,
           xdomain: el.vegaView.scale('x').domain() }; }"""

VIDEOS = """(s) => [...document.querySelectorAll(s + ' video[data-t0]')].map((v) => ({
  src: v.dataset.src || null, t0: Number(v.dataset.t0), ready: v.readyState, seeking: v.seeking, t: v.currentTime, cls: v.className }))"""


@contextlib.contextmanager
def guard(ctx, what):
    """A section that cannot run (its panel is not there) is one failing check in its own words, not a crash."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        ctx.check(f"sim-to-real: {what} could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


def seek(page, t):
    page.evaluate("(t) => document.querySelector('#example').clock.seek(t)", t)
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")


def loaded(ctx, page, key):
    page.locator(f"{D} .dd-panel[data-panel='{key}']").scroll_into_view_if_needed()
    return ctx.until(page, """(s) => { const vs = [...document.querySelectorAll(s + ' video[data-t0]')];
      return vs.length && vs.every((v) => v.dataset.src && v.readyState >= 2 && !v.seeking); }""", f"{D} .dd-panel[data-panel='{key}']", timeout=15000)


def settled(ctx, page, key):
    return ctx.until(page, """(s) => [...document.querySelectorAll(s + ' video[data-t0]')].every((v) => v.readyState >= 2 && !v.seeking)""",
                     f"{D} .dd-panel[data-panel='{key}']", timeout=10000)


def pick_run(page, run):
    page.locator(f"{D} .dd-rail input[data-p='run'][data-value='{run}']").check(timeout=5000)
    page.wait_for_timeout(800)


def run(ctx, path):
    page = ctx.page(path, width=1440, height=1000)
    ready(page)
    got = counts(page)
    ctx.check("sim-to-real: 8 motor cards; 67 runs, 192 model-card terms, 51 + 20 model rows on two rulers",
              got["twin-vs-floor:cards"] == 8 and got["twin-error-by-run"] == len(RUNS) and got["model-cards"] == len(TERMS)
              and got["model-ladder-10-23-runs"] == sum(m["family"] != "friction" for m in MODELS) and got["friction-ladder-10-24-held-out"] == sum(m["family"] == "friction" for m in MODELS), got)

    # ---- CAN 14's headline tiles: the oracle numbers from motors.json / runs.json, to 3 significant figures
    with guard(ctx, "CAN 14's headline tiles"):
        tiles = page.evaluate("""() => { const t = (k, s) => { const e = document.querySelector(`#example [data-panel="${k}"] ${s}`); return e ? e.textContent : null; };
          return { twin: t('twin-gap-rms', '.dv-kpi-num'), twinDelta: t('twin-gap-rms', '.dv-kpi-delta, [class*=delta]'), floor: t('repeat-floor', '.dv-kpi-num'),
                   ratio: t('twin-floor', '.dv-gauge-num'), tone: (document.querySelector('#example [data-panel="twin-floor"] .dv-gauge') || {}).dataset?.tone,
                   target: t('twin-floor', '.dv-gauge-target title'), held: t('held-out-runs', '.dv-kpi-num') }; }""")
        want = {"twin": sig3(v(c14["twin"])), "floor": sig3(v(c14["floor"])), "ratio": sig3(v(c14["twin_over_floor"])), "held": held}
        shown = {k: num(tiles[k]) for k in want}
        ctx.check("sim-to-real tiles: Twin gap RMS, Repeat floor, Twin ÷ floor and Held-out runs show motors.json / runs.json's CAN 14 numbers to 3 significant figures",
                  shown == want, {"shown": shown, "want": want})
        ctx.check("sim-to-real tiles: the Twin ÷ floor gauge marks the 1.5× gate (acceptance T2) and is red, since 2.14 > 1.5 with lower better; Twin gap RMS carries its delta to the floor",
                  tiles["target"] == "target 1.5" and tiles["tone"] == ("bad" if v(c14["twin_over_floor"]) > 1.5 else "good")
                  and num(tiles["twinDelta"]) == sig3(v(c14["twin"]) - v(c14["floor"])), tiles)
        ctx.check("sim-to-real tiles: the gauge's arc is drawn at its size (not collapsed): taller than 60 px",
                  page.evaluate("() => document.querySelector('#example [data-panel=\"twin-floor\"] .dv-gauge-arc svg').getBoundingClientRect().height") > 60)

    # ---- model error by rung: one bullet per CAN 14 budget rung, simplest first, the tick at the floor (rung 20)
    with guard(ctx, "model error by rung"):
        floor_row = next(m for m in MODELS if m["motor"] == "CAN 14" and m["rung"] == 20)
        bl = page.evaluate("""() => [...document.querySelectorAll('#example [data-panel="model-error-by-rung-can-14"] .dv-bullet-row')].map((r) => ({
          label: (r.querySelector('.dv-bullet-label') || {}).title || (r.querySelector('.dv-bullet-label') || {}).textContent,
          value: (r.querySelector('.dv-bullet-value') || {}).textContent }))""")
        foot = page.evaluate("() => (document.querySelector('#example [data-panel=\"model-error-by-rung-can-14\"] .dv-bullet') || {}).textContent || ''")
        ctx.check("sim-to-real rungs: one bullet per CAN 14 budget rung in rung order, each value models.json's error to 3 s.f., the target tick at the rung-20 floor (= motors.json floor)",
                  [b["label"] for b in bl] == [m["model"] for m in rungs] and [num(b["value"]) for b in bl] == [sig3(v(m["error"])) for m in rungs]
                  and v(floor_row["error"]) == v(c14["floor"]) == 0.522 and "target tick 0.522" in foot,
                  {"drawn": bl, "want": [(m["model"], sig3(v(m["error"]))) for m in rungs], "foot": foot[-60:]})

    # ---- the rail's run: the time series and the camera show the default run; the repeat pair always shows tape A and B
    with guard(ctx, "the rail's run, the camera and the repeat pair"):
        ss = page.evaluate(SERIES, "angle-real-vs-twin")
        want_series = sorted({r["situation"] for r in SAMPLES if r["run"] == DEFAULT_RUN})
        n_run = sum(r["run"] == DEFAULT_RUN for r in SAMPLES)
        ctx.check(f"sim-to-real rail: the run rail starts on {DEFAULT_RUN} (a run with a clip); Angle draws its {n_run} rows as target (dashed), real, sim_identified, sim_identified_plus, each in the palette's colour",
                  got["angle-real-vs-twin"] == n_run and ss and sorted(ss["series"]) == want_series == ["real", "sim_identified", "sim_identified_plus", "target"]
                  and bool(ss["series"]["target"]["dash"]) and not any(ss["series"][s]["dash"] for s in want_series if s != "target")
                  and {s: (ss["series"][s]["stroke"] or "").lower() for s in want_series} == {"target": "#8b9099", "real": "#2a78d6", "sim_identified": "#e8743b", "sim_identified_plus": "#19a979"},
                  {"count": got["angle-real-vs-twin"], "series": ss and {k: (x["n"], x["stroke"], bool(x["dash"])) for k, x in ss["series"].items()}})
        gs = page.evaluate(SERIES, "gap-twin-real")
        want_gap = sum(r["run"] == DEFAULT_RUN and r["gap_mrad"] is not None for r in SAMPLES)
        ctx.check("sim-to-real gap: Gap draws only the two twins (gap_mrad is null on target and real), and two rules sit on Vega's y(±floor) within 1 px",
                  got["gap-twin-real"] == want_gap and gs and sorted(gs["series"]) == ["sim_identified", "sim_identified_plus"]
                  and len(gs["rules"]) == 2 and sorted(round(abs(a - b), 1) <= 1 for a, b in zip(sorted(gs["rules"]), sorted(gs["y"]))) == [True, True],
                  {"count": got["gap-twin-real"], "want": want_gap, "rules px": gs and gs["rules"], "y(±0.522)": gs and gs["y"]})
        clip = next(m for m in MEDIA if m["run"] == DEFAULT_RUN)
        ok = loaded(ctx, page, "rack-camera-real")
        vid = page.evaluate(VIDEOS, f"{D} .dd-panel[data-panel='rack-camera-real']")
        cap = page.evaluate("() => (document.querySelector('#example [data-panel=\"rack-camera-real\"] .dv-media-cap') || {}).textContent || ''")
        ctx.check("sim-to-real camera: Rack camera (real) plays the clip whose run is the rail's run, captioned with the run and 'real camera'",
                  ok and len(vid) == 1 and vid[0]["src"] == urljoin(page.url, clip["src"]) and vid[0]["t0"] == clip["t0"] and DEFAULT_RUN in cap and "real camera" in cap,
                  {"video": vid, "want": clip["src"], "caption": cap})
        c = page.evaluate("() => { const c = document.querySelector('#example').clock; return [c.start, c.end]; }")
        ts = [r["t"] for r in SAMPLES]
        ctx.check("sim-to-real clock: the clock spans samples.json's t (clock: data samples)", c == [min(ts), max(ts)], {"clock": c, "want": [min(ts), max(ts)]})
        frame = 1 / clip["fps"]
        offs = []
        for t in (1.0, 12.5, 30.0):
            seek(page, t)
            settled(ctx, page, "rack-camera-real")
            cur = page.evaluate(VIDEOS, f"{D} .dd-panel[data-panel='rack-camera-real']")[0]["t"]
            offs.append({"t": t, "currentTime": round(cur, 4), "off": round(abs(cur - (t - clip["t0"])), 4)})
        ctx.check(f"sim-to-real sync: after seeks to 1.0, 12.5, 30.0 s the camera's currentTime is t − t0 (t0 = {clip['t0']}) within one frame",
                  all(o["off"] <= frame for o in offs), offs)
        ph = page.evaluate("""() => ['angle-real-vs-twin', 'gap-twin-real'].map((k) => { const e = document.querySelector(`#example [data-panel="${k}"] [data-playhead]`);
          if (!e) return null; const b = e.getBoundingClientRect(); return b.left + b.width / 2; })""")
        want_x = [page.evaluate(AT, [k, [[30.0, None]]])[0][0] for k in ("angle-real-vs-twin", "gap-twin-real")]
        ctx.check("sim-to-real sync: at t = 30 s both time series' playheads sit on their Vega x(30) within 1 px",
                  all(p is not None and abs(p - w) <= 1 for p, w in zip(ph, want_x)), {"playheads": ph, "x(30)": want_x})

        pair = [next(m for m in MEDIA if m["run"] == r) for r in ("tape A 10-21", "tape B 10-21")]
        loaded(ctx, page, "tape-a-vs-tape-b-real-repeat")
        pv = page.evaluate(VIDEOS, f"{D} .dd-panel[data-panel='tape-a-vs-tape-b-real-repeat']")
        pcap = page.evaluate("() => (document.querySelector('#example [data-panel=\"tape-a-vs-tape-b-real-repeat\"] .dv-media-cap') || {}).textContent || ''")
        mode = page.evaluate("() => (document.querySelector('#example [data-panel=\"tape-a-vs-tape-b-real-repeat\"] .dv-media-compare') || {}).dataset?.mode")
        ctx.check("sim-to-real repeat: the overlay lays tape A over tape B (both real camera, onion by default) whatever the rail's run",
                  sorted(x["src"] for x in pv) == sorted(urljoin(page.url, m["src"]) for m in pair) and "A: tape A 10-21" in pcap and "B: tape B 10-21" in pcap
                  and "real camera" in pcap and " vs " not in pcap.split("B: tape B 10-21")[-1] and mode == "onion",
                  {"videos": [x["src"] for x in pv], "caption": pcap, "mode": mode})
        ctx.shot(page, "sim-to-real-media-1440")

    # ---- pick tape A, then the sine: the series and the camera follow; the sine has no clip and says so; the pair stays
    with guard(ctx, "picking tape A and the sine in the rail"):
        pick_run(page, "tape A 10-21")
        got = counts(page)
        loaded(ctx, page, "rack-camera-real")
        vid = page.evaluate(VIDEOS, f"{D} .dd-panel[data-panel='rack-camera-real']")
        tape_a = pair[0]
        ctx.check("sim-to-real rail: picking tape A narrows Angle and Gap to its rows and the camera to tape A's clip (media.run ↔ samples.run)",
                  got["angle-real-vs-twin"] == sum(r["run"] == "tape A 10-21" for r in SAMPLES) and got["gap-twin-real"] == sum(r["run"] == "tape A 10-21" and r["gap_mrad"] is not None for r in SAMPLES)
                  and got["rack-camera-real"] == 1 and len(vid) == 1 and vid[0]["src"] == urljoin(page.url, tape_a["src"]),
                  {"counts": {k: got.get(k) for k in ("angle-real-vs-twin", "gap-twin-real", "rack-camera-real")}, "video": [x["src"] for x in vid]})
        seek(page, 2.0)
        settled(ctx, page, "rack-camera-real")
        cur = page.evaluate(VIDEOS, f"{D} .dd-panel[data-panel='rack-camera-real']")[0]["t"]
        ctx.check("sim-to-real sync: on tape A, after a seek to 2.0 s the camera sits on t − t0 within one frame", abs(cur - (2.0 - tape_a["t0"])) <= frame, {"currentTime": cur})
        pick_run(page, "sine 10-23")
        got = counts(page)
        empty = page.evaluate("""() => { const p = document.querySelector('#example [data-panel="rack-camera-real"]');
          return { videos: p.querySelectorAll('video[data-src]').length, text: p.textContent }; }""")
        pv = page.evaluate(VIDEOS, f"{D} .dd-panel[data-panel='tape-a-vs-tape-b-real-repeat']")
        ctx.check("sim-to-real rail: the sine (no usable clip) leaves the camera card with no video and a '—', the text panel says so, and the tape A vs B overlay still has both clips",
                  got["angle-real-vs-twin"] == sum(r["run"] == "sine 10-23" for r in SAMPLES) and not any(m["run"] == "sine 10-23" for m in MEDIA)
                  and empty["videos"] == 0 and "—" in empty["text"] and len(pv) == 2 and "no usable camera clip" in BASE,
                  {"angle": got["angle-real-vs-twin"], "camera": empty, "pair": len(pv)})
    page.context.close()

    # ---- the cross-filter: clicking CAN 14 narrows the four motor datasets; the CAN 14 headline is unlinked and stays
    page = ctx.page(path, width=1440, height=1000)
    ready(page)
    c = card(page, "twin-vs-floor", "CAN 14")
    shown = num(c.locator(".dv-kpi-num").inner_text())
    exact = float(c.locator(".dv-kpi-num").get_attribute("data-exact") or "nan")
    # style.numbers (digits 3) rounds the drawn number since the round-2 rebuild; the stored value stays in data-exact
    ctx.check("sim-to-real: CAN 14's card is its full twin RMS to 3 significant figures (the stored value in data-exact, as written), with the delta to its measured floor",
              shown == sig3(v(c14["twin"])) and exact == v(c14["twin"]) and "Floor" in c.inner_text(), {"shown": shown, "exact": exact, "data": v(c14["twin"])})
    c.locator(".dv-kpi-label").click()
    page.wait_for_timeout(800)
    got = counts(page)
    want = {"twin-error-by-run": sum(r["motor"] == "CAN 14" for r in RUNS), "model-cards": sum(t["motor"] == "CAN 14" for t in TERMS),
            "model-ladder-10-23-runs": sum(m["motor"] == "CAN 14" and m["family"] != "friction" for m in MODELS),
            "friction-ladder-10-24-held-out": sum(m["motor"] == "CAN 14" and m["family"] == "friction" for m in MODELS), "motors": 1}
    ctx.check("sim-to-real cross-filter: clicking CAN 14 narrows all four linked datasets to it (CAN 14 has no friction study: 0 rows, not an error)",
              all(got[k] == x for k, x in want.items()), {"got": got, "want": want})
    c.locator(".dv-kpi-label").click()
    card(page, "twin-vs-floor", "CAN 15").locator(".dv-kpi-label").click()
    page.wait_for_timeout(800)
    got = counts(page)
    with guard(ctx, "the CAN 14 headline under a CAN 15 selection"):
        ctx.check("sim-to-real cross-filter: with CAN 15 selected the CAN 14 tiles, rungs and camera keep their rows (unlinked datasets), while Motors shows CAN 15 only",
                  got["motors"] == 1 and got["twin-gap-rms"] == 1 and got["twin-floor"] == 1 and got["held-out-runs"] == held and got["model-error-by-rung-can-14"] == len(rungs)
                  and got["rack-camera-real"] == 1 and got["tape-a-vs-tape-b-real-repeat"] == len(MEDIA), got)
    rr = page.evaluate("""async () => { const b = document.querySelector('#example .dd-rerun'); const u = new URL('rerun/sim-to-real.rrd', location.href).href;
      const h = await fetch(u, { method: 'HEAD' }); return { button: !!b, ok: h.ok, size: Number(h.headers.get('content-length')) }; }""")
    ctx.check("sim-to-real Open in Rerun: the dashboard offers it (rerun: key) and rerun/sim-to-real.rrd is served (HEAD 200, > 0 bytes)", rr["button"] and rr["ok"] and rr["size"] > 0, rr)
    page.context.close()
    looks(ctx, path)


def looks(ctx, path):
    """Light and dark at 1440 and 390 px. The tiles (the dashboard's surface, PEP 0005 §5) follow the theme; the view
    inside a tile is transparent by design, so the theme is measured on the tile, not on <data-views>."""
    for dark in (False, True):
        for width, mobile in ((1440, False), (390, True)):
            p = ctx.page(path, width=width, height=1000 if width > 400 else 844, dark=dark, mobile=mobile)
            ready(p)
            m = p.evaluate("""() => { const g = document.querySelector('#example .dd-grid').getBoundingClientRect();
              const ps = [...document.querySelectorAll('#example .dd-panel')].map((e) => Math.round(e.getBoundingClientRect().width));
              const tile = getComputedStyle(document.querySelector('#example .dd-panel:not(.dd-panel-text)')).backgroundColor;
              return { scroll: document.scrollingElement.scrollWidth, grid: Math.round(g.width), widths: ps, tile }; }""")
            # rgb(…) in 0-255, or color(srgb …) in 0-1 (a color-mix() token resolves to the latter)
            ch = [float(x) for x in re.findall(r"[\d.]+", m["tile"].replace("srgb", ""))[:3]]
            lum = (sum(ch) / 3 if "color(" in m["tile"] else sum(ch) / (3 * 255)) if len(ch) == 3 else None
            tag = f"sim-to-real {'dark' if dark else 'light'}, {width} px"
            if width == 390:
                ctx.check(f"{tag}: one column and no sideways page scroll", m["scroll"] <= 390 and all(abs(w - m["grid"]) <= 1 for w in m["widths"]), m)
            else:
                ctx.check(f"{tag}: panels side by side, no sideways scroll", len(set(m["widths"])) > 1 and m["scroll"] <= width, m["widths"])
            ctx.check(f"{tag}: the tiles follow the theme", lum is not None and (lum < 0.3) == dark, m["tile"])
            p.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + window.scrollY - 70)")
            p.wait_for_timeout(200)
            ctx.shot(p, f"sim-to-real-{'dark' if dark else 'light'}-{width}")
            p.context.close()
