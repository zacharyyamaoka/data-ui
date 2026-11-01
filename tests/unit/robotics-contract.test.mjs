// PEP 0010 P1a: the trajectory contract (gallery/robotics/CONTRACT.md) as data-ui reads it. Its schemas/*.schema.json
// are sidecars a producer copies (CONTRACT §3): each loads in data-ui with every column's unit, each name ends in the
// unit it declares (schemas/channels.json, with its named exceptions), and the device channels are samples' columns.
// The difference(a, b) fixture (fixtures/difference/) is checked here as a gallery check reads it, in the page's
// language: each table's columns are the contract's with the contract's units, and the expected rows keep the spec's
// arithmetic (err_mm is the distance a → b, ref_quat is a unit quaternion with w ≥ 0). tools/test_robotics_fixture.py
// reproduces every row independently. Written red, before gallery/robotics/ existed.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { normalizeDataset } from '../../packages/core/src/data.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const HERE = join(ROOT, 'gallery', 'robotics');
const SCHEMAS = join(HERE, 'schemas');
const FIXTURE = join(HERE, 'fixtures', 'difference');
const TABLES = ['runs', 'samples', 'poses', 'diff_poses', 'diff_samples', 'links', 'media', 'devices', 'events', 'coverage_samples', 'coverage_poses', 'grid', 'frames'];
const TYPES = new Set(['number', 'integer', 'string', 'boolean', 'array', 'date', 'datetime', 'object']);
const json = (path) => JSON.parse(readFileSync(path, 'utf8'));
const schema = (name) => json(join(SCHEMAS, `${name}.schema.json`));

test('the contract and a schema per table of PEP 0010 §4.2 exist', () => {
  assert.ok(existsSync(join(HERE, 'CONTRACT.md')));
  for (const t of TABLES) assert.ok(existsSync(join(SCHEMAS, `${t}.schema.json`)), t);
});

test('each schema: named for its file, unique typed fields, required ⊂ fields, rowsPer ⊂ required', () => {
  for (const t of TABLES) {
    const s = schema(t);
    assert.equal(s.name, t);
    const names = s.schema.fields.map((f) => f.name);
    assert.ok(names.length > 0, t);
    assert.equal(new Set(names).size, names.length, `${t}: unique field names`);
    for (const f of s.schema.fields) assert.ok(TYPES.has(f.type), `${t}.${f.name}: type ${f.type}`);
    for (const r of s.required) assert.ok(names.includes(r), `${t}: required ${r} is a field`);
    for (const r of s.rowsPer || []) assert.ok(s.required.includes(r), `${t}: rowsPer ${r} is required`);
  }
});

test('each schema loads in data-ui as a sidecar, every unit carried to the column', () => {
  for (const t of TABLES) {
    const s = schema(t);
    const d = normalizeDataset({ ...s, rows: [] });
    for (const f of s.schema.fields) {
      assert.ok(d.properties[f.name], `${t}.${f.name}`);
      if (f.unit) assert.equal(d.properties[f.name].unitText, f.unit, `${t}.${f.name}`);
    }
  }
});

test('every column name ends in the unit it declares (the suffix table), but for the named exceptions', () => {
  const { suffixes, exceptions } = json(join(SCHEMAS, 'channels.json'));
  const ends = Object.keys(suffixes).sort((a, b) => b.length - a.length);
  let checked = 0;
  for (const t of TABLES) {
    for (const f of schema(t).schema.fields) {
      if (exceptions.includes(f.name)) continue;
      const suffix = ends.find((e) => f.name.endsWith(e));
      if (!suffix) continue;
      checked++;
      assert.equal(f.unit, suffixes[suffix], `${t}.${f.name}: ${suffix} means ${suffixes[suffix]}`);
    }
  }
  assert.ok(checked > 40, `checked ${checked} unit-suffixed columns`);
});

test('the channels of each device type (PEP 0010 §4.3) are samples\' and coverage_samples\' columns, with those units', () => {
  const { types } = json(join(SCHEMAS, 'channels.json'));
  assert.deepEqual(Object.keys(types).sort(), ['camera', 'driver', 'gripper', 'servo']);
  for (const t of ['samples', 'coverage_samples']) {
    const fields = Object.fromEntries(schema(t).schema.fields.map((f) => [f.name, f]));
    for (const [type, channels] of Object.entries(types)) {
      for (const [name, unit] of Object.entries(channels)) {
        assert.ok(fields[name], `${t} has ${type}'s ${name}`);
        assert.equal(fields[name].unit ?? null, unit, `${t}.${name}`);
      }
    }
  }
});

const FIXTURE_TABLES = { poses: 'poses', samples: 'samples', diff_poses: 'diff_poses', diff_samples: 'diff_samples' };

test('the fixture\'s four tables are contract tables: declared columns only, the contract\'s units, every required column in every row', () => {
  for (const [file, table] of Object.entries(FIXTURE_TABLES)) {
    const doc = json(join(FIXTURE, `${file}.json`));
    const contract = Object.fromEntries(schema(table).schema.fields.map((f) => [f.name, f]));
    const d = normalizeDataset(doc);
    for (const f of doc.schema.fields) {
      assert.ok(contract[f.name], `${file}.${f.name} is a ${table} column`);
      assert.equal(f.unit ?? null, contract[f.name].unit ?? null, `${file}.${f.name}`);
      assert.equal(d.properties[f.name].unitText ?? null, contract[f.name].unit ?? null);
    }
    assert.ok(doc.rows.length > 0, file);
    for (const r of doc.rows) {
      for (const k of schema(table).required) assert.ok(r[k] !== undefined && r[k] !== null, `${file}: a row without ${k}`);
      for (const k of Object.keys(r)) assert.ok(contract[k], `${file}: undeclared column ${k}`);
    }
  }
});

test('the expected rows keep the spec\'s arithmetic: err_mm is |b − a|, ref_quat is unit with w ≥ 0, a = real and b = target', () => {
  const rows = json(join(FIXTURE, 'diff_poses.json')).rows;
  for (const r of rows) {
    assert.equal(r.situation, 'real');
    assert.equal(r.source, 'real');
    assert.equal(r.reference, 'target');
    const d = Math.hypot(r.ref_x_mm - r.x_mm, r.ref_y_mm - r.y_mm, r.ref_z_mm - r.z_mm);
    assert.ok(Math.abs(d - r.err_mm) <= 1e-9, `err_mm at t=${r.t}: ${r.err_mm} vs ${d}`);
    const q = [r.ref_quat_w, r.ref_quat_x, r.ref_quat_y, r.ref_quat_z];
    assert.ok(Math.abs(Math.hypot(...q) - 1) <= 1e-12, `ref_quat is unit at t=${r.t}`);
    assert.ok(r.ref_quat_w >= 0, `ref_quat is canonical (w ≥ 0) at t=${r.t}`);
    assert.ok(r.err_rot_mrad >= 0 && r.err_rot_mrad <= Math.PI * 1000);
  }
  for (const r of json(join(FIXTURE, 'diff_samples.json')).rows) {
    assert.equal(r.reference, 'target');
    assert.ok((r.e_q_mrad === null) !== (r.e_q_mm === null), `a revolute row has e_q_mrad, a prismatic one e_q_mm (t=${r.t}, ${r.device})`);
  }
});
