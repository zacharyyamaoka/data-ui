/* A live view's rows (docs/peps/0012-live-data.md §5.2): the newest rows at t that pass its filters and search, at most
   its `limit` (else 2,000), in time order, then its own sort.

   Two ways to get them, held equal by tests/unit/live-model.test.mjs (rowModel() over the same snapshot is the oracle):
     snapshotModel  any view: the snapshot read from the store, then rowModel(). The full way; a <data-views> runs it
                    for a grouped, tree, pivot or rolled-up view at most every 250 ms (live/feed.js).
     Tail           a flat view sorted by time (or not sorted) on an append dataset: what arrived is filtered once and
                    put in order at the newest end, what fell out of the window or the cap leaves the other end, a
                    dropped chunk's rows leave by their arrival numbers. O(new rows) a frame instead of O(rows): a full
                    rowModel() sorted by time costs 22 ms at 8,000 rows (Node, this lane), a frame has 16.7.
   WHY time order and not newest first: a file's rows are in time order, and the views read them so (the KPI's newest
   row is the last); a log that wants the newest on top says sort: t DESC, as Bases would. */

import { rowModel, properties as labelled, search, tableModel } from '../rowmodel.js';
import { compileFilters } from '../grammar.js';

export const LIVE_CAP = 2000;

/** The filters, the view's own filters and the search as one test on a row; errors as rowModel() reports them. */
function keeper(ds, base, view, { query = '', filters } = {}) {
  const columns = labelled({ properties: ds.properties }, base);
  const tests = [], errors = [];
  for (const f of [filters !== undefined ? filters : base && base.filters, view.filters]) {
    try { const k = compileFilters(f); if (k) tests.push(k); } catch (err) { errors.push(err.message); }
  }
  const q = String(query || '').trim();
  const keep = (r) => {
    for (const k of tests) if (!k(r)) return false;
    return !q || search([r], columns, view, q).length === 1;
  };
  return { keep, columns, error: errors.join('; ') || null };
}

/** The full way: the snapshot at t (time order) through rowModel(). `total` is every retained row at t. */
export function snapshotModel(ds, base, view, { t, at = 'all', cap = LIVE_CAP, query = '', filters } = {}) {
  const { keep } = keeper(ds, base, view, { query, filters });
  let rows = ds.snapshot(t, { at, limit: view.limit || cap, filter: keep });
  if (ds.keyed) {
    // a keyed table keeps its records where they first appeared, so an update never moves a row (its own sort may)
    const order = new Map(ds.streams().map((k, i) => [k, i]));
    rows = rows.sort((a, b) => order.get(String(a[ds.key])) - order.get(String(b[ds.key])));
  } else rows = rows.reverse();
  const m = rowModel({ id: ds.id, title: ds.title, titleProperty: ds.titleProperty, properties: ds.properties, rows }, base, view, { query, filters });
  m.total = ds.countAt(t, at);
  // the store's rows it read at t (a rolled-up or pivoted view's own rows are made): a paused view checks what
  // retention took against them (live/feed.js pausedNews); not enumerable, so nothing that copies a model carries it
  Object.defineProperty(m, 'read', { value: rows, enumerable: false });
  return m;
}

const cmp = (time) => (a, b) => a[time] - b[time] || a._seq - b._seq;

/** The incremental way, for a flat view sorted by time (or not sorted) on an append dataset. */
export class Tail {
  /** Whether a view can take the incremental way. */
  static fits(ds, base, view) {
    if (!ds || ds.keyed || !view) return false;
    if (view.type === 'pivot' || view.groupBy || view.subGroupBy || view.tree || view.rollup) return false;
    const sort = (view.sort || []).filter(Boolean);
    if (sort.length > 1) return false;
    if (sort.length === 1 && sort[0].property !== ds.time) return false;
    return true;
  }

  constructor(ds, base, view, { at = 'all', cap = LIVE_CAP, query = '', filters } = {}) {
    this.ds = ds;
    this.base = base;
    this.view = view;
    this.at = at;
    this.cap = view.limit || cap;
    this.query = query;
    this.filters = filters;
    this.rows = [];             // the newest `cap` kept rows at t, in time order
    this.t = null;
    this.stats = { incremental: 0, full: 0 };
    this._compile();
  }

  setQuery(q) { if ((q || '') !== this.query) { this.query = q || ''; this._compile(); this.t = null; } }
  setFilters(f) { if (JSON.stringify(f ?? null) !== JSON.stringify(this.filters ?? null)) { this.filters = f; this._compile(); this.t = null; } }

  _compile() {
    const k = keeper(this.ds, this.base, this.view, { query: this.query, filters: this.filters });
    this.keep = k.keep;
    this.columns = k.columns;
    this.error = k.error;
  }

  /** Bring the rows to t. Returns whether they changed. */
  sync(t) {
    const ds = this.ds;
    // WHY these rebuild: back in time, rows after t leave and older ones may enter the cap; forward from a t that had
    // rows after it, those rows arrived before the last sync and are not "new". At the same t, or forward from a
    // complete t (following), what arrived since the last sync is exactly what is new.
    if (this.at === 'latest' || this.t === null || t < this.t || (t > this.t && !this._complete) || ds.resets !== this._resets) return this._full(t);
    const drops = ds.dropsSince(this._dropGen);
    if (drops === null) return this._full(t);
    // WHY: newRows() reads each stream back from its end and stops at the first row already read, so a row that went in
    // before rows this tail has read (an out-of-order arrival) is not in it; the rows at t are read again. Rare: a
    // stream's rows come in time order. One placed after t does not matter yet (a forward move from an incomplete t
    // rebuilds anyway)
    const ro = ds.reordersSince(this._roGen);
    if (ro === null || ro.some((x) => x.t <= t)) return this._full(t);
    this._roGen = ds.reorderGen;
    let changed = false;
    const time = ds.time, sp = ds.stream;
    const wasFull = this.rows.length >= this.cap;
    if (drops.length) {
      const gone = (r) => drops.some((d) => (!sp || r[sp] === d.stream) && r._seq >= d.seqMin && r._seq <= d.seqMax);
      const before = this.rows.length;
      this.rows = this.rows.filter((r) => !gone(r));
      if (this.rows.length !== before) {
        changed = true;
        // WHY a rebuild: rows the cap had pushed out may belong in the newest `cap` again
        if (wasFull) return this._full(t);
      }
    }
    this._dropGen = ds.dropGen;
    // what arrived since the last sync, at or before t, through the filters, put in time order at the newest end
    const fresh = ds.newRows(this._seq, t).filter(this.keep);
    this._seq = ds.seq;
    if (fresh.length) {
      changed = true;
      const order = cmp(time);
      for (const r of fresh) {
        let i = this.rows.length;
        while (i > 0 && order(this.rows[i - 1], r) > 0) i--;
        if (i === this.rows.length) this.rows.push(r); else this.rows.splice(i, 0, r);
      }
      if (this.rows.length > this.cap) this.rows.splice(0, this.rows.length - this.cap);
    }
    // the window ending at t: rows at or before t − window leave the old end
    const w = this._window();
    if (w !== null) {
      let k = 0;
      while (k < this.rows.length && this.rows[k][time] <= t - w) k++;
      if (k) { this.rows.splice(0, k); changed = true; }
    }
    this._complete = ds.end === null || t >= ds.end;
    if (t !== this.t) changed = true;
    this.t = t;
    this.stats.incremental++;
    return changed;
  }

  _window() { return this.at === 'all' || this.at === 'latest' ? null : (typeof this.at === 'number' ? this.at : parseFloat(this.at) * ({ ms: 0.001, s: 1, m: 60, h: 3600 }[String(this.at).replace(/^[\d.]+\s*/, '')] || 1)); }

  _full(t) {
    const ds = this.ds;
    this.rows = ds.snapshot(t, { at: this.at, limit: this.cap, filter: this.keep }).reverse();
    this._seq = ds.seq;
    this._dropGen = ds.dropGen;
    this._roGen = ds.reorderGen;
    this._resets = ds.resets;
    // complete: no retained row lies after t, so everything that arrives later is new to us
    this._complete = ds.end === null || t >= ds.end;
    this.t = t;
    this.stats.full++;
    return true;
  }

  /** rowModel()'s shape for these rows: the view's sort (by time) and limit, a TanStack table built over rows already
      in order (a flat table never asks it for a row model), `total` every retained row at t. */
  model() {
    const ds = this.ds, time = ds.time, view = this.view;
    let rows = this.rows;
    const sort = (view.sort || []).filter(Boolean)[0];
    if (sort && sort.direction === 'DESC') {
      // TanStack's sort is stable: newest first, rows with equal times in their arrival order
      rows = rows.slice().sort((a, b) => b[time] - a[time] || a._seq - b._seq);
    }
    if (view.limit) rows = rows.slice(0, view.limit);
    // the columns again: a dataset's properties may change (its time column learns display: clock from the data)
    const columns = labelled({ properties: ds.properties }, this.base);
    const table = tableModel(rows, columns, { ...view, sort: [] });
    return { rows, groups: null, total: ds.countAt(this.t ?? Infinity, this.at), matched: this.rows.length, error: this.error, columns, table, pivot: null, rolled: null };
  }
}
