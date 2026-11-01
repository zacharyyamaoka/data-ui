// tools/serve-md.mjs on a real socket (docs/CONTRACT.md §46): it answers only its own Host, takes a write only from its own origin, refuses
// any path outside the folder, and a hand edit reaches a page. Each test works on a copy of the case's notes.
import { test, after, before } from 'node:test';
import assert from 'node:assert/strict';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { request } from 'node:http';
import { serve } from '../../tools/serve-md.mjs';

const CASE = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'gallery', 'md-pages', 'feedback');
const home = mkdtempSync(join(tmpdir(), 'serve-md-'));
const dir = join(home, 'notes');
let app, port;
const db = '/db/notes';

/** A raw request: fetch() will not send a forged Host or Origin. */
const raw = (method, path, { headers = {}, body } = {}) => new Promise((ok, no) => {
  const req = request({ host: '127.0.0.1', port, method, path, headers: { host: `127.0.0.1:${port}`, ...headers } }, (res) => {
    const parts = [];
    res.on('data', (c) => parts.push(c));
    res.on('end', () => ok({ status: res.statusCode, text: Buffer.concat(parts).toString('utf8') }));
  });
  req.on('error', no);
  if (body) req.write(body);
  req.end();
});
const post = (what, ask, headers = {}) => raw('POST', `${db}/${what}`, { headers: { origin: `http://127.0.0.1:${port}`, 'content-type': 'application/json', ...headers }, body: JSON.stringify(ask) });
const dataset = async () => JSON.parse((await raw('GET', `${db}/dataset`)).text);

before(async () => {
  cpSync(CASE, dir, { recursive: true });
  symlinkSync('/etc/hostname', join(dir, 'attachments', 'leak.png'));
  app = serve([dir]);
  await new Promise((ok) => app.server.listen(0, '127.0.0.1', ok));
  port = app.server.address().port;
});
after(() => { app.close(); rmSync(home, { recursive: true, force: true }); });

test('binds the loopback address only, and answers only its own Host', async () => {
  assert.equal(app.server.address().address, '127.0.0.1');
  assert.equal((await raw('GET', '/dbs', { headers: { host: 'evil.example' } })).status, 403);
  assert.equal((await raw('GET', '/dbs')).status, 200);
});

test('a write is taken only from its own origin', async () => {
  const id = 'fb-15f0ae2f';
  const file = join(dir, `${id}.md`);
  const was = readFileSync(file, 'utf8');
  const ask = { id, set: { observed: 'forged' } };
  assert.equal((await post('edit', ask, { origin: 'http://evil.example' })).status, 403);
  assert.equal((await post('edit', ask, { origin: `https://127.0.0.1:${port}` })).status, 403);
  assert.equal((await raw('POST', `${db}/edit`, { headers: { 'content-type': 'application/json' }, body: JSON.stringify(ask) })).status, 403, 'no Origin at all');
  assert.equal((await post('edit', ask, { 'sec-fetch-site': 'cross-site' })).status, 403);
  assert.equal((await post('edit', ask, { 'content-type': 'text/plain' })).status, 415, 'the content type a plain form can send');
  assert.equal(readFileSync(file, 'utf8'), was);
});

test('a path outside the folder is refused: dots, encoded dots, a symlink, a note id', async () => {
  const outside = join(home, 'secret.md');
  writeFileSync(outside, '# Secret\n');
  for (const p of ['file/../secret.md', 'file/..%2fsecret.md', 'file/%2e%2e/secret.md', 'file/attachments/../../secret.png', 'file/.trash/x.png', 'file/attachments/leak.png', 'find/..%2f..%2fsecret.md']) {
    const r = await raw('GET', `${db}/${p}`);
    assert.notEqual(r.status, 200, p);
    assert.ok(!r.text.includes('Secret'), p);
  }
  mkdirSync(join(dir, '.hidden'));
  writeFileSync(join(dir, '.hidden', 'secret.png'), 'Secret');
  assert.equal((await raw('GET', `${db}/file/.hidden/secret.png`)).status, 403, 'a dot folder inside it is not served');
  const r = await post('edit', { id: '../secret', set: { secret: 'x' } });
  assert.equal(JSON.parse(r.text).ok, false);
  assert.equal(readFileSync(outside, 'utf8'), '# Secret\n');
  const named = await post('add', { set: { name: '../../escape' } });
  assert.equal(JSON.parse(named.text).ok, true, 'the name is cleaned to a file name in the folder');
  assert.ok(!existsSync(join(home, 'escape.md')));
  assert.equal((await raw('GET', `${db}/file/fb-15f0ae2f.md`)).status, 403, 'a note is not media');
});

test('an edit writes that value alone; a value changed on disk since the page read it is refused', async () => {
  const id = 'fb-25f0fb32';
  const file = join(dir, `${id}.md`);
  const was = readFileSync(file, 'utf8');
  const res = JSON.parse((await post('edit', { id, set: { observed: 'Words from the page' }, was: { observed: 'No stable preview switcher icon on preview ( i thought this was added already )' } })).text);
  assert.equal(res.ok, true);
  assert.equal(readFileSync(file, 'utf8'), was.replace('No stable preview switcher icon on preview ( i thought this was added already )', 'Words from the page'));
  const stale = JSON.parse((await post('edit', { id, set: { observed: 'Mine' }, was: { observed: 'what the page last read' } })).text);
  assert.equal(stale.ok, false);
  assert.match(stale.reason, /changed on disk/);
  assert.ok(readFileSync(file, 'utf8').includes('Words from the page'));
});

test('a hand edit reaches the events stream within a second, and a heading typed into a note is a column', async () => {
  const stream = await new Promise((ok) => {
    const req = request({ host: '127.0.0.1', port, path: `${db}/events`, headers: { host: `127.0.0.1:${port}` } }, ok);
    req.end();
  });
  const seen = [];
  let tell = null;
  stream.on('data', (c) => { seen.push(String(c)); if (tell && seen.length > 1) tell(); });
  await new Promise((ok) => setTimeout(ok, 100));
  const file = join(dir, 'fb-d403bed4.md');
  const t0 = performance.now();
  writeFileSync(file, `${readFileSync(file, 'utf8')}\n# Notes by hand\n\ntyped in a text editor\n`);
  await new Promise((ok) => { tell = ok; if (seen.length > 1) ok(); });
  const took = performance.now() - t0;
  stream.destroy();
  assert.ok(took < 1000, `${took} ms`);
  const { data } = await dataset();
  assert.equal(data.properties.notes_by_hand.label, 'Notes by hand');
  assert.equal(data.rows.find((r) => r.id === 'fb-d403bed4').notes_by_hand, 'typed in a text editor');
});

test('place, dry: says what would change and writes nothing; apply moves every file and writes the .base', async () => {
  const { baseText, data } = await dataset();
  const page = baseText.replace('- { property: observed, place: section }', '- { property: observed }');
  const dry = JSON.parse((await post('place', { property: 'observed', to: 'top', dry: true, text: page })).text);
  assert.equal(dry.ok, true);
  assert.equal(dry.changes, data.rows.filter((r) => 'observed' in r).length, 'each note that holds the section');
  assert.equal(dry.total, data.rows.length);
  assert.ok(readFileSync(join(dir, 'fb-3d4bc1fb.md'), 'utf8').includes('# Observed'), 'dry: the file stays');
  const done = JSON.parse((await post('place', { property: 'observed', to: 'top', text: page })).text);
  assert.equal(done.ok, true);
  const text = readFileSync(join(dir, 'fb-3d4bc1fb.md'), 'utf8');
  assert.ok(!text.includes('# Observed'));
  assert.match(text.split('---')[1], /observed: /);
  assert.equal(readFileSync(join(dir, 'views.base'), 'utf8'), page);
  const back = JSON.parse((await post('place', { property: 'observed', to: 'section', text: baseText })).text);
  assert.equal(back.ok, true);
  assert.ok(readFileSync(join(dir, 'fb-3d4bc1fb.md'), 'utf8').includes('# Observed'));
});

test('a type that does not fit: the file stays, the layout moves, and the page is told why', async () => {
  const { baseText } = await dataset();
  const page = baseText.replace('- { property: status }', '- { property: status, place: section }');
  const before = readFileSync(join(dir, 'fb-3d4bc1fb.md'), 'utf8');
  const res = JSON.parse((await post('place', { property: 'status', to: 'section', text: page })).text);
  assert.equal(res.ok, true);
  assert.equal(res.changes, 0);
  assert.equal(res.layoutOnly, true);
  assert.match(res.note, /stays in the frontmatter/);
  assert.equal(readFileSync(join(dir, 'fb-3d4bc1fb.md'), 'utf8'), before);
  assert.equal(readFileSync(join(dir, 'views.base'), 'utf8'), page);
  JSON.parse((await post('place', { property: 'status', to: 'top', text: baseText })).text);
});

test('a date is not words either', async () => {
  const { baseText } = await dataset();
  const page = baseText.replace('- { property: filed }', '- { property: filed, place: section }');
  const res = JSON.parse((await post('place', { property: 'filed', to: 'section', dry: true, text: page })).text);
  assert.equal(res.changes, 0);
  assert.match(res.note, /filed|Filed/);
  assert.match(res.note, /is a date/);
});

test('a pasted file lands in attachments, named by its bytes', async () => {
  const bytes = Buffer.from([0x89, 0x50, 0x4e, 0x47]);
  const r = JSON.parse((await raw('POST', `${db}/file?name=${encodeURIComponent('my shot.png')}`, { headers: { origin: `http://127.0.0.1:${port}`, 'content-type': 'application/octet-stream' }, body: bytes })).text);
  assert.equal(r.ok, true);
  assert.match(r.attachment.ref, /^attachments\/my-shot-[0-9a-f]{8}\.png$/);
  assert.ok(readFileSync(join(dir, r.attachment.ref)).equals(bytes));
  const bad = JSON.parse((await raw('POST', `${db}/file?name=run.sh`, { headers: { origin: `http://127.0.0.1:${port}`, 'content-type': 'application/octet-stream' }, body: bytes })).text);
  assert.equal(bad.ok, false);
});

test('a vault: named for a folder inside its root; a folder outside it, or none, is told nothing', async () => {
  const inside = serve([dir], { vault: { name: 'My Vault', root: home } });
  const outside = serve([dir], { vault: { name: 'Other', root: join(home, 'nowhere') } });
  const elsewhere = serve([dir], { vault: { name: 'Other', root: CASE } });
  try {
    assert.deepEqual([...inside.dbs.values()][0].vault, { name: 'My Vault', path: 'notes' });
    assert.equal([...outside.dbs.values()][0].vault, null);
    assert.equal([...elsewhere.dbs.values()][0].vault, null);
    assert.equal((await dataset()).vault, null, 'no --vault: the page is told none');
  } finally { inside.close(); outside.close(); elsewhere.close(); }
});

test('an added note is a file, with what was typed in the right places', async () => {
  const r = JSON.parse((await post('add', { set: { name: 'New from the page', observed: 'seen', polarity: 'negative' } })).text);
  assert.equal(r.ok, true);
  assert.equal(readFileSync(join(dir, `${r.id}.md`), 'utf8'), '---\npolarity: negative\n---\n\n# Observed\n\nseen\n');
});
