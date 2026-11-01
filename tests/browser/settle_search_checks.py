"""A preset settles on a pick, never on a word (docs/CONTRACT.md §39). Found reviewing the fleet map's own code after its checks
went green; written red, before the fix.

    ~/psu-atlas/.venv/bin/python tests/browser/settle_search_checks.py     # after npm run build

setRail runs on every keystroke in a search facet. A word that hides the picked run for a moment must not move the pick: it
would be gone when the word is. A tick on a rail upstream that hides the picked run is a pick, and does move it. Measured on
tests/browser/fixtures/fleet_map/search.base, a real keyboard and a real click, the oracle gallery/examples/robotics-fleet's
deployments.json and runs.json. Serves the repo root on a free 127.0.0.1 port, stops it when done, and exits 1 if any check
fails.
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
CASE = ROOT / "gallery" / "examples" / "robotics-fleet"
FLEET = json.loads((CASE / "deployments.json").read_text(encoding="utf-8"))["rows"]
RUNS = sorted(json.loads((CASE / "runs.json").read_text(encoding="utf-8"))["rows"], key=lambda r: r["started"], reverse=True)
WAIT = 20000  # ms: a ceiling, not a pause
checks = []


def check(name, ok, value=None):
    checks.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str)[:300]}]" if value is not None else ""), flush=True)


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


MOUNT = """(src) => { document.body.innerHTML = ''; const el = document.createElement('data-dashboard'); el.id = 'dash'; el.setAttribute('src', src); document.body.append(el); }"""
PICK = """() => { const s = document.querySelector('#dash').state.select.runs; return s ? s.values : null; }"""
DRAWN = """() => document.querySelector('#dash [data-panel="runs"] data-views').model.rows.map((r) => r.run)"""
WAIT_DRAWN = """(want) => JSON.stringify(document.querySelector('#dash [data-panel="runs"] data-views').model.rows.map((r) => r.run)) === JSON.stringify(want)"""
SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 120))))"


def main():
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    origin = f"http://127.0.0.1:{port}"
    page_path = "/tests/browser/fixtures/fleet_map/page.html"
    for _ in range(100):
        try:
            urllib.request.urlopen(origin + page_path, timeout=1)
            break
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.1)
    first = RUNS[0]
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(origin + page_path)
            page.wait_for_function("() => window.kitReady", timeout=WAIT)
            page.evaluate(MOUNT, "/tests/browser/fixtures/fleet_map/search.base")
            page.wait_for_selector("#dash [data-panel='runs'] tbody tr[data-i]", timeout=WAIT)
            page.wait_for_selector("#dash .dd-rail input.df-search", timeout=WAIT)
            page.evaluate(SETTLE)
            check("the page opens on the preset, the newest run", page.evaluate(PICK) == [first["run"]], page.evaluate(PICK))

            word = next(kind for kind in ("homing", "sort cycle", "pick and place") if kind not in first["label"])
            want = [run["run"] for run in RUNS if word in run["label"].lower()]
            box = page.locator("#dash .dd-rail input.df-search").first
            box.click()
            page.keyboard.type(word, delay=30)
            page.wait_for_function(WAIT_DRAWN, arg=want, timeout=WAIT)
            check(f"typing '{word}' narrows the runs and hides the picked one", first["run"] not in page.evaluate(DRAWN), len(page.evaluate(DRAWN)))
            check("... and moves no pick: a word is transient", page.evaluate(PICK) == [first["run"]], page.evaluate(PICK))
            box.fill("")
            page.wait_for_function(WAIT_DRAWN, arg=[run["run"] for run in RUNS], timeout=WAIT)
            page.evaluate(SETTLE)
            check("clearing the word finds the pick where it was", page.evaluate(PICK) == [first["run"]], page.evaluate(PICK))

            owner = next(row for row in FLEET if row["deployment"] == first["deployment"])
            status = next(row["status"] for row in FLEET if row["status"] != owner["status"])
            robots = {row["deployment"] for row in FLEET if row["status"] == status}
            kept = [run["run"] for run in RUNS if run["deployment"] in robots]
            page.evaluate("() => { for (const d of document.querySelectorAll('#dash .dd-rail data-facets details')) d.open = true; }")
            page.evaluate(SETTLE)
            page.locator(f"#dash .dd-rail section.df-group[data-key='status'] input[data-value='{status}']").check()
            page.wait_for_function(WAIT_DRAWN, arg=kept, timeout=WAIT)
            page.evaluate(SETTLE)
            check(f"a tick on {status} upstream hides the picked run: that is a pick, so the preset picks again, the newest run left", page.evaluate(PICK) == [kept[0]], page.evaluate(PICK))
            check("no page error", not errors, errors[:3])
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    print(f"{sum(checks)}/{len(checks)} settle search checks pass")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
