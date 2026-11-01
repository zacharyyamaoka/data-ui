/* How every view writes a value: escaped text, numbers with their unit, the basis mark, "—" with its reason.
   One vocabulary for "how sure" (docs/SPEC.md §9.2), built once here and in <data-value>. */
import { markdown } from './md.js';

import { cellValue, bucketLabel, binKey } from './grammar.js';
import { statusHtml } from './status.js';
import { isMultiSource, stated } from './precedence.js';
import { formatText, typedHtml, hasFormat } from './types.js';

export const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const isEmpty = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
export const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

/** The basis vocabulary: mark, label, meaning. Absence is not a basis: {value: null, why: "not measured"}. */
export const BASIS = {
  measured: { mark: '●', label: 'measured', means: 'measured on a bench or in a run' },
  datasheet: { mark: 'D', label: 'datasheet', means: "the maker's published spec" },
  seller: { mark: 'S', label: 'seller', means: "a seller's listing" },
  derived: { mark: '~', label: 'derived', means: 'computed from other values' },
  estimate: { mark: '○', label: 'estimate', means: 'modelled or estimated' },
  assumed: { mark: 'A', label: 'assumed', means: 'an assumption' },
  chosen: { mark: 'C', label: 'chosen', means: 'a design choice, set on purpose' },
  sampled: { mark: '≈', label: 'sampled', means: 'drawn from a distribution' },
  'stand-in': { mark: '◌', label: 'stand-in', means: 'a placeholder for the real value' },
  claimed: { mark: '”', label: 'claimed', means: "asserted, not computed (an agent's claim)" },
};

/** A number as stored: every stored digit, thousands separators, never an exponent (986.8881, 1,149, 0.0000068).
 * WHY no default rounding: Zach's truthful-rendering rule; a stored value is never silently clipped. A view that wants
 * fewer digits says so with `decimals` on the property. */
export function fmtNum(v, decimals, { digits, compact } = {}) {
  if (!isNum(v)) return v;
  // WHY opt-in only: `digits` (significant figures) and `compact` (26.5K) are declared in the .base, on a property,
  // a card's format: or a dashboard's numbers:, so rounding is the author's visible choice, never a silent default;
  // every caller keeps the stored value one hover away (Zach, 2026-10-26: "round the numbers" on dashboards).
  if (compact && Math.abs(v) >= 1000) return cachedFormat(`c${digits || 3}`, { notation: 'compact', maximumSignificantDigits: digits || 3 }).format(v);
  if (digits) {
    // significant figures, but an integer part is never cut (12,345 at 3 digits stays 12,345, not 12,300)
    const whole = Math.abs(v) >= 1 ? Math.floor(Math.log10(Math.abs(v))) + 1 : 0;
    const sig = Math.min(21, Math.max(digits, whole));
    return cachedFormat(`s${sig}`, { maximumSignificantDigits: sig }).format(v);
  }
  return numberFormat(decimals).format(v);
}

/** A cached Intl.NumberFormat for the digits / compact forms (the same cache rule as numberFormat below). */
function cachedFormat(key, options) {
  let f = NUMBER_FORMATS.get(key);
  if (!f) {
    f = new Intl.NumberFormat('en-US', options);
    if (NUMBER_FORMATS.size < 64) NUMBER_FORMATS.set(key, f);
  }
  return f;
}

/* WHY cached: `v.toLocaleString('en-US', options)` builds a new Intl.NumberFormat on every call (V8 caches only the
   no-argument form), and a first table page formats hundreds of numbers: 15.4 → 1.7 ms for 40 actuator rows (perf
   review 2026-10-26, item 1). ECMA-402 defines toLocaleString(locales, options) as exactly
   `new Intl.NumberFormat(locales, options).format(v)`, so the cached formatter writes the same bytes
   (tests/unit/format-cache.test.mjs holds it to that). An invalid `decimals` still throws the same RangeError, and is
   never cached. */
const NUMBER_FORMATS = new Map();
function numberFormat(decimals) {
  const key = decimals == null ? null : decimals;
  let f = NUMBER_FORMATS.get(key);
  if (!f) {
    f = new Intl.NumberFormat('en-US', key === null
      ? { maximumFractionDigits: 20 }
      : { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    if (NUMBER_FORMATS.size < 64) NUMBER_FORMATS.set(key, f);
  }
  return f;
}

/** The number options a property or a card declares ({digits, compact}); the later source wins. */
export function numOpts(...sources) {
  const out = {};
  for (const s of sources) {
    if (!s || typeof s !== 'object') continue;
    if (Number.isInteger(s.digits) && s.digits > 0) out.digits = s.digits;
    if (typeof s.compact === 'boolean') out.compact = s.compact;
  }
  return out;
}

/** Unix seconds as the reader's wall-clock time, "14:03:21.358" (a live dataset's time column, CONTRACT §26
    `display: clock`). WHY local time and milliseconds: an operator matches it against the room's clock and a host's
    log lines, and a 1 kHz stream has many rows a second. */
export function fmtClock(t) {
  if (!isNum(t)) return '';
  const d = new Date(t * 1000);
  const two = (n) => String(n).padStart(2, '0');
  return `${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}.${String(d.getMilliseconds()).padStart(3, '0')}`;
}

/** How long ago, in plain words: "0.4 s ago", "12 s ago", "3 min ago", "1.5 h ago", "2 d ago"; a negative age (a
    clock ahead of ours) reads "in 1.2 s", never a made-up 0 (CONTRACT §26 `display: age`). */
export function fmtAge(seconds) {
  if (!isNum(seconds)) return '';
  const a = Math.abs(seconds);
  const text = a < 10 ? `${a.toFixed(1)} s` : a < 60 ? `${Math.round(a)} s` : a < 3600 ? `${Math.round(a / 60)} min` : a < 86400 ? `${(a / 3600).toFixed(1)} h` : `${Math.round(a / 86400)} d`;
  return seconds < 0 ? `in ${text}` : `${text} ago`;
}

/** The display string a producer wrote on a rich cell (`{value: [15, 60], text: "15 to 60"}`, docs/CONTRACT.md §22), or
    null: a plain cell, a rich cell without one, a text that is empty or not a string. WHY exactly as written: Zach's
    truthful-rendering rule; the text is never trimmed, rounded or re-cased, and only drawing reads it (sorting, filters,
    groups, summaries, the rail and Copy keep `.value`). */
export function cellText(cell) {
  return cell !== null && typeof cell === 'object' && !Array.isArray(cell) && typeof cell.text === 'string' && cell.text !== '' && 'value' in cell ? cell.text : null;
}

/** A rich cell with a new value: its other keys stay. Not `text`, which is how the old value was written (§22) and would draw over the
    new one, an edit silently lost; nor `sources`: a value set in a formula's cell is no new list of sources, and §36 refuses it as what
    it is. A reason for a missing value stops being true once there is a value. */
export function withValue(cell, value) {
  const { why, text, sources, ...rest } = cell;
  return isEmpty(value) && why ? { ...rest, value, why } : { ...rest, value };
}

/** A media cell's attachments (docs/CONTRACT.md §37): `{value: "words", attachments: [{url, kind, name?, caption?, missing?}]}`;
    [] for any other cell. Filters, sorts, groups, search and Copy read `.value`, the words, as for every rich cell. */
export function attachmentsOf(cell) {
  return cell !== null && typeof cell === 'object' && !Array.isArray(cell) && Array.isArray(cell.attachments) ? cell.attachments.filter((a) => a && typeof a === 'object') : [];
}

/** A media cell's thumbnails: each a button (`data-thumb` its place in the cell's list) that opens it large; one a peer's
    sync has not brought yet says so in words, never a broken image. `dataset` resolves a relative url. '' with none. */
export function thumbsHtml(cell, dataset) {
  const list = attachmentsOf(cell);
  if (!list.length) return '';
  const away = list.filter((a) => a.missing || !a.url).length;
  const here = list.map((a, i) => [a, i]).filter(([a]) => !(a.missing || !a.url));
  const tile = ([a, i]) => {
    const url = esc(mediaUrl(a.url, dataset));
    const word = a.kind === 'video' ? 'video' : 'image';
    const inner = a.kind === 'video' ? `<video src="${url}#t=0.1" preload="metadata" muted playsinline aria-hidden="true"></video><span class="dv-mc-play" aria-hidden="true">▶</span>` : `<img src="${url}" alt="" loading="lazy" decoding="async" draggable="false">`;
    return `<button type="button" class="dv-mc-thumb" data-thumb="${i}" tabindex="-1" aria-label="Open ${word}: ${esc(a.caption || a.name || word)}" title="${esc(a.caption || a.name || word)}">${inner}</button>`;
  };
  return `<span class="dv-mc-thumbs">${here.map(tile).join('')}${away ? `<span class="dv-mc-away">${away} not on this machine yet</span>` : ''}</span>`;
}

/** A value as plain text (lists joined, numbers formatted, labels mapped); a rich cell that carries `text` reads as it. */
export function valueText(v, prop) {
  const x = cellValue(v);
  if (isEmpty(x)) return '';
  const shown = cellText(v);
  if (shown !== null) return shown;
  // a typed column (CONTRACT §28) writes its type's text: 25%, $70.00, Oct 26, 2026; an untyped one is as before
  if (prop && hasFormat(prop)) return formatText(x, prop);
  if (prop && prop.display === 'clock' && isNum(x)) return fmtClock(x);
  if (Array.isArray(x)) return x.map((y) => (prop && prop.labels && prop.labels[y] !== undefined ? prop.labels[y] : y)).join(', ');
  if (prop && prop.labels && prop.labels[x] !== undefined) return String(prop.labels[x]);
  return isNum(x) ? String(fmtNum(x, prop && prop.decimals, numOpts(prop))) : String(x);
}

/** Whether a value is something a link may open: an absolute http(s) URL, or a relative reference (a path, a query or a
    fragment: it holds a / . ? or #) that the view resolves as it resolves paths. Anything else is not: another scheme
    (`account:…`, `mailto:`, `javascript:`), a bare id ("acct-1234", no / . ? #), a value with spaces, a number, empty.
    WHY (docs/CONTRACT.md §22, 2026-10-30): a private source (a supplier chat) has no public URL, and an <a> that opens
    nothing, or runs script, is not a link; it reads as its label. */
export function isLinkTarget(value) {
  if (typeof value !== 'string') return false;
  const s = value.trim();
  if (!s || /\s/.test(s)) return false;
  const scheme = /^([a-z][a-z0-9+.-]*):/i.exec(s);
  if (scheme) {
    if (!/^https?$/i.test(scheme[1])) return false;
    try { return !!new URL(s).host; } catch { return false; }
  }
  return /[/.?#]/.test(s);
}

/** A `display: link` cell: an <a> to its value when the value is a link target (isLinkTarget), labelled by the cell's
    `text` when it has one (exactly as written), else by the value (without its http(s):// when `strip`); otherwise the
    same label as plain text, no <a>. '' for an empty value (the caller draws its "—"). `href(value)` maps the value to
    the address (the side peek resolves it against the data file); `cls` is the anchor's class. */
export function linkCell(cell, { href = (v) => v, cls = '', strip = true, rel = true } = {}) {
  const v = cellValue(cell);
  if (isEmpty(v) || Array.isArray(v)) return '';
  const value = String(v);
  const shown = cellText(cell);
  if (!isLinkTarget(value)) return esc(shown !== null ? shown : value);
  const label = shown !== null ? shown : strip ? value.replace(/^https?:\/\//, '') : value;
  return `<a${cls ? ` class="${esc(cls)}"` : ''} href="${esc(href(value))}"${rel ? ' rel="noopener"' : ''}>${esc(label)}</a>`;
}

/* Where a value came from, for the right-click popover (src/sources-menu.js, docs/CONTRACT.md §22). Built only when the
   cell carries a provenance field, so a plain value costs one `in` test and a table page renders as fast as before. */
const PROVENANCE_FIELDS = ['basis', 'source', 'sourceUrl', 'sourcePage', 'asOf', 'record', 'note'];
const PROVENANCE_TRIGGERS = ['basis', 'source', 'sourceUrl', 'sourcePage', 'asOf', 'record'];

/** The `data-provenance` attribute (leading space included) for a rich cell, or '' when it names no source, as-of,
    record or basis. `plain` is the text the cell shows; `unit` its unit. Keys with no value are left out. */
export function provenanceAttr(rich, plain, unit) {
  if (!rich) return '';
  let any = false;
  for (const k of PROVENANCE_TRIGGERS) if (!isEmpty(rich[k])) { any = true; break; }
  if (!any) return '';
  const p = { value: plain };
  // WHY `value` stays the stored value and `text` rides beside it: the popover's value line is the text, and Copy
  // citation writes the value (CONTRACT §22, `text`)
  const shown = cellText(rich);
  if (shown !== null && shown !== plain) p.text = shown;
  if (unit) p.unit = unit;
  for (const k of PROVENANCE_FIELDS) if (!isEmpty(rich[k])) p[k] = String(rich[k]);
  return ` data-provenance="${esc(JSON.stringify(p))}"`;
}

/** The mark a view writes on the element that draws a value two or more sources state (CONTRACT §36, the source
    popover): ` data-src-row="<row id>" data-src-p="<property>"` (and ` tabindex="0"` with `focusable`, for a record's or
    a peek's field, which are no tab stops otherwise), '' for any other cell. <data-views> opens the value's sources from
    it (a right-click, the menu key on it or on its row or card), and sources.js leaves it to that menu. The raw cell and
    its resolved nominal (which keeps `sources`) are marked alike; a value with one source or none keeps today's menu. */
export function sourcesAttr(cell, id, property, { focusable = false } = {}) {
  if (!isMultiSource(cell) || stated(cell).length < 2) return '';
  return ` data-src-row="${esc(id)}" data-src-p="${esc(property)}"${focusable ? ' tabindex="0"' : ''}`;
}

/** A value exactly as stored, as text: every stored digit of a number (never rounded, never an exponent), a list
    joined, anything else as written. WHY (judge r2 #4, Zach's truthful-rendering rule): a type may round what it draws
    ($123.46, 0%), so a typed value's hover and its detail say this instead. */
export function exactText(v) {
  const x = cellValue(v);
  if (isEmpty(x)) return '';
  if (Array.isArray(x)) return x.map((y) => exactText(y)).join(', ');
  return isNum(x) ? exactNumber(x) : String(x);
}

/** A number's every stored digit: JavaScript's own shortest round-trip text (String(n), lossless), its exponent spelled
    out as zeros, its integer part grouped. WHY not fmtNum (judge r3 #3): Intl stops at 20 decimals, so 1e-21 and
    Number.MIN_VALUE read "0" in the one place that promises the value as stored. */
function exactNumber(n) {
  // WHY "-0" (judge r4 #4): it is what is stored, and a currency draws it "-$0.00"; the as-stored text says so too
  if (Object.is(n, -0)) return '-0';
  const raw = String(n);
  const neg = raw.startsWith('-');
  let [mant, exp] = (neg ? raw.slice(1) : raw).split('e');
  let [int, frac = ''] = mant.split('.');
  const e = exp === undefined ? 0 : Number(exp);
  if (e > 0) { frac = frac.padEnd(e, '0'); int += frac.slice(0, e); frac = frac.slice(e); }
  else if (e < 0) { frac = '0'.repeat(-e - int.length) + int + frac; int = '0'; }
  int = int.replace(/^0+(?=\d)/, '');
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return `${neg ? '-' : ''}${grouped}${frac ? '.' + frac : ''}`;
}

/** `display: source`, the "<label> source" column's cell (CONTRACT §36): {value: the name a source goes by, url?, derived?}. A link to
    where it can be opened when that is a link target (an http(s) URL or a relative path, resolved against the data file), else a plain
    label: a private source has no address (§22). A derived value says so: what is named is what it was derived from. */
function sourceHtml(cell, dataset) {
  const name = esc(cell.value);
  const on = isLinkTarget(cell.url) ? `<a class="dv-src-link" href="${esc(mediaUrl(cell.url, dataset))}" target="_blank" rel="noopener">${name}</a>` : `<span class="dv-src-label">${name}</span>`;
  return `<span class="dv-src-in">${on}${cell.derived ? '<span class="dv-src-derived" title="Derived: computed from other values; the source beside it is what it was derived from">derived</span>' : ''}</span>`;
}

/** A cell's HTML: the value, its unit (unless units: column), its range and basis mark, source and as-of on hover.
    The same markup <data-value> draws, so a table cell and a datasheet value look alike.
    `unit` overrides the property's unit text ('' hides it); `mark: false` draws no basis mark (a view that names the
    value's source beside it: the table's Nominal source column, CONTRACT §36), the basis staying in the hover.
    `detail: true` (the peek, a record): a typed value whose drawing differs from its stored text shows that text beside it.
    `dataset`: what a relative address resolves against. */
export function valueHtml(cell, prop = {}, { unit, mark: withMark = true, detail = false, rel = null, dataset = null } = {}) {
  // a status (docs/CONTRACT.md §35): its glyph and its word in its tone, wherever a cell is written (the peek, the record)
  if (prop && prop.display === 'status') return statusHtml(cell, prop);
  const rich = cell !== null && typeof cell === 'object' && !Array.isArray(cell) && 'value' in cell ? cell : null;
  const v = rich ? rich.value : cell;
  if (isEmpty(v)) {
    const why = (rich && rich.why) || 'no value';
    return `<span class="dv-none" title="${esc(why)}">—</span>`;
  }
  if (prop.display === 'source' && rich) return sourceHtml(rich, dataset);
  // WHY a block, not a span: a README or a model's description is a document (CONTRACT §16 `display: markdown`)
  if (prop.display === 'markdown' && typeof v === 'string') return `<div class="dv-md">${markdown(v)}</div>`;
  // a typed column's own drawing (pills, a status, a bar, a check…; CONTRACT §28), when the cell is a plain value
  const typed = hasFormat(prop);
  const exact = typed ? exactText(v) : '';
  // the stored text beside a typed drawing that does not already say it (a detail view's job; judge r2 #4)
  const echo = (shown) => (detail && typed && exact !== shown ? ` <span class="dv-exact" title="as stored">${esc(exact)}</span>` : '');
  if (!rich && typed) {
    // `rel` (relationContext): a relation's titles and its open buttons, from the view that draws it
    const html = typedHtml(v, prop, { dataset: prop.dataset, ...(rel || {}) });
    // the echo compares with what the drawing says (25.00%, Nov 14, 2026); a pill already says its stored label
    if (html) return `<span class="dv-typed" title="${esc(exact)}">${html}${echo(formatText(v, prop))}</span>`;
  }
  const u = unit !== undefined ? unit : (rich && rich.unit) || prop.unitText || '';
  // WHY once: the text is the cell and the first line of its hover title; formatting it twice doubled a table page's cost
  const plain = valueText(v, prop);
  // WHY the title keeps `plain`: the hover shows the stored value when the cell shows the producer's text (CONTRACT §22)
  const shown = rich ? cellText(rich) : null;
  let text = esc(shown !== null ? shown : plain);
  if (rich && (isNum(rich.low) || isNum(rich.high))) {
    text += ` <span class="dv-range">${esc(fmtNum(rich.low, prop.decimals, numOpts(prop)) ?? '')}–${esc(fmtNum(rich.high, prop.decimals, numOpts(prop)) ?? '')}</span>`;
  }
  const basis = rich && rich.basis ? BASIS[rich.basis] : null;
  const title = [
    `${typed ? exact : plain}${u ? ' ' + u : ''}`,
    rich && rich.basis ? `${rich.basis}${basis ? ': ' + basis.means : ''}` : '',
    rich && isNum(rich.n) ? `n = ${rich.n}` : '',
    rich && rich.source ? `source: ${rich.source}` : '',
    rich && rich.asOf ? `as of ${rich.asOf}` : '',
    rich && rich.note ? rich.note : '',
  ].filter(Boolean).join('\n');
  const mark = withMark && rich && rich.basis ? `<span class="dv-basis dv-basis-${esc(rich.basis)}" aria-label="${esc(rich.basis)}">${esc(basis ? basis.mark : '?')}</span>` : '';
  // WHY the cell's own unit, not `unit`: a column that hides its unit (units: column) still names it in the popover
  const provenance = rich ? provenanceAttr(rich, plain, rich.unit || prop.unitText || '') : '';
  return `<span class="dv-value" title="${esc(title)}"${provenance}>${text}${u ? ` <span class="dv-u">${esc(u)}</span>` : ''}${mark}${echo(plain)}</span>`;
}

/** A property's label, and a group's heading ("No form" for an empty key). */
export function propLabel(columns, id) {
  return (columns[id] && columns[id].label) || id;
}

/** A time level's group (`by:` on the level; the row model marks its column) reads as its bucket, whether a view passes
   the group's key or a row's date: "Week of 19 Oct 2026". */
export function groupLabel(columns, property, key) {
  const p = columns[property];
  if (p && p.by && !isEmpty(key)) key = bucketLabel(key, p.by);
  // a binned level (`bins:`; the row model puts the level's buckets on its column) reads as its bucket, from a key or
  // from a row's number: "250 mL – 1 L" (docs/CONTRACT.md §20)
  if (p && Array.isArray(p.bins) && !isEmpty(key)) {
    const b = p.bins.find((x) => x.key === key) || p.bins.find((x) => x.key === binKey(key, p.bins));
    key = b ? b.label : null;
  }
  if (isEmpty(key)) return `No ${propLabel(columns, property).toLowerCase()}`;
  if (Array.isArray(key)) return key.join(', ');
  if (p && p.labels && p.labels[key] !== undefined) return String(p.labels[key]);
  // WHY only when digits or compact is declared: a group over a number reads its key as stored (1149, not 1,149) unless
  // the .base declared the rounding (CONTRACT §17), then it reads as the cells under it do
  if (p && isNum(key)) {
    const opts = numOpts(p);
    if (opts.digits || opts.compact) return String(fmtNum(key, p.decimals, opts));
  }
  return String(key);
}

const BADGE_HUES = 8;
/** A stable series slot (1-8) for a text value, so a badge keeps its colour whatever else is on the page. */
export function hueOf(text) {
  let h = 0;
  for (const c of String(text)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return (h % BADGE_HUES) + 1;
}

export const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
/** A date the way an admin index writes it, relative to `now` (CONTRACT §43): "Today",
    "Yesterday", "Tomorrow", "Apr 10" in this year, "Jul 25, 2023" in any other. A date-only ISO text ("2026-04-10") is
    that calendar day wherever the reader is (never shifted by the time zone). Returns null for text that is not a date;
    the caller keeps the stored text as the cell's title, so the year a short date drops is one hover away.
    WHY relative to the year, not "3 days ago": Shopify's index tables (Zach's Tycoon S6 screenshots, 2026-10-28) */
export function shortDate(value, now = new Date()) {
  const text = String(cellValue(value) ?? '');
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:$|T)/.exec(text);
  const d = m && text.length === 10 ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : m ? new Date(text) : null;
  if (!d || Number.isNaN(d.getTime())) return null;
  const day = (x) => Math.round(new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime() / 86400000);
  const diff = day(d) - day(now);
  if (diff === 0) return 'Today';
  if (diff === -1) return 'Yesterday';
  if (diff === 1) return 'Tomorrow';
  const md = `${MONTHS[d.getMonth()]} ${d.getDate()}`;
  return d.getFullYear() === now.getFullYear() ? md : `${md}, ${d.getFullYear()}`;
}

/** A relative image or file path in a cell, as a URL: resolved against the data file's URL (`dataset.url`), never
    against the page (docs/CONTRACT.md §1, amendment 2026-10-26). An absolute URL, a data: or blob: URL passes through.
    WHY in the core: the chart, cards, kanban, compare, list and record views each derived the data URL from the
    element's attributes by hand; one rule here keeps them from drifting. */
export function mediaUrl(src, dataset) {
  if (isEmpty(src)) return src;
  const text = String(src);
  const page = typeof document !== 'undefined' ? document.baseURI : undefined;
  try { return new URL(text, (dataset && dataset.url) || page).href; } catch { return text; }
}

// §46: what a markdown cell summarises: pure and on its own, so another host (an Obsidian plugin) can take the one file
export { outlineOf, mediaOf, sectionCell, isDerivedCell } from './section-summary.js';
