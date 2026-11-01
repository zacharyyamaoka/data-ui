/* The smallest text edit that gives a value of a .base file a new content. Pure and Node-safe.

   WHY a patcher and not a re-dump (SPEC §5.1, CONTRACT §34): a dashboard is a file people and agents both edit, and its
   comments, blank lines, key order, quotes and spacing are theirs. So patchAt(text, path, next) compares the value at
   `path` with `next` and touches only what differs: one token inside a `{ … }`, one `key: value` line of a block, one
   block's lines. Everything else stays byte for byte, CRLF and an open last line included. A key that goes takes its
   lines with it (a comment inside them stays); a key that arrives goes after the last key of its map; one going and one
   arriving take the same place, so `view: A` becoming `views: [A, B]` stays first on its line.

   It reads back what it wrote, and throws NoPlace where the text has no place to patch (a value inside a multi-line
   flow, a list in flow style) or the result is not the value asked for: the caller then rewrites that one entry, as
   replaceViewInText does, and never hands out a wrong file. */

import { parseBaseWithLines, parseBase, stringifyBase, yamlFlow, yamlScalar } from '../../../core/src/base.js';

export class NoPlace extends Error {}

const isMap = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const indentOf = (s) => /^ */.exec(s)[0].length;
const isQuiet = (s) => s.trim() === '' || s.trim().startsWith('#');
const get = (doc, path) => path.reduce((o, k) => (o == null ? o : o[k]), doc);

/** Two values the same, key order aside. */
export function sameValue(a, b) {
  const norm = (v) => (Array.isArray(v) ? v.map(norm) : isMap(v) ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, norm(v[k])])) : v);
  return JSON.stringify(norm(a)) === JSON.stringify(norm(b));
}

/** Where a line's comment starts, or -1. A quote opens only where a scalar can start, so it's stays plain text. */
function commentAt(s) {
  let q = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (q) {
      if (q === '"' && c === '\\') i++;
      else if (c === q) { if (q === "'" && s[i + 1] === "'") i++; else q = null; }
    } else if ((c === '"' || c === "'") && (i === 0 || /[\s,[{:]/.test(s[i - 1]))) q = c;
    else if (c === '#' && (i === 0 || /\s/.test(s[i - 1]))) return i;
  }
  return -1;
}

/** A line cut into {body, tail}: tail is its comment with the spaces before it, kept as written. */
function cutComment(line) {
  const at = commentAt(line);
  if (at < 0) return { body: line.replace(/\s+$/, ''), tail: '' };
  const body = line.slice(0, at).replace(/\s+$/, '');
  return { body, tail: line.slice(body.length) };
}

const KEY = /^(\s*(?:-\s+)*)('(?:[^']|'')*'|"(?:[^"\\]|\\.)*"|[^\s#'"{[][^:#]*?)(\s*:)(?=\s|$)/;

/** A `key: value` line: {lead (indent and dashes), key (as written), head (through the colon), value, tail, col}. */
function keyLine(line) {
  const { body, tail } = cutComment(line);
  const m = KEY.exec(body);
  if (!m) return null;
  return { lead: m[1], key: m[2], head: m[0], value: body.slice(m[0].length).trim(), tail, col: m[1].length };
}

/** Where a `{ … }` that opens at s[from] closes, or -1 when it does not close on this line. */
function closeOf(s, from) {
  let q = null, depth = 0;
  for (let i = from; i < s.length; i++) {
    const c = s[i];
    if (q) {
      if (q === '"' && c === '\\') i++;
      else if (c === q) { if (q === "'" && s[i + 1] === "'") i++; else q = null; }
    } else if ((c === '"' || c === "'") && /[\s,[{:]/.test(s[i - 1] || ' ')) q = c;
    else if (c === '{' || c === '[') depth++;
    else if (c === '}' || c === ']') { depth--; if (!depth) return i; }
  }
  return -1;
}

/** The entries of the flow map s[open..close]: [{key, start, end, valueAt}] (start..end is `key: value`, its own spaces out). */
function flowEntries(s, open, close) {
  const out = [];
  let q = null, depth = 0, start = -1, colon = -1;
  const finish = (end) => {
    if (start < 0) return;
    let e = end;
    while (e > start && /\s/.test(s[e - 1])) e--;
    const raw = s.slice(start, colon < 0 ? e : colon).trim();
    const key = Object.keys(parseBase(`${raw}: 1\n`))[0];
    let valueAt = colon < 0 ? e : colon + 1;
    while (valueAt < e && /\s/.test(s[valueAt])) valueAt++;
    out.push({ key, start, end: e, valueAt });
    start = -1;
    colon = -1;
  };
  for (let i = open + 1; i < close; i++) {
    const c = s[i];
    if (q) {
      if (q === '"' && c === '\\') i++;
      else if (c === q) { if (q === "'" && s[i + 1] === "'") i++; else q = null; }
      continue;
    }
    if (start < 0 && !/\s/.test(c)) start = i;
    if ((c === '"' || c === "'") && /[\s,[{:]/.test(s[i - 1])) q = c;
    else if (c === '{' || c === '[') depth++;
    else if (c === '}' || c === ']') depth--;
    else if (!depth && c === ':' && colon < 0 && /\s/.test(s[i + 1] || ' ')) colon = i;
    else if (!depth && c === ',') finish(i);
  }
  finish(close);
  return out;
}

const pair = (k, v) => `${yamlScalar(k)}: ${yamlFlow(v)}`;

/** The text of a flow map `a` written as s[open..close], changed to `b`: only the tokens that differ. */
function patchFlow(s, open, close, a, b) {
  const entries = flowEntries(s, open, close);
  const gone = entries.filter((e) => !(e.key in b));
  const fresh = Object.keys(b).filter((k) => !(k in a));
  const cuts = []; // {from, to, text}: applied right to left
  for (const e of entries) {
    if (!(e.key in b) || sameValue(a[e.key], b[e.key])) continue;
    const c = e.valueAt < e.end && s[e.valueAt] === '{' ? closeOf(s, e.valueAt) : -1;
    if (c === e.end - 1 && isMap(a[e.key]) && isMap(b[e.key])) cuts.push({ from: e.valueAt, to: e.end, text: patchFlow(s.slice(e.valueAt, e.end), 0, e.end - e.valueAt - 1, a[e.key], b[e.key]) });
    else cuts.push({ from: e.valueAt, to: e.end, text: yamlFlow(b[e.key]) });
  }
  // a key that goes and one that arrives take the same place (view → views stays first)
  while (gone.length && fresh.length) {
    const e = gone.shift();
    const k = fresh.shift();
    cuts.push({ from: e.start, to: e.end, text: pair(k, b[k]) });
  }
  for (const e of gone) {
    const i = entries.indexOf(e);
    const next = entries[i + 1];
    const prev = entries[i - 1];
    if (next) cuts.push({ from: e.start, to: next.start, text: '' });
    else if (prev) cuts.push({ from: prev.end, to: e.end, text: '' });
    else cuts.push({ from: e.start, to: e.end, text: '' });
  }
  if (fresh.length) {
    const add = fresh.map((k) => pair(k, b[k])).join(', ');
    const last = entries[entries.length - 1];
    if (last) cuts.push({ from: last.end, to: last.end, text: `, ${add}` });
    else cuts.push({ from: open + 1, to: close, text: ` ${add} ` });
  }
  let out = s;
  for (const c of cuts.sort((x, y) => y.from - x.from || y.to - x.to)) out = out.slice(0, c.from) + c.text + out.slice(c.to);
  return out;
}

class Patch {
  constructor(text) {
    const raw = String(text);
    this.eol = /\r\n/.test(raw) ? '\r\n' : '\n';
    this.src = raw.replace(/\r\n?/g, '\n').split('\n');
    const { doc, lines } = parseBaseWithLines(raw);
    this.doc = doc;
    this.lines = lines;
    this.edits = []; // {from, to, lines}: src[from..to) becomes lines
  }

  line(path) { const l = this.lines.get(JSON.stringify(path)); return l === undefined ? -1 : l - 1; }

  /** The last line a key's value takes (its block, or the rest of a multi-line flow), comments after it not included. */
  end(l, col) {
    let last = l;
    for (let n = l + 1; n < this.src.length; n++) {
      if (isQuiet(this.src[n])) continue;
      if (indentOf(this.src[n]) <= col) break;
      last = n;
    }
    return last;
  }

  /** The value at `path` (a key or a list item) from `a` to `b`. */
  node(path, a, b) {
    if (sameValue(a, b)) return;
    const l = this.line(path);
    if (l < 0) throw new NoPlace(`no line for ${JSON.stringify(path)}`);
    const item = typeof path[path.length - 1] === 'number';
    const line = this.src[l];
    const k = item ? null : keyLine(line);
    if (!item && !k) throw new NoPlace(`no key on line ${l + 1}`);
    if (isMap(a) && isMap(b)) {
      const { body } = cutComment(line);
      const lead = item ? /^\s*(?:-\s+)+/.exec(body) : null;
      if (item && !lead) throw new NoPlace(`no item on line ${l + 1}`);
      const at = item ? lead[0].length : k.head.length + /^\s*/.exec(body.slice(k.head.length))[0].length;
      if (body[at] === '{') {
        const close = closeOf(body, at);
        if (close < 0 || close !== body.length - 1) throw new NoPlace(`a flow map over several lines at ${l + 1}`);
        const tail = line.slice(body.length);
        this.edits.push({ from: l, to: l + 1, lines: [patchFlow(body, at, close, a, b) + tail] });
        return;
      }
      if (!item && body.length > k.head.length && body.slice(k.head.length).trim()) throw new NoPlace(`an inline value at ${l + 1}`);
      this.map(path, a, b);
      return;
    }
    if (item) throw new NoPlace('a list item that is no map');
    this.replace(path, path[path.length - 1], b);
  }

  /** A block map: each key that differs on its own lines. */
  map(path, a, b) {
    const keys = Object.keys(a);
    const lineOf = (k) => this.line([...path, k]);
    if (keys.some((k) => lineOf(k) < 0)) throw new NoPlace(`a block map with no line for every key at ${JSON.stringify(path)}`);
    const gone = keys.filter((k) => !(k in b));
    const fresh = Object.keys(b).filter((k) => !(k in a));
    for (const k of keys) if (k in b) this.node([...path, k], a[k], b[k]);
    while (gone.length && fresh.length) {
      const k = gone.shift();
      const n = fresh.shift();
      this.replace([...path, k], n, b[n]);
    }
    for (const k of gone) this.remove(path, k, keys);
    if (fresh.length) {
      const last = keys.map(lineOf).reduce((x, y) => Math.max(x, y), -1);
      const first = keyLine(this.src[lineOf(keys[0])]);
      const pad = ' '.repeat(first.col);
      const at = this.end(last, first.col);
      const lines = fresh.flatMap((n) => stringifyBase({ [n]: b[n] }).replace(/\n$/, '').split('\n').map((x) => pad + x));
      this.edits.push({ from: at + 1, to: at + 1, lines });
    }
  }

  /** The key at `path` holds `value` under the name `name` (a new name takes the old one's place). */
  replace(path, name, value) {
    const l = this.line(path);
    const k = keyLine(this.src[l]);
    const last = this.end(l, k.col);
    const key = String(path[path.length - 1]) === String(name) ? k.key : yamlScalar(name);
    const head = `${k.lead}${key}${k.head.slice(k.lead.length + k.key.length)}`;
    if (last === l && !k.value.startsWith('|') && !k.value.startsWith('>')) {
      this.edits.push({ from: l, to: l + 1, lines: [`${head} ${yamlFlow(value)}${k.tail}`] });
      return;
    }
    // a block value: the new one in the house style, and the comments it held stay above it
    const held = this.src.slice(l + 1, last + 1).filter((s) => s.trim().startsWith('#')).map((s) => ' '.repeat(k.col) + s.trim());
    const body = stringifyBase({ [name]: value }).replace(/\n$/, '').split('\n').map((x) => ' '.repeat(k.col) + x);
    body[0] = `${k.lead}${body[0].slice(k.col)}`;
    this.edits.push({ from: l, to: last + 1, lines: k.lead.includes('-') ? [...body, ...held] : [...held, ...body] });
  }

  /** The key `k` of the block map at `path` goes; the comments inside its lines stay. */
  remove(path, k, keys) {
    const l = this.line([...path, k]);
    const line = keyLine(this.src[l]);
    const last = this.end(l, line.col);
    const held = this.src.slice(l + 1, last + 1).filter((s) => s.trim().startsWith('#')).map((s) => ' '.repeat(line.col) + s.trim());
    if (line.lead.includes('-')) {
      // the key on the dash goes: the next key takes the dash
      const next = keys.map((x) => this.line([...path, x])).filter((n) => n > l).sort((x, y) => x - y)[0];
      if (next === undefined) throw new NoPlace('the only key of an item');
      const rest = this.src[next];
      this.edits.push({ from: l, to: next, lines: held });
      this.edits.push({ from: next, to: next + 1, lines: [line.lead + rest.slice(line.col)] });
      return;
    }
    this.edits.push({ from: l, to: last + 1, lines: held });
  }

  text() {
    const out = [...this.src];
    const order = this.edits.map((e, i) => ({ ...e, i })).sort((a, b) => b.from - a.from || b.i - a.i);
    for (const e of order) out.splice(e.from, e.to - e.from, ...e.lines);
    return out.join(this.eol);
  }
}

/** `text` with the value at `path` changed to `next`, as small an edit as the text allows. Throws NoPlace when this text
    cannot be patched there; never returns a text that does not read back as asked. */
export function patchAt(text, path, next) {
  const p = new Patch(text);
  p.node(path, get(p.doc, path), next);
  const out = p.text();
  let back;
  try { back = get(parseBase(out), path); } catch (err) { throw new NoPlace(`the patch did not read back: ${err.message}`); }
  if (!sameValue(back, next)) throw new NoPlace(`the patch read back as ${JSON.stringify(back)}`);
  return out;
}
