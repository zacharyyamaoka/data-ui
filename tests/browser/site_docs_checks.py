"""The docs site's Views, Dashboards, Analyses and Docs pages (site/docs-pages.mjs): every page loads with no script
error and nothing from another site, every live demo draws (a view its type, a dashboard its panels, an analysis its
body and embeds, the list its rows), Preview | Code switches, the toolbar presets, embedded chrome and value sources
work on their live demos, the side panels' drags are measured, a phone gets a Menu and no sideways scroll in light and
dark, the landed blocks carry no "coming" badge and the pending slots are still there, badged.

    ~/psu-atlas/.venv/bin/python tests/browser/site_docs_checks.py      # after npm run build

Its own file, as gallery_checks.py is, so the site lanes never meet in checks.py; it borrows checks.py's Ctx (the
page helper that records foreign requests and script errors) and check(). Widths are getBoundingClientRect, never a
screenshot.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from checks import Ctx, check, checks, free_port  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SITE = ROOT / "dist" / "site"
DOCS = ["filters-and-facets", "frames", "open-modes", "resizable-panels", "explain-the-data", "time-groups-and-peek-trail", "performance",
        "toolbar-presets", "embedded-chrome", "value-sources", "rerun-interop"]
PAGES = ["views/index.html", "dashboards/index.html", "analyses/index.html", "docs/index.html"] + [f"docs/{d}.html" for d in DOCS]
# still on their lanes: a dashed block with a "soon" badge, its [data-slot] kept for the integrator
PENDING = {"dashboards/index.html": ["card-catalog", "synced-clock"], "docs/rerun-interop.html": ["rerun-interop"]}
# on main now: the same [data-slot], no "soon" badge, and a live demo inside it that draws
LANDED = {"dashboards/index.html": ["dashboard-live", "dashboard-datasets", "dashboard-select"], "analyses/index.html": ["analyses-live", "analyses-list"],
          "docs/toolbar-presets.html": ["toolbar-presets"]}
# the badges and callouts the site carried before these landed (26ff223); none may be left anywhere
STALE = ["Lands with dashboards", "Coming with lane/analyses", "Lands with the toolbar", "Not on main yet. Analyses"]
SOON_OK = {"Card catalog", "Synced clock", "Rerun interop"}
NAV = [["Overview", "index.html"], ["Views", "views/index.html"], ["Dashboards", "dashboards/index.html"], ["Analyses", "analyses/index.html"], ["Examples", "gallery/index.html"]]
GROUPS = ["Views", "Dashboards", "Analyses", "How it works"]

# every demo on the page, scrolled into life, measured by what it is: a view has drawn the type its block names, a
# dashboard every panel, an analysis its body and every embed, the list of analyses its rows
DEMOS = """() => [...document.querySelectorAll('.dd-preview')].map((b) => {
  const kind = b.dataset.kind || 'views';
  const h = (el) => (el ? Math.round(el.getBoundingClientRect().height) : 0);
  const out = { id: b.dataset.id, kind, src: b.dataset.src, view: b.dataset.view || null, slot: (b.closest('[data-slot]') || { dataset: {} }).dataset.slot || null };
  if (kind === 'dashboard') {
    const d = b.querySelector('data-dashboard');
    const panels = d ? [...d.querySelectorAll('.dd-panel data-views')] : [];
    // WHY content, not a height floor for every panel: a playback bar (40 px) and a compact KPI card (84 px) are drawn and
    // meant to be short; a panel counts as drawn when it has size and rendered content in its stage (a script error
    // anywhere fails "docs pages: no script errors"). Only the types that are meant to be tall keep a 100 px floor.
    const TALL = ['chart', 'timeseries', 'scene3d', 'trajectory', 'table'];
    const drawn = panels.filter((p) => {
      const r = p.getBoundingClientRect(), stage = p.querySelector('.dv-stage');
      return p.dataset.view && r.width > 0 && r.height > 0 && stage && stage.childElementCount > 0 && (!TALL.includes(p.dataset.view) || r.height >= 100);
    });
    return { ...out, h: h(d), n: panels.length, drawn: drawn.length, ok: !!d && d.dataset.view === 'dashboard' && panels.length >= 3 && drawn.length === panels.length && h(d) >= 400 };
  }
  if (kind === 'analysis') {
    const a = b.querySelector('data-analysis');
    const body = a && a.querySelector('.an-body');
    const embeds = a ? [...a.querySelectorAll('[data-embed]')] : [];
    const drawn = embeds.filter((e) => e.querySelector('data-views[data-view], data-dashboard[data-view]'));
    const toc = a ? a.querySelectorAll('.an-toc a').length : 0;
    return { ...out, h: h(a), n: embeds.length, drawn: drawn.length, toc, state: body && body.dataset.state,
      ok: !!body && body.dataset.state === 'ready' && embeds.length >= 2 && drawn.length === embeds.length && !a.querySelector('.an-err') && toc >= 3 && h(a) >= 600 };
  }
  if (kind === 'analyses') {
    const l = b.querySelector('data-analyses');
    const rows = l ? l.querySelectorAll('tr.dv-row').length : 0;
    return { ...out, h: h(l), n: rows, ok: !!l && !!l.dataset.view && rows >= 3 && h(l) >= 150 };
  }
  const v = b.querySelector('data-views');
  return { ...out, want: b.dataset.type, got: (v && v.dataset.view) || null, h: h(v), ok: !!v && v.dataset.view === b.dataset.type && h(v) >= 150 };
})"""
SCROLL = "async () => { for (let y = 0; y <= document.scrollingElement.scrollHeight; y += 450) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 60)); } scrollTo(0, 0); }"
SIDE = """() => { const r = (s) => document.querySelector(s).getBoundingClientRect(); const h = document.querySelector('.docs-side + .dv-splitter');
  return { side: r('.docs-side').width, main: r('.docs-main').left, edge: r('.docs-side').right, y: r('.docs-side').top + 200,
    handle: h && !h.hidden ? r('.docs-side + .dv-splitter').left + r('.docs-side + .dv-splitter').width / 2 : null }; }"""
# a kit side panel inside a demo (the analysis' contents, a dashboard's rail): its width and its handle's centre
PANEL = """(s) => { const p = document.querySelector(s); const h = p && p.nextElementSibling;
  if (!p || !h || !h.classList.contains('dv-splitter') || h.hidden) return null;
  const r = p.getBoundingClientRect(), k = h.getBoundingClientRect();
  return { w: r.width, edge: r.right, x: k.left + k.width / 2, y: k.top + Math.min(k.height / 2, 120) }; }"""


def demos_draw(ctx: Ctx, path: str) -> None:
    page = ctx.page(path, width=1440, height=900)
    page.evaluate(SCROLL)
    want = page.evaluate(DEMOS)
    ok = ctx.until(page, f"() => ({DEMOS})().every((d) => d.ok)", timeout=120000)
    got = page.evaluate(DEMOS)
    bad = [d for d in got if not d["ok"]]
    kinds = sorted({d["kind"] for d in got})
    check(f"{path}: every live demo starts when scrolled to and draws, measured ({len(want)} demos: {', '.join(kinds) or 'none'})", ok and not bad,
          bad[:3] or [f"{d['kind']}: {d.get('view') or d['src']} {d['h']} px" for d in got][:6])
    nav = page.evaluate("() => [...document.querySelectorAll('.top nav a')].map((a) => [a.textContent, new URL(a.href).pathname.replace(/^\\//, ''), a.getAttribute('aria-current')])")
    current = [n[0] for n in nav if n[2] == "page"]
    section = {"views": ["Views"], "dashboards": ["Dashboards"], "analyses": ["Analyses"], "docs": []}[path.split("/")[0]]
    check(f"{path}: the top nav is Overview · Views · Dashboards · Analyses · Examples (Examples still the gallery's page), {section or 'nothing'} current",
          [n[:2] for n in nav] == NAV and current == section, nav)
    side = page.evaluate("""() => ({ groups: [...document.querySelectorAll('.docs-nav h4')].map((h) => h.textContent),
      how: [...document.querySelectorAll('.docs-nav h4')].filter((h) => h.textContent === 'How it works').map((h) => [...h.nextElementSibling.querySelectorAll('a')].map((a) => a.textContent.replace(/\\s*soon$/, '').trim()))[0] || [],
      soon: [...document.querySelectorAll('.docs-nav a')].filter((a) => a.querySelector('.soon-dot')).map((a) => a.textContent.replace(/\\s*soon$/, '').trim()) })""")
    check(f"{path}: the sidebar's groups are Views, Dashboards, Analyses, How it works", side["groups"] == GROUPS, side["groups"])
    check(f"{path}: How it works lists Toolbar presets, Embedded chrome and Value sources",
          all(x in side["how"] for x in ["Toolbar presets", "Embedded chrome", "Value sources"]), side["how"])
    check(f"{path}: only what is still on a lane carries a 'soon' dot in the sidebar (card catalog, synced clock, Rerun)",
          set(side["soon"]) <= SOON_OK and "Rerun interop" in side["soon"], side["soon"])
    text = page.evaluate("() => (document.querySelector('.docs-main') || document.body).innerText")
    stale = [s for s in STALE if s in text]
    check(f"{path}: none of the old 'coming' badges or callouts is left", not stale, stale or None)
    for slot in PENDING.get(path, []):
        n = page.locator(f"[data-slot='{slot}']").count()
        badge = page.locator(f"[data-slot='{slot}'] .badge-soon").count()
        check(f"{path}: the pending slot [data-slot={slot}] is still there, badged as not on main yet", n == 1 and badge >= 1, f"{n} slot, {badge} badge")
    for slot in LANDED.get(path, []):
        got_slot = page.evaluate("""(s) => { const b = document.querySelector(`[data-slot='${s}']`);
          return b && { n: document.querySelectorAll(`[data-slot='${s}']`).length, soon: b.querySelectorAll('.badge-soon').length, live: b.querySelectorAll('.badge-live').length,
            pending: b.classList.contains('dd-pending'), coming: /not on main|lands with|coming with/i.test(b.innerText), demos: b.querySelectorAll('.dd-preview').length }; }""", slot)
        drew = [d for d in got if d["slot"] == slot]
        check(f"{path}: [data-slot={slot}] is live: no 'soon' badge or 'not on main' line, a Live badge, and its demo drew",
              bool(got_slot) and got_slot["n"] == 1 and not got_slot["soon"] and got_slot["live"] >= 1 and not got_slot["pending"] and not got_slot["coming"]
              and drew and all(d["ok"] for d in drew), {"slot": got_slot, "demos": drew[:2]})
    title = page.evaluate("() => { const t = document.querySelector('.title-row'); return t ? t.querySelectorAll('.badge-soon').length : 0; }")
    if path in ("analyses/index.html", "docs/toolbar-presets.html", "docs/embedded-chrome.html", "docs/value-sources.html"):
        check(f"{path}: the page title carries no 'soon' badge", title == 0, title)
    page.context.close()


def overview_tiers(ctx: Ctx) -> None:
    page = ctx.page("index.html", width=1440, height=900)
    got = page.evaluate("""() => { const t = document.querySelector('.tiers'); const hero = document.querySelector('.hero-demo');
      return { links: [...document.querySelectorAll('.tier-list a')].map((a) => [a.querySelector('b').textContent, new URL(a.href).pathname.replace(/^\\//, '')]),
        badges: [...document.querySelectorAll('.tier-list a')].map((a) => [...a.querySelectorAll('.badge')].map((b) => b.className + ': ' + b.textContent)),
        above: !!t && !!hero && t.getBoundingClientRect().top < hero.getBoundingClientRect().top, top: t ? Math.round(t.getBoundingClientRect().top) : null,
        nav: [...document.querySelectorAll('.top nav a')].map((a) => a.textContent), current: (document.querySelector('.top nav a[aria-current=page]') || {}).textContent }; }""")
    check("overview: the three tiers near the top (above the live demo), Views → Dashboards → Analyses, each linking to its page",
          got["links"] == [["Views", "views/index.html"], ["Dashboards", "dashboards/index.html"], ["Analyses", "analyses/index.html"]] and got["above"] and got["top"] < 900
          and got["nav"] == [n[0] for n in NAV] and got["current"] == "Overview", got)
    check("overview: all three tiers are live (a Live badge each, no 'coming' badge on Dashboards or Analyses)",
          len(got["badges"]) == 3 and all(len(b) == 1 and "badge-live" in b[0] and "soon" not in b[0] for b in got["badges"]), got["badges"])
    page.context.close()
    page = ctx.page("docs/index.html", width=1440, height=900)
    cards = page.evaluate("() => [...document.querySelectorAll('.doc-card')].map((c) => [c.querySelector('b').textContent, c.querySelectorAll('.badge-soon').length])")
    soon = [c[0] for c in cards if c[1]]
    check("how it works: the index's cards include the new pages, and only Rerun interop is still badged 'soon'",
          {"Toolbar presets", "Embedded chrome", "Value sources"} <= {c[0] for c in cards} and soon == ["Rerun interop"], cards)
    page.context.close()


def tabs(ctx: Ctx) -> None:
    page = ctx.page("views/index.html#type-table", width=1440, height=900)
    block = "#type-table"
    page.click(f"{block} [role=tab]:has-text('Code')")
    got = page.evaluate(f"""() => ({{ code: !document.querySelector('{block}-c').hidden, preview: document.querySelector('{block}-p').hidden,
      text: document.querySelector('{block}-c pre code').textContent, sel: document.querySelector('{block} [role=tab][aria-selected=true]').textContent }})""")
    check("views: Code shows the view's own .base entry (cut from the case's file) and hides the Preview",
          got["code"] and got["preview"] and got["text"].startswith("- type: table") and "name: By brand" in got["text"] and got["sel"] == "Code", got["text"][:60])
    page.click(f"{block} [role=tab]:has-text('Preview')")
    back = page.evaluate(f"() => !document.querySelector('{block}-p').hidden && document.querySelector('{block}-c').hidden")
    check("views: Preview switches back", back)
    page.context.close()
    # on a page with a dashboard, the dashboard's own .dd-panel rules must not unhide a block's Code panel
    page = ctx.page("dashboards/index.html", width=1440, height=900)
    if not page.locator("[data-slot=dashboard-live] .dd-preview").count():
        check("dashboards: the Code panel stays hidden beside a live dashboard (0 px) and Code shows its layout:", False, "no live dashboard")
        page.context.close()
        return
    page.locator("[data-slot=dashboard-live] .dd-preview").scroll_into_view_if_needed()
    ctx.until(page, "() => document.querySelector('[data-slot=dashboard-live] data-dashboard[data-view=dashboard]')")
    got = page.evaluate("""() => { const b = document.querySelector('[data-slot=dashboard-live]'); const c = b.querySelector('[role=tabpanel][hidden]');
      return { code: c ? Math.round(c.getBoundingClientRect().height) : null, text: c ? c.textContent.trim().slice(0, 30) : null }; }""")
    page.click("[data-slot=dashboard-live] [role=tab]:has-text('Code')")
    shown = page.evaluate("() => { const b = document.querySelector('[data-slot=dashboard-live]'); const c = b.querySelector('[role=tabpanel]:not([hidden]) pre code'); return c ? c.textContent : ''; }")
    check("dashboards: the Code panel stays hidden beside a live dashboard (0 px) and Code shows its layout:", got["code"] == 0 and shown.startswith("layout:"), {"hidden": got, "code": shown[:40]})
    page.context.close()


def switches(ctx: Ctx) -> None:
    page = ctx.page("docs/frames.html", width=1440, height=900)
    page.locator("[data-switch-id=frames-demo]").scroll_into_view_if_needed()
    ctx.until(page, "() => document.querySelector('[data-switch-id=frames-demo] data-views[data-view]')")
    page.click("[data-switch=frames-demo] button[data-value=sheet]")
    ok = ctx.until(page, "() => document.querySelector('[data-switch-id=frames-demo] data-views').getAttribute('frame') === 'sheet'")
    snippet = page.inner_text("#frames-code")
    check("frames: the switch sets frame= on the live demo and on its HTML snippet", ok and 'frame="sheet"' in snippet, snippet)
    page.context.close()


# what each preset must put on the bar (docs/CONTRACT.md §15 note "promote"): the views control, the promoted words
PRESETS = {
    "mix": {"attrs": {"views": "auto", "promote": None}, "words": ["filter"]},
    "shopify": {"attrs": {"views": "dropdown", "promote": ""}, "chip": True, "words": []},
    "notion": {"attrs": {"views": "tabs", "promote": ""}, "tabs": True, "words": []},
    "obsidian": {"attrs": {"views": "dropdown", "promote": "sort group filter properties"}, "chip": True, "words": ["sort", "group", "filter", "properties"]},
}
BAR = """() => { const el = document.querySelector('[data-switch-id=toolbar-demo] data-views'); if (!el) return null;
  const vis = (e) => !!e && !e.hidden && e.getBoundingClientRect().width > 0;
  return { views: el.getAttribute('views'), promote: el.getAttribute('promote'), toolbar: el.getAttribute('toolbar'),
    chip: vis(el.querySelector('.dv-viewchip')), tabs: [...el.querySelectorAll('.dv-viewtabs .dv-vtab')].filter(vis).length,
    words: [...el.querySelectorAll('.dv-bar-word')].filter(vis).map((b) => b.dataset.tool), display: vis(el.querySelector('.dv-bar-display')),
    snippet: (document.getElementById('toolbar-code') || {}).textContent || '' }; }"""


def toolbar_presets(ctx: Ctx) -> None:
    page = ctx.page("docs/toolbar-presets.html", width=1440, height=900)
    box = page.locator("[data-switch-id=toolbar-demo]")
    if not box.count():
        check("toolbar presets: a live toolbar-bar demo with a preset switch", False, "no [data-switch-id=toolbar-demo]")
        page.context.close()
        return
    box.scroll_into_view_if_needed()
    ctx.until(page, "() => document.querySelector('[data-switch-id=toolbar-demo] data-views[data-view]')")
    for name, want in PRESETS.items():
        page.click(f"[data-preset=toolbar-demo] button[data-value={name}]")
        # WHY ?? null: Playwright hands Python's None to the page as undefined, and getAttribute says null
        ok = ctx.until(page, f"""(w) => {{ const b = ({BAR})(); return !!b && b.display && (b.views ?? null) === (w.attrs.views ?? null) && (b.promote ?? null) === (w.attrs.promote ?? null)
          && JSON.stringify(b.words) === JSON.stringify(w.words) && (!w.chip || b.chip) && (!w.tabs || b.tabs >= 2); }}""", want, timeout=15000)
        got = page.evaluate(BAR)
        snip_ok = all((f'{k}="{v}"' in got["snippet"]) if v is not None else (f"{k}=" not in got["snippet"]) for k, v in want["attrs"].items() if k != "views" or v != "auto")
        check(f"toolbar presets: {name} sets {want['attrs']} live, the bar shows {want['words'] or 'no promoted words'}"
              f"{', the view chip' if want.get('chip') else ''}{', the view tabs' if want.get('tabs') else ''} and Display, and the snippet says so",
              ok and snip_ok, got)
    page.context.close()


CHROME = """() => { const el = document.querySelector('[data-switch-id=chrome-demo] data-views'); if (!el) return null;
  const h = (s) => { const e = el.querySelector(s); return e ? Math.round(e.getBoundingClientRect().height) : -1; };
  return { status: el.getAttribute('status'), controls: el.getAttribute('controls'), chrome: el.chrome ? el.chrome() : null,
    statusH: h('.dv-status'), barH: h('.dv-chart-bar'), viewH: h('.dv-stage > .dv-view'), snippet: (document.getElementById('chrome-code') || {}).textContent || '' }; }"""


def embedded_chrome(ctx: Ctx) -> None:
    page = ctx.page("docs/embedded-chrome.html", width=1440, height=900)
    box = page.locator("[data-switch-id=chrome-demo]")
    if not box.count():
        check("embedded chrome: a live chart demo with status and controls switches", False, "no [data-switch-id=chrome-demo]")
        page.context.close()
        return
    box.scroll_into_view_if_needed()
    ctx.until(page, "() => { const b = (" + CHROME + ")(); return b && b.statusH > 0 && b.barH > 0; }")
    on = page.evaluate(CHROME)
    page.click("[data-switch=chrome-demo][data-attr=status] button[data-value=off]")
    page.click("[data-switch=chrome-demo][data-attr=controls] button[data-value=off]")
    ok = ctx.until(page, "() => { const b = (" + CHROME + ")(); return b && b.statusH <= 0 && b.barH <= 0; }", timeout=15000)
    off = page.evaluate(CHROME)
    check("embedded chrome: status and controls start on, measured (the status line and the chart's Encode bar have height)",
          on and on["statusH"] > 0 and on["barH"] > 0 and on["viewH"] > 150, on)
    check('embedded chrome: status="off" controls="off" set live hide both (0 px) while the chart still draws, and the snippet says so',
          ok and off["chrome"] == {"status": False, "controls": False} and off["viewH"] > 150 and 'status="off"' in off["snippet"] and 'controls="off"' in off["snippet"], off)
    page.context.close()


SRCMENU = """() => { const m = document.querySelector('.dv-srcmenu'); if (!m || m.hidden) return null; const r = m.getBoundingClientRect();
  return { w: Math.round(r.width), h: Math.round(r.height), left: r.left, right: r.right, top: r.top, bottom: r.bottom, vw: innerWidth, vh: innerHeight, text: m.innerText }; }"""


def value_sources(ctx: Ctx) -> None:
    page = ctx.page("docs/value-sources.html", width=1440, height=900)
    box = page.locator("[data-switch-id=sources-demo], #sources-live .dd-preview").first
    if not page.locator("#sources-live .dd-preview").count():
        check("value sources: a live demo whose cells carry a source", False, "no #sources-live .dd-preview")
        page.context.close()
        return
    box.scroll_into_view_if_needed()
    ctx.until(page, "() => document.querySelector('#sources-live data-views[data-view] [data-provenance]')")
    cell = page.locator("#sources-live data-views [data-provenance]").first
    cell.scroll_into_view_if_needed()
    prov = cell.evaluate("(e) => JSON.parse(e.dataset.provenance)")
    r = cell.bounding_box()
    page.mouse.click(r["x"] + r["width"] / 2, r["y"] + r["height"] / 2, button="right")
    ok = ctx.until(page, f"() => !!({SRCMENU})()", timeout=10000)
    got = page.evaluate(SRCMENU)
    check("value sources: a right-click on a value with a source opens 'where this value comes from' in the viewport, naming its source",
          ok and got and got["w"] > 150 and got["h"] > 80 and got["left"] >= 0 and got["right"] <= got["vw"] and got["bottom"] <= got["vh"]
          and str(prov.get("source", "")) in got["text"], {"provenance": prov, "menu": got})
    page.keyboard.press("Escape")
    closed = ctx.until(page, f"() => !({SRCMENU})()", timeout=5000)
    check("value sources: Escape closes it", closed)
    page.context.close()


def analyses_list(ctx: Ctx) -> None:
    page = ctx.page("analyses/index.html", width=1440, height=900)
    if not page.locator("[data-slot=analyses-list] .dd-preview").count():
        check("analyses: the list's rows link to each analysis' page, and each page answers 200", False, "no live list")
        page.context.close()
        return
    page.locator("[data-slot=analyses-list] .dd-preview").scroll_into_view_if_needed()
    ctx.until(page, "() => document.querySelectorAll('[data-slot=analyses-list] data-analyses tr.dv-row a[href]').length >= 3", timeout=30000)
    hrefs = page.evaluate("() => [...document.querySelectorAll('[data-slot=analyses-list] data-analyses tr.dv-row a[href]')].map((a) => a.href)")
    status = {h: page.request.get(h).status for h in sorted(set(hrefs))}
    check("analyses: the list's rows link to each analysis' page (gallery/analyses/), and each page answers 200",
          len(status) >= 3 and all("/gallery/analyses/" in h and s == 200 for h, s in status.items()), status)
    page.context.close()


def panels_drag(ctx: Ctx) -> None:
    """The kit's side panels inside the demos (the analysis' contents, a dashboard's rail) keep their handles here."""
    for path, slot, sel in [("analyses/index.html", "analyses-live", "[data-slot=analyses-live] .an-toc"), ("dashboards/index.html", "dashboard-live", "[data-slot=dashboard-live] .dd-rail")]:
        page = ctx.page(path, width=1440, height=900)
        page.evaluate("() => { try { localStorage.clear(); } catch (e) {} }")
        if not page.locator(f"[data-slot={slot}] .dd-preview").count():
            check(f"{path}: {sel} drags +60 px, measured", False, "no live demo")
            page.context.close()
            continue
        page.locator(f"[data-slot={slot}] .dd-preview").scroll_into_view_if_needed()
        ctx.until(page, f"(s) => !!({PANEL})(s)", sel, timeout=60000)
        ctx.frames(page, 4)
        a = page.evaluate(PANEL, sel)
        if not a:
            check(f"{path}: {sel} drags +60 px, measured", False, "no handle")
            page.context.close()
            continue
        page.mouse.move(a["x"], a["y"])
        page.mouse.down()
        page.mouse.move(a["x"] + 60, a["y"], steps=8)
        page.mouse.up()
        ctx.frames(page)
        b = page.evaluate(PANEL, sel)
        check(f"{path}: {sel} has its handle on its right edge and a +60 px drag widens it by 60 px",
              abs(a["x"] - a["edge"]) <= 1.5 and b and abs(b["w"] - a["w"] - 60) <= 2, {"before": round(a["w"]), "after": b and round(b["w"])})
        page.context.close()


def analysis_sticky(ctx: Ctx) -> None:
    page = ctx.page("analyses/index.html", width=1440, height=900)
    if not page.locator("[data-slot=analyses-live] data-analysis, [data-slot=analyses-live] .dd-preview[data-kind=analysis]").count():
        check("analyses: the analysis' contents column stays in view under the site header as the page scrolls past it", False, "no live analysis")
        page.context.close()
        return
    page.locator("[data-slot=analyses-live] .dd-preview").scroll_into_view_if_needed()
    ctx.until(page, "() => { const b = document.querySelector('[data-slot=analyses-live] .an-body'); return b && b.dataset.state === 'ready'; }", timeout=60000)
    got = page.evaluate("""async () => { const a = document.querySelector('[data-slot=analyses-live] data-analysis'); const toc = a.querySelector('.an-toc');
      const head = document.querySelector('header.top').getBoundingClientRect().bottom;
      scrollTo(0, scrollY + a.getBoundingClientRect().top + 500); await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      const t = toc.getBoundingClientRect(), r = a.getBoundingClientRect();
      return { position: getComputedStyle(toc).position, tocTop: Math.round(t.top), tocH: Math.round(t.height), head: Math.round(head), analysisTop: Math.round(r.top), links: toc.querySelectorAll('a').length }; }""")
    check("analyses: the analysis' contents column stays in view under the site header as the page scrolls past it",
          got["position"] == "sticky" and got["analysisTop"] < 0 and got["head"] <= got["tocTop"] <= got["head"] + 24 and got["tocH"] > 60 and got["links"] >= 3, got)
    page.context.close()


def sidebar_drag(ctx: Ctx) -> None:
    page = ctx.page("docs/frames.html", width=1440, height=900)
    page.evaluate("() => { try { localStorage.removeItem('data-ui/panel-width/docs-side'); } catch (e) {} }")
    page.reload()
    page.wait_for_selector(".docs-side + .dv-splitter:not([hidden])")
    a = page.evaluate(SIDE)
    page.mouse.move(a["handle"], a["y"])
    page.mouse.down()
    page.mouse.move(a["handle"] + 100, a["y"], steps=10)
    page.mouse.up()
    b = page.evaluate(SIDE)
    check("sidebar: its handle sits on its right edge and a +100 px drag widens it by 100 px (the page beside it moves 100 px right)",
          abs(a["handle"] - a["edge"]) <= 1.5 and abs(b["side"] - a["side"] - 100) <= 2 and abs(b["main"] - a["main"] - 100) <= 2,
          {"before": round(a["side"]), "dragged": round(b["side"]), "main": [round(a["main"]), round(b["main"])]})
    page.goto(page.url.replace("frames.html", "open-modes.html"))
    page.wait_for_selector(".docs-side + .dv-splitter:not([hidden])")
    c = page.evaluate(SIDE)
    check("sidebar: the width is remembered across pages and reloads (localStorage)", abs(c["side"] - b["side"]) <= 1, {"dragged": round(b["side"]), "next page": round(c["side"])})
    page.dblclick(".docs-side + .dv-splitter")
    ctx.frames(page)
    d = page.evaluate(SIDE)
    stored = page.evaluate("() => { try { return localStorage.getItem('data-ui/panel-width/docs-side'); } catch (e) { return 'unreadable'; } }")
    check("sidebar: a double-click resets it to its default width and forgets the stored one", abs(d["side"] - a["side"]) <= 1 and stored is None, {"reset": round(d["side"]), "default": round(a["side"]), "stored": stored})
    page.context.close()


def phone(ctx: Ctx) -> None:
    bad = []
    for path in PAGES:
        for dark in (False, True):
            page = ctx.page(path, width=375, height=812, dark=dark, mobile=True)
            page.evaluate(SCROLL)
            got = page.evaluate("""() => ({ sw: document.scrollingElement.scrollWidth, cw: document.scrollingElement.clientWidth,
              navShown: !document.querySelector('.docs-nav') || getComputedStyle(document.querySelector('.docs-nav')).display !== 'none', menu: !!document.querySelector('.docs-menu') && getComputedStyle(document.querySelector('.docs-menu')).display !== 'none',
              handle: !!document.querySelector('.docs-side + .dv-splitter:not([hidden])'), bg: getComputedStyle(document.body).backgroundColor })""")
            if got["sw"] > got["cw"] or got["navShown"] or not got["menu"] or got["handle"] or (got["bg"] == "rgb(10, 10, 10)") != dark:
                bad.append({"path": path, "dark": dark, **got})
            page.context.close()
    check(f"phone, 375 px: all {len(PAGES)} pages, light and dark, have no sideways scroll, the sidebar is a closed Menu with no drag handle", not bad, bad[:3] or None)
    page = ctx.page("docs/performance.html", width=375, height=812, mobile=True)
    page.click(".docs-menu")
    got = page.evaluate("() => ({ shown: getComputedStyle(document.querySelector('.docs-nav')).display !== 'none', expanded: document.querySelector('.docs-menu').getAttribute('aria-expanded'), sw: document.scrollingElement.scrollWidth })")
    check("phone: Menu opens the sidebar's list in place, still with no sideways scroll", got["shown"] and got["expanded"] == "true" and got["sw"] <= 375, got)
    page.context.close()


def main() -> int:
    if not (SITE / "docs" / "index.html").exists():
        print("dist/site is not built: npm --prefix ~/data-ui run build")
        return 1
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/index.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = Ctx(browser, base)
            for path in PAGES:
                demos_draw(ctx, path)
            overview_tiers(ctx)
            tabs(ctx)
            switches(ctx)
            toolbar_presets(ctx)
            embedded_chrome(ctx)
            value_sources(ctx)
            analyses_list(ctx)
            analysis_sticky(ctx)
            panels_drag(ctx)
            sidebar_drag(ctx)
            phone(ctx)
            check("docs pages: nothing loaded from another site", not ctx.foreign, ctx.foreign[:3])
            check("docs pages: no script errors", not ctx.errors, ctx.errors[:3])
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    passed = sum(c["ok"] for c in checks)
    print(f"{passed}/{len(checks)} docs-site checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
