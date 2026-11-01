"""A table with no rows says "No rows match this view.", not "No columns to show" (RobotParts' regression from
lane/p0-blockers 2ea9d70, which decided the columns were missing by looking at the rows), measured in headless Chromium
on the built kit.

    ~/psu-atlas/.venv/bin/python tests/browser/empty_table_checks.py [OUT_DIR]     # after npm run build

Each case is a <data-views> table or a <data-dashboard> panel over tests/browser/fixtures/empty-table/ and the p0 page:
  - zero rows, columns declared by `properties:` (the runtime shape) or by a schema: "No rows match this view."
  - rows that a filter leaves zero of: the same
  - a bare [] dataset whose columns the .base file's `properties:` names (robotparts' Offers panel): the same
  - the kept P0 behaviour: rows without the view's columns still say which columns they lack
Serves the repo root on a free 127.0.0.1 port, stops that server when done, writes OUT_DIR/empty-table-checks.json
(default reports/media/empty-table) and exits 1 if any check fails.
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
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "empty-table"
OUT.mkdir(parents=True, exist_ok=True)
PAGE = "/tests/browser/fixtures/p0/p0.html"
BASE_FILE = "/tests/browser/fixtures/empty-table/offers.base"
WAIT = 30000
EMPTY = "No rows match this view."
checks: list[dict] = []

SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"

# the table in the element `sel`: its body text, the header labels and the drawn data rows
READ = """(sel) => {
  const v = document.querySelector(sel); const t = v && v.querySelector('table');
  if (!t) return null;
  return { body: t.tBodies[0].textContent.trim(), heads: [...t.tHead.querySelectorAll('th')].map((th) => th.textContent.trim()).filter(Boolean),
    dataRows: [...t.tBodies[0].rows].filter((r) => r.hasAttribute('data-i')).length, nocols: !!t.querySelector('.dv-nocols'),
    status: ((v.querySelector('.dv-status') || {}).textContent || '').trim() };
}"""

# a <data-views> table over `data` with the view `view`
VIEWS = """([data, view]) => {
  for (const old of document.querySelectorAll('data-dashboard, data-views')) old.remove();
  const v = document.createElement('data-views');
  v.id = 'tbl'; v.setAttribute('no-url', ''); v.className = 'boxed';
  document.body.append(v);
  v.base = { views: [view] };
  v.data = data;
}"""

DASH = """(src) => {
  for (const old of document.querySelectorAll('data-dashboard, data-views')) old.remove();
  const d = document.createElement('data-dashboard');
  d.id = 'dash'; d.setAttribute('src', src);
  document.body.append(d);
}"""

ROWS = [{"id": f"r{i}", "seller": f"s{i}", "variant": "v", "price": i} for i in range(1, 6)]
PROPS = {"seller": {"type": "text"}, "variant": {"type": "text"}, "price": {"type": "number"}}
FIELDS = [{"name": "seller", "type": "string"}, {"name": "variant", "type": "string"}, {"name": "price", "type": "number"}]
ORDER = ["seller", "variant", "price"]


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def settle(page, n=3):
    for _ in range(n):
        page.evaluate(SETTLE)


def views_case(page, name, data, view, *, want_rows):
    page.evaluate(VIEWS, [data, view])
    page.wait_for_function("() => { const v = document.getElementById('tbl'); return v && v.dataset.view && v.querySelector('table'); }", timeout=WAIT)
    settle(page)
    m = page.evaluate(READ, "#tbl")
    if want_rows:
        check(f"{name}: draws its rows (control)", m["dataRows"] == want_rows and not m["nocols"], m)
        return
    check(f"{name}: says \"{EMPTY}\", not \"No columns to show\"", m["body"] == EMPTY and not m["nocols"] and m["dataRows"] == 0, m)


def main() -> int:
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + PAGE, timeout=1)
                break
            except Exception:  # noqa: BLE001 - not up yet
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for width in (1280, 390):
                tag = f"{width} px"
                page = browser.new_context(viewport={"width": width, "height": 900}).new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base + PAGE)
                page.wait_for_function("() => window.kitReady", timeout=WAIT)

                table = {"type": "table", "name": "T", "order": ORDER}
                # zero rows, columns declared
                views_case(page, f"{tag}: zero rows, columns declared by properties", {"properties": PROPS, "rows": []}, table, want_rows=0)
                views_case(page, f"{tag}: zero rows, columns declared by a schema", {"schema": {"fields": FIELDS}, "rows": []}, table, want_rows=0)
                views_case(page, f"{tag}: zero rows, a bare []", [], table, want_rows=0)
                # a filter that leaves zero rows (and its control: the same data, no filter, draws its rows)
                views_case(page, f"{tag}: properties + rows, no filter", {"properties": PROPS, "rows": ROWS}, table, want_rows=5)
                views_case(page, f"{tag}: properties + rows, a filter leaves zero", {"properties": PROPS, "rows": ROWS}, {**table, "filters": "price > 100"}, want_rows=0)
                views_case(page, f"{tag}: schema + rows, a filter leaves zero", {"schema": {"fields": FIELDS}, "rows": ROWS}, {**table, "filters": "price > 100"}, want_rows=0)
                views_case(page, f"{tag}: rows with no schema, a filter leaves zero", ROWS, {**table, "filters": "price > 100"}, want_rows=0)
                m = page.evaluate(READ, "#tbl")
                check(f"{tag}: after a filter leaves zero rows the status counts them (0 of 5) and the header keeps the columns", "0 of 5" in m["status"] and m["heads"][:3] == ["seller", "variant", "price"], m)

                # the kept P0 behaviour: rows without the view's columns say which columns they lack
                page.evaluate(VIEWS, [{"properties": PROPS, "rows": ROWS}, {"type": "table", "name": "T", "order": ["servo", "ff_fraction"]}])
                page.wait_for_function("() => { const v = document.getElementById('tbl'); return v && v.dataset.view && v.querySelector('table'); }", timeout=WAIT)
                settle(page)
                m = page.evaluate(READ, "#tbl")
                check(f"{tag}: rows without the view's columns still say which columns it lacks (P0)", m["nocols"] and "servo" in m["body"] and "ff_fraction" in m["body"] and m["dataRows"] == 0, m)
                page.evaluate(VIEWS, [{"properties": PROPS, "rows": []}, {"type": "table", "name": "T", "order": ["servo"]}])
                page.wait_for_function("() => { const v = document.getElementById('tbl'); return v && v.dataset.view && v.querySelector('table'); }", timeout=WAIT)
                settle(page)
                m = page.evaluate(READ, "#tbl")
                check(f"{tag}: a declared dataset with zero rows, none of the view's columns declared, says which columns it lacks", m["nocols"] and "servo" in m["body"], m)

                # robotparts' shape: a dashboard panel over a bare [] whose columns the .base file's properties: names
                page.evaluate(DASH, BASE_FILE)
                page.wait_for_function("() => { const d = document.getElementById('dash'); return d && d.querySelectorAll('.dd-panel data-views[data-view] table').length >= 2; }", timeout=WAIT)
                settle(page)
                offers = page.evaluate(READ, "#dash .dd-panel[data-panel='offers'] data-views")
                check(f"{tag}: a dashboard's Offers panel (a bare [] dataset) says \"{EMPTY}\", not \"No columns to show\"", offers and offers["body"] == EMPTY and not offers["nocols"], offers)
                stocked = page.evaluate(READ, "#dash .dd-panel[data-panel='stocked'] data-views")
                check(f"{tag}: a dashboard's Stocked panel (rows, a filter leaves zero) says \"{EMPTY}\"", stocked and stocked["body"] == EMPTY and not stocked["nocols"], stocked)
                check(f"{tag}: no page error", not errors, errors[:3])
                page.context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "empty-table-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} empty-table checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
