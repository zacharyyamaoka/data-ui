"""A property's declared `digits` and `compact` (docs/CONTRACT.md §17 "Declared rounding") reach every cell that writes
the property, measured in headless Chromium on the built kit.

    ~/psu-atlas/.venv/bin/python tests/browser/digits_checks.py [OUT_DIR]     # after npm run build

sim2real's report: `data: checks.json` ({"rows": [{"run": "a", "value": 2.6799053096539507}]}) with
`properties: {value: {digits: 3}}` and a table view drew 2.6799053096539507 in the cell (decimals: 3 drew 2.680).
The fixture below is that file and that .base, widened with a 12,345.678 (an integer part is never cut), a 0.0012345,
and two compact columns. The base and data are answered by page.route; nothing else is synthetic.

Each claim is read from the drawn DOM: the table's cell, its summary row and group header, the side peek's field, the
table the peek embeds (record.sections), the peek's "records behind" table, and the list, cards and board cells. The
stored value must stay one hover away (the cell's title). Serves the repo root on a free 127.0.0.1 port, stops it when
done, writes OUT_DIR/digits-checks.json (default reports/media/digits) and exits 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "digits"
OUT.mkdir(parents=True, exist_ok=True)
checks: list[dict] = []
WAIT = 30000

ROWS = [
    {"run": "a", "kind": "x", "value": 2.6799053096539507, "big": 26513.4, "size": 563210.5},
    {"run": "b", "kind": "x", "value": 12345.678, "big": 1234567, "size": 999.123456},
    {"run": "c", "kind": "y", "value": 0.0012345, "big": 4321.987, "size": 1500},
]
DATA = json.dumps({"rows": ROWS})
# what each stored number must read when `value: {digits: 3}`, `big: {digits: 3, compact: true}`, `size: {compact: true}`
WANT = {
    "a": {"value": "2.68", "big": "26.5K", "size": "563K"},
    "b": {"value": "12,346", "big": "1.23M", "size": "999.123456"},
    "c": {"value": "0.00123", "big": "4.32K", "size": "1.5K"},
}

SECTIONS = """    record:
      sections:
        - { name: Numbers, properties: [value, big, size] }
        - { name: Embedded, view: { type: table, name: Emb, order: [run, value, big, size], filters: 'run == this.run' } }
"""
BASE = f"""data: checks.json
properties:
  value: {{ digits: 3 }}
  big: {{ digits: 3, compact: true }}
  size: {{ compact: true }}
views:
  - type: table
    name: T
    order: [run, value, big, size]
{SECTIONS}  - type: table
    name: Grouped
    order: [run, value, big, size]
    groupBy: {{ property: kind }}
    summaries: {{ value: Average, big: Max, size: Sum }}
  - type: table
    name: ByValue
    order: [run, value]
    groupBy: {{ property: value }}
  - type: list
    name: L
    order: [run, value, big, size]
  - type: cards
    name: C
    order: [run, value, big, size]
  - type: kanban
    name: B
    groupBy: {{ property: kind }}
    order: [run, value, big, size]
"""

MOUNT = """async (name) => {
  document.body.innerHTML = '';
  const v = document.createElement('data-views');
  v.setAttribute('no-url', ''); v.setAttribute('src', '/__digits/views.base'); v.setAttribute('view', name);
  document.body.append(v); window.v = v;
}"""
# the table's cells of one row, by column: {col: {text, title}}; the row is the one whose run cell reads `run`
TABLE_ROW = """([root, run]) => {
  const host = root === 'peek' ? document.querySelector('.dv-peek .dv-peek-view data-views') : window.v;
  if (!host) return null;
  const tr = [...host.querySelectorAll('tbody tr[data-i]')].find((r) => (r.querySelector('td[data-col="run"]') || {}).textContent.trim() === run);
  if (!tr) return null;
  return Object.fromEntries([...tr.querySelectorAll('td[data-col]')].map((td) => [td.dataset.col, { text: td.textContent.replace(/\\s+/g, ' ').trim(), title: td.title }]));
}"""


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


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


def mount(page, view, ready):
    page.evaluate(MOUNT, view)
    page.wait_for_function(f"() => window.v.querySelector({json.dumps(ready)})", timeout=WAIT)
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))")


def cells_match(label, got, run):
    """The row's value / big / size cells read WANT[run] and each keeps its stored number in the hover title."""
    ok = bool(got) and all(got.get(c, {}).get("text") == w for c, w in WANT[run].items())
    check(f"{label}: run {run} reads {WANT[run]}", ok, {c: (got or {}).get(c, {}).get("text") for c in WANT[run]})


def main() -> int:
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/tests/browser/fixtures/lifecycle.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route("**/__digits/views.base", lambda r: r.fulfill(status=200, content_type="text/plain", body=BASE))
            page.route("**/__digits/checks.json", lambda r: r.fulfill(status=200, content_type="application/json", body=DATA))
            page.goto(base + "/tests/browser/fixtures/lifecycle.html")
            page.wait_for_function("() => window.kitReady", timeout=WAIT)

            with guard("table cell"):
                mount(page, "T", "tbody tr[data-i]")
                for run in WANT:
                    cells_match("table cell", page.evaluate(TABLE_ROW, ["view", run]), run)
                a = page.evaluate(TABLE_ROW, ["view", "a"]) or {}
                check("table cell: the stored value stays one hover away (title)", "2.6799053096539507" in a.get("value", {}).get("title", ""), a.get("value", {}).get("title"))

            with guard("side peek"):
                page.evaluate("() => window.v.openPeek('0')")
                page.wait_for_function("() => document.querySelector('.dv-peek .dv-peek-view data-views tbody tr[data-i]')", timeout=WAIT)
                page.evaluate("() => new Promise((r) => setTimeout(r, 80))")
                field = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('.dv-peek .dv-peek-field')].map((tr) => [tr.dataset.p, tr.querySelector('td').textContent.replace(/\\s+/g, ' ').trim()]))")
                check("peek field: value, big and size read the declared digits", {c: field.get(c) for c in WANT["a"]} == WANT["a"], field)
                cells_match("peek's embedded table", page.evaluate(TABLE_ROW, ["peek", "a"]), "a")

            with guard("peek records-behind table"):
                page.evaluate("""() => window.v.openPeek('0', { column: 'value', title: 'Run a', records: [
                    { run: 'a', value: 2.6799053096539507, big: 26513.4, size: 563210.5 }, { run: 'b', value: 12345.678, big: 1234567, size: 999.123456 }] })""")
                page.wait_for_function("() => document.querySelector('.dv-peek .dv-peektable tbody tr')", timeout=WAIT)
                rows = page.evaluate("() => [...document.querySelectorAll('.dv-peek .dv-peektable tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent.trim()))")
                check("peek records table: a row reads run, value, big, size with the declared digits",
                      rows == [["a", "2.68", "26.5K", "563K"], ["b", "12,346", "1.23M", "999.123456"]], rows)

            with guard("table summary row and group header"):
                mount(page, "Grouped", "tbody tr.dv-group")
                got = page.evaluate("""() => [...window.v.querySelectorAll('tbody tr.dv-group')].map((tr) => [...tr.querySelectorAll('td.dv-summary')].map((td) => td.textContent.replace(/\\s+/g, ' ').trim()))""")
                # kind x: Average of 2.6799… and 12345.678 = 6174.1789…; Max big = 1234567; Sum size = 564209.629456 (sums are computed, so rounded to the declared digits)
                x = got[0] if got else []
                check("summary row: Average / Max / Sum of a digits column read the declared digits",
                      len(x) == 3 and x[0].endswith("6,174") and x[1].endswith("1.23M") and x[2].endswith("564K"), got)
                mount(page, "ByValue", "tbody tr.dv-group")
                heads = page.evaluate("() => [...window.v.querySelectorAll('tbody tr.dv-group .dv-gname')].map((e) => e.textContent.trim())")
                check("group header over a digits column reads the declared digits", sorted(heads) == sorted(["0.00123", "2.68", "12,346"]), heads)

            with guard("list, cards and board"):
                mount(page, "L", ".dv-list-prop")
                lst = page.evaluate("() => window.v.querySelector('.dv-view').textContent.replace(/\\s+/g, ' ')")
                check("list: the first row's numbers read the declared digits", all(s in lst for s in ("2.68", "26.5K", "563K")) and "2.6799" not in lst, lst[:200])
                mount(page, "C", ".dv-cards-prop")
                crd = page.evaluate("() => window.v.querySelector('.dv-view').textContent.replace(/\\s+/g, ' ')")
                check("cards: the first row's numbers read the declared digits", all(s in crd for s in ("2.68", "26.5K", "563K")) and "2.6799" not in crd, crd[:200])
                mount(page, "B", ".dv-kanban-prop")
                brd = page.evaluate("() => window.v.querySelector('.dv-view').textContent.replace(/\\s+/g, ' ')")
                check("board: the first card's numbers read the declared digits", all(s in brd for s in ("2.68", "26.5K", "563K")) and "2.6799" not in brd, brd[:200])

            check("no script errors", not errors, errors[:2])
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "digits-checks.json").write_text(json.dumps(checks, indent=1, default=str) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} digits checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
