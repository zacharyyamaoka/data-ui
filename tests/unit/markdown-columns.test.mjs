// The markdown property type's H1 columns (docs/CONTRACT.md §46).
import test from 'node:test';
import assert from 'node:assert/strict';
import { h1Sections, setH1, expandH1, liftH1 } from '../../packages/core/src/markdown-columns.js';
import { properties, rowModel } from '../../packages/core/src/rowmodel.js';
import { PROPERTY_TYPES, typeOf } from '../../packages/core/src/types.js';
import { readFileSync } from 'node:fs';
import { sectionCell, isDerivedCell } from '../../packages/core/src/section-summary.js';
import { sectionCell as fromFormat } from '../../packages/core/src/format.js';

const NOTE = '---\nid: x\n---\n\nbefore\n\n# Observed\n\nA thing\n\n## Sub\n\n![[pic.png]]\n\n```\n# not a heading\n```\n\n# Desired\n\nNot sure\n\n# Why\n';

test('h1Sections: each H1 and its body, a fenced # is no heading, an H2 stays inside', () => {
  const { lead, sections } = h1Sections(NOTE);
  assert.deepEqual(sections.map((s) => s.heading), ['Observed', 'Desired', 'Why']);
  assert.match(lead, /before$/);
  assert.match(sections[0].body, /## Sub[\s\S]*# not a heading/);
  assert.equal(sections[1].body, 'Not sure');
  assert.equal(sections[2].body, '');
});

test('setH1: a body changes and every other byte stays; a value equal to itself writes the same bytes', () => {
  const next = setH1(NOTE, 'Desired', 'Something else');
  assert.equal(next, NOTE.replace('Not sure', 'Something else'));
  assert.equal(setH1(NOTE, 'Desired', 'Not sure'), NOTE);
  assert.match(setH1(NOTE, 'Why', 'Because'), /# Why\n\nBecause\n$/);
  assert.match(setH1('# A\n\none\n', 'New', 'two'), /^# A\n\none\n\n# New\n\ntwo\n$/);
  assert.equal(setH1('a\r\n\r\n# B\r\n\r\nold\r\n', 'B', 'new'), 'a\r\n\r\n# B\r\n\r\nnew\r\n');
});

test('expandH1: one column per H1, the listed headings first and always there, the holder hidden', () => {
  const data = { properties: { body: { type: 'text', columns: 'h1', headings: ['Why'] } }, rows: [{ id: 1, body: NOTE }, { id: 2, body: '# Other\n\nwords\n' }] };
  expandH1(data);
  assert.deepEqual(Object.keys(data.properties), ['body', 'why', 'observed', 'desired', 'other']);
  assert.equal(data.properties.body.hidden, true);
  assert.equal(data.properties.observed.kind, 'markdown');
  assert.equal(data.rows[1].observed, '');
  assert.equal(data.rows[0].desired, 'Not sure');
  expandH1(data);
  assert.deepEqual(Object.keys(data.properties), ['body', 'why', 'observed', 'desired', 'other'], 'twice is once');
});

test('expandH1: the .base file can ask for it; a heading a property holds does not overwrite it', () => {
  const data = { properties: { body: { type: 'text' }, observed: { type: 'date' } }, rows: [{ id: 1, body: '# Observed\n\nx\n', observed: '2026-01-01' }] };
  expandH1(data, { body: { columns: 'h1' } });
  assert.equal(data.rows[0].observed, '2026-01-01');
  assert.equal(data.rows[0].body_observed, 'x');
});

test('liftH1: an edit of an H1 column is an edit of the one property; two at once both land', () => {
  const props = { body: {}, a: { h1Of: 'body', h1: 'A' }, b: { h1Of: 'body', h1: 'B' }, other: {} };
  const row = { body: '# A\n\none\n\n# B\n\ntwo\n' };
  const { set, cells } = liftH1({ a: 'ONE', b: 'TWO', other: 3 }, props, row);
  assert.equal(set.body, '# A\n\nONE\n\n# B\n\nTWO\n');
  assert.equal(set.other, 3);
  assert.deepEqual(cells, { a: 'ONE', b: 'TWO' });
});

test('the markdown type: storage is text, its cell an outline unless it says first lines, and it is listed', () => {
  assert.equal(PROPERTY_TYPES.markdown.label, 'Markdown');
  const cols = properties({ properties: { m: { type: 'text' }, p: { type: 'text' } } }, { properties: { m: { type: 'markdown' }, p: { type: 'markdown', summary: 'preview' } } });
  assert.equal(cols.m.display, 'outline');
  assert.equal(cols.p.display, 'preview');
  assert.equal(typeOf(cols.m), 'markdown');
  assert.equal(cols.m.type, 'text');
});

test('a section cell: embeds are small thumbnails, or [image] where there is no room; wikilink embeds count', () => {
  const c = sectionCell('words\n\n![[a.png]]', { mode: 'preview', lines: 3 });
  assert.deepEqual(c.media.map((m) => m.src), ['a.png']);
  assert.equal(sectionCell('words\n\n![[a.png]]', { mode: 'preview', lines: 1 }).media.length, 0);
  assert.match(sectionCell('![[a.png]]\n\nwords', { mode: 'preview', lines: 1 }).text, /\[image\]/);
  assert.equal(isDerivedCell('## A\n', 'outline'), true);
});

test('defaultSort: a view that names no sort it can follow reads newest first; a view of its own wins', () => {
  const data = { defaultSort: [{ property: 'added', direction: 'DESC' }], titleProperty: 'n', properties: { added: { type: 'date' }, n: { type: 'text' } }, rows: [{ id: 1, n: 'a', added: '2026-01-01' }, { id: 2, n: 'b', added: '2026-03-01' }, { id: 3, n: 'c', added: '2026-02-01' }] };
  const ids = (view) => rowModel(data, {}, view).rows.map((r) => r.id);
  assert.deepEqual(ids({ type: 'table' }), [2, 3, 1]);
  assert.deepEqual(ids({ type: 'table', sort: [{ property: 'gone', direction: 'DESC' }] }), [2, 3, 1]);
  assert.deepEqual(ids({ type: 'table', sort: [{ property: 'n', direction: 'ASC' }] }), [1, 2, 3]);
});

test('the summary is one file with no import, so another host can take it; the kit reads the same function', () => {
  const src = readFileSync(new URL('../../packages/core/src/section-summary.js', import.meta.url), 'utf8');
  assert.doesNotMatch(src, /^\s*(import|export \{[^}]*\} from)\b/m);
  assert.doesNotMatch(src, /\b(document|window|HTMLElement)\b/);
  assert.equal(fromFormat, sectionCell);
  assert.deepEqual(sectionCell('## A\n\ntext\n\n### B\n', { lines: 3 }).items.map((x) => x.text), ['A', 'B']);
  assert.equal(sectionCell('plain words', { lines: 3 }).kind, 'preview');
});
