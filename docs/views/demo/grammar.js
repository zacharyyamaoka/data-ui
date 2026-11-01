/* Copied verbatim from robotparts lane/tables @ ab5ba92, design/tables-2026-10-25/views/src/grammar.js, so the demo filters
   with the table lane's own Bases evaluator. data-ui's core takes this file over; do not edit the copy. */
/* The view grammar: a stored view is one entry of an Obsidian Bases `.base` file's `views:` list.

   Bases keys, used with their Bases meaning (help.obsidian.md, "Bases syntax"):
     type        table | cards | list in Bases; this component draws `table`, and adds `pivot`
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
     splitBy     [property, ...]: pivot only; the columns are the distinct values of these, outer first
     value       {property, summary, display}: pivot only; what a pivot cell shows (summary as in `summaries`)
     display     {property: text | number | bar | dist | sparkline | badge}
     units       column | inline: units in a column / header, or written next to each value
     fold        open | closed: groups start unfolded or folded
   WHY Bases (Zach, 2026-10-25): "learn the grammar once for how to edit the views, then reuse it"; he writes .base
   files daily. Everything here is plain data, so the same view drives the table, the pivot, the URL and a saved preset. */

export const SUMMARIES = ['Average', 'Median', 'Min', 'Max', 'Sum', 'Range', 'Unique', 'Filled', 'Empty', 'Count'];
export const DISPLAYS = ['text', 'number', 'bar', 'dist', 'sparkline', 'badge'];

const isEmpty = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
const numeric = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** A summary of values ('Median' etc.), ignoring empties. Range is [min, max]; Unique is the count of distinct. */
export function summarize(values, summary) {
  const filled = values.filter((v) => !isEmpty(v));
  const nums = filled.map(numeric).filter((v) => v !== null).sort((a, b) => a - b);
  switch (summary) {
    case 'Count': return values.length;
    case 'Filled': return filled.length;
    case 'Empty': return values.length - filled.length;
    case 'Unique': return new Set(filled.map(String)).size;
    case 'Sum': return nums.length ? nums.reduce((a, b) => a + b, 0) : null;
    case 'Average': return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null;
    case 'Min': return nums.length ? nums[0] : null;
    case 'Max': return nums.length ? nums[nums.length - 1] : null;
    case 'Range': return nums.length ? [nums[0], nums[nums.length - 1]] : null;
    case 'Median': {
      if (!nums.length) return null;
      const mid = nums.length >> 1;
      return nums.length % 2 ? nums[mid] : (nums[mid - 1] + nums[mid]) / 2;
    }
    default: return filled.length === 1 ? filled[0] : null;
  }
}

// ---------------------------------------------------------------- filters: a small, documented subset of Bases'
// expression language: literals ("text", 12.5, true, false, null), properties (note.x and x are the same), the
// operators == != > >= < <= && || ! and parentheses, and the methods .contains(x) .startsWith(x) .isEmpty().

function tokenize(src) {
  const out = [];
  const re = /\s*(?:(\d+(?:\.\d+)?(?:e[+-]?\d+)?)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(==|!=|>=|<=|&&|\|\||[()!<>.,])|([A-Za-z_][\w]*))/gy;
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
    if (tok.t === 'id') {
      if (tok.v === 'true') return () => true;
      if (tok.v === 'false') return () => false;
      if (tok.v === 'null') return () => null;
      const path = [tok.v];
      let get = null;
      while (peek() && peek().v === '.') {
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
  const names = path[0] === 'note' && path.length > 1 ? path.slice(1) : path;
  const key = names.join('.');
  return (row) => (row[key] !== undefined ? row[key] : names.reduce((o, k) => (o == null ? o : o[k]), row));
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

/** rows -> {rows, columns}: one output row per distinct combination of the view's row properties (its group levels
    and its `order` properties that are not pivot cells), one column per distinct splitBy combination. A cell is
    {v: summary, values: [...], records: [...]}, so the drill-down can list the records behind it. */
export function pivot(rows, view, schema) {
  const split = view.splitBy || [];
  const value = view.value || { property: null, summary: 'Count' };
  const levels = [view.groupBy, view.subGroupBy].filter(Boolean).map((g) => g.property);
  const keep = [...new Set([...levels, ...(view.order || []).filter((p) => !p.startsWith(PIVOT_PREFIX) && schema[p])])];
  const colKeys = new Map();
  const out = new Map();
  for (const r of rows) {
    const rowKey = JSON.stringify(keep.map((p) => r[p] ?? null));
    let o = out.get(rowKey);
    if (!o) {
      o = { _records: [] };
      for (const p of keep) o[p] = r[p];
      o._id = 'p' + out.size;
      out.set(rowKey, o);
    }
    // WHY: a record with no split value (a model never run) keeps its row, which then reads "—" in every column
    if (split.length && split.every((p) => isEmpty(r[p]))) continue;
    o._records.push(r);
    const path = split.map((p) => (isEmpty(r[p]) ? '—' : String(r[p])));
    const id = PIVOT_PREFIX + (path.length ? path.join(' / ') : (value.summary || 'Count'));
    if (!colKeys.has(id)) colKeys.set(id, { id, path, order: split.map((p) => r[p + '_order'] ?? r[p + '.order'] ?? null) });
    (o[id] = o[id] || { records: [] }).records.push(r);
  }
  const columns = [...colKeys.values()].sort((a, b) => {
    for (let k = 0; k < split.length; k++) {
      const x = a.order[k], y = b.order[k];
      if (x !== y) return x !== null && y !== null ? x - y : String(a.path[k]).localeCompare(String(b.path[k]), undefined, { numeric: true });
      if (a.path[k] !== b.path[k]) return String(a.path[k]).localeCompare(String(b.path[k]), undefined, { numeric: true });
    }
    return 0;
  });
  for (const o of out.values()) {
    for (const c of columns) {
      const cell = o[c.id];
      if (!cell) { o[c.id] = null; continue; }
      cell.values = value.property ? cell.records.map((r) => r[value.property]).filter((v) => numeric(v) !== null) : [];
      cell.v = value.property ? summarize(cell.records.map((r) => r[value.property]), value.summary || 'Median') : cell.records.length;
    }
  }
  return { rows: [...out.values()], columns };
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

const KEY_ORDER = ['type', 'name', 'filters', 'order', 'sort', 'groupBy', 'subGroupBy', 'splitBy', 'value', 'summaries', 'display', 'units', 'fold', 'columnSize', 'limit'];

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
