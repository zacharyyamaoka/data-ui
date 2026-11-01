# cards (and the media grid)

Bases' cards view, and with `lightbox: true` the media grid (docs/VIEWS.md: "not a new view: the cards view plus a
lightbox"). One card per row: the image, the title (the view's first `order` property) and one line per other
property; a group heading per `groupBy` value, in `groupOrder`.

- **Bases keys (Obsidian 1.14):** `cardSize` (50–800, default 200: the narrowest a card is drawn; the lanes are as
  many as fit), `image` (the property holding each card's image; none = no image well), `imageFit` (`cover` |
  `contain`), `imageAspectRatio` (0.25–2.5, default 1, read as the image well's height ÷ its width), `order`,
  `sort`, `groupBy`, `groupOrder`, `limit`, `filters`.
- **data-ui keys:** `maxColumns` (1–12: never more lanes than this, however wide; unset is no cap), `lightbox: true` (the image opens full screen), `media` (the property the lightbox shows, default
  `image`; a `.mp4`/`.webm` plays as video), `caption: [p]` (the properties under it), `display: {p: image | badge |
  link}` (a property line drawn as a small image, e.g. a brand logo).
- **The grouped gallery (docs/CONTRACT.md §20)**, a catalogue home (McMaster-Carr, a Shopify collection):
  - `sections: true` (implied by `tiles`): `groupBy` draws as a section title, `role="heading" aria-level="2"`, 22 px
    bold with its row count and a rule under it; `subGroupBy` as a sub-header, `aria-level="3"`, 15 px bold. A
    section's rows with no second-level value come first, straight under the title with no sub-header, so a section
    whose rows all lack it has no second layer. Headings stay items of the virtualised lanes.
  - `tiles: {property, image?, link?, all?, limit?, size?}`: inside each (sub-)section one tile per value of
    `property` instead of a card per row: a picture from the first of its rows (`image`, default the view's `image`;
    a monogram where there is none), the value and its count "(265)", most rows first, then by label. `all: true`
    puts "All <group> (N)" first (under a section's no-value rows it stands for the whole section). `limit: N` keeps
    N tiles while several sections show and ends with "Every <property> (M)", M the number of values; a section the
    reader has drilled into (the only one left) shows every tile. `size` is the tile's width (default 120 px). A
    click goes to `link`'s value on the tile's first row (a real `<a href>`), else drills: `host.setFacet` picks the
    section (and the sub-header for All / Every) and the tile's value, so the page shows only those rows; once the
    filter picks the tiles' property the section draws its rows as cards. Tiles are buttons or links; arrows move
    between them as between cards.
  - `switcher: tabs | segmented | dropdown | none` (default none): a "Group by" control above the grid, one entry
    per `groupings:` item, calling `host.setView({grouping})`. For a page that draws no switcher of its own.
  - `groupings:` / `grouping:` and numeric `bins:` on a level are the core's (the row model resolves them): the view
    receives the effective `groupBy` / `subGroupBy` / `tiles` in `input.view` and the binned groups in
    `input.groups`.
- **Captions carry provenance:** when the media cell is a rich cell, `{value, source, asOf}`, the caption's second
  line reads "source · accessed date" (the source's host, linked).
- **Paths:** a relative image path is read from the data file's folder, as `data:` is read from the `.base` file's.
- **Keyboard:** Tab to a card, arrows move between cards (scrolling the virtualised grid), Enter opens the peek;
  with `lightbox: true` the image is its own button (Enter opens it; arrows and Esc inside PhotoSwipe).
- **Selection:** with `selectable` on the element each card has a check (on hover, and on every card once any is
  selected): a check toggles, shift adds the range; on the card ctrl/cmd-click toggles and shift-click takes the
  range. Selected cards are `.dv-sel` (docs/CONTRACT.md §15).
- **Not built:** `masonry` (lanes already allow it: `laneAssignmentMode: 'measured'` and measured heights), `hover`,
  and the demo's `sketch`.

Stock: TanStack Virtual 3.19.7 with `lanes` (section titles, sub-headers and tiles are items of its lanes) (the page's one copy, imported from `@data-ui/core`), so 1,149 cards keep
a few dozen in the DOM; PhotoSwipe 5.4.4 (MIT) for the lightbox, its stylesheet re-pointed at the `--dv-*` tokens and
the lightbox appended inside `<data-views>`, so it follows the page's theme. Moved from the views report's demo
(`docs/views/demo/views/cards.mjs`).

## 3D models (`mesh:`, docs/CONTRACT.md §23)

`mesh: <property>` puts the row's model in the image well as a `<data-mesh>`, with `image` as its poster: the card
looks the same until the pointer is over it, then the model turns; drag turns it by hand (and does not open the
peek). `meshInteract: hover | click | none` (default `hover`; `click` for dense sheets and phones). One WebGL renderer
serves the page, at most 4 models animate at once. Case: `gallery/examples/object-db-shelf`.

`meshView: <property>` (a per-row `{dir, fov, box, dist}`) starts the live model where its poster was taken: same
direction, same lens, its silhouette on the poster's. `meshBackground: match | light | theme` (default `match`: the
poster's own backdrop, so the hand-off from poster to model shows no edge).
