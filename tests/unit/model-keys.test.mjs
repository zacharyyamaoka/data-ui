// <data-views> reuses its row model while MODEL_KEYS, the search, the filters, the data and its revision are as they
// were (perf review 2026-10-26, item 5). WHY this test: a view key that rowModel starts reading but MODEL_KEYS forgets
// would leave a stale model on screen after that key changes; reading the sources keeps the list honest.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { MODEL_KEYS } from '../../packages/core/src/rowmodel.js';

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'packages', 'core', 'src');

test('MODEL_KEYS names every view key the row model reads (rowmodel.js, and grammar.js up to the YAML writer)', () => {
  const rowmodel = readFileSync(join(SRC, 'rowmodel.js'), 'utf8');
  const grammar = readFileSync(join(SRC, 'grammar.js'), 'utf8');
  const modelPart = grammar.slice(0, grammar.indexOf('export function toBaseYaml'));
  assert.ok(modelPart.length < grammar.length, 'grammar.js still has toBaseYaml (the YAML writer reads every key; it is not the model)');
  const read = new Set();
  for (const text of [rowmodel, modelPart]) for (const m of text.matchAll(/\bview\.([A-Za-z_]\w*)/g)) read.add(m[1]);
  assert.ok(!/\bview\[/.test(rowmodel) && !/\bview\[/.test(modelPart), 'a computed view[key] read cannot be checked: name the key');
  assert.deepEqual([...read].filter((k) => !MODEL_KEYS.includes(k)).sort(), []);
});
