"""The other places a property's declared `digits` / `compact` (docs/CONTRACT.md §17 "Declared rounding") must reach,
beside the cells digits_checks.py draws: a table's rich cell (value, range, basis) and its stats columns, the rail's range
text, a KPI card's range and provenance, a histogram's hover card and a dashboard's selection chip.

    ~/psu-atlas/.venv/bin/python tests/browser/digits_sweep_checks.py [OUT_DIR]     # after npm run build

Every number is the stored one a reader would otherwise get whole (2.6799053096539507); each claim is read from the drawn
DOM, and the stored value must stay one hover away where the cell keeps it. Serves the repo root and dist/site on free
127.0.0.1 ports, stops both when done, writes OUT_DIR/digits-sweep-checks.json (default reports/media/digits) and exits 1
if any check fails.
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
STORED = 2.6799053096539507


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(directory):
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(directory)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    return proc, f"http://127.0.0.1:{port}"


FRAMES = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 80))))"

# a view mounted over an in-page base and dataset, as the oracle's synthetic table is
MOUNT = """([base, data, attrs]) => {
  document.body.innerHTML = '';
  const v = document.createElement('data-views');
  v.id = 'v'; v.setAttribute('no-url', '');
  for (const [k, val] of Object.entries(attrs || {})) v.setAttribute(k, val);
  document.body.append(v); window.v = v;
  v.base = base; v.data = data;
}"""


def main() -> int:
    root_proc, root = serve(ROOT)
    site_proc, site = serve(ROOT / "dist" / "site")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(root + "/tests/browser/fixtures/lifecycle.html")
            page.wait_for_function("() => window.kitReady", timeout=WAIT)

            with guard("table rich cell and stats"):
                cell = {"value": STORED, "low": 2.1234567, "high": 3.7654321, "basis": "measured", "values": [2.1234567, STORED, 3.7654321]}
                page.evaluate(MOUNT, [
                    {"properties": {"m": {"digits": 3}}, "views": [
                        {"type": "table", "name": "Range", "order": ["run", "m"], "display": {"m": "range"}},
                        {"type": "table", "name": "Stats", "order": ["run", "m"], "display": {"m": "stats"}}]},
                    {"properties": {"run": {"type": "text"}, "m": {"type": "number"}}, "rows": [{"run": "a", "m": cell}]}, {"view": "Range"}])
                page.wait_for_function("() => window.v.querySelector('tbody tr[data-i]')", timeout=WAIT)
                page.evaluate(FRAMES)
                got = page.evaluate("() => { const td = window.v.querySelector('tbody td[data-col=\"m\"]'); return { text: td.textContent.replace(/\\s+/g, ' ').trim(), title: td.title }; }")
                check("table rich cell: value and its range read the declared digits", got["text"].startswith("2.68") and "2.12" in got["text"] and "3.77" in got["text"] and "2.6799" not in got["text"] and "2.1234" not in got["text"], got)
                check("table rich cell: the hover title's first line is the text the cell shows", got["title"].split("\n")[0] == "2.68", got["title"])
                page.evaluate(MOUNT, [{"properties": {"m": {"digits": 3}}, "views": [{"type": "table", "name": "Stats", "order": ["run", "m"], "display": {"m": "stats"}}]},
                                      {"properties": {"run": {"type": "text"}, "m": {"type": "number"}}, "rows": [{"run": "a", "m": cell}]}, {}])
                page.wait_for_function("() => window.v.querySelector('td.dv-part')", timeout=WAIT)
                page.evaluate(FRAMES)
                parts = page.evaluate("() => Object.fromEntries([...window.v.querySelectorAll('tbody td.dv-part')].map((td) => [td.dataset.col, td.textContent.replace(/\\s+/g, ' ').trim()]))")
                texts = " | ".join(str(x) for x in parts.values())
                check("table stats columns: median, min and max read the declared digits", "2.68" in texts and "2.12" in texts and "3.77" in texts and "2.6799" not in texts and "2.1234" not in texts, parts)

            with guard("rail range text"):
                rows = [{"run": f"r{i}", "value": 0.0123456789 * (i + 1) + 0.00071234567} for i in range(12)]
                page.evaluate(MOUNT, [{"properties": {"value": {"digits": 3}}, "facets": [{"property": "value", "as": "range"}],
                                       "views": [{"type": "table", "name": "T", "order": ["run", "value"]}]},
                                      {"properties": {"run": {"type": "text"}, "value": {"type": "number"}}, "rows": rows}, {}])
                page.evaluate("() => { const rail = document.createElement('data-facets'); rail.setAttribute('for', 'v'); document.body.prepend(rail); }")
                page.wait_for_function("() => document.querySelector('data-facets output, data-facets .df-range, data-facets [data-out]')", timeout=WAIT)
                page.evaluate(FRAMES)
                rail = page.evaluate("() => document.querySelector('data-facets').textContent.replace(/\\s+/g, ' ').trim()")
                check("rail range: the bounds read the declared digits (0.0131 .. 0.149)", "0.0131" in rail and "0.149" in rail, rail[:200])
                check("rail range: no bound is written with every digit", "0.01305" not in rail and "0.1488" not in rail, rail[:200])

            with guard("KPI card"):
                page.evaluate("() => import('/dist/views/kpi.js')")
                page.evaluate("""() => { document.body.innerHTML = ''; const k = document.createElement('data-kpi'); document.body.append(k); window.k = k;
                    k.card = { label: 'Twin RMS', column: { id: 'rms', type: 'number', digits: 3 }, value: { value: 2.6799053096539507, low: 2.1234567, high: 3.7654321, basis: 'measured', source: 'run 7' } }; }""")
                page.wait_for_selector("data-kpi .dv-kpi-num", timeout=WAIT)
                kpi = page.evaluate("""() => ({ num: document.querySelector('data-kpi .dv-kpi-num').textContent, range: (document.querySelector('data-kpi .dv-kpi-range') || {}).textContent,
                    prov: JSON.parse(document.querySelector('data-kpi .dv-kpi-value').dataset.provenance || '{}').value })""")
                check("KPI card: the number, its range and its provenance popover read the declared digits", kpi["num"] == "2.68" and kpi["range"] == "range 2.12–3.77" and kpi["prov"] == "2.68", kpi)

            with guard("record view"):
                page.evaluate(MOUNT, [{"properties": {"m": {"digits": 3}}, "views": [{"type": "record", "name": "R", "order": ["run", "m"]}]},
                                      {"properties": {"run": {"type": "text"}, "m": {"type": "number"}}, "rows": [{"run": "a", "m": STORED}, {"run": "b", "m": 12345.678}]}, {"view": "R"}])
                page.wait_for_function("() => { const e = window.v.querySelector('.dv-view'); return !!e && e.textContent.includes('2.'); }", timeout=WAIT)
                rec = page.evaluate("() => window.v.querySelector('.dv-view').textContent.replace(/\\s+/g, ' ')")
                check("record view: the first record's number reads the declared digits", "2.68" in rec and "2.6799" not in rec, rec[:160])

            with guard("histogram hover card"):
                rows = [{"run": f"r{i}", "value": 0.0137 * i} for i in range(60)]
                page.evaluate(MOUNT, [{"properties": {"value": {"digits": 3}}, "views": [{"type": "chart", "name": "H", "chart": {"mark": "bar", "encoding": {"x": {"field": "value", "bin": True}, "y": {"aggregate": "count"}}}}]},
                                      {"properties": {"run": {"type": "text"}, "value": {"type": "number"}}, "rows": rows}, {}])
                page.wait_for_function("() => { const v = window.v.querySelector('.dv-view'); return v && v.vegaView; }", timeout=WAIT)
                page.evaluate(FRAMES)
                box = page.evaluate("() => { const r = window.v.querySelector('.dv-view canvas').getBoundingClientRect(); return [r.x, r.y]; }")
                spots = page.evaluate("""() => { const vv = window.v.querySelector('.dv-view').vegaView, o = vv.origin(), out = [];
                    const walk = (n) => { if (n.marktype === 'rect') for (const i of n.items) if (i.height > 2 && i.width > 4) out.push([o[0] + i.x + i.width / 2, o[1] + i.y + i.height - 2]); if (n.items) n.items.forEach(walk); };
                    walk(vv.scenegraph().root); return out; }""")
                seen = []
                for sx, sy in spots:
                    page.mouse.move(box[0] + sx, box[1] + sy)
                    page.mouse.move(box[0] + sx + 1, box[1] + sy)
                    page.wait_for_timeout(120)
                    seen.append(page.evaluate("() => { const c = window.v.querySelector('.dv-chart-hover'); const th = c && !c.hidden && c.querySelector('th'); return th ? c.querySelector('td').textContent : null; }"))
                bins = [s for s in seen if s]
                long = [s for s in bins if any(len(part.replace('.', '').lstrip('0')) > 3 for part in s.replace('–', ' ').split())]
                check("histogram hover card: every bin edge reads at most the declared 3 significant digits", len(bins) >= 5 and not long, {"bins": bins[:8], "too long": long[:4]})

            check("no script errors (kit page)", not errors, errors[:2])
            errors.clear()

            with guard("dashboard selection chip"):
                page.goto(site + "/gallery/vibetracks-dashboard/")
                page.wait_for_function("() => { const d = document.querySelector('data-dashboard'); return d && d.dash && d.datasets && d.datasets.runs; }", timeout=WAIT)
                page.evaluate(FRAMES)
                chip = page.evaluate("""() => { const d = document.querySelector('data-dashboard'); const p = d.dash.panels.find((x) => x.dataset === 'runs');
                    d.select(p.key, 'pass_rate', [0.9898989898989899]); return p.key; }""")
                page.wait_for_selector(".dd-chip", timeout=WAIT)
                text = page.evaluate("() => document.querySelector('.dd-chip b').textContent")
                check("dashboard chip: a picked pass_rate reads the declared digits", text.strip() == "0.99", {"panel": chip, "chip": text})
                check("no script errors (dashboard page)", not errors, errors[:2])
            browser.close()
    finally:
        for proc in (root_proc, site_proc):
            proc.terminate()
            proc.wait(timeout=5)
    (OUT / "digits-sweep-checks.json").write_text(json.dumps(checks, indent=1, default=str) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} digits sweep checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
