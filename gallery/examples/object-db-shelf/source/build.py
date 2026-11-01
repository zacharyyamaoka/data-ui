"""Build the object-db cases' data: a PUBLIC-SAFE sample of BAM's object library (read-only) for data-ui's gallery.

    ~/object-database/.venv/bin/python -I gallery/examples/object-db-shelf/source/build.py

WHY public-safe (2026-10-27): data-ui's gallery is published (data-ui.dev). The integrator blocked the first cut,
whose rows came from customer waste streams and supplier research. This build takes ONLY what the objectdb.dev
public-data review allows: open-licence scans (Google Scanned Objects, CC BY 4.0; EGAD, BSD-3-Clause) and BAM's own
generated primitives ("synthetic", "generated"). Excluded: supplier research (researched), scans whose licence is
non-commercial or unclear (GraspNet-1B, GraspClutter6D), every customer, every customer mix and stream, tags (they
carry customer and stream names), who labelled a row, and archive paths. The one mix is the published RECYC-QUEBEC
2023-24 municipal audit (its shares and their cited notes only). A deny-list check runs before anything is committed.

Writes, beside this folder:
    notes/<id>.md    each sampled object's PUBLIC note: the library note's public fields, as frontmatter
    objects.json     read back from notes/ (so the raw source view's `origin` is the file each row really came from)
    types.json, materials.json, spectra.json (spectra with a stated licence only), mixes.json + mix_list.json (the
                     public audit), taxonomy.json
    thumbs/<id>.webp the library's own poster renders, copied (pixels only; no metadata)
    meshes/<id>.glb  scans: 256 px JPEG texture + gltfpack 1.3.0 (~3k triangles, meshopt); primitives from
                     primitive_size_m. glTF-standard: +Y up, metres.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import trimesh
import yaml
from PIL import Image

LIB = Path("~/bam-waste-objects")
HERE = Path(__file__).resolve().parent.parent
GLTFPACK = ["npx", "--yes", "gltfpack@1.3.0"]
TARGET_TRIANGLES = 3000
MAX_OBJ_BYTES = 150 * 1024 * 1024  # a 890 MB scan is not worth a thumbnail's minute; it keeps its poster only

# the sample: public sources only (deterministic: spread over each source's sorted ids)
PUBLIC = {"google-scanned-objects": 150, "egad": 30, "synthetic": 120, "generated": 66}
LICENCE = {"google-scanned-objects": "CC BY 4.0 (Google Scanned Objects)", "egad": "BSD-3-Clause (EGAD, Morrison/Corke/Leitner, QUT 2020)",
           "synthetic": "generated (BAM)", "generated": "generated (BAM)"}
# the public note's fields, in CONTRACT order: never tags, labels_by, mesh paths, evidence, brand-free product research
PUBLIC_FIELDS = ["id", "name", "kind", "type", "material", "form", "colour", "grade", "damage", "rigidity", "brand", "shape",
                 "length_mm", "width_mm", "height_mm", "bbox_volume_ml", "volume_ml", "size_class", "geometry_class", "fits_2f85",
                 "primitive_size_m", "soft_kind", "mass_g", "mass_source", "density_g_ml", "colour_rgb", "source", "source_ref", "license", "added",
                 "label_confidence"]
# the one public mix: RECYC-QUEBEC's published audit (the library's household-blue-bin composition, its rows only)
PUBLIC_MIX = {"from": "household-blue-bin", "id": "recyc-quebec-municipal-2023", "name": "Household recycling, Quebec municipal (RECYC-QUEBEC 2023-24 audit)",
              "basis": "mass", "measured": True,
              "source": "https://www.recyc-quebec.gouv.qc.ca/sites/default/files/documents/etude-caracterisation-centre-de-tri-2023-2024.pdf#page=15"}

FRONT = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)
LINK = re.compile(r"^\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]$")

def note(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    m = FRONT.match(text)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


def unlink(v):
    """'[[paperboard]]' -> 'paperboard' (a wikilink's target); anything else unchanged."""
    if isinstance(v, str):
        m = LINK.match(v.strip())
        return m.group(1) if m else v
    if isinstance(v, list):
        return [unlink(x) for x in v]
    return v


# ------------------------------------------------------------------------------------------------ read the library
def read_library():
    objects = []
    for p in sorted((LIB / "objects").glob("*/*.md")):
        fm, _ = note(p)
        if fm.get("kind") == "instance":
            fm["_dir"] = p.parent
            fm["_note"] = p
            objects.append(fm)
    types = {}
    for p in sorted((LIB / "types").glob("*.md")):
        fm, body = note(p)
        if fm.get("kind") == "type":
            types[fm["id"]] = fm
    materials = {}
    for p in sorted((LIB / "materials").glob("*.md")):
        fm, body = note(p)
        if fm.get("kind") == "material":
            materials[fm["id"]] = fm
    mixes = {}
    for p in sorted((LIB / "mixes").glob("*.md")):
        fm, body = note(p)
        if fm.get("kind") != "mix":
            continue
        comp = []
        sec = body.split("## Composition", 1)
        if len(sec) == 2:
            for line in sec[1].split("\n## ", 1)[0].splitlines():
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) >= 2 and cells[0].startswith("[["):
                    try:
                        comp.append({"type": unlink(cells[0]), "share": float(cells[1]), "note": cells[2] if len(cells) > 2 else ""})
                    except ValueError:
                        pass
        fm["composition"] = comp
        mixes[fm["id"]] = fm
    customers = {}
    for p in sorted((LIB / "customers").glob("*.md")):
        fm, _ = note(p)
        if fm.get("kind") == "customer":
            customers[fm["id"]] = fm
    return objects, types, materials, mixes, customers



def glb_parts(data: bytes):
    magic, version, length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, "not a GLB"
    off, chunks = 12, []
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunks.append([ctype, data[off + 8: off + 8 + clen]])
        off += 8 + clen
    return chunks


def glb_join(chunks) -> bytes:
    body = b""
    for ctype, payload in chunks:
        pad = (b" " if ctype == 0x4E4F534A else b"\0") * ((4 - len(payload) % 4) % 4)
        payload = payload + pad
        body += struct.pack("<II", len(payload), ctype) + payload
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


def to_y_up_metres(path: Path, scale: float):
    """Wrap every scene root in one node: rotate Z-up to glTF's Y-up (-90 deg about X), scale to metres."""
    chunks = glb_parts(path.read_bytes())
    doc = json.loads(chunks[0][1])
    nodes = doc.setdefault("nodes", [])
    for scene in doc.get("scenes", []):
        roots = scene.get("nodes", [])
        nodes.append({"name": "z-up-to-y-up", "rotation": [-0.7071068, 0, 0, 0.7071068], "scale": [scale] * 3, "children": roots})
        scene["nodes"] = [len(nodes) - 1]
    chunks[0][1] = json.dumps(doc, separators=(",", ":")).encode()
    path.write_bytes(glb_join(chunks))


def prep_obj(src: Path, out: Path):
    """A temp folder the OBJ can be read from: the OBJ (symlinked), its .mtl rewritten to one 256 px JPEG texture."""
    head = src.open("r", errors="ignore").read(300000)
    m = re.search(r"^mtllib\s+(.+)$", head, re.M)
    mtl = m.group(1).strip() if m else None
    tex = None
    if mtl and (src.parent / mtl).exists():
        mm = re.search(r"map_Kd\s+(.+)", (src.parent / mtl).read_text(errors="ignore"))
        if mm:
            name = mm.group(1).strip()
            for c in (src.parent / name, src.parent.parent / "materials" / "textures" / Path(name).name):
                if c.exists():
                    tex = c
                    break
    (out / "m.obj").symlink_to(src)
    if mtl:
        (out / mtl).write_text("newmtl material_0\nKd 1 1 1\n" + ("map_Kd t.jpg\n" if tex else ""))
        if tex:
            im = Image.open(tex).convert("RGB")
            im.thumbnail((256, 256))
            im.save(out / "t.jpg", quality=82)
    return tex


def real_glb(o, dst: Path) -> dict | None:
    src = Path(o["mesh"])
    if not src.exists() or src.stat().st_size > MAX_OBJ_BYTES:
        return None
    faces = 0
    with src.open("r", errors="ignore") as f:
        for line in f:
            if line.startswith("f "):
                faces += 1
    with tempfile.TemporaryDirectory() as tmp:
        tex = prep_obj(src, Path(tmp))
        ratio = min(1.0, TARGET_TRIANGLES / max(1, faces))
        r = subprocess.run([*GLTFPACK, "-i", str(Path(tmp) / "m.obj"), "-o", str(dst), "-si", f"{ratio:.5f}", "-sa", "-cc"], capture_output=True, text=True)
        if r.returncode or not dst.exists():
            print("gltfpack failed:", o["id"], r.stderr[-300:], file=sys.stderr)
            return None
    to_y_up_metres(dst, float(o.get("mesh_scale") or 1.0))
    return {"triangles_source": faces, "textured": bool(tex)}


def primitive_glb(o, dst: Path) -> dict | None:
    shape, size = o.get("shape"), o.get("primitive_size_m")
    if shape not in ("box", "cylinder", "sphere") or not size:
        return None
    try:
        size = [float(x) for x in size]
    except (TypeError, ValueError):
        # WHY float(): PyYAML reads YAML 1.1, where 5e-05 (no dot) is a string, not a number; an unreadable size
        # keeps the card's poster and the build names the note
        print(f"primitive_size_m unreadable, no GLB: {o['id']} {o.get('primitive_size_m')!r}", file=sys.stderr)
        return None
    if shape == "box":
        m = trimesh.creation.box(extents=[2 * s for s in size])
    elif shape == "cylinder":
        m = trimesh.creation.cylinder(radius=size[0], height=2 * size[1], sections=40)
    else:
        m = trimesh.creation.icosphere(subdivisions=3, radius=size[0])
    rgb = o.get("colour_rgb") or "#b8b8b8"
    rgba = [int(rgb[i:i + 2], 16) / 255 for i in (1, 3, 5)] + [1.0]
    m.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(baseColorFactor=rgba, metallicFactor=0.0, roughnessFactor=0.7))
    dst.write_bytes(m.export(file_type="glb"))
    to_y_up_metres(dst, 1.0)  # MuJoCo primitives are Z-up, already in metres
    return {"triangles_source": len(m.faces), "textured": False}


# ------------------------------------------------------------------------------------------------ the poster's camera
# WHY (Zach, 2026-10-26): "ideally the 3D view starts at the same location the thumbnail photo is taken from". Each
# poster renderer's camera direction (glTF frame: +Y up; the library's Z-up (x, y, z) is (x, z, -y) here) and vertical
# FOV, read from the code that made the posters; the framing is measured from the poster itself (its silhouette box),
# because real-scan posters are cropped to the object and padded square (object_database/importers/thumbs.py).
POSTER_CAMERAS = {
    # tools/render_thumbs.py: direction (0.9, -1.1, 0.8) in Z-up, yfov 30 deg
    "scan": {"dir": [0.9, 0.8, 1.1], "fov": 30, "known": True},
    # importers/generated.py render_all (generated + researched primitives): MuJoCo azimuth 135, elevation -28, fovy 45
    "mujoco": {"dir": [0.6236, 0.4695, 0.6236], "fov": 45, "known": True},
    # importers/containers.py: azimuth 135, elevation -58, fovy 45
    "container": {"dir": [0.3747, 0.8480, 0.3747], "fov": 45, "known": True},
}
UNKNOWN = {"graspclutter6d", "graspnet1b", "synthetic"}  # posters from the Oct 5 report / the simulator-eval catalogue


def poster_camera(o) -> str:
    if o.get("source") in ("google-scanned-objects", "egad", "graspclutter6d", "graspnet1b") or o.get("shape") == "mesh":
        return "scan"
    if "container" in (o.get("tags") or []):
        return "container"
    return "mujoco"


def silhouette_box(path: Path, tolerance: int = 24):
    """The poster's object box [x0, y0, x1, y1] (0-1, y down). A pixel is object when it differs from its row's backdrop,
    read as the line between the row's first and last pixels: a white poster and MuJoCo's vertical studio gradient alike
    (the browser check measures the live frame the same way)."""
    import numpy as np

    with Image.open(path) as im:
        a = np.asarray(im.convert("RGB"), dtype=np.float32)
    h, w, _ = a.shape
    t = np.linspace(0.0, 1.0, w)[None, :, None]
    backdrop = a[:, :1, :] * (1 - t) + a[:, -1:, :] * t
    mask = np.abs(a - backdrop).max(axis=2) > tolerance
    if not mask.any():
        return None
    ys, xs = np.where(mask)
    h, w = mask.shape
    return [round(xs.min() / w, 4), round(ys.min() / h, 4), round((xs.max() + 1) / w, 4), round((ys.max() + 1) / h, 4)]


def mesh_view(o, poster: Path | None):
    """{dir, fov, camera, box | dist}: a cropped scan poster gets its measured silhouette box; a MuJoCo render (uncropped,
    384 px square, studio backdrop) gets the renderer's own distance, so no measuring is needed."""
    kind = poster_camera(o)
    cam = POSTER_CAMERAS[kind]
    view = {"dir": cam["dir"], "fov": cam["fov"], "camera": kind if o.get("source") not in UNKNOWN else f"{kind} (assumed)"}
    size = o.get("primitive_size_m")
    try:
        size = [float(x) for x in size] if size else None
    except (TypeError, ValueError):
        size = None
    # WHY a measured box for every poster: the silhouette is the poster's framing whatever the renderer's internals
    # (MuJoCo's own distance rule left the live model ~21 % small: measured 2026-10-26); `dist` stays as the fallback
    box = silhouette_box(poster) if poster and poster.exists() else None
    if box:
        view["box"] = box
    if kind == "scan":
        pass
    elif kind == "container" and all(o.get(k) for k in ("length_mm", "width_mm", "height_mm")):
        view["dist"] = round(2.6 * 0.5 * (sum((o[k] / 1000) ** 2 for k in ("length_mm", "width_mm", "height_mm")) ** 0.5), 5)
    elif size:
        shape = o.get("shape")
        rbound = (sum(v * v for v in size) ** 0.5 if shape == "box" else (size[0] ** 2 + size[1] ** 2) ** 0.5 if shape == "cylinder" else size[0])
        view["dist"] = round(3.0 * rbound, 5)  # importers/generated.py: camera.distance = 3 x geom_rbound
    return view


# ------------------------------------------------------------------------------------------------ outputs
BASIS = {"measured": "measured", "datasheet": "datasheet", "seller": "seller", "estimated": "estimate", "synthetic": "stand-in", "derived": "derived"}


def rich(value, source_kind, note=None):
    if value is None:
        return {"value": None, "why": f"not known ({source_kind or 'no source'})"}
    out = {"value": value}
    if source_kind in BASIS:
        out["basis"] = BASIS[source_kind]
    if note:
        out["note"] = note
    return out


def infer(values):
    vals = [v["value"] if isinstance(v, dict) and "value" in v else v for v in values]
    vals = [v for v in vals if v is not None]
    if vals and all(isinstance(v, bool) for v in vals):
        return "boolean"
    if vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return "number"
    if vals and all(isinstance(v, list) for v in vals):
        return "list"
    return "text"


def write_json(name, obj):
    """WHY every key declared: data-ui's runtime shape knows only the properties it lists (docs/CONTRACT.md §3)."""
    if "rows" in obj:
        props = obj.setdefault("properties", {})
        for key in dict.fromkeys(k for r in obj["rows"] for k in r):
            props.setdefault(key, {})
            props[key].setdefault("type", infer([r.get(key) for r in obj["rows"]]))
    (HERE / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")



def pick(objects):
    """Every public source's objects, spread over its sorted ids (every k-th), up to PUBLIC[source]."""
    by = defaultdict(list)
    for o in objects:
        if o.get("source") in PUBLIC:
            by[o["source"]].append(o)
    out = []
    for src, cap in PUBLIC.items():
        lst = sorted(by[src], key=lambda o: o["id"])
        if src == "google-scanned-objects":
            lst = [o for o in lst if o.get("mesh") and Path(o["mesh"]).exists()]
        k = max(1.0, len(lst) / cap)
        out += [lst[int(i * k)] for i in range(min(cap, len(lst)))]
    return sorted(out, key=lambda o: o["id"])


def num(v):
    try:
        return float(v) if isinstance(v, str) and re.fullmatch(r"[-+]?\d*\.?\d+(e[-+]?\d+)?", v, re.I) else v
    except ValueError:
        return v


def public_note(o) -> str:
    """The public note: CONTRACT-ordered public fields as YAML frontmatter, links as plain ids, nothing else."""
    lines = ["---"]
    for k in PUBLIC_FIELDS:
        v = o.get(k)
        if k in ("type", "material"):
            v = unlink(v)
        if k == "license":
            v = LICENCE[o["source"]]
        if k == "primitive_size_m" and v:
            v = [num(x) for x in v]
        if isinstance(v, str):
            v = num(v)
        if hasattr(v, "isoformat"):  # YAML dates (added) stay ISO text
            v = v.isoformat()
        # plain YAML, as the library's notes are written; floats keep a dot so a YAML 1.1 reader keeps them numbers
        lines.append(yaml.safe_dump({k: v}, allow_unicode=True, sort_keys=False, default_flow_style=True, width=10**6).strip().strip("{}"))
    lines += ["---", "", f"Public export of `{o['id']}` from BAM's object library for data-ui's gallery (source/build.py): "
              "the public fields as stored; tags, labelling provenance and archive paths are not exported.", ""]
    return "\n".join(lines)


def read_public_note(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1]) or {}


def main():
    objects, types, materials, mixes, customers = read_library()
    picked = pick(objects)
    print(f"{len(objects)} instances in the library; {len(picked)} public-safe sampled: {dict(Counter(o['source'] for o in picked))}", file=sys.stderr)

    # start clean: nothing from the first cut survives (rows, notes, posters, meshes of excluded objects)
    for d in ("thumbs", "meshes", "notes", "sources"):
        shutil.rmtree(HERE / d, ignore_errors=True)
    for f in ("customers.json",):
        (HERE / f).unlink(missing_ok=True)
    for d in ("thumbs", "meshes", "notes"):
        (HERE / d).mkdir()

    comp = mixes[PUBLIC_MIX["from"]]["composition"]
    mix_types = {c["type"] for c in comp}
    rows, mesh_stats = [], []
    for o in picked:
        oid = o["id"]
        note_path = HERE / "notes" / f"{oid}.md"
        note_path.write_text(public_note(o), encoding="utf-8")
        fm = read_public_note(note_path)  # WHY read back: the row comes from the public note, so `origin` is truthful
        thumb = unlink(o.get("thumbnail"))
        thumb_rel = None
        if thumb and (o["_dir"] / thumb).exists():
            # WHY re-encode, not copy: pixels only, so no metadata block can carry a name
            Image.open(o["_dir"] / thumb).convert("RGB").save(HERE / "thumbs" / f"{oid}.webp", "WEBP", quality=85)
            thumb_rel = f"thumbs/{oid}.webp"
        soft = unlink(o.get("soft_thumbnail"))
        soft_rel = None
        if soft and (o["_dir"] / soft).exists():
            Image.open(o["_dir"] / soft).convert("RGB").save(HERE / "thumbs" / f"{oid}.soft.webp", "WEBP", quality=85)
            soft_rel = f"thumbs/{oid}.soft.webp"
        glb = HERE / "meshes" / f"{oid}.glb"
        info = real_glb(o, glb) if o.get("shape") == "mesh" and o.get("mesh") else primitive_glb(o, glb)
        mesh_rel = f"meshes/{oid}.glb" if glb.exists() else None
        if mesh_rel:
            mesh_stats.append({"id": oid, "source": o.get("source"), "bytes": glb.stat().st_size, **(info or {})})
        real = fm.get("shape") == "mesh"
        rows.append({
            "id": oid, "kind": "instance", "name": fm["name"], "type": fm["type"], "material": fm["material"],
            "form": fm["form"], "colour": fm["colour"], "grade": fm["grade"], "damage": fm["damage"], "rigidity": fm["rigidity"],
            "brand": fm.get("brand"), "source": fm["source"], "geometry": "real scan" if real else f"primitive ({fm.get('shape')})",
            "size_class": fm.get("size_class"), "geometry_class": fm.get("geometry_class"), "fits_2f85": fm.get("fits_2f85"),
            "mass_g": rich(fm.get("mass_g"), fm.get("mass_source")),
            "length_mm": fm.get("length_mm"), "width_mm": fm.get("width_mm"), "height_mm": fm.get("height_mm"),
            "bbox_volume_ml": fm.get("bbox_volume_ml"),
            "mixes": [PUBLIC_MIX["id"]] if fm["type"] in mix_types else [],
            "soft_kind": fm.get("soft_kind"), "soft_thumbnail": soft_rel,
            "thumbnail": thumb_rel, "mesh": mesh_rel, "colour_rgb": fm.get("colour_rgb"),
            "mesh_view": mesh_view(o, HERE / thumb_rel if thumb_rel else None) if mesh_rel else None,
            "license": fm["license"], "label_confidence": fm.get("label_confidence"),
        })

    props = {
        "id": {"type": "text", "hidden": True}, "kind": {"type": "text", "hidden": True},
        "name": {"type": "text", "width": 220},
        "type": {"type": "text", "display": "badge", "facet": "values"},
        "material": {"type": "text", "display": "badge", "facet": "values"},
        "form": {"type": "text", "facet": "values"}, "colour": {"type": "text", "facet": "values"}, "grade": {"type": "text", "facet": "values"},
        "damage": {"type": "text", "facet": "values"}, "rigidity": {"type": "text", "facet": "values"},
        "brand": {"type": "text"}, "source": {"type": "text", "facet": "values"}, "geometry": {"type": "text", "facet": "values"},
        "size_class": {"type": "text"}, "geometry_class": {"type": "text"}, "fits_2f85": {"type": "boolean"},
        "mass_g": {"type": "number", "unitText": "g", "decimals": 1},
        "length_mm": {"type": "number", "unitText": "mm", "decimals": 0}, "width_mm": {"type": "number", "unitText": "mm", "decimals": 0},
        "height_mm": {"type": "number", "unitText": "mm", "decimals": 0}, "bbox_volume_ml": {"type": "number", "unitText": "mL", "decimals": 0},
        "mixes": {"type": "list"},
        "soft_kind": {"type": "text"}, "soft_thumbnail": {"type": "text", "media": "image", "hidden": True},
        "thumbnail": {"type": "text", "media": "image", "hidden": True},
        "mesh": {"type": "text", "media": "mesh", "hidden": True, "note": "glTF binary, +Y up, metres (built by source/build.py)"},
        "colour_rgb": {"type": "text", "hidden": True},
        "mesh_view": {"type": "text", "hidden": True, "note": "the poster's camera {dir, fov, box}: the live 3D starts where the poster was taken (CONTRACT §23, §29)"},
        "license": {"type": "text"}, "label_confidence": {"type": "text"},
    }
    write_json("objects.json", {
        "id": "bam-objects", "title": "BAM object library (public sample)", "titleProperty": "name", "imageProperty": "thumbnail",
        "origin": {"url": "notes/{id}.md"},
        "source": f"BAM's object library @ {git_head(LIB)}: {len(rows)} of {len(objects)} instances, public sources only "
                  f"(open-licence scans and BAM's generated primitives), sampled by source/build.py",
        "properties": props, "rows": rows,
    })

    # types: library-wide counts (the producer's number), a representative object in the public sample
    n_type = Counter(unlink(o.get("type")) for o in objects)
    rep = {}
    for r in rows:
        if r["mesh"] and (r["type"] not in rep or (rep[r["type"]]["geometry"] != "real scan" and r["geometry"] == "real scan")):
            rep[r["type"]] = r
    type_rows = []
    for tid, t in types.items():
        rr = rep.get(tid)
        type_rows.append({
            "id": tid, "kind": "type", "name": t.get("name"), "material": unlink(t.get("material")), "form": t.get("form"), "colour": t.get("colour"),
            "grade": t.get("grade"), "rigidity": t.get("rigidity"), "typical_mass_g": t.get("typical_mass_g"),
            "typical_length_mm": t.get("typical_length_mm"), "instances": n_type.get(tid, 0),
            "in_sample": sum(1 for r in rows if r["type"] == tid), "description": t.get("description"),
            "thumbnail": rr["thumbnail"] if rr else None, "mesh": rr["mesh"] if rr else None, "mesh_view": rr["mesh_view"] if rr else None,
            "example": rr["name"] if rr else None,
        })
    write_json("types.json", {"id": "bam-types", "title": "Types", "titleProperty": "name", "imageProperty": "thumbnail",
        "source": f"BAM's object library types @ {git_head(LIB)}; instances = library-wide count of {len(objects)}",
        "properties": {"id": {"type": "text", "hidden": True}, "kind": {"type": "text", "hidden": True}, "material": {"type": "text", "display": "badge"},
                       "typical_mass_g": {"type": "number", "unitText": "g"}, "typical_length_mm": {"type": "number", "unitText": "mm"},
                       "instances": {"type": "number", "decimals": 0}, "in_sample": {"type": "number", "decimals": 0},
                       "thumbnail": {"type": "text", "media": "image", "hidden": True}, "mesh": {"type": "text", "media": "mesh", "hidden": True},
                       "mesh_view": {"type": "text", "hidden": True}},
        "rows": type_rows})

    # materials + spectra: a spectrum is published only with a stated licence (USGS public domain, CC BY 4.0)
    n_mat = Counter(unlink(o.get("material")) for o in objects)
    spectra_rows, mat_rows = [], []
    for mid, m in materials.items():
        files = m.get("spectra") or []
        licensed = bool(m.get("spectral_license"))
        for f in files if licensed else []:
            path = LIB / f
            if not path.exists():
                continue
            lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
            label = Path(f).stem.split("__", 1)[1] if "__" in Path(f).stem else Path(f).stem
            buckets = defaultdict(list)
            for row in csv.DictReader(io.StringIO("\n".join(lines))):
                try:
                    w, r = float(row["wavelength_nm"]), float(row["reflectance"])
                except (TypeError, ValueError, KeyError):
                    continue
                if r == r and -1 < r < 2:
                    buckets[round(w / 20) * 20].append(r)
            for w in sorted(buckets):
                spectra_rows.append({"material": mid, "family": m.get("family"), "spectrum": f"{mid} · {label}", "wavelength_nm": w,
                                     "reflectance": round(sum(buckets[w]) / len(buckets[w]), 4)})
        mat_rows.append({
            "id": mid, "kind": "material", "name": m.get("name"), "family": m.get("family"), "resin_code": m.get("resin_code"),
            "density_g_cm3": {"value": m.get("density_g_cm3"), "basis": "datasheet", "source": m.get("density_source")} if m.get("density_g_cm3") else {"value": None, "why": "not recorded"},
            "spectra": len(files) if licensed else 0, "spectral_range_nm": m.get("spectral_range_nm") if licensed else None,
            "spectral_source": m.get("spectral_source") if licensed else None, "spectral_license": m.get("spectral_license"),
            "instances": n_mat.get(mid, 0),
        })
    write_json("materials.json", {"id": "bam-materials", "title": "Materials", "titleProperty": "name",
        "source": f"BAM's object library materials @ {git_head(LIB)}; spectra only where a licence is stated",
        "properties": {"id": {"type": "text", "hidden": True}, "kind": {"type": "text", "hidden": True}, "family": {"type": "text", "display": "badge", "facet": "values"},
                       "density_g_cm3": {"type": "number", "unitText": "g/cm³", "decimals": 2}, "spectra": {"type": "number", "decimals": 0},
                       "instances": {"type": "number", "decimals": 0}},
        "rows": mat_rows})
    write_json("spectra.json", {"id": "bam-spectra", "title": "Reflectance spectra", "titleProperty": "spectrum",
        "source": f"materials/spectra/*.csv @ {git_head(LIB)}, averaged into 20 nm bins by source/build.py (USGS splib07a, HZDR RODARE 2448, 4TU), licensed spectra only",
        "properties": {"wavelength_nm": {"type": "number", "unitText": "nm", "decimals": 0}, "reflectance": {"type": "number", "decimals": 3},
                       "family": {"type": "text", "facet": "values"}, "material": {"type": "text", "facet": "values"}},
        "rows": spectra_rows})

    # the public mix: the audit's composition rows (type, share, the audit's own note) and an example object
    by_type = defaultdict(list)
    for r in rows:
        by_type[r["type"]].append(r)
    mix_rows = []
    for c in comp:
        cands = by_type.get(c["type"], [])
        ex = next((r for r in cands if r["geometry"] == "real scan"), cands[0] if cands else None)
        mix_rows.append({
            "id": f"{PUBLIC_MIX['id']}:{c['type']}", "mix": PUBLIC_MIX["id"], "mix_name": PUBLIC_MIX["name"], "basis": PUBLIC_MIX["basis"],
            "measured": PUBLIC_MIX["measured"], "type": c["type"],
            "share": {"value": c["share"], "basis": "measured", "note": c["note"][:400]},
            "typical_mass_g": types.get(c["type"], {}).get("typical_mass_g"), "objects_in_sample": len(cands),
            "example": ex["name"] if ex else None, "thumbnail": ex["thumbnail"] if ex else None, "mesh": ex["mesh"] if ex else None,
            "mesh_view": ex["mesh_view"] if ex else None,
        })
    write_json("mixes.json", {"id": "bam-mixes", "title": "Mix compositions", "titleProperty": "type", "imageProperty": "thumbnail",
        "source": f"RECYC-QUEBEC, Etude de caracterisation des matieres recyclables, centres de tri 2023-2024, municipal column ({PUBLIC_MIX['source']}), mapped onto BAM's object types",
        "properties": {"share": {"type": "number", "decimals": 3}, "mix_name": {"type": "text", "facet": "values"},
                       "typical_mass_g": {"type": "number", "unitText": "g"}, "objects_in_sample": {"type": "number", "decimals": 0},
                       "thumbnail": {"type": "text", "media": "image", "hidden": True}, "mesh": {"type": "text", "media": "mesh", "hidden": True},
                       "mesh_view": {"type": "text", "hidden": True}},
        "rows": mix_rows})
    write_json("mix_list.json", {"id": "bam-mix-list", "title": "Mixes", "titleProperty": "name",
        "source": "the one public mix (RECYC-QUEBEC 2023-24 audit)",
        "properties": {"id": {"type": "text", "hidden": True}, "kind": {"type": "text", "hidden": True}, "measured": {"type": "boolean"},
                       "tags": {"type": "list"}, "types": {"type": "number", "decimals": 0}},
        "rows": [{"id": PUBLIC_MIX["id"], "kind": "mix", "name": PUBLIC_MIX["name"], "basis": PUBLIC_MIX["basis"], "measured": PUBLIC_MIX["measured"],
                  "tags": ["recycling", "household", "measured"], "source": PUBLIC_MIX["source"], "types": len(comp)}]})

    # taxonomy: family -> material -> type (frontmatter links; library-wide counts)
    nodes = []
    fams = sorted({m.get("family") or "other" for m in materials.values()})
    for f in fams:
        nodes.append({"id": f"family:{f}", "name": f, "kind": "family", "parent": None,
                      "instances": sum(n_mat.get(mid, 0) for mid, m in materials.items() if (m.get("family") or "other") == f)})
    for mid, m in materials.items():
        nodes.append({"id": f"material:{mid}", "name": m.get("name"), "kind": "material", "parent": f"family:{m.get('family') or 'other'}",
                      "instances": n_mat.get(mid, 0), "density_g_cm3": m.get("density_g_cm3")})
    known = set(materials)

    def rep_of(type_list):
        best = max((t for t in type_list if t["mesh"]), key=lambda t: t["instances"], default=None)
        return {"thumbnail": best["thumbnail"], "mesh": best["mesh"], "mesh_view": best["mesh_view"], "example": f'{best["example"]} ({best["name"]})'} if best else {}
    for n in nodes:
        if n["kind"] == "material":
            n.update(rep_of([t for t in type_rows if t["material"] == n["id"].split(":", 1)[1]]))
        else:
            fam = n["id"].split(":", 1)[1]
            n.update(rep_of([t for t in type_rows if (materials.get(t["material"], {}).get("family") or "other") == fam]))
    for t in type_rows:
        par = f"material:{t['material']}" if t["material"] in known else None
        nodes.append({"id": f"type:{t['id']}", "name": t["name"], "kind": "type", "parent": par, "instances": t["instances"],
                      "thumbnail": t["thumbnail"], "mesh": t["mesh"], "mesh_view": t["mesh_view"], "example": t["example"]})
    write_json("taxonomy.json", {"id": "bam-taxonomy", "title": "Family → material → type", "titleProperty": "name", "imageProperty": "thumbnail",
        "source": f"types' and materials' frontmatter @ {git_head(LIB)}; instances = library-wide counts",
        "properties": {"kind": {"type": "text", "display": "badge", "facet": "values"}, "instances": {"type": "number", "decimals": 0},
                       "parent": {"type": "text", "hidden": True},
                       "thumbnail": {"type": "text", "media": "image", "hidden": True}, "mesh": {"type": "text", "media": "mesh", "hidden": True},
                       "mesh_view": {"type": "text", "hidden": True}},
        "rows": nodes})

    (HERE / "source" / "mesh_stats.json").write_text(json.dumps(mesh_stats, indent=0) + "\n")
    sizes = [s["bytes"] for s in mesh_stats]
    print(f"rows {len(rows)}; meshes {len(sizes)}, {sum(sizes) / 1e6:.2f} MB, median {sorted(sizes)[len(sizes) // 2] / 1e3:.1f} KB; "
          f"thumbs {sum(p.stat().st_size for p in (HERE / 'thumbs').glob('*.webp')) / 1e6:.2f} MB", file=sys.stderr)

def git_head(repo: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "?"


if __name__ == "__main__":
    main()

