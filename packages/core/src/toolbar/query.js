/* The query bar (docs/CONTRACT.md §15): Shopify's query builder over the one filter tree. OWNED BY LANE B
   (query + selection). The element (data-views.js, lane A) calls exactly these:

   parseQuery(text, columns)            -> {clauses: [Bases expression text], words: 'free text', errors: [{text, reason, start, end}]}
   formatQuery(filters, words, columns) -> canonical text: each clause of the all-views filter in token form, then the words
   clauseToken(expr, columns)           -> {text: 'brand:Steadywin', label: 'Brand is Steadywin'} (a clause with no token
                                           form comes back as {text: '(<expr>)', label: <expr>})
   suggest(text, caret, ctx)            -> {items: [{kind: 'property'|'operator'|'value'|'hint', label, insert, detail?, count?}],
                                           from, to}  (replace text[from, to) with an item's insert); ctx = {columns, rows, filters, order?}
   mountQuery(el, slot, {tokens})       -> {update(), focus(), destroy()}: draws the box into `slot`; reads el.filters,
                                           el.query, el.model; commits a typed clause by setting el.filters (adding one
                                           {and:} item), words through el.search(words); `tokens` draws the clauses as
                                           tokens inside the box (filters="query-tokens").

   The grammar (each clause is the Bases expression the rail, the Filter menu and an agent writing the .base file write;
   facets.js's normal form, so a typed brand:Steadywin and a rail tick are the same tree and the same URL):
     prop:v             prop == "v"  (a list property: prop.contains("v"); a number property: prop == 4)
     prop:a,b           {or: [prop == "a", prop == "b"]}
     -prop:v / -prop:a,b {not: [prop == "v", ...]}  (the rail's exclude; §15 note 2026-10-26)
     prop:>10 >= < <=   prop > 10
     prop:10..20        prop >= 10, prop <= 20  (`>a` / `..<b` exclusive, as the URL writes them; either end may be empty)
     has:prop / has:a,b !prop.isEmpty() / {or: [!a.isEmpty(), !b.isEmpty()]}
     prop~:text         prop.contains("text")       prop^:text   prop.startsWith("text")
     (expr) or `expr`   any Bases expression, verbatim; -(expr) is {not: [expr]}
     c1 OR c2           {or: [c1, c2]} (each one expression)
   A value with spaces is quoted (brand:"T-Motor AK"); a property is its id or its label, case-insensitive. Everything
   else is words: the free-text search. WHY tokens and not a second filter model (Zach, 2026-10-26): "that way it's all
   internally consistent… they are just different ways you can set things", and an agent can write the same text. */

import { compileExpression, compileFilters, expressionProperties, cellValue } from '../grammar.js';
import { parseClause, ref } from '../facets.js';
import { esc, fmtNum, valueText } from '../format.js';

const NUM = /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/;
const BARE_VALUE = /^[^\s,"'`()<>=]+$/;
const BARE_NAME = /^[A-Za-z0-9_][\w.-]*$/;
const CLAUSE = /^(-?)(?:"((?:[^"\\]|\\.)*)"|([^\s:"`()]+?))([~^]?):([\s\S]*)$/;
const ICONS = { text: 'Aa', number: '#', list: '≡', boolean: '◩', date: '◷' };
const isEmpty = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const lit = (v) => (typeof v === 'string' ? JSON.stringify(v) : String(v));

/** How a stored value reads: its property's label for it (`labels: {steadywin: "Steadywin"}`), as the rail draws it
    (format.js valueText). The query's text and its expressions keep the stored value; only what is shown is the label. */
export function valueLabel(columns, property, value) {
  const col = columns && columns[property];
  const text = valueText(value, col);
  return text === '' || text === undefined || text === null ? String(value ?? '') : String(text);
}

/** The top-level clauses of an all-views filter: a lone expression, {and: [...]}, or one other tree. */
export function clauseList(filters) {
  if (filters === undefined || filters === null || filters === '') return [];
  if (typeof filters === 'string') return [filters];
  if (Object.keys(filters).length === 1 && Array.isArray(filters.and)) return filters.and;
  return [filters];
}

// ------------------------------------------------------------------ reading the text

function closeQuote(text, i) {
  for (let j = i + 1; j < text.length; j++) {
    if (text[j] === '\\') j++;
    else if (text[j] === '"') return j;
  }
  return -1;
}

/** The index of the ")" that closes text[i] === "(", skipping quoted strings; -1 when it never closes. */
function matchParen(text, i) {
  let depth = 0;
  for (let j = i; j < text.length; j++) {
    const c = text[j];
    if (c === '"' || c === "'") {
      for (j++; j < text.length && text[j] !== c; j++) if (text[j] === '\\') j++;
      if (j >= text.length) return -1;
    } else if (c === '(') depth++;
    else if (c === ')' && --depth === 0) return j;
  }
  return -1;
}

/** The text cut at spaces, except inside a quoted value, a parenthesis (to its match) or backticks. */
function segments(text) {
  const out = [];
  const n = text.length;
  let i = 0;
  while (i < n) {
    while (i < n && /\s/.test(text[i])) i++;
    if (i >= n) break;
    const start = i;
    let open = null;
    const j = text[i] === '-' && (text[i + 1] === '(' || text[i + 1] === '`') ? i + 1 : i;
    if (text[j] === '(') { const e = matchParen(text, j); if (e < 0) { open = 'parenthesis'; i = n; } else i = e + 1; }
    else if (text[j] === '`') { const e = text.indexOf('`', j + 1); if (e < 0) { open = 'backtick'; i = n; } else i = e + 1; }
    else {
      while (i < n && !/\s/.test(text[i])) {
        if (text[i] === '"') { const e = closeQuote(text, i); if (e < 0) { open = 'quote'; i = n; break; } i = e + 1; } else i++;
      }
    }
    out.push({ start, end: i, text: text.slice(start, i), open });
  }
  return out;
}

function unquote(s) {
  if (s.length >= 2 && s[0] === '"' && s[s.length - 1] === '"') {
    try { return JSON.parse(s); } catch { return s.slice(1, -1).replace(/\\(.)/g, '$1'); }
  }
  return s;
}

/** "a,b,\"c,d\"" -> ['a', 'b', 'c,d'] (null when a quote is open). */
function splitList(s) {
  const out = [];
  let cur = '', q = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === '\\' && q) { cur += c + (s[i + 1] || ''); i++; continue; }
    if (c === '"') q = !q;
    if (c === ',' && !q) { out.push(cur); cur = ''; continue; }
    cur += c;
  }
  if (q) return null;
  out.push(cur);
  return out;
}

/** A property by id, then id or label without case. */
function resolve(name, columns) {
  if (columns[name]) return columns[name];
  const low = String(name).toLowerCase();
  const all = Object.values(columns);
  return all.find((c) => c.id.toLowerCase() === low) || all.find((c) => String(c.label || '').toLowerCase() === low) || null;
}

function closest(name, columns) {
  const low = String(name).toLowerCase();
  const hit = Object.values(columns).find((c) => c.id.toLowerCase().startsWith(low.slice(0, 3)) || String(c.label || '').toLowerCase().startsWith(low.slice(0, 3)));
  return hit ? ` (did you mean ${propName(hit.id)}?)` : '';
}

/** A typed value as the literal its property compares with: numbers on a number property, true / false on a boolean. */
function literalOf(raw, col) {
  const quoted = raw[0] === '"';
  const v = unquote(raw);
  if (v === '') return { error: `${col.label}: needs a value` };
  // a labelled property: the stored value, typed as itself or as its label (any case), e.g. Steadywin -> steadywin
  if (col.labels && typeof col.labels === 'object') {
    const keys = Object.keys(col.labels);
    const low = v.toLowerCase();
    const key = keys.includes(v) ? v : keys.find((k) => String(col.labels[k]).toLowerCase() === low) ?? keys.find((k) => k.toLowerCase() === low);
    if (key !== undefined) return { value: col.type === 'number' && NUM.test(key) ? Number(key) : col.type === 'boolean' && /^(true|false)$/.test(key) ? key === 'true' : key };
  }
  if (quoted) return { value: v };
  if (col.type === 'number') return NUM.test(v) ? { value: Number(v) } : { error: `${col.label} needs a number, not "${v}"` };
  if (col.type === 'boolean') return /^(true|false)$/i.test(v) ? { value: v.toLowerCase() === 'true' } : { error: `${col.label} is true or false, not "${v}"` };
  return { value: v };
}

const err = (reason) => ({ kind: 'error', reason });

/** One clause-shaped segment -> {kind: 'clause', clauses} | {kind: 'error', reason}. */
function readClause(seg, columns) {
  const t = seg.text;
  const neg = t[0] === '-' && t.length > 1;
  const body = neg ? t.slice(1) : t;
  if (body[0] === '(' || body[0] === '`') {
    if (seg.open) return err(`the ${seg.open} is not closed`);
    const inner = body.slice(1, -1).trim();
    if (!inner) return err('an empty expression');
    try { compileExpression(inner); } catch (e) { return err(e.message); }
    const missing = expressionProperties(inner).filter((p) => !p.startsWith('file.') && !p.startsWith('formula.') && !columns[p]);
    if (missing.length) return err(`no property "${missing[0]}"${closest(missing[0], columns)}`);
    return { kind: 'clause', clauses: [neg ? { not: [inner] } : inner] };
  }
  if (seg.open) return err('the quote is not closed');
  const m = CLAUSE.exec(t);
  const quotedName = m[2] !== undefined;
  const name = quotedName ? unquote(`"${m[2]}"`) : m[3];
  const mark = m[4];
  const rest = m[5];
  if (!quotedName && !mark && name.toLowerCase() === 'has' && !columns[name]) {
    const names = splitList(rest);
    if (!rest || !names || names.some((x) => !x)) return err('has: needs a property');
    const exprs = [];
    for (const x of names) {
      const col = resolve(unquote(x), columns);
      if (!col) return err(`no property "${unquote(x)}"${closest(unquote(x), columns)}`);
      exprs.push(`!${ref(col.id)}.isEmpty()`);
    }
    return { kind: 'clause', clauses: [neg ? { not: exprs } : exprs.length === 1 ? exprs[0] : { or: exprs }] };
  }
  const col = resolve(name, columns);
  if (!col) return err(`no property "${name}"${closest(name, columns)}`);
  const p = ref(col.id);
  if (rest === '') return err(`${col.label}: needs a value`);
  const wrap = (exprs) => ({ kind: 'clause', clauses: neg ? [{ not: exprs }] : exprs });
  if (mark) {
    if (splitList(rest) === null) return err('the quote is not closed');
    const v = unquote(rest);
    if (!v) return err(`${col.label}: needs some text`);
    return wrap([`${p}.${mark === '^' ? 'startsWith' : 'contains'}(${JSON.stringify(v)})`]);
  }
  const bounded = col.type === 'number' || col.type === 'date';
  const range = bounded && rest[0] !== '"' ? /^(>?)([\s\S]*?)\.\.(<?)([\s\S]*)$/.exec(rest) : null;
  if (range) {
    if (neg) return err('a range cannot be negated; write -(…) around the expression');
    const lo = range[2], hi = range[4];
    if (!lo && !hi) return err(`${col.label}: a range needs a low or a high end`);
    const a = lo ? literalOf(lo, col) : null, b = hi ? literalOf(hi, col) : null;
    if ((a && a.error) || (b && b.error)) return err((a && a.error) || b.error);
    if (a && b && a.value > b.value) return err(`${col.label}: the low end is above the high end`);
    const out = [];
    if (a) out.push(`${p} ${range[1] ? '>' : '>='} ${lit(a.value)}`);
    if (b) out.push(`${p} ${range[3] ? '<' : '<='} ${lit(b.value)}`);
    return { kind: 'clause', clauses: out };
  }
  const op = /^(>=|<=|>|<)([\s\S]*)$/.exec(rest);
  if (op) {
    if (!op[2]) return err(`${col.label}: needs a value after ${op[1]}`);
    const v = literalOf(op[2], col);
    if (v.error) return err(v.error);
    return wrap([`${p} ${op[1]} ${lit(v.value)}`]);
  }
  const items = splitList(rest);
  if (items === null) return err('the quote is not closed');
  const exprs = [];
  for (const x of items) {
    const v = literalOf(x, col);
    if (v.error) return err(v.error);
    exprs.push(col.type === 'list' ? `${p}.contains(${lit(v.value)})` : `${p} == ${lit(v.value)}`);
  }
  if (neg) return { kind: 'clause', clauses: [{ not: exprs }] };
  return { kind: 'clause', clauses: [exprs.length === 1 ? exprs[0] : { or: exprs }] };
}

function classify(seg, columns) {
  const t = seg.text;
  if (t === 'OR') return { kind: 'or' };
  const body = t[0] === '-' ? t.slice(1) : t;
  if (body[0] === '(' || body[0] === '`' || (CLAUSE.test(t) && !(seg.open === 'quote' && !/:/.test(t.split('"')[0])))) return readClause(seg, columns);
  if (seg.open === 'quote' && /^-?[^\s"]*:/.test(t)) return err('the quote is not closed');
  return { kind: 'word' };
}

const oneOf = (clauses) => (clauses.length !== 1 ? null : typeof clauses[0] === 'string' ? [clauses[0]] : Object.keys(clauses[0]).length === 1 && Array.isArray(clauses[0].or) ? clauses[0].or : null);

/** Every segment of the text, read: {start, end, text, kind: clause | word | or | error, clauses?, reason?}, and the
    parse (clauses, words, errors). The UI reads the segments to commit and underline; parseQuery returns the parse. */
export function scanQuery(text, columns = {}) {
  const items = segments(String(text || '')).map((s) => ({ ...s, ...classify(s, columns) }));
  const out = [];
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    const prev = out[out.length - 1], next = items[i + 1];
    // c1 OR c2: one {or:} of single expressions; otherwise OR is a word
    if (it.kind === 'or' && prev && prev.kind === 'clause' && next && next.kind === 'clause' && oneOf(prev.clauses) && oneOf(next.clauses)) {
      out[out.length - 1] = { ...prev, end: next.end, text: String(text).slice(prev.start, next.end), clauses: [{ or: [...oneOf(prev.clauses), ...oneOf(next.clauses)] }] };
      i++;
      continue;
    }
    out.push(it.kind === 'or' ? { ...it, kind: 'word' } : it);
  }
  return {
    items: out,
    clauses: out.filter((s) => s.kind === 'clause').flatMap((s) => s.clauses),
    words: out.filter((s) => s.kind === 'word').map((s) => s.text).join(' '),
    errors: out.filter((s) => s.kind === 'error').map(({ text: t, reason, start, end }) => ({ text: t, reason, start, end })),
  };
}

export function parseQuery(text, columns = {}) {
  const { clauses, words, errors } = scanQuery(text, columns);
  return { clauses, words, errors };
}

// ------------------------------------------------------------------ writing the text

function propName(id) { return BARE_NAME.test(id) && id.toLowerCase() !== 'has' ? id : JSON.stringify(id); }

function tokenValue(v, col) {
  if (typeof v !== 'string') return String(v);
  // WHY quote a number-looking string on a number property: it stays the string the expression compares
  const typed = col && (col.type === 'number' || col.type === 'boolean');
  return BARE_VALUE.test(v) && !v.includes('..') && !typed ? v : JSON.stringify(v);
}

const SYM = { '>': '>', '>=': '≥', '<': '<', '<=': '≤' };

/** A clause as the token that parses back to exactly it, and its label; else a raw expression. */
export function clauseToken(expr, columns = {}) {
  const ok = (text) => { const q = scanQuery(text, columns); return !q.errors.length && !q.words && same(q.clauses, [expr]); };
  const label = (p) => (columns[p] ? columns[p].label : p);
  const tries = [];
  if (typeof expr === 'string') {
    const c = parseClause(expr, { wide: true });
    if (c) {
      const col = columns[c.property], pn = propName(c.property), L = label(c.property), v = tokenValue(c.value, col);
      const shown = valueLabel(columns, c.property, c.value);
      if (c.kind === 'eq') tries.push([`${pn}:${v}`, `${L} is ${shown}`]);
      if (c.kind === 'contains') tries.push([`${pn}:${v}`, `${L} has ${shown}`], [`${pn}~:${v}`, `${L} contains ${c.value}`]);
      if (c.kind === 'starts') tries.push([`${pn}^:${v}`, `${L} starts with ${c.value}`]);
      if (c.kind === 'has') tries.push([`has:${pn}`, `Has ${L}`]);
      if (c.kind === 'min' || c.kind === 'max') {
        const op = c.kind === 'min' ? (c.open ? '>' : '>=') : (c.open ? '<' : '<=');
        tries.push([`${pn}:${op}${v}`, `${L} ${SYM[op]} ${c.value}`]);
      }
    }
  } else if (expr && typeof expr === 'object' && Object.keys(expr).length === 1) {
    const [kind] = Object.keys(expr);
    const list = expr[kind];
    const cs = Array.isArray(list) ? list.map((x) => parseClause(x, { wide: true })) : [];
    const one = cs.length && cs.every((c) => c && c.property === cs[0].property && c.kind === cs[0].kind) ? cs[0] : null;
    const col = one && columns[one.property];
    const vals = one ? cs.map((c) => tokenValue(c.value, col)).join(',') : '';
    const shown = one ? cs.map((c) => valueLabel(columns, c.property, c.value)) : [];
    if (kind === 'or' && one && (one.kind === 'eq' || one.kind === 'contains')) tries.push([`${propName(one.property)}:${vals}`, `${label(one.property)} ${one.kind === 'eq' ? 'is' : 'has'} ${shown.join(' or ')}`]);
    if (kind === 'or' && one && one.kind === 'has') tries.push([`has:${cs.map((c) => propName(c.property)).join(',')}`, `Has ${cs.map((c) => label(c.property)).join(' or ')}`]);
    if (kind === 'or' && list.length > 1 && list.every((x) => typeof x === 'string')) {
      const toks = list.map((x) => clauseToken(x, columns));
      tries.push([toks.map((t) => t.text).join(' OR '), toks.map((t) => t.label).join(' or ')]);
    }
    if (kind === 'not' && one && (one.kind === 'eq' || one.kind === 'contains')) {
      const verb = one.kind === 'eq' ? (shown.length > 1 ? 'is none of' : 'is not') : (shown.length > 1 ? 'has none of' : 'has no');
      tries.push([`-${propName(one.property)}:${vals}`, `${label(one.property)} ${verb} ${shown.join(', ')}`]);
    }
    if (kind === 'not' && list.length === 1 && typeof list[0] === 'string') {
      const t = clauseToken(list[0], columns);
      if (t.text[0] !== '-') tries.push([`-${t.text}`, `Not: ${t.label}`]);
    }
  }
  for (const [text, lab] of tries) if (ok(text)) return { text, label: lab };
  const src = typeof expr === 'string' ? expr : exprText(expr);
  const wrapped = matchParen(`(${src})`, 0) === src.length + 1 ? `(${src})` : !src.includes('`') ? `\`${src}\`` : `(${src})`;
  return { text: wrapped, label: src };
}

/** A filter tree as one expression (for a nested tree no token can hold; it reads the same rows). */
function exprText(node) {
  if (typeof node === 'string') return node;
  const [kind] = Object.keys(node || {});
  const parts = (node[kind] || []).map((x) => `(${exprText(x)})`);
  if (kind === 'and') return parts.join(' && ');
  if (kind === 'or') return parts.join(' || ');
  if (kind === 'not') return `!(${parts.join(' || ')})`;
  return String(node);
}

/** The clauses grouped into tokens: a low and a high bound of one property side by side are one range token. */
export function groupClauses(list, columns = {}) {
  const out = [];
  for (let i = 0; i < list.length; i++) {
    const a = list[i], b = list[i + 1];
    const ca = typeof a === 'string' && parseClause(a, { wide: true });
    const cb = typeof b === 'string' && parseClause(b, { wide: true });
    if (ca && cb && ca.kind === 'min' && cb.kind === 'max' && ca.property === cb.property) {
      const col = columns[ca.property];
      const bound = (c) => (typeof c.value === 'string' ? c.value : String(c.value));
      const text = `${propName(ca.property)}:${ca.open ? '>' : ''}${bound(ca)}..${cb.open ? '<' : ''}${bound(cb)}`;
      if (same(scanQuery(text, columns).clauses, [a, b]) && !scanQuery(text, columns).words) {
        out.push({ indices: [i, i + 1], text, label: `${col ? col.label : ca.property} ${ca.open ? '>' : ''}${ca.value}–${cb.open ? '<' : ''}${cb.value}` });
        i++;
        continue;
      }
    }
    out.push({ indices: [i], ...clauseToken(a, columns) });
  }
  return out;
}

export function formatQuery(filters, words, columns = {}) {
  const w = String(words || '').trim();
  return [...groupClauses(clauseList(filters), columns).map((g) => g.text), ...(w ? [w] : [])].join(' ');
}

// ------------------------------------------------------------------ suggestions

/** The rows a property's values are counted over: every clause of the filter except those on that property (the
    rail's disjunctive counts). */
function rowsFor(ctx, prop) {
  const others = clauseList(ctx.filters).filter((c) => !propsOf(c).includes(prop));
  let keep = null;
  try { keep = compileFilters(others.length ? { and: others } : null); } catch { keep = null; }
  const rows = ctx.rows || [];
  return keep ? rows.filter(keep) : rows;
}

function propsOf(node) {
  if (typeof node === 'string') { try { return expressionProperties(node); } catch { return []; } }
  const [kind] = Object.keys(node || {});
  return (node && Array.isArray(node[kind]) ? node[kind] : []).flatMap(propsOf);
}

function counts(rows, prop) {
  const n = new Map();
  for (const r of rows) {
    const v = cellValue(r[prop]);
    for (const x of Array.isArray(v) ? v : [v]) if (!isEmpty(x)) n.set(x, (n.get(x) || 0) + 1);
  }
  return [...n.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]), undefined, { numeric: true }));
}

function extent(rows, prop) {
  let lo = null, hi = null;
  for (const r of rows) {
    const v = cellValue(r[prop]);
    if (isEmpty(v) || Array.isArray(v)) continue;
    if (lo === null || v < lo) lo = v;
    if (hi === null || v > hi) hi = v;
  }
  return lo === null ? null : [lo, hi];
}

function sample(col, rows) {
  if (col.type === 'number' || col.type === 'date') {
    const e = extent(rows, col.id);
    return e ? `${fmtNum(e[0])}–${fmtNum(e[1])}${col.unitText ? ' ' + col.unitText : ''}` : '';
  }
  if (col.type === 'boolean') return 'true / false';
  const top = counts(rows, col.id)[0];
  return top ? valueLabel({ [col.id]: col }, col.id, top[0]) : '';
}

/** The example line under the suggestions, from this data: brand:  peak_torque:>10  has:photo  -form:geared */
function hintLine(ctx) {
  const cols = ctx.columns || {};
  const rows = ctx.rows || [];
  const order = [...(ctx.order || []), ...Object.keys(cols)].filter((id, i, a) => cols[id] && a.indexOf(id) === i);
  const few = order.filter((id) => !cols[id].hidden && (cols[id].type === 'text' || cols[id].type === 'list') && (() => { const n = counts(rows, id).length; return n > 1 && n <= 60; })());
  const num = order.find((id) => !cols[id].hidden && cols[id].type === 'number' && extent(rows, id));
  const has = order.find((id) => cols[id].display === 'image' && rows.some((r) => isEmpty(cellValue(r[id])))) || order.find((id) => rows.some((r) => isEmpty(cellValue(r[id]))) && rows.some((r) => !isEmpty(cellValue(r[id]))));
  const parts = [];
  if (few[0]) parts.push(`${propName(few[0])}:`);
  if (num) {
    const vals = rows.map((r) => cellValue(r[num])).filter((v) => typeof v === 'number').sort((a, b) => a - b);
    const mid = vals[vals.length >> 1];
    // WHY the guard: a number column may hold no numbers, whatever extent() reads from its words (a column retyped, CONTRACT §40)
    if (mid !== undefined) parts.push(`${propName(num)}:>${mid >= 1 ? Math.round(mid) : Number(mid.toPrecision(1))}`);
  }
  if (has) parts.push(`has:${propName(has)}`);
  const neg = few[1] || few[0];
  if (neg) { const c = counts(rows, neg); const v = (c[1] || c[0] || [])[0]; if (v !== undefined) parts.push(`-${propName(neg)}:${tokenValue(v, cols[neg])}`); }
  return parts.join('  ');
}

const hint = (ctx, label) => (label ? { kind: 'hint', label, insert: '' } : { kind: 'hint', label: hintLine(ctx), insert: '', example: true });

function propertyItems(prefix, neg, ctx) {
  const low = prefix.toLowerCase();
  const rows = ctx.rows || [];
  const scored = [];
  Object.values(ctx.columns || {}).forEach((c, i) => {
    if (c.hidden || c.pivot) return;
    const id = c.id.toLowerCase(), label = String(c.label || '').toLowerCase();
    const score = !low ? 0 : id.startsWith(low) || label.startsWith(low) ? 0 : label.split(/[\s_-]+/).some((w) => w.startsWith(low)) ? 1 : id.includes(low) || label.includes(low) ? 2 : -1;
    if (score >= 0) scored.push([score, i, c]);
  });
  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const out = scored.map(([, , c]) => ({ kind: 'property', label: c.label, id: c.id, icon: ICONS[c.type] || ICONS.text, detail: sample(c, rows), insert: `${neg}${propName(c.id)}:` }));
  if (!neg && 'has:'.startsWith(low.slice(0, 4)) && low.length <= 3) out.push({ kind: 'operator', label: 'has:', icon: '∃', detail: 'has a value', insert: 'has:' });
  return out;
}

export function suggest(text, caret, ctx = {}) {
  text = String(text || '');
  caret = caret === undefined || caret === null ? text.length : caret;
  const columns = ctx.columns || {};
  const at = segments(text).find((s) => s.start < caret && caret <= s.end);
  if (!at) return { items: [...propertyItems('', '', ctx), hint(ctx)], from: caret, to: caret };
  const from = at.start, to = at.end;
  const typed = text.slice(from, caret);
  const neg = typed[0] === '-' ? '-' : '';
  const body = neg ? typed.slice(1) : typed;
  if (body[0] === '(' || body[0] === '`') return { items: [hint(ctx, 'a Bases expression, e.g. (peak_torque > 10 || mass < 100)')], from, to };
  const m = /^(?:"((?:[^"\\]|\\.)*)"?|([^\s:"`()]*?))([~^]?):([\s\S]*)$/.exec(body);
  if (!m) {
    const items = propertyItems(body.replace(/^"/, ''), neg, ctx);
    return { items: items.length ? [...items, hint(ctx)] : [hint(ctx, `no property starts with "${body}"`)], from, to };
  }
  const name = m[1] !== undefined ? unquote(`"${m[1]}"`) : m[2];
  const mark = m[3], rest = m[4];
  if (m[1] === undefined && !mark && name.toLowerCase() === 'has' && !columns[name]) {
    const parts = splitList(rest) || [rest];
    const prev = parts.slice(0, -1);
    const low = unquote(parts[parts.length - 1]).toLowerCase();
    const items = Object.values(columns).filter((c) => !c.pivot && !prev.includes(propName(c.id)) && (c.id.toLowerCase().startsWith(low) || String(c.label).toLowerCase().startsWith(low)))
      .map((c) => ({ kind: 'value', label: c.label, id: c.id, icon: ICONS[c.type] || ICONS.text, count: rowsFor(ctx, c.id).filter((r) => !isEmpty(cellValue(r[c.id]))).length, insert: `${neg}has:${[...prev, propName(c.id)].join(',')}` }))
      .sort((a, b) => b.count - a.count).slice(0, 12);
    return { items: items.length ? items : [hint(ctx, `no property starts with "${low}"`)], from, to };
  }
  const col = resolve(name, columns);
  if (!col) return { items: [hint(ctx, `no property "${name}"${closest(name, columns)}`)], from, to };
  const pn = `${neg}${propName(col.id)}`;
  if (mark) return { items: [hint(ctx, `text ${mark === '^' ? 'that starts' : 'contained'} in ${col.label}: ${propName(col.id)}${mark}:${sample(col, ctx.rows || []) || 'text'}`)], from, to };
  const rows = rowsFor(ctx, col.id);
  const items = [];
  const bounded = col.type === 'number' || col.type === 'date';
  if (bounded && !rest) {
    const e = extent(rows, col.id) || extent(ctx.rows || [], col.id);
    const ops = col.type === 'date' ? [['>=', 'on or after'], ['<', 'before']] : [['>', 'more than'], ['>=', 'at least'], ['<', 'less than'], ['<=', 'at most']];
    for (const [op, words] of ops) items.push({ kind: 'operator', label: `${op}`, detail: words, insert: `${pn}:${op}` });
    if (e && !neg) items.push({ kind: 'operator', label: `${e[0]}..${e[1]}`, detail: `between${col.unitText ? ', ' + col.unitText : ''}`, insert: `${pn}:${e[0]}..${e[1]}`, complete: true });
  }
  if (bounded && /^[<>]/.test(rest)) {
    const e = extent(rows, col.id);
    return { items: [hint(ctx, `a ${col.type === 'date' ? 'date' : 'number'}${e ? `, ${fmtNum(e[0])}–${fmtNum(e[1])}${col.unitText ? ' ' + col.unitText : ''} here` : ''}`)], from, to };
  }
  const all = counts(rows, col.id);
  if (!bounded || all.length <= 12) {
    const parts = splitList(rest) || [rest];
    const prev = parts.slice(0, -1);
    const low = unquote(parts[parts.length - 1]).toLowerCase();
    const taken = new Set(prev.map((x) => unquote(x)));
    // a value is found by its label or its stored text; it shows its label and inserts the stored value
    const names = (v) => [valueLabel(columns, col.id, v).toLowerCase(), String(v).toLowerCase()];
    const match = all.filter(([v]) => !taken.has(String(v)) && names(v).some((x) => x.includes(low)));
    const first = match.filter(([v]) => names(v).some((x) => x.startsWith(low)));
    const later = match.filter(([v]) => !names(v).some((x) => x.startsWith(low)));
    for (const [v, n] of [...first, ...later].slice(0, 12)) {
      items.push({ kind: 'value', label: valueLabel(columns, col.id, v), count: n, insert: `${pn}:${[...prev, tokenValue(v, col)].join(',')}` });
    }
  }
  if (!items.length) items.push(hint(ctx, `no ${col.label} starts with "${rest}"`));
  return { items, from, to };
}

// ------------------------------------------------------------------ the box

let uid = 0;

export function mountQuery(el, slot, { tokens = false } = {}) {
  const id = `dv-q${++uid}`;
  slot.innerHTML = `<div class="dv-query${tokens ? ' dv-query-tokens' : ''}">
    <div class="dv-qbox">
      <svg class="dv-qicon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14"/></svg>
      ${tokens ? '<span class="dv-qtokens" role="list" aria-label="Filters"></span>' : ''}
      <span class="dv-qfield"><span class="dv-qmirror" aria-hidden="true"></span><input class="dv-qinput" type="text" role="combobox" aria-autocomplete="list"
        aria-expanded="false" aria-controls="${id}-list" aria-describedby="${id}-err" aria-label="Search or filter" autocomplete="off" spellcheck="false"></span>
    </div>
    <p class="dv-qerr" id="${id}-err" hidden></p>
    <div class="dv-suggest" hidden><ul class="dv-suggest-list" role="listbox" id="${id}-list" aria-label="Suggestions"></ul><p class="dv-suggest-hint"></p></div>
  </div>`;
  const $ = (s) => slot.querySelector(s);
  const input = $('.dv-qinput'), mirror = $('.dv-qmirror'), pop = $('.dv-suggest'), list = $('.dv-suggest-list'), hintEl = $('.dv-suggest-hint'), errEl = $('.dv-qerr'), chipsEl = $('.dv-qtokens');
  let opts = [], hintItem = null, active = -1, from = 0, to = 0, open = false, showAll = false, chipsKey = null, groups = [];
  let sent = null; // the words this box last gave el.search: any other el.query came from outside and replaces the text
  let rowsKey = null, rowsMemo = [];

  const columns = () => (el.model ? el.model.columns : {});
  // the rows before the all-views filter: the view's own filter only, so a value's count is the rail's
  const baseRows = () => {
    const d = el.data;
    if (!d) return [];
    const key = JSON.stringify(el.view && el.view.filters);
    if (key !== rowsKey || rowsMemo.src !== d.rows) {
      let keep = null;
      try { keep = compileFilters(el.view && el.view.filters); } catch { keep = null; }
      rowsMemo = keep ? d.rows.filter(keep) : d.rows;
      rowsMemo.src = d.rows;
      rowsKey = key;
    }
    return rowsMemo;
  };
  const ctx = () => ({ columns: columns(), rows: baseRows(), filters: el.filters, order: el.view && el.view.order });
  const wordsOf = (text) => scanQuery(text, columns()).words;

  function draw() {
    list.innerHTML = opts.map((it, k) => `<li role="option" id="${id}-o${k}" class="dv-suggest-item dv-s-${it.kind}${k === active ? ' dv-on' : ''}" aria-selected="${k === active}" data-k="${k}" title="${esc([it.label, it.id && it.id !== it.label ? it.id : '', it.detail || ''].filter(Boolean).join(' · '))}">`
      + `<span class="dv-s-icon" aria-hidden="true">${esc(it.icon || (it.kind === 'operator' ? '⋯' : it.kind === 'value' ? '·' : ''))}</span><span class="dv-s-label">${esc(it.label)}</span>`
      + `${it.id && it.id !== it.label ? `<code class="dv-s-id">${esc(it.id)}</code>` : ''}${it.detail ? `<span class="dv-s-detail">${esc(it.detail)}</span>` : ''}`
      + `${it.count !== undefined ? `<span class="dv-s-count">${it.count.toLocaleString()}</span>` : ''}${k === active ? '<kbd class="dv-s-enter">↵ Enter</kbd>' : ''}</li>`).join('');
    hintEl.innerHTML = !hintItem ? '' : hintItem.example
      ? `<span>Try</span> ${hintItem.label.split(/\s{2,}/).map((x) => `<code>${esc(x)}</code>`).join(' ')}`
      : esc(hintItem.label);
    hintEl.hidden = !hintItem;
    pop.hidden = !open || (!opts.length && !hintItem);
    input.setAttribute('aria-expanded', String(!pop.hidden));
    if (!pop.hidden) place();
    if (active >= 0 && !pop.hidden) {
      input.setAttribute('aria-activedescendant', `${id}-o${active}`);
      const li = list.children[active];
      if (li.offsetTop < pop.scrollTop) pop.scrollTop = li.offsetTop;
      else if (li.offsetTop + li.offsetHeight > pop.scrollTop + pop.clientHeight) pop.scrollTop = li.offsetTop + li.offsetHeight - pop.clientHeight;
    } else input.removeAttribute('aria-activedescendant');
  }

  /** Keep the list inside the window: it grows to its content from the box's left edge, so near the right edge it moves
      left by what would stick out (never past the window's left edge). */
  function place() {
    pop.style.left = '';
    const r = pop.getBoundingClientRect(), right = document.documentElement.clientWidth - 8;
    if (r.right > right) pop.style.left = `${-Math.min(r.right - right, Math.max(0, r.left - 8))}px`;
  }
  // WHY placed again when the box resizes: under search="icon" (or a squeezed row) the box grows from its icon while
  // the list is already open, so a place() at focus measured the narrow box near the right edge and moved the list off
  // the window's left edge
  const boxSize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => { if (!pop.hidden) place(); });
  if (boxSize) boxSize.observe($('.dv-query'));

  function refresh() {
    const s = suggest(input.value, input.selectionStart ?? input.value.length, ctx());
    opts = s.items.filter((i) => i.kind !== 'hint');
    hintItem = s.items.find((i) => i.kind === 'hint') || null;
    from = s.from;
    to = s.to;
    active = -1;
    draw();
  }
  const openList = () => { open = true; refresh(); };
  const close = () => { open = false; active = -1; draw(); };

  /** Underline the clauses that do not parse (red, with the reason below); while typing, not the one at the caret. */
  function paintErrors() {
    const caret = input.selectionStart ?? input.value.length;
    const errs = scanQuery(input.value, columns()).errors.filter((e) => showAll || document.activeElement !== input || caret < e.start || caret > e.end);
    let html = '', at = 0;
    for (const e of errs) { html += esc(input.value.slice(at, e.start)) + `<span class="dv-qbad">${esc(input.value.slice(e.start, e.end))}</span>`; at = e.end; }
    mirror.innerHTML = html + esc(input.value.slice(at));
    mirror.scrollLeft = input.scrollLeft;
    errEl.textContent = errs.map((e) => `${e.text}: ${e.reason}`).join(' · ');
    errEl.hidden = !errs.length;
    if (errs.length) input.setAttribute('aria-invalid', 'true'); else input.removeAttribute('aria-invalid');
  }

  /** Commit the clauses `which` picks out of the box into the all-views filter; the box keeps the rest. */
  function commit(which) {
    const text = input.value;
    const take = scanQuery(text, columns()).items.filter((s) => s.kind === 'clause' && which(s));
    if (!take.length) return false;
    let rest = text;
    for (const s of [...take].reverse()) {
      const end = /\s/.test(rest[s.end] || '') ? s.end + 1 : s.end;
      rest = rest.slice(0, s.start) + rest.slice(end);
    }
    const caret = Math.min(take[0].start, rest.length);
    input.value = rest;
    input.setSelectionRange(caret, caret);
    const cur = clauseList(el.filters);
    const have = new Set(cur.map((c) => JSON.stringify(c)));
    const add = [];
    for (const c of take.flatMap((s) => s.clauses)) if (!have.has(JSON.stringify(c))) { have.add(JSON.stringify(c)); add.push(c); }
    // WHY the words first: setting el.filters renders once, with both
    el.query = sent = wordsOf(rest);
    el.filters = cur.length + add.length ? { and: [...cur, ...add] } : undefined;
    return true;
  }

  /** The words search as you type, except the word at the caret while it could still become a property name: typing
      "bran" on the way to brand: must not empty the table. Enter, a space or leaving the box applies it. */
  function syncWords(live = false) {
    const caret = input.selectionStart ?? input.value.length;
    const cols = Object.values(columns());
    const items = scanQuery(input.value, columns()).items;
    const w = items.filter((s) => s.kind === 'word' && !(live && s.start < caret && caret <= s.end && (() => {
      const low = s.text.replace(/^-/, '').toLowerCase();
      return 'has'.startsWith(low) || cols.some((c) => !c.hidden && (c.id.toLowerCase().startsWith(low) || String(c.label || '').toLowerCase().startsWith(low)));
    })())).map((s) => s.text).join(' ');
    sent = w;
    if (w !== (el.query || '')) el.search(w);
  }

  function accept(item) {
    if (!item) return;
    const v = input.value;
    input.value = v.slice(0, from) + item.insert + v.slice(to);
    const caret = from + item.insert.length;
    input.setSelectionRange(caret, caret);
    if (item.kind === 'value' || item.complete) {
      // WHY close on a pick: the open list would cover the pill the clause just became; typing, ArrowDown or Space
      // reopen it on the next property
      commit((s) => s.start <= from && s.end >= caret);
      input.focus();
      close();
      paintErrors();
      return;
    }
    syncWords(true);
    input.focus();
    openList();
    paintErrors();
  }

  function drawChips() {
    if (!chipsEl) return;
    const cols = columns();
    const clauses = clauseList(el.filters);
    const key = JSON.stringify([clauses, Object.keys(cols)]);
    if (key === chipsKey) return;
    chipsKey = key;
    groups = groupClauses(clauses, cols);
    chipsEl.innerHTML = groups.map((g, k) => `<span class="dv-qtoken" role="listitem" data-g="${k}" title="${esc(g.text)}"><button type="button" class="dv-qtoken-edit" data-edit="${k}" aria-label="Edit filter: ${esc(g.label)}">${esc(g.label)}</button><button type="button" class="dv-qtoken-x" data-remove="${k}" aria-label="Remove filter: ${esc(g.label)}">✕</button></span>`).join('');
  }

  function removeGroup(k) {
    const g = groups[k];
    if (!g) return;
    const next = clauseList(el.filters).filter((_, i) => !g.indices.includes(i));
    el.filters = next.length ? { and: next } : undefined;
  }

  input.addEventListener('input', (e) => {
    showAll = false;
    const caret = input.selectionStart ?? input.value.length;
    // a space after a complete clause commits it (Shopify)
    if (e.inputType === 'insertText' && e.data === ' ' && commit((s) => s.end === caret - 1)) { openList(); paintErrors(); return; }
    syncWords(true);
    openList();
    paintErrors();
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!open) { openList(); if (e.key === 'ArrowUp') { active = opts.length - 1; draw(); } return; }
      if (!opts.length) return;
      active = e.key === 'ArrowDown' ? (active + 1) % opts.length : active <= 0 ? opts.length - 1 : active - 1;
      draw();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (open && active >= 0) { accept(opts[active]); return; }
      commit(() => true);
      syncWords();
      showAll = true;
      close();
      paintErrors();
    } else if (e.key === 'Tab' && open && active >= 0 && !e.shiftKey) {
      e.preventDefault();
      accept(opts[active]);
    } else if (e.key === 'Escape' && open && !pop.hidden) {
      e.preventDefault();
      e.stopPropagation();
      close();
    } else if (e.key === 'Backspace' && tokens && input.selectionStart === 0 && input.selectionEnd === 0 && groups.length) {
      e.preventDefault();
      removeGroup(groups.length - 1);
    }
  });
  // WHY not under search="expand" while empty (CONTRACT §43): Polaris' search opens to a
  // plain box and its filter chips; the hints come once the reader types (or presses ↓)
  input.addEventListener('focus', () => { if (!(el.getAttribute('search') === 'expand' && !input.value)) openList(); });
  input.addEventListener('blur', () => { showAll = true; close(); syncWords(); paintErrors(); });
  input.addEventListener('scroll', () => { mirror.scrollLeft = input.scrollLeft; });
  input.addEventListener('keyup', () => { mirror.scrollLeft = input.scrollLeft; });
  // WHY mousedown: a click on a suggestion must not blur the box first
  pop.addEventListener('mousedown', (e) => e.preventDefault());
  list.addEventListener('click', (e) => { const li = e.target.closest('[data-k]'); if (li) accept(opts[Number(li.dataset.k)]); });
  slot.addEventListener('click', (e) => {
    const x = e.target.closest('[data-remove]');
    if (x) { removeGroup(Number(x.dataset.remove)); input.focus(); return; }
    const ed = e.target.closest('[data-edit]');
    if (ed) {
      const g = groups[Number(ed.dataset.edit)];
      if (!g) return;
      input.value = g.text + (input.value ? ' ' + input.value : '');
      input.focus();
      input.setSelectionRange(g.text.length, g.text.length);
      removeGroup(Number(ed.dataset.edit));
      openList();
      return;
    }
    if (e.target.closest('.dv-qbox') && !e.target.closest('button')) input.focus();
  });

  return {
    update() {
      drawChips();
      const cols = columns();
      const few = hintLine(ctx()).split(/\s+/)[0];
      input.placeholder = few ? `Search or filter… (try ${few})` : 'Search or filter…';
      const q = el.query || '';
      if (el._queryErrors && el._queryErrors.length && document.activeElement !== input) {
        input.value = [...el._queryErrors.map((x) => x.text), q].filter(Boolean).join(' ');
        el._queryErrors = null;
        sent = q;
        showAll = true;
      } else if (q !== sent && scanQuery(input.value, cols).words !== q) {
        // the words changed from outside (search(), setQuery, the URL): the box shows them
        input.value = q;
        sent = q;
      }
      paintErrors();
      if (open && document.activeElement === input) refresh();
    },
    focus() { input.focus(); },
    destroy() { if (boxSize) boxSize.disconnect(); slot.innerHTML = ''; },
  };
}
