// PEP 0010 P1c: the Servo and Robot arm templates (gallery/examples/robotics-servo, robotics-arm) as files, and their
// use case on the docs site. Each table a template writes is the trajectory contract's (gallery/robotics/CONTRACT.md):
// every column the contract names keeps its type and unit, every other numeric column ends in the unit it declares
// (schemas/channels.json's suffixes), a link pose column is in the scene's unit (mm) or a unitless quaternion part,
// every row has the required columns, a family is real, sim or target, and one body is written in one frame. A case
// stays a few MB (the brief: "keep them small"); its README names its use case, which site/build-site.mjs groups by.
// The browser half is tests/browser/p1c_checks.py. Written red, before the templates.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { normalizeDataset } from '../../packages/core/src/data.js';
import { parseBase } from '../../packages/core/src/base.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const EX = join(ROOT, 'gallery', 'examples');
const SCHEMAS = join(ROOT, 'gallery', 'robotics', 'schemas');
const CASES = { 'robotics-servo': ['runs', 'samples', 'devices'], 'robotics-arm': ['runs', 'poses', 'samples', 'links', 'devices'] };
const BUDGET = 5 * 1024 * 1024;   // bytes a case publishes (every file but source/)
const json = (path) => JSON.parse(readFileSync(path, 'utf8'));
const contract = (name) => json(join(SCHEMAS, `${name}.schema.json`));
const { suffixes, exceptions } = json(join(SCHEMAS, 'channels.json'));
const ENDS = Object.keys(suffixes).sort((a, b) => b.length - a.length);

function published(dir) {
  let bytes = 0;
  const walk = (d) => { for (const n of readdirSync(d)) { const p = join(d, n); if (statSync(p).isDirectory()) walk(p); else bytes += statSync(p).size; } };
  for (const n of readdirSync(dir)) {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) { if (n !== 'source' && !n.startsWith('.')) walk(p); } else bytes += statSync(p).size;
  }
  return bytes;
}

test('each template is a gallery case whose README names its use case, its app and the UI it replaces', () => {
  for (const c of Object.keys(CASES)) {
    const readme = readFileSync(join(EX, c, 'README.md'), 'utf8');
    assert.match(readme, /^- \*\*Use case:\*\* Robotics · Playback$/m, `${c}: "- **Use case:** Robotics · Playback"`);
    assert.match(readme, /^- \*\*App:\*\* \S/m, `${c}: an App bullet`);
    assert.match(readme, /^- \*\*Replaces:\*\* \S/m, `${c}: a Replaces bullet`);
    assert.ok(existsSync(join(EX, c, 'views.base')) && existsSync(join(EX, c, 'checks.py')), `${c}: views.base and checks.py`);
  }
});

test('every table a template writes is the contract\'s: its columns, types, units and required columns', () => {
  for (const [c, tables] of Object.entries(CASES)) {
    for (const t of tables) {
      const doc = json(join(EX, c, `${t}.json`));
      const fields = doc.schema.fields;
      const want = Object.fromEntries(contract(t).schema.fields.map((f) => [f.name, f]));
      const d = normalizeDataset(doc);
      assert.ok(d.rows.length > 0, `${c}/${t}.json has rows`);
      for (const f of fields) {
        const where = `${c}/${t}.json ${f.name}`;
        assert.ok(d.properties[f.name], where);
        if (want[f.name]) {
          assert.equal(f.type, want[f.name].type, `${where}: the contract's type`);
          assert.equal(f.unit, want[f.name].unit, `${where}: the contract's unit`);
        } else if (t === 'links' && /_(x|y|z)$/.test(f.name)) {
          assert.equal(f.unit, 'mm', `${where}: a link position in the scene's unit`);
        } else if (t === 'links' && /_q[wxyz]$/.test(f.name)) {
          assert.equal(f.unit, undefined, `${where}: a quaternion part has no unit`);
        } else if (f.type === 'number' && !exceptions.includes(f.name)) {
          const end = ENDS.find((e) => f.name.endsWith(e));
          assert.ok(end, `${where}: a number not in the contract ends in its unit`);
          assert.equal(f.unit, suffixes[end], `${where}: its unit is its suffix's`);
        }
      }
      for (const r of contract(t).required) {
        assert.ok(fields.some((f) => f.name === r), `${c}/${t}.json declares required ${r}`);
        assert.ok(doc.rows.every((row) => row[r] !== undefined), `${c}/${t}.json: every row has ${r}`);
      }
      if (fields.some((f) => f.name === 'source')) {
        const fams = new Set(doc.rows.map((r) => r.source));
        assert.ok([...fams].every((s) => ['real', 'sim', 'target'].includes(s)), `${c}/${t}.json: families ${[...fams]}`);
      }
    }
  }
});

test('runs: ISO times with an offset, display at most 100 Hz, every run in the samples and poses, one frame per body', () => {
  for (const c of Object.keys(CASES)) {
    const runs = json(join(EX, c, 'runs.json')).rows;
    for (const r of runs) {
      assert.match(r.started, /^\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d(\.\d+)?)?([+-]\d\d:\d\d|Z)$/, `${c} ${r.run}: started ${r.started}`);
      assert.ok(r.display_hz > 0 && r.display_hz <= 100, `${c} ${r.run}: display ${r.display_hz} Hz`);
    }
    const samples = json(join(EX, c, 'samples.json')).rows;
    const have = new Set(samples.map((r) => r.run));
    assert.deepEqual([...have].sort(), runs.map((r) => r.run).sort(), `${c}: every run has samples and nothing else does`);
    if (existsSync(join(EX, c, 'poses.json'))) {
      const poses = json(join(EX, c, 'poses.json')).rows;
      const frames = new Map();
      for (const p of poses) { const k = `${p.run}\u0000${p.body}`; if (!frames.has(k)) frames.set(k, new Set()); frames.get(k).add(p.frame); }
      for (const [k, f] of frames) assert.equal(f.size, 1, `${c}: ${k.replace('\u0000', ' ')} in one frame`);
    }
  }
});

test('the rail lists the runs newest first: the Run facet\'s order is runs.json by started, latest first', () => {
  for (const c of Object.keys(CASES)) {
    const base = parseBase(readFileSync(join(EX, c, 'views.base'), 'utf8'));
    const runs = json(join(EX, c, 'runs.json')).rows;
    const facet = ((base.datasets.runs || {}).facets || []).find((f) => f && f.property === 'run');
    assert.ok(facet && facet.as === 'select', `${c}: runs carries a Run select`);
    assert.deepEqual(facet.order, [...runs].sort((a, b) => (a.started < b.started ? 1 : a.started > b.started ? -1 : 0)).map((r) => r.run), `${c}: Run's order`);
  }
});

test('each template stays a few MB: everything it publishes is within the budget', () => {
  for (const c of Object.keys(CASES)) {
    const bytes = published(join(EX, c));
    assert.ok(bytes <= BUDGET, `${c}: ${(bytes / 1048576).toFixed(2)} MB published, budget ${(BUDGET / 1048576).toFixed(0)} MB`);
  }
});

test('the docs site groups a case by its README\'s use case: Robotics, then Playback', async () => {
  const { useCaseOf, bullets } = await import('../../site/build-site.mjs');
  assert.deepEqual(useCaseOf(bullets('# x\n\n- **Use case:** Robotics · Playback\n')), { group: 'Robotics', sub: 'Playback', text: 'Robotics · Playback' });
  assert.deepEqual(useCaseOf(bullets('# x\n\n- **Use case:** Robotics\n')), { group: 'Robotics', sub: null, text: 'Robotics' });
  assert.equal(useCaseOf(bullets('# x\n\n- **App:** robotparts\n')), null);
  for (const c of Object.keys(CASES)) assert.equal(useCaseOf(bullets(readFileSync(join(EX, c, 'README.md'), 'utf8'))).text, 'Robotics · Playback');
});
