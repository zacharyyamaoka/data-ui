# Filters

Every standard rail filter kind in one rail, on robotparts' 1,149 actuators: search, popular filters, a form ›
brand tree, McMaster's picture gallery and picture list with line drawings, logo swatches, a values list with
exclude, a toggle, a select, has-a-value, Amazon's price buckets and "& up" rating, a histogram slider and a plain
log slider, ranges with dimension diagrams, a date with "last 7 days" and "older than", tag chips, a compact grid, a
Digi-Key listbox and the current-filters bar. Each one edits the same filter, so the table, the cards and the chart
move together. The McMaster, Amazon, Digi-Key and Obsidian tabs are recipes: a view with its own `facets:`.

- **App:** robotparts
- **Replaces:** the three-kind rail (values, range, has) robotparts.dev's category pages use today
  (`robotparts/site/views/actuator.base`), and each site's own hand-built filter widgets that the kinds copy:
  McMaster-Carr's pictorial facets, Algolia InstantSearch's widgets, Airbnb's price histogram, Amazon's rating and
  price bands, Digi-Key's parametric columns, Booking.com's popular filters.
- **Shows:** [every kind, the site it copies and its .base snippet](kinds.html): 21 facet kinds (`as:` values, select, toggle, has, range, slider, slider-histogram, buckets, rating,
  min-level, date, chips, swatch, gallery, picture-list, grid, listbox, tree, search, popular, current), the facet
  options (`label`, `info` ⓘ, `diagram`, `collapsed`, `limit`, `sort`, `unit`, `log`, `buckets`, `presets`,
  `older`, `images`, `columns`, `exclude`, `choices`, `levels`, `properties`, `value`), a view's own rail (`facets:` on
  a view), the readable URL (`?brand=A&peak_torque=10..<100&brand!=KST`), disjunctive counts, light and dark.
- **Data:** `actuators.json` is the robotparts-actuators case's rows (its photos stay in that folder) plus
  `in_stock`, `checks` and `listed`, written by `source/build.py` from robotparts' live rows and catalog. `logos/`
  holds the three actuator brands robotparts has a logo for (Steadywin, Damiao, JMC; hosted on the owner's basis);
  every other brand's swatch is a monogram. `icons/` and `diagrams/` are line drawings made by `source/icons.py`.
