# Arm + gripper · stand-in

An arm with a gripper, on one run: the tool's height and the gripper's width and force on one clock, the contact, grasp
and release marked on each, the width at grasp over many grasps, and the tool path in 3D. Everything here is a
**stand-in**: the arm is sim2real's simulated UR5e and the gripper is **illustrative**, made from a stated rule until a
real gripper is logged. The robotics playback template for an arm with a gripper (PEP 0010 §6, the arm-gripper mock).

- **Use case:** Robotics · Playback
- **App:** BAM rig
- **Replaces:** nothing yet: no gripper page exists anywhere (sim2real's arm suite, `~/sim2real/dashboards/suite/`, has
  no gripper); this is the page a logged gripper fills by writing the same tables.
- **Shows:** one dashboard: the runs table (the one stand-in run, its basis and note); the rail's Show (situation) hides
  target, real or twin in every panel at once (poses and the gripper's samples are linked on run and situation); EEF z,
  gripper width and grip force as time series with events.json's contact, grasp and release as marks; the width at grasp of 300 illustrative grasps as a histogram summed
  by `w`; the arm's trajectory3d of the tool path.
- **Data:** **stand-in**: the arm is simulation (sim2real's MuJoCo UR5e, its "real" a synthetic plant, never measured);
  the gripper is **illustrative**, made by `source/build.py`; none of it is measured.

## Data

`source/build.py` (numpy only: `python3 -B -I gallery/examples/robotics-arm-gripper/source/build.py`) reads
`~/sim2real/dashboards/source/arm_suite_sim.json` (read-only), pidtuna's 7.9 s "coordinated" tape played by a MuJoCo UR5e:

- `poses.json` (597): the tool point (body `tcp`, frame `base`, mm) of the target (the tape's tool point), the synthetic
  real (`real_a`) and the twin, the 100 Hz rows picked at 25 Hz.
- `samples.json` (597): the **illustrative** gripper on the same times. The rule: contact at the target tool's lowest
  point in 1-2 s (the tape's first dip, 1.61 s: the pick), grasp 0.3 s later (1.91 s) once the fingers close on a 38 mm
  object, release at its lowest point in 4.5-5.5 s (4.97 s: the place), the fingers open over 0.4 s. The target is the
  command (width 85 → 38 → 85 mm, force 0 → 20 → 0 N); the twin a 30 ms lag on a rigid object; the real a 40 ms lag,
  0.8 mm of object compliance, 1.5 N of force ripple and seeded noise.
- `events.json` (3): contact, grasp and release at those times. The time series draw them as marks: the timeseries card
  takes marks from its own `annotations:`, so views.base carries one per row of events.json, and checks.py holds the two
  equal.
- `coverage_samples.json` (300): **illustrative** grasps, width ~ N(38, 4) mm and force ~ N(20, 1.5) N (seed 7), one row
  each (`w` = 1).
- `runs.json` (1), `devices.json` (2): the run, labelled stand-in; the tool and the gripper.
