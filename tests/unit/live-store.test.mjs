// The live dataset's store (docs/peps/0012-live-data.md §3, docs/CONTRACT.md §26): appends in chunks, keyed versions,
// latest-at and range, the byte-budgeted ring that keeps the newest of every stream, and one change event per frame.
// Committed before the code it tests (lane/live, Step 2): these are the acceptance assertions.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LiveDataset, isLiveDataset, setLiveBudget, liveBudget, parseBytes, parseDuration, CHUNK_ROWS } from '../../packages/core/src/live/store.js';
import { flushLive } from '../../packages/core/src/live/frame.js';

const props = { t: { type: 'number' }, joint: { type: 'text' }, position: { type: 'number' }, note: { type: 'text' } };
const samples = (n, { t0 = 1000, dt = 0.001, joints = ['a'] } = {}) => {
  const out = [];
  for (let i = 0; i < n; i++) for (const j of joints) out.push({ t: t0 + i * dt, joint: j, position: Math.sin(i / 10), note: i % 7 ? null : `n${i}` });
  return out;
};

test('parse: byte sizes and durations as the .base writes them', () => {
  assert.equal(parseBytes('256MB'), 256 * 2 ** 20);
  assert.equal(parseBytes('1.5GB'), 1.5 * 2 ** 30);
  assert.equal(parseBytes('64 KB'), 64 * 1024);
  assert.equal(parseBytes(1000), 1000);
  assert.equal(parseBytes('lots'), null);
  assert.equal(parseDuration('30s'), 30);
  assert.equal(parseDuration('500ms'), 0.5);
  assert.equal(parseDuration('15m'), 900);
  assert.equal(parseDuration('2h'), 7200);
  assert.equal(parseDuration(5), 5);
  assert.equal(parseDuration('soon'), null);
});

test('a live dataset is dataset-shaped and says it is live', () => {
  const ds = new LiveDataset({ id: 'samples', title: 'Samples', properties: props, time: 't', stream: 'joint' });
  assert.ok(isLiveDataset(ds));
  assert.ok(!isLiveDataset({ rows: [] }));
  assert.equal(ds.id, 'samples');
  assert.equal(ds.live, true);
  assert.equal(ds.keyed, false);
  assert.deepEqual(Object.keys(ds.properties), Object.keys(props));
  assert.equal(ds.rowCount, 0);
  assert.equal(ds.start, null);
  assert.equal(ds.end, null);
});

test('append: rows go in, start / end / rowCount follow, ids are arrival numbers', () => {
  const ds = new LiveDataset({ properties: props, time: 't', stream: 'joint' });
  ds.append(samples(10, { joints: ['a', 'b'] }));
  assert.equal(ds.rowCount, 20);
  assert.equal(ds.start, 1000);
  assert.equal(ds.end, 1000 + 9 * 0.001);
  assert.deepEqual(ds.streams().sort(), ['a', 'b']);
  const last = ds.latestAt(ds.end, 'b');
  assert.equal(last.joint, 'b');
  assert.equal(last.t, 1000 + 9 * 0.001);
  assert.equal(typeof last.id, 'string');
  // a missing number reads as null, never NaN or 0
  ds.append([{ t: 1000.02, joint: 'a', position: null }]);
  assert.equal(ds.latestAt(1000.02, 'a').position, null);
});

test('append: a row without its time gets the arrival time (seconds)', () => {
  const ds = new LiveDataset({ properties: props, time: 't' });
  const before = Date.now() / 1000;
  ds.append([{ joint: 'a', position: 1 }]);
  const after = Date.now() / 1000;
  assert.ok(ds.end >= before - 1e-3 && ds.end <= after + 1e-3, `${ds.end} in [${before}, ${after}]`);
});

test('latestAt: the newest row at or before t, per stream; null before the first', () => {
  const ds = new LiveDataset({ properties: props, time: 't', stream: 'joint' });
  ds.append(samples(5000, { joints: ['a', 'b'] }));   // crosses a chunk boundary (4,096)
  assert.ok(CHUNK_ROWS === 4096);
  assert.equal(ds.latestAt(999, 'a'), null);
  const r = ds.latestAt(1000 + 4500.5 * 0.001, 'a');
  assert.ok(Math.abs(r.t - (1000 + 4500 * 0.001)) < 1e-9);
  // without a stream: the newest row of any stream
  const any = ds.latestAt(ds.end);
  assert.ok(Math.abs(any.t - ds.end) < 1e-9);
});

test('range: typed-array slices of (a, b] per stream, no row objects, across chunks', () => {
  const ds = new LiveDataset({ properties: props, time: 't', stream: 'joint' });
  ds.append(samples(9000, { joints: ['a'] }));
  const parts = ds.range(1000 + 1000 * 0.001, 1000 + 8500 * 0.001, { stream: 'a', columns: ['position'] });
  assert.ok(parts.length >= 2, 'spans more than one chunk');
  let n = 0, prev = -Infinity;
  for (const p of parts) {
    assert.ok(p.t instanceof Float64Array);
    assert.ok(p.cols.position instanceof Float64Array);
    assert.equal(p.t.length, p.cols.position.length);
    for (const x of p.t) { assert.ok(x > 1000 + 1000 * 0.001 - 1e-12 && x <= 1000 + 8500 * 0.001 + 1e-12); assert.ok(x >= prev); prev = x; n++; }
  }
  assert.equal(n, 7500);
});

test('appendColumns: the columnar path stores the same rows as append', () => {
  const a = new LiveDataset({ properties: props, time: 't', stream: 'joint' });
  const b = new LiveDataset({ properties: props, time: 't', stream: 'joint' });
  const rows = samples(300, { joints: ['x'] });
  a.append(rows);
  b.appendColumns({ t: rows.map((r) => r.t), position: rows.map((r) => r.position), note: rows.map((r) => r.note) }, { stream: 'x' });
  assert.equal(b.rowCount, 300);
  const ra = a.snapshot(a.end, { at: 'all', limit: 1000 }).map((r) => [r.t, r.position, r.note, r.joint]);
  const rb = b.snapshot(b.end, { at: 'all', limit: 1000 }).map((r) => [r.t, r.position, r.note, r.joint]);
  assert.deepEqual(rb, ra);
});

test('snapshot: newest first, at: all / a window / latest, the cap and a filter', () => {
  const ds = new LiveDataset({ properties: props, time: 't', stream: 'joint' });
  const given = samples(1000, { joints: ['a', 'b'], dt: 0.01 });   // 10 s of 2 streams
  ds.append(given);
  const t = 1000 + 500 * 0.01;
  const all = ds.snapshot(t, { at: 'all', limit: 100000 });
  // the oracle: the same comparisons on the rows as given
  assert.equal(all.length, given.filter((r) => r.t <= t).length);
  for (let i = 1; i < all.length; i++) assert.ok(all[i - 1].t >= all[i].t, 'newest first');
  assert.ok(all.every((r) => r.t <= t), 'nothing after t');
  const win = ds.snapshot(t, { at: 2 });
  assert.ok(win.every((r) => r.t > t - 2 && r.t <= t));
  assert.equal(win.length, given.filter((r) => r.t > t - 2 && r.t <= t).length);
  assert.equal(ds.snapshot(t, { at: '2s' }).length, win.length, 'a duration may be written as the .base writes it');
  const latest = ds.snapshot(t, { at: 'latest' });
  assert.deepEqual(latest.map((r) => r.joint).sort(), ['a', 'b']);
  assert.ok(latest.every((r) => Math.abs(r.t - t) < 1e-9));
  const capped = ds.snapshot(t, { at: 'all', limit: 7 });
  assert.equal(capped.length, 7);
  assert.deepEqual(capped.map((r) => r.id), all.slice(0, 7).map((r) => r.id));
  const onlyB = ds.snapshot(t, { at: 'all', limit: 5, filter: (r) => r.joint === 'b' });
  assert.equal(onlyB.length, 5);
  assert.ok(onlyB.every((r) => r.joint === 'b'));
});

test('snapshot: the same row object is handed out again while its chunk lives (no churn per frame)', () => {
  const ds = new LiveDataset({ properties: props, time: 't' });
  ds.append(samples(50));
  const a = ds.snapshot(ds.end, { limit: 10 });
  const b = ds.snapshot(ds.end, { limit: 10 });
  assert.equal(a[0], b[0]);
});

test('order: a row older than its stream sealed history is dropped and counted; in the open chunk it is placed in order', () => {
  const ds = new LiveDataset({ properties: props, time: 't', stream: 'joint' });
  ds.append([{ t: 10, joint: 'a', position: 1 }, { t: 12, joint: 'a', position: 2 }]);
  ds.append([{ t: 11, joint: 'a', position: 9 }]);
  const rows = ds.snapshot(20, { limit: 10 });
  assert.deepEqual(rows.map((r) => r.t), [12, 11, 10]);
  ds.append(samples(5000, { t0: 100, joints: ['a'] }));   // seals chunks after t = 12
  ds.append([{ t: 5, joint: 'a', position: 0 }]);
  assert.equal(ds.late, 1);
});

test('keyed: upsert replaces by key; the record at t is its newest version then; remove hides it from then on', () => {
  const ds = new LiveDataset({ properties: { path: { type: 'text' }, level: { type: 'text' }, t: { type: 'number' } }, time: 't', key: 'path' });
  assert.equal(ds.keyed, true);
  ds.upsert([{ path: 'rack/a', level: 'ok', t: 1 }, { path: 'rack/b', level: 'ok', t: 1 }]);
  ds.upsert([{ path: 'rack/a', level: 'warn', t: 5 }]);
  ds.remove(['rack/b'], 7);
  const at3 = ds.snapshot(3, { at: 'latest' });
  assert.deepEqual(at3.map((r) => [r.path, r.level]).sort(), [['rack/a', 'ok'], ['rack/b', 'ok']]);
  const at6 = ds.snapshot(6, { at: 'latest' });
  assert.deepEqual(at6.map((r) => [r.path, r.level]).sort(), [['rack/a', 'warn'], ['rack/b', 'ok']]);
  const at8 = ds.snapshot(8, { at: 'latest' });
  assert.deepEqual(at8.map((r) => [r.path, r.level]), [['rack/a', 'warn']]);
  assert.equal(ds.latestAt(6, 'rack/a').level, 'warn');
  assert.equal(at8[0].id, 'rack/a', 'a keyed row\'s id is its key');
});

test('retention: a dataset byte cap holds, the oldest goes first, the newest chunk of every stream stays', () => {
  setLiveBudget(1e12);
  const ds = new LiveDataset({ properties: props, time: 't', stream: 'joint', retention: { bytes: 600_000 } });
  // a stream that speaks once, early, then never again: it must survive every eviction
  ds.append([{ t: 0.5, joint: 'quiet', position: 42 }]);
  let peak = 0;
  for (let k = 0; k < 40; k++) {
    ds.append(samples(2000, { t0: 1 + k * 2, joints: ['a', 'b'] }));
    peak = Math.max(peak, ds.bytes);
  }
  assert.ok(ds.bytes <= 600_000, `bytes ${ds.bytes} <= cap`);
  assert.ok(peak <= 600_000 + 4 * CHUNK_ROWS * 8 * 6, `never far over the cap between appends: ${peak}`);
  // WHY not ds.start: the quiet stream's one row at 0.5 s is its newest and stays, so start stays 0.5 s too
  const oldestA = ds.range(-Infinity, Infinity, { stream: 'a' })[0].t[0];
  assert.ok(oldestA > 10, `the oldest data of the busy streams went: the oldest 'a' row is at ${oldestA} s`);
  assert.equal(ds.start, 0.5);
  assert.equal(ds.latestAt(ds.end, 'quiet').position, 42, 'the newest of a quiet stream stays');
  assert.ok(ds.latestAt(ds.end, 'a') && ds.latestAt(ds.end, 'b'));
});

test('retention: age drops rows older than end - age (whole chunks), never the newest of a stream', () => {
  setLiveBudget(1e12);
  const ds = new LiveDataset({ properties: props, time: 't', stream: 'joint', retention: { age: 10 } });
  ds.append(samples(60000, { t0: 0, dt: 0.001, joints: ['a'] }));   // 60 s
  assert.ok(ds.start >= 60 - 10 - 5, `start ${ds.start} within a chunk of end - age`);
  assert.ok(ds.end > 59.9);
});

test('retention: the page budget holds across datasets, oldest first', () => {
  setLiveBudget(800_000);
  assert.equal(liveBudget(), 800_000);
  const a = new LiveDataset({ properties: props, time: 't', stream: 'joint' });
  const b = new LiveDataset({ properties: props, time: 't', stream: 'joint' });
  for (let k = 0; k < 30; k++) { a.append(samples(1000, { t0: k * 2, joints: ['a'] })); b.append(samples(1000, { t0: k * 2 + 1, joints: ['b'] })); }
  assert.ok(a.bytes + b.bytes <= 800_000, `${a.bytes} + ${b.bytes}`);
  assert.ok(a.start > 0 && b.start > 1);
  a.clear(); b.clear();
  setLiveBudget(256 * 2 ** 20);
  assert.equal(liveBudget(), 256 * 2 ** 20);
});

test('change: one event per frame with what changed, however many appends', () => {
  const ds = new LiveDataset({ properties: props, time: 't', stream: 'joint' });
  const seen = [];
  ds.addEventListener('change', (e) => seen.push(e.detail));
  for (let i = 0; i < 50; i++) ds.append(samples(10, { t0: 10 + i, joints: ['a'] }));
  assert.equal(seen.length, 0, 'nothing until the frame');
  flushLive();
  assert.equal(seen.length, 1);
  assert.equal(seen[0].appended, 500);
  assert.equal(seen[0].end, ds.end);
  flushLive();
  assert.equal(seen.length, 1, 'no change, no event');
});

test('status: setStatus, the age of the last data, finish() fixes the end', () => {
  const ds = new LiveDataset({ properties: props, time: 't', stale: 5 });
  assert.equal(ds.status.state, 'connecting');
  ds.setStatus('live');
  assert.equal(ds.status.state, 'live');
  ds.append(samples(3));
  assert.ok(ds.status.lastData > 0);
  ds.setStatus('paused', 'tview has the port');
  assert.equal(ds.status.detail, 'tview has the port');
  ds.finish();
  assert.equal(ds.recorded, true);
  const end = ds.end;
  ds.append(samples(3, { t0: 5000 }));
  assert.equal(ds.end, end, 'a finished recording takes no more rows');
});
