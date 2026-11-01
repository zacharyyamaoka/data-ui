# Robot arm · UR5e tool path (stand-in)

A six-joint arm's tool path in 3D with a robot per situation and from the top, compare's arrows from each situation to
the target, the tool's and a joint's error, and the joint's angle, on one clock: the robotics playback template for an
arm (PEP 0010 §6). On a stand-in: no real arm run exists yet, so every number here is
MuJoCo simulation, sim2real's perturbed UR5e (a synthetic "real" plant run twice beside the nominal twin) and pidtuna's
tuning ladder on the same tape. Pick a run and a joint on the rail; Show hides a situation in every panel. Below,
coverage: every run's tool path at 1/n opacity per family over the arm's reachable volume, BAM Reach's reach map as an
image heatmap one slice at a time, and each joint's range over every run.

- **Use case:** Robotics · Playback
- **App:** BAM rig
- **Replaces:** sim2real's arm proposals (`~/sim2real/dashboards/arm/`) and traj_compare's 3D panel for an arm run
  (bam_ws's trajectory_generation `traj_compare/`: `report.py`, `assets/viewer3d.js`), for browsing; pidtuna.com keeps
  its MuJoCo replays.
- **Shows:** the trajectory contract's tables (`gallery/robotics/CONTRACT.md`) as one dashboard: `trajectory3d` twice
  (3D with the meshed UR5e posed from links.json, the trail at 0.6 s, real's Z axes, compare's arrows real → target
  and the Z-arcs between real's and the target's Z; and the top view, every time step, with arrows from every
  situation to the target), the EEF error |b − a| and the rail's joint's error e_q = target − q (from
  `difference(a, b)`'s rows, never computed in the page) and its angle, a runs table that picks a run (a click moves the rail's Run pick; the newest when the page opens:
  CONTRACT §33), the rail's Run (newest first), Show (situations) and Joint; links on run, situation, body and device, so a hidden situation leaves
  every panel, its arrows, its arcs and its robot. Coverage (PEP 0010 P2) reads unlinked copies, so a run pick never
  empties it: `trajectory3d` from the top with every run of every situation at `opacity: auto` (exactly 1/n over each
  family's paths) inside the workspace outline; `voxels` over BAM Reach's map, the slice through z ≈ 143 mm (◀ ▶ steps a
  cell; grey: the map has no family) in its own frame; a box per joint whose whiskers are its min and max.
- **Data:** **STAND-IN, simulation only.** Written by `source/build.py` from `~/sim2real/dashboards/source/arm_suite_sim.json`
  and this repo's `gallery/examples/pid-tuning` (robot.json, samples.json), read-only.

## Data

`source/build.py` (`MUJOCO_GL=egl ~/pidtuna/.venv/bin/python -B -I gallery/examples/robotics-arm/source/build.py`):

- **`ur5e-suite/coordinated`** (Oct 28, sim2real's `arm_suite_sim`): a MuJoCo UR5e with a tool, the twin (family sim)
  against a synthetic plant with four declared perturbations (tool payload +0.2 kg, elbow Coulomb friction 6 N·m, a
  +4 mrad wrist-1 encoder offset, a camera shift), run twice for its run-to-run floor: `real` and `real B` (family
  real: a stand-in, never measured; its tool point carries arm_suite_sim's sensor noise). The target is the tape. Its
  100 Hz rows picked at 25 Hz. The tool is the tcp, 12 cm out of the flange.
- **`ur5e-pidtuna/coordinated`** (Oct 26, pidtuna's replay at pidtuna-website c02e786): the same tape under three
  controller rungs, `factory`, `tuned` and `oracle` (family sim), and the `target`, at robot.json's 25 Hz. The tool is
  the flange (`tool0`, Menagerie's attachment_site).
- **Computed here:** the tool's orientation, wrist_3_link's pose composed with the tool's fixed mounting (pos 0 0.1 0,
  quat −1 1 0 0, the same in both sources); the suite target's link poses by arm_suite_sim.py's own MuJoCo forward
  kinematics of its joint angles. Checked: the composed pose puts the tool point where each source wrote it (3e-13 mm
  for the suite, 0.001 mm for pidtuna's 1 µm rounding).
- `runs.json` (2), `poses.json` (1,588: the tool in the base frame, mm, with its orientation), `samples.json` (9,528:
  q per joint, J1 shoulder pan … J6 wrist 3; τ for the suite), `links.json` (794: every link's world pose in mm for the
  meshed robot; for real and twin in the suite, tuned and target in pidtuna's run), `devices.json` (the six joints).
- **The meshes** are pid-tuning's `media/ur5e_links.glb` (MuJoCo Menagerie's `universal_robots_ur5e`, BSD-3-Clause).
- `diff_poses.json` (1,589) and `diff_samples.json` (9,534): `source/build_diff.py` (standard library only) runs
  `difference(a, b)` (`gallery/robotics/difference.py`, the one shared implementation, which reproduces the contract's
  fixture) on poses.json and samples.json for the contract's pairs: each situation against the target, the twin against
  real and real B. err_mm, err_rot_mrad, the reference pose and quaternion, e_q_mrad and e_tau_nm, every number to 6
  decimals; every situation shares its run's rows, so b(tᵢ) is b's own sample. tools/test_robotics_difference.py
  recomputes every row.
- `grid.json` (2,100 cells) and `media/workspace.glb` (4.5 KB): `source/build_coverage.py` (numpy, scipy and MuJoCo;
  the bam_rack_twin venv carries all three). The grid is BAM Reach's workcell reach map (`reach-001`, read-only) as the
  contract's grid: each tested position's centre in mm and its value, the fraction of the 56 tested tool orientations
  reachable there (IK found, FK checked and consistent, collision-free); `cell_mm` 150 and `frame` (BAM Reach's base,
  `ur_arm/base_link_ur`) at the top. The workspace is the arm's reachable volume in the poses' own frame: the convex
  hull of the suite's tcp over 20,000 joint configurations drawn uniformly in each joint's range (seed 0), above the
  floor, through arm_suite_sim.py's own model. WHY not BAM Reach's lattice for it: its frame is BAM Reach's, and a
  workspace drawn over the runs must be in theirs.
- **Not here yet:** a real arm run; more than two runs, so the coverage is thin (the panels are built for many).
