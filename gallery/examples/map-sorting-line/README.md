# A sorting line, in metres

A small sorting line laid out on a plan in metres, not on the Earth: tipping floor, a 30 m conveyor, four robot pick cells, six output bins, a baler and the control room. Robots are sized by picks per hour and coloured by status, so the one in fault stands out; the scale bar reads in metres.

- **App:** Map
- **Replaces:** a CAD screenshot of the floor plan plus a status table on another screen.
- **Shows:** `space: local` (coordinates are [x, y] metres; MapLibre draws them near 0°, where a degree is 111,320 m both ways), a plan from `regions` with no data join coloured by `kind`, and points sized and coloured by row values.
- **Data:** `line.json` and `plan.geojson`: SYNTHETIC, a plausible line for mixed food-court waste, about 40 m × 18 m.
