// tools/public-export.mjs on a repository made here: what stays out, what is replaced, and that a planted name stops a
// mirror from passing, so a green scan means something.
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { commitMirror, exportTree, greyPng, IDENTITY, imageSize, PLACEHOLDER, redact } from './public-export.mjs';

// every folder a test makes goes when the file is done
const made = [];
const tempDir = (prefix) => { const dir = mkdtempSync(join(tmpdir(), prefix)); made.push(dir); return dir; };
after(() => { for (const dir of made) rmSync(dir, { recursive: true, force: true }); });


const TOOL = join(dirname(fileURLToPath(import.meta.url)), 'public-export.mjs');
// WHY assembled: this file goes through the export too, so it may hold no marker, home path or address of its own
const OWNER_HOME = '/home/owner';
const MARK = ['public-export', 'strip'].join(': ');
const write = (repo, path, text) => { mkdirSync(dirname(join(repo, path)), { recursive: true }); writeFileSync(join(repo, path), text); };

function fixture(files) {
  const repo = tempDir('public-export-');
  const git = (...args) => { const r = spawnSync('git', ['-C', repo, ...args], { encoding: 'utf8' }); assert.equal(r.status, 0, r.stderr); return r.stdout.trim(); };
  git('init', '-q', '-b', 'main');
  git('config', 'user.name', 'Owner');
  git('config', 'user.email', 'owner@example.com');
  for (const [path, text] of Object.entries(files)) write(repo, path, text);
  git('add', '.');
  git('commit', '-q', '-m', 'all');
  return repo;
}

const FILES = {
  'README.md': `code in ${OWNER_HOME}/data-ui, and ${OWNER_HOME} itself; ${OWNER_HOME}ship stays\n`,
  'reports/review.html': '<p>internal</p>\n',
  '.claude/feedback.md': 'a rating\n',
  'gallery/examples/robotparts-photos/media/p-1.webp': Buffer.concat([greyPng(240, 160), Buffer.from('a vendor photo')]),
  'gallery/examples/robotparts-photos/media/logo.svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 8"><path d="M0 0" /><title>a vendor logo</title></svg>',
  'tools/gate.mjs': `const A = 1;\n// ${MARK}-begin => const SECRET = [];\nconst SECRET = [/a private name/];\n// ${MARK}-end\nconst B = 2;\n`,
  'tests/unit/no-home-paths.baseline.json': `{"x": {"${OWNER_HOME}/y": 1}, "z": {"/home/static/a.js": 1, "${OWNER_HOME}/b": 2}}\n`,
};

test("an image's size comes from its header, for every form the placeholders replace", () => {
  assert.deepEqual(imageSize(greyPng(7, 3)), [7, 3]);
  const lossy = Buffer.alloc(30); lossy.write('RIFF', 0, 'latin1'); lossy.write('WEBPVP8 ', 8, 'latin1'); lossy.writeUInt16LE(960, 26); lossy.writeUInt16LE(600, 28);
  assert.deepEqual(imageSize(lossy), [960, 600]);
  const lossless = Buffer.alloc(30); lossless.write('RIFF', 0, 'latin1'); lossless.write('WEBPVP8L', 8, 'latin1'); lossless.writeUInt32LE((240 - 1) | ((160 - 1) << 14), 21);
  assert.deepEqual(imageSize(lossless), [240, 160]);
  const extended = Buffer.alloc(30); extended.write('RIFF', 0, 'latin1'); extended.write('WEBPVP8X', 8, 'latin1'); extended.writeUIntLE(639, 24, 3); extended.writeUIntLE(399, 27, 3);
  assert.deepEqual(imageSize(extended), [640, 400]);
  const jpeg = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0, 4, 0, 0, 0xff, 0xc0, 0, 11, 8, 0, 100, 0, 200, 1, 1, 0x11, 0]);
  assert.deepEqual(imageSize(jpeg), [200, 100]);
  assert.throws(() => imageSize(Buffer.from('not an image at all, not even close')), /not a PNG/);
});

test('home paths become ~, and a longer name that starts the same stays', () => {
  assert.equal(redact(`${OWNER_HOME}/x ${OWNER_HOME} ${OWNER_HOME}ship/y`, OWNER_HOME), `~/x ~ ${OWNER_HOME}ship/y`);
});

test('the tree: private paths out, vendor images replaced under their own names, markers stripped, the baseline empty', () => {
  const repo = fixture(FILES);
  const out = join(tempDir('public-export-out-'), 'tree');
  const did = exportTree({ repo, ref: 'main', out, owner: OWNER_HOME });
  assert.equal(existsSync(join(out, 'reports')), false);
  assert.equal(existsSync(join(out, '.claude')), false);
  assert.equal(readFileSync(join(out, 'README.md'), 'utf8'), `code in ~/data-ui, and ~ itself; ${OWNER_HOME}ship stays\n`);
  const photo = readFileSync(join(out, 'gallery/examples/robotparts-photos/media/p-1.webp'));
  assert.deepEqual(imageSize(photo), [240, 160], 'the same size, so a page lays out the same');
  assert.ok(!photo.includes('a vendor photo'));
  const logo = readFileSync(join(out, 'gallery/examples/robotparts-photos/media/logo.svg'), 'utf8');
  assert.ok(logo.includes('viewBox="0 0 32 8"'));
  assert.ok(!logo.includes('vendor') && !logo.includes('<path'));
  const gate = readFileSync(join(out, 'tools/gate.mjs'), 'utf8');
  assert.match(gate, /const SECRET = \[\];/);
  assert.ok(!gate.includes('a private name'));
  assert.match(gate, /const A = 1;[\s\S]*const B = 2;/, 'only the block goes');
  assert.deepEqual(JSON.parse(readFileSync(join(out, 'tests/unit/no-home-paths.baseline.json'), 'utf8')), { z: { '/home/static/a.js': 1 } }, "only the owner's paths go");
  assert.deepEqual(did.stripped, ['tools/gate.mjs']);
});

test("the mirror's commit carries the noreply identity and no private history", () => {
  const repo = fixture(FILES);
  const base = tempDir('public-export-mirror-');
  const tree = join(base, 'tree');
  exportTree({ repo, ref: 'main', out: tree, owner: OWNER_HOME });
  commitMirror({ tree, mirror: join(base, 'mirror'), message: 'one' });
  const log = (fmt) => spawnSync('git', ['-C', join(base, 'mirror'), 'log', `--format=${fmt}`], { encoding: 'utf8' }).stdout.trim();
  assert.equal(log('%ae %ce'), `${IDENTITY.email} ${IDENTITY.email}`);
  assert.equal(log('%h').split('\n').length, 1);
});

test("every folder of other people's pictures is on the placeholder list, so a new one cannot slip past", () => {
  // WHY read the real tree: 300 vendor photos under robotparts-actuators/ passed the export because the list named its
  // sibling folders and not it (2026-10-31), and a pattern scan cannot read a picture
  const root = join(dirname(TOOL), '..');
  const pictures = [];
  const walk = (dir) => {
    for (const entry of readdirSync(join(root, dir), { withFileTypes: true })) {
      const path = `${dir}/${entry.name}`;
      if (entry.isDirectory()) walk(path);
      else if (/\/(photos|logos|stills)\/[^/]+$|\/robotparts-[^/]+\/media\/[^/]+$/.test(path)) pictures.push(path);
    }
  };
  walk('gallery/examples');
  walk('bench/scenarios');
  assert.ok(pictures.length > 500, 'the walk found the photos');
  assert.deepEqual(pictures.filter((path) => !PLACEHOLDER.some((folder) => path.startsWith(folder))), []);
});

test('a name on the deny list stops the mirror: exit 1 and it says do not push; without it, exit 0', () => {
  const repo = fixture({ ...FILES, 'README.md': `code in ${OWNER_HOME}/data-ui\n`, 'notes.md': 'a customer called Acme Hospital\n' });
  const base = tempDir('public-export-gate-');
  const list = join(base, 'deny.txt');
  writeFileSync(list, '(?i)acme hospital\n');
  const run = (extra) => spawnSync('node', [TOOL, '--repo', repo, '--ref', 'main', ...extra], { encoding: 'utf8', env: { ...process.env, DATA_UI_DENY: list, DATA_UI_OWNER_HOME: OWNER_HOME } });
  const red = run(['--mirror', join(base, 'red')]);
  assert.equal(red.status, 1, red.stdout + red.stderr);
  assert.match(red.stderr, /do not push/);
  writeFileSync(list, '(?i)no such name\n');
  const green = run(['--mirror', join(base, 'green')]);
  assert.equal(green.status, 0, green.stdout + green.stderr);
});
