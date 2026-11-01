# Trajectory tracking

Target vs sim vs real on one clock: the five-bar pick-and-place's tool path against its target (sim) in 2D and 3D,
its error over time beside the study's own MuJoCo clip, the UR5e tool path (sim) and the rack's one real joint against
its twins; then round 1's error summaries per motor, speed and trajectory kind, the 10-09 study of target vs sim per
joint (its real slots were never run, and say so) and the traj_compare reports, linked. Real tool paths do not exist
yet (no real UR5e, the five-bar never ran hardware): both real slots are declared "not requested", never drawn.

- **App:** BAM rig
- **Replaces:** the summary tables of traj_compare's reports (`traj_compare.write_comparison_report`, in bam_ws
  `trajectory_generation/traj_compare`) and the per-run numbers inside `budget_can*.json`, for comparing across runs;
  traj_compare stays the renderer of each experiment's report (the trajectory-comparison skill: never a bespoke
  renderer); this page draws the display-grid samples its payload already carries, and its full-rate statistics are
  read from the report (`stats.json`), never recomputed from those samples.
- **Shows:** KPI tiles (the worst tool error per controller as a bar list, the best controller's TCP RMS, the
  controllers lost, every situation's status as a tracker), the playback bar, then on one clock (`#t=`): the five-bar
  path x against z with the report's 1 mm settle band as its tube, coloured by error with a trail, the same path in
  3D, its error over time, the study's MuJoCo clip (sim render), the UR5e path in 3D with its stick robot
  (`../pid-tuning/tool.json`), and the rack joint's error, real against both twins, on the 10-23 sine run
  (`../sim-to-real/samples.json`). The path (8.2 s), the UR5e tape (7.9 s) and the rack's sine (6.5 s) are different
  motions on one time axis. Below: round 1's three unlinked datasets (each with its own rail section, filtering only
  itself); KPI cards in summary mode (median per speed); grouped bars (`xOffset`) whose click selects a motor; error
  against the measurement floor on log-log axes with an `error = floor` guide; a target-vs-sim study faceted by
  speed, where the 24 real slots are "—" with "not requested", never 0; a table of the reports with their paths.
  "Open in Rerun" opens `rerun/trajectory-tracking.rrd` (`uv run --script tools/rerun_export.py
  gallery/examples/trajectory-tracking/views.base`, gitignored).
- **Data:** written by `source/build.py`, read-only: `rack.json` from `/archive/datasets/bam_rig/rack_2026-10-23/analysis/budget_can*.json`
  (**real** runs vs the identified and full twins); `cells.json` from `~/bam_ws/reports/media/rack-tracking-2026-10-09/{metrics,manifest}.json`
  (sim, a placeholder-gain run: the ff-only rows have zero peak torque, as in the source); `reports.json`, the six
  traj_compare reports found on disk.

## Data (round 2)

Written by `source/build_paths.py` (`python3 -I gallery/examples/trajectory-tracking/source/build_paths.py`: stdlib +
system ffmpeg), read-only from bam_ws `reports/media/five-bar-pnp-tracking-2026-10-12/` (report.html's traj_compare
payload, comparison `c1__nominal-five_bar`; `media/hero.mp4`, `video_spec.json`) and pidtuna-website's `ur5e.json`
(only its rung list). **Sim only**: the five-bar study never ran hardware.

- `path2d.json` (824 rows): the five-bar's tool (TCP) in world `x_mm y_mm z_mm` and the 3D `err_mm`
  (traj_compare's xyz_mag), target + the three controllers that held on, every 40 ms (the payload's display grid).
  The path is 3D (target travel x 224, y 112, z 200 mm), so all three axes are kept: draw `x_mm` against `z_mm` for
  a 2D card, or use a 3D card. traj_compare's own 2D axes are Conveyor = −y and Up = z.
- `situations.json` (14): every situation of the five-bar set and the UR5e set, with `kind` and `status` (ok, lost,
  not requested), so an empty real slot shows as declared, never dropped. The UR5e set's rows are
  `../pid-tuning/tool.json` (not copied).
- `media.json` (1) + `media/fivebar_hero.mp4|jpg`: the study's own MuJoCo hero clip, re-encoded (1280×720, 25 fps,
  9.2 s). `t0` 0 (its burned-in clock reads 0.00 s on frame 0 and 4.00 s on frame 100; its 40.7 mm tool error at 4 s
  matches `err_mm` 40.686). Side by side: right = soft4 + best model (a path2d situation), left = house8i + best model
  (a variant this comparison does not carry). Basis `sim-render`.
- `stats.json` (6), written by `source/build_stats.py` (`python3 -I …/source/build_stats.py`, stdlib): the same
  report's statistics table "Landings and effort (full-rate evidence)" as written, one row per controller (TCP RMS
  while moving, worst landing, held offset, pass-through lag, PD share, torques), keyed by the situation id; "lost"
  and "-" are null with the row's status, "inf" settle is null with `settle_note`. The best controller's TCP RMS
  tile reads it (12.7 mm, house8 + best model), not the 40 ms rows.
- **Missing:** three of the six controllers were lost (tool > 100 mm off) and have no rows; no real run.
