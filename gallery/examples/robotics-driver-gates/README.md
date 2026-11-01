# BLDC driver · Playback + Gates

The BLDC driver template with its diagnostics and gates on top: 27 real rack runs, each checked by RobotDx's diagnostics library from the board's own log. A gate matrix of every run's board temperature, bus voltage, faults and sample rate (a cell opens its evidence beside the run's temperature in that window; the link plays the run there), the hottest sample of each second against warn 60 °C and error 70 °C, each check's verdict over the run, and every check as a status badge. The playback and coverage panels are the template's, unchanged.

- **Use case:** Robotics · Playback + Gates
- **App:** BAM rig
- **Replaces:** sim2real's per-run board checks (`~/sim2real/app/deployment-gates.base`'s run verdicts table: temperature box, fault codes, sample rate), drawn as data-ui's stock gate views.
- **Shows:** the template's every panel, unchanged, plus the overlay (docs/CONTRACT.md §35): a gate matrix, a limits band, a level history and status cells, and the peek's evidence.
- **Data:** **real**: RobotDx's checks of the template's 27 real rack runs (Oct 23-25 2026), from each run's own npz in `/archive/datasets/bam_rig` (read-only), with sim2real's board-temperature limits.

## Data

`source/build.py` (the same command as the Servo twin's; it imports `gallery/robotics/gates.py`) writes:

- `checks.json` (108 rows): per run, Board temp (`stock.box`, warn 60 / error 70 °C, sim2real's BOARD_TEMP), Bus voltage (`stock.box` on the logged voltage), Faults (`stock.fault_codes`, limiters and faults the board reported) and Rate (`stock.sample_rate`), each with its window and its link.
- `windows.json` (840 rows): board temperature and faults per 1 s window (0.5 s step), RobotDx's `stream.monitor`.

The views read the template's files through `../robotics-driver/`; this folder holds only the gate rows and their producer, so `diff ../robotics-driver/views.base views.base` is the overlay.
