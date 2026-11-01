// The table's leaf columns and header rows (packages/views/table/src/columns.js, CONTRACT §16).
import test from 'node:test';
import assert from 'node:assert/strict';
import { leafColumns, headerRows, statsOf, distScale, slotWidths } from '../../packages/views/table/src/columns.js';

const props = {
  model: { id: 'model', label: 'Model', type: 'text' },
  coulomb: { id: 'coulomb', label: 'Coulomb', type: 'number' },
  viscous: { id: 'viscous', label: 'Viscous', type: 'number' },
  err: { id: 'err', label: 'Error added', type: 'number', values: 'runs' },
};
const rows = [{ model: 'M2', coulomb: { value: 0.04, low: 0.039, high: 0.044, basis: 'measured' }, viscous: 0.01, err: 1, runs: [1, 2, 4] }];

test('columnGroups put a header over its properties; stats splits a column into its sub-columns', () => {
  const view = { columnGroups: { Friction: ['coulomb', 'viscous'] }, display: { coulomb: 'stats', err: 'stats' } };
  const leaves = leafColumns(['model', 'coulomb', 'viscous', 'err'], props, view, rows);
  assert.deepEqual(leaves.map((l) => l.key), ['model', 'coulomb:value', 'coulomb:low', 'coulomb:high', 'coulomb:basis', 'viscous', 'err:median', 'err:min', 'err:max', 'err:n', 'err:dist']);
  const h = headerRows(leaves);
  assert.equal(h.length, 3); // Friction › Coulomb › value
  assert.deepEqual(h[0].map((c) => [c.label, c.span]), [['', 1], ['Friction', 5], ['', 5]]);
  assert.deepEqual(h[1].map((c) => [c.label, c.span]), [['', 1], ['Coulomb', 4], ['', 1], ['Error added', 5]]);
  assert.equal(h[2][5].label, 'Viscous'); // a column with no sub-columns: its label in the last row
  assert.equal(h[2].length, leaves.length);
  assert.deepEqual(h[2].slice(1, 5).map((c) => c.label), ['value', 'low', 'high', 'basis']);
});

test('a stats column takes its parts and labels from the view', () => {
  const view = { display: { coulomb: 'stats' }, stats: { coulomb: { parts: ['value', 'low', 'high'], labels: { low: '95% CI low' } } } };
  const leaves = leafColumns(['coulomb'], props, view, rows);
  assert.deepEqual(leaves.map((l) => l.path), [['Coulomb', 'value'], ['Coulomb', '95% CI low'], ['Coulomb', 'high']]);
});

test('pivot column groups merge only under the same parent', () => {
  const pv = {
    '@a / x': { id: '@a / x', label: 'x', group: 'a', pivot: true }, '@a / y': { id: '@a / y', label: 'y', group: 'a', pivot: true },
    '@b / x': { id: '@b / x', label: 'x', group: 'b', pivot: true },
  };
  const h = headerRows(leafColumns(['@a / x', '@a / y', '@b / x'], pv, {}, []));
  assert.deepEqual(h[0].map((c) => [c.label, c.span]), [['a', 2], ['b', 1]]);
});

test('stats, the shared scale (log past two decades), and slot widths shared down a column', () => {
  assert.deepEqual(statsOf([4, 1, 2]), { median: 2, min: 1, max: 4, n: 3 });
  assert.equal(statsOf([]), null);
  assert.equal(distScale(1, 50).log, false);
  assert.equal(distScale(1, 164).log, true);
  const sc = distScale(0, 10, 86);
  assert.equal(sc.x(0), 3);
  assert.equal(sc.x(10), 83);
  const [leaf] = leafColumns(['err'], props, { display: { err: 'dist' } }, rows);
  assert.equal(slotWidths(leaf, rows).m, 84);
});

test('a heavy tail across zero gets a symmetric log scale, so the small values still spread', () => {
  const values = [-1.4, -0.1, 0, 0.05, 0.1, 0.3, 0.5, 1.1, 341];
  const sc = distScale(-1.4, 341, 86, values);
  assert.equal(sc.symlog, true);
  assert.ok(sc.x(1.1) - sc.x(0) > 10); // linear would put 0 and 1.1 a quarter of a pixel apart
  assert.equal(distScale(-1, 2, 86, [-1, 0.5, 2]).symlog, false);
});

// ---- headerCells: rowspans instead of blank cells, split at the frozen edge, one slot template per column
// (2026-10-26 header/divider review, findings 1, 3 and 5)
import { headerCells, slotTemplate, minWidth } from '../../packages/views/table/src/columns.js';

test('headerCells: a column with no group above it is one cell spanning the rows; no blank cells remain', () => {
  const view = { columnGroups: { Friction: ['coulomb', 'viscous'] }, display: { coulomb: 'stats', err: 'stats' } };
  const leaves = leafColumns(['model', 'coulomb', 'viscous', 'err'], props, view, rows);
  const h = headerCells(leaves);
  assert.equal(h.length, 3);
  const all = h.flat();
  assert.ok(all.every((c) => c.label !== ''), 'no blank cells');
  const model = all.find((c) => c.leaf === 0);
  assert.deepEqual([model.row, model.rowspan, model.span], [0, 3, 1]);
  const coulomb = all.find((c) => c.label === 'Coulomb');
  assert.deepEqual([coulomb.row, coulomb.rowspan, coulomb.span, coulomb.start], [1, 1, 4, 1]);
  const viscous = all.find((c) => c.leaf === 5);
  assert.deepEqual([viscous.row, viscous.rowspan], [1, 2]);
  const err = all.find((c) => c.label === 'Error added');
  assert.deepEqual([err.row, err.rowspan, err.span], [0, 2, 5]); // the blank above it is absorbed
  // every leaf has exactly one leaf cell, and each column is covered once in every row
  assert.deepEqual(all.filter((c) => c.leaf !== undefined).map((c) => c.leaf).sort((a, b) => a - b), leaves.map((_, i) => i));
  for (let d = 0; d < 3; d++) {
    const cover = new Array(leaves.length).fill(0);
    for (const c of all) if (c.row <= d && d < c.row + c.rowspan) for (let i = c.start; i < c.start + c.span; i++) cover[i]++;
    assert.deepEqual(cover, new Array(leaves.length).fill(1), `row ${d}`);
  }
});

test('headerCells: a header never spans the frozen edge (the body freezes exactly the same columns)', () => {
  const pv = { model: { id: 'model', label: 'Model', type: 'text' }, '@a / x': { id: '@a / x', label: 'x', group: 'a', pivot: true }, '@a / y': { id: '@a / y', label: 'y', group: 'a', pivot: true } };
  const view = { columnGroups: { Both: ['model', '@a / x'] } };
  const leaves = leafColumns(['model', '@a / x', '@a / y'], pv, view, []);
  const h = headerCells(leaves, { frozen: 1 });
  const top = h[0];
  assert.ok(top.every((c) => c.start + c.span <= 1 || c.start >= 1), JSON.stringify(top));
  assert.ok(top.some((c) => c.label === 'Both' && c.start === 0 && c.span === 1));
});

test('slotTemplate: only the tracks a column uses, so a number ends at the cell edge', () => {
  assert.equal(slotTemplate({ r: 0, m: 0, n: 0 }).tracks, 'minmax(0, 1fr)');
  assert.equal(slotTemplate({ r: 0, m: 84, n: 18 }).tracks, 'minmax(0, 1fr) 84px 18px');
  assert.deepEqual(slotTemplate({ r: 5, m: 14, n: 0 }).used, ['v', 'r', 'm']);
});

test('minWidth: a distribution column is never narrower than its drawing and its number', () => {
  const [leaf] = leafColumns(['err'], props, { display: { err: 'dist' } }, rows);
  const w = minWidth(leaf, { r: 0, m: 84, n: 18 });
  assert.ok(w >= 16 + 84 + 18 + 12 + 30, String(w));
  const [part] = leafColumns(['err'], props, { display: { err: 'stats' } }, rows).filter((l) => l.part === 'dist');
  assert.ok(minWidth(part, { r: 0, m: 84, n: 0 }) >= 16 + 84);
  assert.equal(minWidth(leafColumns(['model'], props, {}, rows)[0], { r: 0, m: 0, n: 0 }), 48);
});

import { distSvg, quantile, violinProfile } from '../../packages/views/table/src/columns.js';
test('distributions: strip by default, a box of the quartiles, a violin of the density; all on the shared scale', () => {
  const sc = distScale(0, 10, 86);
  const values = [1, 2, 2, 3, 3, 3, 8];
  assert.match(distSvg(values, sc), /dv-dist-strip.*<circle/s);
  const box = distSvg(values, sc, 16, 'box');
  assert.equal(quantile([1, 2, 3, 4], 0.25), 1.75);
  assert.match(box, new RegExp(`<rect class="dv-box" x="${sc.x(2).toFixed(1)}"`)); // Q1 of the values is 2
  const violin = distSvg(values, sc, 16, 'violin');
  assert.match(violin, /<polygon class="dv-violin" points="/);
  const pts = violin.match(/points="([^"]+)"/)[1].split(' ').map((p) => p.split(',').map(Number));
  assert.ok(Math.abs(Math.min(...pts.map((p) => p[0])) - sc.x(1)) < 0.1 && Math.abs(Math.max(...pts.map((p) => p[0])) - sc.x(8)) < 2.1, 'spans min to max');
  const prof = violinProfile([10, 10, 10, 50]);
  assert.equal(Math.max(...prof.map((p) => p[1])), 1); // widest where the values bunch
  assert.ok(prof.find((p) => Math.abs(p[0] - 10) < 1)[1] > prof.find((p) => Math.abs(p[0] - 50) < 1.1)[1]);
  assert.match(distSvg([5], sc, 16, 'violin'), /dv-dist-violin.*<circle/s); // one value: its dot, never a made-up shape
});

// judge r2 (round 1 #6 leftover): the minimum comes from the measured content: the widest number, the header, and a
// distribution's title centred over its strip
test('minWidth from measured content: numbers, the header, a distribution title over its strip', () => {
  const [num] = leafColumns(['coulomb'], props, {}, rows);
  assert.equal(minWidth(num, { r: 0, m: 0, n: 0 }, { num: 120, head: 0 }), 16 + 120 + 1);
  assert.equal(minWidth(num, { r: 0, m: 0, n: 0 }, { num: 10, head: 90 }), 90);
  const [dist] = leafColumns(['err'], props, { display: { err: 'dist' } }, rows);
  const w = { r: 0, m: 84, n: 18 };
  assert.ok(minWidth(dist, w, { num: 70 }) >= 16 + 70 + 84 + 18 + 12);
  // a 160 px title: its left half (80) plus the strip's right half and the count's slot must fit
  assert.ok(minWidth(dist, w, { num: 20, title: 160 }) >= 80 + 42 + 6 + 18 + 8);
  const [part] = leafColumns(['err'], props, { display: { err: 'stats' } }, rows).filter((l) => l.part === 'dist');
  assert.ok(minWidth(part, { r: 0, m: 84, n: 0 }, { title: 30 }) >= 16 + 84);
});

// found by the table-oracle review (judge r4 #2): a rich cell with a low–high draws its range by default (CONTRACT
// §16), so its column's slots reserve the range track; without it the range was dropped (lane) or drawn into a
// zero-width hidden track (main), hidden authored text either way
test('slotWidths: a rich numeric column with a low–high reserves its range track under the default display', () => {
  const p = { id: 'x', label: 'X', type: 'number' };
  const rich = [{ x: { value: 9.35, low: 9.351451, high: 9.351451, basis: 'derived' } }, { x: { value: 3.93, low: 3.617457, high: 4.239043 } }];
  const [leaf] = leafColumns(['x'], { x: p }, {}, rich);
  assert.equal(leaf.display, 'number');
  const w = slotWidths(leaf, rich, (raw) => `${raw.low}–${raw.high}`);
  assert.ok(w.r >= '3.617457–4.239043'.length, JSON.stringify(w));
  assert.ok(slotTemplate(w).used.includes('r'));
  const [valueLeaf] = leafColumns(['x'], { x: p }, { display: { x: 'value' } }, rich);
  assert.equal(slotWidths(valueLeaf, rich, (raw) => `${raw.low}–${raw.high}`).r, 0); // `value` keeps the range in the hover
});
