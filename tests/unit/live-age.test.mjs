// a8, time-derived cells (docs/peps/0012-live-data.md, CONTRACT §26 `display: age`): how long ago, in plain words.
// Committed before the code it tests (with tests/browser/live_checks.py's ages_tick, which proves the tick in a page).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fmtAge, fmtClock } from '../../packages/core/src/format.js';

test('fmtAge: tenths under 10 s, seconds, minutes, hours, days; a negative age says "in", never 0', () => {
  assert.equal(fmtAge(0), '0.0 s ago');
  assert.equal(fmtAge(2.36), '2.4 s ago');
  assert.equal(fmtAge(12.4), '12 s ago');
  assert.equal(fmtAge(185), '3 min ago');
  assert.equal(fmtAge(5400), '1.5 h ago');
  assert.equal(fmtAge(3 * 86400), '3 d ago');
  assert.equal(fmtAge(-1.24), 'in 1.2 s');
  assert.equal(fmtAge(null), '');
  assert.equal(fmtAge(NaN), '');
});

test('fmtClock: Unix seconds as the local wall-clock time with milliseconds', () => {
  const t = new Date(2026, 9, 27, 14, 3, 21, 358).getTime() / 1000;
  assert.equal(fmtClock(t), '14:03:21.358');
  assert.equal(fmtClock('x'), '');
});
