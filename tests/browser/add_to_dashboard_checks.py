"""Add to dashboard (docs/CONTRACT.md §34), measured in headless Chromium on the built kit. Written red, before the
code; never edited after.

    ~/psu-atlas/.venv/bin/python tests/browser/add_to_dashboard_checks.py [OUT_DIR]     # after npm run build

Zach, 2026-10-29: "Dashboards are built with data-ui. Humans curate, AI builds." Humans add to a dashboard from any view
of the data, "like the amazon thing of adding to a saved list"; the item goes to the bottom of the chosen dashboard, to
be arranged later. "This is a standard feature you can support in data-ui, shouldn't be specific to robotdx."

The fixture is tests/browser/fixtures/add_to_dashboard/: source.base (a dashboard with a KPI view, a table, a chart, a
time series and a 3D path over two linked datasets and a clock), standalone.base (one <data-views> with its rail) and
target.base (the dashboard a panel is added to, with comments, blank lines, a dataset on the same file under another
name, another file under the source's dataset name, and a view named like the source's). The page plays the host: its
`dashboards()` hook lists target.base, and its `data-add-to-dashboard` listener keeps the text and answers through
`respondWith`. Every expected row comes from the fixture's JSON, read here with Python (the oracle is the file).
  - "Add to dashboard…" is on the view's ⋯ menu (toolbar full) and View settings (the bar), on every dashboard panel's
    menu (a table, a chart, a time series, a 3D path, KPI cards), on a KPI card and a legend's series (their item menu),
    and on a field of the record peek;
  - the panel round-trips: appended to target.base and loaded, the new panel draws the same rows as the source view
    under the same filters (a rail pick, a search and a sort on a <data-views>; another panel's selection and a link
    on a dashboard panel), and sits below every other panel; a series added draws that series alone; a KPI card added
    is that card; "At this moment" pins the panel at the instant;
  - the text keeps every byte of target.base apart from the inserted lines; the dataset on the same file is reused, the
    names that collide take a suffix; data-ui check and tools/check_views.py accept it; Arrange moves the new panel;
  - with no host listener the new dashboard's text goes to the clipboard and the picker says so; a host's error is
    shown; a host that takes over (preventDefault) gets the picker closed;
  - light and dark, at 1280 and 390 px: the picker inside the viewport, its colours the theme's, no sideways scroll.
Serves the repo root on a free 127.0.0.1 port, stops it when done, writes OUT_DIR/add-to-dashboard-checks.json (default
reports/media/add-to-dashboard) with the screenshots, and exits 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import difflib
import json
import os
import pathlib
import socket
import statistics
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "add-to-dashboard"
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "browser" / "fixtures" / "add_to_dashboard"
URL = "/tests/browser/fixtures/add_to_dashboard/"
PAGE = URL + "page.html"
TARGET = (FIX / "target.base").read_text(encoding="utf-8")
WAIT = 30000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
checks: list[dict] = []

sys.path.insert(0, str(ROOT / "packages" / "core" / "python"))
import data_ui_base  # noqa: E402  the stdlib .base reader, the Python twin of base.js


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str, ensure_ascii=False)[:400]}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    """A section that cannot run (nothing drawn to measure) is one failing check in its own words, not a crash."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(directory, probe):
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(directory)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + probe, timeout=1)
            break
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.1)
    return proc, base


# ------------------------------------------------------------------------------------------------- the oracle
def rows(name):
    doc = json.loads((FIX / name).read_text(encoding="utf-8"))
    return doc["rows"] if isinstance(doc, dict) else doc


RUNS = rows("runs.json")
SAMPLES = rows("samples.json")
SOLO_ORDER = ["run", "robot", "kind", "started", "success"]


def js_text(v):
    """A cell as the kit's search reads it (String(v), lowercased)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).lower()


def solo_expected(robots, words, sort_desc):
    """The standalone table's rows under a robot pick, a search over its visible properties and a sort: run ids."""
    keep = [r for r in RUNS if r["robot"] in robots and any(words in js_text(r[p]) for p in SOLO_ORDER if r.get(p) is not None)]
    return [r["id"] for r in sorted(keep, key=lambda r: r[sort_desc], reverse=True)]


def only_insertions(before, after):
    """True when `after` is `before` with lines inserted and nothing changed, removed or moved (difflib's opcodes)."""
    ops = difflib.SequenceMatcher(None, before.split("\n"), after.split("\n"), autojunk=False).get_opcodes()
    bad = [op for op in ops if op[0] not in ("equal", "insert")]
    return not bad, bad[:3]


def parse(text):
    return data_ui_base.loads(text)


def datasets_of(doc):
    return {k: (v if isinstance(v, str) else (v or {}).get("data")) for k, v in (doc.get("datasets") or {}).items()}


def last_panel(doc):
    """The last layout panel and the view it names."""
    p = doc["layout"]["panels"][-1]
    name = p.get("view") or (p.get("views") or [None])[0]
    view = next((v for v in doc.get("views") or [] if v.get("name") == name), None)
    return p, view


def checkers(text, tag):
    """Both checkers on the text, written beside the fixture's data (so the files it names are read)."""
    path = FIX / f"_a2d-check-{os.getpid()}-{tag}.base"
    path.write_text(text, encoding="utf-8")
    try:
        node = subprocess.run(["node", str(ROOT / "bin" / "data-ui.mjs"), "check", str(path), "--json"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        report = json.loads(node.stdout)
        py = subprocess.run(["python3", str(ROOT / "tools" / "check_views.py"), str(path)], cwd=ROOT, capture_output=True, text=True, timeout=120)
        tail = (py.stdout.strip().splitlines() or [""])[-1]
        return {"node_errors": report["errors"], "node_problems": [p for p in report["problems"] if p["level"] == "error"][:3], "python": tail}
    finally:
        path.unlink(missing_ok=True)


# ------------------------------------------------------------------------------------------------- page helpers
SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"

# the host: `dashboards()` on <html> (any ancestor of a view may hold it) and a listener that keeps what it was handed
HOST = """(cfg) => {
  window.hostCfg = cfg;
  if (cfg.list !== null) document.documentElement.dashboards = async () => { if (window.hostCfg.listError) throw new Error(window.hostCfg.listError); return window.hostCfg.list; };
  if (window.hostWired || !cfg.listen) return;
  window.hostWired = true;
  window.added = [];
  document.addEventListener('data-add-to-dashboard', (e) => {
    const c = window.hostCfg;
    window.added.push({ dashboard: e.detail.dashboard, panel: e.detail.panel, text: e.detail.text, cancelable: e.cancelable, respond: typeof e.detail.respondWith });
    if (c.answer === 'take-over') { e.preventDefault(); return; }
    if (c.answer === 'reject') e.detail.respondWith(new Promise((_, no) => setTimeout(() => no(new Error(c.reason)), 30)));
    else e.detail.respondWith(new Promise((yes) => setTimeout(() => yes(c.answer), 30)));
  });
}"""
TARGET_ENTRY = {"id": "target", "title": "Target", "url": URL + "target.base"}

LAST = "() => { const a = window.added || []; return a.length ? a[a.length - 1] : null; }"


def settle(page, n=2):
    for _ in range(n):
        page.evaluate(SETTLE)


def until(page, js, arg=None, timeout=WAIT):
    try:
        page.wait_for_function(js, arg=arg, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False


def new_page(browser, base, *, width=1280, dark=False, clipboard=False):
    mobile = width < 500
    context = browser.new_context(viewport={"width": width, "height": 1000 if width > 500 else 844}, color_scheme="dark" if dark else "light",
                                  device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    if clipboard:
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.goto(base + PAGE)
    page.wait_for_function("window.kitReady === true", timeout=WAIT)
    return page


def add_solo(page, *, toolbar="full", id_="solo"):
    page.evaluate("""([id, toolbar]) => { const v = document.createElement('data-views'); v.id = id; v.setAttribute('no-url', '');
      v.setAttribute('toolbar', toolbar); v.setAttribute('src', 'standalone.base'); document.body.append(v); }""", [id_, toolbar])
    return until(page, "(id) => { const v = document.getElementById(id); return v && v.model && v.dataset.view && v.querySelector('.dv-stage .dv-view'); }", id_)


def add_dash(page, src, id_):
    page.evaluate("""([id, src]) => { const d = document.createElement('data-dashboard'); d.id = id; d.setAttribute('no-url', '');
      d.setAttribute('src', src); document.body.append(d); }""", [id_, src])
    return until(page, """(id) => { const d = document.getElementById(id); if (!d || !d.dash) return false;
      const els = [...d.querySelectorAll('.dd-panel data-views')]; return els.length === d.dash.panels.filter((p) => p.views.length).length
        && els.every((e) => e.dataset.view && e.model); }""", id_)


def panel_sel(dash, key):
    return f"#{dash} .dd-panel[data-panel='{key}']"


def panel_rows(page, dash, key, prop):
    """A panel's rows in the order it draws them (its <data-views>' row model): [[id, value of prop]…]."""
    return page.evaluate("""([sel, p]) => { const el = document.querySelector(sel + ' data-views'); const m = el && el.model;
      const v = (c) => (c && typeof c === 'object' && !Array.isArray(c) ? c.value : c);
      return m ? m.rows.map((r) => [String(r.id), v(r[p])]) : null; }""", [panel_sel(dash, key), prop])


def open_panel_menu(page, dash, key):
    """The dashboard panel's own menu (⋯), then its item."""
    sel = panel_sel(dash, key)
    page.locator(sel).hover()
    page.locator(f"{sel} .dd-panel-menu").first.click()
    item = page.locator(f"{sel} .dd-panel-pop [data-add-dashboard]").first
    item.wait_for(state="visible", timeout=WAIT)
    return item


def open_item_menu(page, target):
    """A right-click on `target` (a legend entry, a KPI card, a peek field): the item menu and its Add item."""
    page.locator(target).first.scroll_into_view_if_needed()
    page.locator(target).first.click(button="right")
    item = page.locator(".dv-itemmenu:not([hidden]) [data-add-dashboard]").first
    item.wait_for(state="visible", timeout=WAIT)
    return item


def pick(page, dashboard_id, *, at_moment=False):
    """In the open picker: optionally "At this moment", then the dashboard. Returns the status's state and text."""
    picker = page.locator(".dv-addpick:not([hidden])").first
    picker.wait_for(state="visible", timeout=WAIT)
    if at_moment:
        picker.locator("input[name='at-moment']").check()
    btn = picker.locator(f"[data-dashboard-id='{dashboard_id}']")
    btn.wait_for(state="visible", timeout=WAIT)
    btn.click()
    return status(page)


def status(page):
    ok = until(page, "() => { const s = document.querySelector('.dv-addpick:not([hidden]) .dv-addpick-status'); return s && ['added', 'error', 'copied'].includes(s.dataset.state); }")
    return page.evaluate("() => { const s = document.querySelector('.dv-addpick:not([hidden]) .dv-addpick-status'); return s ? { state: s.dataset.state, text: s.textContent.trim() } : null; }") if ok else None


def close_picker(page):
    page.keyboard.press("Escape")
    until(page, "() => !document.querySelector('.dv-addpick:not([hidden])')", timeout=5000)


def load_text(page, text, tag):
    """The new text as a file beside target.base, drawn by a fresh <data-dashboard>; its id and the file (to delete)."""
    path = FIX / f"_a2d-{os.getpid()}-{tag}.base"
    path.write_text(text, encoding="utf-8")
    id_ = f"out-{tag}"
    ok = add_dash(page, path.name, id_)
    settle(page, 2)
    return id_, path, ok


def boxes(page, dash):
    return page.evaluate("""(id) => [...document.querySelectorAll(`#${id} .dd-panel`)].map((s) => { const r = s.getBoundingClientRect();
      return { key: s.dataset.panel, top: r.top + scrollY, bottom: r.bottom + scrollY, left: r.left, right: r.right }; })""", dash)


def below_all(page, dash, key):
    b = boxes(page, dash)
    mine = next((x for x in b if x["key"] == key), None)
    others = [x for x in b if x["key"] != key]
    return mine is not None and others and all(mine["top"] >= o["bottom"] - 1 for o in others), {"new": mine, "lowest other bottom": max((o["bottom"] for o in others), default=None)}


def shot(page, name, sel=None):
    try:
        settle(page)
        if sel:
            page.locator(sel).first.screenshot(path=str(OUT / f"{name}.png"))
        else:
            page.screenshot(path=str(OUT / f"{name}.png"))
    except Exception as e:  # noqa: BLE001 -- a missing picture is not a failed behaviour; say so
        print(f"(screenshot {name} not taken: {e})")


# ------------------------------------------------------------------------------------------------- 1. where the item is
def menus(browser, base):
    page = new_page(browser, base)
    page.evaluate(HOST, {"list": [TARGET_ENTRY], "listen": True, "answer": {"ok": True}})
    ok = add_solo(page, toolbar="full")
    page.locator("#solo [data-menu='more']").click()
    item = page.locator("#solo .dv-pop [data-add-dashboard]")
    check("menu: a <data-views>' ⋯ menu (toolbar full) has \"Add to dashboard…\"", ok and item.count() == 1 and item.inner_text().strip().startswith("Add to dashboard"), item.count() and item.inner_text())
    page.keyboard.press("Escape")
    ok = add_solo(page, toolbar="bar", id_="barv")
    page.evaluate("() => document.getElementById('barv').openMenu('settings')")
    row = page.locator("#barv .dv-settings [data-act='add-dashboard']")
    check("menu: View settings (toolbar bar) has an \"Add to dashboard…\" row", ok and until(page, "() => document.querySelector(\"#barv .dv-settings [data-act='add-dashboard']\")", timeout=5000)
          and "Add to dashboard" in row.inner_text(), row.count() and row.inner_text())
    page.keyboard.press("Escape")
    ok = add_dash(page, "source.base", "src")
    for key, what in (("runs", "a table"), ("success-by-run", "a chart"), ("error-by-joint", "a time series"), ("tool-paths", "a 3D path"), ("success", "KPI cards")):
        with guard(f"menu: the {key} panel"):
            item = open_panel_menu(page, "src", key)
            check(f"menu: a dashboard panel of {what} ({key}) has \"Add to dashboard…\" on its menu", ok and "Add to dashboard" in item.inner_text(), item.inner_text())
            page.keyboard.press("Escape")
    with guard("menu: a KPI card"):
        item = open_item_menu(page, f"{panel_sel('src', 'success')} data-kpi[data-key='C'] .dv-kpi-label")
        check("menu: a KPI card's item menu (right-click) adds that card: 'Add “C” …'", "Add" in item.inner_text() and "C" in item.inner_text(), item.inner_text())
        page.keyboard.press("Escape")
    for key, series in (("success-by-run", "B"), ("error-by-joint", "J2"), ("tool-paths", "J2")):
        with guard(f"menu: the {key} legend"):
            item = open_item_menu(page, f"{panel_sel('src', key)} .dv-legend-key[data-legend-series='{series}']")
            only = page.locator(".dv-itemmenu:not([hidden]) [data-legend-only]")
            check(f"menu: a legend series ({key}: {series}) has an item menu with 'Add “{series}” …' and 'Show only'", series in item.inner_text() and only.count() == 1,
                  [item.inner_text(), only.count() and only.inner_text()])
            page.keyboard.press("Escape")
    with guard("menu: a field of the record peek"):
        page.locator("#solo tbody tr td").first.click()
        until(page, "() => document.querySelector('#solo .dv-peek:not([hidden]) .dv-peek-field[data-p=success]')", timeout=10000)
        item = open_item_menu(page, "#solo .dv-peek .dv-peek-field[data-p='success'] th")
        check("menu: a field of the record peek (a record's cell) has 'Add “Success rate” …' on its item menu", "Success rate" in item.inner_text(), item.inner_text())
        page.keyboard.press("Escape")
    check("menus: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- 2. a <data-views> round trip
def round_trip_view(browser, base):
    page = new_page(browser, base)
    page.evaluate(HOST, {"list": [TARGET_ENTRY], "listen": True, "answer": {"ok": True}})
    add_solo(page)
    # what the reader sees: robot A or B (the rail), "r1" typed in the search box, the success rate high to low
    page.evaluate("""() => { const v = document.getElementById('solo'); v.setFacet('robot', { values: ['A', 'B'] }); v.search('r1');
      v.setView({ sort: [{ property: 'success', direction: 'DESC' }] }); }""")
    settle(page, 3)
    want = solo_expected({"A", "B"}, "r1", "success")
    src = page.evaluate("() => document.getElementById('solo').model.rows.map((r) => String(r.id))")
    check("view: the source table draws the oracle's rows (robot A or B, 'r1' searched, success high to low)", src == want, {"drawn": src, "file": want})
    page.locator("#solo [data-menu='more']").click()
    page.locator("#solo .dv-pop [data-add-dashboard]").click()
    st = pick(page, "target")
    got = page.evaluate(LAST)
    check("view: the host's respondWith resolved: the picker says 'Added to Target'", st and st["state"] == "added" and "Target" in st["text"], st)
    check("view: the event is cancelable and carries {dashboard, panel, text, respondWith}", got and got["cancelable"] and got["respond"] == "function"
          and got["dashboard"]["id"] == "target" and isinstance(got["text"], str) and got["panel"] and got["panel"].get("view"), got and {k: got[k] for k in ("dashboard", "cancelable", "respond")})
    text = got["text"]
    same, bad = only_insertions(TARGET, text)
    check("view: the text keeps every byte of target.base apart from the inserted lines", same, bad)
    doc = parse(text)
    p, v = last_panel(doc)
    check("view: the dataset on the same file is reused (runs.json is the target's fleet), no dataset added", v and v.get("from") == "fleet" and datasets_of(doc) == datasets_of(parse(TARGET)),
          {"from": v and v.get("from"), "datasets": datasets_of(doc)})
    check("view: the view's name, taken in the target, takes a suffix: 'Runs (2)'; the panel keeps the title 'Runs'", v and v.get("name") == "Runs (2)" and (p.get("title") in (None, "Runs")), p)
    check("view: an added panel is full width (no w), so it goes below every other", "w" not in p, p)
    rep = checkers(text, "view")
    check("view: data-ui check and tools/check_views.py accept the text", rep["node_errors"] == 0 and rep["python"].startswith("checked") and " 0 errors" in rep["python"], rep)
    out, path, ok = load_text(page, text, "view")
    try:
        last = page.evaluate("(id) => { const d = document.getElementById(id); return d.dash.panels[d.dash.panels.length - 1].key; }", out)
        drawn = panel_rows(page, out, last, "success")
        ids = [r[0] for r in drawn or []]
        check("view: loaded, the new panel draws the same rows as the source (count, first and last)", ok and ids == src and len(ids) == len(want),
              {"count": len(ids), "first": drawn[:1] if drawn else None, "last": drawn[-1:] if drawn else None, "source first/last": [src[:1], src[-1:]]})
        below, m = below_all(page, out, last)
        check("view: the new panel sits below every other panel (getBoundingClientRect)", below, m)
        shot(page, "round-trip-view", f"#{out}")
        # Arrange moves it like any other: drag it onto the first panel, Done
        page.evaluate("() => localStorage.clear()")
        page.locator(f"#{out} [data-act=arrange]").click()
        until(page, f"() => document.querySelector('#{out} .dd-grid.grid-stack .grid-stack-item')", timeout=10000)
        first = boxes(page, out)[0]["key"]
        s = page.locator(panel_sel(out, last)).bounding_box()
        d = page.locator(panel_sel(out, first)).bounding_box()
        page.mouse.move(s["x"] + 40, s["y"] + 20)
        page.mouse.down()
        page.mouse.move(s["x"] + 40, s["y"] - 60, steps=6)
        page.mouse.move(d["x"] + 30, d["y"] + 10, steps=14)
        page.wait_for_timeout(300)
        page.mouse.up()
        page.wait_for_timeout(400)
        page.locator(f"#{out} [data-act=arrange]").click()
        until(page, f"() => !document.querySelector('#{out} .dd-grid.grid-stack')", timeout=10000)
        order = [b["key"] for b in boxes(page, out)]
        check("view: Arrange moves the added panel like any other (dragged to the top, it is first after Done)", order and order[0] == last, order)
    finally:
        path.unlink(missing_ok=True)
    check("view: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- 3. dashboard panels
def round_trip_dashboard(browser, base):
    page = new_page(browser, base)
    page.evaluate(HOST, {"list": [TARGET_ENTRY], "listen": True, "answer": {"ok": True}})
    add_dash(page, "source.base", "src")
    # a click on a run of robot B in the Runs table selects robot B for every other panel (and, through the link, the samples)
    row = page.evaluate("(sel) => document.querySelector(sel + ' data-views').model.rows.findIndex((r) => r.robot === 'B')", panel_sel("src", "runs"))
    page.locator(f"{panel_sel('src', 'runs')} tbody tr[data-i='{row}'] td").first.click()
    until(page, "() => { const s = document.getElementById('src').state.select.runs; return s && JSON.stringify(s.values) === '[\"B\"]'; }")
    settle(page, 3)

    # a chart panel narrowed by another panel's selection
    src = panel_rows(page, "src", "success-by-run", "success")
    want = [r["id"] for r in RUNS if r["robot"] == "B"]
    check("dashboard: the chart panel draws robot B's runs (the Runs panel's selection)", src and sorted(r[0] for r in src) == sorted(want), {"drawn": len(src or []), "file": len(want)})
    open_panel_menu(page, "src", "success-by-run").click()
    st = pick(page, "target")
    got = page.evaluate(LAST)
    close_picker(page)
    doc = parse(got["text"])
    p, v = last_panel(doc)
    out, path, ok = load_text(page, got["text"], "chart")
    try:
        key = page.evaluate("(id) => { const d = document.getElementById(id); return d.dash.panels[d.dash.panels.length - 1].key; }", out)
        drawn = panel_rows(page, out, key, "success")
        check("dashboard: a chart panel added under a selection draws the same rows in the target (count, first, last)", st and st["state"] == "added" and drawn == src,
              {"count": len(drawn or []), "first": (drawn or [None])[:1], "last": (drawn or [None])[-1:], "source": [len(src), src[:1], src[-1:]]})
        check("dashboard: ... and sits below every other panel", below_all(page, out, key)[0], below_all(page, out, key)[1])
        check("dashboard: ... its view takes no preset selection with it, and the text only inserts lines", v and "selected" not in v and only_insertions(TARGET, got["text"])[0], v)
    finally:
        path.unlink(missing_ok=True)

    # a series from a time series' legend: the view narrowed to that series
    src = panel_rows(page, "src", "error-by-joint", "err_mm")
    want = [r["id"] for r in SAMPLES if r["run"] == "r02"]
    check("dashboard: the time series panel draws run r02's samples (its own filter; robot B's runs through the link)", src and [r[0] for r in src] == want, {"drawn": len(src or []), "file": len(want)})
    open_item_menu(page, f"{panel_sel('src', 'error-by-joint')} .dv-legend-key[data-legend-series='J2']").click()
    st = pick(page, "target")
    got = page.evaluate(LAST)
    close_picker(page)
    doc = parse(got["text"])
    p, v = last_panel(doc)
    check("dashboard: a series added is the view with the other series hidden: hiddenSeries [J1, J3], on samples.json under a new name",
          st and st["state"] == "added" and v and sorted(v.get("hiddenSeries") or []) == ["J1", "J3"] and datasets_of(doc).get(v.get("from")) == "samples.json" and v.get("from") != "samples",
          {"view": v and {k: v.get(k) for k in ("name", "from", "hiddenSeries")}, "datasets": datasets_of(doc)})
    out, path, ok = load_text(page, got["text"], "series")
    try:
        key = page.evaluate("(id) => { const d = document.getElementById(id); return d.dash.panels[d.dash.panels.length - 1].key; }", out)
        drawn = panel_rows(page, out, key, "err_mm")
        pressed = page.evaluate("(sel) => [...document.querySelectorAll(sel + ' .dv-legend-key')].map((b) => [b.dataset.legendSeries, b.getAttribute('aria-pressed')])", panel_sel(out, key))
        check("dashboard: loaded, the series panel draws J2 alone (its legend: only J2 pressed) over the same rows", drawn == src and dict(pressed) == {"J1": "false", "J2": "true", "J3": "false"},
              {"pressed": pressed, "rows": len(drawn or [])})
        shot(page, "round-trip-series", panel_sel(out, key))
    finally:
        path.unlink(missing_ok=True)

    # a KPI card: the selection cleared, card C
    page.evaluate("() => document.getElementById('src').clearSelections()")
    settle(page, 3)
    src_num = page.locator(f"{panel_sel('src', 'success')} data-kpi[data-key='C'] .dv-kpi-num").inner_text()
    mean_c = statistics.fmean(r["success"] for r in RUNS if r["robot"] == "C")
    open_item_menu(page, f"{panel_sel('src', 'success')} data-kpi[data-key='C'] .dv-kpi-label").click()
    st = pick(page, "target")
    got = page.evaluate(LAST)
    close_picker(page)
    out, path, ok = load_text(page, got["text"], "kpi")
    try:
        key = page.evaluate("(id) => { const d = document.getElementById(id); return d.dash.panels[d.dash.panels.length - 1].key; }", out)
        cards = page.evaluate("(sel) => [...document.querySelectorAll(sel + ' data-kpi')].map((c) => [c.dataset.key, (c.querySelector('.dv-kpi-num') || {}).textContent])", panel_sel(out, key))
        check("dashboard: a KPI card added is that card alone: C, the same number, the file's mean", st and st["state"] == "added" and cards == [["C", src_num]] and abs(float(src_num) - mean_c) < 1e-4,
              {"cards": cards, "source": src_num, "file mean": round(mean_c, 6)})
    finally:
        path.unlink(missing_ok=True)

    # "At this moment": the 3D path pinned at the instant the dashboard's clock stands at
    page.evaluate("() => document.getElementById('src').clock.seek(1.2)")
    settle(page, 2)
    open_panel_menu(page, "src", "tool-paths").click()
    st = pick(page, "target", at_moment=True)
    got = page.evaluate(LAST)
    close_picker(page)
    p, v = last_panel(parse(got["text"]))
    check("dashboard: 'At this moment' writes the instant on the panel (t: 1.2)", st and st["state"] == "added" and p.get("t") == 1.2, p)
    out, path, ok = load_text(page, got["text"], "moment")
    try:
        key = page.evaluate("(id) => { const d = document.getElementById(id); return d.dash.panels[d.dash.panels.length - 1].key; }", out)
        m = page.evaluate("""([id, sel]) => { const el = document.querySelector(sel + ' data-views'); const c = window.kit.clockFor(el);
          const at = document.querySelector(sel + ' .dd-at'); return { t: c.t, own: c !== document.getElementById(id).clock, dash: document.getElementById(id).clock.t, at: at && at.textContent }; }""", [out, panel_sel(out, key)])
        check("dashboard: loaded, the pinned panel's views read a clock of their own at t = 1.2, not the dashboard's, and its header says when", m["own"] and abs(m["t"] - 1.2) < 1e-9 and m["at"] and "1.2" in m["at"], m)
    finally:
        path.unlink(missing_ok=True)
    check("dashboard: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- 4. dedup and rename
def dedup(browser, base):
    page = new_page(browser, base)
    page.evaluate(HOST, {"list": [TARGET_ENTRY], "listen": True, "answer": {"ok": True}})
    add_dash(page, "source.base", "src")
    texts = [TARGET]
    for i, key in enumerate(("runs", "runs", "error-by-joint", "error-by-joint")):
        # the host now offers the text it saved: the next add appends to it
        page.evaluate("(text) => { window.hostCfg.list = [{ id: 'target', title: 'Target', url: '" + URL + "target.base', text }]; }", texts[-1])
        open_panel_menu(page, "src", key).click()
        st = pick(page, "target")
        texts.append(page.evaluate(LAST)["text"])
        close_picker(page)
        check(f"dedup: add {i + 1} ({key}) only inserts lines into the text before it", st and st["state"] == "added" and only_insertions(texts[-2], texts[-1])[0], only_insertions(texts[-2], texts[-1])[1])
    doc = parse(texts[-1])
    names = [v.get("name") for v in doc["views"]]
    ds = datasets_of(doc)
    check("dedup: the same file is one dataset (runs.json stays fleet; samples.json comes in once, as samples_2), never twice",
          ds == {"fleet": "runs.json", "samples": "other-samples.json", "samples_2": "samples.json"}, ds)
    check("dedup: names that collide take a suffix: Runs (2), Runs (3), Error by joint, Error by joint (2)",
          names[-4:] == ["Runs (2)", "Runs (3)", "Error by joint", "Error by joint (2)"], names)
    keys = page.evaluate("(text) => { const d = window.kit.parseBase(text); return d.layout.panels.length; }", texts[-1])
    check("dedup: four panels added at the bottom, in order", keys == len(parse(TARGET)["layout"]["panels"]) + 4 and [p.get("view") for p in doc["layout"]["panels"][-4:]] == names[-4:],
          [p.get("view") for p in doc["layout"]["panels"]])
    rep = checkers(texts[-1], "dedup")
    check("dedup: data-ui check and tools/check_views.py accept the text after four adds", rep["node_errors"] == 0 and " 0 errors" in rep["python"], rep)
    check("dedup: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- 5. no host
def clipboard(browser, base):
    page = new_page(browser, base, clipboard=True)
    add_solo(page)
    page.locator("#solo [data-menu='more']").click()
    page.locator("#solo .dv-pop [data-add-dashboard]").click()
    picker = page.locator(".dv-addpick:not([hidden])").first
    picker.wait_for(state="visible", timeout=WAIT)
    settle(page)
    listed = picker.locator("[data-dashboard-id]").count()
    picker.locator("[data-dashboard-new]").click()
    picker.locator("input[name='dashboard-title']").fill("Scratch")
    picker.locator("[data-dashboard-create]").click()
    st = status(page)
    clip = page.evaluate("() => navigator.clipboard.readText()")
    want = page.evaluate("() => window.kit.appendPanel('', document.getElementById('solo').panelSpec(), { title: 'Scratch' })")
    check("no host: with no dashboards() hook the picker lists none and offers New dashboard…", listed == 0, listed)
    check("no host: with no listener the new dashboard's text goes to the clipboard, and the picker says so", st and st["state"] == "copied" and "clipboard" in st["text"].lower() and clip == want,
          {"status": st, "clipboard starts": (clip or "")[:60]})
    doc = parse(clip or "")
    check("no host: ... a valid new dashboard: '# Scratch', one dataset, the view, one panel", (clip or "").startswith("# Scratch\n") and len(doc.get("layout", {}).get("panels", [])) == 1
          and len(datasets_of(doc)) == 1 and doc["views"][0].get("name") == "Runs", {"datasets": datasets_of(doc), "views": [v.get("name") for v in doc.get("views", [])]})
    check("no host: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- 6. a host's answers
def answers(browser, base):
    page = new_page(browser, base)
    page.evaluate(HOST, {"list": [TARGET_ENTRY], "listen": True, "answer": "reject", "reason": "disk full"})
    add_solo(page)
    page.locator("#solo [data-menu='more']").click()
    page.locator("#solo .dv-pop [data-add-dashboard]").click()
    st = pick(page, "target")
    check("host: a rejected respondWith shows the host's error", st and st["state"] == "error" and "disk full" in st["text"], st)
    close_picker(page)
    page.evaluate("() => { window.hostCfg.answer = { ok: false, reason: 'the dashboard is read-only' }; }")
    page.locator("#solo [data-menu='more']").click()
    page.locator("#solo .dv-pop [data-add-dashboard]").click()
    st = pick(page, "target")
    check("host: {ok: false, reason} shows the reason", st and st["state"] == "error" and "read-only" in st["text"], st)
    close_picker(page)
    page.evaluate("() => { window.hostCfg.answer = 'take-over'; }")
    page.locator("#solo [data-menu='more']").click()
    page.locator("#solo .dv-pop [data-add-dashboard]").click()
    picker = page.locator(".dv-addpick:not([hidden])").first
    picker.locator("[data-dashboard-id='target']").click()
    gone = until(page, "() => !document.querySelector('.dv-addpick:not([hidden])')", timeout=5000)
    check("host: a host that takes over (preventDefault, no respondWith) gets the picker closed", gone)
    page.evaluate("() => { window.hostCfg.listError = 'the index is down'; }")
    page.locator("#solo [data-menu='more']").click()
    page.locator("#solo .dv-pop [data-add-dashboard]").click()
    ok = until(page, "() => { const p = document.querySelector('.dv-addpick:not([hidden])'); return p && /the index is down/.test(p.textContent) && p.querySelector('[data-dashboard-new]'); }", timeout=10000)
    check("host: a dashboards() that fails is said in the picker, and New dashboard… is still there", ok)
    check("host: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- 7. themes and widths
def looks(browser, base):
    for width, dark in ((1280, False), (1280, True), (390, False), (390, True)):
        tag = f"{width} px, {'dark' if dark else 'light'}"
        page = new_page(browser, base, width=width, dark=dark)
        page.evaluate(HOST, {"list": [TARGET_ENTRY, {"id": "fleet", "title": "Fleet overview", "url": URL + "target.base"}], "listen": True, "answer": {"ok": True}})
        add_solo(page)
        page.locator("#solo [data-menu='more']").click()
        page.locator("#solo .dv-pop [data-add-dashboard]").click()
        picker = page.locator(".dv-addpick:not([hidden])").first
        picker.wait_for(state="visible", timeout=WAIT)
        until(page, "() => document.querySelector('.dv-addpick [data-dashboard-id]')", timeout=10000)
        settle(page)
        m = page.evaluate("""() => { const p = document.querySelector('.dv-addpick:not([hidden])'); const r = p.getBoundingClientRect();
          const bg = getComputedStyle(p).backgroundColor.match(/[\\d.]+/g).map(Number); const lum = (0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2]) / 255;
          return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, vw: innerWidth, vh: innerHeight, scroll: document.scrollingElement.scrollWidth, lum }; }""")
        inside = m["left"] >= 0 and m["right"] <= m["vw"] and m["top"] >= 0 and m["bottom"] <= m["vh"]
        check(f"{tag}: the picker is inside the viewport and the page never scrolls sideways", inside and m["scroll"] <= width, m)
        check(f"{tag}: the picker takes the theme's colours", (m["lum"] < 0.3) if dark else (m["lum"] > 0.7), m["lum"])
        shot(page, f"picker-{'dark' if dark else 'light'}-{width}")
        close_picker(page)
        add_dash(page, "source.base", "src")
        with guard(f"{tag}: a dashboard panel's menu"):
            open_panel_menu(page, "src", "error-by-joint").click()
            ok = until(page, "() => document.querySelector('.dv-addpick:not([hidden]) [data-dashboard-id]')", timeout=10000)
            r = page.evaluate("() => { const r = document.querySelector('.dv-addpick:not([hidden])').getBoundingClientRect(); return [r.left, r.right, innerWidth, document.scrollingElement.scrollWidth]; }")
            check(f"{tag}: from a dashboard panel's menu the picker opens inside the viewport", ok and r[0] >= 0 and r[1] <= r[2] and r[3] <= width, r)
            shot(page, f"panel-picker-{'dark' if dark else 'light'}-{width}")
            close_picker(page)
        check(f"{tag}: no page error", not page.errors, page.errors[:3])
        page.context.close()


def main() -> int:
    if not (ROOT / "dist" / "data-ui.js").exists() or not (ROOT / "dist" / "dashboard.js").exists():
        print("the kit is not built: npm --prefix ~/data-ui run build")
        return 1
    proc, base = serve(ROOT, PAGE)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for name, fn in (("where the item is", menus), ("a <data-views> round trip", round_trip_view), ("dashboard panels", round_trip_dashboard),
                             ("dedup and rename", dedup), ("no host", clipboard), ("a host's answers", answers), ("themes and widths", looks)):
                with guard(name):
                    fn(browser, base)
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        for stale in FIX.glob(f"_a2d-*{os.getpid()}*.base"):
            stale.unlink(missing_ok=True)
    (OUT / "add-to-dashboard-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} add-to-dashboard checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
