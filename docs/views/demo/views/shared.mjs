/* What every view plugin draws the same way: escaped text, numbers with their unit, property labels. */

export const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

/** A value as text. Empty reads "—" (not measured is never 0); numbers keep 4 significant figures, never an exponent. */
export function fmt(v, prop) {
  if (v === null || v === undefined || v === '' || (Array.isArray(v) && !v.length)) return '<span class="du-none">—</span>';
  if (Array.isArray(v)) return esc(v.join(', '));
  if (prop && prop.labels && prop.labels[v] !== undefined) return esc(prop.labels[v]);
  if (!isNum(v)) return esc(v);
  const text = prop && prop.decimals != null
    ? v.toLocaleString('en-US', { minimumFractionDigits: prop.decimals, maximumFractionDigits: prop.decimals })
    : Number(v.toPrecision(4)).toLocaleString('en-US', { maximumFractionDigits: 6 });
  return esc(text) + (prop && prop.unitText ? ` <span class="du-unit">${esc(prop.unitText)}</span>` : '');
}

export function propLabel(columns, id) {
  return (columns[id] && columns[id].label) || id;
}

export function groupLabel(columns, property, key) {
  const p = columns[property];
  if (key === null || key === undefined || key === '') return `No ${propLabel(columns, property).toLowerCase()}`;
  if (p && p.labels && p.labels[key] !== undefined) return p.labels[key];
  return String(key);
}
