// One row = one .md file: the file's text <-> a row's properties, and nothing else (docs/CONTRACT.md §46). Pure, stdlib, no I/O.
//
// A note reads as: YAML frontmatter = short properties; each heading = a section property, its body that cell's value; what comes
// before the first heading = the row's `page` property. Any heading found becomes a property, so a column needs no declaring.
//
// THE RULE FOR HEADINGS. Each column is one H1 (Zach, 2026-10-31: "If I saw each column is associated with an H1 then its simpler"). An H1
// starts a section and runs to the next H1; everything under it, H2 and H3 included, is that one cell. What comes before the first H1,
// an H2 included, is the page. Fenced code holds no headings. Only ATX headings (`# Title`) count; a setext heading (`Title` over `===`)
// stays text, as a line of words.
//
// WHY every edit is a splice of the original text, never a re-serialise: Zach, 2026-10-31: the file must stay one a person is happy
// to open in Obsidian. What was not edited keeps its bytes, its unknown keys, its unknown headings, its blank lines and its line
// endings, because nothing ever rewrites it.
//
// A heading's id comes from its words (`Desired outcome` -> desired_outcome), or from the .base's displayName when one matches
// (`labels`). Two of the same id in a note are `x` and `x_2`, and `x_2` is a property too, so nothing is ever dropped.
import { parseBase, yamlScalar } from '../packages/core/src/base.js';

export const PLACES = ['top', 'section'];
const RESERVED = new Set(['id', 'name', 'page']); // the row's own id, title and free text

/** A heading's or a key's words as a property id. */
export function slug(words) {
  const s = String(words).trim().toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '_').replace(/^_+|_+$/g, '');
  return s || 'heading';
}
export const propId = (words) => { const s = slug(words); return RESERVED.has(s) ? `note_${s}` : s; };

const isBlank = (s) => /^[ \t]*$/.test(s);
const FENCE = /^ {0,3}(`{3,}|~{3,})/;
const HEADING = /^(#{1,6})[ \t]+(.*?)[ \t]*(?:[ \t]#+[ \t]*)?$/;

/** The text's lines as [{start, end, next}]: `end` before the line's break, `next` after it. */
function lineSpans(text, from = 0) {
  const out = [];
  let at = from;
  while (at < text.length) {
    const nl = text.indexOf('\n', at);
    const next = nl < 0 ? text.length : nl + 1;
    const end = nl < 0 ? text.length : nl > at && text[nl - 1] === '\r' ? nl - 1 : nl;
    out.push({ start: at, end, next });
    at = next;
  }
  return out;
}

/** One frontmatter entry's value, or undefined when the YAML subset cannot read it (the entry then stays exactly as written). */
function entryValue(raw) {
  try {
    const doc = parseBase(raw.replace(/\r\n/g, '\n'));
    const keys = doc && typeof doc === 'object' ? Object.keys(doc) : [];
    return keys.length === 1 ? doc[keys[0]] : undefined;
  } catch { return undefined; }
}

function parseFrontmatter(text, from) {
  const lines = lineSpans(text, from);
  if (!lines.length || text.slice(lines[0].start, lines[0].end).trimEnd() !== '---') return null;
  const close = lines.findIndex((l, i) => i > 0 && /^(---|\.\.\.)[ \t]*$/.test(text.slice(l.start, l.end)));
  if (close < 0) return null;
  const entries = [];
  let open = null;
  for (let i = 1; i < close; i++) {
    const l = lines[i];
    const s = text.slice(l.start, l.end);
    const key = /^("(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^\s#:-][^:]*?|-[^\s:][^:]*?)[ \t]*:(?:[ \t]|$)/.exec(s);
    if (key) {
      open = { key: key[1].replace(/^(['"])(.*)\1$/, '$2'), start: l.start, end: l.next };
      entries.push(open);
    } else if (open && (/^\s+\S/.test(s) || /^- /.test(s) || s === '-')) open.end = l.next;
    else if (!isBlank(s)) open = null; // a comment at the margin belongs to no key; it stays where it is
  }
  for (const e of entries) e.value = entryValue(text.slice(e.start, e.end));
  return { start: lines[0].start, inner: lines[0].next, close: lines[close].start, end: lines[close].next, entries };
}

/** The file as spans of its text. `opts`: {labels: Map(heading words -> id)}. */
export function parseNote(text, opts = {}) {
  const bom = text.charCodeAt(0) === 0xfeff ? 1 : 0;
  const eol = text.includes('\r\n') ? '\r\n' : '\n';
  const fm = parseFrontmatter(text, bom);
  const seen = new Map();
  const unique = (id) => {
    const n = (seen.get(id) || 0) + 1;
    seen.set(id, n);
    return n === 1 ? id : `${id}_${n}`;
  };
  if (fm) for (const e of fm.entries) e.id = unique(propId(e.key));
  const bodyStart = fm ? fm.end : bom;
  const labels = opts.labels || new Map();
  const heads = [];
  let fence = null;
  for (const l of lineSpans(text, bodyStart)) {
    const s = text.slice(l.start, l.end);
    const f = FENCE.exec(s);
    if (fence) {
      if (f && f[1][0] === fence[0] && f[1].length >= fence.length && isBlank(s.slice(f[0].length))) fence = null;
      continue;
    }
    if (f) { fence = f[1]; continue; }
    const h = HEADING.exec(s);
    if (!h || !h[2] || h[1].length !== 1) continue;
    heads.push({ id: unique(labels.get(h[2]) ?? propId(h[2])), label: h[2], start: l.start, bodyStart: l.next, lineEnd: l.end });
  }
  const sections = heads.map((h, i) => ({ ...h, end: i + 1 < heads.length ? heads[i + 1].start : text.length }));
  return { text, bom, eol, fm, bodyStart, preEnd: sections.length ? sections[0].start : text.length, sections };
}

/** A span's value: LF line ends, without the blank lines around it. {value, start, end}: where the value sits in the text. */
function trimmed(text, from, to) {
  const lines = lineSpans(text.slice(from, to)).filter((l) => !isBlank(text.slice(from + l.start, from + l.end)));
  if (!lines.length) return { value: '', start: to, end: to };
  const start = from + lines[0].start, end = from + lines[lines.length - 1].end;
  return { value: text.slice(start, end).replace(/\r\n/g, '\n'), start, end };
}

/** What the note says: {values: {id: value}, sections: [{id, label}], keys: [{id, key}], page}. */
export function readNote(text, opts = {}) {
  const note = parseNote(text, opts);
  const values = {};
  const keys = [];
  if (note.fm) for (const e of note.fm.entries) {
    keys.push({ id: e.id, key: e.key, unread: e.value === undefined });
    values[e.id] = e.value === undefined ? text.slice(e.start, e.end).replace(/\r?\n$/, '').replace(/^[^:]*:[ \t]*/, '') : e.value;
  }
  const sections = note.sections.map((s) => {
    values[s.id] = trimmed(text, s.bodyStart, s.end).value;
    return { id: s.id, label: s.label };
  });
  return { values, sections, keys, page: trimmed(text, note.bodyStart, note.preEnd).value };
}

// ---------------------------------------------------------------- writing a value
const toEol = (s, eol) => (eol === '\n' ? s : s.replace(/\n/g, eol));
const DATE = /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;

/** A scalar as YAML. WHY a date stays plain: Obsidian's date property reads `filed: 2026-10-31`, and a quoted one is a word. */
function scalar(v) {
  if (typeof v === 'string' && DATE.test(v) && !v.includes(' ')) return v;
  // a string the plain parser would read as something else, or that starts a flow list (`[[Note]]`), is quoted by yamlScalar
  return yamlScalar(v);
}

/** One frontmatter entry as lines, Obsidian's way: a list one item per line, many lines as a `|-` block. */
export function entryText(key, value, eol = '\n') {
  const name = /^[\p{L}_][\p{L}\p{N}_ -]*$/u.test(key) && key.trim() === key ? key : JSON.stringify(key);
  let out;
  if (value === null || value === undefined || value === '') out = `${name}:\n`;
  else if (Array.isArray(value)) out = value.length ? `${name}:\n${value.map((x) => `  - ${scalar(x)}\n`).join('')}` : `${name}: []\n`;
  else if (typeof value === 'string' && value.includes('\n')) {
    // WHY JSON then: `|-` has no trailing line end, a block scalar cannot start with a space without an indent marker, and a control
    // character has no block form
    if (/^\s|\n$/.test(value) || /[\u0000-\u0008\u000b-\u001f]/.test(value)) out = `${name}: ${JSON.stringify(value)}\n`;
    else out = `${name}: |-\n${value.split('\n').map((l) => (l ? `  ${l}\n` : '\n')).join('')}`;
  } else if (typeof value === 'object') out = `${name}: ${JSON.stringify(value)}\n`;
  else out = `${name}: ${scalar(value)}\n`;
  return toEol(out, eol);
}

const splice = (text, from, to, what) => text.slice(0, from) + what + text.slice(to);
const empty = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && !v.length);
const sameValue = (a, b) => (empty(a) && empty(b)) || JSON.stringify(a) === JSON.stringify(b);

/** Set one section's body; the heading line, and every other byte around the value, stay. */
function setSection(note, section, value) {
  const { text, eol } = note;
  const was = trimmed(text, section.bodyStart, section.end);
  if (was.value === value) return text;
  if (!value) {
    // the heading stays: an empty section is still somewhere to write
    const last = section.end === text.length;
    return splice(text, section.bodyStart, section.end, last ? '' : eol);
  }
  const body = toEol(value, eol);
  if (was.value) return splice(text, was.start, was.end, body);
  const lineBroken = section.bodyStart > section.lineEnd ? '' : eol; // a heading on the file's last line, with no line end
  const last = section.end === text.length;
  return splice(text, section.bodyStart, section.end, `${lineBroken}${eol}${body}${eol}${last ? '' : eol}`);
}

/** Add a frontmatter entry: before the first key that `order` puts after it, else at the end; a new block when the note has none. */
function addEntry(note, id, value, order, key = id) {
  const { text, eol, fm, bom } = note;
  const line = entryText(key, value, eol);
  if (!fm) return splice(text, bom, bom, `---${eol}${line}---${eol}`);
  const rank = (x) => { const i = order ? order.indexOf(x) : -1; return i < 0 ? Infinity : i; };
  const mine = rank(id);
  const after = mine === Infinity ? null : fm.entries.find((e) => rank(e.id) > mine && rank(e.id) !== Infinity);
  const at = after ? after.start : fm.close;
  return splice(text, at, at, line);
}

function removeEntry(note, entry) {
  const { text, fm } = note;
  if (fm.entries.length === 1 && isBlank(text.slice(fm.inner, entry.start)) && isBlank(text.slice(entry.end, fm.close))) return splice(text, fm.start, fm.end, '');
  return splice(text, entry.start, entry.end, '');
}

/** Add a section: before the first section `order` puts after it, else at the end, with a blank line on each side. */
function addSection(note, id, label, value, order) {
  const { text, eol } = note;
  const head = `# ${label}${eol}`;
  const body = value ? `${eol}${toEol(value, eol)}${eol}` : '';
  const rank = (x) => { const i = order ? order.indexOf(x) : -1; return i < 0 ? Infinity : i; };
  const mine = rank(id);
  const next = mine === Infinity ? null : note.sections.find((s) => rank(s.id) > mine);
  if (next) return splice(text, next.start, next.start, `${head}${body}${eol}`);
  // at the end of the file: a blank line above it, unless it is the file's first text
  const before = text.slice(note.bom);
  const lead = !before ? '' : text.endsWith('\n') ? eol : `${eol}${eol}`;
  return `${text}${lead}${head}${body}`;
}

function removeSection(note, section) {
  const { text, eol } = note;
  if (section.end < text.length) return splice(text, section.start, section.end, '');
  // the last section takes the blank line above it: addSection put one there
  const before = text.slice(0, section.start);
  return before.endsWith(eol + eol) ? before.slice(0, before.length - eol.length) : before;
}

/** Set a property to `value` in the note's text, wherever it lives; a no-op leaves the very same string.
    A property the note does not hold yet goes where `opts.place` says ('top' or 'section'), under `opts.label`, in `opts.order`.
    `value` is LF-separated; the file's own line ends are kept. */
export function setValue(text, id, value, opts = {}) {
  const note = parseNote(text, opts);
  const entry = note.fm && note.fm.entries.find((e) => e.id === id);
  if (entry) {
    if (entry.value === undefined) throw new Error(`${entry.key}: this YAML is more than the reader takes, so it stays as written`);
    if (sameValue(entry.value, value)) return text;
    return splice(text, entry.start, entry.end, entryText(entry.key, value, note.eol));
  }
  const section = note.sections.find((s) => s.id === id);
  if (section) return setSection(note, section, value === null || value === undefined ? '' : String(value));
  if (empty(value)) return text;
  const place = opts.place || 'top';
  if (place === 'top') return addEntry(note, id, value, opts.order);
  return addSection(note, id, opts.label || id, String(value), opts.order);
}

/** Set the free text: what comes before the first heading. Everything else stays. */
export function setPage(text, value, opts = {}) {
  const note = parseNote(text, opts);
  const was = trimmed(text, note.bodyStart, note.preEnd);
  if (was.value === value) return text;
  const { eol } = note;
  if (was.value && value) return splice(text, was.start, was.end, toEol(value, eol));
  if (was.value) return splice(text, note.bodyStart, note.preEnd, '');
  const lead = note.fm ? eol : '';
  return splice(text, note.bodyStart, note.preEnd, `${lead}${toEol(value, eol)}${eol}${note.sections.length ? eol : ''}`);
}

/** Move one property: to the frontmatter ('top') or to an H1 ('section'). The value does not change; only where it lives.
    `opts` as parseNote (of the layout it moves FROM), plus `order` and `label`, the .base's displayName if it has one. With no displayName
    a heading's words become the key (`DP:`) and a key's words the heading, so a move and its way back are the same bytes. */
export function moveProperty(text, id, to, opts = {}) {
  const note = parseNote(text, opts);
  const entry = note.fm && note.fm.entries.find((e) => e.id === id);
  const section = note.sections.find((s) => s.id === id);
  if (to === 'top') {
    if (!section) return text;
    if (entry) throw new Error(`${id} is in the frontmatter and under a heading`);
    const value = trimmed(text, section.bodyStart, section.end).value;
    const without = removeSection(note, section);
    return addEntry(parseNote(without, opts), id, value || null, opts.order, opts.label ? id : section.label);
  }
  if (section || !entry) return text;
  if (entry.value === undefined) throw new Error(`${entry.key}: this YAML is more than the reader takes, so it stays as written`);
  if (entry.value !== null && typeof entry.value === 'object') throw new Error(`${entry.key} is a list, not words`);
  const value = entry.value === null ? '' : String(entry.value);
  const without = removeEntry(note, entry);
  return addSection(parseNote(without, opts), id, opts.label || entry.key, value, opts.order);
}

// ---------------------------------------------------------------- a folder's worth of notes as a dataset (no I/O: text in, rows out)
const ISO_DATE = /^\d{4}-\d{2}-\d{2}/;

/** The type frontmatter values say: number, boolean, date, list, else text. A section is always text. */
export function inferType(values) {
  const seen = values.filter((v) => !empty(v));
  if (!seen.length) return 'text';
  if (seen.some(Array.isArray)) return 'list';
  if (seen.every((v) => typeof v === 'number')) return 'number';
  if (seen.every((v) => typeof v === 'boolean')) return 'boolean';
  if (seen.every((v) => typeof v === 'string' && ISO_DATE.test(v) && DATE.test(v))) return 'date';
  return 'text';
}

/** What the .base says about the notes: {labels, places, order}. `base`: the parsed file. */
export function layoutOf(base) {
  const labels = new Map();
  for (const [id, p] of Object.entries((base && base.properties) || {})) if (p && p.displayName) labels.set(String(p.displayName), id);
  const places = new Map();
  const order = [];
  for (const e of (base && Array.isArray(base.page) ? base.page : [])) {
    if (!e || typeof e !== 'object' || !e.property) continue;
    order.push(e.property);
    places.set(e.property, PLACES.includes(e.place) ? e.place : 'top');
  }
  return { labels, places, order };
}

/** Whether a property's value is words a heading can hold. WHY only these: a number, a date, a checkbox, a select or a list is what
    you sort and filter by, so it stays typed in the frontmatter; a heading's body is free text, and one typed "about 12" would turn
    a number column into words. Such a property may still be drawn as a heading: that is the layout's, and no file changes. */
export function fitsHeading(p) {
  return !!p && (p.type === 'text' || !p.type) && !p.labels && !(p.constraints && p.constraints.enum) && p.display !== 'badge' && p.display !== 'link';
}

/** notes: [{id, text}] -> the dataset's {properties, rows}, in a stable order. */
export function buildRows(notes, base, { title = 'name', free = 'page' } = {}) {
  const lay = layoutOf(base);
  const declared = (base && base.properties) || {};
  const rows = [];
  const fmIds = new Map(); // id -> label
  const secIds = new Map(); // id -> label
  const typed = new Map();
  for (const n of notes) {
    const read = readNote(n.text, lay);
    const row = { id: n.id, [title]: n.id.split('/').pop(), ...read.values, [free]: read.page };
    rows.push(row);
    for (const k of read.keys) {
      if (!fmIds.has(k.id)) fmIds.set(k.id, k.key);
      if (!typed.has(k.id)) typed.set(k.id, []);
      typed.get(k.id).push(read.values[k.id]);
    }
    for (const s of read.sections) if (!secIds.has(s.id)) secIds.set(s.id, s.label);
  }
  const properties = { [title]: { type: 'text', label: 'Name', readOnly: true } };
  const define = (id, p) => {
    const d = declared[id] || {};
    // WHY `kind`: a .base's type is how the column reads; the data's storage `type` is what filtering, sorting and saving read (CONTRACT §28)
    const { displayName, type, ...more } = d;
    properties[id] = { ...p, ...more, ...(type ? { kind: type } : {}), label: displayName || p.label };
    if (d.enum) { properties[id].constraints = { enum: d.enum }; delete properties[id].enum; }
  };
  for (const [id, label] of fmIds) define(id, { type: inferType(typed.get(id)), label });
  // WHY display: outline: the cell is drawn from the section, its sub-headings if it has them, else its first lines (CONTRACT §46)
  const section = (label) => ({ type: 'text', kind: 'markdown', label, long: true, display: 'outline', section: true });
  for (const [id, label] of secIds) define(id, section(label));
  // a layout may name a section no note has yet: still a column, still somewhere to write
  for (const [id, place] of lay.places) {
    if (properties[id] || place === 'top') continue;
    define(id, section((declared[id] && declared[id].displayName) || id));
  }
  define(free, { type: 'text', label: 'Page', long: true, display: 'preview', pageBody: true });
  return { properties, rows };
}

/** Every file's move, worked out and checked before anything is written. `notes`: [{id, text}]. `from`, `to`: layouts (layoutOf).
    {files: [{id, text}], changed, unchanged, total, refused: [{id, reason}]}. WHY read each result back: a value holding a `# ` line
    would split into a section of its own, and that is a loss only a re-read can see. */
export function planMove(notes, id, place, from, to, { label } = {}) {
  const files = [];
  const refused = [];
  let same = 0;
  for (const n of notes) {
    const before = readNote(n.text, from);
    const asked = { ...from, label, order: to.order };
    let text;
    try { text = moveProperty(n.text, id, place, asked); } catch (err) { refused.push({ id: n.id, reason: err.message }); continue; }
    const after = readNote(text, to);
    const wrong = [...new Set([...Object.keys(before.values), ...Object.keys(after.values)])].find((k) => !sameValue(norm(before.values[k]), norm(after.values[k])));
    if (wrong !== undefined || before.page !== after.page) { refused.push({ id: n.id, reason: `an H1 inside the value would split it (${wrong ?? 'page'})` }); continue; }
    if (text === n.text) same++; else files.push({ id: n.id, text });
  }
  return { files, changed: files.length, unchanged: same, total: notes.length, refused };
}
const norm = (v) => (typeof v === 'string' ? v.replace(/^(?:[ \t]*\n)+|\s+$/g, '') : v);
