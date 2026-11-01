// PEP 0010 P5: the status vocabulary (packages/core/src/status.js; docs/CONTRACT.md §35) and `display: status`, pure.
// One word list for the gates' verdicts (pass, warn, partial, fail, not_run) and RobotDx's levels (ok, warn, error,
// unknown, stale): each word's tone and glyph (PEP 0010 §7: "always a glyph and a word: ✓ pass, ! warn, ✕ fail, – not
// run, ? unknown, ◷ stale"), the order worst-of reads (RobotDx's ranks: ok 0 < warn 1 < unknown and not run 2 < stale 3 <
// error and fail 4), which map wins (the view's, then the column's, then the list), a value read as stored then as its
// label, and the badge's markup. Also: a field schema's `tones` reaches the property (data.js), the tone tokens are core
// tokens in light and dark (tokens.css), and the analyses' `this.` binding is the core's (sections.js), one function.
// Written red, before the code.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { STATUS, STATUS_ORDER, TONE_GLYPH, statusOf, worstStatus, statusHtml } from '../../packages/core/src/status.js';
import { valueHtml } from '../../packages/core/src/format.js';
import { fieldToProperty } from '../../packages/core/src/data.js';
import { bindThis as coreBind } from '../../packages/core/src/sections.js';
import { bindThis as analysisBind } from '../../packages/analysis/src/format.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

test('the vocabulary: every word of both feeds with its tone and glyph', () => {
  const want = {
    pass: ['good', '✓'], ok: ['good', '✓'],
    warn: ['warn', '!'], warning: ['warn', '!'], partial: ['warn', '!'],
    fail: ['bad', '✕'], error: ['bad', '✕'],
    not_run: ['muted', '–'], 'not run': ['muted', '–'], unknown: ['muted', '?'], stale: ['muted', '◷'],
  };
  for (const [word, [tone, glyph]] of Object.entries(want)) {
    assert.deepEqual([STATUS[word].tone, STATUS[word].glyph], [tone, glyph], word);
    const s = statusOf(word);
    assert.deepEqual([s.word, s.tone, s.glyph, s.known], [word, tone, glyph, true], word);
  }
  assert.deepEqual(Object.keys(STATUS).sort(), Object.keys(want).sort());
  assert.deepEqual(TONE_GLYPH, { good: '✓', warn: '!', bad: '✕', muted: '–', neutral: '•' });
});

test('a word the list does not hold is neutral (•); a missing value is muted and reads "no value"', () => {
  assert.deepEqual((({ word, tone, glyph, known }) => ({ word, tone, glyph, known }))(statusOf('mixed')), { word: 'mixed', tone: 'neutral', glyph: '•', known: false });
  for (const missing of [null, undefined, '']) {
    const s = statusOf(missing);
    assert.deepEqual([s.word, s.tone, s.glyph], ['no value', 'muted', '–'], String(missing));
  }
  // a rich cell is read by its value
  assert.equal(statusOf({ value: 'fail', basis: 'derived' }).tone, 'bad');
});

test('a value is looked up as stored, then as its label: a rank labelled {4: fail} reads fail', () => {
  const rank = { labels: { 0: 'pass', 1: 'warn', 2: 'not run', 4: 'fail' } };
  assert.deepEqual((({ word, tone, glyph }) => ({ word, tone, glyph }))(statusOf(4, { column: rank })), { word: 'fail', tone: 'bad', glyph: '✕' });
  assert.deepEqual((({ word, tone }) => ({ word, tone }))(statusOf(2, { column: rank })), { word: 'not run', tone: 'muted' });
  // a stored word with a label keeps its own tone and shows the label
  const v = statusOf('not_run', { column: { labels: { not_run: 'not run' } } });
  assert.deepEqual([v.word, v.tone, v.glyph], ['not run', 'muted', '–']);
});

test('which map wins: the view\'s, then the column\'s, then the list; an overridden tone takes that tone\'s glyph', () => {
  assert.deepEqual([statusOf('mixed', { column: { tones: { mixed: 'warn' } } }).tone, statusOf('mixed', { column: { tones: { mixed: 'warn' } } }).glyph], ['warn', '!']);
  assert.equal(statusOf('mixed', { tones: { mixed: 'bad' }, column: { tones: { mixed: 'warn' } } }).tone, 'bad');
  const f = statusOf('fail', { tones: { fail: 'warn' } });
  assert.deepEqual([f.tone, f.glyph], ['warn', '!']);
  // a map naming a tone that is not one is ignored
  assert.equal(statusOf('fail', { tones: { fail: 'crimson' } }).tone, 'bad');
  // the stored value is the key, not the label
  assert.equal(statusOf(4, { tones: { 4: 'warn' }, column: { labels: { 4: 'fail' } } }).tone, 'warn');
});

test('STATUS_ORDER is best to worst, RobotDx\'s ranks; worstStatus reads it (an unlisted word ranks best)', () => {
  assert.deepEqual(STATUS_ORDER, ['ok', 'pass', 'warn', 'warning', 'partial', 'unknown', 'not_run', 'not run', 'stale', 'error', 'fail']);
  assert.equal(worstStatus(['pass', 'warn', 'fail']), 'fail');
  assert.equal(worstStatus(['pass', 'not_run']), 'not_run');
  assert.equal(worstStatus(['warn', 'not_run']), 'not_run');
  assert.equal(worstStatus(['ok', 'stale', 'error']), 'error');
  assert.equal(worstStatus(['mixed', 'pass']), 'pass');
  assert.equal(worstStatus([null, 'pass', undefined]), 'pass');
  assert.equal(worstStatus([]), null);
  assert.equal(worstStatus([null]), null);
  assert.equal(worstStatus(['a', 'b'], ['b', 'a']), 'a');
  assert.equal(worstStatus([{ value: 'warn' }, 'pass']), 'warn');
});

test('statusHtml: the glyph hidden from readers, the word, the tone and the stored value', () => {
  assert.equal(statusHtml('pass'), '<span class="dv-state dv-tone-good" data-state="pass"><span class="dv-state-glyph" aria-hidden="true">✓</span><span class="dv-state-word">pass</span></span>');
  assert.equal(statusHtml(4, { labels: { 4: 'fail' } }), '<span class="dv-state dv-tone-bad" data-state="4"><span class="dv-state-glyph" aria-hidden="true">✕</span><span class="dv-state-word">fail</span></span>');
  // a list: one badge per value
  const two = statusHtml(['pass', 'fail']);
  assert.equal((two.match(/class="dv-state /g) || []).length, 2);
  assert.ok(two.indexOf('data-state="pass"') < two.indexOf('data-state="fail"'));
  // escaped
  const odd = statusHtml('<b>"x"');
  assert.ok(!odd.includes('<b>') && odd.includes('&lt;b&gt;') && odd.includes('data-state="&lt;b&gt;&quot;x&quot;"'), odd);
  // missing: the kit's dash with its reason
  assert.equal(statusHtml(null), '<span class="dv-none" title="no value">—</span>');
  assert.equal(statusHtml({ value: null, why: 'not evaluated' }), '<span class="dv-none" title="not evaluated">—</span>');
  // the view's tones
  assert.ok(statusHtml('mixed', {}, { tones: { mixed: 'warn' } }).startsWith('<span class="dv-state dv-tone-warn"'));
});

test('valueHtml draws a status display as statusHtml does (the peek, the record view, the cards\' fields)', () => {
  const col = { display: 'status', labels: { not_run: 'not run' } };
  for (const v of ['pass', 'fail', 'not_run', null, ['ok', 'error']]) assert.equal(valueHtml(v, col), statusHtml(v, col), JSON.stringify(v));
  // every other display is unchanged
  assert.ok(!valueHtml('pass', { display: 'text' }).includes('dv-state'));
});

test('a field schema\'s tones reach the property (data.js), beside labels and colors', () => {
  const p = fieldToProperty({ name: 'verdict', type: 'string', display: 'status', tones: { partial: 'warn' }, labels: { not_run: 'not run' } });
  assert.deepEqual(p.tones, { partial: 'warn' });
  assert.equal(p.display, 'status');
});

test('the tone tokens are core tokens, light and dark (styles/tokens.css): --dv-tone-good, -warn, -bad, -muted, -neutral', () => {
  const css = readFileSync(join(ROOT, 'packages', 'core', 'styles', 'tokens.css'), 'utf8');
  for (const t of ['good', 'warn', 'bad', 'muted', 'neutral']) {
    const n = css.split(`--dv-tone-${t}:`).length - 1;
    assert.ok(n >= 3, `--dv-tone-${t} in the light block and both dark blocks (found ${n})`);
  }
  // from the host's --data-good / --data-warn / --data-bad
  for (const t of ['good', 'warn', 'bad']) assert.ok(new RegExp(`--dv-tone-${t}:\\s*var\\(--data-${t},`).test(css), t);
});

test('the analyses\' this. binding is the core\'s: one function (sections.js)', () => {
  assert.equal(coreBind, analysisBind);
  assert.equal(coreBind('run == this.run && t >= this.t0', { run: 'r1', t0: 1.5 }), 'run == "r1" && t >= 1.5');
});
