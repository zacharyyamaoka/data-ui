"""The Robot arm template's coverage files (PEP 0010 P2, §4.2 and §6), beside this folder:

  grid.json            BAM Reach's reach map as the trajectory contract's grid (gallery/robotics/schemas/grid.schema.json):
                       one row per tested position, its centre in mm and its value, the fraction of the 56 tested tool
                       orientations that are reachable there (BAM Reach's ReachMap.reach_scores: IK found, FK checked,
                       consistent, collision-free). cell_mm (the lattice step, 150 mm) and frame (BAM Reach's base frame,
                       ur_arm/base_link_ur) at the top level. The `voxels` panel draws it, its own frame, its own panel.
  media/workspace.glb  the arm's reachable volume in the poses' own frame (MuJoCo Menagerie's UR5e base, where
                       poses.json's tool points are): the convex hull of the tool point (arm_suite_sim's tcp, 12 cm out
                       of the flange) over 20,000 joint configurations drawn uniformly in each joint's range (seed 0),
                       kept above the floor (z ≥ 0, the suite's floor plane), in metres (glTF's unit). WHY not BAM
                       Reach's lattice for it: its frame is ur_arm/base_link_ur, and a workspace drawn over the runs must
                       be in their frame (frames are declared, never guessed).

    ~/bam_ws/.claude/worktrees/sim-to-real-motor-models-f1ee43/src/dev/bam_rack_twin/.venv/bin/python -B -I \\
        gallery/examples/robotics-arm/source/build_coverage.py
    (any venv with numpy, scipy and MuJoCo; that one carries all three)

Read-only: BAM Reach's workcell reach map (bam_ws src/core/mdp/agent/actor/trajectory_generation/bam_reach/out/
workcell_analysis/reach_maps/reach-001-reach_map.reach.npz, or $BAM_REACH_MAP) and ~/sim2real/dashboards/source/
arm_suite_sim.py's own model (imported, -B), with MuJoCo Menagerie's ur5e.xml it names. Self-checks: every grid value is
k/56, the hull holds every sampled tool point."""

from __future__ import annotations

import json
import os
import pathlib
import struct
import sys

sys.dont_write_bytecode = True
os.environ.setdefault("MUJOCO_GL", "egl")

import numpy as np  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE.parent
REACH = pathlib.Path(os.environ.get("BAM_REACH_MAP", str(pathlib.Path.home() / "bam_ws" / "src" / "core" / "mdp" / "agent" / "actor" / "trajectory_generation"
                                                         / "bam_reach" / "out" / "workcell_analysis" / "reach_maps" / "reach-001-reach_map.reach.npz")))
SUITE_DIR = pathlib.Path(os.environ.get("ARM_SUITE_SIM", str(pathlib.Path.home() / "sim2real" / "dashboards" / "source")))
SAMPLES = 20_000
SEED = 0


def write_grid() -> dict:
    with np.load(REACH, allow_pickle=False) as a:
        manifest = json.loads(str(a["manifest"].item()))
        pos = np.asarray(a["positions"], float)
        valid = a["ik_success"] & a["fk_checked"] & a["fk_success"] & a["consistent"] & (~a["collision_checked"] | ~a["collisions"])
    n_orient = valid.shape[1]
    score = valid.mean(axis=1)
    assert np.allclose(score * n_orient, np.round(score * n_orient)), "a reach fraction is k / orientations"
    step = manifest["metadata"]["scene_provenance"]["config"]["step_xyz"]
    assert len(set(step)) == 1, "one lattice step on every axis"
    cell_mm = round(step[0] * 1000.0, 6)
    rows = [{"x_mm": round(float(p[0]) * 1000, 3), "y_mm": round(float(p[1]) * 1000, 3), "z_mm": round(float(p[2]) * 1000, 3), "value": round(float(s), 4)}
            for p, s in zip(pos, score)]
    doc = {
        "title": "BAM Reach: the UR5e's reach map (the fraction of tool orientations reachable at each position)",
        "source": "BAM Reach workcell analysis reach-001 (bam_reach out/workcell_analysis/reach_maps, read-only); written by gallery/examples/robotics-arm/source/build_coverage.py",
        "cell_mm": cell_mm, "frame": manifest.get("position_frame") or "base",
        "kinematics": manifest.get("kinematics_name"), "orientations": int(n_orient),
        "schema": {"fields": [
            {"name": "x_mm", "type": "number", "unit": "mm", "description": "the tested position (a cell's centre), in the frame above"},
            {"name": "y_mm", "type": "number", "unit": "mm"},
            {"name": "z_mm", "type": "number", "unit": "mm"},
            {"name": "value", "type": "number", "title": "Reach", "decimals": 3,
             "description": f"the fraction of the {n_orient} tested tool orientations reachable there (IK found, FK checked and consistent, collision-free)"},
        ]},
    }
    one = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
    head = one({k: v for k, v in doc.items()})
    (CASE / "grid.json").write_text(head[:-1] + ',"rows":[\n' + ",\n".join(one(r) for r in rows) + "\n]}\n", encoding="utf-8")
    return {"cells": len(rows), "cell_mm": cell_mm, "frame": doc["frame"], "reachable": int((score > 0).sum())}


def tool_points() -> np.ndarray:
    """The suite's tcp over SAMPLES joint configurations, uniform in each joint's range, above the floor (metres)."""
    sys.path.insert(0, str(SUITE_DIR))
    import mujoco  # noqa: E402
    import arm_suite_sim as sim  # noqa: E402  its own model: Menagerie's UR5e with the suite's tool and tcp
    model = sim.build_model("twin")
    data = mujoco.MjData(model)
    rng = np.random.default_rng(SEED)
    lo, hi = model.jnt_range[:6, 0].copy(), model.jnt_range[:6, 1].copy()
    unlimited = ~model.jnt_limited[:6].astype(bool)
    lo[unlimited], hi[unlimited] = -np.pi, np.pi
    tcp = model.site("tcp").id
    out = np.empty((SAMPLES, 3))
    for k in range(SAMPLES):
        data.qpos[:6] = rng.uniform(lo, hi)
        mujoco.mj_kinematics(model, data)
        out[k] = data.site_xpos[tcp]
    return out[out[:, 2] >= 0.0]


def glb(path: pathlib.Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    """A minimal glTF 2.0 binary: one mesh, one node, no transform (metres, the glTF unit)."""
    v = vertices.astype("<f4")
    idx = faces.astype("<u4" if len(v) > 65535 else "<u2").ravel()
    vb, ib = v.tobytes(), idx.tobytes()
    pad = lambda b, c=b"\0": b + c * ((4 - len(b) % 4) % 4)  # noqa: E731
    vb, ib = pad(vb), pad(ib)
    gltf = {
        "asset": {"version": "2.0", "generator": "data-ui gallery/examples/robotics-arm/source/build_coverage.py"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "workspace"}],
        "meshes": [{"name": "workspace", "primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": int(len(v)), "type": "VEC3", "min": v.min(axis=0).tolist(), "max": v.max(axis=0).tolist()},
            {"bufferView": 1, "componentType": 5125 if idx.dtype == np.dtype("<u4") else 5123, "count": int(idx.size), "type": "SCALAR"},
        ],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(v.tobytes()), "target": 34962},
                        {"buffer": 0, "byteOffset": len(vb), "byteLength": len(idx.tobytes()), "target": 34963}],
        "buffers": [{"byteLength": len(vb) + len(ib)}],
    }
    js = pad(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), b" ")
    binc = vb + ib
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(binc), 0x004E4942) + binc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)


def write_workspace() -> dict:
    from scipy.spatial import ConvexHull  # noqa: E402
    pts = tool_points()
    hull = ConvexHull(pts)
    keep = np.unique(hull.simplices)
    remap = {int(old): new for new, old in enumerate(keep)}
    verts = pts[keep]
    faces = np.array([[remap[int(i)] for i in tri] for tri in hull.simplices])
    # outward winding: each face's normal points away from the hull's centre (three draws front faces)
    c = verts.mean(axis=0)
    for f in faces:
        a, b, d = verts[f[0]], verts[f[1]], verts[f[2]]
        if np.dot(np.cross(b - a, d - a), a - c) < 0:
            f[1], f[2] = f[2], f[1]
    # self-check: every sampled point is inside (or on) the hull
    eq = hull.equations
    assert (pts @ eq[:, :3].T + eq[:, 3] <= 1e-9).all(), "the hull holds every sampled tool point"
    glb(CASE / "media" / "workspace.glb", verts, faces)
    return {"samples": int(len(pts)), "hull vertices": int(len(verts)), "faces": int(len(faces)),
            "x mm": [round(float(verts[:, 0].min() * 1000), 1), round(float(verts[:, 0].max() * 1000), 1)],
            "y mm": [round(float(verts[:, 1].min() * 1000), 1), round(float(verts[:, 1].max() * 1000), 1)],
            "z mm": [round(float(verts[:, 2].min() * 1000), 1), round(float(verts[:, 2].max() * 1000), 1)]}


def main() -> int:
    print(json.dumps({"grid": write_grid(), "workspace": write_workspace()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
