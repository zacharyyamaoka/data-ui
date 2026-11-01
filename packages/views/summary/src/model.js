/* The summary card's cells as numbers (docs/CONTRACT.md §43). Pure: the core's functions
   come in as `h` ({compileFilters, summarize, summaryName, cellValue, timeBucket, nextBucket, bucketLabel}), so the
   bundle shares the core's one copy and tests/unit loads this file directly with the core's source.

     summary:
       scope: all | filtered      all (default): the file's rows; filtered: the rows the all-views filter leaves
       cells:
         - label: Open deals      the cell's name (required)
           note: …                its definition: the dotted underline's tooltip
           filters: 'stage != "Won"'          Bases filters, as a view's
           when: {property: due, is: this-month}   today | this-week | this-month | this-quarter | this-year |
                                                   past (before today) | upcoming (today or later)
           value: count           (default) the rows left; or {property, summary}: Bases' summaries and the kit's aliases,
                                  plus Earliest / Latest for a date property (Bases' date summaries)
           spark: {x: created, grain: month}  the same value per bucket of x (day | week | month | quarter | year), from
                                  the cell's rows before `when`; drawn with a delta against the bucket before only when
                                  there are two buckets or more (no series, no line)
           format: {digits, compact}

   WHY counts are computed and never stored: a summary card is a view summary over rows the reader can open (a click
   lists them), so it must agree with the table under it; a producer's headline number is the kpi view's job. */

export const PERIODS = ['today', 'this-week', 'this-month', 'this-quarter', 'this-year', 'past', 'upcoming'];
const GRAIN_OF = { today: 'day', 'this-week': 'week', 'this-month': 'month', 'this-quarter': 'quarter', 'this-year': 'year' };
const DATE_SUMMARIES = ['Earliest', 'Latest'];

const pad = (n) => String(n).padStart(2, '0');
/** The reader's calendar day as ISO text (local time: "today" is the reader's today). */
export const isoToday = (now = new Date()) => `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
const dayText = (v) => (v == null ? '' : String(v).slice(0, 10));

/** The cells' spec from a `summary:` entry: [{label, note, filters, when, value, spark, format}]; bad entries say why. */
export function cellSpecs(summary) {
  const cells = summary && Array.isArray(summary.cells) ? summary.cells : [];
  return cells.map((c, i) => (c && typeof c === 'object' ? c : { label: `Cell ${i + 1}`, error: 'a cell is {label, value?, filters?, when?}' }));
}

/** One cell over `rows`: {label, note, kind: number|date|text, value, rows, error?, series?, delta?}. */
export function cellOf(rows, columns, cell, h, now = new Date()) {
  const out = { label: String(cell.label ?? ''), note: cell.note ? String(cell.note) : '', kind: 'number', value: null, rows: [], format: cell.format || null };
  if (cell.error) return { ...out, error: cell.error };
  let base = rows;
  try {
    const f = cell.filters != null && cell.filters !== '' ? h.compileFilters(cell.filters) : null;
    if (f) base = base.filter(f);
  } catch (err) {
    return { ...out, error: `filters: ${err.message}` };
  }
  let within = base;
  if (cell.when) {
    const { property, is } = cell.when;
    if (!property || !PERIODS.includes(is)) return { ...out, error: `when: {property, is: ${PERIODS.join(' | ')}}` };
    const today = isoToday(now);
    within = base.filter((r) => {
      const d = dayText(h.cellValue(r[property]));
      if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return false;
      if (is === 'past') return d < today;
      if (is === 'upcoming') return d >= today;
      return h.timeBucket(d, GRAIN_OF[is]) === h.timeBucket(today, GRAIN_OF[is]);
    });
  }
  const measured = valueOf(within, columns, cell.value, h);
  if (measured.error) return { ...out, rows: within, error: measured.error };
  Object.assign(out, measured, { rows: within });
  if (cell.spark && cell.spark.x && out.kind === 'number') {
    const series = seriesOf(base, cell, columns, h);
    if (series && series.length >= 2) {
      out.series = series;
      const [prev, last] = series.slice(-2);
      if (typeof prev.y === 'number' && typeof last.y === 'number') out.delta = { value: last.y - prev.y, against: prev.label, at: last.label };
    }
  }
  return out;
}

/** The value of `spec` (count | {property, summary}) over rows: {kind, value} or {error}. */
export function valueOf(rows, columns, spec, h) {
  if (spec == null || spec === 'count' || spec === 'Count') return { kind: 'number', value: rows.length };
  if (typeof spec !== 'object' || !spec.property) return { error: 'value: count, or {property, summary}' };
  const p = spec.property, col = columns[p];
  if (!col) return { error: `value: no property "${p}" in the data` };
  const s = spec.summary || 'Count';
  if (DATE_SUMMARIES.includes(s)) {
    const days = rows.map((r) => h.cellValue(r[p])).filter((v) => v != null && v !== '' && !Number.isNaN(Date.parse(v))).map(String).sort();
    return { kind: 'date', value: days.length ? (s === 'Earliest' ? days[0] : days[days.length - 1]) : null };
  }
  const name = h.summaryName(s);
  if (!name) return { error: `value.summary: "${s}" is not a summary (${['Count', 'Sum', 'Average', 'Median', 'Min', 'Max', 'Unique', 'Filled', 'Empty', ...DATE_SUMMARIES].join(', ')})` };
  const v = h.summarize(rows.map((r) => r[p]), name);
  return Array.isArray(v) ? { kind: 'text', value: v.join('–'), unit: col.unitText || '' } : { kind: 'number', value: typeof v === 'number' ? v : null, unit: name === 'Count' || name === 'Unique' || name === 'Filled' || name === 'Empty' ? '' : col.unitText || '' };
}

/** The cell's value per bucket of spark.x, every bucket from the first to the last (a count in an empty bucket is 0, any
    other summary null: the line lifts). */
function seriesOf(rows, cell, columns, h) {
  const { x, grain = 'month' } = cell.spark;
  const by = new Map();
  for (const r of rows) {
    const k = h.timeBucket(h.cellValue(r[x]), grain);
    if (k == null) continue;
    if (!by.has(k)) by.set(k, []);
    by.get(k).push(r);
  }
  if (!by.size) return null;
  const keys = [...by.keys()].sort();
  const counting = cell.value == null || cell.value === 'count' || cell.value === 'Count';
  const out = [];
  for (let k = keys[0], n = 0; k != null && k <= keys[keys.length - 1] && n < 400; k = h.nextBucket(k, grain), n++) {
    const rs = by.get(k) || [];
    const y = rs.length ? valueOf(rs, columns, cell.value, h).value : counting ? 0 : null;
    out.push({ x: k, label: h.bucketLabel(k, grain), y: typeof y === 'number' ? y : null, n: rs.length });
  }
  return out;
}
