"""PEP 0010's P0 blockers (docs/peps/0010-robotics-playback.md §11), measured in headless Chromium on the built kit.

    ~/psu-atlas/.venv/bin/python tests/browser/p0_checks.py [OUT_DIR]     # after npm run build

The gaps sim2real found building its dashboards (reports/backlog-sim2real-gaps-2026-10-28.md), each on a cut-down copy
of the sim2real repro in tests/browser/fixtures/p0/ (make_fixture.py: the rack's run spans, the suite's devices):
  #1   the clock spans only the rows the filters leave: a run pick spans that run's min..max t, not the 36 s staircase's
  #9   a two-clause dataset filter (run_set && device) still lists every device in the picker, with counts
  #13  a `src` set after the element is on the page (attribute or property) loads that file's panels, defaults and clock
  #14  two rails over a `device` facet each draw their own default radio checked
  and the table that could not scroll to its last rows (the types lane's finding on pid-tuning "Fidelity by servo").
Every number is computed here from the fixture's JSON files (or the gallery file a repro names) and compared with what
the page drew: the clock's span and the playback bar's readout, ticks and thumb (getBoundingClientRect), the rails'
labels, counts and :checked radios, the radios' drawn pixels, the panels' "N of M" lines, the table's rows and scroll
box. Serves the repo root on a free 127.0.0.1 port, stops that server when done, writes OUT_DIR/p0-checks.json
(default reports/media/p0) and exits 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "p0"
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "browser" / "fixtures" / "p0"
PAGE = "/tests/browser/fixtures/p0/p0.html"
RI = "/tests/browser/fixtures/p0/run-inspector.base"
TC = "/tests/browser/fixtures/p0/type-catalog.base"
WAIT = 30000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
checks: list[dict] = []


def rows(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))["rows"]


SERVO, CAMERA, RUNS = rows(FIX / "servo.json"), rows(FIX / "camera.json"), rows(FIX / "runs.json")
SHORT, LONG = "CAN 11 · s09 · 10-25", "CAN 14 · s03 · 10-23"


def tspan(rs):
    ts = [r["t"] for r in rs if isinstance(r.get("t"), (int, float))]
    return [min(ts), max(ts)] if ts else None


def where(rs, **eq):
    return [r for r in rs if all(r.get(k) == v for k, v in eq.items())]


def count_by(rs, key):
    out = {}
    for r in rs:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


def fmt_time(t):
    """core clock.js fmtTime for 0 <= t < 60: '4.52 s'."""
    return f"{t:.2f} s"


# ------------------------------------------------------------------------------------------------- the oracles
ALL_SPAN = tspan(SERVO)                                              # [0, 35.993]: every run
SHORT_SPAN = tspan(where(SERVO, run=SHORT))                          # [0, 4.518]: the "4.5 s run"
J4_SPAN = tspan(where(SERVO, device="J4 wrist 1"))                   # the one run on J4
HELD = where(SERVO, run_set="held-out")
DEFAULT_SERVO = where(SERVO, run_set="held-out", device="J3 elbow")  # the type catalog's two-clause default
DEVICE_COUNTS = count_by(HELD, "device")                             # the picker under run_set == held-out
RUNSET_COUNTS = count_by(where(SERVO, device="J3 elbow"), "run_set")  # the run set picker under device == J3 elbow
SCENE = where(CAMERA, device="Scene camera")
WRIST = where(CAMERA, device="Wrist camera")
RI_PANELS = ["runs", "playback", "angle", "samples"]
TC_PANELS = ["playback", "servo-samples", "camera-frames"]


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    """A section that cannot run (nothing drawn to measure) is one failing check in its own words, not a crash."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def close(a, b, tol=1e-9):
    return a is not None and b is not None and abs(a - b) <= tol


# ------------------------------------------------------------------------------------------------- page helpers
MOUNT = """([id, src]) => {
  for (const old of document.querySelectorAll('data-dashboard, data-views')) old.remove();
  const d = document.createElement('data-dashboard');
  d.id = id;
  if (src) d.setAttribute('src', src);
  document.body.append(d);
  return true;
}"""

# a dashboard drawn: its panels are `keys` (in order), every panel's view has drawn, every rail has painted
READY = """([id, keys]) => {
  const d = document.getElementById(id);
  if (!d || !d.dash) return false;
  const secs = [...d.querySelectorAll('.dd-panel[data-panel]')];
  if (JSON.stringify(secs.map((s) => s.dataset.panel)) !== JSON.stringify(keys)) return false;
  const els = [...d.querySelectorAll('.dd-panel data-views')];
  if (!els.length || !els.every((e) => e.dataset.view)) return false;
  return [...d.querySelectorAll('.dd-rail data-facets')].every((f) => f.querySelector('details'));
}"""

SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"

CLOCK = """(id) => {
  const d = document.getElementById(id); const c = d.clock;
  const pb = d.querySelector('.dd-panel[data-type="playback"]');
  const track = pb && pb.querySelector('.dv-pb-track');
  return { start: c.start, end: c.end, t: c.t, loop: c.loop, rate: c.rate, window: c.window,
    readout: pb ? pb.querySelector('.dv-pb-end').textContent : null,
    min: track ? Number(track.getAttribute('aria-valuemin')) : null, max: track ? Number(track.getAttribute('aria-valuemax')) : null,
    ticks: pb ? [...pb.querySelectorAll('.dv-pb-ticks span')].map((s) => s.textContent) : [],
    empty: !!(pb && pb.querySelector('[data-empty]')) };
}"""

# seek the clock, then where the playback bar drew its thumb, as a fraction of its track
THUMB = """([id, t]) => {
  const d = document.getElementById(id); d.clock.pause(); d.clock.seek(t);
  const pb = d.querySelector('.dd-panel[data-type="playback"]');
  const tr = pb.querySelector('.dv-pb-track').getBoundingClientRect();
  const th = pb.querySelector('.dv-pb-thumb').getBoundingClientRect();
  return { px: th.left + th.width / 2 - tr.left, width: tr.width, t: d.clock.t };
}"""

# each panel's drawn "N of M"
COUNTS = """(id) => { const out = {};
  for (const sec of document.querySelectorAll(`#${id} .dd-panel[data-panel]`)) {
    const s = sec.querySelector('data-views .dv-status'); if (!s) continue;
    const m = /([\\d,]+) of ([\\d,]+)/.exec(s.textContent);
    if (m) out[sec.dataset.panel] = [Number(m[1].replace(/,/g, '')), Number(m[2].replace(/,/g, ''))];
  }
  return out; }"""

# every rail: each group's items (label, count, radio value, checked, :checked, name), the custom-filter line, and
# whether every aria-labelledby in it resolves inside the same rail
RAIL = """(id) => { const out = {};
  for (const f of document.querySelectorAll(`#${id} .dd-rail data-facets`)) {
    const groups = {};
    for (const g of f.querySelectorAll('section.df-group')) {
      groups[g.dataset.key] = [...g.querySelectorAll('li')].map((li) => { const i = li.querySelector('input');
        return { label: ((li.querySelector('.df-label') || {}).textContent || '').trim(),
          count: Number(((li.querySelector('.df-count') || {}).textContent || '').replace(/,/g, '')),
          value: i ? i.dataset.value : null, checked: i ? i.checked : null, matches: i ? i.matches(':checked') : null, name: i ? i.name : null }; });
    }
    const labelled = [...f.querySelectorAll('[aria-labelledby]')].map((e) => { const h = document.getElementById(e.getAttribute('aria-labelledby')); return !!h && f.contains(h); });
    out[f.dataset.dataset] = { groups, custom: (f.querySelector('.df-custom') || {}).textContent || null, labelled,
      ids: [...f.querySelectorAll('[id]')].map((e) => e.id), open: !!(f.querySelector('details') || {}).open };
  }
  return out; }"""


def items(rail, dataset, key):
    """{label: count} of a group, the 'Any' entry left out, and the checked labels."""
    g = rail[dataset]["groups"][key]
    return {x["label"]: x["count"] for x in g if x["value"] != ""}, [x["label"] for x in g if x["checked"]], g


def open_page(browser, base, *, width=1280, dark=False, hash_=""):
    context = browser.new_context(viewport={"width": width, "height": 900}, color_scheme="dark" if dark else "light")
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(f"{base}{PAGE}{hash_}")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    return page


def mount(page, src, keys, did="dash"):
    page.evaluate(MOUNT, [did, src])
    page.wait_for_function(READY, arg=[did, keys], timeout=WAIT)
    settle(page, 3)


def settle(page, n=2):
    for _ in range(n):
        page.evaluate(SETTLE)


def wait_state(page, js, arg=None):
    page.wait_for_function(js, arg=arg, timeout=WAIT)
    settle(page)


def pick_run(page, run, did="dash"):
    page.locator(f"#{did} .dd-panel[data-panel='runs'] tbody tr[data-i]", has_text=run).first.click()
    wait_state(page, "([id, run]) => { const s = document.getElementById(id).state.select.runs; return !!s && s.values.includes(run); }", [did, run])


def clear_run(page, did="dash"):
    page.locator(f"#{did} .dd-chip[data-clear='runs']").click()
    wait_state(page, "(id) => !document.getElementById(id).state.select.runs", did)


def radio(page, dataset, value, key="device", did="dash"):
    return page.locator(f"#{did} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[type=radio][data-value='{value}']")


def tick(page, dataset, value, key="device", did="dash"):
    radio(page, dataset, value, key, did).check()
    settle(page, 3)


def set_rail(page, dataset, expr, did="dash"):
    """The dashboard's public setRail (CONTRACT §17): a pick the rail cannot offer while another panel's pick hides it."""
    page.evaluate("([id, ds, f]) => document.getElementById(id).setRail(ds, f === null ? undefined : f)", [did, dataset, expr])
    settle(page, 3)


def open_rails(page, did="dash"):
    """A phone folds each rail: open them, as a reader would."""
    page.evaluate("(id) => { for (const d of document.querySelectorAll(`#${id} .dd-rail data-facets details`)) d.open = true; }", did)
    settle(page, 2)


def ticks_ok(ticks, end):
    nums = [float(m.group(0)) for t in ticks for m in [re.search(r"-?\d+(\.\d+)?", t)] if m]
    return bool(nums) and max(nums) <= end + 1e-9, nums


# ------------------------------------------------------------------------------------------------- #1 the clock
def gap1(browser, base):
    page = open_page(browser, base)
    mount(page, RI, RI_PANELS)
    c = page.evaluate(CLOCK, "dash")
    check(f"#1 run inspector, nothing picked: the clock spans every sample (oracle {ALL_SPAN})", [c["start"], c["end"]] == ALL_SPAN, [c["start"], c["end"]])

    pick_run(page, SHORT)
    c = page.evaluate(CLOCK, "dash")
    check(f"#1 a run pick ({SHORT}): the clock spans exactly that run's min..max t in servo.json {SHORT_SPAN}", [c["start"], c["end"]] == SHORT_SPAN, [c["start"], c["end"]])
    check(f"#1 the playback bar reads the run's end ('/ {fmt_time(SHORT_SPAN[1])}') and its track's aria range is the run's",
          (c["readout"] or "").strip() == f"/ {fmt_time(SHORT_SPAN[1])}" and close(c["min"], SHORT_SPAN[0]) and close(c["max"], SHORT_SPAN[1]), {k: c[k] for k in ("readout", "min", "max")})
    ok, nums = ticks_ok(c["ticks"], SHORT_SPAN[1])
    check("#1 every tick on the track lies inside the run (none of the staircase's 10 s, 20 s, 30 s)", ok, nums)
    check("#1 an untouched clock sits at the run's start", close(c["t"], SHORT_SPAN[0]), c["t"])
    mid = (SHORT_SPAN[0] + SHORT_SPAN[1]) / 2
    th = page.evaluate(THUMB, ["dash", mid])
    want = (mid - SHORT_SPAN[0]) / (SHORT_SPAN[1] - SHORT_SPAN[0]) * th["width"]
    check(f"#1 seeking to the run's middle ({mid:.4f} s) draws the thumb at the track's middle within 1 px (getBoundingClientRect)",
          abs(th["px"] - want) <= 1, {"thumb px": round(th["px"], 2), "want px": round(want, 2), "track": round(th["width"], 1)})

    # the rail's counts apply the run pick, so J4 is not offered there now; the pick goes through setRail
    set_rail(page, "servo", 'device == "J4 wrist 1"')
    c = page.evaluate(CLOCK, "dash")
    check("#1 a run pick and a device pick that leave no sample: no span (start and end null), the playback bar empty",
          c["start"] is None and c["end"] is None and c["empty"] and (c["readout"] or "") == "", {k: c[k] for k in ("start", "end", "empty", "readout")})
    set_rail(page, "servo", None)
    clear_run(page)
    c = page.evaluate(CLOCK, "dash")
    check(f"#1 the pick cleared and the rail back to Any: every sample again {ALL_SPAN}", [c["start"], c["end"]] == ALL_SPAN, [c["start"], c["end"]])

    tick(page, "servo", "J4 wrist 1")
    c = page.evaluate(CLOCK, "dash")
    check(f"#1 the clock dataset's own rail (device J4 wrist 1) spans that device's samples {J4_SPAN}", [c["start"], c["end"]] == J4_SPAN, [c["start"], c["end"]])
    tick(page, "servo", "")

    page.evaluate("() => document.getElementById('dash').clock.setWindow([10, 20])")
    pick_run(page, SHORT)
    w1 = page.evaluate(CLOCK, "dash")["window"]
    clear_run(page)
    w2 = page.evaluate(CLOCK, "dash")["window"]
    check("#1 a zoom window outside the picked run is dropped, and comes back with the long span", w1 is None and w2 == [10, 20], {"picked": w1, "cleared": w2})
    page.evaluate("() => document.getElementById('dash').clock.setWindow(null)")
    check("#1 run inspector: no page error", not page.errors, page.errors[:3])
    page.context.close()

    # a shared link: a picked run and t = 10 s, past the run's end; the asked instant comes back with the long span
    value = "run:" + urllib.parse.quote(SHORT, safe="")
    link = "#" + urllib.parse.urlencode({"s.runs": value, "t": "10"})
    page = open_page(browser, base, hash_=link)
    mount(page, RI, RI_PANELS)
    c = page.evaluate(CLOCK, "dash")
    check(f"#1 a link with a picked run and #t=10: the run's span {SHORT_SPAN}, t held at its end", [c["start"], c["end"]] == SHORT_SPAN and close(c["t"], SHORT_SPAN[1]), [c["start"], c["end"], c["t"]])
    clear_run(page)
    c = page.evaluate(CLOCK, "dash")
    check("#1 ... the pick cleared: every sample, and t is the link's 10 s again", [c["start"], c["end"]] == ALL_SPAN and close(c["t"], 10), [c["start"], c["end"], c["t"]])
    page.context.close()

    # the phone width, in dark: the same run pick, the same span, the thumb measured again
    page = open_page(browser, base, width=390, dark=True)
    mount(page, RI, RI_PANELS)
    pick_run(page, SHORT)
    c = page.evaluate(CLOCK, "dash")
    th = page.evaluate(THUMB, ["dash", SHORT_SPAN[1]])
    check("#1 390 px, dark: a run pick spans the run, and t at its end draws the thumb at the track's right end within 1 px",
          [c["start"], c["end"]] == SHORT_SPAN and abs(th["px"] - th["width"]) <= 1, {"span": [c["start"], c["end"]], "thumb px": round(th["px"], 2), "track": round(th["width"], 1)})
    page.context.close()


# ------------------------------------------------------------------------------------------------- #9 and #14 the rails
def drawn_center(page, loc):
    """The median colour of the 3 x 3 pixels at a radio's centre, from a screenshot of exactly what was painted."""
    loc.scroll_into_view_if_needed()
    settle(page)
    b = loc.bounding_box()
    cx, cy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    img = Image.open(io.BytesIO(page.screenshot(clip={"x": cx - 1.5, "y": cy - 1.5, "width": 3, "height": 3}))).convert("RGB")
    px = sorted(img.getdata(), key=lambda p: sum(p))
    return px[len(px) // 2]


def rgb(text):
    m = re.findall(r"[\d.]+", text or "")
    return tuple(round(float(x)) for x in m[:3]) if len(m) >= 3 else None


def dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5 if a and b else 999


def rails(browser, base, *, width, dark):
    tag = f"{width} px, {'dark' if dark else 'light'}"
    page = open_page(browser, base, width=width, dark=dark)
    mount(page, TC, TC_PANELS)
    open_rails(page)
    r = page.evaluate(RAIL, "dash")
    dev, dev_on, _ = items(r, "servo", "device")
    rs, rs_on, _ = items(r, "servo", "run_set")
    cam, cam_on, _ = items(r, "camera", "device")

    # gap 9: the two-clause default
    check(f"#9 {tag}: the Servo picker lists every device under run_set held-out, each with its count (oracle {DEVICE_COUNTS})", dev == DEVICE_COUNTS, dev)
    check(f"#9 {tag}: the Runs picker lists every run set under device J3 elbow, with counts (oracle {RUNSET_COUNTS})", rs == RUNSET_COUNTS, rs)
    check(f"#9 {tag}: the two-clause default is not shown as a custom filter", r["servo"]["custom"] is None, r["servo"]["custom"])
    n = page.evaluate(COUNTS, "dash")
    check(f"#9 {tag}: the servo panel shows the default's {len(DEFAULT_SERVO)} of {len(SERVO)} samples", n.get("servo-samples") == [len(DEFAULT_SERVO), len(SERVO)], n.get("servo-samples"))

    # gap 14: each rail's default radio is checked and drawn checked
    check(f"#14 {tag}: the servo rail's default 'J3 elbow' and 'held-out' are checked; the camera rail's 'Scene camera' too (checked and :checked)",
          dev_on == ["J3 elbow"] and rs_on == ["held-out"] and cam_on == ["Scene camera"]
          and all(x["matches"] == x["checked"] for k in ("device", "run_set") for x in r["servo"]["groups"][k])
          and all(x["matches"] == x["checked"] for x in r["camera"]["groups"]["device"]), {"servo device": dev_on, "servo runs": rs_on, "camera": cam_on})
    names = {ds: sorted({x["name"] for g in r[ds]["groups"].values() for x in g if x["name"]}) for ds in r}
    check(f"#14 {tag}: the two rails' radio groups do not share a name", not set(names["servo"]) & set(names["camera"]), names)
    ids = r["servo"]["ids"] + r["camera"]["ids"]
    check(f"#14 {tag}: no id is used twice across the rails, and every group's aria-labelledby names a heading in its own rail",
          len(ids) == len(set(ids)) and all(all(r[ds]["labelled"]) for ds in r), {"ids": ids, "labelled": {ds: r[ds]["labelled"] for ds in r}})
    with guard(f"#14 {tag}: drawn radios"):
        for ds, key, value in (("servo", "device", "J3 elbow"), ("servo", "run_set", "held-out"), ("camera", "device", "Scene camera")):
            on, off = radio(page, ds, value, key), radio(page, ds, "", key)
            accent = rgb(on.evaluate("(e) => getComputedStyle(e).accentColor"))
            p_on, p_off = drawn_center(page, on), drawn_center(page, off)
            check(f"#14 {tag}: {ds} rail, '{value}' is drawn checked (its centre pixel is the accent {accent}) and its group's 'Any' is not",
                  dist(p_on, accent) < 60 and dist(p_off, accent) > 100, {"checked px": p_on, "Any px": p_off, "accent": accent})
    tick(page, "camera", "Wrist camera")
    r = page.evaluate(RAIL, "dash")
    dev_on, cam_on = items(r, "servo", "device")[1], items(r, "camera", "device")[1]
    n = page.evaluate(COUNTS, "dash")
    check(f"#14 {tag}: picking 'Wrist camera' leaves the servo rail's 'J3 elbow' checked; the camera panel shows {len(WRIST)} of {len(CAMERA)}",
          dev_on == ["J3 elbow"] and cam_on == ["Wrist camera"] and n.get("camera-frames") == [len(WRIST), len(CAMERA)], {"servo": dev_on, "camera": cam_on, "panel": n.get("camera-frames")})
    page.screenshot(path=str(OUT / f"rails-{width}-{'dark' if dark else 'light'}.png"))

    # gap 9 again: a pick keeps every device listed, and the URL carries it readably (no custom blob)
    tick(page, "servo", "J4 wrist 1")
    r = page.evaluate(RAIL, "dash")
    dev, dev_on, _ = items(r, "servo", "device")
    n = page.evaluate(COUNTS, "dash")
    want = len(where(HELD, device="J4 wrist 1"))
    url = page.evaluate("() => ({ q: decodeURIComponent(new URLSearchParams(location.search).get('servo.device') || ''), f: new URLSearchParams(location.hash.slice(1)).has('f.servo') })")
    check(f"#9 {tag}: picking 'J4 wrist 1' keeps every device listed with the same counts; the panel shows {want}; the URL says servo.device and holds no custom blob",
          dev == DEVICE_COUNTS and dev_on == ["J4 wrist 1"] and n.get("servo-samples") == [want, len(SERVO)] and url == {"q": "J4 wrist 1", "f": False},
          {"devices": dev, "checked": dev_on, "panel": n.get("servo-samples"), "url": url})
    c = page.evaluate(CLOCK, "dash")
    check(f"#1 {tag}: the type catalog's clock follows its rails too (J4 wrist 1 in held-out: {J4_SPAN})", [c["start"], c["end"]] == J4_SPAN, [c["start"], c["end"]])
    page.reload()
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    mount(page, TC, TC_PANELS)
    open_rails(page)
    r = page.evaluate(RAIL, "dash")
    dev, dev_on, _ = items(r, "servo", "device")
    n = page.evaluate(COUNTS, "dash")
    check(f"#9 {tag}: a reload of that URL draws 'J4 wrist 1' checked, every device listed, the panel at {want}",
          dev == DEVICE_COUNTS and dev_on == ["J4 wrist 1"] and n.get("servo-samples") == [want, len(SERVO)], {"devices": dev, "checked": dev_on, "panel": n.get("servo-samples")})
    check(f"#9/#14 {tag}: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- #13 src after load
def gap13(browser, base):
    page = open_page(browser, base)
    page.evaluate(MOUNT, ["dash", None])
    settle(page, 4)
    check("#13 a dashboard with no src draws nothing yet", page.evaluate("() => document.querySelectorAll('#dash .dd-panel').length") == 0)
    page.evaluate("(src) => document.getElementById('dash').setAttribute('src', src)", RI)
    with guard("#13 setAttribute('src') after the element is on the page"):
        page.wait_for_function(READY, arg=["dash", RI_PANELS], timeout=WAIT)
        settle(page, 3)
        n, c = page.evaluate(COUNTS, "dash"), page.evaluate(CLOCK, "dash")
        check("#13 setAttribute('src') after the element is on the page loads that file: its panels, rows and clock (loop off, rate 1, every sample)",
              n.get("runs") == [len(RUNS), len(RUNS)] and n.get("samples") == [len(SERVO), len(SERVO)] and c["loop"] is False and c["rate"] == 1 and [c["start"], c["end"]] == ALL_SPAN,
              {"counts": n, "clock": {k: c[k] for k in ("loop", "rate", "start", "end")}})

    page.evaluate("(src) => { document.getElementById('dash').src = src; }", TC)
    with guard("#13 the src property"):
        page.wait_for_function(READY, arg=["dash", TC_PANELS], timeout=WAIT)
        settle(page, 3)
        n, c = page.evaluate(COUNTS, "dash"), page.evaluate(CLOCK, "dash")
        got = page.evaluate("() => document.getElementById('dash').src")
        check("#13 setting the src property loads the new file: its panels, its own default filters, its clock (loop on, rate 2, the default's span)",
              n.get("servo-samples") == [len(DEFAULT_SERVO), len(SERVO)] and n.get("camera-frames") == [len(SCENE), len(CAMERA)]
              and c["loop"] is True and c["rate"] == 2 and [c["start"], c["end"]] == SHORT_SPAN and str(got).endswith(TC),
              {"counts": n, "clock": {k: c[k] for k in ("loop", "rate", "start", "end")}, "src": got})

    page.evaluate("(src) => document.getElementById('dash').setAttribute('src', src)", RI)
    with guard("#13 back to the first file"):
        page.wait_for_function(READY, arg=["dash", RI_PANELS], timeout=WAIT)
        settle(page, 3)
        n, c = page.evaluate(COUNTS, "dash"), page.evaluate(CLOCK, "dash")
        check("#13 and back: the first file's panels and clock again, nothing kept from the second (loop off, rate 1, every sample)",
              n.get("samples") == [len(SERVO), len(SERVO)] and c["loop"] is False and c["rate"] == 1 and [c["start"], c["end"]] == ALL_SPAN,
              {"counts": n, "clock": {k: c[k] for k in ("loop", "rate", "start", "end")}})

    with guard("#13 a drill after the src changed"):
        page.locator("#dash .dd-panel[data-panel='samples'] tbody tr[data-i]").first.click()
        page.wait_for_function("() => { const p = document.querySelector('#dash .dd-drill .dv-peek'); return !!p && !p.hidden; }", timeout=5000)
        ok = page.evaluate("() => { const dr = document.querySelector('#dash .dd-drill'); const p = dr && dr.querySelector('.dv-peek'); return !!dr && dr.isConnected && !!p && !p.hidden && p.getBoundingClientRect().width > 0; }")
        check("#13 after the src changed, a row click still opens the drill-down peek (on the page, drawn)", ok)
        page.keyboard.press("Escape")
        settle(page)

    with guard("#13 the latest src wins"):
        page.evaluate("""(pattern) => { const f = window.fetch; window.fetch = (u, o) => { const s = String(u && u.url ? u.url : u);
            return s.includes(pattern) ? new Promise((r) => setTimeout(r, 1500)).then(() => f(u, o)) : f(u, o); }; }""", "run-inspector.base")
        page.evaluate("([a, b]) => { const d = document.getElementById('dash'); d.setAttribute('src', a); d.setAttribute('src', b); }", [RI + "?slow", TC])
        page.wait_for_timeout(3000)
        settle(page, 3)
        keys = page.evaluate("() => [...document.querySelectorAll('#dash .dd-panel[data-panel]')].map((s) => s.dataset.panel)")
        names = page.evaluate("() => { const d = document.getElementById('dash'); return d.dash ? Object.keys(d.dash.datasets) : []; }")
        check("#13 two srcs set in a row, the first answering last: the second file is drawn", keys == TC_PANELS and "camera" in names, {"panels": keys, "datasets": names})

    with guard("#13 a src set while off the page"):
        page.evaluate("(src) => { const d = document.getElementById('dash'); d.remove(); d.setAttribute('src', src); document.body.append(d); }", RI + "?again")
        page.wait_for_function(READY, arg=["dash", RI_PANELS], timeout=WAIT)
        check("#13 a src set while the element is off the page loads when it is put back", True)

    with guard("#13 reload() keeps the reader's state"):
        pick_run(page, SHORT)
        # WHY wait for the old panel to go: until the reload draws, the old panels still pass READY
        page.evaluate("() => { window.__oldPanel = document.querySelector('#dash .dd-panel'); document.getElementById('dash').reload(); }")
        page.wait_for_function("() => !window.__oldPanel.isConnected", timeout=WAIT)
        page.wait_for_function(READY, arg=["dash", RI_PANELS], timeout=WAIT)
        settle(page, 3)
        sel = page.evaluate("() => (document.getElementById('dash').state.select.runs || {}).values || null")
        c = page.evaluate(CLOCK, "dash")
        check("#13 reload() of the same file keeps the pick (and the clock still spans it)", sel == [SHORT] and [c["start"], c["end"]] == SHORT_SPAN, {"select": sel, "span": [c["start"], c["end"]]})
    check("#13 no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- the table
TABLE = """([n, frame, above, order]) => {
  for (const old of document.querySelectorAll('data-dashboard, data-views, .p0-filler')) old.remove();
  if (above) { const a = document.createElement('div'); a.className = 'p0-filler'; a.style.height = above + 'px'; a.textContent = 'above'; document.body.append(a); }
  const v = document.createElement('data-views');
  v.id = 'tbl'; v.setAttribute('no-url', '');
  if (frame) v.setAttribute('frame', frame); else v.className = 'boxed';
  document.body.append(v);
  const b = document.createElement('div'); b.className = 'p0-filler'; b.style.height = '200px'; b.textContent = 'below'; document.body.append(b);
  const rows = Array.from({ length: n }, (_, i) => ({ id: 'r' + i, name: 'row ' + i, k: i }));
  v.base = { views: [{ type: 'table', name: 'T', order }] };
  v.data = { properties: { name: { type: 'text' }, k: { type: 'number' } }, rows };
  window.scrollTo(0, 0);
}"""

# the scroll box (or the page under a page frame), then ONE scroll to its end: what is drawn there
TABLE_END = """async () => {
  const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 40))));
  await frame(); await frame();
  const v = document.getElementById('tbl'); const t = v.querySelector('table'); const page = v.dataset.scroll === 'page';
  let sc = page ? document.scrollingElement : t.parentElement;
  if (!page) while (sc && sc !== v && !/(auto|scroll|overlay)/.test(getComputedStyle(sc).overflowY)) sc = sc.parentElement;
  const head = t.tHead.getBoundingClientRect().height;
  const before = sc.scrollHeight;
  if (page) window.scrollTo(0, sc.scrollHeight); else sc.scrollTop = sc.scrollHeight;
  await frame(); await frame();
  const drawn = [...t.tBodies[0].rows].filter((r) => r.hasAttribute('data-i'));
  const last = drawn[drawn.length - 1];
  const lb = last ? last.getBoundingClientRect() : null;
  const box = page ? { top: 0, bottom: innerHeight } : (() => { const b = sc.getBoundingClientRect(); return { top: b.top + sc.clientTop, bottom: b.top + sc.clientTop + sc.clientHeight }; })();
  const hb = Math.max(...[...t.tHead.querySelectorAll('th')].map((th) => th.getBoundingClientRect().bottom), t.tHead.getBoundingClientRect().bottom);
  return { head, before, after: sc.scrollHeight, rows: v._plugin._model.flat.length, last: last ? Number(last.dataset.i) : null,
    lastTop: lb && lb.top, lastBottom: lb && lb.bottom, boxTop: box.top, boxBottom: box.bottom, headBottom: hb };
}"""

EMPTY_COLS = """() => {
  const v = document.getElementById('tbl'); const t = v.querySelector('table');
  let sc = t ? t.parentElement : null;
  while (sc && sc !== v && !/(auto|scroll|overlay)/.test(getComputedStyle(sc).overflowY)) sc = sc.parentElement;
  const rows = t ? [...t.tBodies[0].rows] : [];
  return { dataRows: rows.filter((r) => r.hasAttribute('data-i')).length, zero: rows.filter((r) => r.hasAttribute('data-i') && r.getBoundingClientRect().height === 0).length,
    text: (v.querySelector('.dv-view') || {}).textContent || '', scroll: sc ? [sc.scrollHeight, sc.clientHeight] : null,
    status: ((v.querySelector('.dv-status') || {}).textContent || '').trim() };
}"""


def table(browser, base, *, width, dark):
    tag = f"{width} px, {'dark' if dark else 'light'}"
    page = open_page(browser, base, width=width, dark=dark)
    for n, frame, above in ((132, None, 0), (300, "page", 800)):
        where_ = f"{'frame=page, ' + str(above) + ' px above' if frame else 'boxed'}, {n} rows"
        page.evaluate(TABLE, [n, frame, above, ["name", "k"]])
        page.wait_for_function("() => document.querySelector('#tbl .dv-view table tbody tr[data-i]')", timeout=WAIT)
        m = page.evaluate(TABLE_END)
        check(f"table {tag}, {where_}: one scroll to the end draws the last row ({n - 1}) wholly inside the visible box, below the header",
              m["last"] == n - 1 and m["lastBottom"] <= m["boxBottom"] + 0.5 and m["lastTop"] >= m["headBottom"] - 0.5 and m["lastTop"] >= m["boxTop"] - 0.5,
              {k: (round(v, 1) if isinstance(v, float) else v) for k, v in m.items()})
        check(f"table {tag}, {where_}: the scroll length is right from the start (scrollHeight {m['before']} before the scroll = {m['after']} at the end)",
              abs(m["after"] - m["before"]) <= 1, [m["before"], m["after"]])
        if not frame:
            want = round(m["head"]) + n * 30
            check(f"table {tag}, {where_}: scrollHeight = header + {n} x 30 px rows = {want}", abs(m["before"] - want) <= 1, m["before"])

    # a table whose columns are not in its data (the backlog's repro: a dashboard view opened in a plain <data-views>)
    page.evaluate(TABLE, [132, None, 0, ["servo", "ff_fraction", "real_p90"]])
    page.wait_for_function("() => { const v = document.getElementById('tbl'); return v && v.dataset.view; }", timeout=WAIT)
    settle(page, 3)
    e = page.evaluate(EMPTY_COLS)
    check(f"table {tag}: a view none of whose columns is in the data draws no cell-less (0 px) rows and says which columns it lacks",
          e["dataRows"] == 0 and "No columns" in e["text"] and all(c in e["text"] for c in ("servo", "ff_fraction", "real_p90")) and e["scroll"][0] <= e["scroll"][1] + 1,
          {k: e[k] for k in ("dataRows", "zero", "scroll", "status")} | {"text": e["text"][:160]})
    page.evaluate("""() => { for (const old of document.querySelectorAll('data-views, .p0-filler')) old.remove();
      const v = document.createElement('data-views'); v.id = 'tbl'; v.className = 'boxed'; v.setAttribute('no-url', '');
      v.setAttribute('src', '/gallery/examples/pid-tuning/views.base'); v.setAttribute('view', 'Fidelity by servo'); document.body.append(v); }""")
    page.wait_for_function("() => { const v = document.getElementById('tbl'); return v && v.dataset.view && v.querySelector('.dv-view'); }", timeout=WAIT)
    settle(page, 3)
    e = page.evaluate(EMPTY_COLS)
    check(f"table {tag}: the backlog's repro (pid-tuning 'Fidelity by servo' in a plain <data-views>, 132 rows of another dataset) names its missing columns instead of a blank box that cannot reach its end",
          e["dataRows"] == 0 and "No columns" in e["text"] and "servo" in e["text"] and "ff_fraction" in e["text"] and re.search(r"132 of 132", e["status"]) is not None,
          {k: e[k] for k in ("dataRows", "zero", "scroll", "status")} | {"text": e["text"][:160]})
    check(f"table {tag}: no page error", not page.errors, page.errors[:3])
    page.context.close()


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
        check("fixture: the 4.5 s run, the 36 s staircase and the type catalog's default, as make_fixture.py writes them",
              SHORT_SPAN == [0.0, 4.518] and ALL_SPAN == [0.0, 35.993] and len(DEFAULT_SERVO) > 0 and len(DEVICE_COUNTS) == 4,
              {"short": SHORT_SPAN, "all": ALL_SPAN, "default": len(DEFAULT_SERVO), "devices": DEVICE_COUNTS})
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            with guard("#1 the clock spans the filtered rows"):
                gap1(browser, base)
            for width, dark in ((1280, False), (1280, True), (390, False), (390, True)):
                with guard(f"#9/#14 rails at {width} px, {'dark' if dark else 'light'}"):
                    rails(browser, base, width=width, dark=dark)
            with guard("#13 src after load"):
                gap13(browser, base)
            for width, dark in ((1280, False), (390, True)):
                with guard(f"table at {width} px"):
                    table(browser, base, width=width, dark=dark)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "p0-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} P0 checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
