/* The view grammar: a stored view is one entry of an Obsidian Bases `.base` file's `views:` list.
   Moved from robotparts lane/tables @ ab5ba92 (design/tables-2026-10-25/views/src/grammar.js) into data-ui's core;
   this is now the one copy. The checker (bin/data-ui.mjs) and every view read it, so they never disagree.

   Bases keys, used with their Bases meaning (help.obsidian.md, "Bases syntax"):
     type        table | cards | list | kanban | map in Bases; data-ui adds pivot, chart, kpi, calendar, timeline,
                 graph, record, compare (docs/CONTRACT.md lists the keys of each)
     name        the tab label
     filters     an expression string, or {and: [...]}, {or: [...]}, {not: [...]} of them
     order       the visible properties, left to right (a property not listed is hidden)
     sort        [{property, direction: ASC | DESC}]
     groupBy     {property, direction}: the one group level Bases has
     columnSize  {property: px}
     summaries   {property: Average | Median | Min | Max | Sum | Range | Unique | Filled | Empty}, on group rows
     limit       the first N rows
   Extension keys (Bases ignores keys it does not know, so a .base file stays valid in Obsidian):
     subGroupBy  {property, direction}: the second group level (Notion's "sub-group", Linear's "sub-grouping")
     path        on a group level: dotted | <separator>: nest to any depth (a list cell is a path as declared; PEP 0020)
     by, gaps    on a group level: a date's bucket (day | week | month | quarter | year), and keep empty buckets
     splitBy     [property, ...]: pivot only; the columns are the distinct values of these, outer first
     value       {property, summary, display}: pivot only; what a pivot cell shows (summary as in `summaries`)
     display     {property: text | number | bar | dist | sparkline | badge}
     units       column | inline: units in a column / header, or written next to each value
     fold        open | closed: groups start unfolded or folded
     rollup      {keep: [property, ...], agg: {property: summary}, dims: [property, ...]}: roll the rows up to the kept
                 dimensions, every other one aggregated per column (docs/CONTRACT.md §16)
   WHY Bases (Zach, 2026-10-25): "learn the grammar once for how to edit the views, then reuse it"; he writes .base
   files daily. Everything here is plain data, so the same view drives the table, the pivot, the URL and a saved preset. */

export const SUMMARIES = ['Average', 'Median', 'Min', 'Max', 'Sum', 'Range', 'Spread', 'Unique', 'Filled', 'Empty', 'Count'];
// WHY aliases: a roll-up's aggregate is written the way spreadsheets say it ("summarize by median / mean / spread",
// Excel and Sheets pivots); each maps onto one Bases summary name, so there is still one vocabulary underneath
export const SUMMARY_ALIASES = { median: 'Median', mean: 'Average', average: 'Average', min: 'Min', max: 'Max', count: 'Count', spread: 'Spread', sum: 'Sum', range: 'Range' };
/** A summary's Bases name from its own name or an alias (median, mean, spread…); null when it is neither. */
export function summaryName(s) {
  if (!s) return null;
  return SUMMARIES.includes(s) ? s : SUMMARY_ALIASES[String(s).toLowerCase()] || null;
}
/** The column menu's Calculate list (Notion's names → the summary each computes; CONTRACT §28), per kind of column. */
export const CALCULATIONS = {
  any: [['Count', 'Count all'], ['Filled', 'Count values'], ['Unique', 'Count unique values'], ['Empty', 'Count empty'], ['Percent empty', 'Percent empty'], ['Percent filled', 'Percent not empty']],
  number: [['Sum', 'Sum'], ['Average', 'Average'], ['Median', 'Median'], ['Min', 'Min'], ['Max', 'Max'], ['Spread', 'Range (max − min)']],
  checkbox: [['Checked', 'Checked'], ['Unchecked', 'Unchecked']],
  date: [['Earliest', 'Earliest date'], ['Latest', 'Latest date']],
};
export const DISPLAYS = ['text', 'number', 'bar', 'dist', 'sparkline', 'badge', 'range', 'stats', 'markdown', 'outline', 'preview', 'status', 'media', 'checkbox'];

const isEmpty = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
const numeric = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** A summary of values ('Median' etc.), ignoring empties. Range is [min, max]; Unique is the count of distinct.
    WHY one pass, sorting only when the answer needs order: every summary used to sort the numbers first, ~30 ms per
    footer at 100,000 rows (perf review 2026-10-26, item 4). Min / Max keep the sort's tie rule (the first of equal
    lows, the last of equal highs, which tells 0 from -0). Sum and Average add in ascending order, as before, unless
    every number is an integer whose sum stays exact: then the order cannot change one bit, and no sort is needed. */
export function summarize(values, summary) {
  switch (summary) {
    case 'Count': return values.length;
    case 'Filled': case 'Empty': {
      let filled = 0;
      for (const v of values) if (!isEmpty(cellValue(v))) filled++;
      return summary === 'Filled' ? filled : values.length - filled;
    }
    case 'Unique': {
      const seen = new Set();
      for (const v of values) { const x = cellValue(v); if (!isEmpty(x)) seen.add(String(x)); }
      return seen.size;
    }
    case 'Min': case 'Max': case 'Range': case 'Spread': {
      let lo = null, hi = null;
      for (const v of values) {
        const x = numeric(cellValue(v));
        if (x === null) continue;
        if (lo === null || x < lo) lo = x;
        if (hi === null || x >= hi) hi = x;
      }
      if (lo === null) return null;
      return summary === 'Min' ? lo : summary === 'Max' ? hi : summary === 'Spread' ? hi - lo : [lo, hi];
    }
    case 'Sum': case 'Average': {
      const nums = numbers(values);
      if (!nums.length) return null;
      // exact when every partial sum is: integers whose absolute values add up to a safe integer
      let exact = true, total = 0, size = 0;
      for (const x of nums) { if (!Number.isInteger(x)) { exact = false; break; } total += x; size += Math.abs(x); }
      if (!exact || !Number.isSafeInteger(size)) total = nums.sort((a, b) => a - b).reduce((a, b) => a + b, 0);
      return summary === 'Sum' ? total : total / nums.length;
    }
    case 'Median': {
      const nums = numbers(values).sort((a, b) => a - b);
      if (!nums.length) return null;
      const mid = nums.length >> 1;
      return nums.length % 2 ? nums[mid] : (nums[mid - 1] + nums[mid]) / 2;
    }
    // Notion's Calculate (CONTRACT §28): the share of rows empty or filled (0-1), a checkbox's ticks, a date's ends
    case 'Percent empty': case 'Percent filled': {
      if (!values.length) return null;
      let filled = 0;
      for (const v of values) if (!isEmpty(cellValue(v))) filled++;
      return summary === 'Percent filled' ? filled / values.length : 1 - filled / values.length;
    }
    case 'Checked': case 'Unchecked': {
      let on = 0;
      for (const v of values) { const x = cellValue(v); if (x === true || x === 'true' || x === 1) on++; }
      return summary === 'Checked' ? on : values.length - on;
    }
    case 'Earliest': case 'Latest': {
      // WHY instants (judge r2 #6): '2026-10-26T00:00:00+14:00' is earlier than '2026-10-25T12:00:00Z', which a string
      // compare gets wrong; the answer is the value as stored, never a reformatted one. A date-only value is that day
      // at 00:00 local, as the date type draws it. Values that are not dates are not compared.
      let best = null, at = null;
      for (const v of values) {
        const x = cellValue(v);
        if (isEmpty(x)) continue;
        const text = String(x);
        const t = Date.parse(/^\d{4}-\d{2}-\d{2}$/.test(text) ? text + 'T00:00:00' : text);
        if (!Number.isFinite(t)) continue;
        if (at === null || (summary === 'Earliest' ? t < at : t > at)) { at = t; best = x; }
      }
      return best;
    }
    default: {
      let only, n = 0;
      for (const v of values) { const x = cellValue(v); if (!isEmpty(x) && n++ === 0) only = x; if (n > 1) break; }
      return n === 1 ? only : null;
    }
  }
}

function numbers(values) {
  const out = [];
  for (const v of values) { const x = numeric(cellValue(v)); if (x !== null) out.push(x); }
  return out;
}

// ---------------------------------------------------------------- filters: a small, documented subset of Bases'
// expression language: literals ("text", 12.5, -20, true, false, null), properties (note.x, x and note["x"] are the
// same), the operators == != > >= < <= && || ! and unary -, parentheses, and the methods .contains(x)
// .startsWith(x) .isEmpty().
// WHY the bracket form: vault notes have hyphenated properties, which Bases writes note["vibe-status"] (Zach's own
// Kanban cards.base); WHY unary minus: `temp_min > -20` failed in the lane (docs/SPEC.md §6, "found on the way").

/** A rich cell {value, unit?, basis?, source?, ...} reads as its value everywhere a view filters, sorts or groups. */
export const cellValue = (v) => (v !== null && typeof v === 'object' && !Array.isArray(v) && 'value' in v ? v.value : v);

function tokenize(src) {
  const out = [];
  const re = /\s*(?:(\d+(?:\.\d+)?(?:e[+-]?\d+)?)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(==|!=|>=|<=|&&|\|\||[()!<>.,\-[\]])|([A-Za-z_][\w]*))/gy;
  let m;
  while (re.lastIndex < src.length) {
    const at = re.lastIndex;
    m = re.exec(src);
    if (!m || m.index !== at) {
      if (/^\s*$/.test(src.slice(at))) break;
      throw new Error(`cannot read the filter at "${src.slice(at, at + 12)}"`);
    }
    if (m[1] !== undefined) out.push({ t: 'num', v: Number(m[1]) });
    else if (m[2] !== undefined) out.push({ t: 'str', v: m[2].slice(1, -1).replace(/\\(.)/g, '$1') });
    else if (m[3] !== undefined) out.push({ t: 'op', v: m[3] });
    else if (m[4] !== undefined) out.push({ t: 'id', v: m[4] });
  }
  return out;
}

/** Compile an expression string into (row) => boolean. Throws on a syntax error (the menu shows it). */
export function compileExpression(src) {
  const toks = tokenize(String(src));
  let i = 0;
  const peek = () => toks[i];
  const take = (v) => (toks[i] && toks[i].v === v ? (i++, true) : false);
  const need = (v) => { if (!take(v)) throw new Error(`expected "${v}" in ${src}`); };
  function primary() {
    const tok = toks[i++];
    if (!tok) throw new Error(`unexpected end of ${src}`);
    if (tok.t === 'num' || tok.t === 'str') return () => tok.v;
    if (tok.t === 'op' && tok.v === '(') { const e = or(); need(')'); return e; }
    if (tok.t === 'op' && tok.v === '!') { const e = primary(); return (r) => !truthy(e(r)); }
    if (tok.t === 'op' && tok.v === '-') {
      const e = primary();
      return (r) => { const v = cellValue(e(r)); return numeric(v) !== null ? -v : null; };
    }
    if (tok.t === 'id') {
      if (tok.v === 'true') return () => true;
      if (tok.v === 'false') return () => false;
      if (tok.v === 'null') return () => null;
      const path = [tok.v];
      let get = null;
      while (peek() && (peek().v === '.' || peek().v === '[')) {
        if (take('[')) {
          const key = toks[i++];
          if (!key || key.t !== 'str') throw new Error(`expected a quoted name inside [ ] in ${src}`);
          need(']');
          if (get) throw new Error(`unexpected [${JSON.stringify(key.v)}] in ${src}`);
          path.push({ key: key.v });
          continue;
        }
        i++;
        const name = toks[i++];
        if (!name || name.t !== 'id') throw new Error(`expected a name after "." in ${src}`);
        if (peek() && peek().v === '(') {
          i++;
          const args = [];
          if (!take(')')) { do args.push(or()); while (take(',')); need(')'); }
          const base = get || propertyGetter(path);
          get = method(base, name.v, args, src);
        } else if (!get) path.push(name.v);
        else throw new Error(`unexpected ".${name.v}" in ${src}`);
      }
      return get || propertyGetter(path);
    }
    throw new Error(`unexpected "${tok.v}" in ${src}`);
  }
  function cmp() {
    const left = primary();
    const tok = peek();
    if (tok && tok.t === 'op' && ['==', '!=', '>', '>=', '<', '<='].includes(tok.v)) {
      i++;
      const right = primary();
      return (r) => compare(left(r), tok.v, right(r));
    }
    return left;
  }
  function and() { let e = cmp(); while (take('&&')) { const a = e, b = cmp(); e = (r) => truthy(a(r)) && truthy(b(r)); } return e; }
  function or() { let e = and(); while (take('||')) { const a = e, b = and(); e = (r) => truthy(a(r)) || truthy(b(r)); } return e; }
  const expr = or();
  if (i < toks.length) throw new Error(`unexpected "${toks[i].v}" in ${src}`);
  return (row) => truthy(expr(row));
}

function propertyGetter(path) {
  const names = (path[0] === 'note' && path.length > 1 ? path.slice(1) : path).map((p) => (typeof p === 'object' ? p.key : p));
  const key = names.join('.');
  return (row) => cellValue(row[key] !== undefined ? row[key] : names.reduce((o, k) => (o == null ? o : cellValue(o)[k]), row));
}

function method(base, name, args, src) {
  switch (name) {
    case 'contains': return (r) => { const v = base(r), x = args[0](r); return Array.isArray(v) ? v.map(String).includes(String(x)) : !isEmpty(v) && String(v).toLowerCase().includes(String(x).toLowerCase()); };
    case 'startsWith': return (r) => { const v = base(r); return !isEmpty(v) && String(v).toLowerCase().startsWith(String(args[0](r)).toLowerCase()); };
    case 'isEmpty': return (r) => isEmpty(base(r));
    default: throw new Error(`unknown method .${name}() in ${src}`);
  }
}

const truthy = (v) => !(v === false || isEmpty(v) || v === 0);

function compare(a, op, b) {
  if (op === '==' || op === '!=') {
    const same = isEmpty(a) && isEmpty(b) ? true : isEmpty(a) || isEmpty(b) ? false : (numeric(a) !== null && numeric(b) !== null ? a === b : String(a) === String(b));
    return op === '==' ? same : !same;
  }
  if (isEmpty(a) || isEmpty(b)) return false;
  const x = numeric(a) !== null && numeric(b) !== null ? [a, b] : [String(a), String(b)];
  return op === '>' ? x[0] > x[1] : op === '>=' ? x[0] >= x[1] : op === '<' ? x[0] < x[1] : x[0] <= x[1];
}

/** The properties an expression reads, by name, from the same tokens the evaluator reads (so the checker and the
    page never disagree): `x`, `note.x` and `note["x"]` read x; `file.name` and `formula.f` are kept whole. */
export function expressionProperties(src) {
  const toks = tokenize(String(src));
  const out = [];
  for (let i = 0; i < toks.length; i++) {
    const tok = toks[i];
    if (tok.t !== 'id' || ['true', 'false', 'null', 'this'].includes(tok.v)) continue;
    const prev = toks[i - 1];
    if (prev && prev.t === 'op' && prev.v === '.') continue;
    const path = [tok.v];
    let j = i + 1;
    while (j < toks.length) {
      if (toks[j].v === '.' && toks[j + 1] && toks[j + 1].t === 'id' && !(toks[j + 2] && toks[j + 2].v === '(')) { path.push(toks[j + 1].v); j += 2; }
      else if (toks[j].v === '[' && toks[j + 1] && toks[j + 1].t === 'str' && toks[j + 2] && toks[j + 2].v === ']') { path.push(toks[j + 1].v); j += 3; }
      else break;
    }
    if (toks[j] && toks[j].v === '(' && path.length === 1) continue; // a function call: if(...), reads no property by name
    if (path[0] === 'file' || path[0] === 'formula') out.push(path.slice(0, 2).join('.'));
    else out.push(path[0] === 'note' && path.length > 1 ? path[1] : path[0]);
    i = j - 1;
  }
  return out;
}

// ---------------------------------------------------------------- the one formula data-ui runs (CONTRACT §36, PEP 0021)
// Zach, 2026-10-31: "The roll up itsself is also then just like a formula.. almost like FIRST Value(of cells, x, y, ...)". SQL calls it
// COALESCE. Bases has no such function, and a name of ours would be an error in Obsidian, so the file writes it with Bases' own list
// functions. WHY two spellings (real Obsidian, 2026-10-31): `!value.isEmpty()` is the short one and fails on a boolean ("Cannot find
// function "isEmpty" on type Boolean"); guarding it with isType runs on every type. WHY a reader of this one shape and not an
// evaluator: formulas run for display columns only (the Survey's §16, decision 1), and this lane needs nothing else. The tokens are the
// filters' own, so a name reads here as it reads there.
const COALESCE_TESTS = ['!value.isEmpty()', 'value.isType("boolean")||!value.isEmpty()'];
const COALESCE_TAIL = '.filter(value.isType("boolean") || !value.isEmpty())[0]';
// names an expression keeps for itself: a property called one of these is written note["…"]
const WORDS = new Set(['true', 'false', 'null', 'this', 'note', 'file', 'formula', 'value', 'index']);

/** The property ids of a formula that is `[a, b].filter(…)[0]`, in order; null for any other text, never a throw. */
export function parseCoalesce(text) {
  if (typeof text !== 'string') return null;
  let toks;
  try { toks = tokenize(text); } catch { return null; }
  let i = 0;
  const is = (v) => { const tok = toks[i]; return tok && tok.t !== 'str' && tok.v === v ? (i++, true) : false; };
  if (!is('[')) return null;
  const ids = [];
  do {
    const tok = toks[i++];
    if (!tok || tok.t !== 'id') return null;
    if (tok.v === 'note') {
      if (is('.')) { const name = toks[i++]; if (!name || name.t !== 'id') return null; ids.push(name.v); continue; }
      if (!is('[')) return null;
      const name = toks[i++];
      if (!name || name.t !== 'str' || !is(']')) return null;
      ids.push(name.v);
      continue;
    }
    if (WORDS.has(tok.v) && tok.v !== 'value' && tok.v !== 'index') return null;
    ids.push(tok.v);
  } while (is(','));
  if (!is(']') || !is('.') || !is('filter') || !is('(')) return null;
  let depth = 1, end = i;
  for (; end < toks.length && depth; end++) if (toks[end].t === 'op') depth += toks[end].v === '(' ? 1 : toks[end].v === ')' ? -1 : 0;
  if (depth) return null;
  const test = toks.slice(i, end - 1).map((tok) => (tok.t === 'str' ? JSON.stringify(tok.v) : tok.v)).join('');
  if (!COALESCE_TESTS.includes(test)) return null;
  i = end;
  return is('[') && is(0) && is(']') && i === toks.length ? ids : null;
}

/** A list back into a formula's text, bare where Bases reads a bare name; `like`: a formula whose spelling to keep (a drag rewrites
    the list inside it, so precedence stays visible text). */
export function coalesceText(ids, like = null) {
  const name = (id) => (/^[A-Za-z_]\w*$/.test(id) && !WORDS.has(id) ? id : `note[${JSON.stringify(id)}]`);
  const tail = like && parseCoalesce(like) ? like.slice(like.lastIndexOf(']', like.lastIndexOf('filter')) + 1) : COALESCE_TAIL;
  return `[${ids.map(name).join(', ')}]${tail}`;
}

/** A Bases `filters` value (string or and/or/not tree) as (row) => boolean; null when there is none. */
export function compileFilters(filters) {
  if (filters == null || filters === '') return null;
  if (typeof filters === 'string') return compileExpression(filters);
  const [kind] = Object.keys(filters);
  const parts = (filters[kind] || []).map(compileFilters).filter(Boolean);
  if (kind === 'and') return (r) => parts.every((p) => p(r));
  if (kind === 'or') return (r) => parts.some((p) => p(r));
  if (kind === 'not') return (r) => !parts.some((p) => p(r));
  throw new Error(`filters: expected and / or / not, got ${kind}`);
}

/** The flat list of expression strings at the top of an and-filter (what the Filter menu edits). */
export function filterList(filters) {
  if (filters == null || filters === '') return [];
  if (typeof filters === 'string') return [filters];
  if (filters.and) return filters.and.flatMap((f) => (typeof f === 'string' ? [f] : [f]));
  return [filters];
}

// ---------------------------------------------------------------- pivot: a transform before the table.
// WHY a transform: a pivot is "group rows, split columns, summarise a value"; once its cells are computed the result is
// an ordinary table, so the same group-by, sort, fold, column menu and drill-down serve both (one component).

export const PIVOT_PREFIX = '@';
// WHY cached: as rowmodel.js' TEXT_ORDER; localeCompare(…, undefined, {numeric: true}) builds a collator per call
const PATH_ORDER = new Intl.Collator(undefined, { numeric: true });

/** rows -> {rows, columns}: one output row per distinct combination of the view's row properties (its group levels
    and its `order` properties that are not pivot cells), one column per distinct splitBy combination. A cell is
    {v: summary, values: [...], records: [...]}, so the drill-down can list the records behind it. */
export function pivot(rows, view, schema) {
  const split = view.splitBy || [];
  const value = view.value || { property: null, summary: 'Count' };
  const levels = [view.groupBy, view.subGroupBy].filter(Boolean).map((g) => g.property);
  const keep = [...new Set([...levels, ...(view.order || []).filter((p) => !p.startsWith(PIVOT_PREFIX) && schema[p])])];
  // a time level (`by:`) makes one pivot row per bucket, which holds the bucket's key in place of a record's date
  const grains = new Map([view.groupBy, view.subGroupBy].filter(timeGrain).map((g) => [g.property, g.by]));
  // and a binned level (`bins:`, CONTRACT §20) one per bucket: the model's column carries the level's buckets
  const binned = new Map([view.groupBy, view.subGroupBy].filter((g) => binsOf(g) && !grains.has(g.property) && schema[g.property] && Array.isArray(schema[g.property].bins)).map((g) => [g.property, schema[g.property].bins]));
  const at = (r, p) => (grains.has(p) ? timeBucket(r[p], grains.get(p)) : binned.has(p) ? binKey(r[p], binned.get(p)) : cellValue(r[p]) ?? null);
  // carried, not keyed: a property every record of a row shares (a model's page URL) rides along without splitting rows
  const carry = (view._carry || []).filter((p) => schema[p] && !keep.includes(p));
  const colKeys = new Map();
  const out = new Map();
  for (const r of rows) {
    const rowKey = JSON.stringify(keep.map((p) => at(r, p)));
    let o = out.get(rowKey);
    if (!o) {
      o = { _records: [] };
      for (const p of keep) o[p] = grains.has(p) || binned.has(p) ? at(r, p) : r[p];
      for (const p of carry) o[p] = r[p];
      o._id = 'p' + out.size;
      out.set(rowKey, o);
    }
    for (const p of carry) if (o[p] !== undefined && JSON.stringify(cellValue(o[p])) !== JSON.stringify(cellValue(r[p]))) o[p] = null;
    // WHY: a record with no split value (a model never run) keeps its row, which then reads "—" in every column
    if (split.length && split.every((p) => isEmpty(cellValue(r[p])))) continue;
    o._records.push(r);
    const path = split.map((p) => { const v = cellValue(r[p]); return isEmpty(v) ? '—' : String(v); });
    const id = PIVOT_PREFIX + (path.length ? path.join(' / ') : (value.summary || 'Count'));
    if (!colKeys.has(id)) colKeys.set(id, { id, path, order: split.map((p) => r[p + '_order'] ?? r[p + '.order'] ?? null) });
    (o[id] = o[id] || { records: [] }).records.push(r);
  }
  const columns = [...colKeys.values()].sort((a, b) => {
    for (let k = 0; k < split.length; k++) {
      const x = a.order[k], y = b.order[k];
      if (x !== y) return x !== null && y !== null ? x - y : PATH_ORDER.compare(String(a.path[k]), String(b.path[k]));
      if (a.path[k] !== b.path[k]) return PATH_ORDER.compare(String(a.path[k]), String(b.path[k]));
    }
    return 0;
  });
  for (const o of out.values()) {
    for (const c of columns) {
      const cell = o[c.id];
      if (!cell) { o[c.id] = null; continue; }
      cell.values = value.property ? cell.records.map((r) => cellValue(r[value.property])).filter((v) => numeric(v) !== null) : [];
      cell.v = value.property ? summarize(cell.records.map((r) => r[value.property]), summaryName(value.summary) || 'Median') : cell.records.length;
    }
  }
  return { rows: [...out.values()], columns };
}

// ---------------------------------------------------------------- roll-up: dimensionality reduction (CONTRACT §16)
// WHY a transform before sort and group, like the pivot: rolling up is "group by the dimensions you keep, aggregate
// the rest" (OLAP roll-up; Excel / Sheets pivot "summarize by"; Tableau's Aggregate Measures). Once its rows are made,
// the same sort, group, fold, displays and drill-down serve them. Each rolled row keeps its records (`_records`), so a
// click drills back down to the rows behind it.

/** The dimensions a roll-up keeps: `rollup.keep`, plus the view's group levels (a group can only use a kept
    dimension) and, in a pivot, its splitBy (the columns are a dimension too). */
export function rollupKeep(view, props) {
  const r = view.rollup || {};
  const levels = [view.groupBy, view.subGroupBy].filter(Boolean).map((g) => g.property);
  const split = view.type === 'pivot' ? view.splitBy || [] : [];
  return [...new Set([...(r.keep || []), ...levels, ...split])].filter((p) => props[p]);
}

/** The dimensions a roll-up menu offers: `rollup.dims`, else every visible text or list property. */
export function rollupDims(view, props) {
  const r = view.rollup || {};
  if (Array.isArray(r.dims) && r.dims.length) return r.dims.filter((p) => props[p]);
  return Object.values(props).filter((p) => !p.hidden && !p.pivot && (p.type === 'text' || p.type === 'list' || p.type === 'boolean')).map((p) => p.id);
}

/** The offered dimensions a roll-up really aggregates: not kept, and with more than one value inside some rolled-up
    row (a model's family is constant per model, so keeping the model does not roll it away). */
export function rolledAway(rows, view, props) {
  const keep = rollupKeep(view, props);
  const dims = rollupDims(view, props).filter((d) => !keep.includes(d));
  const seen = new Map();
  for (const r of rows) {
    const key = JSON.stringify(keep.map((p) => cellValue(r[p]) ?? null));
    if (!seen.has(key)) seen.set(key, Object.fromEntries(dims.map((d) => [d, new Set()])));
    for (const d of dims) seen.get(key)[d].add(JSON.stringify(cellValue(r[d]) ?? null));
  }
  return dims.filter((d) => [...seen.values()].some((g) => g[d].size > 1));
}

/**
 * rows -> one row per distinct combination of the kept dimensions (rollupKeep). Every other property:
 *   number   a rich cell {value: <agg>, n, low: min, high: max, values, basis: derived, note}; agg is
 *            `rollup.agg[property]` (a summary name or alias), else Median
 *   list     the values of every row, in order (a sparkline's or a distribution's points), duplicates kept
 *   other    the value when every row agrees, else {value: null, why: "rolled up: N values (…)", rolled: N}
 * A rolled row has `id` '@r<n>', `_rollup: true` and `_records` (the rows behind it).
 */
export function rollup(rows, view, props) {
  if (!view.rollup) return rows;
  const keep = rollupKeep(view, props);
  const agg = view.rollup.agg || {};
  const groups = new Map();
  for (const r of rows) {
    const key = JSON.stringify(keep.map((p) => cellValue(r[p]) ?? null));
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }
  const out = [];
  for (const recs of groups.values()) {
    const o = { id: '@r' + out.length, _id: '@r' + out.length, _rollup: true, _records: recs };
    for (const [id, p] of Object.entries(props)) {
      if (keep.includes(id)) { o[id] = recs[0][id]; continue; }
      const vals = recs.map((x) => x[id]);
      if (p.type === 'number') {
        const name = summaryName(agg[id]) || 'Median';
        const nums = vals.map(cellValue).filter((v) => numeric(v) !== null).sort((a, b) => a - b);
        if (!nums.length) { o[id] = { value: null, why: `no value in the ${recs.length} rows rolled up` }; continue; }
        const value = name === 'Range' ? nums[nums.length - 1] - nums[0] : summarize(vals, name);
        o[id] = { value, n: nums.length, low: nums[0], high: nums[nums.length - 1], values: vals.map(cellValue).filter((v) => numeric(v) !== null),
          basis: 'derived', note: `${name} of ${nums.length} row${nums.length === 1 ? '' : 's'} (rolled up)`, summary: name };
        continue;
      }
      if (p.type === 'list') { o[id] = vals.flatMap((v) => (Array.isArray(cellValue(v)) ? cellValue(v) : isEmpty(cellValue(v)) ? [] : [cellValue(v)])); continue; }
      const distinct = [...new Set(vals.map((v) => JSON.stringify(cellValue(v) ?? null)))].map((k) => JSON.parse(k));
      if (distinct.length === 1) o[id] = recs[0][id];
      else o[id] = { value: null, rolled: distinct.length, why: `rolled up: ${distinct.length} values (${distinct.slice(0, 6).map((v) => (v === null ? '—' : String(v))).join(', ')}${distinct.length > 6 ? ', …' : ''})` };
    }
    out.push(o);
  }
  return out;
}

// ---------------------------------------------------------------- serialising a view back to .base YAML

const YAML_PLAIN = /^[A-Za-z_][\w .·/()-]*$/;
function yamlScalar(v) {
  if (v === null || v === undefined) return 'null';
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  const s = String(v);
  return YAML_PLAIN.test(s) && !/^(true|false|null|yes|no)$/i.test(s) && s.trim() === s ? s : JSON.stringify(s);
}
function yamlFlow(v) {
  if (Array.isArray(v)) return '[' + v.map(yamlFlow).join(', ') + ']';
  if (v && typeof v === 'object') return '{ ' + Object.entries(v).map(([k, x]) => `${yamlScalar(k)}: ${yamlFlow(x)}`).join(', ') + ' }';
  return yamlScalar(v);
}

const KEY_ORDER = ['type', 'name', 'filters', 'order', 'sort', 'groupBy', 'subGroupBy', 'groupOrder', 'splitBy', 'value', 'rollup', 'summaries', 'display', 'columnGroups', 'units', 'fold', 'columnSize', 'limit'];

/** One view as the `views:` entry of a .base file (two-space indent, flow style for small maps and lists). */
export function toBaseYaml(view) {
  const lines = [];
  const keys = [...KEY_ORDER.filter((k) => k in view), ...Object.keys(view).filter((k) => !KEY_ORDER.includes(k) && !k.startsWith('_'))];
  keys.forEach((k, n) => {
    const v = view[k];
    if (v === undefined || (Array.isArray(v) && !v.length) || (v && typeof v === 'object' && !Array.isArray(v) && !Object.keys(v).length)) return;
    const lead = n === 0 ? '  - ' : '    ';
    if (k === 'filters' && v && typeof v === 'object' && Array.isArray(v.and)) {
      lines.push(`${lead}filters:`, '      and:', ...v.and.map((f) => `        - ${yamlFlow(f)}`));
    } else if (k === 'sort' || k === 'order') {
      lines.push(`${lead}${k}:`, ...v.map((x) => `      - ${yamlFlow(x)}`));
    } else lines.push(`${lead}${k}: ${yamlFlow(v)}`);
  });
  return 'views:\n' + lines.join('\n') + '\n';
}

/** A canonical, comparable form of a view (to tell whether the user changed the preset). */
export function viewKey(view) {
  const clean = {};
  for (const k of Object.keys(view).sort()) if (!k.startsWith('_') && view[k] !== undefined) clean[k] = view[k];
  return JSON.stringify(clean);
}

export function encodeView(view) {
  const json = viewKey(view);
  return btoa(String.fromCharCode(...new TextEncoder().encode(json))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function decodeView(text) {
  const b64 = text.replace(/-/g, '+').replace(/_/g, '/');
  const bytes = Uint8Array.from(atob(b64 + '==='.slice((b64.length + 3) % 4)), (c) => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}

// ---------------------------------------------------------------- time groups: `groupBy: {property, by, gaps}`
// docs/CONTRACT.md amendment 2026-10-26 (time groups and peek trail). A group level with `by:` groups a date property
// by its day, ISO week, month, quarter or year; a bucket's key is plain text that sorts in time order within a grain:
//   day '2026-10-20'   week '2026-10-19' (its Monday)   month '2026-10'   quarter '2026-Q4'   year '2026'
// WHY the written date, never a converted one: a date-only value has no time zone, and a run started at 23:30 local
// time belongs to that evening's day for the person who logged it; converting to UTC or the viewer's zone moves it.
// WHY ISO weeks (Monday first): Zach's spec (2026-10-26), and what Vibe Tracks' runs and every European calendar use.

export const TIME_GRAINS = ['day', 'week', 'month', 'quarter', 'year'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const DAY_MS = 86400000;
const pad = (n, w = 2) => String(n).padStart(w, '0');
const isoDay = (t) => { const d = new Date(t); return `${pad(d.getUTCFullYear(), 4)}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`; };

/** The calendar day a value names, as a UTC midnight timestamp, or null. ISO text is read as written: '2026-09-30',
    '2026-09-30T23:30:00-07:00' and '2026-09-30T23:30Z' are all 30 Sep; a bucket's own key ('2026-10', '2026-Q4',
    '2026') reads as its first day, so a key buckets to itself. Anything else (a number, a list) names no day: dates
    are ISO text (docs/CONTRACT.md §3). */
function dayOf(v) {
  v = cellValue(v);
  if (typeof v !== 'string') return null;
  const m = /^(\d{4})(?:-(?:(\d{2})(?:-(\d{2}))?|Q([1-4])))?(?=$|[T ]\d)/.exec(v.trim());
  if (!m) return null;
  const y = Number(m[1]);
  const month = m[4] ? (Number(m[4]) - 1) * 3 + 1 : m[2] ? Number(m[2]) : 1;
  const day = m[3] ? Number(m[3]) : 1;
  const t = Date.UTC(y, month - 1, day);
  const d = new Date(t);
  // WHY check it back: Date.UTC rolls 2026-02-30 over into March; a date that does not exist has no bucket
  if (month < 1 || month > 12 || d.getUTCMonth() !== month - 1 || d.getUTCDate() !== day) return null;
  return t;
}

/** A value's bucket key at a grain (`by`), or null when it names no date. */
export function timeBucket(v, by) {
  const t = dayOf(v);
  if (t === null) return null;
  const d = new Date(t);
  const y = pad(d.getUTCFullYear(), 4), m = d.getUTCMonth();
  switch (by) {
    case 'day': return isoDay(t);
    case 'week': return isoDay(t - ((d.getUTCDay() + 6) % 7) * DAY_MS);
    case 'month': return `${y}-${pad(m + 1)}`;
    case 'quarter': return `${y}-Q${Math.floor(m / 3) + 1}`;
    case 'year': return y;
    default: return null;
  }
}

/** The bucket after a key at its grain ('2026-12' -> '2027-01'). */
export function nextBucket(key, by) {
  const t = dayOf(key);
  if (t === null) return null;
  const d = new Date(t);
  const y = d.getUTCFullYear(), m = d.getUTCMonth();
  const next = { day: t + DAY_MS, week: t + 7 * DAY_MS, month: Date.UTC(y, m + 1, 1), quarter: Date.UTC(y, m + 3, 1), year: Date.UTC(y + 1, 0, 1) }[by];
  return next === undefined ? null : timeBucket(isoDay(next), by);
}

/** A bucket's first day as ISO date text (a chart's time axis plots it). */
export function bucketStart(key, by) {
  const t = dayOf(timeBucket(key, by));
  return t === null ? null : isoDay(t);
}

/** A bucket key in words: 'Tue 20 Oct 2026', 'Week of 19 Oct 2026', 'Oct 2026', 'Q4 2026', '2026'. Fixed English
    month names, so a label reads the same on every machine (the rest of the kit writes English too). */
export function bucketLabel(key, by) {
  const k = timeBucket(key, by);
  if (k === null) return null;
  const d = new Date(dayOf(k));
  const dmy = `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  if (by === 'day') return `${WEEKDAYS[d.getUTCDay()]} ${dmy}`;
  if (by === 'week') return `Week of ${dmy}`;
  if (by === 'month') return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  if (by === 'quarter') return `${k.slice(5)} ${k.slice(0, 4)}`;
  return k;
}

/** A group level's grain, or null: `by` must be one of TIME_GRAINS. */
export const timeGrain = (level) => (level && TIME_GRAINS.includes(level.by) ? level.by : null);

// ---------------------------------------------------------------- numeric bins: `groupBy: {property, bins, log, unit}`
// docs/CONTRACT.md §20 (the grouped gallery). The number twin of `by:`: a level with `bins:` groups a number by the
// half-open bucket [min, max) it falls in. The buckets themselves are facets.js' (bucketsFrom / autoEdges / nice, the
// rail's own `buckets` kind), resolved once per model by rowmodel.js over the whole dataset, so they hold still while
// filtering; here is only the level's test and a value's bucket.

/** A group level's bins (`[edges]`, `[{label, min, max}]` or `auto`), or null when it has none. */
export const binsOf = (level) => (level && (level.bins === 'auto' || (Array.isArray(level.bins) && level.bins.length)) ? level.bins : null);

/** The key of the bucket a value falls in (`buckets`: [{key, min?, max?, maxOpen?}], the first that holds it), or null
    when it is not a number. A bucket is [min, max): a value on an edge belongs to the upper one. */
export function binKey(v, buckets) {
  if (!Array.isArray(buckets)) return null;
  // a bucket's own key is its bucket (a pivot row holds the key in place of its records' numbers), as a time key is
  if (typeof v === 'string' && buckets.some((b) => b.key === v)) return v;
  const x = numeric(cellValue(v));
  if (x === null) return null;
  for (const b of buckets) {
    if (b.min !== undefined && b.min !== null && x < b.min) continue;
    if (b.max !== undefined && b.max !== null && (b.maxOpen === false ? x > b.max : x >= b.max)) continue;
    return b.key;
  }
  return null;
}

// ---------------------------------------------------------------- nested levels: `groupBy: {property, path: dotted}`
// WHY (Zach, Oct 31): "We should be able to support multiple nested things. For example here servo.pid_position should be
// within servo! not on the same flat level". A level with `path` reads its value as a path, to any depth: `dotted` splits text
// at each ".", any other word is its separator, and a list cell is a path as declared. PEP 0020.

/** A level's path separator, or null when it groups by the whole value. `by` and `bins` make their own buckets: no path. */
export function pathSep(level) {
  if (!level || typeof level !== 'object' || level.by || level.bins) return null;
  const p = level.path;
  if (p === undefined || p === null || p === false || p === '') return null;
  return p === true || p === 'dotted' ? '.' : String(p);
}

/** A cell's value as path segments. Only text is split: a number's point is no separator (1.5 is one group). Empty segments
    go, as a `tree: {path}`'s do. */
export function pathSegments(value, sep) {
  if (value === null || value === undefined || value === '') return [];
  if (Array.isArray(value)) return value.filter((x) => x !== null && x !== undefined && x !== '').map(String);
  return typeof value === 'string' ? value.split(sep).filter(Boolean) : [String(value)];
}

// WHY only these: they draw a nest. A board's drop writes its column's key, so a "servo" column would overwrite servo.fw;
// a nav facet, a timeline's lanes, a calendar's and a KPI's groups are whole values, and stay so (PEP 0020)
const PATH_VIEWS = new Set(['table', 'list', 'cards']);

/** The separator of a level as this view groups it: null where the view keeps whole values, or under `tree:`. */
export function viewPath(view, level) {
  return view && !view.tree && PATH_VIEWS.has(view.type || 'table') ? pathSep(level) : null;
}

// ---------------------------------------------------------------- groupings: `groupings: [...]` and `grouping: <id>`
// WHY (Zach, 2026-10-27): "This home page feels like a Shopify 'collection'. It's almost like a particular view of the
// table where we make the subheaders big and the children gallery cards." A catalogue home is read several ways (by
// material, by size, by stream); each way is one entry, and a host's own switcher only calls setView({grouping}).

/** The `groupings` entry a view's `grouping` names, or null (none named, or an id no entry has). */
export function groupingOf(view) {
  if (!view || typeof view.grouping !== 'string' || !Array.isArray(view.groupings)) return null;
  return view.groupings.find((g) => g && g.id === view.grouping) || null;
}

/** The view as the row model and every view draw it: when `grouping` names an entry, that entry's groupBy, subGroupBy
    and tiles replace the view's own (a key the entry leaves out is none: an entry is a whole grouping); an unknown id
    keeps the view's own (the checker warns). A new object; the entry is never changed. */
export function effectiveView(view) {
  const g = groupingOf(view);
  if (!g) return view;
  const out = { ...view, groupBy: g.groupBy, subGroupBy: g.subGroupBy, tiles: g.tiles };
  for (const k of ['groupBy', 'subGroupBy', 'tiles']) if (out[k] === undefined || out[k] === null || out[k] === false) delete out[k];
  return out;
}
