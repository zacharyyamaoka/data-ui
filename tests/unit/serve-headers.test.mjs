// Open in Rerun's hosted viewer (docs/RERUN.md): app.rerun.io fetches the .rrd from our origin, so `npm run serve`
// (tools/serve.mjs) and the deployed site (dist/site/_headers, Cloudflare static assets) must let it read the file.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const RERUN = 'https://app.rerun.io';

/** serve.mjs on a free port over a fixture site with one .rrd; resolves {base, stop}. */
async function serve() {
  const site = mkdtempSync(join(tmpdir(), 'serve-headers-'));
  writeFileSync(join(site, 'index.html'), '<!doctype html><title>x</title>');
  mkdirSync(join(site, 'gallery', 'case', 'rerun'), { recursive: true });
  writeFileSync(join(site, 'gallery', 'case', 'rerun', 'case.rrd'), Buffer.from('RRF2fixture'));
  const child = spawn(process.execPath, [join(ROOT, 'tools', 'serve.mjs')], { env: { ...process.env, PORT: '0', DATA_UI_SITE: site }, stdio: ['ignore', 'pipe', 'pipe'] });
  const base = await new Promise((ok, fail) => {
    let out = '';
    child.stdout.on('data', (d) => { out += d; const m = /http:\/\/127\.0\.0\.1:(\d+)\//.exec(out); if (m) ok(m[0]); });
    child.on('exit', (code) => fail(new Error(`serve.mjs exited ${code}: ${out}`)));
  });
  return { base, stop: () => { child.kill(); rmSync(site, { recursive: true, force: true }); } };
}

test('serve: a .rrd answers app.rerun.io with Access-Control-Allow-Origin, GET and HEAD; other files do not', async () => {
  const { base, stop } = await serve();
  try {
    for (const method of ['GET', 'HEAD']) {
      const r = await fetch(`${base}gallery/case/rerun/case.rrd`, { method, headers: { origin: RERUN } });
      assert.equal(r.status, 200, method);
      assert.equal(r.headers.get('access-control-allow-origin'), RERUN, method);
      if (method === 'GET') assert.equal(await r.text(), 'RRF2fixture');
    }
    const page = await fetch(`${base}index.html`, { headers: { origin: RERUN } });
    assert.equal(page.status, 200);
    assert.equal(page.headers.get('access-control-allow-origin'), null);
  } finally { stop(); }
});

test('serve: the preflight (OPTIONS) for a .rrd is 204 with the origin, the methods, the asked headers and Private Network Access', async () => {
  const { base, stop } = await serve();
  try {
    const r = await fetch(`${base}gallery/case/rerun/case.rrd`, { method: 'OPTIONS', headers: {
      origin: RERUN, 'access-control-request-method': 'GET', 'access-control-request-headers': 'range',
      'access-control-request-private-network': 'true' } });
    assert.equal(r.status, 204);
    assert.equal(r.headers.get('access-control-allow-origin'), RERUN);
    assert.match(r.headers.get('access-control-allow-methods') || '', /\bGET\b/);
    assert.match(r.headers.get('access-control-allow-methods') || '', /\bHEAD\b/);
    assert.equal(r.headers.get('access-control-allow-headers'), 'range');
    assert.equal(r.headers.get('access-control-allow-private-network'), 'true');
    assert.equal(await r.text(), '');
    // a preflight for anything else gets no CORS grant
    const other = await fetch(`${base}index.html`, { method: 'OPTIONS', headers: { origin: RERUN, 'access-control-request-method': 'GET' } });
    assert.equal(other.headers.get('access-control-allow-origin'), null);
  } finally { stop(); }
});

test('deployed site: _headers grants app.rerun.io every .rrd, and the build writes it into dist/site/', async () => {
  const { SITE_HEADERS } = await import('../../site/build-site.mjs');
  // Cloudflare's _headers form: a path line, then indented "Name: value" lines (developers.cloudflare.com/workers/static-assets/headers/)
  const rules = {};
  let path = null;
  for (const line of SITE_HEADERS.split('\n')) {
    if (!line.trim() || line.startsWith('#')) continue;
    if (!/^\s/.test(line)) { path = line.trim(); rules[path] = {}; continue; }
    const [name, ...value] = line.trim().split(':');
    rules[path][name.trim().toLowerCase()] = value.join(':').trim();
  }
  assert.deepEqual(rules, { '/*.rrd': { 'access-control-allow-origin': RERUN } });
  const built = join(ROOT, 'dist', 'site', '_headers');
  assert.ok(existsSync(join(ROOT, 'dist', 'site', 'index.html')), 'dist/site is not built: run node build.mjs first');
  assert.equal(readFileSync(built, 'utf8'), SITE_HEADERS);
});
