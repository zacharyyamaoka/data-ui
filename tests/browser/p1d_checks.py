"""PEP 0010 P1d (docs/peps/0010-robotics-playback.md §5.2, §11): compare. The arrows and Z-arcs a trajectory3d draws
from the difference rows, compare's display-only scale, the error panels of both templates, and the rail hiding a
series in every panel; measured in headless Chromium on the built kit. Written red, before the code.

    ~/psu-atlas/.venv/bin/python tests/browser/p1d_checks.py [OUT_DIR]     # after npm run build

Two oracles, both files read here with Python (never the page's model):
  - the difference(a, b) fixture, gallery/robotics/fixtures/difference/, read through gallery/robotics/fixture.py as a
    gallery check reads it (fixture.rows('diff_poses')), drawn by tests/browser/fixtures/p1d/fixture.base: a = real,
    b = target, tool0 of run fixture/r1;
  - each template's own diff_poses.json / diff_samples.json (gallery/examples/robotics-servo, robotics-arm), which
    their producers write with gallery/robotics/difference.py (tools/test_robotics_difference.py holds that half).

The card's hook (`.dv-scene3d`'s `scene3d`, tests/browser/p1b_checks.py lists the rest) gains:
  arrows()  [{series, t, from: [x, y, z], to: [x, y, z], tip: [x, y, z], drawn: {from: [x, y, z], tip: [x, y, z]}}]:
            every arrow drawn now (its time inside the trail window, its series shown), in buffer order. `from` and
            `to` are a(t) and b(t) as the card read them from the difference rows (float64), `tip` where the head is
            drawn (from + scale · (to − from), float64), `drawn` the shaft's two ends read back from the GPU buffer
            (float32)
  arcs()    [{series, t, at: [x, y, z], own: [w, x, y, z], ref: [w, x, y, z], drawn: {own: [p0, p1], ref: [p0, p1],
            arc: [p…]}}]: every Z-arc drawn now: its anchor and the two quaternions as read (a's, b's), and from the
            buffer the own-Z segment, the reference-Z segment and the arc's points, own-Z tip to reference-Z tip
DOM: [data-compare-label], the card's label of compare's display scale ("arrows ×20"), shown while the scale is not 1.

What is measured:
  - every drawn arrow runs from a(tᵢ) to b(tᵢ) within 1e-6 mm of the fixture: as read (float64), and in the GPU
    buffer, whose float32 holds the fixture's number rounded to float32 (within 1e-6 mm of that rounding); at density
    20 the arrows are the 23 marker rows of 152 (the density rule), at density 400 every row;
  - at scale 20 every arrow is 20 times as long (its drawn tip at a + 20 (b − a) within float32's rounding, the
    length ratio within 1e-4), and the card says "arrows ×20" where it can be read, at 1280 and at 390 px;
  - each arc ends along both Z axes within 0.1°: its own-Z segment along a's quaternion's +Z, its reference segment
    along b's, the arc's first point along a's Z and its last along b's;
  - the error panels' values equal the diff files: each timeseries' own Vega dataset against the file's rows of the
    picked run (reference target, the rail's joint), every situation, every sample, exactly;
  - a series hidden on the rail (Show) loses its arrows and arcs in every 3D panel and its line in every error panel;
  - both templates in light and dark at 1280 and 390 px: every panel draws, the page never scrolls sideways.
Screenshots to OUT_DIR (default reports/media/robotics-p1cd). Serves the repo root and dist/site on free 127.0.0.1
ports, stops both, writes OUT_DIR/p1d-checks.json, exits 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import json
import math
import pathlib
import socket
import struct
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "robotics-p1cd"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "gallery" / "robotics"))
import fixture  # noqa: E402  the difference fixture, read the one way every consumer reads it

SITE = ROOT / "dist" / "site"
EX = ROOT / "gallery" / "examples"
SERVO, ARM = "robotics-servo", "robotics-arm"
PAGE = "/tests/browser/fixtures/p1d/p1d.html"
FIX_BASE = "/tests/browser/fixtures/p1d/fixture.base"
WAIT = 45000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
MM = 1e-6     # the PEP's tolerance on an arrow's ends, mm
DEG = 0.1     # the PEP's tolerance on an arc's end directions
checks: list[dict] = []


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str)[:400]}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


def rows(case, name):
    doc = json.loads((EX / case / name).read_text(encoding="utf-8"))
    return doc["rows"] if isinstance(doc, dict) else doc


# ------------------------------------------------------------------------------------------------- arithmetic
def f32(x):
    return struct.unpack("f", struct.pack("f", x))[0]


def off(p, q):
    """The largest coordinate difference of two points, or inf when either is missing."""
    if not p or not q or len(p) != 3 or len(q) != 3:
        return math.inf
    return max(abs(a - b) for a, b in zip(p, q))


def markers_at(n, density):
    """traj_compare's density rule (CONTRACT §32): samples 0, s, 2s, … with s = ⌊n / density⌋ (at least 1), plus the
    last."""
    s = max(1, n // density)
    idx = list(range(0, n, s))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return idx


def z_axis(q):
    """The +Z column of a wxyz quaternion's rotation, normalised first."""
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z)
    w, x, y, z = w / n, x / n, y / n, z / n
    return [2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)]


def angle_deg(a, b):
    na, nb = math.sqrt(sum(c * c for c in a)), math.sqrt(sum(c * c for c in b))
    if not na or not nb:
        return math.inf
    d = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b)) / (na * nb)))
    return math.degrees(math.acos(d))


def sub(p, q):
    return [a - b for a, b in zip(p, q)]


A = lambda r: [r["x_mm"], r["y_mm"], r["z_mm"]]  # noqa: E731  a(tᵢ), the row's own pose
B = lambda r: [r["ref_x_mm"], r["ref_y_mm"], r["ref_z_mm"]]  # noqa: E731  b(tᵢ)
QA = lambda r: [r[f"quat_{c}"] for c in "wxyz"]  # noqa: E731
QB = lambda r: [r[f"ref_quat_{c}"] for c in "wxyz"]  # noqa: E731


def arrow_errors(drawn, want, scale=1.0):
    """Each drawn arrow against its difference row (matched by t, in time order): the worst float64 and float32
    differences, and the rows that miss."""
    got = sorted(drawn or [], key=lambda a: a["t"])
    want = sorted(want, key=lambda r: r["t"])
    if len(got) != len(want):
        return {"drawn": len(got), "rows": len(want)}, None
    worst = {"from (as read)": 0.0, "to (as read)": 0.0, "from (GPU)": 0.0, "tip (GPU)": 0.0, "t": 0.0}
    bad = []
    for g, r in zip(got, want):
        a, b = A(r), B(r)
        tip64 = [c + (bb - c) * scale for c, bb in zip(a, b)]  # the card's own arithmetic: c + (to − c) · scale
        e = {"from (as read)": off(g.get("from"), a), "to (as read)": off(g.get("to"), b),
             "from (GPU)": off((g.get("drawn") or {}).get("from"), [f32(c) for c in a]),
             "tip (GPU)": off((g.get("drawn") or {}).get("tip"), [f32(c) for c in tip64]), "t": abs(g["t"] - r["t"])}
        for k, v in e.items():
            worst[k] = max(worst[k], v)
        if max(e.values()) > MM:
            bad.append({"t": r["t"], **{k: v for k, v in e.items() if v > MM}})
    return (bad[:3] if bad else None), worst


def arc_errors(drawn, want):
    """Each drawn arc against its difference row: the angle of its own-Z segment to a's +Z, of its reference segment to
    b's, and of the arc's first and last points (from the anchor) to a's and b's Z."""
    got = sorted(drawn or [], key=lambda a: a["t"])
    want = sorted(want, key=lambda r: r["t"])
    if len(got) != len(want):
        return {"drawn": len(got), "rows": len(want)}, None
    worst = {"own Z": 0.0, "ref Z": 0.0, "arc start": 0.0, "arc end": 0.0, "anchor mm": 0.0}
    bad = []
    for g, r in zip(got, want):
        d = g.get("drawn") or {}
        za, zb = z_axis(QA(r)), z_axis(QB(r))
        own, ref, arc = d.get("own") or [[0, 0, 0], [0, 0, 0]], d.get("ref") or [[0, 0, 0], [0, 0, 0]], d.get("arc") or []
        at = own[0]
        e = {"own Z": angle_deg(sub(own[1], own[0]), za), "ref Z": angle_deg(sub(ref[1], ref[0]), zb),
             "arc start": angle_deg(sub(arc[0], at), za) if arc else math.inf, "arc end": angle_deg(sub(arc[-1], at), zb) if arc else math.inf}
        anchor = off(at, [f32(c) for c in A(r)])
        for k, v in e.items():
            worst[k] = max(worst[k], v)
        worst["anchor mm"] = max(worst["anchor mm"], anchor)
        if max(e.values()) > DEG or anchor > MM:
            bad.append({"t": r["t"], **{k: round(v, 5) for k, v in e.items()}, "anchor mm": anchor})
    return (bad[:3] if bad else None), worst


# ------------------------------------------------------------------------------------------------- serving and pages
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(directory, probe):
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(directory)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + probe, timeout=1)
            break
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.1)
    return proc, base


SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"


def settle(page, n=2):
    for _ in range(n):
        page.evaluate(SETTLE)


def new_page(browser, width=1280, dark=False):
    mobile = width < 500
    context = browser.new_context(viewport={"width": width, "height": 1000 if width > 500 else 844}, color_scheme="dark" if dark else "light",
                                  device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(f"console: {m.text}") if m.type == "error" else None)
    return page


def hook_js(scope):
    return f"(k) => {{ const p = document.querySelector(`{scope} .dd-panel[data-panel='${{k}}']`); const r = p && p.querySelector('.dv-scene3d'); return r && r.scene3d ? r.scene3d : null; }}"


def hook(page, scope, key, call, *args):
    return page.evaluate(f"([k, args]) => {{ const h = ({hook_js(scope)})(k); try {{ return h ? h.{call}(...args) : null; }} catch (e) {{ return null; }} }}", [key, list(args)])


def set_compare(page, scope, key, block):
    """host.setView on a panel's <data-views>, merging `block` into its trajectory3d entry (the controls' own path)."""
    page.evaluate("""([scope, k, block]) => { const el = document.querySelector(`${scope} .dd-panel[data-panel='${k}'] data-views`);
      const v = el.view || {}; el.setView({ trajectory3d: { ...(v.trajectory3d || {}), ...block } }); }""", [scope, key, block])
    settle(page, 4)


def label(page, scope, key):
    """The card's compare label as a reader sees it: its text, and whether it is laid out, visible and inside the card."""
    return page.evaluate("""([scope, k]) => { const p = document.querySelector(`${scope} .dd-panel[data-panel='${k}']`); const card = p && p.querySelector('.dv-scene3d');
      const e = card && card.querySelector('[data-compare-label]'); if (!e) return null; const r = e.getBoundingClientRect(), c = card.getBoundingClientRect(), s = getComputedStyle(e);
      return { text: e.textContent.trim(), shown: !e.hidden && s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity) > 0 && r.width > 0 && r.height > 0,
        inside: r.left >= c.left - 1 && r.right <= c.right + 1 && r.top >= c.top - 1 && r.bottom <= c.bottom + 1 }; }""", [scope, key])


def no_sideways(page, width):
    return page.evaluate("() => document.scrollingElement.scrollWidth") <= width


def shot(page, scope, name):
    try:
        page.evaluate(f"() => {{ const d = document.querySelector('{scope}'); if (d) window.scrollTo(0, d.getBoundingClientRect().top + window.scrollY - 60); }}")
        settle(page)
        page.locator(scope).first.screenshot(path=str(OUT / f"{name}.png"))
    except Exception as e:  # noqa: BLE001 -- a missing picture is not a failed behaviour; say so
        print(f"(screenshot {name} not taken: {e})")


# ------------------------------------------------------------------------------------------------- the fixture
FIX_ROWS = [r for r in fixture.rows("diff_poses") if r["run"] == "fixture/r1" and r["body"] == "tool0" and r["situation"] == "real" and r["reference"] == "target"]


def fixture_page(browser, base, *, width=1280, dark=False):
    page = new_page(browser, width, dark)
    page.goto(f"{base}{PAGE}")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    page.evaluate("""(src) => { const d = document.createElement('data-dashboard'); d.id = 'dash'; d.setAttribute('no-url', ''); d.setAttribute('src', src); document.body.append(d); }""", FIX_BASE)
    ok = True
    try:
        page.wait_for_function(f"() => {{ const h = ({hook_js('#dash')})('compare'); return !!h && h.renders() > 0; }}", timeout=WAIT)
    except Exception:  # noqa: BLE001
        ok = False
    settle(page, 3)
    return page, ok


def fixture_checks(browser, base):
    n = len(FIX_ROWS)
    check(f"fixture: diff_poses.json holds {n} rows of real against target for tool0 of fixture/r1 (the oracle)", n == 152, n)
    page, ok = fixture_page(browser, base)
    check("fixture: the compare card draws the fixture (a frame rendered)", ok)
    # density 20: the 23 marker rows
    idx = markers_at(n, 20)
    want = [FIX_ROWS[i] for i in idx]
    got = hook(page, "#dash", "compare", "arrows")
    bad, worst = arrow_errors(got, want)
    check(f"fixture, density 20: {len(idx)} arrows, at the marker rows 0, 7, … 147, 151 of 152 (the density rule)",
          got is not None and sorted(a["t"] for a in got) == [r["t"] for r in want], {"drawn": len(got or []), "want": len(idx)})
    check("fixture, density 20: every drawn arrow runs from a(tᵢ) to b(tᵢ) within 1e-6 mm of the fixture (as read, and in the GPU buffer to float32's rounding)",
          got is not None and bad is None and worst is not None, bad or worst)
    # the arcs (real draws frames-z): one per marker row, along a's Z and b's Z
    arcs = hook(page, "#dash", "compare", "arcs")
    bad, worst = arc_errors(arcs, want)
    check("fixture: every Z-arc's ends lie along a's Z and b's Z within 0.1° (own segment, reference segment, the arc's first and last points)",
          arcs is not None and bad is None and worst is not None, bad or worst)
    shot(page, "#dash", "fixture-compare-light-1280")
    # density 400: every row
    set_compare(page, "#dash", "compare", {"density": 400})
    got = hook(page, "#dash", "compare", "arrows")
    bad, worst = arrow_errors(got, FIX_ROWS)
    check(f"fixture, density 400: an arrow on every one of the {n} rows, each from a(tᵢ) to b(tᵢ) within 1e-6 mm (as read and in the GPU buffer)",
          got is not None and len(got) == n and bad is None, bad or {"drawn": len(got or []), **(worst or {})})
    arcs = hook(page, "#dash", "compare", "arcs")
    bad, worst = arc_errors(arcs, FIX_ROWS)
    check(f"fixture, density 400: a Z-arc on every row, its ends along both Z axes within 0.1°", arcs is not None and bad is None, bad or worst)
    # scale 20: display only, 20 times as long, and the card says so
    set_compare(page, "#dash", "compare", {"density": 20, "compare": {"data": "diff", "pairs": [["real", "target"]], "scale": 20}})
    got = hook(page, "#dash", "compare", "arrows")
    bad, worst = arrow_errors(got, want, scale=20)
    ratios = []
    for g, r in zip(sorted(got or [], key=lambda a: a["t"]), want):
        d = math.dist(A(r), B(r))
        if d > 1e-3:
            ratios.append(math.dist(g["drawn"]["from"], g["drawn"]["tip"]) / d)
    worst_ratio = max((abs(x - 20) / 20 for x in ratios), default=math.inf)
    check("fixture, scale 20: every arrow's drawn tip is at a + 20 (b − a) (float32's rounding of the card's float64, within 1e-6 mm) and from stays a(tᵢ)",
          got is not None and bad is None, bad or worst)
    check("fixture, scale 20: every arrow is 20 times as long as b − a (length ratio within 1e-4)", ratios and worst_ratio <= 1e-4,
          {"arrows": len(ratios), "worst relative": worst_ratio})
    lab = label(page, "#dash", "compare")
    check("fixture, scale 20: the card says 'arrows ×20' where it is read (visible, inside the card)",
          bool(lab) and "arrows ×20" in lab["text"] and lab["shown"] and lab["inside"], lab)
    shot(page, "#dash", "fixture-compare-x20-light-1280")
    set_compare(page, "#dash", "compare", {"compare": {"data": "diff", "pairs": [["real", "target"]], "scale": 1}})
    lab = label(page, "#dash", "compare")
    check("fixture, scale 1: no arrows label (the arrows are their true length)", lab is None or not lab["shown"], lab)
    check("fixture: no page error", not page.errors, page.errors[:3])
    page.context.close()
    for width, dark in ((390, False), (390, True), (1280, True)):
        page, ok = fixture_page(browser, base, width=width, dark=dark)
        set_compare(page, "#dash", "compare", {"compare": {"data": "diff", "pairs": [["real", "target"]], "scale": 20}})
        lab = label(page, "#dash", "compare")
        got = hook(page, "#dash", "compare", "arrows")
        bad, _ = arrow_errors(got, want, scale=20)
        tag = f"fixture, {width} px, {'dark' if dark else 'light'}"
        check(f"{tag}: at scale 20 the arrows are drawn to a + 20 (b − a) and 'arrows ×20' is readable on the card; no sideways scroll",
              ok and bad is None and bool(lab) and "arrows ×20" in lab["text"] and lab["shown"] and lab["inside"] and no_sideways(page, width), {"label": lab, "arrows": bad})
        shot(page, "#dash", f"fixture-compare-x20-{'dark' if dark else 'light'}-{width}")
        check(f"{tag}: no page error", not page.errors, page.errors[:3])
        page.context.close()


# ------------------------------------------------------------------------------------------------- the templates
POINTS = """([scope, k]) => { const p = document.querySelector(`${scope} .dd-panel[data-panel='${k}']`); const plot = p && p.querySelector('.dv-timeseries-plot');
  const v = plot && plot.parentElement.vegaView; if (!v) return null; const out = {}; for (const d of v.data('series')) (out[d.series] = out[d.series] || []).push([d.x, d.value]); return out; }"""
READY = """([scope, keys]) => { const d = document.querySelector(scope); if (!d || !d.dash) return false;
  for (const k of keys) { const s = d.querySelector(`.dd-panel[data-panel='${k}']`); if (!s) return false; const el = s.querySelector('data-views'); if (!el || !el.dataset.view) return false;
    const r = s.querySelector('.dv-scene3d'); if (r && !(r.scene3d && r.scene3d.renders() > 0)) return false;
    const v = s.querySelector('.dv-timeseries-plot'); if (v && !v.parentElement.vegaView) return false; }
  return [...d.querySelectorAll('.dd-rail data-facets')].every((f) => f.querySelector('details')); }"""


def open_case(browser, base, case, keys, *, width=1280, dark=False):
    page = new_page(browser, width, dark)
    page.goto(f"{base}/gallery/{case}/index.html")
    with contextlib.suppress(Exception):
        page.wait_for_selector("#example .dd-panel[data-panel]", timeout=WAIT)
        for k in keys:
            page.locator(f"#example .dd-panel[data-panel='{k}']").scroll_into_view_if_needed(timeout=5000)
    ok = True
    try:
        page.wait_for_function(READY, arg=["#example", keys], timeout=WAIT)
    except Exception:  # noqa: BLE001
        ok = False
    settle(page, 3)
    return page, ok


def drawn_points(page, key):
    return {s: sorted(tuple(p) for p in pts) for s, pts in (page.evaluate(POINTS, ["#example", key]) or {}).items()}


def file_points(rs, run, y, **eq):
    out = {}
    for r in rs:
        if r["run"] != run or any(r.get(k) != v for k, v in eq.items()):
            continue
        v = r.get(y)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out.setdefault(r["situation"], []).append((r["t"], v))
    return {s: sorted(v) for s, v in out.items()}


def same_points(drawn, want):
    bad = []
    for s in sorted(set(drawn) | set(want)):
        d, w = drawn.get(s, []), want.get(s, [])
        if d != w:
            i = next((k for k, (x, y) in enumerate(zip(d, w)) if x != y), min(len(d), len(w)))
            bad.append({"series": s, "drawn": len(d), "file": len(w), "first difference": i, "drawn point": d[i] if i < len(d) else None, "file point": w[i] if i < len(w) else None})
    return bad


def rail_radio(dataset, key, value):
    return f"#example .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[type=radio][data-value='{value}']"


def checked_value(page, dataset, key):
    return page.evaluate("(s) => { const i = document.querySelector(s); return i ? i.dataset.value : null; }",
                         f"#example .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[type=radio]:checked")


def pick_run(page, run):
    radio = page.locator(rail_radio("runs", "run", run))
    if not radio.count():
        more = page.locator("#example .dd-rail data-facets[data-dataset='runs'] section.df-group[data-key='run'] [data-more]")
        if more.count():
            more.first.click()
            settle(page)
    radio = page.locator(rail_radio("runs", "run", run))
    radio.scroll_into_view_if_needed()
    radio.check()
    page.wait_for_function("(run) => JSON.stringify(document.querySelector('#example').state.rail.runs || '').includes(run)", arg=run, timeout=WAIT)
    settle(page, 4)


def show_only(page, dataset, values):
    """The rail's Show facet: tick these situations, so every other is hidden (the rail's own checkboxes)."""
    for v in values:
        box = page.locator(f"#example .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='situation'] input[type=checkbox][data-value='{v}']")
        box.scroll_into_view_if_needed()
        box.check()
        settle(page, 2)
    settle(page, 3)


SERVO_KEYS = ["runs", "playback", "angle", "angle-error", "velocity", "torque"]
ARM_KEYS = ["runs", "playback", "path-3d", "path-top", "eef-error", "joint-error", "joint-angle"]


def servo(browser, base):
    runs, diff = rows(SERVO, "runs.json"), rows(SERVO, "diff_samples.json")
    samples = rows(SERVO, "samples.json")
    page, ok = open_case(browser, base, SERVO, SERVO_KEYS)
    check("servo: every panel draws, the angle error among them", ok)
    newest = max(runs, key=lambda r: r["started"])["run"]
    longest = max(runs, key=lambda r: r["duration_s"])["run"]
    for i, run in enumerate(dict.fromkeys([newest, longest])):
        if i:
            pick_run(page, run)
        dev = next(r["device"] for r in samples if r["run"] == run)
        bad = same_points(drawn_points(page, "angle-error"), file_points(diff, run, "e_q_mrad", reference="target", device=dev))
        check(f"servo {run}: the angle error panel draws exactly diff_samples.json's e_q_mrad against the target, every situation, every sample", not bad, bad[:3] or None)
    # hide the twin on the rail: its error line leaves the panel, real's stays
    show_only(page, "samples", ["target", "real"])
    drawn = drawn_points(page, "angle-error")
    run = checked_value(page, "runs", "run")
    dev = next((r["device"] for r in samples if r["run"] == run), None)
    want = {s: v for s, v in file_points(diff, run, "e_q_mrad", reference="target", device=dev).items() if s != "twin"}
    bad = same_points(drawn, want)
    check("servo: hiding the twin on the rail (Show: target and real) removes its error line and leaves real's exactly", "twin" not in drawn and not bad, bad[:3] or sorted(drawn))
    check("servo: no page error", not page.errors, page.errors[:3])
    page.context.close()


def arm(browser, base):
    runs, dposes, dsamples = rows(ARM, "runs.json"), rows(ARM, "diff_poses.json"), rows(ARM, "diff_samples.json")
    page, ok = open_case(browser, base, ARM, ARM_KEYS)
    check("arm: every panel draws, the EEF and joint error among them", ok)
    newest = max(runs, key=lambda r: r["started"])["run"]
    others = [r["run"] for r in runs if r["run"] != newest]
    for i, run in enumerate([newest] + others):
        if i:
            pick_run(page, run)
        dev = checked_value(page, "samples", "device")
        bad = same_points(drawn_points(page, "eef-error"), file_points(dposes, run, "err_mm", reference="target"))
        check(f"arm {run}: the EEF error panel draws exactly diff_poses.json's err_mm against the target, every situation, every sample", not bad, bad[:3] or None)
        bad = same_points(drawn_points(page, "joint-error"), file_points(dsamples, run, "e_q_mrad", reference="target", device=dev))
        check(f"arm {run}: the joint error panel draws exactly diff_samples.json's e_q_mrad of the rail's joint ({dev}) against the target", dev is not None and not bad, bad[:3] or None)
        # the top view draws every time step: each pair the card compares, at the density's marker rows
        cmp = hook(page, "#example", "path-top", "arrows") or []
        series = sorted({a["series"] for a in cmp})
        problems = {}
        for s in series:
            pair = [r for r in dposes if r["run"] == run and r["situation"] == s and r["reference"] == "target"]
            pair.sort(key=lambda r: r["t"])
            want = [pair[k] for k in markers_at(len(pair), 20)] if pair else []
            bad, worst = arrow_errors([a for a in cmp if a["series"] == s], want)
            if bad is not None:
                problems[s] = bad
        check(f"arm {run}: path-top's arrows ({', '.join(series) or 'none'}) each run from a(tᵢ) to b(tᵢ) of diff_poses.json within 1e-6 mm (as read and in the GPU buffer), at the density's marker rows",
              series and not problems, problems or {"series": series, "arrows": len(cmp)})
    # back on the newest run: the 3D view's arcs inside its trail window, along both Z axes
    pick_run(page, newest)
    pair = sorted((r for r in dposes if r["run"] == newest and r["situation"] == "real" and r["reference"] == "target"), key=lambda r: r["t"])
    marks = [pair[k] for k in markers_at(len(pair), 20)]
    mid = marks[len(marks) // 2]["t"] if marks else 0
    page.evaluate("(t) => { const c = document.querySelector('#example').clock; c.pause(); c.seek(t); }", mid)
    settle(page, 3)
    w = hook(page, "#example", "path-3d", "window") or {}
    lo, hi = w.get("lo"), w.get("hi")
    inside = [r for r in marks if (lo is None or r["t"] >= lo) and (hi is None or r["t"] <= hi)]
    arcs = [a for a in (hook(page, "#example", "path-3d", "arcs") or []) if a["series"] == "real"]
    bad, worst = arc_errors(arcs, inside)
    check(f"arm: path-3d at t = {mid} draws real's Z-arcs inside its trail window {[lo, hi]}, each ending along a's and b's Z within 0.1°",
          inside and bad is None, bad or worst)
    arrows = [a for a in (hook(page, "#example", "path-3d", "arrows") or []) if a["series"] == "real"]
    bad, worst = arrow_errors(arrows, inside)
    check("arm: path-3d's arrows inside that window run from a(tᵢ) to b(tᵢ) within 1e-6 mm", inside and bad is None, bad or worst)
    shot(page, "#example", "arm-compare-light-1280")
    # hide real on the rail (Show: every other situation): its arrows, arcs and error lines leave every panel
    others = sorted({r["situation"] for r in rows(ARM, "poses.json") if r["run"] == newest} - {"real"})
    show_only(page, "poses", others)
    got = {k: [a for a in (hook(page, "#example", k, "arrows") or []) if a["series"] == "real"] for k in ("path-3d", "path-top")}
    arcs = [a for a in (hook(page, "#example", "path-3d", "arcs") or []) if a["series"] == "real"]
    eef, joint = drawn_points(page, "eef-error"), drawn_points(page, "joint-error")
    check("arm: hiding real on the rail (Show: the others) removes its arrows from path-3d and path-top, its Z-arcs, and its line from the EEF and joint error panels",
          not got["path-3d"] and not got["path-top"] and not arcs and "real" not in eef and "real" not in joint and eef and joint,
          {"arrows": {k: len(v) for k, v in got.items()}, "arcs": len(arcs), "eef": sorted(eef), "joint": sorted(joint)})
    still = [a for a in (hook(page, "#example", "path-top", "arrows") or [])]
    check("arm: the other series keep their arrows in path-top (it compares every situation with the target: a hide is per series, not all of compare)",
          any(a["series"] != "real" for a in still), sorted({a["series"] for a in still}))
    check("arm: no page error", not page.errors, page.errors[:3])
    page.context.close()


def looks(browser, base):
    for case, keys in ((SERVO, SERVO_KEYS), (ARM, ARM_KEYS)):
        for width, dark in ((1280, False), (1280, True), (390, False), (390, True)):
            tag = f"{case}, {width} px, {'dark' if dark else 'light'}"
            page, ok = open_case(browser, base, case, keys, width=width, dark=dark)
            check(f"{tag}: every panel draws (the error panels among them) and the page never scrolls sideways", ok and no_sideways(page, width),
                  page.evaluate("() => document.scrollingElement.scrollWidth"))
            shot(page, "#example", f"{case.removeprefix('robotics-')}-{'dark' if dark else 'light'}-{width}")
            check(f"{tag}: no page error", not page.errors, page.errors[:3])
            page.context.close()


def main() -> int:
    if not (ROOT / "dist" / "data-ui.js").exists() or not (SITE / "index.html").exists():
        print("dist/ is not built: npm --prefix ~/data-ui run build")
        return 1
    procs = []
    try:
        root_proc, base = serve(ROOT, PAGE)
        procs.append(root_proc)
        site_proc, site_base = serve(SITE, "/index.html")
        procs.append(site_proc)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for name, fn, where in (("the fixture", fixture_checks, base), ("the servo template", servo, site_base), ("the arm template", arm, site_base),
                                    ("themes and widths", looks, site_base)):
                with guard(name):
                    fn(browser, where)
            browser.close()
    finally:
        for p in procs:
            p.terminate()
            p.wait(timeout=10)
    (OUT / "p1d-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} P1d checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
