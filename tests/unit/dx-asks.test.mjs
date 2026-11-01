// RobotDx's asks of data-ui (RobotDx PEP 0001 §17.1, found wiring /dx/'s "Add to dashboard"; docs/CONTRACT.md §26,
// §34): the halves that run in Node. Written red, before the code; never edited after. The browser half is
// tests/browser/dx_asks_checks.py. Every oracle is written out by hand from the tiny inputs here, never from the code.
//   ask 2: in a <data-dashboard> an added panel names the file the dashboard DECLARES for its dataset (a host may hand
//          one dataset object to several declared files, as RobotDx's /dx/ does): model.js declaredFile.
//   ask 3: "At this moment" on a live panel stands at t: its LiveClock, restored at t before its live data binds,
//          stays paused there when the data binds and keeps arriving (RobotDx measured its panel 4.3 s past t).
import { test } from 'node:test';
import assert from 'node:assert/strict';

// requestAnimationFrame is faked: the live frame loop runs on demand (flushLive), a play tick never runs by itself
globalThis.requestAnimationFrame = () => 0;
globalThis.cancelAnimationFrame = () => {};
globalThis.performance = { now: () => 0 };

const { LiveClock } = await import('../../packages/core/src/live/clock.js');
const { LiveDataset } = await import('../../packages/core/src/live/store.js');
const { flushLive } = await import('../../packages/core/src/live/frame.js');
const { parseBase } = await import('../../packages/core/src/base.js');
const M = await import('../../packages/dashboard/src/model.js');

const props = { t: { type: 'number' }, v: { type: 'number' } };
/** n rows from t0, dt apart (the same rows each time: v is the row's index). */
const feed = (ds, t0, n, dt = 0.1) => { const rows = []; for (let i = 0; i < n; i++) rows.push({ t: t0 + i * dt, v: i }); ds.append(rows); };
// RobotDx's own example of the instant a reader added: a host's wall clock, Unix seconds (PEP 0001 §17.1, ask 5)
const T = 1792631514.923;

// ------------------------------------------------------------------------------------------- ask 3: the pinned clock

test('a LiveClock restored at a moment before any live data is bound stands there when the data binds', () => {
  const c = new LiveClock({ loop: false });
  c.restore({ t: T });
  assert.equal(c.t, T, 'restored at T');
  const ds = new LiveDataset({ properties: props, time: 't' });
  c.bind(ds);
  feed(ds, T - 5, 60);   // T − 5 … T + 0.9: data on both sides of the moment
  flushLive();
  assert.equal(c.live, true, 'a live dataset is bound');
  assert.equal(c.following, false, 'it does not follow the newest data');
  assert.equal(c.playing, false);
  assert.equal(c.t, T, 'still at the moment, not the newest data');
});

test('a pinned LiveClock stays at its moment while the live data keeps arriving after it, and says so in no time event', () => {
  const c = new LiveClock({ loop: false });
  c.restore({ t: T });
  const ds = new LiveDataset({ properties: props, time: 't' });
  c.bind(ds);
  const sources = [];
  c.addEventListener('time', (e) => sources.push(e.detail.source));
  feed(ds, T - 5, 60);
  flushLive();
  for (let k = 1; k <= 5; k++) { feed(ds, T + k, 10); flushLive(); }
  assert.equal(c.following, false);
  assert.equal(c.t, T);
  assert.ok(c.liveEnd > T + 5, `the data reached ${c.liveEnd - T} s past the moment`);
  assert.ok(!sources.includes('live'), `no time event from following: ${sources.join(', ')}`);
});

test('a LiveClock restored with a range before its live data binds pauses there too (a link\'s range, as a moment)', () => {
  const c = new LiveClock({ loop: false });
  c.restore({ t: T - 2, range: [T - 3, T - 1] });
  const ds = new LiveDataset({ properties: props, time: 't' });
  c.bind(ds);
  feed(ds, T - 5, 60);
  flushLive();
  assert.equal(c.following, false);
  assert.equal(c.t, T - 2);
});

test('a LiveClock restored to live, or with no t, before its live data binds follows it when it binds (unchanged)', () => {
  for (const nav of [{ t: 'live' }, { t: 'home' }, {}]) {
    const c = new LiveClock({ loop: false });
    c.restore(nav);
    const ds = new LiveDataset({ properties: props, time: 't' });
    c.bind(ds);
    feed(ds, 100, 20);
    flushLive();
    assert.equal(c.following, true, `${JSON.stringify(nav)}: follows`);
    assert.equal(c.t, ds.end, `${JSON.stringify(nav)}: at the newest data`);
  }
});

test('bound first and then restored at a moment, a LiveClock pauses there (a dashboard opening a #t= link; unchanged)', () => {
  const c = new LiveClock({ loop: false });
  const ds = new LiveDataset({ properties: props, time: 't' });
  c.bind(ds);
  feed(ds, 100, 50);
  flushLive();
  assert.equal(c.following, true);
  c.restore({ t: 102 });
  feed(ds, 105, 20);
  flushLive();
  assert.equal(c.following, false);
  assert.equal(c.t, 102);
});

test('goLive() on a pinned LiveClock follows the newest data again (the reader asked for it)', () => {
  const c = new LiveClock({ loop: false });
  c.restore({ t: T });
  const ds = new LiveDataset({ properties: props, time: 't' });
  c.bind(ds);
  feed(ds, T - 5, 60);
  flushLive();
  c.goLive();
  flushLive();
  assert.equal(c.following, true);
  assert.equal(c.t, ds.end);
});

// ------------------------------------------------------------------------------------------- ask 2: the declared file

const BOARD = `# a board as RobotDx's /dx/ writes them: data paths relative to the dashboards folder
data: events.json
datasets:
  config:
    data: ../datasets/config.json?path=b
  logs:
    data: /api/logs.json?since=0
  runs:
    data: runs/{run}.json
  index: runs.json
links:
  - { from: index.run, to: runs.run, direction: one-way }
views:
  - { type: table, name: Settings, from: config }
layout:
  panels:
    - { view: Settings }
`;
const dash = () => M.readDashboard(parseBase(BOARD));
const AT = 'http://127.0.0.1:8821/dx/dashboards/board-b.base';

test('declaredFile is exported by the dashboard model', () => {
  assert.equal(typeof M.declaredFile, 'function');
});

test('declaredFile: a dataset\'s data: resolved against where the .base lives, its query kept', () => {
  assert.equal(M.declaredFile(dash(), 'config', { base: AT }), 'http://127.0.0.1:8821/dx/datasets/config.json?path=b');
  // the folder the .base lives in says the same as the .base's own URL
  assert.equal(M.declaredFile(dash(), 'config', { base: 'http://127.0.0.1:8821/dx/dashboards/' }), 'http://127.0.0.1:8821/dx/datasets/config.json?path=b');
  assert.equal(M.declaredFile(dash(), 'logs', { base: AT }), 'http://127.0.0.1:8821/api/logs.json?since=0');
  assert.equal(M.declaredFile(dash(), 'index', { base: AT }), 'http://127.0.0.1:8821/dx/dashboards/runs.json');
});

test('declaredFile: the top level\'s data: is declared under its name (its file stem, CONTRACT §17)', () => {
  assert.equal(M.declaredFile(dash(), 'events', { base: AT }), 'http://127.0.0.1:8821/dx/dashboards/events.json');
});

test('declaredFile: a per-pick dataset declares the one file its picks read now, and none while no file is read', () => {
  assert.equal(M.declaredFile(dash(), 'runs', { base: AT, picked: 'http://127.0.0.1:8821/dx/dashboards/runs/r7.json' }), 'http://127.0.0.1:8821/dx/dashboards/runs/r7.json');
  assert.equal(M.declaredFile(dash(), 'runs', { base: AT, picked: null }), null);
  assert.equal(M.declaredFile(dash(), 'runs', { base: AT }), null);
});

test('declaredFile: a dataset the dashboard does not declare has no file', () => {
  assert.equal(M.declaredFile(dash(), 'nope', { base: AT }), null);
});
