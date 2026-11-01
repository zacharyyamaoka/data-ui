"""A derived nominal names its source (docs/CONTRACT.md §36, its amendment "a derived value names its source"), measured
in headless Chromium on the built kit against an oracle over the fixture's own JSON.

    ~/psu-atlas/.venv/bin/python tests/browser/source_derived_checks.py [OUT_DIR]     # after npm run build

RobotParts' case: JMC's pole pairs are decoded from the model code on a selection list (a value derived from another,
cited to the document it was read from), and the Nominal source column showed "—" for such a value. The column now names
the source a derived nominal came from, with a quiet "derived" mark, and keeps "—" only where nothing names one. On
tests/browser/fixtures/source-column/derived.json (a made-up servo; its pole pairs are the JMC-equivalent row):
  - every row's source cell against the oracle: the source's name (a link where its address is a link target, a plain
    label for a private one), or, for a cell naming only an address (sourceUrl, else sourcePage), that address as the
    link's label; the "derived" mark exactly on the derived ones (an entry's own basis, or its declared source's); "—"
    and no mark where nothing names a source
  - the mark follows the value shown: picking the decoder for Rotor inertia (its dropdown) marks it, Back to precedence
    unmarks it; the value never changes but by the pick
  - light and dark at 1280 and 390 px: the mark reads at contrast >= 4.5 (its opacity counted), no sideways page scroll
Serves the repo root on a free 127.0.0.1 port, stops that server when done, writes OUT_DIR/source-derived-checks.json and
screenshots (default reports/media/source-derived) and exits 1 if any check fails.
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
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "source-derived"
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "browser" / "fixtures" / "source-column"
PAGE = "/tests/browser/fixtures/source-column/page.html?src=derived.base"
WAIT = 30000
checks: list[dict] = []

DATA = json.loads((FIX / "derived.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the oracle, from the JSON alone
def filled(v):
    return v is not None and v != "" and v != []


def ladder_order(data):
    rank = {r["id"]: i for i, r in enumerate(data.get("ladder") or [])}
    ids = list(data["sources"].keys())
    return sorted(ids, key=lambda s: (rank.get(data["sources"][s].get("rung"), len(rank)), ids.index(s)))


def entries(cell):
    out = {}
    for e in cell.get("sources") or []:
        if filled(e.get("source")) and e["source"] not in out and filled(e.get("value")):
            out[e["source"]] = e
    return out


def shown(cell, order, ov, rid):
    st = entries(cell)
    o = (ov or {}).get(rid)
    if o in st:
        return o
    for s in list(order) + [s for s in st if s not in order]:
        if s in st:
            return s
    return None


def is_link(u):
    if not isinstance(u, str) or not u.strip() or any(ch.isspace() for ch in u.strip()):
        return False
    s = u.strip()
    head = s.split(":", 1)[0]
    if ":" in s and head and head[0].isalpha() and all(ch.isalnum() or ch in "+.-" for ch in head):
        return head.lower() in ("http", "https") and "//" in s and len(s.split("//", 1)[1].split("/", 1)[0]) > 0
    return any(ch in s for ch in "/.?#")


def named(cell, order, ov, rid):
    """{name, address, derived} the column names for the row, or None ("—")."""
    if isinstance(cell, dict) and isinstance(cell.get("sources"), list) and cell["sources"]:
        s = shown(cell, order, ov, rid)
        if s is None:
            return None
        e, d = entries(cell)[s], DATA["sources"].get(s, {})
        basis = e.get("basis") if filled(e.get("basis")) else d.get("basis")
        return {"name": d.get("name") or s, "address": e.get("sourceUrl") if filled(e.get("sourceUrl")) else d.get("url"), "derived": basis == "derived"}
    if not isinstance(cell, dict):
        return None
    name = str(cell["source"]) if filled(cell.get("source")) else None
    address = cell.get("sourceUrl") if filled(cell.get("sourceUrl")) else cell.get("sourcePage") if filled(cell.get("sourcePage")) else None
    if name is None and address is None:
        return None
    return {"name": name, "address": address, "derived": cell.get("basis") == "derived"}


def label_of(u):
    return u[len("https://"):] if u.startswith("https://") else u[len("http://"):] if u.startswith("http://") else u


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
    page.goto(f"{base}{PAGE}")
    page.wait_for_function("() => window.kitReady && window.v && window.v.querySelector('tbody tr[data-id]')", timeout=WAIT)
    settle(page)


CELLS = """() => Object.fromEntries([...document.querySelectorAll('#col tbody tr[data-id]')].map((tr) => {
  const td = tr.querySelector('td[data-col="nominal@source"]');
  if (!td) return [tr.dataset.id, null];
  const links = [...td.querySelectorAll('a')];
  const label = td.querySelector('.dv-src-label');
  const mark = td.querySelector('.dv-src-derived');
  const val = tr.querySelector('td[data-col="nominal"]');
  return [tr.dataset.id, { text: td.textContent.replace(/\\s+/g, ' ').trim(), links: links.map((a) => ({ text: a.textContent.trim(), href: a.href, target: a.target })),
    label: label ? label.textContent.trim() : null, mark: mark ? mark.textContent.trim() : null, marks: td.querySelectorAll('.dv-src-derived').length,
    nil: !!td.querySelector('.dv-nil'), value: val ? (() => { const c = val.cloneNode(true); for (const x of c.querySelectorAll('.dv-src-dd, .dv-src-pin')) x.remove(); return c.textContent.replace(/\\s+/g, ' ').trim(); })() : null }];
}))"""


def cells_ok(tag, what, page, data_url, order, ov):
    got = page.evaluate(CELLS)
    bad = []
    for r in DATA["rows"]:
        want = named(r["nominal"], order, ov, r["id"])
        g = got.get(r["id"])
        if g is None:
            bad.append({"row": r["id"], "got": None})
            continue
        if want is None:
            ok = g["text"] == "—" and g["nil"] and not g["links"] and g["marks"] == 0
        else:
            title = want["name"] if want["name"] is not None else label_of(want["address"]) if want["address"] and is_link(want["address"]) else want["address"]
            if want["address"] and is_link(want["address"]):
                href = urllib.parse.urljoin(data_url, want["address"])
                ok = len(g["links"]) == 1 and g["links"][0]["text"] == title and g["links"][0]["href"] == href
            else:
                ok = not g["links"] and g["label"] == title
            ok = ok and (g["marks"] == 1 and g["mark"] == "derived" if want["derived"] else g["marks"] == 0)
        if not ok:
            bad.append({"row": r["id"], "want": want, "got": g})
    check(f"{tag}: {what}: each row names the source its value came from (the address where only that is named), \"derived\" exactly on the derived ones, \"—\" only where nothing names one",
          not bad, bad[:3] or None)
    return got


def run_rows(page, base, tag, shots):
    open_page(page, base)
    data_url = page.evaluate("() => window.v.dataUrl")
    order = ladder_order(DATA)
    pre = page.evaluate("() => window.v.precedence && window.v.precedence.order")
    check(f"{tag}: the oracle's default order is the element's ({order})", pre == order, pre)
    got = cells_ok(tag, "the default", page, data_url, order, {})
    pole = got.get("pole_pairs") or {}
    check(f"{tag}: RobotParts' case (Pole pairs, decoded from the model code on the private selection list): \"Zeta selection list (private) derived\", no link",
          pole.get("label") == "Zeta selection list (private)" and pole.get("mark") == "derived" and not pole.get("links"), pole)
    tc = got.get("torque_constant") or {}
    check(f"{tag}: a derived value that names no source keeps \"—\" (no mark)", tc.get("text") == "—" and tc.get("marks") == 0, tc)
    shots.append(f"{tag}-derived.png".replace(" ", "-"))
    page.screenshot(path=str(OUT / shots[-1]), full_page=False)

    # ---- the mark follows the value shown: the decoder picked for Rotor inertia (its dropdown), then back
    before = (got.get("rotor_inertia") or {}).get("value")
    page.locator('#col tbody tr[data-id="rotor_inertia"] button.dv-src-dd').click()
    page.wait_for_selector(".dv-itemmenu [role=menuitemradio][data-source='decoder']", timeout=WAIT)
    page.locator(".dv-itemmenu [role=menuitemradio][data-source='decoder']").click()
    settle(page)
    ov = {"rotor_inertia": "decoder"}
    check(f"{tag}: picked by hand: el.precedence.ov is {ov}", page.evaluate("() => window.v.precedence.ov") == ov, page.evaluate("() => window.v.precedence.ov"))
    got = cells_ok(tag, "the decoder picked for Rotor inertia", page, data_url, order, ov)
    ri = got.get("rotor_inertia") or {}
    check(f"{tag}: Rotor inertia now names the decoder (a link) and is marked derived (its source declares it), its value the decoder's 0.18",
          ri.get("mark") == "derived" and ri.get("links") and ri["links"][0]["text"] == "Model-code decoder" and (ri.get("value") or "").startswith("0.18 ") and before != ri.get("value"), ri)
    page.locator('#col tbody tr[data-id="rotor_inertia"] button.dv-src-dd').click()
    page.wait_for_selector(".dv-itemmenu [data-src-back]", timeout=WAIT)
    page.locator(".dv-itemmenu [data-src-back]").click()
    settle(page)
    got = cells_ok(tag, "back to precedence", page, data_url, order, {})
    check(f"{tag}: back to precedence: the selection list's 0.183 again, no mark", (got.get("rotor_inertia") or {}).get("marks") == 0 and ((got.get("rotor_inertia") or {}).get("value") or "").startswith("0.183"), got.get("rotor_inertia"))


CONTRAST = """(sel) => {
  const parse = (c) => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const over = (top, under) => ({ r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1 });
  const bgOf = (el) => { const layers = []; for (let n = el.parentElement; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let acc = { r: 255, g: 255, b: 255, a: 1 }; if (matchMedia('(prefers-color-scheme: dark)').matches && !layers.some((l) => l.a >= 1)) acc = { r: 0, g: 0, b: 0, a: 1 };
    for (const l of layers.reverse()) acc = over(l, acc); return acc; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const el = document.querySelector(sel); if (!el) return null;
  const own = parse(getComputedStyle(el).backgroundColor);
  let bg = bgOf(el); if (own && own.a > 0) bg = over(own, bg);
  const fc = parse(getComputedStyle(el).color); if (!fc) return { unreadable: getComputedStyle(el).color };
  // WHY the opacity: a quiet mark may be drawn faded; what a reader sees is its colour at that opacity over the cell
  let alpha = fc.a; for (let n = el; n && n !== document.documentElement; n = n.parentElement) alpha *= Number(getComputedStyle(n).opacity);
  const fg = over({ ...fc, a: alpha }, bg);
  const L1 = lum(fg), L2 = lum(bg);
  return { ratio: (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05), alpha };
}"""


def run_theme(page, base, tag, shots):
    open_page(page, base)
    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check(f"{tag}: the page never scrolls sideways", overflow <= 0, overflow)
    for rid in ("pole_pairs", "encoder_lines", "frame_size"):
        c = page.evaluate(CONTRAST, f'#col tbody tr[data-id="{rid}"] td[data-col="nominal@source"] .dv-src-derived')
        check(f"{tag}: {rid}: the \"derived\" mark reads at contrast >= 4.5 (its opacity counted)", c and c.get("ratio", 0) >= 4.5, c)
    shots.append(f"{tag}-derived-theme.png".replace(" ", "-"))
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
                    scenarios.append(("rows", lambda: run_rows(page, base, tag, shots)))
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
    (OUT / "source-derived-checks.json").write_text(json.dumps({"checks": checks, "shots": shots}, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} source-derived checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
