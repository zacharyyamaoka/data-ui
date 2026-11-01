# robotparts logo rounds

Every SVG from robotparts' eleven logo rounds of 2026-10-25 (203 files) as one media grid: grouped by round, each
card the logo with its name, kind and the round's score out of 35; click a logo for the lightbox, then arrow through
all of them. Other views rank the lockups by score and lay out the favicon marks.

- **App:** design work
- **Replaces:** the hand-built logo gallery reports, one per round (`reports/media/robotparts-logos-r2…r11-2026-10-25.html`
  in robotparts, each written by its round's own `build_gallery.py`, which inlined every SVG into a page of its own).
- **Shows:** the media grid (`type: cards` with `lightbox: true` and `caption`), `imageFit: contain` with a wide
  `imageAspectRatio`, group headings by round, a score that is missing with its reason (`{value: null, why: "round 1
  was not scored"}`), the rail's range facet on score, and a skin that keeps the image wells paper-white in a dark
  theme because the logos are one dark ink.
- **Data:** `logos.json` and the `r01-…r11-*.svg` files in `svg/`, written by `source/make.py` from the logo lane's
  `design/logos-2026-10-25*/` folders (robotparts `lane-logos` @ 2d1aaf3): every SVG joined to its round's
  `logos.json` by file name; an SVG no entry names (an animation, the live logo) is still a row.
