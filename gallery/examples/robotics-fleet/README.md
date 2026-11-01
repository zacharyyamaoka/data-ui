# Fleet map: every deployment, one robot at a time

Every deployment in one list you can navigate, and the global view of that list a tab away: a map, a table and cards of
the same rows on one panel. Click a robot on the map and its runs list below, and its newest run plays. **Synthetic
data around one real rack:** only the One Dof Test Rack is real; every other robot, site and run is made up and labelled so.

- **Use case:** Robotics · Navigation
- **App:** BAM rig
- **Replaces:** the all-deployments table on sim2real's first page (`~/sim2real/app/deployments.base`), which has no map:
  here that list is one tab and the map another.
- **Shows:** a dashboard panel with tabs on one dataset (`views: [Map, Table, Cards]`), each view with `select:
  deployment`, so a marker, a row and a card are one pick, marked in all three (docs/CONTRACT.md §39), in the URL, one
  history entry per pick. A counted marker (two robots at one site) asks which robot rather than taking both. The legend
  beside the map says what the colours mean and how many robots hold each status, and it notes that a counted marker
  shows its most common status (so a fault beside a running robot draws green); a click on a status picks its robots. Below it,
  deployments → runs → one run as in `robotics-deployments`: `selected: first` picks the newest run of each robot you
  click, the per-run dataset (`runs/{run}.json`) reads only that run's file, and Back and Forward step through the picks.
- **Data:** **real**: the One Dof Test Rack and 4 of its 24 runs, copied byte for byte from `robotics-deployments`
  (the rack's own logs, Oct 28-29 2026). **Synthetic**: the other 11 robots, their sites, statuses, runs and samples,
  written by `source/build.py` with a fixed seed. No customer is named: sites are generic ("Hospital site A"), the
  cities are real, each point is a city centre.

## Data

`source/build.py` (stdlib; a rebuild writes the same bytes) reads `../robotics-deployments` and writes:

- `deployments.json` (12): one row per robot. `basis` says `real` or `synthetic` on every row. `runs` and `last_run`
  are counted from `runs.json`. The rack's `status` and `coordinates` are this case's, not measured: the archive holds no
  live status, and its point is Vancouver's city centre, never the bench's address.
- `runs.json`: one row per run, the columns `robotics-deployments` uses plus `basis`.
- `runs/<run>.json`: the rack's four files as they are (its `real` and `target` situations), and one small file per
  synthetic run at 10 Hz, two situations on the same rows: `target`, a minimum-jerk move through random waypoints, and
  `synthetic`, that move with a first-order lag and a little noise. The plots say `synthetic`, so a made-up trace never
  reads as a log. It is a stand-in shaped like a joint log, not a model of any robot.
