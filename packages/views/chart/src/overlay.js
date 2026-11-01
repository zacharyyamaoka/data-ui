/* What the time series and trajectory cards draw over Vega's canvas (docs/peps/0005-dashboard-cards.md §4): the
   playhead, the crosshair and the markers are positioned DOM, placed through Vega's own scales.

   WHY not a Vega signal: a clock tick would re-run the dataflow of every card 60 times a second; the scales are
   already computed, so a tick is a transform on one element (the brief: never re-run Vega per tick). */

/** The plot rectangle in the overlay's px (the element that holds the canvas): where Vega's renderer puts the plot
    (padding + origin, as vega-view's own offset(); view.origin() alone leaves the padding out, 2026-10-26: markers
    sat 2 px left and 8 px high of their paths) plus where the canvas sits in that element. Measured after each Vega
    run, never per tick. */
export function plotBox(view, holder) {
  const canvas = holder.querySelector('canvas');
  if (!view || !canvas) return null;
  const a = holder.getBoundingClientRect(), c = canvas.getBoundingClientRect();
  const o = view.origin(), p = view.padding();
  // WHY a guarded y: a chart on the clock may have no y scale at all (a state strip); view.scale throws for a name it lacks
  let sy = null;
  try { sy = view.scale('y'); } catch { sy = null; }
  return { x: c.left - a.left + p.left + o[0], y: c.top - a.top + p.top + o[1], w: view.width(), h: view.height(), sx: view.scale('x'), sy };
}

/** A time axis' y gutter and padding (kit gap 3, CONTRACT §25 addendum): the time series card and a chart whose x is a
    time in seconds keep at least GUTTER px for their y labels (Grafana's fixed axis width), so in a dashboard column
    every one puts the same t at the same x. A label wider than the gutter widens it, never clips. */
export const GUTTER = 44;
export const TIME_PAD = { left: 2, right: 10, top: 8, bottom: 2 };

/** A column's unit text: `unitText` (a Table Schema field's unit), else a runtime property's own `unit`. */
export function unitOf(col) {
  return (col && (col.unitText || (typeof col.unit === 'string' ? col.unit : ''))) || '';
}

/** A tone (good | warn | bad | muted | neutral) as a token colour. */
export function toneColor(tone, t) {
  return { good: t.good, warn: t.warn, bad: t.bad, neutral: t.fg, muted: t.muted }[tone] || t.muted;
}

/** Axis labels as compact numbers: 1.5k past a thousand, otherwise the shortest exact form (Vega expression). */
export const COMPACT = "abs(datum.value) >= 1000 ? format(datum.value, '.3~s') : format(datum.value, '~r')";
