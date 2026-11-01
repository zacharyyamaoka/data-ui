// settledSelections on a live dataset (docs/CONTRACT.md §39, §26). Found reviewing the fleet map's own code after its checks
// went green; written red, before the fix. A live dataset's `.rows` is not what its panel draws (a store and a window, read
// through snapshot), so "names no row" cannot be told from it: a selection there stays what it is.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readDashboard, settledSelections } from '../../packages/dashboard/src/model.js';
import { normalizeDataset } from '../../packages/core/src/data.js';

const dash = readDashboard({
  data: 'sites.json',
  datasets: { sites: 'sites.json', robots: 'robots.json' },
  links: [{ from: 'sites.site', to: 'robots.site', direction: 'one-way' }],
  layout: { panels: [{ view: 'Sites' }, { view: 'Robots' }] },
  views: [
    { type: 'table', name: 'Sites', from: 'sites', select: 'site' },
    { type: 'table', name: 'Robots', from: 'robots', select: 'robot', selected: 'first' },
  ],
});
const sites = normalizeDataset({ rows: [{ id: 's1', site: 's1' }] });
// the shape model.js isLive reads: a store whose rows are not on `.rows`
const liveRobots = { live: true, snapshot: () => [{ id: 'a', robot: 'a', site: 's1' }], rows: [], properties: {} };

test('a selection on a live dataset stays: its rows are not on .rows, so it cannot be told to name none', () => {
  const state = { rail: {}, tabs: {}, legend: {}, select: { robots: { dataset: 'robots', property: 'robot', values: ['a'] } } };
  assert.deepEqual(settledSelections(dash, { sites, robots: liveRobots }, state).robots, state.select.robots);
});
