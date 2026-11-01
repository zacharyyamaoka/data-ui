"""PEP 0010 P3, navigation (docs/peps/0010-robotics-playback.md §8, §11 P3), measured in headless Chromium on the built
kit and site. Written red, before the code; never edited after.

    ~/psu-atlas/.venv/bin/python tests/browser/p3_checks.py [OUT_DIR]     # after npm run build

The case is gallery/examples/robotics-deployments: deployments → runs → one run's playback, one <data-dashboard> on the
rack's real runs. What these checks take from its views.base (and nothing else): the datasets whose `data:` is a
template (`runs/{run}.json`: loaded when exactly one run is picked), the panels whose views read them, the `runs` panel
(the runs table, `select: run`, `selected: first`) and the `deployments` panel (`select: deployment`, `selected: first`).
Every expected number comes from the case's own files, read here with Python (the oracle is the file, never the page):
runs.json's newest `started`, runs/<run>.json's min..max t and q_deg.
  - picking one run fetches exactly runs/<run>.json (the network log) and the clock spans exactly its t;
  - two picks (a ctrl-click adds the second) show "Pick one run" in every panel reading the per-run dataset, fetch
    nothing, and leave the clock without a span;
  - Back and Forward restore the pick and t (each pick one history entry, a seek none), and fetch no file twice;
  - the newest run is the runs table's first row and opens by default (selected on load, in the URL, its one file);
  - a one-way link narrows only its `to` side: tests/browser/fixtures/p3/oneway.base against twoway.base (the same link
    two-way), the rail counts on both sides measured against the fixture's files; the kit gaps' driver fixture, now
    one-way, lists every run; the case's own Show pick leaves the runs' rail as it was;
  - a preset selection in the .base is selected on load and in the URL (the case's `first`, the fixture's `r3`), and a
    link that clears it (`s.runs=`) keeps it cleared through a reload;
  - the robotics templates' runs tables pick a run (the P1c deviation): a click on a row moves the rail's Run pick;
  - light and dark, at 1280 and 390 px.
Serves the repo root and dist/site on free 127.0.0.1 ports, stops both when done, writes OUT_DIR/p3-checks.json (default
reports/media/robotics-p3) and exits 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "robotics-p3"
OUT.mkdir(parents=True, exist_ok=True)
SITE = ROOT / "dist" / "site"
EX = ROOT / "gallery" / "examples"
CASE = "robotics-deployments"
HERE = EX / CASE
FIX = ROOT / "tests" / "browser" / "fixtures" / "p3"
PAGE = "/tests/browser/fixtures/p3/p3.html"
FIXURL = "/tests/browser/fixtures/p3/"
DRIVER_MARKS = "/tests/browser/fixtures/kit_gaps/driver-marks.base"
WAIT = 45000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
checks: list[dict] = []

sys.path.insert(0, str(ROOT / "packages" / "core" / "python"))
import data_ui_base  # noqa: E402  the stdlib .base reader, the Python twin of base.js


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str)[:400]}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    """A section that cannot run (the case missing, nothing drawn to measure) is one failing check in its own words."""
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


# ------------------------------------------------------------------------------------------------- the files
def rows(path):
    doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return doc["rows"] if isinstance(doc, dict) else doc


def slug(text):
    """core format.js slug: a panel's key from its key, title or first view's name."""
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", str(text).lower()))


def enc(value):
    """One URL path segment, as encodeURIComponent writes it (the template fills `{run}` so)."""
    return urllib.parse.quote(str(value), safe="-_.!~*'()")


def case_base():
    return data_ui_base.loads((HERE / "views.base").read_text(encoding="utf-8"))


def templated(base):
    """{dataset: data} for each dataset whose data: names a placeholder."""
    out = {}
    for name, entry in (base.get("datasets") or {}).items():
        data = entry if isinstance(entry, str) else (entry or {}).get("data")
        if isinstance(data, str) and re.search(r"\{[^{}]+\}", data):
            out[name] = data
    return out


def panels_reading(base, datasets):
    """The layout's panel keys whose views read one of `datasets` (model.js readDashboard's key rule)."""
    views = {v.get("name"): v for v in base.get("views") or []}
    keys, out = set(), []
    for p in (base.get("layout") or {}).get("panels") or []:
        names = p.get("views") or ([p["view"]] if p.get("view") else [])
        if not names:
            continue
        key = slug(p.get("key") or p.get("title") or names[0]) or "panel"
        while key in keys:
            key += "-2"
        keys.add(key)
        if any((views.get(n) or {}).get("from") in datasets for n in names):
            out.append(key)
    return out


def run_file(run):
    return HERE / "runs" / f"{run}.json"


def span(run):
    ts = [r["t"] for r in rows(run_file(run)) if isinstance(r.get("t"), (int, float))]
    return [min(ts), max(ts)] if ts else None


def series_points(run, y):
    """{situation: [(t, value)…]} of a run's file, sorted by t, the nulls left out (a timeseries draws a gap there)."""
    out = {}
    for r in rows(run_file(run)):
        v = r.get(y)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and isinstance(r.get("t"), (int, float)):
            out.setdefault(r["situation"], []).append((r["t"], v))
    for s in out.values():
        s.sort()
    return out


def compare_points(drawn, want):
    bad = []
    for s in sorted(set(drawn or {}) | set(want)):
        d, w = sorted((drawn or {}).get(s, [])), want.get(s, [])
        if len(d) != len(w):
            bad.append({"series": s, "drawn": len(d), "file": len(w)})
        elif any(a[0] != b[0] or a[1] != b[1] for a, b in zip(d, w)):
            i = next(i for i, (a, b) in enumerate(zip(d, w)) if a[0] != b[0] or a[1] != b[1])
            bad.append({"series": s, "first differing point": i, "drawn": d[i], "file": w[i]})
    return bad


def round3(x):
    """An instant the URL writes as it is (writeClockParams keeps 3 decimals)."""
    return float(f"{x:.3f}")


# ------------------------------------------------------------------------------------------------- page helpers
SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"


def panel_js(root):
    return f"(k) => document.querySelector(`{root} .dd-panel[data-panel='${{k}}']`)"


def ready_js(root):
    return f"""(keys) => {{
  const d = document.querySelector('{root}'); if (!d || !d.dash) return false;
  if (keys.some((k) => !document.querySelector(`{root} .dd-panel[data-panel='${{k}}']`))) return false;
  const els = [...d.querySelectorAll('.dd-panel data-views')]; if (!els.length || !els.every((e) => e.dataset.view)) return false;
  return [...d.querySelectorAll('.dd-rail data-facets')].every((f) => f.querySelector('details')); }}"""


def points_js(root):
    return f"""(k) => {{ const p = ({panel_js(root)})(k); const plot = p && p.querySelector('.dv-timeseries-plot'); const v = plot && plot.parentElement.vegaView;
  if (!v) return null; const out = {{}}; for (const d of v.data('series')) (out[d.series] = out[d.series] || []).push([d.x, d.value]); return out; }}"""


def clock_js(root):
    return f"() => {{ const c = document.querySelector('{root}').clock; return {{ start: c.start, end: c.end, t: c.t }}; }}"


def select_js(root):
    return f"(k) => {{ const s = document.querySelector('{root}').state.select[k]; return s ? s.values : null; }}"


def table_js(root):
    """A table panel's runs in the order it draws them (its row model), each cell's value."""
    return f"""([k, p]) => {{ const sec = ({panel_js(root)})(k); const el = sec && sec.querySelector('data-views'); const m = el && el.model;
  return m ? m.rows.map((r) => (r[p] && typeof r[p] === 'object' && !Array.isArray(r[p]) ? r[p].value : r[p])) : null; }}"""


# every rail: {dataset: {group key: [[label, count, checked]…]}} ('Any' left out)
RAIL = """(root) => { const out = {};
  for (const f of document.querySelectorAll(`${root} .dd-rail data-facets`)) {
    const groups = {};
    for (const g of f.querySelectorAll('section.df-group')) groups[g.dataset.key] = [...g.querySelectorAll('li')].map((li) => { const i = li.querySelector('input');
      return { label: ((li.querySelector('.df-label') || {}).textContent || '').trim(), count: Number(((li.querySelector('.df-count') || {}).textContent || '').replace(/,/g, '')),
        value: i ? i.dataset.value : null, checked: i ? i.checked : null }; }).filter((x) => x.value !== '');
    out[f.dataset.dataset] = groups;
  }
  return out; }"""

# each panel's drawn "N of M"
COUNTS = """(root) => { const out = {};
  for (const sec of document.querySelectorAll(`${root} .dd-panel[data-panel]`)) {
    const s = sec.querySelector('data-views .dv-status'); if (!s) continue;
    const m = /([\\d,]+) of ([\\d,]+)/.exec(s.textContent);
    if (m) out[sec.dataset.panel] = [Number(m[1].replace(/,/g, '')), Number(m[2].replace(/,/g, ''))];
  }
  return out; }"""

# the text a panel shows (innerText: what is rendered, so a hidden element's text is not in it)
SHOWN = """([root, k]) => { const sec = document.querySelector(`${root} .dd-panel[data-panel='${k}']`); return sec ? sec.innerText : null; }"""

# a table panel's drawn rows: [index, the first cell's background, the row's text] (the pointer moved away first)
MARKS = """([root, k]) => { const sec = document.querySelector(`${root} .dd-panel[data-panel='${k}']`);
  return sec ? [...sec.querySelectorAll('tbody tr[data-i]')].map((tr) => [Number(tr.dataset.i), getComputedStyle(tr.querySelector('td')).backgroundColor]) : []; }"""


def settle(page, n=2):
    for _ in range(n):
        page.evaluate(SETTLE)


def until(page, js, arg=None, timeout=WAIT):
    """Wait for a state; False when it never comes (the check that reads it says so in its own words)."""
    try:
        page.wait_for_function(js, arg=arg, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False


def new_page(browser, *, width=1280, dark=False):
    mobile = width < 500
    context = browser.new_context(viewport={"width": width, "height": 1000 if width > 500 else 844}, color_scheme="dark" if dark else "light",
                                  device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.errors, page.reqs = [], []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.on("request", lambda r: page.reqs.append(r.url))
    return page


def run_files(page, since=0):
    """The per-run files the page asked for since request number `since`, as paths under the case."""
    return [u.split(f"/{CASE}/", 1)[1] for u in page.reqs[since:] if f"/{CASE}/runs/" in u]


def open_case(browser, site, *, width=1280, dark=False, hash_="", keys=("deployments", "runs", "playback")):
    page = new_page(browser, width=width, dark=dark)
    page.goto(f"{site}/gallery/{CASE}/index.html{hash_}")
    ok = until(page, ready_js("#example"), list(keys))
    settle(page, 3)
    return page, ok


def click_row(page, root, key, i, add=False):
    """A click on a table panel's row i (ctrl-click with add: the second pick)."""
    cell = page.locator(f"{root} .dd-panel[data-panel='{key}'] tbody tr[data-i='{i}'] td").first
    cell.scroll_into_view_if_needed()
    cell.click(modifiers=["Control"] if add else None)
    page.mouse.move(1, 1)


def wait_selected(page, root, key, values):
    return until(page, f"([k, want]) => {{ const s = document.querySelector('{root}').state.select[k]; return JSON.stringify(s ? s.values : null) === JSON.stringify(want); }}", [key, values])


def wait_span(page, root, want):
    return until(page, f"(want) => {{ const c = document.querySelector('{root}').clock; return JSON.stringify([c.start, c.end]) === JSON.stringify(want); }}", want)


def hash_selection(page, key):
    """The run(s) the URL's s.<key>= names, decoded as readHash reads them; None when absent, [] when empty."""
    h = urllib.parse.parse_qs(urllib.parse.urlsplit(page.url).fragment, keep_blank_values=True)
    if f"s.{key}" not in h:
        return None
    text = h[f"s.{key}"][0]
    if ":" not in text:
        return []
    return [urllib.parse.unquote(x) for x in text.split(":", 1)[1].split(",") if x != ""]


def hash_t(page):
    h = urllib.parse.parse_qs(urllib.parse.urlsplit(page.url).fragment)
    return float(h["t"][0]) if "t" in h else None


def no_sideways(page, width):
    return page.evaluate("() => document.scrollingElement.scrollWidth") <= width


def shot(page, name, root="#example"):
    try:
        page.evaluate(f"() => {{ const d = document.querySelector('{root}'); if (d) window.scrollTo(0, d.getBoundingClientRect().top + window.scrollY - 60); }}")
        settle(page)
        page.locator(root).screenshot(path=str(OUT / f"{name}.png"))
    except Exception as e:  # noqa: BLE001 -- a missing picture is not a failed behaviour; say so
        print(f"(screenshot {name} not taken: {e})")


# ------------------------------------------------------------------------------------------------- the case's files
def files():
    for f in ("views.base", "README.md", "deployments.json", "runs.json", "source/build.py"):
        check(f"files: {CASE} has {f}", (HERE / f).exists(), str((HERE / f).relative_to(ROOT)))
    runs = rows(HERE / "runs.json")
    bad = [r["run"] for r in runs if not run_file(r["run"]).exists() or any(x.get("run") != r["run"] for x in rows(run_file(r["run"])))]
    check(f"files: every run of runs.json ({len(runs)}) has runs/<run>.json, every row of which is that run's", runs and not bad, bad[:5])
    stray = sorted(p.stem for p in (HERE / "runs").glob("*.json")) if (HERE / "runs").exists() else []
    check("files: runs/ holds no file for a run runs.json does not list", set(stray) == {r["run"] for r in runs}, sorted(set(stray) ^ {r["run"] for r in runs})[:5])
    started = sorted((r["started"] for r in runs), reverse=True)
    check("files: one run is the newest (no tie on started), so 'newest first' names one run", len(started) > 2 and started[0] != started[1], started[:2])
    deps = rows(HERE / "deployments.json")
    check("files: every run's deployment is a row of deployments.json", deps and {r["deployment"] for r in runs} <= {d["deployment"] for d in deps},
          sorted({r["deployment"] for r in runs} - {d["deployment"] for d in deps}))
    readme = (HERE / "README.md").read_text(encoding="utf-8") if (HERE / "README.md").exists() else ""
    check("files: the README says the data is the rack's real runs, read from ~/… (never a home path)", "real" in readme.lower() and "/home/" not in readme, None)
    base = case_base()
    t = templated(base)
    check("files: views.base names a per-run dataset (data: runs/{run}.json)", list(t.values()) == ["runs/{run}.json"], t)
    views = {v.get("name"): v for v in base.get("views") or []}
    runs_view = next((v for v in views.values() if v.get("select") == "run"), {})
    check("files: the runs table selects a run and opens on its first row (select: run, selected: first), newest first",
          runs_view.get("selected") == "first" and runs_view.get("sort") == [{"property": "started", "direction": "DESC"}], {k: runs_view.get(k) for k in ("select", "selected", "sort")})


def newest():
    return max(rows(HERE / "runs.json"), key=lambda r: r["started"])["run"]


def order():
    return [r["run"] for r in sorted(rows(HERE / "runs.json"), key=lambda r: r["started"], reverse=True)]


# ------------------------------------------------------------------------------------------------- the case
def case_main(browser, site):
    base = case_base()
    per_run = panels_reading(base, templated(base))
    first = newest()
    page, ok = open_case(browser, site, keys=["deployments", "runs", "playback", *per_run])
    check(f"case: every panel draws (deployments, runs, playback and the per-run panels {per_run})", ok and per_run, per_run)
    got = page.evaluate(table_js("#example"), ["runs", "run"])
    check("newest first: the runs table draws every run of runs.json, newest first (runs.json's started)", got == order(), {"drawn": (got or [])[:3], "file": order()[:3], "n": [len(got or []), len(order())]})
    ok_sel = wait_selected(page, "#example", "runs", [first])
    check(f"opens by default: the newest run ({first}) is selected when the page opens", ok_sel, page.evaluate(select_js("#example"), "runs"))
    check("preset in the URL: the hash names the newest run (s.runs=run:<newest>), the preset written as the selection it made", hash_selection(page, "runs") == [first], page.url.split("#", 1)[-1][:200])
    dep = rows(HERE / "deployments.json")[0]["deployment"]
    check(f"preset: the deployments table's selected: first selects its first row ({dep}), on load and in the URL",
          page.evaluate(select_js("#example"), "deployments") == [dep] and hash_selection(page, "deployments") == [dep],
          {"state": page.evaluate(select_js("#example"), "deployments"), "url": hash_selection(page, "deployments")})
    want = span(first)
    ok_span = wait_span(page, "#example", want)
    check(f"opens by default: exactly one per-run file is fetched, runs/{enc(first)}.json", run_files(page) == [f"runs/{enc(first)}.json"], run_files(page))
    check(f"opens by default: the clock spans exactly the newest run's t, min..max of its file {want}", ok_span, page.evaluate(clock_js("#example")))
    angle = next((k for k in per_run if k == "angle"), per_run[0] if per_run else None)
    drawn = page.evaluate(points_js("#example"), angle)
    bad = compare_points(drawn, series_points(first, "q_deg"))
    check(f"opens by default: panel {angle} draws exactly runs/{first}.json's q_deg, every situation, every sample", drawn and not bad, bad[:3])
    marks = page.evaluate(MARKS, ["#example", "runs"])
    others = [bg for i, bg in marks if i != 0]
    check("the runs table marks the selected row (row 0): its cells' background is no other drawn row's",
          marks and marks[0][0] == 0 and marks[0][1] not in others and len(set(others)) == 1, marks[:4])

    # one pick: the third row
    order_ = order()
    b, c = order_[2], order_[4]
    n0 = len(page.reqs)
    click_row(page, "#example", "runs", 2)
    ok_sel = wait_selected(page, "#example", "runs", [b])
    ok_span = wait_span(page, "#example", span(b))
    check(f"pick: a click on the runs table's row selects that run ({b})", ok_sel, page.evaluate(select_js("#example"), "runs"))
    check(f"pick: picking one run fetches exactly runs/{enc(b)}.json (the network log since the click)", run_files(page, n0) == [f"runs/{enc(b)}.json"], run_files(page, n0))
    check(f"pick: the clock spans exactly {b}'s t {span(b)}", ok_span, page.evaluate(clock_js("#example")))
    drawn = page.evaluate(points_js("#example"), angle)
    bad = compare_points(drawn, series_points(b, "q_deg"))
    check(f"pick: panel {angle} draws exactly runs/{b}.json's q_deg", drawn and not bad, bad[:3])
    check("pick: the URL names the picked run (s.runs=run:<run>)", hash_selection(page, "runs") == [b], hash_selection(page, "runs"))

    # two picks: a ctrl-click adds the fifth row
    n1 = len(page.reqs)
    click_row(page, "#example", "runs", 4, add=True)
    ok_sel = wait_selected(page, "#example", "runs", [b, c])
    check(f"two picks: a ctrl-click adds a second run ({b}, {c})", ok_sel, page.evaluate(select_js("#example"), "runs"))
    ok_pick = until(page, f"([root, keys]) => keys.every((k) => (document.querySelector(`${{root}} .dd-panel[data-panel='${{k}}']`).innerText || '').includes('Pick one run'))", ["#example", per_run])
    shown = {k: (page.evaluate(SHOWN, ["#example", k]) or "")[:80] for k in per_run}
    check(f"two picks show 'Pick one run' in every panel reading the per-run dataset ({', '.join(per_run)})", ok_pick, shown)
    check("two picks: no per-run file is fetched", run_files(page, n1) == [], run_files(page, n1))
    ck = page.evaluate(clock_js("#example"))
    check("two picks: the clock has no span (no run's samples are loaded)", ck["start"] is None and ck["end"] is None, ck)
    drawn = page.evaluate(points_js("#example"), angle)
    check(f"two picks: panel {angle} draws no sample", not drawn or not any(drawn.values()), {k: len(v) for k, v in (drawn or {}).items()})
    shot(page, "pick-one-run-light-1280")
    # the ctrl-click again takes the second away: one run, read before, drawn from what was fetched
    click_row(page, "#example", "runs", 4, add=True)
    ok_sel = wait_selected(page, "#example", "runs", [b])
    ok_span = wait_span(page, "#example", span(b))
    gone = until(page, f"([root, keys]) => keys.every((k) => !(document.querySelector(`${{root}} .dd-panel[data-panel='${{k}}']`).innerText || '').includes('Pick one run'))", ["#example", per_run])
    check(f"back to one pick: a second ctrl-click takes {c} away; {b} draws again from the file already read (no request), 'Pick one run' gone",
          ok_sel and ok_span and gone and run_files(page, n1) == [], {"select": page.evaluate(select_js("#example"), "runs"), "fetched": run_files(page, n1)})

    # one-way on the case: the samples' Show pick leaves the runs' rail and table as they were
    rail0 = page.evaluate(RAIL, "#example")
    target = next((k for k, v in rail0.items() if k != "runs" and v), None)
    group = next(iter(rail0.get(target) or {}), None) if target else None
    values = [x["value"] for x in (rail0.get(target) or {}).get(group, [])]
    if target and values:
        page.locator(f"#example .dd-rail data-facets[data-dataset='{target}'] section.df-group[data-key='{group}'] input[data-value='{values[-1]}']").check()
        settle(page, 4)
        rail1 = page.evaluate(RAIL, "#example")
        same = {g: [(x["label"], x["count"]) for x in v] for g, v in (rail0.get("runs") or {}).items()} == {g: [(x["label"], x["count"]) for x in v] for g, v in (rail1.get("runs") or {}).items()}
        check(f"one-way (case): a pick on the {target} rail ({group} = {values[-1]}) leaves the runs rail's counts and the runs table as they were",
              same and page.evaluate(table_js("#example"), ["runs", "run"]) == order(), {"runs rail before": rail0.get("runs"), "after": rail1.get("runs")})
    else:
        check("one-way (case): the per-run dataset has a rail to pick on", False, list(rail0))
    check("case: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- Back and Forward
def history(browser, site, width=1280, dark=False):
    base = case_base()
    per_run = panels_reading(base, templated(base))
    angle = next((k for k in per_run if k == "angle"), per_run[0] if per_run else None)
    look = f"{width} px, {'dark' if dark else 'light'}"
    page, ok = open_case(browser, site, width=width, dark=dark, keys=["deployments", "runs", "playback", *per_run])
    a = newest()
    o = order()
    b, c = o[1], o[3]
    ok = ok and wait_selected(page, "#example", "runs", [a]) and wait_span(page, "#example", span(a))
    check(f"history, {look}: the case opens on the newest run", ok, page.evaluate(select_js("#example"), "runs"))
    h0 = page.evaluate("() => history.length")
    click_row(page, "#example", "runs", 1)
    wait_selected(page, "#example", "runs", [b])
    wait_span(page, "#example", span(b))
    tb = round3(span(b)[0] + 0.4 * (span(b)[1] - span(b)[0]))
    page.evaluate("(t) => { const c = document.querySelector('#example').clock; c.pause(); c.seek(t); }", tb)
    settle(page, 2)
    h1 = page.evaluate("() => history.length")
    click_row(page, "#example", "runs", 3)
    wait_selected(page, "#example", "runs", [c])
    wait_span(page, "#example", span(c))
    tc = round3(span(c)[0] + 0.7 * (span(c)[1] - span(c)[0]))
    page.evaluate("(t) => { const c = document.querySelector('#example').clock; c.pause(); c.seek(t); }", tc)
    settle(page, 2)
    h2 = page.evaluate("() => history.length")
    check(f"history, {look}: each pick is one history entry, a seek none", h1 == h0 + 1 and h2 == h1 + 1, [h0, h1, h2])
    check(f"history, {look}: the URL holds the pick and its t (s.runs=run:{c}, t={tc})", hash_selection(page, "runs") == [c] and hash_t(page) == tc, page.url.split("#", 1)[-1][:200])
    fetched = run_files(page)

    def at(name, run, t, home=False):
        ok_sel = wait_selected(page, "#example", "runs", [run])
        ok_span = wait_span(page, "#example", span(run))
        if not home:
            until(page, "(t) => document.querySelector('#example').clock.t === t", t)
        ck = page.evaluate(clock_js("#example"))
        drawn = page.evaluate(points_js("#example"), angle)
        bad = compare_points(drawn, series_points(run, "q_deg"))
        want_t = span(run)[0] if home else t
        check(f"{name}, {look}: the pick is {run} again (state and URL), the clock spans its t and t = {want_t}{' (its start: that entry has no t)' if home else ''}, {angle} draws its file",
              ok_sel and ok_span and hash_selection(page, "runs") == [run] and ck["t"] == want_t and drawn and not bad,
              {"select": page.evaluate(select_js("#example"), "runs"), "clock": ck, "bad": bad[:2]})

    page.go_back()
    at("Back", b, tb)
    page.go_back()
    at("Back again", a, None, home=True)
    page.go_forward()
    at("Forward", b, tb)
    page.go_forward()
    at("Forward again", c, tc)
    check(f"history, {look}: Back and Forward fetched no file a second time", run_files(page) == fetched and len(set(fetched)) == len(fetched), {"before": fetched, "after": run_files(page)})
    page.reload()
    until(page, ready_js("#example"), ["deployments", "runs", "playback", *per_run])
    at("reload", c, tc)
    check(f"history, {look}: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- fixtures: presets, one-way
MOUNT = """([id, src]) => {
  for (const old of document.querySelectorAll('data-dashboard')) old.remove();
  const d = document.createElement('data-dashboard'); d.id = id; d.setAttribute('src', src); document.body.append(d); return true; }"""


def open_fixture(browser, base, src, keys, *, hash_="", width=1280, dark=False):
    page = new_page(browser, width=width, dark=dark)
    page.goto(f"{base}{PAGE}{hash_}")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    page.evaluate(MOUNT, ["dash", src])
    ok = until(page, ready_js("#dash"), keys)
    settle(page, 3)
    return page, ok


def presets(browser, base):
    runs, samples = rows(FIX / "runs.json"), rows(FIX / "samples.json")
    r3 = [s for s in samples if s["run"] == "r3"]
    page, ok = open_fixture(browser, base, FIXURL + "preset.base", ["runs", "samples"])
    ok = ok and wait_selected(page, "#dash", "runs", ["r3"])
    n = page.evaluate(COUNTS, "#dash")
    check("preset (fixture): selected: r3 in the .base selects r3 when the page opens, and the samples narrow to its rows through the link",
          ok and n.get("samples") == [len(r3), len(samples)], {"select": page.evaluate(select_js("#dash"), "runs"), "counts": n})
    check("preset (fixture): the URL holds it (s.runs=run:r3)", hash_selection(page, "runs") == ["r3"], page.url.split("#", 1)[-1])
    check("preset (fixture): no page error", not page.errors, page.errors[:3])
    page.context.close()
    # a link that clears it: nothing selected, every sample; a reload keeps it cleared
    page, ok = open_fixture(browser, base, FIXURL + "preset.base", ["runs", "samples"], hash_="#s.runs=")
    n = page.evaluate(COUNTS, "#dash")
    sel = page.evaluate(select_js("#dash"), "runs")
    check("preset (fixture): a link with s.runs= (empty) opens with nothing selected, every sample shown: the preset is not applied over it",
          ok and sel is None and n.get("samples") == [len(samples), len(samples)], {"select": sel, "counts": n})
    page.reload()
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    page.evaluate(MOUNT, ["dash", FIXURL + "preset.base"])
    until(page, ready_js("#dash"), ["runs", "samples"])
    settle(page, 3)
    sel = page.evaluate(select_js("#dash"), "runs")
    check("preset (fixture): a reload of that link keeps it cleared (the URL still says s.runs=)", sel is None and hash_selection(page, "runs") == [], {"select": sel, "url": page.url.split("#", 1)[-1]})
    # clearing the preset's selection writes the empty s.runs= (so a reload does not bring the preset back)
    page.evaluate("() => history.replaceState(null, '', location.pathname)")
    page.evaluate(MOUNT, ["dash", FIXURL + "preset.base"])
    until(page, ready_js("#dash"), ["runs", "samples"])
    wait_selected(page, "#dash", "runs", ["r3"])
    page.locator("#dash .dd-chip[data-clear='runs']").click()
    until(page, "() => !document.getElementById('dash').state.select.runs")
    check("preset (fixture): clearing the preset's selection (its chip) writes s.runs= into the URL", hash_selection(page, "runs") == [], page.url.split("#", 1)[-1])
    page.context.close()


def counts_of(rail, dataset, key):
    """{value: count} of a rail group, the values counted 0 left out (a rail may list them, dimmed)."""
    return {x["label"]: x["count"] for x in (rail.get(dataset) or {}).get(key, []) if x["count"]}


def tick(page, root, dataset, key, value):
    page.locator(f"{root} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[data-value='{value}']").check()
    settle(page, 4)


def untick(page, root, dataset, key, value):
    page.locator(f"{root} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[data-value='{value}']").uncheck()
    settle(page, 4)


def tally(xs):
    out = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out


def oneway(browser, base):
    runs, samples = rows(FIX / "runs.json"), rows(FIX / "samples.json")
    targets = {s["run"] for s in samples if s["situation"] == "target"}
    check("one-way fixture: some run has no target row, so a two-way link would narrow the runs on a 'target' pick", {r["run"] for r in runs} - targets, sorted({r["run"] for r in runs} - targets))
    stations_all = tally(r["station"] for r in runs)
    stations_target = tally(r["station"] for r in runs if r["run"] in targets)
    s1 = {r["run"] for r in runs if r["station"] == "S1"}
    shows_s1 = tally(s["situation"] for s in samples if s["run"] in s1)
    for width, dark in ((1280, False), (390, True)):
        tag = f"{width} px, {'dark' if dark else 'light'}"
        page, ok = open_fixture(browser, base, FIXURL + "oneway.base", ["runs", "samples"], width=width, dark=dark)
        page.evaluate("() => { for (const d of document.querySelectorAll('#dash .dd-rail data-facets details')) d.open = true; }")
        settle(page, 2)
        tick(page, "#dash", "samples", "situation", "target")
        r = page.evaluate(RAIL, "#dash")
        n = page.evaluate(COUNTS, "#dash")
        check(f"one-way, {tag}: a pick on the to side (Show = target) leaves the from side's rail counts as runs.json has them {stations_all}, and its table at every run",
              ok and counts_of(r, "runs", "station") == stations_all and n.get("runs") == [len(runs), len(runs)],
              {"Station": counts_of(r, "runs", "station"), "runs panel": n.get("runs")})
        check(f"one-way, {tag}: ... and narrows the to side itself (the samples panel: the target rows)", n.get("samples") == [sum(1 for s in samples if s["situation"] == "target"), len(samples)], n.get("samples"))
        untick(page, "#dash", "samples", "situation", "target")
        tick(page, "#dash", "runs", "station", "S1")
        r = page.evaluate(RAIL, "#dash")
        n = page.evaluate(COUNTS, "#dash")
        check(f"one-way, {tag}: a pick on the from side (Station = S1) narrows the to side: the samples rail counts S1's rows by situation {shows_s1}, the panel S1's samples",
              counts_of(r, "samples", "situation") == shows_s1 and n.get("samples") == [sum(shows_s1.values()), len(samples)],
              {"Show": counts_of(r, "samples", "situation"), "samples panel": n.get("samples")})
        check(f"one-way, {tag}: no page error", not page.errors, page.errors[:3])
        if width == 1280:
            shot(page, "oneway-light-1280", "#dash")
        page.context.close()
    # the same link two-way: the to side's pick narrows the from side, so the fixture tells the two apart
    page, ok = open_fixture(browser, base, FIXURL + "twoway.base", ["runs", "samples"])
    page.evaluate("() => { for (const d of document.querySelectorAll('#dash .dd-rail data-facets details')) d.open = true; }")
    tick(page, "#dash", "samples", "situation", "target")
    r = page.evaluate(RAIL, "#dash")
    n = page.evaluate(COUNTS, "#dash")
    check(f"two-way (the default, unchanged): the same pick narrows the from side too (Station {stations_target}, the runs with a target row)",
          ok and counts_of(r, "runs", "station") == stations_target and n.get("runs") == [len(targets), len(runs)], {"Station": counts_of(r, "runs", "station"), "runs panel": n.get("runs")})
    page.context.close()


def driver_runs(browser, base):
    """The kit gaps' driver fixture: its fault and mode datasets are filtered to one kind each and linked to the runs. Two-way,
    they listed only the runs with both kinds; one-way (P3), the Run picker lists every run."""
    runs = rows(EX / "robotics-driver" / "runs.json")
    page, ok = open_fixture(browser, base, DRIVER_MARKS, ["iq", "vbus"])
    page.evaluate("() => { for (const d of document.querySelectorAll('#dash .dd-rail data-facets details')) d.open = true; }")
    settle(page, 2)
    page.evaluate("() => { for (const b of document.querySelectorAll('#dash .dd-rail [data-more]')) b.click(); }")
    settle(page, 2)
    listed = sorted((page.evaluate(RAIL, "#dash").get("runs") or {}).get("run", []), key=lambda x: x["value"])
    check(f"one-way (the kit gaps' driver fixture): the Run picker lists every run of runs.json ({len(runs)}), not only the runs with a fault and a mode change",
          ok and sorted(x["value"] for x in listed) == sorted(r["run"] for r in runs), {"listed": len(listed), "runs.json": len(runs)})
    check("one-way (driver fixture): no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- the templates' runs tables
def pickers(browser, site):
    for case, clock_file in (("robotics-servo", "samples.json"), ("robotics-driver", "samples.json")):
        runs, samples = rows(EX / case / "runs.json"), rows(EX / case / clock_file)
        want_order = [r["run"] for r in sorted(runs, key=lambda r: r["started"], reverse=True)]
        page = new_page(browser)
        page.goto(f"{site}/gallery/{case}/index.html")
        ok = until(page, ready_js("#example"), ["runs", "playback"])
        settle(page, 3)
        pick = want_order[2]
        click_row(page, "#example", "runs", 2)
        ok = ok and until(page, "(run) => { const s = document.querySelector(\"#example .dd-rail data-facets[data-dataset='runs'] section.df-group[data-key='run'] input[type=radio]:checked\"); return !!s && s.dataset.value === run; }", pick)
        ts = [r["t"] for r in samples if r["run"] == pick]
        ok_span = wait_span(page, "#example", [min(ts), max(ts)])
        check(f"{case}: a click on the runs table's row ({pick}) picks it on the rail: the Run radio checked, the panels follow", ok, json.dumps(page.evaluate("() => document.querySelector('#example').state.rail.runs"), default=str)[:200])
        check(f"{case}: ... the clock spans exactly that run's t in {clock_file} {[min(ts), max(ts)]}", ok_span, page.evaluate(clock_js("#example")))
        check(f"{case}: ... the runs table still lists every run of runs.json ({len(runs)}), newest first", page.evaluate(table_js("#example"), ["runs", "run"]) == want_order,
              (page.evaluate(table_js("#example"), ["runs", "run"]) or [])[:3])
        marks = page.evaluate(MARKS, ["#example", "runs"])
        mine = [bg for i, bg in marks if i == 2]
        others = [bg for i, bg in marks if i != 2]
        check(f"{case}: ... and marks the picked row, no other", mine and mine[0] not in others and len(set(others)) == 1, marks[:4])
        check(f"{case}: no page error", not page.errors, page.errors[:3])
        shot(page, f"{case.removeprefix('robotics-')}-picked-light-1280")
        page.context.close()


# ------------------------------------------------------------------------------------------------- themes and widths
def looks(browser, site):
    base = case_base()
    per_run = panels_reading(base, templated(base))
    first, o = newest(), order()
    for width, dark in ((1280, False), (1280, True), (390, False), (390, True)):
        tag = f"{width} px, {'dark' if dark else 'light'}"
        page, ok = open_case(browser, site, width=width, dark=dark, keys=["deployments", "runs", "playback", *per_run])
        ok = ok and wait_selected(page, "#example", "runs", [first]) and wait_span(page, "#example", span(first))
        check(f"{tag}: the newest run is selected on load, in the URL, its one file fetched, the clock spanning it",
              ok and hash_selection(page, "runs") == [first] and run_files(page) == [f"runs/{enc(first)}.json"], {"files": run_files(page), "clock": page.evaluate(clock_js("#example"))})
        shot(page, f"deployments-{'dark' if dark else 'light'}-{width}")
        n0 = len(page.reqs)
        click_row(page, "#example", "runs", 2)
        ok = wait_selected(page, "#example", "runs", [o[2]]) and wait_span(page, "#example", span(o[2]))
        check(f"{tag}: a click picks {o[2]}: exactly its file fetched, the clock spanning its t", ok and run_files(page, n0) == [f"runs/{enc(o[2])}.json"], run_files(page, n0))
        click_row(page, "#example", "runs", 3, add=True)
        ok = until(page, f"([root, keys]) => keys.every((k) => (document.querySelector(`${{root}} .dd-panel[data-panel='${{k}}']`).innerText || '').includes('Pick one run'))", ["#example", per_run])
        check(f"{tag}: two picks show 'Pick one run' in every per-run panel", ok, {k: (page.evaluate(SHOWN, ["#example", k]) or "")[:60] for k in per_run})
        check(f"{tag}: the page never scrolls sideways, and no page error", no_sideways(page, width) and not page.errors,
              {"scrollWidth": page.evaluate("() => document.scrollingElement.scrollWidth"), "errors": page.errors[:3]})
        shot(page, f"pick-one-{'dark' if dark else 'light'}-{width}")
        page.context.close()


def main() -> int:
    if not (SITE / "index.html").exists() or not (ROOT / "dist" / "dashboard.js").exists():
        print("the kit and site are not built: npm --prefix ~/data-ui run build")
        return 1
    with guard("the case's files"):
        files()
    proc, base = serve(ROOT, PAGE)
    sproc, site = serve(SITE, "/index.html")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for name, fn in (("the case", lambda: case_main(browser, site)), ("Back and Forward", lambda: history(browser, site)),
                             ("Back and Forward, 390 px dark", lambda: history(browser, site, 390, True)),
                             ("presets", lambda: presets(browser, base)), ("one-way links", lambda: oneway(browser, base)),
                             ("the driver fixture", lambda: driver_runs(browser, base)), ("the templates' runs tables", lambda: pickers(browser, site)),
                             ("themes and widths", lambda: looks(browser, site))):
                with guard(name):
                    fn()
            browser.close()
    finally:
        for p in (proc, sproc):
            p.terminate()
            p.wait(timeout=10)
    (OUT / "p3-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} P3 checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
