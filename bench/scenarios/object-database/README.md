# BAM object library, public sample (366 rows, thumbnails)

The public sample of BAM's object library: 366 of its 2,196 spawnable instances (open-licence scans and BAM's generated primitives) with material, form, colour, grade, size and mass. It exercises a mid-size table with many enum columns, a cards view that loads 366 small `thumbs/*.webp` images (lazy-image path), and grouping by type. `source/build.py` copies the rows' `thumbs/` from the library; `objects.json` is a frozen copy and is not rebuilt (it held customer tags until 2026-10-27).

- **App:** object-database
- **Base:** `views.base` (opens on its first view)
- **Rows:** 366

## Provenance

- **From:** lane/object-db-public 809e9b2 gallery/examples/object-db-shelf/objects.json (366 of the library's 2,196 instances @ 3a3be7a: open-licence scans and generated primitives)
- **sha256 of the data file:** `e491417c86f4431d21c5a67dd62567ed248baea69cc7c1aeb0f4488906e9a1da`
- **Copied:** 2026-10-27
- **Note:** The public sample replaced the full library (2,196 rows, whose tags named customers) on 2026-10-27; the bench's object-database numbers before and after this date are on different data.

A frozen copy: the gallery or the source app may change, this folder does not. Check it from the worktree root:
`node bin/data-ui.mjs check bench/scenarios/object-database/views.base --data bench/scenarios/object-database/objects.json`
