// The Node checker reads a dashboard's CSV / TSV / JSON-lines dataset as the browser does (CONTRACT §3: a schema sidecar
// `<name>.schema.json` beside it, else the header): found building PEP 0010 P2's Servo coverage (coverage_samples.csv),
// whose views the checker had checked against the default dataset's columns, since it read only .json files.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { main, datasetProperties, datasetTypes, isDataFile } from '../../packages/core/src/check.js';

function run(files) {
  const dir = mkdtempSync(join(tmpdir(), 'dui-check-csv-'));
  for (const [name, text] of Object.entries(files)) writeFileSync(join(dir, name), text);
  const lines = [];
  const code = main([join(dir, 'views.base')], { log: (l) => lines.push(String(l)) });
  rmSync(dir, { recursive: true, force: true });
  return { code, text: lines.join('\n') };
}

const base = (extra = '') => `data: runs.json
datasets:
  runs: runs.json
  coverage:
    data: coverage.csv
${extra}views:
  - type: chart
    name: Angle
    from: coverage
    chart: { mark: bar, encoding: { x: { field: q_deg, bin: true }, 'y': { aggregate: sum, field: w } } }
`;

test('a CSV dataset\'s columns come from its sidecar, else its header; its views are checked against them', () => {
  const runs = JSON.stringify({ schema: { fields: [{ name: 'run', type: 'string' }] }, rows: [{ run: 'a' }] });
  const ok = run({ 'views.base': base(), 'runs.json': runs, 'coverage.csv': 'run,q_deg,w\na,1.5,1\n' });
  assert.equal(ok.code, 0, ok.text);
  assert.match(ok.text, /coverage\.csv/);
  const bad = run({ 'views.base': base().replace('field: w', 'field: weight'), 'runs.json': runs, 'coverage.csv': 'run,q_deg,w\na,1.5,1\n' });
  assert.equal(bad.code, 1);
  assert.match(bad.text, /'weight' is not a property of coverage\.csv/);
  const side = run({ 'views.base': base(), 'runs.json': runs, 'coverage.csv': 'x,y\n1,2\n',
    'coverage.schema.json': JSON.stringify({ schema: { fields: [{ name: 'q_deg', type: 'number' }, { name: 'w', type: 'number' }] } }) });
  assert.equal(side.code, 0, side.text);
});

test('datasetProperties and datasetTypes read CSV, TSV and JSON lines', () => {
  const dir = mkdtempSync(join(tmpdir(), 'dui-check-csv-'));
  try {
    writeFileSync(join(dir, 'a.tsv'), 'run\t"q deg"\n');
    writeFileSync(join(dir, 'b.jsonl'), '{"run": "a", "w": 1}\n{"run": "b", "q": 2}\n');
    writeFileSync(join(dir, 'c.csv'), 'run,w\n');
    writeFileSync(join(dir, 'c.schema.json'), JSON.stringify({ schema: { fields: [{ name: 'run', type: 'string' }, { name: 'w', type: 'number' }] } }));
    assert.deepEqual([...datasetProperties(join(dir, 'a.tsv'))], ['run', 'q deg']);
    assert.deepEqual([...datasetProperties(join(dir, 'b.jsonl'))].sort(), ['q', 'run', 'w']);
    assert.deepEqual(datasetTypes(join(dir, 'c.csv')), { run: 'text', w: 'number' });
    assert.equal(datasetTypes(join(dir, 'a.tsv')), null);   // a header says no types
    assert.ok(isDataFile('x.CSV') && isDataFile('x.json') && isDataFile('x.jsonl') && !isDataFile('x.glb'));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
