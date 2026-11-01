# Deployments → runs → one run

Robotics navigation on one dashboard: the deployments registry, the picked deployment's runs newest first, and the picked
run's playback, on the 1-DOF rack's real runs. The newest run opens by default; a click on another row loads that run's
file (`runs/<run>.json`, and only that one), a ctrl/cmd-click on a second shows "Pick one run", and Back and Forward step
through the picks with their playback time. The navigation template of PEP 0010 §8 (P3).

- **Use case:** Robotics · Navigation
- **App:** BAM rig
- **Replaces:** sim2real's app (`~/sim2real/app/`): deployments, one deployment and one run as three pages, the host
  writing `{deployment}` and `{run}` into each `.base` before data-ui reads it; and the run inspector's `#s.runs=…`
  written by its host so it starts on a run (sim2real gap #7). Here one `.base` holds all three levels.
- **Shows:** the per-run dataset (`samples: {data: 'runs/{run}.json'}`): read only when the dashboard's picks leave
  exactly one run, fetched once and kept while the reader flips between runs, and "Pick one run" in its panels when none
  or two are picked; one-way links (`direction: one-way`, sim2real gap #8): a deployment pick narrows its runs and a run
  pick names the file, while the samples' rail (Show: real, target) never narrows the runs; selection presets
  (`selected: first`, sim2real gap #7): the deployments table picks its first row and the runs table its newest run when
  the page opens, written into the URL as the selections they made; one history entry per pick, so Back and Forward
  restore the pick and the clock's t. Angle and velocity against the commanded target (dashed, muted), torque and
  q-axis current as logged, on one clock spanning the picked run.
- **Data:** **real**: the rack's own logs, Oct 28-29 2026, read-only from `/archive/datasets/bam_rig` by
  `source/build.py` (numpy). Nothing is simulated.

## Data

`source/build.py` reads every run under a `runs/` folder of `rack_2026-10-28` and `rack_2026-10-29` with at least 20
samples and at most 15 s, and keeps the newest three of each of the rack's eight stations (24 runs):

- `deployments.json` (1): the host's registry row (PEP 0010 §8, level 1): the One Dof Test Rack, its id and kind from
  bam_rack_twin's deployment record, its name, place and summary from sim2real's registry
  (`~/sim2real/app/registry.json`), and this case's run count and first and last run. One deployment is all the
  archive holds; a second is one more row and its runs.
- `runs.json` (24): the trajectory contract's runs table (gallery/robotics/CONTRACT.md): `run` is the day, folder and
  step under the archive joined by `~` (`10-29~gates~36_warm_can13_ff~s12`), which is also its file's name and one URL
  path segment as it stands; `started` on the rig's wall clock with its offset; the station (`device`), kind, length,
  the logged and drawn rates, and the archive file it came from.
- `runs/<run>.json` (24 files, about 45 KB each): that run's samples, rows picked on a 25 Hz grid (the first logged row
  at or after each grid time, plus the last; never averaged), in two situations on the same rows: `real` (the board's
  q, qd, torque and i_q) and `target` (the commanded q and qd). q and qd in the joint's output frame (board radians ×
  the board's `output_per_board` when the run started, from bam_rack_twin's deployment record), in degrees; t in s from
  the run's first logged row.
