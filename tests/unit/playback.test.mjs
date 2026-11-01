// The playback proposals' arithmetic (packages/views/playback/src/model.js, docs/peps/0005-dashboard-cards.md §4b):
// Rerun's events and streams, YouTube's chapters, the sparkline decimation and path, and the text each proposal
// prints. The drawing is measured in the browser by gallery/examples/playback-proposals/checks.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { niceTicks, niceStep, eventTimes, nextEvent, prevEvent, streamsOf, tickColumns, decimate, sparkPath, chaptersOf, chapterAt,
  rerunTime, rerunSpeed, parseTime, parseSpeed, ytTime, timecode, foxTime, spanText, isClip, plain } from '../../packages/views/playback/src/model.js';

const ds = {
  samples: { rows: [{ t: 0, q: 1, s: 'a' }, { t: 0.5, q: 2, s: 'a' }, { t: 0.5, q: null, s: 'b' }, { t: 1.25, q: { value: 3 }, err: 4, s: 'b' }] },
  tool: { rows: [{ t: 0.1, px: 1 }, { t: 2, px: 2 }] },
  kpis: { rows: [{ id: 'x', v: 1 }] },
  series: { rows: [{ t: '2026-10-11T21:05:59Z', value: 1 }] },
  media: { rows: [{ id: 'm1', situation: 'tuned', src: 'media/a.mp4', t0: 0, duration: 7.9 }, { id: 'm2', src: 'media/b.webm?x=1', t0: 0.5, duration: 2 }] },
};

test('niceTicks / niceStep: 1-2-5 steps that include an end landing on a float', () => {
  assert.deepEqual(niceTicks(0, 7.9, 8), [0, 1, 2, 3, 4, 5, 6, 7]);
  assert.deepEqual(niceTicks(0.30000000000000004, 0.9, 6), [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]);
  assert.equal(niceStep(0, 7.9, 4), 2);
  assert.deepEqual(niceTicks(3, 3), [3]);
});

test('events: the distinct numeric times of every time-aware dataset, sorted; ISO-string and time-less datasets are not events', () => {
  const ev = eventTimes(ds, 't');
  assert.deepEqual(ev, [0, 0.1, 0.5, 1.25, 2]);
  assert.equal(nextEvent(ev, 0.5), 1.25);
  assert.equal(nextEvent(ev, 0.49), 0.5);
  assert.equal(prevEvent(ev, 0.5), 0.1);
  assert.equal(nextEvent(ev, 2), null);
  assert.equal(prevEvent(ev, 0), null);
});

test('streams: one node per time-aware dataset, a child per numeric column (cells may be {value}), a clip dataset by clip', () => {
  const s = streamsOf(ds, 't');
  assert.deepEqual(s.map((n) => n.name), ['samples', 'tool', 'media']);
  const samples = s[0];
  assert.deepEqual([samples.t0, samples.t1], [0, 1.25]);
  assert.deepEqual(samples.children.map((c) => [c.name, c.t0, c.t1, c.times.length]), [['q', 0, 1.25, 3], ['err', 1.25, 1.25, 1]]);
  const media = s[2];
  assert.equal(media.kind, 'video');
  assert.deepEqual(media.children.map((c) => [c.name, c.t0, c.t1]), [['tuned', 0, 7.9], ['m2', 0.5, 2.5]]);
  assert.deepEqual([media.t0, media.t1], [0, 7.9]);
  assert.ok(isClip(ds.media.rows[1]) && !isClip({ src: 'a.png' }));
  assert.equal(plain({ value: 2, basis: 'x' }), 2);
});

test('tickColumns: distinct pixel columns, or null when the ticks are too dense to read apart (a solid bar)', () => {
  assert.deepEqual(tickColumns([0, 0.5, 1], 0, 1, 100), [0, 50, 100]);
  assert.equal(tickColumns(Array.from({ length: 400 }, (_, i) => i / 399), 0, 1, 300), null);
  assert.deepEqual(tickColumns([1], 1, 1, 100), []);
});

test('decimate keeps each bucket\'s min and max in t order; sparkPath maps to a 1000 × 100 box and breaks at null', () => {
  const pts = Array.from({ length: 1000 }, (_, i) => [i / 100, i === 500 ? 99 : Math.sin(i / 50)]);
  const d = decimate(pts, 50);
  assert.ok(d.length <= 100 && d.length > 50);
  assert.ok(d.some((p) => p[1] === 99), 'the spike survives');
  for (let i = 1; i < d.length; i++) assert.ok(d[i][0] >= d[i - 1][0]);
  assert.equal(sparkPath([[0, 0], [5, 10], [10, null], [10, 5]], 0, 10, 0, 10), 'M0.0 100.0L500.0 0.0M1000.0 50.0');
});

test('chapters: a new chapter where a held signal starts moving (holds ≥ 0.2 s), titled Move 1, Move 2 …', () => {
  // a step target: move 0-0.5, hold to 1.4, move to 1.6, hold to 2, a 0.1 s blip hold, move, hold to 3
  const v = (t) => (t <= 0.5 ? t : t <= 1.4 ? 0.5 : t <= 1.6 ? 0.5 + (t - 1.4) : t <= 2 ? 0.7 : t <= 2.1 ? 0.7 + (t - 2) : t <= 2.2 ? 0.8 : t <= 2.4 ? 0.8 + (t - 2.2) : 1);
  const pts = Array.from({ length: 151 }, (_, i) => +(i * 0.02).toFixed(2)).map((t) => [t, +v(t).toFixed(6)]);
  const ch = chaptersOf(pts, 0, 3);
  assert.deepEqual(ch.map((c) => c.t0), [0, 1.4, 2]);
  assert.deepEqual(ch.map((c) => c.title), ['Move 1', 'Move 2', 'Move 3']);
  assert.equal(ch[2].t1, 3);
  assert.equal(chapterAt(ch, 1.5).title, 'Move 2');
  assert.equal(chapterAt(ch, 3).title, 'Move 3');
  assert.deepEqual(chaptersOf([], 0, 1).map((c) => [c.t0, c.t1]), [[0, 1]]);
});

test('the text each proposal prints, and what a typed field parses to', () => {
  assert.equal(rerunTime(3.2), '+3.20s');
  assert.equal(rerunTime(-0.5), '−0.50s');
  assert.equal(rerunSpeed(1), '1.00x');
  assert.equal(parseTime('+3.2s'), 3.2);
  assert.equal(parseTime(' 4.5 '), 4.5);
  assert.equal(parseTime('1:02.5'), 62.5);
  assert.equal(parseTime('−1s'), -1);
  assert.equal(parseTime('abc'), null);
  assert.equal(parseTime(''), null);
  assert.equal(parseSpeed('1.5x'), 1.5);
  assert.equal(parseSpeed('2×'), 2);
  assert.equal(parseSpeed('0'), null);
  assert.equal(parseSpeed('fast'), null);
  assert.equal(ytTime(3.99), '0:03');
  assert.equal(ytTime(62), '1:02');
  assert.equal(ytTime(3723), '1:02:03');
  assert.equal(timecode(3.2, 30), '00:00:03:06');
  assert.equal(timecode(61 + 29 / 30, 30), '00:01:01:29');
  assert.equal(foxTime(3.2, 0, 'seconds'), '3.200');
  assert.equal(foxTime(3.2, 0, 'elapsed'), '00:03.200');
  assert.equal(foxTime(65.5, 0.5, 'elapsed'), '01:05.000');
  assert.equal(spanText(1.2, 3.4), '1.20 – 3.40 s (2.20 s)');
});

test('the variant registry: one create(host, el, clock, ctx) per name, listed in order; a second registration throws', async () => {
  const R = await import('../../packages/views/playback/src/registry.js');
  const made = [];
  R.registerPlaybackVariant('test-live', { label: 'Live', create: (host, el, clock, ctx) => { made.push([host, el, clock, ctx]); return { update() {}, destroy() {} }; } });
  assert.equal(R.playbackVariant('test-live').label, 'Live');
  assert.ok(R.playbackVariants().some((v) => v.name === 'test-live'));
  const v = R.playbackVariant('test-live').create('h', 'e', 'c', { name: 'test-live' });
  assert.equal(typeof v.update, 'function');
  assert.deepEqual(made[0], ['h', 'e', 'c', { name: 'test-live' }]);
  assert.throws(() => R.registerPlaybackVariant('test-live', { create() {} }), /already registered/);
  assert.throws(() => R.registerPlaybackVariant('x', {}), /create/);
  assert.equal(R.playbackVariant('nope'), null);
});
