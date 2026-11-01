// nextDateChange() names the exact instant the rail's date presets' bounds next move, in any timezone and across DST
// (judge r2, 2026-10-27: Last 7 days in Vancouver on 2026-11-01 moves at 23:00, not midnight). The property, checked
// every 3 hours of a year in five zones: the bounds are the same 1 ms before that instant and different at it.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const FACETS = pathToFileURL(join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'packages', 'core', 'src', 'facets.js')).href;
const PROBE = `
const F = await import(${JSON.stringify(FACETS)});
const specs = [{ as: 'date', key: 'listed' }, { as: 'date', key: 'seen', presets: ['1d', '2w', '3m', 'year'], older: ['1y'] }];
const bad = [];
let checked = 0;
for (let t = Date.UTC(2026, 0, 1); t < Date.UTC(2027, 0, 1); t += 3 * 3600e3) {
  const now = new Date(t), next = F.nextDateChange(specs, now);
  const b = (x) => JSON.stringify(F.dateBounds(specs, new Date(x)));
  if (next === null || next <= t) { bad.push([now.toISOString(), 'no next']); continue; }
  if (b(next - 1) !== b(t)) bad.push([now.toISOString(), 'moved before', new Date(next).toISOString()]);
  if (b(next) === b(t)) bad.push([now.toISOString(), 'not moved at', new Date(next).toISOString()]);
  checked++;
}
console.log(JSON.stringify({ checked, bad: bad.slice(0, 5), n: bad.length }));
`;

for (const tz of ['America/Vancouver', 'Europe/London', 'Pacific/Auckland', 'Pacific/Kiritimati', 'UTC']) {
  test(`nextDateChange is exact every 3 h of 2026 in ${tz} (the bounds move at it, not before)`, () => {
    const out = JSON.parse(execFileSync(process.execPath, ['--input-type=module', '-e', PROBE], { env: { ...process.env, TZ: tz }, encoding: 'utf8' }));
    assert.equal(out.n, 0, JSON.stringify(out.bad));
    assert.ok(out.checked > 2900, String(out.checked));
  });
}
