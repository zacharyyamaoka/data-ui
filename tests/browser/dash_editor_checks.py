"""The dashboard editor (the dashboard editor amendment of docs/CONTRACT.md, docs/peps/*-dashboard-editor.md), measured in
headless Chromium on the built kit. Written red, before the code; never edited after.

    $DATA_UI_PYTHON tests/browser/dash_editor_checks.py [OUT_DIR]     # after npm run build

Zach's verdict on the babble (2026-10-29): V1 Edit mode and V2 Blueprint "feel quite related", support both; "Cool idea how
you kinda like queue up these things to be added to the dashboard". So one editor: Edit mode is the base, the Blueprint is
its outline, the queue is a short list beside it. Every input here is the real mouse or keyboard (page.mouse, drag_to,
page.keyboard); nothing calls the editor's functions.

THE ORACLE IS THE FIXTURE'S TEXT. tests/browser/fixtures/dash_editor/servo.base carries comments above, inside and after
entries, a key quoted by hand, a block entry, blank lines between its blocks. Where an edit has one right answer, the
expected text is built here from servo.base by replacing literal lines, and the editor's text must equal it to the byte.
reading.golden.json was written by make_golden.py from main @ d5ede93, before the editor, so "renders exactly as today"
is measured against the old code.

  - today:      no `editor`: the page is the golden, Arrange stays, no editor bundle loads, the babble's attributes do
                nothing. `editor`: the same panels, Edit in place of Arrange, a reader's kept arrangement not drawn over the
                file, nothing loaded until Edit is pressed.
  - the task:   the babble's task (add Torque, above Angle, half width, remove the note, rename Velocity, show it as a table,
                save), its frozen outcome checks, both checkers, drawn again from what the host kept.
  - canvas:     drag and resize where panels sit, up and down; the text is exactly one moved or changed line; what the canvas
                shows after a drop is what the file draws; comments and hand-written quotes stay.
  - outline:    the layout as a tree in file order, reorder, hide, group as tabs, and either side showing a change in the
                other at once, without redrawing the panels; one options pane.
  - queue:      filled by Add to dashboard (§34), drained by a drag or a click, back on Undo, out of its file only on Save.
  - save:       the diff first, the host's answer, its error, no host, Save as copy, Exit's question, undo and redo, a file
                that moved underneath, reload().
  - panes:      every side panel (found on the page, so a new one is covered) drags, keeps its width, resets, folds, by
                mouse and key, measured with getBoundingClientRect. The rail too, while editing.
  - keyboard:   the whole loop with no mouse.
  - themes:     light and dark at 1280 and 390 px, colours from the tokens, no sideways page scroll in any state.
  - gallery:    the Servo case opts in, and its page edits and saves.
Serves the repo root on a free 127.0.0.1 port, stops it when done, writes OUT_DIR/dash-editor-checks.json (default
reports/media/dash-editor) with screenshots, and exits 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import difflib
import json
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "dash-editor"
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "browser" / "fixtures" / "dash_editor"
URL = "/tests/browser/fixtures/dash_editor/"
PAGE = URL + "page.html"
READING = URL + "reading.html"
SERVO = (FIX / "servo.base").read_text(encoding="utf-8")
SAVED = (FIX / "saved.base").read_text(encoding="utf-8")
GOLDEN = json.loads((FIX / "reading.golden.json").read_text(encoding="utf-8"))
WAIT = 30000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
D = "#servo"
checks: list[dict] = []

sys.path.insert(0, str(ROOT / "packages" / "core" / "python"))
import data_ui_base  # noqa: E402  the stdlib .base reader, the Python twin of base.js

sys.path.insert(0, str(FIX))
from make_golden import MEASURE, READY  # noqa: E402  both sides of the golden measure one way

# ---- the fixture's own lines: what an edit may touch
L_DURATION = '    - { "view": Duration, w: 4 }  # quoted by hand, and an edit keeps the quotes\n'
L_PLAYBACK = "    - { view: Playback, w: 12 }\n"
L_ANGLE = "    - { view: Angle, w: 6, h: 3 }  # the tracking plot\n"
L_VELOCITY = "    - { view: Velocity, w: 6, h: 3 }\n"
L_RUNS_W = "      w: 12\n"
L_NOTE_HEAD = "    # the agent's note on what the twin check means\n"
L_TWIN = "    - { view: Twin q RMS, w: 4 }\n"
ANGLE_V = "  - type: timeseries\n    name: Angle\n"


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str, ensure_ascii=False)[:500]}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    """A section that cannot run is one failing check in its own words, not a crash."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:400]}")


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


def checkers(text):
    """Both checkers on a text, next to the fixture's data files: (js ok, py ok, their output)."""
    with tempfile.TemporaryDirectory() as tmp:
        for f in ("runs.json", "samples.json"):
            shutil.copy(FIX / f, pathlib.Path(tmp) / f)
        path = pathlib.Path(tmp) / "saved.base"
        path.write_text(text, encoding="utf-8")
        js = subprocess.run(["node", str(ROOT / "bin" / "data-ui.mjs"), "check", str(path)], capture_output=True, text=True)
        py = subprocess.run([sys.executable, str(ROOT / "tools" / "check_views.py"), str(path)], capture_output=True, text=True)
    return js.returncode == 0, py.returncode == 0, (js.stdout + js.stderr + py.stdout + py.stderr).strip()[-500:]


def changed(a, b):
    """The lines one text lost and gained against the other: (removed, added)."""
    rem, add = [], []
    for line in difflib.ndiff(a.splitlines(), b.splitlines()):
        if line.startswith("- "):
            rem.append(line[2:])
        elif line.startswith("+ "):
            add.append(line[2:])
    return rem, add


def same_text(tag, got, want):
    """The editor's text is exactly the expected one (the oracle is built from the fixture's lines)."""
    if got == want:
        check(tag, True)
        return
    rem, add = changed(want, got or "")
    check(tag, False, {"expected but missing": rem[:6], "unexpected": add[:6]})


# ------------------------------------------------------------------------------------------------- driving the page

P = lambda key: f'{D} .dd-panel[data-panel="{key}"]'  # noqa: E731
GRIP = lambda key: f"{P(key)} .dde-grip"  # noqa: E731
EAST = lambda key: f"{P(key)} .ui-resizable-e"  # noqa: E731
OUTLINE = '[data-dde-pane="outline"]'
OPTIONS = '[data-dde-pane="options"]'
ROW = lambda key: f'{OUTLINE} .dde-row[data-key="{key}"]'  # noqa: E731
Q = lambda item: f'{OUTLINE} .dde-q[data-item="{item}"]'  # noqa: E731
OPT = lambda name: f'{OPTIONS} [data-dde="{name}"]'  # noqa: E731
BAR = lambda act: f'{D} [data-act="{act}"]'  # noqa: E731
WIDE = (1280, 800)


class Pages:
    """One browser: a fresh context per journey, its page errors collected."""

    def __init__(self, browser, base):
        self.browser, self.base = browser, base
        self.errors: list[str] = []

    def open(self, path=PAGE, size=WIDE, dark=False, motion="reduce", storage=None, mobile=False, perms=None):
        ctx = self.browser.new_context(viewport={"width": size[0], "height": size[1]}, color_scheme="dark" if dark else "light",
                                       reduced_motion=motion, has_touch=mobile, is_mobile=mobile)
        if perms:
            ctx.grant_permissions(perms, origin=self.base)
        page = ctx.new_page()
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        page.requests = []
        page.on("request", lambda r: page.requests.append(r.url))
        if storage:
            page.goto(self.base + "/tests/browser/fixtures/dash_editor/reading.html")
            page.evaluate("(s) => { for (const [k, v] of Object.entries(s)) localStorage.setItem(k, v); }", storage)
        page.goto(self.base + path)
        ready(page)
        return page


def ready(page):
    page.wait_for_function("window.kitReady === true", timeout=WAIT)
    page.wait_for_function(READY, timeout=WAIT)
    page.wait_for_timeout(350)


def edit(page, grid=True):
    """Press Edit, as a reader does, and wait for the editor to be up."""
    page.locator(BAR("edit")).click()
    page.wait_for_selector(f"{D}[data-editing] {OUTLINE}", timeout=WAIT)
    if grid:
        page.wait_for_selector(f"{D} .dd-grid.grid-stack .dd-panel.grid-stack-item", timeout=WAIT)
    page.wait_for_function(READY, timeout=WAIT)
    page.wait_for_timeout(250)


def text(page):
    """The text the dashboard is drawing (the draft while editing)."""
    return page.evaluate(f"() => document.querySelector('{D}').baseText")


def rev(page):
    return page.evaluate(f"() => +(document.querySelector('{D}').dataset.ddeRev || 0)")


def settle(page, before, what, timeout=WAIT):
    """Wait for an edit to land (the editor counts every text it applies on the element), then a frame."""
    try:
        page.wait_for_function(f"() => +(document.querySelector('{D}').dataset.ddeRev || 0) > {before}", timeout=timeout)
    except Exception as e:  # noqa: BLE001 -- said in the step's own words
        raise RuntimeError(f"no edit landed after: {what}") from e
    page.wait_for_timeout(120)


def box(page, sel):
    loc = page.locator(sel).first
    loc.scroll_into_view_if_needed()
    b = loc.bounding_box()
    if not b:
        raise RuntimeError(f"nothing drawn for {sel}")
    return b


def rect(page, sel):
    """A box as getBoundingClientRect says, with no scrolling."""
    return page.evaluate("(s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }", sel)


def drag(page, src, to, steps=18):
    """A pointer drag from point src to point to, with a pause before the drop (gridstack and native DnD both see it)."""
    page.mouse.move(*src)
    page.mouse.down()
    page.mouse.move(src[0] + 8, src[1] + 8, steps=4)
    page.mouse.move(*to, steps=steps)
    page.wait_for_timeout(250)
    page.mouse.up()


def grid_order(page):
    """The panels in the order the canvas previews them, the one being dragged in its place (gridstack's own nodes)."""
    return page.evaluate(f"""() => [...document.querySelector('{D} .dd-grid').gridstack.engine.nodes].sort((a, b) => a.y - b.y || a.x - b.x).map((n) => n.id)""")


def drag_until(page, mover, before=None, after=None, label="move"):
    """Take the panel by its grip and move it a little at a time until the canvas previews it right before `before` or
    right after `after`, then let go: what a reader does, watching the grid. WHY closed-loop: a list reflows under the
    pointer as the panel passes others, so a fixed target point says less than the preview does."""
    anchor = before or after
    page.evaluate("(s) => { const t = document.querySelector(s).getBoundingClientRect(); window.scrollBy(0, t.top - 200); }", P(anchor))
    page.wait_for_timeout(120)
    page.hover(P(mover))
    g = rect(page, GRIP(mover))
    a = rect(page, P(anchor))
    x, y = g["x"] + min(40, g["w"] / 2), g["y"] + g["h"] / 2
    r = rev(page)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 6, y + 6, steps=3)
    x, y = x + 6, y + 6
    step = -24 if a["y"] < g["y"] else 24
    hit = False
    for _ in range(70):
        y += step
        page.mouse.move(x, y, steps=2)
        page.wait_for_timeout(30)
        order = grid_order(page)
        i = order.index(mover)
        hit = (i + 1 < len(order) and order[i + 1] == before) if before else (i > 0 and order[i - 1] == after)
        if hit:
            break
    page.mouse.up()
    if not hit:
        raise RuntimeError(f"{label}: the canvas never previewed {mover} next to {anchor}: {grid_order(page)}")
    settle(page, r, label)


def resize_to(page, key, columns):
    """Drag the panel's east handle until it is `columns` of 12 wide."""
    page.locator(P(key)).scroll_into_view_if_needed()
    page.hover(P(key))
    page.wait_for_timeout(120)
    h = rect(page, EAST(key))
    g = rect(page, f"{D} .dd-grid")
    p = rect(page, P(key))
    r = rev(page)
    y = h["y"] + h["h"] / 2
    drag(page, (h["x"] + h["w"] / 2, y), (p["x"] + g["w"] * columns / 12 - 4, y), steps=20)
    settle(page, r, "resize")


def row_order(page):
    return page.evaluate(f"""() => [...document.querySelectorAll('{OUTLINE} .dde-row[data-key]')].map((e) => e.dataset.key)""")


def panel_rows(page):
    """The panels as drawn, row by row: [[key, …], …] (a row is a shared top)."""
    return page.evaluate(f"""() => {{ const ps = [...document.querySelectorAll('{D} .dd-panel')].map((s) => {{ const r = s.getBoundingClientRect(); return {{ k: s.dataset.panel, y: Math.round(r.top), x: r.left }}; }}).sort((a, b) => a.y - b.y || a.x - b.x);
      const out = []; for (const p of ps) {{ const last = out[out.length - 1]; if (last && Math.abs(last.y - p.y) <= 3) last.keys.push(p.k); else out.push({{ y: p.y, keys: [p.k] }}); }} return out.map((r) => r.keys); }}""")


def layout_names(t):
    doc = data_ui_base.loads(t)
    out = []
    for p in (doc.get("layout") or {}).get("panels") or []:
        out.append(p.get("view") or ("text" if "text" in p else tuple(p.get("views"))))
    return out


def saves(page, name=None):
    all_ = page.evaluate("() => window.host.saves")
    return [s for s in all_ if not name or s["name"] == name]


def set_opt(page, name, value):
    """Type into an options field and leave it, as a reader does (fill, Enter or Tab)."""
    r = rev(page)
    page.fill(OPT(name), str(value))
    page.press(OPT(name), "Enter")
    settle(page, r, name)


def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"))


# ------------------------------------------------------------------------------------------------- today

def today(pages):
    for width in (1280, 390):
        page = pages.open(READING, size=(width, 800 if width > 400 else 844))
        got = page.evaluate(MEASURE)
        check(f"no editor, {width} px: the bar, the element and every panel's box are the golden from before the editor", got == GOLDEN[str(width)],
              [k for k in got if got[k] != GOLDEN[str(width)].get(k)])
        if width == 1280:
            check("no editor: Arrange is there, Edit is not", page.locator(BAR("arrange")).count() == 1 and page.locator(BAR("edit")).count() == 0)
            page.wait_for_timeout(300)
            none = page.evaluate("() => document.querySelectorAll('[class*=\"dde-\"], .grid-stack, [data-editing]').length")
            check("no editor: the babble's edit-variant and edit-switcher do nothing, and no editor chrome exists", none == 0, none)
            check("no editor: the editor bundle is never requested", not [u for u in page.requests if "dashboard-edit" in u or "dashboard-arrange" in u], [u for u in page.requests if "dashboard-" in u])
        page.context.close()
    bundle = ROOT / "dist" / "dashboard-edit.js"
    gone = [w for w in ("edit-variant", "edit-switcher", "dde-switcher", "src-toggle", "ask-input", "sv-toggle") if bundle.exists() and w in bundle.read_text(encoding="utf-8")]
    check("the editor's bundle exists and carries nothing of the switcher or of V3, V4 and V5", bundle.exists() and not gone, gone)
    page = pages.open(PAGE)
    got = page.evaluate(MEASURE)
    want = GOLDEN["1280"]
    check("editor opted in, not editing: the same panels in the same boxes", got["panels"] == want["panels"] and got["grid"] == want["grid"] and got["rail"] == want["rail"], got["panels"][:2])
    check("editor opted in: one quiet Edit in place of Arrange", page.locator(BAR("edit")).count() == 1 and page.locator(BAR("arrange")).count() == 0, got["actions"][:200])
    check("editor opted in: nothing of the editor is loaded before Edit is pressed", not [u for u in page.requests if "dashboard-edit" in u or "dashboard-arrange" in u])
    shot(page, "reading")
    page.context.close()
    # WHY both pages: Arrange's rule holds where no editor is opted in, and where one is the file is the one truth
    order = json.dumps([{"key": k, "w": w, "h": h} for k, w, h in (("velocity", 6, 3), ("angle", 6, 3))])
    kept = {f"data-ui/dash-layout:{URL}servo.base": order}
    page = pages.open(READING, storage=kept)
    rows = panel_rows(page)
    check("no editor: a reader's kept arrangement is still drawn over the file", rows and rows[0] == ["velocity", "angle"], rows)
    page.context.close()
    page = pages.open(PAGE, storage=kept)
    rows = panel_rows(page)
    check("editor opted in: a kept arrangement is not drawn over the file (the file is what Edit edits)", rows and rows[0] == ["twin-q-rms", "duration", "logged-at"], rows)
    page.context.close()


# ------------------------------------------------------------------------------------------------- the babble's task

ORDER = ["Twin q RMS", "Duration", "Logged at", "Runs", "Playback", "Torque", "Angle", "Velocity"]


def outcome(tag, t):
    """The babble's frozen outcome (tests/browser/dash_edit_checks.py on lane/dash-edit-babble): structure, then comments."""
    if not isinstance(t, str) or not t.strip():
        check(f"{tag}: the host received the saved .base text", False, t)
        return
    check(f"{tag}: the host received the saved .base text", True, f"{len(t)} chars")
    js_ok, py_ok, out = checkers(t)
    check(f"{tag}: data-ui check accepts the saved text", js_ok, out)
    check(f"{tag}: tools/check_views.py accepts the saved text", py_ok, out)
    doc = data_ui_base.loads(t)
    orig = data_ui_base.loads(SERVO)
    names = layout_names(t)
    check(f"{tag}: the panels are in the task's order, the note gone", names == ORDER, names)
    panels = (doc.get("layout") or {}).get("panels") or []
    entry = {p.get("view"): p for p in panels if p.get("view")}
    vs = {v.get("name"): v for v in (doc.get("views") or [])}
    ovs = {v.get("name"): v for v in (orig.get("views") or [])}
    torque = vs.get("Torque") or {}
    check(f"{tag}: Torque is half width (w: 6)", (entry.get("Torque") or {}).get("w") == 6, entry.get("Torque"))
    check(f"{tag}: Torque is a time series of Samples' tau_nm", torque.get("type") == "timeseries" and torque.get("from") == "samples" and (torque.get("timeseries") or {}).get("y") == "tau_nm", torque)
    check(f"{tag}: Velocity's panel is titled Joint velocity", (entry.get("Velocity") or {}).get("title") == "Joint velocity", entry.get("Velocity"))
    check(f"{tag}: Velocity is drawn as a table of Samples", (vs.get("Velocity") or {}).get("type") == "table" and (vs.get("Velocity") or {}).get("from") == "samples", vs.get("Velocity"))
    same = [n for n in ("Twin q RMS", "Duration", "Logged at", "Runs", "Playback", "Angle") if vs.get(n) != ovs.get(n)]
    check(f"{tag}: every other view is as the agent wrote it", not same, same)
    check(f"{tag}: the datasets, links, clock and style are as the agent wrote them", all(doc.get(k) == orig.get(k) for k in ("datasets", "links", "clock", "style", "data")))
    lost = [l for l in SERVO.splitlines() if l.strip().startswith("#") and l.strip() != L_NOTE_HEAD.strip() and l not in t.splitlines()]
    check(f"{tag}: every comment line survives but the removed note's own", not lost, lost)


def drawn(tag, page):
    """The dashboard as drawn from the saved text: Torque | Angle side by side at half width, Joint velocity a table."""
    m = page.evaluate(f"""() => {{
      const dash = document.querySelector('{D}');
      const grid = dash.querySelector('.dd-grid').getBoundingClientRect();
      const b = (sel) => {{ const e = dash.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect(); return {{ x: r.x, y: r.y, w: r.width, h: r.height }}; }};
      const byTitle = (t) => [...dash.querySelectorAll('.dd-panel')].find((s) => (s.querySelector('.dd-panel-h span') || {{}}).textContent === t);
      const jv = byTitle('Joint velocity');
      return {{ grid: grid.width, torque: b('.dd-panel[aria-label="Torque"]'), angle: b('.dd-panel[aria-label="Angle"]'),
               jvType: jv ? jv.dataset.type : null, jvTable: !!(jv && jv.querySelector('data-views table')), note: !!dash.querySelector('.dd-panel-text') }};
    }}""")
    t, a = m.get("torque"), m.get("angle")
    check(f"{tag}: drawn again, Torque sits left of Angle on one row", bool(t and a and abs(t["y"] - a["y"]) <= 2 and t["x"] < a["x"]), m)
    check(f"{tag}: drawn again, Torque and Angle are half width each", bool(t and a and 0.45 <= t["w"] / m["grid"] <= 0.52 and abs(t["w"] - a["w"]) <= 2), m)
    check(f"{tag}: drawn again, Joint velocity's panel is a table", m.get("jvType") == "table" and m.get("jvTable"), m)
    check(f"{tag}: drawn again, the Twin check note is gone", not m.get("note"))


def task(pages):
    tag = "the task"
    page = pages.open(PAGE)
    edit(page)
    shot(page, "task-1-editing")
    # add: a click on the queue's row
    r = rev(page)
    page.locator(Q("torque")).click()
    settle(page, r, "place Torque")
    page.wait_for_selector(P("torque"), timeout=WAIT)
    check(f"{tag}: a click on a queued item puts it on the grid and in the outline, with no reload", page.locator(ROW("torque")).count() == 1 and page.locator(Q("torque")).count() == 0)
    # move: the grid, by its grip
    drag_until(page, "torque", before="angle", label="move Torque above Angle")
    names = layout_names(text(page))
    check(f"{tag}: a drag puts Torque above Angle", names.index("Torque") + 1 == names.index("Angle"), names)
    shot(page, "task-2-moved")
    # half width: the east edge
    resize_to(page, "torque", 6)
    rows = panel_rows(page)
    check(f"{tag}: at half width, Torque and Angle share a row at once, as the file will draw them", ["torque", "angle"] in rows, rows)
    # remove: the options pane, from a click on the outline's row
    note = [p for p in row_order(page) if p.startswith("text-")]
    page.locator(ROW(note[0])).click()
    page.wait_for_selector(OPT("remove"), timeout=WAIT)
    r = rev(page)
    page.locator(OPT("remove")).click()
    settle(page, r, "remove the note")
    # rename and retype: a click on the panel itself selects it
    page.locator(P("velocity")).click(position={"x": 120, "y": 120})
    page.wait_for_selector(OPT("title"), timeout=WAIT)
    set_opt(page, "title", "Joint velocity")
    r = rev(page)
    page.locator(OPT("type-table")).click()
    settle(page, r, "show as a table")
    shot(page, "task-3-options")
    page.locator(BAR("edit-save")).click()
    page.wait_for_selector(f"{OPTIONS} .dde-diff", timeout=WAIT)
    check(f"{tag}: Save shows the diff first: the host has been handed nothing", not saves(page))
    shot(page, "task-4-diff")
    page.locator(OPT("save-go")).click()
    page.wait_for_function("() => window.host.saves.filter((s) => s.name === 'servo.base').length === 1", timeout=WAIT)
    page.wait_for_timeout(300)
    t = saves(page, "servo.base")[-1]["text"]
    outcome(tag, t)
    shelf = saves(page, "saved.base")
    check(f"{tag}: Torque left the queue's file when the dashboard was saved", len(shelf) == 1 and "name: Torque" not in shelf[-1]["text"] and "Twin q RMS by run" in shelf[-1]["text"], shelf[-1]["text"][-200:] if shelf else None)
    page.reload()
    ready(page)
    page.wait_for_selector(f'{D} .dd-panel[aria-label="Torque"]', timeout=WAIT)
    page.wait_for_timeout(600)
    drawn(tag, page)
    shot(page, "task-5-saved")
    page.context.close()


# ------------------------------------------------------------------------------------------------- the canvas (V1)

def canvas(pages):
    page = pages.open(PAGE)
    edit(page)
    keys = page.evaluate(f"() => [...document.querySelectorAll('{D} .dd-panel')].map((s) => s.dataset.panel)")
    missing = [k for k in keys if page.locator(GRIP(k)).count() != 1]
    check("canvas: every panel has a grip to drag by, the playback bar and the note too", len(keys) == 8 and not missing, missing)
    check("canvas: the panel's own ⋯ steps aside while editing", page.evaluate(f"""() => [...document.querySelectorAll('{D} .dd-panel-menu')].every((b) => !b.getClientRects().length)"""))
    # down the page: Playback under Angle and Velocity
    drag_until(page, "playback", after="velocity", label="move Playback down")
    want = SERVO.replace(L_PLAYBACK, "").replace(L_VELOCITY, L_VELOCITY + L_PLAYBACK)
    same_text("canvas: a drag down moves one line, every other byte stays", text(page), want)
    check("canvas: the moved panel's rows follow at once", ["angle", "velocity"] in panel_rows(page), panel_rows(page))
    # the east edge: 6 → 4, one number on one line, its comment kept
    resize_to(page, "angle", 4)
    want = want.replace(L_ANGLE, L_ANGLE.replace("w: 6", "w: 4"))
    same_text("canvas: a resize changes one number on one line, its trailing comment kept", text(page), want)
    a = rect(page, P("angle"))
    g = rect(page, f"{D} .dd-grid")
    check("canvas: the panel is 4 of 12 wide (getBoundingClientRect)", abs(a["w"] - g["w"] / 3) <= 3, {"panel": a["w"], "grid": g["w"]})
    plot = page.evaluate(f"""() => {{ const c = document.querySelector('{P("angle")} canvas'); return c ? c.getBoundingClientRect().width : null; }}""")
    check("canvas: the chart inside redraws to the panel's new width", plot is not None and plot <= a["w"] and plot >= a["w"] - 64, {"plot": plot, "panel": a["w"]})
    shot(page, "canvas-1")
    # Save, Exit: the canvas showed what the file draws
    before = panel_rows(page)
    page.locator(BAR("edit-save")).click()
    page.wait_for_selector(OPT("save-go"), timeout=WAIT)
    page.locator(OPT("save-go")).click()
    page.wait_for_function("() => window.host.saves.length >= 1", timeout=WAIT)
    page.wait_for_timeout(200)
    page.locator(BAR("edit-exit")).click()
    page.wait_for_function(f"() => !document.querySelector('{D}').hasAttribute('data-editing')", timeout=WAIT)
    page.wait_for_function(READY, timeout=WAIT)
    page.wait_for_timeout(300)
    after = panel_rows(page)
    check("canvas: the reading view draws the same rows the canvas showed after the drop", before == after, {"canvas": before, "reading": after})
    left = page.evaluate(f"() => document.querySelectorAll('{D} .dde-pane, {D} .grid-stack, {D} .dde-grip, .dv-splitter[aria-label*=\"outline\" i], .dv-splitter[aria-label*=\"options\" i]').length")
    check("canvas: Exit leaves no editing chrome behind", left == 0, left)
    page.context.close()
    # the block entry and the quoted key, from the options pane
    page = pages.open(PAGE)
    edit(page)
    page.locator(ROW("runs")).click()
    set_opt(page, "w", 8)
    want = SERVO.replace("      # a comment inside an entry stays with it\n" + L_RUNS_W, "      # a comment inside an entry stays with it\n      w: 8\n")
    same_text("canvas: a block entry changes on its own line; the comment inside it stays", text(page), want)
    page.locator(ROW("duration")).click()
    set_opt(page, "w", 3)
    want = want.replace(L_DURATION, L_DURATION.replace("w: 4", "w: 3"))
    same_text("canvas: a key quoted by hand keeps its quotes and the line its comment", text(page), want)
    page.context.close()


# ------------------------------------------------------------------------------------------------- the outline (V2)

def outline(pages):
    page = pages.open(PAGE)
    edit(page)
    want_keys = ["twin-q-rms", "duration", "logged-at", "runs", "playback", "angle", "velocity", "text-8"]
    check("outline: the layout as a tree, in the file's order", row_order(page) == want_keys, row_order(page))
    check("outline: a tree a screen reader can walk", page.locator(f'{OUTLINE} [role="tree"]').count() == 1 and page.locator(f'{OUTLINE} [role="treeitem"]').count() >= 8)
    panes = page.evaluate("() => [...document.querySelectorAll('[data-dde-pane]')].map((e) => e.dataset.ddePane).sort()")
    check("outline: the editor has two side panels, the outline and one options pane", panes == ["options", "outline"], panes)
    # the same state: a row dragged shows on the canvas at once, and the panels are not redrawn for it
    page.evaluate(f"() => {{ window.__angle = document.querySelector('{P('angle')} data-views'); }}")
    r = rev(page)
    h = rect(page, ROW("velocity"))["h"]
    page.locator(ROW("playback")).drag_to(page.locator(ROW("velocity")), target_position={"x": 60, "y": h - 3})
    settle(page, r, "reorder in the outline")
    want = SERVO.replace(L_PLAYBACK, "").replace(L_VELOCITY, L_VELOCITY + L_PLAYBACK)
    same_text("outline: a row dragged below another moves one line, every other byte stays", text(page), want)
    rows = panel_rows(page)
    check("outline: the canvas shows the new order at once", rows.index(["angle", "velocity"]) < rows.index(["playback"]), rows)
    check("outline: a layout edit does not redraw the panels (the same element still on the page)", page.evaluate("() => window.__angle.isConnected"))
    # the other way: a panel dragged on the canvas is in the outline's order at once
    drag_until(page, "runs", before="twin-q-rms", label="move Runs to the top")
    names = layout_names(text(page))
    check("outline: a drag on the canvas moves the row at once", row_order(page)[0] == "runs" and names[0] == "Runs", row_order(page))
    check("outline: still the same panels, not redrawn", page.evaluate("() => window.__angle.isConnected"))
    # selection, both ways, into the one pane
    page.locator(P("angle")).click(position={"x": 120, "y": 120})
    page.wait_for_selector(f'{ROW("angle")}[aria-selected="true"]', timeout=WAIT)
    check("outline: a click on a panel selects its row and fills the options pane", page.input_value(OPT("title")) == "Angle")
    page.locator(ROW("velocity")).click()
    page.wait_for_selector(f'{P("velocity")}[data-dde-selected]', timeout=WAIT)
    check("outline: a click on a row selects the panel on the canvas, and only it", page.locator(f"{D} .dd-panel[data-dde-selected]").count() == 1 and page.input_value(OPT("title")) == "Velocity")
    check("outline: still one options pane", page.locator(OPTIONS).count() == 1 and page.evaluate("() => document.querySelectorAll('[data-dde-pane]').length") == 2)
    # width both ways
    set_opt(page, "w", 4)
    v = rect(page, P("velocity"))
    g = rect(page, f"{D} .dd-grid")
    check("outline: Width in the options pane changes the panel on the canvas at once", abs(v["w"] - g["w"] / 3) <= 3, {"panel": v["w"], "grid": g["w"]})
    resize_to(page, "velocity", 8)
    check("outline: a resize on the canvas shows in the options pane at once", str(page.input_value(OPT("w"))) == "8", page.input_value(OPT("w")))
    page.context.close()
    # hide and show: an entry kept in place, one key, an exact inverse
    page = pages.open(PAGE)
    edit(page)
    r = rev(page)
    page.locator(ROW("angle")).hover()
    page.locator(f'{ROW("angle")} [data-dde-hide]').click()
    settle(page, r, "hide")
    hidden = SERVO.replace(L_ANGLE, L_ANGLE.replace("h: 3 }", "h: 3, hidden: true }"))
    same_text("outline: Hide writes one key on the entry and moves nothing", text(page), hidden)
    check("outline: a hidden panel leaves the canvas; its row stays in place, greyed", page.locator(P("angle")).count() == 0 and row_order(page)[5] == "angle" and page.locator(f'{ROW("angle")}[data-hidden]').count() == 1)
    js_ok, py_ok, out = checkers(text(page))
    check("outline: both checkers accept a hidden panel", js_ok and py_ok, out)
    r = rev(page)
    page.locator(ROW("angle")).hover()
    page.locator(f'{ROW("angle")} [data-dde-hide]').click()
    settle(page, r, "show")
    same_text("outline: Show is the exact inverse of Hide", text(page), SERVO)
    check("outline: the panel is back where it was, beside Velocity", ["angle", "velocity"] in panel_rows(page), panel_rows(page))
    check("outline: nothing to save after hide then show", page.locator(BAR("edit-save")).is_disabled())
    # group as tabs, and back
    r = rev(page)
    h = rect(page, ROW("angle"))["h"]
    page.locator(ROW("velocity")).drag_to(page.locator(ROW("angle")), target_position={"x": 60, "y": h / 2})
    settle(page, r, "group")
    grouped = SERVO.replace(L_ANGLE, L_ANGLE.replace("view: Angle", "views: [Angle, Velocity]")).replace(L_VELOCITY, "")
    same_text("outline: a row dropped onto another makes one panel of tabs, one line changed and one gone", text(page), grouped)
    page.wait_for_function(f"""() => document.querySelectorAll('{P("angle")} .dv-tab').length === 2""", timeout=WAIT)
    check("outline: the panel draws two tabs, and the row lists them", page.locator(f'{OUTLINE} .dde-row[data-tab]').count() == 2 and page.locator(P("velocity")).count() == 0)
    js_ok, py_ok, out = checkers(text(page))
    check("outline: both checkers accept the group", js_ok and py_ok, out)
    r = rev(page)
    page.locator(f'{OUTLINE} .dde-row[data-tab="Velocity"]').hover()
    page.locator(f'{OUTLINE} .dde-row[data-tab="Velocity"] [data-dde-ungroup]').click()
    settle(page, r, "ungroup")
    same_text("outline: taking a tab out is the exact inverse", text(page), SERVO)
    # what cannot be grouped is not offered: a text panel, another dataset
    r = rev(page)
    h = rect(page, ROW("text-8"))["h"]
    page.locator(ROW("runs")).drag_to(page.locator(ROW("angle")), target_position={"x": 60, "y": h / 2})
    page.wait_for_timeout(300)
    same = text(page) == SERVO or layout_names(text(page)).count("Runs") == 1
    check("outline: two datasets never become one panel's tabs", same and "views: [" not in text(page), layout_names(text(page)))
    page.context.close()


# ------------------------------------------------------------------------------------------------- the queue (V4, kept small)

def queue(pages):
    page = pages.open(PAGE)
    edit(page)
    items = page.evaluate(f"() => [...document.querySelectorAll('{OUTLINE} .dde-q')].map((e) => e.dataset.item)")
    check("queue: the list names what the host's queue file holds, in its order", items == ["torque", "twin-q-rms-by-run", "held-out-runs"], items)
    shot(page, "queue-1")
    # a drag onto a panel's top edge: before it
    a = rect(page, P("angle"))
    r = rev(page)
    page.locator(Q("torque")).drag_to(page.locator(P("angle")), target_position={"x": a["w"] / 2, "y": 6})
    settle(page, r, "drag from the queue")
    t = text(page)
    names = layout_names(t)
    check("queue: a drag onto a panel's top edge places the item before it", names.index("Torque") + 1 == names.index("Angle"), names)
    rem, add = changed(SERVO, t)
    check("queue: placing only adds lines", not rem, rem[:4])
    check("queue: the panel's line sits right above Angle's", "    - { view: Torque, h: 3 }\n" + L_ANGLE in t)
    check("queue: its dataset is found by file, not added twice", t[: t.index("layout:")] == SERVO[: SERVO.index("layout:")])
    check("queue: the placed item leaves the list", page.locator(Q("torque")).count() == 0)
    check("queue: nothing is written to the queue's file before Save", not saves(page))
    # Undo gives it back
    r = rev(page)
    page.locator(BAR("edit-undo")).click()
    settle(page, r, "undo")
    same_text("queue: Undo takes it off the dashboard to the byte", text(page), SERVO)
    check("queue: Undo puts it back in the list", page.locator(Q("torque")).count() == 1)
    # a click with a panel selected: right after it
    page.locator(ROW("logged-at")).click()
    r = rev(page)
    page.locator(Q("held-out-runs")).click()
    settle(page, r, "click to place")
    names = layout_names(text(page))
    check("queue: a click places the item right after the selected panel", names.index("Held-out runs") == names.index("Logged at") + 1, names)
    check("queue: the placed panel is selected, in the outline and the options pane", page.locator(f'{ROW("held-out-runs")}[aria-selected="true"]').count() == 1)
    page.wait_for_function(f"""() => {{ const v = document.querySelector('{P("held-out-runs")} data-views'); return v && v.dataset.view; }}""", timeout=WAIT)
    # another dataset of the same file, then Save: the queue's file loses exactly those items
    r = rev(page)
    page.locator(Q("twin-q-rms-by-run")).click()
    settle(page, r, "place the chart")
    page.locator(BAR("edit-save")).click()
    page.wait_for_selector(OPT("save-go"), timeout=WAIT)
    page.locator(OPT("save-go")).click()
    page.wait_for_function("() => window.host.saves.filter((s) => s.name === 'saved.base').length === 1", timeout=WAIT)
    names = [s["name"] for s in saves(page)]
    check("queue: the dashboard is saved first, then the queue's file", names == ["servo.base", "saved.base"], names)
    want = SAVED.replace("    - { view: Twin q RMS by run, h: 3 }\n    - { view: Held-out runs }\n", "")
    want = want[: want.index("  - type: chart\n")]
    got = saves(page, "saved.base")[-1]["text"]
    same_text("queue: the queue's file loses the placed items' lines and nothing else", got, want)
    js_ok, py_ok, out = checkers(got)
    check("queue: both checkers accept the queue's file after the drain", js_ok and py_ok, out)
    page.reload()
    ready(page)
    edit(page)
    items = page.evaluate(f"() => [...document.querySelectorAll('{OUTLINE} .dde-q')].map((e) => e.dataset.item)")
    check("queue: after a reload the list has only what is left", items == ["torque"], items)
    r = rev(page)
    page.locator(Q("torque")).click()
    settle(page, r, "place the last")
    check("queue: an empty list takes no room", page.locator(f"{OUTLINE} .dde-queue").count() == 0 or not page.locator(f"{OUTLINE} .dde-queue").is_visible())
    page.context.close()
    # no host, no queue, and the editor still works
    page = pages.open(PAGE + "?nohost=1")
    edit(page)
    check("queue: a host that lists no queue gets no list", page.locator(f"{OUTLINE} .dde-q").count() == 0)
    page.context.close()
    # filled by Add to dashboard: a panel's ⋯ in the reading view, the picker, the host saves; Edit lists it
    page = pages.open(PAGE)
    sec = page.locator(P("velocity"))
    sec.scroll_into_view_if_needed()
    sec.hover()
    sec.locator(".dd-panel-menu").first.click()
    sec.locator("[data-add-dashboard]").first.click()
    page.wait_for_selector('.dv-addpick [data-dashboard-id="saved"]', timeout=WAIT)
    page.locator('.dv-addpick [data-dashboard-id="saved"]').click()
    page.wait_for_selector('.dv-addpick-status[data-state="added"]', timeout=WAIT)
    check("queue: Add to dashboard… fills it through §34's picker: the host saved the queue's file", saves(page, "saved.base") and "name: Velocity" in saves(page, "saved.base")[-1]["text"])
    page.keyboard.press("Escape")
    edit(page)
    check("queue: Edit lists the item just added", page.locator(Q("velocity")).count() == 1, page.evaluate(f"() => [...document.querySelectorAll('{OUTLINE} .dde-q')].map((e) => e.dataset.item)"))
    r = rev(page)
    page.locator(Q("velocity")).click()
    settle(page, r, "place a view whose name is taken")
    js_ok, py_ok, out = checkers(text(page))
    check("queue: a view whose name is taken is placed under a new one, and both checkers accept it", js_ok and py_ok and "name: Velocity (2)" in text(page), out)
    page.context.close()


# ------------------------------------------------------------------------------------------------- saving

def save(pages):
    page = pages.open(PAGE)
    edit(page)
    check("save: nothing to save yet", page.locator(BAR("edit-save")).is_disabled())
    page.locator(ROW("angle")).click()
    set_opt(page, "w", 4)
    page.locator(BAR("edit-save")).click()
    page.wait_for_selector(f"{OPTIONS} .dde-diff", timeout=WAIT)
    want_rem, want_add = changed(SERVO, text(page))
    d = page.evaluate(f"""() => ({{ add: [...document.querySelectorAll('{OPTIONS} .dde-diff .dde-dadd')].map((e) => e.dataset.line), del: [...document.querySelectorAll('{OPTIONS} .dde-diff .dde-ddel')].map((e) => e.dataset.line) }})""")
    check("save: the diff is exactly the file's changed lines", d["add"] == want_add and d["del"] == want_rem, d)
    check("save: the review names the change in words", "Angle" in page.locator(f"{OPTIONS} .dde-changes").inner_text())
    check("save: the review is the one options pane, not a new one", page.evaluate("() => document.querySelectorAll('[data-dde-pane]').length") == 2)
    check("save: the host has been handed nothing", not saves(page))
    page.locator(OPT("save-back")).click()
    page.wait_for_selector(OPT("w"), timeout=WAIT)
    check("save: Back returns to the panel, its edit kept", str(page.input_value(OPT("w"))) == "4" and not page.locator(BAR("edit-save")).is_disabled())
    page.locator(BAR("edit-save")).click()
    page.wait_for_selector(OPT("save-go"), timeout=WAIT)
    page.fill(OPT("save-message"), "narrower angle plot")
    page.locator(OPT("save-go")).click()
    page.wait_for_function("() => window.host.saves.length === 1", timeout=WAIT)
    s = saves(page)[0]
    same_text("save: the host receives the draft to the byte", s["text"], SERVO.replace(L_ANGLE, L_ANGLE.replace("w: 6", "w: 4")))
    check("save: the event carries the text it replaces, the message, the changes and which file",
          s["before"] == SERVO and s["message"] == "narrower angle plot" and len(s["changes"]) >= 1 and s["dashboard"]["url"].endswith("servo.base"), {k: s[k] for k in ("message", "dashboard")})
    page.wait_for_function(f"""() => /saved/i.test(document.querySelector('{D} .dde-status').textContent)""", timeout=WAIT)
    check("save: still editing, nothing left to save", page.locator(f"{D}[data-editing]").count() == 1 and page.locator(BAR("edit-save")).is_disabled())
    page.locator(BAR("edit-exit")).click()
    page.wait_for_function(f"() => !document.querySelector('{D}').hasAttribute('data-editing')", timeout=WAIT)
    check("save: Exit after a save asks nothing", page.locator("dialog[open]").count() == 0)
    page.context.close()
    # the host's error: said, nothing lost
    page = pages.open(PAGE)
    edit(page)
    page.locator(ROW("angle")).click()
    set_opt(page, "w", 4)
    page.evaluate("() => { window.host.fail = 'the disk is full'; }")
    page.locator(BAR("edit-save")).click()
    page.wait_for_selector(OPT("save-go"), timeout=WAIT)
    page.locator(OPT("save-go")).click()
    page.wait_for_function(f"""() => /disk is full/.test(document.querySelector('{OPTIONS}').textContent)""", timeout=WAIT)
    check("save: a host's error is said and the draft stays", "w: 4" in text(page) and not page.locator(BAR("edit-save")).is_disabled() and page.locator(OPT("save-go")).count() == 1)
    page.context.close()
    # no host: the text on the clipboard, and it says so
    page = pages.open(PAGE + "?nohost=1", perms=["clipboard-read", "clipboard-write"])
    edit(page)
    page.locator(ROW("angle")).click()
    set_opt(page, "w", 4)
    page.locator(BAR("edit-save")).click()
    page.wait_for_selector(OPT("save-go"), timeout=WAIT)
    page.locator(OPT("save-go")).click()
    page.wait_for_function(f"""() => /clipboard/i.test(document.querySelector('{D} .dde-status').textContent)""", timeout=WAIT)
    same_text("save: with no host the text goes to the clipboard, as §34's does", page.evaluate("() => navigator.clipboard.readText()"), SERVO.replace(L_ANGLE, L_ANGLE.replace("w: 6", "w: 4")))
    page.context.close()
    # Save as copy: a new file, this one left alone
    page = pages.open(PAGE)
    edit(page)
    page.locator(ROW("angle")).click()
    set_opt(page, "w", 4)
    page.locator(BAR("edit-save")).click()
    page.wait_for_selector(OPT("save-copy"), timeout=WAIT)
    page.locator(OPT("save-copy")).click()
    page.fill(OPT("save-copy-title"), "Servo, my copy")
    page.locator(OPT("save-copy")).click()
    page.wait_for_function("() => window.host.saves.some((s) => s.name === 'servo-my-copy.base')", timeout=WAIT)
    check("save: Save as copy hands the host a new file and leaves this one alone", not saves(page, "servo.base") and saves(page, "servo-my-copy.base")[0]["asCopy"]["title"] == "Servo, my copy")
    page.context.close()
    # Exit's question, undo and redo
    page = pages.open(PAGE)
    edit(page)
    page.locator(ROW("angle")).click()
    set_opt(page, "w", 4)
    page.locator(BAR("edit-exit")).click()
    page.wait_for_selector("dialog.dde-dialog[open]", timeout=WAIT)
    shot(page, "save-exit-dialog")
    page.locator('dialog.dde-dialog [data-dde="cancel"]').click()
    check("save: Cancel in Exit's question keeps editing and the draft", page.locator(f"{D}[data-editing]").count() == 1 and "w: 4" in text(page))
    page.keyboard.press("Control+z")
    page.wait_for_function(f"() => document.querySelector('{D}').baseText.includes('{L_ANGLE.strip()}')", timeout=WAIT)
    same_text("save: Ctrl+Z restores the text to the byte", text(page), SERVO)
    page.keyboard.press("Control+Shift+z")
    page.wait_for_function(f"() => document.querySelector('{D}').baseText.includes('w: 4, h: 3')", timeout=WAIT)
    check("save: Ctrl+Shift+Z brings it back", True)
    page.locator(BAR("edit-exit")).click()
    page.wait_for_selector("dialog.dde-dialog[open]", timeout=WAIT)
    page.locator('dialog.dde-dialog [data-dde="discard"]').click()
    page.wait_for_function(f"() => !document.querySelector('{D}').hasAttribute('data-editing')", timeout=WAIT)
    page.wait_for_function(READY, timeout=WAIT)
    page.wait_for_timeout(300)
    same_text("save: Discard goes back to the file", text(page), SERVO)
    got = page.evaluate(MEASURE)
    check("save: after Discard the page is the golden's panels again", got["panels"] == GOLDEN["1280"]["panels"], got["panels"][:2])
    page.context.close()
    # the file moved underneath: said at review; reload() keeps the draft
    page = pages.open(PAGE)
    edit(page)
    page.locator(ROW("angle")).click()
    set_opt(page, "w", 4)
    draft = text(page)
    page.evaluate("() => document.querySelector('#servo').reload()")
    page.wait_for_timeout(600)
    same_text("save: reload() while editing keeps the draft", text(page), draft)
    check("save: reload() leaves the editor on", page.locator(f"{D}[data-editing] {OUTLINE}").count() == 1 and page.locator(P("angle")).count() == 1)
    page.evaluate("(t) => window.host.put('servo.base', t)", SERVO + "# a line an agent added while you were editing\n")
    page.locator(BAR("edit-save")).click()
    page.wait_for_selector(".dde-moved", timeout=WAIT)
    check("save: a file that changed since Edit is said before anything is replaced", "changed" in page.locator(".dde-moved").inner_text().lower() and not saves(page))
    page.context.close()


# ------------------------------------------------------------------------------------------------- every side panel

def side_widths(page, side):
    return page.evaluate(f"""() => document.querySelector('[data-dde-pane="{side}"]').getBoundingClientRect().width""")


def panes(pages):
    page = pages.open(PAGE)
    edit(page)
    # WHY read from the page: a side panel added later is measured here without a word changed
    sides = page.evaluate("() => [...document.querySelectorAll('[data-dde-pane]')].map((e) => e.dataset.ddePane)")
    check("panes: found on the page", set(sides) >= {"outline", "options"}, sides)
    every = page.evaluate("""() => [...document.querySelectorAll('[data-dde-pane]')].map((e) => ({ side: e.dataset.ddePane, handle: !!(e.nextElementSibling && e.nextElementSibling.matches('.dv-splitter')), fold: !!e.querySelector('button.dde-fold') }))""")
    check("panes: every side panel has a boundary to drag and a fold button", all(p["handle"] and p["fold"] for p in every), every)
    widths = {}
    for side in sides:
        before = side_widths(page, side)
        main = rect(page, f"{D} .dd-main")["w"]
        h = page.locator(f'[data-dde-pane="{side}"] + .dv-splitter')
        b = h.bounding_box()
        edge = page.evaluate(f"""() => document.querySelector('[data-dde-pane="{side}"]').nextElementSibling.classList.contains('dv-splitter-left') ? -1 : 1""")
        page.mouse.move(b["x"] + b["width"] / 2, b["y"] + 40)
        page.mouse.down()
        page.mouse.move(b["x"] + b["width"] / 2 + 60 * edge, b["y"] + 40, steps=6)
        page.mouse.up()
        page.wait_for_timeout(120)
        after = side_widths(page, side)
        check(f"panes: the {side} boundary drags 60 px wider (getBoundingClientRect)", abs((after - before) - 60) <= 3, {"before": before, "after": after})
        now = rect(page, f"{D} .dd-main")["w"]
        check(f"panes: the grid gives the {side} panel that room", abs((main - now) - 60) <= 4, {"before": main, "after": now})
        widths[side] = after
    page.reload()
    ready(page)
    edit(page)
    for side in sides:
        kept = side_widths(page, side)
        check(f"panes: the {side} panel keeps its width after a reload", abs(kept - widths[side]) <= 2, {"want": widths[side], "kept": kept})
    for side in sides:
        h = page.locator(f'[data-dde-pane="{side}"] + .dv-splitter')
        h.focus()
        before = side_widths(page, side)
        out = page.evaluate(f"""() => document.querySelector('[data-dde-pane="{side}"]').nextElementSibling.classList.contains('dv-splitter-left') ? 'ArrowLeft' : 'ArrowRight'""")
        page.keyboard.press(out)
        page.wait_for_timeout(60)
        check(f"panes: an arrow key on the {side} boundary moves it 16 px", abs(side_widths(page, side) - before - 16) <= 1, side_widths(page, side) - before)
        b = h.bounding_box()
        page.mouse.dblclick(b["x"] + b["width"] / 2, b["y"] + 40)
        page.wait_for_timeout(120)
        reset = side_widths(page, side)
        check(f"panes: a double-click resets the {side} panel to its default", abs(reset - before) > 20 or reset < before, {"reset": reset, "was": before})
    # fold: a click, a remembered state, a measured gain
    for side in sides:
        before = side_widths(page, side)
        main = rect(page, f"{D} .dd-main")["w"]
        page.locator(f'[data-dde-pane="{side}"] button.dde-fold').click()
        page.wait_for_function(f"""() => document.querySelector('[data-dde-pane="{side}"]').hasAttribute('data-folded')""", timeout=WAIT)
        page.wait_for_timeout(150)
        folded = side_widths(page, side)
        grew = rect(page, f"{D} .dd-main")["w"] - main
        check(f"panes: the {side} panel folds to a strip and the grid gets the room", folded <= 40 and abs(grew - (before - folded)) <= 6, {"folded": folded, "grew": grew})
        check(f"panes: a folded {side} panel has no boundary to drag", not page.locator(f'[data-dde-pane="{side}"] + .dv-splitter').is_visible())
        check(f"panes: its fold button says so", page.get_attribute(f'[data-dde-pane="{side}"] button.dde-fold', "aria-expanded") == "false")
    shot(page, "panes-folded")
    page.reload()
    ready(page)
    edit(page)
    for side in sides:
        check(f"panes: the {side} panel stays folded after a reload", page.locator(f'[data-dde-pane="{side}"][data-folded]').count() == 1)
        page.locator(f'[data-dde-pane="{side}"] button.dde-fold').click()
        page.wait_for_function(f"""() => !document.querySelector('[data-dde-pane="{side}"]').hasAttribute('data-folded')""", timeout=WAIT)
        page.wait_for_timeout(100)
        check(f"panes: the {side} panel unfolds to its width", side_widths(page, side) >= 180, side_widths(page, side))
    # the keyboard commands (VS Code's)
    page.keyboard.press("Control+b")
    page.wait_for_function(f"""() => document.querySelector('{OUTLINE}').hasAttribute('data-folded')""", timeout=WAIT)
    page.keyboard.press("Control+b")
    page.wait_for_function(f"""() => !document.querySelector('{OUTLINE}').hasAttribute('data-folded')""", timeout=WAIT)
    page.keyboard.press("Control+Alt+b")
    page.wait_for_function(f"""() => document.querySelector('{OPTIONS}').hasAttribute('data-folded')""", timeout=WAIT)
    page.keyboard.press("Control+Alt+b")
    page.wait_for_function(f"""() => !document.querySelector('{OPTIONS}').hasAttribute('data-folded')""", timeout=WAIT)
    check("panes: Ctrl+B folds the outline and Ctrl+Alt+B the options pane, and back", True)
    # the filter rail: a side panel of the dashboard, folded while editing and one press away
    check("panes: the filter rail steps aside while editing", not page.locator(f"{D} .dd-rail").is_visible())
    page.locator(BAR("edit-filters")).click()
    page.wait_for_selector(f"{D} .dd-rail", state="visible", timeout=WAIT)
    page.wait_for_timeout(150)
    rail = page.locator(f"{D} .dd-rail + .dv-splitter")
    before = rect(page, f"{D} .dd-rail")["w"]
    b = rail.bounding_box()
    page.mouse.move(b["x"] + b["width"] / 2, b["y"] + 40)
    page.mouse.down()
    page.mouse.move(b["x"] + b["width"] / 2 + 40, b["y"] + 40, steps=6)
    page.mouse.up()
    page.wait_for_timeout(120)
    check("panes: the rail's boundary drags while editing", abs(rect(page, f"{D} .dd-rail")["w"] - before - 40) <= 3, {"before": before, "after": rect(page, f"{D} .dd-rail")["w"]})
    page.locator(BAR("edit-filters")).click()
    page.wait_for_selector(f"{D} .dd-rail", state="hidden", timeout=WAIT)
    check("panes: the rail folds again", True)
    page.context.close()


# ------------------------------------------------------------------------------------------------- the keyboard alone

def keyboard(pages):
    page = pages.open(PAGE)
    page.evaluate("() => document.querySelector('#servo').focus()")
    reached = False
    for _ in range(80):
        page.keyboard.press("Tab")
        if page.evaluate("""() => { const a = document.activeElement; return !!(a && a.dataset && a.dataset.act === 'edit'); }"""):
            reached = True
            break
    check("keyboard: Tab reaches Edit", reached)
    page.keyboard.press("Enter")
    page.wait_for_selector(f"{D}[data-editing] {OUTLINE}", timeout=WAIT)
    page.wait_for_function(READY, timeout=WAIT)
    page.wait_for_timeout(300)
    check("keyboard: Enter on Edit puts focus in the outline", page.evaluate("() => !!document.activeElement.closest('.dde-tree')"))
    page.keyboard.press("ArrowDown")
    page.wait_for_selector(f'{ROW("twin-q-rms")}[aria-selected="true"]', timeout=WAIT)
    page.keyboard.press("ArrowDown")
    page.wait_for_selector(f'{ROW("duration")}[aria-selected="true"]', timeout=WAIT)
    check("keyboard: ↓ walks the rows and the options pane follows", page.input_value(OPT("title")) == "Duration")
    r = rev(page)
    page.keyboard.press("Alt+ArrowUp")
    settle(page, r, "Alt+↑")
    same_text("keyboard: Alt+↑ moves the panel up one row, to the byte", text(page), SERVO.replace(L_TWIN + L_DURATION, L_DURATION + L_TWIN))
    check("keyboard: focus stays on the moved row", page.evaluate("() => document.activeElement.dataset.key") == "duration")
    r = rev(page)
    page.keyboard.press("Control+z")
    settle(page, r, "undo")
    same_text("keyboard: Ctrl+Z from the outline undoes it", text(page), SERVO)
    # Tab out of the tree to the queue: Enter places
    for _ in range(8):
        page.keyboard.press("Tab")
        if page.evaluate("() => document.activeElement.classList.contains('dde-q')"):
            break
    check("keyboard: Tab goes from the tree to the queue", page.evaluate("() => document.activeElement.classList.contains('dde-q')"))
    r = rev(page)
    page.keyboard.press("Enter")
    settle(page, r, "place by Enter")
    check("keyboard: Enter on a queued item places it", "view: Torque" in text(page))
    page.keyboard.press("Control+s")
    page.wait_for_selector(OPT("save-go"), timeout=WAIT)
    check("keyboard: Ctrl+S opens the review; it never saves blind", not saves(page))
    check("keyboard: focus lands in the review", page.evaluate(f"() => !!document.activeElement.closest('{OPTIONS}')"))
    page.keyboard.press("Escape")
    page.wait_for_selector(OPT("save-go"), state="detached", timeout=WAIT)
    check("keyboard: Escape leaves the review", True)
    page.keyboard.press("Control+s")
    page.wait_for_selector(OPT("save-go"), timeout=WAIT)
    for _ in range(12):
        if page.evaluate("() => document.activeElement.dataset && document.activeElement.dataset.dde === 'save-go'"):
            break
        page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.host.saves.length >= 1", timeout=WAIT)
    check("keyboard: Tab and Enter reach Save", saves(page, "servo.base") and "view: Torque" in saves(page, "servo.base")[0]["text"])
    page.context.close()


# ------------------------------------------------------------------------------------------------- themes and the phone

SCROLL = "() => document.scrollingElement.scrollWidth"


def themes(pages):
    for dark in (False, True):
        tag = "dark" if dark else "light"
        page = pages.open(PAGE, dark=dark)
        edit(page)
        page.locator(ROW("angle")).click()
        page.wait_for_selector(OPT("title"), timeout=WAIT)
        m = page.evaluate(f"""() => {{
          const lum = (c) => {{ const p = document.createElement('canvas').getContext('2d'); p.fillStyle = c; p.fillRect(0, 0, 1, 1); const [r, g, b] = p.getImageData(0, 0, 1, 1).data; return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255; }};
          const out = {{}};
          for (const s of ['{OUTLINE}', '{OPTIONS}']) {{ const e = document.querySelector(s); const c = getComputedStyle(e); out[s] = {{ bg: lum(c.backgroundColor), fg: lum(c.color) }}; }}
          return out; }}""")
        ok = all((v["bg"] < 0.3 and v["fg"] > 0.6) if dark else (v["bg"] > 0.7 and v["fg"] < 0.4) for v in m.values())
        check(f"themes {tag}: the panes follow the theme, legibly", ok, m)
        shot(page, f"themes-{tag}-1280")
        check(f"themes {tag}, 1280 px: no sideways page scroll while editing", page.evaluate(SCROLL) <= 1280, page.evaluate(SCROLL))
        page.locator(BAR("edit-add")).click()
        page.wait_for_selector(".dde-menu", timeout=WAIT)
        page.keyboard.press("Escape")
        page.context.close()
        size = (390, 844)
        page = pages.open(PAGE, dark=dark, size=size, mobile=True)
        check(f"themes {tag}, 390 px: no sideways scroll reading", page.evaluate(SCROLL) <= 390, page.evaluate(SCROLL))
        edit(page, grid=False)
        check(f"themes {tag}, 390 px: the panes start folded, so the dashboard stays the main thing", page.locator(f"{OUTLINE}[data-folded]").count() == 1 and page.locator(f"{OPTIONS}[data-folded]").count() == 1)
        check(f"themes {tag}, 390 px: no sideways scroll editing", page.evaluate(SCROLL) <= 390, page.evaluate(SCROLL))
        page.locator(f"{OUTLINE} button.dde-fold").click()
        page.wait_for_selector(ROW("angle"), timeout=WAIT)
        page.wait_for_timeout(120)
        w = rect(page, OUTLINE)["w"]
        check(f"themes {tag}, 390 px: the outline opens full width, in the page", w >= 320 and w <= 390 and page.evaluate(SCROLL) <= 390, {"w": w, "scroll": page.evaluate(SCROLL)})
        page.locator(ROW("angle")).click()
        page.locator(f"{OPTIONS} button.dde-fold").click()
        page.wait_for_selector(OPT("up"), timeout=WAIT)
        r = rev(page)
        page.locator(OPT("up")).click()
        settle(page, r, "move up on a phone")
        check(f"themes {tag}, 390 px: Move up reorders with no drag", layout_names(text(page)).index("Angle") == 4, layout_names(text(page)))
        check(f"themes {tag}, 390 px: no sideways scroll with both panes open", page.evaluate(SCROLL) <= 390, page.evaluate(SCROLL))
        shot(page, f"themes-{tag}-390")
        page.locator(BAR("edit-save")).click()
        page.wait_for_selector(OPT("save-go"), timeout=WAIT)
        page.wait_for_timeout(120)
        check(f"themes {tag}, 390 px: the diff fits, no sideways page scroll", page.evaluate(SCROLL) <= 390, page.evaluate(SCROLL))
        shot(page, f"themes-{tag}-390-review")
        page.context.close()


# ------------------------------------------------------------------------------------------------- the gallery case

def gallery(pages):
    path = "/dist/site/gallery/robotics-servo/index.html"
    ctx = pages.browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light", reduced_motion="reduce")
    page = ctx.new_page()
    page.on("pageerror", lambda e: pages.errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    page.goto(pages.base + path)
    page.wait_for_selector('#example[data-view="dashboard"] [data-act="edit"]', timeout=WAIT)
    page.wait_for_timeout(600)
    page.locator('#example [data-act="edit"]').click()
    page.wait_for_selector(f"#example[data-editing] {OUTLINE}", timeout=WAIT)
    page.wait_for_selector("#example .dd-grid.grid-stack .dd-panel.grid-stack-item", timeout=WAIT)
    page.wait_for_timeout(500)
    items = page.locator(f"{OUTLINE} .dde-q").count()
    check("gallery: the Servo case opts in: Edit, the outline and a queue from the case's own host", items >= 1, items)
    rows = page.locator(f"{OUTLINE} .dde-row[data-key]").count()
    drawn_now = page.evaluate("() => document.querySelector('#example').dash.panels.length")
    check("gallery: the outline lists the template's panels", rows == drawn_now and rows >= 8, rows)
    r = page.evaluate("() => +(document.querySelector('#example').dataset.ddeRev || 0)")
    first = page.evaluate(f"() => document.querySelector('{OUTLINE} .dde-row[data-key]').dataset.key")
    page.locator(f'{OUTLINE} .dde-row[data-key="{first}"]').click()
    page.locator(f'{OUTLINE} .dde-q').first.click()
    page.wait_for_function(f"() => +(document.querySelector('#example').dataset.ddeRev || 0) > {r}", timeout=WAIT)
    page.wait_for_timeout(200)
    page.locator('#example [data-act="edit-save"]').click()
    page.wait_for_selector(OPT("save-go"), timeout=WAIT)
    page.locator(OPT("save-go")).click()
    page.wait_for_function("""() => /saved/i.test(document.querySelector('#example .dde-status').textContent)""", timeout=WAIT)
    page.screenshot(path=str(OUT / "gallery.png"))
    page.reload()
    page.wait_for_selector('#example[data-view="dashboard"] [data-act="edit"]', timeout=WAIT)
    page.wait_for_timeout(300)
    now = page.evaluate("() => document.querySelector('#example').dash.panels.length")
    check("gallery: what was saved is drawn after a reload (the page's host keeps it)", now == drawn_now + 1, {"before": drawn_now, "after": now})
    ctx.close()


# ------------------------------------------------------------------------------------------------- run

def main() -> int:
    if not (ROOT / "dist" / "dashboard.js").exists():
        print("the kit is not built: npm run build")
        return 1
    proc, base = serve(ROOT, PAGE)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            pages = Pages(browser, base)
            for name, journey in (("today", today), ("the task", task), ("canvas", canvas), ("outline", outline), ("queue", queue),
                                  ("save", save), ("panes", panes), ("keyboard", keyboard), ("themes", themes), ("gallery", gallery)):
                with guard(name):
                    journey(pages)
            check("no page errors in any journey", not pages.errors, pages.errors[:3])
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    (OUT / "dash-editor-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"\n{len(checks) - len(failed)} of {len(checks)} checks pass")
    return 1 if failed or not checks else 0


if __name__ == "__main__":
    sys.exit(main())
