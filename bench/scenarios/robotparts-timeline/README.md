# robotparts releases and branches (30 rows, timeline)

robotparts' releases and the branches merged into them over four days (30 rows, from git metadata): timeline lanes by kind, by release and sub-grouped, plus a releases-only view. It exercises the timeline view: spans, point events, lane grouping and zoom.

- **App:** robotparts
- **Base:** `views.base` (opens on its first view)
- **Rows:** 30

## Provenance

- **From:** ~/data-ui/gallery/examples/robotparts-timeline/timeline.json @ main 0dbc3d4
- **sha256 of the data file:** `7a70f510f8cd78de25f2c96f08dc264c4a1f0586a3ab59a0496373924cdaf4cb`
- **Copied:** 2026-10-26
- **Note:** Releases and the branches merged into them, 2026-10-22 to 2026-10-25, read from robotparts' git (metadata only).

A frozen copy: the gallery or the source app may change, this folder does not. Check it from the worktree root:
`node bin/data-ui.mjs check bench/scenarios/robotparts-timeline/views.base --data bench/scenarios/robotparts-timeline/timeline.json`
