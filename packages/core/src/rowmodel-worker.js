/* The row model off the main thread, for 10k-100k+ rows (review 2026-10-26 item 10). Built as a prototype on
   lane/perf-views; wired into <data-views> on lane/perf-worker (below: how it is used).

   WHY this shape, measured (lane/perf-views, 2026-10-26, 100,000 synthetic actuators, Node 22):
     rowModel() on the main thread                         4.4-6.9 s   (TanStack's sorted row model is nearly all of it)
     the same TanStack table over rows already in order    0.15-0.33 s (no sort to do)
   So the worker runs the real rowModel() (the same code, so the same answer by construction, and perf-core's
   speed-ups arrive in both places at once) and sends back only ORDER: Uint32Array indices into dataset.rows, plus
   the groups as index lists. The main thread then builds the table the views read (input.table) over the rows in that
   order with no sort state, which yields the same rows, groups, group rows and leaf order (tests/unit/
   rowmodel-worker.test.mjs is the oracle: every view of a matrix, against rowModel()).

   Why not TanStack 9.3.1's experimental worker row models (@tanstack/table-core/experimental-worker-plugin), read
   first as the review asked: their documented constraints do not fit data-ui's model.
     - Columns and fns are fixed when the worker starts (initTableWorker(config)) and must be closure-free;
       data-ui's sortFn closes over the view (groupOrder's rank of a named group), so each view would need a new
       worker and a new copy of the data.
     - Only TanStack's own stages run there (filtered -> grouped -> sorted -> expanded); data-ui filters with the
       Bases grammar and searches before TanStack, so every filter or keystroke would post a new data array: the
       per-interaction clone this is meant to remove.
     - Nothing terminates the worker ("nothing calls this automatically yet"); a host must. Here terminate() does.
   Its wire format is the same idea as this one (a transferable index permutation for flat results).

   Opt-in by size: below WORKER_ROWS rows, or for a pivot or a `tree:` view (whose order is per level), the host keeps
   the synchronous rowModel().

   HOW <data-views> USES IT (lane/perf-worker, 2026-10-26; elements/data-views.js, "the row-model worker"):
     made          once the first rows are on screen (a frame, then a task), for data of WORKER_ROWS rows or more. The
                   data goes over as the very response bytes the page fetched (recordingFetch, transferred, parsed
                   there), or, for data a host set from script, cloned in slices of 2,000 rows, one task each.
     _render()     model reuse first (presentation-only renders never ask); then, when the worker holds this data at this
                   revision and the view is workerEligible(), the model is asked for and the previous rows stay on
                   screen until it lands (stale-while-revalidate); a newer render supersedes it (it draws nothing).
                   Until the worker is ready, the model is built synchronously, as before.
     edits         propose/acceptEdit post the changed row (w.edit) with the new dataRevision before the next model, so
                   the worker never answers from a stale row; a row it cannot place retires the worker.
     removed       disconnectedCallback() terminates it; connectedCallback() makes a new one.
     the first     model of a page is built on the main thread: the worker cannot hold the rows before the page has
                   parsed them (it was ready ~0.7 s after the first rows at 100k), so asking it would put the first
                   rows later. It is built from order.js' typed-array keys and modelFromOrder(), not rowModel()
                   (DataViews._modelHere): the same rows, ~0.3-0.5 s sooner at 100k.
     the worker    answers with order.js' fastOrder() (ranks cached per copy of the data, reset by an edit), falling
                   back to orderOf() for what it does not model.

   MEASURED in Chromium (pinned to 8 cores, 100,000 rows, real Worker, lane/perf-views 2026-10-26):
     main thread per model    sync 2,978-3,535 ms   ->  worker: 17-24 ms worst frame gap while it runs, then
                              174-372 ms rebuilding TanStack's rows from the order (lazy, on the view's first read)
     wall time per model      unchanged (3.0-3.8 s): the worker runs the same TanStack sort
     main heap, grouped model 89.4 MB sync, 87.3 MB worker (the worker holds a second copy of the rows)
   With perf-core's collator (f0d980f) the 100k sync model falls to ~0.6 s (Node), so the worker's main-thread
   saving at 100k becomes ~0.6 s -> ~0.2 s; first paint gains nothing from a worker alone (the rows still wait for
   the sort), which is what a sort over precomputed column ranks (typed arrays) inside the worker would address. */

import { rowModel, tableModel, properties, treeSpec } from './rowmodel.js';
import { timeGrain, binsOf, viewPath } from './grammar.js';
import { loadDataset } from './data.js';
import { railInputs, railCounts } from './facets.js';
import { fastOrder, rankCache } from './order.js';

/** At or above this many dataset rows a host may use the worker; below it the synchronous model is fast enough
    (1,149 actuators: ~25 ms) and a round trip would only add latency. */
export const WORKER_ROWS = 5000;

/** Whether a view's model may come from the worker: flat and grouped tables, lists, cards, charts; not a pivot (its
    rows are synthetic) and not a `tree:` view (TanStack sorts each level of a tree on its own). */
export function workerEligible(dataset, view, props) {
  if (!dataset || !dataset.rows || dataset.rows.length < WORKER_ROWS) return false;
  if (!view || view.type === 'pivot') return false;
  // WHY not a rollup or a time level (lane/models-views, f554bce): a rollup's rows are made, not the dataset's, and a
  // time level groups by a bucket the rebuilt table (modelFromOrder) would not know
  if (view.rollup || timeGrain(view.groupBy) || timeGrain(view.subGroupBy)) return false;
  // WHY not the grouped gallery's levels (CONTRACT §20): `grouping:` swaps in a `groupings:` entry's levels and `bins`
  // groups numbers by bucket, and the worker and order.js's fast path build groups from the view's own groupBy with
  // neither; such a view is built by rowModel() (tests/unit/worker-eligible-collection.test.mjs)
  if (view.grouping || (Array.isArray(view.groupings) && view.groupings.length) || binsOf(view.groupBy) || binsOf(view.subGroupBy) || viewPath(view, view.groupBy) || viewPath(view, view.subGroupBy)) return false;
  return !treeSpec(view, props || properties(dataset, null));
}

/**
 * The worker's half, pure (it runs in Node for the oracle): the model's ORDER as indices into dataset.rows.
 *   {rows: Uint32Array (after limit), table: Uint32Array (every matched row, the table's leaf order),
 *    groups: [{key, property, rows: Uint32Array, groups?}] | null, total, matched, error}
 * `indexOf` is the worker's Map(row -> index), made once per dataset.
 */
export function orderOf(dataset, base, view, opts, indexOf) {
  const m = rowModel(dataset, base, view, opts);
  const idx = (list) => { const out = new Uint32Array(list.length); for (let i = 0; i < list.length; i++) out[i] = indexOf.get(list[i]); return out; };
  const leaves = [];
  for (const r of m.table.getRowModel().rows) if (!r.getIsGrouped()) leaves.push(r.original);
  const groups = (gs) => gs && gs.map((g) => ({ key: g.key, property: g.property, rows: idx(g.rows), ...(g.groups ? { groups: groups(g.groups) } : {}) }));
  return { rows: idx(m.rows), table: idx(leaves), groups: groups(m.groups), total: m.total, matched: m.matched, error: m.error };
}

/** The buffers in an orderOf() result, for postMessage's transfer list (they move, never copy). */
export function transferables(result) {
  const out = [result.rows.buffer, result.table.buffer];
  const walk = (gs) => { for (const g of gs || []) { out.push(g.rows.buffer); walk(g.groups); } };
  walk(result.groups);
  return [...new Set(out)]; // fastOrder's rows and table can be one array (no limit): a buffer is listed once
}

/**
 * The main thread's half: rowModel()'s shape from the worker's order, without sorting anything.
 * WHY no sort state is still the same table: the leaves arrive in the sorted model's leaf order, which is its groups
 * in their order, each group's rows in theirs; TanStack groups by first appearance, so with no sorting it rebuilds
 * the same groups in the same order. Group levels keep their property (the grouping), lose their direction (the sort).
 */
export function modelFromOrder(dataset, base, view, result) {
  const columns = properties(dataset, base);
  const all = dataset.rows;
  const pick = (ix) => { const out = new Array(ix.length); for (let i = 0; i < ix.length; i++) out[i] = all[ix[i]]; return out; };
  const level = (g) => (g ? { property: g.property } : undefined);
  const unsorted = { ...view, sort: [], groupBy: level(view.groupBy), subGroupBy: level(view.subGroupBy), groupOrder: undefined };
  const table = tableModel(pick(result.table), columns, unsorted);
  const groups = (gs) => gs && gs.map((g) => ({ key: g.key, property: g.property, rows: pick(g.rows), ...(g.groups ? { groups: groups(g.groups) } : {}) }));
  return { rows: pick(result.rows), groups: groups(result.groups), total: result.total, matched: result.matched, error: result.error, columns, table, pivot: null, rolled: null };
}


/**
 * The worker's side as a plain message handler, so Node runs the same protocol in tests (rowmodel.worker.js is only
 * `self.onmessage = workerServer(post)`). `post(message, transfer)` answers.
 *
 * Messages in:
 *   {type: 'data', dataset, rev}                           the dataset at once (structured clone)
 *   {type: 'begin', dataset, rev} {type: 'rows', rows}… {type: 'end'}
 *                                                          the same in slices: the dataset without its rows, then rows
 *   {type: 'load', url, bodies?, rev}                      load it here: from `bodies` (the main thread's own fetches,
 *                                                          replayed, so the very same bytes are parsed), else from url
 *   {type: 'row', index, row, rev}                         an edit: row `index` is now `row`
 *   {type: 'model', id, base, view, opts, rev}             a model's order (orderOf), or {stale: true} when this copy is
 *                                                          not at revision `rev`
 *   {type: 'counts', id, view, filters, specs, now, rev}   <data-facets>' counts: railCounts(railInputs(...)), the
 *                                                          same object the rail computes itself
 * Out: {type: 'ready', rows} once the data is in, {type: 'failed', error} if it could not be, {id, result} answers
 * (result null: superseded before it started), {id, error}, {id, stale: true}.
 * WHY a coalescing queue: a worker cannot stop a sort halfway, so while it is busy the requests pile up; when it is
 * free it answers only the newest and tells the older ones they were superseded.
 */
export function workerServer(post, { load = null } = {}) {
  let dataset = null;
  let indexOf = null;
  let ranks = null; // order.js' column ranks for this copy of the data, until an edit
  let rev = 0;
  let ready = null;
  let building = null; // the dataset arriving in slices
  let finish = null;
  const pending = { model: null, counts: null }; // the newest request of each kind not answered yet
  let scheduled = false;
  const use = (ds, r) => {
    dataset = ds;
    indexOf = new Map(ds.rows.map((row, i) => [row, i]));
    ranks = rankCache(ds);
    rev = r || 0;
    post({ type: 'ready', rows: ds.rows.length });
  };
  const fail = (err) => { post({ type: 'failed', error: String((err && err.message) || err) }); throw err; };
  const answer = (req) => {
    if (req.rev !== undefined && req.rev !== rev) { post({ id: req.id, stale: true }); return; }
    try {
      if (req.type === 'counts') {
        const { rows, rail, rest } = railInputs(dataset, req.view, req.filters, req.specs);
        post({ id: req.id, result: railCounts(rows, rail.facets, req.specs, rest, { now: new Date(req.now) }) });
        return;
      }
      // WHY fastOrder first: the same order from typed-array keys, with every column ranked once per copy of the data
      // (order.js; ~30-100 ms at 100k against ~0.9 s for TanStack's sort); what it does not model goes to orderOf
      const result = fastOrder(dataset, req.base, req.view, req.opts || {}, ranks) || orderOf(dataset, req.base, req.view, req.opts || {}, indexOf);
      post({ id: req.id, result }, transferables(result));
    } catch (err) {
      post({ id: req.id, error: err.message });
    }
  };
  const drain = () => {
    scheduled = false;
    // the rows first: a model is what the reader is waiting for; the rail's counts follow
    for (const kind of ['model', 'counts']) {
      const req = pending[kind];
      pending[kind] = null;
      if (req) ready.then(() => answer(req), (err) => post({ id: req.id, error: String((err && err.message) || err) }));
    }
  };
  return (msg) => {
    if (msg.type === 'data') { ready = Promise.resolve().then(() => use(msg.dataset, msg.rev)); return; }
    if (msg.type === 'begin') {
      building = { ...msg.dataset, rows: [] };
      ready = new Promise((resolve) => { finish = resolve; }).then(() => use(building, msg.rev));
      return;
    }
    if (msg.type === 'rows') { for (const r of msg.rows) building.rows.push(r); return; }
    if (msg.type === 'end') { finish(); return; }
    if (msg.type === 'load') {
      // WHY replay the main thread's responses: a file fetched twice can change in between (an agent edits it, then
      // reload()); indices into the main thread's rows are only right if both copies came from the same bytes
      const get = msg.bodies ? replay(msg.bodies) : undefined;
      ready = (load || defaultLoad)(msg.url, get).then((ds) => use(ds, msg.rev), fail);
      ready.catch(() => { /* reported as 'failed'; each request reports it again */ });
      return;
    }
    if (msg.type === 'row') {
      ready.then(() => {
        const old = dataset.rows[msg.index];
        indexOf.delete(old);
        dataset.rows[msg.index] = msg.row;
        indexOf.set(msg.row, msg.index);
        ranks = rankCache(dataset); // a value changed: every column is ranked again on its next use
        rev = msg.rev;
      }, () => { /* no data: every request reports it */ });
      return;
    }
    if (msg.type === 'model' || msg.type === 'counts') {
      const old = pending[msg.type];
      if (old) post({ id: old.id, result: null }); // superseded before it started
      pending[msg.type] = msg;
      if (!scheduled) { scheduled = true; setTimeout(drain, 0); }
    }
  };
}

function defaultLoad(url, get) {
  return loadDataset(url, get ? { fetch: get } : undefined);
}

/** A fetch that answers from recorded responses: [[url, {ok, status, bytes} | {error}]]. A url never fetched throws,
    as a failed request does. */
function replay(bodies) {
  const map = new Map(bodies);
  return async (url) => {
    const r = map.get(String(url));
    if (!r || r.error) throw new Error(`cannot load ${url}: ${(r && r.error) || 'not fetched'}`);
    return { ok: r.ok, status: r.status, text: async () => (r.text !== undefined && r.text !== null ? r.text : decode(r.bytes)) };
  };
}

// WHY bytes and TextDecoder: Response.text() is defined as UTF-8 decode of the body (BOM dropped, bad bytes as U+FFFD),
// which is what TextDecoder('utf-8') does, so the text is the same; the bytes are an ArrayBuffer the page can transfer
// to the worker at no cost, where posting the 50 MB string cost ~51 ms. Measured in Chromium on the 100,000-row bench
// file, arrayBuffer() + decode was also faster than text(): ~320 ms against ~530-750 ms.
const decode = (bytes) => (bytes ? new TextDecoder().decode(bytes) : '');

/**
 * A fetch for loadDataset that records every response it reads, for a worker to parse the same bytes:
 *   const rec = recordingFetch((u) => fetch(u, {signal}));  await loadDataset(url, {fetch: rec.fetch});  rec.bodies
 */
export function recordingFetch(get) {
  const bodies = new Map();
  return {
    bodies,
    fetch: async (url) => {
      const key = String(url);
      let r;
      try { r = await get(url); } catch (err) { bodies.set(key, { error: err.message }); throw err; }
      const rec = { ok: r.ok, status: r.status, bytes: null };
      bodies.set(key, rec);
      const text = async () => {
        if (typeof r.arrayBuffer !== 'function') { rec.text = await r.text(); return rec.text; } // a stand-in fetch
        rec.bytes = await r.arrayBuffer();
        return decode(rec.bytes);
      };
      return { ok: r.ok, status: r.status, text };
    },
  };
}

/** The buffers of recorded bodies, for postMessage's transfer list. */
const bodyBuffers = (bodies) => [...bodies.values()].map((b) => b.bytes).filter((b) => b && b.byteLength !== undefined);

/**
 * A persistent worker over one dataset: the data goes over once, then each model() is one small request and one
 * transferable answer. A newer request supersedes an older one still running: its promise resolves with null, so a
 * host draws only the latest (the stale-result rule of the 2026-10-26 review).
 *   const w = createRowModelWorker(dataset, { rev })        // or { url, bodies } to have it parse the same bytes
 *   w.ready                                                 // true once the worker holds the data
 *   const m = await w.model(base, view, { query, filters }) // rowModel()'s shape, or null when superseded
 *   w.edit(index, row, rev)                                 // a row changed in place (data-views' propose)
 *   w.terminate()                                           // the host's disconnectedCallback
 * `slice`: send the rows in slices of this many, one task each, so cloning 100,000 rows never blocks the page in one
 * go. `Worker`: the constructor (a test passes Node's stand-in).
 */
export function createRowModelWorker(dataset, { workerUrl = new URL('./rowmodel-worker.js', import.meta.url), url = null, bodies = null, rev = 0, slice = 0, onReady = null, Worker: Ctor = globalThis.Worker } = {}) {
  // WHY beside the core: dist/data-ui.js and dist/rowmodel-worker.js ship together (build.mjs)
  const worker = new Ctor(workerUrl, { type: 'module' });
  let seq = 0;
  const waiting = new Map();
  const newest = { model: 0, counts: 0 };
  // one request of each kind at a time: a newer one resolves the older with null at once
  const ask = (type, body) => {
    const id = ++seq;
    const prev = newest[type];
    newest[type] = id;
    const d = waiting.get(prev);
    if (d) { waiting.delete(prev); d.resolve(null); }
    return new Promise((resolve, reject) => {
      waiting.set(id, { resolve, reject });
      worker.postMessage({ type, id, ...body, rev: client.rev });
    }).then((msg) => {
      if (msg && msg.stale) throw new Error('the row-model worker holds an older revision of the data');
      return msg && msg.result && id === newest[type] ? msg.result : null;
    });
  };
  let failed = null;
  let sending = 0;
  const client = {
    worker,
    ready: false,
    rev,
    dataset,
    async model(base, view, opts = {}) {
      if (failed) throw failed;
      const result = await ask('model', { base, view, opts });
      return result ? modelFromOrder(dataset, base, view, result) : null;
    },
    /** <data-facets>' counts for `view` (its filters) under the all-views `filters`: railCounts()'s object, or null
        when superseded. `now` dates the date facets' presets, as the page's clock says. */
    async counts(view, filters, specs, now = Date.now()) {
      if (failed) throw failed;
      return ask('counts', { view: { filters: (view || {}).filters }, filters, specs, now });
    },
    edit(index, row, nextRev) {
      client.rev = nextRev;
      worker.postMessage({ type: 'row', index, row, rev: nextRev });
    },
    terminate() {
      clearTimeout(sending);
      worker.terminate();
      for (const d of waiting.values()) d.resolve(null);
      waiting.clear();
      failed = new Error('the row-model worker was terminated');
      client.ready = false;
    },
  };
  worker.onmessage = (e) => {
    const msg = e.data;
    if (msg.type === 'ready') { client.ready = true; if (onReady) onReady(client); return; }
    if (msg.type === 'failed') { failed = new Error(msg.error); for (const d of waiting.values()) d.reject(failed); waiting.clear(); return; }
    const done = waiting.get(msg.id);
    if (!done) return;
    waiting.delete(msg.id);
    if (msg.error) done.reject(new Error(msg.error)); else done.resolve(msg);
  };
  worker.onerror = (e) => {
    failed = new Error((e && e.message) || 'the row-model worker failed');
    for (const d of waiting.values()) d.reject(failed);
    waiting.clear();
  };
  const sliced = !url && slice && dataset.rows.length > slice;
  const { rows, ...rest } = dataset;
  try {
    if (url) worker.postMessage({ type: 'load', url, bodies: bodies ? [...bodies] : null, rev }, bodies ? bodyBuffers(bodies) : []);
    else if (!sliced) worker.postMessage({ type: 'data', dataset, rev });
    else worker.postMessage({ type: 'begin', dataset: rest, rev });
  } catch (err) { worker.terminate(); throw err; } // data that cannot be cloned: no worker, never a stray one
  if (sliced) {
    // WHY slices: one structured clone of 100,000 bench rows held Chromium's main thread for ~282 ms; slices of 2,000
    // took at most ~14 ms each, one task apiece, so the page keeps drawing frames while the copy goes over
    let at = 0;
    const next = () => {
      sending = 0;
      if (failed) return;
      try { worker.postMessage({ type: 'rows', rows: rows.slice(at, at + slice) }); } catch (err) { client.terminate(); failed = err; return; }
      at += slice;
      if (at < rows.length) sending = setTimeout(next, 0); else worker.postMessage({ type: 'end' });
    };
    next();
  }
  return client;
}
