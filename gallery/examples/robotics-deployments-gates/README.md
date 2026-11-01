# Deployments · Playback + Gates

The deployments template with the mock's gates overlay: the rack's eight stations × its acceptance gates T1-T11 as bam_rack_twin last judged them, the rack as a tree whose plates and stations take the worst gate under them, every run's checks by RobotDx's diagnostics library (a cell opens its evidence; the link picks the run and plays it at the window), and the picked run's angle and speed against the station's own window and ceiling, with each check's verdict over the run. All real; the navigation and playback are the template's, unchanged.

- **Use case:** Robotics · Playback + Gates
- **App:** BAM rig
- **Replaces:** sim2real's app gates layer (`~/sim2real/app/deployment-gates.base`: the Stations × gates tracker without column labels, the gate verdict tables) and the deployment.png mock's gate matrix, as data-ui's stock gate views.
- **Shows:** the template's every panel, unchanged, plus the overlay (docs/CONTRACT.md §35): the mock's station gate matrix, a roll-up tree (`tree` + a Max-of-rank roll-up + `display: status`), a run gate matrix with the peek's evidence, two limits bands per station, a level history.
- **Data:** **real**: the rack's newest bam_rack_twin acceptance file that holds all eight stations (`acceptance_limiting.json`, Oct 29 2026), and RobotDx's checks of the template's 24 real runs from their own npz (`/archive/datasets/bam_rig`, read-only); the stations' windows are bam_rack_twin's TAPE_STATIONS.

## Data

`source/build.py` (the same command as the Servo twin's) writes:

- `gates.json` (88 rows): the station gate matrix, one row per station and gate T1-T11, as the acceptance file holds it (status, value, target text, detail).
- `components.json` (11 rows): the rack, its two plates and eight stations as a tree; `worst` is empty in the file and filled in the page by the dataset roll-up (the Max of the gates' RobotDx ranks under each node), drawn as the worst gate's word.
- `checks.json` (144 rows): per run, Tracking, Speed (against the station's ceiling), Angle (against its window; not run where the station has none), Board temp, Faults and Rate, each with its window and a link that picks the run here.
- `windows.json` (591 rows): the speed, angle and board temperature per 1 s window.
- `live_checks.json` (144 rows): the same checks per window for the three newest runs of three stations, keyed by run and check and stamped with the rig's wall-clock time: a RobotDx-style live feed. `tests/browser/p5_checks.py` pushes it into this page's Run checks view as a keyed live dataset (CONTRACT §26) and checks the matrix as of each moment.

The views read the template's files through `../robotics-deployments/`; this folder holds only the gate rows and their producer, so `diff ../robotics-deployments/views.base views.base` is the overlay.
