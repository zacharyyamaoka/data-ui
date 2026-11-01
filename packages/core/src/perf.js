/* Named milestones in the browser's own timeline (User Timing), so a bench, DevTools' Performance panel or a host's
   PerformanceObserver can see when rows were first drawn without patching the kit. bench/README.md lists them:

     mark    data-ui:data          a <data-views>' data has been fetched and parsed     detail {id}
     mark    data-ui:start         its toolbar, status line and stage are in the DOM    detail {id}
     mark    data-ui:first-render  its first view has drawn (before the browser paints) detail {id, type, rows}
     measure data-ui:model         one row-model build (filter, search, sort, group)  detail {id, type, rows}
     measure data-ui:render        model + toolbar + the view's update(), per render   detail {id, type, rows}
     measure data-ui:rail          one <data-facets> count-and-draw pass               detail {id, facets}

   WHY tiny and guarded: this runs on every render of every page that uses the kit. A browser without User Timing
   (or with a detail it cannot clone) skips the entry; it never throws into a render. WHY the clear: the timeline keeps
   every measure until cleared, so a long session would grow it without bound; observers already received each one. */

const NAMES = ['data-ui:model', 'data-ui:render', 'data-ui:rail'];
const KEEP = 500;
let count = 0;

const ok = () => typeof performance !== 'undefined' && typeof performance.mark === 'function';

export function mark(name, detail) {
  if (!ok()) return;
  try { performance.mark(name, { detail }); } catch { /* User Timing is a nicety: never break a render */ }
}

/** A measure from `start` (a performance.now() value) to now. */
export function measure(name, start, detail) {
  if (!ok() || typeof performance.measure !== 'function') return;
  try { performance.measure(name, { start, end: performance.now(), detail }); } catch { /* as above */ }
  if (++count % KEEP === 0) for (const n of NAMES) { try { performance.clearMeasures(n); } catch { /* as above */ } }
}

export const PERF_NAMES = { marks: ['data-ui:data', 'data-ui:start', 'data-ui:first-render'], measures: NAMES, keep: KEEP };
