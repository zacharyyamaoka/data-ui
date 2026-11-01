"""Derive the table oracle's golden for the P0 table fix WITHOUT the code under test, and compare it with that code.

    ~/psu-atlas/.venv/bin/python -I docs/table_oracle_p0_derivation.py BASE_ROOT NEW_ROOT OUT_JSON

(lane/p0-blockers, 2026-10-28; tests/browser/table-oracle.golden.json's _p0_blockers note says what it wrote.)

BASE_ROOT: integrate/packet 8eb8480 built (the code before). NEW_ROOT: lane/p0-blockers built (the code under test).
For every view the oracle pins (the oracle's own cases(), MOUNT, SYNTH, digest, imported from BASE_ROOT), this:
  1. captures the NEW build exactly as table_oracle_checks.py's CAPTURE does, and also records where the mid capture
     scrolled (which element, which scrollTop);
  2. captures the BASE build at the same two positions, then applies the declared change by its spec, computed from the
     BASE page's own virtualiser plan, never from the new code:
       - the spacer below the drawn rows is the sum of the planned sizes of every row after the last one drawn;
       - a table with no column to draw has, as its whole body, one cell saying which named columns its data lacks;
  3. reports, per view, whether hash(spec(BASE)) == hash(NEW) for top and mid, and writes the derived entries.
"""

import hashlib
import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE, NEW, OUT = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
sys.path.insert(0, str(BASE / "tests" / "browser"))
import table_oracle_checks as T  # noqa: E402  (the ruler as it is in the code before)

WAIT = 60000
GRAB = r"""
  const grab = (view, transform) => {
    const t = view.querySelector('table');
    let html;
    if (t) {
      const thead = t.querySelector('thead'), tbody = t.querySelector('tbody');
      html = (thead ? thead.outerHTML : '') + (tbody ? (transform ? transform(tbody) : tbody.outerHTML) : '');
    } else html = view.innerHTML;
    return html.split(location.origin).join('ORIGIN').replace(/ data-provenance="[^"]*"/g, '');
  };
  const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 30))));
"""

# NEW: the oracle's CAPTURE, plus where its mid capture scrolled
NEW_CAPTURE = "async () => {" + GRAB + r"""
  const v = window.v; const view = v.querySelector('.dv-view');
  await frame();
  const top = grab(view);
  const all = [view, ...view.querySelectorAll('*')];
  const sc = all.find((e) => e.scrollHeight > e.clientHeight + 4 && getComputedStyle(e).overflowY !== 'visible');
  let mid = '', at = null, idx = -1;
  if (sc) { idx = all.indexOf(sc); at = Math.floor((sc.scrollHeight - sc.clientHeight) / 2); sc.scrollTop = at; await frame(); await frame(); at = sc.scrollTop; mid = grab(view); sc.scrollTop = 0; await frame(); }
  return { top, mid, at, idx, status: v.querySelector('.dv-status .dv-count')?.textContent || '' };
}"""

# BASE: the same positions, the spec applied to what the code before drew
BASE_CAPTURE = "async ([idx, at]) => {" + GRAB + r"""
  const v = window.v; const view = v.querySelector('.dv-view');
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const plug = v._plugin;
  const spec = (tbody) => {
    const m = plug && plug._model;
    if (!m) return tbody.outerHTML;
    const ncol = m.leaves.length + (plug._selectable ? 1 : 0);
    if (!m.leaves.length) {
      const props = m.props || {};
      const missing = ((plug.input && plug.input.view && plug.input.view.order) || []).filter((id) => !props[id] && !String(id).startsWith('@'));
      const names = missing.slice(0, 6).join(', ') + (missing.length > 6 ? `, … (${missing.length - 6} more)` : '');
      const text = missing.length ? `No columns to show: this view's columns (${names}) are not in its data.` : 'No columns to show: this view hides every property of its data.';
      // through the DOM, as the oracle's grab serializes every capture (an escaped ' is written back as ')
      const t = document.createElement('table');
      t.innerHTML = `<tbody><tr><td class="dv-empty dv-nocols" colspan="${Math.max(1, ncol)}" title="${esc(text)}">${esc(text)}</td></tr></tbody>`;
      return t.tBodies[0].outerHTML;
    }
    const drawn = [...tbody.children].filter((r) => r.hasAttribute('data-index'));
    if (!drawn.length) return tbody.outerHTML;
    const last = Math.max(...drawn.map((r) => Number(r.dataset.index)));
    const cache = plug._virt.measurementsCache || [];
    let below = 0;
    for (let i = last + 1; i < plug._virt.options.count; i++) below += cache[i] ? cache[i].size : plug._virt.options.estimateSize(i);
    const c = tbody.cloneNode(true);
    const tail = c.lastElementChild;
    if (tail && tail.classList.contains('dv-pad') && c.children.length > 1 && tail.previousElementSibling && !tail.previousElementSibling.classList.contains('dv-pad')) tail.remove();
    if (below > 0) c.insertAdjacentHTML('beforeend', `<tr class="dv-pad" aria-hidden="true"><td colspan="${ncol}" style="height:${below}px"></td></tr>`);
    return c.outerHTML;
  };
  await frame();
  const top = grab(view, spec);
  let mid = '', reached = null;
  if (idx >= 0) {
    const all = [view, ...view.querySelectorAll('*')];
    const sc = all[idx];
    sc.scrollTop = at; await frame(); await frame(); reached = sc.scrollTop; mid = grab(view, spec); sc.scrollTop = 0; await frame();
  }
  return { top, mid, reached, status: v.querySelector('.dv-status .dv-count')?.textContent || '' };
}"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(root):
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/tests/browser/fixtures/lifecycle.html", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    return proc, base


def page_for(browser, base):
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.clock.set_fixed_time("2026-10-27T06:00:00Z")
    page.goto(base + "/tests/browser/fixtures/lifecycle.html")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    return page


def mount(page, item):
    src, name, key = item
    if src is None:
        page.evaluate(T.SYNTH, name)
        page.wait_for_function("() => window.v.querySelector('.dv-view tbody tr[data-i]')", timeout=WAIT)
    else:
        page.evaluate(T.MOUNT, [src, name])
        page.wait_for_function("() => window.v.querySelector('.dv-view') && window.v.dataset.view", timeout=WAIT)


def main():
    items = list(T.cases()) + [(None, [30000, False], "synthetic 30000 flat"), (None, [30000, True], "synthetic 30000 grouped")]
    pb, base_url = serve(BASE)
    pn, new_url = serve(NEW)
    out, report = {}, []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            pbase, pnew = page_for(browser, base_url), page_for(browser, new_url)
            for item in items:
                key = item[2]
                mount(pnew, item)
                n = pnew.evaluate(NEW_CAPTURE)
                mount(pbase, item)
                b = pbase.evaluate(BASE_CAPTURE, [n["idx"], n["at"]])
                derived = {"top": T.digest(b["top"]), "mid": T.digest(b["mid"]), "status": b["status"], "bytes": len(b["top"])}
                new = {"top": T.digest(n["top"]), "mid": T.digest(n["mid"]), "status": n["status"], "bytes": len(n["top"])}
                ok = derived == new and (n["idx"] < 0 or b["reached"] == n["at"])
                out[key] = derived
                report.append({"key": key, "ok": ok, "derived": derived, "new": new, "at": n["at"], "reached": b["reached"]})
                print(("SAME " if ok else "DIFF ") + key + ("" if ok else f"  derived {derived} new {new} at {n['at']} reached {b['reached']}"), flush=True)
            browser.close()
    finally:
        pb.terminate(); pn.terminate(); pb.wait(timeout=10); pn.wait(timeout=10)
    OUT.write_text(json.dumps({"views": out, "report": report}, indent=1, ensure_ascii=False) + "\n")
    bad = [r for r in report if not r["ok"]]
    print(f"{len(report) - len(bad)}/{len(report)} views: the spec applied to the code before = the code under test")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
