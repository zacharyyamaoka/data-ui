/* The selected rows as CSV (docs/CONTRACT.md §15, the export-csv bulk action). RFC 4180: a field holding a comma, a
   quote, CR or LF is quoted, a quote inside is doubled, lines end CRLF. The header is each property's label with its
   unit, "Peak torque (N·m)"; a rich cell writes its value, a list its items joined by ", ", a missing value nothing. */

import { cellValue } from '../grammar.js';

export function csvField(v) {
  if (v === null || v === undefined) return '';
  const s = Array.isArray(v) ? v.join(', ') : String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** rows -> CSV text over the properties in `order` (ids of `columns`). */
export function toCsv(rows, columns, order) {
  const head = order.map((id) => { const c = columns[id] || { label: id }; return csvField(`${c.label || id}${c.unitText ? ` (${c.unitText})` : ''}`); });
  const lines = [head.join(',')];
  for (const r of rows) lines.push(order.map((id) => csvField(cellValue(r[id]))).join(','));
  return lines.join('\r\n') + '\r\n';
}
