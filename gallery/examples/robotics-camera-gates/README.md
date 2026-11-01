# Camera · Playback + Gates

The Camera template with its diagnostics and gates on top: each RealSense camera's frame rate and dropped frames per session as cameras × sessions, checked by RobotDx's sample-rate diagnostic from the camera's own frame stamps, the largest frame interval in each second against warn 50 ms and error 100 ms, each camera's verdict over the session, and every check as a status badge. The playback panels are the template's, unchanged.

- **Use case:** Robotics · Playback + Gates
- **App:** BAM rig
- **Replaces:** the frame-rate checks RealSense captures get by hand (counting dropped frames in a notebook), as data-ui's stock gate views over RobotDx's sample-rate diagnostic.
- **Shows:** the template's every panel, unchanged, plus the overlay (docs/CONTRACT.md §35): two gate matrices (cameras × sessions), a limits band, a level history and status cells, and the peek's evidence.
- **Data:** **real**: RobotDx's `stock.sample_rate` over the two RealSense cameras' own `hw_ms` frame stamps of Oct 23 2026 (`/archive/datasets/bam_rig`, read-only). The 50 ms and 100 ms window thresholds are this twin's choice (1.5 and 3 frame periods at 30 fps), said in every row.

## Data

`source/build.py` (the same command as the Servo twin's) reads each session's `cameras/cam_<serial>.npz` and writes:

- `checks.json` (12 rows): per session and camera, Rate (achieved fps against 30, RobotDx's ±10 %) and Dropped (intervals over 1.5 frame periods), with the session's window and a link into this page at it.
- `windows.json` (441 rows): the largest frame interval per 1 s window, warn 50 ms, error 100 ms.

The views read the template's files through `../robotics-camera/`; this folder holds only the gate rows and their producer, so `diff ../robotics-camera/views.base views.base` is the overlay.
