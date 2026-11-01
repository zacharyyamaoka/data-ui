// The User Timing milestones (packages/core/src/perf.js) that npm run bench reads: named, carrying their detail,
// bounded, and never able to throw into a render. The browser side (that <data-views> emits them in order on a real
// page) is checked by every bench run: bench/runner.py fails a scenario whose page lacks data-ui:first-render.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mark, measure, PERF_NAMES } from '../../packages/core/src/perf.js';

test('mark and measure land in the timeline with their names and detail', () => {
  performance.clearMarks('data-ui:first-render');
  performance.clearMeasures('data-ui:render');
  mark('data-ui:first-render', { id: 'parts', type: 'table', rows: 1149 });
  const t0 = performance.now();
  for (let i = 0, x = 0; i < 1e5; i++) x += i;
  measure('data-ui:render', t0, { id: 'parts', type: 'table', rows: 40 });
  const [m] = performance.getEntriesByName('data-ui:first-render', 'mark');
  assert.deepEqual(m.detail, { id: 'parts', type: 'table', rows: 1149 });
  const [r] = performance.getEntriesByName('data-ui:render', 'measure');
  assert.equal(r.startTime, t0);
  assert.ok(r.duration >= 0);
  assert.equal(r.detail.rows, 40);
});

test('the per-render measures are cleared every KEEP entries, so a long session cannot grow the timeline', () => {
  performance.clearMeasures('data-ui:model');
  for (let i = 0; i < PERF_NAMES.keep * 2 + 5; i++) measure('data-ui:model', performance.now(), null);
  assert.ok(performance.getEntriesByName('data-ui:model', 'measure').length <= PERF_NAMES.keep);
});

test('a detail the timeline cannot clone, or no User Timing at all, never throws', () => {
  assert.doesNotThrow(() => mark('data-ui:data', { fn: () => 1 }));
  const saved = globalThis.performance;
  try {
    Object.defineProperty(globalThis, 'performance', { value: undefined, configurable: true, writable: true });
    assert.doesNotThrow(() => mark('data-ui:start', {}));
    assert.doesNotThrow(() => measure('data-ui:render', 0, {}));
  } finally {
    Object.defineProperty(globalThis, 'performance', { value: saved, configurable: true, writable: true });
  }
});
