# Servo · rack runs vs twin

One servo and its encoder, run by run: 40 real runs of the 1-DOF rack's CAN 12 and CAN 14, each against its motor's
twin replayed on the same commands and against the commanded target. Pick a run on the rail (the newest opens first);
angle, its error against the target, velocity and torque follow it on one clock. Below them, coverage: every rack run of
the servo picked under *Coverage · servo* (Oct 23-25), as the time spent at each angle, each run kind's velocity range
and the angle × velocity phase space. The robotics playback template for a servo (PEP 0010 §6).

- **Use case:** Robotics · Playback
- **App:** BAM rig
- **Replaces:** sim2real's run inspector (`~/sim2real/dashboards/rack/4-run-inspector.base`) and traj_compare's
  per-run report for the rack (bam_ws `reports/media/rack-sensors-2026-10-21/report.html`), for browsing runs; the
  twin studies keep their figures.
- **Shows:** the trajectory contract's tables (`gallery/robotics/CONTRACT.md`) as one dashboard: a runs table that
  picks a run (a click moves the rail's Run pick; it lists every run the rest of the rail leaves, the picked one marked;
  `selected: first` picks the newest when the page opens: CONTRACT §33), the rail's Run picker (newest first), Servo and
  Run kind on the runs, Show on the samples (one-way: it never narrows the runs); one clock spanning the picked run; four
  time series, each situation in its family's hue (`style.families`: real slot 1, sim slot 2, target muted and
  dashed): angle, the angle error e_q = target − q (from `difference(a, b)`'s rows, never computed in the page),
  velocity and torque. The difference rows are linked on run, device and situation, so Servo and Show reach them.
  Coverage (PEP 0010 P2, the mock's bottom row) reads `coverage_samples.csv`, unlinked so a run pick never empties it,
  with its own servo pick (opening on the newest run's servo): the time at each angle (a histogram of Σ w, 1 Hz, so its
  bars are seconds), with the full-rate min and max as dotted rules; each run kind's velocity as a box whose whiskers
  are the full-rate min and max; the angle × velocity phase space as 2D bins of seconds.
- **Data:** **real** rack runs, Oct 24-25 2026, with a **twin replay** (simulation) beside each. Written by
  `source/build.py`, read-only from `/archive/datasets/bam_rig`.

## Data

`source/build.py` (run with the bam_rack_twin worktree's venv, `-B -I`; it imports sim2real's
`dashboards/source/rack_replays.py` and calls its twin rebuilds) replays 40 runs, then `source/write_tables.py` writes
the display projection:

- **CAN 12** (JMC 60ASM200, moteus r4.11, 10:1): the 13 runs round 7 replays with CAN 12's deployed twin
  (`capture-203db390`): `rack_2026-10-25` `dataset_rotor` (can12, its rest sessions) and the two cogging-phase gravity
  runs (30 s each).
- **CAN 14** (SteadyWin GIM4305-10, moteus c1, 10:1): 27 runs of `rack_2026-10-24` replayed with that day's envelope
  twin (`full-10d0d210`): `dataset/can14` (12), `floors/can14` (5 waypoint repeats) and sine sessions 09, 10 and 11.
  Session 30's 3 rad sines are left out: at 2.8 Hz the board hits its 1.5 N·m cap and the twin's replay leaves the
  real angle by 1.75 rad RMS, a twin outside its range rather than a picture of one.
- **The oracle:** 19 of the runs are held-out rows of their motor's dataset file (`dataset_twin_can12.json`,
  `dataset_twin_can14.json`); on each, the replayed q RMS (real − twin, on the rows both were in position mode)
  reproduces the file's `twin_q_rms_mrad.full` (rack_replays.py's 2 % rule; every one matched to 3 decimals).
  runs.json's `held_out` and `note` say which; the other 21 have no file value.
- `runs.json` (40): `run` is the day, folder and session under the rack's archive (`10-24/dataset/can14/s01`), with a
  readable label; `started` in the rig's local time; the native rate (≈ 95 Hz) and the display rate; the twin's
  version and its q RMS at the full logged rate; the npz path.
- `samples.json` (≈ 14,500 rows): per run three situations, `real` (the board's log, family real), `twin` (the replay,
  family sim) and `target` (the commanded q_target and qd_target, family target, no torque); `q_deg`, `qd_deg_s`,
  `tau_nm` in the joint's output frame. Rows picked at about 19 Hz (every 5th logged row, plus each run's last), the
  same rows in all three situations, never averaged.
- `devices.json` (2): the two servos, their parts (robotparts ids) and the rack as their parent.
- `diff_samples.json` (14,511 rows): `source/build_diff.py` (standard library only) runs `difference(a, b)`
  (`gallery/robotics/difference.py`, the one shared implementation, which reproduces the contract's fixture) on
  samples.json for the contract's pairs: real and twin against the target, the twin against real. b − a in mrad
  (`e_q_mrad`), deg/s and N·m, every number to 6 decimals; real, twin and target share each run's rows, so b(tᵢ) is
  b's own sample. tools/test_robotics_difference.py recomputes every row from samples.json.
- `coverage_samples.csv` (3,245 rows) and its `coverage_samples.schema.json`: `source/build_coverage.py` (numpy only)
  reads every CAN 12 and CAN 14 run of `rack_2026-10-23`, `-24` and `-25` (278 runs with ≥ 20 samples, read-only) and
  writes the trajectory contract's coverage_samples: rows picked on a 1 Hz grid (w = 1, so Σ w is seconds) plus each
  run's argmin and argmax row of q and qd (w = 0), so a histogram stays unbiased while min and max over rows are the
  full-rate ones; q and qd in the joint's output frame (each board's frame at the run's start, from bam_rack_twin's
  deployment record), in degrees. WHY 1 Hz: the case publishes at most 5 MB and its playback tables take 4.6 MB.
  `--deployment DIR` writes every rack run (1,000, eight servos) at the largest whole rate under 150,000 rows (18 Hz,
  144,644 rows) into DIR, never the case: the P2 checks draw this template's panels over it and time a rail click.
- **Editing:** this page opts into the dashboard editor (`site.json`: `editor`): press Edit, drag a panel, place what is waiting under To place, Save. `host.js` plays the host and keeps what is saved in this browser; `saved.base` is its queue (docs/CONTRACT.md §41).
- **Not here yet:** coverage of the twin (sim) beside real: only the 40 runs above have twin replays; the camera (P4).
