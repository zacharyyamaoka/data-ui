// One row = one .md file (docs/CONTRACT.md §46): reading and writing leave the file a person would be happy to open in Obsidian.
// The real rows are gallery/md-pages: Zach's feedback and spec items as notes. What a check expects is worked out from the file's
// own text here, never from what the writer produced.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseBase } from '../../packages/core/src/base.js';
import { buildRows, entryText, fitsHeading, inferType, layoutOf, moveProperty, parseNote, planMove, propId, readNote, setPage, setValue } from '../../tools/md-notes.mjs';

const CASE = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'gallery', 'md-pages');
const folder = (name) => {
  const dir = join(CASE, name);
  const base = parseBase(readFileSync(join(dir, 'views.base'), 'utf8'));
  const notes = readdirSync(dir).filter((f) => f.endsWith('.md')).sort().map((f) => ({ id: f.replace(/\.md$/, ''), text: readFileSync(join(dir, f), 'utf8') }));
  return { base, notes, lay: layoutOf(base) };
};
const REAL = { feedback: folder('feedback'), frdparrc: folder('frdparrc') };

/** A note with everything a person's file may hold that a writer could trip on. */
const MESSY = [
  '---',
  'title:   "spaced  on purpose"   # a comment that stays',
  'count: 3',
  '# a comment at the margin',
  'tags:',
  '    - indented',
  '    - list',
  'nested:',
  '  a: 1',
  '  b: { c: 2 }',
  'empty:',
  'odd key with spaces: yes',
  '---',
  'Free text before any heading.  ',
  '',
  '',
  '# One',
  '',
  'Body of one.',
  '',
  '```python',
  '# not a heading, it is a comment in code',
  '```',
  '',
  '## Inside one',
  '',
  'still one',
  '',
  '# Two #',
  'tight body',
  '#notatag',
  '',
  '',
  '# Three',
  '',
  '',
].join('\n');

test('reading: frontmatter, sections, the rule for H2 under H1, the free text', () => {
  const r = readNote(MESSY);
  assert.equal(r.values.title, 'spaced  on purpose');
  assert.equal(r.values.count, 3);
  assert.deepEqual(r.values.tags, ['indented', 'list']);
  assert.equal(r.values.empty, null);
  assert.equal(r.page, 'Free text before any heading.  ');
  assert.deepEqual(r.sections.map((s) => s.id), ['one', 'two', 'three']);
  assert.ok(r.values.one.includes('## Inside one') && r.values.one.endsWith('still one'), 'an H2 under an H1 is that cell');
  assert.ok(r.values.one.includes('# not a heading'), 'a fence holds no heading');
  assert.equal(r.values.two, 'tight body\n#notatag');
  assert.equal(r.values.three, '');
});

test('reading: each column is one H1: an H2 or H3 is inside its cell, and before the first H1 it is the page', () => {
  const r = readNote('## Early\n\nwords\n\n# Dp\n\n## One\n\nx\n\n### Two\n\ny\n');
  assert.deepEqual(r.sections, [{ id: 'dp', label: 'Dp' }]);
  assert.equal(r.page, '## Early\n\nwords');
  assert.equal(r.values.dp, '## One\n\nx\n\n### Two\n\ny');
});

test('reading: a heading twice is two properties, and nothing is dropped', () => {
  const r = readNote('# Notes\n\nfirst\n\n# Notes\n\nsecond\n');
  assert.deepEqual([r.values.notes, r.values.notes_2], ['first', 'second']);
  const both = readNote('---\nrisks: low\n---\n\n# Risks\n\nwritten\n');
  assert.deepEqual([both.values.risks, both.values.risks_2], ['low', 'written']);
  assert.equal(propId('id'), 'note_id');
  assert.equal(propId('Desired outcome'), 'desired_outcome');
});

test('reading: a .base displayName names a heading', () => {
  const r = readNote('# ±\n\nnegative\n', { labels: new Map([['±', 'polarity']]) });
  assert.equal(r.values.polarity, 'negative');
});

/** The bytes around a replaced span are the file's: `text` must be `before + value + after` for a single contiguous change. */
function spliced(before, after) {
  let start = 0;
  while (start < before.length && start < after.length && before[start] === after[start]) start++;
  let endA = before.length, endB = after.length;
  while (endA > start && endB > start && before[endA - 1] === after[endB - 1]) { endA--; endB--; }
  return { removed: before.slice(start, endA), added: after.slice(start, endB) };
}

test('writing a section changes its value and not one byte around it', () => {
  const out = setValue(MESSY, 'two', 'new words');
  const d = spliced(MESSY, out);
  assert.equal(d.removed.replace(/^.*?(tight body)/s, '$1').length <= 'tight body\n#notatag'.length, true);
  assert.equal(out, MESSY.replace('tight body\n#notatag', 'new words'));
  assert.equal(setValue(MESSY, 'one', readNote(MESSY).values.one), MESSY, 'its own value: the same string');
});

test('every value of a messy note set to itself: the very same string, odd blank lines and all', () => {
  const r = readNote(MESSY);
  for (const [id, v] of Object.entries(r.values)) assert.equal(setValue(MESSY, id, v), MESSY, id);
  const spaced = '# A\n\n\n\n\n# B\n\n\n';
  assert.equal(setValue(spaced, 'a', ''), spaced);
  assert.equal(setValue(spaced, 'b', ''), spaced);
});

test('writing a frontmatter key changes that key alone: comments, unknown keys and spacing stay', () => {
  assert.equal(setValue(MESSY, 'count', 4), MESSY.replace('count: 3', 'count: 4'));
  assert.equal(setValue(MESSY, 'tags', ['indented', 'list']), MESSY, 'a list set to itself keeps its indent');
  assert.equal(setValue(MESSY, 'title', 'spaced  on purpose'), MESSY, 'the same value keeps its quotes and its comment');
});

test('writing the free text keeps everything after it', () => {
  const out = setPage(MESSY, 'Other words');
  assert.equal(out, MESSY.replace('Free text before any heading.  ', 'Other words'));
  assert.equal(setPage(MESSY, 'Free text before any heading.  '), MESSY);
  assert.equal(readNote(setPage('# A\n\nx\n', 'words')).page, 'words');
  assert.equal(setPage('# A\n\nx\n', 'words'), 'words\n\n# A\n\nx\n');
  assert.equal(setPage('---\na: 1\n---\n', 'words'), '---\na: 1\n---\n\nwords\n');
});

test('line endings: a CRLF file stays CRLF, LF stays LF, a BOM stays', () => {
  const crlf = `﻿${MESSY}`.replace(/\n/g, '\r\n');
  const out = setValue(crlf, 'two', 'a\nb');
  assert.ok(out.includes('a\r\nb'));
  assert.equal(out.replace(/\r\n/g, '').includes('\n'), false, 'no bare LF');
  assert.equal(out.charCodeAt(0), 0xfeff);
  assert.equal(readNote(out).values.two, 'a\nb');
  assert.equal(setValue(crlf, 'one', readNote(crlf).values.one), crlf);
});

test('a value needing YAML quoting reads back as itself', () => {
  for (const v of ['[[PROJECT - Robot Parts#Oct 31]]', 'a: b', '# not a comment', 'yes', '3', '- dash', "it's", 'say "hi"', ' leading', '2026-10-31', 'line one\nline two', 'line one\n\n  indented\n', '  starts indented\nsecond', 'true', 'null', '~', '@at', '%p', 'tab\there', 'ünï · code']) {
    const out = entryText('key', v);
    assert.equal(parseBase(out).key, v, `${JSON.stringify(v)} as ${JSON.stringify(out)}`);
  }
});

const textProps = (props, title = 'name', free = 'page') => Object.entries(props).filter(([id, p]) => id !== title && id !== free && fitsHeading(p)).map(([id]) => id);

for (const [name, { base, notes, lay }] of Object.entries(REAL)) {
  const { properties, rows } = buildRows(notes, base);

  test(`${name}, real rows: each row's every value set to itself leaves the very same file`, () => {
    assert.ok(notes.length >= 4);
    for (const n of notes) {
      const r = readNote(n.text, lay);
      for (const [id, v] of Object.entries(r.values)) assert.equal(setValue(n.text, id, v, lay), n.text, `${n.id}: ${id}`);
      assert.equal(setPage(n.text, r.page, lay), n.text, n.id);
    }
  });

  test(`${name}, real rows: a property moved to its other place and back is byte-identical, and every other value stays`, () => {
    const ids = textProps(properties);
    assert.ok(ids.length >= 3, 'the case has text properties');
    let moved = 0;
    for (const id of ids) {
      for (const n of notes) {
        const was = lay.places.get(id) || 'top';
        const before = readNote(n.text, lay);
        for (const to of ['top', 'section'].filter((x) => x !== was)) {
          const into = lay;
          const label = base.properties[id] && base.properties[id].displayName;
          const there = moveProperty(n.text, id, to, { ...lay, label });
          const read = readNote(there, into);
          for (const [k, v] of Object.entries(before.values)) {
            const a = v ?? '', b = read.values[k] ?? '';
            assert.deepEqual(a, b, `${n.id}: ${k} after ${id} -> ${to}`);
          }
          const back = moveProperty(there, id, was, { ...into, label });
          assert.equal(back, n.text, `${n.id}: ${id} -> ${to} -> ${was}`);
          moved++;
        }
      }
    }
    assert.ok(moved >= notes.length * ids.length, `${moved} round trips`);
  });

  test(`${name}, real rows: the plan moves every file, and reads each back before anything is written`, () => {
    const id = textProps(properties).find((x) => properties[x].section);
    const from = lay;
    const page = base.page.map((e) => (e.property === id ? { property: id } : e));
    const to = layoutOf({ ...base, page });
    const plan = planMove(notes, id, 'top', from, to, { label: base.properties[id]?.displayName });
    assert.equal(plan.refused.length, 0);
    assert.equal(plan.changed + plan.unchanged, notes.length);
    assert.ok(plan.files.every((f) => readNote(f.text, to).keys.some((k) => k.id === id)));
  });

  test(`${name}: the rows hold what the files hold`, () => {
    assert.equal(rows.length, notes.length);
    for (const r of rows) assert.equal(r.name, r.id);
    assert.ok(Object.values(properties).some((p) => p.pageBody));
  });
}

test('frontmatter <-> heading when the frontmatter empties, or there is none', () => {
  const only = '---\nnote: words\n---\n';
  const out = moveProperty(only, 'note', 'section', { label: 'Note' });
  assert.equal(out, '# Note\n\nwords\n');
  assert.equal(moveProperty(out, 'note', 'top', { label: 'Note' }), only);
  const none = '# Note\n\nwords\n\nmore\n';
  const up = moveProperty(none, 'note', 'top', {});
  assert.equal(up, '---\nNote: |-\n  words\n\n  more\n---\n', 'with no displayName the heading\'s words are the key');
  assert.equal(moveProperty(up, 'note', 'section', {}), none);
});

const WIKI = '---\nstatus: open\n---\n\n# Dp\n\nSee [[Some Note]], [[Some Note|the alias]] and [[Some Note#A heading]].\n\n![[shot one.png]]\n\n## Sub with [[Link]]\n\n# Risks\n\nnone\n';

test('wikilinks: a section holding each form survives reads, a write beside it, and a move there and back, byte for byte', () => {
  const lay = layoutOf({ page: [{ property: 'status' }, { property: 'dp', place: 'section' }, { property: 'risks', place: 'section' }] });
  const r = readNote(WIKI, lay);
  assert.ok(r.values.dp.includes('[[Some Note|the alias]]') && r.values.dp.includes('[[Some Note#A heading]]') && r.values.dp.includes('![[shot one.png]]'));
  assert.equal(setValue(WIKI, 'dp', r.values.dp, lay), WIKI);
  assert.equal(setValue(WIKI, 'risks', 'some', lay), WIKI.replace('none', 'some'));
  const up = moveProperty(WIKI, 'dp', 'top', { ...lay, label: 'Dp' });
  assert.equal(readNote(up, lay).values.dp, r.values.dp, 'in YAML it reads the same');
  assert.equal(moveProperty(up, 'dp', 'section', { ...lay, label: 'Dp' }), WIKI);
  assert.equal(parseBase(entryText('k', '[[Note|alias]]')).k, '[[Note|alias]]');
});

test('a section is placed by the layout order, and a heading with a word inside', () => {
  const t = '# A\n\na\n\n# C\n\nc\n';
  const out = setValue(t, 'b', 'b', { place: 'section', label: 'B', order: ['a', 'b', 'c'] });
  assert.equal(out, '# A\n\na\n\n# B\n\nb\n\n# C\n\nc\n');
});

test('a value holding an H1 is refused, and nothing moves; an H2 in it moves with it', () => {
  const notes = [{ id: 'x', text: '---\nbody: |-\n  words\n  # Sneaky\n  more\n---\n' }, { id: 'y', text: '---\nbody: fine\n---\n' }];
  const from = layoutOf({ page: [{ property: 'body' }] });
  const to = layoutOf({ page: [{ property: 'body', place: 'section' }] });
  const plan = planMove(notes, 'body', 'section', from, to, { label: 'Body' });
  assert.deepEqual(plan.refused.map((r) => r.id), ['x']);
  const inside = planMove([{ id: 'z', text: '---\nbody: |-\n  ## Sub\n\n  more\n---\n' }], 'body', 'section', from, to, { label: 'Body' });
  assert.equal(inside.refused.length, 0);
  assert.equal(inside.files[0].text, '# Body\n\n## Sub\n\nmore\n');
});

test('types: only words fit a heading', () => {
  assert.equal(inferType([1, 2.5, null]), 'number');
  assert.equal(inferType([true, false]), 'boolean');
  assert.equal(inferType(['2026-10-31', '2026-10-31T18:15:32Z']), 'date');
  assert.equal(inferType([['a'], 'b']), 'list');
  assert.equal(inferType(['open', 3]), 'text');
  for (const p of [{ type: 'number' }, { type: 'date' }, { type: 'boolean' }, { type: 'list' }, { type: 'text', constraints: { enum: ['a'] } }, { type: 'text', labels: { a: 'A' } }, { type: 'text', display: 'badge' }]) assert.equal(fitsHeading(p), false, JSON.stringify(p));
  assert.equal(fitsHeading({ type: 'text' }), true);
  assert.equal(fitsHeading({ type: 'text', long: true, display: 'outline', section: true }), true);
});

test('YAML the reader does not take stays as written, and a write to it is refused', () => {
  const t = '---\nanchored: &x 1\nplain: 2\n---\n';
  assert.equal(setValue(t, 'plain', 3), t.replace('plain: 2', 'plain: 3'));
  assert.throws(() => setValue(t, 'anchored', 5), /stays as written/);
});

test('parseNote keeps offsets into the very text', () => {
  const n = parseNote(MESSY);
  for (const s of n.sections) assert.ok(MESSY.slice(s.start).startsWith('#'));
});
