// loadDataset asks for a CSV / TSV / JSONL file and its schema sidecar together: neither depends on the other (perf
// review 2026-10-26, item 6). WHY a test: the two awaits read naturally one after the other, which doubled the wait.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadDataset } from '../../packages/core/src/data.js';

function slowFetch(files, log) {
  return (url) => {
    log.push(['start', url]);
    return new Promise((resolve) => setTimeout(() => {
      log.push(['end', url]);
      const body = files[url];
      resolve(body === undefined ? { ok: false, status: 404, text: async () => '' } : { ok: true, status: 200, text: async () => body });
    }, 20));
  };
}

test('a CSV and its .schema.json are requested before either answers, and the rows read through the schema', async () => {
  const log = [];
  const files = {
    'http://x/parts.csv': 'id,mass\na,1.5\nb,2',
    'http://x/parts.schema.json': JSON.stringify({ schema: { fields: [{ name: 'id', type: 'string' }, { name: 'mass', type: 'number' }] } }),
  };
  const d = await loadDataset('http://x/parts.csv', { fetch: slowFetch(files, log) });
  const firstEnd = log.findIndex(([k]) => k === 'end');
  assert.deepEqual(log.slice(0, firstEnd).map(([, u]) => u).sort(), ['http://x/parts.csv', 'http://x/parts.schema.json']);
  assert.deepEqual(d.rows.map((r) => [r.id, r.mass]), [['a', 1.5], ['b', 2]]);
});

test('a CSV without a sidecar still loads (the missing sidecar is not an error)', async () => {
  const log = [];
  const d = await loadDataset('http://x/plain.csv', { fetch: slowFetch({ 'http://x/plain.csv': 'id,n\na,1' }, log) });
  assert.equal(d.rows.length, 1);
});
