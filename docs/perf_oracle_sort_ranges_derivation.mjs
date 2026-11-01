// Derive the perf oracle's `model` digest for the sort change (a numeric list sorts by its low end, ties by its high
// end) FROM THE CODE BEFORE IT: the old kit's row models over the gallery, with every per-property sort whose property
// holds numeric lists re-ordered by an independent implementation of the spec (Math.min / Math.max, TanStack's index
// tie-break), then digested exactly as tests/unit/perf-oracle-corpus.mjs does. Never imports the code under test.
//   node docs/perf_oracle_sort_ranges_derivation.mjs <checkout of the commit before> <this checkout>/gallery/examples
// (main a6fd07c over this lane's gallery prints model 107b14de…6, the golden; with PLAIN=1, the re-ordering off, it prints
// the golden before, 13c92dd8…dfdd)
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';

const [oldRoot, exRoot] = process.argv.slice(2);
const corpus = await import(pathToFileURL(join(oldRoot, 'tests', 'unit', 'perf-oracle-corpus.mjs')).href);
const kit = await corpus.loadKit(oldRoot);
const all = [...corpus.cases(kit, exRoot), corpus.tieCase(kit)];
const { rowModel, properties } = kit.rowmodel;
const cellValue = kit.grammar.cellValue;

// the corpus's own serialiser and digest (perf-oracle-corpus.mjs lines 74-81 and `digest`), copied
const groupShape = (gs) => (gs || []).map((g) => [JSON.stringify(g.key), g.property, g.rows.map((r) => r.id).join(','), groupShape(g.groups)]);
const modelText = (m) => JSON.stringify([m.rows.map((r) => r.id), groupShape(m.groups), m.total, m.matched, m.error,
  m.pivot ? [m.pivot.rows.map((r) => r.id ?? r._id ?? JSON.stringify(Object.keys(r))), m.pivot.columns.map((c) => c.id), groupShape(m.pivot.groups)] : null]);
const digest = (parts) => createHash('sha256').update(parts.join('\u0001')).digest('hex');

const finite = (x) => typeof x === 'number' && Number.isFinite(x);
const empty = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
const numList = (v) => Array.isArray(v) && v.length > 0 && v.every(finite);

const touched = [];
/** The spec, independently: rows with a value by (min, max) of their list, ascending or descending, a full tie by data
    index (TanStack's fallback, never negated); rows with no value after them, in data index order. */
function reorder(rows, id, direction, indexOf) {
  const withValue = rows.filter((r) => !empty(cellValue(r[id])));
  const none = rows.filter((r) => empty(cellValue(r[id])));
  const key = (r) => { const v = cellValue(r[id]); return { lo: Math.min(...v), hi: Math.max(...v), i: indexOf.get(r) }; };
  const sign = direction === 'DESC' ? -1 : 1;
  const sorted = withValue.map((r) => [r, key(r)]).sort(([, a], [, b]) => sign * (a.lo - b.lo) || sign * (a.hi - b.hi) || a.i - b.i).map(([r]) => r);
  none.sort((a, b) => indexOf.get(a) - indexOf.get(b));
  return [...sorted, ...none];
}

const out = [];
for (const { name, base, dataset } of all) {
  base.views.forEach((v, i) => { out.push(name, String(i), modelText(rowModel(dataset, base, v))); });
  const props = properties(dataset, base);
  const grouped = base.views.find((v) => v.groupBy);
  const indexOf = new Map(dataset.rows.map((r, i) => [r, i]));
  for (const id of Object.keys(props)) {
    const vals = dataset.rows.map((r) => cellValue(r[id])).filter((v) => !empty(v));
    const lists = process.env.PLAIN ? false : vals.some(numList); // PLAIN=1: the old kit as it is, the golden before
    if (lists && !vals.every(numList)) throw new Error(`${name}.${id} mixes numeric lists with other values: this derivation does not model that`);
    for (const direction of ['ASC', 'DESC']) {
      const flat = { type: 'table', sort: [{ property: id, direction }] };
      const m = rowModel(dataset, base, flat);
      if (lists) {
        const rows = reorder(m.rows, id, direction, indexOf);
        touched.push(`${name}.${id} ${direction}`);
        out.push(name, id, direction, modelText({ ...m, rows }));
      } else out.push(name, id, direction, modelText(m));
      if (grouped) {
        const g = rowModel(dataset, base, { ...flat, groupBy: grouped.groupBy });
        if (lists) {
          if ((g.groups || []).some((x) => x.groups)) throw new Error('sub-groups: not modelled');
          if (grouped.groupBy.property === id) throw new Error('grouped by the list property itself: not modelled');
          const groups = g.groups.map((x) => ({ ...x, rows: reorder(x.rows, id, direction, indexOf) }));
          out.push(name, id, direction, 'g', modelText({ ...g, rows: groups.flatMap((x) => x.rows), groups }));
        } else out.push(name, id, direction, 'g', modelText(g));
      }
    }
  }
}
console.log(JSON.stringify({ model: digest(out), touched }, null, 1));
