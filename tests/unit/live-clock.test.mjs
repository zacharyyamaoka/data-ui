// The live clock (docs/peps/0012-live-data.md §4, docs/CONTRACT.md §26): Rerun's following / paused-at-t states on the
// one Clock. Committed before the code it tests (lane/live, Step 2). requestAnimationFrame is faked so play ticks run
// on demand.
import { test } from 'node:test';
import assert from 'node:assert/strict';

let rafs = [];
globalThis.requestAnimationFrame = (fn) => { rafs.push(fn); return rafs.length; };
globalThis.cancelAnimationFrame = () => {};
let now = 0;
globalThis.performance = { now: () => now };
const tick = (ms) => { now += ms; const run = rafs; rafs = []; for (const f of run) f(now); };

const { Clock, fmtTime } = await import('../../packages/core/src/clock.js');
const { LiveClock, isLiveClock } = await import('../../packages/core/src/live/clock.js');
const { LiveDataset } = await import('../../packages/core/src/live/store.js');
const { flushLive } = await import('../../packages/core/src/live/frame.js');

const props = { t: { type: 'number' }, v: { type: 'number' } };
const feed = (ds, t0, n, dt = 0.1) => { const rows = []; for (let i = 0; i < n; i++) rows.push({ t: t0 + i * dt, v: i }); ds.append(rows); };
const make = () => {
  const clock = new LiveClock({ fps: 10 });
  const ds = new LiveDataset({ properties: props, time: 't' });
  clock.bind(ds);
  return { clock, ds };
};

test('a LiveClock is a Clock; with no live dataset it is exactly one', () => {
  const c = new LiveClock();
  assert.ok(c instanceof Clock);
  assert.ok(isLiveClock(c));
  assert.ok(!isLiveClock(new Clock()));
  assert.equal(c.live, false);
  assert.equal(c.following, false);
  c.setSpan(0, 10);
  c.seek(4);
  assert.equal(c.t, 4);
  c.play();
  tick(16); tick(500);
  assert.ok(c.t > 4 && c.t < 5, `plays like a Clock: ${c.t}`);
  c.pause();
  c.seek(9.99);
  c.setLoop(false);
  c.play();
  tick(16); tick(1000);
  assert.equal(c.playing, false, 'stops at the end, as a Clock does');
});

test('bound to a live dataset it follows: t = end on every arrival, with time events from source live', () => {
  const { clock, ds } = make();
  assert.equal(clock.live, true);
  assert.equal(clock.following, true);
  const sources = [];
  clock.addEventListener('time', (e) => sources.push(e.detail.source));
  feed(ds, 100, 20);
  flushLive();
  assert.equal(clock.end, ds.end);
  assert.equal(clock.t, ds.end);
  assert.equal(clock.start, 100);
  assert.equal(clock.lag, 0);
  assert.ok(sources.includes('live'));
  feed(ds, 102, 5);
  flushLive();
  assert.equal(clock.t, ds.end);
  assert.equal(clock.playing, true, 'following counts as playing (the play button shows pause)');
});

test('the live event fires when the span grows, without a state event (the URL is not rewritten every frame)', () => {
  const { clock, ds } = make();
  feed(ds, 100, 5);
  flushLive();
  clock.pause();
  let live = 0, state = 0;
  clock.addEventListener('live', () => live++);
  clock.addEventListener('state', () => state++);
  feed(ds, 101, 5);
  flushLive();
  assert.ok(live >= 1);
  assert.equal(state, 0);
});

test('any seek, step, loop range or loop leaves following; data keeps arriving under a paused t', () => {
  for (const act of [(c) => c.seek(c.end - 1), (c) => c.step(-1), (c) => c.setRange([c.start, c.end - 0.5]), (c) => c.setLoop(true)]) {
    const { clock, ds } = make();
    clock.setLoop(false);
    feed(ds, 100, 50);
    flushLive();
    clock.goLive();
    act(clock);
    assert.equal(clock.following, false, String(act));
    const t = clock.t, end = clock.end;
    feed(ds, 106, 10);
    flushLive();
    assert.equal(clock.t, t, 'paused: t holds while data arrives');
    // the data's end grows (liveEnd); the drawn span holds still while paused (CONTRACT §26, d9e9223)
    assert.ok(clock.liveEnd > t);
    assert.equal(clock.end, end);
    assert.ok(clock.lag > 0);
  }
});

test('zoom or pan (setWindow) keeps following (Rerun 0.40)', () => {
  const { clock, ds } = make();
  feed(ds, 100, 50);
  flushLive();
  clock.setWindow([102, 104]);
  assert.equal(clock.following, true);
});

test('Space (toggle) while following pauses at t; it never jumps to live', () => {
  const { clock, ds } = make();
  feed(ds, 100, 50);
  flushLive();
  clock.toggle();
  assert.equal(clock.following, false);
  assert.equal(clock.playing, false);
  const t = clock.t;
  feed(ds, 105, 50);
  flushLive();
  assert.equal(clock.t, t);
  clock.seek(t - 2);
  clock.toggle();   // play: a replay from t, not a jump
  assert.equal(clock.playing, true);
  assert.equal(clock.following, false);
  assert.ok(Math.abs(clock.t - (t - 2)) < 1e-9);
});

test('a replay that catches up with the newest data rejoins following (decided 2026-10-27)', () => {
  const { clock, ds } = make();
  clock.setLoop(false);
  feed(ds, 100, 100);   // 100 .. 109.9
  flushLive();
  clock.seek(108);
  clock.setRate(4);
  clock.play();
  for (let i = 0; i < 60 && !clock.following; i++) tick(16);
  assert.equal(clock.following, true, `rejoined at t=${clock.t}, end=${clock.end}`);
  assert.equal(clock.t, clock.end);
});

test('play at the end of live data follows instead of starting over from the oldest data', () => {
  const { clock, ds } = make();
  feed(ds, 100, 30);
  flushLive();
  clock.pause();
  assert.equal(clock.t, clock.end);
  clock.play();
  assert.equal(clock.following, true);
  assert.equal(clock.t, clock.end);
});

test('goLive: one call from anywhere, no replay of the gap', () => {
  const { clock, ds } = make();
  feed(ds, 100, 30);
  flushLive();
  clock.seek(100.5);
  feed(ds, 103, 300);
  flushLive();
  let times = 0;
  clock.addEventListener('time', () => times++);
  clock.goLive();
  assert.equal(clock.following, true);
  assert.equal(clock.t, clock.end);
  assert.equal(times, 1, 'one time event: a jump, not a replay');
});

test('a recorded (finished) dataset is not live: no following, playback as a Clock', () => {
  const clock = new LiveClock();
  const ds = new LiveDataset({ properties: props, time: 't' });
  feed(ds, 0, 50);
  ds.finish();
  clock.bind(ds);
  flushLive();
  assert.equal(clock.live, false);
  assert.equal(clock.following, false);
  assert.equal(clock.start, 0);
  assert.ok(Math.abs(clock.end - 4.9) < 1e-9);
});

test('status: the clock reports its sources worst first', () => {
  const clock = new LiveClock();
  const a = new LiveDataset({ properties: props, time: 't' });
  const b = new LiveDataset({ properties: props, time: 't' });
  clock.bind(a); clock.bind(b);
  a.setStatus('live'); b.setStatus('reconnecting', 'try 2');
  assert.equal(clock.status().state, 'reconnecting');
  b.setStatus('live');
  assert.equal(clock.status().state, 'live');
  clock.unbind(b);
  assert.equal(clock.datasets.length, 1);
});

test('fmtTime: a Unix time reads as a wall-clock time; small times are unchanged', () => {
  assert.equal(fmtTime(3.2), '3.20 s');
  assert.equal(fmtTime(62.4), '1:02.40');
  const t = new Date(2026, 9, 27, 14, 3, 21, 400).getTime() / 1000;
  assert.equal(fmtTime(t), '14:03:21.40');
});
