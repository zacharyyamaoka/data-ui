/* The pure parts of the interactive time series (timeseries.interactive: true, src/plot.js): which wheel gesture does
   what, pan and zoom arithmetic on a scale's own distribution (linear, log, symlog), the legend's hide / isolate rule
   (the core's, re-exported) and the help popover's list. No DOM and no uPlot, so tests/unit/plot.test.mjs runs them in Node as they are. */

// WHY Rerun's list, word for word where it fits: Zach (2026-10-26) pointed at Rerun's "?" popover as the reference;
// a reader who knows Rerun's or Foxglove's plot already knows this one
export const CONTROLS = [
  ['Pan', 'Drag'],
  ['Horizontal pan', 'Shift + wheel'],
  ['Zoom', 'Ctrl + wheel'],
  ['Zoom X-axis', 'Ctrl + Shift + wheel'],
  ['Zoom Y-axis', 'Ctrl + Alt + wheel'],
  ['Zoom to selection', 'Right-drag or Shift + drag'],
  ['Move time cursor', 'Click'],
  ['Reset view', 'Double-click'],
  ['Hide/show series', 'Click legend'],
  ['Hide/show other series', 'Alt + click legend'],
];

/** What a wheel event does, from its modifiers (Cmd counts as Ctrl, as on a Mac): 'pan-x', 'zoom', 'zoom-x', 'zoom-y',
    or null for a plain wheel, which stays the page's scroll. */
export function wheelAction({ ctrlKey = false, metaKey = false, shiftKey = false, altKey = false } = {}) {
  const ctrl = ctrlKey || metaKey;
  if (ctrl && shiftKey && !altKey) return 'zoom-x';
  if (ctrl && altKey && !shiftKey) return 'zoom-y';
  if (ctrl && !shiftKey && !altKey) return 'zoom';
  if (shiftKey && !ctrl && !altKey) return 'pan-x';
  return null;
}

/** A wheel event's travel in px, whichever axis carries it (Chrome on Linux and Windows turns Shift + wheel into deltaX);
    lines and pages are converted as browsers scroll them. */
export function wheelDelta({ deltaX = 0, deltaY = 0, deltaMode = 0 } = {}) {
  const d = Math.abs(deltaY) >= Math.abs(deltaX) ? deltaY : deltaX;
  return d * (deltaMode === 1 ? 16 : deltaMode === 2 ? 400 : 1);
}

/** Zoom factor for a wheel travel: 100 px of wheel scales the span by e^0.2 (out for a positive travel). */
export function zoomFactor(delta) {
  return Math.exp(Math.max(-1, Math.min(1, delta * 0.002)));
}

// a scale's distribution as uPlot names it: 1 linear, 3 log10, 4 asinh (symlog); x on a time axis is linear
const FWD = { 1: (v) => v, 3: (v) => Math.log10(v), 4: (v) => Math.asinh(v) };
const INV = { 1: (v) => v, 3: (v) => 10 ** v, 4: (v) => Math.sinh(v) };
const fwd = (distr) => FWD[distr] || FWD[1];
const inv = (distr) => INV[distr] || INV[1];

/** [min, max] zoomed by `factor` (< 1 in, > 1 out) about `anchor`, in the scale's own distribution, so the value under
    the pointer stays under it. */
export function zoomRange([min, max], anchor, factor, distr = 1) {
  const f = fwd(distr), g = inv(distr);
  const a = f(anchor), lo = f(min), hi = f(max);
  return [g(a - (a - lo) * factor), g(a + (hi - a) * factor)];
}

/** [min, max] moved by `frac` of its span (positive: towards larger values), in the scale's own distribution. */
export function panRange([min, max], frac, distr = 1) {
  const f = fwd(distr), g = inv(distr);
  const lo = f(min), hi = f(max), d = (hi - lo) * frac;
  return [g(lo + d), g(hi + d)];
}

/** The value at a fraction `frac` (0..1) along [min, max] in the scale's distribution (a px over the plot's width). */
export function valueAt([min, max], frac, distr = 1) {
  const f = fwd(distr), g = inv(distr);
  return g(f(min) + (f(max) - f(min)) * frac);
}

// The legend's rule (Rerun's) is the core's, one rule for every chart's legend (packages/core/src/legend.js); re-exported
// here so this module's callers and tests keep their import. WHY a path, not '@data-ui/core': this file runs in Node as
// it is (tests/unit/plot.test.mjs), and the build maps any core path to the page's one core (build.mjs coreExternal)
export { legendClick } from '../../../core/src/legend.js';

/** Each series' samples as a uPlot table [xs, ys] (sorted by x, as series.js leaves them); uPlot.join aligns the tables
    on the union of their x, an x a series lacks being an alignment gap the line spans (longRows already dropped every
    missing value, so no real gap is lost; the simple time series connects them the same way). */
export function tablesOf(series) {
  return series.map((s) => [Float64Array.from(s.points, (p) => p.x), s.points.map((p) => p.value)]);
}

/** Two ranges are the same view within a millionth of their span (a pan echoed back through the clock is not a change). */
export function sameRange(a, b) {
  if (!a || !b) return a === b;
  const tol = 1e-6 * Math.max(Math.abs(a[1] - a[0]), Math.abs(b[1] - b[0]), 1e-12);
  return Math.abs(a[0] - b[0]) <= tol && Math.abs(a[1] - b[1]) <= tol;
}
