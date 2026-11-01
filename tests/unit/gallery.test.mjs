// The gallery's cases (gallery/examples/*): the layout docs/CONTRACT.md §6 fixes, and the two data fixes the
// examples carry (the lane's mass x1000 bug; CAN 14's Kt correction).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseBase } from '../../packages/core/src/base.js';
import { normalizeDataset, parseCSV, parseJSONL } from '../../packages/core/src/data.js';
import { cellValue } from '../../packages/core/src/grammar.js';

const EX = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'gallery', 'examples');
const cases = readdirSync(EX).filter((d) => existsSync(join(EX, d, 'views.base')));

test('every case: README with a title, views.base whose data: exists, rows with ids', () => {
  assert.ok(cases.length >= 2);
  for (const c of cases) {
    const readme = readFileSync(join(EX, c, 'README.md'), 'utf8');
    assert.match(readme, /^# \S/, `${c}/README.md starts with its title`);
    const base = parseBase(readFileSync(join(EX, c, 'views.base'), 'utf8'));
    assert.ok(base.data && existsSync(join(EX, c, base.data)), `${c}: data: ${base.data}`);
    assert.ok(base.views.length >= 2, `${c} has views`);
    // a case's data is any form CONTRACT §3 accepts (the raw-source case is a CSV)
    const text = readFileSync(join(EX, c, base.data), 'utf8');
    const ext = base.data.split('.').pop().toLowerCase();
    const d = normalizeDataset(ext === 'csv' || ext === 'tsv' ? parseCSV(text, { sep: ext === 'tsv' ? '\t' : ',' }) : ext === 'jsonl' ? parseJSONL(text) : JSON.parse(text));
    assert.equal(new Set(d.rows.map((r) => r.id)).size, d.rows.length, `${c}: ids are unique`);
  }
});

test('actuators: mass from each spec\'s own unit (the AKE40-6 KV90 is 140 g, not 140,000 g)', () => {
  const d = JSON.parse(readFileSync(join(EX, 'robotparts-actuators', 'actuators.json'), 'utf8'));
  assert.equal(d.rows.length, 1149);
  const ake = d.rows.find((r) => r.id === 'cubemars-ake40-6-kv90');
  assert.equal(cellValue(ake.mass), 140);
  assert.equal(ake.mass.basis, 'datasheet');
  const heaviest = Math.max(...d.rows.map((r) => cellValue(r.mass)).filter((x) => typeof x === 'number'));
  assert.ok(heaviest < 100000, `no actuator weighs 100 kg or more (heaviest ${heaviest} g)`);
});

test('GIM4305-10: CAN 14\'s corrected torque values (coulomb friction 0.0551 N·m; ripple 25.8 / 12.3 / 11.1 mN·m)', () => {
  const d = JSON.parse(readFileSync(join(EX, 'gim4305-datasheet', 'datasheet.json'), 'utf8'));
  const row = (id) => d.rows.find((r) => r.id === id);
  const can14 = (id) => row(id)._detail.filter((e) => e.column === 'measured' && e.specimen.startsWith('CAN 14')).map((e) => e.value);
  assert.ok(can14('coulomb_friction').includes('0.0551'));
  assert.ok(!can14('coulomb_friction').includes('0.0448'), 'the superseded value is gone');
  assert.deepEqual(can14('torque_ripple'), ['k14: 25.8', 'k28: 12.3', 'k24: 11.1']);
  assert.match(row('coulomb_friction').measured, /^0\.0551 · /);
  assert.ok(row('coulomb_friction')._detail.find((e) => e.value === '0.0551').method.includes('Supersedes the 0.0448 N·m'));
});
