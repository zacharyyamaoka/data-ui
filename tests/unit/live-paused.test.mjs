// A paused view redraws only when what it shows at t can change (docs/peps/0012-live-data.md §8, docs/CONTRACT.md §26).
// Follow-up to bfc632f, found by the RobotDx lane: paused at t, every upsert to a keyed dataset redrew its views at the
// same t (230-440 ms apart, repeatedly), though every new version lay after t. The rule, per frame of news:
//   'draw'   a row, version or removal written at or before t inside the view's window (a late one); retention taking
//            a row the view reads at t (a plot or levels card: any sample in its span); a reset; the recording ending
//   'count'  retention took rows at t the view does not read: only the status line's count moved
//   null     everything else, above all whatever arrived after t
// Committed before the code it tests (failing first): pausedNews does not exist yet, and a keyed dataset's retention
// drops are not in the drop log yet.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as feed from '../../packages/core/src/live/feed.js';
import { LiveDataset } from '../../packages/core/src/live/store.js';
import { snapshotModel } from '../../packages/core/src/live/model.js';
import { flushLive } from '../../packages/core/src/live/frame.js';

const { atOf } = feed;
// WHY through the namespace: each test fails on its own while pausedNews is missing (the store's tests run regardless)
const pausedNews = (...args) => { assert.equal(typeof feed.pausedNews, 'function', 'live/feed.js exports pausedNews'); return feed.pausedNews(...args); };
const T = 1000;   // the paused clock's t
const news = (over = {}) => ({ appended: 0, upserted: 0, removed: 0, dropped: 0, reset: false, recorded: false, from: undefined, to: undefined, ...over });
// a row as the store makes it: its arrival number hidden, as LiveDataset gives it
const row = (seq, extra) => { const r = { id: String(seq), ...extra }; Object.defineProperty(r, '_seq', { value: seq, enumerable: false }); return r; };
const byStream = (r) => r.src;

test('pausedNews: a version or row after t draws nothing, whatever the view or its window', () => {
  for (const at of ['latest', 'all', 5]) {
    assert.equal(pausedNews(news({ upserted: 3, from: T + 0.01, to: T + 2 }), { t: T, at }), null, `keyed upsert after t, at ${at}`);
    assert.equal(pausedNews(news({ appended: 600, from: T + 0.01, to: T + 2 }), { t: T, at }), null, `append after t, at ${at}`);
    assert.equal(pausedNews(news({ removed: 1, from: T + 1, to: T + 1 }), { t: T, at }), null, `removal after t, at ${at}`);
    assert.equal(pausedNews(news({ appended: 60, from: T + 0.5, to: T + 0.6 }), { t: T, at, native: true }), null, `plot rows after t, at ${at}`);
  }
});

test('pausedNews: a late version, row or removal at or before t draws (exactly at t too)', () => {
  assert.equal(pausedNews(news({ upserted: 1, from: T - 0.5, to: T - 0.5 }), { t: T, at: 'latest' }), 'draw');
  assert.equal(pausedNews(news({ upserted: 1, from: T, to: T }), { t: T, at: 'latest' }), 'draw', 'a version at t is the record at t');
  assert.equal(pausedNews(news({ removed: 1, from: T - 1, to: T - 1 }), { t: T, at: 'latest' }), 'draw');
  assert.equal(pausedNews(news({ appended: 1, from: T - 0.2, to: T - 0.2 }), { t: T, at: 'all' }), 'draw');
  // one frame that brought a late row and many after t: the late one counts
  assert.equal(pausedNews(news({ appended: 900, upserted: 0, from: T - 0.2, to: T + 3 }), { t: T, at: 'all' }), 'draw');
  assert.equal(pausedNews(news({ appended: 1, from: T - 2, to: T - 2 }), { t: T, at: 10, native: true }), 'draw', 'a late sample inside the plot window');
});

test('pausedNews: a window ending at t (append and keyed): a late row before the window draws nothing', () => {
  // at: 5s shows (t − 5, t]: a row at t − 6, or exactly at t − 5, is not in it
  assert.equal(pausedNews(news({ appended: 1, from: T - 6, to: T - 6 }), { t: T, at: 5 }), null);
  assert.equal(pausedNews(news({ appended: 1, from: T - 5, to: T - 5 }), { t: T, at: 5 }), null, 'the window is open at its start');
  assert.equal(pausedNews(news({ appended: 1, from: T - 4.9, to: T - 4.9 }), { t: T, at: 5 }), 'draw');
  assert.equal(pausedNews(news({ upserted: 1, from: T - 6, to: T - 6 }), { t: T, at: 5 }), null, 'keyed: an old version cannot enter the window');
  // the same late row, for a view with no window, draws
  assert.equal(pausedNews(news({ appended: 1, from: T - 6, to: T - 6 }), { t: T, at: 'all' }), 'draw');
  assert.equal(pausedNews(news({ appended: 1, from: T - 6, to: T - 6 }), { t: T, at: 'latest' }), 'draw');
  // a plot's span is its window and its zoom (which may reach past t): a row inside the zoom draws
  assert.equal(pausedNews(news({ appended: 1, from: T - 30, to: T - 30 }), { t: T, at: 10, native: true }), null);
  assert.equal(pausedNews(news({ appended: 1, from: T + 2, to: T + 2 }), { t: T, at: 10, native: true, zoom: [T - 20, T + 5] }), 'draw');
  assert.equal(pausedNews(news({ appended: 1, from: T - 15, to: T - 15 }), { t: T, at: 10, native: true, zoom: [T - 20, T + 5] }), 'draw');
});

test('pausedNews: retention taking a row the view reads at t draws; rows it does not read only recount', () => {
  const read = [row(10, { src: 'a', t: T - 3 }), row(11, { src: 'b', t: T - 2 }), row(12, { src: 'a', t: T - 1 })];
  const drop = (stream, seqMin, seqMax, t0, t1) => ({ gen: 1, stream, seqMin, seqMax, t0, t1 });
  const opts = { t: T, at: 'all', read, streamOf: byStream };
  // a chunk of stream a holding arrival 10: the view shows it
  assert.equal(pausedNews(news({ dropped: 4096 }), { ...opts, drops: [drop('a', 1, 10, T - 9, T - 3)] }), 'draw');
  // the same arrival numbers in another stream's chunk: not a row this view reads (arrival numbers are global)
  assert.equal(pausedNews(news({ dropped: 4096 }), { ...opts, drops: [drop('c', 1, 11, T - 9, T - 2)] }), 'count');
  // an older chunk of stream a, before every row shown: the rows did not change, the count of rows at t did
  assert.equal(pausedNews(news({ dropped: 4096 }), { ...opts, drops: [drop('a', 1, 9, T - 60, T - 50)] }), 'count');
  // a chunk after t (eviction skipped the minute before a paused t and took a newer one): nothing at t moved
  assert.equal(pausedNews(news({ dropped: 4096 }), { ...opts, drops: [drop('a', 20, 30, T + 1, T + 5)] }), null);
  // a window: a chunk older than its start is not at t at all
  assert.equal(pausedNews(news({ dropped: 4096 }), { ...opts, at: 5, drops: [drop('a', 1, 9, T - 60, T - 50)] }), null);
  // the drop log no longer reaches back to the last draw: draw (it cannot tell)
  assert.equal(pausedNews(news({ dropped: 4096 }), { ...opts, drops: null }), 'draw');
  // with no stream property every row is in stream '' (one stream): the arrival numbers decide
  const flat = [row(5, { t: T - 1 })];
  assert.equal(pausedNews(news({ dropped: 1 }), { t: T, at: 'all', read: flat, streamOf: () => '', drops: [drop('', 1, 5, T - 2, T - 1)] }), 'draw');
  assert.equal(pausedNews(news({ dropped: 1 }), { t: T, at: 'all', read: flat, streamOf: () => '', drops: [drop('', 1, 4, T - 9, T - 8)] }), 'count');
});

test('pausedNews: a plot or levels card draws every sample in its span, so a drop inside it draws', () => {
  const drop = (t0, t1) => ({ gen: 1, stream: 'a', seqMin: 1, seqMax: 9, t0, t1 });
  assert.equal(pausedNews(news({ dropped: 9 }), { t: T, at: 10, native: true, drops: [drop(T - 12, T - 8)] }), 'draw');
  assert.equal(pausedNews(news({ dropped: 9 }), { t: T, at: 10, native: true, drops: [drop(T - 40, T - 20)] }), null);
  // a recording's plot shows all of it: any drop at or before t draws
  assert.equal(pausedNews(news({ dropped: 9 }), { t: T, at: 'all', native: true, drops: [drop(T - 400, T - 390)] }), 'draw');
});

test('pausedNews: a reset or the recording ending always draws', () => {
  assert.equal(pausedNews(news({ reset: true }), { t: T, at: 'all' }), 'draw');
  assert.equal(pausedNews(news({ recorded: true }), { t: T, at: 'all', native: true }), 'draw');
});

// ------------------------------------------------------------------ with the real store

/** The change detail the next frame publishes. */
function frameNews(ds) {
  let got = null;
  const on = (e) => { got = e.detail; };
  ds.addEventListener('change', on);
  flushLive();
  ds.removeEventListener('change', on);
  return got;
}

test('store: keyed upserts after a paused t are news a view at t skips; a late version is not', () => {
  const ds = new LiveDataset({ properties: { path: { type: 'text' }, t: { type: 'number' }, value: { type: 'number' } }, time: 't', key: 'path' });
  ds.upsert([{ path: 'p1', t: T - 2, value: 1 }, { path: 'p2', t: T - 1.9, value: 2 }]);
  frameNews(ds);
  const view = { type: 'table' };
  const at = atOf(view, ds);
  assert.equal(at, 'latest');
  const gen = ds.dropGen;
  for (let k = 1; k <= 5; k++) {
    ds.upsert([{ path: 'p1', t: T + k * 0.25, value: 10 + k }, { path: 'p2', t: T + k * 0.25, value: 20 + k }]);
    const d = frameNews(ds);
    assert.equal(pausedNews(d, { t: T, at, drops: ds.dropsSince(gen), read: ds.snapshot(T, { at }), streamOf: (r) => r.id }), null, `version batch ${k} after t`);
  }
  ds.upsert([{ path: 'p1', t: T - 0.5, value: 999 }]);
  const late = frameNews(ds);
  assert.equal(pausedNews(late, { t: T, at, drops: ds.dropsSince(gen), read: ds.snapshot(T, { at }), streamOf: (r) => r.id }), 'draw');
  assert.equal(ds.latestAt(T, 'p1').value, 999, 'the record at t is the late version');
});

test('store: a keyed dataset\'s retention drops go in the drop log (key, arrival numbers, times), and its start moves', () => {
  const ds = new LiveDataset({ properties: { host: { type: 'text' }, t: { type: 'number' }, n: { type: 'number' } }, time: 't', key: 'host', retention: { age: 10 } });
  for (let i = 0; i <= 20; i++) ds.upsert([{ host: 'rack', t: T + i, n: i }]);
  frameNews(ds);
  // end 1020, age 10: the versions before 1010 went, the newest of the key stays
  assert.equal(ds.snapshot(Infinity, { at: 'latest' })[0].n, 20);
  assert.ok(ds.dropGen > 0, 'a keyed drop moves the drop generation');
  const log = ds.dropsSince(0);
  assert.ok(Array.isArray(log) && log.length > 0, 'the drops are logged');
  const seqs = log.flatMap((x) => [x.seqMin, x.seqMax]);
  assert.ok(log.every((x) => x.stream === 'rack'), 'a keyed drop names its key as the stream');
  assert.ok(log.every((x) => x.t1 < 1010 && x.t0 <= x.t1), 'a keyed drop says the times it took');
  assert.equal(Math.min(...seqs), 1, 'the oldest version (arrival 1) went');
  assert.equal(ds.start, ds.latestAt(1010, 'rack').t, 'the dataset starts at its oldest kept version');
  assert.equal(ds.start, 1010);
});

test('store: paused at t, keyed age retention takes old versions the view does not read (count), then the one it does (draw)', () => {
  // RobotDx's summary: one key, a version every 0.25 s, age retention; paused at t while versions keep coming
  const ds = new LiveDataset({ properties: { host: { type: 'text' }, t: { type: 'number' }, n: { type: 'number' } }, time: 't', key: 'host', retention: { age: 3 } });
  for (let i = 0; i < 40; i++) ds.upsert([{ host: 'rack', t: T - 10 + i * 0.25, n: i }]);
  ds.upsert([{ host: 'rack', t: T, n: 40 }]);
  frameNews(ds);
  const at = 'latest';
  let gen = ds.dropGen;
  const read = () => ds.snapshot(T, { at });
  let shown = read();
  assert.equal(shown.length, 1);
  assert.equal(shown[0].n, 40, 'the record at t');
  const seen = [];
  for (let i = 1; i <= 16; i++) {
    ds.upsert([{ host: 'rack', t: T + i * 0.25, n: 40 + i }]);
    const d = frameNews(ds);
    const drops = ds.dropsSince(gen);
    gen = ds.dropGen;
    const verdict = pausedNews(d, { t: T, at, drops, read: shown, streamOf: (r) => r.id });
    seen.push(verdict);
    if (verdict === 'draw') shown = read();
  }
  // until end − 3 passes t the drops are versions older than the record at t: not one draw
  assert.deepEqual(seen.slice(0, 12).filter((v) => v === 'draw'), [], `versions after t and old drops: ${seen.join(' ')}`);
  // at end = t + 3.25 the record at t itself goes: the view at t loses it, and draws once
  assert.ok(seen.slice(12).includes('draw'), `retention reached t: ${seen.join(' ')}`);
  assert.equal(seen.filter((v) => v === 'draw').length, 1);
  assert.deepEqual(shown, [], 'nothing of the key is left at t');
});

test('store: an append chunk dropped by the byte budget names its stream, arrival numbers and times (as before)', () => {
  const ds = new LiveDataset({ properties: { t: { type: 'number' }, src: { type: 'text' }, v: { type: 'number' } }, time: 't', stream: 'src', retention: { bytes: 400_000 } });
  const rows = [];
  for (let i = 0; i < 30000; i++) rows.push({ t: T - 30 + i * 0.001, src: i % 2 ? 'a' : 'b', v: i });
  ds.append(rows);
  frameNews(ds);
  const log = ds.dropsSince(0);
  assert.ok(log && log.length > 0);
  assert.ok(log.every((x) => (x.stream === 'a' || x.stream === 'b') && x.seqMin <= x.seqMax && x.t0 <= x.t1));
});

test('snapshotModel: the model says which rows it read at t (a rolled-up view\'s rows are made, its reads are the store\'s)', () => {
  const ds = new LiveDataset({ properties: { t: { type: 'number' }, src: { type: 'text' }, v: { type: 'number' } }, time: 't', stream: 'src' });
  const rows = [];
  for (let i = 0; i < 200; i++) rows.push({ t: T - 10 + i * 0.05, src: `s${i % 4}`, v: i });
  ds.append(rows);
  const m = snapshotModel(ds, {}, { type: 'table', groupBy: { property: 'src' } }, { t: T - 1, at: 'all' });
  assert.ok(Array.isArray(m.read), 'model.read');
  assert.equal(m.read.length, ds.countAt(T - 1, 'all'));
  assert.ok(m.read.every((r) => typeof r._seq === 'number' && r.t <= T - 1), 'the store\'s own rows at t');
  assert.ok(!Object.keys(m).includes('read'), 'not enumerable: nothing that copies a model carries it');
});

// ------------------------------------------------------------------ what the redraw shows: a late row reaches every reader
// The gate above lets a late row through; the readers must then show it. Two read only what is new since their last
// read and missed a row that went in BEFORE rows they had read (an out-of-order arrival in its stream's open chunk):
// the Tail (newRows() stops at the first row it has seen) and the plot's ColumnCache (it reads back only LATE = 0.25 s),
// and the ColumnCache kept the columns of a chunk retention took inside its window.

const num = { type: 'number' };
const copy = (out) => out.map((a) => Array.from(a));

test('Tail: a late row placed before rows the tail has read reaches it, paused and following (equal to the snapshot)', async () => {
  const { Tail } = await import('../../packages/core/src/live/model.js');
  const ds = new LiveDataset({ properties: { t: num, n: num }, time: 't' });
  const seed = [];
  for (let i = 0; i < 40; i++) seed.push({ t: T - 4 + i * 0.1, n: i });
  ds.append(seed);
  const tail = new Tail(ds, {}, { type: 'table' }, { at: 'all' });
  const want = (t) => ds.snapshot(t, { at: 'all', limit: 2000 }).reverse().map((r) => r.n);
  tail.sync(T);
  ds.append([{ t: T + 0.5, n: 100 }]);   // paused at T: a row after t, read past
  tail.sync(T);
  assert.deepEqual(tail.rows.map((r) => r.n), want(T));
  ds.append([{ t: T - 6, n: 666 }]);     // late, before every row the tail holds
  tail.sync(T);
  assert.deepEqual(tail.rows.map((r) => r.n), want(T), 'paused: the late row is in the tail, in its place');
  assert.ok(tail.rows.some((r) => r.n === 666));
  // following: t = end, and a row goes in between rows the tail has read
  tail.sync(T + 0.5);
  ds.append([{ t: T + 1, n: 101 }]);
  tail.sync(T + 1);
  ds.append([{ t: T + 0.7, n: 102 }]);
  tail.sync(T + 1);
  assert.deepEqual(tail.rows.map((r) => r.n), want(T + 1), 'following: the out-of-order row is in the tail too');
});

test('ColumnCache: paused, a late sample further back than the late window reaches its column (equal to a fresh cache)', async () => {
  const { ColumnCache } = await import('../../packages/core/src/live/window.js');
  const ds = new LiveDataset({ properties: { t: num, v: num }, time: 't' });
  const rows = [];
  for (let i = 0; i < 3000; i++) rows.push({ t: T - 3 + i * 0.001, v: Math.sin(i / 40) });
  ds.append(rows);   // 3,000 samples over 3 s: one open chunk (under 4,096 rows and 10 s)
  const list = [{ name: 'v', column: 'v', ds, stream: null }];
  const W = 300, a = T - 2, b = T;
  const cache = new ColumnCache();
  cache.data(list, a, b, W);
  cache.data(list, a, b, W);
  assert.equal(cache.mode, 'cached', 'paused: the window holds, the columns are reused');
  ds.append([{ t: T - 1.5, v: -50 }]);   // 1.5 s before the newest sample: past what the cache reads back
  const got = copy(cache.data(list, a, b, W)), want = copy(new ColumnCache().data(list, a, b, W));
  assert.ok(want[1].includes(-50), 'the oracle has the late sample');
  assert.deepEqual(got, want);
});

test('ColumnCache: retention taking a chunk inside the window empties its columns (equal to a fresh cache)', async () => {
  const { ColumnCache } = await import('../../packages/core/src/live/window.js');
  const ds = new LiveDataset({ properties: { t: num, v: num }, time: 't', retention: { age: 12 } });
  const rows = [];
  for (let i = 0; i < 20000; i++) rows.push({ t: T - 20 + i * 0.001, v: Math.cos(i / 70) });
  ds.append(rows);
  const list = [{ name: 'v', column: 'v', ds, stream: null }];
  const W = 400, a = T - 10, b = T;
  const cache = new ColumnCache();
  cache.data(list, a, b, W);
  cache.data(list, a, b, W);
  assert.equal(cache.mode, 'cached');
  // paused at T while 5 s more arrive: end − 12 passes the chunks that start the window, and they go
  const more = [];
  for (let i = 1; i <= 5000; i++) more.push({ t: T + i * 0.001, v: 0 });
  ds.append(more);
  assert.ok(ds.start > a, `retention reached into the window (start ${ds.start - T} s)`);
  const got = copy(cache.data(list, a, b, W)), want = copy(new ColumnCache().data(list, a, b, W));
  assert.ok(want[1].slice(0, 20).every((y) => y === null), 'the oracle: the window starts empty, its samples are gone');
  assert.deepEqual(got, want);
});
