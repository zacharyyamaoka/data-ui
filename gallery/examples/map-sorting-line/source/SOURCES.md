# Sources: map-sorting-line

Rebuild: `python3 -I gallery/examples/map-sorting-line/source/build.py` (Python 3 stdlib, no inputs). Built
2026-10-28.

## line.json and plan.geojson — SYNTHETIC

- **Source:** none. This is an invented floor plan of a small sorting line for mixed food-court waste. No real
  facility, layout, rate, purity or status is represented. Both titles say "synthetic"; plan.geojson carries
  `"synthetic": true`.
- **Licence:** written for data-ui; no third-party data.
- **Coordinates:** local metres, x east, y north, origin at the building's south-west inside corner
  (`"crs_note"` in plan.geojson). They are not longitude/latitude: a map view must use a plain Cartesian frame.
- **Layout (all invented):** 40 m × 18 m building; infeed tipping floor 8 m × 10 m at the west end with a 6 m truck
  door; a 30 m conveyor along y = 9 m from x = 8 to 38 m; four 4 m × 4 m robot cells straddling it at x = 11–33 m;
  five 2 m × 2 m bins south of the belt (organics, PET, aluminium, paper, film) and the residue bin at the belt's end;
  a 6 m × 3.5 m baler north of the belt; a 6 m × 3 m control room in the north-west corner.
- **Figures (all invented, fixed in build.py, no randomness):** `picks_per_hour` on robots, 1,860–2,480 picks/h;
  `purity` on bins, 82.6–96.8 %; `status` running / idle / fault, with exactly one fault (Robot cell 3) and the
  paper bin it feeds idle.
- **line.json:** one row per item (14), `xy` = the centre of its footprint, `[x, y]` in m.
- **plan.geojson:** 17 features: building walls (Polygon), control-room walls and the truck door (LineString), the
  conveyor (LineString), and a Polygon footprint per item whose `id` matches line.json.
