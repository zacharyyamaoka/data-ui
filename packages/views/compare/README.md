# compare

2 to 6 rows side by side: one column per row, one line per property, the better value marked by each property's
direction, a "Differences only" switch, and a photo pair as a slider.

```yaml
views:
  - type: compare
    name: Side by side
    order: [peak_torque, rated_torque, mass, gear_ratio, voltage, price]
    compare:
      rows: [aifitlab-8541438771336, cubemars-ak60-6]   # or "selection": the reader picks; none: the first four
      better: { peak_torque: higher, mass: lower, price: lower }   # else each property's own `better`
      diffOnly: false
```

- A column's ✕ removes it and "+ Add a row…" adds one: both write `compare.rows` through `host.setView`, so the pick
  is a view (Save view keeps it). A title opens the host's side peek; ↗ opens the row's page (`linkProperty`).
- The best value of a property with a direction is bold with an accent edge (a tie marks every best); a property
  whose values read the same on every row is muted, and hidden under Differences only (counted in a footer line).
- The photo row comes from the dataset's `imageProperty` (or a property shown as `image`); with two or more photos a
  Slide row puts any two of them in `<img-comparison-slider>`.
- Stock: TanStack Table 9.3.1 on the transposed rows (through the core's `tableModel`, the page's one copy) and
  img-comparison-slider 8.0.7 (MIT, bundled; its light-DOM stylesheet is inlined in this view's css).
