"""Browser checks for the live robot case (docs/peps/0012-live-data.md): a SIMULATED arm streams into four live datasets.
Oracles are the page's own datasets (the rows simulate.js pushed), read through their public API (latestAt, rowCount)."""

import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from dashboard_helpers import D, ready  # noqa: E402


def run(ctx, path):
    page = ctx.page(path, width=1440, height=1100)
    ready(page)
    # six seconds of data: the temperatures come twice a second, so 2 s back still has a dozen rows per joint
    page.wait_for_function(f"() => document.querySelector('{D}').datasets.joints.rowCount > 9000", timeout=30000)
    s = page.evaluate(f"""() => {{ const d = document.querySelector('{D}');
      return {{ line: d.querySelector('data-live-status')?.textContent || '', state: d.querySelector('data-live-status')?.dataset.state,
               following: d.clock.following, hash: location.hash, rows: d.datasets.joints.rowCount }}; }}""")
    ctx.check("live robot: streaming, following, the line says the source is simulated", s["state"] == "live" and "simulated" in s["line"] and s["following"] and "t=live" in s["hash"], s)
    a = page.evaluate(f"() => document.querySelector('{D}').datasets.joints.rowCount")
    page.wait_for_timeout(1000)
    b = page.evaluate(f"() => document.querySelector('{D}').datasets.joints.rowCount")
    ctx.check("live robot: about 1,500 joint samples a second arrive (3 joints at 500 Hz)", 900 <= b - a <= 2100, b - a)
    # the KPI cards at t: each joint's newest temperature (latest-at)
    page.evaluate(f"() => document.querySelector('{D}').clock.seek(document.querySelector('{D}').clock.liveEnd - 2)")
    ctx.frames(page, 3)
    k = page.evaluate(f"""() => {{ const d = document.querySelector('{D}');
      return [...d.querySelectorAll('[aria-label="Motor temperature"] .dv-kpi-card')].map((c) => {{
        const label = c.querySelector('.dv-kpi-label').textContent.trim(), num = c.querySelector('.dv-kpi-num');
        const want = d.datasets.thermal.latestAt(d.clock.t, label);
        return {{ label, shown: parseFloat(num.dataset.exact || num.getAttribute('title') || num.textContent), want: want && want.temp_c }}; }}); }}""")
    ctx.check("live robot: paused 2 s back, each temperature card is its joint's newest value at t", len(k) == 3 and all(x["want"] is not None and abs(x["shown"] - x["want"]) < 1e-9 for x in k), k)
    live = page.evaluate(f"() => {{ const b = document.querySelector('{D} .dv-pb-live'); return {{ pressed: b.getAttribute('aria-pressed'), text: b.textContent }}; }}")
    ctx.check("live robot: paused, ● LIVE is up and says how far behind it is", live["pressed"] == "false" and "−" in live["text"], live)
    page.click(f"{D} .dv-pb-live")
    ctx.frames(page, 2)
    ctx.check("live robot: one click on ● LIVE follows again", page.evaluate(f"() => document.querySelector('{D}').clock.following"))
    page.context.close()
    themes(ctx, path)


def themes(ctx, path):
    """Light and dark at 1440 and 390 px, as dashboard_helpers.themes() does, with one difference named: the theme is
    read off the panel's surface (the .dd-panel section, which draws it under style.surface: filled), not off the
    <data-views> inside it, which is transparent there. WHY: on 8515930 (before the live tier) the shared helper's
    "panels follow the theme" fails in light mode for every dashboard case it runs (pid-tuning, sim-to-real,
    trajectory-tracking, vibetracks-runs, vibetracks-track: 12 FAILs in tests/browser/checks.py), for that reason."""
    for dark in (False, True):
        for width, mobile in ((1440, False), (390, True)):
            p = ctx.page(path, width=width, height=1000 if width > 400 else 844, dark=dark, mobile=mobile)
            ready(p)
            m = p.evaluate("""() => { const g = document.querySelector('#example .dd-grid').getBoundingClientRect();
              const ps = [...document.querySelectorAll('#example .dd-panel')].map((e) => Math.round(e.getBoundingClientRect().width));
              return { scroll: document.scrollingElement.scrollWidth, grid: Math.round(g.width), widths: ps,
                       surface: getComputedStyle(document.querySelector('#example .dd-panel[data-type]')).backgroundColor }; }""")
            tag = f"live-robot {'dark' if dark else 'light'}, {width} px"
            if width == 390:
                ctx.check(f"{tag}: one column and no sideways page scroll", m["scroll"] <= 390 and all(abs(w - m["grid"]) <= 1 for w in m["widths"]), m)
            else:
                ctx.check(f"{tag}: panels side by side, no sideways scroll", len(set(m["widths"])) > 1 and m["scroll"] <= width, m["widths"])
            light = m["surface"] in ("rgb(255, 255, 255)",)
            ctx.check(f"{tag}: the panels' surface follows the theme", light != dark and m["surface"] != "rgba(0, 0, 0, 0)", m["surface"])
            p.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + window.scrollY - 70)")
            p.wait_for_timeout(400)
            ctx.shot(p, f"live-robot-{'dark' if dark else 'light'}-{width}")
            p.context.close()
