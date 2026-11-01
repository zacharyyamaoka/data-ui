"""A rich cell's `text` (docs/CONTRACT.md §22), measured in headless Chromium on the built kit.

    ~/psu-atlas/.venv/bin/python tests/browser/cell_text_checks.py [OUT_DIR]     # after npm run build

RobotParts stores a range as a list, {value: [15, 60], text: "15 to 60"}, and redrew those cells after render. Each case is
a <data-views> over tests/browser/fixtures/cell-text/ rows whose cells carry `text`; the rule under test:
  - every place that draws the cell shows `text` exactly as written: the table (a list column, a number column and a
    badge column), list, cards, kanban, record, the peek's field
  - sorting, filtering and Copy keep using `value`; the hover title is the stored value
  - the right-click popover's value line is the text, and its Copy citation writes the value
  - a `text` that is not a string is ignored: the cell draws its value
Serves the repo root on a free 127.0.0.1 port, stops that server when done, writes OUT_DIR/cell-text-checks.json (default
reports/media/cell-text) and exits 1 if any check fails.
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
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "cell-text"
OUT.mkdir(parents=True, exist_ok=True)
PAGE = "/tests/browser/fixtures/cell-text/cell-text.html"
WAIT = 30000
checks: list[dict] = []

SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 80))))"

# the "power" values are 100, 3 and 20; their texts sort the other way round as words ("one hundred" < "three" < "twenty")
ROWS = [
    {"id": "a", "name": "alpha", "power": {"value": 100, "text": "one hundred"}, "range": {"value": [100, 200], "text": "100 to 200", "source": "datasheet p3"}, "kind": "x"},
    {"id": "b", "name": "bravo", "power": {"value": 3, "text": "three"}, "range": {"value": [5, 20], "text": "5 to 20", "source": "datasheet p3"}, "kind": "x"},
    {"id": "c", "name": "charlie", "power": {"value": 20, "text": "twenty"}, "range": {"value": [15, 60], "text": "15 to 60", "source": "datasheet p3"}, "kind": "y"},
]
PROPS = {"name": {"type": "text"}, "power": {"type": "number"}, "range": {"type": "list"}, "kind": {"type": "text"}}
ORDER = ["name", "power", "range", "kind"]
DATA = {"properties": PROPS, "rows": ROWS}

VIEWS = """([data, view, attrs]) => {
  for (const old of document.querySelectorAll('data-dashboard, data-views')) old.remove();
  const v = document.createElement('data-views');
  v.id = 'v'; v.setAttribute('no-url', ''); v.className = 'boxed';
  for (const [k, val] of Object.entries(attrs || {})) v.setAttribute(k, val);
  document.body.append(v);
  v.base = { views: [view] };
  v.data = data;
  window.v = v;
}"""

# the table's cells of one column, in row order, as {text, title} (text with the whitespace collapsed)
COLUMN = """(col) => [...document.querySelectorAll('#v tbody tr[data-i] td[data-col="' + col + '"]')].map((td) => ({ text: td.textContent.replace(/\\s+/g, ' ').trim(), title: td.title }))"""
NAMES = """() => [...document.querySelectorAll('#v tbody tr[data-i] td[data-col="name"]')].map((td) => td.textContent.trim())"""
VIEW_TEXT = "() => document.querySelector('#v').innerText.replace(/\\s+/g, ' ')"


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


def mount(page, view, ready, data=DATA, attrs=None):
    page.evaluate(VIEWS, [data, view, attrs])
    page.wait_for_function("(sel) => { const v = document.getElementById('v'); return v && v.dataset.view && v.querySelector(sel); }", arg=ready, timeout=WAIT)
    settle(page)


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
                ctx = browser.new_context(viewport={"width": width, "height": 900})
                page = ctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base + PAGE)
                page.wait_for_function("() => window.kitReady", timeout=WAIT)

                # ---- the table
                table = {"type": "table", "name": "T", "order": ORDER}
                mount(page, table, "tbody tr[data-i]")
                rng = page.evaluate(COLUMN, "range")
                check(f"{tag}: table: the range cells read \"100 to 200\", \"5 to 20\", \"15 to 60\" (a list column, exactly as written)",
                      [c["text"] for c in rng] == ["100 to 200", "5 to 20", "15 to 60"], rng)
                check(f"{tag}: table: the hover title of a range cell is the stored value (\"15, 60\"), not the text", rng[2]["title"] == "15, 60", rng[2])
                power = page.evaluate(COLUMN, "power")
                check(f"{tag}: table: a number column's rich cell reads its text (\"one hundred\", \"three\", \"twenty\")",
                      [c["text"] for c in power] == ["one hundred", "three", "twenty"], power)
                check(f"{tag}: table: ... and its title is the stored number", [c["title"].split("\n")[0] for c in power] == ["100", "3", "20"], power)
                check(f"{tag}: table: a plain cell is unchanged (the name column)", page.evaluate(NAMES) == ["alpha", "bravo", "charlie"], page.evaluate(NAMES))

                # sorting follows the value: 3, 20, 100 -> b, c, a (the texts as words would give a, c, b ... "one hundred" first)
                mount(page, {**table, "sort": [{"property": "power", "direction": "ASC"}]}, "tbody tr[data-i]")
                check(f"{tag}: sort: by the power column, ascending, orders by value (b, c, a), not by text", page.evaluate(NAMES) == ["bravo", "charlie", "alpha"], page.evaluate(NAMES))
                mount(page, {**table, "sort": [{"property": "power", "direction": "DESC"}]}, "tbody tr[data-i]")
                check(f"{tag}: sort: descending is a, c, b", page.evaluate(NAMES) == ["alpha", "charlie", "bravo"], page.evaluate(NAMES))

                # the header's own sort control
                mount(page, table, "tbody tr[data-i]")
                page.locator("#v thead th", has_text="power").first.click(modifiers=["Shift"])
                settle(page)
                first = page.evaluate(NAMES)
                if first != ["bravo", "charlie", "alpha"]:
                    page.locator("#v thead th", has_text="power").first.click(modifiers=["Shift"])
                    settle(page)
                    second = page.evaluate(NAMES)
                else:
                    second = first
                check(f"{tag}: sort: clicking the power header sorts by value (ascending b, c, a on a click)", second == ["bravo", "charlie", "alpha"] or first == ["bravo", "charlie", "alpha"], [first, second])

                # filters match the value
                mount(page, {**table, "filters": "power >= 20"}, "tbody tr[data-i]")
                check(f"{tag}: filter: power >= 20 keeps a and c", sorted(page.evaluate(NAMES)) == ["alpha", "charlie"], page.evaluate(NAMES))
                mount(page, {**table, "filters": "power == 3"}, "tbody tr[data-i]")
                check(f"{tag}: filter: power == 3 matches the value 3 (the text \"three\" is not what is compared)", page.evaluate(NAMES) == ["bravo"], page.evaluate(NAMES))

                # a badge column draws one chip with the text
                mount(page, {**table, "display": {"range": "badge"}}, "tbody tr[data-i]")
                chips = page.evaluate("() => [...document.querySelectorAll('#v tbody tr[data-i] td[data-col=\"range\"] .dv-badge')].map((b) => b.textContent)")
                check(f"{tag}: chips: a badge column draws one chip per cell with the text", chips == ["100 to 200", "5 to 20", "15 to 60"], chips)

                # ---- the other views
                for kind, ready in (("list", ".dv-list-prop"), ("cards", ".dv-cards-value"), ("kanban", ".dv-kanban-value"), ("record", ".dv-record-sheet, .dv-record")):
                    view = {"type": kind, "name": kind.title(), "order": ORDER}
                    if kind == "kanban":
                        view["groupBy"] = {"property": "kind"}
                    mount(page, view, ready)
                    text = page.evaluate(VIEW_TEXT)
                    check(f"{tag}: {kind}: draws \"15 to 60\" and not the joined list \"15, 60\"" if kind != "record" else f"{tag}: record: draws the selected row's range as text",
                          ("15 to 60" in text and "15, 60" not in text) if kind != "record" else ("100 to 200" in text or "5 to 20" in text or "15 to 60" in text) and "15, 60" not in text and "100, 200" not in text and "5, 20" not in text,
                          text[:300])

                # ---- the peek's field
                mount(page, table, "tbody tr[data-i]")
                page.evaluate("() => window.v.openPeek('c')")
                page.wait_for_function("() => document.querySelector('.dv-peek .dv-peek-field[data-p=range]')", timeout=WAIT)
                settle(page)
                field = page.evaluate("() => { const td = document.querySelector('.dv-peek .dv-peek-field[data-p=range] td'); const v = td.querySelector('.dv-value'); return { text: td.textContent.replace(/\\s+/g, ' ').trim(), title: v ? v.title : null }; }")
                check(f"{tag}: peek: the range field shows \"15 to 60\"; its hover title is the stored value", field["text"] == "15 to 60" and (field["title"] or "").split("\n")[0] == "15, 60", field)
                power_field = page.evaluate("() => document.querySelector('.dv-peek .dv-peek-field[data-p=power] td').textContent.replace(/\\s+/g, ' ').trim()")
                check(f"{tag}: peek: the power field shows \"twenty\"", power_field == "twenty", power_field)
                page.keyboard.press("Escape")

                # ---- the right-click popover and Copy: the label is the text, the citation is the value
                mount(page, table, "tbody tr[data-i]")
                page.locator("#v tbody tr[data-i] td[data-col=range] .dv-value").nth(2).scroll_into_view_if_needed()
                page.locator("#v tbody tr[data-i] td[data-col=range] .dv-value").nth(2).click(button="right")
                page.wait_for_selector(".dv-srcmenu", timeout=WAIT)
                label = page.evaluate("() => (document.querySelector('.dv-srcmenu .dv-srcmenu-value') || {}).textContent")
                check(f"{tag}: right-click: the popover's value line is the text", label == "15 to 60", label)
                page.evaluate("(() => { window.__copied = null; Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (t) => { window.__copied = t; } } }); })()")
                page.get_by_role("button", name="Copy citation").click()
                page.wait_for_function("() => window.__copied !== null", timeout=WAIT)
                copied = page.evaluate("window.__copied")
                check(f"{tag}: Copy citation writes the value (\"15, 60 — datasheet p3\"), never the text", copied.startswith("15, 60") and "15 to 60" not in copied, copied)
                page.keyboard.press("Escape")

                # ---- a text that is not a string is ignored
                bad = [{**r, "range": {**r["range"], "text": 5 if i == 0 else ["5 to 20"] if i == 1 else {"a": 1}}} for i, r in enumerate(ROWS)]
                mount(page, table, "tbody tr[data-i]", data={"properties": PROPS, "rows": bad})
                rng = page.evaluate(COLUMN, "range")
                check(f"{tag}: a non-string text (number, list, object) is ignored: the cell draws its value", [c["text"] for c in rng] == ["100, 200", "5, 20", "15, 60"], rng)

                check(f"{tag}: no page error", not errors, errors[:3])
                ctx.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "cell-text-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} cell-text checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
