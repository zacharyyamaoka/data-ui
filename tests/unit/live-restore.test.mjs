// A link on a live clock, where the two lanes meet (written at the merge of lane/live into the packet, red first):
// lane/dashboard-cards' Clock places t by one rule, `restore(link)` and the asked instant (docs/CONTRACT.md §25);
// lane/live's LiveClock follows the newest data (§26), and its dashboard read a link as a seek, so "a link to a moment
// pauses there, #t=live (or none) follows". These pin that rule on the merged Clock: a fresh load and Back / Forward
// alike, and a range or span change re-places t from where live put it, never from a stale instant or home().
import { test } from 'node:test';
import assert from 'node:assert/strict';

let rafs = [];
globalThis.requestAnimationFrame = (fn) => { rafs.push(fn); return rafs.length; };
globalThis.cancelAnimationFrame = () => {};
let now = 0;
globalThis.performance = { now: () => now };
// the dashboard's live hooks import the whole live tier, whose <data-live-status> class extends HTMLElement at load
// (it registers itself only where customElements exists); a bare class is enough to import it in Node
globalThis.HTMLElement ??= class {};

const { clockNavigation } = await import('../../packages/core/src/clock.js');
const { LiveClock } = await import('../../packages/core/src/live/clock.js');
const { LiveDataset } = await import('../../packages/core/src/live/store.js');
const { flushLive } = await import('../../packages/core/src/live/frame.js');
const { liveNavigation } = await import('../../packages/dashboard/src/live.js');

const props = { t: { type: 'number' }, v: { type: 'number' } };
const feed = (ds, t0, n, dt = 0.1) => { const rows = []; for (let i = 0; i < n; i++) rows.push({ t: t0 + i * dt, v: i }); ds.append(rows); };
const following = () => {
  const clock = new LiveClock({ fps: 10 });
  const ds = new LiveDataset({ properties: props, time: 't' });
  clock.bind(ds);
  feed(ds, 100, 50);   // 100 .. 104.9
  flushLive();
  assert.equal(clock.following, true);
  assert.equal(clock.t, ds.end);
  return { clock, ds };
};
/** What the dashboard hands restore() for a fragment: core's clockNavigation, with live's own t kept. */
const nav = (hash) => { const p = new URLSearchParams(hash); return liveNavigation(clockNavigation(p), p); };

test('a link to a moment pauses there, and data arriving after it does not move t', () => {
  const { clock, ds } = following();
  clock.restore(nav('t=102.5'));
  assert.equal(clock.following, false);
  assert.equal(clock.playing, false);
  assert.equal(clock.t, 102.5);
  feed(ds, 105, 10);
  flushLive();
  assert.equal(clock.t, 102.5, 'paused at the link\'s moment while rows keep arriving');
  assert.ok(clock.lag > 0);
});

test('#t=live, or no t, follows the newest data: on a fresh load and on Back / Forward from a paused moment', () => {
  for (const hash of ['t=live', '']) {
    const { clock, ds } = following();
    clock.seek(101);
    assert.equal(clock.following, false);
    clock.restore(nav(hash));
    assert.equal(clock.following, true, `"${hash}" follows`);
    assert.equal(clock.t, ds.end);
    feed(ds, 105, 5);
    flushLive();
    assert.equal(clock.t, ds.end, `"${hash}": t keeps up with the data`);
  }
});

test('a range asked while following holds t when the range contains it (the asked instant is the newest data)', () => {
  const { clock, ds } = following();
  const end = clock.t;
  clock.setRange([100.5, end]);
  assert.equal(clock.following, false);
  assert.equal(clock.t, end, 'not home() and not the range start: t was the newest data and the range keeps it');
  void ds;
});

test('with no live dataset bound a LiveClock restores exactly as a Clock; #t=live reads as no t there', () => {
  const c = new LiveClock();
  c.setSpan(0, 10);
  c.restore(clockNavigation(new URLSearchParams('t=4&tr=2,6')));
  assert.equal(c.t, 4);
  assert.deepEqual(c.range, [2, 6]);
  const p = new URLSearchParams('t=live');
  c.restore(liveNavigation(clockNavigation(p), p));
  assert.equal(c.range, null, 'no tr: no range');
  assert.equal(c.t, 0, 'no t is home(): 0 clamped to the span');
});
