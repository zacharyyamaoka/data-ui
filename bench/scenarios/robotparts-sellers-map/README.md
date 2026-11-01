# robotparts sellers map (322 rows, map)

Where robotparts' sellers are based and ship to (322 rows; coordinates are rich cells carrying their basis). It exercises the map view's marker path and a grouped table; rows without coordinates (76) exercise the missing-value path.

- **App:** robotparts
- **Base:** `views.base` (opens on its first view)
- **Rows:** 322

## Provenance

- **From:** ~/data-ui/gallery/examples/robotparts-sellers-map/sellers.json @ main 0dbc3d4
- **sha256 of the data file:** `613a36566e13ebdb0dcfdbe4bd3607ec2bd451cc8206d7e579ae0b3fd658d177`
- **Copied:** 2026-10-26
- **Note:** Where robotparts' sellers are based and ship to, from their own listings; coordinates are Natural Earth label points.

A frozen copy: the gallery or the source app may change, this folder does not. Check it from the worktree root:
`node bin/data-ui.mjs check bench/scenarios/robotparts-sellers-map/views.base --data bench/scenarios/robotparts-sellers-map/sellers.json`
