// .base files: the JS reader and writer (packages/core/src/base.js) and the stdlib Python port
// (packages/core/python/data_ui_base.py), against PyYAML as the oracle on every .base file in Zach's vault.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseBase, parseBaseWithLines, stringifyBase, replaceViewInText, lineOf, BaseSyntaxError } from '../../packages/core/src/base.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const VAULT = '~/zach_brain';

function baseFiles(dir, out = []) {
  for (const f of readdirSync(dir)) {
    if (f === '.claude' || f === '.trash' || f === '.git' || f === 'node_modules' || f === '.obsidian') continue;
    const p = join(dir, f);
    const s = statSync(p, { throwIfNoEntry: false });
    if (!s) continue;
    if (s.isDirectory()) baseFiles(p, out); else if (f.endsWith('.base')) out.push(p);
  }
  return out;
}
const ours = [...baseFiles(join(ROOT, 'examples')), ...baseFiles(join(ROOT, 'gallery'))];
const vault = existsSync(VAULT) ? baseFiles(VAULT) : [];
const havePyYaml = spawnSync('python3', ['-c', 'import yaml'], { stdio: 'ignore' }).status === 0;

test('every .base file reads exactly as PyYAML reads it (the vault, the examples, the gallery)', { skip: !havePyYaml && 'PyYAML is not installed' }, () => {
  const files = [...vault, ...ours];
  assert.ok(files.length >= ours.length);
  if (vault.length) assert.ok(vault.length > 50, `the vault has ${vault.length} .base files`);
  const oracle = execFileSync('python3', [join(ROOT, 'tools', 'yaml_oracle.py'), ...files], { maxBuffer: 64 << 20 }).toString().trim().split('\n').map((l) => JSON.parse(l));
  for (const o of oracle) {
    if (o.error) { assert.throws(() => parseBase(readFileSync(o.file, 'utf8')), BaseSyntaxError, o.file); continue; }
    assert.deepEqual(parseBase(readFileSync(o.file, 'utf8')), o.doc, o.file);
  }
});

test('stringifyBase round-trips every file, and the Python port writes the same text', () => {
  const files = [...vault, ...ours];
  const py = spawnSync('python3', ['-c', `
import json, sys
sys.path.insert(0, ${JSON.stringify(join(ROOT, 'packages', 'core', 'python'))})
import data_ui_base as B
for path in sys.argv[1:]:
    doc = B.loads(open(path, encoding="utf-8").read())
    assert B.loads(B.dumps(doc)) == doc, path
    print(json.dumps({"file": path, "text": B.dumps(doc), "doc": doc}, ensure_ascii=False))
`, ...files], { maxBuffer: 64 << 20 });
  assert.equal(py.status, 0, py.stderr.toString());
  const byFile = new Map(py.stdout.toString().trim().split('\n').map((l) => JSON.parse(l)).map((o) => [o.file, o]));
  for (const f of files) {
    const doc = parseBase(readFileSync(f, 'utf8'));
    const text = stringifyBase(doc);
    assert.deepEqual(parseBase(text), doc, f);
    assert.deepEqual(byFile.get(f).doc, doc, `python reads ${f} the same`);
    assert.equal(byFile.get(f).text, text, `python writes ${f} the same`);
  }
});

test('the subset\'s edges: flow over lines, block scalars, quotes, comments, a sequence at its key\'s indent', () => {
  const doc = parseBase(`---
# a comment
a: [x, "y, z",
    'it''s']
b: { k: v # not a comment inside? it is: YAML ends the line
   , n: -3.5 }
views:
- type: table
  name: "Brand › form"   # trailing comment
  filters: '!x.isEmpty()'
c: |
  line one
  line two
d: >-
  folded
  text
e: ~
f: true
g: 1e3
`);
  assert.deepEqual(doc.a, ['x', 'y, z', "it's"]);
  assert.deepEqual(doc.views, [{ type: 'table', name: 'Brand › form', filters: '!x.isEmpty()' }]);
  assert.equal(doc.c, 'line one\nline two\n');
  assert.equal(doc.d, 'folded text');
  assert.equal(doc.e, null);
  assert.equal(doc.f, true);
  assert.equal(doc.g, 1000);
});

test('what the subset refuses, with the line', () => {
  const bad = { 'a: &x 1\nb: *x': /anchors/, 'a: !!str 1': /tag/, 'filters: !x.isEmpty()': /quote it/, 'a: 1\na: 2': /appears twice/,
    'a:\n\t- x': /tab/, 'a: 1\n---\nb: 2': /one YAML document/, 'a: [1, 2': /expected , or ]/, 'a: "open': /unclosed/ };
  for (const [text, re] of Object.entries(bad)) {
    assert.throws(() => parseBase(text), (err) => err instanceof BaseSyntaxError && re.test(err.message) && err.line >= 1, text);
  }
});

test('lines: every path knows the line it was written on', () => {
  const { lines } = parseBaseWithLines('views:\n  - type: table\n    name: A\n    sort:\n      - { property: x, direction: ASC }\n');
  assert.equal(lineOf(lines, ['views', 0, 'name']), 3);
  assert.equal(lineOf(lines, ['views', 0, 'sort', 0, 'direction']), 5);
});

test('replaceViewInText edits one view and keeps every other line, comments included', () => {
  const text = readFileSync(join(ROOT, 'gallery', 'examples', 'robotparts-actuators', 'views.base'), 'utf8');
  const doc = parseBase(text);
  const changed = { ...doc.views[1], fold: 'open', sort: [{ property: 'mass', direction: 'ASC' }] };
  const out = replaceViewInText(text, 1, changed);
  const after = parseBase(out);
  assert.deepEqual(after.views[1], changed);
  assert.deepEqual(after.views.filter((_, i) => i !== 1), doc.views.filter((_, i) => i !== 1));
  assert.ok(out.startsWith(text.split('\n').slice(0, 5).join('\n')), 'the header comment survives');
  const last = replaceViewInText(text, doc.views.length - 1, { type: 'table', name: 'Last' });
  assert.deepEqual(parseBase(last).views.at(-1), { type: 'table', name: 'Last' });
  const appended = replaceViewInText(text, doc.views.length, { type: 'table', name: 'New' });
  assert.equal(parseBase(appended).views.length, doc.views.length + 1);
});
