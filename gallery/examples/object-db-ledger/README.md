# Object library · the dataset's own Bases (proposal 2)

Table-first, and no new view design: the `.base` files `object-db bases` already writes (all but Customers, which is private) for Obsidian, read by
data-ui. Each needs two edits (a `data:` line added; the `file.inFolder(...)` clause commented out, because a data
file has no vault folders), and Types.base a third (its backlink formula becomes a precomputed column). The peek adds
the 3D orbit viewer on its own, from the field's `media: mesh`.

- **App:** object database
- **Replaces:** nothing: it is the same files, so Obsidian and data-ui show one library the same way. The verbatim copies are in `library/`.
- **Shows:** table, cards (the dataset's Cards, Real scans, Soft twins), the peek's 3D viewer, the measured gap between Obsidian's grammar and data-ui's (`file.*` and formulas)
- **Data:** `../object-db-shelf/objects.json`, `types.json`, `materials.json`, `mix_list.json` (a public-safe sample, built by `../object-db-shelf/source/build.py`; the library's Customers.base is not reproduced: customers are private)
- **Prior art:** Obsidian Bases (the files themselves), Airtable and Notion database tables, FiftyOne's sample table

On the public sample the dataset's "Real scans" view (GraspClutter6D and GraspNet-1B scans) shows no rows: those scans' licences keep them out of a published gallery. The view is kept as the dataset wrote it.
