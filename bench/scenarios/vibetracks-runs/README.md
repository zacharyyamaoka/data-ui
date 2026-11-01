# Vibe Tracks aruco-studio producer runs (700 rows, flat)

Vibe Tracks' producer runs for Aruco Studio's feature benchmark (700 runs over cpython, pyodide-node and browser hosts), flattened to one row per run. It exercises a plain-number table sorted on a timestamp, grouping by a three-value facet, a pivot with bars and a scatter chart on a log axis. `source/build.py` rebuilds `runs.json` from the producer's `runs_table.jsonl`.

- **App:** vibetracks
- **Base:** `views.base` (opens on its first view)
- **Rows:** 700

## Provenance

- **From:** ~/vt/zach/producers/aruco-studio/runs_table.jsonl (vt-run/1) @ file mtime 2026-10-26, flattened by source/build.py
- **sha256 of the data file:** `a8b16072231d33452c0011e12d65bbed0a97f2eef3fe22b7263a7599610c2e60`
- **Copied:** 2026-10-26
- **Note:** Aruco Studio's feature benchmark runs (cpython, pyodide-node, browser hosts) as one row per run; written by Vibe Tracks' aruco-studio producer.

A frozen copy: the gallery or the source app may change, this folder does not. Check it from the worktree root:
`node bin/data-ui.mjs check bench/scenarios/vibetracks-runs/views.base --data bench/scenarios/vibetracks-runs/runs.json`
