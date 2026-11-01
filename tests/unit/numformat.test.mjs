// digits and compact: declared rounding for dashboards (Zach, 2026-10-26: "round the numbers"); stored values stay exact
// unless a .base or a card asks
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fmtNum, numOpts } from '../../packages/core/src/format.js';

test('no option: every stored digit (the truthful default is unchanged)', () => {
  assert.equal(fmtNum(0.9964028776978417), '0.9964028776978417');
  assert.equal(fmtNum(1149), '1,149');
});
test('digits: significant figures, never cutting the integer part', () => {
  assert.equal(fmtNum(0.9964028776978417, undefined, { digits: 3 }), '0.996');
  assert.equal(fmtNum(12345.678, undefined, { digits: 3 }), '12,346');
  assert.equal(fmtNum(0.30000000000000004, undefined, { digits: 3 }), '0.3');
  assert.equal(fmtNum(-0.0012345, undefined, { digits: 2 }), '-0.0012');
});
test('compact: 26,513 -> 26.5K, 563,000 -> 563K, 1.2e6 -> 1.2M; under 1,000 is not abbreviated', () => {
  assert.equal(fmtNum(26513, undefined, { compact: true }), '26.5K');
  assert.equal(fmtNum(563000, undefined, { compact: true }), '563K');
  assert.equal(fmtNum(1200000, undefined, { compact: true }), '1.2M');
  assert.equal(fmtNum(15.78, undefined, { compact: true }), '15.78');
  assert.equal(fmtNum(15.78123, undefined, { compact: true, digits: 3 }), '15.8');
});
test('numOpts: later sources win; junk is ignored', () => {
  assert.deepEqual(numOpts({ digits: 3 }, { compact: true }), { digits: 3, compact: true });
  assert.deepEqual(numOpts({ digits: 3 }, { digits: 5 }), { digits: 5 });
  assert.deepEqual(numOpts({ digits: 'x', compact: 1 }, null), {});
});
