/* <data-dashboard>'s live part (docs/peps/0012-live-data.md §4, §7.2; docs/CONTRACT.md §26). WHY its own file: the
   dashboard's index.js is shared with lanes dashboards, dc-pb and dc-plot; it calls these few hooks, and everything
   live stays here.

     .base   datasets.<name>.live: {time, stream | key, sse | poll …, retention, stale, recorded} → a LiveDataset in
             dashboard.datasets, its source connected (SSE or polling) or left to the page (dataset.append);
             top-level retention: {bytes} → the page's buffer.
     clock   a LiveClock bound to every live dataset; following on open unless the link says #t=<seconds>.
     keys    End and Ctrl/Cmd+Shift+→ go live; Ctrl/Cmd+Shift+← goes to the oldest data (Home already does).
     URL     #t=live while following.
     bar     a <data-live-status> line.
     roll-up a §17 roll-up that reads live data is the rows as of the clock's t, computed again as t moves and as its
             datasets get news (watchRollups). */

import { LiveDataset, isLiveDataset, setLiveBudget, connectSSE, connectPoll, LiveClock } from '../../core/src/live.js';
import { loadDataset } from '../../core/src/data.js';
import { applyRollups, liveRollups } from './model.js';

const specOf = (base, name) => {
  const d = base && base.datasets && base.datasets[name];
  return d && typeof d === 'object' && d.live && typeof d.live === 'object' ? d.live : null;
};

/** After the files load: every dataset whose .base entry has `live:` becomes a LiveDataset (its file's properties and
    rows are the schema and the backlog), and its source connects. Returns the datasets to draw. */
export function liveDatasets(dash, base, datasets, baseUrl) {
  closeLive(dash);
  if (base && base.retention && base.retention.bytes !== undefined) setLiveBudget(base.retention.bytes);
  const out = { ...datasets };
  dash._liveSources = [];
  for (const [name, file] of Object.entries(datasets)) {
    const spec = specOf(base, name);
    if (!spec || isLiveDataset(file)) continue;
    const ds = new LiveDataset({
      id: file.id || name, title: file.title || name, titleProperty: file.titleProperty, linkProperty: file.linkProperty,
      imageProperty: file.imageProperty, properties: file.properties, rows: file.rows, url: file.url,
      time: spec.time, stream: spec.stream || null, key: spec.key || null, retention: spec.retention || {}, stale: spec.stale ?? 5,
      recorded: spec.recorded === true,
    });
    out[name] = ds;
    dash._liveSources.push({ name, ds, spec, file: file.url, baseUrl, source: null });
  }
  openLive(dash);
  return out;
}

/** Connect each live dataset's source (again, after the element was put back on the page). */
export function openLive(dash) {
  for (const s of dash._liveSources || []) {
    if (s.source || s.spec.recorded) continue;
    if (s.spec.sse) s.source = connectSSE(s.ds, s.spec.sse, { base: s.baseUrl, events: s.spec.events, withCredentials: s.spec.withCredentials });
    else if (s.spec.poll) s.source = connectPoll(s.ds, s.spec.poll, { base: s.baseUrl, every: s.spec.every ?? '1s', since: s.spec.since, cursor: s.spec.cursor, rows: s.spec.rows });
    else s.ds.setStatus('live');   // the page pushes rows (dashboard.datasets.<name>.append)
    // WHY: a host that cannot resume sends `reset`; the dataset clears, and the backlog file is read again
    if (!s.onReset) {
      s.onReset = (e) => { if (e.detail.reset && s.file) loadDataset(s.file).then((d) => s.ds.append(d.rows || [])).catch(() => {}); };
      s.ds.addEventListener('change', s.onReset);
    }
  }
}

/** Close every source (the element left the page, or the .base is read again). */
export function closeLive(dash) {
  for (const s of dash._liveSources || []) if (s.source) { s.source.close(); s.source = null; }
}

/** The dashboard's clock: a LiveClock (exactly a Clock while nothing live is bound), loop off when anything is live. */
export function makeClock(dash, c) {
  const live = Object.values(dash.datasets || {}).some((d) => isLiveDataset(d) && !d.recorded);
  return new LiveClock({ rate: Number(c.rate) || 1, loop: live ? c.loop === true : c.loop !== false, fps: Number(c.fps) || 30 });
}

/** Bind the clock to every live dataset now drawn (and let go of those no longer). Before the link's #t= is read, so
    a link to a moment pauses there. */
export function bindLive(dash) {
  const clock = dash.clock;
  if (!clock || typeof clock.bind !== 'function') return;
  const now = Object.values(dash.datasets || {}).filter(isLiveDataset);
  for (const d of clock.datasets) if (!now.includes(d)) clock.unbind(d);
  for (const d of now) clock.bind(d);
  // WHY per clock: a new document gets a new clock (index.js _setupClock), which needs this listener too
  if (dash._liveUrl !== clock) {
    dash._liveUrl = clock;
    // WHY on state: following counts as playing, and the dashboard writes the URL only while paused
    clock.addEventListener('state', () => { if (dash.clock === clock && clock.following && !dash._clockSetup) dash._writeUrl(); });
  }
  if (now.length) dash.dispatchEvent(new CustomEvent('data-dashboard-live', { detail: { datasets: Object.fromEntries(Object.entries(dash.datasets).filter(([, d]) => isLiveDataset(d))) } }));
  watchRollups(dash);
}

// ------------------------------------------------------------------ roll-ups over live data (CONTRACT §17 addendum)

const ROLLUP_EVERY = 250;   // ms between redraws of a rolled-up panel while the clock plays or follows (live/feed.js FULL_EVERY)

/** The t a roll-up reads its rows at: the dashboard clock's (model.js rowsAsOf reads a file's rows whatever it is). */
export function rollupTime(dash) {
  const c = dash && dash.clock;
  return c && Number.isFinite(c.t) ? c.t : undefined;
}

/** A roll-up that reads live data is the rows as of the clock's t (model.js applyRollups {t}), so it rewinds with the
    clock: computed again on every move of t and on every change of a live dataset it reads (a late row at or before t
    while paused, a retention drop), before the frame's views draw (live/frame.js: datasets, then clocks, then views),
    so a live tree reads its cells at the t it draws. A panel on a roll-up whose cells moved is handed its data again
    (data-views' rule for rows changed in place): at once while paused, at most every 250 ms while the clock plays or
    follows (a live tree re-models no oftener, live/feed.js). WHY (RobotDx PEP 0001 §18.4, ask 2): the roll-up read
    the newest rows, once per rail click, so on live data it neither followed nor rewound. Called by bindLive on every
    draw of a document (and again after the element is put back); a document with no such roll-up has no watch. */
export function watchRollups(dash) {
  unwatchRollups(dash);
  const clock = dash.clock;
  const names = dash.dash && dash.datasets ? liveRollups(dash.dash, dash.datasets) : [];
  if (!clock || !names.length) return;
  const sets = [...new Set(names.flatMap((n) => [dash.datasets[n], dash.datasets[dash.dash.datasets[n].rollup.from]]))].filter(isLiveDataset);
  const w = { clock, sets, names, sig: null, cells: {}, owed: new Set(), drawnAt: -Infinity, timer: null };
  w.run = () => rollupNow(dash, w);
  // WHY not on news after t while following: the clock moves t to it in this same frame, after the datasets publish
  // (live/frame.js), and its time event computes at the new t; computed here, it would be at the old one. A late row (at
  // or before t), a drop or a reset computes now, since t may not move
  w.news = (e) => {
    const d = (e && e.detail) || {};
    if (w.clock.following && !d.reset && !d.dropped && typeof d.from === 'number' && d.from > w.clock.t) return;
    rollupNow(dash, w);
  };
  clock.addEventListener('time', w.run);
  for (const ds of sets) ds.addEventListener('change', w.news);
  dash._rollWatch = w;
}

export function unwatchRollups(dash) {
  const w = dash._rollWatch;
  if (!w) return;
  w.clock.removeEventListener('time', w.run);
  for (const ds of w.sets) ds.removeEventListener('change', w.news);
  if (w.timer) clearTimeout(w.timer);
  dash._rollWatch = null;
}

function rollupNow(dash, w) {
  if (dash._rollWatch !== w || !dash.dash) return;
  // off the page: nothing to compute for; the first news or move after it is put back computes at its t
  if (!dash.isConnected) { w.sig = null; return; }
  const t = rollupTime(dash);
  // the inputs of the roll-ups: t, and each live dataset's rows (its writes, drops and resets); the rails come through
  // the dashboard's _update, which computes them itself
  const sig = JSON.stringify([t ?? null, ...w.sets.map((ds) => [ds.seq, ds.dropGen, ds.resets])]);
  if (sig === w.sig) return;
  w.sig = sig;
  const out = applyRollups(dash.dash, dash.datasets, dash.state, { t, only: w.names });
  for (const name of w.names) {
    const cells = JSON.stringify(Object.entries(out[name] || {}).map(([col, byId]) => [col, Object.entries(byId).map(([id, c]) => [id, c.value ?? null, c.n ?? null, c.why ?? null])]));
    if (cells === w.cells[name]) continue;
    w.cells[name] = cells;
    w.owed.add(name);
  }
  if (!w.owed.size || !dash.isConnected) return;
  const go = () => {
    w.timer = null;
    if (dash._rollWatch !== w || !dash.dash) return;
    w.drawnAt = performance.now();
    const names = new Set(w.owed);
    w.owed.clear();
    for (const p of dash.dash.panels) {
      const el = dash.panelEls && dash.panelEls[p.key];
      if (!el) continue;
      if (names.has(p.dataset)) el.data = dash.datasets[p.dataset];
      // a 3D view's layers on a rolled-up dataset (CONTRACT §32) hear it as the dashboard's _update hands them
      if ((p.layers || []).some((n) => names.has(n)) && typeof dash._handLayers === 'function') dash._handLayers(p, el, true);
    }
  };
  const busy = w.clock.playing || w.clock.following;
  const wait = ROLLUP_EVERY - (performance.now() - w.drawnAt);
  if (!busy || wait <= 0) { if (w.timer) { clearTimeout(w.timer); w.timer = null; } go(); }
  else if (!w.timer) w.timer = setTimeout(go, wait);
}

/** The keys Rerun adds for live data. True when the key was ours. */
export function liveKey(e, clock) {
  if (!clock || !clock.live) return false;
  const mod = e.ctrlKey || e.metaKey;
  if ((e.key === 'ArrowRight' && mod && e.shiftKey) || (e.key === 'End' && !mod && !e.altKey)) { clock.goLive(); return true; }
  if (e.key === 'ArrowLeft' && mod && e.shiftKey) { clock.seek(clock.start ?? clock.liveStart); return true; }
  return false;
}

/** clockNavigation's answer (core clock.js, CONTRACT §25) with this tier's own t kept: `#t=live`, which it reads as
    malformed, is 'live', and LiveClock.restore follows it (CONTRACT §26). `key` as clockNavigation's. */
export function liveNavigation(nav, params, key = null) {
  const raw = key && params.has(`t.${key}`) ? params.get(`t.${key}`) : params.get('t');
  return nav && raw !== null && raw.trim() === 'live' ? { ...nav, t: 'live' } : nav;
}

/** The URL's t: "live" while following, else the time (null: leave it to the dashboard). */
export function liveHash(clock) {
  if (!clock || !clock.live) return null;
  return clock.following ? 'live' : clock.t.toFixed(3).replace(/\.?0+$/, '');
}

/** The connection line in the dashboard's bar, when it has a live dataset. */
export function liveBar(dash) {
  const bar = dash.querySelector(':scope .dd-bar');
  if (!bar || !Object.values(dash.datasets || {}).some(isLiveDataset)) return;
  if (bar.querySelector('data-live-status')) return;
  const st = document.createElement('data-live-status');
  st.className = 'dd-live-status';
  bar.querySelector('.dd-actions').before(st);
}
