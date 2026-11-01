// The KPI card's delta (packages/views/kpi/src/delta.js): a computed difference prints without float noise.
import test from 'node:test';
import assert from 'node:assert/strict';
import { deltaValue } from '../../packages/views/kpi/src/delta.js';

test('a computed delta loses its float noise, to the column decimals when it has some', () => {
  const d = 1.018 - 1.032; // -0.014000000000000012 in binary floating point
  assert.notEqual(d, -0.014);
  assert.equal(deltaValue(d), -0.014);
  assert.equal(deltaValue(d, 2), -0.01);
  assert.equal(deltaValue(2.41 - 2.582, 3), -0.172);
});

test('a delta without noise, zero and non-numbers pass through unchanged', () => {
  assert.equal(deltaValue(0.5), 0.5);
  assert.equal(deltaValue(0), 0);
  assert.equal(deltaValue(123456.789), 123456.789);
  assert.equal(deltaValue(null), null);
  assert.equal(deltaValue(Number.NaN), Number.NaN);
});
