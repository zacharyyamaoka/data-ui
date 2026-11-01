# Object collection

BAM's object library as a catalogue home, the way McMaster-Carr and a Shopify collection lay one out, over its public
sample (366 objects): a big title per material with its count, a second heading only where the data has one (Plastics,
Glass and Paper split into Medical and Food; Metals has no second layer), and inside each a tile per type with its
count. The left rail filters to one group and gives every group back when clicked again; the switcher regroups the
same rows by size (bins of the bounding-box volume), shape, type or source, and the rail follows it.

- **App:** ObjectDB
- **Replaces:** ObjectDB's home page (object-database `site/`), which draws its own category sections and links; the
  grouped gallery is the cards view with headers and sub-headers, so ObjectDB's home becomes one `.base` view.
- **Shows:** `type: cards` with `tiles: {property, all, limit}` (one tile per sub-category, "All …" first, "Every
  Type (N)" when there are more), `subGroupBy` drawn as a sub-header only where its value exists, `groupings:` with
  `grouping:` and the built-in `switcher: segmented`, a numeric group level with `bins:` (`< 250 mL`, `250 mL – 1 L`,
  `1 L – 5 L`, `≥ 5 L`: 78 / 135 / 113 / 40 objects), and the rail's `as: nav` facet following the view's grouping
  (`?family=metal`, `?bbox_volume_ml=250..<1000`).
- **Data:** `objects.json`, written by `source/snapshot.py`: ObjectDB's public sample only, the 366 objects
  lane/object-db-public (809e9b2) vetted (`source/public_ids.txt`): 150 Google Scanned Objects (CC BY 4.0), 30 EGAD
  shapes (BSD-3-Clause) and 186 of BAM's generated primitives. Columns: id, name, family, type, grade, size class,
  bounding-box volume, mass, source, geometry and shape, plus a derived `area` (Medical / Food for plastic, glass and
  paper; none elsewhere). No customers, mixes, streams, tags, supplier research or labellers; the rebuild fails closed
  on any id or source outside the sample. No thumbnails: each tile draws a monogram.
