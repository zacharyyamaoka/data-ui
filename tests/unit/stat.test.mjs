// The stat cards' arithmetic (packages/views/kpi/src/stat-model.js): scales, bands, the arc, the bar list's order and
// widths, the tracker's tones. The drawing is measured in the browser by gallery/examples/dashboard-cards/checks_stat.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fraction, niceMax, bandSegments, bandTone, againstTarget, arcPoint, arcPath, barlistRows, shadeLevels, stateTone } from '../../packages/views/kpi/src/stat-model.js';
import { fmtNum, numOpts } from '../../packages/core/src/format.js';

test('fraction: where a value sits on a scale, clipped and said so; a scale that is not one is null', () => {
  assert.deepEqual(fraction(0.25, 0, 1), { f: 0.25, clipped: null });
  assert.deepEqual(fraction(124, 0, 60), { f: 1, clipped: 'high' });
  assert.deepEqual(fraction(-3, 0, 60), { f: 0, clipped: 'low' });
  assert.equal(fraction(1, 5, 5), null);
  assert.equal(fraction(null, 0, 1), null);
});

test('niceMax: the next of 1, 2, 2.5, 5, 10 x 10^k', () => {
  assert.equal(niceMax(0.9), 1);
  assert.equal(niceMax(1), 1);
  assert.equal(niceMax(3.2), 5);
  assert.equal(niceMax(124.4), 200);
  assert.equal(niceMax(0), 1);
});

test('bandSegments: the last band runs to max; a value on a band edge belongs to the band below', () => {
  const bands = [{ to: 0.5, tone: 'bad' }, { to: 0.9, tone: 'warn' }, { tone: 'good' }];
  const segs = bandSegments(bands, 0, 1);
  assert.deepEqual(segs.map((s) => [s.from, s.to, s.tone]), [[0, 0.5, 'bad'], [0.5, 0.9, 'warn'], [0.9, 1, 'good']]);
  assert.equal(bandTone(bands, 0.5), 'bad');
  assert.equal(bandTone(bands, 0.5001), 'warn');
  assert.equal(bandTone(bands, 0.95), 'good');
  assert.equal(bandTone([], 0.5), null);
  // numbers as a bullet gives them: [5, 20, 60] over 0..60
  assert.deepEqual(bandSegments([5, 20, 60].map((to) => ({ to })), 0, 60).map((s) => [s.f0, s.f1]), [[0, 5 / 60], [5 / 60, 20 / 60], [20 / 60, 1]]);
});

test('againstTarget: over / under, and whether that side is the better one', () => {
  assert.deepEqual(againstTarget(0.25, 0.9, 'higher'), { dir: 'under', diff: 0.65, good: false });
  assert.equal(againstTarget(0.4059, 5, 'lower').good, true);
  assert.equal(againstTarget(124, 5, 'lower').good, false);
  assert.equal(againstTarget(5, 5, 'lower').dir, 'on');
  assert.equal(againstTarget(1, null), null);
});

test('arc: f = 0 is the left end, f = 1 the right, f = 0.5 the top; the path ends where the points say', () => {
  const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} vs ${b}`);
  const [x0, y0] = arcPoint(100, 100, 84, 0), [x1, y1] = arcPoint(100, 100, 84, 1), [xt, yt] = arcPoint(100, 100, 84, 0.5);
  near(x0, 16); near(y0, 100); near(x1, 184); near(y1, 100); near(xt, 100); near(yt, 16);
  assert.equal(arcPath(100, 100, 84, 0, 1), 'M16.00,100.00A84,84 0 0 1 184.00,100.00');
  assert.equal(arcPath(100, 100, 84, 0.3, 0.3), '');
  assert.match(arcPath(100, 100, 84, 0, 0.75), /A84,84 0 0 1 /);
});

test('barlistRows: largest first, smallest first when lower is better, bars over the max of ALL entries, a limit and the rest', () => {
  const entries = [{ label: 'b', value: 90 }, { label: 'a', value: 835 }, { label: 'n', value: null }, { label: 'c', value: 6 }, { label: 'd', value: 6 }, { label: 'z', value: 0 }];
  const desc = barlistRows(entries, { limit: 3 });
  assert.deepEqual(desc.rows.map((r) => r.label), ['a', 'b', 'c']);
  assert.deepEqual(desc.rest.map((r) => r.label), ['d', 'z', 'n'], 'ties keep input order; a missing value goes last');
  assert.equal(desc.max, 835);
  assert.ok(Math.abs(desc.rows[1].frac - 90 / 835) < 1e-12);
  const asc = barlistRows([{ label: 'factory', value: 86.7 }, { label: 'oracle', value: 0.2 }, { label: 'tuned', value: 0.43 }], { better: 'lower' });
  assert.deepEqual(asc.rows.map((r) => r.label), ['oracle', 'tuned', 'factory']);
  assert.equal(asc.rows[2].frac, 1);
  assert.equal(asc.rest.length, 0);
});

test('shadeLevels: the worst band is the darkest', () => {
  assert.deepEqual(shadeLevels(3, 'lower'), [0, 1, 2]);
  assert.deepEqual(shadeLevels(3, 'higher'), [2, 1, 0]);
});

test('stateTone: the declared tone; a missing state is muted; one the map does not list is neutral', () => {
  const tones = { pass: 'good', fail: 'bad', mixed: 'warn', none: 'muted' };
  assert.equal(stateTone('pass', tones), 'good');
  assert.equal(stateTone('none', tones), 'muted');
  assert.equal(stateTone(null, tones), 'muted');
  assert.equal(stateTone('flaky', tones), 'neutral');
  assert.equal(stateTone('x', { x: 'purple' }), 'neutral');
});

test('compact numbers the cards print: 26,513 is 26.5K under style.numbers {digits 3, compact}; 835 stays 835', () => {
  const opts = numOpts({ digits: 3, compact: true });
  assert.equal(fmtNum(26513, undefined, opts), '26.5K');
  assert.equal(fmtNum(835, undefined, opts), '835');
  assert.equal(fmtNum(0.4059, undefined, opts), '0.406');
});

// the arc gauge over 0.5 drew its fill the long way round (found by the Vibe Tracks lane, 2026-10-26): a semicircle's
// arc never spans more than 180°, so SVG's large-arc flag is always 0
test('arcPath: an arc of more than half the semicircle keeps the short way (large-arc flag 0), its end on the gauge', async () => {
  const { arcPath, arcPoint } = await import('../../packages/views/kpi/src/stat-model.js');
  for (const f of [0.25, 0.574, 0.9, 1]) {
    const d = arcPath(100, 100, 80, 0, f);
    const m = /A80,80 0 (\d) 1 ([\d.-]+),([\d.-]+)$/.exec(d);
    assert.ok(m, d);
    assert.equal(m[1], '0', `f=${f}: ${d}`);
    const [x, y] = arcPoint(100, 100, 80, f);
    assert.ok(Math.abs(Number(m[2]) - x) < 0.01 && Math.abs(Number(m[3]) - y) < 0.01);
  }
});
