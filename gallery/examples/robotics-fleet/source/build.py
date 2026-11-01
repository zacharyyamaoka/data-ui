"""The fleet case's data: one list of deployments on a map (Zach, 2026-10-30), one real rack among synthetic robots.

    python3 -I gallery/examples/robotics-fleet/source/build.py       (stdlib; seeded, so a rebuild writes the same bytes)

REAL (read-only, copied byte for byte from gallery/examples/robotics-deployments): the One Dof Test Rack, its name and
kind, and the newest run of each of the REAL_RUNS stations that ran last, as their own files under runs/. Nothing about
the rack is computed here except this case's run count and last run. Its `status` word and its `coordinates` are this
case's: the archive holds no live status, and the point is Vancouver's city centre, never the bench's address.

SYNTHETIC (made up here, seeded, labelled `basis: synthetic` on every row of deployments.json and runs.json, and
`situation: synthetic` on every sample): every other robot, site, status, run and sample. No customer is named: sites
are generic ("Hospital site A"), the cities are real, and the points are city centres. Each synthetic run is a minimum-
jerk move through random waypoints (the `target`) with a first-order lag and a little noise on top (the `synthetic`
trace): a stand-in shaped like a joint log so the page has something to play, not a model of any robot.

What it writes:
  - deployments.json: one row per robot, `runs` and `last_run` counted from runs.json;
  - runs.json: one row per run, the trajectory contract's columns (gallery/robotics/CONTRACT.md) as robotics-deployments
    writes them, plus `basis`;
  - runs/<run>.json: that run's samples (copied for the rack; DISPLAY_HZ for the rest, so the case stays small).
Self-checks before writing (the build stops when one fails): every run id is its own and path-safe, every run names a
deployment, every file holds only its run's rows, every copied file equals its source.
"""

from __future__ import annotations

import json
import math
import pathlib
import random
import re
import shutil

HERE = pathlib.Path(__file__).resolve().parents[1]
RACK = HERE.parent / "robotics-deployments"
SEED = 20261030
REAL_RUNS = 4        # the newest run of each of this many stations
DISPLAY_HZ = 10
PATH_SAFE = re.compile(r"^[A-Za-z0-9._~-]+$")

STATUS_SLOTS = {"running": 6, "idle": 1, "fault": 8, "offline": 0}   # --data-series-N: green, blue, red; 0 muted
BASIS_SLOTS = {"real": 7, "synthetic": 0}

# id, name, model, site, city, lat, lng (the city's centre), status. Two sites hold two robots: rows at one point
# count together on the map. WHY these cities: a BC fleet growing across Canada and into a few US cities, far enough
# apart that twelve robots read as twelve places at the zoom that fits them all.
SYNTHETIC = [
    ("sorter-a1", "Sorter A1", "Arm sorter Mk2", "Hospital site A", "Victoria", 48.4284, -123.3656, "running"),
    ("sorter-a2", "Sorter A2", "Arm sorter Mk2", "Hospital site A", "Victoria", 48.4284, -123.3656, "fault"),
    ("sorter-b1", "Sorter B1", "Arm sorter Mk3", "Hospital site B", "Kelowna", 49.8880, -119.4960, "running"),
    ("gantry-c1", "Gantry C1", "Gantry sorter Mk1", "Transfer station C", "Prince George", 53.9171, -122.7497, "idle"),
    ("sorter-d1", "Sorter D1", "Arm sorter Mk3", "Food court site D", "Calgary", 51.0447, -114.0719, "running"),
    ("sorter-e1", "Sorter E1", "Arm sorter Mk3", "Hospital site E", "Toronto", 43.6532, -79.3832, "running"),
    ("gantry-e2", "Gantry E2", "Gantry sorter Mk1", "Hospital site E", "Toronto", 43.6532, -79.3832, "idle"),
    ("sorter-f1", "Sorter F1", "Arm sorter Mk2", "Materials site F", "Montréal", 45.5019, -73.5674, "offline"),
    ("sorter-g1", "Sorter G1", "Arm sorter Mk3", "Food court site G", "Seattle", 47.6062, -122.3321, "running"),
    ("gantry-h1", "Gantry H1", "Gantry sorter Mk1", "Transfer station H", "San Francisco", 37.7749, -122.4194, "fault"),
    ("sorter-i1", "Sorter I1", "Arm sorter Mk2", "Hospital site I", "Chicago", 41.8781, -87.6298, "idle"),
]
RACK_ROW = {"site": "Test bench", "city": "Vancouver", "coordinates": [49.2827, -123.1207], "status": "idle"}

DEPLOYMENT_PROPERTIES = {
    "deployment": {"type": "text", "label": "Deployment", "hidden": True},
    "name": {"type": "text", "label": "Name"},
    "robot_model": {"type": "text", "label": "Robot model"},
    "site": {"type": "text", "label": "Site"},
    "city": {"type": "text", "label": "City"},
    "status": {"type": "text", "label": "Status", "display": "badge", "colors": STATUS_SLOTS},
    "last_run": {"type": "date", "label": "Last run"},
    "runs": {"type": "number", "label": "Runs"},
    "coordinates": {"type": "list", "label": "Coordinates", "hidden": True},
    "basis": {"type": "text", "label": "Data", "display": "badge", "colors": BASIS_SLOTS},
}
RUN_FIELDS = [
    {"name": "run", "type": "string", "title": "Run", "description": "the run's id: its file is runs/<run>.json"},
    {"name": "deployment", "type": "string", "title": "Deployment"},
    {"name": "label", "type": "string", "title": "Run"},
    {"name": "started", "type": "datetime", "title": "Started"},
    {"name": "device", "type": "string", "title": "Station"},
    {"name": "kind", "type": "string", "title": "Kind"},
    {"name": "duration_s", "type": "number", "unit": "s", "title": "Duration"},
    {"name": "basis", "type": "string", "title": "Data", "description": "real: the rack's own log; synthetic: made up for this case"},
]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data, *, indent=None):
    text = json.dumps(data, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"))
    path.write_text(text + "\n", encoding="utf-8")


def real_runs():
    """The newest run of each of the REAL_RUNS stations that ran last, newest first."""
    rows = sorted(load(RACK / "runs.json")["rows"], key=lambda r: r["started"], reverse=True)
    picked, seen = [], set()
    for row in rows:
        if row["device"] not in seen and len(picked) < REAL_RUNS:
            seen.add(row["device"])
            picked.append(row)
    return picked


def minimum_jerk(fraction):
    """Position and rate (per unit of the move's time) of a rest-to-rest minimum-jerk move."""
    return 10 * fraction**3 - 15 * fraction**4 + 6 * fraction**5, 30 * fraction**2 - 60 * fraction**3 + 30 * fraction**4


def synthetic_samples(run, device, duration, rng):
    """A move through random waypoints, then a lagged, slightly noisy trace of it: both on one DISPLAY_HZ grid."""
    step = 1 / DISPLAY_HZ
    count = round(duration * DISPLAY_HZ) + 1
    legs = rng.randint(2, 4)
    waypoints = [0.0] + [rng.uniform(-60, 60) for _ in range(legs)]
    leg_seconds = (count - 1) * step / legs
    lag_seconds = rng.uniform(0.08, 0.22)
    blend = 1 - math.exp(-step / lag_seconds)
    rows, followed, previous = [], waypoints[0], waypoints[0]
    for i in range(count):
        t = i * step
        leg = min(int(t / leg_seconds), legs - 1)
        position, rate = minimum_jerk(min((t - leg * leg_seconds) / leg_seconds, 1.0))
        span = waypoints[leg + 1] - waypoints[leg]
        target = waypoints[leg] + span * position
        target_rate = span * rate / leg_seconds
        followed += blend * (target - followed) + rng.gauss(0, 0.12)
        rate_seen = 0.0 if i == 0 else (followed - previous) / step
        previous = followed
        base = {"t": round(t, 3), "run": run, "device": device}
        rows.append({**base, "situation": "synthetic", "source": "sim", "q_deg": round(followed, 3), "qd_deg_s": round(rate_seen, 2)})
        rows.append({**base, "situation": "target", "source": "target", "q_deg": round(target, 3), "qd_deg_s": round(target_rate, 2)})
    return rows


def synthetic_runs(deployment, name, rng):
    """Two to four made-up runs of one robot, oldest first, each with its samples."""
    runs = []
    for number in range(rng.randint(2, 4)):
        day = rng.randint(20, 29)
        clock = f"{rng.randint(6, 21):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
        kind = rng.choice(["sort cycle", "pick and place", "homing"])
        step = f"s{number * 2 + 2:02d}"
        run = f"{deployment}~10-{day}~{step}"
        duration = round(rng.uniform(4, 7), 1)
        runs.append(({"run": run, "deployment": deployment, "label": f"{name} · {kind} · {step}",
                      "started": f"2026-10-{day}T{clock}-07:00", "device": "Joint 1", "kind": kind,
                      "duration_s": duration, "basis": "synthetic"},
                     synthetic_samples(run, "Joint 1", duration, rng)))
    return sorted(runs, key=lambda pair: pair[0]["started"])


def main():
    rng = random.Random(SEED)
    rack = load(RACK / "deployments.json")["rows"][0]
    (HERE / "runs").mkdir(exist_ok=True)
    for old in (HERE / "runs").glob("*.json"):
        old.unlink()

    run_rows, files = [], {}
    real = real_runs()
    for row in sorted(real, key=lambda r: r["started"]):
        run_rows.append({"run": row["run"], "deployment": rack["deployment"], "label": row["label"], "started": row["started"],
                         "device": row["device"], "kind": row["kind"], "duration_s": row["duration_s"], "basis": "real"})
        shutil.copyfile(RACK / "runs" / f"{row['run']}.json", HERE / "runs" / f"{row['run']}.json")

    rows = [{"id": rack["deployment"], "deployment": rack["deployment"], "name": rack["title"], "robot_model": rack["kind"],
             **{k: RACK_ROW[k] for k in ("site", "city", "status")}, "coordinates": RACK_ROW["coordinates"], "basis": "real"}]
    for deployment, name, model, site, city, lat, lng, status in SYNTHETIC:
        rows.append({"id": deployment, "deployment": deployment, "name": name, "robot_model": model, "site": site, "city": city,
                     "status": status, "coordinates": [lat, lng], "basis": "synthetic"})
        for row, samples in synthetic_runs(deployment, name, rng):
            run_rows.append(row)
            files[row["run"]] = samples
    for row in rows:
        mine = [r for r in run_rows if r["deployment"] == row["deployment"]]
        row["runs"] = len(mine)
        row["last_run"] = max(r["started"] for r in mine)[:10]   # the day: the runs table holds each run's instant

    # the build stops here rather than write a case that lies
    known = {row["deployment"] for row in rows}
    assert len({r["run"] for r in run_rows}) == len(run_rows), "a run id is used twice"
    for row in run_rows:
        assert PATH_SAFE.match(row["run"]), f"{row['run']} is not one URL path segment"
        assert row["deployment"] in known, f"{row['run']} names no deployment"
    for run, samples in files.items():
        assert {r["run"] for r in samples} == {run}, f"{run}'s file holds another run's rows"
    for row in real:
        same = (HERE / "runs" / f"{row['run']}.json").read_bytes() == (RACK / "runs" / f"{row['run']}.json").read_bytes()
        assert same, f"{row['run']} is not the rack's file"

    write(HERE / "deployments.json", {
        "id": "deployments", "title": "Deployments", "titleProperty": "name",
        "source": "One Dof Test Rack: gallery/examples/robotics-deployments (real). Every other row: synthetic, written by source/build.py",
        "properties": DEPLOYMENT_PROPERTIES, "rows": rows}, indent=1)
    write(HERE / "runs.json", {
        "name": "runs", "title": "Runs of the fleet", "primaryKey": "run", "titleProperty": "label",
        "source": f"The rack's runs: gallery/examples/robotics-deployments (real, newest of {REAL_RUNS} stations). Every other run: synthetic, written by source/build.py",
        "schema": {"fields": RUN_FIELDS}, "rows": run_rows}, indent=1)
    for run, samples in files.items():
        write(HERE / "runs" / f"{run}.json", {
            "name": run, "title": f"Samples of {run}",
            "source": "SYNTHETIC: a minimum-jerk move and a lagged, noisy trace of it, written by source/build.py; nothing measured",
            "rows": samples})
    total = sum(p.stat().st_size for p in (HERE / "runs").glob("*.json"))
    print(f"{len(rows)} deployments (1 real), {len(run_rows)} runs ({len(real)} real), runs/ {total:,} bytes")


if __name__ == "__main__":
    main()
