# BLDC driver · rack boards

One moteus board's driver channels, run by run: 27 real runs of the 1-DOF rack's CAN 12, 13 and 14 (Oct 23-25 2026),
with coverage over all 532 runs of those three boards. Pick a run on the rail (the newest opens first); q- and d-axis
current, bus voltage, board temperature and the mode and fault registers follow it on one clock, and the coverage
panels show every run of its board. The robotics playback template for a driver (PEP 0010 §6, the bldc-driver mock).

- **Use case:** Robotics · Playback
- **App:** BAM rig
- **Replaces:** the "Current (real only)" and "Winding temperature (real only)" panels of sim2real's rack run inspector
  (`~/sim2real/dashboards/rack/4-run-inspector.base`), as one page per board with every driver channel, its mode and
  fault registers and its coverage.
- **Shows:** the trajectory contract's tables (`gallery/robotics/CONTRACT.md`) as one dashboard: a runs table that picks a
  run, with its fault-register note (a click moves the rail's Run pick; it lists every run the rest of the rail leaves;
  `selected: first` picks the newest when the page opens: CONTRACT §33); the rail's Run picker (newest first), Driver and
  Run kind; one-way links from the runs to the samples, events and coverage; one clock spanning the picked run; four time series (i_q,
  i_d, v_bus, temperature); the mode and fault registers as state strips (one span per state, from the row it began);
  the board's coverage: an i_q histogram and an i_q × qd operating map summed by `w`, and the temperature per run kind
  as a box (min-max whiskers, q1-q3 box, median).
- **Data:** **real**: the boards' own logs, Oct 23-25 2026, read-only from `/archive/datasets/bam_rig` by
  `source/build.py`. Nothing is simulated: the twin replays torque, not current, so every series is the real one.

## Data

`source/build.py` (numpy only: `python3 -B -I gallery/examples/robotics-driver/source/build.py`) reads every run npz
under a `runs/` folder of `rack_2026-10-23`, `-24` and `-25` whose sidecar names CAN 12, 13 or 14 and that has at least
20 samples (PEP 0010's rule): 221, 254 and 57 runs. Then:

- `runs.json` (27): per board up to 9 playback runs of at most 25 s: every run whose fault register was ever non-zero
  (limiters 98, 99 and 102 on these boards), then the newest run of each kind, then the newest others. `run` is the
  day, folder and session under the archive (`10-24/session_11/s07`), `npz` the run's file, `device` its one board.
- `samples.json` (≈ 7,400 rows): those runs' `i_q_a`, `i_d_a`, `v_bus_v`, `temp_c`, `power_w` as logged, `mode` and
  `fault` as moteus names them (`position`; `limiter 102 · commanded max torque`; a fault register of 0 is null). Every
  third logged row (≈ 31 Hz of ≈ 94 Hz), the last row, and every row where mode or fault changes, so a limiter held for
  two rows (22 ms) still draws from its first row. Rows are picked, never averaged.
- `events.json` (177): each playback run's mode and fault-register changes at the log's full rate, `kind` mode or
  fault, `label` the state entered (`none` when the fault register returns to 0).
- `coverage_samples.csv` + `.schema.json` (≈ 18,500 rows): all 532 runs on a uniform 4 Hz time grid (`w` = 1: a count is
  time spent, count ÷ 4 s) plus each run's argmin and argmax row of i_q, qd, temperature and voltage (`w` = 0), so a
  histogram sums `w` without bias and min and max over rows are the full-rate extremes. `kind` rides in each row, so the
  box per kind reads its own rows.
- `devices.json` (3): the boards, with `i_max_a` (`servo.max_current_A`) from the 10-23 electrical survey.

Board temperature, not winding: moteus's temperature register is the board's FET temperature (sim2real's diagnostics
catalog files it as `driver.board_temp`); the mock's "Winding temperature" title is corrected here.
