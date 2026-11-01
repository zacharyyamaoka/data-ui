# timeline

Rows as bars (`start` -> `end`) or points (no end) on a zoomable time axis, stacked in lanes. A click opens the
record; the peeked row is selected.

- **Keys:** `start` (required), `end`, `title` (default: the dataset's title property), `groupBy` (lanes, in
  `groupOrder`), `subGroupBy` (nested lanes, foldable), `color` (a property: each value a series slot from its
  column's `colors`, else `hueOf`), `zoom: {min, max}` (ISO 8601 durations, e.g. PT10M, P14D), `filters`.
- **Not drawn:** dependency arrows (no key for them yet; VIEWS.md names Frappe Gantt if they are ever needed).
- **Stock:** `vis-timeline` 8.5.5, standalone build (vis-data and moment inside), dual Apache-2.0 / MIT. It has no
  custom properties, so `src/timeline.css` recolours its classes from `--dv-*`.
