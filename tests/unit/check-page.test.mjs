// `data-ui check page.html` (judge round 3 #6, the coordinator's call): several URL-bearing <data-dashboard>s on one
// page need a unique URL scope each, so a repeated or slug-colliding src without an id, or a repeated id, is an error
// at the tag's line (packages/dashboard/src/model.js clockScopes, the rule the page itself applies at runtime).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const FIX = new URL('../browser/fixtures/', import.meta.url);

test('checkPage: a repeated src without ids is an error on each tag, at its line; unique ids pass (r3 #6)', async () => {
  const { checkPage } = await import('../../packages/dashboard/src/model.js');
  assert.equal(typeof checkPage, 'function', 'checkPage is exported');
  const page = ['<main>', '<data-dashboard src="views.base"></data-dashboard>', '<p>x</p>',
    '<data-dashboard\n  src="views.base" aria-label="b"></data-dashboard>', '<data-dashboard src="other.base" no-url></data-dashboard>', '</main>'].join('\n');
  const got = checkPage(page);
  assert.deepEqual(got.map((p) => [p.level, p.line]), [['error', 2], ['error', 4]]);
  assert.match(got[0].message, /views\.base.*give each an id/);
  assert.deepEqual(checkPage('<data-dashboard id="left" src="views.base"></data-dashboard>\n<data-dashboard id="right" src="views.base"></data-dashboard>'), []);
  assert.deepEqual(checkPage('<data-dashboard src="views.base"></data-dashboard>'), [], 'one dashboard: plain #t=, nothing to check');
  const dup = checkPage("<data-dashboard id='dup' src='a.base'></data-dashboard>\n<data-dashboard id=dup src=b.base></data-dashboard>");
  assert.deepEqual(dup.map((p) => p.line), [1, 2]);
  assert.match(dup[0].message, /id 'dup' is used by 2 dashboards/);
});

test('data-ui check FILE.html: the fixtures — same src and same id fail with file:line, distinct ids pass (r3 #6)', async () => {
  const { main } = await import('../../packages/analysis/src/check.js');
  const run = (name) => { const out = []; const status = main([new URL(name, FIX).pathname], { log: (l) => out.push(l) }); return { status, out }; };
  const same = run('two-dashboards-same-src.html');
  assert.equal(same.status, 1, same.out.join('\n'));
  const lines = readFileSync(new URL('two-dashboards-same-src.html', FIX), 'utf8').split('\n');
  const tagLines = lines.map((l, i) => (l.includes('<data-dashboard') ? i + 1 : 0)).filter(Boolean);
  for (const n of tagLines) assert.ok(same.out.some((l) => l.includes(`two-dashboards-same-src.html:${n}: error:`)), `line ${n}: ${same.out.join('\n')}`);
  assert.equal(run('two-dashboards-same-id.html').status, 1);
  const ok = run('two-dashboards.html');
  assert.equal(ok.status, 0, ok.out.join('\n'));
});
