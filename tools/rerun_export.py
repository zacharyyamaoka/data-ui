# /// script
# requires-python = ">=3.11"
# dependencies = ["rerun-sdk==0.40.0", "numpy"]
# ///
"""Write a dashboard's datasets into one Rerun .rrd, with a blueprint mirroring its layout (docs/RERUN.md).

    uv run --script tools/rerun_export.py gallery/examples/dashboard-cards/views.base [--out FILE.rrd]

The "Open in Rerun" backdoor (docs/peps/0005-dashboard-cards.md §6): the same rows the dashboard draws, read from
the same files, logged as one recording on one timeline `t` (the clock's time, a duration in seconds):

  timeseries   /timeseries/<view>/<series>       Scalars on t; rules and band edges as constant series; a
                                                 /timeseries/<view>-log10/... companion when scale: log
  trajectory,  /world/<view>/<series>/path       the full path (static LineStrips3D)
  scene3d      /world/<view>/<series>/marker     the moving point on t (Points3D)
               /world/<view>/<series>/skeleton   the stick robot on t (LineStrips3D), scene3d only
  video,       /video/<value>                    AssetVideo + VideoFrameReference rows on t from the row's t0
  video-compare
  kpi, table   /notes                            the dashboard's numbers as one markdown TextDocument

Default output: <case dir>/rerun/<case>.rrd, or the file's own `rerun: {rrd}`. What Rerun cannot draw (the stat
cards, Vega charts, images, the wipe/onion overlay, dashes, annotations) is listed in /notes, never dropped silently.

WHY a build-time `uv run` script: rerun-sdk is 100+ MB of wheels and must never become a runtime dependency of
data-ui; one pin (SDK_VERSION) has to match the viewer that opens the file, so it lives here and in docs/RERUN.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import re
import sys

import numpy as np
import rerun as rr
import rerun.blueprint as rrb

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "packages" / "core" / "python"))
from data_ui_base import loads  # noqa: E402

SDK_VERSION = "0.40.0"
MAX_BYTES = 25 * 1024 * 1024  # Cloudflare's per-file cap: past it a static site cannot serve the .rrd

# Rerun's UI is dark, so unnamed series take the dark theme's series slots (packages/core/styles/tokens.css) through
# the same hueOf as seriesColor(); the dashboard's style.palette wins by name, as in the cards.
DARK_SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
TONES = {"bad": "#e66767", "good": "#199e70", "warn": "#f0a070", "muted": "#8b9099", "neutral": "#8b9099"}


# ---- the dashboard's rows, as data-ui reads them

def slug(text) -> str:
    """format.js slug(): the same entity names a reader sees in the dashboard's panel ids."""
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", str(text).lower()))


def cell_value(v):
    """grammar.js cellValue(): a {value, unit, basis, ...} cell is its value."""
    return v["value"] if isinstance(v, dict) and "value" in v else v


def hue_of(text) -> int:
    h = 0
    for c in str(text):
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return h % 8 + 1


def rgb(hex_colour: str) -> list[int]:
    h = hex_colour.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


class Unsupported(ValueError):
    pass


TOKEN = re.compile(r'\s*(?:(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)|("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')|(==|!=|>=|<=|&&|\|\||[()!<>])|([A-Za-z_]\w*))')


def compile_expression(src: str):
    """The subset of Bases' filter grammar the gallery cases use: property == / != / < / > / <= / >= literal,
    joined by && || ! and parentheses. Anything else (method calls, file.*, formulas, dates) raises Unsupported."""
    tokens, at = [], 0
    while at < len(src):
        m = TOKEN.match(src, at)
        if not m or m.end() == at:
            if src[at:].strip():
                raise Unsupported(f"filter {src!r}: cannot read {src[at:].strip()[:20]!r} (only ==, !=, <, >, &&, ||, !)")
            break
        at = m.end()
        number, string, op, name = m.groups()
        if number is not None:
            tokens.append(("lit", float(number) if "." in number or "e" in number.lower() else int(number)))
        elif string is not None:
            tokens.append(("lit", json.loads(string) if string[0] == '"' else string[1:-1].replace("\\'", "'")))
        elif op is not None:
            tokens.append(("op", op))
        elif name in ("true", "false", "null"):
            tokens.append(("lit", {"true": True, "false": False, "null": None}[name]))
        else:
            tokens.append(("name", name))
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else (None, None)

    def take(kind, value=None):
        nonlocal pos
        k, v = peek()
        if k != kind or (value is not None and v != value):
            raise Unsupported(f"filter {src!r}: expected {value or kind} at token {pos + 1}")
        pos += 1
        return v

    def disjunction():
        left = conjunction()
        while peek() == ("op", "||"):
            take("op")
            right = conjunction()
            left = (lambda a, b: lambda r: a(r) or b(r))(left, right)
        return left

    def conjunction():
        left = negation()
        while peek() == ("op", "&&"):
            take("op")
            right = negation()
            left = (lambda a, b: lambda r: a(r) and b(r))(left, right)
        return left

    def negation():
        if peek() == ("op", "!"):
            take("op")
            inner = negation()
            return lambda r: not inner(r)
        return comparison()

    def operand():
        kind, value = peek()
        if kind == "op" and value == "(":
            take("op")
            inner = disjunction()
            take("op", ")")
            return inner
        if kind == "name":
            take("name")
            if peek() == ("op", "("):
                raise Unsupported(f"filter {src!r}: function calls are not supported")
            return lambda r, n=value: cell_value(r.get(n))
        if kind == "lit":
            take("lit")
            return lambda r, v=value: v
        raise Unsupported(f"filter {src!r}: unexpected {value!r}")

    compare = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b, "<": lambda a, b: a < b, ">": lambda a, b: a > b,
               "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b}

    def comparison():
        left = operand()
        kind, value = peek()
        if kind == "op" and value in compare:
            take("op")
            right = operand()
            fn = compare[value]

            def test(r, a=left, b=right, fn=fn):
                x, y = a(r), b(r)
                if value not in ("==", "!=") and (x is None or y is None):
                    return False
                try:
                    return fn(x, y)
                except TypeError:
                    return False
            return test
        return lambda r: bool(left(r))

    keep = disjunction()
    if pos != len(tokens):
        raise Unsupported(f"filter {src!r}: unexpected {tokens[pos][1]!r}")
    return keep


def compile_filters(f):
    """A Bases filters value: an expression string, or {and | or | not: [...]} of them; None keeps every row."""
    if f is None or f == "":
        return None
    if isinstance(f, str):
        return compile_expression(f)
    if isinstance(f, dict) and len(f) == 1:
        (key, items), = f.items()
        parts = [p for p in (compile_filters(x) for x in (items or [])) if p]
        if key == "and":
            return lambda r: all(p(r) for p in parts)
        if key == "or":
            return lambda r: any(p(r) for p in parts)
        if key == "not":
            return lambda r: not any(p(r) for p in parts)
    raise Unsupported(f"filters {f!r}: not an expression or {{and | or | not: [...]}}")


def load_case(base_path: pathlib.Path):
    """The .base and every dataset it names, the way dashboard/src/model.js readDashboard() resolves them."""
    base = loads(base_path.read_text(encoding="utf-8"))
    given = base.get("datasets") or {}
    datasets, default_name = {}, None
    for name, entry in given.items():
        d = {"data": entry} if isinstance(entry, str) else dict(entry or {})
        datasets[name] = {"name": name, "data": d["data"], "filters": d.get("filters")}
        if base.get("data") and d["data"] == base["data"]:
            default_name = name
    if base.get("data") and not default_name:
        default_name = pathlib.Path(base["data"]).stem
        datasets[default_name] = {"name": default_name, "data": base["data"], "filters": None}
    if default_name and datasets[default_name]["filters"] is None:
        datasets[default_name]["filters"] = base.get("filters")
    for d in datasets.values():
        path = base_path.parent / d["data"]
        doc = json.loads(path.read_text(encoding="utf-8"))
        d["path"] = path
        d["rows"] = doc["rows"] if isinstance(doc, dict) else doc
        d["properties"] = (doc.get("properties") if isinstance(doc, dict) else None) or {}
    return base, datasets, default_name


def view_rows(view, datasets, default_name):
    """The view's rows after its dataset's filters and its own, then `sort` (rowmodel.js, minus search)."""
    d = datasets[view.get("from") or default_name]
    rows = d["rows"]
    for f in (d["filters"], view.get("filters")):
        keep = compile_filters(f)
        if keep:
            rows = [r for r in rows if keep(r)]
    for s in reversed(view.get("sort") or []):
        prop = s.get("property")
        present = [r for r in rows if cell_value(r.get(prop)) is not None]
        missing = [r for r in rows if cell_value(r.get(prop)) is None]
        rows = sorted(present, key=lambda r: cell_value(r.get(prop)), reverse=str(s.get("direction", "ASC")).upper() == "DESC") + missing
    if view.get("limit"):
        rows = rows[: int(view["limit"])]
    return d, rows


def series_colour(name, palette):
    return rgb(palette.get(name) or DARK_SERIES[hue_of(name) - 1])


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def as_instant(v):
    """A date cell (ISO text) as numpy datetime64[ns] in UTC, or None."""
    if not isinstance(v, str):
        return None
    try:
        when = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is not None:
        when = when.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return np.datetime64(when, "ns")


# ---- logging, one card type at a time

class Export:
    def __init__(self, base_path: pathlib.Path):
        self.base_path = base_path
        self.base, self.datasets, self.default_name = load_case(base_path)
        clock = self.base.get("clock") or {}
        self.timeline = clock.get("time") or "t"
        self.clock = clock
        self.palette = (self.base.get("style") or {}).get("palette") or {}
        self.views = {v.get("name"): v for v in self.base.get("views") or [] if isinstance(v, dict)}
        self.skipped: list[str] = []      # "view: why" for /notes and stdout
        self.videos: dict[str, dict] = {}  # entity -> its clip, logged once however many cards show it
        self.entities: list[str] = []
        self.ops: list = []  # the log calls, replayed after save(): Rerun wants its sink set before anything is logged

    def log(self, *args, **kwargs):
        self.ops.append(("log", args, kwargs))

    def send(self, *args, **kwargs):
        self.ops.append(("send_columns", args, kwargs))

    def time_column(self, values, column):
        """(timeline name, TimeColumn) for a column of times: seconds on the clock's timeline, or dates on `date`."""
        if all(is_number(v) for v in values):
            return column, rr.TimeColumn(column, duration=np.asarray(values, dtype=float))
        instants = [as_instant(v) for v in values]
        if all(i is not None for i in instants):
            return "date", rr.TimeColumn("date", timestamp=np.asarray(instants, dtype="datetime64[ns]"))
        raise Unsupported(f"time column {column!r} is neither seconds nor ISO dates")

    def timeseries(self, view):
        spec = view.get("timeseries") or {}
        d, rows = view_rows(view, self.datasets, self.default_name)
        x = spec.get("x") or self.timeline
        ys = spec.get("y") if isinstance(spec.get("y"), list) else [spec.get("y")]
        split = spec.get("series")
        name = view["name"]
        root = f"/timeseries/{slug(name)}"
        log_root = f"{root}-log10"
        unit = spec.get("unit") or (d["properties"].get(ys[0]) or {}).get("unit")
        groups: dict[str, list] = {}
        for r in rows:
            for y in ys:
                label = (f"{cell_value(r.get(split))} · {y}" if len(ys) > 1 else str(cell_value(r.get(split)))) if split else y
                groups.setdefault(label, []).append((cell_value(r.get(x)), cell_value(r.get(y))))
        timeline_used = None
        span = []
        for label, pairs in groups.items():
            pairs = [(t, v) for t, v in pairs if t is not None and is_number(v)]
            if not pairs:
                continue
            pairs.sort(key=lambda p: (as_instant(p[0]) if isinstance(p[0], str) else p[0]))
            timeline_used, index = self.time_column([p[0] for p in pairs], x)
            values = np.asarray([p[1] for p in pairs], dtype=float)
            colour = series_colour(label.split(" · ")[0], self.palette)
            path = f"{root}/{slug(label)}"
            self.log(path, rr.SeriesLines(colors=[colour], names=[label]), static=True)
            self.send(path, indexes=[index], columns=rr.Scalars.columns(scalars=values))
            self.entities.append(path)
            span += [pairs[0][0], pairs[-1][0]]
            if spec.get("scale") == "log":
                # WHY a companion series: Rerun has no log axis (issue #6773); log10|y| is labelled as what it is
                lpath = f"{log_root}/{slug(label)}"
                with np.errstate(divide="ignore"):
                    logged = np.where(values != 0, np.log10(np.abs(values)), np.nan)
                self.log(lpath, rr.SeriesLines(colors=[colour], names=[f"log10 |{label}|"]), static=True)
                self.send(lpath, indexes=[index], columns=rr.Scalars.columns(scalars=logged))
                self.entities.append(lpath)
        if not span:
            self.skipped.append(f"{name}: no numeric samples after its filters")
            return []
        lo = min(span, key=lambda t: as_instant(t) if isinstance(t, str) else t)
        hi = max(span, key=lambda t: as_instant(t) if isinstance(t, str) else t)
        # rules and the edges of y bands: constant series over the view's span (Rerun has no rule or band mark)
        # an unlabelled rule is named by its value, "y = -5" -> rules/y-minus-5, so y = 5 and y = -5 stay apart
        constants = [(r.get("label") or f"y = {r['y']:g}", r.get("label") or f"y {'minus ' if r['y'] < 0 else ''}{abs(r['y']):g}", r["y"], r.get("tone"))
                     for r in spec.get("rules") or [] if is_number(r.get("y"))]
        for b in spec.get("bands") or []:
            if isinstance(b.get("y"), list) and len(b["y"]) == 2:
                for edge, v in zip(("low", "high"), b["y"]):
                    label = f"{b.get('label') or 'band'} ({edge})"
                    constants.append((label, label, v, b.get("tone")))
            elif b.get("x") is not None:
                self.skipped.append(f"{name}: x band {b.get('label') or b['x']} (no shaded time span in Rerun)")
        for label, key, value, tone in constants:
            path = f"{root}/rules/{slug(key)}"
            _, index = self.time_column([lo, hi], x)
            self.log(path, rr.SeriesLines(colors=[rgb(TONES.get(tone or "muted", TONES["muted"]))], names=[label]), static=True)
            self.send(path, indexes=[index], columns=rr.Scalars.columns(scalars=np.asarray([value, value], dtype=float)))
            self.entities.append(path)
        for key in ("dash", "annotations"):
            if spec.get(key):
                self.skipped.append(f"{name}: {key} (no Rerun equivalent; the data is all there)")
        if spec.get("scale") == "symlog":
            self.skipped.append(f"{name}: symlog scale (drawn linear; Rerun has no log axis, #6773)")
        title = f"{name}" + (f" [{unit}]" if unit else "") + (f" · timeline {timeline_used}" if timeline_used != self.timeline else "")
        out = [rrb.TimeSeriesView(origin=root, name=title)]
        if spec.get("scale") == "log":
            out.append(rrb.TimeSeriesView(origin=log_root, name=f"{name} · log10 |y| (Rerun has no log axis)"))
        return out

    def path3d(self, view):
        kind = view["type"]
        spec = view.get(kind) or {}
        d, rows = view_rows(view, self.datasets, self.default_name)
        name = view["name"]
        root = f"/world/{slug(name)}"
        cols = [spec.get("x"), spec.get("y"), spec.get("z")] if kind == "scene3d" else [spec.get("x"), spec.get("y")]
        t_col = spec.get("t") or self.timeline
        split = spec.get("series")
        self.log(root, rr.ViewCoordinates.RIGHT_HAND_Z_UP, static=True)
        groups: dict[str, list] = {}
        for r in rows:
            groups.setdefault(str(cell_value(r.get(split))) if split else name, []).append(r)
        everything = []
        for label, members in groups.items():
            members = [r for r in members if all(is_number(cell_value(r.get(c))) for c in cols)]
            if not members:
                continue
            members.sort(key=lambda r: cell_value(r.get(t_col)) if is_number(cell_value(r.get(t_col))) else 0)
            # a 2D trajectory lies in the z = 0 plane, seen from above: x right, y up, as the card draws it
            points = np.asarray([[cell_value(r.get(c)) for c in cols] + ([] if kind == "scene3d" else [0.0]) for r in members], dtype=float)
            everything.append(points)
            colour = series_colour(label, self.palette)
            base = f"{root}/{slug(label)}"
            self.log(f"{base}/path", rr.LineStrips3D([points], colors=[colour], radii=rr.Radius.ui_points(1.5 if label != spec.get("target") else 1.0), labels=[label]), static=True)
            self.entities.append(f"{base}/path")
            times = [cell_value(r.get(t_col)) for r in members]
            if all(is_number(t) for t in times):
                index = rr.TimeColumn(t_col, duration=np.asarray(times, dtype=float))
                self.send(f"{base}/marker", indexes=[index], columns=rr.Points3D.columns(positions=points))
                self.log(f"{base}/marker", rr.Points3D.from_fields(colors=[colour], radii=rr.Radius.ui_points(6.0)), static=True)
                self.entities.append(f"{base}/marker")
                if kind == "scene3d" and spec.get("skeleton"):
                    joints = spec["skeleton"]
                    strips, at = [], []
                    for r, t in zip(members, times):
                        strip = [[cell_value(r.get(c)) for c in joint] for joint in joints]
                        if all(all(is_number(v) for v in p) for p in strip):
                            strips.append(strip)
                            at.append(t)
                    if strips:
                        index = rr.TimeColumn(t_col, duration=np.asarray(at, dtype=float))
                        self.send(f"{base}/skeleton", indexes=[index], columns=rr.LineStrips3D.columns(strips=np.asarray(strips, dtype=float)).partition([1] * len(strips)))
                        self.log(f"{base}/skeleton", rr.LineStrips3D.from_fields(colors=[colour], radii=rr.Radius.ui_points(2.5)), static=True)
                        self.entities.append(f"{base}/skeleton")
            else:
                self.skipped.append(f"{name}: series {label} has no numeric {t_col}, so no moving marker")
        for key in ("tolerance", "color", "trail"):
            if spec.get(key) not in (None, False):
                self.skipped.append(f"{name}: {key} (the card draws it; Rerun shows the raw paths)")
        if not everything:
            self.skipped.append(f"{name}: no rows with numeric {', '.join(cols)}")
            return []
        allp = np.concatenate(everything)
        centre = (allp.min(axis=0) + allp.max(axis=0)) / 2
        reach = float(np.max(allp.max(axis=0) - allp.min(axis=0))) or 1.0
        if kind == "scene3d":
            eye = rrb.EyeControls3D(kind="Orbital", position=centre + np.array([1.2, -1.6, 0.9]) * reach, look_target=centre, eye_up=[0.0, 0.0, 1.0])
            title = f"{name} · z up"
        else:
            eye = rrb.EyeControls3D(kind="Orbital", position=centre + np.array([0.0, 0.0, 2.0 * reach]), look_target=centre, eye_up=[0.0, 1.0, 0.0])
            title = f"{name} · x = {cols[0]}, y = {cols[1]}, seen from above"
        return [rrb.Spatial3DView(origin=root, name=title, eye_controls=eye)]

    def video(self, view):
        kind = view["type"]
        d, rows = view_rows(view, self.datasets, self.default_name)
        name = view["name"]
        if kind == "video":
            spec = view.get("video") or {}
            src, key = spec.get("src") or "src", spec.get("label")
            chosen = rows[:1]  # the card shows the first row its filters leave
        else:
            spec = view.get("overlay") or {}
            src, key = "src", spec.get("by")
            by = key

            def pick(value, fallback):
                if value is None:
                    return rows[fallback] if len(rows) > fallback else None
                return next((r for r in rows if cell_value(r.get(by)) == value), None)
            chosen = [r for r in (pick(spec.get("a"), 0), pick(spec.get("b"), 1)) if r]
            if spec.get("mode", "wipe") != "side":
                self.skipped.append(f"{name}: {spec.get('mode', 'wipe')} overlay (Rerun shows the two clips side by side)")
        out = []
        for r in chosen:
            file = cell_value(r.get(src))
            if not file:
                self.skipped.append(f"{name}: a row with no {src}")
                continue
            label = str(cell_value(r.get(key))) if key and cell_value(r.get(key)) is not None else pathlib.Path(file).stem
            entity = f"/video/{slug(label)}"
            # media paths resolve against the data file (CONTRACT §1 amendment), not the page
            path = (d["path"].parent / file).resolve()
            if entity not in self.videos:
                if not path.exists():
                    self.skipped.append(f"{name}: {file} is missing")
                    continue
                asset = rr.AssetVideo(path=path)
                self.log(entity, asset, static=True)
                nanos = asset.read_frame_timestamps_nanos()
                t0 = cell_value(r.get("t0"))
                t0 = float(t0) if is_number(t0) else 0.0
                self.send(entity, indexes=[rr.TimeColumn(self.timeline, duration=t0 + nanos / 1e9)],
                                 columns=rr.VideoFrameReference.columns_nanos(nanos))
                self.videos[entity] = {"row": r, "frames": len(nanos), "file": file}
                self.entities.append(entity)
            basis = cell_value(r.get("basis"))
            out.append(rrb.Spatial2DView(origin=entity, name=f"{name} · {label}" + (f" ({basis})" if basis else "")))
        return out

    def numbers(self, view):
        """A kpi or table card's rows as markdown: the dashboard's numbers as data."""
        d, rows = view_rows(view, self.datasets, self.default_name)
        props = d["properties"]
        label_of = lambda p: ((self.base.get("properties") or {}).get(p) or {}).get("displayName") or (props.get(p) or {}).get("displayName") or p

        def text(v, p):
            raw = v
            v = cell_value(v)
            if v is None:
                why = raw.get("why") if isinstance(raw, dict) else None
                return "—" + (f" ({why})" if why else "")
            unit = (raw.get("unit") if isinstance(raw, dict) else None) or (props.get(p) or {}).get("unit")
            return f"{v} {unit}" if unit and is_number(v) else str(v)

        if view["type"] == "kpi":
            spec = view.get("kpi") or {}
            prop = (spec.get("value") or {}).get("property")
            lines = [f"### {view['name']}", "", f"| {spec.get('label') or label_of(prop)} | target | better | basis | source |", "|---|---|---|---|---|"]
            for r in rows:
                cell = r.get(prop)
                meta = cell if isinstance(cell, dict) else {}
                better = (spec.get("compare") or {}).get("better", "")
                lines.append(f"| {text(cell, prop)} | {spec.get('target', '—')} | {better} | {meta.get('basis', '—')} | {meta.get('source', '—')} |")
            return "\n".join(lines)
        cols = view.get("order") or [p for p, meta in props.items() if not (meta or {}).get("hidden")]
        lines = [f"### {view['name']}", "", "| " + " | ".join(label_of(c) for c in cols) + " |", "|" + "---|" * len(cols)]
        for r in rows:
            lines.append("| " + " | ".join(text(r.get(c), c).replace("|", "\\|") for c in cols) + " |")
        return "\n".join(lines)

    def run(self, out_path: pathlib.Path) -> None:
        case = self.base_path.parent.name
        panels = [p for p in ((self.base.get("layout") or {}).get("panels") or []) if isinstance(p, dict)]
        order = [p["view"] for p in panels if p.get("view")] or list(self.views)
        texts = [p["text"] for p in panels if p.get("text")]
        rows3d, rows_ts, rows_video, notes = [], [], [], []
        for view_name in order:
            view = self.views.get(view_name)
            if not view:
                self.skipped.append(f"{view_name}: no view by that name")
                continue
            kind = view.get("type")
            try:
                if kind == "timeseries":
                    rows_ts += self.timeseries(view)
                elif kind in ("trajectory", "scene3d"):
                    rows3d += self.path3d(view)
                elif kind in ("video", "video-compare"):
                    rows_video += self.video(view)
                elif kind in ("kpi", "table"):
                    notes.append(self.numbers(view))
                elif kind != "playback":
                    self.skipped.append(f"{view_name}: a {kind} card (not exported: Rerun has no equivalent view)")
            except Unsupported as err:
                self.skipped.append(f"{view_name}: {err}")
        if not (rows3d or rows_ts or rows_video or notes):
            raise SystemExit(f"{self.base_path}: nothing to export (no layout panels Rerun can show)")

        doc = "\n\n".join(texts + [f"Exported from `{self.base_path.name}` by tools/rerun_export.py (rerun-sdk {SDK_VERSION}).", *notes])
        if self.skipped:
            doc += "\n\n### Not in this recording\n\n" + "\n".join(f"- {s}" for s in self.skipped)
        self.log("/notes", rr.TextDocument(doc, media_type=rr.MediaType.MARKDOWN), static=True)
        self.entities.append("/notes")

        sections = []
        if rows3d:
            sections.append(rrb.Horizontal(*rows3d))
        if rows_ts:
            sections.append(rrb.Horizontal(*rows_ts))
        if rows_video:
            sections.append(rrb.Horizontal(*rows_video))
        sections.append(rrb.TextDocumentView(origin="/notes", name="Notes · the dashboard's numbers"))
        blueprint = rrb.Blueprint(
            rrb.Vertical(*sections),
            # WHY expanded on t: the time panel is the clock's scrubber, the one control every card shares
            rrb.TimePanel(state="expanded", timeline=self.timeline, fps=float(self.clock.get("fps") or 30),
                          playback_speed=float(self.clock.get("rate") or 1)),
            rrb.SelectionPanel(state="collapsed"),
            collapse_panels=False,
        )
        # The blueprint is saved into the .rrd itself, so the file is the whole backdoor (no separate .rbl to serve);
        # the sink is set before anything is logged so no data goes to the default sink.
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # WHY a hyphen: 0.40 migrates an id with "/" or "." to a hashed one ("data-ui/x" -> "data-ui-x3a92")
        rec = rr.RecordingStream(f"data-ui-{case}")
        rec.save(out_path, default_blueprint=blueprint)
        # WHY the case first: Rerun's recording list truncates long names (the bake-off, 2026-10-24)
        rec.send_recording_name(f"{case} · {self.base_path.name}")
        for method, args, kwargs in self.ops:
            getattr(rec, method)(*args, **kwargs)
        rec.flush()
        rec.disconnect()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base", type=pathlib.Path, help="a dashboard .base file (one with layout:)")
    parser.add_argument("--out", type=pathlib.Path, help="the .rrd to write (default: rerun.rrd from the file, else <case>/rerun/<case>.rrd)")
    args = parser.parse_args(argv)
    base_path = args.base.resolve()
    export = Export(base_path)
    if not export.base.get("layout"):
        print(f"{args.base}: not a dashboard (no layout:)", file=sys.stderr)
        return 2
    pinned = (export.base.get("rerun") or {}).get("sdk")
    if pinned and pinned != SDK_VERSION:
        print(f"{args.base}: rerun.sdk is {pinned}, this exporter writes {SDK_VERSION}; the viewer must match the file", file=sys.stderr)
        return 2
    declared = (export.base.get("rerun") or {}).get("rrd")
    out = args.out or (base_path.parent / declared if declared else base_path.parent / "rerun" / f"{base_path.parent.name}.rrd")
    out = out.resolve()
    export.run(out)
    size = out.stat().st_size
    print(f"wrote {out} ({size / 2**20:.2f} MiB, {len(export.entities)} entities, rerun-sdk {SDK_VERSION})")
    for entity in export.entities:
        print(f"  {entity}")
    for why in export.skipped:
        print(f"  not exported: {why}")
    if size > MAX_BYTES:
        print(f"warning: {out.name} is over 25 MiB: a static host (Cloudflare) will not serve it; leave the video out", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
