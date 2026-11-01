// Time grouping: `groupBy: {property, by: day | week | month | quarter | year}` in the row model, the pivot, the labels
// and both checkers (docs/CONTRACT.md amendment 2026-10-26 (time groups and peek trail)). The oracle is computed here,
// from the data file's text, with its own day count (days_from_civil), never with grammar.js's bucketing.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

// WHY a far zone: a date-only value or a written datetime must keep its calendar date in any zone (+14 h here)
process.env.TZ = 'Pacific/Kiritimati';

const { TIME_GRAINS, timeBucket, bucketLabel, nextBucket } = await import('../../packages/core/src/grammar.js');
const { rowModel } = await import('../../packages/core/src/rowmodel.js');
const { groupLabel } = await import('../../packages/core/src/format.js');
const { checkText } = await import('../../packages/core/src/check.js');

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
// Vibe Tracks' runs (ml-experiments: 120 runs of its synthetic grasp bench, each with its start time)
const runs = JSON.parse(readFileSync(join(ROOT, 'gallery', 'examples', 'ml-experiments', 'runs.json'), 'utf8'));

// ---- the oracle: Howard Hinnant's days_from_civil, and 1970-01-05 (day 4) was a Monday
function dayNumber(y, m, d) {
  y -= m <= 2 ? 1 : 0;
  const era = Math.floor(y / 400);
  const yoe = y - era * 400;
  const doy = Math.floor((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5) + d - 1;
  return era * 146097 + yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy - 719468;
}
const ymd = (text) => text.slice(0, 10).split('-').map(Number);
const weekIndex = (text) => Math.floor((dayNumber(...ymd(text)) - 4) / 7);
const tally = (keyOf) => { const m = new Map(); for (const r of runs.rows) { const k = keyOf(r.started); m.set(k, (m.get(k) || 0) + 1); } return m; };
const sorted = (m) => [...m.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1));

test('weeks: ISO weeks from Monday; counts per week equal the oracle over the 120 runs, in time order', () => {
  const view = { type: 'table', name: 'By week', groupBy: { property: 'started', by: 'week' } };
  const m = rowModel(runs, null, view);
  const want = sorted(tally(weekIndex));
  assert.equal(m.groups.length, want.length);
  for (const g of m.groups) assert.equal((dayNumber(...ymd(g.key)) - 4) % 7, 0, `${g.key} is a Monday`);
  assert.deepEqual(m.groups.map((g) => [weekIndex(g.key), g.rows.length]), want);
  assert.equal(m.groups.reduce((n, g) => n + g.rows.length, 0), 120);
  assert.ok(m.groups.every((g) => g.by === 'week' && g.property === 'started'));
  // every run sits in the week its own date falls in
  for (const g of m.groups) for (const r of g.rows) assert.equal(weekIndex(r.started), weekIndex(g.key), r.id);
});

test('months, quarters, years: counts equal the oracle (the written date\'s year and month)', () => {
  for (const [by, keyOf] of [['month', (t) => t.slice(0, 7)], ['quarter', (t) => `${t.slice(0, 4)}-Q${Math.ceil(Number(t.slice(5, 7)) / 3)}`], ['year', (t) => t.slice(0, 4)], ['day', (t) => t.slice(0, 10)]]) {
    const m = rowModel(runs, null, { type: 'table', name: by, groupBy: { property: 'started', by } });
    assert.deepEqual(m.groups.map((g) => [g.key, g.rows.length]), sorted(tally(keyOf)), by);
  }
});

test('labels: "Week of 19 Oct 2026", "Oct 2026", "Q4 2026"; groupLabel reads the grain from the model\'s columns', () => {
  assert.deepEqual(TIME_GRAINS, ['day', 'week', 'month', 'quarter', 'year']);
  assert.equal(bucketLabel('2026-10-19', 'week'), 'Week of 19 Oct 2026');
  assert.equal(bucketLabel('2026-10', 'month'), 'Oct 2026');
  assert.equal(bucketLabel('2026-Q4', 'quarter'), 'Q4 2026');
  assert.equal(bucketLabel('2026', 'year'), '2026');
  assert.equal(bucketLabel('2026-10-20', 'day'), 'Tue 20 Oct 2026');
  const m = rowModel(runs, null, { type: 'table', name: 'w', groupBy: { property: 'started', by: 'week' } });
  // a view that labels a group from one of its rows (the table, the list) gets the same words as from the key
  assert.equal(groupLabel(m.columns, 'started', m.groups[0].rows[0].started), 'Week of 21 Sep 2026');
  assert.equal(groupLabel(m.columns, 'started', m.groups[0].key), 'Week of 21 Sep 2026');
  assert.equal(groupLabel(m.columns, 'started', null), 'No started');
  // the dataset's own columns are not marked: a later model without `by` labels raw values again
  assert.equal(runs.properties.started.by, undefined);
  assert.equal(groupLabel(rowModel(runs, null, { type: 'table', name: 'p', groupBy: { property: 'started' } }).columns, 'started', '2026-10-01'), '2026-10-01');
});

test('bucket rules: the written date, never shifted by a time zone; ISO week years; bad or missing dates have no bucket', () => {
  assert.equal(timeBucket('2026-10-01', 'month'), '2026-10');
  assert.equal(timeBucket('2026-09-30T23:30:00-07:00', 'day'), '2026-09-30'); // Oct 1 in UTC, and in Kiritimati
  assert.equal(timeBucket('2026-09-30T23:30:00Z', 'month'), '2026-09');
  assert.equal(timeBucket({ value: '2026-10-25', basis: 'measured' }, 'week'), '2026-10-19'); // a Sunday ends its week
  assert.equal(timeBucket('2026-10-26', 'week'), '2026-10-26'); // a Monday starts one
  assert.equal(timeBucket('2026-01-01', 'week'), '2025-12-29'); // Thursday 1 Jan 2026 is in ISO week 1 from 29 Dec
  assert.equal(timeBucket('2026-12-31', 'quarter'), '2026-Q4');
  // dates are ISO text (docs/CONTRACT.md §3): a number, even an epoch, names no day
  for (const v of [null, '', 'soon', '2026-13-01', '2026-02-30', 42.5, Date.UTC(2026, 9, 1), [], true, { value: null, why: 'not run' }]) assert.equal(timeBucket(v, 'week'), null, JSON.stringify(v));
  // a bucket's key is its own bucket, so a key and a row label the same way
  for (const by of TIME_GRAINS) for (const v of ['2026-10-20', '2026-02-28T10:00:00+09:00']) { const k = timeBucket(v, by); assert.equal(timeBucket(k, by), k, `${by} ${v}`); }
  assert.equal(nextBucket('2026-12-28', 'week'), '2027-01-04');
  assert.equal(nextBucket('2026-12', 'month'), '2027-01');
  assert.equal(nextBucket('2026-Q4', 'quarter'), '2027-Q1');
  assert.equal(nextBucket('2026', 'year'), '2027');
  assert.equal(nextBucket('2026-02-28', 'day'), '2026-03-01');
});

test('order: newest week first with direction DESC; inside a week the view\'s own sort on the same date still holds', () => {
  const view = { type: 'table', name: 'w', groupBy: { property: 'started', by: 'week', direction: 'DESC' }, sort: [{ property: 'started', direction: 'ASC' }] };
  const m = rowModel(runs, null, view);
  const keys = m.groups.map((g) => g.key);
  assert.deepEqual(keys, [...keys].sort().reverse());
  for (const g of m.groups) {
    const t = g.rows.map((r) => r.started);
    assert.deepEqual(t, [...t].sort(), `${g.key} oldest first inside the week`);
  }
  const desc = rowModel(runs, null, { ...view, groupBy: { property: 'started', by: 'week' }, sort: [{ property: 'started', direction: 'DESC' }] });
  assert.deepEqual(desc.groups.map((g) => g.key), [...keys].reverse());
  for (const g of desc.groups) { const t = g.rows.map((r) => r.started); assert.deepEqual(t, [...t].sort().reverse()); }
  // a sort on another property orders the rows inside each week
  const by = rowModel(runs, null, { ...view, sort: [{ property: 'success_rate', direction: 'DESC' }] });
  for (const g of by.groups) { const s = g.rows.map((r) => r.success_rate); assert.deepEqual(s, [...s].sort((a, b) => b - a)); }
});

test('empty buckets: left out by default; `gaps: true` keeps every bucket from the first to the last, empty ones with no rows', () => {
  const filters = 'started < "2026-09-28" || started >= "2026-10-12"';
  const plain = rowModel(runs, null, { type: 'table', name: 'g', filters, groupBy: { property: 'started', by: 'week' } });
  assert.deepEqual(plain.groups.map((g) => g.key), ['2026-09-21', '2026-10-12']);
  const gaps = rowModel(runs, null, { type: 'table', name: 'g', filters, groupBy: { property: 'started', by: 'week', gaps: true } });
  assert.deepEqual(gaps.groups.map((g) => [g.key, g.rows.length]), [['2026-09-21', plain.groups[0].rows.length], ['2026-09-28', 0], ['2026-10-05', 0], ['2026-10-12', plain.groups[1].rows.length]]);
  assert.deepEqual(gaps.rows.map((r) => r.id), plain.rows.map((r) => r.id));
  const back = rowModel(runs, null, { type: 'table', name: 'g', filters, groupBy: { property: 'started', by: 'week', gaps: true, direction: 'DESC' } });
  assert.deepEqual(back.groups.map((g) => g.key), ['2026-10-12', '2026-10-05', '2026-09-28', '2026-09-21']);
  // gaps per model inside a month level, and "No started" stays last, never a gap
  const rows = [...runs.rows.slice(0, 3), { id: 'x', run: 'x', started: null, model: 'M1.base' }];
  const none = rowModel({ ...runs, rows }, null, { type: 'table', name: 'n', groupBy: { property: 'started', by: 'month', gaps: true } });
  assert.deepEqual(none.groups.map((g) => [g.key, g.rows.length]), [['2026-09', 3], [null, 1]]);
});

test('subGroupBy by week under groupBy model; the pivot groups its rows by week too', () => {
  const m = rowModel(runs, null, { type: 'table', name: 's', groupBy: { property: 'model', direction: 'ASC' }, subGroupBy: { property: 'started', by: 'week' } });
  for (const g of m.groups) {
    const want = sorted((() => { const t = new Map(); for (const r of runs.rows.filter((x) => x.model === g.key)) { const k = weekIndex(r.started); t.set(k, (t.get(k) || 0) + 1); } return t; })());
    assert.deepEqual(g.groups.map((s) => [weekIndex(s.key), s.rows.length]), want, g.key);
    assert.ok(g.groups.every((s) => s.by === 'week'));
  }
  const p = rowModel(runs, null, { type: 'pivot', name: 'p', order: ['model'], splitBy: ['env'], value: { property: 'success_rate', summary: 'Median' }, groupBy: { property: 'started', by: 'month' } });
  assert.deepEqual(p.pivot.groups.map((g) => g.key), ['2026-09', '2026-10']);
  // one pivot row per model per month, and each cell holds exactly that month's runs of that model and environment
  for (const g of p.pivot.groups) {
    for (const row of g.rows) {
      for (const c of p.pivot.columns) {
        const n = runs.rows.filter((r) => r.started.slice(0, 7) === g.key && r.model === row.model && r.env === c.path[0]).length;
        assert.equal(row[c.id] ? row[c.id].records.length : 0, n, `${g.key} ${row.model} ${c.id}`);
      }
    }
  }
});

test('both checkers: `by:` is one of day, week, month, quarter, year; `gaps` is a yes/no; a grain on a property that is not a date warns', () => {
  const props = new Set(Object.keys(runs.properties));
  const types = Object.fromEntries(Object.entries(runs.properties).map(([k, v]) => [k, v.type]));
  const good = 'views:\n  - type: table\n    name: A\n    groupBy: { property: started, by: week, gaps: true }\n  - type: pivot\n    name: B\n    splitBy: [env]\n    groupBy: { property: started, by: quarter, direction: DESC }\n    subGroupBy: { property: started, by: month }\n';
  assert.deepEqual(checkText(good, { properties: props, types, datasetName: 'runs.json' }), []);
  const bad = checkText('views:\n  - type: table\n    name: A\n    groupBy: { property: started, by: weekly }\n  - type: table\n    name: B\n    subGroupBy: { property: started, by: month, gaps: often }\n', { properties: props, types, datasetName: 'runs.json' });
  const lines = bad.map((p) => `${p.level} ${p.line} ${p.path.join('.')} ${p.message}`);
  assert.ok(lines.some((l) => l.startsWith('error 4 views.0.groupBy.by "weekly" is not one of day, week, month, quarter, year (did you mean \'week\'?)')), lines.join('\n'));
  assert.ok(lines.some((l) => l.startsWith('error 7 views.1.subGroupBy.gaps must be boolean')), lines.join('\n'));
  const text = checkText('views:\n  - type: table\n    name: A\n    groupBy: { property: model, by: month }\n', { properties: props, types, datasetName: 'runs.json' });
  assert.deepEqual(text.map((p) => `${p.level} ${p.line} ${p.path.join('.')} ${p.message}`), ["warning 4 views.0.groupBy.by 'by: month' groups dates, and 'model' is text: a value that is not an ISO date falls in \"No model\""]);
});
