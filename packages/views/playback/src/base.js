/* What every playback proposal shares (docs/peps/0005-dashboard-cards.md §4b): the clock and its events, the
   dashboard's datasets read-only, a variant's own keys, and pointer → time mapping.

   A proposal never owns time. It calls the clock (packages/core/src/clock.js, the one writer) and redraws on its
   events; on a `time` event it only moves things (a CSS variable, a transform, a text node), never re-renders. */

import { clockFor, cellValue, compileFilters, mediaUrl, seriesColor } from '@data-ui/core';
import { isClip, streamsOf, eventTimes, decimate, plain } from './model.js';

export const ICON = {
  play: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 2.8v10.4L13 8z" fill="currentColor"/></svg>',
  pause: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 3h3v10H4zM9 3h3v10H9z" fill="currentColor"/></svg>',
  playLine: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3.2v9.6L12.4 8z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
  pauseLine: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5.5 3.5v9M10.5 3.5v9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  stepFwd: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 3.5v9L10 8z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M12 3.5v9" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  stepBack: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M12 3.5v9L6 8z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M4 3.5v9" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  scrub: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.5v11M5.5 2.5h5M4 6 1.8 8 4 10M12 6l2.2 2L12 10" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  loop: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.2 9.8A4.2 4.2 0 1 0 5 4.3M4.6 1.8 5 4.3l-2.5.6" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  repeat: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 5h7.5l-1.6-1.6M12 11H4.5l1.6 1.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  chev: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4.5 6.5 3.5 3.5 3.5-3.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  search: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.3" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="m10.2 10.2 3.3 3.3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  caret: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m6 4 4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  gear: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 5.6a2.4 2.4 0 1 0 0 4.8 2.4 2.4 0 0 0 0-4.8Z" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M8 1.5v1.8M8 12.7v1.8M14.5 8h-1.8M3.3 8H1.5M12.6 3.4l-1.3 1.3M4.7 11.3l-1.3 1.3M12.6 12.6l-1.3-1.3M4.7 4.7 3.4 3.4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  back5: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3.5v9L2.5 8zM14 3.5v9L8.5 8z" fill="currentColor"/></svg>',
  fwd5: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3.5v9L13.5 8zM2 3.5v9L7.5 8z" fill="currentColor"/></svg>',
  next: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3.2v9.6L10 8z" fill="currentColor"/><path d="M11.5 3.2h1.7v9.6h-1.7z" fill="currentColor"/></svg>',
  film: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="3" width="12" height="10" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M5 3v10M11 3v10M2 6h3M2 10h3M11 6h3M11 10h3" stroke="currentColor" stroke-width="1.1"/></svg>',
  wave: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M1.5 9.5 4 6l2.5 4L9 4l2.5 6L14.5 7" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  entity: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.5 13.5 8 8 13.5 2.5 8z" fill="none" stroke="currentColor" stroke-width="1.2"/><circle cx="8" cy="8" r="1.4" fill="currentColor"/></svg>',
  component: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 5.5v5M13 5.5v5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>',
};

const TYPING = 'input, select, textarea, [contenteditable]';

/** Which of a dashboard's key-owning proposals answers its keys: the one used last (a pointer or focus inside it),
    else the first that asked. WHY: the proposals page puts several on one clock, and one key must move t once. */
function keyOwner(dash) {
  const list = dash._dvPbKeys || [];
  return list.includes(dash._dvPbActive) ? dash._dvPbActive : list[0] || null;
}

export class Variant {
  constructor(host, el, name, clock = clockFor(host.element)) {
    this.host = host;
    this.el = el;
    this.name = name;
    this.clock = clock;
    this.dashEl = host.element.closest('data-dashboard');
    this.input = null;
    this._off = [];
    this.on(this.clock, 'time', () => this.time());
    this.on(this.clock, 'state', () => this.state());
  }

  /** addEventListener that destroy() undoes. */
  on(target, type, fn, opts) {
    if (!target) return;
    target.addEventListener(type, fn, opts);
    this._off.push(() => target.removeEventListener(type, fn, opts));
  }

  /** Own some keys while this proposal is in use: `fn(e)` returns true when it handled the key. Installed on the
      closest <data-dashboard> in the capture phase, so it runs before the dashboard's own keys (its _key), and it
      stops the event there for the keys it takes. Removed in destroy(). */
  ownKeys(fn) {
    const dash = this.dashEl;
    if (!dash) return;
    (dash._dvPbKeys = dash._dvPbKeys || []).push(this);
    const mark = () => { dash._dvPbActive = this; };
    this.on(this.el, 'pointerdown', mark);
    this.on(this.el, 'focusin', mark);
    this.on(dash, 'keydown', (e) => {
      if (keyOwner(dash) !== this || !this.dashEl.dash || !this.dashEl.dash.clock) return;
      if (e.target.closest && e.target.closest(TYPING)) return;
      if (fn(e)) { e.preventDefault(); e.stopImmediatePropagation(); }
    }, true);
    this._off.push(() => {
      dash._dvPbKeys = (dash._dvPbKeys || []).filter((v) => v !== this);
      if (dash._dvPbActive === this) dash._dvPbActive = null;
    });
  }

  destroy() {
    this.closeMenu();
    for (const off of this._off.splice(0)) off();
    if (this._ro) this._ro.disconnect();
    this.el.innerHTML = '';
  }

  update(input) { this.input = input; }
  time() {}
  state() {}

  // ------------------------------------------------------------------ the dashboard's data, read-only

  /** {name: dataset} of the dashboard (else this view's own dataset), the clock's time column and the dashboard
      model (null outside a dashboard). */
  data() {
    const d = this.dashEl;
    if (d && d.datasets && d.dash) return { datasets: d.datasets, timeCol: (d.dash.clock && d.dash.clock.time) || 't', dash: d.dash };
    const ds = this.input && this.input.dataset;
    return { datasets: ds ? { data: { ...ds, rows: this.input.rows || [] } } : {}, timeCol: 't', dash: null };
  }

  events() {
    const { datasets, timeCol } = this.data();
    const key = this._key(datasets);
    if (this._ev && this._ev.key === key) return this._ev.list;
    const list = eventTimes(datasets, timeCol);
    this._ev = { key, list };
    return list;
  }

  streams() {
    const { datasets, timeCol } = this.data();
    return streamsOf(datasets, timeCol);
  }

  _key(datasets) { return Object.entries(datasets).map(([k, d]) => `${k}:${d && d.rows ? d.rows.length : 0}`).join('|'); }

  /** The dashboard's video clips, the primary first: the clock's `primary` panel, else a view with video.primary,
      else the first video view; then every other clip row. [{id, src (URL), t0, fps, duration, label, basis}] */
  clips() {
    const { datasets, dash } = this.data();
    const out = [], seen = new Set();
    const add = (row, ds, srcCol = 'src') => {
      const src = plain(row[srcCol]);
      if (!src || seen.has(String(src))) return;
      seen.add(String(src));
      const v = (k) => cellValue(row[k]);
      out.push({ id: row.id, src: mediaUrl(src, ds), t0: Number.isFinite(v('t0')) ? v('t0') : 0, fps: Number(v('fps')) || 30,
        duration: Number.isFinite(v('duration')) ? v('duration') : null, label: String(v('situation') ?? v('label') ?? row.id ?? 'video'),
        basis: v('basis') || null, width: Number(v('width')) || null, height: Number(v('height')) || null });
    };
    if (dash) {
      const panels = dash.panels.filter((p) => p.views.length);
      const vids = panels.flatMap((p) => p.views.filter((v) => v.type === 'video').map((v) => ({ p, v })));
      const want = dash.clock && dash.clock.primary;
      vids.sort((x, y) => rank(x.v) - rank(y.v));
      function rank(v) { return v.name === want ? 0 : v.video && v.video.primary ? 1 : 2; }
      for (const { p, v } of vids) {
        const ds = datasets[p.dataset];
        if (!ds) continue;
        let f = null;
        try { f = compileFilters(v.filters); } catch { f = null; }
        const row = ds.rows.find((r) => !f || f(r));
        if (row) add(row, ds, (v.video && v.video.src) || 'src');
      }
    }
    for (const ds of Object.values(datasets)) for (const r of ds.rows || []) if (isClip(r)) add(r, ds);
    return out;
  }

  /** The dashboard's time series views as sparkline sources: [{name, unit, lines: [{name, color, points}]}], in
      layout order. points decimated to ~2n. Each view's own filters apply. */
  seriesTracks(n = 200) {
    const { datasets, dash } = this.data();
    if (!dash) return [];
    const out = [];
    for (const p of dash.panels) {
      for (const v of p.views) {
        if (v.type !== 'timeseries' || !v.timeseries) continue;
        const ds = datasets[p.dataset];
        if (!ds) continue;
        const k = v.timeseries, x = k.x || 't', ys = [].concat(k.y || []), by = k.series || null;
        let f = null;
        try { f = compileFilters(v.filters); } catch { f = null; }
        const groups = new Map();
        for (const r of ds.rows) {
          if (f && !f(r)) continue;
          const t = cellValue(r[x]);
          if (typeof t !== 'number' || !Number.isFinite(t)) continue;
          for (const y of ys) {
            const name = by ? String(cellValue(r[by])) + (ys.length > 1 ? ` · ${y}` : '') : y;
            if (!groups.has(name)) groups.set(name, []);
            const val = cellValue(r[y]);
            groups.get(name).push([t, typeof val === 'number' && Number.isFinite(val) ? val : null]);
          }
        }
        if (!groups.size) continue;
        const lines = [...groups].map(([name, pts]) => {
          pts.sort((a, b) => a[0] - b[0]);
          return { name, color: seriesColor(name.split(' · ')[0], this.input), points: decimate(pts, n) };
        });
        out.push({ name: v.name, unit: k.unit || '', lines });
      }
    }
    return out;
  }

  // ------------------------------------------------------------------ time ↔ pixels

  span() {
    const c = this.clock;
    const a = c.start ?? 0, b = c.end ?? a;
    return [a, b > a ? b : a + 1];
  }

  frac(t) { const [a, b] = this.span(); return Math.max(0, Math.min(1, (t - a) / (b - a))); }

  tAt(clientX, box) {
    const r = box.getBoundingClientRect();
    const [a, b] = this.span();
    return a + Math.max(0, Math.min(1, (clientX - r.left) / (r.width || 1))) * (b - a);
  }

  /** Pointer scrubbing on `box`: down seeks and pauses, a drag follows, up resumes play if it was playing. */
  scrub(box, { onDown } = {}) {
    let dragging = false, was = false;
    this.on(box, 'pointerdown', (e) => {
      if (e.button !== 0) return;
      if (onDown && onDown(e) === false) return;
      dragging = true; was = this.clock.playing;
      this.clock.pause();
      try { box.setPointerCapture(e.pointerId); } catch { /* synthetic pointer */ }
      this.clock.seek(this.tAt(e.clientX, box));
    });
    this.on(box, 'pointermove', (e) => { if (dragging) this.clock.seek(this.tAt(e.clientX, box)); });
    const end = () => { if (!dragging) return; dragging = false; if (was) this.clock.play(); };
    this.on(box, 'pointerup', end);
    this.on(box, 'pointercancel', end);
  }

  /** A small popup menu anchored on `button`: items [{label, key?, act, checked?} | '-']; closes on pick, Escape or
      a click outside. */
  menu(button, items, { align = 'left', up = true } = {}) {
    this.closeMenu();
    const m = document.createElement('div');
    m.className = 'dv-pbv-menu';
    m.setAttribute('role', 'menu');
    m.innerHTML = items.map((it, i) => (it === '-' ? '<div class="dv-pbv-sep" role="separator"></div>'
      : `<button type="button" role="menuitem${it.checked !== undefined ? 'radio' : ''}"${it.checked !== undefined ? ` aria-checked="${!!it.checked}"` : ''} data-i="${i}"${it.disabled ? ' disabled' : ''}><span class="dv-pbv-mk">${it.checked ? '✓' : ''}</span><span class="dv-pbv-ml">${it.label}</span>${it.key ? `<kbd>${it.key}</kbd>` : ''}${it.sub ? `<span class="dv-pbv-sub">${it.sub}</span>` : ''}</button>`)).join('');
    this.el.append(m);
    const host = this.el.getBoundingClientRect(), b = button.getBoundingClientRect();
    const mr = m.getBoundingClientRect();
    let left = align === 'right' ? b.right - host.left - mr.width : b.left - host.left;
    left = Math.max(0, Math.min(left, host.width - mr.width));
    m.style.left = `${left}px`;
    // WHY open upwards by default: the card usually sits above the cards it drives, and a menu that opens into them
    // is clipped by the next panel; flip down when there is no room above inside the page
    const top = b.top - host.top - mr.height - 6;
    m.style.top = `${up && b.top - mr.height - 6 > 0 ? top : b.bottom - host.top + 6}px`;
    button.setAttribute('aria-expanded', 'true');
    m.addEventListener('click', (e) => {
      const it = items[Number((e.target.closest('[data-i]') || {}).dataset?.i)];
      if (!it || it === '-') return;
      e.stopPropagation();
      this.closeMenu();
      it.act();
    });
    const outside = (e) => { if (!m.contains(e.target) && !button.contains(e.target)) this.closeMenu(); };
    const esc = (e) => { if (e.key === 'Escape') { e.stopPropagation(); this.closeMenu(); button.focus(); } };
    document.addEventListener('pointerdown', outside, true);
    m.addEventListener('keydown', esc);
    this._menu = { m, button, off: () => document.removeEventListener('pointerdown', outside, true) };
    const first = m.querySelector('button:not([disabled])');
    if (first) first.focus({ preventScroll: true });
    return m;
  }

  closeMenu() {
    if (!this._menu) return;
    this._menu.off();
    this._menu.m.remove();
    this._menu.button.setAttribute('aria-expanded', 'false');
    this._menu = null;
  }
}
