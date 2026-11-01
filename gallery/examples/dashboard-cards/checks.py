"""Browser checks for the card catalog (docs/peps/0005-dashboard-cards.md). This file only loads every
checks_<lane>.py beside it and runs its run(ctx, path, helpers), so each card lane owns its own checks file and no
two lanes edit one file. Shared helpers for them are below: wait for the dashboard, read a panel, seek the clock.

Every expected number is computed from the case's JSON (the oracle), never read from the page's model."""

import importlib.util
import json
import pathlib

HERE = pathlib.Path(__file__).parent
D = "#example"


def rows(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))["rows"]


def ready(page, extra_ms=500):
    """The dashboard has drawn every panel's view (data-view set on each panel's <data-views>)."""
    page.wait_for_selector(f"{D} .dd-panel", timeout=20000)
    page.wait_for_function("""() => { const els = [...document.querySelectorAll('#example .dd-panel data-views')];
      return els.length && els.every((e) => e.dataset.view); }""", timeout=30000)
    page.wait_for_timeout(extra_ms)


def panel(page, key):
    """A panel's section locator by its key (the slug of its view name, e.g. 'step-response')."""
    return page.locator(f"{D} .dd-panel[data-panel='{key}']")


def seek(page, t):
    """Seek the dashboard's clock (the only writer of t) and wait two frames for every follower to draw."""
    page.evaluate("(t) => document.querySelector('#example').clock.seek(t)", t)
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")


def clock(page):
    return page.evaluate("""() => { const c = document.querySelector('#example').clock;
      return { t: c.t, start: c.start, end: c.end, playing: c.playing, rate: c.rate, loop: c.loop, range: c.range, window: c.window }; }""")


HELPERS = {"rows": rows, "ready": ready, "panel": panel, "seek": seek, "clock": clock, "D": D}


def run(ctx, path):
    for f in sorted(HERE.glob("checks_*.py")):
        spec = importlib.util.spec_from_file_location(f"dashboard_cards_{f.stem}", f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.run(ctx, path, HELPERS)
