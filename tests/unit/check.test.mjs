// data-ui check (packages/core/src/check.js, bin/data-ui.mjs): the Node checker names the same mistakes as the
// Python proof (tools/check_views.py), on the grammar the page runs.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { existsSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkText } from '../../packages/core/src/check.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const CLI = join(ROOT, 'bin', 'data-ui.mjs');
const VAULT = '~/zach_brain';
const run = (...args) => {
  const r = spawnSync('node', [CLI, 'check', ...args], { cwd: ROOT, maxBuffer: 64 << 20 });
  return { status: r.status, out: r.stdout.toString() };
};

test('broken.base: every mistake on its own line, with its line number and a suggestion (the Python proof\'s list)', () => {
  const { status, out } = run('examples/broken.base', '--data', 'examples/actuators.schema.json');
  assert.equal(status, 1);
  for (const line of [
    "broken.base:3: error: filters: unknown key 'AND' (did you mean 'and'?)",
    "broken.base:11: error: views[0].chart.encoding: unknown key 'colour' (did you mean 'color'?)",
    'views[0].chart.encoding.x.scale.type: "logarithmic" is not one of',
    "(did you mean 'log'?)",
    'broken.base:10: error: views[0].chart.mark: "dots" is not one of',
    "broken.base:19: error: views[1].sort[0].direction: \"desc\" is not one of ASC, DESC (did you mean 'DESC'?)",
    "broken.base:21: error: views[2]: needs 'chart'",
    "warning: views[0].type: data-ui cannot draw type 'chrat' (did you mean 'chart'?)",
    "warning: views[1].groupby: unknown view key 'groupby' (did you mean 'groupBy'?)",
    "views[0].chart.encoding.x.field: 'mas' is not a property of actuators.schema.json (did you mean 'mass'?)",
    "views[1].order[1]: 'peak_torq' is not a property of actuators.schema.json (did you mean 'peak_torque'?)",
    '8 errors, 2 warnings',
  ]) assert.ok(out.includes(line), `missing: ${line}\n${out}`);
});

test('the same counts as the Python checker on every example', { skip: spawnSync('python3', ['-c', 'import yaml, jsonschema'], { stdio: 'ignore' }).status !== 0 && 'PyYAML / jsonschema absent' }, () => {
  for (const [base, data] of [['examples/broken.base', 'examples/actuators.schema.json'], ['examples/actuators.base', 'examples/actuators.schema.json'], ['examples/runs.base', 'examples/runs.schema.json']]) {
    const node = run(base, '--data', data).out.trim().split('\n').at(-1);
    const py = spawnSync('python3', [join(ROOT, 'tools', 'check_views.py'), base, '--data', data], { cwd: ROOT }).stdout.toString().trim().split('\n').at(-1);
    assert.equal(node, py, base);
  }
});

test('the gallery passes, each file against its own data: key', () => {
  const { status, out } = run(...readdirSync(join(ROOT, 'gallery', 'examples')).map((d) => `gallery/examples/${d}/views.base`));
  assert.equal(status, 0, out);
  assert.match(out, /0 errors, 0 warnings/);
});

test('filters: compiled by grammar.js; Obsidian-only expressions are warnings, typos are errors', () => {
  const text = 'views:\n  - type: table\n    name: A\n    filters:\n      and:\n        - \'price <\'\n        - file.inFolder("x")\n        - \'note["vibe-status"] == "done" && temp > -20\'\n';
  const out = checkText(text);
  assert.deepEqual(out.map((p) => [p.level, p.line]), [['error', 6], ['warning', 7]]);
  assert.match(out[0].message, /does not compile: unexpected end/);
  const syntax = checkText('views:\n  - type: table\n  name: x');
  assert.equal(syntax[0].level, 'error');
  assert.match(syntax[0].message, /not valid YAML/);
});

test('every view type and key in docs/VIEWS.md is known before its view is built', () => {
  const text = `views:
  - { type: calendar, name: C, start: started, end: ended, calendarView: week }
  - { type: timeline, name: T, start: started, color: model, zoom: { min: PT1H, max: P1Y } }
  - { type: graph, name: G, edges: { property: feeds }, layout: { algorithm: dagre, direction: LR } }
  - { type: map, name: M, coordinates: where, defaultZoom: 4, mapTiles: world.pmtiles }
  - { type: compare, name: X, compare: { rows: selection, better: { mass: lower }, diffOnly: true } }
  - { type: record, name: R, record: { sections: [{ name: Specs, properties: [mass] }] }, edit: true }
  - { type: cards, name: P, image: photo, lightbox: true, caption: [model], masonry: true }
  - { type: list, name: L, markers: number, tree: { parent: up } }
  - { type: kanban, name: K, groupBy: { property: status }, columnWidth: 280 }
  - { type: graph, name: NoEdges }
`;
  const out = checkText(text, { properties: new Set(['started', 'ended', 'model', 'feeds', 'where', 'mass', 'photo', 'up', 'status']), datasetName: 'd' });
  assert.deepEqual(out.map((p) => `${p.level} ${p.message}`), ["error needs 'edges'"]);
  const typo = checkText('views:\n  - { type: calendar, name: C, start: startd }', { properties: new Set(['started']), datasetName: 'd' });
  assert.match(typo[0].message, /'startd' is not a property of d \(did you mean 'started'\?\)/);
});

function baseFiles(dir, out = []) {
  for (const f of readdirSync(dir)) {
    if (['.claude', '.trash', '.git', 'node_modules', '.obsidian'].includes(f)) continue;
    const p = join(dir, f);
    const s = statSync(p, { throwIfNoEntry: false });
    if (s && s.isDirectory()) baseFiles(p, out); else if (s && f.endsWith('.base')) out.push(p);
  }
  return out;
}

test('every Bases file in Zach\'s vault has 0 errors (Obsidian-only filters are warnings)', { skip: !existsSync(VAULT) && 'the vault is not on this machine' }, () => {
  const files = baseFiles(VAULT);
  assert.ok(files.length > 50);
  const out = execFileSync('node', [CLI, 'check', ...files, '--quiet'], { maxBuffer: 64 << 20 }).toString();
  assert.match(out, / 0 errors, /);
});

test('core pass: a chart may leave out its mark (Show Me picks it); kpi.compare.better may name a property', () => {
  const props = new Set(['mass', 'peak_torque', 'value', 't', 'better', 'label']);
  const clean = checkText(`views:
  - type: chart
    name: Defaults
    chart:
      encoding:
        x: { field: mass }
        y: { field: peak_torque }
  - type: kpi
    name: K
    groupBy: { property: label }
    kpi:
      value: { property: value }
      compare: { against: previous, better: better }
      spark: { x: t, y: value }
`, { properties: props, datasetName: 'd' });
  assert.deepEqual(clean.filter((p) => p.level === 'error'), []);
  const empty = checkText('views:\n  - type: chart\n    name: Nothing\n    chart: { title: x }\n');
  assert.ok(empty.some((p) => p.level === 'error' && /needs an encoding/.test(p.message)), JSON.stringify(empty));
  const typo = checkText('views:\n  - type: kpi\n    name: K\n    kpi:\n      value: { property: value }\n      compare: { against: previous, better: beter }\n', { properties: props, datasetName: 'd' });
  assert.ok(typo.some((p) => p.level === 'error' && /beter/.test(p.message) && /better/.test(p.message)), JSON.stringify(typo));
});

test('open modes: `open:` is a top-level and per-view key (short or long form); an unknown mode fails the check; link with no URL warns', async () => {
  const { mkdtempSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const props = new Set(['name', 'url', 'page']);
  const good = `open: { mode: side, splitAt: 1100 }
views:
  - type: table
    name: A
    open: expand
  - type: table
    name: B
    open: { mode: link, url: url }
  - type: cards
    name: C
    open: side
`;
  assert.deepEqual(checkText(good, { properties: props, datasetName: 'd', link: 'url' }), []);
  const bad = [...checkText('open: sideways\nviews:\n  - type: table\n    name: A\n    open: { mode: peek }\n'), ...checkText('views:\n  - type: table\n    name: A\n    open: { mode: side, splitAt: wide }\n')];
  const errors = bad.filter((p) => p.level === 'error').map((p) => `${p.line} ${p.path.join('.')} ${p.message}`);
  assert.ok(errors.some((e) => e.startsWith('1 open "sideways" is not one of expand, side, link (did you mean \'side\'?)')), errors.join('\n'));
  assert.ok(errors.some((e) => e.startsWith('5 views.0.open.mode "peek" is not one of expand, side, link')), errors.join('\n'));
  assert.ok(errors.some((e) => e.startsWith('4 views.0.open.splitAt must be number, not string')), errors.join('\n'));
  const typo = checkText('views:\n  - type: table\n    name: A\n    open: { mode: link, url: pag }\n', { properties: props, datasetName: 'd', link: 'url' });
  assert.ok(typo.some((p) => p.level === 'error' && /'pag' is not a property of d \(did you mean 'page'\?\)/.test(p.message)), JSON.stringify(typo));
  // no URL anywhere: link falls back to side, and says so
  const nolink = checkText('open: link\nviews:\n  - type: table\n    name: A\n  - type: table\n    name: B\n    open: { mode: link }\n', { properties: props, datasetName: 'd', link: null });
  assert.deepEqual(nolink.map((p) => `${p.level} ${p.path.join('.')}`), ['warning open', 'warning views.1.open'], JSON.stringify(nolink));
  assert.ok(nolink.every((p) => /falls back to side/.test(p.message)), JSON.stringify(nolink));
  // the CLI: an unknown mode is an error, exit 1
  const dir = mkdtempSync(join(tmpdir(), 'data-ui-open-'));
  writeFileSync(join(dir, 'v.base'), 'views:\n  - type: table\n    name: A\n    open: sideways\n');
  const { status, out } = run(join(dir, 'v.base'));
  assert.equal(status, 1, out);
  assert.match(out, /v\.base:4: error: views\[0\]\.open: "sideways" is not one of expand, side, link/);
});

test('graph layout engines: layout.engine is flow or mermaid; any other engine fails the check and names both', () => {
  const props = new Set(['title', 'depends_on']);
  const view = (engine) => `views:\n  - type: graph\n    name: A\n    edges: { property: depends_on }\n    layout: { engine: ${engine}, direction: BT }\n`;
  assert.deepEqual(checkText(view('flow'), { properties: props, datasetName: 'd' }), []);
  assert.deepEqual(checkText(view('mermaid'), { properties: props, datasetName: 'd' }), []);
  const errors = checkText(view('mermiad'), { properties: props, datasetName: 'd' }).filter((p) => p.level === 'error').map((p) => `${p.line} ${p.path.join('.')} ${p.message}`);
  assert.deepEqual(errors, ['5 views.0.layout.engine "mermiad" is not one of flow, mermaid (did you mean \'mermaid\'?)']);
});

test('the checker reports a clock.primary that names no video card on the layout, at its line (docs/peps/0008-one-clock-driver.md)', () => {
  const text = [
    'data: a.json',
    'clock:',
    '  time: t',
    '  primary: Tuned vid',
    'layout:',
    '  panels:',
    '    - { view: Tuned video }',
    'views:',
    '  - type: video',
    '    name: Tuned video',
    '    video: { src: src }',
  ].join('\n');
  const bad = checkText(text).filter((p) => p.path[0] === 'clock' && p.path[1] === 'primary');
  assert.equal(bad.length, 1, JSON.stringify(checkText(text)));
  assert.equal(bad[0].level, 'error');
  assert.equal(bad[0].line, 4);
  assert.equal(checkText(text.replace('primary: Tuned vid', 'primary: Tuned video')).filter((p) => p.path[0] === 'clock').length, 0);
});
