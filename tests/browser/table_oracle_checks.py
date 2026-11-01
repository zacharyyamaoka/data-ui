"""The table view draws the same HTML as before its speed work: every table and pivot view of every gallery case, and a
synthetic 30,000-row flat and grouped table, at the top and after a scroll to the middle, header and body, compared
with table-oracle.golden.json written from the build BEFORE the change (lane/perf-worker 9bb1818).

    ~/psu-atlas/.venv/bin/python tests/browser/table_oracle_checks.py              # check (after npm run build)
    ~/psu-atlas/.venv/bin/python tests/browser/table_oracle_checks.py --write GOLDEN   # from the OLD build only

WHY HTML, not pixels: the speed work (rows made only for the drawn window, column scales reused while the rows are the
same) must not change one character a reader or a screen reader gets; the drawn HTML is that, exactly. Never write the
golden from the code under test: a deliberate output change regenerates it from the commit before and says why.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN = pathlib.Path(__file__).with_name("table-oracle.golden.json")
WAIT = 60000

CAPTURE = """async () => {
  const v = window.v;
  const view = v.querySelector('.dv-view');
  const grab = () => {
    const t = view.querySelector('table');
    // WHY the origin out: links are absolute, and the test server's port is a new one each run
    const html = t ? (t.querySelector('thead')?.outerHTML || '') + (t.querySelector('tbody')?.outerHTML || '') : view.innerHTML;
    // WHY data-provenance out (CONTRACT §22): a rich cell carries its sources in that attribute on purpose
    // (tests/unit/provenance.test.mjs and sources_checks.py hold it); this oracle proves the speed work changed no
    // other byte, as perf-oracle-corpus.mjs does. The attribute's JSON is escaped, so it holds no raw quote.
    return html.split(location.origin).join('ORIGIN').replace(/ data-provenance="[^"]*"/g, '');
  };
  const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 30))));
  await frame();
  const top = grab();
  const sc = [view, ...view.querySelectorAll('*')].find((e) => e.scrollHeight > e.clientHeight + 4 && getComputedStyle(e).overflowY !== 'visible');
  let mid = '';
  if (sc) { sc.scrollTop = Math.floor((sc.scrollHeight - sc.clientHeight) / 2); await frame(); await frame(); mid = grab(); sc.scrollTop = 0; await frame(); }
  return { top, mid, status: v.querySelector('.dv-status .dv-count')?.textContent || '' };
}"""

MOUNT = """async ([src, name]) => {
  document.body.innerHTML = '';
  const v = document.createElement('data-views');
  v.setAttribute('no-url', ''); v.setAttribute('src', src); v.setAttribute('view', name);
  document.body.append(v); window.v = v;
}"""

SYNTH = """async ([n, grouped]) => {
  document.body.innerHTML = '';
  const v = document.createElement('data-views');
  v.setAttribute('no-url', '');
  document.body.append(v); window.v = v;
  const forms = ['Planetary', 'Harmonic', 'Cycloidal', 'Direct', null];
  const rows = Array.from({ length: n }, (_, i) => ({ id: 'r' + i, name: 'part ' + ((i * 7919) % 4999), form: forms[i % 5],
    mass: (i % 11) ? { value: ((i * 37) % 1000) / 10, basis: i % 3 ? 'datasheet' : 'measured' } : null, torque: ((i * 7919) % 100000) / 100 }));
  v.base = { views: [{ type: 'table', name: 'T', order: ['name', 'form', 'mass', 'torque'], sort: [{ property: 'torque', direction: 'DESC' }],
    ...(grouped ? { groupBy: { property: 'form', direction: 'ASC' }, summaries: { torque: 'Max', mass: 'Average' } } : {}) }] };
  v.data = { properties: { name: { type: 'text' }, form: { type: 'text' }, mass: { type: 'number', unitText: 'g' }, torque: { type: 'number', unitText: 'N·m' } }, rows };
}"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def cases():
    out = []
    for d in sorted((ROOT / "gallery" / "examples").iterdir()):
        f = d / "views.base"
        if not f.exists():
            continue
        text = f.read_text()
        # the view names and types, read the way the kit does (yaml subset): name/type pairs under views:
        try:
            import yaml  # noqa: PLC0415
            doc = yaml.safe_load(text)
        except Exception:  # noqa: BLE001
            continue
        for v in (doc or {}).get("views") or []:
            if (v.get("type") or "table") in ("table", "pivot") and v.get("name"):
                out.append((f"/gallery/examples/{d.name}/views.base", v["name"], f"{d.name} :: {v['name']}"))
    return out


def digest(x):
    return hashlib.sha256(x.encode()).hexdigest()[:16]


def collect(page):
    got = {}
    for src, name, key in cases():
        page.evaluate(MOUNT, [src, name])
        try:
            page.wait_for_function("() => window.v.querySelector('.dv-view') && window.v.dataset.view", timeout=WAIT)
        except Exception:  # noqa: BLE001
            got[key] = {"error": "did not draw"}
            continue
        c = page.evaluate(CAPTURE)
        got[key] = {"top": digest(c["top"]), "mid": digest(c["mid"]), "status": c["status"], "bytes": len(c["top"])}
    for n, grouped in ((30000, False), (30000, True)):
        key = f"synthetic {n} {'grouped' if grouped else 'flat'}"
        page.evaluate(SYNTH, [n, grouped])
        page.wait_for_function("() => window.v.querySelector('.dv-view tbody tr[data-i]')", timeout=WAIT)
        c = page.evaluate(CAPTURE)
        got[key] = {"top": digest(c["top"]), "mid": digest(c["mid"]), "status": c["status"], "bytes": len(c["top"])}
    return got


def main() -> int:
    write = sys.argv[sys.argv.index("--write") + 1] if "--write" in sys.argv else None
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
            # WHY a fixed clock: some views write relative times ("2 h ago"); the same build must draw the same bytes
            page.clock.set_fixed_time("2026-10-27T06:00:00Z")
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base + "/tests/browser/fixtures/lifecycle.html")
            page.wait_for_function("() => window.kitReady", timeout=WAIT)
            got = collect(page)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    if write:
        pathlib.Path(write).write_text(json.dumps({"_": "written by table_oracle_checks.py --write from the build before the change; never from the code under test", "views": got}, indent=1) + "\n")
        print(f"wrote {len(got)} views to {write}; errors {errors[:2]}")
        return 0
    golden = json.loads(GOLDEN.read_text())["views"]
    bad = []
    # WHY the key sets must be equal (judge r4 #2): checking only the golden's keys let a regenerated golden that lost
    # 17 live views pass; a case drawn but not pinned, or pinned but no longer drawn, is a failure of its own
    missing, extra = sorted(set(golden) - set(got)), sorted(set(got) - set(golden))
    ok = not missing and not extra
    print(("PASS " if ok else "FAIL ") + f"table oracle: the golden pins exactly the views drawn ({len(got)})" + ("" if ok else f"  [pinned, not drawn: {missing[:8]}; drawn, not pinned: {extra[:8]}]"), flush=True)
    if not ok:
        bad.append("key sets")
    for key, want in golden.items():
        have = got.get(key)
        ok = have == want
        print(("PASS " if ok else "FAIL ") + f"table oracle: {key}" + ("" if ok else f"  [want {want} have {have}]"), flush=True)
        if not ok:
            bad.append(key)
    print(("PASS " if not errors else "FAIL ") + f"table oracle: no script errors  [{errors[:2]}]")
    n = len(golden) + 2  # every view, the key sets, no script errors
    print(f"{n - len(bad) - (1 if errors else 0)}/{n} table oracle checks pass")
    return 0 if not bad and not errors else 1


if __name__ == "__main__":
    sys.exit(main())
