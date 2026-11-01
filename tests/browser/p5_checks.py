"""PEP 0010 P5 (docs/peps/0010-robotics-playback.md §10, §11 P5; docs/CONTRACT.md §35): the diagnostics and gates
overlay, measured in headless Chromium on the built site and on tests/browser/fixtures/p5/. Written red, before the
code; never edited after.

    ~/psu-atlas/.venv/bin/python tests/browser/p5_checks.py [OUT_DIR]     # after npm run build

The six "Playback + Gates" twins (gallery/examples/robotics-<part>-gates, CONTRACT §35): each one's views.base holds every
dataset and view of its template (robotics-<part>) unchanged, plus gate datasets its source/ writes (PEP 0010 §10's
diagnostic rows) and the overlay's views. What is measured, against oracles computed here from the cases' own files:

  files     each twin: README (use case Robotics · Playback + Gates, App, Replaces, a Data bullet saying real or
            stand-in), a producer in source/, every dataset, view, link and panel of its template unchanged (the seam is a
            file diff), gate rows carrying §10's columns with the vocabulary's words, RobotDx's ranks and a basis of
            data-ui's, stand-in rows said in the README, every evidence link's #t / #tr its row's window to 3 decimals,
            and at most 5 MB of its own files.
  matrix    every gate matrix (a tracker with `column:`) of every twin, light and dark, 1280 and 390 px: a header cell per
            column whose text is the column's value as labelled, in order (the `columns:` asked for, then as the rows
            first show them); each column's cells within 0.5 px of its header's left and right edges in every row;
            every cell a visible glyph (the vocabulary's) and aria-label "<row> · <column>: <word>"; each cell's state the
            worst of the rows the panel holds for it (n/a where none), in its tone; no sideways page scroll. The
            deployments twin's Stations × gates against its gate file itself, cell by cell.
  status    every `display: status` cell of every twin's tables: a glyph and its word, in the vocabulary's tone.
  evidence  one cell per twin (and the deployments twin on a phone, dark): a click opens the side peek on that row (its
            record id); the peek's evidence link is the row's evidence URL resolved against its data file; each section
            view embedded in the peek draws exactly the rows its bound filter keeps; the link lands the page on the
            row's run with the clock at t = t0 and the range [t0, t1] (the link's 3 decimals, the row's window), spanning
            that run's own t.
  limits    every limits panel (timeseries.limits) whose rows hold two devices with different limits: on a run of each,
            every limit rule is that device's own value and sits at the y scale's image of it within 1 px, and each
            zone's limit edge too. At least one such panel, in the deployments twin.
  rollup    the deployments twin's tree table over a rolled-up dataset: each node's status (data-state and word) is the
            worst rank of the gate rows under it (oracle: its files).
  kpi       every KPI view with a spark and a target: the headline's history draws exactly its rows' (x, y) in x order,
            and a target rule at the target's y within 1 px. At least one, in the servo twin.
  live      tests/browser/fixtures/p5/p5.html: the deployments twin's Run checks view, its entry unchanged, fed a keyed
            LiveDataset (CONTRACT §26) of RobotDx's windowed rows (its live_checks.json): following, after more rows,
            and paused back at an earlier t, every cell is the newest version per key as of t.
  fixture   tests/fixtures/p5/gates.base on the same page: the live plot's plotView.guides hold each device's own error
            limits; the gate matrix's peek embeds its two section views, each drawing exactly its bound rows.
  path      the arm twin's path overlay (trajectory3d color + tolerance): every painted segment's colour on the ramp
            series 1 → warn at its value (OKLab, within 0.03 of the ramp), the ends exact; the tube's rings centred on the
            target's path at the tolerance.
  voxels    the arm twin's verdict voxels: the ramp's ends are the bad and good tones, every cell's colour its value's,
            ✕ and ✓ on the bar.
  looks     each twin, light and dark at 1280 and 390 px: every panel drawn, no sideways page scroll, no page error; a
            screenshot of each.
Screenshots go to OUT_DIR (default reports/media/robotics-p5).

Serves dist/site and the repo root on free 127.0.0.1 ports, stops them when done, writes OUT_DIR/p5-checks.json and
exits 1 if any check fails. A part that cannot be measured is one failing check in its own words, never a silent pass.
"""

from __future__ import annotations

import contextlib
import csv
import json
import math
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "core" / "python"))
import data_ui_base  # noqa: E402  the stdlib .base reader, the Python twin of base.js

OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "robotics-p5"
OUT.mkdir(parents=True, exist_ok=True)
SITE = ROOT / "dist" / "site"
EX = ROOT / "gallery" / "examples"
PAGE = "/tests/browser/fixtures/p5/p5.html"
CHECKER_BASE = "/tests/fixtures/p5/gates.base"
CHECKER_FIX = ROOT / "tests" / "fixtures" / "p5"
TWINS = {
    "robotics-servo-gates": "robotics-servo",
    "robotics-driver-gates": "robotics-driver",
    "robotics-camera-gates": "robotics-camera",
    "robotics-arm-gates": "robotics-arm",
    "robotics-arm-gripper-gates": "robotics-arm-gripper",
    "robotics-deployments-gates": "robotics-deployments",
}
DEPLOY = "robotics-deployments-gates"
LOOKS = ((1280, False), (1280, True), (390, False), (390, True))
WAIT = 45000                 # ms: a ceiling for a state to arrive on a loaded machine, not a pause
BUDGET = 5 * 1024 * 1024     # bytes a case publishes of its own (every file but source/)
D = "#example"

# the vocabulary (CONTRACT §35), written out here as the oracle
STATUS = {"pass": ("good", "✓"), "ok": ("good", "✓"), "warn": ("warn", "!"), "warning": ("warn", "!"), "partial": ("warn", "!"),
          "fail": ("bad", "✕"), "error": ("bad", "✕"), "not_run": ("muted", "–"), "not run": ("muted", "–"), "unknown": ("muted", "?"),
          "stale": ("muted", "◷")}
ORDER = ["ok", "pass", "warn", "warning", "partial", "unknown", "not_run", "not run", "stale", "error", "fail"]
TONE_GLYPH = {"good": "✓", "warn": "!", "bad": "✕", "muted": "–", "neutral": "•"}
TONES = ("good", "warn", "bad", "muted", "neutral")
RANK = {"pass": 0, "ok": 0, "warn": 1, "warning": 1, "partial": 1, "not_run": 2, "not run": 2, "unknown": 2, "stale": 3, "fail": 4, "error": 4}
BASIS = ("measured", "datasheet", "seller", "derived", "estimate", "assumed", "chosen", "sampled", "stand-in", "claimed")
HINTS = ("gate_matrix", "threshold_band", "kpi_trend", "rollup_tree", "evidence", "distribution", "level_history", "path_overlay")

checks: list[dict] = []


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str, ensure_ascii=False)[:600]}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    """A part that cannot run (a case missing, nothing drawn, a page that never settles) is one failing check."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:500]}")


# ------------------------------------------------------------------------------------------------- values and words
def cellv(v):
    return v.get("value") if isinstance(v, dict) and "value" in v else v


def empty(v):
    return v is None or v == "" or (isinstance(v, list) and not v)


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def js_str(v):
    """JavaScript's String(v) for a scalar cell: 4.0 is '4', True is 'true'."""
    v = cellv(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def status_of(value, tones=None, column=None):
    """The vocabulary's reading of a value: {word, tone, glyph}. The view's map, then the column's, then the list."""
    v = cellv(value)
    if empty(v):
        return {"word": "no value", "tone": "muted", "glyph": "–"}
    column = column or {}
    labels = column.get("labels") or {}
    key = js_str(v)
    word = str(labels[key]) if key in labels else key
    base = STATUS.get(key) or STATUS.get(word)
    tone = None
    for m in (tones or {}, column.get("tones") or {}):
        if key in m and m[key] in TONES:
            tone = m[key]
            break
    if tone is None:
        tone = base[0] if base else "neutral"
    glyph = base[1] if base and base[0] == tone else TONE_GLYPH[tone]
    return {"word": word, "tone": tone, "glyph": glyph}


def worst(values, order=None):
    order = order or ORDER
    best, rank = None, -2
    for v in values:
        v = cellv(v)
        if empty(v):
            continue
        r = order.index(js_str(v)) if js_str(v) in order else -1
        if r > rank:
            best, rank = v, r
    return best


def label_of(value, column, none_label):
    """A group's or a column's text (groupLabel): its label, else the value; a missing one "No <property>"."""
    if empty(value):
        return f"No {none_label.lower()}"
    labels = (column or {}).get("labels") or {}
    key = js_str(value)
    return str(labels[key]) if key in labels else key


# ------------------------------------------------------------------------------------------------- the files
def base_of(case):
    return data_ui_base.loads((EX / case / "views.base").read_text(encoding="utf-8"))


def views_of(base):
    return [v for v in base.get("views") or [] if isinstance(v, dict)]


def data_spec(base, name):
    d = (base.get("datasets") or {}).get(name)
    if isinstance(d, str):
        return {"data": d}
    return d if isinstance(d, dict) else None


def default_name(base):
    for name, d in (base.get("datasets") or {}).items():
        spec = {"data": d} if isinstance(d, str) else d
        if isinstance(spec, dict) and spec.get("data") == base.get("data"):
            return name
    return pathlib.PurePosixPath(str(base.get("data"))).stem


def resolved(case, rel):
    """A path in a case's .base as a path under gallery/examples (../robotics-servo/samples.json → robotics-servo/samples.json)."""
    return str(pathlib.PurePosixPath(urllib.parse.urljoin(f"/{case}/", rel)).relative_to("/"))


def load_table(path):
    """(rows, fields): a JSON dataset (runtime shape, a field schema, or a bare list) or a CSV with its sidecar."""
    path = pathlib.Path(path)
    if path.suffix == ".csv":
        side = json.loads(path.with_suffix(".schema.json").read_text(encoding="utf-8"))
        flist = side["schema"]["fields"]
        types = {f["name"]: f.get("type") for f in flist}
        rows = []
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows.append({k: (None if v == "" else float(v) if types.get(k) in ("number", "integer") else v) for k, v in r.items()})
        return rows, {f["name"]: {"label": f.get("title") or f["name"], "labels": f.get("labels"), "tones": f.get("tones")} for f in flist}
    doc = json.loads(path.read_text(encoding="utf-8"))
    # A descriptor ({path: samples.csv, schema}, as the camera's clock dataset is) names its file; read that file
    # (orchestrator fix: the frozen form read the descriptor as an empty table, so its span came back null).
    if isinstance(doc, dict) and doc.get("path") and "rows" not in doc:
        return load_table(path.parent / doc["path"])
    if isinstance(doc, list):
        return doc, {}
    rows = doc.get("rows") or []
    if isinstance(doc.get("schema"), dict):
        fields = {f["name"]: {"label": f.get("title") or f["name"], "labels": f.get("labels"), "tones": f.get("tones")} for f in doc["schema"].get("fields") or []}
    else:
        fields = {k: {"label": (p or {}).get("label") or k, "labels": (p or {}).get("labels"), "tones": (p or {}).get("tones")} for k, p in (doc.get("properties") or {}).items()}
    return rows, fields


def rows_of(case, base, name, values=None):
    """A dataset of a case's .base as (rows, fields); a per-pick template filled with `values`."""
    spec = data_spec(base, name)
    rel = spec["data"] if spec else base["data"]
    if values:
        for k, v in values.items():
            rel = rel.replace("{" + k + "}", urllib.parse.quote(str(v), safe=""))
    if "{" in rel:
        return [], {}
    return load_table(EX / resolved(case, rel))


CLAUSE = re.compile(r'^\s*([A-Za-z_][\w]*)\s*(==|!=|>=|<=|>|<)\s*("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[eE]-?\d+)?|true|false|null)\s*$')


def compile_filter(filters):
    """A view's filters as a predicate, for the forms the twins write: clauses `col op literal` joined by && (a string),
    a list of them, or {and: [...]}. Anything else raises: the oracle cannot be computed, which is a failing check."""
    if filters is None:
        return lambda r: True
    if isinstance(filters, list):
        parts = [compile_filter(f) for f in filters]
        return lambda r: all(p(r) for p in parts)
    if isinstance(filters, dict) and set(filters) == {"and"}:
        return compile_filter(filters["and"])
    if not isinstance(filters, str):
        raise ValueError(f"filter form not read here: {filters!r}")
    clauses = []
    for raw in split_and(filters):
        m = CLAUSE.match(raw)
        if not m:
            raise ValueError(f"filter clause not read here: {raw!r}")
        col, op, lit = m.groups()
        val = json.loads(lit)
        clauses.append((col, op, val))

    def test(r):
        for col, op, val in clauses:
            x = cellv(r.get(col))
            if op == "==" and not same(x, val):
                return False
            if op == "!=" and same(x, val):
                return False
            if op in (">=", "<=", ">", "<"):
                if not (num(x) and num(val)):
                    return False
                if not {">=": x >= val, "<=": x <= val, ">": x > val, "<": x < val}[op]:
                    return False
        return True
    return test


def same(a, b):
    if num(a) and num(b):
        return a == b
    if a is None or b is None:
        return a is None and b is None
    return js_str(a) == js_str(b)


def split_and(text):
    out, cur, q, i = [], "", None, 0
    while i < len(text):
        c = text[i]
        if q:
            cur += c
            if c == "\\" and i + 1 < len(text):
                cur += text[i + 1]
                i += 2
                continue
            if c == q:
                q = None
        elif c in "\"'":
            q = c
            cur += c
        elif text.startswith("&&", i):
            out.append(cur)
            cur = ""
            i += 2
            continue
        else:
            cur += c
        i += 1
    out.append(cur)
    return [x for x in out if x.strip()]


def bind_this(filters, row):
    """`this.<column>` in a filter, bound to a row's values (the analyses' rule, CONTRACT §19 and §35)."""
    def lit(v):
        v = cellv(v)
        return "null" if v is None else json.dumps(v) if isinstance(v, str) else ("true" if v is True else "false" if v is False else repr(v))
    if isinstance(filters, str):
        return re.sub(r'(?<![\w.])this\.([A-Za-z_][\w-]*)', lambda m: lit(row.get(m.group(1))), filters)
    if isinstance(filters, list):
        return [bind_this(f, row) for f in filters]
    if isinstance(filters, dict):
        return {k: bind_this(v, row) for k, v in filters.items()}
    return filters


def fragment(url):
    """{t, tr} from a link's fragment (#t=a&tr=a,b)."""
    frag = urllib.parse.urlparse(url).fragment
    q = urllib.parse.parse_qs(frag)
    t = float(q["t"][0]) if "t" in q else None
    tr = [float(x) for x in q["tr"][0].split(",")] if "tr" in q else None
    return t, tr


def readme_bullets(text):
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^- \*\*([^*]+):\*\* (.+)$", text, re.M)}


def published_bytes(case):
    total = 0
    for p in (EX / case).rglob("*"):
        rel = p.relative_to(EX / case)
        if p.is_file() and rel.parts[0] != "source" and not rel.parts[0].startswith("."):
            total += p.stat().st_size
    return total


def matrix_views(base):
    return [v for v in views_of(base) if v.get("type") == "tracker" and isinstance(v.get("tracker"), dict) and v["tracker"].get("column")]


def diagnostic_datasets(case, base, tmpl):
    """The twin's own datasets whose rows are diagnostic rows (they carry a hint)."""
    out = []
    for name in base.get("datasets") or {}:
        if name in (tmpl.get("datasets") or {}):
            continue
        try:
            rows, fields = rows_of(case, base, name)
        except Exception:  # noqa: BLE001 -- a per-pick or unreadable file is not a diagnostic table here
            continue
        if rows and all(isinstance(r, dict) and "hint" in r for r in rows):
            out.append((name, rows, fields))
    return out


def files():
    for case, template in TWINS.items():
        with guard(f"{case}: the files"):
            here = EX / case
            check(f"{case}: the twin exists (README.md, views.base)", (here / "README.md").exists() and (here / "views.base").exists(), str(here))
            readme = (here / "README.md").read_text(encoding="utf-8")
            bullets = readme_bullets(readme)
            check(f"{case}: README files it under '- **Use case:** Robotics · Playback + Gates', with App, Replaces and Data bullets",
                  re.search(r"^- \*\*Use case:\*\* Robotics · Playback \+ Gates$", readme, re.M) is not None and all(bullets.get(k) for k in ("App", "Replaces", "Data")),
                  {k: bullets.get(k, "")[:80] for k in ("Use case", "App", "Replaces", "Data")})
            producers = sorted(p.name for p in (here / "source").glob("*.py")) if (here / "source").is_dir() else []
            check(f"{case}: a producer in source/ writes its gate rows", producers, producers)
            base, tmpl = base_of(case), base_of(template)
            # the seam is a file diff: every dataset, view, link and panel of the template, unchanged
            bad = []
            if resolved(case, str(base.get("data"))) != resolved(template, str(tmpl.get("data"))):
                bad.append({"data": [base.get("data"), tmpl.get("data")]})
            for name, d in (tmpl.get("datasets") or {}).items():
                a, b = data_spec(tmpl, name), data_spec(base, name)
                if not b:
                    bad.append({"dataset missing": name})
                    continue
                if resolved(template, a["data"]) != resolved(case, b["data"]) or {k: v for k, v in a.items() if k != "data"} != {k: v for k, v in b.items() if k != "data"}:
                    bad.append({"dataset differs": name})
            tviews = {v.get("name"): v for v in views_of(base)}
            for v in views_of(tmpl):
                if tviews.get(v.get("name")) != v:
                    bad.append({"view differs or is missing": v.get("name")})
            for link in tmpl.get("links") or []:
                if link not in (base.get("links") or []):
                    bad.append({"link missing": link})
            names = lambda b: {n for p in ((b.get("layout") or {}).get("panels") or []) if isinstance(p, dict) for n in (p.get("views") or ([p["view"]] if p.get("view") else []))}  # noqa: E731
            missing = names(tmpl) - names(base)
            if missing:
                bad.append({"panels missing": sorted(missing)})
            if tmpl.get("clock") != base.get("clock"):
                bad.append({"clock": [tmpl.get("clock"), base.get("clock")]})
            for k, v in (tmpl.get("style") or {}).items():
                if (base.get("style") or {}).get(k) != v:
                    bad.append({"style": k})
            check(f"{case}: every dataset, view, link and panel of {template} is in it unchanged (the seam is a file diff)", not bad, bad[:4])
            # the gate rows: PEP 0010 §10's columns
            diag = diagnostic_datasets(case, base, tmpl)
            check(f"{case}: at least one gate dataset of diagnostic rows (each row a hint)", diag, [n for n, _, _ in diag])
            stand_in = False
            for name, rows, _f in diag:
                wrong = []
                for r in rows:
                    word = cellv(r.get("verdict")) if "verdict" in r else cellv(r.get("level"))
                    title = cellv(r.get("title")) if "title" in r else cellv(r.get("gate"))
                    if empty(cellv(r.get("subject"))) or empty(title) or js_str(word) not in STATUS:
                        wrong.append({"row": r.get("id"), "subject/title/word": [cellv(r.get("subject")), title, word]})
                    elif cellv(r.get("rank")) != RANK[js_str(word)]:
                        wrong.append({"row": r.get("id"), "rank": cellv(r.get("rank")), "word": word})
                    elif cellv(r.get("hint")) not in HINTS or cellv(r.get("basis")) not in BASIS or empty(cellv(r.get("source"))):
                        wrong.append({"row": r.get("id"), "hint/basis/source": [cellv(r.get("hint")), cellv(r.get("basis")), cellv(r.get("source"))]})
                    if cellv(r.get("basis")) == "stand-in":
                        stand_in = True
                check(f"{case}: {name}'s {len(rows)} rows carry PEP 0010 §10's columns: subject, a title, a vocabulary word (verdict or level) with RobotDx's rank, a hint, a basis of data-ui's and a source",
                      not wrong, wrong[:3])
                ev_bad, n_ev = [], 0
                for r in rows:
                    ev = cellv(r.get("evidence"))
                    if not isinstance(ev, str) or "#" not in ev or not num(cellv(r.get("t0"))) or not num(cellv(r.get("t1"))):
                        continue
                    n_ev += 1
                    t, tr = fragment(ev)
                    t0, t1 = cellv(r["t0"]), cellv(r["t1"])
                    if t is None or tr is None or abs(t - t0) > 5e-4 or abs(tr[0] - t0) > 5e-4 or abs(tr[1] - t1) > 5e-4:
                        ev_bad.append({"row": r.get("id"), "link": ev, "window": [t0, t1]})
                if n_ev:
                    check(f"{case}: {name}: each of the {n_ev} evidence links' #t and #tr are its row's window (t0; t0, t1) to 3 decimals", not ev_bad, ev_bad[:3])
            said = bullets.get("Data", "").lower()
            check(f"{case}: the README's Data bullet says what the gate rows are ({'stand-in' if stand_in else 'real'})",
                  ("stand-in" in said) if stand_in else ("real" in said), bullets.get("Data", "")[:160])
            size = published_bytes(case)
            check(f"{case}: it publishes at most 5 MB of its own ({size / 1e6:.2f} MB)", size <= BUDGET, size)


# ------------------------------------------------------------------------------------------------- the server and pages
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


SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 80))))"
READY = """() => { const d = document.querySelector('#example'); if (!d || !d.dash) return false;
  const els = [...d.querySelectorAll('.dd-panel data-views')]; return els.length > 0 && els.every((e) => e.dataset.view); }"""
# the panel whose current view is `name`: its key
PANEL = """(name) => { for (const s of document.querySelectorAll('#example .dd-panel[data-panel]')) { const e = s.querySelector(':scope > data-views');
  if (e && e.view && e.view.name === name) return s.dataset.panel; } return null; }"""
CV = "const cv = (x) => (x && typeof x === 'object' && !Array.isArray(x) && 'value' in x ? x.value : x);"
# a gate matrix as drawn, and the rows its panel holds (the view's own model)
MATRIX = r"""([root, name]) => { const R = document.querySelector(root); if (!R) return null;
  const s = [...R.querySelectorAll('.dd-panel[data-panel]')].find((x) => { const e = x.querySelector(':scope > data-views'); return e && e.view && e.view.name === name; });
  if (!s) return null; const el = s.querySelector(':scope > data-views'); const g = s.querySelector('[role=grid]'); const m = el.model; const v = el.view;
  const cv = (x) => (x && typeof x === 'object' && !Array.isArray(x) && 'value' in x ? x.value : x);
  const tr = v.tracker || {}; const gb = v.groupBy && v.groupBy.property;
  const col = (p) => (p && m && m.columns[p] ? { label: m.columns[p].label || p, labels: m.columns[p].labels || null, tones: m.columns[p].tones || null } : null);
  const pick = (r) => ({ id: String(r.id), state: cv(r[tr.state]) ?? null, column: cv(r[tr.column]) ?? null });
  const groups = !m ? [] : m.groups && m.groups.length ? m.groups.map((x) => ({ key: x.key ?? null, rows: x.rows.map(pick) })) : [{ key: null, rows: m.rows.map(pick) }];
  const box = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.right, r.top, r.bottom]; };
  const out = { panel: s.dataset.panel, tracker: JSON.parse(JSON.stringify(tr)), groupBy: gb || null, cols: { group: col(gb), column: col(tr.column), state: col(tr.state) },
    groups, grid: !!g, sw: document.scrollingElement.scrollWidth, vw: innerWidth };
  if (!g) return out;
  out.heads = [...g.querySelectorAll('[role=columnheader][data-column]')].map((h) => ({ column: h.dataset.column, text: h.textContent.trim(), box: box(h) }));
  out.rows = [...g.querySelectorAll('[role=row]')].filter((r) => r.querySelector('[role=gridcell]')).map((r) => { const rh = r.querySelector('[role=rowheader]');
    return { label: rh ? rh.textContent.trim() : '', cells: [...r.querySelectorAll('[role=gridcell]')].map((c) => { const gl = c.querySelector('.dv-tracker-glyph'); const gs = gl ? getComputedStyle(gl) : null;
      return { column: c.dataset.column ?? null, state: c.hasAttribute('data-state') ? c.dataset.state : null, na: c.hasAttribute('data-na'), id: c.dataset.id ?? null,
        aria: c.getAttribute('aria-label'), tone: (c.className.match(/dv-tone-(\w+)/) || [])[1] || null, glyph: gl ? gl.textContent : null,
        glyphW: gl ? gl.getBoundingClientRect().width : 0, glyphShown: !!gs && gs.display !== 'none' && gs.visibility !== 'hidden' && Number(gs.opacity) > 0, box: box(c) }; }) }; });
  return out; }"""
# every status cell of a table view: its stored value, glyph, word and tone, and the column's labels and tones
STATUS_CELLS = r"""([root, name]) => { const R = document.querySelector(root);
  const s = [...R.querySelectorAll('.dd-panel[data-panel]')].find((x) => { const e = x.querySelector(':scope > data-views'); return e && e.view && e.view.name === name; });
  if (!s) return null; const el = s.querySelector(':scope > data-views'); const m = el.model;
  const cols = {}; for (const [k, c] of Object.entries((m && m.columns) || {})) cols[k] = { labels: c.labels || null, tones: c.tones || null };
  return { cols, cells: [...s.querySelectorAll('td.dv-d-status')].map((td) => ({ col: td.dataset.col, badges: [...td.querySelectorAll('.dv-state')].map((b) => ({
    state: b.dataset.state, tone: (b.className.match(/dv-tone-(\w+)/) || [])[1] || null, glyph: (b.querySelector('.dv-state-glyph') || {}).textContent ?? null,
    hidden: (b.querySelector('.dv-state-glyph') || { getAttribute: () => null }).getAttribute('aria-hidden'), word: (b.querySelector('.dv-state-word') || {}).textContent ?? null })),
    none: !!td.querySelector('.dv-none') })) }; }"""


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


def wait_ready(page):
    page.wait_for_selector(f"{D} .dd-panel[data-panel]", timeout=WAIT)
    page.wait_for_function(READY, timeout=WAIT)
    settle(page, 3)


def open_case(browser, base, case, *, width=1280, dark=False, url=None):
    page = new_page(browser, width, dark)
    page.goto(url or f"{base}/gallery/{case}/index.html")
    ok = True
    try:
        wait_ready(page)
    except Exception:  # noqa: BLE001 -- the check that reads the state says so
        ok = False
    return page, ok


def scroll_panel(page, name):
    key = page.evaluate(PANEL, name)
    if key:
        with contextlib.suppress(Exception):
            page.locator(f"{D} .dd-panel[data-panel='{key}']").scroll_into_view_if_needed(timeout=5000)
            settle(page, 2)
    return key


def shot(page, name, selector=D):
    try:
        page.evaluate("(s) => { const d = document.querySelector(s); if (d) window.scrollTo(0, d.getBoundingClientRect().top + window.scrollY - 60); }", selector)
        settle(page)
        page.locator(selector).first.screenshot(path=str(OUT / f"{name}.png"))
    except Exception as e:  # noqa: BLE001 -- a missing picture is not a failed behaviour; say so
        print(f"(screenshot {name} not taken: {e})")


def tag(case, width, dark):
    return f"{case}, {width} px, {'dark' if dark else 'light'}"


# ------------------------------------------------------------------------------------------------- the matrix
def matrix_oracle(got):
    """The matrix the panel's rows make: columns (asked for, then first shown, null last) and per group the worst state."""
    tr = got["tracker"]
    asked = [js_str(c) for c in (tr.get("columns") or [])]
    cols = list(asked)
    has_null = False
    for g in got["groups"]:
        for r in g["rows"]:
            if empty(r["column"]):
                has_null = True
            elif js_str(r["column"]) not in cols:
                cols.append(js_str(r["column"]))
    if has_null:
        cols.append(None)
    order = tr.get("order") or ORDER
    out = []
    for g in got["groups"]:
        cells = []
        for c in cols:
            rs = [r for r in g["rows"] if (c is None and empty(r["column"])) or (c is not None and not empty(r["column"]) and js_str(r["column"]) == c)]
            cells.append({"column": c, "na": not rs, "n": len(rs), "state": worst([r["state"] for r in rs], order) if rs else None, "ids": [r["id"] for r in rs]})
        out.append({"key": g["key"], "cells": cells})
    return cols, out


def measure_matrix(page, case, view, look, root=D):
    """Every matrix check on one drawn matrix. Returns the drawn matrix (or None)."""
    name = view["name"]
    got = page.evaluate(MATRIX, [root, name])
    t = f"{look}: matrix '{name}'"
    if not got or not got.get("grid"):
        check(f"{t}: drawn as a grid ([role=grid])", False, got and {k: got.get(k) for k in ("panel", "grid")})
        return None
    cols, want = matrix_oracle(got)
    cc, gc = got["cols"]["column"] or {"label": view["tracker"]["column"]}, got["cols"]["group"] or {"label": got.get("groupBy") or ""}
    col_text = [label_of(c, cc, cc["label"]) for c in cols]
    heads = got.get("heads") or []
    check(f"{t}: the header text equals the column titles, in order ({len(cols)}: {', '.join(col_text[:4])}{'…' if len(cols) > 4 else ''})",
          [h["text"] for h in heads] == col_text and [h["column"] for h in heads] == [c or "" for c in cols],
          {"drawn": [h["text"] for h in heads][:12], "want": col_text[:12]})
    rows = got.get("rows") or []
    # alignment: each column's cells share its header's left and right edges, in every row, within 0.5 px
    worst_off, where = 0.0, None
    for r in rows:
        for j, c in enumerate(r["cells"]):
            if j >= len(heads):
                worst_off, where = 999.0, {"row": r["label"], "extra cell": j}
                continue
            off = max(abs(c["box"][0] - heads[j]["box"][0]), abs(c["box"][1] - heads[j]["box"][1]))
            if off > worst_off:
                worst_off, where = off, {"row": r["label"], "column": heads[j]["text"], "cell": c["box"][:2], "header": heads[j]["box"][:2]}
    check(f"{t}: gate columns align within 0.5 px across rows ({len(rows)} rows × {len(heads)} columns; worst {worst_off:.3f} px)",
          rows and heads and worst_off <= 0.5 and all(len(r["cells"]) == len(heads) for r in rows), where)
    # every cell: a visible glyph and an accessible name; its state, n/a and tone the oracle's
    tones = (got["tracker"] or {}).get("tones") or {}
    sc = got["cols"]["state"] or {}
    bad_name, bad_state = [], []
    if len(rows) != len(want):
        bad_state.append({"rows drawn": len(rows), "groups": len(want)})
    for r, w in zip(rows, want):
        rl = label_of(w["key"], gc, gc["label"]) if got.get("groupBy") else ""
        if r["label"] != rl:
            bad_state.append({"row header": r["label"], "want": rl})
        for c, wc, ct in zip(r["cells"], w["cells"], col_text):
            st = status_of(wc["state"], tones, sc) if not wc["na"] else {"word": "n/a", "tone": "muted", "glyph": "–"}
            word = st["word"] + (f", worst of {wc['n']} rows" if wc["n"] > 1 else "")
            aria = " · ".join(x for x in (rl, ct) if x) + ": " + word
            if c["aria"] != aria or c["glyph"] != st["glyph"] or not (c["glyphW"] > 0 and c["glyphShown"]):
                bad_name.append({"row": rl, "column": ct, "aria": c["aria"], "want": aria, "glyph": c["glyph"], "want glyph": st["glyph"], "w": c["glyphW"], "shown": c["glyphShown"]})
            want_state = "" if wc["na"] or empty(wc["state"]) else js_str(wc["state"])
            if c["na"] != wc["na"] or (c["state"] or "") != want_state or c["tone"] != st["tone"] or (wc["n"] == 1 and c["id"] != wc["ids"][0]):
                bad_state.append({"row": rl, "column": ct, "drawn": [c["state"], c["na"], c["tone"], c["id"]], "want": [want_state, wc["na"], st["tone"], wc["ids"][:2]]})
    n = sum(len(r["cells"]) for r in rows)
    check(f"{t}: every cell ({n}) has a visible glyph and an accessible name '<row> · <column>: <word>'", rows and not bad_name, bad_name[:3])
    check(f"{t}: every cell is the worst state of the rows the panel holds for it (n/a where none), in its tone", rows and not bad_state, bad_state[:3])
    return got


def deploy_gate_file(page, look):
    """The deployments twin's Stations × gates against its gate file itself, cell by cell."""
    base = base_of(DEPLOY)
    view = next((v for v in matrix_views(base) if v.get("name") == "Stations × gates"), None)
    check(f"{look}: the deployments twin has the mock's 'Stations × gates' matrix", view is not None)
    if not view:
        return
    rows, fields = rows_of(DEPLOY, base, view.get("from") or default_name(base))
    rows = [r for r in rows if compile_filter(view.get("filters"))(r)]
    gb, tr = view["groupBy"]["property"], view["tracker"]
    file_cells = {}
    for r in rows:
        file_cells.setdefault((js_str(r[gb]), js_str(r[tr["column"]])), []).append(cellv(r[tr["state"]]))
    got = page.evaluate(MATRIX, [D, view["name"]]) or {}
    gc = (got.get("cols") or {}).get("group") or {"label": gb}
    cc = (got.get("cols") or {}).get("column") or {"label": tr["column"]}
    drawn = {}
    heads = [h["column"] for h in got.get("heads") or []]
    for r in got.get("rows") or []:
        for c, col in zip(r["cells"], heads):
            drawn[(r["label"], col)] = c["state"] if not c["na"] else None
    bad = []
    for (dev, col), states in file_cells.items():
        key = (label_of(dev, gc, gc["label"]), col)
        want = js_str(worst(states, tr.get("order")))
        if drawn.get(key) != want:
            bad.append({"cell": key, "drawn": drawn.get(key), "file": want})
    devices = {d for d, _ in file_cells}
    check(f"{look}: Stations × gates is the gate file, cell by cell ({len(file_cells)} cells, {len(devices)} stations × {len({c for _, c in file_cells})} gates)",
          file_cells and not bad and len(devices) >= 2, bad[:4] or {"cells": len(file_cells)})


def status_cells(page, case, look):
    base = base_of(case)
    for v in views_of(base):
        if v.get("type", "table") != "table" or "status" not in (v.get("display") or {}).values():
            continue
        scroll_panel(page, v["name"])
        got = page.evaluate(STATUS_CELLS, [D, v["name"]]) or {}
        bad, n = [], 0
        for c in got.get("cells") or []:
            col = (got.get("cols") or {}).get(c["col"]) or {}
            for b in c["badges"]:
                n += 1
                st = status_of(b["state"], None, col)
                if b["glyph"] != st["glyph"] or b["word"] != st["word"] or b["tone"] != st["tone"] or b["hidden"] != "true":
                    bad.append({"col": c["col"], "drawn": [b["state"], b["glyph"], b["word"], b["tone"], b["hidden"]], "want": [st["glyph"], st["word"], st["tone"]]})
            if not c["badges"] and not c["none"]:
                bad.append({"col": c["col"], "empty cell without the dash": True})
        check(f"{look}: table '{v['name']}': every status cell ({n} badges) shows its glyph (hidden from readers) and its word, in the vocabulary's tone", n and not bad, bad[:3])


def matrices(browser, base):
    for case in TWINS:
        with guard(f"{case}: the matrices"):
            b = base_of(case)
            mats = matrix_views(b)
            check(f"{case}: at least one gate matrix (a tracker with column:)", mats, [v.get("name") for v in mats])
            for width, dark in LOOKS:
                look = tag(case, width, dark)
                page, ok = open_case(browser, base, case, width=width, dark=dark)
                try:
                    check(f"{look}: every panel drew", ok)
                    for v in mats:
                        scroll_panel(page, v["name"])
                        with contextlib.suppress(Exception):
                            page.wait_for_function("([r, n]) => { const R = document.querySelector(r); return !!R && [...R.querySelectorAll('.dd-panel')].some((s) => { const e = s.querySelector(':scope > data-views'); return e && e.view && e.view.name === n && s.querySelector('[role=grid] [role=gridcell]'); }); }",
                                                   arg=[D, v["name"]], timeout=WAIT)
                        measure_matrix(page, case, v, look)
                    if case == DEPLOY:
                        deploy_gate_file(page, look)
                    status_cells(page, case, look)
                    sw = page.evaluate("() => document.scrollingElement.scrollWidth")
                    check(f"{look}: the page never scrolls sideways", sw <= width, sw)
                    page.evaluate("() => window.scrollTo(0, 0)")
                    shot(page, f"{case.removeprefix('robotics-')}-{'dark' if dark else 'light'}-{width}")
                    if mats:
                        key = scroll_panel(page, mats[0]["name"])
                        if key:
                            shot(page, f"{case.removeprefix('robotics-')}-matrix-{'dark' if dark else 'light'}-{width}", f"{D} .dd-panel[data-panel='{key}']")
                    check(f"{look}: no page error", not page.errors, page.errors[:3])
                finally:
                    page.context.close()


# ------------------------------------------------------------------------------------------------- the peek and its evidence
CLOCK = """() => { const d = document.querySelector('#example'); const c = d && d.clock; if (!c) return null;
  return { t: c.t, range: c.range ? [c.range[0], c.range[1]] : null, start: c.start, end: c.end }; }"""
PEEK = r"""() => { const p = document.querySelector('#example .dd-drill .dv-peek'); if (!p || p.hidden) return null;
  const rec = p.querySelector('.dv-open-rec'); const a = p.querySelector('a.dv-peek-link');
  return { id: rec ? rec.dataset.id : null, link: a ? a.href : null, linkText: a ? a.textContent : null,
    sections: [...p.querySelectorAll('.dv-peek-view[data-section]')].map((s) => { const e = s.querySelector('data-views'); const m = e && e.model;
      return { name: s.dataset.section, drawn: !!(e && e.dataset.view), matched: m ? m.matched : null, total: m ? m.total : null, ids: m ? m.rows.map((r) => String(r.id)) : null }; }) }; }"""


def section_oracle(case, base, view, section, row):
    """The rows a section's embedded view keeps: its dataset's file rows passing its filters bound to the row."""
    sv = section["view"]
    ds = sv.get("from") or view.get("from") or default_name(base)
    rows, _f = rows_of(case, base, ds)
    keep = compile_filter(bind_this(sv.get("filters"), row))
    return [r for r in rows if keep(r)]


def evidence_case(browser, base, case, *, width=1280, dark=False):
    b = base_of(case)
    look = tag(case, width, dark)
    target = None
    for v in matrix_views(b):
        ds = v.get("from") or default_name(b)
        rows, _f = rows_of(case, b, ds)
        keep = compile_filter(v.get("filters"))
        cand = [r for r in rows if keep(r) and isinstance(cellv(r.get("evidence")), str) and "#" in cellv(r["evidence"]) and num(cellv(r.get("t0"))) and num(cellv(r.get("t1")))]
        if cand:
            target = (v, ds, cand)
            break
    check(f"{look}: a gate matrix whose rows carry evidence windows", target is not None)
    if not target:
        return
    view, ds, cand = target
    page, ok = open_case(browser, base, case, width=width, dark=dark)
    try:
        key = scroll_panel(page, view["name"])
        page.wait_for_function("([r, n]) => [...document.querySelectorAll(r + ' .dd-panel')].some((s) => { const e = s.querySelector(':scope > data-views'); return e && e.view && e.view.name === n && s.querySelector('[role=gridcell][data-id]'); })",
                               arg=[D, view["name"]], timeout=WAIT)
        ids = page.evaluate("([k]) => [...document.querySelectorAll(`#example .dd-panel[data-panel='${k}'] [role=gridcell][data-id]`)].map((c) => c.dataset.id)", [key])
        by_id = {str(r.get("id")): r for r in cand}
        pick = next((i for i in ids if i in by_id), None)
        check(f"{look}: a drawn single-row cell whose row has an evidence window", pick is not None, {"drawn ids": ids[:5]})
        if pick is None:
            return
        row = by_id[pick]
        cell = page.locator(f"{D} .dd-panel[data-panel='{key}'] [role=gridcell][data-id='{pick}']").first
        cell.scroll_into_view_if_needed()
        cell.click()
        with contextlib.suppress(Exception):
            page.wait_for_function("(id) => { const p = document.querySelector('#example .dd-drill .dv-peek'); const r = p && !p.hidden && p.querySelector('.dv-open-rec'); return !!r && r.dataset.id === id; }", arg=pick, timeout=WAIT)
        settle(page, 3)
        peek = page.evaluate(PEEK) or {}
        check(f"{look}: a cell click opens the side peek on that gate row ({pick})", peek.get("id") == pick, peek.get("id"))
        file_url = urllib.parse.urljoin(f"{base}/gallery/{case}/", data_spec(b, ds)["data"] if data_spec(b, ds) else b["data"])
        want_link = urllib.parse.urljoin(file_url, cellv(row["evidence"]))
        check(f"{look}: the peek's evidence link is the row's evidence URL, resolved against its data file", peek.get("link") == want_link, {"drawn": peek.get("link"), "want": want_link})
        # the section views embedded in the peek: each draws exactly its bound rows
        for sec in ((view.get("record") or {}).get("sections") or []):
            if not isinstance(sec, dict) or not isinstance(sec.get("view"), dict):
                continue
            with contextlib.suppress(Exception):
                page.wait_for_function("(n) => { const s = document.querySelector(`#example .dd-drill .dv-peek .dv-peek-view[data-section='${n}'] data-views`); return !!s && !!s.dataset.view && !!s.model; }", arg=sec["name"], timeout=WAIT)
            peek = page.evaluate(PEEK) or {}
            got = next((s for s in peek.get("sections") or [] if s["name"] == sec["name"]), None)
            try:
                want = section_oracle(case, b, view, sec, row)
                err = None
            except Exception as e:  # noqa: BLE001
                want, err = [], str(e)
            check(f"{look}: the peek's '{sec['name']}' section embeds its view, which keeps exactly the {len(want)} rows its filter bound to this row keeps",
                  err is None and got and got["drawn"] and got["matched"] == len(want) and len(want) > 0, {"drawn": got and {k: got.get(k) for k in ("drawn", "matched", "total")}, "want": len(want), "error": err})
        shot(page, f"{case.removeprefix('robotics-')}-peek-{'dark' if dark else 'light'}-{width}")
        # the link lands on the window
        link = peek.get("link")
        if not link:
            check(f"{look}: the evidence link lands on its window", False, "no link in the peek")
            return
        t, tr = fragment(link)
        t0, t1 = cellv(row["t0"]), cellv(row["t1"])
        before = urllib.parse.urlparse(page.url)
        after = urllib.parse.urlparse(link)
        link_el = page.locator(f"{D} .dd-drill .dv-peek a.dv-peek-link").first
        if (before.path, before.query) != (after.path, after.query):
            # another document (the rail's run param changed): wait for it, then for its panels
            with page.expect_navigation(timeout=WAIT):
                link_el.click()
            with contextlib.suppress(Exception):
                wait_ready(page)
        else:
            link_el.click()
        with contextlib.suppress(Exception):
            page.wait_for_function("([t, a, b]) => { const c = document.querySelector('#example') && document.querySelector('#example').clock; return !!c && Math.abs(c.t - t) <= 5e-4 && !!c.range && Math.abs(c.range[0] - a) <= 5e-4 && Math.abs(c.range[1] - b) <= 5e-4; }",
                                   arg=[t, tr[0], tr[1]], timeout=WAIT)
        settle(page, 3)
        c = page.evaluate(CLOCK) or {}
        run = cellv(row.get("run"))
        clock = b.get("clock") or {}
        crows, _f = rows_of(case, b, clock.get("data"), {"run": run}) if clock.get("data") else ([], {})
        tcol = clock.get("time") or "t"
        ts = [cellv(r.get(tcol)) for r in crows if (cellv(r.get("run")) == run or "run" not in r) and num(cellv(r.get(tcol)))]
        span = [min(ts), max(ts)] if ts else None
        ok_t = c.get("t") is not None and t is not None and abs(c["t"] - t) <= 5e-4 and abs(t - t0) <= 5e-4
        ok_r = c.get("range") and tr and abs(c["range"][0] - tr[0]) <= 5e-4 and abs(c["range"][1] - tr[1]) <= 5e-4 and abs(tr[0] - t0) <= 5e-4 and abs(tr[1] - t1) <= 5e-4
        ok_s = span is not None and c.get("start") is not None and abs(c["start"] - span[0]) <= 1e-6 and abs(c["end"] - span[1]) <= 1e-6
        check(f"{look}: its evidence link lands on #t / #tr equal to the window: t = {t0:.3f}, range [{t0:.3f}, {t1:.3f}], on run {run}'s own span",
              ok_t and ok_r and ok_s, {"clock": c, "link": [t, tr], "window": [t0, t1], "run span": span})
        shot(page, f"{case.removeprefix('robotics-')}-landed-{'dark' if dark else 'light'}-{width}")
        check(f"{look}: evidence: no page error", not page.errors, page.errors[:3])
    finally:
        page.context.close()


def evidence(browser, base):
    for case in TWINS:
        with guard(f"{case}: the peek and its evidence"):
            evidence_case(browser, base, case)
    with guard(f"{DEPLOY}: the peek and its evidence on a phone"):
        evidence_case(browser, base, DEPLOY, width=390, dark=True)


# ------------------------------------------------------------------------------------------------- limits
GUIDES = """(name) => { const s = [...document.querySelectorAll('#example .dd-panel[data-panel]')].find((x) => { const e = x.querySelector(':scope > data-views'); return e && e.view && e.view.name === name; });
  const t = s && s.querySelector('.dv-view-timeseries'); const view = t && t.vegaView; if (!view) return null;
  let data = null; try { data = view.data('guides'); } catch (e) { return { missing: String(e) }; }
  const y = view.scale('y'); const items = [];
  const walk = (n) => { if (!n) return; for (const i of n.items || []) { if (i.datum && typeof i.datum.guide === 'string' && /^(limit|zone):/.test(i.datum.guide)) items.push({ mark: n.marktype, guide: i.datum.guide, series: i.datum.series ?? null, value: i.datum.value ?? null, lo: i.datum.lo ?? null, hi: i.datum.hi ?? null, y: i.y ?? null, y2: i.y2 ?? null }); if (i.items) walk(i); } };
  walk(view.scenegraph().root);
  return { data: data.map((d) => ({ guide: d.guide, series: d.series ?? null, x: d.x, value: d.value ?? null, lo: d.lo ?? null, hi: d.hi ?? null })),
    items: items.map((i) => ({ ...i, yv: i.value !== null ? y(i.value) : null, ylo: i.lo !== null ? y(i.lo) : null, yhi: i.hi !== null ? y(i.hi) : null })) }; }"""


def limit_oracle(rows, lim, series_col):
    """{series: {bound: value}} for property and number ends (constant per series in the twins)."""
    out = {}
    for r in rows:
        s = js_str(r.get(series_col)) if series_col else None
        for side in ("warn", "error"):
            pair = lim.get(side) or [None, None]
            for i, end in enumerate(pair[:2]):
                b = f"{side}_{'lo' if i == 0 else 'hi'}"
                v = end if num(end) else cellv(r.get(end)) if isinstance(end, str) else None
                if num(v):
                    out.setdefault(s, {}).setdefault(b, set()).add(v)
    return out


def limits(browser, base):
    found = 0
    for case in TWINS:
        b = base_of(case)
        for v in views_of(b):
            lim = (v.get("timeseries") or {}).get("limits") if v.get("type") == "timeseries" else None
            if not isinstance(lim, dict):
                continue
            with guard(f"{case}: limits panel '{v['name']}'"):
                ds = v.get("from") or default_name(b)
                rows, _f = rows_of(case, b, ds)
                rows = [r for r in rows if compile_filter(v.get("filters"))(r)]
                sc = (v.get("timeseries") or {}).get("series")
                runs = []
                for r in rows:
                    if cellv(r.get("run")) not in runs:
                        runs.append(cellv(r.get("run")))
                sig = {run: json.dumps({k: {kk: sorted(vv) for kk, vv in d.items()} for k, d in limit_oracle([r for r in rows if cellv(r.get("run")) == run], lim, sc).items()}, sort_keys=True) for run in runs}
                pair = []
                for run in runs:
                    if sig[run] != "{}" and all(sig[run] != sig[p] for p in pair):
                        pair.append(run)
                    if len(pair) == 2:
                        break
                if len(pair) < 2:
                    continue
                # a link that picks each run: an evidence link of a row of that run, in any of the twin's datasets
                links = {}
                for name in b.get("datasets") or {}:
                    try:
                        drows, _ = rows_of(case, b, name)
                    except Exception:  # noqa: BLE001
                        continue
                    for r in drows:
                        ev = cellv(r.get("evidence")) if isinstance(r, dict) else None
                        if isinstance(ev, str) and "#" in ev and cellv(r.get("run")) in pair and cellv(r.get("run")) not in links:
                            links[cellv(r["run"])] = urllib.parse.urljoin(f"{base}/gallery/{case}/" + (data_spec(b, name) or {"data": b["data"]})["data"], ev)
                found += 1
                for run in pair:
                    want = limit_oracle([r for r in rows if cellv(r.get("run")) == run], lim, sc)
                    look = f"{case}, 1280 px, light: limits '{v['name']}' on run {run}"
                    if run not in links:
                        check(f"{look}: an evidence link picks the run", False, sorted(links))
                        continue
                    page, ok = open_case(browser, base, case, url=links[run])
                    try:
                        scroll_panel(page, v["name"])
                        with contextlib.suppress(Exception):
                            page.wait_for_function("(n) => { const s = [...document.querySelectorAll('#example .dd-panel')].find((x) => { const e = x.querySelector(':scope > data-views'); return e && e.view && e.view.name === n; }); const t = s && s.querySelector('.dv-view-timeseries'); if (!t || !t.vegaView) return false; try { return t.vegaView.data('guides').some((d) => /^limit:/.test(d.guide)); } catch (e) { return false; } }",
                                                   arg=v["name"], timeout=WAIT)
                        settle(page, 3)
                        g = page.evaluate(GUIDES, v["name"]) or {}
                        drawn = {}
                        for d in g.get("data") or []:
                            if d["guide"].startswith("limit:"):
                                drawn.setdefault(d["series"], {}).setdefault(d["guide"][6:], set()).add(d["value"])
                        bad = []
                        for s, bounds in want.items():
                            for bd, vals in bounds.items():
                                got_v = drawn.get(s, {}).get(bd) or (drawn.get(None, {}).get(bd) if len(want) == 1 else None)
                                if got_v != vals:
                                    bad.append({"series": s, "bound": bd, "drawn": sorted(got_v or []), "file": sorted(vals)})
                        px = [i for i in g.get("items") or [] if i["guide"].startswith("limit:") and i["yv"] is not None and abs(i["y"] - i["yv"]) > 1]
                        zones = [i for i in g.get("items") or [] if i["guide"].startswith("zone:")]
                        zpx = [i for i in zones if (i["guide"].endswith("_hi") and i["ylo"] is not None and abs(i["y"] - i["ylo"]) > 1) or (i["guide"].endswith("_lo") and i["yhi"] is not None and i["y2"] is not None and abs(i["y2"] - i["yhi"]) > 1)]
                        rules = [i for i in g.get("items") or [] if i["guide"].startswith("limit:")]
                        check(f"{look}: bands come from each device's own limits ({json.dumps({str(k): {kk: sorted(vv) for kk, vv in d.items()} for k, d in want.items()})}): every limit rule is the device's value and sits at its y within 1 px, every zone's limit edge too",
                              want and not bad and rules and not px and zones and not zpx, {"bad": bad[:3], "off px": px[:2], "zone off px": zpx[:2], "rules": len(rules), "zones": len(zones)})
                        shot(page, f"{case.removeprefix('robotics-')}-limits-{re.sub(r'[^a-z0-9]+', '-', str(run).lower())[:40]}", f"{D} .dd-panel[data-panel='{page.evaluate(PANEL, v['name'])}']")
                        check(f"{look}: no page error", not page.errors, page.errors[:3])
                    finally:
                        page.context.close()
    check(f"limits: at least one limits panel holds two devices with different limits, measured on a run of each ({found})", found >= 1, found)
    dep = [v for v in views_of(base_of(DEPLOY)) if v.get("type") == "timeseries" and isinstance((v.get("timeseries") or {}).get("limits"), dict)]
    check("limits: the deployments twin has a limits panel (threshold_band)", dep, [v["name"] for v in dep])


# ------------------------------------------------------------------------------------------------- the roll-up tree
TREE = r"""([name, col]) => { const s = [...document.querySelectorAll('#example .dd-panel[data-panel]')].find((x) => { const e = x.querySelector(':scope > data-views'); return e && e.view && e.view.name === name; });
  if (!s) return null; const el = s.querySelector(':scope > data-views');
  return { total: el.model ? el.model.total : null, rows: [...s.querySelectorAll('tbody tr[data-id]')].map((tr) => { const td = tr.querySelector(`td[data-col="${col}"]`); const b = td && td.querySelector('.dv-state');
    return { id: tr.dataset.id, state: b ? b.dataset.state : null, word: b ? (b.querySelector('.dv-state-word') || {}).textContent : null, glyph: b ? (b.querySelector('.dv-state-glyph') || {}).textContent : null, none: !!(td && td.querySelector('.dv-none')) }; }) }; }"""


def rollup(browser, base):
    b = base_of(DEPLOY)
    target = None
    for v in views_of(b):
        ds = v.get("from") or default_name(b)
        spec = data_spec(b, ds) or {}
        cols = [c for c, d in (v.get("display") or {}).items() if d == "status"]
        if v.get("type", "table") == "table" and isinstance(v.get("tree"), dict) and isinstance(spec.get("rollup"), dict) and any(c in (spec["rollup"].get("values") or {}) for c in cols):
            target = (v, ds, spec, next(c for c in cols if c in spec["rollup"]["values"]))
            break
    check(f"{DEPLOY}: a rollup_tree: a tree table with a status column a roll-up fills", target is not None)
    if not target:
        return
    view, ds, spec, col = target
    with guard(f"{DEPLOY}: the roll-up tree"):
        comp, cfields = rows_of(DEPLOY, b, ds)
        src = spec["rollup"]["from"]
        grows, _f = rows_of(DEPLOY, b, src)
        prop = spec["rollup"]["values"][col]["property"]
        link = next((l for l in b.get("links") or [] if {str(l.get("from")).split(".")[0], str(l.get("to")).split(".")[0]} == {src, ds}), None)
        check(f"{DEPLOY}: the roll-up's dataset is linked to {src} directly", link is not None, b.get("links"))
        a, z = str(link["from"]).split("."), str(link["to"]).split(".")
        fk, key = (a[1], z[1]) if a[0] == src else (z[1], a[1])
        parent = spec.get("tree", {}).get("parent") or view["tree"]["parent"]
        ids = {str(r.get("id")): r for r in comp}
        kids = {}
        for r in comp:
            p = cellv(r.get(parent))
            if not empty(p):
                kids.setdefault(str(p), []).append(str(r.get("id")))

        def subtree(i, seen=None):
            seen = seen or set()
            if i in seen:
                return []
            seen.add(i)
            return [i] + [x for k in kids.get(i, []) for x in subtree(k, seen)]
        labels = (cfields.get(col) or {}).get("labels") or {}
        want = {}
        for r in comp:
            keys = {js_str(cellv(ids[i].get(key)) if key != "id" else i) for i in subtree(str(r.get("id")))}
            ranks = [cellv(g.get(prop)) for g in grows if js_str(cellv(g.get(fk))) in keys and num(cellv(g.get(prop)))]
            want[str(r.get("id"))] = max(ranks) if ranks else None
        page, ok = open_case(browser, base, DEPLOY)
        try:
            scroll_panel(page, view["name"])
            with contextlib.suppress(Exception):
                page.wait_for_function("([n, c]) => { const s = [...document.querySelectorAll('#example .dd-panel')].find((x) => { const e = x.querySelector(':scope > data-views'); return e && e.view && e.view.name === n; }); return !!s && s.querySelectorAll(`td[data-col='${c}'] .dv-state`).length > 0; }",
                                       arg=[view["name"], col], timeout=WAIT)
            settle(page, 2)
            got = page.evaluate(TREE, [view["name"], col]) or {}
            drawn = {r["id"]: r for r in got.get("rows") or []}
            bad = []
            for i, rank in want.items():
                d = drawn.get(i)
                if d is None:
                    bad.append({"node": i, "not drawn": True})
                elif rank is None:
                    if not d["none"]:
                        bad.append({"node": i, "drawn": d["state"], "want": "—"})
                else:
                    word = str(labels.get(js_str(rank), js_str(rank)))
                    if d["state"] != js_str(rank) or d["word"] != word or d["glyph"] != status_of(rank, None, {"labels": labels})["glyph"]:
                        bad.append({"node": i, "drawn": [d["state"], d["word"], d["glyph"]], "want": [js_str(rank), word]})
            check(f"{DEPLOY}: rollup worst-of equals an oracle: each of the {len(want)} nodes shows the worst rank of the {src} rows under it, as its word and glyph",
                  want and not bad and any(v is not None for v in want.values()), bad[:4] or {"nodes": len(want)})
            shot(page, "deployments-rollup", f"{D} .dd-panel[data-panel='{page.evaluate(PANEL, view['name'])}']")
            check(f"{DEPLOY}: roll-up: no page error", not page.errors, page.errors[:3])
        finally:
            page.context.close()


# ------------------------------------------------------------------------------------------------- KPI trend
HISTORY = r"""([name, xf, yf]) => { const s = [...document.querySelectorAll('#example .dd-panel[data-panel]')].find((x) => { const e = x.querySelector(':scope > data-views'); return e && e.view && e.view.name === name; });
  const card = s && s.querySelector('data-kpi'); const ch = card && card.querySelector('.dv-kpi-history .dv-view-chart'); const v = ch && ch.vegaView;
  if (!v) return null; const y = v.scale('y'); const pts = [], rules = [];
  const tx = (x) => (x instanceof Date ? x.getTime() : typeof x === 'string' && !Number.isNaN(Date.parse(x)) && /\d{4}-\d{2}-\d{2}/.test(x) ? Date.parse(x) : x);
  const walk = (n) => { if (!n) return; if (n.marktype === 'line' && n.role === 'mark') for (const i of n.items || []) if (i.datum && i.datum[yf] !== undefined) pts.push([tx(i.datum[xf]), i.datum[yf]]);
    if (n.marktype === 'rule' && n.role === 'mark') for (const i of n.items || []) rules.push(i.y);
    for (const i of n.items || []) if (i.items) walk(i); };
  walk(v.scenegraph().root);
  return { points: pts, rules, label: (card.querySelector('.dv-kpi-label') || {}).textContent || null }; }"""


def x_key(v):
    v = cellv(v)
    if isinstance(v, str) and re.match(r"\d{4}-\d{2}-\d{2}", v):
        from datetime import datetime
        return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() * 1000 if ("T" in v) else datetime.fromisoformat(v + "T00:00:00+00:00").timestamp() * 1000
    return v


def kpi(browser, base):
    found = []
    for case in TWINS:
        b = base_of(case)
        for v in views_of(b):
            k = v.get("kpi") if v.get("type") == "kpi" else None
            if not isinstance(k, dict) or not isinstance(k.get("spark"), dict) or k.get("target") is None:
                continue
            found.append(case)
            with guard(f"{case}: kpi trend '{v['name']}'"):
                page, ok = open_case(browser, base, case)
                try:
                    key = scroll_panel(page, v["name"])
                    with contextlib.suppress(Exception):
                        page.wait_for_function("(k) => { const c = document.querySelector(`#example .dd-panel[data-panel='${k}'] data-kpi .dv-kpi-history .dv-view-chart`); return !!c && !!c.vegaView; }", arg=key, timeout=WAIT)
                    settle(page, 3)
                    xf, yf = k["spark"]["x"], k["spark"].get("y") or (k.get("value") or {}).get("property")
                    # the headline card's rows: the panel's own (its first group's, with groupBy)
                    model = page.evaluate(f"""(k) => {{ {CV} const el = document.querySelector(`#example .dd-panel[data-panel='${{k}}'] > data-views`); const m = el && el.model; if (!m) return null;
                      const rows = m.groups && m.groups.length ? m.groups[0].rows : m.rows; return rows.map((r) => ({{ x: cv(r['{xf}']) ?? null, y: cv(r['{yf}']) ?? null, target: typeof {json.dumps(k.get('target'))} === 'string' ? cv(r[{json.dumps(k.get('target'))}]) ?? null : null }})); }}""", key) or []
                    rows = sorted((r for r in model if not empty(r["x"])), key=lambda r: x_key(r["x"]))
                    want = [[x_key(r["x"]), r["y"]] for r in rows if num(r["y"])]
                    got = page.evaluate(HISTORY, [v["name"], xf, yf]) or {}
                    drawn = [[p[0], p[1]] for p in got.get("points") or []]
                    check(f"{case}: kpi_trend '{v['name']}': the headline's history draws exactly its {len(want)} rows' ({xf}, {yf}) in {xf} order",
                          want and drawn == want, {"drawn": drawn[:4], "want": want[:4], "n": [len(drawn), len(want)]})
                    target = k["target"] if num(k["target"]) else (rows[-1]["target"] if rows else None)
                    ty = page.evaluate("([k, t]) => { const c = document.querySelector(`#example .dd-panel[data-panel='${k}'] data-kpi .dv-kpi-history .dv-view-chart`); return c && c.vegaView ? c.vegaView.scale('y')(t) : null; }", [key, target]) if num(target) else None
                    check(f"{case}: kpi_trend '{v['name']}': a target rule at the target ({target}) within 1 px",
                          ty is not None and any(abs(r - ty) <= 1 for r in got.get("rules") or []), {"rules": (got.get("rules") or [])[:4], "y(target)": ty})
                    shot(page, f"{case.removeprefix('robotics-')}-kpi", f"{D} .dd-panel[data-panel='{key}']")
                    check(f"{case}: kpi trend: no page error", not page.errors, page.errors[:3])
                finally:
                    page.context.close()
    check(f"kpi_trend: at least one KPI view with a spark and a target, in the servo twin ({sorted(set(found))})", "robotics-servo-gates" in found, sorted(set(found)))


# ------------------------------------------------------------------------------------------------- live (RobotDx's checks)
MOUNT_LIVE = r"""async ([caseUrl, viewName]) => {
  const kit = window.kit; const text = await (await fetch(caseUrl + 'views.base')).text(); const base = kit.parseBase(text);
  const view = base.views.find((v) => v.name === viewName); const ds = view.from;
  const spec = typeof base.datasets[ds] === 'string' ? { data: base.datasets[ds] } : base.datasets[ds];
  const file = await kit.loadDataset(new URL(spec.data, caseUrl).href);
  const live = new kit.LiveDataset({ id: ds, title: file.title || ds, titleProperty: file.titleProperty, properties: file.properties, rows: [], time: 't', key: 'id' });
  const mini = { data: spec.data, datasets: { [ds]: { ...spec } }, layout: { panels: [{ view: viewName, w: 12, h: 5 }] }, views: [view], style: base.style, properties: base.properties };
  document.querySelector('#live')?.remove();
  const d = document.createElement('data-dashboard'); d.id = 'live'; document.body.append(d);
  d.load(mini, { [ds]: live });
  window.liveSet = live; window.liveView = view; return { ds, n: file.rows.length }; }"""


def live_oracle(rows, at, view):
    newest = {}
    for r in rows:
        if r["t"] <= at and (r["id"] not in newest or r["t"] >= newest[r["id"]]["t"]):
            newest[r["id"]] = r
    tr, gb = view["tracker"], view["groupBy"]["property"]
    cells = {}
    for r in newest.values():
        cells.setdefault((js_str(r[gb]), js_str(r[tr["column"]])), []).append(r[tr["state"]])
    return {k: js_str(worst(v, tr.get("order"))) for k, v in cells.items()}


def live(browser, root_base):
    b = base_of(DEPLOY)
    view = next((v for v in views_of(b) if v.get("name") == "Run checks"), None)
    check(f"live: the deployments twin has its 'Run checks' matrix", view is not None and view in matrix_views(b))
    feed = EX / DEPLOY / "live_checks.json"
    check(f"live: the deployments twin's live_checks.json (RobotDx's windowed rows) exists", feed.exists(), str(feed))
    if not view or not feed.exists():
        return
    rows, _f = load_table(feed)
    rows = sorted((r for r in rows if num(r.get("t")) and not empty(r.get("id"))), key=lambda r: r["t"])
    check(f"live: {len(rows)} keyed rows, each with an id, a t, the matrix's columns and a vocabulary word",
          len(rows) >= 10 and all(not empty(r.get(view["groupBy"]["property"])) and not empty(r.get(view["tracker"]["column"])) and js_str(r.get(view["tracker"]["state"])) in STATUS for r in rows), len(rows))
    if len(rows) < 10:
        return
    ts = [r["t"] for r in rows]
    t1 = ts[len(ts) * 2 // 5]
    t2 = ts[-1]
    for width, dark in ((1280, False), (390, True)):
        look = f"live, {width} px, {'dark' if dark else 'light'}"
        with guard(look):
            page = new_page(browser, width, dark)
            try:
                page.goto(root_base + PAGE)
                page.wait_for_function("() => window.kitReady === true", timeout=WAIT)
                page.evaluate(MOUNT_LIVE, [f"{root_base}/gallery/examples/{DEPLOY}/", view["name"]])
                entry = page.evaluate("() => JSON.parse(JSON.stringify(window.liveView))")
                check(f"{look}: the matrix is the twin's own view entry, unchanged", entry == view, {"keys": sorted(entry or {})})

                def push(upto, after):
                    batch = [r for r in rows if after < r["t"] <= upto]
                    page.evaluate("(rs) => window.liveSet.upsert(rs)", batch)
                    return len(batch)

                def drawn():
                    got = page.evaluate(MATRIX, ["#live", view["name"]]) or {}
                    heads = [h["column"] for h in got.get("heads") or []]
                    out = {}
                    for r in got.get("rows") or []:
                        for c, col in zip(r["cells"], heads):
                            if not c["na"]:
                                out[(r["label"], col)] = c["state"]
                    return out, got

                gc = None
                n1 = push(t1, -math.inf)
                page.wait_for_function("() => { const g = document.querySelector('#live [role=grid]'); return !!g && g.querySelectorAll('[role=gridcell]').length > 0; }", timeout=WAIT)
                settle(page, 4)
                d1, got = drawn()
                gc = (got.get("cols") or {}).get("group") or {"label": view["groupBy"]["property"]}
                relabel = lambda o: {(label_of(k[0], gc, gc["label"]), k[1]): v for k, v in o.items()}  # noqa: E731
                w1 = relabel(live_oracle(rows, t1, view))
                check(f"{look}: following, after {n1} rows up to t = {t1}: every cell is the newest version per key ({len(w1)} cells)", d1 == w1, {"drawn": list(d1.items())[:3], "want": list(w1.items())[:3]})
                n2 = push(t2, t1)
                w2 = relabel(live_oracle(rows, t2, view))
                with contextlib.suppress(Exception):
                    page.wait_for_function("(n) => { const g = document.querySelector('#live [role=grid]'); return !!g && g.querySelectorAll('[role=gridcell]:not([data-na])').length === n; }", arg=len(w2), timeout=WAIT)
                settle(page, 4)
                d2, _ = drawn()
                check(f"{look}: following, after {n2} more rows up to t = {t2}: the matrix moved with them ({len(w2)} cells, the newest version per key)", d2 == w2 and w2 != w1, {"drawn": list(d2.items())[:3], "want": list(w2.items())[:3]})
                page.evaluate("(t) => { const c = document.querySelector('#live').clock; c.pause(); c.seek(t); }", t1)
                settle(page, 6)
                d3, _ = drawn()
                check(f"{look}: paused back at t = {t1}: the matrix is again as of that t (rewind)", d3 == w1, {"drawn": list(d3.items())[:3], "want": list(w1.items())[:3]})
                shot(page, f"live-{'dark' if dark else 'light'}-{width}", "#live")
                check(f"{look}: no page error", not page.errors, page.errors[:3])
            finally:
                page.context.close()


# ------------------------------------------------------------------------------------------------- the checker fixture
def fixture(browser, root_base):
    with guard("fixture: tests/fixtures/p5/gates.base"):
        page = new_page(browser)
        try:
            page.goto(root_base + PAGE)
            page.wait_for_function("() => window.kitReady === true", timeout=WAIT)
            page.evaluate("(src) => { const d = document.createElement('data-dashboard'); d.id = 'example'; d.setAttribute('src', src); document.body.append(d); }", CHECKER_BASE)
            wait_ready(page)
            # the live plot's limits: each device's own
            key = scroll_panel(page, "Live limits")
            with contextlib.suppress(Exception):
                page.wait_for_function("(k) => { const p = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-view-plot`); return !!p && !!p.plotView && !!p.uplot; }", arg=key, timeout=WAIT)
            settle(page, 3)
            pg = page.evaluate("(k) => { const p = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-view-plot`); const v = p && p.plotView; const u = p && p.uplot; if (!v || !u) return null; return { guides: JSON.parse(JSON.stringify(v.guides || [])), ymax: u.scales.y.max, ymin: u.scales.y.min }; }", key) or {}
            win, _f = load_table(CHECKER_FIX / "windows.json")
            want = {}
            for r in win:
                for bd in ("error_lo", "error_hi"):
                    if num(r.get(bd)):
                        want.setdefault((r["device"], bd), set()).add(r[bd])
            got = {}
            for g in pg.get("guides") or []:
                if str(g.get("guide", "")).startswith("limit:"):
                    for s in g.get("shared") or [g.get("series")]:
                        got.setdefault((s, g["guide"][6:]), set()).update(p[1] for p in g.get("points") or [])
            check("fixture: the live plot's limits are each device's own (plotView.guides: error_lo and error_hi per device), on its y scale",
                  got == want and pg.get("ymax") is not None and pg["ymax"] >= max(max(v) for v in want.values()) and pg["ymin"] <= min(min(v) for v in want.values()),
                  {"drawn": {f"{k[0]}:{k[1]}": sorted(v) for k, v in got.items()}, "want": {f"{k[0]}:{k[1]}": sorted(v) for k, v in want.items()}, "y": [pg.get("ymin"), pg.get("ymax")]})
            # the gate matrix's peek: both section views, each its bound rows
            base = data_ui_base.loads((CHECKER_FIX / "gates.base").read_text(encoding="utf-8"))
            view = next(v for v in base["views"] if v["name"] == "Gate matrix")
            checks_rows, _f = load_table(CHECKER_FIX / "checks.json")
            row = next(r for r in checks_rows if r["id"] == "r1#temperature")
            key = scroll_panel(page, "Gate matrix")
            cell = page.locator(f"{D} .dd-panel[data-panel='{key}'] [role=gridcell][data-id='r1#temperature']").first
            cell.click()
            with contextlib.suppress(Exception):
                page.wait_for_function("() => { const s = document.querySelectorAll('#example .dd-drill .dv-peek .dv-peek-view[data-section] data-views'); return s.length === 2 && [...s].every((e) => e.dataset.view && e.model); }", timeout=WAIT)
            settle(page, 3)
            peek = page.evaluate(PEEK) or {}
            check("fixture: a cell click opens the peek on its row (r1#temperature)", peek.get("id") == "r1#temperature", peek.get("id"))
            for sec in view["record"]["sections"]:
                if not isinstance(sec.get("view"), dict):
                    continue
                sv = sec["view"]
                rows, _f = load_table(CHECKER_FIX / f"{sv['from']}.json")
                keep = compile_filter(bind_this(sv.get("filters"), row))
                want_ids = sorted(str(r.get("id", i)) for i, r in enumerate(rows) if keep(r))
                got = next((s for s in peek.get("sections") or [] if s["name"] == sec["name"]), None)
                check(f"fixture: the peek's '{sec['name']}' section draws exactly the {len(want_ids)} rows its filter bound to the row keeps",
                      got and got["drawn"] and got["matched"] == len(want_ids) and len(want_ids) > 0, {"drawn": got, "want": len(want_ids)})
            want_link = urllib.parse.urljoin(f"{root_base}/tests/fixtures/p5/checks.json", row["evidence"])
            check("fixture: the peek's evidence field is a real link, resolved against checks.json", peek.get("link") == want_link, {"drawn": peek.get("link"), "want": want_link})
            shot(page, "fixture-peek-light-1280")
            check("fixture: no page error", not page.errors, page.errors[:3])
        finally:
            page.context.close()


# ------------------------------------------------------------------------------------------------- the path overlay and the verdict voxels
def srgb_to_oklab(hexs):
    h = hexs.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    l = (0.4122214708 * lin[0] + 0.5363325363 * lin[1] + 0.0514459929 * lin[2]) ** (1 / 3)
    m = (0.2119034982 * lin[0] + 0.6806995451 * lin[1] + 0.1073969566 * lin[2]) ** (1 / 3)
    s = (0.0883024619 * lin[0] + 0.2817188376 * lin[1] + 0.6299787005 * lin[2]) ** (1 / 3)
    return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s]


def to_hex(c):
    if not isinstance(c, str):
        return None
    if c.startswith("#"):
        return c.lower()[:7]
    n = re.findall(r"[\d.]+", c)
    return "#%02x%02x%02x" % tuple(round(float(x)) for x in n[:3]) if len(n) >= 3 else None


def close_hex(a, b, tol=2):
    a, b = to_hex(a), to_hex(b)
    return bool(a and b) and all(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) <= tol for i in (1, 3, 5))


def path_overlay(browser, base):
    case = "robotics-arm-gates"
    b = base_of(case)
    view = next((v for v in views_of(b) if v.get("type") == "trajectory3d" and isinstance(v.get("trajectory3d"), dict) and v["trajectory3d"].get("color") and num(v["trajectory3d"].get("tolerance"))), None)
    check(f"{case}: a path_overlay: a trajectory3d with color and tolerance", view is not None)
    if not view:
        return
    with guard(f"{case}: the path overlay"):
        page, ok = open_case(browser, base, case)
        try:
            key = scroll_panel(page, view["name"])
            page.wait_for_function("(k) => { const r = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`); return !!r && !!r.scene3d && r.scene3d.renders() > 0 && typeof r.scene3d.overlay === 'function'; }", arg=key, timeout=WAIT)
            settle(page, 3)
            got = page.evaluate("(k) => { const h = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`).scene3d; return { overlay: h.overlay(), tube: h.tube() }; }", key) or {}
            tk = page.evaluate("(k) => { const e = document.querySelector(`#example .dd-panel[data-panel='${k}'] > data-views`); const t = e.tokens(); return { s1: t.series[0], warn: t.tone && t.tone.warn }; }", key) or {}
            ov = got.get("overlay") or {}
            segs = ov.get("segments") or []
            lo_hex, hi_hex = to_hex(tk.get("s1")), to_hex(tk.get("warn"))
            vmin, vmax = ov.get("min"), ov.get("max")
            bad = []
            if lo_hex and hi_hex and num(vmin) and num(vmax) and vmax > vmin:
                a, z = srgb_to_oklab(lo_hex), srgb_to_oklab(hi_hex)
                axis = [z[i] - a[i] for i in range(3)]
                ln2 = sum(x * x for x in axis)
                for s in segs:
                    if not num(s.get("value")):
                        continue
                    want = (s["value"] - vmin) / (vmax - vmin)
                    c = srgb_to_oklab(to_hex(s["color"]))
                    proj = sum((c[i] - a[i]) * axis[i] for i in range(3)) / ln2
                    if abs(proj - want) > 0.03:
                        bad.append({"value": s["value"], "colour": s["color"], "at": round(proj, 3), "want": round(want, 3)})
                ends = [s for s in segs if s.get("value") in (vmin, vmax)]
                for s in ends:
                    if not close_hex(s["color"], lo_hex if s["value"] == vmin else hi_hex):
                        bad.append({"end": s["value"], "colour": s["color"]})
            else:
                bad.append({"tokens": tk, "min/max": [vmin, vmax]})
            check(f"{case}: path_overlay colour: every painted segment ({len(segs)}) sits on the ramp series 1 → warn at its {view['trajectory3d']['color']} (OKLab, within 0.03), the ends exact",
                  len(segs) > 10 and not bad and ov.get("color") == view["trajectory3d"]["color"], bad[:3] or {"segments": len(segs), "color": ov.get("color")})
            tube = got.get("tube") or {}
            path = tube.get("path") or []
            rings = tube.get("rings") or []
            radius = view["trajectory3d"]["tolerance"]

            def dist_to_path(p):
                best = math.inf
                for q0, q1 in zip(path, path[1:]):
                    d = [q1[i] - q0[i] for i in range(3)]
                    dd = sum(x * x for x in d)
                    u = 0 if dd == 0 else max(0.0, min(1.0, sum((p[i] - q0[i]) * d[i] for i in range(3)) / dd))
                    best = min(best, math.dist(p, [q0[i] + u * d[i] for i in range(3)]))
                return best
            tb = []
            for ring in rings:
                c = ring.get("center")
                if dist_to_path(c) > 1e-3 * max(1.0, radius):
                    tb.append({"center off the path": c})
                for p in ring.get("points") or []:
                    if abs(math.dist(p, c) - radius) > 1e-3 * radius:
                        tb.append({"radius": math.dist(p, c), "want": radius})
                        break
            check(f"{case}: path_overlay tolerance: the tube's rings ({len(rings)}) are centred on the target's path, each point at the tolerance ({radius}) from its centre",
                  tube.get("radius") == radius and len(rings) >= 2 and len(path) >= 2 and not tb, tb[:3] or {"radius": tube.get("radius"), "rings": len(rings)})
            shot(page, "arm-path-overlay", f"{D} .dd-panel[data-panel='{key}']")
            check(f"{case}: path overlay: no page error", not page.errors, page.errors[:3])
        finally:
            page.context.close()


def voxels_verdict(browser, base):
    case = "robotics-arm-gates"
    b = base_of(case)
    view = next((v for v in views_of(b) if v.get("type") == "voxels" and (v.get("voxels") or {}).get("scale") == "verdict"), None)
    check(f"{case}: voxels with scale: verdict", view is not None)
    if not view:
        return
    with guard(f"{case}: the verdict voxels"):
        page, ok = open_case(browser, base, case)
        try:
            key = scroll_panel(page, view["name"])
            page.wait_for_function("(k) => { const r = document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`); return !!r && !!r.scene3d && r.scene3d.renders() > 0 && !!r.scene3d.ramp(); }", arg=key, timeout=WAIT)
            settle(page, 3)
            got = page.evaluate("""(k) => { const s = document.querySelector(`#example .dd-panel[data-panel='${k}']`); const h = s.querySelector('.dv-scene3d').scene3d; const e = s.querySelector(':scope > data-views');
              const t = e.tokens(); const r = h.ramp(); const cells = typeof h.cellColours === 'function' ? h.cellColours() : null;
              return { ramp: r, tone: t.tone || null, cells, bar: (s.querySelector('[data-ramp]') || {}).textContent || '', lo: r ? h.colour(r.domain[0]) : null, hi: r ? h.colour(r.domain[1]) : null }; }""", key) or {}
            tone = got.get("tone") or {}
            better = (view.get("voxels") or {}).get("better") or "higher"
            want_lo, want_hi = (tone.get("bad"), tone.get("good")) if better == "higher" else (tone.get("good"), tone.get("bad"))
            check(f"{case}: verdict voxels: the ramp's ends are the {'bad' if better == 'higher' else 'good'} and {'good' if better == 'higher' else 'bad'} tones ({better} is better)",
                  close_hex(got.get("lo"), want_lo) and close_hex(got.get("hi"), want_hi), {"lo": got.get("lo"), "hi": got.get("hi"), "tones": tone})
            cells = got.get("cells") or []
            bad = [c for c in cells if not close_hex(c[4], page.evaluate("([k, v]) => document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`).scene3d.colour(v)", [key, c[3]]))][:3] if len(cells) <= 400 else None
            if bad is None:
                sample = cells[:: max(1, len(cells) // 200)]
                bad = [c for c in sample if not close_hex(c[4], page.evaluate("([k, v]) => document.querySelector(`#example .dd-panel[data-panel='${k}'] .dv-scene3d`).scene3d.colour(v)", [key, c[3]]))][:3]
            check(f"{case}: verdict voxels: every drawn cell's colour ({len(cells)} cells, from the instance buffers) is its value's on the ramp", cells and not bad, bad)
            bar = got.get("bar") or ""
            check(f"{case}: verdict voxels: the ramp's bar carries ✕ at its bad end and ✓ at its good end", "✕" in bar and "✓" in bar, bar[:120])
            shot(page, "arm-verdict-voxels", f"{D} .dd-panel[data-panel='{key}']")
            check(f"{case}: verdict voxels: no page error", not page.errors, page.errors[:3])
        finally:
            page.context.close()


def main() -> int:
    if not (SITE / "index.html").exists():
        print("dist/site is not built: npm --prefix ~/data-ui run build")
        return 1
    with guard("the files"):
        files()
    proc, base = serve(SITE, "/index.html")
    rproc, root = serve(ROOT, PAGE)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for name, fn, where in (("the matrices", matrices, base), ("the peek and evidence", evidence, base), ("limits", limits, base),
                                    ("the roll-up", rollup, base), ("KPI trend", kpi, base), ("live", live, root), ("the checker fixture", fixture, root),
                                    ("the path overlay", path_overlay, base), ("the verdict voxels", voxels_verdict, base)):
                with guard(name):
                    fn(browser, where)
            browser.close()
    finally:
        for p in (proc, rproc):
            p.terminate()
            p.wait(timeout=10)
    (OUT / "p5-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} P5 checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
