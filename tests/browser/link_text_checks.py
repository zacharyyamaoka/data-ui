"""`display: link` and source links (docs/CONTRACT.md §22), measured in headless Chromium on the built kit.

    ~/psu-atlas/.venv/bin/python tests/browser/link_text_checks.py [OUT_DIR]     # after npm run build

The rule under test: a value becomes an <a> only when it is something a browser can open (an http(s) URL, or a relative
path, query or fragment), and its label is the cell's `text` when the producer wrote one; anything else (`account:…`, a
bare id, `javascript:`) is drawn as its label, plain text, no <a>. Each case is a <data-views> over
tests/browser/fixtures/link-text/ rows: the table, list, cards, record, compare and the side peek; then the right-click
popover on data-provenance elements whose source page and URL are private (a scheme, a bare id) or public.
Serves the repo root on a free 127.0.0.1 port, stops that server when done, writes OUT_DIR/link-text-checks.json (default
reports/media/link-text) and exits 1 if any check fails.
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
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "link-text"
OUT.mkdir(parents=True, exist_ok=True)
PAGE = "/tests/browser/fixtures/link-text/link-text.html"
WAIT = 30000
checks: list[dict] = []

SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 80))))"

ROWS = [
    {"id": "a", "name": "alpha", "link": {"value": "https://example.com/a", "text": "Example page"}},
    {"id": "b", "name": "bravo", "link": "https://example.com/b"},
    {"id": "c", "name": "charlie", "link": {"value": "account:supplier-chat/2026-10-08", "text": "Supplier chat"}},
    {"id": "d", "name": "delta", "link": "acct-1234"},
    {"id": "e", "name": "echo", "link": "javascript:alert(1)"},
    {"id": "f", "name": "foxtrot", "link": "docs/sheet.pdf"},
]
PROPS = {"name": {"type": "text"}, "link": {"type": "text", "display": "link"}}
DATA = {"properties": PROPS, "rows": ROWS}
# (label, href as written): what each link-target row draws
LINKS = [("Example page", "https://example.com/a"), ("example.com/b", "https://example.com/b"), ("docs/sheet.pdf", "docs/sheet.pdf")]
# what each other row draws, as plain text
PLAIN = ["Supplier chat", "acct-1234", "javascript:alert(1)"]
LABELS = [label for label, _ in LINKS] + PLAIN

VIEWS = """([data, view]) => {
  for (const old of document.querySelectorAll('data-views, .prov')) old.remove();
  const v = document.createElement('data-views');
  v.id = 'v'; v.setAttribute('no-url', ''); v.className = 'boxed';
  document.body.append(v);
  v.base = { views: [view] };
  v.data = data;
  window.v = v;
}"""

# every <a> under `root` whose text is one of the labels: [{label, href (as written), abs}]
ANCHORS = """([sel, labels]) => [...document.querySelectorAll(sel + ' a')].map((a) => ({ label: a.textContent.trim(), href: a.getAttribute('href'), abs: a.href }))
  .filter((a) => labels.includes(a.label) || /^(account:|javascript:|acct-)/.test(a.href || ''))"""
TEXT = "(sel) => (document.querySelector(sel) || {}).innerText || ''"


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


def mount(page, view, ready):
    page.evaluate(VIEWS, [DATA, view])
    page.wait_for_function("(sel) => { const v = document.getElementById('v'); return v && v.dataset.view && v.querySelector(sel); }", arg=ready, timeout=WAIT)
    settle(page)


def judge(tag, where, got, text, links=LINKS, plain=PLAIN, absolute=False):
    """The anchors and the text of one surface against the rule."""
    have = {(a["label"], a["abs"] if absolute else a["href"]) for a in got}
    for label, href in links:
        want = href
        ok = any(lab == label and ((h.endswith("/" + want) or h == want) if absolute else h == want) for lab, h in have)
        check(f"{tag}: {where}: \"{label}\" is an <a> to {href}", ok, sorted(have))
    bad = [a for a in got if a["label"] in plain or (a["href"] or "").startswith(("account:", "javascript:", "acct-"))]
    check(f"{tag}: {where}: no <a> for a private or non-URL value (account:, a bare id, javascript:)", not bad, bad)
    missing = [p for p in plain if p not in text]
    check(f"{tag}: {where}: the plain labels read as written ({', '.join(plain)})", not missing, {"missing": missing, "text": text[:240]})


PROV = """(list) => {
  for (const old of document.querySelectorAll('data-views, .prov')) old.remove();
  for (const [id, p] of list) {
    const s = document.createElement('span');
    s.className = 'prov'; s.id = id; s.textContent = id + ' 3.8'; s.style.cssText = 'display:inline-block;margin:12px;padding:6px;border:1px solid';
    s.setAttribute('data-provenance', JSON.stringify(p));
    document.body.append(s);
  }
}"""
POP = """() => { const m = document.querySelector('.dv-srcmenu'); if (!m) return null;
  const rows = {}; const dl = m.querySelector('.dv-srcmenu-rows');
  if (dl) { const kids = [...dl.children]; for (let i = 0; i < kids.length; i += 2) rows[kids[i].textContent] = { text: kids[i + 1].textContent, a: kids[i + 1].querySelector('a') ? kids[i + 1].querySelector('a').getAttribute('href') : null }; }
  return { rows, acts: [...m.querySelectorAll('.dv-srcmenu-act')].map((a) => a.textContent) }; }"""


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

                # ---- the table, list and cards: every row at once
                for kind, ready in (("table", "tbody tr[data-i]"), ("list", ".dv-list-prop"), ("cards", ".dv-cards-value")):
                    mount(page, {"type": kind, "name": kind.title(), "order": ["name", "link"]}, ready)
                    judge(tag, kind, page.evaluate(ANCHORS, ["#v .dv-view", LABELS]), page.evaluate(TEXT, "#v .dv-view"))

                # ---- compare: the six rows as columns
                mount(page, {"type": "compare", "name": "Compare", "order": ["name", "link"], "compare": {"rows": [r["id"] for r in ROWS]}}, ".dv-cmp tbody td")
                judge(tag, "compare", page.evaluate(ANCHORS, ["#v .dv-view", LABELS]), page.evaluate(TEXT, "#v .dv-view"))

                # ---- record: one row at a time, a link row and a private row
                mount(page, {"type": "record", "name": "Record", "order": ["name", "link"]}, ".dv-record-sheet, .dv-record")
                for rid, links, plain in (("a", [LINKS[0]], []), ("c", [], ["Supplier chat"]), ("d", [], ["acct-1234"]), ("f", [LINKS[2]], [])):
                    # the list of records beside the sheet (wide), or its select (a phone)
                    item = page.locator(f"#v .dv-record-item[data-id='{rid}']")
                    if item.count() and item.is_visible():
                        item.click()
                    else:
                        page.locator("#v .dv-record-pick select").select_option(rid)
                    settle(page)
                    judge(tag, f"record {rid}", page.evaluate(ANCHORS, ["#v .dv-record-sheet", LABELS]), page.evaluate(TEXT, "#v .dv-record-sheet"), links=links, plain=plain)

                # ---- the side peek: the field shows as the view displays it (display: link)
                mount(page, {"type": "table", "name": "T", "order": ["name", "link"], "display": {"link": "link"}}, "tbody tr[data-i]")
                for rid, links, plain in (("a", [LINKS[0]], []), ("c", [], ["Supplier chat"]), ("e", [], ["javascript:alert(1)"]), ("f", [LINKS[2]], [])):
                    page.evaluate(f"() => window.v.openPeek('{rid}')")
                    page.wait_for_function("() => document.querySelector('.dv-peek:not([hidden]) .dv-peek-field[data-p=link]')", timeout=WAIT)
                    settle(page)
                    judge(tag, f"peek {rid}", page.evaluate(ANCHORS, [".dv-peek .dv-peek-field[data-p=link]", LABELS]),
                          page.evaluate(TEXT, ".dv-peek .dv-peek-field[data-p=link]"), links=links, plain=plain, absolute=True)
                    page.evaluate("() => window.v.closePeek()")

                # ---- the right-click popover: a private source page or URL is a plain label; a public one is a link
                page.evaluate(PROV, [
                    ["p-scheme", {"value": "3.8", "source": "Supplier chat", "sourcePage": "account:supplier-chat/7", "sourceUrl": "account:supplier-chat/7"}],
                    ["p-bare", {"value": "3.8", "source": "Bench notes", "sourcePage": "chat-7"}],
                    ["p-public", {"value": "3.8", "source": "Maker", "sourcePage": "https://example.com/maker", "sourceUrl": "https://example.com/sheet.pdf"}],
                    ["p-relative", {"value": "3.8", "source": "Gallery", "sourcePage": "../gallery/index.html"}],
                ])
                pops = {}
                for pid in ("p-scheme", "p-bare", "p-public", "p-relative"):
                    page.locator(f"#{pid}").click(button="right")
                    page.wait_for_selector(".dv-srcmenu", timeout=WAIT)
                    pops[pid] = page.evaluate(POP)
                    page.keyboard.press("Escape")
                    settle(page, 1)
                s = pops["p-scheme"]
                check(f"{tag}: popover: a source page with another scheme (account:) is a plain label, no <a>",
                      s and s["rows"].get("Source", {}).get("text") == "Supplier chat" and s["rows"]["Source"]["a"] is None, s)
                check(f"{tag}: popover: ... its URL row is plain text, and there is no Open URL ↗ or Source page action",
                      s and s["rows"].get("URL", {}).get("a") is None and s["acts"] == ["Copy citation"], s)
                b = pops["p-bare"]
                check(f"{tag}: popover: a bare id as the source page is a plain label, no <a> (it is not resolved against the page)",
                      b and b["rows"].get("Source", {}).get("a") is None and "Source page" not in b["acts"], b)
                p = pops["p-public"]
                check(f"{tag}: popover: an https source page and URL are links, with Open URL ↗ and Source page",
                      p and p["rows"].get("Source", {}).get("a") == "https://example.com/maker" and p["acts"] == ["Open URL ↗", "Source page", "Copy citation"], p)
                r = pops["p-relative"]
                check(f"{tag}: popover: a relative source page stays a link, as before", r and (r["rows"].get("Source", {}).get("a") or "").endswith("/gallery/index.html"), r)

                check(f"{tag}: no page error", not errors, errors[:3])
                ctx.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "link-text-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} link-text checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
