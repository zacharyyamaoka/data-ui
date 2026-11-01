# Arm + gripper · Playback + Gates

The Arm + gripper template with its gates on top, on STAND-IN data as the template is (a simulated UR5e and an illustrative gripper): the grip force and the width at the grasp against stand-in tolerances, the tool's path error, the grip force in each half second against its limits, and every check as a status badge. The playback panels are the template's, unchanged.

- **Use case:** Robotics · Playback + Gates
- **App:** BAM rig
- **Replaces:** a gripper's grasp checks (force and width at the grasp against the commanded values), as data-ui's stock gate views.
- **Shows:** the template's every panel, unchanged, plus the overlay (docs/CONTRACT.md §35): a gate matrix, a limits band, a level history and status cells.
- **Data:** **stand-in**: the arm is sim2real's simulated UR5e and the gripper illustrative, as in the template; every gate row is `basis: stand-in`, with stand-in tolerances said in each row (force warn ±3 N, error ±5 N; width warn ±1.5 mm, error ±3 mm).

## Data

`source/build.py` reads the template's poses, samples and events and writes:

- `checks.json` (3 rows): Grip force and Grip width at the grasp, and the tool's Path error.
- `windows.json` (15 rows): the grip force per 0.5 s window (warn above 23 N, error above 25 N).

The views read the template's files through `../robotics-arm-gripper/`; this folder holds only the gate rows and their producer, so `diff ../robotics-arm-gripper/views.base views.base` is the overlay.
