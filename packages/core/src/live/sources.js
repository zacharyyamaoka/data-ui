/* Where a live dataset's rows come from (docs/peps/0012-live-data.md §7): a server-sent-events URL, a polling URL, or
   the page itself (dataset.append from the host's own code). data-ui only ever reads: no source sends anything that
   changes a host (RobotDx's /act, /config, /watch stay the host page's own).

   SSE (EventSource): the browser reconnects by itself and sends Last-Event-ID, so a host that keeps a ring resumes
   with no gap (WHATWG HTML §9.2). Polling: since=<cursor> after each answer, a back-off while the host is down, and
   no polls while the tab is hidden (the cursor catches the gap up when it shows).
   STOCK PARTS: EventSource and fetch. */

import { parseDuration } from './store.js';

/** The value at a dotted path, arrays on the way flattened: rowsAt({groups: [{rows: […]}, …]}, 'groups.rows'). With no
    path: the body if it is an array, else body.rows. */
export function rowsAt(body, path) {
  if (path === null || path === undefined) return Array.isArray(body) ? body : body && Array.isArray(body.rows) ? body.rows : [];
  if (path === '') return Array.isArray(body) ? body : body ? [body] : [];
  let cur = [body];
  for (const key of String(path).split('.')) {
    cur = cur.flatMap((x) => (Array.isArray(x) ? x : [x])).map((x) => (x && typeof x === 'object' ? x[key] : undefined)).filter((x) => x !== undefined && x !== null);
  }
  return cur.flatMap((x) => (Array.isArray(x) ? x : [x]));
}

const valueAt = (body, path) => {
  let cur = body;
  for (const key of String(path).split('.')) cur = cur && typeof cur === 'object' ? cur[key] : undefined;
  return cur;
};

const pageUrl = () => (typeof location !== 'undefined' ? location.href : 'http://localhost/');

/**
 * Poll `url` every `every` (ms as a number, or '250ms' / '1s'; never under 50 ms) into `ds`.
 * {since: the query parameter that carries the cursor, cursor: a dotted path or (body) => value, rows: a dotted path or
 *  (body) => rows, map: (rows, body) => rows, fetch, base: the URL `url` is relative to}
 * Returns {close()}.
 */
export function connectPoll(ds, url, opts = {}) {
  const every = Math.max(50, typeof opts.every === 'number' ? opts.every : (parseDuration(opts.every ?? '1s') ?? 1) * 1000);
  const get = opts.fetch || ((u, o) => fetch(u, o));
  const base = opts.base || pageUrl();
  let cursor = null, closed = false, tries = 0, timer = null;
  ds.setStatus('connecting');
  const schedule = (ms) => { if (!closed) timer = setTimeout(once, ms); };
  async function once() {
    if (closed) return;
    // WHY skip while hidden: a background tab polls nothing; the since cursor fetches the gap when it shows
    if (typeof document !== 'undefined' && document.hidden && !opts.hidden) { schedule(every); return; }
    const u = new URL(url, base);
    if (cursor !== null && opts.since) u.searchParams.set(opts.since, String(cursor));
    try {
      const res = await get(u.href, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = await res.json();
      if (closed) return;
      let rows = typeof opts.rows === 'function' ? opts.rows(body) : rowsAt(body, opts.rows ?? null);
      if (opts.map) rows = opts.map(rows, body);
      if (rows && rows.length) ds.append(rows);
      const next = typeof opts.cursor === 'function' ? opts.cursor(body) : opts.cursor ? valueAt(body, opts.cursor) : undefined;
      if (next !== undefined && next !== null) cursor = next;
      tries = 0;
      // the connection is back; staleness is about data and stays the store's call
      if (ds.status.state === 'connecting' || ds.status.state === 'reconnecting') ds.setStatus('live');
      schedule(every);
    } catch (err) {
      if (closed) return;
      tries++;
      ds.setStatus('reconnecting', err && err.message ? err.message : 'the host did not answer', tries);
      schedule(Math.min(10000, every * 2 ** tries));
    }
  }
  schedule(0);
  return { close() { closed = true; clearTimeout(timer); ds.setStatus('closed'); } };
}

const WIRE = new Set(['remove', 'status', 'reset']);

/** Apply one SSE payload: {rows}, a bare array, {remove, t}, {status, detail}. */
function apply(ds, data) {
  if (Array.isArray(data)) { ds.append(data); return; }
  if (!data || typeof data !== 'object') return;
  if (Array.isArray(data.rows)) ds.append(data.rows);
  if (Array.isArray(data.remove)) ds.remove(data.remove, typeof data.t === 'number' ? data.t : undefined);
  if (typeof data.status === 'string') ds.setStatus(data.status, data.detail || '');
}

/**
 * Read `url` as server-sent events into `ds`. {events: the event names that carry rows (default message and rows),
 * map: (data, type) => rows for a host's own events, withCredentials, EventSource, base}. The events remove, status and
 * reset are always read. Returns {close(), source}.
 */
export function connectSSE(ds, url, opts = {}) {
  const ES = opts.EventSource || globalThis.EventSource;
  const href = new URL(url, opts.base || pageUrl()).href;
  const es = new ES(href, { withCredentials: !!opts.withCredentials });
  let closed = false, tries = 0;
  ds.setStatus('connecting');
  const parse = (e) => { try { return JSON.parse(e.data); } catch { return undefined; } };
  const onRows = (e) => {
    const data = parse(e);
    if (data === undefined) return;
    if (opts.map) { const rows = opts.map(data, e.type); if (rows && rows.length) ds.append(rows); return; }
    apply(ds, data);
  };
  for (const type of new Set(opts.events || ['message', 'rows'])) if (!WIRE.has(type)) es.addEventListener(type, onRows);
  es.addEventListener('remove', (e) => { const d = parse(e); if (d) apply(ds, Array.isArray(d) ? { remove: d } : d); });
  es.addEventListener('status', (e) => { const d = parse(e); if (d) apply(ds, typeof d === 'string' ? { status: d } : d); });
  es.addEventListener('reset', () => ds.clear());
  es.addEventListener('open', () => { tries = 0; if (!closed) ds.setStatus('live'); });
  es.addEventListener('error', () => {
    if (closed) return;
    // readyState 2 (CLOSED): the browser gave up (a non-200, a wrong type); 0: it is retrying, with Last-Event-ID
    if (es.readyState === 2) ds.setStatus('closed', 'the host closed the stream');
    else ds.setStatus('reconnecting', 'the connection dropped', ++tries);
  });
  return { close() { closed = true; es.close(); ds.setStatus('closed'); }, source: es };
}
