// The rail on a large dataset: 150,000 numeric rows. Math.min(...nums) passes every value as an argument, and V8
// throws "Maximum call stack size exceeded" somewhere past ~120k of them (the 2026-10-26 performance review's RISK
// finding), so every count the rail draws must take its extents with a loop.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as F from '../../packages/core/src/facets.js';

const N = 150000;
const ROWS = Array.from({ length: N }, (_, i) => ({ id: `r${i}`, mass: (i % 997) + 0.5, stars: (i % 5) + 1, at: i }));
const PROPS = {
  mass: { id: 'mass', type: 'number', label: 'mass' },
  stars: { id: 'stars', type: 'number', label: 'stars' },
  at: { id: 'at', type: 'number', label: 'at' },
};

test(`railCounts: range, histogram, buckets and rating facets on ${N.toLocaleString('en-US')} numeric rows, with the extents a loop finds`, () => {
  const specs = F.facetSpecs({ facets: [
    { property: 'mass', as: 'range' },
    { property: 'at', as: 'slider-histogram' },
    { property: 'mass', as: 'buckets', step: 100 },
    { property: 'stars', as: 'rating' },
  ] }, null, PROPS);
  const counts = F.railCounts(ROWS, { stars: { min: 2 } }, specs);
  const [range, hist, buckets, rating] = specs.map((s) => counts[s.key]);
  assert.deepEqual([range.n, range.min, range.max, range.domain], [N * 4 / 5, 0.5, 996.5, { min: 0.5, max: 996.5 }]);
  assert.deepEqual([hist.min, hist.max, hist.domain], [1, N - 1, { min: 0, max: N - 1 }]);
  assert.equal(hist.binsAll.reduce((a, b) => a + b.n, 0), N);
  assert.ok(buckets.buckets.length > 0);
  assert.ok(rating, 'the rating facet counts');
});

test(`facetCounts: a range's extent on ${N.toLocaleString('en-US')} numeric rows`, () => {
  const out = F.facetCounts(ROWS, {}, { at: 'range' });
  assert.deepEqual(out.at, { n: N, min: 0, max: N - 1 });
});
