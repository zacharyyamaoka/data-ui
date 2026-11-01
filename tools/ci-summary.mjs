// A run's DATA_UI_TEST_SUMMARY as a Markdown table, for the job's summary page: what failed, what was skipped and why,
// and how long it all took. Skips are listed every time, so they stay visible.
//   node tools/ci-summary.mjs test-summary.json
import { existsSync, readFileSync } from 'node:fs';

const file = process.argv[2];
if (!file || !existsSync(file)) { console.log(`**No test summary at ${file}: the suite did not finish.**`); process.exit(0); }
const run = JSON.parse(readFileSync(file, 'utf8'));
const failed = run.results.filter((r) => r.result.startsWith('FAIL'));
const skipped = run.results.filter((r) => r.result.startsWith('SKIP'));
console.log(`### ${failed.length ? `RED: ${failed.length} failed` : 'Green'} · ${run.results.length - skipped.length} ran, ${skipped.length} skipped · ${Math.round(run.total_seconds / 60)} min · Node ${run.node}\n`);
for (const r of failed) console.log(`- **${r.name}**: ${r.result}`);
if (skipped.length) { console.log('\nSkipped:\n'); for (const r of skipped) console.log(`- ${r.name}: ${r.result.replace(/^SKIPPED: /, '')}`); }
const slowest = run.results.filter((r) => r.seconds !== null).sort((a, b) => b.seconds - a.seconds).slice(0, 8);
console.log('\n| Slowest | s |\n|---|---|');
for (const r of slowest) console.log(`| ${r.name} | ${r.seconds} |`);
