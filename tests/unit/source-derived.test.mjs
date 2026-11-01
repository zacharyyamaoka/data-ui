// A derived nominal names its source (docs/CONTRACT.md §36, its amendment "a derived value names its source"): the
// Nominal source column showed "—" for a value derived from another (RobotParts' JMC pole pairs, decoded from the model
// code on a selection list). A derived value reaches data-ui by its basis ('derived': the entry's own, else its declared
// source's, which precedence.js entryCell() fills in), and what it was derived from is what the cell names: a value with
// several sources, its picked entry's source; a §22 cell, its `source`, else its `sourceUrl` or `sourcePage`.
// precedence.js nominalSource() says what the column names, measured here against an oracle over the fixture's JSON
// and pick(); "—" (null) only where nothing names a source.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { pick, precedenceOf, nominalSource } from '../../packages/core/src/precedence.js';

const read = (rel) => JSON.parse(readFileSync(new URL(rel, import.meta.url), 'utf8'));
const DERIVED = read('../browser/fixtures/source-column/derived.json');
const SERVO = read('../browser/fixtures/source-column/servo.json');
const PART = read('../browser/fixtures/source-precedence/part.json');

// ---------------------------------------------------------------- the oracle: the JSON alone, plus pick()
const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const filled = (v) => v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0);
const entries = (cell) => { const m = new Map(); for (const e of cell.sources) if (filled(e.source) && !m.has(String(e.source)) && filled(e.value)) m.set(String(e.source), e); return m; };
function expected(data, cell, view, id) {
  if (isObj(cell) && Array.isArray(cell.sources) && cell.sources.length) {
    const s = pick(cell, view, id).source;
    if (s === null) return null;
    const e = entries(cell).get(s), d = (data.sources || {})[s] || {};
    const basis = filled(e.basis) ? e.basis : d.basis;
    return { source: s, name: filled(d.name) ? d.name : s, address: filled(e.sourceUrl) ? e.sourceUrl : filled(d.url) ? d.url : null, derived: basis === 'derived' };
  }
  if (!isObj(cell)) return null;
  const name = filled(cell.source) ? String(cell.source) : null;
  const address = filled(cell.sourceUrl) ? String(cell.sourceUrl) : filled(cell.sourcePage) ? String(cell.sourcePage) : null;
  if (name === null && address === null) return null;
  return { source: null, name, address, derived: cell.basis === 'derived' };
}

const ladder = (data) => (precedenceOf(data) || { default: [] }).default;

for (const [label, data] of [['derived.json (values decoded from a model code)', DERIVED], ['servo.json (one source per value)', SERVO], ['part.json (several sources)', PART]]) {
  test(`nominalSource, ${label}: what the Nominal source column names, under the default and a pick by hand`, () => {
    const info = precedenceOf(data) || {};
    const def = ladder(data);
    const picks = {};
    for (const r of data.rows) {
      const c = r.nominal;
      if (isObj(c) && Array.isArray(c.sources)) { const list = [...entries(c).keys()]; if (list.length > 1) picks[r.id] = list[list.length - 1]; }
    }
    for (const view of [{ order: def, ov: {} }, { order: def, ov: picks }]) {
      for (const r of data.rows) {
        assert.deepEqual(nominalSource(r.nominal, view, r.id, info), expected(data, r.nominal, view, r.id), `${r.id} (${JSON.stringify(view.ov)})`);
      }
    }
  });
}

test('nominalSource: the cases the derived fixture holds, named', () => {
  const info = precedenceOf(DERIVED);
  const view = { order: info.default, ov: {} };
  const row = (id) => DERIVED.rows.find((r) => r.id === id).nominal;
  assert.deepEqual(nominalSource(row('pole_pairs'), view, 'pole_pairs', info), { source: 'selection', name: 'Zeta selection list (private)', address: 'account:zeta/selection-list', derived: true },
    "RobotParts' case: a value decoded from the model code on a private selection list names that list, and is derived");
  assert.equal(nominalSource(row('rotor_inertia'), view, 'rotor_inertia', info).derived, false, 'the selection list states it: not derived');
  assert.deepEqual(nominalSource(row('rotor_inertia'), { ...view, ov: { rotor_inertia: 'decoder' } }, 'rotor_inertia', info),
    { source: 'decoder', name: 'Model-code decoder', address: 'https://example.com/zeta/model-codes', derived: true }, "picked, the decoder's value is derived by its source's declared basis");
  assert.deepEqual(nominalSource(row('encoder_lines'), view, 'encoder_lines', info), { source: null, name: null, address: 'https://example.com/zeta/model-codes', derived: true }, 'an address alone names the source');
  assert.deepEqual(nominalSource(row('brake'), view, 'brake', info), { source: null, name: null, address: 'notes/zeta-model-code.md', derived: true }, "a source's page alone names it");
  assert.equal(nominalSource(row('torque_constant'), view, 'torque_constant', info), null, 'derived, but nothing names a source: "—"');
  assert.equal(nominalSource(row('mass'), view, 'mass', info), null, 'a plain value names nothing');
  assert.deepEqual(nominalSource(row('frame_size'), view, 'frame_size', info), { source: null, name: 'Zeta drawing', address: 'https://example.com/zeta/zs60-drawing.pdf', derived: true });
  assert.equal(nominalSource(row('rated_speed'), view, 'rated_speed', info).derived, false, 'stated, not derived');
  for (const c of [null, undefined, 4, 'x', [1, 2], { value: 1 }, { value: 1, basis: 'derived' }, { sources: [] }, { sources: [{ source: 'a', value: null }] }]) {
    assert.equal(nominalSource(c, view, 'x', info), null, JSON.stringify(c));
  }
  const before = JSON.stringify(DERIVED);
  for (const r of DERIVED.rows) nominalSource(r.nominal, view, r.id, info);
  assert.equal(JSON.stringify(DERIVED), before, 'it never edits a cell');
});
