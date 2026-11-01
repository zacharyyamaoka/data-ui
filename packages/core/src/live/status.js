/* <data-live-status [for="id"]>: one line of connection state (docs/peps/0012-live-data.md §6.4).

   RobotDx's status bar said "Last update N s ago" / "Host unreachable" (PEP 0001 E8); this is that line for any live
   clock: "● Live · 3 sources · last data 0.1 s ago", "Reconnecting · try 3 · last data 12 s ago", "Stale · no data for
   8 s", "Paused by the host: tview has the port", "Recorded". It never invents progress: the age keeps growing while
   nothing arrives (prior-art note: the clock never fakes progress). It ticks once a second while the page is visible,
   because the age changes with no new row. data-state carries the state for a host's CSS and for checks. */

import { clockFor } from '../clock.js';
import { isLiveClock } from './clock.js';
import { addLiveStyle } from './style.js';

const age = (ms) => (ms < 1000 ? `${(ms / 1000).toFixed(1)} s` : ms < 60000 ? `${Math.round(ms / 1000)} s` : `${Math.round(ms / 60000)} min`);

export class DataLiveStatus extends HTMLElement {
  connectedCallback() {
    addLiveStyle();
    this.setAttribute('role', 'status');
    // WHY throttled but never late on a change of state: the span grows every frame; a new state draws at once
    this._onLive = (e) => {
      const st = e && e.detail && e.detail.status ? e.detail.status.state : null;
      if (st !== this._drawn || performance.now() - (this._at || 0) > 250) this._draw();
    };
    this._tick = setInterval(() => { if (!document.hidden) this._draw(); }, 1000);
    this._draw();
  }

  disconnectedCallback() {
    clearInterval(this._tick);
    if (this._clock) this._clock.removeEventListener('live', this._onLive);
    this._clock = null;
  }

  /** The clock this line reports: the element `for` names (its clock), else the nearest dashboard's, else the page's. */
  _find() {
    const id = this.getAttribute('for');
    const target = id ? document.getElementById(id) : this.closest('data-dashboard');
    const c = target && target.clock ? target.clock : clockFor(target || this);
    if (c === this._clock) return c;
    if (this._clock) this._clock.removeEventListener('live', this._onLive);
    this._clock = isLiveClock(c) ? c : null;
    if (this._clock) this._clock.addEventListener('live', this._onLive);
    return this._clock;
  }

  _draw() {
    this._at = performance.now();
    const c = this._find();
    if (!c || !c.datasets.length) { this.dataset.state = 'idle'; this.textContent = ''; this.hidden = true; return; }
    this.hidden = false;
    const s = c.status();
    this._drawn = s.state;
    const all = c.datasets;
    const state = all.every((d) => d.recorded) ? 'recorded' : s.state;
    const since = s.lastData ? Date.now() - s.lastData : null;
    const n = all.filter((d) => !d.recorded).length;
    const text = {
      // a source's own word stays visible ("simulated", "replay of run 0420"): never a live line that hides it
      live: `Live${s.detail ? ` · ${s.detail}` : ''} · ${n} source${n === 1 ? '' : 's'}${since !== null ? ` · last data ${age(since)} ago` : ''}`,
      stale: `Stale · no data for ${since !== null ? age(since) : 'a while'}`,
      reconnecting: `Reconnecting${s.tries ? ` · try ${s.tries}` : ''}${since !== null ? ` · last data ${age(since)} ago` : ''}`,
      connecting: 'Connecting…',
      paused: `Paused by the host${s.detail ? `: ${s.detail}` : ''}`,
      closed: `Closed${since !== null ? ` · last data ${age(since)} ago` : ''}`,
      recorded: 'Recorded',
      idle: '',
    }[state] ?? state;
    if (this.dataset.state !== state) this.dataset.state = state;
    if (this.textContent !== text) this.textContent = text;
    this.title = s.detail ? `${text} (${s.detail})` : text;
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('data-live-status')) customElements.define('data-live-status', DataLiveStatus);
