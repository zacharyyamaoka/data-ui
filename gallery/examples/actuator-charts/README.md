# Actuator charts

robotparts' 1,149 actuators as chart presets in one `.base` file: peak torque vs mass coloured by brand, an Ashby
chart with a filled envelope per drivetrain and a constant N·m-per-gram index line, torque density, price vs torque,
small multiples by form and median torque by brand. Tick the rail and every chart redraws; hover a dot for the
part's photo and values; click it for the record.

- **App:** robotparts
- **Replaces:** robotparts.dev's hand-rolled Chart view (`site/static/site.js` `scatter()`: one log-log SVG with an
  X and a Y picker, no colour, no presets, no hover card) and the views lane's demo chart
  (`docs/views/demo/views/chart.mjs`).
- **Shows:** each preset a `type: chart` view whose `chart:` block is Vega-Lite; log or linear per axis; colour by
  any field (past eight values the commonest seven keep a colour and the rest read Other); size; `facet`; the
  Encode menu (Encode, top left of the chart) rewriting `chart:` live, so Reset and Save view appear; the hover
  card with the photo, the title and each value with its unit and basis; Rows, the same filtered rows as the table;
  `guides:` envelopes (convex hulls in log space, filled), an index line and a rule.
- **Data:** the sibling case's rows, `../robotparts-actuators/actuators.json` (`data:` points there), whose `photo`
  column `gallery/tools/build_examples.py` writes: `../robotparts-actuators/photos/*.webp` are 150 of robotparts'
  primary photos (one or more per brand, 240 px), resolved against the data file, not this page. The other 999 parts'
  cards say "no photo". 128 parts lack a peak torque or a mass, so the
  torque-vs-mass charts draw 1,021 dots and say so.
- **Skin:** `skin.css` is robotparts' token mapping, the same block as the sibling case's.
