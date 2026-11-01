/* Source columns (docs/CONTRACT.md §36, docs/peps/0021-source-columns.md, which supersedes 0015): a value several sources state is
   one property per source and a formula over them. Pure: no DOM; the host (elements/data-views.js) unfolds a dataset with it and every
   view reads the columns it makes.

   Zach, 2026-10-31: "its just like a column roll up where the left most take precencde. And then to hide them it simply like a view
   with thoose columns hidden. The roll up itsself is also then just like a formula.. almost like FIRST Value(of cells, x, y, ...)".

     dataset  {sources?: {<id>: {name, kind?, rung?, date?, url?, page?, basis?}}, ladder?: [{id, label}], rows}
     cell     {sources: [{source: <id>, value, text?, unit?, basis?, note?, asOf?, sourceUrl?, sourcePage?, record?}], unit?, why?}
              each entry is a §22 rich cell one source states; `source` names a dataset source (an undeclared one is named by
              that string)
     columns  <property>@<source>: one source's statements, an ordinary column; <property>@source: the source that won;
              <property> itself: the formula, the first non-empty of them. A .base's `formulas:` may state the same formula over any
              plain columns (formula.<name>), in Bases' own syntax (grammar.js parseCoalesce).
     view     {order: [<source id>], ov: {<row id>: <source id>}}: the precedence, and one row's own pick

   WHY truthful (Zach's rule, and the prototype's): a value is kept exactly as its source states it. Precedence and an
   override only choose which stated value is nominal: nothing here edits, drops, merges, rounds or averages a value,
   and nothing mutates a cell. An entry with no value states nothing; a source a stale order lacks is never hidden. */

import { cellValue, coalesceText, parseCoalesce } from './grammar.js';

const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
// WHY as Bases' isEmpty(): 0 and false are values; an object with no keys is not (obsidian.md/help/bases/functions, and run in Obsidian)
const blank = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0) || (isObj(v) && !Object.keys(v).length);

/** A cell whose value several sources may state: a rich cell with a non-empty `sources` list. */
export function isMultiSource(cell) {
  return isObj(cell) && Array.isArray(cell.sources) && cell.sources.length > 0;
}

/** {source id: entry} for the entries that state a value, the first entry per source, in the cell's order. */
function entriesOf(cell) {
  const out = new Map();
  if (!isMultiSource(cell)) return out;
  for (const e of cell.sources) {
    if (!isObj(e) || e.source === undefined || e.source === null || e.source === '') continue;
    const id = String(e.source);
    if (!out.has(id) && !blank(e.value)) out.set(id, e);
  }
  return out;
}

/** The entry of `source` that states the cell (its first), or null. */
export function entryOf(cell, source) {
  return source === null || source === undefined ? null : entriesOf(cell).get(String(source)) || null;
}

/** The sources that state the cell, in precedence order; a source the order does not name follows, in the cell's order
    (WHY: a stored or linked order made before a source existed must never hide it). */
export function stated(cell, order = []) {
  const have = entriesOf(cell);
  const out = [];
  for (const s of order || []) if (have.has(String(s)) && !out.includes(String(s))) out.push(String(s));
  for (const s of have.keys()) if (!out.includes(s)) out.push(s);
  return out;
}

/** The first source in the order that states the cell, or null. */
export function byPrecedence(cell, order = []) {
  return stated(cell, order)[0] ?? null;
}

/** What two stated values are compared by: the value as stated (JSON, so a list compares element by element and a
    number never equals its text) and its unit (the entry's, else the cell's; no conversion: 3800 mN·m and 3.8 N·m are
    two statements). -0 and 0 are one value. */
function keyOf(entry, cell) {
  const unit = entry.unit !== undefined && entry.unit !== null && entry.unit !== '' ? entry.unit : isObj(cell) ? cell.unit ?? null : null;
  return JSON.stringify([entry.value, unit]);
}

/** Do the sources that state the cell disagree? Independent of precedence. Text differences alone are not a
    disagreement: `text` is how a value is written, `value` what it says (CONTRACT §22). */
export function conflict(cell) {
  const keys = new Set();
  for (const e of entriesOf(cell).values()) keys.add(keyOf(e, cell));
  return keys.size > 1;
}

/** Do sources a and b both state the cell, and differently? */
export function differs(cell, a, b) {
  const have = entriesOf(cell);
  const x = a != null && have.get(String(a)), y = b != null && have.get(String(b));
  return !!(x && y) && keyOf(x, cell) !== keyOf(y, cell);
}

/** The agree / differs fact of a cell two or more sources state: {text: "+3 · 2 differ", conflict}, or null. Derived from the statements
    alone, so it holds with their columns hidden. */
export function agreement(cell, view = {}, id = null) {
  const list = stated(cell, view.order || []);
  if (list.length < 2) return null;
  const { source } = pick(cell, view, id);
  const others = list.length - 1;
  const nd = list.filter((s) => s !== source && differs(cell, s, source)).length;
  return { text: nd ? `+${others} · ${nd} differ${nd === 1 ? 's' : ''}` : `+${others} agree${others === 1 ? 's' : ''}`, conflict: conflict(cell) };
}

/** The source shown for a cell of row `id`: the row's override when that source states the cell, else precedence.
    {source, via: 'override' | 'precedence' | 'none', prec: what precedence alone picks}. */
export function pick(cell, view = {}, id = null) {
  const prec = byPrecedence(cell, view.order || []);
  const o = view.ov && id !== null && id !== undefined ? view.ov[String(id)] : undefined;
  if (o !== undefined && o !== null && entriesOf(cell).has(String(o))) return { source: String(o), via: 'override', prec };
  return { source: prec, via: prec ? 'precedence' : 'none', prec };
}

/** The fields ([{id, cell}]) whose shown VALUE changes between two views. A switch between two sources that agree is
    not a change. */
export function changed(fields, before, after) {
  return (fields || []).filter((f) => {
    const a = pick(f.cell, before, f.id).source, b = pick(f.cell, after, f.id).source;
    return a !== b && differs(f.cell, a, b);
  });
}

/** The fields an override holds while precedence alone would now show a different value than it did before. */
export function held(fields, before, after) {
  return (fields || []).filter((f) => pick(f.cell, after, f.id).via === 'override'
    && differs(f.cell, byPrecedence(f.cell, (before || {}).order || []), byPrecedence(f.cell, (after || {}).order || [])));
}

/** The wanted items, in their new order, in the places they held; everything else stays. WHY: a hidden source keeps its place when the
    visible ones move: "to hide them it simply like a view". Never mutates. */
export function inPlace(list, wanted) {
  const have = new Set(list);
  const next = wanted.filter((x) => have.has(x));
  const want = new Set(next);
  let i = 0;
  return list.map((x) => (want.has(x) ? next[i++] : x));
}

/** The default order: the sources sorted by their rung on the evidence ladder (best first); a tie keeps the given order;
    a source with no rung, or one the ladder does not list, follows. No ladder: the given order. */
export function ladderOrder(ids, sources = {}, ladder = null) {
  const list = (ids || []).map(String);
  const rungs = Array.isArray(ladder) ? ladder.map((r) => String(isObj(r) ? r.id : r)) : [];
  const rank = (s) => { const r = isObj(sources) && isObj(sources[s]) ? sources[s].rung : undefined; const i = r === undefined ? -1 : rungs.indexOf(String(r)); return i < 0 ? rungs.length : i; };
  return list.map((s, i) => [s, rank(s), i]).sort((a, b) => a[1] - b[1] || a[2] - b[2]).map(([s]) => s);
}

/** Every multi-source cell of the rows: [{id: row id, property, cell}], rows in order, properties in `props` order. */
export function fieldsOf(rows, props) {
  const out = [];
  for (const r of rows || []) for (const p of props) if (isMultiSource(r[p])) out.push({ id: String(r.id), property: p, cell: r[p] });
  return out;
}

/** Every source id: the dataset's declared sources in declaration order, then any a cell names that is not declared, as
    first met (rows in order, a row's properties in key order). */
export function sourceIds(dataset) {
  const out = isObj(dataset && dataset.sources) ? Object.keys(dataset.sources) : [];
  for (const r of (dataset && dataset.rows) || []) {
    for (const v of Object.values(r)) {
      if (!isMultiSource(v)) continue;
      for (const e of v.sources) if (isObj(e) && e.source !== undefined && e.source !== null && e.source !== '' && !out.includes(String(e.source))) out.push(String(e.source));
    }
  }
  return out;
}

/** An order read from a link or storage, against this data: unknown and repeated ids go, the ones it lacks follow in the
    default order. */
export function normalizeOrder(order, ids, def = ids) {
  const known = new Set((ids || []).map(String));
  const out = [];
  for (const s of Array.isArray(order) ? order : []) if (known.has(String(s)) && !out.includes(String(s))) out.push(String(s));
  for (const s of def || []) if (!out.includes(String(s)) && known.has(String(s))) out.push(String(s));
  for (const s of ids || []) if (!out.includes(String(s))) out.push(String(s));
  return out;
}

/** Overrides read from a link or storage, against these fields: only a row that has a multi-source cell, picking a
    source that states one of that row's cells (WHY: "N chosen by hand" must count what is really chosen). */
export function normalizePicks(ov, fields) {
  const out = {};
  if (!isObj(ov)) return out;
  for (const [row, s] of Object.entries(ov)) {
    if (s === null || s === undefined || s === '') continue;
    if ((fields || []).some((f) => String(f.id) === String(row) && entriesOf(f.cell).has(String(s)))) out[String(row)] = String(s);
  }
  return out;
}

const PROVENANCE = ['text', 'unit', 'basis', 'note', 'asOf', 'sourceUrl', 'sourcePage', 'record', 'low', 'high', 'n', 'why'];

/** One entry as the §22 rich cell it is, its source named: the entry's own fields exactly as stated, the source's
    name as `source`, its url / page / date / basis only where the entry has none, the cell's unit where the entry has
    none. */
export function entryCell(entry, sources = {}, cell = null) {
  const id = String(entry.source);
  const def = isObj(sources) && isObj(sources[id]) ? sources[id] : {};
  const out = { value: entry.value };
  for (const k of PROVENANCE) if (entry[k] !== undefined && entry[k] !== null && entry[k] !== '') out[k] = entry[k];
  // `named`: a rich cell in a plain column a formula reads says its own source; the column is only where it sat
  out.source = !blank(entry.named) ? String(entry.named) : def.name !== undefined && def.name !== null && def.name !== '' ? String(def.name) : id;
  if (out.unit === undefined && isObj(cell) && cell.unit !== undefined && cell.unit !== null && cell.unit !== '') out.unit = cell.unit;
  if (out.sourceUrl === undefined && def.url) out.sourceUrl = def.url;
  if (out.sourcePage === undefined && def.page) out.sourcePage = def.page;
  if (out.asOf === undefined && def.date) out.asOf = def.date;
  if (out.basis === undefined && def.basis) out.basis = def.basis;
  return out;
}

/** The nominal cell for row `id`: the picked entry (entryCell), with every entry still in `sources`, untouched. No
    source states a value: {value: null, why}, the cell's reason, else the entries' own, else "no source states a value". */
export function resolveCell(cell, view = {}, id = null, sources = {}) {
  const { source } = pick(cell, view, id);
  if (source === null) {
    const whys = isMultiSource(cell) ? cell.sources.map((e) => (isObj(e) ? e.why : null)).filter((w) => typeof w === 'string' && w) : [];
    const why = isObj(cell) && typeof cell.why === 'string' && cell.why ? cell.why : whys.length ? whys.join('; ') : 'no source states a value';
    const out = { value: null, why, sources: cell.sources };
    if (isObj(cell) && cell.unit) out.unit = cell.unit;
    return out;
  }
  const out = entryCell(entriesOf(cell).get(source), sources, cell);
  out.sources = cell.sources;
  return out;
}

/** The rows of a value's source popover (CONTRACT §36, the source popover): every source that states the cell, in
    precedence order (a source the order lacks after, in the cell's order), each {source, rank (its place in the order,
    1-based; null when the order lacks it), name, rung, rungLabel (its rung's label on the ladder, or null), cell (the
    entry as the §22 cell it is: entryCell), state: 'shown' | 'differs' | 'agrees' (a source column's words), nominal,
    pinned (the row's pick put it there)}; and what is shown ({shown, via, prec}: pick()'s). `info` is precedenceOf()'s
    {sources, ladder} (el.precedence carries both). WHY here, pure: the popover's marks are precedence's own answers,
    and a view, the element and a test read them alike. */
export function sourceRows(cell, view = {}, id = null, info = {}) {
  const sources = isObj(info) && isObj(info.sources) ? info.sources : {};
  const ladder = isObj(info) && Array.isArray(info.ladder) ? info.ladder : [];
  const order = ((view && view.order) || []).map(String);
  const { source: shown, via, prec } = pick(cell, view || {}, id);
  const have = entriesOf(cell);
  const rows = stated(cell, order).map((s) => {
    const def = isObj(sources[s]) ? sources[s] : {};
    const rung = def.rung === undefined || def.rung === null || def.rung === '' ? null : String(def.rung);
    const step = rung === null ? null : ladder.find((r) => String(isObj(r) ? r.id : r) === rung);
    const at = order.indexOf(s);
    return {
      source: s,
      rank: at < 0 ? null : at + 1,
      name: def.name !== undefined && def.name !== null && def.name !== '' ? String(def.name) : s,
      rung,
      rungLabel: isObj(step) && step.label !== undefined && step.label !== null && step.label !== '' ? String(step.label) : null,
      cell: entryCell(have.get(s), sources, cell),
      state: s === shown ? 'shown' : differs(cell, s, shown) ? 'differs' : 'agrees',
      nominal: s === shown,
      pinned: s === shown && via === 'override',
    };
  });
  return { rows, shown, via, prec };
}

/** What the Nominal source column names for a cell (CONTRACT §36, a derived value names its source): {source (the
    picked source's id, for a value with several; null for a §22 cell), name (its name; null when the cell names only an
    address), address (the picked entry's sourceUrl, else its source's url; a §22 cell's sourceUrl, else its sourcePage;
    null when none), derived (the value shown is derived: its basis, the entry's own else its declared source's, is
    'derived')}, or null when nothing names a source (the column draws "—"). WHY by basis and by what the cell names:
    data-ui computes no value, so a derived one arrives marked by the producer's resolver (RobotParts' JMC pole pairs,
    decoded from the model code on a selection list, cite that list), and what it came from is the source it names. */
export function nominalSource(cell, view = {}, id = null, info = {}) {
  if (isMultiSource(cell)) {
    const sources = isObj(info) && isObj(info.sources) ? info.sources : {};
    const { source } = pick(cell, view || {}, id);
    if (source === null) return null;
    const c = entryCell(entriesOf(cell).get(source), sources, cell);
    return { source, name: c.source, address: blank(c.sourceUrl) ? null : c.sourceUrl, derived: c.basis === 'derived' };
  }
  if (!isObj(cell)) return null;
  const name = blank(cell.source) ? null : String(cell.source);
  const address = !blank(cell.sourceUrl) ? String(cell.sourceUrl) : !blank(cell.sourcePage) ? String(cell.sourcePage) : null;
  if (name === null && address === null) return null;
  return { source: null, name, address, derived: cell.basis === 'derived' };
}

/** Does a cell name a source? A list of sources (several), or a §22 rich cell with a `source`, a `sourceUrl` or a
    `sourcePage` (one). */
function namesSource(v) {
  return isObj(v) && (isMultiSource(v) || !blank(v.source) || !blank(v.sourceUrl) || !blank(v.sourcePage));
}

/** The properties whose cells name a source (several, or one: see namesSource), in the dataset's properties order,
    then any other as first met (rows in order, a row's keys in order). Reads every cell: call it for a dataset that
    declares `sourceColumn: true` (sourceColumnOf), never for every dataset. */
export function sourcedProperties(dataset) {
  if (!dataset || !Array.isArray(dataset.rows)) return [];
  const met = new Set();
  for (const r of dataset.rows) {
    if (!isObj(r)) continue;
    for (const k in r) if (!met.has(k) && namesSource(r[k])) met.add(k);
  }
  const declared = Object.keys(dataset.properties || {});
  return [...declared.filter((k) => met.has(k)), ...[...met].filter((k) => !declared.includes(k))];
}

/** The Nominal source column's declaration (CONTRACT §36, the source column on one-source data): null when the dataset
    declares none (the column then follows a value with several sources only, as before: WHY, data whose cells carry
    one §22 source is common, a gallery's sourced torques and KPIs, and must not grow a column it never asked for);
    {on: false, properties: []} for `sourceColumn: false` (never drawn); {on: true, properties} for `sourceColumn: true`,
    `properties` the ones whose cells name a source (sourcedProperties). Only a boolean declares it. */
export function sourceColumnOf(dataset) {
  const decl = dataset && typeof dataset === 'object' ? dataset.sourceColumn : undefined;
  if (decl === false) return { on: false, properties: [] };
  if (decl === true) return { on: true, properties: sourcedProperties(dataset) };
  return null;
}

/** The column of `source` in `property`, `<property>@<source>`; with no source, `<property>@source`, the "<label> source" column.
    WHY @: it is no part of a name Bases reads bare, so nothing can read it as anything else, and YAML takes it unquoted (not first); a
    formula writes such a column note["nominal@bench"], which real Obsidian runs. A source really called `source` keeps a column. */
export function columnId(property, source) {
  if (source === undefined) return `${property}@source`;
  return source === 'source' ? `${property}@@source` : `${property}@${source}`;
}

/** The file's formulas: [{name, text, list}], `list` null for one data-ui does not run. */
function formulasOf(base) {
  const all = isObj(base) && isObj(base.formulas) ? base.formulas : {};
  return Object.entries(all).map(([name, text]) => ({ name, text, list: parseCoalesce(text) }));
}

/** The declared source a one-source cell names (its id, or its name), or null. */
function ownSource(cell, sources) {
  if (!isObj(cell) || blank(cell.source)) return null;
  const s = String(cell.source);
  if (isObj(sources[s])) return s;
  for (const [id, def] of Object.entries(sources)) if (isObj(def) && def.name === s) return id;
  return null;
}

/** What a dataset and its .base file roll up, or null when nothing does: {ids (every source, or column a formula reads), sources (each
    named), ladder, default, properties (the formulas: each property with several sources, then formula.<name>), columns (<property>:
    [source ids that state it]), members (<column id>: {formula, source}), lists (<formula>: [sources], a file's own order), formulas
    (<formula>: {name, text})}. The default: the sources by their rung; a file's formula states it; with none, the first view that
    names two sources, left to right; either way the others keep their ladder places. */
export function precedenceOf(dataset, base = null) {
  if (!dataset || !Array.isArray(dataset.rows)) return null;
  const props = [];
  const declared = Object.keys(dataset.properties || {});
  // WHY for-in and a cheap test first: every dataset is scanned once when it is set, so data with no multi-source cell
  // (nearly all) pays one typeof per cell and no allocation
  for (const r of dataset.rows) {
    if (!isObj(r)) continue;
    for (const k in r) {
      const v = r[k];
      if (v !== null && typeof v === 'object' && v.sources !== undefined && !props.includes(k) && isMultiSource(v)) props.push(k);
    }
  }
  const written = formulasOf(base).filter((f) => f.list);
  const over = written.filter((f) => !props.includes(f.name));
  if (!props.length && !over.length) return null;
  props.sort((a, b) => (declared.indexOf(a) < 0 ? 1e9 : declared.indexOf(a)) - (declared.indexOf(b) < 0 ? 1e9 : declared.indexOf(b)));
  const ids = props.length ? sourceIds(dataset) : [];
  for (const f of over) for (const m of f.list) if (!ids.includes(m)) ids.push(m);
  const given = isObj(dataset.sources) ? dataset.sources : {};
  const sources = Object.fromEntries(ids.map((s) => [s, { name: s, ...(isObj(given[s]) ? given[s] : {}) }]));
  // a column a formula reads stands for a source, under its own label
  for (const f of over) for (const m of f.list) { const label = ((dataset.properties || {})[m] || {}).label; if (label && !isObj(given[m])) sources[m].name = label; }
  const columns = {}, members = {};
  for (const p of props) {
    const seen = new Set();
    for (const r of dataset.rows) {
      const cell = isObj(r) ? r[p] : null;
      if (isMultiSource(cell)) { for (const e of cell.sources) if (isObj(e) && !blank(e.source)) seen.add(String(e.source)); } else { const s = ownSource(cell, sources); if (s !== null) seen.add(s); }
    }
    columns[p] = ids.filter((s) => seen.has(s));
    for (const s of columns[p]) members[columnId(p, s)] = { formula: p, source: s };
  }
  for (const f of over) for (const m of f.list) if (!members[m]) members[m] = { formula: `formula.${f.name}`, source: m };
  const ladder = Array.isArray(dataset.ladder) ? dataset.ladder : null;
  const keys = (list) => [...new Set(list.filter((m) => members[m]).map((m) => members[m].source))];
  const ladderly = ladderOrder(ids, sources, ladder);
  let order = ladderly;
  const lists = {}, formulas = {};
  for (const f of written) {
    const id = props.includes(f.name) ? f.name : `formula.${f.name}`;
    // WHY the ladder under a value's formula: a file that names some sources never hides another (the rule a stale order keeps)
    lists[id] = props.includes(f.name) ? inPlace(ladderly, keys(f.list)) : keys(f.list);
    formulas[id] = { name: f.name, text: f.text, list: f.list };
  }
  // WHY backwards: a column two formulas read draws in the first one's place; each formula's value still reads its own list (formulaView)
  for (const f of [...written].reverse()) order = inPlace(order, keys(f.list));
  if (!written.length) {
    for (const v of (isObj(base) && Array.isArray(base.views) ? base.views : [])) {
      const named = keys(Array.isArray(v.order) ? v.order : []);
      if (named.length > 1) { order = inPlace(order, named); break; }
    }
  }
  return { ids, sources, ladder, default: order, properties: [...props, ...over.map((f) => `formula.${f.name}`)], columns, members, lists, formulas };
}

/** The state a formula reads: `view`, or with the reader's order untouched, the formula's own list. WHY: two formulas may read one
    column in opposite orders ("best case", "checked first"), and each file's text means what it says; a reader's drag moves a column,
    so it moves for every formula that reads it. */
export function formulaView(info, view, property) {
  const list = info && info.lists && info.lists[property];
  if (!list || (view && view.order && view.order.join('\u0000') !== info.default.join('\u0000'))) return view;
  return { ...view, order: list };
}

/** What the "<label> source" column says of a cell: {value: the name it goes by, url?, derived?}, or null when nothing names one. */
function sourceCell(cell, view, id, info) {
  const named = nominalSource(cell, view, id, info);
  if (!named) return null;
  const out = { value: named.name !== null ? named.name : String(named.address).replace(/^https?:\/\//, '') };
  if (named.address !== null) out.url = named.address;
  if (named.derived) out.derived = true;
  return out;
}

/** A row's cell for a formula over plain columns: the columns' filled cells as a list of sources, in the formula's order, so the pill,
    the popover and a pick read it as they read any value with several sources. */
function overColumns(row, list) {
  const sources = [];
  for (const id of list) {
    const c = row[id];
    const v = cellValue(c);
    if (blank(v)) continue;
    sources.push(isObj(c) ? { ...c, value: v, source: id, ...(blank(c.source) ? {} : { named: c.source }) } : { source: id, value: v });
  }
  return sources.length ? { sources } : null;
}

const NOT_RUN = 'data-ui runs one formula, the first non-empty of a list of columns: this one needs Obsidian';

/** The dataset with its columns: every row gains <property>@<source> and the formulas over plain columns (still unresolved: their list
    of sources); every property gains its meta. `info` is precedenceOf()'s, null when nothing rolls up. The same dataset object when
    nothing is added, so nothing changes for it. The dataset as loaded is never touched. A column is typed as its value and reads its
    unit the same way; `hidden` keeps it out of a view that does not name it, `offered` keeps it in Property visibility and the inspector. */
export function unfoldDataset(dataset, info = null, base = null) {
  if (!dataset || !Array.isArray(dataset.rows)) return dataset;
  const props = dataset.properties || {};
  const unfolded = info ? Object.keys(info.columns) : [];
  const sc = sourceColumnOf(dataset);
  const named = new Set(unfolded);
  if (sc && sc.on) {
    for (const p of sc.properties) named.add(p);
    const first = Object.keys(props).find((id) => id !== dataset.titleProperty);
    if (!named.size && first) named.add(first);
  }
  const idle = formulasOf(base).filter((f) => !f.list);
  if (!info && !named.size && !idle.length) return dataset;
  const added = {};
  const quiet = { hidden: true, offered: true };
  // WHY these go: a column says its own label, width and reason; the rest (type, unit, digits, labels) is how its value reads
  const like = (id) => { const { label, width, hidden, facet, description, note, why, ...rest } = isObj(props[id]) ? props[id] : {}; return { type: 'text', ...rest }; };
  for (const p of unfolded) {
    const label = (props[p] || {}).label || p;
    for (const s of info.columns[p]) {
      const def = info.sources[s];
      const about = [def.kind, def.date].filter(Boolean).join(' · ');
      added[columnId(p, s)] = { ...like(p), label: unfolded.length > 1 ? `${label} · ${def.name}` : def.name, ...quiet, of: p, source: s, width: 156, why: `${def.name} states no value here`, ...(about ? { note: about } : {}) };
    }
  }
  for (const p of named) {
    const label = (props[p] || {}).label || p;
    added[columnId(p)] = { type: 'text', label: `${label} source`, ...quiet, of: p, display: 'source', width: 236, derived: `the source of each row's ${label}`, note: `the source of each row's ${label}`, why: 'no source given' };
  }
  const over = info ? info.properties.filter((id) => !info.columns[id]) : [];
  for (const id of over) { const f = info.formulas[id]; added[id] = { ...like(f.list[0]), label: f.name, ...quiet, icon: 'formula', derived: f.text, why: 'none of its columns has a value' }; }
  for (const f of idle) added[`formula.${f.name}`] = { type: 'text', label: f.name, ...quiet, icon: 'formula', derived: f.text, why: NOT_RUN };
  // WHY the same rows when only a formula data-ui does not run is added: a column of dashes costs no copy of a big dataset
  if (!info && !named.size) return { ...dataset, properties: { ...props, ...added } };
  const rows = dataset.rows.map((r) => {
    if (!isObj(r)) return r;
    const out = { ...r };
    for (const p of unfolded) {
      const cell = r[p];
      if (isMultiSource(cell)) {
        const have = entriesOf(cell);
        for (const s of info.columns[p]) {
          const e = have.get(s);
          if (e) { out[columnId(p, s)] = entryCell(e, info.sources, cell); continue; }
          const said = cell.sources.find((x) => isObj(x) && String(x.source) === s && !blank(x.why));
          if (said) out[columnId(p, s)] = { value: null, why: `${info.sources[s].name}: ${said.why}` };
        }
      } else {
        // WHY: a plain cell that names a source is that source's statement, so "1 property per cell" holds for its row too
        const s = ownSource(cell, info.sources);
        if (s !== null) out[columnId(p, s)] = cell;
      }
    }
    for (const p of named) if (!isMultiSource(r[p])) { const c = sourceCell(r[p], {}, r.id, info); if (c) out[columnId(p)] = c; }
    for (const id of over) out[id] = overColumns(r, info.formulas[id].list);
    return out;
  });
  return { ...dataset, properties: { ...props, ...added }, rows };
}

/** The dataset as a reader sees it under `view`: each formula's cell the first non-empty of its columns (resolveCell), and "<label>
    source" the source that won. A row with no such cell is the same object; `dataset` (unfoldDataset's) is never touched. */
export function resolveDataset(dataset, view = {}, info = precedenceOf(dataset)) {
  if (!info) return dataset;
  const props = info.properties;
  const rows = dataset.rows.map((r) => {
    if (!isObj(r) || !props.some((p) => isMultiSource(r[p]))) return r;
    const out = { ...r };
    for (const p of props) {
      if (!isMultiSource(r[p])) continue;
      const v = formulaView(info, view, p);
      out[p] = resolveCell(r[p], v, r.id, info.sources);
      if (info.columns[p]) out[columnId(p)] = sourceCell(r[p], v, r.id, info);
    }
    return out;
  });
  // the header says what it reads, best first, as Bases' text does; a producer's own note stays
  const properties = { ...dataset.properties };
  for (const p of props) {
    const meta = properties[p];
    if (!isObj(meta)) continue;
    const list = formulaView(info, view, p).order || info.default;
    const names = list.filter((s) => (info.columns[p] ? info.columns[p].includes(s) : (info.lists[p] || []).includes(s))).map((s) => info.sources[s].name);
    properties[p] = { ...meta, icon: meta.icon || 'formula', ...(meta.note || meta.description ? {} : { note: `the first value of: ${names.join(', ')}` }) };
  }
  return { ...dataset, properties, rows };
}

/** A view's `order` with the columns a formula reads in precedence order, in the places the view gave them. WHY: left-most is the winner
    whatever a file wrote, and a view that shows two sources can never say otherwise. */
export function slotOrder(list, info, precedence) {
  if (!info || !precedence) return list;
  const rank = new Map(precedence.map((s, i) => [s, i]));
  const places = new Map();
  list.forEach((id, i) => { const m = info.members[id]; if (m) { if (!places.has(m.formula)) places.set(m.formula, []); places.get(m.formula).push(i); } });
  const out = [...list];
  const at = (id) => rank.get(info.members[id].source) ?? 1e9;
  for (const slots of places.values()) {
    const ids = slots.map((i) => list[i]).sort((a, b) => at(a) - at(b));
    slots.forEach((i, k) => { out[i] = ids[k]; });
  }
  return out;
}

/** The precedence after a view's `order` went from `before` to `after`: the same columns in another order are a new precedence, in the
    places they held; a hide or a show is no reorder (WHY: Property visibility appends, and a source shown again goes back to its
    place). `order` itself when nothing moved. */
export function orderAfter(before, after, info, order) {
  if (!info) return order;
  let out = order;
  for (const f of new Set(Object.values(info.members).map((m) => m.formula))) {
    const of = (list) => (list || []).filter((id) => info.members[id] && info.members[id].formula === f);
    const a = of(before), b = of(after);
    if (a.length < 2 || a.length !== b.length || a.every((id, i) => id === b[i]) || !a.every((id) => b.includes(id))) continue;
    out = inPlace(out, b.map((id) => info.members[id].source));
  }
  return out;
}

/** `after`, with a column a formula reads that `before` lacked put beside the others of its formula, in its place in the list. WHY: Property
    visibility appends, and slotOrder alone would throw the last source into that last slot, past whatever follows the sources. */
export function placeShown(before, after, info, precedence) {
  if (!info || !precedence) return after;
  const at = (id) => { const i = precedence.indexOf(info.members[id].source); return i < 0 ? 1e9 : i; };
  let out = after;
  for (const id of after) {
    const m = info.members[id];
    if (!m || (before || []).includes(id)) continue;
    const peers = out.filter((x) => x !== id && info.members[x] && info.members[x].formula === m.formula);
    if (!peers.length) continue;
    const ahead = peers.filter((x) => at(x) < at(id)).pop();
    out = out.filter((x) => x !== id);
    out.splice(ahead ? out.indexOf(ahead) + 1 : out.indexOf(peers[0]), 0, id);
  }
  return out;
}

/** A view of this data, its columns said: `formula.<p>` read as <p>, `<p>@*` as every source of it in precedence order, and in a table
    the "<label> source" column after the value, the alias an existing .base needs: a view that names the value and no column of it
    keeps the column it always had, unless the view or the dataset says `sourceColumn: false`. Then the columns a formula reads in
    precedence order. The same view when there is nothing to say. */
export function ownColumns(view, dataset, info, order) {
  const sc = sourceColumnOf(dataset);
  if (!view || (!info && !(sc && sc.on))) return view;
  const unfolded = info ? Object.keys(info.columns) : [];
  const table = (view.type || 'table') === 'table';
  const bare = (id) => { const x = String(id).replace(/^(?:note|formula)\./, ''); return unfolded.includes(x) ? x : id; };
  const rank = (p) => { const of = info.columns[p]; return (order || info.default).filter((s) => of.includes(s)); };
  const every = (id) => { const p = typeof id === 'string' && id.endsWith('@*') ? id.slice(0, -2) : null; return p && info && info.columns[p] ? rank(p).map((s) => columnId(p, s)) : [id]; };
  const props = dataset.properties || {};
  let list = Array.isArray(view.order) && view.order.length ? view.order.map(bare).flatMap(every) : null;
  if (!list && !table) return view;
  if (!list) list = Object.keys(props).filter((id) => !props[id].hidden && !props[id].pivot);
  if (table && view.sourceColumn !== false && dataset.sourceColumn !== false) {
    const P = list.find((id) => unfolded.includes(id)) || (sc && sc.on ? list.find((id) => sc.properties.includes(id)) || list.find((id) => id !== dataset.titleProperty) : null);
    if (P && !list.some((id) => typeof id === 'string' && id.startsWith(`${P}@`))) list = list.flatMap((id) => (id === P ? [id, columnId(P)] : [id]));
  }
  return { ...view, order: slotOrder(list, info, order || (info && info.default)) };
}

/** The saved view that shows the sources, for a file that has none: its first table with the value in it, each "<label> source" column
    given up for every source of the value. WHY a view (Zach: "to hide them it simply like a view with thoose columns hidden") and WHY
    implied: Manage sources was the one way to reach them from a file that predates them, and one file may serve a thousand parts, each
    with its own sources. A file that names a source column, or a view called Sources, has said what it wants. */
export function sourcesView(views, info) {
  const unfolded = info ? Object.keys(info.columns) : [];
  if (!unfolded.length || !Array.isArray(views)) return null;
  const orderOf = (v) => (Array.isArray(v.order) ? v.order : []).map((id) => String(id).replace(/^(?:note|formula)\./, ''));
  if (views.some((v) => v.name === 'Sources' || orderOf(v).some((id) => unfolded.some((p) => id.startsWith(`${p}@`))))) return null;
  const from = views.find((v) => (v.type || 'table') === 'table' && orderOf(v).some((id) => unfolded.includes(id)));
  if (!from) return null;
  const { sourceColumn, ...rest } = from;
  return { ...rest, name: 'Sources', order: orderOf(from).flatMap((id) => (unfolded.includes(id) ? [id, `${id}@*`] : [id])) };
}

/** A cell with one source's statement set: an edit goes to that source's own column, and nothing beside it moves. Its old `text` goes,
    it would contradict the value; what the source said of itself stays. Empty clears the statement, the entry staying (it may say
    why). On a plain cell: the source it names is that cell; any other keeps what was there as a statement of its own, so no value is
    lost. Never mutates. */
export function setSourceValue(cell, source, value, sources = {}) {
  const id = String(source);
  const v = blank(value) ? null : value;
  const put = (e) => { const { text, ...rest } = e; return { ...rest, value: v }; };
  if (isMultiSource(cell)) {
    const list = [...cell.sources];
    const at = list.findIndex((e) => isObj(e) && String(e.source) === id);
    if (at < 0) list.push({ source: id, value: v }); else list[at] = put(list[at]);
    return { ...cell, sources: list };
  }
  const known = isObj(sources) ? sources : {};
  if (isObj(cell) && (String(cell.source) === id || ownSource(cell, known) === id)) return put(cell);
  if (blank(cellValue(cell))) return { sources: [{ source: id, value: v }] };
  const own = isObj(cell) ? cell : { value: cell };
  return { sources: [{ ...own, source: ownSource(own, known) ?? (blank(own.source) ? 'unstated' : String(own.source)) }, { source: id, value: v }] };
}

/** An edit whose keys are source columns, as the stored property, whole: the row holds one cell, and a host and undo see that cell.
    `row`: the row as loaded. The same object when no key is one. */
export function foldEdit(set, row, info) {
  if (!info || !set) return set;
  const keys = Object.keys(set).filter((k) => info.members[k] && info.columns[info.members[k].formula]);
  if (!keys.length) return set;
  const out = { ...set };
  for (const k of keys) {
    const { formula, source } = info.members[k];
    out[formula] = setSourceValue(formula in out ? out[formula] : row[formula], source, cellValue(set[k]), info.sources);
    delete out[k];
  }
  return out;
}

/** A formula's text with a list of its columns, in the spelling it had. WHY: precedence stays visible text in the file. */
export function formulaText(info, formula, order) {
  const f = info.formulas[formula];
  const of = info.columns[formula];
  const ids = of ? order.filter((s) => of.includes(s)).map((s) => columnId(formula, s)) : [...order.filter((m) => f.list.includes(m))];
  return coalesceText(ids, f ? f.text : null);
}

// ---------------------------------------------------------------- the URL forms (CONTRACT §31's pattern: readable)
const part = (s) => encodeURIComponent(String(s));
const unpart = (s) => { try { return decodeURIComponent(s); } catch { return s; } };

/** `sources=` in the hash: the order, comma-joined, each id URI-encoded. */
export function encodeOrder(order) { return (order || []).map(part).join(','); }
export function decodeOrder(text) { return typeof text === 'string' && text ? text.split(',').filter(Boolean).map(unpart) : []; }

/** `picks=` in the hash: `row:source` pairs, comma-joined, each part URI-encoded. A pair without a source is skipped. */
export function encodePicks(ov) { return Object.entries(ov || {}).map(([r, s]) => `${part(r)}:${part(s)}`).join(','); }
export function decodePicks(text) {
  const out = {};
  if (typeof text !== 'string' || !text) return out;
  for (const pair of text.split(',')) {
    const at = pair.indexOf(':');
    if (at <= 0 || at === pair.length - 1) continue;
    out[unpart(pair.slice(0, at))] = unpart(pair.slice(at + 1));
  }
  return out;
}
