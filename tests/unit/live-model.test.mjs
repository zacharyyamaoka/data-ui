// The incremental live model equals the full one (docs/peps/0012-live-data.md §5.2). A Tail keeps a flat,
// time-ordered view's rows up to date from what arrived and what was dropped; rowModel() over the same snapshot is the
// oracle, for random appends (several streams, equal times), retention drops, windows, filters, search, both sort
// directions, a limit, and t moving forward, back and live. Committed before the code (lane/live, Step 2).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LiveDataset, setLiveBudget } from '../../packages/core/src/live/store.js';
import { Tail, snapshotModel } from '../../packages/core/src/live/model.js';
import { flushLive } from '../../packages/core/src/live/frame.js';
import { rowModel, properties as labelled, search } from '../../packages/core/src/rowmodel.js';
import { compileFilters } from '../../packages/core/src/grammar.js';

const props = { t: { type: 'number' }, src: { type: 'text' }, level: { type: 'text' }, msg: { type: 'text' }, v: { type: 'number' } };
const LEVELS = ['info', 'warn', 'error'];

// a small seeded generator, so a failure replays
function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32); }

/** The oracle: every retained row at or before t in the window, newest first (time, then arrival), through the
    filters and the search, the newest `cap` (the view's limit, else the given cap), put back in time order (the
    dataset's own order, oldest first); then rowModel() exactly as <data-views> would run it. */
function oracle(ds, base, view, { t, at, cap, query, filters }) {
  const all = ds.snapshot(t, { at, limit: Infinity });
  const columns = labelled({ properties: ds.properties, rows: all }, base);
  let rows = all;
  for (const f of [filters, view.filters]) { const keep = compileFilters(f); if (keep) rows = rows.filter(keep); }
  rows = search(rows, columns, view, query).slice(0, view.limit || cap).reverse();
  const m = rowModel({ id: ds.id, properties: ds.properties, rows }, base, view, { query, filters });
  return m.rows.map((r) => r.id);
}

const VIEWS = {
  plain: { type: 'table', name: 'plain' },
  newest: { type: 'table', name: 'newest', sort: [{ property: 't', direction: 'DESC' }] },
  oldest: { type: 'table', name: 'oldest', sort: [{ property: 't', direction: 'ASC' }] },
  errors: { type: 'table', name: 'errors', filters: 'level == "error"', sort: [{ property: 't', direction: 'DESC' }] },
  limited: { type: 'table', name: 'limited', limit: 25 },
  oldestLimited: { type: 'table', name: 'oldestLimited', limit: 25, sort: [{ property: 't', direction: 'ASC' }] },
};

for (const [name, view] of Object.entries(VIEWS)) {
  for (const at of ['all', 3]) {
    test(`Tail equals rowModel over the snapshot: ${name}, at ${at}`, () => {
      setLiveBudget(1e12);
      const r = rng(name.length * 97 + (at === 'all' ? 1 : 2));
      const ds = new LiveDataset({ properties: props, time: 't', stream: 'src', retention: { bytes: 400_000 } });
      const base = { properties: {} };
      const cap = 120;
      const opts = { at, cap, query: '', filters: undefined };
      const tail = new Tail(ds, base, view, opts);
      assert.ok(Tail.fits(ds, base, view), 'a flat, time-ordered view fits the incremental path');
      let clock = 1000, t = clock, following = true, seq = 0;
      for (let step = 0; step < 160; step++) {
        // arrivals: 0-60 rows over 1-3 streams, times non-decreasing per stream, sometimes equal
        const n = Math.floor(r() * 60);
        const rows = [];
        for (let i = 0; i < n; i++) {
          if (r() < 0.8) clock += r() * 0.05;
          rows.push({ t: clock, src: `s${Math.floor(r() * 3)}`, level: LEVELS[Math.floor(r() * 3)], msg: `m${seq++} ${r() < 0.1 ? 'needle' : ''}`, v: r() });
        }
        ds.append(rows);
        flushLive();
        // the clock: mostly live, sometimes a seek back, sometimes forward again, sometimes the search changes
        const p = r();
        if (p < 0.08) { following = false; t = ds.start + (ds.end - ds.start) * r(); }
        else if (p < 0.12) { following = true; }
        else if (p < 0.16 && !following) { t = Math.min(ds.end, t + r()); }
        else if (p < 0.19) { opts.query = opts.query ? '' : 'needle'; tail.setQuery(opts.query); }
        if (following) t = ds.end;
        tail.sync(t);
        const want = oracle(ds, base, view, { t, ...opts });
        const got = tail.model().rows.map((row) => row.id);
        assert.deepEqual(got, want, `step ${step}: t=${t} following=${following} query=${opts.query}`);
      }
      assert.ok(tail.stats.incremental > tail.stats.full, `mostly incremental: ${JSON.stringify(tail.stats)}`);
    });
  }
}

test('Tail.fits: grouped, tree, pivot, rolled-up or sorted by another property go the full way', () => {
  const ds = new LiveDataset({ properties: props, time: 't', stream: 'src' });
  const base = {};
  assert.equal(Tail.fits(ds, base, { type: 'table', groupBy: { property: 'src' } }), false);
  assert.equal(Tail.fits(ds, base, { type: 'table', tree: { parent: 'src' } }), false);
  assert.equal(Tail.fits(ds, base, { type: 'pivot', splitBy: ['src'] }), false);
  assert.equal(Tail.fits(ds, base, { type: 'table', rollup: { keep: ['src'] } }), false);
  assert.equal(Tail.fits(ds, base, { type: 'table', sort: [{ property: 'v', direction: 'ASC' }] }), false);
  assert.equal(Tail.fits(ds, base, { type: 'table', sort: [{ property: 't', direction: 'DESC' }, { property: 'v' }] }), false);
  const keyed = new LiveDataset({ properties: props, time: 't', key: 'src' });
  assert.equal(Tail.fits(keyed, base, { type: 'table' }), false, 'a keyed dataset is a snapshot of records, not a tail');
});

test('snapshotModel: the full path is rowModel() over the capped snapshot, for any view', () => {
  const ds = new LiveDataset({ properties: props, time: 't', stream: 'src' });
  const rows = [];
  for (let i = 0; i < 500; i++) rows.push({ t: 10 + i * 0.01, src: `s${i % 4}`, level: LEVELS[i % 3], msg: `m${i}`, v: (i * 7919) % 100 });
  ds.append(rows);
  const view = { type: 'table', groupBy: { property: 'src', direction: 'ASC' }, sort: [{ property: 'v', direction: 'DESC' }] };
  const m = snapshotModel(ds, {}, view, { t: 12, at: 'all', cap: 100 });
  // the snapshot is the newest 100 rows at t, in time order (oldest first), as a static file would be
  const want = rowModel({ properties: props, rows: ds.snapshot(12, { at: 'all', limit: 100 }).reverse() }, {}, view);
  assert.deepEqual(m.rows.map((r) => r.id), want.rows.map((r) => r.id));
  assert.deepEqual(m.groups.map((g) => g.key), want.groups.map((g) => g.key));
  assert.equal(m.total, ds.snapshot(12, { at: 'all', limit: Infinity }).length, 'total: every retained row at t');
});

test('the Tail model is what a flat table needs: rows in order and a TanStack table built over them', () => {
  const ds = new LiveDataset({ properties: props, time: 't', stream: 'src' });
  ds.append([{ t: 1, src: 'a', level: 'info', msg: 'x', v: 1 }, { t: 2, src: 'b', level: 'warn', msg: 'y', v: 2 }]);
  flushLive();
  const tail = new Tail(ds, {}, { type: 'table' }, { at: 'all', cap: 10 });
  tail.sync(2);
  const m = tail.model();
  assert.deepEqual(m.rows.map((r) => r.t), [1, 2], 'time order, as the rows came: a view sorts them newest first with sort:');
  assert.equal(m.groups, null);
  assert.equal(m.pivot, null);
  assert.equal(typeof m.table.setExpanded, 'function');
  assert.ok(m.columns.t && m.columns.level);
  assert.equal(m.total, 2);
  assert.equal(m.matched, 2);
});
