// The dashboard editor's pure half (packages/dashboard/src/edit/): every control ends in these text edits. Written red, before
// the code; never edited after. WHY the text is the oracle: a dashboard is a file people and agents both edit ("Humans
// curate, AI builds", Zach 2026-10-29), so where an edit has one right answer the expected text is built here from the
// fixture's literal lines and must equal the result to the byte. Across the gallery's real dashboards, where the expected
// text cannot be written by hand, the parsed result is compared with the parsed file changed by hand, and no comment may go.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseBase } from '../../packages/core/src/base.js';
import { readDashboard } from '../../packages/dashboard/src/model.js';
import {
  panelsOf, movePanel, orderPanels, updatePanel, resizePanel, renamePanel, removePanel, hidePanel, groupPanels, ungroupPanel, addPanel,
  panelSpec, updateView, setSignal, setViewType, convertView, typesFor, setPanelText, lineDiff, hunks, changeList, arrangeText, layoutOnly,
} from '../../packages/dashboard/src/edit/ops.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DIR = join(ROOT, 'tests', 'browser', 'fixtures', 'dash_editor');
const SERVO = readFileSync(join(DIR, 'servo.base'), 'utf8');
const SAVED = readFileSync(join(DIR, 'saved.base'), 'utf8');
const BASE = 'http://127.0.0.1:4610/tests/browser/fixtures/dash_editor/servo.base';
const SHELF = 'http://127.0.0.1:4610/tests/browser/fixtures/dash_editor/saved.base';
const CLI = join(ROOT, 'bin', 'data-ui.mjs');
const HAS_PY = spawnSync('python3', ['-c', 'import yaml, jsonschema'], { stdio: 'ignore' }).status === 0;
const COLUMNS = { numbers: ['t', 'q_deg', 'qd_deg_s', 'tau_nm'], texts: ['run', 'situation', 'source', 'device'], labels: {} };

const L = {
  duration: '    - { "view": Duration, w: 4 }  # quoted by hand, and an edit keeps the quotes\n',
  logged: '    - { view: Logged at, w: 4 }\n',
  playback: '    - { view: Playback, w: 12 }\n',
  angle: '    - { view: Angle, w: 6, h: 3 }  # the tracking plot\n',
  velocity: '    - { view: Velocity, w: 6, h: 3 }\n',
  runsW: '      # a comment inside an entry stays with it\n      w: 12\n      h: 3\n',
  note: `    # the agent's note on what the twin check means\n    - text: "**Twin check** · each real run's command is replayed through its motor's twin (bam_rack_twin); *Twin q RMS* is real − twin, in mrad."\n      w: 12\n`,
};

const idx = (text, name) => panelsOf(text).find((p) => p.name === name || (p.views[0] && p.views[0].name === name)).i;
const comments = (text) => text.split('\n').filter((l) => l.trim().startsWith('#'));

function checkers(text) {
  const dir = mkdtempSync(join(tmpdir(), 'dash-editor-'));
  for (const f of ['runs.json', 'samples.json']) cpSync(join(DIR, f), join(dir, f));
  const path = join(dir, 'out.base');
  writeFileSync(path, text);
  const js = spawnSync('node', [CLI, 'check', path], { cwd: ROOT });
  const py = HAS_PY ? spawnSync('python3', [join(ROOT, 'tools', 'check_views.py'), path], { cwd: ROOT }) : { status: 0 };
  return { js: js.status, py: py.status, out: `${js.stdout}${js.stderr}${py.stdout || ''}${py.stderr || ''}` };
}

function task(text) {
  const torque = panelSpec(SAVED, idx(SAVED, 'Torque'), { base: SHELF });
  let t = addPanel(text, torque, { base: BASE, at: idx(text, 'Angle') });
  t = resizePanel(t, idx(t, 'Torque'), { w: 6 });
  t = removePanel(t, panelsOf(t).find((p) => p.text !== null).i);
  t = renamePanel(t, idx(t, 'Velocity'), 'Joint velocity');
  t = setViewType(t, 'Velocity', 'table', { columns: COLUMNS }).text;
  return t;
}

test('the task through ops gives the babble\'s outcome, both checkers accept it, every comment but the note\'s stays', () => {
  const out = task(SERVO);
  const doc = parseBase(out);
  assert.deepEqual(doc.layout.panels.map((p) => p.view || 'text'), ['Twin q RMS', 'Duration', 'Logged at', 'Runs', 'Playback', 'Torque', 'Angle', 'Velocity']);
  const entry = Object.fromEntries(doc.layout.panels.map((p) => [p.view, p]));
  assert.equal(entry.Torque.w, 6);
  assert.equal(entry.Velocity.title, 'Joint velocity');
  assert.equal(entry.Velocity.key, 'velocity', 'the rename pins the key the panel had');
  const views = Object.fromEntries(doc.views.map((v) => [v.name, v]));
  assert.equal(views.Torque.from, 'samples', 'Torque reuses the samples dataset (the same file)');
  assert.equal(views.Velocity.type, 'table');
  assert.deepEqual(views.Velocity.order, ['t', 'situation', 'qd_deg_s']);
  assert.deepEqual(Object.keys(doc.datasets), ['runs', 'samples'], 'no dataset added');
  const gone = comments(SERVO).filter((l) => !comments(out).includes(l)).map((l) => l.trim());
  assert.deepEqual(gone, ["# the agent's note on what the twin check means"]);
  const r = checkers(out);
  assert.equal(r.js, 0, r.out);
  assert.equal(r.py, 0, r.out);
});

test('a size changes one token: a flow entry keeps its other keys, its spacing, its quotes and its trailing comment', () => {
  assert.equal(resizePanel(SERVO, idx(SERVO, 'Angle'), { w: 4 }), SERVO.replace(L.angle, L.angle.replace('w: 6', 'w: 4')));
  assert.equal(resizePanel(SERVO, idx(SERVO, 'Duration'), { w: 3 }), SERVO.replace(L.duration, L.duration.replace('w: 4', 'w: 3')));
  assert.equal(resizePanel(SERVO, idx(SERVO, 'Angle'), { h: 5 }), SERVO.replace(L.angle, L.angle.replace('h: 3', 'h: 5')));
  assert.equal(updatePanel(SERVO, idx(SERVO, 'Logged at'), { h: 2 }), SERVO.replace(L.logged, '    - { view: Logged at, w: 4, h: 2 }\n'));
  assert.equal(resizePanel(SERVO, idx(SERVO, 'Angle'), { h: null }), SERVO.replace(L.angle, '    - { view: Angle, w: 6 }  # the tracking plot\n'));
  assert.equal(updatePanel(SERVO, idx(SERVO, 'Angle'), { toolbar: 'full' }), SERVO.replace(L.angle, L.angle.replace('h: 3 }', 'h: 3, toolbar: full }')));
});

test('a block entry changes on its own line; a new key goes after its last key; the comment inside stays', () => {
  assert.equal(resizePanel(SERVO, idx(SERVO, 'Runs'), { w: 8 }), SERVO.replace(L.runsW, L.runsW.replace('w: 12', 'w: 8')));
  assert.equal(updatePanel(SERVO, idx(SERVO, 'Runs'), { toolbar: 'full' }), SERVO.replace(L.runsW, `${L.runsW}      toolbar: full\n`));
  assert.equal(resizePanel(SERVO, idx(SERVO, 'Runs'), { h: null }), SERVO.replace(L.runsW, L.runsW.replace('      h: 3\n', '')));
});

test('a rename writes the title and pins the key; back to the view\'s name drops the title; odd text stays valid YAML', () => {
  const c = renamePanel(SERVO, idx(SERVO, 'Angle'), 'Joint angle');
  assert.equal(c, SERVO.replace(L.angle, '    - { view: Angle, w: 6, h: 3, title: Joint angle, key: angle }  # the tracking plot\n'));
  const e = renamePanel(c, idx(c, 'Angle'), 'Angle');
  assert.ok(e.includes('- { view: Angle, w: 6, h: 3, key: angle }  # the tracking plot'), 'the pinned key stays: the URL state keyed by it keeps working');
  for (const title of ['Angle: #1 (deg)', "it's [odd], really", 'a: b # c', 'true']) {
    const t = renamePanel(SERVO, idx(SERVO, 'Angle'), title);
    assert.equal(parseBase(t).layout.panels[idx(SERVO, 'Angle')].title, title);
  }
});

test('a move keeps every line byte for byte (only their order changes); comments ride with their entry', () => {
  const text = movePanel(SERVO, panelsOf(SERVO).find((p) => p.text !== null).i, 0);
  assert.equal(text, SERVO.replace(L.note, '').replace('  panels:\n', `  panels:\n${L.note}`));
  assert.equal(movePanel(text, 0, panelsOf(SERVO).length - 1), SERVO, 'and back, to the byte');
  assert.equal(movePanel(SERVO, idx(SERVO, 'Playback'), idx(SERVO, 'Velocity')), SERVO.replace(L.playback, '').replace(L.velocity, L.velocity + L.playback));
  const n = panelsOf(SERVO).length;
  assert.deepEqual([...orderPanels(SERVO, [...Array(n).keys()].reverse()).split('\n')].sort(), [...SERVO.split('\n')].sort());
});

test('hide writes one key where the entry sits, show is its exact inverse, in a flow entry and in a block entry', () => {
  const a = hidePanel(SERVO, idx(SERVO, 'Angle'), true);
  assert.equal(a, SERVO.replace(L.angle, L.angle.replace('h: 3 }', 'h: 3, hidden: true }')));
  assert.equal(hidePanel(a, idx(SERVO, 'Angle'), false), SERVO);
  const b = hidePanel(SERVO, idx(SERVO, 'Runs'), true);
  assert.equal(b, SERVO.replace(L.runsW, `${L.runsW}      hidden: true\n`));
  assert.equal(hidePanel(b, idx(SERVO, 'Runs'), false), SERVO);
  const r = checkers(a);
  assert.equal(r.js, 0, r.out);
  assert.equal(r.py, 0, r.out);
});

test('group as tabs changes the entry in place and takes the other\'s line; a tab taken out is the exact inverse', () => {
  const g = groupPanels(SERVO, idx(SERVO, 'Velocity'), idx(SERVO, 'Angle'));
  assert.equal(g, SERVO.replace(L.angle, L.angle.replace('view: Angle', 'views: [Angle, Velocity]')).replace(L.velocity, ''));
  assert.equal(ungroupPanel(g, idx(g, 'Angle'), 'Velocity'), SERVO);
  assert.throws(() => groupPanels(SERVO, idx(SERVO, 'Runs'), idx(SERVO, 'Angle')), /one dataset/);
  assert.throws(() => groupPanels(SERVO, panelsOf(SERVO).find((p) => p.text !== null).i, idx(SERVO, 'Angle')));
  const r = checkers(g);
  assert.equal(r.js, 0, r.out);
  assert.equal(r.py, 0, r.out);
});

test('remove takes the entry, the comment right above it, and its view when no other panel names it', () => {
  assert.equal(removePanel(SERVO, panelsOf(SERVO).find((p) => p.text !== null).i), SERVO.replace(L.note, ''));
  const gone = removePanel(SERVO, idx(SERVO, 'Angle'));
  assert.ok(!parseBase(gone).views.some((v) => v.name === 'Angle'));
  assert.ok(gone.includes('# the velocity plot: a comment above a view stays with it'));
  assert.equal(removePanel(SERVO, idx(SERVO, 'Angle'), { dropViews: false }), SERVO.replace(L.angle, ''));
});

test('a signal changes one token inside a flow map; its quotes stay', () => {
  const s = setSignal(SERVO, 'Angle', 'tau_nm');
  assert.equal(s, SERVO.replace("timeseries: { x: t, 'y': q_deg,", "timeseries: { x: t, 'y': tau_nm,"));
});

test('a view type changes only the keys that differ: the name line\'s comment and the comment above stay', () => {
  const { text, stash } = setViewType(SERVO, 'Velocity', 'table', { columns: COLUMNS });
  const d = lineDiff(SERVO, text).filter((x) => x.op !== ' ');
  assert.deepEqual(d.filter((x) => x.op === '-').map((x) => x.line.trim()), ['- type: timeseries', "timeseries: { x: t, 'y': qd_deg_s, series: situation, dash: [target], legend: top, unit: '°/s' }"]);
  for (const line of ['  # the velocity plot: a comment above a view stays with it', '    name: Velocity  # a comment on the name line stays too', '    from: samples', '    # the same axes as Angle']) assert.ok(text.includes(`${line}\n`), line);
  assert.equal(parseBase(text).views.find((v) => v.name === 'Velocity').type, 'table');
  const back = setViewType(text, 'Velocity', 'timeseries', { columns: COLUMNS, stash });
  assert.deepEqual(parseBase(back.text).views.find((v) => v.name === 'Velocity'), parseBase(SERVO).views.find((v) => v.name === 'Velocity'), 'back, as written');
});

test('only types that can draw the view are offered; every offer passes both checkers; a type with no conversion offers itself', () => {
  assert.deepEqual(typesFor({ type: 'playback' }, COLUMNS), ['playback']);
  assert.deepEqual(typesFor({ type: 'scene3d' }, COLUMNS), ['scene3d']);
  assert.deepEqual(typesFor({ type: 'table' }, { numbers: [], texts: ['a'], labels: {} }), ['table', 'list'], 'no number column: nothing to plot');
  for (const name of ['Angle', 'Runs', 'Twin q RMS']) {
    const v = parseBase(SERVO).views.find((x) => x.name === name);
    const columns = name === 'Angle' ? COLUMNS : { numbers: ['duration_s', 'q_rms_mrad', 'rate_hz'], texts: ['run', 'kind'], labels: {} };
    for (const type of typesFor(v, columns)) {
      if (type === (v.type || 'table')) continue;
      const { text } = setViewType(SERVO, name, type, { columns });
      const r = checkers(text);
      assert.equal(r.js, 0, `${name} as ${type}: ${r.out}`);
      assert.equal(r.py, 0, `${name} as ${type}: ${r.out}`);
    }
  }
  const v = parseBase(SERVO).views.find((x) => x.name === 'Angle');
  const t = convertView(v, 'table', { columns: COLUMNS });
  const c = convertView(t.view, 'chart', { columns: COLUMNS, stash: t.stash });
  assert.deepEqual(convertView(c.view, 'timeseries', { columns: COLUMNS, stash: c.stash }).view, v, 'through two types and back: exactly as written');
});

test('placing an item only adds lines; its dataset is found by file; a taken name takes a suffix; placed anywhere', () => {
  const spec = panelSpec(SAVED, idx(SAVED, 'Torque'), { base: SHELF });
  const t = addPanel(SERVO, spec, { base: BASE, at: idx(SERVO, 'Angle') });
  assert.equal(lineDiff(SERVO, t).filter((x) => x.op === '-').length, 0);
  assert.ok(t.includes(`    - { view: Torque, h: 3 }\n${L.angle}`));
  assert.equal(t.slice(0, t.indexOf('layout:')), SERVO.slice(0, SERVO.indexOf('layout:')));
  const again = addPanel(t, spec, { base: BASE });
  assert.ok(again.includes('name: Torque (2)'));
  const r = checkers(again);
  assert.equal(r.js, 0, r.out);
});

test('a note\'s text stays on its line, however odd the new text; its width line stays', () => {
  const i = panelsOf(SERVO).find((p) => p.text !== null).i;
  const out = setPanelText(SERVO, i, 'Two: lines\nand a "quote" # not a comment');
  assert.equal(parseBase(out).layout.panels[i].text, 'Two: lines\nand a "quote" # not a comment');
  assert.equal(out.replace(/^ {4}- text: .*$/m, '@'), SERVO.replace(/^ {4}- text: .*$/m, '@'), 'every other line as written');
});

test('CRLF stays CRLF, an open last line stays open', () => {
  const crlf = SERVO.replace(/\n/g, '\r\n');
  for (const [name, edit] of [['resize', (t) => resizePanel(t, idx(t, 'Angle'), { w: 4 })], ['hide', (t) => hidePanel(t, idx(t, 'Runs'), true)], ['move', (t) => movePanel(t, 0, 3)], ['type', (t) => setViewType(t, 'Velocity', 'table', { columns: COLUMNS }).text]]) {
    const out = edit(crlf);
    assert.ok(!/[^\r]\n/.test(out), `${name}: every newline is CRLF`);
    assert.equal(out.replace(/\r\n/g, '\n'), edit(SERVO), `${name}: otherwise the same edit`);
  }
  const open = SERVO.replace(/\n$/, '');
  assert.ok(!resizePanel(open, idx(open, 'Angle'), { w: 4 }).endsWith('\n'));
  assert.ok(!setSignal(open, 'Velocity', 'tau_nm').endsWith('\n'));
});

test('a layout written in flow style is the one block rewritten (§34\'s exception), and the rest of the file stays', () => {
  const head = '# a comment\ndata: runs.json\n';
  const tail = 'views:\n  # kept\n  - { type: table, name: A }\n  - { type: table, name: B }\n';
  const flow = `${head}layout: { panels: [{ view: A }, { view: B, w: 6 }] }\n${tail}`;
  const moved = movePanel(flow, 1, 0);
  assert.deepEqual(parseBase(moved).layout.panels, [{ view: 'B', w: 6 }, { view: 'A' }]);
  assert.ok(moved.startsWith(head) && moved.endsWith(tail));
  const sized = resizePanel(flow, 0, { w: 4 });
  assert.deepEqual(parseBase(sized).layout.panels[0], { view: 'A', w: 4 });
  const list = `${head}layout:\n  panels: [{ view: A }, { view: B, w: 6 }]\n${tail}`;
  assert.deepEqual(parseBase(hidePanel(list, 1, true)).layout.panels[1], { view: 'B', w: 6, hidden: true });
});

test('every dashboard in the gallery takes every edit: the parsed file changes by exactly that, one or two lines, no comment lost', () => {
  const ex = join(ROOT, 'gallery', 'examples');
  const files = readdirSync(ex).map((d) => join(ex, d, 'views.base')).filter((f) => existsSync(f) && /^layout:/m.test(readFileSync(f, 'utf8')));
  assert.ok(files.length >= 10, `${files.length} dashboards`);
  let edits = 0;
  for (const file of files) {
    const text = readFileSync(file, 'utf8');
    const doc = parseBase(text);
    for (const p of panelsOf(text)) {
      const want = (patch) => { const d = JSON.parse(JSON.stringify(doc)); Object.assign(d.layout.panels[p.i], patch); return d; };
      const cases = [[resizePanel(text, p.i, { w: 5 }), { w: 5 }], [hidePanel(text, p.i, true), { hidden: true }], [updatePanel(text, p.i, { h: 7 }), { h: 7 }]];
      for (const [out, patch] of cases) {
        assert.deepEqual(parseBase(out), JSON.parse(JSON.stringify(want(patch))), `${file} panel ${p.i}`);
        assert.deepEqual(comments(out), comments(text), `${file} panel ${p.i}: a comment went`);
        const d = lineDiff(text, out).filter((x) => x.op !== ' ');
        assert.ok(d.length <= 2, `${file} panel ${p.i}: ${d.length} lines changed: ${d.map((x) => x.line).join(' | ')}`);
        edits++;
      }
      const up = movePanel(text, p.i, 0);
      assert.equal(comments(up).length, comments(text).length, `${file} panel ${p.i}: a move lost a comment`);
      assert.deepEqual([...up.split('\n')].filter(Boolean).sort(), [...text.split('\n')].filter(Boolean).sort(), `${file} panel ${p.i}: a move changed a line`);
      edits++;
    }
    for (const v of (doc.views || []).filter((x) => x && x.name)) {
      const out = updateView(text, v.name, (x) => ({ ...x, description: 'kept: as written' }));
      const d = JSON.parse(JSON.stringify(doc));
      d.views.find((x) => x.name === v.name).description = 'kept: as written';
      assert.deepEqual(parseBase(out), d, `${file} view ${v.name}`);
      assert.deepEqual(comments(out), comments(text), `${file} view ${v.name}: a comment went`);
      assert.ok(lineDiff(text, out).filter((x) => x.op !== ' ').length <= 2, `${file} view ${v.name}`);
      edits++;
    }
  }
  assert.ok(edits > 500, `${edits} edits`);
});

test('arrangeText writes the order and only the sizes a reader changed; a hidden entry keeps its slot', () => {
  const nodes = (text) => panelsOf(text).filter((p) => !p.hidden).map((p) => ({ key: p.key, w: p.w, h: p.h || 2 }));
  const was = Object.fromEntries(nodes(SERVO).map((n) => [n.key, n]));
  const order = nodes(SERVO);
  assert.equal(arrangeText(SERVO, order, was), SERVO, 'nothing moved: nothing written');
  const swapped = [...order];
  [swapped[5], swapped[6]] = [swapped[6], swapped[5]];
  assert.equal(arrangeText(SERVO, swapped, was), SERVO.replace(L.angle + L.velocity, L.velocity + L.angle));
  const wider = order.map((n) => (n.key === 'angle' ? { ...n, w: 4 } : n));
  assert.equal(arrangeText(SERVO, wider, was), SERVO.replace(L.angle, L.angle.replace('w: 6', 'w: 4')));
  const hid = hidePanel(SERVO, idx(SERVO, 'Playback'), true);
  const left = nodes(hid);
  const a = left.findIndex((n) => n.key === 'runs');
  const b = left.findIndex((n) => n.key === 'angle');
  [left[a], left[b]] = [left[b], left[a]];
  const out = arrangeText(hid, left, Object.fromEntries(nodes(hid).map((n) => [n.key, n])));
  assert.deepEqual(parseBase(out).layout.panels.map((p) => p.view || 'text'), ['Twin q RMS', 'Duration', 'Logged at', 'Angle', 'Playback', 'Runs', 'Velocity', 'text'], 'Playback stays the fifth entry');
});

test('layoutOnly tells a layout edit, which redraws nothing, from one that needs the panels drawn again', () => {
  assert.equal(layoutOnly(SERVO, movePanel(SERVO, 0, 2)), true);
  assert.equal(layoutOnly(SERVO, resizePanel(SERVO, idx(SERVO, 'Angle'), { w: 4 })), true);
  assert.equal(layoutOnly(SERVO, renamePanel(SERVO, idx(SERVO, 'Angle'), 'New')), false);
  assert.equal(layoutOnly(SERVO, setSignal(SERVO, 'Angle', 'tau_nm')), false);
  assert.equal(layoutOnly(SERVO, hidePanel(SERVO, idx(SERVO, 'Angle'), true)), false);
  assert.equal(layoutOnly(SERVO, removePanel(SERVO, idx(SERVO, 'Angle'))), false);
  const note = panelsOf(SERVO).find((p) => p.text !== null).i;
  assert.equal(layoutOnly(SERVO, movePanel(SERVO, note, 0)), false, 'a note\'s key is its place in the list, so moving it renames a panel');
});

test('the change list names what a reader did, in words, and hide, tabs and placement among them', () => {
  const words = changeList(SERVO, task(SERVO)).map((c) => c.detail);
  assert.deepEqual(words.slice(0, 1), ['Added Torque, above Angle']);
  assert.ok(words.some((w) => /^Removed the note “Twin check/.test(w)), words.join(' | '));
  assert.ok(words.includes('Renamed Velocity to Joint velocity'), words.join(' | '));
  assert.ok(words.includes('Joint velocity: Time series → Table'), words.join(' | '));
  assert.deepEqual(changeList(SERVO, movePanel(SERVO, idx(SERVO, 'Velocity'), 0)).map((c) => c.detail), ['Moved Velocity'], 'one panel moved is one move, not every panel it passed');
  assert.deepEqual(changeList(SERVO, hidePanel(SERVO, idx(SERVO, 'Angle'), true)).map((c) => c.detail), ['Hid Angle']);
  assert.deepEqual(changeList(hidePanel(SERVO, idx(SERVO, 'Angle'), true), SERVO).map((c) => c.detail), ['Showed Angle']);
  assert.deepEqual(changeList(SERVO, groupPanels(SERVO, idx(SERVO, 'Velocity'), idx(SERVO, 'Angle'))).map((c) => c.detail), ['Grouped Velocity into Angle as a tab']);
});

test('a diff is exact, and a hunk keeps two lines of context', () => {
  const after = resizePanel(SERVO, idx(SERVO, 'Angle'), { w: 4 });
  const d = lineDiff(SERVO, after);
  assert.deepEqual(d.filter((x) => x.op !== ' ').map((x) => `${x.op}${x.line}`), [`-${L.angle.trimEnd()}`, `+${L.angle.trimEnd().replace('w: 6', 'w: 4')}`]);
  const h = hunks(d, 2);
  assert.equal(h.length, 6);
  assert.deepEqual(h.map((x) => x.op), [' ', ' ', '-', '+', ' ', ' ']);
});

test('a hidden panel leaves the layout, keeps its key and its neighbours\' keys, and the model lists it', () => {
  const text = hidePanel(SERVO, idx(SERVO, 'Angle'), true);
  const d = readDashboard(parseBase(text));
  assert.ok(!d.panels.some((p) => p.key === 'angle'));
  assert.deepEqual(d.hidden.map((p) => p.key), ['angle']);
  assert.deepEqual(d.problems, []);
  assert.deepEqual(panelsOf(text).map((p) => [p.key, !!p.hidden]).filter((x) => x[1]), [['angle', true]]);
  const video = 'data: a.json\nclock: { data: a, primary: Clip }\nlayout:\n  panels:\n    - { view: Clip, hidden: true }\n    - { view: T }\nviews:\n  - { type: video, name: Clip }\n  - { type: table, name: T }\n';
  assert.deepEqual(readDashboard(parseBase(video)).problems, [], 'clock.primary may name a hidden card');
  const dup = 'data: a.json\nlayout:\n  panels:\n    - { view: T, hidden: true }\n    - { view: T }\nviews:\n  - { type: table, name: T }\n';
  assert.deepEqual(readDashboard(parseBase(dup)).panels.map((p) => p.key), ['t-2'], 'a key does not change when the panel before it is hidden');
});

test('hidden is a key both checkers read, and they refuse the wrong shape', () => {
  const bad = SERVO.replace(L.angle, '    - { view: Angle, hidden: yes please }\n');
  const r = checkers(bad);
  assert.notEqual(r.js, 0, r.out);
  if (HAS_PY) assert.notEqual(r.py, 0, r.out);
});

test('the editor\'s CSS: every rule is prefixed, every colour a token', () => {
  const css = readFileSync(join(ROOT, 'packages', 'dashboard', 'src', 'edit', 'edit.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
  assert.ok(!/#[0-9a-f]{3,8}\b/i.test(css), 'a raw hex colour');
  assert.ok(!/\b(?:rgb|rgba|hsl|hsla|oklch)\(/i.test(css), 'a raw colour function');
  assert.ok(!/:\s*(?:white|black|red|green|blue|gray|grey)\b/i.test(css.replace(/color-mix\([^;]*;/g, ';')), 'a named colour');
  const selectors = css.replace(/@media[^{]*\{/g, '').replace(/@container[^{]*\{/g, '').replace(/@supports[^{]*\{/g, '').replace(/\{[^{}]*\}/g, '\u0001').split('\u0001').map((s) => s.trim()).filter((s) => s && s !== '}');
  assert.ok(selectors.length > 30, `${selectors.length} selectors`);
  for (const group of selectors) {
    for (const s of group.replace(/^\}\s*/, '').split(/,(?![^(]*\))/).map((x) => x.trim()).filter(Boolean)) {
      assert.ok(/^(?:\.dde-|data-dashboard\[data-editing\]|:root\b|\.dd-panel\[data-dde-)/.test(s) || /\.dde-|\[data-dde/.test(s), `an unprefixed rule: ${s}`);
    }
  }
});

test('one kind of side panel: every pane is made by pane.js, which owns the handle and the fold; nothing of the babble ships', () => {
  const dir = join(ROOT, 'packages', 'dashboard', 'src', 'edit');
  const files = readdirSync(dir).filter((f) => f.endsWith('.js'));
  for (const f of files) {
    const src = readFileSync(join(dir, f), 'utf8');
    if (f !== 'pane.js') {
      assert.ok(!/makeResizable\(/.test(src), `${f} makes its own resizable panel: pane.js owns that`);
      assert.ok(!/createElement\('aside'\)|<aside/.test(src), `${f} makes its own side panel: pane.js owns that`);
    }
    assert.ok(!/edit-variant|edit-switcher|mountSwitcher/.test(src), `${f} still speaks of the switcher`);
  }
  for (const gone of ['v3-source.js', 'v4-saved.js', 'v5-ask.js', 'agent.js', 'variant.js']) assert.ok(!files.includes(gone), gone);
  const pane = readFileSync(join(dir, 'pane.js'), 'utf8');
  assert.ok(/makeResizable\(/.test(pane) && /dde-fold/.test(pane), 'pane.js gives every pane its boundary and its fold');
  for (const f of ['index.js', 'arrange.js']) assert.ok(!/edit-variant|edit-switcher/.test(readFileSync(join(ROOT, 'packages', 'dashboard', 'src', f), 'utf8')), f);
  const arrange = readFileSync(join(ROOT, 'packages', 'dashboard', 'src', 'arrange.js'), 'utf8');
  assert.ok(/export function liveGrid/.test(arrange), 'one gridstack path: arrange.js');
  assert.equal(files.filter((f) => /GridStack\.init|from 'gridstack'/.test(readFileSync(join(dir, f), 'utf8'))).length, 0, 'the editor has no gridstack of its own');
});
