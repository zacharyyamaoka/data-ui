/* The source view's pure parts: a stored value as literal text, the columns of a dataset, the record's origin file
   name, and RFC 4180 CSV. No DOM and no core import, so tests/unit/source.test.mjs runs them in Node.

   WHY literal, not formatted: Zach's truthful-rendering rule (memory feedback_truthful_property_rendering): a stored
   value is never normalised, trimmed, substituted or hidden. The table formats (units, decimals, badges); this view
   shows what the data holds, so a debugging eye sees "1.50" vs 1.5, "" vs null vs an absent key, and the spaces. */

const own = Object.prototype.hasOwnProperty;

/** One cell as the grid writes it: {text, kind}. kind is absent (the row has no such key), null, empty (""), string,
    number, boolean or json (an array or an object, rich cells included, as compact JSON). */
export function literal(row, key) {
  if (!row || !own.call(row, key)) return { text: '', kind: 'absent' };
  const v = row[key];
  if (v === null) return { text: 'null', kind: 'null' };
  if (v === undefined) return { text: 'undefined', kind: 'null' };
  if (typeof v === 'string') return v === '' ? { text: '""', kind: 'empty' } : { text: v, kind: 'string' };
  // WHY Object.is: String(-0) is "0", and the sign is part of what was stored
  if (typeof v === 'number') return { text: Object.is(v, -0) ? '-0' : String(v), kind: 'number' };
  if (typeof v === 'boolean') return { text: String(v), kind: 'boolean' };
  if (typeof v === 'object') {
    try { return { text: JSON.stringify(v), kind: 'json' }; } catch { return { text: String(v), kind: 'json' }; }
  }
  return { text: String(v), kind: 'string' };
}

/** Every key of every row, in the order they are first seen (a Set keeps insertion order). JavaScript lists an
    integer-like key ("2") before the others within one object; that is the only reordering. */
export function columnsOf(rows) {
  const seen = new Set();
  for (const r of rows) if (r && typeof r === 'object') for (const k of Object.keys(r)) seen.add(k);
  return [...seen];
}

/** A dataset's `origin.url` template for one row: each {property} becomes that row's value (a rich cell's .value), as
    one URL path segment. null when the row has no value for a placeholder. */
export function fillTemplate(template, row) {
  let missing = null;
  const out = String(template).replace(/\{([^{}]+)\}/g, (_, p) => {
    let v = row ? row[p] : undefined;
    if (v && typeof v === 'object' && !Array.isArray(v) && 'value' in v) v = v.value;
    if (v === null || v === undefined || v === '' || typeof v === 'object') { missing = missing || p; return ''; }
    return encodeURIComponent(String(v));
  });
  return missing ? null : out;
}

/** One CSV field (RFC 4180): quoted when it holds a quote, a comma or a line break, or starts or ends with
    whitespace (so a reader that trims cannot lose it); a quote inside is doubled. */
export function csvField(text) {
  const s = String(text);
  return /[",\r\n]/.test(s) || /^\s|\s$/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** The header and one line per row, each value exactly as the grid shows it (an absent key is an empty field). Lines
    end in CRLF, RFC 4180's line break, with none after the last. */
export function toCSV(columns, rows) {
  const lines = [columns.map(csvField).join(',')];
  for (const r of rows) lines.push(columns.map((k) => csvField(literal(r, k).text)).join(','));
  return lines.join('\r\n');
}

/** raw.format -> what the info strip says. */
export const FORMATS = { runtime: 'runtime shape', frictionless: 'Frictionless', csv: 'CSV', tsv: 'TSV', jsonl: 'JSONL', list: 'bare list', object: 'one object' };
