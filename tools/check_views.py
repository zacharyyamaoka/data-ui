#!/usr/bin/env python3
"""data-ui check: validate .base view files, for people and for agents (docs/SPEC.md §5.7).

    python3 tools/check_views.py FILE.base [FILE.base ...] [--data DATA.json] [--quiet]

Each problem is one line, `file:line: error|warning: path: message`, with a "did you mean ...?" when a name is close
to a real one. In order:

  1. the YAML parses;
  2. it matches schemas/view.schema.json (Obsidian Bases keys plus data-ui's extensions);
  3. unknown keys and unknown view types are warnings, with a suggestion (Bases allows extra keys, so they are
     never errors, but a typo is the most common mistake an agent makes);
  4. with --data, every property a view names exists in the data: order, sort, groupBy, splitBy, value,
     display, the chart's encoded fields, guides, the kpi block, the rail's facets and the filter expressions;
  5. the rail's own rules: a facet names what it filters, and with --data its kind fits the property's type;
  6. `open:` (how a record opens): with --data that names no linkProperty, link with no url: warns that it falls back
     to side;
  7. a group level's time grain (`by:`) on a property the data does not type as a date warns;
  8. the grouped gallery (CONTRACT §20): `grouping:` names a `groupings:` entry, ids are unique, a level groups by
     `bins:` or `by:` (not both), and bins on a property the data does not type as a number warn;
  9. the 3D cards (CONTRACT §32): a refused projection, decay or axes says what was probably meant, a projection's
     vectors make a view, a layer names a dataset the file has, and with --data every column a layer, the trajectory
     binding (given or by default) and voxels read exists. WHY only the default dataset's columns here: this proof has
     no dashboard model, so a view with `from:` or a layer with `data:` is the Node checker's to name;
 10. navigation (CONTRACT §33): selected: needs select:; the file's own data: names one file; a dataset read per pick
     (data: runs/{run}.json) is not on a timer or live, a link ends on each of its placeholders, and a link into it is
     written one-way (a warning). The per-pick files' columns and a literal selected: value are the Node checker's.

Exit status 1 on any error; warnings never fail. Needs PyYAML and jsonschema.

WHY this is the proof version, in Python: both libraries are already on this machine, so the proof needs no install.
The shipped checker is a Node CLI that imports the same grammar.js the element runs, so the browser and the checker
can never disagree about what an expression means (SPEC §5.7). This one checks shape and names, not expression
semantics.
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import pathlib
import re
import sys

import jsonschema
import yaml

HERE = pathlib.Path(__file__).resolve().parent
SCHEMA = json.loads((HERE.parent / "schemas" / "view.schema.json").read_text(encoding="utf-8"))

BASES_TOP = {"filters", "formulas", "properties", "summaries", "views", "display", "newItemFolder", "newItemTemplate"}
DATA_UI_TOP = {"facets", "data", "open", "datasets", "links", "layout", "clock", "style", "rerun", "retention", "defaultView", "sharedColumns", "before", "after", "summary", "page"}  # dashboards: PEP 0004 (CONTRACT §17) / 0005 (§25); retention: live data, PEP 0012 (§26)
# WHY read from the schema: the schema is the one list of view keys and types (docs/CONTRACT.md §5); the Node
# checker reads the same lists, so a key a view lane adds there is known to both at once
VIEW_KEYS = set(SCHEMA["$defs"]["view"]["properties"])
VIEW_TYPES = set(SCHEMA["$defs"]["view"]["properties"]["type"]["examples"])
KEYWORDS = {"true", "false", "null", "this", "and", "or", "not"}


class Lines:
    """Line numbers for a parsed document: path tuple -> 1-based line, from PyYAML's node tree."""

    def __init__(self, text: str):
        self.at: dict[tuple, int] = {}
        try:
            root = yaml.compose(text, Loader=yaml.SafeLoader)
        except yaml.YAMLError:
            root = None
        if root is not None:
            self._walk(root, ())

    def _walk(self, node, path):
        self.at[path] = node.start_mark.line + 1
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                child = path + (key.value,)
                self.at[child] = key.start_mark.line + 1
                self._walk(value, child)
                self.at[child] = key.start_mark.line + 1
        elif isinstance(node, yaml.SequenceNode):
            for index, value in enumerate(node.value):
                self._walk(value, path + (index,))

    def line(self, path) -> int:
        path = tuple(path)
        while path and path not in self.at:
            path = path[:-1]
        return self.at.get(path, 1)


def show(path) -> str:
    out = ""
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out or "(file)"


def suggest(word: str, choices) -> str:
    words = sorted(map(str, choices))
    match = [c for c in words if c.lower() == str(word).lower()][:1]  # 'AND' -> 'and', 'groupby' -> 'groupBy'
    match = match or difflib.get_close_matches(str(word), words, n=1, cutoff=0.72)
    if not match:  # 'logarithmic' -> 'log': a choice the word starts with
        match = [c for c in words if len(c) >= 3 and str(word).lower().startswith(c.lower())][:1]
    return f" (did you mean '{match[0]}'?)" if match else ""


PRIORITY = {"additionalProperties": 3, "enum": 3, "const": 3, "required": 1, "type": 0}


def deepest(error: jsonschema.ValidationError) -> jsonschema.ValidationError:
    """For oneOf/anyOf, the branch error that says the most: an unknown key or a wrong choice, at the deepest path.
    WHY not jsonschema's best_match: it picked "must be string" for {AND: [...]}, the branch the user never meant;
    a type mismatch at the parent's own level only says which branch was NOT intended."""
    if error.validator not in ("oneOf", "anyOf") or not error.context:
        return error
    flat, stack = [], list(error.context)
    while stack:
        e = stack.pop()
        if e.validator in ("oneOf", "anyOf") and e.context:
            stack.extend(e.context)
        else:
            flat.append(e)
    depth = len(error.absolute_path)
    # every branch only says "needs <key>" (a chart's encoding, mark or layer): the composite's own sentence names all
    if flat and all(e.validator == "required" and len(e.absolute_path) == depth for e in flat):
        return error
    def score(e):
        own_level_type = e.validator == "type" and len(e.absolute_path) == depth
        return (not own_level_type, len(e.absolute_path), PRIORITY.get(e.validator, 2))
    return max(flat, key=score) if flat else error


def schema_message(error: jsonschema.ValidationError) -> str:
    """One readable sentence for a schema error, instead of jsonschema's dump of the instance."""
    validator, value = error.validator, error.instance
    if validator == "enum":
        return f"{json.dumps(value)} is not one of {', '.join(map(str, error.validator_value))}{suggest(value, error.validator_value)}"
    if validator == "required":
        missing = [name for name in error.validator_value if not (isinstance(value, dict) and name in value)]
        return f"needs {', '.join(repr(m) for m in missing)}"
    if validator == "additionalProperties":
        allowed = set(error.schema.get("properties", {}))
        if allowed and allowed <= {"and", "or", "not"}:  # one branch of a filter's oneOf: offer all three
            allowed = {"and", "or", "not"}
        extra = [k for k in value if k not in allowed] if isinstance(value, dict) else []
        return "; ".join(f"unknown key '{k}'{suggest(k, allowed)}" for k in extra) or error.message
    if validator == "anyOf" and error.schema.get("anyOf") == [{"required": ["properties"]}, {"required": ["view"]}]:
        return "a record section needs 'properties' (its fields) or a 'view' (an inline view of the peeked row's evidence)"
    if validator in ("minItems", "maxItems") and list(error.absolute_path)[-2:-1] == ["limits"]:  # a $ref leaves no name in schema_path
        return "a limits side is a pair [low, high]: a number, a property, or null for no limit on that end"
    if validator == "oneOf" and "filters" in (error.schema.get("description") or "").lower() + "".join(map(str, error.schema_path)):
        return "a filter is an expression string, or exactly one of and / or / not over a list of filters"
    if validator == "type":
        return f"must be {error.validator_value}, not {type(value).__name__}"
    if validator == "not":
        return "a chart block must not carry data, datasets, $schema or config: data-ui supplies the rows and the theme"
    if validator == "anyOf" and error.schema.get("anyOf") == [{"required": ["mark"]}, {"required": ["layer"]}, {"required": ["encoding"]}]:
        return "a chart needs an encoding (Show Me picks the mark), a mark, or a layer of marks"
    if validator == "anyOf" and error.schema.get("anyOf") == [{"required": ["x", "y", "z"]}, {"required": ["layers"]}]:
        return "a scene3d needs x, y and z (a path), or layers"
    return error.message


# ------------------------------------------------------------------------------------------------ 3D (CONTRACT §32)
# The Node checker's sceneMessage / sceneProblems / sceneNames, sentence for sentence.

SCENE_BLOCKS = ("scene3d", "trajectory3d", "voxels")
FACES = ["perspective", "top", "bottom", "front", "back", "left", "right"]
OBLIQUE = "{dir: [-1, -1, -1], up: [0, 0, 1]}"
# WHY a table, not only the spelling distance: the words CAD tools and drafting use for a view ("iso", "plan", "xz")
# are far from the face that shows it, and an agent writes them. A view no face has (diagonal, isometric) is a {dir}.
PROJECTION_WORDS = {
    **dict.fromkeys(["diagonal", "oblique", "iso", "isometric", "axonometric", "corner", "three-quarter", "home"], OBLIQUE),
    **dict.fromkeys(["plan", "above", "overhead", "xy", "top-down", "topdown", "ortho", "orthographic", "2d"], "top"),
    **dict.fromkeys(["below", "underneath", "under"], "bottom"),
    **dict.fromkeys(["xz", "elevation"], "front"),
    **dict.fromkeys(["yz", "side"], "right"),
    **dict.fromkeys(["3d", "persp", "orbit", "free"], "perspective"),
}
INF_WORDS = {"inf", ".inf", "+inf", "+.inf", "infinity", "+infinity", "forever", "unlimited", "max"}


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def projection_message(value) -> str:
    choices = f"{', '.join(FACES)}, or {{dir: [x, y, z], up: [x, y, z]}}"
    if isinstance(value, dict):
        extra = [k for k in value if k not in ("dir", "up")]
        if extra:
            return f"unknown key '{extra[0]}'{suggest(extra[0], ['dir', 'up'])}: a projection is {choices}"
        return "a projection {…} needs dir: [x, y, z], the direction the camera looks"
    if not isinstance(value, str):
        return f"a projection is {choices}"
    hint = suggest(value, FACES)
    if not hint:
        word = PROJECTION_WORDS.get(re.sub(r"[\s_]+", "-", value.strip().lower()))
        hint = f" (did you mean {OBLIQUE}, an oblique view?)" if word == OBLIQUE else f" (did you mean '{word}'?)" if word else ""
    return f"'{value}' is not a projection: {choices}{hint}"


def decay_message(value) -> str:
    """WHY -1 → inf: -1 is the "no limit" sentinel of many trail settings; any other negative number is read as its size."""
    finite = not _is_number(value) or math.isfinite(value)
    if isinstance(value, str):
        shown = f"'{value}'"
    elif not finite:
        shown = "'.inf'" if value > 0 else "'-.inf'" if value < 0 else "'.nan'"
    else:
        shown = json.dumps(value)
    hint = ""
    if _is_number(value):
        if value == -1:
            hint = " (did you mean inf, the whole past up to t?)"
        elif not finite:
            hint = " (did you mean inf?)"
        elif value < 0:
            hint = f" (did you mean {json.dumps(-value)}?)"
    elif isinstance(value, str):
        k = value.strip().lower()
        m = re.match(r"^(\d+(?:\.\d+)?)\s*(ms|s|sec|secs|second|seconds)$", k)
        if k in INF_WORDS:
            hint = " (did you mean inf?)"
        elif k == "all":
            hint = " (did you mean show: all, every time step?)"
        elif m:
            seconds = float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)
            hint = f" (did you mean {seconds:g}?)"
    return f"{shown} is not a decay: seconds behind t (0 or more), or inf{hint}"


def axes_message(value) -> str:
    """WHY off → none: YAML 1.1 (PyYAML here) reads `off` as false, so the key says none, as legend: none does."""
    shown = f"'{value}'" if isinstance(value, str) else json.dumps(value)
    k = json.dumps(value).strip('"').strip().lower() if not isinstance(value, str) else value.strip().lower()
    if k in ("off", "false", "no", "hide", "hidden"):
        hint = " (did you mean 'none'?)"
    elif k in ("on", "true", "yes", "show"):
        hint = " (did you mean 'auto'?)"
    else:
        hint = suggest(value, ["auto", "none"])
    return f"{shown} is not an axes setting: auto (ticks on a face-aligned view) or none{hint}"


def scene_message(path, error) -> str | None:
    """A 3D key's own sentence for a schema error at that key, or None for the schema's own."""
    path = list(path)
    if len(path) != 4 or path[0] != "views" or path[2] not in SCENE_BLOCKS:
        return None
    key, value = path[3], error.instance
    if key == "projection":
        return projection_message(value)
    if key == "decay":
        return decay_message(value)
    if key == "axes":
        return axes_message(value)
    if key == "workspace" and error.validator in ("oneOf", "required"):
        return "a workspace is {model: <glb>} or {box: [[x0, y0, z0], [x1, y1, z1]]}, one of them"
    return None


def layer_refs(view: dict):
    """(path, name) where a view names a layer dataset (model.js layerRefs): a scene3d view's layers' data:, a
    trajectory3d view's compare.data and robots.data, a timeseries' annotations' data: (kit gap 2)."""
    named = lambda x: isinstance(x, dict) and isinstance(x.get("data"), str) and x["data"] != ""
    scene = view.get("scene3d") if view.get("type") == "scene3d" and isinstance(view.get("scene3d"), dict) else None
    for j, layer in enumerate(scene.get("layers") if scene and isinstance(scene.get("layers"), list) else []):
        if named(layer):
            yield ("scene3d", "layers", j, "data"), layer["data"]
    traj = view.get("trajectory3d") if view.get("type") == "trajectory3d" and isinstance(view.get("trajectory3d"), dict) else None
    for key in ("compare", "robots") if traj else ():
        if named(traj.get(key)):
            yield ("trajectory3d", key, "data"), traj[key]["data"]
    series = view.get("timeseries") if view.get("type") == "timeseries" and isinstance(view.get("timeseries"), dict) else None
    for j, mark in enumerate(series.get("annotations") if series and isinstance(series.get("annotations"), list) else []):
        if named(mark):
            yield ("timeseries", "annotations", j, "data"), mark["data"]


def dashboard_datasets(doc: dict) -> list[str]:
    """The dataset names a dashboard has, in model.js readDashboard's order: each datasets: entry with data, then the
    default data named by its file stem when no entry names that file."""
    names, given = [], doc.get("datasets") if isinstance(doc.get("datasets"), dict) else {}
    found = False
    for name, entry in given.items():
        data = entry if isinstance(entry, str) else entry.get("data") if isinstance(entry, dict) else None
        if not data:
            continue
        names.append(name)
        found = found or data == doc.get("data")
    if doc.get("data") and not found:
        stem = re.sub(r"\.[^.]+$", "", str(doc["data"]).split("/")[-1])
        if stem not in names:
            names.append(stem)
    return names


def _vec(v) -> bool:
    return isinstance(v, list) and len(v) == 3 and all(_is_number(x) and math.isfinite(x) for x in v)


def scene_problems(doc: dict):
    """The 3D blocks' own rules, past the schema (the Node checker's sceneProblems, plus model.js's unknown layer dataset):
    a projection's dir is a direction and its up crosses it; a decay YAML 1.1 read as a float infinity; a layer's dataset,
    which a dashboard must have and a plain file cannot. Yield (level, path, message)."""
    dashboard = any(doc.get(k) for k in ("datasets", "layout", "links"))
    names = dashboard_datasets(doc) if dashboard else []
    for index, view in enumerate(doc.get("views") or []):
        if not isinstance(view, dict):
            continue
        for block in SCENE_BLOCKS:
            scene = view.get(block)
            if not isinstance(scene, dict):
                continue
            at = ("views", index, block)
            p = scene.get("projection")
            if isinstance(p, dict) and _vec(p.get("dir")):
                a, b, c = p["dir"]
                if math.hypot(a, b, c) == 0:
                    yield "error", at + ("projection", "dir"), "dir is the direction the camera looks: it cannot be [0, 0, 0]"
                elif _vec(p.get("up")):
                    u, v, w = p["up"]
                    cross = math.hypot(b * w - c * v, c * u - a * w, a * v - b * u)
                    if cross <= 1e-9 * math.hypot(a, b, c) * math.hypot(u, v, w):
                        along = abs(c) >= 0.999 * math.hypot(a, b, c)
                        text = lambda vec: "[" + ", ".join(json.dumps(x) for x in vec) + "]"
                        yield "error", at + ("projection", "up"), \
                            f"up {text(p['up'])} is parallel to dir {text(p['dir'])}: the screen's up must cross the view (did you mean up: {'[0, 1, 0]' if along else '[0, 0, 1]'}?)"
            decay = scene.get("decay")
            if _is_number(decay) and not math.isfinite(decay):
                yield "error", at + ("decay",), decay_message(decay)
        for path, name in layer_refs(view):
            if not dashboard:
                yield "warning", ("views", index) + path, \
                    f"'{name}' names a dashboard dataset, and this file has no datasets: (a plain <data-views> has only its own rows, so this draws nothing)"
            elif name not in names:
                yield "error", ("views", index) + path, f"no dataset '{name}' (datasets: {', '.join(names)})"


PLACEHOLDER = re.compile(r"\{([^{}]+)\}")


def placeholders(path):
    """The placeholders a per-pick data: names (model.js placeholders): each once, in order; None for a plain file."""
    out = []
    for m in PLACEHOLDER.finditer(str(path or "")):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out or None


def navigation_problems(doc: dict):
    """CONTRACT §33 (PEP 0010 P3), past the schema: model.js readDashboard's navigation problems and the Node checker's
    link warnings. Yield (level, path, message)."""
    if isinstance(doc.get("data"), str) and placeholders(doc["data"]):
        yield "error", ("data",), \
            f"the file's data: is read before anything is picked, so it names one file; a file read per pick ({doc['data']}) belongs in a datasets: entry"
    for index, view in enumerate(doc.get("views") or []):
        if isinstance(view, dict) and "selected" in view and view["selected"] is not None and not (isinstance(view.get("select"), str) and view["select"]):
            yield "error", ("views", index, "selected"), "it presets what a click on this view selects, and the view has no select: (add select: <property>)"
    given = doc.get("datasets") if isinstance(doc.get("datasets"), dict) else {}
    templates = {}
    for name, entry in given.items():
        data = entry if isinstance(entry, str) else entry.get("data") if isinstance(entry, dict) else None
        found = placeholders(data) if isinstance(data, str) else None
        if not found:
            continue
        templates[name] = (found, data)
        for key in ("refresh", "live"):
            if isinstance(entry, dict) and key in entry:
                yield "error", ("datasets", name, key), \
                    f"{name} is read one {found[0]} at a time (data: {data}), when a pick names it, so it cannot also {'refresh on a timer' if key == 'refresh' else 'be live'}"
    links = []
    for index, link in enumerate(doc.get("links") or []):
        if not isinstance(link, dict) or not isinstance(link.get("from"), str) or not isinstance(link.get("to"), str):
            continue
        a, _, ac = link["from"].partition(".")
        b, _, bc = link["to"].partition(".")
        links.append((index, a, ac, b, bc, link.get("direction") == "one-way"))
    for name, (found, data) in templates.items():
        for ph in found:
            reached = any((b == name and bc == ph and a != name) or (not one and a == name and ac == ph and b != name) for _, a, ac, b, bc, one in links)
            if not reached:
                yield "error", ("datasets", name, "data") if isinstance(given[name], dict) else ("datasets", name), \
                    f"nothing can pick the '{ph}' that {data} is read for: no link ends at {name}.{ph} (write one from the dataset that is picked, e.g. {{from: runs.{ph}, to: {name}.{ph}, direction: one-way}})"
    for index, a, ac, b, bc, one in links:
        ta, tb = (templates.get(a) or (None,))[0], (templates.get(b) or (None,))[0]
        if not (ta or tb) or (ta and tb and ta == tb):
            continue
        t, other, ph = (b, a, tb[0]) if tb else (a, b, ta[0])
        if not one:
            yield "warning", ("links", index), \
                f"{t} is read one {ph} at a time (data: {templates[t][1]}), so its rows narrow nothing back: write this link direction: one-way, from {other} to {t}"
        elif ta:
            yield "warning", ("links", index), \
                f"{a} is read one {ta[0]} at a time (data: {templates[a][1]}), so a link from it narrows nothing: turn it round, from {b} to {a} (direction: one-way)"


# trajectory3d's defaults: the trajectory contract's own column names (gallery/robotics/CONTRACT.md)
TRAJECTORY_POSES = {"x": "x_mm", "y": "y_mm", "z": "z_mm", "frame": "frame", "body": "body"}
TRAJECTORY_BINDING = {"series": "situation", "family": "source", "run": "run", "t": "t"}
LINK_WHY = "a link is posed from <link>_x/_y/_z and <link>_qw/_qx/_qy/_qz"


def scene_names(doc: dict):
    """(path, column, why) for every column the 3D cards read from the view's own (default) dataset: a scene3d layer's
    without data:, the trajectory3d binding's (given, or the contract's name it defaults to), a robot link's first column
    when robots names no data:, and voxels'. Views with `from:` are skipped (the Node checker scopes them)."""
    for index, view in enumerate(doc.get("views") or []):
        if not isinstance(view, dict) or view.get("from"):
            continue
        s = lambda x: isinstance(x, str) and x != ""
        scene = view.get("scene3d") if view.get("type") == "scene3d" and isinstance(view.get("scene3d"), dict) else None
        for j, layer in enumerate(scene.get("layers") if scene and isinstance(scene.get("layers"), list) else []):
            if not isinstance(layer, dict) or s(layer.get("data")):
                continue
            at = ("views", index, "scene3d", "layers", j)
            for key in ("x", "y", "z", "color", "t", "by"):
                if s(layer.get(key)):
                    yield at + (key,), layer[key], None
            for key in ("by", "quat", "from", "to", "at", "min", "max"):
                for n, column in enumerate(layer.get(key) if isinstance(layer.get(key), list) else []):
                    if s(column):
                        yield at + (key, n), column, None
            for n, link in enumerate(layer.get("links") if isinstance(layer.get("links"), list) else []):
                if s(link):
                    yield at + ("links", n), f"{link}_x", LINK_WHY
        if view.get("type") == "trajectory3d":
            traj = view.get("trajectory3d") if isinstance(view.get("trajectory3d"), dict) else {}
            at = ("views", index, "trajectory3d") if isinstance(view.get("trajectory3d"), dict) else ("views", index, "type")
            poses = traj.get("poses") if isinstance(traj.get("poses"), dict) else {}
            for key, default in TRAJECTORY_POSES.items():
                yield (at + ("poses", key), poses[key], None) if s(poses.get(key)) else \
                    (at, default, f"trajectory3d reads it for poses.{key} by default; name the column there")
            for n, column in enumerate(poses.get("quat") if isinstance(poses.get("quat"), list) else []):
                if s(column):
                    yield at + ("poses", "quat", n), column, None
            for key, default in TRAJECTORY_BINDING.items():
                yield (at + (key,), traj[key], None) if s(traj.get(key)) else \
                    (at, default, f"trajectory3d reads it for {key} by default; name the column there")
            robots = traj.get("robots") if isinstance(traj.get("robots"), dict) else None
            if robots and not s(robots.get("data")):
                for n, link in enumerate(robots.get("links") if isinstance(robots.get("links"), list) else []):
                    if s(link):
                        yield at + ("robots", "links", n), f"{link}_x", LINK_WHY
        series = view.get("timeseries") if view.get("type") == "timeseries" and isinstance(view.get("timeseries"), dict) else None
        for j, mark in enumerate(series.get("annotations") if series and isinstance(series.get("annotations"), list) else []):
            # kit gap 2: an annotation from the view's own rows names its time and label columns there
            if not isinstance(mark, dict) or not s(mark.get("x")) or s(mark.get("data")):
                continue
            at = ("views", index, "timeseries", "annotations", j)
            yield at + ("x",), mark["x"], None
            if s(mark.get("label")):
                yield at + ("label",), mark["label"], None
        vox = view.get("voxels") if view.get("type") == "voxels" and isinstance(view.get("voxels"), dict) else None
        if vox:
            at = ("views", index, "voxels")
            for key in ("x", "y", "z"):
                if s(vox.get(key)):
                    yield at + (key,), vox[key], None
            if s(vox.get("value")) and vox["value"] not in ("time", "runs", "count"):
                yield at + ("value",), vox["value"], None
            if s(vox.get("w")):
                yield at + ("w",), vox["w"], None
            elif vox.get("value") == "time":
                yield at, "w", "voxels sums it for value: time by default; name the column with w:"
            if s(vox.get("run")):
                yield at + ("run",), vox["run"], None
            elif vox.get("value") == "runs":
                yield at, "run", "voxels counts it for value: runs by default; name the column with run:"


def dataset_link(path: pathlib.Path) -> str | None:
    """The dataset file's linkProperty (each record's page URL), or None when it names none."""
    data = json.loads(path.read_text(encoding="utf-8"))
    link = data.get("linkProperty") if isinstance(data, dict) else None
    return link if isinstance(link, str) and link else None


def dataset_properties(path: pathlib.Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return own_properties(data) | source_columns(data)


def own_properties(data) -> set[str]:
    if isinstance(data, dict) and isinstance(data.get("properties"), dict):  # the <data-views> runtime shape
        return set(data["properties"])
    if isinstance(data, dict) and isinstance(data.get("schema"), dict):  # Table Schema vocabulary
        return {field["name"] for field in data["schema"].get("fields", [])}
    rows = data.get("rows") if isinstance(data, dict) else data
    return {key for row in (rows or [])[:200] if isinstance(row, dict) for key in row}


def source_columns(data) -> set[str]:
    """The columns a dataset's lists of sources unfold to (CONTRACT §36): a .base may name them; `<p>@*` is every source of p."""
    out: set[str] = set()
    for row in (data.get("rows") if isinstance(data, dict) else None) or []:
        for key, cell in row.items() if isinstance(row, dict) else ():
            if isinstance(cell, dict) and isinstance(cell.get("sources"), list) and cell["sources"]:
                out |= {f"{key}@source", f"{key}@*"}
                out |= {f"{key}@{'@source' if e['source'] == 'source' else e['source']}" for e in cell["sources"] if isinstance(e, dict) and e.get("source")}
            elif isinstance(cell, dict) and data.get("sourceColumn") is True and any(cell.get(k) for k in ("source", "sourceUrl", "sourcePage")):
                out.add(f"{key}@source")
    return out


COALESCE = re.compile(r"^\s*\[(?P<items>.*)\]\s*\.\s*filter\s*\((?P<test>.*)\)\s*\[\s*0\s*\]\s*$", re.S)
COALESCE_TESTS = {"!value.isEmpty()", 'value.isType("boolean")||!value.isEmpty()'}
COALESCE_ITEM = re.compile(r"""\s*(note\.[A-Za-z_]\w*|note\[\s*(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')\s*\]|[A-Za-z_]\w*)\s*(?:,|$)""")


def is_coalesce(text) -> bool:
    """Whether a formula is the one data-ui runs: the Python side of grammar.js parseCoalesce."""
    found = COALESCE.match(text) if isinstance(text, str) else None
    if not found or "".join(found["test"].replace("'", '"').split()) not in COALESCE_TESTS or not found["items"].strip():
        return False
    at, items = 0, found["items"]
    while at < len(items):
        step = COALESCE_ITEM.match(items, at)
        if not step or step[1] in ("true", "false", "null", "this", "file", "formula", "note"):
            return False
        at = step.end()
    return True


STRING = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')
BRACKET = re.compile(r'note\[\s*("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')\s*\]')
CHAIN = re.compile(r"(?<![\w.])([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)(\s*\()?")


def expression_properties(source: str) -> list[str]:
    """The properties an expression reads, by name only (the engine's compiler judges the rest)."""
    found = [json.loads(m.group(1)) if m.group(1)[0] == '"' else m.group(1)[1:-1] for m in BRACKET.finditer(source)]
    stripped = STRING.sub('""', BRACKET.sub("_bracket_", source))
    for m in CHAIN.finditer(stripped):
        chain, call = m.group(1).split("."), bool(m.group(2))
        if call:
            chain = chain[:-1]  # x.contains( -> x; a bare function call (if(...)) reads no property by name
        if not chain or chain[0] in KEYWORDS or chain[0] == "_bracket_":
            continue
        if chain[0] in ("file", "formula", "this"):
            found.append(".".join(chain[:2]))
            continue
        found.append(chain[1] if chain[0] == "note" and len(chain) > 1 else chain[0])
    return found


def filter_strings(node, path):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            for index, child in enumerate(value if isinstance(value, list) else []):
                yield from filter_strings(child, path + (key, index))


def chart_fields(node, path):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "field" and isinstance(value, str):
                yield path + (key,), value
            else:
                yield from chart_fields(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from chart_fields(value, path + (index,))


PIVOTED = object()


def _as_list(x):
    return x if isinstance(x, list) else [] if x is None else [x]


def transform_made(t):
    """The names one Vega-Lite transform makes (kit gap 5; the Node checker's transformMade): calculate, timeUnit, bin and
    stack `as` (a bin's or stack's one name also makes <as>_end), aggregate, joinaggregate and window ops' `as`, fold
    (key, value), density (value, density), quantile (prob, value), lookup's `as` or its fields; a pivot: PIVOTED."""
    if not isinstance(t, dict):
        return []
    if "pivot" in t:
        return [PIVOTED]
    out = []
    pair = lambda a: [a, f"{a}_end"] if isinstance(a, str) else _as_list(a)  # noqa: E731
    if "calculate" in t or "timeUnit" in t:
        out += _as_list(t.get("as"))
    if "bin" in t:
        out += pair(t.get("as"))
    if "stack" in t:
        out += pair(t.get("as"))
    for key in ("aggregate", "joinaggregate", "window"):
        out += [op["as"] for op in _as_list(t.get(key)) if isinstance(op, dict) and op.get("as")]
    if "fold" in t:
        out += _as_list(t["as"]) if t.get("as") else ["key", "value"]
    if "density" in t:
        out += _as_list(t["as"]) if t.get("as") else ["value", "density"]
    if "quantile" in t:
        out += _as_list(t["as"]) if t.get("as") else ["prob", "value"]
    for key in ("loess", "regression", "flatten"):
        if key in t:
            out += _as_list(t.get("as"))
    if "lookup" in t:
        out += _as_list(t["as"]) if t.get("as") else _as_list((t.get("from") or {}).get("fields") if isinstance(t.get("from"), dict) else None)
    return [x for x in out if isinstance(x, str)]


def chart_refs(node, path, made=frozenset()):
    """(path, field) for every column a chart block reads (kit gap 5; the Node checker's chartRefs): each `field:` that no
    transform in its scope makes. A spec's scope is its parent's and its own transform's names, so the chart's own
    transform reaches every layer and a layer's only that layer; after a pivot nothing in that scope is named."""
    if not isinstance(node, dict):
        return
    here = set(made)
    for t in _as_list(node.get("transform")):
        made_here = transform_made(t)
        if PIVOTED in made_here:
            return
        here.update(made_here)
    for key, value in node.items():
        if key in ("layer", "hconcat", "vconcat", "concat") and isinstance(value, list):
            for i, child in enumerate(value):
                yield from chart_refs(child, path + (key, i), here)
            continue
        if key == "spec" and isinstance(value, dict):
            yield from chart_refs(value, path + (key,), here)
            continue
        for where, name in chart_fields(value, path + (key,)):
            if name not in here:
                yield where, name


def referenced(doc: dict):
    """(path, property) for every property the file names, wherever it names one."""
    yield from facet_names(doc.get("facets"), ("facets",))
    if isinstance(doc.get("open"), dict) and isinstance(doc["open"].get("url"), str):
        yield ("open", "url"), doc["open"]["url"]
    for path, source in filter_strings(doc.get("filters"), ("filters",)):
        for name in expression_properties(source):
            yield path, name
    yield from summary_names(doc.get("summary"), ("summary",))
    for v_index, view in enumerate(doc.get("views") or []):
        if not isinstance(view, dict):
            continue
        base = ("views", v_index)
        for i, name in enumerate(view.get("order") or []):
            yield base + ("order", i), name
        for i, rule in enumerate(view.get("sort") or []):
            yield base + ("sort", i, "property"), (rule or {}).get("property")
        for key in ("groupBy", "subGroupBy"):
            if isinstance(view.get(key), dict):
                yield base + (key, "property"), view[key].get("property")
        yield from tile_names(view.get("tiles"), base + ("tiles",))
        for g_index, grouping in enumerate(view.get("groupings") if isinstance(view.get("groupings"), list) else []):
            if not isinstance(grouping, dict):
                continue
            for key in ("groupBy", "subGroupBy"):
                if isinstance(grouping.get(key), dict):
                    yield base + ("groupings", g_index, key, "property"), grouping[key].get("property")
            yield from tile_names(grouping.get("tiles"), base + ("groupings", g_index, "tiles"))
        for i, name in enumerate(view.get("splitBy") or []):
            yield base + ("splitBy", i), name
        for key in ("display", "columnSize", "summaries"):
            for name in (view.get(key) or {}):
                yield base + (key, name), name
        if isinstance(view.get("value"), dict):
            for key in ("property", "per"):
                if view["value"].get(key):
                    yield base + ("value", key), view["value"][key]
        for key in ("image", "media", "start", "end", "title", "color", "coordinates"):
            if isinstance(view.get(key), str) and view.get(key):
                yield base + (key,), view[key]
        for i, name in enumerate(view.get("caption") or []):
            yield base + ("caption", i), name
        for key, sub in (("edges", "property"), ("edges", "label"), ("tree", "parent"), ("tree", "path"), ("sketch", "diameter"), ("sketch", "length")):
            if isinstance(view.get(key), dict) and view[key].get(sub):
                yield base + (key, sub), view[key][sub]
        # lineage (CONTRACT §21): every property-valued key of the block, and each kept: property
        lineage = view.get("lineage") if isinstance(view.get("lineage"), dict) else {}
        for key in ("parents", "x", "xLabel", "image", "label"):
            if isinstance(lineage.get(key), str) and lineage.get(key):
                yield base + ("lineage", key), lineage[key]
        for name in (lineage.get("kept") if isinstance(lineage.get("kept"), dict) else {}):
            yield base + ("lineage", "kept", name), name
        rollup = view.get("rollup") if isinstance(view.get("rollup"), dict) else {}
        for key in ("keep", "dims"):
            for i, name in enumerate(rollup.get(key) or []):
                yield base + ("rollup", key, i), name
        for name in (rollup.get("agg") or {}):
            yield base + ("rollup", "agg", name), name
        for group, names in (view.get("columnGroups") or {}).items():
            for i, name in enumerate(names or []):
                yield base + ("columnGroups", group, i), name
        for name in (view.get("stats") or {}):
            yield base + ("stats", name), name
        for s_index, section in enumerate((view.get("record") or {}).get("sections") or []):
            for i, name in enumerate((section or {}).get("properties") or []):
                yield base + ("record", "sections", s_index, "properties", i), name
        for name in ((view.get("record") or {}).get("visibility") or {}):
            if not name.startswith("@"):
                yield base + ("record", "visibility", name), name
        for name in ((view.get("compare") or {}).get("better") or {}):
            yield base + ("compare", "better", name), name
        hover = view.get("hover") or {}
        for key in ("image", "title"):
            if hover.get(key):
                yield base + ("hover", key), hover[key]
        for i, name in enumerate(hover.get("fields") or []):
            yield base + ("hover", "fields", i), name
        for path, name in chart_refs(view.get("chart"), base + ("chart",)):
            yield path, name
        for i, guide in enumerate(view.get("guides") or []):
            if isinstance(guide, dict) and guide.get("envelope"):
                yield base + ("guides", i, "envelope"), guide["envelope"]
        kpi = view.get("kpi") or {}
        for key in ("property", "per"):
            if (kpi.get("value") or {}).get(key):
                yield base + ("kpi", "value", key), kpi["value"][key]
        for key in ("x", "y"):
            if (kpi.get("spark") or {}).get(key):
                yield base + ("kpi", "spark", key), kpi["spark"][key]
        against = (kpi.get("compare") or {}).get("against")
        if against and against not in ("previous", "target"):
            yield base + ("kpi", "compare", "against"), against
        better = (kpi.get("compare") or {}).get("better")
        if isinstance(better, str) and better and better not in ("higher", "lower"):
            yield base + ("kpi", "compare", "better"), better
        for path, source in filter_strings(view.get("filters"), base + ("filters",)):
            for name in expression_properties(source):
                yield path, name
        if isinstance(view.get("facets"), list):
            yield from facet_names(view["facets"], base + ("facets",))
        if isinstance(view.get("open"), dict) and isinstance(view["open"].get("url"), str):
            yield base + ("open", "url"), view["open"]["url"]
        # CONTRACT §35: a property target, the gate matrix's column, a limits end that is a property, the path's colour
        if isinstance(kpi.get("target"), str) and kpi["target"]:
            yield base + ("kpi", "target"), kpi["target"]
        tracker = view.get("tracker") if isinstance(view.get("tracker"), dict) else {}
        if isinstance(tracker.get("column"), str) and tracker["column"]:
            yield base + ("tracker", "column"), tracker["column"]
        for block in ("timeseries", "plot"):
            limits = (view.get(block) or {}).get("limits") if isinstance(view.get(block), dict) else None
            for side in ("warn", "error") if isinstance(limits, dict) else ():
                for i, end in enumerate(limits.get(side) if isinstance(limits.get(side), list) else []):
                    if isinstance(end, str) and end:
                        yield base + (block, "limits", side, i), end
        trajectory = view.get("trajectory3d") if isinstance(view.get("trajectory3d"), dict) else {}
        if isinstance(trajectory.get("color"), str) and trajectory["color"]:
            yield base + ("trajectory3d", "color"), trajectory["color"]
        yield from map_names(view, base)
        # CONTRACT §43: the avatar's colour property and a summary view's cells
        if isinstance(view.get("avatar"), dict) and isinstance(view["avatar"].get("color"), str) and view["avatar"]["color"]:
            yield base + ("avatar", "color"), view["avatar"]["color"]
        yield from summary_names(view.get("summary"), base + ("summary",))


def summary_names(summary, at):
    """The properties a summary: block's cells read: each cell's filters, when.property, value.property, spark.x."""
    cells = summary.get("cells") if isinstance(summary, dict) and isinstance(summary.get("cells"), list) else []
    for i, cell in enumerate(cells):
        if not isinstance(cell, dict):
            continue
        base = at + ("cells", i)
        for path, source in filter_strings(cell.get("filters"), base + ("filters",)):
            for name in expression_properties(source):
                yield path, name
        for key, sub in (("when", "property"), ("value", "property"), ("spark", "x")):
            if isinstance(cell.get(key), dict) and isinstance(cell[key].get(sub), str) and cell[key][sub]:
                yield base + (key, sub), cell[key][sub]


def map_names(view: dict, base: tuple):
    """The map view's property-valued keys (CONTRACT §42), as check.js's mapNames: each layer's row properties and the
    properties its filter, of: and count: expressions read, then time:, multiples.by, drawBy and drawSum. A region
    layer's label: and key: name the geometry file's feature properties, so they are not checked here."""
    def text(x):
        return isinstance(x, str) and x
    for i, layer in enumerate(view.get("layers") if isinstance(view.get("layers"), list) else []):
        if not isinstance(layer, dict):
            continue
        at = base + ("layers", i)
        # join: id is every row's own id (CONTRACT §3), which a data file need not list among its properties
        for key in ("coordinates", "weight", "path", "from", "to", "text", "join"):
            if text(layer.get(key)) and not (key == "join" and layer[key] == "id"):
                yield at + (key,), layer[key]
        if text(layer.get("value")):
            yield at + ("value",), layer["value"]
        for key in ("value", "size", "width"):
            if isinstance(layer.get(key), dict) and text(layer[key].get("property")):
                yield at + (key, "property"), layer[key]["property"]
        if isinstance(layer.get("bivariate"), dict):
            for key in ("x", "y"):
                if text(layer["bivariate"].get(key)):
                    yield at + ("bivariate", key), layer["bivariate"][key]
        if layer.get("type") == "points" and text(layer.get("label")):
            yield at + ("label",), layer["label"]
        detail = layer.get("detail")
        if isinstance(detail, list):
            for j, name in enumerate(detail):
                yield at + ("detail", j), name
        elif text(detail):
            yield at + ("detail",), detail
        for key in ("filter", "of", "count"):
            if text(layer.get(key)):
                for name in expression_properties(layer[key]):
                    yield at + (key,), name
    t = view.get("time")
    if text(t):
        yield base + ("time",), t
    elif isinstance(t, dict) and text(t.get("property")):
        yield base + ("time", "property"), t["property"]
    if isinstance(view.get("multiples"), dict) and text(view["multiples"].get("by")):
        yield base + ("multiples", "by"), view["multiples"]["by"]
    for key in ("drawBy", "drawSum"):
        if text(view.get(key)):
            yield base + (key,), view[key]

def tile_names(tiles, at):
    if isinstance(tiles, dict):
        for key in ("property", "image", "link"):
            if isinstance(tiles.get(key), str) and tiles[key]:
                yield at + (key,), tiles[key]


def grouping_problems(doc: dict, types: dict | None):
    """The grouped gallery's rules, past the schema (the Node checker's groupingProblems): `grouping` names one of the
    view's `groupings`, each id once, a level groups by `bins:` or `by:` (not both), and bins on a property the data
    does not type as a number warn. Yield (level, path, message)."""
    for index, view in enumerate(doc.get("views") or []):
        if not isinstance(view, dict):
            continue
        groupings = view.get("groupings") if isinstance(view.get("groupings"), list) else []
        ids = [g.get("id") if isinstance(g, dict) else None for g in groupings]
        for j, ident in enumerate(ids):
            if isinstance(ident, str) and ids.index(ident) != j:
                yield "error", ("views", index, "groupings", j, "id"), f"id '{ident}' is used twice: a grouping is picked by its id"
        grouping = view.get("grouping")
        if isinstance(grouping, str) and grouping not in ids:
            yield "warning", ("views", index, "grouping"), \
                f"'{grouping}' names no groupings entry{suggest(grouping, [i for i in ids if isinstance(i, str)])}; the view's own groupBy is used"
        levels = [(view.get("groupBy"), ("views", index, "groupBy")), (view.get("subGroupBy"), ("views", index, "subGroupBy"))]
        for j, g in enumerate(groupings):
            if isinstance(g, dict):
                levels += [(g.get(key), ("views", index, "groupings", j, key)) for key in ("groupBy", "subGroupBy")]
        for level, at in levels:
            if not isinstance(level, dict) or "bins" not in level:
                continue
            if "by" in level:
                yield "error", at + ("bins",), "a level groups by bins: (numbers) or by: (dates), not both"
                continue
            kind = (types or {}).get(level.get("property"))
            if kind and kind != "number":
                yield "warning", at + ("bins",), f"'bins' groups numbers, and '{level.get('property')}' is {kind}: every row falls in \"No {level.get('property')}\""


def _open_mode(value):
    return value if isinstance(value, str) else value.get("mode") if isinstance(value, dict) else None


def _open_url(value):
    return value.get("url") if isinstance(value, dict) and isinstance(value.get("url"), str) else None


def open_problems(doc: dict, link):
    """`open:`'s own rule (the Node checker's openProblems): link needs a URL, the url: key or the data's linkProperty;
    without one the page falls back to side. Only when the data is known to name no link (`link` None; the sentinel
    ... means not known). Yield (level, path, message)."""
    if link is not None:
        return
    say = "link needs a URL: no url: here and the data names no linkProperty, so it falls back to side"
    top = doc.get("open")
    if _open_mode(top) == "link" and not _open_url(top):
        yield "warning", ("open",), f"open: {say} (in every view that does not say)"
    for index, view in enumerate(doc.get("views") or []):
        if isinstance(view, dict) and _open_mode(view.get("open")) == "link" and not _open_url(view["open"]) and not _open_url(top):
            yield "warning", ("views", index, "open"), f"open: {say}"


def facet_names(facets, at):
    """(path, property) for every property a rail names: a facet's property, a tree's levels, a has or search group's
    properties, a gallery's image column, and the properties inside a popular filter's expressions."""
    for index, facet in enumerate(facets if isinstance(facets, list) else []):
        if isinstance(facet, str):
            yield at + (index,), facet
            continue
        if not isinstance(facet, dict):
            continue
        if facet.get("property"):
            yield at + (index, "property"), facet["property"]
        for key in ("levels", "properties"):
            for j, name in enumerate(facet.get(key) if isinstance(facet.get(key), list) else []):
                yield at + (index, key, j), name
        if isinstance(facet.get("image"), str):
            yield at + (index, "image"), facet["image"]
        for j, option in enumerate(facet.get("options") if isinstance(facet.get("options"), list) else []):
            source = option if isinstance(option, str) else (option or {}).get("filter") if isinstance(option, dict) else None
            if isinstance(source, str):
                path = at + (index, "options", j) + (() if isinstance(option, str) else ("filter",))
                for name in expression_properties(source):
                    yield path, name


NUMBER_KINDS = {"range", "slider", "slider-histogram", "buckets", "rating", "min-level"}
GROUP_KINDS = {"tree": "levels", "has": "properties", "search": "properties"}


def facet_problems(doc: dict, types: dict | None):
    """The rail's own rules, past the schema (the Node checker's facetProblems): a facet names what it filters, and
    its kind fits the property's type. Yield (level, path, message)."""
    lists = [(doc.get("facets"), ("facets",))]
    lists += [((view or {}).get("facets") if isinstance(view, dict) else None, ("views", i, "facets")) for i, view in enumerate(doc.get("views") or [])]
    lists += [(entry.get("facets"), ("datasets", name, "facets")) for name, entry in (doc.get("datasets") or {}).items() if isinstance(entry, dict) and isinstance(doc.get("datasets"), dict)]
    for facets, at in lists:
        owned = [f if isinstance(f, str) else f.get("property") for f in (facets if isinstance(facets, list) else []) if isinstance(f, (str, dict))]
        owned = [p for p in owned if isinstance(p, str) and p]
        for index, facet in enumerate(facets if isinstance(facets, list) else []):
            if not isinstance(facet, dict):
                continue
            kind = facet.get("as") or "values"
            path = at + (index,)
            # kit gap 8: parent names another facet of this rail, the one whose pick this facet's values nest under
            if "parent" in facet:
                parent = facet["parent"]
                if parent == facet.get("property"):
                    yield "error", path + ("parent",), f"'{parent}' cannot be its own parent: parent names another facet of this rail, the one this facet's values nest under"
                elif parent not in owned:
                    yield "error", path + ("parent",), f"'{parent}' is no facet of this rail{suggest(str(parent), [p for p in owned if p != facet.get('property')])}: parent names the facet this facet's values nest under"
            if kind == "popular":
                if not isinstance(facet.get("options"), list) or not facet["options"]:
                    yield "error", path, "a popular facet needs 'options': filter expressions, or {label, filter}"
                continue
            if kind == "current":
                continue
            if kind == "nav" and not facet.get("property"):
                continue  # a nav facet with no property lists the groups of the view's current groupBy (CONTRACT §20)
            group = GROUP_KINDS.get(kind)
            if not facet.get("property") and not (group and isinstance(facet.get(group), list) and facet[group]):
                yield "error", path, f"a {kind} facet needs 'property'" + (f" or '{group}'" if group else "")
                continue
            prop = facet.get("property") or facet[group][0]
            kind_of = (types or {}).get(prop)
            if not kind_of:
                continue
            if kind in NUMBER_KINDS and kind_of != "number" and not (kind == "range" and kind_of == "date"):
                yield "error", path + ("as",), f"'{kind}' needs a number property{' or a date' if kind == 'range' else ''}; '{prop}' is {kind_of} (did you mean 'values'?)"
            if kind == "date" and kind_of != "date":
                yield "warning", path + ("as",), f"'date' reads ISO dates; '{prop}' is {kind_of}, so its values compare as text"
            if kind == "chips" and kind_of != "list":
                yield "warning", path + ("as",), f"'chips' is for a list property (tags); '{prop}' is {kind_of}, so each row has one chip"


def time_problems(doc: dict, types: dict | None):
    """A group level's `by:` buckets dates: on a property the data types otherwise, say what happens (the Node
    checker's timeProblems). Yield (level, path, message)."""
    if not types:
        return
    for index, view in enumerate(doc.get("views") or []):
        for key in ("groupBy", "subGroupBy"):
            level = view.get(key) if isinstance(view, dict) else None
            kind = types.get(level.get("property")) if isinstance(level, dict) and level.get("by") else None
            if kind and kind != "date":
                yield "warning", ("views", index, key, "by"), \
                    f"'by: {level['by']}' groups dates, and '{level['property']}' is {kind}: a value that is not an ISO date falls in \"No {level['property']}\""


def dataset_types(path: pathlib.Path) -> dict | None:
    """{property: type} of a dataset file, when it says (the runtime shape's properties, or a field schema)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("properties"), dict):
        return {k: (v or {}).get("type") or "text" for k, v in data["properties"].items()}
    if isinstance(data, dict) and isinstance(data.get("schema"), dict):
        names = {"integer": "number", "number": "number", "array": "list", "boolean": "boolean", "date": "date", "datetime": "date"}
        return {f["name"]: names.get(f.get("type"), "text") for f in data["schema"].get("fields", [])}
    return None


def check_file(path: pathlib.Path, properties: set[str] | None, dataset_name: str, types: dict | None = None, link=...):
    """Yield (level, line, path, message)."""
    text = path.read_text(encoding="utf-8")
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        yield "error", (mark.line + 1 if mark else 1), (), f"not valid YAML: {getattr(error, 'problem', error)}"
        return
    if doc is None:
        doc = {}
    if not isinstance(doc, dict):
        yield "error", 1, (), "a .base file is a mapping (filters, properties, views, ...)"
        return
    lines = Lines(text)
    validator = jsonschema.Draft202012Validator(SCHEMA)
    for error in sorted(validator.iter_errors(doc), key=lambda e: list(map(str, e.absolute_path))):
        # WHY the deepest branch: a oneOf/anyOf (a filter, a channel, a mark) reports every branch it tried, and
        # "not valid under any of the given schemas" tells an agent nothing. One sentence at the deepest path does.
        error = deepest(error)
        where = tuple(error.absolute_path)
        yield "error", lines.line(where), where, scene_message(where, error) or schema_message(error)
    for key in doc:
        if key not in BASES_TOP | DATA_UI_TOP:
            yield "warning", lines.line((key,)), (key,), f"unknown top-level key '{key}'{suggest(key, BASES_TOP | DATA_UI_TOP)}; Bases keeps it, data-ui ignores it"
    for index, view in enumerate(doc.get("views") or []):
        if not isinstance(view, dict):
            continue
        for key in view:
            if key not in VIEW_KEYS:
                yield "warning", lines.line(("views", index, key)), ("views", index, key), \
                    f"unknown view key '{key}'{suggest(key, VIEW_KEYS)}; Bases keeps it, data-ui ignores it"
        kind = view.get("type")
        if isinstance(kind, str) and kind not in VIEW_TYPES:
            yield "warning", lines.line(("views", index, "type")), ("views", index, "type"), \
                f"data-ui cannot draw type '{kind}'{suggest(kind, VIEW_TYPES)} (a plugin's view? Obsidian needs that plugin too)"
    # an embedded view (a record section's, CONTRACT §35) is a view: the schema checks its type's block, and a key or
    # type it does not know is a warning too. WHY no column checks: this proof reads no dataset but --data, and an
    # embedded view reads its own from: dataset; the Node checker names those columns.
    for index, view in enumerate(doc.get("views") or []):
        sections = (view.get("record") or {}).get("sections") if isinstance(view, dict) and isinstance(view.get("record"), dict) else None
        for s_index, section in enumerate(sections if isinstance(sections, list) else []):
            inline = section.get("view") if isinstance(section, dict) else None
            if not isinstance(inline, dict):
                continue
            base = ("views", index, "record", "sections", s_index, "view")
            for key in inline:
                if key not in VIEW_KEYS:
                    yield "warning", lines.line(base + (key,)), base + (key,), \
                        f"unknown view key '{key}'{suggest(key, VIEW_KEYS)}; Bases keeps it, data-ui ignores it"
            if isinstance(inline.get("type"), str) and inline["type"] not in VIEW_TYPES:
                yield "warning", lines.line(base + ("type",)), base + ("type",), \
                    f"data-ui cannot draw type '{inline['type']}'{suggest(inline['type'], VIEW_TYPES)} (a plugin's view? Obsidian needs that plugin too)"
    # CONTRACT §36: the one formula data-ui runs, and what it is for. WHY only with data: a .base with none is Obsidian's own, where any
    # formula is right, and the vault's files stay clean
    for name, formula in ((doc.get("formulas") or {}) if properties is not None or doc.get("data") else {}).items():
        if not is_coalesce(formula):
            yield "warning", lines.line(("formulas", name)), ("formulas", name), \
                f"data-ui does not run formula '{name}' (only [a, b].filter(!value.isEmpty())[0], the first non-empty column): its column shows a dash here, and Obsidian runs it"
    for index, view in enumerate(doc.get("views") or []):
        read = ((view.get("kpi") or {}).get("value") or {}).get("property") if isinstance(view, dict) else None
        if isinstance(read, str) and read.startswith("formula."):
            yield "error", lines.line(("views", index, "kpi", "value", "property")), ("views", index, "kpi", "value", "property"), \
                f"'{read}': a headline KPI is the producer's number; a formula runs for a display column"
    for level, where, message in facet_problems(doc, types):
        yield level, lines.line(where), where, message
    for level, where, message in open_problems(doc, link):
        yield level, lines.line(where), where, message
    for level, where, message in time_problems(doc, types):
        yield level, lines.line(where), where, message
    for level, where, message in grouping_problems(doc, types):
        yield level, lines.line(where), where, message
    for level, where, message in scene_problems(doc):
        yield level, lines.line(where), where, message
    for level, where, message in navigation_problems(doc):
        yield level, lines.line(where), where, message
    if properties is None:
        return
    formulas = set((doc.get("formulas") or {}).keys())
    for where, name in referenced(doc):
        if not isinstance(name, str) or not name or name.startswith("@"):
            continue  # "@…" names a pivot column (table lane), not a property
        if name.startswith("file."):
            continue  # Bases' file namespace: the host provides it when rows are notes
        if name.startswith("formula."):
            # a value with several sources is a formula with no text: `formula.<it>` is Bases' name for its column
            if name[8:] not in formulas and f"{name[8:]}@*" not in properties:
                yield "error", lines.line(where), where, f"'{name}' names a formula this file does not define"
            continue
        bare = name[5:] if name.startswith("note.") else name
        if bare not in properties:
            yield "error", lines.line(where), where, f"'{name}' is not a property of {dataset_name}{suggest(bare, properties)}"
    # the 3D cards' columns read from the default dataset (CONTRACT §32; the Node checker's sceneNames)
    for where, name, why in scene_names(doc):
        if name not in properties:
            yield "error", lines.line(where), where, f"'{name}' is not a property of {dataset_name}{suggest(name, properties)}" + (f" ({why})" if why else "")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate .base view files (Obsidian Bases + data-ui extensions).")
    parser.add_argument("files", nargs="+", type=pathlib.Path)
    parser.add_argument("--data", type=pathlib.Path, help="the data the files view (rows, or a schema sidecar): its property names are checked")
    parser.add_argument("--quiet", action="store_true", help="print only the summary line")
    args = parser.parse_args(argv)
    properties = dataset_properties(args.data) if args.data else None
    types = dataset_types(args.data) if args.data else None
    link = dataset_link(args.data) if args.data else ...
    errors = warnings = 0
    for path in args.files:
        for level, line, where, message in check_file(path, properties, args.data.name if args.data else "", types, link):
            errors += level == "error"
            warnings += level == "warning"
            if not args.quiet:
                print(f"{path}:{line}: {level}: {show(where)}: {message}")
    noun = "file" if len(args.files) == 1 else "files"
    print(f"checked {len(args.files)} {noun}{f' against {args.data.name}' if args.data else ''}: {errors} errors, {warnings} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
