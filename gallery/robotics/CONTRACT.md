# The trajectory contract: what a robotics producer writes for data-ui

**Version 1, 2026-10-29** (PEP 0010 P1a; docs/CONTRACT.md §32 refers to it). Changing this file is a barrier, as
changing docs/CONTRACT.md is: the change lands alone, first, with its tests, and the templates and producers follow.

A producer (sim2real's rack_replays.py and arm_suite_sim.py, RobotDx's feed, traj_compare, a future `lk_msgs`) writes
these tables; the robotics templates (PEP 0010 §6, gallery cases from P1c) read them; data-ui's views never know what a
joint or a gate is. Zach, 2026-10-28: "we are expecting trajectories in a certain format and then we can easily like
display them … Data UI doesn't need to know the robotic semantic meaning behind these things."

- **The dataset is a display projection.** SI stays in the producer's own bundle or npz. The files here carry display
  units, declared per column, because data-ui converts nothing: rails, URL filters, hovers and axes read the stored
  number. Every column name ends in its unit (§3; the exceptions are listed there).
- **Rows and column names, never a dataclass.** A `Trajectory` type (traj_compare's `Situation`, RobotDx's samples, a
  future `lk_msgs`) reaches data-ui through its own `to_rows()` that emits these columns, so no view changes when the
  types move. Pin that function with a test against the fixture (§5).
- **Missing is null, never 0.** A sample a sensor dropped, a channel a device does not have, a quaternion a producer did
  not compute: null, which every view draws as a gap.

## 1. Words

| Word | Means |
|---|---|
| **deployment** | one installed machine (the 1-DOF rack, the UR5e cell): a host-level registry row |
| **run** | one execution, with a stable unique id (for the rack, the npz path under the day folder) |
| **situation** | one way of playing the run, one series on screen: `real`, `real B`, `twin v7`, `model 2`, `target` |
| **source** | the situation's family: `real`, `sim` or `target`. Every model, twin, replay or prediction is `sim`. It picks the hue (docs/CONTRACT.md §32, `style.families`) |
| **device** | the part whose channels a row holds: `CAN 12`, `J3 elbow`, `gripper` |
| **body** | the rigid body a pose row tracks: `tool0`, `lever_tip` |
| **frame** | the frame a pose row's coordinates are written in: `base`, `belt` |
| **difference trajectory** | `difference(a, b)`'s rows: a's samples, each paired with b at the same time (§5) |
| **display rate** | the rate a producer writes for display, by picking rows, never by averaging |

## 2. Files

A table is JSON written as `{"schema": {"fields": […]}, "rows": […]}` (the schema inline), or CSV with a
`<name>.schema.json` sidecar beside it (docs/CONTRACT.md §3). Each `schemas/<name>.schema.json` here is that sidecar:
copy it, keep the units, drop the optional fields you do not write. Its `required` lists the columns every row has;
`rowsPer` names what one row is.

| File | One row per | Required | Optional | Schema |
|---|---|---|---|---|
| `runs.json` | run | `run`, `deployment`, `started` (ISO datetime with offset), `duration_s`, `kind`, `devices` (list), `situations` (list), `rate_hz`, `display_hz` | `label`, `basis`, `url` (the run page), `note` | [runs](schemas/runs.schema.json) |
| `samples.json` | t × run × situation × device | `t`, `run`, `situation`, `source`, `device` | the device type's channels (§3); any extra channel with a unit suffix | [samples](schemas/samples.schema.json) |
| `poses.json` | t × run × situation × body | `t`, `run`, `situation`, `source`, `body`, `frame`, `x_mm`, `y_mm`, `z_mm` | `quat_w`, `quat_x`, `quat_y`, `quat_z` (unitless, wxyz): needed for frames and Z-arcs | [poses](schemas/poses.schema.json) |
| `diff_poses.json` | t × run × situation × reference × body | `t`, `run`, `situation` (a), `source` (a's), `reference` (b), `body`, `frame`, `x_mm`/`y_mm`/`z_mm` (a), `ref_x_mm`/`ref_y_mm`/`ref_z_mm` (b at t), `err_mm` | `quat_*` (a), `ref_quat_*` (b at t), `err_rot_mrad` | [diff_poses](schemas/diff_poses.schema.json) |
| `diff_samples.json` | t × run × situation × reference × device | `t`, `run`, `situation`, `source`, `reference`, `device`, and `e_q_mrad` (revolute) or `e_q_mm` (prismatic) | `e_qd_deg_s` / `e_qd_mm_s`, `e_tau_nm` | [diff_samples](schemas/diff_samples.schema.json) |
| `links.json` | t × run × situation | `t`, `run`, `situation`, `source`, and per link `<link>_x/_y/_z` (the scene's unit) and `<link>_qw/_qx/_qy/_qz` | scene3d.robot's columns as built: the producer runs forward kinematics, the card only poses | [links](schemas/links.schema.json) |
| `media.json` | clip | PEP 0005 §3's clip (`src`, `poster`, `t0`, `fps`, `duration`, `basis`), `run`, `camera`, `kind` (`rgb`, `depth`, `band`) | `band_nm` | [media](schemas/media.schema.json) |
| `devices.json` | device | `device`, `type` (`servo`, `driver`, `camera`, `gripper`, `arm`, `eef`), `label`, `parent`, `order` | limits as columns (`q_min_deg`, `q_max_deg`, `qd_max_deg_s`, `tau_max_nm`, `i_max_a`; `_mm` for a prismatic axis), `part` (robotparts id) | [devices](schemas/devices.schema.json) |
| `events.json` | event | `t`, `run`, `device`, `kind` (`grasp`, `release`, `contact`, `fault`, `mode`), `label` | | [events](schemas/events.schema.json) |
| `coverage_samples.json`, `coverage_poses.json` | the deployment's runs, decimated | as samples / poses, plus `w` (§4) | at most 150,000 rows each | [samples](schemas/coverage_samples.schema.json), [poses](schemas/coverage_poses.schema.json) |
| `grid.json` | voxel cell | `x_mm`, `y_mm`, `z_mm` (cell centres), `value`; `cell_mm` and `frame` at the sidecar's top level | BAM Reach's reach map as rows | [grid](schemas/grid.schema.json) |
| `workspace.glb` | mesh | glTF, in metres per its spec, in the poses' frame | or a box in the `.base` | |
| `frames.json` (P3 and later) | frame | `frame`, `parent`, `x_mm`, `y_mm`, `z_mm`, `quat_*` | lets the viewer switch its display frame (Foxglove's "Display frame") | [frames](schemas/frames.schema.json) |

`source` is in the difference tables too (a's family): a view colours a row by its own columns and never joins
(docs/CONTRACT.md §10), so the arrows of a sim situation find their hue in their own row.

## 3. Channels and units

[schemas/channels.json](schemas/channels.json) is the machine version of both tables.

| Device type | Channels in samples.json |
|---|---|
| servo | `q_deg`, `qd_deg_s`, `qdd_deg_s2`, `tau_nm`; a prismatic axis writes `q_mm`, `qd_mm_s`, `qdd_mm_s2` |
| driver | `i_q_a`, `i_d_a`, `v_bus_v`, `temp_c`, `power_w`, `mode`, `fault` (text) |
| gripper | `width_mm`, `force_n`, `grip` (text: open, closing, holding) |
| camera | clips in `media.json`; frame stamps as `frame_dt_ms` rows in samples (the device is the camera) |
| eef / body | rows in `poses.json` |

The rack's npz holds `t, q, q_target, qd, qd_target, tau, i_q, i_d, voltage, temp_c, power_w, mode, fault`; `qdd` is not
logged, so the producer derives it at full rate and marks it `basis: derived`.

**A name ends in its unit**, the longest suffix that matches: `_s` s, `_ms` ms, `_hz` Hz, `_m` m, `_mm` mm, `_deg` deg,
`_rad` rad, `_mrad` mrad, `_deg_s` deg/s, `_deg_s2` deg/s², `_mm_s` mm/s, `_mm_s2` mm/s², `_rad_s` rad/s, `_nm` N·m,
`_n` N, `_a` A, `_v` V, `_w` W, `_c` °C. The sidecar declares the same unit. The names that end in a suffix without
meaning it: `quat_w` and `ref_quat_w` (a quaternion's w, unitless), `band_nm` (a wavelength in nanometres). The names
with no suffix carry their unit in the sidecar only: `t` (s), the link pose columns `<link>_x` (the scene's unit, as
scene3d.robot reads them) and PEP 0005's clip columns (`t0`, `fps`, `duration`).

## 4. Rules

- **Time.** `t` is seconds from the run's start (the target's start). `runs.started` gives the absolute order.
- **The target is a situation** (`source: target`), never a column: one more series, dashed, muted, and the robot's ghost.
- **Frames are declared, never guessed.** A pose row's coordinates are in its `frame`, so the view cube aligns with that
  frame by construction. For conveyor picking the producer writes the `belt` frame (x along the belt, y across, z up)
  and the top view reads cross-belt error directly. One body is written in one frame; rows in two frames are never
  mixed (the viewer names both and draws neither).
- **The scene's length unit.** `unit: mm` in a 3D view scales glTF meshes (metres, by spec) by 1000. Link poses are
  written in the scene's unit.
- **Display decimation.** At most 100 Hz per run (rack_replays.py's rule), by picking rows. Coverage files pick rows on a
  uniform time grid (`display_hz`), so a count is time spent (`count / display_hz` s), with `w = 1`; each run's argmin
  and argmax row of every channel is kept too, with `w = 0`. Histograms sum `w` and stay unbiased; min and max over rows
  stay exact (Zach asked for "the maximum and minimum position and velocity", which a thinned series misses; M4, Jugel
  et al., VLDB 2014, weighted).
- **The budget.** A coverage file stays at or under 150,000 rows (Vega-Lite 6.5 bins, box plots and 2D bins of that many
  rows take 83-105 ms in Node, measured on rack q/qd rows; 720,000 rows take 319-460 ms). Past that, Arrow IPC (PEP 0010 §12).

## 5. difference(a, b)

The one comparison. Computed once, in Python, in the trajectory library (traj_compare's `tp`/`tquat` today); data-ui
never interpolates one trajectory against another. WHY one definition: derived channels are computed once and no viewer
recomputes them (the tracking-run contract), so the arrows, the error plots and the gates cannot drift apart.

- **Inputs.** a and b are rows of one table, poses or samples, of two situations of the same run. b's rows are paired
  with a's by `(run, body, frame)` for poses and `(run, device)` for samples; an a row whose key b does not have gives no
  row (a body b writes in another frame gives none: frames are never mixed). Within a key, b's `t` rises strictly.
- **Times.** One row for each sample of a whose `t` lies in b's span, `[first t, last t]` of b's rows for that key,
  both ends included. Outside it, no row: difference never extrapolates. The rows stay on a's own sample times, never a
  shared resampled clock.
- **b at t.** At one of b's own sample times, b's values exactly. Between two of b's samples at fraction
  `f = (t − tᵢ) / (tᵢ₊₁ − tᵢ)`: positions and every numeric channel linearly, `vᵢ + f · (vᵢ₊₁ − vᵢ)`; orientations by
  slerp of the normalized quaternions the short way (when `⟨qᵢ, qᵢ₊₁⟩ < 0`, `qᵢ₊₁` is negated first). A null on either
  side of t is null at t, never a number made from 0.
- **diff_poses rows.** a's columns as written (`t`, `run`, `situation`, `source`, `body`, `frame`, `x_mm`…, `quat_*`
  unnormalized), `reference` = b's situation, `ref_<column>` = b at t, and:
  - `err_mm = |b(t) − a(t)|`, the Euclidean distance: the arrow runs from a(t) to b(t), to where the point should have
    been, and this is its length;
  - `ref_quat_*` written with `w ≥ 0` (when `w = 0`, the first non-zero of x, y, z positive: scipy's canonical form), so
    every conforming library writes the same four numbers;
  - `err_rot_mrad = 1000 · 2 · atan2(‖v‖, |w|)` of `(w, v) = conj(â) ⊗ b̂`: the angle of the rotation from a to b. It
    equals `2 · acos(|⟨â, b̂⟩|)`, written this way because acos loses half its digits near 0. Null when a has no
    quaternion.
- **diff_samples rows.** `t`, `run`, `situation`, `source`, `reference`, `device`, and b − a at t: `e_q_mrad` (from
  `q_deg`, converted to mrad, `· π / 180 · 1000`; a revolute axis), `e_q_mm` (a prismatic axis), `e_qd_deg_s` or
  `e_qd_mm_s`, `e_tau_nm`; null when either side is null. A library may add `e_<channel>` for another numeric channel,
  b − a in its unit. WHY b − a: the error plot reads "e_q = target − x", where the point should have gone.
- **Order.** a's row order.
- **The pairs a producer writes:** each situation against `target`, and each `sim` situation against `real`. The
  viewer's Compare menu lists the pairs present.

**The fixture.** [fixtures/difference/](fixtures/difference/README.md) holds two trajectories of one run (a = `real`,
b = `target`) as a producer writes them, and the rows difference(a, b) returns, computed with numpy and scipy's
Rotation/Slerp. Every case above sits in it where it can be seen. A library conforms when

```python
import sys; sys.path.insert(0, "<data-ui checkout>/gallery/robotics")
import fixture
assert fixture.check_difference(poses=difference, samples=difference) == []
```

(numbers within 1e-9 in the column's unit, `err_rot_mrad` within 1e-4 mrad, text equal, null as null;
[fixture.py](fixture.py), stdlib only). data-ui's own tools/test_robotics_fixture.py reproduces every row with an
independent implementation, and nine plausible wrong ones (nlerp, the long way, extrapolating, pairing across frames,
acos without |…|, a non-canonical sign, null as 0, a − b, degrees) each fail it.

## 6. Validation

- `node bin/data-ui.mjs check <template>.base --data <file>` names every column a view reads that the data lacks: each
  3D layer's against the dataset it reads, the trajectory3d binding's (given, or this contract's name it defaults to),
  compare's difference columns (docs/CONTRACT.md §32).
- Each template's `checks.py` checks the sidecar's units against §3 (schemas/channels.json).
- tests/unit/robotics-contract.test.mjs: each schema here loads in data-ui with its units, and every name ends in the
  unit it declares.

## 7. What data-ui does not do

No forward kinematics, metric, gate, diagnostic or trajectory difference is computed in data-ui; no dataclass is
imported; no unit is converted; no dataset is pivoted (RobotDx adapts its `key/value` feed to §3's device rows).
