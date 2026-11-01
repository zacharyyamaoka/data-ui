# Sim-to-real · rack motor twins

CAN 14's twin against the real rack, sample by sample and on camera, then the rack's eight motor twins against the
real motors on one page: twin error against the measurement floor per motor, the model ladders (which modelling rung
buys how much), the twin's error run by run, the improvement rounds, and every model-card term. Click a motor anywhere
and every motor panel shows only it.

## Layout (round 2, PEP 0005 cards)

- **Tiles (CAN 14):** Twin gap RMS (motors.json `twin`, delta to `floor`), Repeat floor (`floor`), Twin ÷ floor
  (gauge, the 1.5× tick is acceptance gate T2 from rack_2026-10-24 `acceptance.json`), Held-out runs (Count of
  runs.json's CAN 14 rows, derived). They read unlinked copies of motors/runs/models (`can14_*` datasets), so a
  motor click below never empties them.
- **Playback**, one clock over `samples.t` (`clock: {data: samples, time: t}`).
- **Angle: real vs twin** (target dashed, real, sim_identified, sim_identified_plus) beside **Rack camera (real)**,
  the primary video; **Gap: twin − real** (`gap_mrad`, rules at ± CAN 14's repeat floor 0.522 mrad) beside **Tape A
  vs tape B (real repeat)**, an onion/wipe overlay of the two real repeats (its own `tape_pair` dataset, so the rail
  never empties it).
- The rail's **Run** (samples.json, `as: select`) narrows the time series and, through `media.run ↔ samples.run`,
  the camera. It starts on the staircase (has a clip, and spans the whole clock).
- **Twin vs floor** (eight motors), **Model error by rung (CAN 14)** (bullets in rung order, the tick at the floor),
  then the round-1 ladders, run-by-run chart, rounds, model cards and motors table.
- **No sim video:** no sim render of the rack exists, so no card lays a sim picture over the camera; the overlay is
  real vs real (the repeatability floor, the bar a twin can never beat). The sine has no usable clip: its camera card
  shows "—". Open in Rerun: `uv run --script tools/rerun_export.py gallery/examples/sim-to-real/views.base`.

- **App:** BAM rig
- **Replaces:** the rack motor models report's tables and its per-motor JSON
  (bam_ws `reports/media/rack-motor-models-2026-10-23/report.html`, built by `bam_rack_twin/docs/`)
  and the model cards' markdown tables (`model_cards/*.md`), for browsing; the report keeps the figures and video.
- **Shows:** five datasets linked by `motor` to one `motors` dataset; KPI cards with the delta to a property of the
  same row (`compare.against: floor`); two charts kept apart because they use different rulers; a run-by-run line
  chart; rounds filtered by a view `filters:` expression; a model-card table grouped by motor with the full toolbar;
  per-dataset rails (part and board; model family; run kind and speed; term status).
- **Data:** written by `source/build.py`, read-only from `/archive/datasets/bam_rig/rack_2026-10-23/analysis/`
  (`budget_can*.json`, `model_cards/*.json`), `rack_2026-10-24/analysis/` (`acceptance.json`, `floors.json`,
  `friction_study.json`) and `rack_2026-10-25/analysis/twin_round{4..7,9,10}.json`. **Real** hardware runs. Only CAN
  14's floor is a measured repeat floor; the other seven are a sine cycle-to-cycle proxy, drawn as a stand-in. Every
  budget run is held out, so there is no train/test split to show.

## Data (round 2)

Written by `source/build_replays.py` (`~/pidtuna/.venv/bin/python -I
gallery/examples/sim-to-real/source/build_replays.py`: numpy + system ffmpeg), read-only from bam_ws
`reports/media/rack-motor-models-2026-10-23/traj_compare.html` (the CAN 14 traj_compare payload) and
`/archive/datasets/bam_rig/rack_2026-10-2{1,3}/<session>/{runs,cameras}/`. **Real** hardware runs and real camera
footage; the two sim situations are twin replays of the same commands.

- `samples.json` (12,368 rows): four held-out CAN 14 runs: `staircase 10-23` (rack_2026-10-23/session_01a s03),
  `sine 10-23` (session_01c s03), and `tape A 10-21` / `tape B 10-21` (rack_2026-10-21/session_03 s01 and s05, the
  same medium tape twice: a real-vs-real repeat). Situations target, real, sim_identified, sim_identified_plus;
  `q_deg`, `err_mrad` (the payload's err_q), `gap_mrad` (sim − real). The payload's own display grid (~93 Hz, the
  staircase ~46 Hz), not resampled. The file's `runs` maps each short id to its path. traj_compare names runs without
  their date, so each is matched to its dated folder by data (real q equal to the npz to 1e-5 rad).
- `media.json` (3) + `media/can14_*.mp4|jpg`: camera 218622274411, cut from the session recording, resampled on a
  uniform 30 fps grid by nearest frame stamp from the run's start − 0.3 s, so `t0` = −0.300 s and frame k is at
  t0 + k/30 by construction; `max_stamp_gap_s` says how far the farthest picture is from its slot (8-70 ms here).
  Cropped to the left plate, brightened (gamma 0.5), CAN 14's tag boxed (box from the 10-24 tag detection, same
  mount, checked by eye). Basis `real-camera`.
- **Rungs:** no `rungs.json`: `models.json` already holds the model ladder per CAN (`rung`, `model`, `family`,
  `error` = median RMS rich cell with `n` runs; the floor is its `rung` 20 row) and `motors.json` holds `floor`,
  `twin`, `twin_over_floor` per motor.
- **Missing:** the sine has no clip (its camera kept 53 frames over 6.5 s, a 0.8 s hole); the payload's other 27 CAN 14
  comparisons are not used (several have no npz on disk under their session name, or a corrupt camera file). **No sim render of the
  rack exists**: bam_rack_twin has a renderer (`bam_rack_twin/render.py`, cad2robot MJCF through a calibrated camera),
  but nothing has been rendered with it, and CAN 14's joint is not in the CAD export (traj_compare's `sim_cad` slot is
  empty for that reason). The camera's capture-to-stamp latency is not measured.
