// A property's declared digits / compact (CONTRACT §17 "Declared rounding") reach every place a value or a group is
// written, not only the KPI card: sim2real's {"value": 2.6799053096539507} with `properties: {value: {digits: 3}}` drew
// every digit in a table cell. tests/browser/digits_checks.py draws the views; this holds the pure writers they share.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { groupLabel, valueText, valueHtml, fmtNum, numOpts } from '../../packages/core/src/format.js';
import { properties } from '../../packages/core/src/rowmodel.js';

const STORED = 2.6799053096539507;

test('a .base properties entry carries digits and compact onto the dataset property', () => {
  const props = properties({ properties: { value: { type: 'number' } } }, { properties: { value: { digits: 3, compact: true } } });
  assert.equal(props.value.digits, 3);
  assert.equal(props.value.compact, true);
});

test('valueText and valueHtml write the declared digits and keep the stored value in the title', () => {
  const p = { id: 'value', type: 'number', digits: 3 };
  assert.equal(valueText(STORED, p), '2.68');
  const html = valueHtml(STORED, p);
  assert.match(html, />2\.68</);
});

test('a group header over a number reads the declared digits (every digit when none is declared)', () => {
  assert.equal(groupLabel({ value: { id: 'value', type: 'number', digits: 3 } }, 'value', STORED), '2.68');
  assert.equal(groupLabel({ value: { id: 'value', type: 'number', digits: 3 } }, 'value', 12345.678), '12,346');
  assert.equal(groupLabel({ big: { id: 'big', type: 'number', compact: true } }, 'big', 26513.4), '26.5K');
  assert.equal(groupLabel({ value: { id: 'value', type: 'number' } }, 'value', STORED), String(STORED));
  assert.equal(groupLabel({ value: { id: 'value', type: 'number' } }, 'value', 1149), '1149');
});

test('numOpts(property) is what every number site passes: digits, compact, never decimals', () => {
  assert.equal(fmtNum(STORED, undefined, numOpts({ digits: 3 })), '2.68');
  assert.equal(fmtNum(STORED, 3, numOpts({})), '2.680');
  assert.equal(fmtNum(26513.4, undefined, numOpts({ compact: true })), '26.5K');
});
