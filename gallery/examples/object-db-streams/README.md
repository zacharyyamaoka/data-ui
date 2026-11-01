# Object library · stream board (proposal 4)

Mix-first: a waste stream is the page. Its composition as bars and shares, an example object per type, and the
objects sampled for that stream as 3D cards with their mass distribution and size scatter. One stream picker drives
both `.base` files on the prototype page.

- **App:** object database
- **Replaces:** `~/bam-waste-objects/views/composition.html` (object-db composition) and FiftyOne's saved views per mix
- **Shows:** chart (Vega-Lite bars, histogram, scatter with hover card), table with share bars, pivot (streams × types), cards with `mesh:` (3D on click)
- **Data:** `../object-db-shelf/mixes.json` (10 mixes' composition rows, from the mixes' `## Composition` tables) and `objects.json` (a 409-object sample); built by `../object-db-shelf/source/build.py`
- **Prior art:** Greyparrot Analyzer's composition dashboards, AMP Cortex's material breakdowns, waste-audit reports (RECYC-QUÉBEC 2023-24), Zach's own composition.html
