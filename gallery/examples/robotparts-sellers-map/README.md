# robotparts sellers by country

Where robotparts' sellers are based and where they ship, from what each seller published with its listings
(`seller_country`, `ships_to`). Markers sit on the country's Natural Earth label point; rows at one point count
together and a counted marker lists its rows. The basemap is bundled: no tile server is asked.

- **App:** robotparts
- **Replaces:** the part page's "Ships to <region>: yes / no" column (robotparts `build/site_pages.py`) and the
  seller table in `docs/sellers.md` for the question "who can ship to me".
- **Shows:** the map view (MapLibre GL on the bundled Natural Earth 1:110m countries) with `coordinates`,
  `markerColor` from a property (the `seller` column's `colors`) or a token (`var(--data-series-3)`), `center` and
  `defaultZoom`, filters, and the same rows grouped by country in a table.
- **Data:** `sellers.json`, written by `source/build.py` from robotparts' `parts/*/quotes.jsonl`. Countries too
  small for 1:110m have no point and say so; Hong Kong's centre is entered by hand and marked `assumed`. Makers
  have no country in robotparts, so none is shown.
