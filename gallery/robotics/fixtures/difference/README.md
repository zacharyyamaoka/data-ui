# The difference(a, b) fixture

Two trajectories in, the expected rows out: the oracle for `difference(a, b)` (../../CONTRACT.md §5). A trajectory
library's test reads it through ../../fixture.py (`fixture.check_difference(poses=…, samples=…) == []`); a gallery
case's checks read `fixture.rows("diff_poses")` to measure the arrows a view drew.

| File | What |
|---|---|
| `poses.json`, `samples.json` | the inputs, as a producer writes them ({schema, rows}): a = situation `real`, b = situation `target`, of run `fixture/r1` (and a run `fixture/r2` that only a has) |
| `diff_poses.json`, `diff_samples.json` | the rows `difference(a, b)` returns: 152 pose rows (tool0) and 304 sample rows (J3 elbow, Z lift) |
| `provenance.json` | the command, the seed, the Python, numpy and scipy versions that wrote them, and the row counts |
| `source/make_difference_fixture.py` | rebuilds all of it: `uv run --with numpy --with scipy python3 gallery/robotics/fixtures/difference/source/make_difference_fixture.py` |

**How the expected rows were made.** numpy for the linear interpolation (exact at b's own samples) and scipy's
`Rotation` and `Slerp` for the orientations (the short way), the angle between two orientations (`magnitude()` of
`a⁻¹·b`) and the canonical sign (`as_quat(canonical=True)`), computed from the input files as written (the script
writes them, reads them back, then computes), so the expected rows come from exactly the numbers every reader sees.
Written with numpy 2.5.4 and scipy 1.18.1 on Python 3.14.6 (provenance.json).

**Checked by two more implementations.** tools/test_robotics_fixture.py reproduces every row with a stdlib-only
difference(a, b) written from the spec, and nine wrong ones each fail. traj_compare's landed interpolation
(`analysis._resample_columns`, `_slerp_resample`, `rotations.rotation_angles_between`) reproduces every row once its
rows are kept to b's span; as landed it also writes 18 rows outside it, because `np.interp` holds b's end values (the
spec never extrapolates).

**The trajectories are synthetic on purpose.** Each case the spec names sits where it can be seen:

| Case | Where |
|---|---|
| a starts before b and ends after it: no rows there | a runs −0.05 to 1.75 s, b 0 to 1.6 s |
| a sample exactly on b's first, an interior and its last sample: b's values exactly | a has t = 0, 0.4 and 1.6 s |
| non-uniform rates | a at a jittered 94.4 Hz, b at 25 Hz |
| a 150° turn between two of b's samples, where slerp and nlerp part by degrees | b, 0.80 → 0.84 s |
| b's quaternion written with the other sign: slerp must take the short way | b at 1.2 s (k = 30) |
| b's quaternions past w < 0: the canonical sign is tested | b after 0.84 s |
| a's quaternion with the other sign than b's: the angle stays the small one | every 7th a sample |
| a quaternion that is not unit: normalized before it is measured | a's sample 40 (× 1.000002) |
| a null in b and a null in a: null out, never 0 | b's J3 elbow `tau_nm` at 0.6 s; a's J3 elbow `qd_deg_s` at its sample 50 |
| a prismatic axis: `e_q_mm`, not `e_q_mrad` | Z lift |
| a body b writes in another frame: no rows | lever_tip (a: belt, b: base) |
| a body, a device and a run only a has: no rows | camera_link, J1 base, fixture/r2 |
