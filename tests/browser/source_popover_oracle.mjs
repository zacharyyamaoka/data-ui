// The source popover's oracle (tests/browser/source_popover_checks.py; docs/CONTRACT.md §36, the source popover): what
// the popover of every value several sources state must list, computed from a fixture's own JSON with precedence.js's
// pick() and conflict() (the pure half, held on its own by tests/unit/precedence.test.mjs), never from the popover's
// code. Everything else (the default order from the ladder, which entries state a value, the order of the rows, which
// one differs from the nominal, what each row says) is re-derived here from the JSON alone.
//
//   node tests/browser/source_popover_oracle.mjs <data.json> '{"order": [...] | null, "ov": {...}}'
//
// prints {default, order, rows: {<row id>: {<property>: {sources, nominal, via, prec, conflict, popover, rowWide,
// entries: {<source>: {name, rungLabel, rank, state, text, unit, basis, asOf, note, url, link, addr}}}}}}. `popover`:
// two or more sources state the value (the popover is for those; one source keeps the §22 menu). `link`: the address
// when it is a link target (an http(s) URL with a host, or a relative path, query or fragment), else null; `addr`: an
// address that is not one (a private source), drawn as text. Exits 1 if conflict() and the rows' marks disagree.
import { readFileSync } from 'node:fs';
import { pick, conflict } from '../../packages/core/src/precedence.js';

const data = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const state = JSON.parse(process.argv[3] || '{}');
const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const blank = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
const multi = (c) => isObj(c) && Array.isArray(c.sources) && c.sources.length > 0;
const declared = isObj(data.sources) ? data.sources : {};
const ladder = Array.isArray(data.ladder) ? data.ladder : [];

// every source id: the declared ones in declaration order, then any a cell names, as first met
const ids = Object.keys(declared);
for (const r of data.rows) for (const v of Object.values(r)) if (multi(v)) for (const e of v.sources) if (isObj(e) && !blank(e.source) && !ids.includes(String(e.source))) ids.push(String(e.source));
const rungAt = (s) => { const r = isObj(declared[s]) ? declared[s].rung : undefined; const i = ladder.findIndex((x) => String(isObj(x) ? x.id : x) === String(r)); return r === undefined || i < 0 ? ladder.length : i; };
const def = ids.map((s, i) => [s, rungAt(s), i]).sort((a, b) => a[1] - b[1] || a[2] - b[2]).map(([s]) => s);
const order = Array.isArray(state.order) ? state.order : def;
const ov = isObj(state.ov) ? state.ov : {};

/** {source: entry}: the first entry per source that states a value, in the cell's order. */
const entries = (cell) => {
  const out = new Map();
  for (const e of cell.sources) if (isObj(e) && !blank(e.source) && !out.has(String(e.source)) && !blank(e.value)) out.set(String(e.source), e);
  return out;
};
const key = (e, cell) => JSON.stringify([e.value, !blank(e.unit) ? e.unit : (blank(cell.unit) ? null : cell.unit)]);
const isLink = (u) => {
  if (typeof u !== 'string' || !u.trim() || /\s/.test(u.trim())) return false;
  const s = u.trim(), scheme = /^([a-z][a-z0-9+.-]*):/i.exec(s);
  if (scheme) return /^https?$/i.test(scheme[1]) && /^https?:\/\/[^/?#\s]+/i.test(s);
  return /[/.?#]/.test(s);
};
const text = (e) => (typeof e.text === 'string' && e.text !== '' ? e.text : Array.isArray(e.value) ? e.value.join(', ') : String(e.value));

const rows = {};
let bad = [];
for (const r of data.rows) {
  const props = Object.keys(r).filter((p) => multi(r[p]));
  for (const p of props) {
    const cell = r[p], have = entries(cell);
    const list = [...order.filter((s) => have.has(s)), ...[...have.keys()].filter((s) => !order.includes(s))];
    const chosen = pick(cell, { order, ov }, r.id);
    const nominal = chosen.source;
    const meta = isObj(data.properties) && isObj(data.properties[p]) ? data.properties[p] : {};
    const out = {};
    for (const s of list) {
      const e = have.get(s), d = isObj(declared[s]) ? declared[s] : {};
      const rung = d.rung === undefined ? null : ladder.find((x) => String(isObj(x) ? x.id : x) === String(d.rung));
      const unit = [e.unit, cell.unit, meta.unit ? r[meta.unit] : null, meta.unitText].find((u) => !blank(u)) ?? null;
      const url = !blank(e.sourceUrl) ? String(e.sourceUrl) : !blank(d.url) ? String(d.url) : null;
      out[s] = {
        name: !blank(d.name) ? String(d.name) : s,
        rungLabel: rung && isObj(rung) && !blank(rung.label) ? String(rung.label) : null,
        rank: order.includes(s) ? order.indexOf(s) + 1 : null,
        state: s === nominal ? 'shown' : key(e, cell) !== key(have.get(nominal), cell) ? 'differs' : 'agrees',
        text: text(e),
        unit,
        basis: !blank(e.basis) ? String(e.basis) : !blank(d.basis) ? String(d.basis) : null,
        asOf: !blank(e.asOf) ? String(e.asOf) : !blank(d.date) ? String(d.date) : null,
        note: !blank(e.note) ? String(e.note) : null,
        url,
        link: url && isLink(url) ? url : null,
        addr: url && !isLink(url) ? url : null,
      };
    }
    const anyDiffers = Object.values(out).some((x) => x.state === 'differs');
    if (nominal !== null && anyDiffers !== conflict(cell)) bad.push(`${r.id}.${p}`);
    (rows[r.id] ||= {})[p] = {
      sources: list, nominal, via: chosen.via, prec: chosen.prec, conflict: conflict(cell), popover: list.length >= 2,
      // a pick is the row's (CONTRACT §36: ov is keyed by row): the popover says so when the row has another such value
      rowWide: props.length > 1,
      entries: out,
    };
  }
}
if (bad.length) { console.error(`oracle: conflict() and the rows' differs marks disagree on ${bad.join(', ')}`); process.exit(1); }
process.stdout.write(JSON.stringify({ default: def, order, rows }) + '\n');
