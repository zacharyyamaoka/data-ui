"""The lineage view's links (docs/CONTRACT.md §21): one curve for every link, and extinct lines folded by default.

    ~/psu-atlas/.venv/bin/python tests/browser/lineage_links_checks.py [OUT_DIR]     # after npm run build

Serves the repo root on a free 127.0.0.1 port (tests/browser/fixtures/lineage-links.html), stops it when done, writes
OUT_DIR/lineage-links-checks.json (default reports/media/gallery-lineage) and exits 1 if any check fails. Every claim
is read from the drawn SVG, never from the layout module's own return value.

  one shape    every tree edge, "+N" stub and splice of every lineage view of both lineage cases (rectangular and radial,
               extinct folded and shown) is the same path: one move, one cubic curve. Zach, 2026-10-28: "I am just not a
               fan of how you are using different line shapes like straight vs curved."
  tangents     a rectangular link leaves its parent and meets its child horizontally (a d3 linkHorizontal), so the curve
               is the same shape and not merely the same command letters
  dashed       only a splice is dashed (a second parent is data), never an edge or a stub
  default      a view with no `extinct:` key opens with its extinct lines folded into "+N", the Show extinct button not
               pressed, and shows them as stubs after one click
"""

from __future__ import annotations

import json
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "gallery-lineage"
OUT.mkdir(parents=True, exist_ok=True)
checks: list[dict] = []
FIXTURE = "tests/browser/fixtures/lineage-links.html"
CASES = [
    ("brand-lineage", "/gallery/examples/brand-lineage/views.base", ["robotparts", "robotparts radial", "BAM", "Every brand"]),
    ("model-lineage", "/gallery/examples/model-lineage/views.base", ["Ladder", "Ladder, radial"]),
]
DEFAULTS = ("default", "/tests/browser/fixtures/lineage-links-default.base", ["Default", "Default radial"])


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# every link as drawn: its class, its path data and the dash the browser resolved for it
LINKS = """() => {
  const root = document.querySelector('#v .dv-lineage');
  return { layout: root.dataset.layout, extinct: root.dataset.extinct,
    pressed: root.querySelector('[data-act=extinct]').getAttribute('aria-pressed'),
    groups: root.querySelectorAll('g.dv-lineage-node.dv-group').length,
    links: [...root.querySelectorAll('path.dv-lineage-edge, path.dv-lineage-splice, path.dv-lineage-stub')].map((p) => ({
      kind: p.classList.contains('dv-lineage-splice') ? 'splice' : p.classList.contains('dv-lineage-stub') ? 'stub' : 'edge',
      extinctEdge: p.classList.contains('dv-extinct') && p.classList.contains('dv-lineage-edge'),
      d: p.getAttribute('d'), dash: getComputedStyle(p).strokeDasharray })) };
}"""

NUM = r"-?\d*\.?\d+(?:e-?\d+)?"


def commands(d: str) -> str:
    return re.sub(r"[-\d.,e\s]+", "", d)


def flat_tangents(d: str) -> bool:
    """A d3 linkHorizontal: M x0,y0 C mx,y0 mx,y1 x1,y1, so both control points sit at their endpoint's height."""
    n = [float(x) for x in re.findall(NUM, d)]
    return len(n) == 8 and abs(n[3] - n[1]) < 1e-6 and abs(n[5] - n[7]) < 1e-6


def open_page(browser, base, src, view):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(f"{base}/{FIXTURE}?src={src}&view={view}")
    page.wait_for_selector("#v .dv-lineage g.dv-lineage-node", timeout=30000)
    page.evaluate("() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))")
    return page


def main() -> int:
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/" + FIXTURE, timeout=1)
                break
            except Exception:  # noqa: BLE001 - not up yet
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()

            # ---- one shape, in every lineage view of both cases, folded and shown
            for case, src, views in CASES:
                for view in views:
                    page = open_page(browser, base, src, view)
                    for state in ("as the case ships it", "extinct toggled"):
                        if state == "extinct toggled":
                            page.click("#v .dv-lineage-bar [data-act=extinct]")
                            page.wait_for_timeout(200)
                        m = page.evaluate(LINKS)
                        links = m["links"]
                        shapes = sorted({commands(l["d"]) for l in links})
                        kinds = sorted({l["kind"] for l in links})
                        label = f"{case} / {view} ({m['layout']}, extinct {m['extinct']}, {state})"
                        check(f"{label}: every link, {len(links)} drawn ({', '.join(kinds)}), is one move and one cubic curve",
                              len(links) > 0 and shapes == ["MC"], {"shapes": shapes, "kinds": kinds})
                        if m["layout"] == "rectangular":
                            bad = [l["d"] for l in links if not flat_tangents(l["d"])]
                            check(f"{label}: every rectangular link leaves its parent and meets its child horizontally (the same d3 curve)",
                                  not bad, bad[:2])
                        dashed = sorted({l["kind"] for l in links if l["dash"] not in ("none", "")})
                        check(f"{label}: only splices are dashed", dashed in ([], ["splice"]) and not any(l["kind"] == "splice" and l["dash"] in ("none", "") for l in links), dashed)
                    check(f"{case} / {view}: no page error", not page.errors, page.errors[:2])
                    page.context.close()

            # ---- the default: no `extinct:` key means folded
            case, src, views = DEFAULTS
            for view in views:
                page = open_page(browser, base, src, view)
                m = page.evaluate(LINKS)
                shown_extinct = [l for l in m["links"] if l["extinctEdge"]]
                check(f"default ({view}): with no `extinct:` key the view opens folded (+N groups, no extinct stub drawn, Show extinct not pressed)",
                      m["extinct"] == "collapse" and m["groups"] > 0 and not shown_extinct and m["pressed"] == "false",
                      {"extinct": m["extinct"], "groups": m["groups"], "extinct edges": len(shown_extinct), "pressed": m["pressed"]})
                page.click("#v .dv-lineage-bar [data-act=extinct]")
                page.wait_for_timeout(200)
                m2 = page.evaluate(LINKS)
                check(f"default ({view}): one click on Show extinct draws them as stubs and folds nothing",
                      m2["extinct"] == "show" and m2["groups"] == 0 and any(l["extinctEdge"] for l in m2["links"]) and m2["pressed"] == "true",
                      {"extinct": m2["extinct"], "groups": m2["groups"], "extinct edges": sum(l["extinctEdge"] for l in m2["links"])})
                page.context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    passed = sum(c["ok"] for c in checks)
    print(f"{passed}/{len(checks)} lineage link checks pass")
    (OUT / "lineage-links-checks.json").write_text(json.dumps(checks, indent=1, ensure_ascii=False))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
