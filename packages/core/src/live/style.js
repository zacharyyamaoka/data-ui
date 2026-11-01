/* The live tier's few styles (docs/peps/0012-live-data.md): the tail's "N new · Resume" and <data-live-status>.
   WHY in JS, added once on first use: only a page with live data pays for them, and the core's stylesheet list
   (build.mjs) stays untouched. Colours only from the --dv-* tokens (CONTRACT §4). */

const CSS = `
data-views[data-live] { position: relative; }
.dv-live-new { position: absolute; left: 50%; transform: translateX(-50%); bottom: 14px; z-index: 6;
  font: 500 12px/1 var(--dv-font, system-ui, sans-serif); padding: 7px 12px; border-radius: 999px; cursor: pointer;
  color: var(--dv-on-accent, #fff); background: var(--dv-accent, #2563eb); border: 0;
  box-shadow: 0 1px 2px rgb(0 0 0 / .18), 0 4px 12px rgb(0 0 0 / .12); font-variant-numeric: tabular-nums; }
.dv-live-new:hover { filter: brightness(1.08); }
.dv-live-new:focus-visible { outline: 2px solid var(--dv-accent, #2563eb); outline-offset: 2px; }
.dv-live-new[hidden] { display: none; }
data-live-status { display: inline-flex; align-items: center; gap: 6px; font: 12px/1.3 var(--dv-font, system-ui, sans-serif);
  color: var(--dv-muted, #6b7280); white-space: nowrap; font-variant-numeric: tabular-nums; }
data-live-status::before { content: ''; flex: none; width: 7px; height: 7px; border-radius: 50%; box-sizing: border-box;
  border: 1.5px solid currentColor; }
data-live-status[data-state="live"]::before { background: var(--dv-accent, #2563eb); border-color: var(--dv-accent, #2563eb); }
data-live-status[data-state="stale"], data-live-status[data-state="reconnecting"] { color: var(--dv-warn, #b45309); }
data-live-status[data-state="recorded"]::before, data-live-status[data-state="closed"]::before { border-radius: 1px; }
`;

export function addLiveStyle() {
  if (typeof document === 'undefined' || document.querySelector('style[data-ui-live]')) return;
  const s = document.createElement('style');
  s.dataset.uiLive = '';
  s.textContent = CSS;
  document.head.append(s);
}
