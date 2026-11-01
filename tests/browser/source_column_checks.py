"""The Nominal source column on data whose values have one source each (docs/CONTRACT.md §36, its amendment "the source
column on one-source data"), measured in headless Chromium on the built kit against an oracle over the fixture's own JSON.

    ~/psu-atlas/.venv/bin/python tests/browser/source_column_checks.py [OUT_DIR]     # after npm run build

RobotParts asked for it: its datasheet showed data-ui's Nominal source column only when some value had several sources,
so a part whose every value has one source needed a column of its own. A dataset now declares `sourceColumn: true` (draw
it, beside the first column whose values name a source) or `false` (never in a view that does not name it); undeclared, it
follows a value with several sources only, as before (so no other table, and no golden, changes). What is measured, on
tests/browser/fixtures/source-column/servo.json (a made-up servo, every value from one source or none) and on the
source-precedence part.json:
  - declared true: the column, named "<label> source", right after Nominal (the first column whose values name a source,
    not the Section column before it); each row's source under §22's link rule (an http(s) URL or a relative path is a
    link, a private address a plain label), "—" where nothing names one; no pill, no Sources view, no precedence
  - the values themselves drawn exactly as without the declaration
  - undeclared or false: no column; false on data with several sources hides it too, while the Sources view is still there
  - declared true where no value names a source: the column beside the first column after the title, every row "—"
  - light and dark at 1280 and 390 px: no sideways page scroll; the links and labels readable (contrast >= 4.5)
Serves the repo root on a free 127.0.0.1 port, stops that server when done, writes OUT_DIR/source-column-checks.json and
screenshots (default reports/media/source-column) and exits 1 if any check fails.
"""

from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "source-column"
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "browser" / "fixtures"
PAGE = "/tests/browser/fixtures/source-column/page.html"
WAIT = 30000
checks: list[dict] = []

SERVO = json.loads((FIX / "source-column" / "servo.json").read_text(encoding="utf-8"))
PART = json.loads((FIX / "source-precedence" / "part.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the oracle, from the JSON alone
def filled(v):
    return v is not None and v != ""


def is_link(u):
    """§22's link rule: an http(s) URL with a host, or a relative path, query or fragment; anything else is a label."""
    if not isinstance(u, str) or not u.strip() or any(ch.isspace() for ch in u.strip()):
        return False
    s = u.strip()
    head = s.split(":", 1)[0]
    if ":" in s and head and head[0].isalpha() and all(ch.isalnum() or ch in "+.-" for ch in head):
        return head.lower() in ("http", "https") and "//" in s and len(s.split("//", 1)[1].split("/", 1)[0]) > 0
    return any(ch in s for ch in "/.?#")


def source_of(cell):
    """What the column says for a one-source cell: {name, address, link} or None (it draws "—")."""
    if not isinstance(cell, dict) or not filled(cell.get("source")):
        return None
    address = cell.get("sourceUrl") if filled(cell.get("sourceUrl")) else cell.get("sourcePage") if filled(cell.get("sourcePage")) else None
    return {"name": str(cell["source"]), "address": address, "link": bool(address) and is_link(address)}


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"


def settle(page, n=3):
    for _ in range(n):
        page.evaluate(SETTLE)


def open_page(page, base):
    page.goto(f"{base}{PAGE}")
    page.wait_for_function("() => window.kitReady && window.v && window.v.querySelector('tbody tr[data-id]')", timeout=WAIT)
    page.evaluate("() => localStorage.clear()")
    settle(page)


# a fresh element on data and a view given by script (each variant starts with no state)
MOUNT = """([data, view]) => { const old = document.querySelector('data-views'); if (old) old.remove(); localStorage.clear();
  const v = document.createElement('data-views'); v.id = 'col'; v.setAttribute('toolbar', 'bar'); v.setAttribute('views', 'tabs'); v.setAttribute('no-url', '');
  document.body.append(v); v.base = { views: [view] }; v.data = data; window.v = v; }"""
TABLE = """() => {
  const ths = [...document.querySelectorAll('#col thead tr.dv-hleaf th, #col thead tr:last-child th')].filter((th, i, all) => all.indexOf(th) === i);
  const heads = ths.map((th) => th.dataset.col || th.dataset.sort || null).filter(Boolean);
  const rows = Object.fromEntries([...document.querySelectorAll('#col tbody tr[data-id]')].map((tr) => {
    const td = tr.querySelector('td[data-col$="@source"]');
    const val = tr.querySelector('td[data-col="nominal"]');
    const a = td && td.querySelector('a');
    return [tr.dataset.id, { src: td ? { text: td.textContent.replace(/\\s+/g, ' ').trim(), a: a ? { text: a.textContent.trim(), href: a.href, cls: a.className } : null,
      label: td.querySelector('.dv-src-label') ? td.querySelector('.dv-src-label').textContent.trim() : null, anchors: td.querySelectorAll('a').length,
      dd: !!tr.querySelector('button.dv-src-dd'), pin: !!tr.querySelector('.dv-src-pin'), nil: !!td.querySelector('.dv-nil') } : null,
      value: val ? (() => { const c = val.cloneNode(true); for (const x of c.querySelectorAll('.dv-src-dd, .dv-src-pin')) x.remove(); return c.textContent.replace(/\\s+/g, ' ').trim(); })() : null }];
  }));
  const head = document.querySelector('#col thead th[data-col$="@source"]');
  return { heads, head: head ? head.textContent.trim() : null, rows, prec: window.v.precedence,
    srcHeads: heads.filter((c) => c.startsWith('nominal@') && c !== 'nominal@source').map((c) => c.slice(8)) };
}"""
# is a Sources view offered? The element's own list: a narrow bar folds its tabs (CONTRACT §15)
OFFERED = "() => window.v.presets.some((p) => p.name === 'Sources')"


def table(page):
    return page.evaluate(TABLE)


def mount(page, data, view):
    page.evaluate(MOUNT, [data, view])
    page.wait_for_function("() => window.v && window.v.querySelector('tbody tr[data-id]')", timeout=WAIT)
    settle(page)


def after(heads, col, prev):
    return col in heads and prev in heads and heads.index(col) == heads.index(prev) + 1


def run_declared(page, base, tag, shots):
    open_page(page, base)
    data_url = page.evaluate("() => window.v.dataUrl")
    t = table(page)
    check(f"{tag}: servo (sourceColumn: true, one source per value): a \"Nominal source\" column right after Nominal, not after Section",
          t["head"] == "Nominal source" and after(t["heads"], "nominal@source", "nominal") and not after(t["heads"], "nominal@source", "section"), {"heads": t["heads"], "head": t["head"]})
    bad = []
    for r in SERVO["rows"]:
        got = (t["rows"].get(r["id"]) or {}).get("src")
        want = source_of(r.get("nominal"))
        if got is None:
            bad.append({"row": r["id"], "got": None})
            continue
        if want is None:
            ok = got["text"] == "—" and got["nil"] and got["anchors"] == 0
        elif want["link"]:
            href = urllib.parse.urljoin(data_url, want["address"])
            ok = got["a"] is not None and got["a"]["text"] == want["name"] and got["a"]["href"] == href and got["anchors"] == 1 and got["text"] == want["name"]
        else:
            ok = got["label"] == want["name"] and got["anchors"] == 0 and got["text"] == want["name"]
        if not ok or got["dd"] or got["pin"]:
            bad.append({"row": r["id"], "want": want, "got": got})
    check(f"{tag}: servo: each row names its one source under §22's link rule (a link, a private label, \"—\" where none), no dropdown, no pin", not bad, bad[:3] or None)
    offered = page.evaluate(OFFERED)
    settle(page)
    check(f"{tag}: servo: no values with several sources, so no precedence and no Sources view", t["prec"] is None and not offered, {"prec": t["prec"], "offered": offered})
    shots.append(f"{tag}-servo-declared.png".replace(" ", "-"))
    page.screenshot(path=str(OUT / shots[-1]), full_page=False)
    declared_values = {k: v["value"] for k, v in t["rows"].items()}

    # ---- undeclared and false: no column; the values exactly as with it
    view = {"type": "table", "name": "Datasheet", "order": ["field", "section", "nominal"], "units": "inline"}
    data = {k: v for k, v in SERVO.items() if k != "sourceColumn"}
    data["url"] = data_url
    mount(page, data, view)
    t = table(page)
    check(f"{tag}: servo undeclared: no source column (as before), the columns Field, Section, Nominal", t["head"] is None and "nominal@source" not in t["heads"]
          and [h for h in t["heads"] if not h.startswith("@")] == ["field", "section", "nominal"], t["heads"])
    check(f"{tag}: servo: the values are drawn exactly as with the column (the declaration adds a column, nothing else)",
          {k: v["value"] for k, v in t["rows"].items()} == declared_values, {"undeclared": {k: v["value"] for k, v in t["rows"].items()}, "declared": declared_values})
    mount(page, {**data, "sourceColumn": False}, view)
    t = table(page)
    check(f"{tag}: servo, sourceColumn: false: no source column", t["head"] is None and "nominal@source" not in t["heads"], t["heads"])

    # ---- data with several sources: false hides the column (the Sources view is still there); true changes nothing
    part_url = urllib.parse.urljoin(base + "/", "tests/browser/fixtures/source-precedence/part.json")
    pview = {"type": "table", "name": "Flat", "order": ["field", "nominal"], "units": "inline"}
    mount(page, {**PART, "url": part_url, "sourceColumn": False}, pview)
    t = table(page)
    check(f"{tag}: part (several sources), sourceColumn: false: no Nominal source column, the values still their nominals",
          t["head"] is None and "nominal@source" not in t["heads"] and t["prec"] is not None and (t["rows"].get("peak_torque") or {}).get("value") == "3.1 N·m", {"heads": t["heads"], "peak": (t["rows"].get("peak_torque") or {}).get("value")})
    offered = page.evaluate(OFFERED)
    settle(page)
    check(f"{tag}: part, sourceColumn: false: the Sources view is still offered", offered, offered)
    page.evaluate("() => window.v.selectView('Sources')")
    settle(page)
    t = table(page)
    check(f"{tag}: part, sourceColumn: false: Sources still draws one column per source", t["srcHeads"] == ["bench", "datasheet", "listing", "chat"], t["srcHeads"])
    page.evaluate("() => window.v.selectView('Flat')")
    settle(page)
    check(f"{tag}: part, sourceColumn: false: back on its view, no source column", table(page)["head"] is None, table(page)["heads"])
    mount(page, {**PART, "url": part_url, "sourceColumn": True}, pview)
    t = table(page)
    dds = sorted(k for k, v in t["rows"].items() if v["src"] and v["src"]["dd"])
    check(f"{tag}: part, sourceColumn: true: as before, the column after Nominal and a dropdown on the rows with two or more sources",
          t["head"] == "Nominal source" and after(t["heads"], "nominal@source", "nominal") and dds == ["mass", "max_speed", "peak_torque", "pole_pairs", "rated_current", "rated_torque", "supply_voltage"], {"heads": t["heads"], "dropdowns": dds})

    # ---- declared where no value names a source: beside the first column after the title, every row "—"
    bare = {"id": "bare", "title": "No sources", "titleProperty": "field", "sourceColumn": True,
            "properties": {"field": {"type": "text", "label": "Field"}, "note": {"type": "text", "label": "Note"}, "size": {"type": "number", "label": "Size"}},
            "rows": [{"id": "a", "field": "A", "note": "first", "size": 1}, {"id": "b", "field": "B", "note": "second", "size": 2}]}
    mount(page, bare, {"type": "table", "name": "T", "order": ["field", "note", "size"]})
    t = table(page)
    nils = all(v["src"] and v["src"]["text"] == "—" for v in t["rows"].values())
    check(f"{tag}: declared with no source anywhere: a \"Note source\" column after Note (the first after the title), every row \"—\"",
          t["head"] == "Note source" and after(t["heads"], "note@source", "note") and nils and len(t["rows"]) == 2, {"heads": t["heads"], "head": t["head"], "rows": t["rows"]})


CONTRAST = """(sel) => {
  const parse = (c) => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const over = (top, under) => ({ r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1 });
  const bgOf = (el) => { const layers = []; for (let n = el; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let acc = { r: 255, g: 255, b: 255, a: 1 }; if (matchMedia('(prefers-color-scheme: dark)').matches && !layers.some((l) => l.a >= 1)) acc = { r: 0, g: 0, b: 0, a: 1 };
    for (const l of layers.reverse()) acc = over(l, acc); return acc; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const el = document.querySelector(sel); if (!el) return null;
  const fgc = parse(getComputedStyle(el).color); if (!fgc) return { unreadable: getComputedStyle(el).color };
  const bg = bgOf(el), fg = over(fgc, bg);
  const L1 = lum(fg), L2 = lum(bg);
  return { ratio: (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05) };
}"""


def run_theme(page, base, tag, shots):
    open_page(page, base)
    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check(f"{tag}: servo: the page never scrolls sideways (the table scrolls in its own box)", overflow <= 0, overflow)
    for sel in ('#col tbody tr[data-id="rated_torque"] td[data-col="nominal@source"] a.dv-src-link', '#col tbody tr[data-id="rated_speed"] td[data-col="nominal@source"] .dv-src-label'):
        c = page.evaluate(CONTRAST, sel)
        check(f"{tag}: servo: {sel.split(' ')[-1]} reads at contrast >= 4.5", c and c.get("ratio", 0) >= 4.5, c)
    shots.append(f"{tag}-servo.png".replace(" ", "-"))
    page.screenshot(path=str(OUT / shots[-1]), full_page=False)


def main() -> int:
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    shots: list[str] = []
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + PAGE, timeout=1)
                break
            except Exception:  # noqa: BLE001 - not up yet
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for width, scheme in ((1280, "light"), (390, "dark"), (1280, "dark"), (390, "light")):
                tag = f"{width} px {scheme}"
                ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
                page = ctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                scenarios = [("theme", lambda: run_theme(page, base, tag, shots))]
                if (width, scheme) in ((1280, "light"), (390, "dark")):
                    scenarios.append(("declaration", lambda: run_declared(page, base, tag, shots)))
                for name, run in scenarios:
                    try:
                        run()
                    except Exception as err:  # noqa: BLE001 - a scenario that stops is a FAIL, and the next one runs
                        check(f"{tag}: the {name} checks ran to the end", False, f"{type(err).__name__}: {str(err).splitlines()[0][:300]}")
                check(f"{tag}: no page error", not errors, errors[:3])
                ctx.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "source-column-checks.json").write_text(json.dumps({"checks": checks, "shots": shots}, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} source-column checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
