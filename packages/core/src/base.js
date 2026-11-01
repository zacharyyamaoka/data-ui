/* .base files: read and write the YAML subset Obsidian Bases files use, with no dependency.

   The subset (every one of the 109 .base files in Zach's vault reads the same as PyYAML reads it; tests/unit/base.test.mjs):
     block mappings and sequences (a sequence may sit at its key's own indent, `views:\n- type: table`),
     flow collections  [a, b]  { property: brand, direction: ASC }  (they may span lines),
     plain, 'single' ('' escapes a quote) and "double" (backslash escapes) scalars,
     null ~ true false, numbers, # comments, the block scalars | |- > >-, and a leading --- line.
   Not read (a clear error, never a guess): anchors and aliases (& *), tags (!!str), complex keys (? ), several
   documents, tabs in indentation.
   WHY our own and not js-yaml / yaml: a view file must read the same in the browser, in the Node checker and in a
   Python build (robotparts is stdlib-only), so the subset is small enough to write three times and test against
   one oracle (PyYAML); packages/core/python/data_ui_base.py is the same parser line for line. */

export class BaseSyntaxError extends Error {
  constructor(message, line) {
    super(`line ${line}: ${message}`);
    this.name = 'BaseSyntaxError';
    this.line = line;
    this.reason = message;
  }
}

const NUMBER = /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$/;

function plainScalar(text) {
  if (text === '' || text === '~' || text === 'null' || text === 'Null' || text === 'NULL') return null;
  if (text === 'true' || text === 'True' || text === 'TRUE') return true;
  if (text === 'false' || text === 'False' || text === 'FALSE') return false;
  if (NUMBER.test(text)) return Number(text);
  return text;
}

/** Where a `#` comment starts on a line (outside quotes and after whitespace), or -1. */
export function commentAt(text) {
  let quote = null;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quote) {
      if (quote === '"' && c === '\\') i++;
      else if (c === quote) {
        if (quote === "'" && text[i + 1] === "'") i++;
        else quote = null;
      }
    } else if (c === '#' && (i === 0 || text[i - 1] === ' ')) return i;
    else if ((c === '"' || c === "'") && (i === 0 || /[\s[{,:-]/.test(text[i - 1]))) quote = c;
  }
  return -1;
}

/** The index of the `:` that ends a mapping key on this line (outside quotes and flow), or -1. */
function keyColon(text) {
  let quote = null, depth = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quote) {
      if (quote === '"' && c === '\\') i++;
      else if (c === quote) { if (quote === "'" && text[i + 1] === "'") i++; else quote = null; }
      continue;
    }
    if ((c === '"' || c === "'") && i === 0) quote = c;
    else if (c === '[' || c === '{') { if (i === 0) return -1; depth++; }
    else if (c === ']' || c === '}') depth--;
    else if (c === ':' && depth <= 0 && (i + 1 === text.length || text[i + 1] === ' ')) return i;
  }
  return -1;
}

function unquote(text, line) {
  if (text[0] === "'") {
    if (!text.endsWith("'") || text.length < 2) throw new BaseSyntaxError(`an unclosed ' quote: ${text}`, line);
    return text.slice(1, -1).replace(/''/g, "'");
  }
  if (!text.endsWith('"') || text.length < 2) throw new BaseSyntaxError(`an unclosed " quote: ${text}`, line);
  try { return JSON.parse(text.replace(/\\'/g, "'").replace(/\t/g, '\\t')); } catch { throw new BaseSyntaxError(`cannot read the string ${text}`, line); }
}

function keyText(raw, line) {
  const k = raw.trim();
  if (k[0] === '"' || k[0] === "'") return unquote(k, line);
  if (k.startsWith('? ')) throw new BaseSyntaxError('complex keys (? ) are not supported', line);
  return k;
}

function guard(text, line) {
  const t = text.trimStart();
  if (t[0] === '&' || t[0] === '*') throw new BaseSyntaxError('anchors and aliases (& *) are not supported in .base files', line);
  // WHY an error, not a string: unquoted, `!x.isEmpty()` is a YAML tag (PyYAML refuses it, Obsidian quotes it)
  if (t[0] === '!') throw new BaseSyntaxError(`a value that starts with ! is a YAML tag; quote it: '${t}'`, line);
}

// ------------------------------------------------------------------------------------------------ flow collections

function parseFlow(src, line) {
  let i = 0;
  const ws = () => { while (i < src.length && /\s/.test(src[i])) i++; };
  function value(inMap) {
    ws();
    const c = src[i];
    if (c === '[') {
      i++;
      const out = [];
      ws();
      if (src[i] === ']') { i++; return out; }
      for (;;) {
        out.push(value(false));
        ws();
        if (src[i] === ',') { i++; ws(); if (src[i] === ']') { i++; return out; } continue; }
        if (src[i] === ']') { i++; return out; }
        throw new BaseSyntaxError(`expected , or ] in ${src}`, line);
      }
    }
    if (c === '{') {
      i++;
      const out = {};
      ws();
      if (src[i] === '}') { i++; return out; }
      for (;;) {
        const k = value(true);
        ws();
        let v = null;
        if (src[i] === ':') { i++; v = value(false); ws(); }
        const key = k === null ? 'null' : String(k);
        if (Object.prototype.hasOwnProperty.call(out, key)) throw new BaseSyntaxError(`the key '${key}' appears twice`, line);
        out[key] = v;
        if (src[i] === ',') { i++; ws(); if (src[i] === '}') { i++; return out; } continue; }
        if (src[i] === '}') { i++; return out; }
        throw new BaseSyntaxError(`expected , or } in ${src}`, line);
      }
    }
    if (c === '"' || c === "'") {
      let j = i + 1;
      while (j < src.length) {
        if (c === '"' && src[j] === '\\') { j += 2; continue; }
        if (src[j] === c) { if (c === "'" && src[j + 1] === "'") { j += 2; continue; } break; }
        j++;
      }
      const text = src.slice(i, j + 1);
      i = j + 1;
      return unquote(text, line);
    }
    // a plain scalar reads to the next , ] or } (a key also stops at its `:`): `title: Mass (g)` is one value
    let j = i;
    while (j < src.length && !',[]{}'.includes(src[j]) && !(inMap && src[j] === ':' && (j + 1 === src.length || /[\s,\]}]/.test(src[j + 1])))) j++;
    const text = src.slice(i, j).trim();
    i = j;
    guard(text, line);
    return plainScalar(text);
  }
  const out = value(false);
  ws();
  if (i < src.length) throw new BaseSyntaxError(`unexpected "${src.slice(i, i + 12)}" after ${src.slice(0, i)}`, line);
  return out;
}

export function flowBalance(text) {
  let quote = null, depth = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quote) {
      if (quote === '"' && c === '\\') i++;
      else if (c === quote) { if (quote === "'" && text[i + 1] === "'") i++; else quote = null; }
    } else if (c === '"' || c === "'") quote = c;
    else if (c === '[' || c === '{') depth++;
    else if (c === ']' || c === '}') depth--;
  }
  return depth;
}

// ------------------------------------------------------------------------------------------------ the block parser

/** Parse a .base file. Returns {doc, lines} where lines maps a path key (JSON of the path) to its 1-based line. */
export function parseBaseWithLines(text) {
  const raw = String(text).replace(/\r\n?/g, '\n').split('\n');
  const lines = [];
  for (let n = 0; n < raw.length; n++) {
    const full = raw[n];
    const indentMatch = /^[ \t]*/.exec(full)[0];
    if (indentMatch.includes('\t') && full.trim() && !full.trim().startsWith('#')) throw new BaseSyntaxError('a tab in the indentation (use spaces)', n + 1);
    const at = commentAt(full);
    const body = (at >= 0 ? full.slice(0, at) : full).replace(/\s+$/, '');
    lines.push({ n: n + 1, indent: indentMatch.length, text: body.slice(indentMatch.length), raw: full });
  }
  let pos = 0;
  const where = new Map();
  const mark = (path, line) => { where.set(JSON.stringify(path), line); };
  const skip = () => { while (pos < lines.length && !lines[pos].text) pos++; };
  skip();
  if (pos < lines.length && lines[pos].indent === 0 && lines[pos].text === '---') { pos++; skip(); }

  function blockScalar(header, parentIndent) {
    const folded = header[0] === '>';
    const chomp = header.includes('-') ? 'strip' : header.includes('+') ? 'keep' : 'clip';
    const body = [];
    let indent = null;
    while (pos < lines.length) {
      const l = lines[pos];
      if (l.raw.trim() === '') { body.push(''); pos++; continue; }
      const ind = /^ */.exec(l.raw)[0].length;
      if (ind <= parentIndent) break;
      if (indent === null) indent = ind;
      if (ind < indent) break;
      body.push(l.raw.slice(indent));
      pos++;
    }
    while (body.length && body[body.length - 1] === '' && chomp !== 'keep') body.pop();
    let out = folded ? body.reduce((s, x, k) => (k === 0 ? x : x === '' || body[k - 1] === '' ? s + '\n' + x : s + ' ' + x), '') : body.join('\n');
    if (chomp !== 'strip' && body.length) out += '\n';
    return out;
  }

  /** An inline value (after `key: ` or `- `), which may continue onto the next lines (flow or plain). */
  function inline(text, line, parentIndent) {
    guard(text, line);
    if (text === '|' || text === '|-' || text === '|+' || text === '>' || text === '>-' || text === '>+') return blockScalar(text, parentIndent);
    if (text[0] === '[' || text[0] === '{') {
      let src = text;
      while (flowBalance(src) > 0 && pos < lines.length) { src += ' ' + lines[pos].text.trim(); pos++; skip(); }
      return parseFlow(src, line);
    }
    if (text[0] === '"' || text[0] === "'") {
      let src = text;
      // a quoted scalar that runs over several lines folds its line breaks into spaces
      while (!closes(src) && pos < lines.length) { src += ' ' + lines[pos].raw.trim(); pos++; }
      return unquote(src, line);
    }
    // a plain scalar continues on more-indented lines that are not keys or items
    let src = text;
    while (pos < lines.length && lines[pos].text && lines[pos].indent > parentIndent && keyColon(lines[pos].text) < 0 && !/^-( |$)/.test(lines[pos].text)) {
      src += ' ' + lines[pos].text.trim();
      pos++;
    }
    return plainScalar(src);
  }

  function closes(src) {
    const q = src[0];
    if (src.length < 2) return false;
    let k = 1;
    while (k < src.length) {
      if (q === '"' && src[k] === '\\') { k += 2; continue; }
      if (src[k] === q) { if (q === "'" && src[k + 1] === "'") { k += 2; continue; } return k === src.length - 1 || /^\s*$/.test(src.slice(k + 1)); }
      k++;
    }
    return false;
  }

  function block(indent, path) {
    skip();
    if (pos >= lines.length) return null;
    const l = lines[pos];
    if (/^-( |$)/.test(l.text)) return sequence(l.indent, path);
    return mapping(l.indent, path);
  }

  function valueAfterKey(rest, keyIndent, line, path) {
    if (rest !== '') return inline(rest, line, keyIndent);
    skip();
    if (pos >= lines.length) return null;
    const next = lines[pos];
    if (next.indent > keyIndent) return block(next.indent, path);
    if (next.indent === keyIndent && /^-( |$)/.test(next.text)) return sequence(keyIndent, path);
    return null;
  }

  function mapping(indent, path, first = null) {
    const out = {};
    for (;;) {
      let l;
      if (first) { l = first; first = null; } else {
        skip();
        if (pos >= lines.length) break;
        l = lines[pos];
        if (l.indent < indent) break;
        if (l.indent > indent) throw new BaseSyntaxError(`unexpected indentation: ${l.text}`, l.n);
        if (/^-( |$)/.test(l.text)) break;
        pos++;
      }
      const at = keyColon(l.text);
      if (at < 0 && (l.text === '---' || l.text === '...')) throw new BaseSyntaxError('a .base file holds one YAML document', l.n);
      if (at < 0) throw new BaseSyntaxError(`expected "key: value", got: ${l.text}`, l.n);
      const key = keyText(l.text.slice(0, at), l.n);
      if (Object.prototype.hasOwnProperty.call(out, key)) throw new BaseSyntaxError(`the key '${key}' appears twice`, l.n);
      const child = [...path, key];
      mark(child, l.n);
      out[key] = valueAfterKey(l.text.slice(at + 1).trim(), indent, l.n, child);
    }
    return out;
  }

  function sequence(indent, path) {
    const out = [];
    for (;;) {
      skip();
      if (pos >= lines.length) break;
      const l = lines[pos];
      if (l.indent !== indent || !/^-( |$)/.test(l.text)) {
        if (l.indent > indent) throw new BaseSyntaxError(`unexpected indentation: ${l.text}`, l.n);
        break;
      }
      pos++;
      const child = [...path, out.length];
      mark(child, l.n);
      const rest = l.text.slice(1).replace(/^ +/, '');
      const col = indent + (l.text.length - rest.length);
      if (rest === '') {
        skip();
        out.push(pos < lines.length && lines[pos].indent > indent ? block(lines[pos].indent, child) : null);
      } else if (/^-( |$)/.test(rest)) {
        // "- - x": a sequence inside a sequence, written on one line
        pos--;
        lines[pos] = { ...l, indent: col, text: rest };
        out.push(sequence(col, child));
      } else if (rest[0] !== '[' && rest[0] !== '{' && rest[0] !== '"' && rest[0] !== "'" && keyColon(rest) >= 0) {
        out.push(mapping(col, child, { ...l, indent: col, text: rest }));
      } else {
        out.push(inline(rest, l.n, indent));
      }
    }
    return out;
  }

  let doc = null;
  if (pos < lines.length) {
    const l = lines[pos];
    if (l.indent !== 0 && !/^-( |$)/.test(l.text)) { /* an indented document still reads as one block */ }
    if (/^-( |$)/.test(l.text) || keyColon(l.text) >= 0) doc = block(l.indent, []);
    else { pos++; doc = inline(l.text, l.n, -1); }
    skip();
    if (pos < lines.length) {
      const extra = lines[pos];
      if (extra.text === '---' || extra.text === '...') throw new BaseSyntaxError('a .base file holds one YAML document', extra.n);
      throw new BaseSyntaxError(`unexpected indentation: ${extra.text}`, extra.n);
    }
  }
  return { doc, lines: where };
}

export function parseBase(text) {
  return parseBaseWithLines(text).doc;
}

/** The line a path was written on (or its nearest ancestor's), from parseBaseWithLines(). */
export function lineOf(lines, path) {
  const p = [...path];
  while (p.length) {
    const hit = lines.get(JSON.stringify(p));
    if (hit) return hit;
    p.pop();
  }
  return 1;
}

// ------------------------------------------------------------------------------------------------ writing

const PLAIN = /^[\p{L}_$][\p{L}\p{N}_ .·/()›×$%+&'-]*$/u;
const RESERVED = /^(?:true|false|null|yes|no|on|off|y|n|~)$/i;

export function yamlScalar(v) {
  if (v === null || v === undefined) return 'null';
  if (typeof v === 'number') return Number.isFinite(v) ? String(v) : JSON.stringify(String(v));
  if (typeof v === 'boolean') return String(v);
  const s = String(v);
  if (PLAIN.test(s) && !RESERVED.test(s) && s.trim() === s && !NUMBER.test(s) && !s.includes(" '")) return s;
  // WHY single quotes first: a filter reads 'brand == "KST"', not "brand == \"KST\"" (what Zach's files do)
  return !s.includes("'") && !/[\u0000-\u001f]/.test(s) ? `'${s}'` : JSON.stringify(s);
}

const isScalar = (v) => v === null || typeof v !== 'object';

export function yamlFlow(v) {
  if (Array.isArray(v)) return '[' + v.map(yamlFlow).join(', ') + ']';
  if (v && typeof v === 'object') {
    const entries = Object.entries(v);
    return entries.length ? '{ ' + entries.map(([k, x]) => `${yamlScalar(k)}: ${yamlFlow(x)}`).join(', ') + ' }' : '{}';
  }
  return yamlScalar(v);
}

const WIDTH = 110;
// WHY these stay block-style: they are what an agent edits most, and one item per line diffs cleanly
const BLOCK_KEYS = new Set(['views', 'filters', 'and', 'or', 'not', 'sort', 'chart', 'layer', 'encoding', 'guides', 'kpi', 'properties', 'formulas']);

function emit(value, indent, key, out) {
  const pad = ' '.repeat(indent);
  if (Array.isArray(value)) {
    for (const item of value) {
      if (isScalar(item) || (yamlFlow(item).length + indent + 4 <= WIDTH && key !== 'views')) out.push(`${pad}- ${yamlFlow(item)}`);
      else if (Array.isArray(item)) { out.push(`${pad}-`); emit(item, indent + 2, null, out); }
      else {
        const lines = [];
        emit(item, indent + 2, null, lines);
        if (lines.length) lines[0] = `${pad}- ${lines[0].slice(indent + 2)}`;
        out.push(...lines);
      }
    }
    return;
  }
  for (const [k, v] of Object.entries(value)) {
    if (v === undefined) continue;
    const head = `${pad}${yamlScalar(k)}:`;
    const flow = yamlFlow(v);
    // WHY a list of names stays on one line however long: `order:` reads as the row of columns it is
    const names = Array.isArray(v) && v.every(isScalar);
    const inlineOk = isScalar(v) || (!BLOCK_KEYS.has(k) && (names || (head.length + 1 + flow.length <= WIDTH && !(Array.isArray(v) && v.some((x) => x && typeof x === 'object') && v.length > 1))));
    if (inlineOk || (Array.isArray(v) && !v.length) || (v && typeof v === 'object' && !Object.keys(v).length)) out.push(`${head} ${flow}`);
    else {
      out.push(head);
      emit(v, indent + 2, k, out);
    }
  }
}

/** A .base document (or any plain JSON value) as YAML text in the house style: block mappings, small maps and
    lists in flow style, one view and one sort rule per line. parseBase(stringifyBase(doc)) deep-equals doc. */
export function stringifyBase(doc, key = null) {
  if (isScalar(doc)) return yamlScalar(doc) + '\n';
  const out = [];
  emit(doc, 0, key, out);
  return out.join('\n') + '\n';
}

/** Replace views[index] inside the file's own text (or append when index is past the end), keeping every other
    line and its comments as written. WHY in place: Obsidian re-dumps the YAML and drops comments; data-ui's writer
    must not (docs/SPEC.md §5.1). */
export function replaceViewInText(text, index, view) {
  const { doc, lines: at } = parseBaseWithLines(text);
  const src = String(text).replace(/\r\n?/g, '\n').split('\n');
  const views = doc && doc.views;
  if (!Array.isArray(views) || !views.length) throw new Error('the file has no views: list to edit');
  const start = (i) => at.get(JSON.stringify(['views', i]));
  const indentOf = (s) => /^ */.exec(s)[0].length;
  const dash = indentOf(src[start(0) - 1]);
  const body = stringifyBase([view], 'views').replace(/\n$/, '').split('\n').map((x) => ' '.repeat(dash) + x);
  const quiet = (s) => s.trim() === '' || s.trim().startsWith('#');
  // the last line of item i: up to the next item, or (for the last item) while lines stay indented past the dash
  const endOf = (i) => {
    let end;
    if (i + 1 < views.length) end = start(i + 1) - 1;
    else {
      end = start(i);
      for (let n = start(i); n < src.length; n++) {
        if (quiet(src[n])) continue;
        if (indentOf(src[n]) <= dash) break;
        end = n + 1;
      }
    }
    while (end > start(i) && quiet(src[end - 1])) end--;
    return end;
  };
  if (index >= views.length) {
    src.splice(endOf(views.length - 1), 0, ...body);
  } else {
    const s = start(index);
    src.splice(s - 1, endOf(index) - s + 1, ...body);
  }
  return src.join('\n');
}

/** The file's text with one top-level key set (null or undefined removes it), every other line as it was: its comments,
    its order, its hand-written views (CONTRACT §37: a host writes the picked view and the all-views filter into the file).
    A new key goes just above `views:`. */
export function replaceKeyInText(text, key, value) {
  const src = String(text).replace(/\r\n?/g, '\n').split('\n');
  const { lines: at } = parseBaseWithLines(text);
  const body = value === null || value === undefined ? [] : stringifyBase({ [key]: value }).replace(/\n$/, '').split('\n');
  const line = at.get(JSON.stringify([key]));
  if (line !== undefined) {
    let end = line;
    // its value runs on while lines are indented, or a sequence at the key's own indent (`views:\n- type: table`)
    while (end < src.length && (src[end].trim() === '' ? false : /^(\s+|- )/.test(src[end]))) end++;
    src.splice(line - 1, end - line + 1, ...body);
    return src.join('\n');
  }
  if (!body.length) return src.join('\n');
  const views = at.get(JSON.stringify(['views']));
  if (views !== undefined) src.splice(views - 1, 0, ...body);
  else src.push(...body);
  return src.join('\n');
}
