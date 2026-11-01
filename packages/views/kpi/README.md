# kpi

The stat cards of the kit, one bundle (`dist/views/kpi.js`, SVG and CSS, no chart engine of its own):

| `type` | Draws | Source file |
|---|---|---|
| `kpi` | one stat card, or one per group: label, big number, unit, delta pill, sparkline, footer | `src/index.js`, `src/elements.js` |
| `gauge` | one number against a scale: a progress bar or a semicircle arc, target tick, bands, over / under | `src/gauge.js` |
| `bullet` | one bullet chart per row or group, aligned | `src/bullet.js` |
| `barlist` | a ranked bar list (Tremor's BarList) | `src/barlist.js` |
| `status` | a tracker grid (Tremor's Tracker): a row per group, a block per row coloured by its state; with `tracker.column` the gate matrix (CONTRACT §35): a column per value, headers, a glyph and an accessible name in every cell, n/a where no row reaches | `src/status.js` |

KPI cards (docs/SPEC.md §9.1): `type: kpi`, and the two elements it draws, `<data-kpi>` and `<data-sparkline>`.

**On a plain page** (no `<data-views>`), load the stylesheet and this bundle; it defines both elements and adds its
own styles (`import 'data-ui/kpi'` from a bundler; the bundle imports `../data-ui.js` beside it, so vendor the whole
`dist/`):

```html
<link rel="stylesheet" href="/vendor/data-ui/data-ui.css">
<script type="module" src="/vendor/data-ui/views/kpi.js"></script>

<data-kpi label="Successful picks per minute" value="24.6" unit="picks/min" basis="measured"
          delta="+1.2 vs previous" tone="good" from="computed from 3 runs">24.6 picks/min</data-kpi>
<data-sparkline values="18.2,19.9,,21.4,23.4,24.6" bases="measured,measured,,estimate,measured,measured"></data-sparkline>
```

From script, `el.card = {label, value: {value, unit, basis, n}, delta: {text, tone}, spark: [{y, basis}], from}` and
`spark.points = [{y, basis}]`. The text inside a tag is the no-JS fallback. The site's `plain/kpi.html` is this page,
and the browser checks load it.

- **Keys:** `kpi {label, value {property, summary?, per?}, compare {against, better, neutral}, spark {x, y, window},
  target (a number, or a property read from each card's newest row: CONTRACT §35's kpi_trend), gate {min, max}}`; Bases' `groupBy` (one card per group), `groupOrder`, `sort`, `filters`.
- **The number:** no `summary` = the producer's number, the newest row's cell (by `spark.x`) as written, with its
  basis badge and "computed from N runs" (the cell's `n`); a `summary` (Bases' names, or `Ratio` = Σvalue / Σper) =
  a view summary over the card's rows, badged derived. A missing value is "—" with its `why`.
- **The delta:** against `previous` (the reading before, or with `spark.window` the window before), `target`, or a
  property of the newest row; neutral inside the relative `neutral` band, else good or bad by `better`, never by the
  sign (`--data-good` / `--data-bad`, calm grey by default). `better` is `higher`, `lower`, or a property whose newest
  value (higher | lower) sets each card's direction (`better: better` in the Vibe Tracks case), so one view holds KPIs
  that point both ways. A card with no direction draws its delta neutral.
- **The history:** a sparkline per card (SVG, no engine; a reading not taken lifts the pen; hollow marks for
  estimate, stand-in, assumed, claimed). The first card is the headline when the order is the author's (one card, or a
  `groupOrder`): bigger, and its history is drawn by the chart view (bare), so the page loads one chart engine. In
  summary mode each x is one point, the card's summary over the rows at that x.
- **Click** a card (or Enter): the host's peek with the rows behind it.
- **Stock:** none; ours, after Evidence's BigValue vocabulary and Vibe Tracks' tiles.

## The look (docs/peps/0005-dashboard-cards.md §2)

- **Card:** the label muted (12.5px) on top; the number big in tabular figures, sized by the card's own width
  (`clamp(20px, 12cqi, 44px)`, a container query, so it shrinks with its card and never overflows); the unit muted beside
  it; the delta a small pill whose **▲ / ▼ is always drawn with its colour** (the arrow is a `::before` keyed by
  `data-dir`, so `.dv-kpi-delta`'s text stays the producer's words); the sparkline the card's full width; the footer
  muted (11.5px). Inside a `<data-dashboard>` the card has no box of its own (the dashboard draws the surface); on a
  plain page it keeps its border, and the number stays 22px.
- **Numbers:** `input.view.style.numbers` (`{digits, compact}`) is the default for every number a stat card prints, under
  the property's own `digits` / `compact` and a card's `format:`; the stored value stays in a `title` (`data-exact` on a
  KPI). A computed number (a summary, a delta, a quotient) defaults to 4 (3 for a delta) significant figures.
- **Tones:** `good` / `bad` are `--data-good` / `--data-bad`; where a host sets neither, the stat cards use a quiet green
  and red (`--dv-tone-good` / `-bad`), and `warn` is `--data-warn` over an amber (`--dv-tone-warn`). A host's own
  colours win. `muted` and `neutral` are greys from `--dv-muted`.
- **Click** on any stat card is `host.open(row, {records, title})`: the dashboard's peek, or a selection when the panel
  has `select:`.

## gauge

```yaml
- type: gauge
  gauge:
    value: { property: passed_runs, summary: Ratio, per: judged_runs }   # or a property name; no summary = the newest row's cell
    min: 0                  # a number or a property; 0 by default
    max: 1                  # a number or a property; none = the next tidy number above value and target
    target: 0.9
    shape: arc              # bar (default) | arc
    better: higher          # which side of the target is good
    label: Judged runs passing, last 21 days
    bands: [{ to: 0.5, tone: bad }, { to: 0.9, tone: warn }, { tone: good }]
```

The fill wears the tone of the band the value is in; with no bands it is good or bad by the target; with neither, the
accent. "▼ 0.651 under target" says which side. The bar's fill is a width of its track, the arc's fill a path of the
same circle as its track (`getTotalLength()` ratio = the value's fraction); the target is a tick at its fraction.

## bullet

```yaml
- type: bullet
  bullet: { value: { property: stop_p90 }, target: 5, max: 60, label: title, better: lower, bands: [5, 20, 60] }
```

One row per record (or per group with `groupBy`, its value summarised when `value.summary` is set): the label, then a
track of 2-3 grey bands (the worst darkest), the value bar and the target tick, then the value. One scale (0 to `max`)
for every row, so the bars compare; a value past `max` fills the track and is marked (`data-clipped`, a chevron), never
drawn longer than the track.

## barlist

```yaml
- type: barlist
  barlist: { label: track_title, value: { property: runs, summary: Sum }, limit: 8, better: higher }
```

One row per label (rows that share a label are one entry: summarised when `value.summary` is set, else the newest
row's cell); ordered largest first (smallest first when `better: lower`); bar width = value / max over all entries (a
`limit` never rescales the bars), drawn as a light fill behind the label; the rest are one "+N more" line that opens
them. No minimum bar width: a tiny value is a nearly invisible bar and a true number beside it.

## status

```yaml
- type: tracker
  groupBy: { property: track_title }
  sort: [{ property: day, direction: ASC }]
  tracker: { state: verdict, label: day, tones: { pass: good, mixed: warn, fail: bad, none: muted } }
```

With `groupBy`, one tracker row per group (its name on the left), one block per row in the view's sort order; without,
one row. A block's hover reads "<label> · <state>"; a legend names the states present. A missing state is `muted`, a
state the `tones` map does not list is `neutral`. The classes are `dv-tracker-*` because `<data-views>` already owns
`.dv-status`.

The arithmetic (scales, bands, the arc path, the bar list's order and widths, tones) is `src/stat-model.js`, pure and
tested by `tests/unit/stat.test.mjs`; the drawing is measured by `gallery/examples/dashboard-cards/checks_stat.py`.
