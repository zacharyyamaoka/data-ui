"""Browser checks for the playback proposals (docs/peps/0005-dashboard-cards.md §4b): every variant drives the one
clock, and each one's own controls do what its prior art does.

Every expected number comes from the case's JSON and views.base (the oracle): the clock's span is samples.json's t
range (clock: {data: samples, time: t}), a frame is 1 / fps (views.base: fps 30), events are the distinct sample
times, streams are the datasets' numeric columns and clips. Every claim is a measurement: getBoundingClientRect, the
clock's state, a canvas's pixels; never "the element exists"."""

import inspect
import json
import math
import pathlib
import re

HERE = pathlib.Path(__file__).parent
D = "#example"
FPS = int(re.search(r"^\s+fps:\s*(\d+)", (HERE / "views.base").read_text(encoding="utf-8"), re.M).group(1))
FRAME = 1 / FPS
# variant -> (the panel key: the slug of its view name in views.base, the scrub surface, the playhead)
VARIANTS = {
    "bar": ("bar", ".dv-pb-track", "[data-thumb]"),
    "rerun": ("rerun", "[data-scrub]", "[data-playhead]"),
    "rerun-streams": ("rerun-streams", "[data-scrub]", "[data-playhead]"),
    "youtube": ("youtube", "[data-scrub]", "[data-playhead]"),
    "tracks": ("tracks", "[data-scrub]", "[data-playhead]"),
    "foxglove": ("foxglove", "[data-scrub]", "[data-playhead]"),
    "range": ("range", "[data-scrub]", "[data-playhead]"),
}


def rows(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))["rows"]


def val(c):
    return c["value"] if isinstance(c, dict) else c


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


SAMPLES, TOOL, MEDIA = rows("samples.json"), rows("tool.json"), rows("media.json")
T = sorted({val(r["t"]) for r in SAMPLES if num(val(r["t"]))})
SPAN = (T[0], T[-1])                                   # clock: {data: samples, time: t}
EVENTS = sorted({val(r["t"]) for r in SAMPLES + TOOL if num(val(r.get("t")))})


def P(key):
    return f"{D} .dd-panel[data-panel='{key}']"


def ready(page):
    page.wait_for_selector(f"{D} .dd-panel", timeout=20000)
    page.wait_for_function("""() => { const els = [...document.querySelectorAll('#example .dd-panel data-views')];
      return els.length && els.every((e) => e.dataset.view) && document.querySelector('#example').clock.end !== null; }""", timeout=30000)
    page.wait_for_timeout(300)


def clock(page):
    return page.evaluate("""() => { const c = document.querySelector('#example').clock;
      return { t: c.t, start: c.start, end: c.end, playing: c.playing, rate: c.rate, loop: c.loop, range: c.range, window: c.window }; }""")


def seek(page, t):
    page.evaluate("(t) => { const c = document.querySelector('#example').clock; c.pause(); c.seek(t); }", t)
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")


def rect(page, sel, scroll=True):
    """The element's box in viewport px, after scrolling it into view (None when it is missing). scroll=False for a
    part measured beside one just scrolled to (scrolling it too may shift a clipped container under the first)."""
    if not page.locator(sel).count():
        return None
    if scroll:
        page.locator(sel).first.scroll_into_view_if_needed()
    return page.evaluate("""(s) => { const r = document.querySelector(s).getBoundingClientRect();
      return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height, cx: r.left + r.width / 2, cy: r.top + r.height / 2 }; }""", sel)


def x_of(t, box):
    return box["left"] + (t - SPAN[0]) / (SPAN[1] - SPAN[0]) * box["width"]


def press(page, key):
    page.keyboard.press(key)
    page.evaluate("() => new Promise((r) => requestAnimationFrame(r))")


def chapters_oracle():
    """The YouTube chapters, recomputed here from samples.json: the target's q_deg starts moving after holding still
    for >= 0.2 s (views.base's palette names `target` first)."""
    pts = sorted((val(r["t"]), val(r["q_deg"])) for r in SAMPLES if r["situation"] == "target")
    starts, still = [SPAN[0]], None
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if abs(v1 - v0) <= 1e-6:
            still = t0 if still is None else still
            continue
        if still is not None and t0 - still >= 0.2 and t0 > starts[-1] + 1e-9:
            starts.append(t0)
        still = None
    return [s for s in starts if s < SPAN[1]]


def streams_oracle():
    """Rerun's STREAMS from the datasets: {dataset: (t0, t1, children)}; numeric columns other than t (and id) for a
    table, one child per clip spanning [t0, t0 + duration] for media."""
    out = {}
    for name, data in (("samples", SAMPLES), ("tool", TOOL)):
        cols = sorted({k for r in data for k, v in r.items() if k not in ("t", "id") and num(val(v))})
        ts = [val(r["t"]) for r in data]
        out[name] = (min(ts), max(ts), cols)
    out["media"] = (min(val(r["t0"]) for r in MEDIA), max(val(r["t0"]) + val(r["duration"]) for r in MEDIA), [r["situation"] for r in MEDIA])
    return out


def shots_dir(ctx):
    return getattr(inspect.getmodule(type(ctx)), "OUT", pathlib.Path("."))


def common(ctx, page, variant):
    """Every variant: play/pause toggles the clock; a click on its scrub surface seeks to that x; its playhead sits at
    clock.t after seeks."""
    check = ctx.check
    key, scrub, head = VARIANTS[variant]
    p = P(key)
    seek(page, 2.0)
    play = f"{p} [data-act=play]"
    on = off = None
    if page.locator(play).count():
        page.locator(play).first.scroll_into_view_if_needed()
        page.click(play)
        on = clock(page)["playing"]
        page.wait_for_timeout(250)
        page.click(play)
        off = clock(page)["playing"]
    check(f"proposal {variant}: its play button starts the clock and a second click pauses it", on is True and off is False, {"after 1st": on, "after 2nd": off})

    box = rect(page, f"{p} {scrub}")
    got = want = None
    if box:
        page.mouse.click(box["left"] + 0.3 * box["width"], box["cy"])
        got, want = clock(page)["t"], SPAN[0] + 0.3 * (SPAN[1] - SPAN[0])
    check(f"proposal {variant}: a click at 30 % of its scrub surface seeks the clock there (within one frame, {FRAME:.4f} s)",
          got is not None and abs(got - want) <= FRAME + 1e-6, {"t": got, "want": round(want, 4) if want else None, "scrub": box and round(box["width"])})

    offs = []
    for t in (1.5, 5.25, SPAN[1]):
        seek(page, t)
        b, h = rect(page, f"{p} {scrub}"), rect(page, f"{p} {head}", scroll=False)
        if not b or not h:
            offs.append(None)
            continue
        offs.append(round(h["cx"] - x_of(clock(page)["t"], b), 2))
    check(f"proposal {variant}: after seeks to 1.5, 5.25 and the end ({SPAN[1]} s) its playhead's centre sits at t on the scrub surface (within 1 px)",
          all(o is not None and abs(o) <= 1 for o in offs), {"px off": offs})


def guard(ctx, name, fn):
    """Run one section; an element that never comes is that section's FAIL, not a crash of the whole case."""
    try:
        fn()
    except Exception as e:  # noqa: BLE001 - reported, never hidden
        ctx.check(f"{name}: its checks ran to the end", False, f"{type(e).__name__}: {str(e).splitlines()[0][:300]}")


def shoot(ctx, page, variant, theme):
    key = VARIANTS[variant][0]
    loc = page.locator(P(key))
    loc.scroll_into_view_if_needed()
    if variant == "tracks":
        ctx.until(page, """(s) => { const cs = [...document.querySelectorAll(s + ' .dv-tk-strip canvas')]; return cs.length && cs.every((c) => c.dataset.frame); }""", P(key), timeout=20000)
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
    loc.screenshot(path=str(shots_dir(ctx) / f"playback-{variant}-{theme}.png"))


def run(ctx, path):
    check = ctx.check
    page = ctx.page(path, width=1440, height=1000)
    ready(page)
    page.set_default_timeout(8000)   # a control that is not there fails its section in seconds, not minutes
    c0 = clock(page)
    check("proposals: the clock spans samples.json's t (clock: {data: samples, time: t})", abs(c0["start"] - SPAN[0]) < 1e-9 and abs(c0["end"] - SPAN[1]) < 1e-9, c0)
    kinds = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#example .dd-panel[data-type=playback]')].map((s) => [s.dataset.panel, (s.querySelector('.dv-view-playback') || {}).dataset?.variant || null]))""")
    check("proposals: each playback card draws the variant its view names (bar, rerun, rerun-streams, youtube, tracks, foxglove, range)",
          all(kinds.get(k) == v for v, (k, _, _) in VARIANTS.items()), kinds)

    for variant in VARIANTS:
        guard(ctx, f"proposal {variant}", lambda: common(ctx, page, variant))

    # ---- P1 rerun: the step menu, its keys, the loop modes, the speed and time fields
    def sec_rerun():
        p = P("rerun")
        end, start = SPAN[1], SPAN[0]
        nxt = lambda t: next(e for e in EVENTS if e > t + 1e-9)
        prv = lambda t: [e for e in EVENTS if e < t - 1e-9][-1]
        t0 = 3.2
        want = {"Forward 0.1s": t0 + 0.1, "Backward 0.1s": t0 - 0.1, "Forward 1s": t0 + 1, "Backward 1s": t0 - 1,
                "Next event": nxt(t0), "Previous event": prv(t0), "End of timeline": end, "Start of timeline": start}
        got, labels = {}, []
        for label in want:
            seek(page, t0)
            page.locator(f"{p} [data-act=steps]").scroll_into_view_if_needed()
            page.click(f"{p} [data-act=steps]")
            labels = page.locator(f"{p} .dv-pbv-menu [role=menuitem]").all_inner_texts()
            item = page.locator(f"{p} .dv-pbv-menu [role=menuitem]", has_text=label)
            if item.count():
                item.first.click()
            got[label] = round(clock(page)["t"], 6)
        check("rerun: the step menu lists Rerun's eight steps with their keys, and each moves t from 3.2 s by exactly 0.1 s / 1 s, to the next / previous sample time, or to the end / start",
              all(abs(got[k] - want[k]) < 1e-6 for k in want) and len(labels) == 8 and any("Ctrl+Shift+Right" in x for x in labels),
              {"got": got, "want": {k: round(v, 6) for k, v in want.items()}, "items": [x.replace("\n", " ") for x in labels]})
        keys = {"ArrowRight": t0 + 0.1, "ArrowLeft": t0 - 0.1, "Shift+ArrowRight": t0 + 1, "Shift+ArrowLeft": t0 - 1, "Control+ArrowRight": nxt(t0),
                "Control+ArrowLeft": prv(t0), "Control+Shift+ArrowRight": end, "Control+Shift+ArrowLeft": start}
        mini = rect(page, f"{p} [data-scrub]")
        page.mouse.click(mini["left"] + 2, mini["cy"])   # use the card (its keys win while it is the one in use)
        gotk = {}
        for k, w in keys.items():
            seek(page, t0)
            press(page, k)
            gotk[k] = round(clock(page)["t"], 6)
        check("rerun: its keys do the same (←/→ 0.1 s, Shift 1 s, Ctrl next / previous event, Ctrl+Shift end / start), once each",
              all(abs(gotk[k] - w) < 1e-6 for k, w in keys.items()), {"got": gotk, "want": {k: round(v, 6) for k, v in keys.items()}})
        modes = {}
        for label in ("Loop selection", "Off", "Loop all"):
            page.click(f"{p} [data-act=loop]")
            page.locator(f"{p} .dv-pbv-menu [role=menuitemradio]", has_text=label).first.click()
            c = clock(page)
            modes[label] = {"loop": c["loop"], "range": c["range"]}
        check("rerun: the loop menu's three modes set the clock: selection (loop over a range), off (no loop), all (loop, no range)",
              modes["Loop selection"]["loop"] and modes["Loop selection"]["range"] and not modes["Off"]["loop"] and modes["Loop all"]["loop"] and modes["Loop all"]["range"] is None, modes)
        page.fill(f"{p} .dv-rr-speed", "2")
        page.press(f"{p} .dv-rr-speed", "Enter")
        rate = clock(page)["rate"]
        speed_text = page.input_value(f"{p} .dv-rr-speed")
        page.fill(f"{p} .dv-rr-time", "+4.5s")
        t_typed = clock(page)["t"]
        page.press(f"{p} .dv-rr-time", "Enter")
        sel_text = page.eval_on_selector(f"{p} .dv-rr-timeline select", "(s) => s.options[s.selectedIndex].textContent")
        check("rerun: typing 2 in the speed field sets the clock's rate (shown as 2.00x), typing +4.5s in the time field seeks to 4.5 s, and the timeline picker names the clock's time column (t)",
              rate == 2 and speed_text == "2.00x" and abs(t_typed - 4.5) < 1e-9 and sel_text == "t", {"rate": rate, "speed": speed_text, "t": t_typed, "timeline": sel_text})
        page.evaluate("() => document.querySelector('#example').clock.setRate(1)")
        seek(page, 2.0)
        page.click(f"{p} [data-act=play]")
        blue = page.eval_on_selector(f"{p} [data-act=play]", "(b) => getComputedStyle(b).backgroundColor")
        page.click(f"{p} [data-act=play]")
        idle = page.eval_on_selector(f"{p} [data-act=play]", "(b) => getComputedStyle(b).backgroundColor")
        series1 = page.evaluate("""(s) => { const i = document.createElement('i'); i.style.background = 'var(--dv-series-1)'; document.querySelector(s).append(i); const c = getComputedStyle(i).backgroundColor; i.remove(); return c; }""", p + " .dv-rr")
        check("rerun: the play button fills blue (the series-1 token, Rerun's blue) while playing, and not when paused", blue == series1 and idle != series1, {"playing": blue, "paused": idle, "series-1": series1})

    guard(ctx, "rerun", sec_rerun)

    # ---- P1 rerun-streams: the tree, the event bars, the playhead line, selection, the resizable tree
    def sec_rerun_streams():
        p = P("rerun-streams")
        so = streams_oracle()
        page.locator(p).scroll_into_view_if_needed()
        tree = page.evaluate("""(p) => [...document.querySelectorAll(p + ' [data-stream]')].map((r) => r.dataset.stream)""", p)
        want_ids = [x for name, (_, _, kids) in so.items() for x in [name] + [f"{name}/{k}" for k in kids]]
        check(f"rerun-streams: one tree row per dataset and per series ({len(want_ids)}: samples and tool by numeric column, media by clip)",
              sorted(tree) == sorted(want_ids), {"got": tree, "want": want_ids})
        ruler = rect(page, f"{p} .dv-rrs-ruler")
        bars = page.evaluate("""(p) => Object.fromEntries([...document.querySelectorAll(p + ' [data-lane]')].filter((l) => !l.dataset.lane.includes('/'))
          .map((l) => { const r = l.querySelector('.dv-rrs-ev').getBoundingClientRect(); return [l.dataset.lane, [r.left, r.right]]; }))""", p)
        clamp = lambda t: min(max(t, SPAN[0]), SPAN[1])
        offs = {n: [round(bars[n][0] - x_of(clamp(a), ruler), 2), round(bars[n][1] - x_of(clamp(b), ruler), 2)] for n, (a, b, _) in so.items() if n in bars}
        check("rerun-streams: each dataset's event bar spans its own min to max t on the ruler (media: first t0 to last t0 + duration, clipped to the clock's span), within 1 px",
              len(offs) == len(so) and all(abs(o) <= 1 for v in offs.values() for o in v), {"px off [left, right]": offs})
        seek(page, 4.0)
        tri, line = rect(page, f"{p} .dv-rrs-tri"), rect(page, f"{p} .dv-rrs-line")
        body = rect(page, f"{p} .dv-rrs-body")
        check("rerun-streams: the playhead line runs from the ruler down every row, under the triangle, at t (within 1 px)",
              abs(line["cx"] - x_of(4.0, ruler)) <= 1 and abs(tri["cx"] - line["cx"]) <= 1 and line["top"] <= body["top"] + 1 and line["bottom"] >= body["bottom"] - 1,
              {"line": round(line["cx"], 1), "triangle": round(tri["cx"], 1), "want": round(x_of(4.0, ruler), 1)})
        page.click(f"{p} [data-stream='tool']")
        sel = page.evaluate("""(p) => ({ row: document.querySelector(p + " [data-stream='tool']").classList.contains('dv-sel'), lane: document.querySelector(p + " [data-lane='tool']").classList.contains('dv-sel'),
          bg: getComputedStyle(document.querySelector(p + " [data-stream='tool']")).backgroundColor })""", p)
        VIS = """(p) => [...document.querySelectorAll(p + " [data-parent='samples']")].every((r) => r.getBoundingClientRect().height === 0)"""
        folded = page.evaluate(VIS, p)
        page.click(f"{p} [data-stream='samples'] .dv-rrs-tw")
        folded_after = page.evaluate(VIS, p)
        check("rerun-streams: a click selects a stream (its row and its lane highlighted), and the caret folds a dataset's children",
              sel["row"] and sel["lane"] and folded is False and folded_after is True, {**sel, "children hidden before / after the caret": [folded, folded_after]})
        page.click(f"{p} [data-stream='samples'] .dv-rrs-tw")
        align = page.evaluate("""(p) => [...document.querySelectorAll(p + ' [data-stream]')].filter((r) => r.getBoundingClientRect().height)
          .map((r) => { const l = document.querySelector(p + ` [data-lane="${CSS.escape(r.dataset.stream)}"]`); return [r.dataset.stream, Math.round((l ? l.getBoundingClientRect().top : NaN) - r.getBoundingClientRect().top)]; })""", p)
        check("rerun-streams: every shown tree row sits level with its event lane (folded rows take no room in either)",
              len(align) >= 3 and all(abs(o) <= 1 for _, o in align), align)
        split = rect(page, f"{p} .dv-splitter")
        w0 = rect(page, f"{p} .dv-rrs-tree")["width"]
        if split:
            page.mouse.move(split["cx"], split["cy"])
            page.mouse.down()
            page.mouse.move(split["cx"] + 60, split["cy"], steps=6)
            page.mouse.up()
        page.wait_for_timeout(100)
        w1 = rect(page, f"{p} .dv-rrs-tree")["width"]
        r1, l1 = rect(page, f"{p} .dv-rrs-ruler"), rect(page, f"{p} .dv-rrs-lanes")
        check("rerun-streams: the STREAMS tree is a resizable side panel: a 60 px drag on its edge widens it by 60 px and the ruler stays aligned with the event lanes",
              split is not None and abs((w1 - w0) - 60) <= 2 and abs(r1["left"] - l1["left"]) <= 1 and abs(r1["right"] - l1["right"]) <= 1,
              {"width": [round(w0), round(w1)], "ruler": [round(r1["left"]), round(r1["right"])], "lanes": [round(l1["left"]), round(l1["right"])]})
        page.mouse.dblclick(split["cx"] + 60, split["cy"]) if split else None
        ruler = rect(page, f"{p} .dv-rrs-ruler")
        page.keyboard.down("Shift")
        page.mouse.move(ruler["left"] + 0.2 * ruler["width"], ruler["cy"])
        page.mouse.down()
        page.mouse.move(ruler["left"] + 0.5 * ruler["width"], ruler["cy"], steps=6)
        page.mouse.up()
        page.keyboard.up("Shift")
        c = clock(page)
        want_r = [SPAN[0] + 0.2 * (SPAN[1] - SPAN[0]), SPAN[0] + 0.5 * (SPAN[1] - SPAN[0])]
        check("rerun-streams: Shift+drag on the ruler sets the loop selection over the dragged span (within one frame) and turns loop on",
              c["range"] is not None and all(abs(a - b) <= FRAME for a, b in zip(c["range"], want_r)) and c["loop"], {"range": c["range"], "want": [round(x, 3) for x in want_r]})
        page.evaluate("() => document.querySelector('#example').clock.setRange(null)")

    guard(ctx, "rerun-streams", sec_rerun_streams)

    # ---- P2 youtube: hover thumbnail of real frames, chapters, thicker on hover, keys, gear
    def sec_youtube():
        p = P("youtube")
        bar = rect(page, f"{p} .dv-yt-bar")
        thick0 = rect(page, f"{p} .dv-yt-chaps")["height"]
        pix = []
        for f in (0.25, 0.75):
            x = bar["left"] + f * bar["width"]
            page.mouse.move(x, bar["cy"])
            want_t = SPAN[0] + f * (SPAN[1] - SPAN[0])
            ok = ctx.until(page, """([s, t]) => { const c = document.querySelector(s + ' .dv-yt-frame'); return c && c.dataset.t && Math.abs(Number(c.dataset.t) - t) < 0.02; }""", [p, want_t], timeout=15000)
            pix.append(page.evaluate("""(s) => { const c = document.querySelector(s + ' .dv-yt-frame'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
              let lo = 255, hi = 0, sum = 0; for (let i = 0; i < d.length; i += 4) { const v = (d[i] + d[i + 1] + d[i + 2]) / 3; lo = Math.min(lo, v); hi = Math.max(hi, v); sum += v; }
              return { ok: true, t: Number(c.dataset.t), frame: Number(c.dataset.frame), range: hi - lo, mean: sum / (d.length / 4), data: Array.from(d.filter((_, i) => i % 4 !== 3)) }; }""", p) | {"arrived": ok})
        thick1 = rect(page, f"{p} .dv-yt-chaps")["height"]
        tip = page.evaluate("""(s) => { const t = document.querySelector(s + ' .dv-yt-tip'); return { hidden: t.hidden, time: t.querySelector('.dv-yt-tip-t').textContent, chapter: t.querySelector('.dv-yt-tip-ch').textContent }; }""", p)
        diff = None
        if len(pix) == 2 and pix[0].get("data") and pix[1].get("data"):
            a, b = pix[0]["data"], pix[1]["data"]
            diff = sum(1 for i in range(0, len(a), 3) if max(abs(a[i] - b[i]), abs(a[i + 1] - b[i + 1]), abs(a[i + 2] - b[i + 2])) > 24) / (len(a) / 3)
        summary = [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in x.items() if k != "data"} for x in pix]
        check("youtube: hovering the bar draws a real frame of the tuned clip into the tooltip's canvas (not blank: its pixels span > 40 levels), and a later hover time draws different pixels (> 1 % changed)",
              all(x.get("arrived") and x.get("range", 0) > 40 for x in pix) and diff is not None and diff > 0.01 and pix[0]["frame"] != pix[1]["frame"],
              {"frames": summary, "changed": diff and round(diff, 4)})
        check("youtube: the bar thickens under the pointer (3 to 5 px) and the tooltip says the hovered time and chapter", thick0 < thick1 and abs(thick1 - 5) < 0.6 and not tip["hidden"] and tip["time"] == "0:05",
              {"px": [thick0, thick1], "tip": tip})
        page.mouse.move(bar["left"], bar["top"] - 80)
        chaps = chapters_oracle()
        segs = page.evaluate("""(s) => [...document.querySelectorAll(s + ' .dv-yt-seg')].map((e) => e.getBoundingClientRect().left)""", p)
        seg_off = [round(x - x_of(t, bar), 2) for x, t in zip(segs, chaps)]
        check(f"youtube: chapters at the target's moves ({len(chaps)}, recomputed from samples.json): one bar segment each, starting at its time (within 1 px)",
              len(segs) == len(chaps) and all(abs(o) <= 1 for o in seg_off), {"chapters (s)": chaps, "px off": seg_off})
        buf = page.evaluate("""(s) => document.querySelector(s + ' .dv-yt-seg .dv-yt-buf').getBoundingClientRect().width""", p)
        check("youtube: the buffered range of the primary clip shows on the bar (the first segment's buffered fill is drawn)", buf > 1, round(buf, 1))
        page.mouse.click(bar["left"] + 0.5 * bar["width"], bar["cy"])   # use this card: its keys win
        ytk = {".": 3.0 + FRAME, ",": 3.0 - FRAME, "ArrowRight": 3.5, "ArrowLeft": 2.5, "l": 4.0, "j": 2.0}
        gy = {}
        for k, w in ytk.items():
            seek(page, 3.0)
            press(page, k)
            gy[k] = round(clock(page)["t"], 6)
        seek(page, 3.0)
        press(page, "k")
        k_on = clock(page)["playing"]
        press(page, "k")
        k_off = clock(page)["playing"]
        check("youtube: its keys: . and , step one frame, ←/→ 0.5 s, J/L 1 s, K plays and pauses",
              all(abs(gy[k] - w) < 1e-6 for k, w in ytk.items()) and k_on and not k_off, {"got": gy, "want": {k: round(v, 6) for k, v in ytk.items()}, "k": [k_on, k_off]})
        page.click(f"{p} [data-act=settings]")
        page.locator(f"{p} .dv-pbv-menu [role=menuitem]", has_text="Playback speed").first.click()
        page.locator(f"{p} .dv-pbv-menu [role=menuitemradio]", has_text="1.5").first.click()
        r15 = clock(page)["rate"]
        page.click(f"{p} [data-act=settings]")
        page.locator(f"{p} .dv-pbv-menu [role=menuitem]", has_text="Loop").first.click()
        lp = clock(page)["loop"]
        page.click(f"{p} [data-act=settings]")
        page.locator(f"{p} .dv-pbv-menu [role=menuitem]", has_text="Loop").first.click()
        check("youtube: the gear menu sets the playback speed (1.5) and toggles loop", r15 == 1.5 and lp is False and clock(page)["loop"] is True, {"rate": r15, "loop after one toggle": lp})
        page.evaluate("() => document.querySelector('#example').clock.setRate(1)")

    guard(ctx, "youtube", sec_youtube)

    # ---- P3 tracks: filmstrips of real frames, sparklines, the work area, the resizable headers
    def sec_tracks():
        p = P("tracks")
        page.locator(p).scroll_into_view_if_needed()
        ctx.until(page, """(s) => [...document.querySelectorAll(s + ' .dv-tk-v')].every((t) => t.querySelectorAll('canvas[data-frame]').length >= 4)""", p, timeout=20000)
        strips = page.evaluate("""(s) => [...document.querySelectorAll(s + ' .dv-tk-v')].map((t) => { const cs = [...t.querySelectorAll('canvas[data-frame]')];
          const lit = cs.filter((c) => { const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let lo = 255, hi = 0;
            for (let i = 0; i < d.length; i += 16) { const v = (d[i] + d[i + 1] + d[i + 2]) / 3; lo = Math.min(lo, v); hi = Math.max(hi, v); } return hi - lo > 40; });
          return { drawn: lit.length, frames: new Set(cs.map((c) => c.dataset.frame)).size }; })""", p)
        check(f"tracks: one video track per clip ({len(MEDIA)}), each a filmstrip of >= 4 real frames (drawn canvases, not blank, distinct frame indices)",
              len(strips) == len(MEDIA) and all(s["drawn"] >= 4 and s["frames"] >= 4 for s in strips), strips)
        sp = page.evaluate("""(s) => [...document.querySelectorAll(s + ' .dv-tk-d')].map((t) => [...t.querySelectorAll('path')].map((p) => p.getTotalLength() > 50 ? p.getAttribute('stroke') : null))""", p)
        check("tracks: one sparkline track per time series card (2), one line per series in its palette colour",
              len(sp) == 2 and all(len(x) >= 2 and all(x) for x in sp) and "#2a78d6" in sp[0], sp)
        work = rect(page, f"{p} .dv-tk-work")
        page.mouse.move(work["left"] + 0.25 * work["width"], work["cy"])
        page.mouse.down()
        page.mouse.move(work["left"] + 0.6 * work["width"], work["cy"], steps=6)
        page.mouse.up()
        c = clock(page)
        want_r = [SPAN[0] + 0.25 * (SPAN[1] - SPAN[0]), SPAN[0] + 0.6 * (SPAN[1] - SPAN[0])]
        wa = rect(page, f"{p} .dv-tk-wa")
        check("tracks: a drag over the work-area lane sets the clock's range (the loop) to the dragged span (within one frame), drawn where it was dragged",
              c["range"] and all(abs(a - b) <= FRAME for a, b in zip(c["range"], want_r)) and abs(wa["left"] - x_of(c["range"][0], work)) <= 1,
              {"range": c["range"], "want": [round(x, 3) for x in want_r]})
        page.dblclick(f"{p} .dv-tk-work")
        cleared = clock(page)["range"]
        sp_box = rect(page, f"{p} .dv-splitter")
        h0 = rect(page, f"{p} .dv-tk-heads")["width"]
        if sp_box:
            page.mouse.move(sp_box["cx"], sp_box["cy"])
            page.mouse.down()
            page.mouse.move(sp_box["cx"] + 40, sp_box["cy"], steps=5)
            page.mouse.up()
        h1 = rect(page, f"{p} .dv-tk-heads")["width"]
        check("tracks: a double-click clears the work area; the track headers are a resizable side panel (a 40 px drag widens them by 40 px)",
              cleared is None and sp_box is not None and abs((h1 - h0) - 40) <= 2, {"range after dblclick": cleared, "headers": [round(h0), round(h1)]})
        if sp_box:
            page.mouse.dblclick(sp_box["cx"] + 40, sp_box["cy"])

    guard(ctx, "tracks", sec_tracks)

    # ---- P4 foxglove: the time format, speed, loop, loaded ranges
    def sec_foxglove():
        p = P("foxglove")
        seek(page, 3.2)
        fmt = {}
        for label in ("Elapsed", "Seconds"):
            page.click(f"{p} [data-act=format]")
            page.locator(f"{p} .dv-pbv-menu [role=menuitemradio]", has_text=label).first.click()
            fmt[label] = page.inner_text(f"{p} .dv-fx-now")
        page.click(f"{p} [data-act=speed]")
        page.locator(f"{p} .dv-pbv-menu [role=menuitemradio]", has_text="2×").first.click()
        r2 = clock(page)["rate"]
        page.click(f"{p} [data-act=loop]")
        lp = clock(page)["loop"]
        page.click(f"{p} [data-act=loop]")
        check("foxglove: the time display switches between seconds (3.200) and elapsed (00:03.200); the speed menu sets 2×; the loop button toggles the clock's loop",
              fmt == {"Elapsed": "00:03.200", "Seconds": "3.200"} and r2 == 2 and lp is False and clock(page)["loop"], {"format": fmt, "rate": r2, "loop": lp})
        page.evaluate("() => document.querySelector('#example').clock.setRate(1)")
        sc, ld = rect(page, f"{p} .dv-fx-track"), page.evaluate("""(s) => [...document.querySelectorAll(s + ' .dv-fx-loaded i')].map((i) => { const r = i.getBoundingClientRect(); return [r.left, r.right]; })""", p)
        check("foxglove: the scrubber shows the loaded range: every dataset spans the whole clock, so one band edge to edge (within 1 px)",
              len(ld) == 1 and abs(ld[0][0] - sc["left"]) <= 1 and abs(ld[0][1] - sc["right"]) <= 1, {"loaded": [[round(a), round(b)] for a, b in ld], "track": [round(sc["left"]), round(sc["right"])]})

    guard(ctx, "foxglove", sec_foxglove)

    # ---- P5 range: the brush sets clock.window; the time series zoom to it
    def sec_range():
        p = P("range")
        m = rect(page, f"{p} .dv-rg-map")
        page.mouse.move(m["left"] + 0.2 * m["width"], m["cy"])
        page.mouse.down()
        page.mouse.move(m["left"] + 0.6 * m["width"], m["cy"], steps=8)
        page.mouse.up()
        c = clock(page)
        want_w = [SPAN[0] + 0.2 * (SPAN[1] - SPAN[0]), SPAN[0] + 0.6 * (SPAN[1] - SPAN[0])]
        br = rect(page, f"{p} .dv-rg-brush")
        check("range: a drag across the overview sets clock.window to the brushed span (within one frame), and the brush is drawn over it (within 1 px)",
              c["window"] and all(abs(a - b) <= FRAME for a, b in zip(c["window"], want_w)) and abs(br["left"] - x_of(c["window"][0], m)) <= 1 and abs(br["right"] - x_of(c["window"][1], m)) <= 1,
              {"window": c["window"], "want": [round(x, 3) for x in want_w]})
        page.click(f"{p} [data-act=zoomout]")
        check("range: Zoom out clears the window", clock(page)["window"] is None, clock(page)["window"])
        spark = page.evaluate("""(s) => [...document.querySelectorAll(s + ' .dv-rg-spark path')].map((p) => p.getAttribute('stroke'))""", p)
        check("range: the overview draws the main time series (Step response): one line per situation in its palette colour", sorted(spark) == sorted(["#8b9099", "#e8743b", "#2a78d6"]), spark)

    guard(ctx, "range", sec_range)

    # ---- the switcher: only on the card that asks for it; switches live; remembered after a reload
    def sec_switcher():
        shown = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#example .dd-panel[data-type=playback]')].map((s) => [s.dataset.panel, s.querySelector('.dv-pbv-foot').getBoundingClientRect().height > 0]))""")
        sw = f"{P('playback')} .dv-pbv-switch select"
        opts = page.eval_on_selector(sw, "(s) => [...s.options].map((o) => o.value)")
        check("switcher: only the card with switcher: true shows it, listing the seven variants", shown == {k: k == "playback" for k in shown} and opts == list(VARIANTS), {"shown": shown, "options": opts})
        page.select_option(sw, "youtube")
        live = page.evaluate("""(s) => { const v = document.querySelector(s + ' .dv-view-playback'); return { variant: v.dataset.variant, yt: !!v.querySelector('.dv-yt'), bar: !!v.querySelector('.dv-pb') }; }""", P("playback"))
        page.reload()
        ready(page)
        kept = page.evaluate("""(s) => { const v = document.querySelector(s + ' .dv-view-playback'); return { variant: v.dataset.variant, yt: !!v.querySelector('.dv-yt'), select: v.querySelector('select').value }; }""", P("playback"))
        check("switcher: picking YouTube swaps the card live, and the pick is still there after a reload (localStorage)",
              live == {"variant": "youtube", "yt": True, "bar": False} and kept == {"variant": "youtube", "yt": True, "select": "youtube"}, {"live": live, "after reload": kept})
        page.select_option(sw, "bar")
    guard(ctx, "switcher", sec_switcher)

    page.context.close()

    # ---- screenshots: every variant, light and dark at 1440; the page at 390 has no sideways scroll
    for dark in (False, True):
        page = ctx.page(path, width=1440, height=1000, dark=dark)
        ready(page)
        seek(page, 3.2)
        for variant in VARIANTS:
            shoot(ctx, page, variant, "dark" if dark else "light")
        page.context.close()
    for dark in (False, True):
        page = ctx.page(path, width=390, height=844, dark=dark, mobile=True)
        ready(page)
        seek(page, 3.2)
        sw_ = page.evaluate("document.scrollingElement.scrollWidth")
        over = page.evaluate("""() => [...document.querySelectorAll('#example .dd-panel[data-type=playback]')].map((s) => [s.dataset.panel, Math.round(s.getBoundingClientRect().right), s.scrollWidth > s.clientWidth + 1]).filter((x) => x[1] > 390 || x[2])""")
        check(f"proposals, {'dark' if dark else 'light'}, 390 px: no sideways page scroll and no playback card wider than the screen", sw_ <= 390 and not over, {"scrollWidth": sw_, "overflowing": over})
        for variant in VARIANTS:
            shoot(ctx, page, variant, f"{'dark' if dark else 'light'}-390")
        page.context.close()
