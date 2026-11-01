"""Property types, the column menu and the table's chrome (docs/CONTRACT.md §28), measured in headless Chromium.

    ~/psu-atlas/.venv/bin/python tests/browser/types_checks.py [OUT_DIR] [--only chrome,types,menu]

Serves the built site (dist/site) on a free 127.0.0.1 port, stops it when done, writes OUT_DIR/types-checks.json
(default reports/media/types) and exits 1 if any check fails. Every claim is a number read from the page
(getComputedStyle, getBoundingClientRect), never the presence of a class.

- chrome: the six findings of the 2026-10-26 header/divider review (reports/media/audits/2026-10-26-table-headers-
  judge-r1.md): dividers on every cell edge including under column groups, distribution titles over their strips,
  numeric headers ending where their numbers end, basis left, the frozen span the same in the header as in the body,
  and a distribution column never narrower than its drawing.
- types: every property type and option renders (the property-types gallery case).
- menu: the column-header menu does each action and writes the expected .base change.
Kept out of tests/browser/checks.py so a lane editing that file never meets this one (tools/test-all.mjs runs both).
"""

from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
SITE = ROOT / "dist" / "site"
ARGS = [a for a in sys.argv[1:] if not a.startswith("--only")]
ONLY = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--only=")), "chrome,types,menu").split(",")
RUN_ALL = not any(a.startswith("--only=") for a in sys.argv[1:])
OUT = pathlib.Path(ARGS[0]) if ARGS else ROOT / "reports" / "media" / "types"
OUT.mkdir(parents=True, exist_ok=True)
checks: list[dict] = []
MODELS = "gallery/robotparts-models/index.html"
TYPES = "gallery/property-types/index.html"


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, ensure_ascii=False)[:600]}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Pages:
    def __init__(self, browser, base):
        self.browser, self.base = browser, base
        self.errors: list[str] = []

    def open(self, path, width=1440, height=1000, dark=False, mobile=False, frame=None, editable=False, attrs=None):
        context = self.browser.new_context(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light",
                                           device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
        if frame or editable or attrs:
            # before the kit starts, so the element starts in its frame (as tests/browser/fixtures/frame.html does)
            more = "".join(f"v.setAttribute({json.dumps(k)}, {json.dumps(v)});" for k, v in (attrs or {}).items())
            context.add_init_script(f"""document.addEventListener('DOMContentLoaded', () => {{ const v = document.querySelector('#example');
              if (v) {{ {f"v.setAttribute('frame', {json.dumps(frame)});" if frame else ''} {"v.setAttribute('editable', '');" if editable else ''} {more} }} }});""")
        page = context.new_page()
        page.on("pageerror", lambda e: self.errors.append(f"{path}: {e}"))
        page.goto(f"{self.base}/{path}")
        page.wait_for_selector("#example[data-view]", timeout=30000)
        page.wait_for_function("() => document.querySelector('#example tbody tr[data-i]')", timeout=30000)
        page.wait_for_timeout(300)
        return page


def tab(page, name):
    page.click(f"#example .dv-tab[data-name='{name}']")
    page.wait_for_function(f"() => document.querySelector('#example').view.name === {json.dumps(name)} && document.querySelector('#example tbody tr[data-i]')")
    page.wait_for_timeout(400)


# ---------------------------------------------------------------------------------------------------------------- chrome
# Every cell's right divider: its computed width and whether its colour is visible (alpha > 0), for every header row
# (groups, leaves, the axis row) and the drawn body rows. A cell edge with no divider is reported by its column key.
DIVIDERS = """() => {
  const v = document.querySelector('#example');
  const vis = (c) => { const m = /rgba?\\(([^)]+)\\)/.exec(c); if (!m) return false; const p = m[1].split(',').map(Number); return p.length < 4 || p[3] > 0; };
  const tableRight = v.querySelector('.dv-table').getBoundingClientRect().right;
  // the table's outer right edge is the frame's line (boxed: its border; bleed: the page edge), not a column divider
  const edge = (cell) => { const cs = getComputedStyle(cell); if (Math.abs(cell.getBoundingClientRect().right - tableRight) < 1) return true; return parseFloat(cs.borderRightWidth) >= 1 && vis(cs.borderRightColor) && cs.borderRightStyle !== 'none'; };
  const missing = [];
  let n = 0;
  for (const tr of v.querySelectorAll('.dv-table thead tr')) for (const th of tr.children) { n++; if (!edge(th)) missing.push(`${tr.className || 'head'}:${th.dataset.col || th.textContent.trim().slice(0, 18) || '(blank)'}`); }
  for (const tr of [...v.querySelectorAll('.dv-table tbody tr.dv-row')].slice(0, 12)) for (const td of tr.children) { n++; if (!edge(td)) missing.push(`body:${td.dataset.col}`); }
  return { cells: n, missing: [...new Set(missing)] }; }"""

# Column boundaries line up through every header row: each leaf's right edge is some cell's right edge in every row
# above it (a merged header's divider sits on a leaf boundary; a leaf boundary inside a merged header is drawn by the
# rows below it, so only the bottom-most row is required to have every boundary).
BOUNDARIES = """() => {
  const v = document.querySelector('#example');
  const leaves = [...v.querySelectorAll('.dv-table thead th[data-col]')];
  const xs = leaves.map((t) => Math.round(t.getBoundingClientRect().right));
  const at = Object.fromEntries(leaves.map((t, i) => [t.dataset.col, xs[i]]));
  const body = [...v.querySelectorAll('.dv-table tbody tr.dv-row')][0];
  const cells = body ? [...body.children] : [];
  const off = [];
  v.querySelectorAll('.dv-table thead tr').forEach((tr, i) => [...tr.children].forEach((th) => { const r = Math.round(th.getBoundingClientRect().right); if (!xs.some((x) => Math.abs(x - r) <= 1)) off.push([i, th.textContent.trim().slice(0, 16), r]); }));
  // each body cell ends where its own column's header ends (matched by column key: with rowspans the header's DOM
  // order is not the column order)
  return { leaves: xs.length, bodyMatches: cells.length === xs.length && cells.every((td) => Math.abs(Math.round(td.getBoundingClientRect().right) - at[td.dataset.col]) <= 1), off }; }"""


def chrome(pages: Pages):
    for frame in (None, "bleed"):
        for dark in (False, True):
            tag = f"{frame or 'boxed'}, {'dark' if dark else 'light'}"
            page = pages.open(MODELS, frame=frame, dark=dark)
            bad = {}
            for name in ["Benches", "Parameters", "Parameters · with CI", "What each rung adds · columns", "Leaderboard"]:
                tab(page, name)
                d = page.evaluate(DIVIDERS)
                b = page.evaluate(BOUNDARIES)
                if d["missing"] or b["off"] or not b["bodyMatches"]:
                    bad[name] = {"no divider": d["missing"][:8], "header edges off a column boundary": b["off"][:6], "body matches header": b["bodyMatches"]}
            check(f"chrome ({tag}): a 1 px visible divider on every cell's right edge, header rows (groups, blanks, leaves, axis) and body alike, every one on a column boundary",
                  not bad, bad or None)
            page.context.close()

    page = pages.open(MODELS)
    # 2. a distribution title sits over its strip: its centre is the mark slot's centre (pivot cells with counts, and a
    #    stats column's `runs`); the unit is a separate muted caption in parentheses, never glued to the name
    tab(page, "Benches")
    piv = page.evaluate("""() => {
      const v = document.querySelector('#example');
      const out = [];
      for (const th of [...v.querySelectorAll('.dv-table thead th[data-col^="@"]')]) {
        const col = th.dataset.col;
        const title = th.querySelector('.dv-th-text') || th.querySelector('.dv-th');
        const m = [...v.querySelectorAll(`.dv-table tbody td[data-col="${CSS.escape(col)}"] .dv-m`)].map((e) => e.getBoundingClientRect()).filter((r) => r.width > 0)[0];
        const unit = th.querySelector('.dv-unit');
        const t = title.getBoundingClientRect();
        out.push({ col, dx: m ? Math.round(((t.left + t.right) / 2 - (m.left + m.right) / 2) * 10) / 10 : null, unit: unit ? unit.textContent.trim() : null,
          unitColor: unit ? getComputedStyle(unit).color : null, labelColor: getComputedStyle(title).color });
      }
      return out; }""")
    tab(page, "What each rung adds · columns")
    runs = page.evaluate("""() => {
      const v = document.querySelector('#example');
      const th = v.querySelector('.dv-table thead th[data-col="delta_mrad:dist"]');
      const title = th.querySelector('.dv-th-text') || th.querySelector('.dv-th');
      const m = [...v.querySelectorAll('.dv-table tbody td[data-col="delta_mrad:dist"] .dv-m')].map((e) => e.getBoundingClientRect()).filter((r) => r.width > 0)[0];
      const t = title.getBoundingClientRect();
      return { dx: Math.round(((t.left + t.right) / 2 - (m.left + m.right) / 2) * 10) / 10 }; }""")
    ok = piv and all(p["dx"] is not None and abs(p["dx"]) <= 1 for p in piv) and abs(runs["dx"]) <= 1 \
        and all(p["unit"] == "(× floor)" for p in piv)
    check("chrome: a distribution's title is centred over its strip (pivot cells, a stats column's runs), and its unit is a muted '(× floor)' caption, not glued to the name",
          ok, {"pivot": piv[:3], "runs": runs})

    # 3. + 4. a numeric header ends where its numbers end (no empty-slot gutter); basis is left, like its values
    def edges_of(name, cols):
        tab(page, name)
        return page.evaluate("""(cols) => {
          const v = document.querySelector('#example');
          const out = {};
          for (const col of cols) {
            const th = v.querySelector(`.dv-table thead th[data-col="${CSS.escape(col)}"]`);
            // the header's text: its name and its unit caption, together (what a reader sees end where the numbers end)
            const lab = th.querySelector('.dv-th-text') || th.querySelector('.dv-th');
            // the label's own text box (a Range over its text), not its block, so an alignment shows
            const range = document.createRange(); range.selectNodeContents(lab); const t = range.getBoundingClientRect();
            const cells = [...v.querySelectorAll(`.dv-table tbody td[data-col="${CSS.escape(col)}"]`)].filter((td) => !td.classList.contains('dv-none'));
            const content = cells.map((td) => { const e = td.querySelector('.dv-v') || td.querySelector('.dv-basis') || td; const r2 = document.createRange(); r2.selectNodeContents(e); return r2.getBoundingClientRect(); }).filter((r) => r.width > 0);
            out[col] = { headLeft: Math.round(t.left), headRight: Math.round(t.right), right: content.length ? Math.round(Math.max(...content.map((r) => r.right))) : null,
              left: content.length ? Math.round(Math.min(...content.map((r) => r.left))) : null, align: getComputedStyle(th).textAlign, n: content.length };
          }
          return out; }""", cols)
    ci = edges_of("Parameters · with CI", ["coulomb:value", "coulomb:low", "coulomb:high", "coulomb:basis"])
    st = edges_of("What each rung adds · columns", ["delta_mrad:median", "delta_mrad:min", "delta_mrad:max", "delta_mrad:n"])
    nums = {**{k: v for k, v in ci.items() if not k.endswith("basis")}, **st}
    gaps = {k: (v["right"] - v["headRight"]) if v["right"] is not None else None for k, v in nums.items()}
    check("chrome: a numeric header's right edge is its numbers' right edge (CI value | low | high; median | min | max | n), within 1 px",
          all(g is not None and abs(g) <= 1 for g in gaps.values()), gaps)
    b = ci["coulomb:basis"]
    check("chrome: 'basis' is left-aligned, header and values alike (their left edges within 1 px)",
          b["align"] in ("left", "start") and b["left"] is not None and abs(b["left"] - b["headLeft"]) <= 1, b)

    # 5. the frozen span: under a horizontal scroll, the header's frozen cells cover exactly the body's frozen column(s)
    page.set_viewport_size({"width": 700, "height": 900})
    for name in ["Parameters · with CI", "Parameters"]:
        tab(page, name)
        page.evaluate("() => { const s = document.querySelector('#example .dv-scroll'); s.scrollLeft = 600; }")
        page.wait_for_timeout(200)
        fr = page.evaluate("""() => {
          const v = document.querySelector('#example');
          const stuck = (e) => getComputedStyle(e).position === 'sticky' && getComputedStyle(e).left !== 'auto';
          const bodyRight = Math.max(...[...v.querySelector('.dv-table tbody tr.dv-row').children].filter(stuck).map((e) => e.getBoundingClientRect().right));
          const head = [...v.querySelectorAll('.dv-table thead th')].filter(stuck).map((e) => [e.textContent.trim().slice(0, 14) || '(blank)', Math.round(e.getBoundingClientRect().right)]);
          return { bodyRight: Math.round(bodyRight), head }; }""")
        check(f"chrome: scrolled sideways ({name}), every frozen header cell ends where the frozen body column ends",
              fr["head"] and all(abs(r - fr["bodyRight"]) <= 1 for _, r in fr["head"]), fr)
    page.set_viewport_size({"width": 1440, "height": 1000})

    # 6. a distribution column is never narrower than its drawing: a saved 60 px width and a 300 px drag inwards both
    #    stop at the content minimum, and no cell clips its strip
    tab(page, "Benches")
    col = page.evaluate("() => document.querySelector('#example .dv-table thead th[data-col^=\"@\"]').dataset.col")
    page.evaluate(f"() => document.querySelector('#example').setView({{ columnSize: {{ [{json.dumps(col)}]: 60 }} }})")
    page.wait_for_timeout(300)
    clip = page.evaluate(f"""(col) => {{ const v = document.querySelector('#example');
      const tds = [...v.querySelectorAll(`.dv-table tbody td[data-col="${{CSS.escape(col)}}"]`)];
      const svg = tds.map((td) => {{ const s = td.querySelector('svg.dv-dist'); if (!s) return null; const a = s.getBoundingClientRect(), b = td.getBoundingClientRect(); return a.left >= b.left - 0.5 && a.right <= b.right + 0.5; }}).filter((x) => x !== null);
      return {{ width: Math.round(v.querySelector(`.dv-table thead th[data-col="${{CSS.escape(col)}}"]`).getBoundingClientRect().width), clipped: svg.filter((x) => !x).length, cells: svg.length }}; }}""", col)
    h = page.locator(f"#example thead th[data-col='{col}'] .dv-resize").bounding_box()
    page.mouse.move(h["x"] + 2, h["y"] + 5)
    page.mouse.down()
    page.mouse.move(h["x"] - 300, h["y"] + 5, steps=6)
    page.mouse.up()
    page.wait_for_timeout(300)
    dragged = page.evaluate(f"(col) => Math.round(document.querySelector(`#example .dv-table thead th[data-col=\"${{CSS.escape(col)}}\"]`).getBoundingClientRect().width)", col)
    check("chrome: a distribution column stops at its content minimum (a saved 60 px width and a 300 px drag inwards), and no strip is clipped",
          clip["width"] >= 120 and clip["clipped"] == 0 and clip["cells"] > 3 and dragged >= 120, {**clip, "after drag": dragged})
    page.context.close()


def main() -> int:
    if not (SITE / "index.html").exists():
        print("dist/site is not built: node build.mjs")
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
            pages = Pages(browser, base)
            if "chrome" in ONLY:
                chrome(pages)
            if "types" in ONLY and (ROOT / "gallery" / "examples" / "property-types").exists():
                import types_cases  # noqa: E402  (tests/browser/types_cases.py: the property-types and menu checks)
                types_cases.types(pages, check, tab)
            if "menu" in ONLY and (ROOT / "gallery" / "examples" / "property-types").exists():
                import types_cases  # noqa: E402
                types_cases.menu(pages, check, tab)
            # judge round 2: --only=r2 (all) or --only=r2:<name> (one), tests/browser/types_r2.py
            r2 = [o for o in ONLY if o == "r2" or o.startswith("r2:")]
            if r2 or RUN_ALL:
                import types_r2  # noqa: E402
                names = list(types_r2.REGISTRY) if ("r2" in r2 or not r2) else [o.split(":", 1)[1] for o in r2]
                for n in names:
                    # WHY caught: one check that throws (a click that times out) must be a FAIL, not the end of the run
                    try:
                        types_r2.REGISTRY[n](pages, check, tab)
                    except Exception as err:  # noqa: BLE001
                        check(f"r2 {n}: ran to the end", False, f"{type(err).__name__}: {str(err).splitlines()[0][:200]}")
            check("no script errors", not pages.errors, pages.errors[:3])
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    (OUT / "types-checks.json").write_text(json.dumps(checks, indent=1, ensure_ascii=False), encoding="utf-8")
    passed = sum(c["ok"] for c in checks)
    print(f"{passed}/{len(checks)} types checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    sys.exit(main())
