// The perf-core speedups change no output byte: the kit's output over every gallery example digests the same as it
// did before the work (perf-oracle.golden.json, written from main 7b9d09e by perf-oracle-corpus.mjs).
// WHY: the perf review's items (cached Intl formatters and collators, linear summaries, split facet counting) are
// pure speedups; Zach's truthful-rendering rule means a faster cell that writes one different character is a bug.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { allDigests } from './perf-oracle-corpus.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const golden = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'perf-oracle.golden.json'), 'utf8'));
const now = await allDigests(ROOT);

test('format: every gallery cell writes the same HTML and text, and fmtNum the same digits, as before the cached formatters', () => {
  assert.equal(now.format, golden.format);
});

test('row model: every view and every property sorted both ways (flat and grouped) orders rows and groups as before', () => {
  assert.equal(now.model, golden.model);
});

test('rail: the disjunctive counts of every faceted view (nothing, each facet alone, all at once) and the rows the rail keeps are as before', () => {
  assert.equal(now.rail, golden.rail);
});

test('summaries: every summary of every gallery column, every pivot cell, and sums built to expose a reordering are as before', () => {
  assert.equal(now.summary, golden.summary);
});

// judge r1 finding 8 (2026-10-27): the rail's date presets use local calendar days, so the same code digested
// differently in UTC+14; the corpus pins its own timezone, and this proves it from a process in another one
test('the oracle does not depend on the machine timezone: digests under TZ=Pacific/Kiritimati (UTC+14) equal the golden', async () => {
  const { execFileSync } = await import('node:child_process');
  const corpus = join(dirname(fileURLToPath(import.meta.url)), 'perf-oracle-corpus.mjs');
  const out = execFileSync(process.execPath, [corpus, ROOT], { env: { ...process.env, TZ: 'Pacific/Kiritimati' }, encoding: 'utf8', maxBuffer: 1 << 24 });
  const there = JSON.parse(out);
  for (const k of ['format', 'model', 'rail', 'summary']) assert.equal(there[k], golden[k], k);
});

// judge r2 #11: the golden is reproducible: the corpus digests the same whatever the machine's clock and timezone
// (relative dates and local times are drawn against a fixed instant in UTC inside the corpus)
test('the digests do not depend on the clock or the timezone they run at', async () => {
  const realNow = Date.now, tz = process.env.TZ;
  try {
    Date.now = () => realNow() + 3600e3 * 37;
    process.env.TZ = 'Pacific/Kiritimati';
    const shifted = await allDigests(ROOT);
    assert.deepEqual(shifted, now);
  } finally { Date.now = realNow; if (tz === undefined) delete process.env.TZ; else process.env.TZ = tz; }
});
