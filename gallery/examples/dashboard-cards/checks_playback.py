"""The playback card's default (docs/peps/0005-dashboard-cards.md §4b): with no playback.variant the catalog's card is
still the bar, with no switcher and none of the proposals' keys, and it still drives the clock. The proposals
themselves are checked in gallery/examples/playback-proposals/checks.py.

Loaded by checks.py beside it. Expected numbers come from samples.json and views.base (the oracle): the clock spans
samples' t, a frame is 1 / fps."""

import pathlib
import re

HERE = pathlib.Path(__file__).parent
FPS = int(re.search(r"^\s+fps:\s*(\d+)", (HERE / "views.base").read_text(encoding="utf-8"), re.M).group(1))


def run(ctx, path, h):
    check, D = ctx.check, h["D"]
    ts = [r["t"] for r in h["rows"]("samples.json")]
    a, b = min(ts), max(ts)
    frame = 1 / FPS
    pb = f"{D} .dd-panel[data-panel='playback']"
    page = ctx.page(path, width=1440, height=1000)
    h["ready"](page)
    page.locator(pb).scroll_into_view_if_needed()
    got = page.evaluate("""(s) => { const v = document.querySelector(s + ' .dv-view-playback'), foot = v && v.querySelector('.dv-pbv-foot');
      const dash = document.querySelector('#example');
      return { variant: v && v.dataset.variant, bar: !!(v && v.querySelector('.dv-pb .dv-pb-track')), others: !!(v && v.querySelector('.dv-rr, .dv-yt, .dv-tk, .dv-fx, .dv-rg')),
        switcher: !!foot && foot.getBoundingClientRect().height > 0, keyOwners: (dash._dvPbKeys || []).length }; }""", pb)
    check("playback default: no playback.variant draws the bar (none of the proposals), with no switcher on the card and no proposal holding the dashboard's keys",
          got == {"variant": "bar", "bar": True, "others": False, "switcher": False, "keyOwners": 0}, got)

    page.click(f"{pb} [data-act=play]")
    on = h["clock"](page)["playing"]
    page.click(f"{pb} [data-act=play]")
    off = h["clock"](page)["playing"]
    check("playback default: the bar's play button starts the clock and a second click pauses it", on is True and off is False, [on, off])

    tr = page.locator(f"{pb} .dv-pb-track").bounding_box()
    page.mouse.click(tr["x"] + 0.3 * tr["width"], tr["y"] + tr["height"] / 2)
    t = h["clock"](page)["t"]
    check("playback default: a click at 30 % of the track seeks there (within one frame)", abs(t - (a + 0.3 * (b - a))) <= frame + 1e-6, round(t, 4))

    offs = []
    for want in (1.5, 5.25, b):
        h["seek"](page, want)
        g = page.evaluate("""(s) => { const tr = document.querySelector(s + ' .dv-pb-track').getBoundingClientRect(), th = document.querySelector(s + ' [data-thumb]').getBoundingClientRect();
          return { x: th.left + th.width / 2, left: tr.left, w: tr.width, t: document.querySelector('#example').clock.t }; }""", pb)
        offs.append(round(g["x"] - (g["left"] + (g["t"] - a) / (b - a) * g["w"]), 2))
    check("playback default: after seeks to 1.5, 5.25 and the end the thumb's centre sits at t (within 1 px)", all(abs(o) <= 1 for o in offs), offs)

    h["seek"](page, 3.0)
    page.locator(f"{D} .dd-panel[data-panel='playback'] .dv-pb-time").click()
    page.keyboard.press("ArrowRight")
    t1 = h["clock"](page)["t"]
    check("playback default: the dashboard's own ← / → still steps one frame (no proposal took the key)", abs(t1 - (3.0 + frame)) < 1e-6, round(t1, 6))
    page.context.close()
