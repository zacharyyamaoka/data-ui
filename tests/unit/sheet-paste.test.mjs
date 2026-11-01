// CONTRACT §40: a pasted block. What is a block, how it reads (the CSV reader's scanner, so Excel's and Sheets' quoting), what each
// value becomes (nothing is rewritten: what does not fit stays as written), and where each one lands.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseBlock, isBlock, coerceCell, planPaste } from '../../packages/core/src/sheet.js';
import { parseCSV, parseRecords } from '../../packages/core/src/data.js';

test('parseBlock: rows of cells, whichever line ending; a last line break adds no row', () => {
  assert.deepEqual(parseBlock('a\tb\nc\td\n'), [['a', 'b'], ['c', 'd']]);
  assert.deepEqual(parseBlock('a\tb\r\nc\td\r\n'), [['a', 'b'], ['c', 'd']]);
  assert.deepEqual(parseBlock('a\tb'), [['a', 'b']]);
});

test('parseBlock: an empty cell and a blank line are cells', () => {
  assert.deepEqual(parseBlock('a\t\tc'), [['a', '', 'c']]);
  assert.deepEqual(parseBlock('a\n\nc'), [['a'], [''], ['c']]);
});

test('parseBlock: Excel and Sheets quote a cell holding a tab, a line break or a quote', () => {
  assert.deepEqual(parseBlock('"two\nlines"\tx'), [['two\nlines', 'x']]);
  assert.deepEqual(parseBlock('"a\tb"\ty'), [['a\tb', 'y']]);
  assert.deepEqual(parseBlock('"Ana ""B"""\tz'), [['Ana "B"', 'z']]);
});

test('parseBlock: a quote that does not close a whole cell is the words as written', () => {
  assert.deepEqual(parseBlock('"hello" world\tb'), [['"hello" world', 'b']]);
  assert.deepEqual(parseBlock('"open\tb\nc\td'), [['"open', 'b'], ['c', 'd']]);
  assert.deepEqual(parseBlock('5" screen\tb'), [['5" screen', 'b']]);
});

test('parseRecords: the scanner under parseCSV; parseCSV reads as it did', () => {
  assert.deepEqual(parseRecords('a,b\n\nc').map((r) => r.cells), [['a', 'b'], [''], ['c']]);
  assert.deepEqual(parseCSV('a,b\n"x, y",2\n'), [{ a: 'x, y', b: 2 }]);
  // not strict, a quote at a cell's start opens it whatever follows: parseCSV's reading of a file stays as it was
  assert.deepEqual(parseRecords('"hello" world,b').map((r) => r.cells), [['hello world', 'b']]);
});

test('isBlock: a tab; or several lines with a table on the clipboard', () => {
  assert.equal(isBlock('a\tb', ''), true);
  assert.equal(isBlock('a\nb\nc', '<table><tr><td>a</td></tr></table>'), true);
  assert.equal(isBlock('a\nb\nc', '<meta charset="utf-8"><google-sheets-html-origin><table xmlns="x"><tbody></tbody></table>'), true);
});

test('isBlock: words stay words: one line, a paragraph, a single cell, nothing', () => {
  assert.equal(isBlock('just words', ''), false);
  assert.equal(isBlock('line one\nline two', ''), false);
  assert.equal(isBlock('line one\nline two', '<p>line one</p><p>line two</p>'), false);
  assert.equal(isBlock('abc\r\n', '<table><tr><td>abc</td></tr></table>'), false);
  assert.equal(isBlock('"a\tb"', ''), false);
  assert.equal(isBlock('', ''), false);
});

const num = { id: 'n', type: 'number' };
const text = { id: 't', type: 'text' };
const bool = { id: 'b', type: 'boolean' };

test('coerceCell: a number that reads as one is a number; anything else is kept as written', () => {
  assert.equal(coerceCell('12.5', num), 12.5);
  assert.equal(coerceCell(' 7 ', num), 7);
  assert.equal(coerceCell('-1e3', num), -1000);
  assert.equal(coerceCell('12 mm', num), '12 mm');
  assert.equal(coerceCell('1,234', num), '1,234');
  assert.equal(coerceCell('Infinity', num), 'Infinity');
});

test('coerceCell: words are not trimmed or changed', () => {
  assert.equal(coerceCell('  spaced  ', text), '  spaced  ');
  assert.equal(coerceCell('007', text), '007');
});

test('coerceCell: an empty cell clears', () => {
  for (const p of [num, text, bool]) assert.equal(coerceCell('', p), null);
  assert.equal(coerceCell('   ', num), null);
});

test('coerceCell: a checkbox reads the words spreadsheets write; anything else as written', () => {
  for (const t of ['TRUE', 'true', 'Yes', 'yes', '1', '✓', 'x'.replace('x', '✓')]) assert.equal(coerceCell(t, bool), true, t);
  for (const t of ['FALSE', 'false', 'No', 'no', '0']) assert.equal(coerceCell(t, bool), false, t);
  assert.equal(coerceCell('maybe', bool), 'maybe');
});

test('coerceCell: a list splits on commas, as the add row and the form do', () => {
  assert.deepEqual(coerceCell('a, b,c', { id: 'l', type: 'list' }), ['a', 'b', 'c']);
});

test('coerceCell: a labelled property stores its key for its label; an unknown word stays', () => {
  const p = { id: 'k', type: 'text', labels: { direct_drive: 'Direct drive' } };
  assert.equal(coerceCell('Direct drive', p), 'direct_drive');
  assert.equal(coerceCell('direct_drive', p), 'direct_drive');
  assert.equal(coerceCell('Geared', p), 'Geared');
});

test('coerceCell: a rich cell keeps its other keys; a why goes once there is a value', () => {
  assert.deepEqual(coerceCell('5', num, { value: 3, unit: 'N·m', basis: 'measured' }), { value: 5, unit: 'N·m', basis: 'measured' });
  assert.deepEqual(coerceCell('words', text, { value: 'old', attachments: [{ url: 'a.png' }] }), { value: 'words', attachments: [{ url: 'a.png' }] });
  assert.deepEqual(coerceCell('5', num, { value: null, why: 'not measured' }), { value: 5 });
  assert.deepEqual(coerceCell('', num, { value: null, why: 'not measured' }), { value: null, why: 'not measured' });
});

const leaf = (id, extra = {}) => ({ id, key: id, p: { id, type: 'text', ...extra } });
const LEAVES = [leaf('a'), leaf('lock'), leaf('n', { type: 'number' }), leaf('z')];
const ROWS = [{ id: 'r1', a: 'A1', lock: 'L1', n: 1, z: 'Z1' }, { id: 'r2', a: 'A2', lock: 'L2', n: 2, z: 'Z2' }, { id: 'r3', a: 'A3', lock: 'L3', n: 3, z: 'Z3', frozen: true }];
const plan = (block, at, opts = {}) => planPaste({ block, rows: ROWS, leaves: LEAVES, at, can: (row, l) => l.id !== 'lock' && !row.frozen, takes: (l) => l.id !== 'lock', canAdd: true, ...opts });

test('planPaste: fills across and down from the anchor, by position', () => {
  const r = plan([['x', 'skip', '9'], ['y', 'skip', '8']], { row: 0, leaf: 0 });
  assert.deepEqual(r.edits, [{ id: 'r1', set: { a: 'x', n: 9 } }, { id: 'r2', set: { a: 'y', n: 8 } }]);
  assert.deepEqual(r.adds, []);
  assert.equal(r.filled, 4);
  assert.equal(r.locked, 2);
  assert.equal(r.pastColumn, 0);
  assert.equal(r.pastRow, 0);
});

test('planPaste: a locked row is skipped and counted, and the rows around it still fill', () => {
  const r = plan([['x'], ['y']], { row: 1, leaf: 0 });
  assert.deepEqual(r.edits, [{ id: 'r2', set: { a: 'x' } }]);
  assert.equal(r.locked, 1);
});

test('planPaste: a value past the last column is counted', () => {
  const r = plan([['p', 'q', 'r']], { row: 0, leaf: 2 });
  assert.deepEqual(r.edits, [{ id: 'r1', set: { n: 'p', z: 'q' } }]);
  assert.equal(r.pastColumn, 1);
});

test('planPaste: past the last row it adds rows when canAdd holds, keeping the block in order', () => {
  const rows = ROWS.slice(0, 2);
  const r = plan([['x'], ['y'], ['z']], { row: 1, leaf: 0 }, { rows });
  assert.deepEqual(r.edits, [{ id: 'r2', set: { a: 'x' } }]);
  assert.deepEqual(r.adds, [{ set: { a: 'y' }, at: 'end' }, { set: { a: 'z' }, at: 'end' }]);
  assert.equal(r.filled, 3);
});

test('planPaste: a new row takes only what a new row can; a locked column there is counted', () => {
  const r = plan([['x', 'skip', '5']], { row: 0, leaf: 0 }, { rows: [] });
  assert.deepEqual(r.adds, [{ set: { a: 'x', n: 5 }, at: 'end' }]);
  assert.equal(r.locked, 1);
});

test('planPaste: past the last row with canAdd false nothing is added and the cells are counted', () => {
  const r = plan([['x', '', '1'], ['y', '', '2']], { row: 2, leaf: 2 }, { rows: ROWS.slice(0, 3), canAdd: false, can: (row, l) => l.id !== 'lock' });
  assert.equal(r.adds.length, 0);
  assert.equal(r.pastRow, 2);
});

test('planPaste: a cell already holding the value is filled and proposes nothing', () => {
  const r = plan([['A1', 'skip', '1']], { row: 0, leaf: 0 });
  assert.deepEqual(r.edits, []);
  assert.equal(r.filled, 2);
});

test('planPaste: an empty cell clears; a blank line past the last row adds nothing', () => {
  const r = plan([['']], { row: 0, leaf: 0 });
  assert.deepEqual(r.edits, [{ id: 'r1', set: { a: null } }]);
  const s = plan([['y'], ['']], { row: 0, leaf: 0 }, { rows: [] });
  assert.deepEqual(s.adds, [{ set: { a: 'y' }, at: 'end' }]);
});
