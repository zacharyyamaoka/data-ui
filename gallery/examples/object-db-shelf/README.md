# Object library · 3D shelf (proposal 1)

Gallery-first: BAM's object library as cards, each the library's own poster render, the object's real mesh turning
under the pointer. One WebGL renderer serves the whole page (at most 4 models animate at once), so 409 or 2,454
cards cost images until someone hovers. The rail is the library's six orthogonal axes plus where the geometry came
from; the peek opens on an orbit viewer.

- **App:** object database
- **Replaces:** `~/bam-waste-objects/views/Objects.base` (Cards, Real scans) and the FiftyOne App's grid on port 5162
- **Shows:** cards with `mesh:` (3D on hover; `meshInteract: click` on the contact sheet), the peek's 3D orbit viewer, a rail of chips, lists, search and a log mass histogram, the same rows as a table, and the raw source (`type: source`: every key as stored; a row's Source opens the Markdown note it was read from, `sources/<id>.md`)
- **Data:** `objects.json`: a public-safe sample of 366 of the library's 2,196 instances: 150 Google Scanned Objects (CC BY 4.0) and 30 EGAD shapes (BSD-3-Clause) as real scans, 186 of BAM's own generated primitives. No customers, customer mixes, supplier research or scans under non-commercial or unclear licences. Each row is read from its public note in `notes/` (the raw source view's origin); posters in `thumbs/` (the library's own renders, pixels only), a GLB per object in `meshes/`. Built by `source/build.py` from the library (read-only).
- **Prior art:** Sketchfab and Thingiverse grids (static thumbnails, 3D on open), FiftyOne's grid + 3D modal, Obsidian Bases' card view (the library's current Cards view), Objaverse's browser
