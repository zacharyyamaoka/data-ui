"""The media cards' checks (video, video-compare, image; docs/peps/0005-dashboard-cards.md §2b, §4).

Loaded by checks.py beside it. Every expected number comes from media.json and views.base (the oracle): a video's
time is the clock's t minus the row's t0, within one frame (1 / the row's fps)."""

import re
import pathlib
from urllib.parse import urljoin

HERE = pathlib.Path(__file__).parent
BASE = (HERE / "views.base").read_text(encoding="utf-8")


def _overlay_oracle():
    """The Overlay view's overlay: block, read from views.base as written."""
    m = re.search(r"name: Overlay\n(?:.*\n)*?\s+overlay: \{([^}]*)\}", BASE)
    return dict((k.strip(), v.strip()) for k, v in (kv.split(":", 1) for kv in m.group(1).split(",")))


def _videos(page, scope):
    # src: the clip's URL (data-src; the element may play a local blob: copy of it when the server has no Range support)
    return page.evaluate("""(s) => [...document.querySelectorAll(s + ' video[data-t0]')].map((v) => ({
      src: v.dataset.src || null, el: v.getAttribute('src'), currentSrc: v.currentSrc, poster: v.poster, t0: Number(v.dataset.t0), preload: v.preload,
      ready: v.readyState, seeking: v.seeking, t: v.currentTime, paused: v.paused, duration: v.duration }))""", scope)


def _settled(ctx, page, scope="#example"):
    """Every loaded video on the page has finished seeking (waits for the `seeked` that a clock seek starts)."""
    return ctx.until(page, """(s) => [...document.querySelectorAll(s + ' video[data-t0]')].every((v) => v.readyState >= 2 && !v.seeking)""", scope, timeout=10000)


def _loaded(ctx, page, key, D):
    page.locator(f"{D} .dd-panel[data-panel='{key}']").scroll_into_view_if_needed()
    return ctx.until(page, """(s) => { const vs = [...document.querySelectorAll(s + ' video[data-t0]')];
      return vs.length && vs.every((v) => v.dataset.src && v.readyState >= 2 && v.seekable.length && v.seekable.end(0) >= v.duration - 0.05); }""", f"{D} .dd-panel[data-panel='{key}']", timeout=15000)


def _clip_right(clip):
    """inset(0px 50% 0px 0px) -> 50.0 (the right inset, in percent); None for anything else."""
    m = re.match(r"inset\(\s*0(?:px)?\s+([\d.]+)%", clip or "")
    return float(m.group(1)) if m else None


def _overlay_geom(page, D):
    return page.evaluate("""(D) => { const p = document.querySelector(D + " .dd-panel[data-panel='overlay']");
      const root = p.querySelector('.dv-media-compare'), stage = p.querySelector('.dv-media-stage');
      const a = p.querySelector('video.dv-media-a'), b = p.querySelector('video.dv-media-b'), h = p.querySelector('.dv-media-handle');
      const r = (e) => { if (!e) return null; const x = e.getBoundingClientRect(); return { left: x.left, right: x.right, top: x.top, width: x.width, height: x.height }; };
      const cs = a && getComputedStyle(a);
      return { mode: root && root.dataset.mode, stage: r(stage), a: r(a), b: r(b), handle: r(h), handleShown: !!h && getComputedStyle(h).display !== 'none',
        clip: cs && cs.clipPath, opacity: cs && Number(cs.opacity), blend: cs && cs.mixBlendMode,
        view: p.querySelector('data-views').view.overlay, caption: (p.querySelector('.dv-media-cap') || {}).textContent || '' }; }""", D)


def _click(page, selector):
    """Click when the element is there (a missing one is the check's FAIL, not a crash)."""
    if page.locator(selector).count():
        page.locator(selector).first.click()


def run(ctx, path, helpers):
    D, rows, ready, seek, clock = helpers["D"], helpers["rows"], helpers["ready"], helpers["seek"], helpers["clock"]
    media = rows("media.json")
    tuned = next(r for r in media if r["situation"] == "tuned")
    factory = next(r for r in media if r["situation"] == "factory")
    ov = _overlay_oracle()
    split0 = float(ov.get("split", 0.5))

    # ---- the tuned video follows the clock, within one frame, at three instants
    page = ctx.page(path, width=1440, height=1000)
    ready(page)
    loaded = _loaded(ctx, page, "tuned-video", D)
    v = _videos(page, f"{D} .dd-panel[data-panel='tuned-video']")
    want_src, want_poster = urljoin(page.url, tuned["src"]), urljoin(page.url, tuned["poster"])
    one = v[0] if v else {}
    ctx.check("media video: the Tuned video card is a video[data-t0] whose src is media.json's tuned clip (resolved against the data file), with its poster and t0; it loads seekable end to end with media.json's duration",
              loaded and len(v) == 1 and one.get("src") == want_src and (one.get("el") == want_src or (one.get("el") or "").startswith("blob:"))
              and one.get("poster") == want_poster and one.get("t0") == tuned["t0"] and abs(one.get("duration", 0) - tuned["duration"]) <= 1 / tuned["fps"],
              {"loaded": loaded, "got": {k: one.get(k) for k in ("src", "el", "poster", "t0", "ready", "duration")}, "want": [want_src, want_poster, tuned["t0"], tuned["duration"]]})
    frame = 1 / tuned["fps"]
    got = []
    for t in (1.0, 3.5, 6.2):
        seek(page, t)
        _settled(ctx, page, f"{D} .dd-panel[data-panel='tuned-video']")
        cur = (_videos(page, f"{D} .dd-panel[data-panel='tuned-video']") or [{"t": float("nan")}])[0]["t"]
        got.append({"t": t, "currentTime": round(cur, 4), "off": round(abs(cur - (t - tuned["t0"])), 4)})
    ctx.check(f"media video: after a clock seek to 1.0, 3.5 and 6.2 s the video's currentTime is t - t0 within one frame ({frame:.4f} s)",
              all(g["off"] <= frame for g in got), got)
    hud = page.evaluate(f"""() => {{ const p = document.querySelector("{D} .dd-panel[data-panel='tuned-video']");
      return {{ time: (p.querySelector('.dv-media-time') || {{}}).textContent, glyph: !!p.querySelector('.dv-media-glyph') && getComputedStyle(p.querySelector('.dv-media-glyph')).display !== 'none',
        controls: (p.querySelector('video') || {{}}).controls ?? null, cap: (p.querySelector('.dv-media-cap') || {{}}).textContent || '' }}; }}""")
    ctx.check("media video: no native controls; paused, the overlay shows the play glyph and the clock's time (6.20 s); the caption names the clip and says it is a sim render",
              hud["controls"] is False and hud["glyph"] and (hud["time"] or "").startswith("6.20") and "tuned" in hud["cap"] and "sim render" in hud["cap"], hud)

    # ---- play ~1.2 s: the primary video drives t; after the pause every video lands on t - t0 within one frame
    _loaded(ctx, page, "overlay", D)
    seek(page, 1.0)
    _settled(ctx, page)
    before = clock(page)["t"]
    page.evaluate(f"() => document.querySelector('{D}').clock.play()")
    page.wait_for_timeout(600)
    driver = page.evaluate(f"() => {{ const c = document.querySelector('{D}').clock; return c.driver && c.driver.id; }}")
    page.wait_for_timeout(600)
    page.evaluate(f"() => document.querySelector('{D}').clock.pause()")
    _settled(ctx, page)
    after = clock(page)
    vids = _videos(page, D)
    offs = [round(abs(x["t"] - (after["t"] - x["t0"])), 4) for x in vids]
    ctx.check("media play: 1.2 s of play advances the clock by >= 0.8 s, the tuned video (primary) drives t while it plays, and after the pause all three videos sit on t - t0 within one frame",
              after["t"] - before >= 0.8 and not after["playing"] and driver is not None and len(vids) == 3 and all(o <= frame for o in offs) and all(x["paused"] for x in vids),
              {"t": [round(before, 3), round(after["t"], 3)], "driver": driver, "offs": offs, "paused": [x["paused"] for x in vids]})
    # a click on the video toggles the clock
    _click(page, f"{D} .dd-panel[data-panel='tuned-video'] .dv-media-frame")
    playing = clock(page)["playing"]
    _click(page, f"{D} .dd-panel[data-panel='tuned-video'] .dv-media-frame")
    ctx.check("media video: a click on the video plays the clock, a second click pauses it", playing and not clock(page)["playing"], {"after first click": playing})

    # ---- the overlay: wipe at split, the handle drags, the modes switch and persist through host.setView
    g = _overlay_geom(page, D)
    hx = g["handle"]["left"] + g["handle"]["width"] / 2 if g["handle"] else None
    sx = g["stage"]["left"] + split0 * g["stage"]["width"] if g["stage"] else None
    ctx.check(f"media overlay: default mode {ov.get('mode')}: A is clipped to inset(0 {100 - split0 * 100:g}% 0 0) and the handle's centre is at {split0 * 100:g}% of the picture (±1 px)",
              g["mode"] == ov.get("mode") and _clip_right(g["clip"]) is not None and abs(_clip_right(g["clip"]) - (100 - split0 * 100)) < 0.01 and hx is not None and abs(hx - sx) <= 1,
              {"mode": g["mode"], "clip": g["clip"], "handle x": hx, "want x": sx})
    if g["handle"]:
        y = g["handle"]["top"] + g["handle"]["height"] / 2
        page.mouse.move(hx, y)
        page.mouse.down()
        page.mouse.move(g["stage"]["left"] + 0.4 * g["stage"]["width"], y, steps=4)
        page.mouse.move(g["stage"]["left"] + 0.25 * g["stage"]["width"], y, steps=4)
        page.mouse.up()
    ctx.until(page, f"""() => {{ const o = document.querySelector("{D} .dd-panel[data-panel='overlay'] data-views").view.overlay; return o && Math.abs(o.split - 0.25) < 0.01; }}""", timeout=3000)
    g = _overlay_geom(page, D)
    hx = g["handle"]["left"] + g["handle"]["width"] / 2 if g["handle"] else None
    ctx.check("media overlay: dragging the handle to 25% moves the clip (inset right 75%) and the handle with it, and the view entry's overlay.split becomes 0.25 (host.setView)",
              _clip_right(g["clip"]) is not None and abs(_clip_right(g["clip"]) - 75) < 1 and hx is not None and abs(hx - (g["stage"]["left"] + 0.25 * g["stage"]["width"])) <= 1
              and abs((g["view"] or {}).get("split", -1) - 0.25) < 0.01,
              {"clip": g["clip"], "handle x": hx, "view": g["view"]})
    if page.locator(f"{D} .dd-panel[data-panel='overlay'] .dv-media-handle").count():
        page.locator(f"{D} .dd-panel[data-panel='overlay'] .dv-media-handle").focus()
        page.keyboard.press("ArrowRight")
    k = _clip_right(_overlay_geom(page, D)["clip"])
    ctx.check("media overlay: → on the focused handle moves the wipe 5% right", k is not None and abs(k - 70) < 1, {"clip right %": k})

    def mode(m):
        _click(page, f"{D} .dd-panel[data-panel='overlay'] .dv-media-modes button[data-mode='{m}']")
        ctx.until(page, f"""(m) => document.querySelector("{D} .dd-panel[data-panel='overlay'] data-views").view.overlay.mode === m""", m, timeout=3000)
        ctx.frames(page)
        return _overlay_geom(page, D)

    g = mode("onion")
    split = (g["view"] or {}).get("split")
    ctx.check("media overlay: onion: A is unclipped with opacity = split, and the view entry says mode onion",
              g["mode"] == "onion" and g["clip"] in ("none", None) and split is not None and g["opacity"] is not None and abs(g["opacity"] - split) < 0.01 and not g["handleShown"],
              {"mode": g["mode"], "clip": g["clip"], "opacity": g["opacity"], "split": split})
    g = mode("difference")
    ctx.check("media overlay: difference: A blends with mix-blend-mode difference at full opacity",
              g["mode"] == "difference" and g["blend"] == "difference" and g["opacity"] == 1 and g["clip"] in ("none", None), {"blend": g["blend"], "opacity": g["opacity"]})
    g = mode("side")
    a, b = g["a"], g["b"]
    ctx.check("media overlay: side: the two videos sit side by side, equal widths (±1 px), no overlap, same top; the view entry keeps mode side",
              a and b and abs(a["width"] - b["width"]) <= 1 and a["right"] <= b["left"] + 0.5 and abs(a["top"] - b["top"]) <= 1 and a["width"] > 50 and (g["view"] or {}).get("mode") == "side",
              {"a": a, "b": b, "view": g["view"]})
    want = "sim render vs real camera" if tuned["basis"] != factory["basis"] else "sim render"
    ctx.check("media overlay: the caption names A and B by their situation and states both clips' basis (sim render vs real camera only when they differ)",
              f"A: {ov.get('a')}" in g["caption"] and f"B: {ov.get('b')}" in g["caption"] and want in g["caption"] and (" vs " in g["caption"]) == (tuned["basis"] != factory["basis"]),
              g["caption"])

    # ---- the image card
    page.locator(f"{D} .dd-panel[data-panel='poster']").scroll_into_view_if_needed()
    ctx.until(page, f"""() => {{ const i = document.querySelector("{D} .dd-panel[data-panel='poster'] img"); return i && i.complete && i.naturalWidth > 0; }}""", timeout=10000)
    im = page.evaluate(f"""() => {{ const p = document.querySelector("{D} .dd-panel[data-panel='poster']"), i = p.querySelector('img');
      return i ? {{ n: p.querySelectorAll('img').length, w: i.naturalWidth, src: i.src, loading: i.loading, fit: getComputedStyle(i).objectFit,
        cap: (p.querySelector('figcaption') || {{}}).textContent }} : null; }}""")
    ctx.check("media image: the Poster card loads media.json's factory poster (natural size > 0, lazy, object-fit contain) captioned with the row's note",
              im and im["n"] == 1 and im["w"] > 0 and im["src"] == urljoin(page.url, factory["poster"]) and im["loading"] == "lazy" and im["fit"] == "contain" and im["cap"] == factory["note"],
              im and {**im, "cap": (im["cap"] or "")[:60]})
    page.context.close()

    # ---- lazy at 390 px: the overlay card below the fold has no src until it nears the viewport; light and dark looks
    for dark in (False, True):
        theme = "dark" if dark else "light"
        page = ctx.page(path, width=390, height=844, dark=dark, mobile=True)
        ready(page)
        before = _videos(page, f"{D} .dd-panel[data-panel='overlay']")
        _loaded(ctx, page, "overlay", D)
        after = _videos(page, f"{D} .dd-panel[data-panel='overlay']")
        sw = page.evaluate("document.scrollingElement.scrollWidth")
        st = page.evaluate(f"""() => {{ const e = document.querySelector("{D} .dd-panel[data-panel='overlay'] .dv-media-stage"); if (!e) return [-1, -1]; const s = e.getBoundingClientRect(); return [s.left, s.right]; }}""")
        if not dark:
            ctx.check("media lazy (390 px): the overlay's two videos below the fold have no src and preload none; scrolled near, both get src and preload auto",
                      len(before) == 2 and all(x["src"] is None and x["el"] is None and x["preload"] == "none" for x in before) and len(after) == 2 and all(x["src"] and x["preload"] == "auto" for x in after),
                      {"before": [(x["src"], x["preload"]) for x in before], "after": [(bool(x["src"]), x["preload"]) for x in after]})
        ink = page.evaluate(f"""() => {{ const e = document.querySelector("{D} .dd-panel[data-panel='overlay'] .dv-media-frame"); return e ? getComputedStyle(e).backgroundColor : 'none'; }}""")
        rgb = [int(x) for x in re.findall(r"\d+", ink)[:3]]
        lum = sum(rgb) / (3 * 255) if len(rgb) == 3 else 1
        ctx.check(f"media 390 px {theme}: no sideways page scroll, the overlay picture fits the screen, and its letterbox is dark",
                  sw <= 390 and st[0] >= 0 and st[1] <= 390 and lum < 0.2, {"scrollWidth": sw, "stage": st, "letterbox": ink})
        ctx.shot(page, f"media-{theme}-390")
        page.context.close()
        page = ctx.page(path, width=1440, height=1000, dark=dark)
        ready(page)
        _loaded(ctx, page, "tuned-video", D)
        _loaded(ctx, page, "overlay", D)
        seek(page, 3.5)
        _settled(ctx, page)
        page.locator(f"{D} .dd-panel[data-panel='tuned-video']").scroll_into_view_if_needed()
        page.evaluate(f"""() => document.querySelector("{D} .dd-panel[data-panel='tuned-video']").scrollIntoView({{ block: 'start' }})""")
        ctx.frames(page)
        ctx.shot(page, f"media-{theme}-1440")
        page.locator(f"{D} .dd-panel[data-panel='poster']").scroll_into_view_if_needed()
        ctx.frames(page)
        ctx.shot(page, f"media-poster-{theme}-1440")
        page.context.close()
