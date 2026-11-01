# robotparts photos (175 rows, cards with images)

robotparts' actuators and cameras (175 rows) as image cards with brand logos, grouped by brand, plus a square photo wall with a lightbox. It exercises the cards view with real images (`media/` holds the 177 photos and logos the rows name), group headers and the lightbox.

- **App:** robotparts
- **Base:** `views.base` (opens on its first view)
- **Rows:** 175

## Provenance

- **From:** ~/data-ui/gallery/examples/robotparts-photos/photos.json @ main 0dbc3d4
- **sha256 of the data file:** `f781eb0524bbaf5bf5ffd39e9c04682809d896544806ce24e679eee61a2fae20`
- **Copied:** 2026-10-26
- **Note:** Actuators and cameras as image cards with brand logos; photos are robotparts' hosted primary photos resized by the gallery build.

A frozen copy: the gallery or the source app may change, this folder does not. Check it from the worktree root:
`node bin/data-ui.mjs check bench/scenarios/robotparts-photos/views.base --data bench/scenarios/robotparts-photos/photos.json`
