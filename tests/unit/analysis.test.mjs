// Analyses (docs/peps/0007-analyses.md, CONTRACT §19): the file format's reader (packages/analysis/src/format.js) and
// the checker (`data-ui check x.md`). Cases ported from robotparts' tests/site/test_analysis.py, where the format was
// born (its PEP 0002); oracles are written out by hand, never from the reader.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { splitFrontmatter, readAnalysis, blocksOf, bindThis, bindDoc, linkify, datasetsOf, analysisRow, outline, STATUSES } from '../../packages/analysis/src/format.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const FIX = join(HERE, '..', 'fixtures', 'analysis');

const GOOD = `---
type: analysis
title: Shoulder actuator
question: Which one?
status: decided
parts: [a1, a2]
decision: a1
date: 2026-10-26
---

Body line one.
`;

test('frontmatter is read with the kit\'s own parser, and the body starts on the right line', () => {
  const r = readAnalysis(GOOD);
  assert.equal(r.front.title, 'Shoulder actuator');
  assert.deepEqual(r.front.parts, ['a1', 'a2']);
  assert.deepEqual(r.problems, []);
  assert.equal(r.bodyLine, 10);
  assert.deepEqual(STATUSES, ['draft', 'open', 'decided', 'superseded']);
  assert.equal(splitFrontmatter('# no front').yaml, null);
});

test('problems name their line', () => {
  assert.deepEqual(readAnalysis('# Just a note\n').problems.map((p) => p.message), ['no frontmatter: the file must start with --- and a title:']);
  const bad = readAnalysis('---\ntitle: T\nstatus: maybe\nparts: [a1]\ndecision: zz\ndate: yesterday\n---\nx\n');
  const at = Object.fromEntries(bad.problems.map((p) => [p.message, p.line]));
  assert.ok('question: is required' in at);
  assert.equal(at['status: must be one of draft, open, decided, superseded (it is maybe)'], 3);
  assert.equal(at['decision: zz is not one of parts:'], 5);
  assert.equal(at['date: must be YYYY-MM-DD (it is yesterday)'], 6);
  assert.match(readAnalysis('---\ntitle: [unclosed\n---\nx\n').problems[0].message, /^frontmatter does not parse/);
});

test('blocks: prose, ```base fences, ![[x.base]] embeds and > [!type] callouts, each with its line', () => {
  const body = 'Intro **bold**.\n\n```base\ndata: /x.json\nviews:\n  - { type: table, name: T }\n```\n\n'
    + '![[dash.base]]\n![[actuator.base#Ashby · torque vs mass]]\n\n'
    + '> [!decision] Chosen: [[a1|GIM]]\n> Because.\n> - Cheap\n\n'
    + '> [!note]- Folded\n> hidden\n\n> a plain quote\n\n```js\nnot a view\n```\nEnd.\n';
  const b = blocksOf(body, 10);
  assert.deepEqual(b.map((x) => x.kind), ['markdown', 'base', 'embed', 'embed', 'callout', 'callout', 'markdown']);
  assert.equal(b[1].line, 12);
  assert.deepEqual([b[2].name, b[2].view, b[2].line], ['dash.base', null, 18]);
  assert.deepEqual([b[3].name, b[3].view], ['actuator.base', 'Ashby · torque vs mass']);
  assert.deepEqual([b[4].type, b[4].title, b[4].text], ['decision', 'Chosen: [[a1|GIM]]', 'Because.\n- Cheap']);
  assert.deepEqual([b[5].type, b[5].fold], ['note', '-']);
  assert.match(b[6].text, /> a plain quote/);
  assert.match(b[6].text, /```js/);
});

test('this is the host note, as in Obsidian', () => {
  assert.equal(bindThis('this.parts.contains(id)', { parts: ['a', 'b-2'] }), '(id == "a" || id == "b-2")');
  assert.equal(bindThis('this.parts.contains(id) && !price.isEmpty()', { parts: ['a'] }), '(id == "a") && !price.isEmpty()');
  assert.equal(bindThis('this.parts.contains(id)', { parts: [] }), 'false');
  assert.equal(bindThis('status == this.status', { status: 'decided' }), 'status == "decided"');
  assert.equal(bindThis('name == "this.parts" || this.missing.isEmpty()', { parts: ['a'] }), 'name == "this.parts" || true');
  assert.equal(bindThis('this.parts.contains(note["id"])', { parts: ['q"uote'] }), '(note["id"] == "q\\"uote")');
  const doc = bindDoc({ filters: { and: ['this.parts.contains(id)', 'level > 1'] }, datasets: { c: { data: '/x', filters: 'this.parts.contains(id)' }, plain: 'y.json' },
    views: [{ type: 'table', name: 'T', filters: 'this.parts.contains(id)' }] }, { parts: ['p1'] });
  assert.deepEqual(doc.filters, { and: ['(id == "p1")', 'level > 1'] });
  assert.equal(doc.datasets.c.filters, '(id == "p1")');
  assert.equal(doc.datasets.plain, 'y.json');
  assert.equal(doc.views[0].filters, '(id == "p1")');
});

test('wikilinks: the host resolves them; unresolved ones stay text; code is left alone; the table pipe escape works', () => {
  const resolve = (t) => ({ a1: { name: 'Alpha', url: '/p/a1/' } }[t] || null);
  assert.equal(linkify('See [[a1]] and [[a1|the first]].', resolve), 'See [Alpha](/p/a1/) and [the first](/p/a1/).');
  assert.equal(linkify('Unknown [[zz]] and [[zz|label]].', resolve), 'Unknown zz and label.');
  assert.equal(linkify('Unknown [[zz]].', resolve, { missing: (t, l) => `${l || t} (not here)` }), 'Unknown zz (not here).');
  assert.equal(linkify('| [[a1\\|A]] | x', resolve), '| [A](/p/a1/) | x');
  assert.equal(linkify('Code `[[a1]]` stays.', resolve), 'Code `[[a1]]` stays.');
  assert.equal(linkify('An embed ![[x.base]] stays.', resolve), 'An embed ![[x.base]] stays.');
});

test('a dashboard\'s datasets are named as data-ui names them', () => {
  assert.deepEqual(datasetsOf({ data: '/a.json', datasets: { cands: { data: '/a.json' }, bench: 'b.json' } }), [{ name: 'cands', data: '/a.json' }, { name: 'bench', data: 'b.json' }]);
  assert.deepEqual(datasetsOf({ data: 'x/runs.json', datasets: { other: { data: 'o.json' } } }), [{ name: 'other', data: 'o.json' }, { name: 'runs', data: 'x/runs.json' }]);
  assert.deepEqual(datasetsOf({ data: '/a.json' }), [{ name: 'a', data: '/a.json' }]);
});

test('a list row is the frontmatter, with names from the host', () => {
  const lookup = (id) => ({ a1: { name: 'Alpha' }, a2: { name: 'Beta' } }[id] || null);
  const row = analysisRow('shoulder', { title: 'Shoulder', question: 'Which?', status: 'decided', parts: ['a1', 'a2', 'gone'], decision: 'a1', date: '2026-10-26', author: 'T', tags: ['x'] },
    { lookup, url: '/a/shoulder/', path: 'analyses/shoulder.md' });
  assert.deepEqual(row, { id: 'shoulder', title: 'Shoulder', question: 'Which?', status: 'decided', parts: ['Alpha', 'Beta', 'gone'], part_ids: ['a1', 'a2', 'gone'],
    parts_count: 3, decision: 'Alpha', decision_id: 'a1', date: '2026-10-26', author: 'T', tags: ['x'], visibility: 'private', url: '/a/shoulder/', path: 'analyses/shoulder.md' });
  assert.equal(analysisRow('x', { status: 'nope' }).status, 'draft');
});

test('the outline is the prose\'s headings, for the table of contents', () => {
  assert.deepEqual(outline('<h2>One</h2><p>x</p><h3>Two a</h3><h2>One</h2>'), [{ level: 2, text: 'One', id: 'one' }, { level: 3, text: 'Two a', id: 'two-a' }, { level: 2, text: 'One', id: 'one-2' }]);
});

const cli = (...args) => spawnSync(process.execPath, [join(ROOT, 'bin', 'data-ui.mjs'), 'check', ...args], { encoding: 'utf8' });

test('data-ui check passes a good analysis: its fences, its embedded dashboard and its data', () => {
  const run = cli(join(FIX, 'good.md'));
  assert.equal(run.status, 0, run.stdout + run.stderr);
  assert.match(run.stdout, /0 errors/);
});

test('data-ui check names every problem of a broken analysis with its line', () => {
  const run = cli(join(FIX, 'bad.md'), '--json');
  assert.equal(run.status, 1, run.stdout + run.stderr);
  const got = JSON.parse(run.stdout).problems.map((p) => `${p.line}: ${p.message}`);
  const want = [/^1: question: is required$/, /^3: status: must be one of/, /^5: decision: p9 is not one of parts:$/, /^11: .*'prise' is not a property of parts\.json/,
    /^14: !\[\[missing\.base\]\]: no such file/, /^1[67]: .*data\/nope\.json: no such file/];
  for (const w of want) assert.ok(got.some((g) => w.test(g)), `${w} in\n${got.join('\n')}`);
  assert.equal(got.length, want.length, got.join('\n'));
});
