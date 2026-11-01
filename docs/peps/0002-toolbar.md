# PEP 0002: the toolbar: one bar, its variants as attributes, one filter tree

- **Status:** accepted, 2026-10-26 (built on `lane/toolbar-mix`, lane A the bar and lane B the query bar and the
  selection; it lands when that branch merges)
- **Decided by:** Zach, 2026-10-26, on the six toolbar proposals (`reports/data-ui-toolbar-proposals-2026-10-26.html`,
  lane/toolbar-proposals @ 4481dfe): "Definitely yes I like the mix", with one change, below. His notes and the twelve
  screenshots behind them: zach_brain `Sources/Daily Notes/Daily Note - Oct 26 2026.md`.
- **Code:** `packages/core/src/toolbar/` (`bar.js`, `settings.js`, `icons.js`; `query.js` and `selection.js` are lane
  B's), `packages/core/src/elements/data-views.js`, `packages/core/styles/toolbar.css`; the API is
  docs/CONTRACT.md §15; the cases are `gallery/examples/toolbar-bar`, `toolbar-notion`, `toolbar-obsidian`.

## Context

`<data-views>` had one chrome: preset tabs, a search box and a row of words (Layout, Group, Sort, Filter, Properties,
Units, ⋯), with `toolbar="compact"` and `"none"` as lighter forms. robotparts.dev/actuator/ wrapped it in a header
search and a rail, so a reader met two search boxes and eleven words before the first row. The proposals mocked six
whole toolbars (Bases, Linear, Notion, a query bar, McMaster, Shopify) over the real kit; none won alone (P1 and P5 at
79, P6 at 74, all fragile), and the report recommended a splice.

Zach did not pick one toolbar. He asked for the mix, and for the differences between apps to stay available:

> "I think we can support a couple of different variants of the tool bars you can use in different places...."

> "its funny how notion and obsidan are almost opositie / obsidan has compact views and spread out filters / Notion
> has compact filters and spread out views."

> "The drop down for display config an then be like a modal in linear or a side bar linke in notion … I prefer the
> notion layout though its much cleaner than the linear one"

> "so in one option I kinda like that perhaps like the filters etc you apply show up in the serach bar as added
> things... that way is all internally consitent! / they are just likke diufferent ways you can set htings.."

> "I also like it because its file first esign / It makes it very easy for the AI to just write filters its self.. it
> doesn't need to like use the GUI per say..."

## Decision

1. **The bar is a new chrome beside full, compact and none: `toolbar="bar"`.** One quiet row (the view chip or tabs ·
   the table's query bar · the filter control · Display), then a pill row or a bulk bar only when there is something
   to show. `toolbar="full"` stays the default and draws byte for byte what it drew; nothing in the existing gallery
   changes. The bar keeps the full toolbar's buttons in the DOM, hidden, so every menu (Group, Sort, Filter,
   Properties, Save, ⋯) keeps one implementation: the bar opens the same bodies under its own buttons, and the View
   settings panel draws them as sub-pages with a ‹ back.
2. **The variants are attributes of the element, not keys of the `.base` file.** `views="auto|dropdown|tabs"`,
   `filters="pills expanded query-tokens rail"` (a set), `display="panel|popover"`. They are read live: changing one
   redraws the chrome and keeps the view, the filters, the query and the selection. Why attributes: the variant is
   *where the page shows the controls* (a product page's sidebar wants the chip, a full-width catalog the tabs, a phone
   the two-line bar), so it belongs to the host page, as `toolbar` and `no-url` already do. The `.base` file is the
   data's view grammar, shared with Obsidian, whose own chrome draws it; a chrome key there would mean nothing in
   Obsidian, and the same file is shown by several pages in several chromes (the three toolbar cases share one file).
   What the controls *edit* stays `.base` keys and the URL, so the proposals' gate G1 ("every control writes a `.base`
   key or the URL") still holds. Zach's "Notion / Obsidian" presets are attribute sets (`toolbar-notion`: tabs + pills
   + panel; `toolbar-obsidian`: dropdown + expanded + panel).
3. **One filter tree, edited from four places.** The query bar's clauses, the pills, the rail and the Filter menu all
   read and write the one all-views filter (`el.filters`, a Bases `filters` tree) that the URL carries
   (`?brand=A,B&…`, the rest in `#f=`). The pills are a projection of it, not a second state: the bar reads it through
   the rail's own projection (`toRail(el.filters, railConfig(facetSpecs(base, view)))`), so ticking Steadywin and KST
   in the rail is one pill, "Brand: Steadywin, KST", and the pill's ✕ removes exactly that part, which the rail hears
   (its `data-views-change` listener) and unticks. A clause the rail cannot draw is a pill of its own, verbatim
   (`clauseToken` from the query bar). WHY: Zach's "internally consistent", and his file-first reason: an agent writes
   a filter as a Bases expression in the `.base` file or the URL, and every control shows it without a GUI step. The
   proposals' P6 mock kept its pills in a list of its own and drifted from the rail; that is the failure this rules
   out.
4. **The page's header search stays the site's global search; the table gets its own query bar inside the bar.**
   Zach's change to the proposals (P5 had folded the table's search into robotparts' header). The header searches the
   whole site (parts, sellers, pages); the bar's box searches and filters these rows, and `/` focuses it only when
   focus is not already in a text field, for one bar (the one under the pointer or last used, else the first).
5. **The selection lives in the element, not in a view.** `el.selection` survives a re-sort and a switch of view
   (select three actuators in the table, open the gallery, compare them), and rows a new filter hides leave it. It is
   not written to the `.base` file or the URL: a selection is a moment's working set, not a view of the data; a view
   that needs one says so (`compare.rows: [ids]` is written when Compare runs). "Show only selected"
   (`el._onlySelected`) narrows the row model before sort and group, so the groups and counts describe the selection,
   and the status line says "showing N selected".
6. **Display: Notion's panel by default, Linear's popover as the option.** The panel is a side panel inside the
   element's right edge, under the bar, resizable like every side panel (§11: 260-640 px, remembered, double-click
   resets); below 700 px both open as a full-width sheet. Layout › is the layout grid (robotparts' 3 × 4: Table Gallery
   List Board / Chart Compare Pivot Graph / Calendar Timeline Map KPI, planned types greyed) plus the layout's own
   settings from its plugin's `options()`, whatever they are; the bar adds nothing view-specific.
7. **`views="auto"` means "tabs while the whole bar fits on one line".** Tabs, the query box's minimum (200 px) and the
   tools must share the line, else the chip; a ResizeObserver re-decides. A phone's two-line bar therefore always gets
   the chip, and robotparts' ten actuator views get the chip at 1280 px (as tabs they need 1,238 px; the bar there is
   998 px wide).

8. **Views visible ⇒ filters folded; views in a dropdown ⇒ filters may expand** (2026-10-26). With no `filters`
   attribute the filter control follows how the views are drawn: tabs give one Filter button (pills once a filter is
   set), the chip gives Sort · Group · Filter · Properties as words, re-decided when `views="auto"` flips; an explicit
   attribute wins. `search="icon"` folds the table's query box behind a Search icon until it is wanted. Zach, on
   robotparts' part pages (Specs, User data, Config as tabs on the bar): "If you have these quick-switch views visible,
   then usually the pattern should be to make the filters more hidden (this is the Notion pattern)."

## Consequences

- A host chooses a toolbar with attributes and gets the same filter state whichever it chooses; a link made under one
  chrome opens the same rows under another.
- The bar's tabs never scroll sideways: the bar measures the tabs and folds what does not fit into "N more…", keeping
  the open view's tab in the strip.
- The menu bodies are shared, so a fix to the Sort menu lands in the full toolbar, the bar's Sort word and the
  panel's Sort page at once. Under the bar a menu stays open when its own redraw detaches the clicked control (the full
  toolbar still closes it, as it did).
- The class `.dv-bar` is now the bar's (§15). The table view's bar cells also use `.dv-bar` (packages/views/table,
  `table.css`), whose `position: absolute` and `span {height: 100%}` would wreck the bar; toolbar.css undoes them on
  the bar until the table's rule is scoped to its cells.
- The variants are not portable to Obsidian: Obsidian draws a `.base` file in its own chrome, which is the point.

## Alternatives considered

- **One of the six proposals as built** (P1 Bases 79, P5 McMaster 79, P6 Shopify 74, P3 Notion, P2 Linear, P4 query
  bar; `reports/data-ui-toolbar-proposals-2026-10-26.html`): each lost a criterion another won; Zach chose the mix.
- **The variants as `.base` keys** (a `toolbar:` block at the top of the file): rejected for the reasons in 2; a view
  already carries `facets:` for its own rail, which *is* view content, and stays.
- **A pill state of its own, synced to the rail** (P6's mock): two states drift; one tree with projections cannot.
- **The selection in the view entry or the URL**: it would make a view switch drop it or a shared link carry someone's
  half-finished picking.
- **Linear's popover as the default**: Zach prefers Notion's panel ("much cleaner"); the popover stays an option.

## Addendum 2026-10-26: one row, degrading by priority

Zach, looking at a case whose toolbar wrapped to a second line (his screenshots 78-82): "How the table toolbar folds
to two lines? I don't like that… I feel it should be 1 bar. How do other prior-art apps deal with this? Quickly look at
Shopify and Obsidian, I can see it never splits on top into multiple lines."

| App | How its toolbar degrades (source) |
|---|---|
| Obsidian Bases | One row at every width: Sort · Group · Filter · Properties · Search · New as words, then the same as icons only, then the view chip shortened ("T ⌃ 5…") with a few icons (Zach's screenshots 80-82, three widths). |
| Shopify admin index tables | One pill bar, never a second line: the saved-view chip ("All ⌃⌄"), "Search and filter", a columns icon; the filters and sort live behind the bar's controls, not beside them (Zach's screenshot 79; Polaris IndexFilters). |
| Notion databases | View tabs show what fits and the rest fold into "{#} more…"; a tab can show its icon only; when the toolbar is short of room, Filter and Sort are reached from the ••• menu (Notion help, "Views, filters, sorts & groups"; a third-party guide on the ••• fallback). |
| Linear | One header row: the view's filters and Display behind buttons, with the view's settings in one Display popover rather than words in the bar (Zach's screenshot 20261026122542; narrow-width behaviour not verified this session). |
| GitHub Projects | View tabs above one row of the filter box and controls; not verified this session how it narrows. |
| Airtable | One view bar (Hide fields, Filter, Group, Sort, Color…); users on small laptops report the extra icons not showing, i.e. it drops controls rather than wrap (Airtable community thread; the exact rule not documented). |

**Decision:** the bar is one row, always (CONTRACT §15 note "the bar is one row"). As its own width shrinks it takes the
steps of one priority table (bar.js `DEGRADE`) in order: the tabs fold into "N more"; labels drop to icons; low-priority
controls move into "…"; the query box folds to its icon; the tabs fold to the chip; the count drops; the chip drops its
name. This replaces `views="auto"`'s two-state rule (tabs while they all fit, else the chip) with a graded one, and the
two-line bar below 640 px and frame="tabs"' tabs-over-a-rule line with the one row. The pill / bulk row stays a second
row by design: it appears only while there is a filter or a selection.

Sources: polaris.shopify.com/components/selection-and-input/index-filters; notion.com/help/views-filters-and-sorts;
temperstack.com/learn/notion/filter-sort-database (the ••• fallback); community.airtable.com, "view bar customise field
option do not show" (accessed 2026-10-26).

## Addendum 2026-10-26: one model for the controls

Zach, on the first-look report: "Why do you have Filter twice? Filters and Filter?" and "I don't like how you have
Filter outside and also inside the Display dropdown." **Decision:** Display, the right-most control, always holds
everything (layout, frame, properties, filter, sort, group); any of filter, sort, group and properties may also be
promoted onto the bar (`promote="…"`), and a promoted control is the same control: the same state and the same body,
opened anchored to it. There is one Filter: with a linked rail it drives the rail. `labels="icons"` keeps the bar's
labels off; by default they drop first as the bar narrows. The bulk bar becomes Shopify's band over the column header
row, tinted (`--data-selection-band`), so it never reads as a second toolbar. Presets: Shopify (`promote=""`, three
elements), Notion (tabs, `promote=""`), Obsidian (dropdown, the four promoted). `filters="expanded"` stays as an alias of
promoting the four. WHY attributes again (as in decision 2): where the controls sit is the host page's choice; the state
they edit stays in the `.base` file and the URL.
