// Gap #1 (docs/peps/0010-robotics-playback.md §11 P0; reports/backlog-sim2real-gaps-2026-10-28.md): a dashboard's clock
// spans the rows its filters leave, not every row of `clock.data`. sim2real's run inspector played a 4.5 s run on the
// 36 s staircase's clock. The model's half (model.js clockSpan) and the clock's half (an empty span, the zoom window
// kept inside the span). Oracles are written out by hand from the tiny fixture below, never from the code.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as M from '../../packages/dashboard/src/model.js';
import { normalizeDataset } from '../../packages/core/src/data.js';

globalThis.requestAnimationFrame = () => 0;
globalThis.cancelAnimationFrame = () => {};
const { Clock } = await import('../../packages/core/src/clock.js');

const base = {
  data: 'runs.json',
  clock: { data: 'samples', time: 't' },
  datasets: { runs: 'runs.json', samples: { data: 'samples.json', facets: [{ property: 'device', as: 'select' }] } },
  links: [{ from: 'samples.run', to: 'runs.run' }],
  layout: { panels: [{ view: 'Runs' }, { view: 'Samples' }] },
  views: [{ type: 'table', name: 'Runs', from: 'runs', select: 'run' }, { type: 'table', name: 'Samples', from: 'samples' }],
};
const data = () => ({
  runs: normalizeDataset({ properties: { run: {} }, rows: [{ id: 'A', run: 'A' }, { id: 'B', run: 'B' }, { id: 'C', run: 'C' }] }),
  samples: normalizeDataset({ properties: { t: { type: 'number' }, run: {}, device: {} }, rows: [
    { id: 's1', t: 0, run: 'A', device: 'J3' }, { id: 's2', t: 1, run: 'A', device: 'J3' }, { id: 's3', t: 4.5, run: 'A', device: 'J3' },
    { id: 's4', t: 0, run: 'B', device: 'J3' }, { id: 's5', t: 10, run: 'B', device: 'J3' }, { id: 's6', t: 36, run: 'B', device: 'J3' },
    { id: 's7', t: 0.5, run: 'C', device: 'J4' }, { id: 's8', t: { value: 3, unit: 's' }, run: 'C', device: 'J4' },
    { id: 's9', t: 'n/a', run: 'C', device: 'J4' },
  ] }),
});
const dash = () => M.readDashboard(base);
const span = (state) => M.clockSpan(dash(), data(), { rail: {}, select: {}, ...state });

test('clockSpan is exported by the dashboard model', () => {
  assert.equal(typeof M.clockSpan, 'function');
});

test('no filter: the clock spans every row of clock.data (a text t is not a time)', () => {
  assert.deepEqual(span({}), [0, 36]);
});

test('a run picked in another panel narrows the clock through the link: the run\'s own min..max t', () => {
  assert.deepEqual(span({ select: { runs: { dataset: 'runs', property: 'run', values: ['A'] } } }), [0, 4.5]);
  assert.deepEqual(span({ select: { runs: { dataset: 'runs', property: 'run', values: ['B'] } } }), [0, 36]);
});

test('the clock dataset\'s own rail narrows it, and a rich cell reads as its value', () => {
  assert.deepEqual(span({ rail: { samples: 'device == "J4"' } }), [0.5, 3]);
});

test('a selection made on the clock dataset itself counts too (the clock is no panel, so no selection is its own)', () => {
  assert.deepEqual(span({ select: { samples: { dataset: 'samples', property: 'run', values: ['A'] } } }), [0, 4.5]);
});

test('filters that leave no row with a time: null (no span), never the whole dataset', () => {
  assert.equal(span({ rail: { samples: 'device == "J4"' }, select: { runs: { dataset: 'runs', property: 'run', values: ['A'] } } }), null);
});

test('a dashboard without clock.data declares no span: undefined', () => {
  const d = M.readDashboard({ ...base, clock: { loop: true } });
  assert.equal(M.clockSpan(d, data(), { rail: {}, select: {} }), undefined);
  assert.equal(M.clockSpan(M.readDashboard({ ...base, clock: undefined }), data(), { rail: {}, select: {} }), undefined);
});

test('Clock.setSpan(null, null): an empty span (the filters leave nothing); the next span brings the asked t back', () => {
  const c = new Clock();
  c.setSpan(0, 36);
  c.seek(10);
  let states = 0;
  c.addEventListener('state', () => { states += 1; });
  c.setSpan(0, 4.5);
  assert.equal(c.t, 4.5, 'clamped into the new span');
  c.setSpan(null, null);
  assert.deepEqual([c.start, c.end], [null, null]);
  assert.ok(states >= 2, 'a state event per span change');
  c.extent(0, 99);
  assert.deepEqual([c.start, c.end], [null, null], 'still declared: a card\'s extent does not make the span up');
  c.setSpan(0, 36);
  assert.deepEqual([c.start, c.end, c.t], [0, 36, 10], 'the instant asked for (10) is kept through the narrow and empty spans');
});

test('the zoom window meets the span: gone when a narrower span misses it, back when the span returns, kept while it overlaps', () => {
  const c = new Clock();
  c.setSpan(0, 36);
  c.setWindow([10, 20]);
  let states = 0;
  c.addEventListener('state', () => { states += 1; });
  c.setSpan(0, 4.5);
  assert.equal(c.window, null, 'a window wholly outside the span is no window');
  c.setSpan(0, 36);
  assert.deepEqual(c.window, [10, 20], 'the asked window comes back, as the asked range does');
  assert.ok(states >= 2);
  c.setWindow([3, 6]);
  c.setSpan(0, 4.5);
  assert.deepEqual(c.window, [3, 6], 'a window that overlaps the span is kept as asked (a zoom may reach past the data)');
  c.setSpan(null, null);
  assert.equal(c.window, null, 'an empty span has no window');
  c.setSpan(0, 36);
  assert.deepEqual(c.window, [3, 6]);
  c.setWindow(null);
  c.setSpan(0, 4.5);
  c.setSpan(0, 36);
  assert.equal(c.window, null, 'a cleared window stays cleared');
});

test('the loop range on an empty span is no range, and the asked range comes back with the span', () => {
  const c = new Clock();
  c.setSpan(0, 36);
  c.setRange([2, 4]);
  c.setSpan(null, null);
  assert.equal(c.range, null);
  c.setSpan(0, 4.5);
  assert.deepEqual(c.range, [2, 4]);
});
