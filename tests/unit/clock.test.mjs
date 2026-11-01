// The dashboard clock (docs/peps/0005-dashboard-cards.md §4): one writer of t, every follower in the same task.
import { test } from 'node:test';
import assert from 'node:assert/strict';
let frames = [];
globalThis.requestAnimationFrame = (f) => { frames.push(f); return frames.length; };
globalThis.cancelAnimationFrame = () => {};
const { Clock, followVideo, fmtTime, seriesColor } = await import('../../packages/core/src/clock.js');
const run = (ms) => { const f = frames; frames = []; for (const fn of f) fn(ms); };

test('seek clamps to the span and fires time synchronously with its source', () => {
  const c = new Clock({ start: 0, end: 8 });
  const seen = [];
  c.addEventListener('time', (e) => seen.push([e.detail.t, e.detail.source]));
  c.seek(3.2); c.seek(99); c.seek(-1, { source: 'url' });
  assert.deepEqual(seen, [[3.2, 'user'], [8, 'user'], [0, 'url']]);
});
test('extent: the union of the cards spans unless the .base declared it', () => {
  const c = new Clock();
  c.extent(1, 5); c.extent(0.5, 4); c.extent(2, 9);
  assert.deepEqual([c.start, c.end], [0.5, 9]);
  const d = new Clock({ start: 0, end: 7.9 }); d.extent(0, 100);
  assert.deepEqual([d.start, d.end], [0, 7.9]);
});
test('step lands on the frame grid: ten forward and ten back return to the same frame', () => {
  const c = new Clock({ start: 0, end: 10, fps: 30 });
  c.seek(1.01);
  for (let i = 0; i < 10; i++) c.step(1);
  for (let i = 0; i < 10; i++) c.step(-1);
  assert.ok(Math.abs(c.t - 30 / 30) < 1e-9, c.t);
});
test('play advances by dt × rate and loops inside the range', () => {
  const c = new Clock({ start: 0, end: 10, rate: 2 });
  c.setRange([2, 3]);
  assert.equal(c.t, 2);
  globalThis.performance = globalThis.performance || { now: () => 0 };
  c.play(); c._last = 0; run(200);   // 0.2 s × 2 = 0.4 s
  assert.ok(Math.abs(c.t - 2.4) < 1e-9, c.t);
  c._last = 200; run(450);           // + 0.5 s → 2.9
  c._last = 450; run(600);           // + 0.3 s → 3.2 → wraps to 2.2
  assert.ok(Math.abs(c.t - 2.2) < 1e-9, c.t);
  c.pause(); assert.equal(c.playing, false);
});
test('no loop: play stops at the end', () => {
  const c = new Clock({ start: 0, end: 1, loop: false });
  c.play(); c._last = 0; run(250); c._last = 250; run(500); c._last = 500; run(750); c._last = 750; run(1000); c._last = 1000; run(1250);
  assert.equal(c.t, 1); assert.equal(c.playing, false);
});
test('followVideo: paused seeks exactly; playing jumps past 0.1 s and nudges the rate between 0.04 and 0.1 s', () => {
  const c = new Clock({ start: 0, end: 10 });
  const v = { readyState: 4, duration: 8, currentTime: 0, paused: true, playbackRate: 1, pause() { this.paused = true; }, play() { this.paused = false; return Promise.resolve(); } };
  c.seek(3); followVideo(v, c, 0.5); assert.equal(v.currentTime, 2.5);
  c.playing = true; v.paused = false;
  v.currentTime = 2.5 + 0.2; followVideo(v, c, 0.5); assert.equal(v.currentTime, 2.5);          // jump
  v.currentTime = 2.5 + 0.06; followVideo(v, c, 0.5); assert.equal(v.playbackRate, 0.95);       // ahead: slow down
  v.currentTime = 2.5 - 0.06; followVideo(v, c, 0.5); assert.equal(v.playbackRate, 1.05);       // behind: speed up
  v.currentTime = 2.5 + 0.01; followVideo(v, c, 0.5); assert.equal(v.playbackRate, 1);
});
test('fmtTime and seriesColor', () => {
  assert.equal(fmtTime(3.2), '3.20 s');
  assert.equal(fmtTime(62.4), '1:02.40');
  assert.equal(seriesColor('tuned', { view: { style: { palette: { tuned: '#123456' } } } }), '#123456');
  const a = seriesColor('real', { tokens: { series: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] } });
  assert.equal(a, seriesColor('real', { tokens: { series: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] } }));
});

// ---- judge round 1 (reports/media/audits/2026-10-27-dashboards-judge-r1.md): ownership, seek generations, one
// driver, sub-ms paused seeks, loop ranges inside the span, the URL. One fake time for rAF and performance.now().
let wall = 0;
globalThis.performance = { now: () => wall };
const at = (ms) => { wall = ms; run(ms); };
const playingAt = (c, ms = 0) => { wall = ms; c.play(); c._last = ms; };
const { primaryDriver, readClockParams, writeClockParams } = await import('../../packages/core/src/clock.js');

test('a buffering primary keeps t: no wall advance while it owns t, and no backward jump when its frames resume (#1)', () => {
  const c = new Clock({ start: 0, end: 10 });
  c.setDriver('v');
  playingAt(c, 0);
  c.drive(1.0, 'v');
  for (const ms of [250, 500, 750, 1000, 1250]) at(ms);   // 1.25 s of rAF, no presented frame (waiting / seeking)
  assert.equal(c.t, 1.0);
  assert.equal(c.driver && c.driver.id, 'v');
  assert.equal(c.fallback, false);
  c.drive(1.033333, 'v');
  assert.equal(c.t, 1.033333);
  c.drive(1.02, 'v');                                      // a frame behind t never moves it back
  assert.equal(c.t, 1.033333);
});
test('a long stall (> 3 s without a frame) falls back to wall time in an explicit fallback state, and frames resuming behind t never move it back (#1)', () => {
  const c = new Clock({ start: 0, end: 20 });
  c.setDriver('v');
  playingAt(c, 0);
  c.drive(1.0, 'v');
  const states = [];
  c.addEventListener('state', () => states.push(c.fallback));
  for (let ms = 250; ms <= 3000; ms += 250) at(ms);
  assert.equal(c.t, 1.0);
  assert.equal(c.fallback, false);
  at(3250);                                                // 3.25 s held: fallback, and wall time runs t from this tick
  assert.equal(c.fallback, true);
  assert.deepEqual(states, [true]);
  assert.ok(Math.abs(c.t - 1.25) < 1e-9, c.t);
  at(3500);
  assert.ok(Math.abs(c.t - 1.5) < 1e-9, c.t);
  c.drive(1.1, 'v');                                       // the stalled video resumes behind t: t holds
  assert.ok(Math.abs(c.t - 1.5) < 1e-9, c.t);
  assert.equal(c.fallback, false);
  at(3750);
  assert.ok(Math.abs(c.t - 1.5) < 1e-9, c.t);              // owned again: no wall advance
  c.drive(1.533, 'v');
  assert.equal(c.t, 1.533);
});
test('release(id): a driver that ended, failed or was removed hands t to wall time from where it is; another id cannot release it (#1)', () => {
  const c = new Clock({ start: 0, end: 10 });
  c.setDriver('v');
  playingAt(c, 0);
  c.drive(2.0, 'v');
  c.release('other');
  at(250);
  assert.equal(c.t, 2.0);
  c.release('v');
  assert.equal(c.driver, null);
  at(500);
  assert.ok(Math.abs(c.t - 2.25) < 1e-9, c.t);
});
test('a frame armed before a seek is ignored: seek to 7, a pre-seek callback fires, t stays at 7; the next frame drives (#2)', () => {
  const c = new Clock({ start: 0, end: 10 });
  c.setDriver('v');
  playingAt(c, 0);
  c.drive(1.0, 'v');
  const armed = c.gen;
  c.seek(7);
  assert.notEqual(c.gen, armed);
  assert.equal(c.drive(1.033333, 'v', armed), false);
  assert.equal(c.t, 7);
  at(250); at(500);                                        // the seek is still landing: the video keeps t
  assert.equal(c.t, 7);
  c.drive(7.033333, 'v', c.gen);
  assert.equal(c.t, 7.033333);
  for (const source of ['url', 'step', 'user']) { const g = c.gen; c.seek(3, { source }); assert.notEqual(c.gen, g, source); }
});
test('one driver per clock: setDriver(id); drive() from any other id is ignored; null drives nothing (#3)', () => {
  const c = new Clock({ start: 0, end: 10 });
  c.setDriver('Tuned video');
  playingAt(c, 0);
  assert.equal(c.drive(4, 'Factory video'), false);
  assert.equal(c.t, 0);
  assert.equal(c.driver, null);
  assert.equal(c.drive(1, 'Tuned video'), true);
  assert.equal(c.t, 1);
  c.setDriver('Factory video');                            // re-designated: the old one's ownership ends
  assert.equal(c.driver, null);
  assert.equal(c.drive(2, 'Tuned video'), false);
  c.setDriver(null);
  assert.equal(c.drive(3, 'Factory video'), false);
  assert.equal(c.t, 1);
});
test('primaryDriver: clock.primary names the video, else the first video.primary card in layout order, else none (#3)', () => {
  const tuned = { type: 'video', name: 'Tuned video', video: { primary: true } };
  const factory = { type: 'video', name: 'Factory video', video: { primary: true } };
  const plain = { type: 'video', name: 'Real video', video: {} };
  const chart = { type: 'timeseries', name: 'Step response' };
  assert.equal(primaryDriver(null, [chart, tuned, factory]), 'Tuned video');
  assert.equal(primaryDriver({}, [chart, factory, tuned]), 'Factory video');
  assert.equal(primaryDriver({ primary: 'Real video' }, [tuned, plain]), 'Real video');
  assert.equal(primaryDriver({ primary: 'Real video' }, [plain]), 'Real video');
  assert.equal(primaryDriver({ primary: 'Step response' }, [chart, factory]), 'Factory video');   // not a video card
  assert.equal(primaryDriver({ primary: 'Gone' }, [plain, chart]), null);
  assert.equal(primaryDriver({}, [plain, chart]), null);
});
test('followVideo paused: every change of target is applied, also under 1 ms (1 → 1.0009 → 1) (#4)', () => {
  const c = new Clock({ start: 0, end: 10 });
  const v = { readyState: 4, duration: 8, currentTime: 0, paused: true, playbackRate: 1, pause() { this.paused = true; }, play() { this.paused = false; return Promise.resolve(); } };
  c.seek(1); followVideo(v, c); assert.equal(v.currentTime, 1);
  c.seek(1.0009); followVideo(v, c); assert.equal(v.currentTime, 1.0009);
  c.seek(1.0002); followVideo(v, c, 0); assert.equal(v.currentTime, 1.0002);
  c.seek(1); followVideo(v, c); assert.equal(v.currentTime, 1);
  c.seek(2.5); followVideo(v, c, 0.5); assert.equal(v.currentTime, 2);
});
test('setRange: intersected with the span, an empty intersection is no range, bounds are always [lo <= hi] inside the span (#6)', () => {
  const c = new Clock({ start: 0, end: 10 });
  c.setRange([20, 30]);
  assert.equal(c.range, null);
  assert.deepEqual(c.bounds, [0, 10]);
  c.setRange([5, 30]); assert.deepEqual(c.range, [5, 10]);
  c.setRange([-5, 3]); assert.deepEqual(c.range, [-0 + 0, 3]);
  c.setRange([10, 12]); assert.equal(c.range, null);       // touches the end only: empty
  c.setRange([4, 6]); assert.deepEqual(c.bounds, [4, 6]);
  c.setRange([6, 4]); assert.equal(c.range, null);
  // a range read before the span is known (a link opening before the cards report): re-intersected as the span lands
  const d = new Clock();
  d.setRange([2, 6]);
  d.extent(0, 4); assert.deepEqual(d.range, [2, 4]);
  d.extent(0, 10); assert.deepEqual(d.range, [2, 6]);
  const [lo, hi] = d.bounds; assert.ok(lo <= hi && lo >= d.start && hi <= d.end);
  d.setSpan(0, 1); assert.equal(d.range, null); assert.deepEqual(d.bounds, [0, 1]);
  const e = new Clock(); e.setRange([20, 30]); e.setSpan(0, 10);
  assert.equal(e.range, null);
  assert.deepEqual(e.bounds, [0, 10]);
});
test('clock URL params: plain t / tr on a page with one dashboard; t.<id> / tr.<id> with several, falling back to the plain ones (#5)', () => {
  const P = (s) => new URLSearchParams(s);
  assert.deepEqual(readClockParams(P('t=4.1&tr=2,6')), { t: 4.1, range: [2, 6], hasT: true, hasRange: true });
  assert.deepEqual(readClockParams(P('t=4.1&t.left=1.25&tr.left=1,2'), 'left'), { t: 1.25, range: [1, 2], hasT: true, hasRange: true });
  assert.deepEqual(readClockParams(P('t=4.1&t.left=1.25'), 'right'), { t: 4.1, range: null, hasT: true, hasRange: false });
  assert.deepEqual(readClockParams(P('t=x&tr=1'), null), { t: null, range: null, hasT: true, hasRange: true });
  const c = new Clock({ start: 0, end: 10 });
  c.seek(5); c.setRange([2, 6]);
  assert.equal(writeClockParams(P('s.a=x:1'), c).toString(), 's.a=x%3A1&t=5&tr=2%2C6');
  assert.equal(writeClockParams(P('t=3'), c, 'left').toString(), 't=3&t.left=5&tr.left=2%2C6');
  // a scoped dashboard at its start shadows a plain t= (so a reload does not bring the plain one back)
  const d = new Clock({ start: 0, end: 10 });
  assert.equal(writeClockParams(P('t=3&tr=1,2&t.left=4'), d, 'left').toString(), 't=3&tr=1%2C2&t.left=0&tr.left=');
  assert.deepEqual(readClockParams(P('t=3&tr=1,2&t.left=0&tr.left='), 'left'), { t: 0, range: null, hasT: true, hasRange: true });
  assert.equal(writeClockParams(P('t.left=4'), d, 'left').toString(), '');
  assert.equal(writeClockParams(P('t=4'), d).toString(), '');
});

// judge round 2 #1: every loop wrap (wall time, fallback, the driver at the end) bumps the seek generation and says
// it is a loop, so a frame callback armed before it is ignored and the driving clip seeks to the wrap point.
test('every loop wrap is a discontinuity: wall-time wrap and the range wrap bump gen and fire source loop (r2 #1)', () => {
  frames = [];
  const c = new Clock({ start: 0, end: 10 });
  const seen = [];
  c.addEventListener('time', (e) => seen.push(e.detail.source));
  c.seek(9.9);
  c.play(); c._last = 0;
  const g0 = c.gen;
  run(100);                                                // 9.9 + 0.1 = 10 → wraps to 0
  assert.ok(c.t < 1e-9, c.t);
  assert.ok(c.gen > g0, 'the wall-time wrap bumped the generation');
  assert.equal(seen.at(-1), 'loop');
  const g1 = c.gen;
  c._last = 100; run(300);                                 // an ordinary tick: same generation, source play
  assert.equal(c.gen, g1);
  assert.equal(seen.at(-1), 'play');
  c.setRange([2, 3]);
  c.seek(2.95);
  const g2 = c.gen;
  c._last = 300; run(400);                                 // 2.95 + 0.1 → wraps inside the range to 2.05
  assert.ok(Math.abs(c.t - 2.05) < 1e-9, c.t);
  assert.ok(c.gen > g2);
  assert.equal(seen.at(-1), 'loop');
  c.pause();
});

// judge round 2 #2: one view shown on two panels made two drivers (both clips had the view's name as id). The driver
// is one card INSTANCE: `<panel key>/<view name>`, the first panel in layout order that shows the chosen view.
test('driverInstance: primaryDriver\'s choice resolves to ONE panel instance, the first in layout order (r2 #2)', async () => {
  const core = await import('../../packages/core/src/clock.js');
  assert.equal(typeof core.driverInstance, 'function', 'driverInstance is exported');
  assert.equal(typeof core.driverKey, 'function', 'driverKey is exported');
  const video = { name: 'Video', type: 'video', video: { primary: true } };
  const chart = { name: 'Chart', type: 'timeseries' };
  const real = { name: 'Real video', type: 'video', video: {} };
  const pick = (spec, panels) => core.driverInstance(primaryDriver(spec, panels.flatMap((p) => p.views)), panels);
  const twice = [{ key: 'chart', views: [chart] }, { key: 'video', views: [video] }, { key: 'video-2', views: [video] }];
  assert.equal(pick({}, twice), 'video/Video');
  assert.equal(pick(null, twice), core.driverKey('video', 'Video'));
  assert.notEqual(core.driverKey('video', 'Video'), core.driverKey('video-2', 'Video'), 'two instances, two keys');
  const named = [{ key: 'v', views: [video] }, { key: 'r', views: [chart, real] }, { key: 'r-2', views: [real] }];
  // judge r3 #4: panel r shows Chart (its first tab), so its Real video is not on screen; r-2 is the first that shows it
  assert.equal(pick({ primary: 'Real video' }, named), 'r-2/Real video');
  assert.equal(pick({ primary: 'Chart' }, named), 'v/Video');   // not a video card: the flag rule
  assert.equal(pick({}, [{ key: 'c', views: [chart] }, { key: 'r', views: [real] }]), null);
  assert.equal(pick({}, []), null);
  assert.equal(core.driverInstance('Gone', twice), null, 'a name no panel shows designates nothing');
  assert.equal(core.driverInstance('Chart', twice), null, 'only a video card can be the driver');
  assert.equal(Clock.driverInstance('Video', twice), 'video/Video');
});

// judge round 2 #3: Back / Forward to a URL without t or tr kept the old ones (#t=4.5&tr=2,6 → #t=3 kept [2, 6] and
// rewrote the fragment to #t=3&tr=2,6). A navigation gives what a fresh load of that URL gives: an absent t is the
// clock's home (where a fresh clock sits), an absent or empty tr is no range; a malformed value leaves that part alone.
test('clockNavigation: absent t → home, absent or empty tr → no range, malformed → leave as is (r2 #3)', async () => {
  const { clockNavigation } = await import('../../packages/core/src/clock.js');
  assert.equal(typeof clockNavigation, 'function', 'clockNavigation is exported');
  const P = (s) => new URLSearchParams(s);
  assert.deepEqual(clockNavigation(P('t=4.5&tr=2,6')), { t: 4.5, range: [2, 6] });
  assert.deepEqual(clockNavigation(P('t=3')), { t: 3, range: 'none' });
  assert.deepEqual(clockNavigation(P('')), { t: 'home', range: 'none' });
  assert.deepEqual(clockNavigation(P('tr=2,6')), { t: 'home', range: [2, 6] });
  assert.deepEqual(clockNavigation(P('t=abc&tr=2,6')), { t: null, range: [2, 6] }, 'malformed t: leave t');
  assert.deepEqual(clockNavigation(P('t=3&tr=x')), { t: 3, range: null }, 'malformed tr: leave the range');
  assert.deepEqual(clockNavigation(P('t=3&tr=6,2')), { t: 3, range: null }, 'a reversed range is malformed');
  assert.deepEqual(clockNavigation(P('t=3&tr=2')), { t: 3, range: null });
  assert.deepEqual(clockNavigation(P('t=')), { t: null, range: 'none' }, 'an empty t is malformed');
  // scoped: t.<key> / tr.<key> first, the plain ones as the fallback; `tr.<key>=` (written to shadow a plain tr) is none
  assert.deepEqual(clockNavigation(P('t=3&tr=1,2&t.left=0&tr.left='), 'left'), { t: 0, range: 'none' });
  assert.deepEqual(clockNavigation(P('t=3&tr=1,2'), 'left'), { t: 3, range: [1, 2] });
  assert.deepEqual(clockNavigation(P('t.right=4'), 'left'), { t: 'home', range: 'none' });
});

test('clock.home(): where a fresh clock sits — 0 clamped to the span, then inside the range (r2 #3)', () => {
  const c = new Clock({ start: 0, end: 10 });
  assert.equal(typeof c.home, 'function');
  assert.equal(c.home(), 0);
  c.setRange([2, 6]);
  assert.equal(c.home(), 2, 'a fresh clock given tr=2,6 sits at 2');
  const fresh = new Clock({ start: 0, end: 10 }); fresh.setRange([2, 6]);
  assert.equal(fresh.t, c.home(), 'home is what a fresh load gives');
  // a fresh load as the dashboard does it: new Clock(), then setSpan from clock: data/time (or a card's first extent)
  const freshly = (lo, hi, how = 'span') => { const f = new Clock(); if (how === 'span') f.setSpan(lo, hi); else f.extent(lo, hi); return f; };
  for (const [lo, hi] of [[1.5, 9], [-2, 5], [0, 10]]) {
    for (const how of ['span', 'extent']) {
      const f = freshly(lo, hi, how);
      assert.equal(f.home(), f.t, `[${lo}, ${hi}] by ${how}: home ${f.home()} is where the fresh clock sits (${f.t})`);
    }
  }
  assert.equal(freshly(1.5, 9).home(), 1.5);
  assert.equal(freshly(-2, 5).home(), 0);
});

// judge round 3 #2: home() matched a fresh load only when the span arrived at once. Open #tr=2,6, then the cards report
// [5, 10] and [0, 10]: the fresh load ended at t = 5 (only the FIRST extent clamped t), a navigation to the same URL at
// t = 2. One rule now: until something asks for an instant, t is home(), re-placed every time the span or range moves;
// an asked instant (a seek, a link's t) is kept and re-clamped as the span is discovered.
test('an untouched clock stays at home() while extents arrive one at a time (r3 #2)', () => {
  const ranged = new Clock();
  ranged.setRange([2, 6]);
  ranged.extent(5, 10);
  assert.equal(ranged.t, 5, 'inside [5, 10] ∩ [2, 6]');
  ranged.extent(0, 10);
  assert.equal(ranged.t, ranged.home(), `t ${ranged.t} is home ${ranged.home()}`);
  assert.equal(ranged.t, 2);
  const plain = new Clock();
  plain.extent(5, 10);
  assert.equal(plain.t, 5);
  plain.extent(0, 10);
  assert.equal(plain.t, 0, 'the span grew to 0: home is 0 again');
  const declared = new Clock();
  declared.setSpan(5, 10); declared.setSpan(0, 10);
  assert.equal(declared.t, 0);
});

test('an asked instant is kept while extents arrive: a seek, then a span that grows to cover it (r3 #2)', () => {
  const c = new Clock();
  c.seek(7);
  c.extent(0, 5);
  assert.equal(c.t, 5, 'clamped while the span is [0, 5]');
  c.extent(0, 10);
  assert.equal(c.t, 7, 'the span now covers 7: the asked instant comes back');
  const d = new Clock();
  d.extent(0, 10);
  d.seek(8);
  d.extent(0, 20);
  assert.equal(d.t, 8, 'a later extent does not move an explicit seek');
  d.setRange([2, 6]);
  assert.equal(d.t, 2, 'a range that excludes t moves it to the range start');
  d.setRange(null);
  assert.equal(d.t, 2, 'clearing the range does not jump back to the old instant');
});

test('restore(): a fresh load and a navigation to the same link end in the same state, extents in any order (r3 #2)', async () => {
  const { clockNavigation } = await import('../../packages/core/src/clock.js');
  const P = (s) => new URLSearchParams(s);
  assert.equal(typeof new Clock().restore, 'function', 'clock.restore(link) exists');
  const link = (frag) => clockNavigation(P(frag));   // what the dashboard hands restore(), fresh load and navigation alike
  for (const frag of ['tr=2,6', '', 't=2&tr=2,6', 't=7', 't=1&tr=2,6', 't=4.5&tr=2,6']) {
    for (const spans of [[[0, 10]], [[5, 10], [0, 10]], [[0, 5], [0, 10]], [[6, 10], [0, 3], [0, 10]]]) {
      const fresh = new Clock();
      fresh.restore(link(frag));
      for (const [a, b] of spans) fresh.extent(a, b);
      const nav = new Clock();
      nav.extent(0, 10); nav.seek(9.5); nav.setRange([7, 9]);          // somewhere else first, as Back finds it
      nav.restore(link(frag));
      assert.deepEqual([nav.t, nav.range], [fresh.t, fresh.range], `#${frag} with extents ${JSON.stringify(spans)}`);
    }
  }
  // explicit seeks are kept: #t=7 opens at 7 even when the span reaches 7 only on its second extent
  const late = new Clock(); late.restore(link('t=7')); late.extent(0, 5); late.extent(0, 10);
  assert.equal(late.t, 7);
});

// judge round 3 #4: a panel with tabs [Table, Video] before a visible Video panel designated the tab that is not open
// (tabs/Video), so no card drove t. The driver is resolved against what each panel SHOWS (its open tab; the first
// view by default), re-resolved when a tab changes, and a chosen video that no open tab shows is a visible note.
test('driverInstance: only a panel whose open tab shows the video is eligible (r3 #4)', async () => {
  const { driverInstance } = await import('../../packages/core/src/clock.js');
  const table = { name: 'Table', type: 'table' };
  const video = { name: 'Video', type: 'video', video: { primary: true } };
  const panels = [{ key: 'tabs', views: [table, video] }, { key: 'video', views: [video] }];
  assert.equal(driverInstance('Video', panels), 'video/Video', 'by default a panel shows its first view');
  const open = { tabs: 'Table' };
  const shown = (p) => open[p.key] || p.views[0].name;
  assert.equal(driverInstance('Video', panels, shown), 'video/Video');
  open.tabs = 'Video';
  assert.equal(driverInstance('Video', panels, shown), 'tabs/Video', 'the tab opened: the first panel in layout order now shows it');
  assert.equal(driverInstance('Video', [{ key: 'tabs', views: [table, video] }]), null, 'no open tab shows it: nothing drives');
});

test('clock.setNote: a quiet note for the clock bar, announced with state; null clears it (r3 #4)', () => {
  const c = new Clock();
  let states = 0;
  c.addEventListener('state', () => { states += 1; });
  assert.equal(c.note, null);
  c.setNote('Video drives this clock, but no open tab shows it');
  assert.equal(c.note, 'Video drives this clock, but no open tab shows it');
  c.setNote('Video drives this clock, but no open tab shows it');
  c.setNote(null);
  assert.equal(c.note, null);
  assert.equal(states, 2, 'one state per change, none for the same note');
});
