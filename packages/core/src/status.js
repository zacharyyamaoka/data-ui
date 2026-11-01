/* The status vocabulary (docs/CONTRACT.md §35; PEP 0010 §7 and §10): one word list for the gates' verdicts (pass, warn,
   partial, fail, not_run: bam_rack_twin's acceptance, sim2real, robotdx.diagnostics' `verdict`) and RobotDx's levels
   (ok, warn, error, unknown, stale: ROS diagnostics', robotdx.diagnostics' `level`), so one view draws either feed.

   Zach, 2026-10-28: "Data-UI should have standard views for showing diagnostics data. Also for showing gates". PEP 0010
   §7: green and red are status only, "always a glyph and a word: ✓ pass, ! warn, ✕ fail, – not run, ? unknown, ◷ stale".
   WHY the order is RobotDx's ranks (ok 0 < warn 1 < unknown and not run 2 < stale 3 < error and fail 4): a check that did
   not run is never a pass ("can't tell is never green", robotdx.diagnostics core.py), so a worst-of over gates and levels
   agrees with the producer's own roll-up.

   No imports: the tracker (kpi bundle), the levels card (live bundle), the table, the side peek and node --test read it
   as it is. */

export const STATUS = Object.freeze({
  pass: Object.freeze({ tone: 'good', glyph: '✓' }),
  ok: Object.freeze({ tone: 'good', glyph: '✓' }),
  warn: Object.freeze({ tone: 'warn', glyph: '!' }),
  warning: Object.freeze({ tone: 'warn', glyph: '!' }),
  partial: Object.freeze({ tone: 'warn', glyph: '!' }),
  fail: Object.freeze({ tone: 'bad', glyph: '✕' }),
  error: Object.freeze({ tone: 'bad', glyph: '✕' }),
  not_run: Object.freeze({ tone: 'muted', glyph: '–' }),
  'not run': Object.freeze({ tone: 'muted', glyph: '–' }),
  unknown: Object.freeze({ tone: 'muted', glyph: '?' }),
  stale: Object.freeze({ tone: 'muted', glyph: '◷' }),
});

/** Best to worst: worst-of reads it (a word it does not hold ranks best, so an unexpected word never hides a known problem). */
export const STATUS_ORDER = Object.freeze(['ok', 'pass', 'warn', 'warning', 'partial', 'unknown', 'not_run', 'not run', 'stale', 'error', 'fail']);

/** The glyph of a tone a map chose (a view or a column naming a word's tone outright). */
export const TONE_GLYPH = Object.freeze({ good: '✓', warn: '!', bad: '✕', muted: '–', neutral: '•' });

const TONES = ['good', 'warn', 'bad', 'muted', 'neutral'];
const has = (o, k) => !!o && typeof o === 'object' && Object.prototype.hasOwnProperty.call(o, k);
const val = (c) => (c !== null && typeof c === 'object' && !Array.isArray(c) && 'value' in c ? c.value : c);
const missing = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const toneIn = (map, key) => (has(map, key) && TONES.includes(map[key]) ? map[key] : null);

/** A value as a status: {value, word, tone, glyph, known}. The word is the column's label when it has one; the tone is
    the view's map (`tones`), then the column's (`column.tones`), then the vocabulary's (a word looked up as stored, then
    as its label), else neutral. A tone a map chose takes that tone's glyph; a missing value is muted, "no value". */
export function statusOf(value, { tones = null, column = null } = {}) {
  const v = val(value);
  if (missing(v)) return { value: v === undefined ? null : v, word: 'no value', tone: 'muted', glyph: '–', known: false };
  const key = String(v);
  const labels = column && column.labels;
  const word = has(labels, key) ? String(labels[key]) : key;
  const base = (has(STATUS, key) && STATUS[key]) || (has(STATUS, word) && STATUS[word]) || null;
  const tone = toneIn(tones, key) || toneIn(column && column.tones, key) || (base ? base.tone : 'neutral');
  return { value: v, word, tone, glyph: base && base.tone === tone ? base.glyph : TONE_GLYPH[tone], known: !!base };
}

/** The worst of some values by `order` (best first, worst last), read as stored (`String(value)`); a missing value is
    skipped and a word the order does not hold ranks best. null when nothing is left. */
export function worstStatus(values, order = STATUS_ORDER) {
  let worst = null, rank = -2;
  for (const raw of values || []) {
    const v = val(raw);
    if (missing(v)) continue;
    const r = order.indexOf(String(v));
    if (r > rank) { rank = r; worst = v; }
  }
  return worst;
}

/** `display: status`: each value a badge, its glyph hidden from readers (the word is the accessible text), the word in
    its tone, the stored value in data-state. A missing value is the kit's dash with its reason. */
export function statusHtml(cell, column = {}, { tones = null } = {}) {
  const v = val(cell);
  if (missing(v)) {
    const why = (cell && typeof cell === 'object' && !Array.isArray(cell) && cell.why) || 'no value';
    return `<span class="dv-none" title="${esc(why)}">—</span>`;
  }
  return (Array.isArray(v) ? v : [v]).map((x) => {
    const s = statusOf(x, { tones, column });
    return `<span class="dv-state dv-tone-${s.tone}" data-state="${esc(String(x))}"><span class="dv-state-glyph" aria-hidden="true">${s.glyph}</span><span class="dv-state-word">${esc(s.word)}</span></span>`;
  }).join(' ');
}
