/* type: levels — a level history (docs/peps/0012-live-data.md §6.3, docs/CONTRACT.md §26).

     levels: {state, by, label, order: [best … worst], tones: {level: good|warn|bad|muted}, bar}
     at: 60s            the window ending at the clock's t (default 30 s live, the whole recording when recorded)

   On a recording (a plain dataset, not live) the default is the whole of it (PEP 0012 §5.1: Foxglove's "last 30 s live,
   the full range recorded"): the clock's span, else the rows' own, or the clock's zoom window, with the clock's t drawn
   as a playhead ([data-playhead]); the strips stand still while t moves. `at: <duration>` keeps the window ending at t.
   WHY (kit gap 4): a recording showed only the 30 s before t, so a 4 s run filled an eighth of the strip while this
   header promised the whole recording.

   Grafana's Status history panel and RobotDx's health bar (io-diagnostics web/health.js, PEP 0001 E17): one strip per
   stream, one bar per time bin, the worst level held in the bin (levels-model.js); a bin with no data is an empty
   outline, never a level; bars 3 px with a 2 px gap, the count from the width. A bin is (start, end], so the newest
   reading at t is in the last bar the frame it arrives.

   Each strip is [data-strip="<value>"], each bar [data-bin] with data-level (empty: no data); the view element
   carries data-t0 / data-t1 (the window), so a check reads the bars against the dataset. Bars are reused between
   frames and only their class changes. STOCK PARTS: none (divs; ~25 strips × 150 bars is 3,750 nodes at most). */

import { esc, cellValue, clockFor, fmtTime, parseDuration } from '@data-ui/core';
import { levelBins, LEVELS } from './levels-model.js';

// the status vocabulary's tones (docs/CONTRACT.md §35) and the words this card always knew
const TONES = { ok: 'good', good: 'good', pass: 'good', warn: 'warn', warning: 'warn', partial: 'warn', error: 'bad', fail: 'bad', bad: 'bad', stale: 'muted', unknown: 'muted', not_run: 'muted', 'not run': 'muted' };
const GAP = 2;

export class LevelsView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    el.innerHTML = '<div class="dv-levels" role="list"></div><div class="dv-levels-axis" aria-hidden="true"><span></span><span><i></i><i></i></span></div><div class="dv-levels-playhead" data-playhead hidden></div>';
    this.list = el.querySelector('.dv-levels');
    this.playhead = el.querySelector('.dv-levels-playhead');
    this.clock = clockFor(host.element || el);
    // a window that ends at t redraws as t moves; the whole recording only moves its playhead
    this._onTime = () => { if (this.input && !this.input.live) { if (this._whole) this._place(); else this._draw(); } };
    this._onState = () => { if (this.input && !this.input.live && this._whole && JSON.stringify(this._window()) !== JSON.stringify(this._win)) this._draw(); };
    this.clock.addEventListener('time', this._onTime);
    this.clock.addEventListener('state', this._onState);
    this._ro = new ResizeObserver(() => { if (this.input) this._draw(); });
    this._ro.observe(el);
  }

  destroy() {
    this.clock.removeEventListener('time', this._onTime);
    this.clock.removeEventListener('state', this._onState);
    this._ro.disconnect();
    this.host.setStatus('');
    this.el.innerHTML = '';
  }

  update(input) {
    this.input = input;
    // a recording's own span (its rows' time), reported to the clock as a time series reports its own
    this._extent = null;
    if (!input.live) {
      const t = (input.view.levels && input.view.levels.t) || 't';
      let lo = Infinity, hi = -Infinity;
      for (const r of input.rows) { const v = cellValue(r[t]); if (typeof v === 'number' && Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } }
      if (hi >= lo) { this._extent = [lo, hi]; this.clock.extent(lo, hi); }
    }
    this._draw();
  }

  /** [{name, changes: [{t, level, label}], before}] over (a, b]. */
  _strips(a, b) {
    const input = this.input, o = input.view.levels || {};
    const state = o.state || 'level', label = o.label || null;
    const out = [];
    if (input.live) {
      const ds = input.live.dataset;
      const by = o.by || ds.stream;
      const names = by && by === ds.stream ? ds.streams().sort() : [null];
      for (const s of names) {
        const changes = [];
        for (const p of ds.range(a, b, { stream: s, columns: label ? [state, label] : [state] })) {
          for (let i = 0; i < p.t.length; i++) changes.push({ t: p.t[i], level: p.cols[state][i], label: label ? p.cols[label][i] : null });
        }
        changes.sort((x, y) => x.t - y.t);
        const prev = ds.latestAt(a, s === null ? undefined : s);
        out.push({ name: s === null ? (input.columns[state] ? input.columns[state].label : state) : String(s), changes, before: prev ? prev[state] : null });
      }
      return out;
    }
    const t = (input.view.levels && input.view.levels.t) || 't', by = o.by && input.columns[o.by] ? o.by : null;
    const groups = new Map();
    for (const r of input.rows) {
      const k = by ? String(cellValue(r[by]) ?? '') : '';
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push({ t: cellValue(r[t]), level: cellValue(r[state]), label: label ? cellValue(r[label]) : null });
    }
    for (const [k, rows] of groups) {
      rows.sort((x, y) => x.t - y.t);
      const before = rows.filter((x) => x.t <= a).pop();
      out.push({ name: by ? k : state, changes: rows.filter((x) => x.t > a && x.t <= b), before: before ? before.level : null });
    }
    return out;
  }

  /** The time window the strips show (the live tier's, else `at:`'s): [a, b]. Sets this._whole (no t in it). */
  _window() {
    const live = this.input.live;
    this._whole = false;
    if (live) return live.at === 'latest' ? [live.t - 30, live.t] : live.at;
    const at = this.input.view.at;
    const t = this.clock.t;
    const d = at === undefined || at === null || at === 'all' || at === 'latest' ? null : parseDuration(at);
    if (at === 'latest') return [t - 30, t];
    if (d !== null) return [t - d, t];
    this._whole = true;
    const c = this.clock, w = c.window;
    if (w && w[1] > w[0]) return [w[0], w[1]];
    if (typeof c.start === 'number' && typeof c.end === 'number' && c.end > c.start) return [c.start, c.end];
    return this._extent ? [...this._extent] : [t - 30, t];
  }

  /** The playhead at the clock's t on the strips (the whole recording only): where t falls along the bars. */
  _place() {
    const ph = this.playhead;
    const w = this._win, strip = this.list.querySelector('[data-strip]');
    if (!this._whole || !w || !strip || !strip.children.length) { ph.hidden = true; return; }
    const t = this.clock.t;
    if (!(t >= w[0] && t <= w[1])) { ph.hidden = true; return; }
    const box = this.el.getBoundingClientRect();
    const first = strip.firstElementChild.getBoundingClientRect(), last = strip.lastElementChild.getBoundingClientRect();
    const list = this.list.getBoundingClientRect();
    const x = first.left + ((t - w[0]) / (w[1] - w[0])) * (last.right - first.left) - box.left;
    ph.hidden = false;
    ph.style.height = `${list.height}px`;
    ph.style.transform = `translate(${x - 0.5}px, ${list.top - box.top}px)`;
  }

  _draw() {
    const o = this.input.view.levels || {};
    const order = Array.isArray(o.order) && o.order.length ? o.order : LEVELS;
    const tones = { ...TONES, ...(o.tones || {}) };
    const bar = Math.max(1, Number(o.bar) || 3);
    let [a, b] = this._window();
    if (!(b > a)) b = a + 1;
    this._win = [a, b];
    const strips = this._strips(a, b);
    const width = Math.max(40, (this.list.clientWidth || 400) * 0.78 - 10);
    const n = Math.max(4, Math.floor((width + GAP) / (bar + GAP)));
    this.el.dataset.t0 = String(a);
    this.el.dataset.t1 = String(b);
    this.list.style.setProperty('--dv-levels-bar', `${bar}px`);
    this.list.style.setProperty('--dv-levels-gap', `${GAP}px`);
    if (!strips.length) { this.list.innerHTML = '<p class="dv-levels-empty">No levels in this window yet</p>'; this._place(); return; }
    // rows: reuse each strip's row and bars, change only what moved
    const have = new Map([...this.list.querySelectorAll(':scope > .dv-levels-row')].map((row) => [row.dataset.name, row]));
    const keep = new Set();
    for (const s of strips) {
      let row = have.get(s.name);
      if (!row) {
        row = document.createElement('div');
        row.className = 'dv-levels-row';
        row.setAttribute('role', 'listitem');
        row.dataset.name = s.name;
        row.innerHTML = `<span class="dv-levels-name" title="${esc(s.name)}">${esc(s.name)}</span><div class="dv-levels-strip" data-strip="${esc(s.name)}"></div>`;
      }
      this.list.append(row);   // keeps the strips in order
      keep.add(s.name);
      const strip = row.querySelector('[data-strip]');
      while (strip.children.length < n) { const i = document.createElement('i'); i.dataset.bin = ''; i.dataset.level = ''; strip.append(i); }
      while (strip.children.length > n) strip.lastChild.remove();
      const bins = levelBins(s.changes, s.before, a, b, n, order);
      for (let k = 0; k < n; k++) {
        const el = strip.children[k], level = bins[k] ?? '';
        if (el.dataset.level === level) continue;
        el.dataset.level = level;
        el.className = level ? `dv-tone-${tones[level] || 'muted'}` : '';
      }
      const last = [...s.changes].pop();
      const now = last ? last.level : s.before;
      strip.title = `${s.name}: ${now ?? 'no data'}${last && last.label ? ` · ${last.label}` : ''}`;
    }
    for (const [name, row] of have) if (!keep.has(name)) row.remove();
    const axis = this.el.querySelectorAll('.dv-levels-axis i');
    axis[0].textContent = fmtTime(a);
    axis[1].textContent = fmtTime(b);
    this.host.setStatus(`<span class="dv-chart-status">${strips.length} strip${strips.length === 1 ? '' : 's'} · ${n} bins of ${((b - a) / n).toFixed(2)} s${this._whole ? ' · the whole recording' : ''}</span>`);
    this._place();
  }
}
