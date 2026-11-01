// The popover that lists every source of a value several sources state (docs/CONTRACT.md §36, its amendment "the source
// popover"; docs/peps/0015-source-precedence.md): its rows are precedence.js sourceRows(), measured here against an
// oracle over the fixtures' own JSON (tests/browser/fixtures/source-precedence/part.json, the datasheet; and
// tests/browser/fixtures/source-popover/parts.json, a record per part) and precedence.js's pick() and conflict(), which
// tests/unit/precedence.test.mjs holds on their own. A view marks such a value with format.js sourcesAttr(), so the
// item menu finds its row and property (and sources.js leaves its right-click to that menu).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { pick, conflict, precedenceOf, resolveCell, sourceRows } from '../../packages/core/src/precedence.js';
import { sourcesAttr } from '../../packages/core/src/format.js';

const read = (rel) => JSON.parse(readFileSync(new URL(rel, import.meta.url), 'utf8'));
const PART = read('../browser/fixtures/source-precedence/part.json');
const PARTS = read('../browser/fixtures/source-popover/parts.json');

// ---------------------------------------------------------------- the oracle: the JSON alone, plus pick() and conflict()
const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const blank = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
const multi = (c) => isObj(c) && Array.isArray(c.sources) && c.sources.length > 0;
function ladderDefault(data) {
  const ids = Object.keys(data.sources || {});
  for (const r of data.rows) for (const v of Object.values(r)) if (multi(v)) for (const e of v.sources) if (!blank(e.source) && !ids.includes(String(e.source))) ids.push(String(e.source));
  const rungs = (data.ladder || []).map((x) => x.id);
  const at = (s) => { const r = (data.sources[s] || {}).rung; const i = rungs.indexOf(r); return r === undefined || i < 0 ? rungs.length : i; };
  return ids.map((s, i) => [s, at(s), i]).sort((a, b) => a[1] - b[1] || a[2] - b[2]).map(([s]) => s);
}
const entries = (cell) => { const m = new Map(); for (const e of cell.sources) if (!blank(e.source) && !m.has(String(e.source)) && !blank(e.value)) m.set(String(e.source), e); return m; };
const key = (e, cell) => JSON.stringify([e.value, !blank(e.unit) ? e.unit : (blank(cell.unit) ? null : cell.unit)]);

/** What sourceRows(cell, view, id, info) must return, from the JSON: the sources in precedence order (a source the order
    lacks after, in the cell's order), each with its place, name, rung label, mark and the entry exactly as stated. */
function expected(data, row, prop, view) {
  const cell = row[prop], have = entries(cell);
  const order = view.order || [];
  const list = [...order.filter((s) => have.has(s)), ...[...have.keys()].filter((s) => !order.includes(s))];
  const chosen = pick(cell, view, row.id);
  return {
    shown: chosen.source, via: chosen.via, prec: chosen.prec,
    rows: list.map((s) => {
      const d = data.sources[s] || {};
      const rung = (data.ladder || []).find((x) => x.id === d.rung);
      return {
        source: s, rank: order.includes(s) ? order.indexOf(s) + 1 : null,
        name: d.name || s, rungLabel: rung ? rung.label : null,
        state: s === chosen.source ? 'shown' : key(have.get(s), cell) !== key(have.get(chosen.source), cell) ? 'differs' : 'agrees',
        nominal: s === chosen.source, pinned: s === chosen.source && chosen.via === 'override',
      };
    }),
  };
}

/** The views every check runs under: the ladder default; every row with two or more sources chosen by hand (its first
    such value's last-listed source); and an order that puts the last source first and leaves the rest out (a stale link). */
function views(data) {
  const def = ladderDefault(data);
  const picks = {};
  for (const r of data.rows) for (const p of Object.keys(r)) if (multi(r[p])) {
    const list = [...entries(r[p]).keys()];
    if (list.length > 1 && !picks[r.id]) picks[r.id] = list[list.length - 1];
  }
  return [
    ['the default', { order: def, ov: {} }],
    ['picks by hand', { order: def, ov: picks }],
    ['a changed, stale order', { order: [def[def.length - 1], def[0]], ov: {} }],
  ];
}

const multiCells = (data) => data.rows.flatMap((r) => Object.keys(r).filter((p) => multi(r[p])).map((p) => [r, p]));

for (const [name, data] of [['the datasheet (part.json)', PART], ['a record per part (parts.json)', PARTS]]) {
  test(`sourceRows, ${name}: every source that states each value, in precedence order, its place, name, rung label and mark`, () => {
    const info = precedenceOf(data);
    assert.ok(info, 'the fixture has values with several sources');
    assert.deepEqual(info.default, ladderDefault(data), 'the oracle and precedenceOf agree on the default order');
    let popovers = 0;
    for (const [label, view] of views(data)) {
      for (const [row, prop] of multiCells(data)) {
        const got = sourceRows(row[prop], view, row.id, info);
        const want = expected(data, row, prop, view);
        const where = `${label}: ${row.id}.${prop}`;
        assert.deepEqual({ shown: got.shown, via: got.via, prec: got.prec }, { shown: want.shown, via: want.via, prec: want.prec }, `${where}: what is shown is pick()'s`);
        assert.deepEqual(got.rows.map(({ source, rank, name: n, rungLabel, state, nominal, pinned }) => ({ source, rank, name: n, rungLabel, state, nominal, pinned })), want.rows, where);
        assert.equal(got.rows.filter((r) => r.nominal).length, want.shown === null ? 0 : 1, `${where}: one nominal row`);
        if (want.shown !== null) assert.equal(got.rows.some((r) => r.state === 'differs'), conflict(row[prop]), `${where}: a row differs exactly when conflict() says the sources disagree`);
        if (got.rows.length > 1) popovers += 1;
      }
    }
    assert.ok(popovers >= 6, `the fixture exercises the popover (${popovers} cases)`);
  });

  test(`sourceRows, ${name}: each row's cell is the entry exactly as stated, with its source's name, address, date and basis where it has none`, () => {
    const info = precedenceOf(data);
    for (const [row, prop] of multiCells(data)) {
      const cell = row[prop], have = entries(cell);
      for (const r of sourceRows(cell, { order: info.default, ov: {} }, row.id, info).rows) {
        const e = have.get(r.source), d = data.sources[r.source] || {};
        const where = `${row.id}.${prop} ${r.source}`;
        assert.equal(r.cell.value, e.value, `${where}: the value is the entry's own (never a copy that could differ)`);
        assert.equal(r.cell.text, typeof e.text === 'string' && e.text ? e.text : undefined, `${where}: text as written`);
        assert.equal(r.cell.source, d.name || r.source, `${where}: the source's name`);
        assert.equal(r.cell.unit, !blank(e.unit) ? e.unit : !blank(cell.unit) ? cell.unit : undefined, `${where}: the entry's unit, else the cell's`);
        assert.equal(r.cell.sourceUrl, !blank(e.sourceUrl) ? e.sourceUrl : !blank(d.url) ? d.url : undefined, `${where}: the entry's address, else its source's`);
        assert.equal(r.cell.asOf, !blank(e.asOf) ? e.asOf : !blank(d.date) ? d.date : undefined, `${where}: the entry's date, else its source's`);
        assert.equal(r.cell.basis, !blank(e.basis) ? e.basis : !blank(d.basis) ? d.basis : undefined, `${where}: the entry's basis, else its source's`);
        assert.equal(r.cell.note, !blank(e.note) ? e.note : undefined, `${where}: the entry's note`);
      }
    }
  });
}

test('sourceRows is truthful: it never edits a cell, an entry or the dataset, whatever the view', () => {
  for (const data of [PART, PARTS]) {
    const before = JSON.stringify(data);
    const info = precedenceOf(data);
    for (const [, view] of views(data)) for (const [row, prop] of multiCells(data)) {
      const got = sourceRows(row[prop], view, row.id, info);
      for (const r of got.rows) void r.cell.value; // read every row
    }
    assert.equal(JSON.stringify(data), before);
  }
});

test('sourceRows: the cases the parts fixture holds (an undeclared source, an entry\'s own unit and address, a relative address)', () => {
  const info = precedenceOf(PARTS);
  const row = (id) => PARTS.rows.find((r) => r.id === id);
  const memo = sourceRows(row('qdd-b').torque, { order: info.default, ov: {} }, 'qdd-b', info).rows.find((r) => r.source === 'memo');
  assert.deepEqual({ name: memo.name, rungLabel: memo.rungLabel, rank: memo.rank, state: memo.state }, { name: 'memo', rungLabel: null, rank: 4, state: 'differs' }, 'a source only a cell names: its id as its name, no rung, last');
  const mass = sourceRows(row('qdd-a').mass, { order: info.default, ov: {} }, 'qdd-a', info).rows;
  const shop = mass.find((r) => r.source === 'shop');
  assert.equal(shop.cell.unit, 'kg', 'an entry stated in its own unit keeps it');
  assert.equal(shop.cell.sourceUrl, 'https://example.com/shop/qdd-a', "an entry's own address wins over its source's (a private one)");
  assert.equal(shop.state, 'differs', '0.5 kg and 492 g are two statements (no conversion)');
  assert.equal(mass.find((r) => r.source === 'bench').cell.sourceUrl, 'logs/bench-2026-10.html', 'a relative address as written (the view resolves it against the data file)');
  const picked = sourceRows(row('qdd-a').mass, { order: info.default, ov: { 'qdd-a': 'shop' } }, 'qdd-a', info);
  assert.deepEqual([picked.shown, picked.via, picked.prec], ['shop', 'override', 'bench']);
  assert.deepEqual(picked.rows.map((r) => [r.source, r.state, r.pinned]), [['bench', 'differs', false], ['maker', 'differs', false], ['shop', 'shown', true]]);
});

test('sourceRows: a stale order still lists every source (the ones it lacks after, unranked); an override whose source states nothing here is ignored', () => {
  const info = precedenceOf(PART);
  const peak = PART.rows.find((r) => r.id === 'peak_torque').nominal;
  const got = sourceRows(peak, { order: ['listing', 'bench'], ov: {} }, 'peak_torque', info);
  assert.deepEqual(got.rows.map((r) => [r.source, r.rank]), [['listing', 1], ['bench', 2], ['chat', null], ['datasheet', null]]);
  assert.equal(got.shown, 'listing');
  const rated = PART.rows.find((r) => r.id === 'rated_torque').nominal;
  const ignored = sourceRows(rated, { order: info.default, ov: { rated_torque: 'bench' } }, 'rated_torque', info);
  assert.deepEqual([ignored.shown, ignored.via], ['datasheet', 'precedence']);
  assert.ok(ignored.rows.every((r) => !r.pinned));
  const none = sourceRows(PART.rows.find((r) => r.id === 'backlash').nominal, { order: info.default, ov: {} }, 'backlash', info);
  assert.deepEqual([none.rows, none.shown, none.via], [[], null, 'none'], 'no source states it: no rows');
});

test('sourcesAttr: the mark a view writes on a value two or more sources state; nothing on any other cell', () => {
  const peak = PART.rows.find((r) => r.id === 'peak_torque').nominal;
  assert.equal(sourcesAttr(peak, 'peak_torque', 'nominal'), ' data-src-row="peak_torque" data-src-p="nominal"');
  assert.equal(sourcesAttr(peak, 'peak_torque', 'nominal', { focusable: true }), ' data-src-row="peak_torque" data-src-p="nominal" tabindex="0"', 'the record and the peek make it a tab stop (its fields are not)');
  const info = precedenceOf(PART);
  assert.equal(sourcesAttr(resolveCell(peak, { order: info.default, ov: {} }, 'peak_torque', info.sources), 'peak_torque', 'nominal'), ' data-src-row="peak_torque" data-src-p="nominal"', 'the resolved cell (what a view draws) is marked the same');
  for (const id of ['kt', 'protection', 'encoder', 'backlash']) {
    const c = PART.rows.find((r) => r.id === id).nominal;
    assert.equal(sourcesAttr(c, id, 'nominal'), '', `${id}: one source or none keeps today's menu`);
    assert.equal(sourcesAttr(c, id, 'nominal', { focusable: true }), '', `${id}: and is no tab stop`);
  }
  for (const c of [null, undefined, 3, 'IP54', [24, 48], { value: 7, source: "Maker's page" }, { sources: [] }, { sources: [{ source: 'a', value: 1 }, { source: 'a', value: 2 }] }, { sources: [{ source: 'a', value: 1 }, { source: 'b', value: null }, { source: 'c', value: '' }] }]) {
    assert.equal(sourcesAttr(c, 'r', 'p'), '', JSON.stringify(c));
  }
  assert.equal(sourcesAttr({ sources: [{ source: 'a', value: 1 }, { source: 'b', value: 1 }] }, 'r', 'p'), ' data-src-row="r" data-src-p="p"', 'two sources that agree are still two sources');
  assert.equal(sourcesAttr(peak, `a"b<c>&'d`, 'x"y'), ' data-src-row="a&quot;b&lt;c&gt;&amp;&#39;d" data-src-p="x&quot;y"', 'ids are escaped');
});
