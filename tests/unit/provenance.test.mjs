// data-provenance on a rich cell's .dv-value (packages/core/src/format.js provenanceAttr, docs/CONTRACT.md §22)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { valueHtml } from '../../packages/core/src/format.js';

const attrOf = (html) => {
  const m = /data-provenance="([^"]*)"/.exec(html);
  return m ? JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')) : null;
};

test('a rich cell with a source emits data-provenance with the value as shown and every field it has', () => {
  const html = valueHtml({ value: 5.5, unit: 'N·m', basis: 'seller', source: 'aifitlab.com', sourceUrl: 'https://www.aifitlab.com/p/1', sourcePage: '/parts/1', asOf: '2026-10-22',
    record: 'aifitlab-8541438771336 · specs.rated_torque_nm', note: 'rated, not peak' }, {});
  assert.deepEqual(attrOf(html), {
    value: '5.5', unit: 'N·m', basis: 'seller', source: 'aifitlab.com', sourceUrl: 'https://www.aifitlab.com/p/1', sourcePage: '/parts/1', asOf: '2026-10-22',
    record: 'aifitlab-8541438771336 · specs.rated_torque_nm', note: 'rated, not peak',
  });
  assert.match(html, /<span class="dv-value" title="[^"]*" data-provenance="/, 'one attribute on the dv-value span, after the title');
  assert.match(html, /title="5\.5 N·m\nseller/, 'the title is unchanged');
});

test('empty keys are left out; the value is the text the cell shows (formatted, with the property unit)', () => {
  const html = valueHtml({ value: 1149.5, source: 'steadywin.cn', sourceUrl: '', note: null }, { unitText: 'g' });
  assert.deepEqual(attrOf(html), { value: '1,149.5', unit: 'g', source: 'steadywin.cn' });
});

test('a basis alone is enough; as-of alone and a record alone too', () => {
  assert.deepEqual(attrOf(valueHtml({ value: 3, basis: 'measured' }, {})), { value: '3', basis: 'measured' });
  assert.deepEqual(attrOf(valueHtml({ value: 3, asOf: '2026-01-02' }, {})), { value: '3', asOf: '2026-01-02' });
  assert.deepEqual(attrOf(valueHtml({ value: 3, record: 'r1' }, {})), { value: '3', record: 'r1' });
});

test('a plain value, and a rich cell with no provenance field, emit no data-provenance', () => {
  assert.doesNotMatch(valueHtml(3.82, {}), /data-provenance/);
  assert.doesNotMatch(valueHtml({ value: 3.82, n: 4, low: 3, high: 4 }, {}), /data-provenance/);
  assert.doesNotMatch(valueHtml({ value: null, why: 'not measured', source: 'x' }, {}), /data-provenance/);
});

test('quotes, angle brackets and ampersands in a field cannot break out of the attribute', () => {
  const html = valueHtml({ value: 1, source: '"><img src=x onerror=alert(1)> & co', record: "it's" }, {});
  assert.doesNotMatch(html, /<img/);
  assert.equal(attrOf(html).source, '"><img src=x onerror=alert(1)> & co');
  assert.equal(attrOf(html).record, "it's");
});
