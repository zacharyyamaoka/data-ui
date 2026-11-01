# Robot arm · Playback + Gates

The Robot arm template with its gates on top, on STAND-IN data as the template is (sim2real's simulated UR5e; no real arm run exists): each situation's path error against the target, judged against a stand-in tolerance, its tool path painted by its own error with the tolerance as a tube around the target, the error per half second against the tolerance, and BAM Reach's reach map (real) in verdict colours, red where no orientation reaches and green where every one does.

- **Use case:** Robotics · Playback + Gates
- **App:** BAM rig
- **Replaces:** traj_compare's error colouring and tolerance band on the tool path (its report's 3D panel), and BAM Reach's red-to-green reach colours (`bam_reach` colorize.py), as data-ui's path overlay and verdict voxels.
- **Shows:** the template's every panel, unchanged, plus the overlay (docs/CONTRACT.md §35): a gate matrix, the path overlay (`trajectory3d` color and tolerance), a limits band, a level history, verdict voxels (`scale: verdict`) and status cells.
- **Data:** **stand-in**: every gate row is computed from the template's stand-in difference rows (sim2real's simulated UR5e) against a stand-in tolerance (warn 5 mm, error 10 mm; rotation warn 20, error 50 mrad), `basis: stand-in`; the reach map is BAM Reach's real analysis (the template's grid.json).

## Data

`source/build.py` reads the template's `poses.json` and `diff_poses.json` and writes:

- `checks.json` (18 rows): per run and situation, Path error (RMS of err_mm), Path max and Rotation (largest err_rot_mrad), against the stand-in tolerance.
- `windows.json` (90 rows): the path error per 0.5 s window.
- `poses_error.json` (1,588 rows): the template's poses, each with its own err_mm from diff_poses.json (the target's rows null): what the path overlay paints.

The views read the template's files through `../robotics-arm/`; this folder holds only the gate rows and their producer, so `diff ../robotics-arm/views.base views.base` is the overlay.
