# Camera · rack RealSense

A camera's frames, session by session: the 1-DOF rack's two RealSense cameras over six recording sessions of Oct 23
2026, every frame stamp of both, and the RGB footage of CAN 14's plate for its three sessions. Pick a session (the newest
opens first) and the clip plays on the clock; pick a camera and the frame-interval histogram and the dropped frames per
session show all six of its sessions. Depth and hyperspectral cards are wired and empty: nothing has been captured yet.
The robotics playback template for a camera (PEP 0010 §6, the camera mock).

- **Use case:** Robotics · Playback
- **App:** BAM rig
- **Replaces:** the "Camera (only the staircase has one)" card of sim2real's rack run inspector
  (`~/sim2real/dashboards/rack/4-run-inspector.base`) and the sim-to-real case's clip cards, as one page per camera that
  also shows how well it kept its frame rate.
- **Shows:** one dashboard: a sessions table (every session, newest first) that picks a session (a click moves the rail's
  Session pick; the newest when the page opens: CONTRACT §33); the rail's Session picker and Camera; the RGB clip as the clock's primary video; Depth and Hyperspectral cards over
  `media.json`'s `depth` and `band` rows, which do not exist yet, each saying so; the frame-interval histogram (2 ms bins to 120 ms, every interval of the camera's six sessions;
  longer stalls counted in Dropped frames) and the intervals over 1.5 × 33.3 ms per session.
- **Data:** **real**: the cameras' hardware stamps (`hw_ms`) and footage, read-only from `/archive/datasets/bam_rig` by
  `source/build.py`. **None captured yet:** depth and hyperspectral.

## Data

`source/build.py` (numpy and ffmpeg: `python3 -B -I gallery/examples/robotics-camera/source/build.py`) reads
`rack_2026-10-23/<session>/cameras/cam_<serial>.npz` (only `hw_ms` and `wall`: the frames themselves are 2.4 GB a file)
and `cam_<serial>.mp4` for sessions 01a, 01c, 02, 04, 05 and 06 (the six the mock drew; 03's camera file is corrupt):

- `samples.csv` + `samples.schema.json` (26,089 rows): every frame interval of both cameras, `frame_dt_ms` = hw_ms[k] −
  hw_ms[k−1] written exactly (the shortest decimal that reads back as the same float), `t` frame k's time from the
  session's first frame, `device` the camera. A histogram of this file is numpy's histogram of `np.diff(hw_ms)`.
- `media.json` + `media/` (3 clips, ≈ 960 KB): CAN 14's sessions (01a, 01c, 02) from camera 218622274411, the camera that
  sees CAN 14's tag: resampled on a uniform 30 fps grid in hardware time (each grid frame the camera frame whose stamp is
  nearest; frame k sits at t0 + k / 30), cropped to CAN 14's plate, brightened (gamma 0.5), the tag boxed in orange (the
  sim-to-real case's crop and box). WHY only these: PEP 0010 §13 Q5's default publishes no rack footage beyond CAN 14's,
  so CAN 1's sessions (04-06) and camera 218622276036 give stamps only.
- `runs.json` (3): the sessions with a clip, their plan (`backlash`, `inertia heldout`, `backlash fine`), started from
  the camera's wall clock; `devices.json` (2): the cameras.
