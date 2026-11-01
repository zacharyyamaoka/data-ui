/* LiveDataset: a dataset that is still growing (docs/peps/0012-live-data.md §3, docs/CONTRACT.md §26).

   Zach, 2026-10-26: "with foxglove you can do playback (which is like the static dataset) or you can do streaming.
   actually I really like rerun.. you kinda do streaming but at any moment you can just kinda like 'rewind'". So a live
   dataset is the static dataset that has not stopped growing, and every view reads it as of the clock's t.

   Two kinds, one class:
     append  rows that grow with time (samples, events, level changes). Each stream (the rows sharing a value of
             `stream:`) holds chunks of up to 4,096 rows in time order, one typed array per number column, so 60,000
             samples a second never become 60,000 objects; a row object is made only when a view reads that row.
     keyed   rows replaced by `key:` (a tree, checks, configuration). Each replacement is a version at its time, so
             the record at t is its newest version then (rewinding a table is a latest-at query).
   Two questions answer every view (Rerun's query model): latestAt(t) and range(a, b]. snapshot(t) is the rows a
   row-reading view gets, newest first.

   Memory is a ring with a byte budget (256 MB per page by default, decided 2026-10-27): over it, the oldest sealed
   chunk of any live dataset goes, then the next; the newest chunk of every stream and the newest version of every key
   always stay (Rerun's protect_latest), and the minute before a paused clock's t goes last.

   Changes are published once per animation frame (live/frame.js), never per row. A reader that reads only what is new
   (live/model.js's Tail, the plot's ColumnCache, a paused view deciding whether to draw) keeps up through two logs:
   dropsSince() (what retention took) and reordersSince() (rows that went in before newer rows of their stream).
   STOCK PARTS: typed arrays and EventTarget; the chunk shape copies Rerun's (re_chunk) without its Arrow encoding. */

import { markDataset } from './frame.js';
import { inferProperties } from '../data.js';

export const CHUNK_ROWS = 4096;     // Rerun's compaction threshold (store-compaction.md)
export const CHUNK_SPAN = 10;       // s of data time: a slow stream still seals, and age retention is exact to 10 s
export const PROTECT_S = 60;        // s before a paused clock's t that eviction keeps while it can
const ROW_BYTES = 64;               // an estimate for one materialized row object
const VALUE_BYTES = 16;             // an estimate for one non-number value
const LOG = 4096;                   // drop-log entries kept for incremental readers (live/model.js)

let BUDGET = 256 * 2 ** 20;
const LIVE = new Set();             // every live dataset holding data: the page budget spans them

// ------------------------------------------------------------------ parsing the .base's words

/** '256MB', '1.5GB', '64 KB', 1000 → bytes (KB = 1,024); anything else → null. */
export function parseBytes(x) {
  if (typeof x === 'number') return Number.isFinite(x) && x >= 0 ? x : null;
  const m = /^\s*(\d+(?:\.\d+)?)\s*(B|KB|MB|GB)?\s*$/i.exec(String(x ?? ''));
  if (!m) return null;
  return Number(m[1]) * { b: 1, kb: 1024, mb: 2 ** 20, gb: 2 ** 30 }[(m[2] || 'B').toLowerCase()];
}

/** '30s', '500ms', '15m', '2h', 5 → seconds; anything else → null. */
export function parseDuration(x) {
  if (typeof x === 'number') return Number.isFinite(x) && x >= 0 ? x : null;
  const m = /^\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h)\s*$/.exec(String(x ?? ''));
  if (!m) return null;
  return Number(m[1]) * { ms: 0.001, s: 1, m: 60, h: 3600 }[m[2]];
}

/** The page's buffer for every live dataset (bytes, or '256MB'); over it the oldest chunks go first. */
export function setLiveBudget(bytes) {
  const n = parseBytes(bytes);
  if (n === null) return;
  BUDGET = n;
  enforcePage();
}
export function liveBudget() { return BUDGET; }

export function isLiveDataset(x) { return !!(x && typeof x === 'object' && x.live === true && typeof x.snapshot === 'function'); }

// ------------------------------------------------------------------ chunks

const isNumType = (p) => p && (p.type === 'number' || p.type === 'integer');
/** A number column's value: a number, a rich cell's number, else null. */
const numberIn = (v) => (typeof v === 'number' ? v : v !== null && typeof v === 'object' && typeof v.value === 'number' ? v.value : null);
const valueBytes = (v) => (v === null || v === undefined ? 8 : typeof v === 'string' ? 2 * v.length + VALUE_BYTES : typeof v === 'object' ? 4 * VALUE_BYTES : VALUE_BYTES);

class Chunk {
  constructor(stream, nums, anys, cap = 16) {
    this.stream = stream;
    this.n = 0;
    this.cap = cap;
    this.t = new Float64Array(cap);
    this.seq = new Float64Array(cap);
    this.num = {};
    for (const k of nums) this.num[k] = new Float64Array(cap);
    this.any = {};
    for (const k of anys) this.any[k] = new Array(cap);
    this.anyBytes = 0;
    // a number column's rich cells ({value, unit, …}), by index, made on the first one: the typed array holds the
    // value, this the cell as it came (CONTRACT §26's addendum: a typed number column keeps a cell's unit)
    this.rich = null;
    this.rows = null;       // materialized row objects, by index
    this.rowBytes = 0;
    this.sealed = false;
  }

  get t0() { return this.n ? this.t[0] : Infinity; }
  get t1() { return this.n ? this.t[this.n - 1] : -Infinity; }
  get seqMin() { let m = Infinity; for (let i = 0; i < this.n; i++) if (this.seq[i] < m) m = this.seq[i]; return m; }
  get seqMax() { let m = -Infinity; for (let i = 0; i < this.n; i++) if (this.seq[i] > m) m = this.seq[i]; return m; }
  get bytes() { return this.cap * 8 * (2 + Object.keys(this.num).length) + this.anyBytes + this.rowBytes; }

  grow() {
    const cap = Math.min(CHUNK_ROWS, this.cap * 2);
    const up = (a) => { const b = new Float64Array(cap); b.set(a.subarray(0, this.n)); return b; };
    this.t = up(this.t);
    this.seq = up(this.seq);
    for (const k of Object.keys(this.num)) this.num[k] = up(this.num[k]);
    for (const k of Object.keys(this.any)) this.any[k].length = cap;
    if (this.rich) for (const k of Object.keys(this.rich)) this.rich[k].length = cap;
    this.cap = cap;
  }

  /** Trim the arrays to the rows they hold (sealed chunks never grow). */
  seal() {
    if (this.sealed) return;
    this.sealed = true;
    if (this.cap === this.n) return;
    const cut = (a) => a.slice(0, this.n);
    this.t = cut(this.t);
    this.seq = cut(this.seq);
    for (const k of Object.keys(this.num)) this.num[k] = cut(this.num[k]);
    for (const k of Object.keys(this.any)) this.any[k].length = this.n;
    if (this.rich) for (const k of Object.keys(this.rich)) this.rich[k].length = this.n;
    this.cap = this.n;
  }

  /** Put a number column's value at i: a number as it is; a rich cell's value in the typed array and the cell beside
      it; anything else NaN (no value). Returns the bytes the cell added. */
  setNum(k, i, v) {
    if (typeof v === 'number') { this.num[k][i] = v; if (this.rich && this.rich[k]) this.rich[k][i] = undefined; return 0; }
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      this.num[k][i] = typeof v.value === 'number' ? v.value : NaN;
      // WHY the cell beside the number: its unit (and its basis, range, reason) is part of it, and a row read back
      // carries the cell as it came, as a file's does (RobotDx PEP 0001 §18.4, ask 4: a KPI card lost the unit of a
      // typed reading, so RobotDx typed it as nothing); range() still reads the typed array (the plots)
      const rich = this.rich || (this.rich = {});
      (rich[k] || (rich[k] = new Array(this.cap)))[i] = v;
      const b = valueBytes(v);
      this.anyBytes += b;
      return b;
    }
    this.num[k][i] = NaN;
    if (this.rich && this.rich[k]) this.rich[k][i] = undefined;
    return 0;
  }

  /** The index of the last row with t <= x (-1 if none). */
  lastAtOrBefore(x) {
    let lo = 0, hi = this.n - 1, ans = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (this.t[m] <= x) { ans = m; lo = m + 1; } else hi = m - 1; }
    return ans;
  }
}

// ------------------------------------------------------------------ the dataset

export class LiveDataset extends EventTarget {
  /**
   * {id, title, titleProperty, linkProperty, imageProperty, properties, rows?, time, stream?, key?,
   *  retention?: {bytes, age}, stale?, url?, recorded?}
   * `time` (seconds) is required; `key` makes it keyed; `rows` is a backlog appended at once.
   */
  constructor(opts = {}) {
    super();
    const { id = 'live', title, titleProperty, linkProperty, imageProperty, properties, rows, time, stream = null, key = null, retention = {}, stale = 5, url = null } = opts;
    if (!time) throw new Error('a live dataset needs time: (the time property, in seconds)');
    this.id = id;
    this.title = title || id;
    this.properties = properties && Object.keys(properties).length ? { ...properties } : (rows && rows.length ? inferProperties(rows) : {});
    if (!this.properties[time]) this.properties[time] = { type: 'number', unit: 's', label: 'Time' };
    this.titleProperty = titleProperty || (key && this.properties[key] ? key : Object.keys(this.properties).find((p) => p !== time) || time);
    this.linkProperty = linkProperty;
    this.imageProperty = imageProperty;
    this.url = url;
    this.time = time;
    this.stream = key ? null : stream;
    this.key = key;
    this.retention = { bytes: parseBytes(retention.bytes ?? null), age: parseDuration(retention.age ?? null) };
    this.staleAfter = parseDuration(stale) ?? 5;
    this.late = 0;
    this._seq = 0;
    this._streams = new Map();   // append: name -> {name, chunks: [Chunk], sealedT1}
    this._keys = new Map();      // keyed: key -> [{t, seq, row, removed}]
    this._keyBytes = 0;
    this._bytes = 0;             // append: kept up to date on every write, seal, drop and row made (never summed)
    this._rows = 0;
    this._start = null;
    this._end = null;
    this._recorded = false;
    this._status = { state: 'connecting', since: Date.now(), detail: '', lastData: 0, tries: 0 };
    this._pending = null;
    this._drops = [];            // [{gen, stream, seqMin, seqMax, t0, t1}] for incremental readers (keyed: stream = the key)
    this._dropGen = 0;
    this._reorders = [];         // [{gen, stream, t}]: rows that went in before newer rows of their stream
    this._reorderGen = 0;
    this._resets = 0;
    this._clocks = new Set();    // clocks bound to this dataset: a paused one protects its minute
    const nums = [], anys = [];
    for (const [k, p] of Object.entries(this.properties)) {
      if (k === time || k === this.stream || k === 'id') continue;
      (isNumType(p) ? nums : anys).push(k);
    }
    anys.push('id');
    this._nums = nums;
    this._numSet = new Set(nums);
    this._anys = anys;
    if (rows && rows.length) (key ? this.upsert(rows) : this.append(rows));
    if (opts.recorded) this.finish();
  }

  get live() { return true; }
  get keyed() { return !!this.key; }
  get recorded() { return this._recorded; }
  get start() { return this._start; }
  get end() { return this._end; }
  get rowCount() { return this._rows; }
  get status() { return { ...this._status }; }
  get bytes() { return this._bytes + this._keyBytes; }
  /** A dataset-shaped `rows`: the newest 2,000, in time order (what the dashboard's rails, links and roll-ups read of
      a live dataset). WHY capped: a live dataset may hold millions of rows; a view reads snapshot() at its own t. */
  get rows() { return this.snapshot(Infinity, { at: 'all', limit: 2000 }).reverse(); }

  /** The streams (append: the values of `stream:`; keyed: the keys). */
  streams() { return this.key ? [...this._keys.keys()] : [...this._streams.keys()]; }

  // ---------------------------------------------------------------- writing

  /** Append rows (objects, in time order per stream). A keyed dataset upserts them. Returns how many went in. */
  append(rows) {
    if (this.key) return this.upsert(rows);
    if (this._recorded || !rows || !rows.length) return 0;
    const time = this.time, sp = this.stream, nums = this._nums, anys = this._anys;
    const arrival = Date.now() / 1000;
    let n = 0, lo = Infinity, hi = -Infinity;
    const touched = new Set();
    for (const r of rows) {
      if (!r || typeof r !== 'object') continue;
      let t = r[time];
      if (typeof t !== 'number' || !Number.isFinite(t)) t = arrival;
      const s = sp ? String(r[sp] ?? '') : '';
      const st = this._stream(s);
      if (t < st.sealedT1) { this.late++; continue; }
      const c = this._open(st, t);
      const i = this._slot(c, t);
      c.t[i] = t;
      c.seq[i] = ++this._seq;
      for (const k of nums) this._bytes += c.setNum(k, i, r[k]);
      for (const k of anys) { const v = r[k] ?? null; c.any[k][i] = v; const b = valueBytes(v); c.anyBytes += b; this._bytes += b; }
      st.count++;
      n++;
      touched.add(s);
      if (t < lo) lo = t;
      if (t > hi) hi = t;
    }
    if (!n) return 0;
    this._afterWrite(n, lo, hi, touched, 'appended');
    return n;
  }

  /** Append columns: {<property>: array}, every array as long as the time column, for one stream. No row objects. */
  appendColumns(cols, { stream = '' } = {}) {
    if (this.key) throw new Error('appendColumns is for an append dataset; a keyed dataset upserts rows');
    if (this._recorded || !cols) return 0;
    const ts = cols[this.time];
    if (!ts || !ts.length) return 0;
    const st = this._stream(String(stream ?? ''));
    let n = 0, lo = Infinity, hi = -Infinity;
    for (let j = 0; j < ts.length; j++) {
      const t = ts[j];
      if (typeof t !== 'number' || !Number.isFinite(t) || t < st.sealedT1) { this.late++; continue; }
      const c = this._open(st, t);
      const i = this._slot(c, t);
      c.t[i] = t;
      c.seq[i] = ++this._seq;
      for (const k of this._nums) { const a = cols[k]; this._bytes += c.setNum(k, i, a ? a[j] : null); }
      for (const k of this._anys) { const a = cols[k]; const v = a ? a[j] ?? null : null; c.any[k][i] = v; const b = valueBytes(v); c.anyBytes += b; this._bytes += b; }
      st.count++;
      n++;
      if (t < lo) lo = t;
      if (t > hi) hi = t;
    }
    if (n) this._afterWrite(n, lo, hi, new Set([st.name]), 'appended');
    return n;
  }

  /** Keyed: replace each row's record by its key (a version at row[time], or now). */
  upsert(rows) {
    if (!this.key) return this.append(rows);
    if (this._recorded || !rows || !rows.length) return 0;
    const arrival = Date.now() / 1000;
    let n = 0, lo = Infinity, hi = -Infinity;
    const touched = new Set();
    for (const r of rows) {
      if (!r || typeof r !== 'object' || r[this.key] === undefined || r[this.key] === null) continue;
      const k = String(r[this.key]);
      let t = r[this.time];
      if (typeof t !== 'number' || !Number.isFinite(t)) t = arrival;
      const row = { ...r, id: k, [this.time]: t };
      this._version(k, t, row, false);
      n++;
      touched.add(k);
      if (t < lo) lo = t;
      if (t > hi) hi = t;
    }
    if (n) this._afterWrite(n, lo, hi, touched, 'upserted');
    return n;
  }

  /** Keyed: the records of `keys` are gone from t on (default now). */
  remove(keys, t = Date.now() / 1000) {
    if (!this.key || this._recorded) return 0;
    let n = 0;
    const touched = new Set();
    for (const key of keys || []) {
      const k = String(key);
      if (!this._keys.has(k)) continue;
      this._version(k, t, null, true);
      n++;
      touched.add(k);
    }
    if (n) this._afterWrite(n, t, t, touched, 'removed');
    return n;
  }

  /** Forget every row (the host started over: SSE `reset`). Properties and the connection stay. */
  clear() {
    this._streams.clear();
    this._keys.clear();
    this._keyBytes = 0;
    this._bytes = 0;
    this._rows = 0;
    this._start = this._end = null;
    this._resets++;
    this._dropGen++;
    this._drops = [];
    this._reorderGen++;
    this._reorders = [];
    LIVE.delete(this);
    this._note({ reset: true });
  }

  /** A finished recording: no more rows; the clock's end stops growing. */
  finish() {
    if (this._recorded) return;
    this._recorded = true;
    for (const s of this._streams.values()) for (const c of s.chunks) { const b0 = c.bytes; c.seal(); this._bytes += c.bytes - b0; }
    this.setStatus('recorded');
    this._note({ recorded: true });
  }

  /** The connection: connecting | live | stale | reconnecting | paused | closed | recorded (+ detail, try count). */
  setStatus(state, detail = '', tries = 0) {
    const s = this._status;
    if (s.state === state && s.detail === (detail || '') && s.tries === tries) return;
    this._status = { ...s, state, detail: detail || '', tries, since: Date.now() };
    this.dispatchEvent(new CustomEvent('status', { detail: this.status }));
    if (state === 'live' && this.staleAfter > 0) watchStale(this);
  }

  // ---------------------------------------------------------------- reading

  /** The newest row at or before t: of `stream` (append), of the key `stream` names (keyed), else of any. */
  latestAt(t, stream) {
    if (this.key) {
      if (stream !== undefined && stream !== null) { const v = this._versionAt(String(stream), t); return v && !v.removed ? v.row : null; }
      let best = null;
      for (const k of this._keys.keys()) { const v = this._versionAt(k, t); if (v && !v.removed && (!best || v.t > best.t || (v.t === best.t && v.seq > best.seq))) best = v; }
      return best ? best.row : null;
    }
    const pick = (st) => {
      for (let ci = st.chunks.length - 1; ci >= 0; ci--) {
        const c = st.chunks[ci];
        if (!c.n || c.t0 > t) continue;
        const i = c.lastAtOrBefore(t);
        if (i >= 0) return [c, i];
      }
      return null;
    };
    if (stream !== undefined && stream !== null) {
      const st = this._streams.get(String(stream));
      const hit = st && pick(st);
      return hit ? this._row(hit[0], hit[1]) : null;
    }
    let best = null;
    for (const st of this._streams.values()) {
      const hit = pick(st);
      if (hit && (!best || hit[0].t[hit[1]] > best[0].t[best[1]] || (hit[0].t[hit[1]] === best[0].t[best[1]] && hit[0].seq[hit[1]] > best[0].seq[best[1]]))) best = hit;
    }
    return best ? this._row(best[0], best[1]) : null;
  }

  /** Typed-array slices of (a, b] per stream: [{stream, t, cols, from, to, chunk}]; no row objects, no copies. */
  range(a, b, { stream = null, columns = null } = {}) {
    const out = [];
    if (this.key) {
      for (const [k, vs] of this._keys) {
        if (stream !== null && String(stream) !== k) continue;
        const hit = vs.filter((v) => v.t > a && v.t <= b && !v.removed);
        if (!hit.length) continue;
        const cols = {};
        // a number column's values, never its cells: what an append dataset's typed arrays give (a plot reads numbers)
        for (const p of columns || Object.keys(this.properties)) cols[p] = this._numSet.has(p) ? hit.map((v) => numberIn(v.row[p])) : hit.map((v) => v.row[p] ?? null);
        out.push({ stream: k, t: Float64Array.from(hit, (v) => v.t), cols, from: 0, to: hit.length, chunk: null });
      }
      return out;
    }
    const names = stream !== null ? [String(stream)] : [...this._streams.keys()];
    for (const name of names) {
      const st = this._streams.get(name);
      if (!st) continue;
      for (const c of st.chunks) {
        if (!c.n || c.t1 <= a || c.t0 > b) continue;
        const from = c.lastAtOrBefore(a) + 1, to = c.lastAtOrBefore(b) + 1;
        if (to <= from) continue;
        const cols = {};
        for (const p of columns || [...this._nums, ...this._anys]) {
          if (c.num[p]) cols[p] = c.num[p].subarray(from, to);
          else if (c.any[p]) cols[p] = c.any[p].slice(from, to);
        }
        out.push({ stream: name, t: c.t.subarray(from, to), cols, from, to, chunk: c });
      }
    }
    return out;
  }

  /**
   * The rows a view reads at t, NEWEST FIRST (time, then arrival): `at` is 'latest' (the newest of each stream / each
   * key's record), 'all' (every retained row at or before t) or a window in seconds or as written ('30s'); `limit`
   * caps it (default 2,000); `filter(row)` keeps rows (they count toward the limit only when kept).
   */
  snapshot(t, { at = 'all', limit = 2000, filter = null } = {}) {
    if (t === null || t === undefined) t = Infinity;
    const w = at === 'all' || at === 'latest' ? null : parseDuration(at);
    const lo = w === null ? -Infinity : t - w;
    const keep = filter || (() => true);
    const out = [];
    if (this.key) {
      for (const k of this._keys.keys()) {
        const v = this._versionAt(k, t);
        if (!v || v.removed || v.t <= lo) continue;
        if (keep(v.row)) out.push(v);
      }
      out.sort((x, y) => y.t - x.t || y.seq - x.seq);
      return out.slice(0, limit).map((v) => v.row);
    }
    if (at === 'latest') {
      for (const name of this._streams.keys()) {
        const r = this.latestAt(t, name);
        if (r && r[this.time] > lo && keep(r)) out.push(r);
      }
      out.sort((x, y) => y[this.time] - x[this.time] || y._seq - x._seq);
      return out.slice(0, limit);
    }
    // a k-way merge going back from t: one cursor per stream, the newest head first
    const heads = [];
    for (const st of this._streams.values()) {
      for (let ci = st.chunks.length - 1; ci >= 0; ci--) {
        const c = st.chunks[ci];
        if (!c.n || c.t0 > t) continue;
        const i = c.lastAtOrBefore(t);
        if (i >= 0) { heads.push({ st, ci, i }); break; }
      }
    }
    const newer = (x, y) => { const cx = x.st.chunks[x.ci], cy = y.st.chunks[y.ci]; return cx.t[x.i] > cy.t[y.i] || (cx.t[x.i] === cy.t[y.i] && cx.seq[x.i] > cy.seq[y.i]); };
    const heap = new Heap(newer);
    for (const h of heads) heap.push(h);
    while (heap.size && out.length < limit) {
      const h = heap.pop();
      const c = h.st.chunks[h.ci];
      if (c.t[h.i] <= lo) continue;   // past the window: this stream is done
      const r = this._row(c, h.i);
      if (keep(r)) out.push(r);
      if (h.i > 0) { h.i--; heap.push(h); }
      else {
        let ci = h.ci - 1;
        while (ci >= 0 && !h.st.chunks[ci].n) ci--;
        if (ci >= 0) { h.ci = ci; h.i = h.st.chunks[ci].n - 1; heap.push(h); }
      }
    }
    return out;
  }

  /** Rows that arrived after arrival number `afterSeq`, at or before t, in time order (live/model.js's Tail). It reads
      back from each stream's end and stops at the first older arrival: O(new rows). A row placed out of order inside
      the open chunk reaches a reader at its next full rebuild. */
  newRows(afterSeq, t = Infinity, limit = Infinity) {
    const out = [];
    for (const st of this._streams.values()) {
      scan: for (let ci = st.chunks.length - 1; ci >= 0; ci--) {
        const c = st.chunks[ci];
        for (let i = c.n - 1; i >= 0; i--) {
          if (c.seq[i] <= afterSeq || out.length >= limit) break scan;
          if (c.t[i] <= t) out.push(this._row(c, i));
        }
      }
    }
    out.sort((x, y) => x[this.time] - y[this.time] || x._seq - y._seq);
    return out;
  }

  /** How many retained rows lie at or before t inside the window (the status line's "of N rows"). */
  countAt(t, at = 'all') {
    if (this.key) return this.snapshot(t, { at: 'latest', limit: Infinity }).length;
    if (at === 'latest') return this._streams.size;
    const w = at === 'all' ? null : parseDuration(at);
    // rows after x, read back from the stream's end (near t, a chunk or two)
    const after = (st, x) => {
      let n = 0;
      for (let ci = st.chunks.length - 1; ci >= 0; ci--) {
        const c = st.chunks[ci];
        if (!c.n) continue;
        if (c.t1 <= x) break;
        n += c.n - (c.lastAtOrBefore(x) + 1);
      }
      return n;
    };
    let n = 0;
    for (const st of this._streams.values()) n += (w === null ? st.count : after(st, t - w)) - after(st, t);
    return n;
  }

  /** The arrival number of the newest row (incremental readers remember it). */
  get seq() { return this._seq; }
  /** What retention took since `gen`: [{gen, stream, seqMin, seqMax, t0, t1}] (an append chunk of `stream`; a keyed
      dataset's old versions of the key `stream`), or null when the log no longer reaches back that far. */
  dropsSince(gen) { return since(this._drops, this._dropGen, gen); }
  get dropGen() { return this._dropGen; }
  /** Rows that went in before newer rows of their stream since `gen` (an out-of-order arrival, placed in time order in
      the open chunk): [{gen, stream, t}], or null when the log no longer reaches back that far. WHY: a reader that
      reads only what is new at a stream's end (the Tail's newRows(), the plot's ColumnCache) cannot see such a row. */
  reordersSince(gen) { return since(this._reorders, this._reorderGen, gen); }
  get reorderGen() { return this._reorderGen; }
  get resets() { return this._resets; }

  // ---------------------------------------------------------------- inside

  _stream(name) {
    let st = this._streams.get(name);
    if (!st) { st = { name, chunks: [], sealedT1: -Infinity, count: 0 }; this._streams.set(name, st); }
    return st;
  }

  /** The stream's open chunk, sealing the current one when it is full or spans CHUNK_SPAN. */
  _open(st, t) {
    let c = st.chunks[st.chunks.length - 1];
    if (c && !c.sealed && (c.n >= CHUNK_ROWS || (c.n && t - c.t0 > CHUNK_SPAN))) { const b0 = c.bytes; c.seal(); this._bytes += c.bytes - b0; st.sealedT1 = c.t1; c = null; }
    if (!c || c.sealed) { c = new Chunk(st.name, this._nums, this._anys); st.chunks.push(c); this._bytes += c.bytes; }
    return c;
  }

  /** The index a row at t takes in the open chunk: the end, or in order for a row older than the newest. */
  _slot(c, t) {
    if (c.n === c.cap) { const b0 = c.bytes; c.grow(); this._bytes += c.bytes - b0; }
    const i = c.n;
    c.n++;
    if (i === 0 || c.t[i - 1] <= t) return i;
    // older than the newest: shift the newer ones up one (rare; the row cache's indexes move, so it goes)
    let j = i;
    while (j > 0 && c.t[j - 1] > t) j--;
    this._logReorder(c.stream, t);
    c.t.copyWithin(j + 1, j, i);
    c.seq.copyWithin(j + 1, j, i);
    for (const k of Object.keys(c.num)) c.num[k].copyWithin(j + 1, j, i);
    for (const k of Object.keys(c.any)) { const a = c.any[k]; for (let x = i; x > j; x--) a[x] = a[x - 1]; }
    if (c.rich) for (const k of Object.keys(c.rich)) { const a = c.rich[k]; for (let x = i; x > j; x--) a[x] = a[x - 1]; a[j] = undefined; }
    if (c.rows) { c.rows = null; this._bytes -= c.rowBytes; c.rowBytes = 0; }
    return j;
  }

  _row(c, i) {
    const rows = c.rows || (c.rows = []);
    let r = rows[i];
    if (r) return r;
    const id = c.any.id ? c.any.id[i] : null;
    r = { id: id !== null && id !== undefined ? String(id) : String(c.seq[i]) };
    r[this.time] = c.t[i];
    if (this.stream) r[this.stream] = c.stream;
    for (const k of this._nums) {
      const cell = c.rich && c.rich[k] ? c.rich[k][i] : undefined;
      if (cell !== undefined) { r[k] = cell; continue; }
      const v = c.num[k][i];
      r[k] = Number.isNaN(v) ? null : v;
    }
    for (const k of this._anys) if (k !== 'id') r[k] = c.any[k][i] ?? null;
    // WHY a hidden arrival number: ties in time order by arrival, and an incremental reader removes a dropped chunk's
    // rows by it; the underscore keeps it out of every view's columns (data.js skips _ keys)
    Object.defineProperty(r, '_seq', { value: c.seq[i], enumerable: false });
    rows[i] = r;
    const add = ROW_BYTES + VALUE_BYTES * (this._nums.length + this._anys.length);
    c.rowBytes += add;
    this._bytes += add;
    return r;
  }

  _version(k, t, row, removed) {
    let vs = this._keys.get(k);
    if (!vs) { vs = []; this._keys.set(k, vs); }
    const v = { t, seq: ++this._seq, row, removed };
    if (row) Object.defineProperty(row, '_seq', { value: v.seq, enumerable: false });
    let j = vs.length;
    while (j > 0 && vs[j - 1].t > t) j--;
    if (j < vs.length) this._logReorder(k, t);   // a late version, before newer ones of its key
    vs.splice(j, 0, v);
    this._keyBytes += ROW_BYTES + (row ? Object.keys(row).reduce((b, p) => b + valueBytes(row[p]), 0) : 8);
  }

  _versionAt(k, t) {
    const vs = this._keys.get(k);
    if (!vs) return null;
    let lo = 0, hi = vs.length - 1, ans = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (vs[m].t <= t) { ans = m; lo = m + 1; } else hi = m - 1; }
    return ans >= 0 ? vs[ans] : null;
  }

  _afterWrite(n, lo, hi, touched, kind) {
    // WHY: a host's time is Unix seconds; its column reads as a wall-clock time unless the data says how to draw it
    const tp = this.properties[this.time];
    if (hi >= 1e9 && tp && tp.display === undefined) this.properties[this.time] = { ...tp, display: 'clock' };
    this._rows += n;
    if (this._end === null || hi > this._end) this._end = hi;
    if (this._start === null || lo < this._start) this._start = lo;
    const s = this._status;
    this._status = { ...s, lastData: Date.now() };
    if (s.state === 'connecting' || s.state === 'stale') this.setStatus('live', '', 0);
    LIVE.add(this);
    this._note({ [kind]: n, streams: touched, from: lo, to: hi });
    enforce(this);
    enforcePage();
  }

  _note(what) {
    const p = this._pending || (this._pending = { appended: 0, upserted: 0, removed: 0, dropped: 0, streams: new Set(), reset: false, recorded: false, from: Infinity, to: -Infinity });
    for (const [k, v] of Object.entries(what)) {
      if (k === 'streams') for (const s of v) p.streams.add(s);
      else if (k === 'from') p.from = Math.min(p.from, v);
      else if (k === 'to') p.to = Math.max(p.to, v);
      else if (typeof v === 'number') p[k] += v;
      else if (v) p[k] = true;
    }
    markDataset(this);
  }

  /** The frame loop calls this once per frame: one `change` event with everything since the last. */
  _publish(frame) {
    const p = this._pending;
    if (!p) return;
    this._pending = null;
    // from / to: the oldest and newest time written this frame (a paused view whose t is before `from` skips the frame)
    this.dispatchEvent(new CustomEvent('change', { detail: { frame, start: this._start, end: this._end, appended: p.appended, upserted: p.upserted, removed: p.removed, dropped: p.dropped, streams: [...p.streams], reset: p.reset, recorded: p.recorded, from: Number.isFinite(p.from) ? p.from : undefined, to: Number.isFinite(p.to) ? p.to : undefined } }));
  }

  /** Ranges eviction keeps while it can: the minute before each bound clock that is paused. */
  _protected() {
    const out = [];
    for (const c of this._clocks) if (c && !c.following && Number.isFinite(c.t)) out.push([c.t - PROTECT_S, c.t]);
    return out;
  }

  /** The oldest chunk that may go (never a stream's newest; with `strict`, never one under a paused clock). */
  _victim(strict) {
    let best = null, bestSt = null;
    const prot = strict ? this._protected() : [];
    for (const st of this._streams.values()) {
      for (let ci = 0; ci < st.chunks.length - 1; ci++) {
        const c = st.chunks[ci];
        if (!c.sealed) break;
        if (prot.some(([a, b]) => c.t1 >= a && c.t0 <= b)) continue;
        if (!best || c.t1 < best.t1) { best = c; bestSt = st; }
        break;   // a stream's chunks are in time order: its first droppable one is its oldest
      }
    }
    return best ? { chunk: best, st: bestSt } : null;
  }

  _drop({ chunk, st }) {
    const i = st.chunks.indexOf(chunk);
    if (i < 0) return;
    st.chunks.splice(i, 1);
    this._rows -= chunk.n;
    st.count -= chunk.n;
    this._bytes -= chunk.bytes;
    this._logDrop(st.name, chunk.seqMin, chunk.seqMax, chunk.t0, chunk.t1);
    let s = Infinity;
    for (const x of this._streams.values()) if (x.chunks.length && x.chunks[0].n) s = Math.min(s, x.chunks[0].t0);
    this._start = Number.isFinite(s) ? s : this._start;
    this._note({ dropped: chunk.n, streams: [st.name] });
  }

  _logReorder(stream, t) {
    this._reorderGen++;
    this._reorders.push({ gen: this._reorderGen, stream, t });
    if (this._reorders.length > LOG) this._reorders.splice(0, this._reorders.length - LOG);
  }

  _logDrop(stream, seqMin, seqMax, t0, t1) {
    this._dropGen++;
    this._drops.push({ gen: this._dropGen, stream, seqMin, seqMax, t0, t1 });
    if (this._drops.length > LOG) this._drops.splice(0, this._drops.length - LOG);
  }

  /** Keyed versions older than `before`, except each key's newest. Each key's drop goes in the drop log, so a paused
      view redraws only when it took the version that view shows at t (live/feed.js pausedNews). */
  _dropVersions(before) {
    let n = 0;
    const touched = [];
    for (const [k, vs] of this._keys) {
      let m = 0, seqMin = Infinity, seqMax = -Infinity, t0 = Infinity, t1 = -Infinity;
      while (vs.length > 1 && vs[0].t < before) {
        const v = vs.shift();
        m++;
        if (v.seq < seqMin) seqMin = v.seq;
        if (v.seq > seqMax) seqMax = v.seq;
        if (v.t < t0) t0 = v.t;
        if (v.t > t1) t1 = v.t;
        this._keyBytes -= ROW_BYTES + (v.row ? Object.keys(v.row).reduce((b, p) => b + valueBytes(v.row[p]), 0) : 8);
      }
      if (m) { n += m; touched.push(k); this._logDrop(k, seqMin, seqMax, t0, t1); }
    }
    if (n) {
      this._rows -= n;
      // WHY: the clock's span starts at the oldest data kept (the playback bar must not offer history that is gone),
      // and the byte cap's one-second steps start from here
      let s = Infinity;
      for (const vs of this._keys.values()) if (vs.length && vs[0].t < s) s = vs[0].t;
      if (Number.isFinite(s)) this._start = s;
      this._note({ dropped: n, streams: touched });
    }
    return n;
  }
}

/** A log's entries after `gen`, or null when it lost some of them. Each entry's gen is one more than the one before
    it (clear() empties the log and moves the gen), so the entries after `gen` are a slice. */
function since(log, last, gen) {
  if (gen === last) return [];
  if (gen === null || gen === undefined || !log.length || log[0].gen > gen + 1) return null;
  return log.slice(Math.max(0, gen + 1 - log[0].gen));
}

// ------------------------------------------------------------------ retention

/** One dataset's own caps: age first (whole chunks older than end − age), then bytes. */
function enforce(ds) {
  const { bytes, age } = ds.retention;
  if (ds.key) {
    if (age !== null && ds.end !== null) ds._dropVersions(ds.end - age);
    if (bytes !== null) { let cut = ds.start; while (ds.bytes > bytes && ds._dropVersions(cut += 1)) { /* one second at a time */ } }
    return;
  }
  if (age !== null && ds.end !== null) {
    for (let v = ds._victim(false); v && v.chunk.t1 < ds.end - age; v = ds._victim(false)) ds._drop(v);
  }
  if (bytes !== null) {
    for (const strict of [true, false]) {
      while (ds.bytes > bytes) { const v = ds._victim(strict); if (!v) break; ds._drop(v); }
    }
  }
}

/** The page's budget across every live dataset: the globally oldest chunk goes first. */
function enforcePage() {
  let total = 0;
  for (const ds of LIVE) total += ds.bytes;
  if (total <= BUDGET) return;
  for (const strict of [true, false]) {
    while (total > BUDGET) {
      let best = null, bestDs = null;
      for (const ds of LIVE) {
        if (ds.key) continue;
        const v = ds._victim(strict);
        if (v && (!best || v.chunk.t1 < best.chunk.t1)) { best = v; bestDs = ds; }
      }
      if (!best) break;
      const before = bestDs.bytes;
      bestDs._drop(best);
      total -= before - bestDs.bytes;
    }
  }
}

// ------------------------------------------------------------------ staleness: a change with no arrival

const WATCHED = new Set();
let staleTimer = null;
function watchStale(ds) {
  WATCHED.add(ds);
  if (staleTimer || typeof setInterval !== 'function') return;
  staleTimer = setInterval(() => {
    const now = Date.now();
    for (const d of WATCHED) {
      const s = d._status;
      if (s.state !== 'live') { WATCHED.delete(d); continue; }
      if (s.lastData && now - s.lastData > d.staleAfter * 1000) { d.setStatus('stale', `no data for ${Math.round((now - s.lastData) / 1000)} s`); WATCHED.delete(d); }
    }
    if (!WATCHED.size) { clearInterval(staleTimer); staleTimer = null; }
  }, 250);
  // WHY unref: a Node test (or a worker) must be able to exit while a dataset is still live
  if (staleTimer && typeof staleTimer.unref === 'function') staleTimer.unref();
}

// ------------------------------------------------------------------ a small binary heap (the k-way merge's cursors)

class Heap {
  constructor(before) { this.a = []; this.before = before; }
  get size() { return this.a.length; }
  push(x) {
    const a = this.a;
    a.push(x);
    let i = a.length - 1;
    while (i > 0) { const p = (i - 1) >> 1; if (!this.before(a[i], a[p])) break; [a[i], a[p]] = [a[p], a[i]]; i = p; }
  }
  pop() {
    const a = this.a, top = a[0], last = a.pop();
    if (a.length) {
      a[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1;
        let m = i;
        if (l < a.length && this.before(a[l], a[m])) m = l;
        if (r < a.length && this.before(a[r], a[m])) m = r;
        if (m === i) break;
        [a[i], a[m]] = [a[m], a[i]];
        i = m;
      }
    }
    return top;
  }
}
