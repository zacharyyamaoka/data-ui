# PID tuning results

pidtuna's four-rung tuning ladder (factory → analytic → tuned → oracle) on nine simulated robots, as one dashboard:
how close the tuned gains get to the oracle per robot, gains against the error they buy, the error per rung, every
joint and motor, and the one real check (the sim plant against the rack's servos).

- **App:** BAM rig
- **Replaces:** pidtuna.com's per-robot result tables and the rack tuner's printed summaries
  (`bam_pid_tunning/docs/build_report.py`); the MuJoCo replays stay on pidtuna.com
  (`~/pidtuna-website/site`) and the design rationale in `~/bam_ws/reports/pid-tuner-design-rationale-2026-10-26.html`.
- **Shows:** three datasets, two linked (`gains.robot_id → robots.robot_id`) and one deliberately not (the rack's
  fidelity data, which the robots' rail leaves alone); KPI cards whose delta is against a property of the same row
  (`compare.against: oracle_tracking_rms`); a log-log gain-vs-error scatter whose click selects a robot; bars of the
  median error per rung whose click selects a rung; a per-joint table and a robot × rung pivot as tabs; a sim-vs-real
  scatter with a y = x guide.
- **Data:** `gains.json` (132 joint × rung rows), `robots.json` (9) from pidtuna-website's exported
  `site/public/data/*.json` at 1414ae6: **simulated, illustrative parameters** (commit 63c33ba), scores drawn as
  estimates; `fidelity.json` (10 rows) from bam_ws `bam_pid_tunning/docs/sim_fidelity.json` (branch
  `claude/pid-auto-tuner-stack-e956da`, d572a55f): **real** rack measurements. Written by `source/build.py`, read-only.
  No overshoot or settling time exists in either source.

## Dashboard (round 2)

The UR5e's ladder on top, one clock for everything time-aware (`clock: {data: samples}`, 0-7.9 s), round 1's nine
robots and the rack below, one colour per rung in every panel (`style.palette`):

- **Tiles:** the tuned rung's worst-joint stop p90 (▼ against the factory's), tracking RMS (▲ against the oracle's),
  × better than factory, and tracking RMS by rung (`kpis.json`, `headline.json`).
- **Playback**, then the rail's joint (`samples`, a single-select `joint` facet, elbow to start: the tuned rung's
  worst joint) as joint angle vs target and error over time (symlog; the rule is the tuned rung's worst-joint tracking
  RMS, since the export has no numeric gate), beside the MuJoCo replay of the tuned gains (primary: its frames drive
  the clock while it plays) and a factory-vs-tuned wipe.
- The tool path in 3D with the meshed UR5e (`robot.json`, `media/ur5e_links.glb`) and in XZ (`tool.json`), the lever's pick-and-place tape (`step.json`; 8.67
  s, so its last 0.77 s lies past the UR5e's clock), the gates per joint × rung and torque saturation per rung, and the
  UR5e's gains (`joints.json`).
- **Open in Rerun:** `uv run --script tools/rerun_export.py gallery/examples/pid-tuning/views.base` writes
  `rerun/pid-tuning.rrd` (gitignored; regenerate before building).

`headline.json` (4 rows) is written by `source/build_headline.py` (`python3 -I
gallery/examples/pid-tuning/source/build_headline.py`) from `kpis.json`: each rung's stop p90 and tracking RMS with the
factory's and the oracle's cells copied beside them, because a tile's delta compares against a property of its own
row. No number is recomputed; each cell's `source` names the kpis.json row it came from. Sim.

## Data (round 2)

Written by `source/build_replay.py` (`MUJOCO_GL=glfw xvfb-run -a ~/pidtuna/.venv/bin/python -I
gallery/examples/pid-tuning/source/build_replay.py`; `--no-media` for the JSON alone) from pidtuna-website's replay
export `site/public/data/{ur5e,lever}.json` (last changed at c02e786) and pidtuna's `src/pidtuna/models/ur5e_bare.xml`
(f93cf9c), read-only. **Everything here is simulation**: pidtuna's ArmSim / ServoSim against a hidden truth plant with
illustrative parameters. Nothing is a real robot and nothing is drawn "measured".

- `samples.json` (11,880 rows): UR5e, tape `coordinated`, target + the four rungs × 6 joints; `q_deg`,
  `q_target_deg`, `err_mrad` (q − q_target, null on target rows). Shown at 50 Hz (every second 100 Hz sample),
  display only. Sim.
- `step.json` (4,340 rows): the lever (1 joint), tape `pickplace`, same shape, the export's full 100 Hz. Sim.
- `tool.json` (1,980 rows): UR5e tool site position `px py pz` (m) and `err_mm` against the target's, plus a stick
  robot `s0…s7` (base, shoulder, upper arm, forearm, wrist 1-3 body origins, then the tool site; names in the file's
  `skeleton`), 50 Hz. MuJoCo forward kinematics of the replayed joint angles: sim, never a camera.
- `robot.json` (792 rows): each UR5e link's world pose per situation (target, factory, tuned, oracle) at 25 Hz:
  `<link>_x/_y/_z` (m) and `<link>_qw/_qx/_qy/_qz` (wxyz) for base … wrist_3_link, plus the tool site `px py pz`. MuJoCo
  forward kinematics of the same replay on `ur5e_bare.xml` (sim). With `media/ur5e_links.glb` (1.5 MB, 121,783
  triangles: one node per link) it draws the meshed arm in "Tool path 3D (sim FK)". Both written by
  `source/build_robot.py` (`~/pidtuna/.venv/bin/python -I gallery/examples/pid-tuning/source/build_robot.py`),
  which also writes the catalog's copy, `../dashboard-cards/robot.json` (target, factory, tuned).
  **The meshes are MuJoCo Menagerie's `universal_robots_ur5e` (BSD-3-Clause, Copyright 2018 ROS Industrial
  Consortium; google-deepmind/mujoco_menagerie@71f066a, its `universal_robots_ur5e/LICENSE`).**
- `kpis.json` (4): per rung the worst joint's stop p90, tracking RMS, peak error and saturation (named joint), the
  producer's numbers picked, never recomputed; `admissible` / `gates` from the export's `ladder` (the oracle study's
  own workload, not this replay); `vs_factory` = factory's worst tracking RMS ÷ this rung's. Basis `derived`, note
  "sim" (the brief's call; `gains.json` draws the same scores as `estimate`).
- `joints.json` (24): per rung × joint the replay's scores, kp, kd, feed-forward and the ladder's gate verdict.
- `media.json` (5) + `media/ur5e_{target,factory,analytic,tuned,oracle}.mp4|jpg`: MuJoCo 3.17.0 renders, one fixed
  camera, 640×400, 30 fps, 238 frames each, `t0` 0 (frame k = t k/30 s), basis `sim-render`. The model's collision
  capsules in grey, the tool site in blue; no target ghost.
- **Missing:** no real UR5e run exists (pidtuna is sim only); no overshoot or settling time in the export; the
  replay JSON's positions are stored to 1 µrad, so `err_mrad` resolves 0.001 mrad and no finer.

- Accuracy: the link poses are exact at robot.json's 25 Hz rows (MuJoCo forward kinematics of the replay, within 1e-6 m as stored); between rows the card lerps positions and slerps orientations, which is ≤ 1.34 mm (max 1.335 mm over 104,804 link samples; 95th percentile 0.42 mm) from true forward kinematics on this tape: worst wrist_3_link at t = 1.62 s, tuned (source/measure_robot_interp.py). A producer that needs better between rows bakes them denser.
