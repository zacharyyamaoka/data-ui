# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "mujoco==3.17.0"]
# ///
"""Write the meshed UR5e for the 3D card (docs/peps/0005-dashboard-cards.md §2b `scene3d.robot`): the link meshes as
one GLB and each link's world pose per situation, so the card only applies poses (traj_compare's RobotDisplay split:
bam_ws .../traj_compare/model.py computes link poses in Python, its viewer3d.js only sets them).

    ~/pidtuna/.venv/bin/python -I gallery/examples/pid-tuning/source/build_robot.py

Inputs (read-only):
  MENAGERIE (default ~/.cache/lk-gui/library/mujoco_menagerie): google-deepmind/mujoco_menagerie's
    universal_robots_ur5e/ur5e.xml and its OBJ meshes (BSD-3-Clause, Copyright 2018 ROS Industrial Consortium; the
    LICENSE beside ur5e.xml). Only the visual geoms (group 2) are read, through MuJoCo's compiled model.
  PIDTUNA_DATA, MODEL: as source/build_replay.py (ur5e.json's coordinated tape; ur5e_bare.xml for the FK), whose
    helpers this script imports so both files read the same tape on the same time grid.

Writes:
  media/ur5e_links.glb: one node per body (base … wrist_3_link), named exactly as the body, each holding that body's
    visual meshes in the body's own frame, one primitive per Menagerie material (PBR base colour from its rgba, read as
    sRGB). Vertices welded (MuJoCo stores one per face corner), 16-bit indices, no normals (the card creases its own),
    nodes at the zero pose. No decimation: welding alone brings it under 2 MB with every triangle kept.
  robot.json: rows {t, situation, px, py, pz, <link>_x/_y/_z, <link>_qw/_qx/_qy/_qz} at 25 Hz for target, factory,
    tuned and oracle: MuJoCo forward kinematics of the replayed joint angles (xpos, xquat per body; the tool site's
    xpos). SIMULATED, never measured.
  ../dashboard-cards/robot.json: the same rows for the catalog's three situations (target, factory, tuned), so that
    case reads only its own folder (tools/test_rerun_export.py copies it alone); its view points at this case's GLB.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import struct

import numpy as np

HERE = pathlib.Path(__file__).resolve().parents[1]
MENAGERIE = pathlib.Path(os.environ.get("MENAGERIE", "~/.cache/lk-gui/library/mujoco_menagerie"))
UR5E = MENAGERIE / "universal_robots_ur5e" / "ur5e.xml"
SITUATIONS = ("target", "factory", "tuned", "oracle")
# WHY 0.04 s: 25 Hz lands on every fourth 100 Hz sample, so each row is the replay's own sample (never an interpolated
# angle) and the file stays a third of tool.json's 50 Hz per column; the card slerps between rows
STEP = 0.04
ROUGHNESS = {"black": 0.45, "jointgray": 0.5, "linkgray": 0.4, "urblue": 0.55}

spec = importlib.util.spec_from_file_location("build_replay", pathlib.Path(__file__).with_name("build_replay.py"))
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    # WHY: glTF's baseColorFactor is linear; Menagerie's rgba is what MuJoCo's viewer puts on screen (display sRGB)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


# ---------------------------------------------------------------- the GLB

def link_meshes(mujoco, model) -> dict[str, list[dict]]:
    """Per body: one welded triangle list per material, vertices in the body frame."""

    out: dict[str, list[dict]] = {}
    for body_id in range(1, model.nbody):
        body = model.body(body_id).name
        groups: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}
        for g in np.flatnonzero(model.geom_bodyid == body_id):
            if model.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH or model.geom_group[g] != 2:
                continue
            m = model.geom_dataid[g]
            v = model.mesh_vert[model.mesh_vertadr[m]: model.mesh_vertadr[m] + model.mesh_vertnum[m]].astype(np.float64)
            f = model.mesh_face[model.mesh_faceadr[m]: model.mesh_faceadr[m] + model.mesh_facenum[m]].astype(np.int64)
            rot = np.zeros(9)
            mujoco.mju_quat2Mat(rot, model.geom_quat[g])
            groups.setdefault(model.material(model.geom_matid[g]).name, []).append((v @ rot.reshape(3, 3).T + model.geom_pos[g], f))
        prims = []
        for material, parts in groups.items():
            verts, faces, base = [], [], 0
            for v, f in parts:
                verts.append(v)
                faces.append(f + base)
                base += len(v)
            v32 = np.concatenate(verts).astype(np.float32)
            # weld: MuJoCo keeps one vertex per face corner (for its normals); equal float32 positions become one
            uniq, inverse = np.unique(v32, axis=0, return_inverse=True)
            tri = inverse.reshape(-1)[np.concatenate(faces)]
            keep = (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
            prims.append({"material": material, "positions": uniq, "indices": tri[keep], "dropped": int((~keep).sum())})
        out[body] = prims
    return out


def write_glb(path: pathlib.Path, links: dict[str, list[dict]], materials: dict[str, list[float]], rest: dict, extras: dict) -> dict:
    """glTF 2.0 binary (Khronos spec §4.4): a JSON chunk and one BIN chunk; every bufferView 4-byte aligned."""

    blob = bytearray()
    views, accessors, meshes, nodes = [], [], [], []

    def view(data: bytes, target: int) -> int:
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": target})
        blob.extend(data)
        return len(views) - 1

    names = list(materials)
    tris = verts = 0
    for body, prims in links.items():
        primitives = []
        for p in prims:
            pos, idx = p["positions"], p["indices"]
            small = len(pos) < 65536
            accessors.append({"bufferView": view(pos.astype("<f4").tobytes(), 34962), "componentType": 5126, "count": len(pos),
                              "type": "VEC3", "min": pos.min(axis=0).tolist(), "max": pos.max(axis=0).tolist()})
            a_pos = len(accessors) - 1
            accessors.append({"bufferView": view(idx.astype("<u2" if small else "<u4").reshape(-1).tobytes(), 34963),
                              "componentType": 5123 if small else 5125, "count": int(idx.size), "type": "SCALAR"})
            primitives.append({"attributes": {"POSITION": a_pos}, "indices": len(accessors) - 1, "material": names.index(p["material"]), "mode": 4})
            tris += len(idx)
            verts += len(pos)
        node = {"name": body}
        if primitives:
            meshes.append({"name": body, "primitives": primitives})
            node["mesh"] = len(meshes) - 1
        p, q = rest[body]
        node["translation"] = [float(c) for c in p]
        node["rotation"] = [float(q[1]), float(q[2]), float(q[3]), float(q[0])]   # glTF is xyzw, MuJoCo wxyz
        nodes.append(node)
    doc = {
        "asset": {"version": "2.0", "generator": "data-ui gallery/examples/pid-tuning/source/build_robot.py", "extras": extras},
        "scene": 0, "scenes": [{"name": "ur5e", "nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes,
        "materials": [{"name": n, "pbrMetallicRoughness": {"baseColorFactor": c, "metallicFactor": 0.0, "roughnessFactor": ROUGHNESS.get(n, 0.5)}}
                      for n, c in materials.items()],
        "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(blob)}],
    }
    while len(blob) % 4:
        blob.append(0)
    text = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    total = 12 + 8 + len(text) + 8 + len(blob)
    data = struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    path.write_bytes(data)
    return {"bytes": len(data), "triangles": tris, "vertices": verts}


def same_kinematics(mujoco, menagerie, bare) -> float:
    """Worst body-position gap between Menagerie's ur5e.xml and pidtuna's ur5e_bare.xml over 50 random poses: the
    meshes come from one file and the poses from the other, so they must agree."""

    assert [bare.joint(j).name for j in range(bare.njnt)] == [menagerie.joint(j).name for j in range(menagerie.njnt)], "joint order differs"
    rng = np.random.default_rng(0)
    worst = 0.0
    for _ in range(50):
        q = rng.uniform(-np.pi, np.pi, menagerie.nq)
        poses = []
        for m in (menagerie, bare):
            d = mujoco.MjData(m)
            d.qpos[:] = q
            mujoco.mj_kinematics(m, d)
            poses.append({m.body(b).name: (d.xpos[b].copy(), d.xquat[b].copy()) for b in range(1, m.nbody)})
        for name, (p, qq) in poses[0].items():
            p2, q2 = poses[1][name]
            worst = max(worst, float(np.abs(p - p2).max()), float(min(np.abs(qq - q2).max(), np.abs(qq + q2).max())))
    return worst


# ---------------------------------------------------------------- the poses

def poses(robot: dict, mujoco) -> tuple[list[dict], list[str], dict]:
    tape = replay.tape_of(robot, "coordinated")
    dt = tape["dt"]
    model, data = replay.load_model(mujoco, for_render=False)
    bodies = replay.chain(model)
    links = [model.body(b).name for b in bodies]
    site = model.site("tool")
    tool = {"link": model.body(site.bodyid[0]).name, "pos": [float(c) for c in model.site_pos[site.id]],
            "quat": [float(c) for c in model.site_quat[site.id] / np.linalg.norm(model.site_quat[site.id])]}
    rows = []
    for situation in SITUATIONS:
        last: dict[str, np.ndarray] = {}
        for t in replay.grid(tape, STEP):
            angles = {}
            for joint in robot["joints"]:
                series = tape["target"][joint["name"]] if situation == "target" else tape["rungs"][situation][joint["name"]]
                angles[joint["name"]] = replay.at(series, dt, t)
            if any(v is None for v in angles.values()):
                continue
            replay.pose(model, data, mujoco, robot, angles)
            p = data.site("tool").xpos
            row = {"t": round(t, 3), "situation": situation, "px": round(float(p[0]), 6), "py": round(float(p[1]), 6), "pz": round(float(p[2]), 6)}
            for b, name in zip(bodies, links):
                q = data.xquat[b].copy()
                # WHY one hemisphere per link along the run: q and −q are the same rotation, and a sign flip between two
                # rows would make the card's slerp (and any lerp) swing the long way round
                if name in last and float(np.dot(q, last[name])) < 0:
                    q = -q
                last[name] = q
                for axis, v in zip("xyz", data.xpos[b]):
                    row[f"{name}_{axis}"] = round(float(v), 6)
                for axis, v in zip("wxyz", q):
                    row[f"{name}_q{axis}"] = round(float(v), 6)
            rows.append(row)
    return rows, links, tool


def main() -> None:
    import mujoco

    menagerie = mujoco.MjModel.from_xml_path(str(UR5E))
    bare, _ = replay.load_model(mujoco, for_render=False)
    gap = same_kinematics(mujoco, menagerie, bare)
    assert gap < 1e-9, f"ur5e_bare.xml and Menagerie's ur5e.xml disagree on body poses by {gap}"

    zero = mujoco.MjData(menagerie)
    mujoco.mj_kinematics(menagerie, zero)
    rest = {menagerie.body(b).name: (zero.xpos[b].copy(), zero.xquat[b].copy()) for b in range(1, menagerie.nbody)}
    materials = {menagerie.material(i).name: [*srgb_to_linear(menagerie.mat_rgba[i][:3].astype(np.float64)).round(6).tolist(), 1.0]
                 for i in range(menagerie.nmat)}
    links = link_meshes(mujoco, menagerie)
    used = {p["material"] for prims in links.values() for p in prims}
    materials = {k: v for k, v in materials.items() if k in used}
    licence = (MENAGERIE / "universal_robots_ur5e" / "LICENSE").read_text(encoding="utf-8").splitlines()[0]
    head = os.popen(f"git -C {MENAGERIE} rev-parse --short HEAD 2>/dev/null").read().strip() or "unknown"
    extras = {"source": f"google-deepmind/mujoco_menagerie@{head} universal_robots_ur5e/ur5e.xml, visual geoms (group 2), compiled by MuJoCo {mujoco.__version__}",
              "license": f"BSD-3-Clause ({licence}); universal_robots_ur5e/LICENSE in mujoco_menagerie"}
    media = HERE / "media"
    media.mkdir(exist_ok=True)
    glb = write_glb(media / "ur5e_links.glb", links, materials, rest, extras)
    dropped = sum(p["dropped"] for prims in links.values() for p in prims)
    print(f"media/ur5e_links.glb: {glb['bytes']:,} bytes, {glb['triangles']:,} triangles, {glb['vertices']:,} vertices "
          f"({dropped} degenerate after welding dropped); bare vs Menagerie body poses agree within {gap:.1e}")

    ur5e = json.loads((replay.DATA / "ur5e.json").read_text(encoding="utf-8"))
    rows, names, tool = poses(ur5e, mujoco)
    assert names == list(links), f"FK chain {names} is not the GLB's nodes {list(links)}"
    props = {
        "t": {"type": "number", "unit": "s", "digits": 3, "note": f"Seconds from the target's start; every {STEP} s (25 Hz) of the 100 Hz replay, each row the replay's own sample."},
        "situation": {"type": "text", "display": "badge", "note": "target or one of pidtuna's controller rungs (sim; the analytic rung is left out of the 3D card)."},
        "px": {"type": "number", "unit": "m", "digits": 6, "note": "Tool site `tool` world x: MuJoCo forward kinematics of the replayed joint angles (sim), model ur5e_bare.xml. Rounded to 1 µm."},
        "py": {"type": "number", "unit": "m", "digits": 6, "note": "Tool site world y, as px."},
        "pz": {"type": "number", "unit": "m", "digits": 6, "note": "Tool site world z (up), as px."},
    }
    for name in names:
        for axis in "xyz":
            props[f"{name}_{axis}"] = {"type": "number", "unit": "m", "digits": 6, "hidden": True,
                                       "note": f"{name}'s origin, world {axis} (MuJoCo xpos), FK of the replayed joint angles (sim). Rounded to 1 µm."}
        for axis in "wxyz":
            props[f"{name}_q{axis}"] = {"type": "number", "digits": 6, "hidden": True,
                                        "note": f"{name}'s world orientation, quaternion {axis} in MuJoCo's wxyz order (xquat), FK (sim); one sign along each run. Rounded to 1e-6."}
    source = (f"{replay.SRC}: ur5e.json tapes[coordinated]; FK by MuJoCo {mujoco.__version__} on {replay.MODEL} (pidtuna f93cf9c), "
              f"whose body poses equal Menagerie ur5e.xml's within {gap:.0e} over 50 random poses. Meshes: pid-tuning/media/ur5e_links.glb "
              f"({extras['source']}; {extras['license']}). Written by pid-tuning/source/build_robot.py.")
    doc = {"id": "pid-tuning-ur5e-robot", "title": "UR5e · coordinated tape · link poses per situation for the meshed 3D robot (sim, FK)",
           "titleProperty": "situation", "source": source,
           "robot": {"model": "media/ur5e_links.glb", "links": names, "tool": tool}, "properties": props, "rows": rows}
    replay.write("robot.json", doc)
    catalog = HERE.parent / "dashboard-cards"
    replay.HERE = catalog   # write() names its file under HERE
    replay.write("robot.json", {**doc, "id": "dashboard-cards-ur5e-robot", "source": f"pid-tuning/robot.json: situations target, factory, tuned. {source}",
                                "robot": {**doc["robot"], "model": "../pid-tuning/media/ur5e_links.glb"},
                                "rows": [r for r in rows if r["situation"] in ("target", "factory", "tuned")]})


if __name__ == "__main__":
    main()
