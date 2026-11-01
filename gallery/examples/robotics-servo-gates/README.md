# Servo · Playback + Gates

The Servo template with its diagnostics and gates on top: 40 real runs of the rack's CAN 12 and CAN 14, each checked by RobotDx's diagnostics library from its own log. A gate matrix of every run's checks (a cell opens its evidence beside the run's angle in that window; the link plays the run there), the twin's error per run against 1.5 × the station's floor as a KPI trend, the speed in each second against the station's own ceiling, each check's verdict over the run, and every check as a status badge. The playback and coverage panels are the template's, unchanged.

- **Use case:** Robotics · Playback + Gates
- **App:** BAM rig
- **Replaces:** sim2real's gates layer for the rack (`~/sim2real/app/deployment-gates.base`'s run verdicts and station diagnostics tables, and `run-gates.base`), drawn as data-ui's stock gate views instead of tables of verdict words.
- **Shows:** the template's every panel, unchanged, plus the overlay (docs/CONTRACT.md §35): a gate matrix (`tracker.column`), a KPI trend with each row's own target, a limits band (`limits`) per station, a level history and status cells, and the side peek's evidence (a section view bound to the clicked row, the evidence link).
- **Data:** **real**: RobotDx's checks of the template's 40 real rack runs (Oct 24-25 2026), from each run's own npz in `/archive/datasets/bam_rig` (read-only); the twin error is the template's own replay number; the stations' floors and limits are bam_rack_twin's.

## Data

`source/build.py` (run with `env -u VIRTUAL_ENV uv run --isolated --with "~/io-diagnostics[diagnostics]" python source/build.py`; it imports `gallery/robotics/gates.py`) reads the template's runs and each run's npz and writes:

- `checks.json` (200 rows): per run, PEP 0010 §10's diagnostic row for Tracking (`stock.tracking_error`, real against the target; a reading, no limit), Twin error (the template's `q_rms_mrad`, judged against 1.5 × the station's T1 floor from bam_rack_twin's newest acceptance file; the target column is that number), Board temp (`stock.box` temp_c, warn 60 °C, error 70 °C), Faults (`stock.fault_codes`) and Rate (`stock.sample_rate`), each with its evidence window and a link into this page at it.
- `windows.json` (657 rows): RobotDx's `stream.monitor` per 1 s window (0.5 s step) of the largest |qd| against the station's speed ceiling and, for CAN 12, the angle against its window (bam_rack_twin's TAPE_STATIONS).
- The matrix, the KPI trend, the limits band and the levels read these rows; data-ui computes no verdict, value or limit.

The views read the template's files through `../robotics-servo/`; this folder holds only the gate rows and their producer, so `diff ../robotics-servo/views.base views.base` is the overlay.
