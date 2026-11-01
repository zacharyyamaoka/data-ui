/* A page to play with (docs/CONTRACT.md §40): the element keeps every edit in memory; this file adds the three things a playground needs and
   a table does not. What is typed stays through a reload (one snapshot in this browser's localStorage), New blank table starts from nothing,
   and Reset to the sample goes back. WHY a snapshot and no hooks: nothing here owns the data, so there is nothing for a hook to decide.
   Written only once something has changed, so an untouched page always shows the sample. */
const KEY = 'data-ui/notion-table/v1';
const el = document.querySelector('data-views');
const BLANK = {
  data: { id: 'notion-table', title: 'Blank table', titleProperty: 'name', properties: { name: { type: 'text', label: 'Name' } }, rows: [] },
  base: { views: [{ type: 'table', name: 'Table', addRow: true }] },
  filters: null,
};

const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch { return null; } };
const write = (text) => { try { localStorage.setItem(KEY, text); } catch { /* a private window: this visit only */ } };
const forget = () => { try { localStorage.removeItem(KEY); } catch { /* nothing was kept */ } };
// WHY back to the bare path: the link may carry a filter or a view of the table being left
const restart = () => location.replace(location.pathname);

/** What a reload needs: the rows and their columns, the views with the open one as it stands, the filter. */
function snapshot() {
  const { id, title, titleProperty, properties, rows } = el.data;
  const views = el.presets.map((v) => (v.name === el.origin.name ? el.view : v));
  return JSON.stringify({ data: { id, title, titleProperty, properties, rows }, base: { properties: el.base.properties, views }, filters: el.filters ?? null });
}

const bar = document.createElement('div');
bar.className = 'data-ui';
bar.style.cssText = 'display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin:0 0 8px';
bar.innerHTML = `<span data-hint style="flex:1 1 260px;color:var(--dv-muted);font-size:13px">Type in any cell, paste from a spreadsheet, right-click a row or a header. It stays in this browser.</span>
  <button type="button" class="dv-btn" data-new-blank>New blank table</button><button type="button" class="dv-btn" data-reset-sample>Reset to the sample</button>`;
el.parentElement.before(bar);
bar.querySelector('[data-new-blank]').addEventListener('click', () => { write(JSON.stringify(BLANK)); restart(); });
bar.querySelector('[data-reset-sample]').addEventListener('click', () => { forget(); restart(); });

const saved = read();
if (saved) el.style.visibility = 'hidden';
el.addEventListener('data-views-render', () => {
  if (saved) {
    el.baseText = null;
    el.data = saved.data;
    el.base = saved.base;
    el.filters = saved.filters;
    el.style.visibility = '';
  }
  let last = saved ? JSON.stringify(saved) : snapshot();
  let timer = 0;
  el.addEventListener('data-views-change', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { const now = snapshot(); if (now !== last) { last = now; write(now); } }, 120);
  });
}, { once: true });
