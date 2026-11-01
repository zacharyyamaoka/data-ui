/* The playback card on a live clock (docs/peps/0012-live-data.md §4): the ● LIVE control, the growing span, wall-clock
   tick labels. WHY its own file, mounted by one line: lane/dc-pb is rewriting index.js into five variants; any variant
   mounts this the same way (mountLive(el, clock, redraw)).

   Rerun's time panel: following, the control is a filled "● LIVE"; paused or replaying it is hollow with how far
   behind live the clock is ("LIVE −12.4 s"); with a source down it says so in grey. One click goes live (goLive: the
   gap is not replayed). The clock never invents progress: the lag keeps growing while nothing arrives. */

import { isLiveClock, fmtTime } from '@data-ui/core';

const CSS = `
.dv-pb-live { display: inline-flex; align-items: center; gap: 6px; margin-left: auto; padding: 3px 10px; border-radius: 999px;
  font: 600 11px/1.4 var(--dv-font, system-ui, sans-serif); letter-spacing: .04em; cursor: pointer; white-space: nowrap;
  font-variant-numeric: tabular-nums; background: transparent; color: var(--dv-muted); border: 1px solid var(--dv-border); }
.dv-pb-live::before { content: ''; width: 7px; height: 7px; border-radius: 50%; box-sizing: border-box; border: 1.5px solid currentColor; }
.dv-pb-live[aria-pressed="true"] { color: var(--dv-on-accent, #fff); background: var(--dv-accent); border-color: var(--dv-accent); }
.dv-pb-live[aria-pressed="true"]::before { background: currentColor; }
.dv-pb-live[data-state="reconnecting"], .dv-pb-live[data-state="stale"] { color: var(--dv-warn); border-color: currentColor; }
.dv-pb-live .dv-pb-lag { font-weight: 500; letter-spacing: 0; }
.dv-pb-live[hidden] { display: none; }
/* a wall-clock readout and the control are wider than "3.20 / 7.93": the row may shrink and wrap instead of widening
   the panel (or the page, on a phone) */
.dv-pb-ctl:has(> .dv-pb-live:not([hidden])) { flex: 0 1 auto; min-width: 0; flex-wrap: wrap; row-gap: 4px; }
@media (max-width: 640px) { .dv-pb-ctl:has(> .dv-pb-live:not([hidden])) { flex-basis: 100%; } }
`;

function addStyle() {
  if (typeof document === 'undefined' || document.querySelector('style[data-ui-pb-live]')) return;
  const s = document.createElement('style');
  s.dataset.uiPbLive = '';
  s.textContent = CSS;
  document.head.append(s);
}

const two = (n) => String(n).padStart(2, '0');

/** A tick's label: seconds for a playback span, a wall-clock time for a live one (Unix seconds, t ≥ 10⁹). */
export function tickText(v, span = 0) {
  if (Math.abs(v) < 1e9) return `${+v.toFixed(3)} s`;
  const d = new Date(v * 1000);
  const hms = `${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`;
  // as many decimals as the ticks are apart (about an eighth of the span), so no two ticks read the same
  if (span < 1) return `${hms}.${String(Math.floor(d.getMilliseconds() / 10)).padStart(2, '0')}`;
  if (span < 10) return `${hms}.${Math.floor(d.getMilliseconds() / 100)}`;
  return span < 7200 ? hms : `${two(d.getHours())}:${two(d.getMinutes())}`;
}

/** Put the ● LIVE control at the end of the card's control row; `redraw()` is the card's own state redraw, called (at
    most four times a second) while the span grows. Returns {destroy()}. */
export function mountLive(el, clock, redraw = () => {}) {
  addStyle();
  const row = el.querySelector('.dv-pb-ctl') || el;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'dv-pb-live';
  btn.hidden = true;
  btn.title = 'Back to live: follow the newest data (End, Ctrl+Shift+→)';
  row.append(btn);
  let last = 0, lastText = '';
  const draw = (force) => {
    const live = isLiveClock(clock) && clock.live;
    btn.hidden = !live;
    if (!live) return;
    const now = performance.now();
    if (!force && now - last < 100) return;
    last = now;
    const st = clock.status();
    const down = st.state === 'reconnecting' || st.state === 'stale' || st.state === 'closed';
    const lag = clock.lag;
    const text = clock.following && !down ? 'LIVE' : `LIVE <span class="dv-pb-lag">${down ? st.state : `−${lag < 100 ? lag.toFixed(1) : Math.round(lag)} s`}</span>`;
    if (text !== lastText) { btn.innerHTML = text; lastText = text; }
    btn.setAttribute('aria-pressed', String(!!clock.following));
    btn.dataset.state = st.state;
    btn.setAttribute('aria-label', clock.following ? 'Live: following the newest data' : `Back to live (${lag.toFixed(1)} s behind)`);
  };
  let spanAt = 0;
  const onLive = () => {
    draw(false);
    const now = performance.now();
    // WHY throttled: the span grows every frame while data streams; the ticks need not
    if (now - spanAt > 250) { spanAt = now; redraw(); }
  };
  const onState = () => draw(true);
  // following, the bar's "/ end" readout moves with t (the card redraws it only with its state)
  const endEl = el.querySelector('.dv-pb-end');
  const onTime = () => {
    // WHY forced: a seek moves t (the lag) at once; while following the lag is 0 and only the end readout moves
    if (!clock.following) draw(true);
    else if (endEl && clock.end !== null) endEl.textContent = ` / ${fmtTime(clock.end)}`;
  };
  btn.addEventListener('click', () => { clock.goLive(); draw(true); });
  clock.addEventListener('live', onLive);
  clock.addEventListener('state', onState);
  clock.addEventListener('time', onTime);
  draw(true);
  return {
    destroy() {
      clock.removeEventListener('live', onLive);
      clock.removeEventListener('state', onState);
      clock.removeEventListener('time', onTime);
      btn.remove();
    },
  };
}
