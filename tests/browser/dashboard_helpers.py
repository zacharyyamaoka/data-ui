"""Shared helpers for the dashboard cases' checks.py (docs/peps/0004-dashboards.md): wait for every panel, read each
panel's drawn "N of M", click a KPI card, and the light/dark × desktop/phone pass with screenshots. The numbers a
check expects are computed by the case from its JSON files, never read from here."""

import json
import pathlib
import re

D = "#example"


def rows(here, name):
    return json.loads((pathlib.Path(here) / name).read_text(encoding="utf-8"))["rows"]


def ready(page):
    page.wait_for_selector(f"{D} .dd-panel data-views .dv-status", timeout=20000)
    page.wait_for_function("""() => { const els = [...document.querySelectorAll('#example .dd-panel data-views')];
      return els.length && els.every((e) => e.dataset.view && /of/.test(e.querySelector('.dv-status').textContent)); }""", timeout=20000)
    page.wait_for_timeout(600)


def counts(page):
    return page.evaluate("""() => { const out = {};
      for (const sec of document.querySelectorAll('#example .dd-panel[data-panel]')) {
        const s = sec.querySelector('data-views .dv-status'); if (!s) continue;
        const m = /([\\d,]+) of ([\\d,]+)/.exec(s.textContent); out[sec.dataset.panel] = m ? Number(m[1].replace(/,/g, '')) : null;
        const cards = sec.querySelectorAll('data-kpi'); if (cards.length) out[sec.dataset.panel + ':cards'] = cards.length; }
      return out; }""")


def card(page, panel, label):
    """A KPI card's drawn number and label, and a click on it."""
    loc = page.locator(f"{D} [data-panel='{panel}'] data-kpi", has=page.locator(".dv-kpi-label", has_text=label)).first
    return loc


def num(text):
    m = re.search(r"-?[\d,]*\.?\d+", text or "")
    return float(m.group(0).replace(",", "")) if m else None


def themes(ctx, path, name):
    """Light and dark at 1440 and 390 px: one column and no sideways scroll on a phone, side by side on a desktop."""
    for dark in (False, True):
        for width, mobile in ((1440, False), (390, True)):
            p = ctx.page(path, width=width, height=1000 if width > 400 else 844, dark=dark, mobile=mobile)
            ready(p)
            m = p.evaluate("""() => { const g = document.querySelector('#example .dd-grid').getBoundingClientRect();
              const ps = [...document.querySelectorAll('#example .dd-panel')].map((e) => Math.round(e.getBoundingClientRect().width));
              return { scroll: document.scrollingElement.scrollWidth, grid: Math.round(g.width), widths: ps,
                       bg: getComputedStyle(document.querySelector('#example .dd-panel:not(.dd-panel-text)')).backgroundColor,
                       body: getComputedStyle(document.body).backgroundColor }; }""")
            tag = f"{name} {'dark' if dark else 'light'}, {width} px"
            if width == 390:
                ctx.check(f"{tag}: one column and no sideways page scroll", m["scroll"] <= 390 and all(abs(w - m["grid"]) <= 1 for w in m["widths"]), m)
            else:
                ctx.check(f"{tag}: panels side by side, no sideways scroll", len(set(m["widths"])) > 1 and m["scroll"] <= width, m["widths"])
            # WHY the tile, not its <data-views>: inside a dashboard the view is transparent on its tile (docs/CONTRACT.md §25)
            ctx.check(f"{tag}: the panels follow the theme", (m["bg"] != "rgb(255, 255, 255)") == dark, m["bg"])
            p.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + window.scrollY - 70)")
            p.wait_for_timeout(200)
            ctx.shot(p, f"{name}-{'dark' if dark else 'light'}-{width}")
            p.context.close()
