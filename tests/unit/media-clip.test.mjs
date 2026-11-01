// The media cards' Clip (packages/views/media/src/clip.js) on a real Clock with a scripted <video>: the primary's
// requestVideoFrameCallback driving, seek generations, release on ended / error / destroy, one driver
// (docs/peps/0005-dashboard-cards.md §4; judge round 1 #1-#3, reports/media/audits/2026-10-27-dashboards-judge-r1.md).
// The browser half (a real <video>) is gallery/examples/dashboard-cards/checks_dashboard.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
let frames = [], wall = 0;
globalThis.requestAnimationFrame = (f) => { frames.push(f); return frames.length; };
globalThis.cancelAnimationFrame = () => {};
globalThis.performance = { now: () => wall };
const at = (ms) => { wall = ms; const f = frames; frames = []; for (const fn of f) fn(ms); };

/** A <video> that does what the clock asks and nothing else: currentTime writes start a seek that `land()` completes. */
class FakeVideo extends EventTarget {
  constructor() {
    super();
    Object.assign(this, { readyState: 4, duration: 8, paused: true, seeking: false, playbackRate: 1, muted: false, dataset: {}, _t: 0, vfc: new Map(), _n: 0 });
    this.seekable = { length: 1, end: () => this.duration };
  }
  get currentTime() { return this._t; }
  set currentTime(v) { this._t = v; this.seeking = true; }
  land() { this.seeking = false; this.dispatchEvent(new Event('seeked')); }
  play() { this.paused = false; return Promise.resolve(); }
  pause() { this.paused = true; }
  setAttribute() {} removeAttribute() {} hasAttribute() { return false; } getAttribute() { return null; } load() {}
  requestVideoFrameCallback(f) { this._n += 1; this.vfc.set(this._n, f); return this._n; }
  cancelVideoFrameCallback(id) { this.vfc.delete(id); }
  /** Present one frame: every pending callback gets (now, {mediaTime}). */
  present(mediaTime) { const cbs = [...this.vfc.values()]; this.vfc.clear(); for (const f of cbs) f(wall, { mediaTime }); }
}
globalThis.document = { createElement: () => new FakeVideo() };

const shim = `export { isNum } from ${JSON.stringify(join(ROOT, 'packages/core/src/format.js'))};
export { followVideo } from ${JSON.stringify(join(ROOT, 'packages/core/src/clock.js'))};`;
const out = await build({
  stdin: { contents: `export { Clip } from './clip.js';`, resolveDir: join(ROOT, 'packages/views/media/src') },
  bundle: true, write: false, format: 'esm', platform: 'node', logLevel: 'silent',
  plugins: [{ name: 'shim', setup(b) {
    b.onResolve({ filter: /^@data-ui\/core$/ }, () => ({ path: 'core', namespace: 'shim' }));
    b.onLoad({ filter: /^core$/, namespace: 'shim' }, () => ({ contents: shim, loader: 'js', resolveDir: ROOT }));
  } }],
});
const { Clip } = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString('base64')}`);
const { Clock } = await import('../../packages/core/src/clock.js');

/** A clip on the clock's events, as the media cards wire it (ClockCard in index.js). */
function wired(clock) {
  const clip = new Clip(clock);
  clock.addEventListener('time', (e) => clip.onTime(e.detail.source));
  clock.addEventListener('state', () => clip.onState());
  return clip;
}

/** A clock playing with `id` designated, and its clip loaded at t0 = 0 and presenting frames. */
function playing(id = 'Tuned video') {
  frames = []; wall = 0;
  const clock = new Clock({ start: 0, end: 10, fps: 30 });
  clock.setDriver(id);
  const clip = wired(clock);
  clip.set({ src: 'a.mp4', poster: null, t0: 0, id });
  clip.show();
  clock.seek(1);
  clip.video.land();
  clock.play(); clock._last = 0;
  return { clock, clip, v: clip.video };
}

test('the designated clip drives t from its presented frames (mediaTime + t0)', () => {
  const { clock, v } = playing();
  assert.equal(v.paused, false);
  v.present(1.033333);
  assert.equal(clock.t, 1.033333);
  assert.equal(clock.driver.id, 'Tuned video');
  v.present(1.066667);
  assert.equal(clock.t, 1.066667);
});

test('a stale frame callback cannot undo a seek: seek to 7, the pre-seek callback fires, t stays 7; driving resumes after seeked (#2)', () => {
  const { clock, v } = playing();
  v.present(1.0);
  const stale = [...v.vfc.values()][0];                    // armed before the seek, as the judge injected it
  assert.ok(stale, 'a callback is pending while playing');
  clock.seek(7);
  assert.equal(v.currentTime, 7);
  assert.equal(v.seeking, true);
  stale(wall, { mediaTime: 1.033333 });
  assert.equal(clock.t, 7);
  at(250); at(500);                                        // still seeking: t is held, not run on wall time
  assert.equal(clock.t, 7);
  assert.equal(v.vfc.size, 0, 'nothing is armed until the seek lands');
  v.land();
  assert.equal(v.vfc.size, 1, 'seeked arms the next frame');
  v.present(7.033333);
  assert.equal(clock.t, 7.033333);
});

test('buffering keeps ownership: no frame for 1 s (waiting), t holds; the next frame continues forward (#1)', () => {
  const { clock, v } = playing();
  v.present(1.5);
  for (const ms of [250, 500, 750, 1000]) at(ms);
  assert.equal(clock.t, 1.5);
  v.present(1.533333);
  assert.equal(clock.t, 1.533333);
});

test('ended, error and destroy release the clock: wall time runs t from where it is (#1)', () => {
  for (const how of ['ended', 'error', 'destroy']) {
    const { clock, clip, v } = playing();
    v.present(2.0);
    if (how === 'destroy') clip.destroy(); else v.dispatchEvent(new Event(how));
    assert.equal(clock.driver, null, how);
    at(250);
    assert.ok(Math.abs(clock.t - 2.25) < 1e-9, `${how}: ${clock.t}`);
    if (how === 'error') { at(500); assert.ok(clock.t > 2.25, 'a failed clip does not take t back'); }
  }
});

test('one driver: a second primary clip on the same clock never drives; it follows (#3)', () => {
  const { clock, v } = playing('Tuned video');
  const other = wired(clock);
  other.set({ src: 'b.mp4', poster: null, t0: 0, id: 'Factory video' });
  other.show();
  v.present(1.2);
  assert.equal(other.primary, false);
  assert.equal(other.video.vfc.size, 0, 'the follower arms no frame callback');
  assert.equal(clock.drive(5, 'Factory video', clock.gen), false);
  assert.equal(clock.t, 1.2);
});

// judge round 2 #1 (reports/media/audits/2026-10-28-dashboards-judge-r2.md): a loop wrap is a discontinuity like a
// seek. Before the fix the fallback wrap ran through seek(t, {source: 'play'}), which keeps the generation, so a
// callback armed before the wrap drove t from 0.4 back to 9.933333.
test('a fallback loop wrap is a new generation: the pre-wrap callback cannot pull t back to the end (r2 #1)', () => {
  const { clock, clip, v } = playing();
  v.duration = 10;
  v.present(9.9);
  assert.equal(clock.t, 9.9);
  const stale = [...v.vfc.values()][0];                    // armed before the wrap, as the judge captured it
  assert.ok(stale, 'a callback is pending while playing');
  const before = clock.gen;
  for (let ms = 250; ms <= 3500; ms += 250) { clock._last = ms - 250; at(ms); }   // no frame for 3.5 s
  assert.equal(clock.fallback, true, 'past STALL the clock runs on wall time');
  assert.ok(Math.abs(clock.t - 0.4) < 1e-9, `wrapped to 0.4, got ${clock.t}`);
  assert.ok(clock.gen > before, 'the wrap started a new generation');
  // the wrap tick was 3250 ms (10.15 → 0.15); the video is still seeking there when t reaches 0.4, so it is not re-sent
  assert.ok(Math.abs(v.currentTime - 0.15) < 1e-9, `the driving video was sent to the wrap point, at ${v.currentTime}`);
  assert.equal(v.vfc.size, 0, 'the pre-wrap callback was cancelled');
  stale(wall, { mediaTime: 9.933333 });
  assert.ok(clock.t < 1, `the pre-wrap frame was accepted: t = ${clock.t}`);
  assert.equal(clock.drive(9.933333, clip.id, before), false, 'the old generation is refused by the clock too');
  assert.ok(clock.t < 1, `t = ${clock.t}`);
});

test('the first frame after a wrap drives again: seeked re-arms, the new generation drives t forward from the wrap point (r2 #1)', () => {
  const { clock, v } = playing();
  v.duration = 10;
  v.present(9.9);
  for (let ms = 250; ms <= 3500; ms += 250) { clock._last = ms - 250; at(ms); }
  assert.ok(Math.abs(clock.t - 0.4) < 1e-9, clock.t);
  assert.equal(v.seeking, true, 'the video is seeking to the wrap point');
  assert.equal(v.vfc.size, 0, 'nothing is armed while the wrap seek lands');
  v.land();
  assert.equal(v.vfc.size, 1, 'seeked arms the first frame after the wrap');
  v.present(0.433333);
  assert.equal(clock.t, 0.433333);
  assert.equal(clock.fallback, false, 'a frame of the new generation ends the fallback');
  assert.equal(clock.driver.id, 'Tuned video');
});

test('a driven loop at the end is a new generation too: a callback armed before it is refused (r2 #1)', () => {
  const { clock, v } = playing();
  v.duration = 10;
  v.present(9.9995);                                       // the driver reached the end (within 1 ms)
  const stale = [...v.vfc.values()][0];
  const before = clock.gen;
  clock._last = 0; at(16);
  assert.equal(clock.t, 0, 'looped to the start');
  assert.ok(clock.gen > before, 'the loop started a new generation');
  stale(wall, { mediaTime: 9.999 });
  assert.equal(clock.t, 0, `t = ${clock.t}`);
  v.land();
  v.present(0.033333);
  assert.equal(clock.t, 0.033333);
});

test('the fallback follow jump cancels the pre-jump callback: a frame presented mid-jump does not end the fallback; seeked re-arms (r2 #1, sibling path)', () => {
  const { clock, v } = playing();
  v.duration = 10;
  v.present(5.0);
  for (let ms = 250; ms <= 3250; ms += 250) { clock._last = ms - 250; at(ms); }   // past STALL: fallback, t = 5.25
  assert.equal(clock.fallback, true);
  assert.equal(v.seeking, true, 'the stalled video was sent to t');
  assert.equal(v.vfc.size, 0, 'the callback armed before the jump is cancelled');
  v.present(5.033333);                                     // a frame of the old position reaches the compositor
  assert.equal(clock.fallback, true, 'a pre-jump frame does not end the fallback');
  v.land();
  assert.equal(v.vfc.size, 1, 'seeked arms the next frame');
  v.present(5.3);
  assert.equal(clock.t, 5.3);
  assert.equal(clock.fallback, false);
});

test('one view on two panels: two instance keys, only the designated instance drives; the other\'s ended does not release it (r2 #2)', () => {
  const a = 'video/Video', b = 'video-2/Video';
  const { clock, clip: A, v } = playing(a);
  const B = wired(clock);
  B.set({ src: 'a.mp4', poster: null, t0: 0, id: b });
  B.show();
  assert.equal(A.primary, true);
  assert.equal(B.primary, false);
  v.present(1.0);
  assert.equal(clock.t, 1.0);
  assert.equal(B.video.vfc.size, 0, 'the second instance arms no frame callback');
  assert.equal(clock.drive(1.3, b, clock.gen), false, 'the second instance cannot drive');
  B.video.dispatchEvent(new Event('ended'));
  assert.equal(clock.driver && clock.driver.id, a, 'the second instance ending leaves the first one driving');
  v.present(1.033333);
  assert.equal(clock.t, 1.033333);
});
