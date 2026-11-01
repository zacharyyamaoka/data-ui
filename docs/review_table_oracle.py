#!/usr/bin/env python3
"""Review the table oracle's drawing change before its golden is accepted (judge r4 #2, r5 #2).

    ~/psu-atlas/.venv/bin/python docs/review_table_oracle.py BEFORE_ROOT [OUT_JSON]

BEFORE_ROOT is a built checkout of main (its dist/ and gallery/); this checkout is the after. Every table and pivot view
the oracle pins is drawn by both builds, each over its own gallery files, through the oracle's own page
(tests/browser/fixtures/lifecycle.html, the same fixed clock). Each build's view is visited (SNAPSHOT): its own scroll
box is scrolled from the top in steps of 0.8 of the band a reader sees rows in, until the first CAP rows have been drawn,
then to the end; every stop measures that band and every drawn row's box. compare() checks what a reader gets:

- the view's rows by identity and order (the model's record ids, the flat list with group rows): none removed, added
  or moved;
- each build's drawing, measured, never read from its own plan (judge r7 #2): at every stop the drawn rows are
  consecutive, abut on screen and cover the band from its top to its foot (the foot may stay blank only once the
  view's last row is drawn); and the review's sample (the first CAP rows and the last TAIL, by position, the same for
  both builds) is drawn at some stop and read, in both builds;
- the columns: none missing, none added, none reordered (the model's leaf order); every header label the same; the
  merged headings above them the same, position by position, but for a column's unit moved onto one as a caption;
- units: only lane/types' declared transform, "N·m" -> "(N·m)", or a stats column's unit moved to its group header;
- group rows by identity and label, position by position;
- every cell of the sample: an untyped cell's text and drawing the same (a group row's summary may only rename its
  label, the number the same); a typed cell, and a typed column's group summary, exactly the text an independent
  formatter (this file, not the kit's code) writes for its stored value, a rich cell's range and basis mark included,
  and drawn as its type draws (an option's pill, a status pill, a bar or ring, a rating's count) — checked even when
  the text did not move. Which columns are typed, and how, is read from the input (the case's views.base
  `properties.<p>.type` and options over its data file's own, as the kit merges them: input_types()), never from the
  after build's metadata (judge r7 #2): a column the .base types and the after build draws untyped fails.

Anything else is a problem; the review exits 1 when there is one, and writes every view's findings to OUT_JSON (default
<main>/reports/media/types/oracle-review.json). compare() is pure: tools/test_review_table_oracle.py holds it to that.
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal

# the review's sample of every view, by position (judge r7 #2: rows past the window both builds first draw): the first
# CAP rows and the last TAIL; every row of a shorter view. The same for both builds, so neither one's drawing decides it
CAP, TAIL = 300, 10
TOL = 1.0  # px: how far two measured edges may sit apart and still meet (rects are fractional)
# a view whose table has no columns in either build (its rows have no cells): reported, never counted as reviewed
NO_COLUMNS = "no columns in either build"

# the basis marks (packages/core/src/format.js BASIS), as a reader sees them
MARK = {"measured": "●", "datasheet": "D", "seller": "S", "derived": "~", "estimate": "○", "assumed": "A", "chosen": "C", "sampled": "≈", "stand-in": "◌", "claimed": "”"}
SUMMARY = r"^(?:med|avg|ave|min|max|sum|cou|ran|spr|uni|fil|emp|count|values|unique|empty|filled|median|range|checked|unchecked|earliest|latest) "


class Unsupported(Exception):
    """A typed column whose formatting this review has no independent expectation for."""


def _grouped(int_text):
    neg = int_text.startswith("-")
    digits = int_text.lstrip("-")
    out = ""
    while len(digits) > 3:
        out = "," + digits[-3:] + out
        digits = digits[:-3]
    return ("-" if neg else "") + digits + out


def full(x):
    """A number with every stored digit, grouped, never an exponent (the kit's fmtNum without decimals)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return str(x)
    d = Decimal(repr(float(x))) if isinstance(x, float) else Decimal(x)
    text = format(d.normalize(), "f") if d != d.to_integral() else str(int(d))
    if "." in text:
        i, f = text.split(".")
        return f"{_grouped(i)}.{f}"
    return _grouped(text)


def fixed(x, d):
    """A number at d decimals, rounded half away from zero (Intl's default), grouped."""
    q = Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    text = format(q, "f")
    if "." in text:
        i, f = text.split(".")
        return f"{_grouped(i)}.{f}"
    return _grouped(text)


def number_text(v, meta, kind):
    d = meta.get("decimals")
    d = None if d in (None, "") else int(d)
    fmt = meta.get("format") or ("percent" if kind == "percent" else "currency" if kind == "currency" else "number_with_commas")
    if meta.get("abbreviate"):
        raise Unsupported("abbreviate")
    if fmt == "percent":
        pct = Decimal(repr(float(v))) * 100
        if d is None:
            q = pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            text = format(q.normalize(), "f") if q != q.to_integral() else str(int(q))
        else:
            text = format(pct.quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP), "f")
        i, _, f = text.partition(".")
        return f"{_grouped(i)}{'.' + f if f else ''}%"
    if fmt == "currency":
        code = (meta.get("currency") or "USD").upper()
        if code != "USD":
            raise Unsupported(f"currency {code}")
        body = fixed(abs(v), 2 if d is None else d)
        return f"{'-' if v < 0 else ''}${body}"
    if fmt == "number":
        raise Unsupported("ungrouped number format")
    return full(v) if d is None else fixed(v, d)


def expect(meta, raw):
    """What a typed cell writes (its text content) for a stored value, independently of the kit's code."""
    # a value rolled away by the view's roll-up (CONTRACT §16) reads its count, whatever its type
    if isinstance(raw, dict) and raw.get("rolled"):
        return f"{raw['rolled']} values"
    rich = raw if isinstance(raw, dict) and "value" in raw else None
    v = rich["value"] if rich else raw
    kind = meta.get("kind")
    labels = meta.get("labels") or {}
    if v is None or v == "" or v == []:
        return "—"
    if kind in ("select", "status"):
        if kind == "status" and meta.get("showAs") == "checkbox":
            return ""
        return "".join(str(labels.get(str(x), x)) for x in (v if isinstance(v, list) else [v]))
    if kind == "multi_select":
        return "".join(str(labels.get(str(x), x)) for x in (v if isinstance(v, list) else [v]))
    if kind in ("checkbox", "rating"):
        return ""
    if kind in ("number", "currency", "percent", "rollup"):
        if not isinstance(v, (int, float)):
            return str(v)
        show = meta.get("showAs")
        text = "" if show in ("bar", "ring") and meta.get("showNumber") is False else number_text(v, meta, kind)
        if kind == "rollup" and show not in ("bar", "ring"):
            text += "Σ"
        if rich:
            if isinstance(rich.get("low"), (int, float)) or isinstance(rich.get("high"), (int, float)):
                text += f"{full(rich['low']) if rich.get('low') is not None else ''}–{full(rich['high']) if rich.get('high') is not None else ''}"
            if rich.get("basis"):
                text += MARK.get(rich["basis"], "?")
        return text
    raise Unsupported(kind or "untyped")


def drawing(meta, raw):
    """What a typed cell draws beside its text, in the snapshot's words (SNAPSHOT `marks`): one pill per option of a
    select, a status pill per value, a bar or a ring, a rating's or a checkbox's spoken label. Text alone cannot tell
    a select, a status or a bar drawn by its type from the same text drawn untyped; this can (judge r7 #2). None when
    the type draws nothing this review tells from plain text, or the view draws the column its own way (`display:`)."""
    if meta.get("viewDisplay") not in (None, "", "badge"):
        return None
    if isinstance(raw, dict) and raw.get("rolled"):
        return []
    v = raw["value"] if isinstance(raw, dict) and "value" in raw else raw
    if v is None or v == "" or v == []:
        return []
    kind = meta.get("kind")
    labels = meta.get("labels") or {}
    values = v if isinstance(v, list) else [v]
    number = isinstance(v, (int, float)) and not isinstance(v, bool)
    if kind in ("select", "multi_select"):
        return ["pill:" + str(labels.get(str(x), x)) for x in values]
    if kind == "status":
        return None if meta.get("showAs") == "checkbox" else ["status:" + str(labels.get(str(x), x)) for x in values]
    if kind in ("number", "currency", "percent", "rollup"):
        show = meta.get("showAs")
        return [show] if number and show in ("bar", "ring") else []
    if kind == "rating":
        if not number:
            return []
        try:  # the kit's Math.max(1, Math.min(10, Number(max) || 5))
            top = int(float(meta.get("max") or 5)) or 5
        except (TypeError, ValueError):
            top = 5
        top = max(1, min(10, top))
        return [f"img:{max(0, min(top, math.floor(v + 0.5)))} of {top}"]  # Math.round: half up
    if kind == "checkbox":
        on = v is True or v == "true" or (number and v == 1)
        return ["img:Yes" if on else "img:No"]
    return None


def types_from(base, view_name, data_props):
    """{column: its type and options} for one view, from a parsed .base file and its data file's `properties` (pure).
    The kit's merge (packages/core/src/rowmodel.js properties()): a .base entry over the data's own meta, its `type`
    landing as `kind`; `note.<p>` is `<p>`. Only the .base says a column is typed: a data file's `kind` is dropped. A
    view's own `display:` for a column replaces the type's drawing (the view's bar, a distribution), so it is kept."""
    view = next((x for x in (base.get("views") or []) if isinstance(x, dict) and x.get("name") == view_name), None) or {}
    display = view.get("display") if isinstance(view.get("display"), dict) else {}
    out = {}
    for key, entry in (base.get("properties") or {}).items():
        if not isinstance(entry, dict) or not entry.get("type"):
            continue
        pid = key[5:] if key.startswith("note.") else key
        data = data_props.get(pid) if isinstance(data_props.get(pid), dict) else {}
        own = {k: v for k, v in entry.items() if k not in ("type", "displayName")}
        out[pid] = {**{k: v for k, v in data.items() if k != "kind"}, **own, "kind": entry["type"]}
        if display.get(pid):
            out[pid]["viewDisplay"] = display[pid]
    return out


def input_types(case_dir, view_name):
    """types_from() over the files: the case's views.base and, when it names one, its JSON data file's properties."""
    import yaml  # noqa: PLC0415  (PyYAML: the oracle's cases() reads the .base files with it too)

    case_dir = pathlib.Path(case_dir)
    base = yaml.safe_load((case_dir / "views.base").read_text(encoding="utf-8")) or {}
    data_props = {}
    src = base.get("data")
    if isinstance(src, str) and src.strip().endswith(".json") and (case_dir / src.strip()).is_file():
        doc = json.loads((case_dir / src.strip()).read_text(encoding="utf-8"))
        if isinstance(doc, dict) and isinstance(doc.get("properties"), dict):
            data_props = doc["properties"]
    return types_from(base, view_name, data_props)


def sample(n):
    """The rows the review reads in a view of n rows, by position: the first CAP and the last TAIL."""
    return sorted(set(range(min(n, CAP))) | set(range(max(0, n - TAIL), n)))


def drawn_problems(label, snap):
    """One build's drawing as measured at every stop of its visit (judge r7 #2): never held to its own plan. At each
    stop the drawn rows are consecutive positions, abut on screen and cover the band a reader sees rows in, top to foot
    (the foot may stay blank only below the view's last row: a short table, or its end). Over the visit every row of
    the review's sample is drawn at some stop and read once, at its position, as the view's row there."""
    flat = snap.get("flatIds")
    stops = snap.get("stops")
    if not isinstance(flat, list):
        return [f"{label}: the view's rows were not read"]
    if not stops:
        return [f"{label}: the visit measured no stop"]
    n = len(flat)
    problems = []
    drawn = set()
    for s in stops:
        rows = sorted(s.get("rows") or [], key=lambda r: (r[0], r[1]))
        idx = [r[0] for r in rows]
        drawn.update(idx)
        at = f"{label} at scroll {s.get('top')}"
        if not rows:
            if n:
                problems.append(f"{at}: no row drawn, the view has {n}")
            continue
        twice = sorted(i for i, c in Counter(idx).items() if c > 1)
        if twice:
            problems.append(f"{at}: rows {twice[:5]} drawn twice")
        elif idx != list(range(idx[0], idx[0] + len(idx))):
            problems.append(f"{at}: rows {sorted(set(range(idx[0], idx[-1] + 1)) - set(idx))[:5]} missing between drawn rows")
        if idx[0] < 0 or idx[-1] >= n:
            problems.append(f"{at}: drew row {idx[-1] if idx[-1] >= n else idx[0]} of a view of {n}")
        for a, b in zip(rows, rows[1:]):
            if abs(b[1] - a[2]) > TOL:
                problems.append(f"{at}: {b[1] - a[2]:+.1f} px between rows {a[0]} and {b[0]}")
                break
        top, foot = s["band"]
        # WHY not for a view with no columns: a row with no cells has no height to cover a band with (the oracle's
        # dashboard views that read `from:` another dataset, which <data-views> does not load, draw none in both
        # builds); main() reports such a view as having nothing to compare, never as declared changes
        if foot - top > TOL and snap.get("leafOrder"):
            if rows[0][1] > top + TOL:
                problems.append(f"{at}: the band's top is blank from {top} to {rows[0][1]} (row {rows[0][0]} is the first drawn)")
            if rows[-1][2] < foot - TOL and idx[-1] != n - 1:
                problems.append(f"{at}: the band's foot is blank from {rows[-1][2]} to {foot}: row {idx[-1] + 1} of {n} is not drawn")
        planned = s.get("planned")
        if planned is not None and sorted(planned) != idx:
            # an extra consistency check only: the plan is the implementation's, so it never proves what is drawn
            problems.append(f"{at}: drew {idx[:4]}… ({len(idx)}) where its virtualizer planned {sorted(planned)[:4]}… ({len(planned)})")
    read = Counter(r.get("index") for r in snap.get("rows") or [])
    want = sample(n)
    unseen = [i for i in want if i not in drawn or not read[i]]
    if unseen:
        problems.append(f"{label}: {len(unseen)} of the review's {len(want)} sample rows never drawn and read: {unseen[:6]}")
    wanted = set(want)
    for i, c in sorted(read.items(), key=lambda x: (x[0] is None, x[0] or 0)):
        if c > 1:
            problems.append(f"{label}: row {i} read {c} times")
        if i not in wanted:
            problems.append(f"{label}: row {i} read outside the review's sample")
        elif i not in drawn:
            problems.append(f"{label}: row {i} read but drawn at no stop")
    for r in snap.get("rows") or []:
        i = r.get("index")
        if isinstance(i, int) and 0 <= i < n and flat[i] != r.get("id"):
            problems.append(f"{label}: row {i} drew {r.get('id')!r}, the view's row there is {flat[i]!r}")
    return problems


RENAMED = {"med": {"median"}, "avg": {"avg"}, "ave": {"avg"}, "min": {"min"}, "max": {"max"}, "sum": {"sum"}, "ran": {"range"}, "spr": {"range"},
           "cou": {"count"}, "uni": {"unique"}, "fil": {"values", "filled"}, "emp": {"empty"}}
COUNTS = {"cou", "count", "uni", "unique", "fil", "filled", "values", "emp", "empty", "checked", "unchecked"}


def summary_problem(before_text, after_text, meta):
    """None when a typed column's group summary changed only as declared (its name as the Calculate row names it, its
    number written in the column's type), else why not."""
    mb, ma = re.match(r"^(\S+) (.+)$", before_text), re.match(r"^(\S+) (.+)$", after_text)
    if not mb or not ma:
        return "not a summary"
    nb, vb = mb.groups()
    na, va = ma.groups()
    if na != nb and na not in RENAMED.get(nb, set()):
        return f"name {nb!r} -> {na!r}"
    if nb in COUNTS:
        return None if va == vb else "a count changed"
    try:
        parts = [float(x.replace(",", "")) for x in vb.split("–")]
    except ValueError:
        return "an unreadable number"
    try:
        want = "–".join(expect({**meta, "showAs": None}, x) for x in parts)
    except Unsupported as err:
        return f"type {err} cannot be checked"
    return None if va == want else f"expected {want!r}"


def compare(before, after, types):
    """Every undeclared difference between two snapshots of one view, as a list of problems (empty: declared only).
    `types` is the view's typed columns as the input says (input_types(), types_from()): never the after build's own
    metadata (judge r7 #2)."""
    if not after or after.get("error"):
        return ["the after build did not draw this view"]
    if not before or before.get("error"):
        return ["the before build did not draw this view"]
    problems = []
    if before["modelIds"] != after["modelIds"]:
        gone = [x for x in before["modelIds"] if x not in after["modelIds"]]
        new = [x for x in after["modelIds"] if x not in before["modelIds"]]
        problems.append(f"rows differ: removed {gone[:5]}, added {new[:5]}" if gone or new else "rows reordered")
    bh, ah = before["heads"], after["heads"]
    for col in bh:
        if col not in ah:
            problems.append(f"column {col} is missing")
    for col in ah:
        if col not in bh:
            problems.append(f"column {col} is new")
    # the leaf columns' order (judge r6 #4): no reorder is declared
    lb, la = before.get("leafOrder"), after.get("leafOrder")
    if lb is not None and la is not None and lb != la:
        problems.append(f"columns reordered: {lb} -> {la}")
    # the merged headings above them, position by position: the same text, or the same with a column's unit moved onto
    # it as a caption ("Coulomb" -> "Coulomb (N·m)", the declared move); none added, dropped or renamed
    gb, ga = before.get("groupHeads") or [], after.get("groupHeads") or []
    units_b = {(h.get("unit") or "").strip() for h in bh.values()} - {""}
    if len(gb) != len(ga):
        problems.append(f"merged headings {gb} -> {ga}")
    else:
        for x, y in zip(gb, ga):
            m = re.fullmatch(re.escape(x) + r" \(([^)]*)\)", y)
            if x != y and not (m and m.group(1) in units_b):
                problems.append(f"merged heading {x!r} -> {y!r}")
    group_text = " ".join(after.get("groupHeads") or [])
    for col, h in bh.items():
        a = ah.get(col)
        if not a:
            continue
        if a["label"] != h["label"]:
            problems.append(f"column {col}: label {h['label']!r} -> {a['label']!r}")
        ub, ua = (h.get("unit") or "").strip(), (a.get("unit") or "").strip()
        ok = ub == ua or (ub and ua == f"({ub})") or (ub and not ua and ":" in col and f"({ub})" in group_text)
        if not ok:
            problems.append(f"column {col}: unit {ub!r} -> {ua!r}")
    # the rows: the view's every row (group rows too) in the same order in both builds; then each build's own drawing,
    # measured at every stop of its visit (judge r7 #2). How many rows a stop draws is its band's (a taller header
    # leaves room for fewer), so counts are never compared: the band is covered, and the sample is drawn, or not.
    fb, fa = before.get("flatIds"), after.get("flatIds")
    if isinstance(fb, list) and isinstance(fa, list) and fb != fa:
        cb, ca = Counter(fb), Counter(fa)
        gone, extra = list((cb - ca).elements()), list((ca - cb).elements())
        problems.append(f"the view's rows {len(fb)} -> {len(fa)}: missing {gone[:5]}, extra {extra[:5]}" if gone or extra else "the view's rows reordered")
    for label, snap in (("before", before), ("after", after)):
        problems.extend(drawn_problems(label, snap))
    # cells: every row of the review's sample, read in both builds at the same position (the before build's text and
    # stored values are the baseline; a typed cell's expected text and drawing come from the input's types)
    rows_b = {r.get("index"): r for r in before.get("rows") or []}
    rows_a = {r.get("index"): r for r in after.get("rows") or []}
    order = lb or list(bh)
    for i in sample(len(fb) if isinstance(fb, list) else 0):
        rb, ra = rows_b.get(i), rows_a.get(i)
        if rb is None or ra is None:
            continue  # drawn_problems() said which build never drew it
        if rb["id"] != ra["id"]:
            problems.append(f"row {i}: {rb['id']!r} -> {ra['id']!r}")
            continue
        if rb["kind"] != ra["kind"]:
            problems.append(f"row {rb['id']!r}: {rb['kind']} -> {ra['kind']}")
            continue
        if rb["kind"] == "group" and rb.get("label") != ra.get("label"):
            problems.append(f"group {rb['id']!r}: label {rb.get('label')!r} -> {ra.get('label')!r}")
        marks_b, marks_a = rb.get("marks") or {}, ra.get("marks") or {}
        for col in ra["cells"]:
            if col not in rb["cells"]:
                problems.append(f"row {rb['id']!r}: cell {col} is new")
        for col, text in rb["cells"].items():
            if col not in ra["cells"]:
                problems.append(f"row {rb['id']!r}: cell {col} is missing")
                continue
            got = ra["cells"][col]
            mb, ma = marks_b.get(col) or [], marks_a.get(col) or []
            # a typed cell (the input types its column) is held to the independent formatter, and to its type's
            # drawing, whether or not its text moved (judge r6 #4, r7 #2: a typed column drawn untyped is a
            # regression); only a type this review cannot check may stand, unchanged
            meta = types.get(col) if rb["kind"] == "row" and ":" not in col else None
            if meta:
                raw = rb["values"].get(col)
                try:
                    want = expect(meta, raw)
                    if got != want:
                        problems.append(f"row {rb['id']!r}: {col} ({meta['kind']}) {text!r} -> {got!r}, expected {want!r}")
                except Unsupported as err:
                    if got != text:
                        problems.append(f"row {rb['id']!r}: {col} is typed {err}, which this review cannot check: {text!r} -> {got!r}")
                look = drawing(meta, raw)
                look = mb if look is None else look
                if ma != look:
                    problems.append(f"row {rb['id']!r}: {col} ({meta['kind']}) drawn as {ma} where its type draws {look}")
                continue
            # an untyped cell's drawing (pills, bars, labelled images) never moves
            if ma != mb:
                problems.append(f"row {rb['id']!r}: {col} drawn as {mb} -> {ma}")
            if rb["kind"] == "group" and col.startswith("#"):
                # a group summary of a typed column, written in its type: exactly the formatter's text for the same
                # number, also when it reads as before
                k = int(col[1:])
                key = order[k] if k < len(order) else None
                kmeta = types.get(key) if key and ":" not in key else None
                if kmeta and re.match(r"^\S+ .+$", text):
                    why = summary_problem(text, got, kmeta)
                    if why:
                        problems.append(f"group {rb['id']!r}: {key} summary {text!r} -> {got!r} ({why})")
                    continue
            if got == text:
                continue
            if rb["kind"] == "group" and re.sub(SUMMARY, "", text) == re.sub(SUMMARY, "", got):
                continue  # declared: a group summary named as the Calculate row names it, the number the same
            problems.append(f"row {rb['id']!r}: {col} {text!r} -> {got!r}")
    return problems


# ------------------------------------------------------------------------------------------------- the browser half
SNAPSHOT = """async ([CAP, TAIL]) => {
  const v = window.v; const view = v.querySelector('.dv-view');
  const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 30))));
  await frame();
  const t = view && view.querySelector('table');
  const plug = v._plugin, m = plug && plug._model;
  if (!t || !m || !t.tHead || !t.tBodies[0]) return { error: 'no table' };
  const json = (x) => (x === undefined ? null : JSON.parse(JSON.stringify(x)));
  const clean = (e) => { if (!e) return ''; const c = e.cloneNode(true); c.querySelectorAll('.dv-unit, .dv-sortmark, .dv-ticon, .dv-resize, svg').forEach((x) => x.remove()); return c.textContent.replace(/\\s+/g, ' ').trim(); };
  const heads = {};
  for (const th of t.querySelectorAll('thead th[data-col]')) heads[th.dataset.col] = { label: clean(th.querySelector('.dv-th-label') || th.querySelector('.dv-th') || th), unit: ((th.querySelector('.dv-unit') || {}).textContent || '').trim() };
  const groupHeads = [...t.querySelectorAll('thead th:not([data-col])')].map((th) => th.textContent.replace(/\\s+/g, ' ').trim()).filter(Boolean);
  const model = v.model;
  const modelIds = (model.pivot ? model.pivot.rows : model.rows).map((r) => String(r._id ?? r.id));
  // the view's every row in drawn order (group rows too)
  const idOf = (row, i) => (row.getIsGrouped && row.getIsGrouped() ? 'group:' + row.id : String((row.original || {})._id ?? (row.original || {}).id ?? (row.original || {})._heading ?? i));
  const flatIds = m.flat.map(idOf);
  const n = flatIds.length;
  // the review's sample, by position (compare() derives the same from the view's rows): the first CAP, the last TAIL
  const inSample = (i) => i < CAP || i >= n - TAIL;
  // what a typed drawing shows beside its text (judge r7 #2): option and status pills, a bar or ring, a labelled image
  const marks = (td) => [...td.querySelectorAll('.dv-opt, .dv-statuspill, .dv-progress, [role="img"][aria-label]')].map((e) => (
    e.classList.contains('dv-opt') ? 'pill:' + e.textContent.trim()
      : e.classList.contains('dv-statuspill') ? 'status:' + e.textContent.trim()
        : e.classList.contains('dv-progress') ? (e.classList.contains('dv-ring') ? 'ring' : 'bar')
          : 'img:' + e.getAttribute('aria-label')));
  const read = new Map();
  const record = (tr, i) => {
    if (!inSample(i) || read.has(i) || !m.flat[i]) return;
    const row = m.flat[i];
    const tds = [...tr.querySelectorAll(':scope > td:not(.dv-selcol)')];
    const key = (td, k) => td.dataset.col || ('#' + k);
    const cells = Object.fromEntries(tds.map((td, k) => [key(td, k), td.textContent.replace(/\\s+/g, ' ').trim()]));
    const drawn = Object.fromEntries(tds.map((td, k) => [key(td, k), marks(td)]).filter(([, x]) => x.length));
    if (row.getIsGrouped && row.getIsGrouped()) {
      const name = tr.querySelector('.dv-gname');
      read.set(i, { kind: 'group', id: idOf(row, i), index: i, label: name ? name.textContent.trim() : '', cells, marks: drawn, values: {} });
    } else {
      const o = row.original || {};
      const values = {};
      for (const l of m.leaves) { const raw = o[l.id]; values[l.key] = json(l.p.pivot ? (raw ? raw.v : null) : raw); }
      // a tree's path heading has no record behind it (core isHeading): its cells are compared, never typed
      read.set(i, { kind: o._heading !== undefined ? 'heading' : 'row', id: idOf(row, i), index: i, cells, marks: drawn, values });
    }
  };
  // the view's own scroll box: the table's nearest ancestor that scrolls vertically (none: the table does not scroll)
  let sc = t.parentElement;
  while (sc && sc !== v && !/(auto|scroll|overlay)/.test(getComputedStyle(sc).overflowY)) sc = sc.parentElement;
  if (sc === v || !sc) sc = null;
  const r1 = (x) => Math.round(x * 10) / 10;
  const stops = [];
  // one stop, measured: the band a reader sees rows in (the box's client area, within the window, under the sticky
  // header) and every drawn row's box, an open band below a row counted as its row's (padding rows are not rows)
  const measure = () => {
    const box = (sc || t).getBoundingClientRect();
    const top = sc ? box.top + sc.clientTop : box.top;
    const foot = sc ? top + sc.clientHeight : box.bottom;
    // the header: its sticky cells, and its own box while it is in view (a header row with no cells has no cell to measure)
    const head = Math.max(top, t.tHead.getBoundingClientRect().bottom, ...[...t.tHead.querySelectorAll('th')].map((th) => th.getBoundingClientRect().bottom));
    const rows = [];
    let cur = null;
    for (const tr of t.tBodies[0].rows) {
      if (tr.hasAttribute('data-i')) {
        const b = tr.getBoundingClientRect(); const i = Number(tr.dataset.i);
        cur = [i, r1(b.top), r1(b.bottom)]; rows.push(cur); record(tr, i);
      } else if (cur && !tr.classList.contains('dv-pad')) cur[2] = r1(Math.max(cur[2], tr.getBoundingClientRect().bottom));
      else cur = null;
    }
    stops.push({ top: sc ? sc.scrollTop : 0, band: [r1(Math.max(head, 0)), r1(Math.min(foot, innerHeight))], rows, planned: plug._virt ? plug._virt.getVirtualItems().map((x) => x.index) : null });
    return rows.reduce((k, r) => Math.max(k, r[0]), -1);
  };
  let seen = measure();
  if (sc) {
    // down from the top, 0.8 of the band a step (the bands overlap, so every position is seen), until the first CAP
    // rows have been drawn or the box will not scroll further
    for (let k = 0; k < 2000 && seen < Math.min(n, CAP) - 1; k++) {
      const s = stops[stops.length - 1];
      const at = sc.scrollTop;
      sc.scrollTop = at + Math.max(8, Math.floor(0.8 * (s.band[1] - s.band[0])));
      await frame();
      if (sc.scrollTop === at) break;
      seen = Math.max(seen, measure());
    }
    // then the last screen, until it stays put (a redraw at the end can lengthen the table)
    for (let k = 0; k < 6; k++) {
      const at = sc.scrollTop;
      sc.scrollTop = sc.scrollHeight;
      await frame();
      if (sc.scrollTop === at) break;
      measure();
    }
  }
  return { heads, groupHeads, modelIds, flatIds, leafOrder: m.leaves.map((l) => l.key), stops, rows: [...read.values()].sort((a, b) => a.index - b.index) };
}"""


def measured(snap):
    """A build's visit in brief, for the record: its first stop's band (top, foot, height) and rows drawn there, and the
    rows each stop drew (fewest, most). Where a taller header leaves room for fewer rows, this is that room, measured."""
    stops = snap.get("stops") or []
    if not stops:
        return None
    first = stops[0]
    counts = [len(s.get("rows") or []) for s in stops]
    return {"band": [*first["band"], round(first["band"][1] - first["band"][0], 1)], "first stop rows": counts[0], "rows per stop": [min(counts), max(counts)]}


def main():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tests" / "browser"))
    import table_oracle_checks as T  # noqa: PLC0415
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    after_root = pathlib.Path(__file__).resolve().parent.parent
    before_root = pathlib.Path(sys.argv[1]).resolve()
    main_root = pathlib.Path(subprocess.run(["git", "-C", str(after_root), "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True).stdout.strip()).parent
    out_path = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else main_root / "reports" / "media" / "types" / "oracle-review.json"

    def serve(root):
        port = T.free_port()
        proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        for _ in range(80):
            try:
                urllib.request.urlopen(base + "/tests/browser/fixtures/lifecycle.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        return proc, base

    def read_all(root, browser, keys):
        proc, base = serve(root)
        got = {}
        try:
            page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
            page.clock.set_fixed_time("2026-10-27T06:00:00Z")
            page.goto(base + "/tests/browser/fixtures/lifecycle.html")
            page.wait_for_function("() => window.kitReady", timeout=T.WAIT)
            for key in keys:
                case, name = key.split(" :: ", 1)
                if not (root / "gallery" / "examples" / case / "views.base").exists():
                    got[key] = None
                    continue
                page.evaluate(T.MOUNT, [f"/gallery/examples/{case}/views.base", name])
                try:
                    page.wait_for_function("() => window.v.querySelector('.dv-view') && window.v.dataset.view", timeout=T.WAIT)
                    got[key] = page.evaluate(SNAPSHOT, [CAP, TAIL])
                except Exception as err:  # noqa: BLE001
                    got[key] = {"error": str(err).splitlines()[0][:200]}
            page.context.close()
        finally:
            proc.terminate()
        return got

    keys = [k for _, _, k in T.cases()]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        before = read_all(before_root, browser, keys)
        after = read_all(after_root, browser, keys)
        browser.close()
    result, failed = {}, 0
    for key in keys:
        if before.get(key) is None:
            ok_after = after.get(key) and not after[key].get("error")
            result[key] = {"status": "new view" if ok_after else "NEW VIEW DID NOT DRAW", "problems": [] if ok_after else ["did not draw"]}
            failed += 0 if ok_after else 1
            continue
        case, name = key.split(" :: ", 1)
        # the types the input gives this view (the lane's views.base over its data file), never the after build's own
        types = input_types(after_root / "gallery" / "examples" / case, name)
        problems = compare(before[key], after[key], types)
        snap_b, snap_a = before[key], after[key] or {}
        typed = [c for c in snap_b.get("leafOrder") or [] if c in types]
        both = {r.get("index") for r in snap_b.get("rows") or []} & {r.get("index") for r in snap_a.get("rows") or []}
        # a view with no columns in either build draws rows with no cells: nothing a reader sees, so nothing compared
        empty = not snap_b.get("leafOrder") and not snap_a.get("leafOrder") and not snap_b.get("heads") and not snap_a.get("heads")
        status = "UNDECLARED" if problems else NO_COLUMNS if empty else "declared changes only"
        result[key] = {"status": status, "problems": problems, "typed columns checked": typed,
                       "rows compared": len(both & set(sample(len(snap_b.get("flatIds") or [])))), "view rows": len(snap_b.get("flatIds") or []),
                       "model rows": len(snap_b.get("modelIds", [])), "stops": [len(snap_b.get("stops") or []), len(snap_a.get("stops") or [])],
                       "measured": {"before": measured(snap_b), "after": measured(snap_a)}}
        failed += 1 if problems else 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for key, r in result.items():
        stops = "/".join(str(x) for x in r.get("stops") or []) or "-"
        print(f"{r['status']:<22} {key:<52} rows {r.get('rows compared', '-'):>3}/{r.get('view rows', '-'):<5} stops {stops:<7} typed {','.join(r.get('typed columns checked') or []) or '-'}")
        for prob in r["problems"][:4]:
            print(f"    - {prob}")
    print(f"\n{len(result)} views; {sum(1 for r in result.values() if r['status'] == 'declared changes only')} declared changes only; "
          f"{sum(1 for r in result.values() if r['status'] == 'new view')} new; {sum(1 for r in result.values() if r['status'] == NO_COLUMNS)} {NO_COLUMNS} "
          f"(nothing drawn, so nothing reviewed); {failed} with problems; wrote {out_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
