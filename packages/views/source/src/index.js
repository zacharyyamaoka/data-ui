/* type: source — the raw source view: the dataset behind the views as a plain grid, every key of every row, each
   value as stored, and the record as it sits in its file (docs/CONTRACT.md §24).

   WHY (Zach, 2026-10-26): "One view I haven't seen yet in data-ui is a raw source view: almost a plain Excel chart of
   what the data set is behind it. Helpful for debugging." So nothing here formats: no units, no decimals, no badges,
   no links; the columns are the union of the rows' keys (hidden, undeclared and `_` keys too), not the view's `order`;
   strings keep their spaces; "" , null and an absent key are three different things on screen. A value too long for
   its column ends in an ellipsis and is whole in its title and in the source panel (Zach's truthful-rendering rule).

   Keys: `rows: all | filtered` (every row as loaded, the default, or only the rows the view's filters, search and
   limit leave). The info strip says where the data came from (input.dataset.url, raw.format, raw.bytes) and copies or
   exports what is shown as RFC 4180 CSV. A row's Source button (or Enter) opens a side panel with its origin: the file
   the dataset's `origin.url` template names for it (fetched on demand, same origin only: the one fetch a view may
   make), else input.dataset.originOf(row): the JSON object as parsed, the JSONL line, or the CSV / TSV header and the
   record's lines verbatim.

   STOCK PARTS: @tanstack/virtual-core 3.19.7 (the page's one copy, from @data-ui/core), twice: the rows, and (with
   `horizontal: true`) the columns, so only the cells on screen are in the DOM and 2,196 rows × 50 columns scroll like
   40 × 8. WHY the columns too: measured 2026-10-26, laying out 30 rows of 53 cells took 16 ms a frame, and 11 ms of it
   was the element count alone (empty cells, no titles); the header keeps every column. The panel's drag handle is the core's makeResizable (§11). OURS:
   the literal cell text (literal.js), the info strip, the panel. Writes back only through the host: setView({rows}). */

import { Virtualizer, elementScroll, observeElementOffset, observeElementRect, makeResizable, mediaUrl, esc } from '@data-ui/core';
import css from './source.css';
import { literal, columnsOf, fillTemplate, toCSV, FORMATS } from './literal.js';

export { css };

const ROW = 28; // px: one single-line row
const COL = 168; // px: every column; the grid scrolls sideways inside the view, never the page
const GUTTER = 104; // px: the row number and its Source button, pinned on the left

/** The view's setting in the Layout menu. */
export function options() {
  return [{ type: 'dropdown', key: 'rows', displayName: 'Rows', default: 'all', options: { all: 'Every row as loaded', filtered: 'Only rows in the current filter' } }];
}

const bytes = (n) => (typeof n === 'number' ? `${n.toLocaleString('en-US')} bytes` : 'not known (set from script)');
const abs = (u) => { try { return new URL(u, document.baseURI).href; } catch { return u; } };

export default class SourceView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    el.innerHTML = `
      <div class="dv-source-info">
        <dl class="dv-source-meta"></dl>
        <div class="dv-source-actions">
          <label class="dv-source-toggle"><input type="checkbox" class="dv-source-filtered"> Only rows in the current filter</label>
          <button type="button" class="dv-btn dv-source-copy">Copy</button>
          <button type="button" class="dv-btn dv-source-export">Export CSV</button>
          <span class="dv-source-note" aria-live="polite"></span>
        </div>
      </div>
      <div class="dv-source-body">
        <div class="dv-source-scroll" tabindex="-1">
          <div class="dv-source-grid" role="grid" aria-label="Every row and key of the data, as stored">
            <div class="dv-source-head" role="row"></div>
            <div class="dv-source-rows" role="rowgroup"></div>
          </div>
        </div>
        <aside class="dv-source-panel" aria-label="Record source" hidden></aside>
      </div>`;
    this.$ = (sel) => el.querySelector(sel);
    this._scroll = this.$('.dv-source-scroll');
    this._rows = this.$('.dv-source-rows');
    this._panel = this.$('.dv-source-panel');
    this._cols = [];
    this._shown = [];
    this._drawn = null;
    this._panelRow = null;
    // WHY its own box under every frame: a page frame gives a view that is not a list a fixed height (data-fill, core
    // src/frame.js), so this grid scrolls itself in both directions there too
    this._virt = new Virtualizer({
      count: 0, getScrollElement: () => this._scroll, scrollToFn: elementScroll, observeElementRect, observeElementOffset,
      estimateSize: () => ROW, overscan: 12, onChange: () => this._draw(),
    });
    this._unmount = this._virt._didMount();
    this._colVirt = new Virtualizer({
      horizontal: true, count: 0, getScrollElement: () => this._scroll, scrollToFn: elementScroll, observeElementRect, observeElementOffset,
      estimateSize: () => COL, paddingStart: GUTTER, overscan: 2, onChange: () => this._draw(),
    });
    this._unmountCols = this._colVirt._didMount();
    // WHY: every side panel resizes, remembers its width and resets on a double-click (Zach, memory
    // feedback_resizable_panels; docs/CONTRACT.md §11)
    this._resizer = makeResizable(this._panel, { edge: 'left', min: 280, max: 1200, keep: 160, key: `source:${host.element.id || 'data-views'}`, label: 'the source panel' });
    this._wire();
  }

  destroy() {
    if (this._unmount) this._unmount();
    if (this._unmountCols) this._unmountCols();
    if (this._resizer) this._resizer.destroy();
    this.host.element.removeEventListener('keydown', this._onKey);
    this._fetching = null;
    this.el.innerHTML = '';
  }

  update(input) {
    this.input = input;
    // every row as loaded is the element's dataset (docs/CONTRACT.md §6 `data`); input.rows is what the view's filters,
    // search and limit leave
    const data = this.host.element.data;
    const all = (data && data.rows) || input.rows;
    if (all !== this._all || all.length !== this._allLength) {
      this._all = all;
      this._allLength = all.length;
      this._cols = columnsOf(all);
      this._loadedAt = null;
      this._assigned = this._cols.includes('id') && all.some((r) => this._idAssigned(r));
      // new data (a reload, or rows set from script): a panel on a row that is gone closes
      if (this._panelRow && !all.includes(this._panelRow)) this._close();
    }
    this._filtered = input.view.rows === 'filtered';
    this._shown = this._filtered ? input.rows : all;
    this._info();
    this._head();
    const headH = this.$('.dv-source-head').offsetHeight;
    this._virt.setOptions({ ...this._virt.options, count: this._shown.length, scrollMargin: headH });
    this._virt._willUpdate();
    this._virt.measure();
    this._colVirt.setOptions({ ...this._colVirt.options, count: this._cols.length });
    this._colVirt._willUpdate();
    this._colVirt.measure();
    this._drawn = null;
    this._draw();
  }

  // ------------------------------------------------------------------ the info strip and the header
  _info() {
    const ds = this.input.dataset;
    const raw = ds.raw || {};
    const src = this.host.element.getAttribute('src');
    const link = (u) => `<a href="${esc(u)}" rel="noopener">${esc(u)}</a>`;
    const items = [
      ['Data file', ds.url ? link(ds.url) : 'none (set from script)'],
      ...(raw.url && raw.url !== ds.url ? [['Rows from', link(raw.url)]] : []),
      ['.base file', src ? link(abs(src)) : 'none'],
      ['Format', esc(FORMATS[raw.format] || raw.format || 'not known')],
      ['Size', esc(bytes(raw.bytes))],
      ['Rows', `${this._all.length.toLocaleString('en-US')} loaded${this._filtered ? ` · ${this._shown.length.toLocaleString('en-US')} in the current filter` : ''}`],
      ['Columns', String(this._cols.length)],
    ];
    this.$('.dv-source-meta').innerHTML = items.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join('');
    this.$('.dv-source-filtered').checked = this._filtered;
  }

  _head() {
    const props = this.input.columns;
    this.$('.dv-source-grid').style.width = `${GUTTER + COL * this._cols.length}px`;
    const th = (k) => {
      const p = props[k];
      const type = p ? p.type || 'text' : 'undeclared';
      const marks = [type, ...(k === 'id' && this._assigned ? ['assigned by data-ui'] : [])].join(' · ');
      return `<div class="dv-source-th${p ? '' : ' dv-source-undeclared'}" role="columnheader" title="${esc(`${k} — ${marks}`)}"><span class="dv-source-name">${esc(k)}</span><span class="dv-source-type">${esc(marks)}</span></div>`;
    };
    this.$('.dv-source-head').innerHTML = `<div class="dv-source-gutter dv-source-corner" role="columnheader" title="the row's place in the file as loaded">#</div>${this._cols.map(th).join('')}`;
  }

  _idAssigned(row) {
    const o = this.input.dataset.originOf(row);
    return !!(o && o.idAssigned);
  }

  /** A row's 1-based place among the rows as loaded (the same as its place on screen unless the view filters). */
  _loadedIndex(row, i) {
    if (!this._filtered) return i + 1;
    if (!this._loadedAt) this._loadedAt = new Map(this._all.map((r, k) => [r, k + 1]));
    return this._loadedAt.get(row) || '';
  }

  // ------------------------------------------------------------------ the rows
  _draw() {
    if (!this.input) return;
    const rows = this._rows;
    if (!this._shown.length) {
      rows.style.height = '';
      rows.innerHTML = '<p class="dv-source-none">No rows.</p>';
      this._drawn = null;
      return;
    }
    const items = this._virt.getVirtualItems();
    const first = items.length ? items[0].index : 0;
    const last = items.length ? items[items.length - 1].index : -1;
    const total = this._virt.getTotalSize();
    const cols = this._colVirt.getVirtualItems();
    const c0 = cols.length ? cols[0].index : 0;
    const c1 = cols.length ? cols[cols.length - 1].index : -1;
    const d = this._drawn;
    if (d && d.first === first && d.last === last && d.total === total && d.c0 === c0 && d.c1 === c1) return; // nothing moved
    // WHY keep the focused row: a redraw replaces every row, and ↑/↓ need the row to stay focused through it
    const had = document.activeElement && document.activeElement.closest && document.activeElement.closest('.dv-source-row');
    const keep = had && this.el.contains(had) ? had.dataset.i : null;
    const margin = this._virt.options.scrollMargin || 0;
    rows.style.height = `${total}px`;
    rows.innerHTML = items.map((it) => this._rowHtml(it.index, it.start - margin, c0, c1)).join('');
    this._drawn = { first, last, total, c0, c1 };
    if (keep !== null) { const again = rows.querySelector(`.dv-source-row[data-i="${keep}"]`); if (again) again.focus({ preventScroll: true }); }
  }

  /** One row: its gutter, a spacer as wide as the columns left of the window, then columns c0..c1. */
  _rowHtml(i, top, c0, c1) {
    const row = this._shown[i];
    const n = this._loadedIndex(row, i);
    const idMade = this._assigned && this._idAssigned(row);
    const cells = this._cols.slice(c0, c1 + 1).map((k, j) => {
      const { text, kind } = literal(row, k);
      const at = ` data-k="${c0 + j}" aria-colindex="${c0 + j + 2}"`;
      if (kind === 'absent') return `<div class="dv-source-td dv-source-absent" role="gridcell"${at} title="absent"></div>`;
      const made = k === 'id' && idMade;
      const title = made ? `${text} (assigned by data-ui: the record has no id)` : text;
      // a value with a line break shows its first line and an ellipsis; the whole value is in the title and the panel
      const br = /\r\n|\r|\n/.exec(text);
      const body = br ? `${esc(text.slice(0, br.index))}<span class="dv-source-more" aria-hidden="true">…</span>` : esc(text);
      return `<div class="dv-source-td dv-source-${kind}${made ? ' dv-source-made' : ''}" role="gridcell"${at} title="${esc(title)}">${body}</div>`;
    }).join('');
    const pad = c0 > 0 ? `<div class="dv-source-pad" style="width:${c0 * COL}px"></div>` : '';
    const on = row === this._panelRow ? ' dv-active' : '';
    return `<div class="dv-source-row${on}" role="row" data-i="${i}" tabindex="0" style="transform:translateY(${top}px)">`
      + `<div class="dv-source-gutter" role="rowheader"><span class="dv-source-n" title="row ${n} as loaded">${n}</span><button type="button" class="dv-btn dv-source-open" tabindex="-1">Source</button></div>${pad}${cells}</div>`;
  }

  // ------------------------------------------------------------------ the source panel
  _open(i) {
    const row = this._shown[i];
    if (!row) return;
    this._panelRow = row;
    const panel = this._panel;
    const ds = this.input.dataset;
    const id = row.id !== undefined ? String(row.id) : String(i + 1);
    const tpl = ds.origin && ds.origin.url;
    const file = tpl ? fillTemplate(tpl, row) : null;
    const head = `<header class="dv-source-panel-head"><h2>Source <code>${esc(id)}</code></h2><button type="button" class="dv-btn dv-source-close" aria-label="Close the source panel">✕</button></header>`;
    panel.hidden = false;
    if (file) {
      const url = mediaUrl(file, ds);
      panel.innerHTML = `${head}<p class="dv-source-where">Origin file <code>${esc(file)}</code> (the data's <code>origin.url</code>, <code>${esc(tpl)}</code>)</p><p class="dv-source-path"><a href="${esc(url)}" rel="noopener">${esc(url)}</a></p><pre class="dv-source-text dv-source-file-text">Loading…</pre>`;
      this._fetch(url, row);
    } else {
      panel.innerHTML = `${head}${this._recordHtml(row, tpl ? `The data's <code>origin.url</code> (<code>${esc(tpl)}</code>) names a property this row has no value for, so this is the record in the data file.` : '')}`;
      this._fillRecord(row);
    }
    this._drawn = null;
    this._draw();
    panel.scrollTop = 0;
  }

  /** The record as it sits in the data file (input.dataset.originOf). */
  _recordHtml(row, lead = '') {
    const ds = this.input.dataset;
    const o = ds.originOf(row);
    const name = esc(((ds.raw && ds.raw.url) || ds.url || 'the data').split('/').pop());
    const note = lead ? `<p class="dv-source-where">${lead}</p>` : '';
    if (!o) return `${note}<p class="dv-source-where">This row has no record in a file (it was not among the rows as loaded).</p>`;
    if (o.kind === 'csv' || o.kind === 'tsv') {
      const nums = (from, text) => text.split(/\r\n|\r|\n/).map((_, k) => from + k).join('\n');
      return `${note}<p class="dv-source-where"><code>${name}</code>, ${o.kind.toUpperCase()} line ${o.line}: the header and the record, verbatim</p>
        <div class="dv-source-lines"><pre class="dv-source-lnums" aria-hidden="true">${nums(o.header.line, o.header.text)}</pre><pre class="dv-source-text dv-source-header-text"></pre></div>
        <div class="dv-source-lines"><pre class="dv-source-lnums" aria-hidden="true">${nums(o.line, o.text)}</pre><pre class="dv-source-text dv-source-record-text"></pre></div>`;
    }
    const where = o.kind === 'jsonl' ? `<code>${name}</code>, JSONL line ${o.line}, as parsed` : `<code>${name}</code>: the record as parsed, before data-ui added anything`;
    return `${note}<p class="dv-source-where">${where}${o.idAssigned ? ' (it has no <code>id</code>; data-ui assigned one)' : ''}</p><pre class="dv-source-text dv-source-record-text"></pre>`;
  }

  /** The record's text into its <pre>s as text, not HTML: the HTML parser would turn a CR LF inside a quoted field into LF. */
  _fillRecord(row) {
    const o = this.input.dataset.originOf(row);
    if (!o) return;
    const set = (sel, text) => { const pre = this._panel.querySelector(sel); if (pre) pre.textContent = text; };
    set('.dv-source-record-text', o.text);
    if (o.header) set('.dv-source-header-text', o.header.text);
  }

  /** The one fetch a view makes (docs/CONTRACT.md §24): a row's declared origin file, same origin, on demand. */
  async _fetch(url, row) {
    const token = (this._fetching = {});
    const pre = () => this._panel.querySelector('.dv-source-file-text');
    let text, error = null;
    try {
      if (new URL(url).origin !== location.origin) throw new Error('it is on another site, and a view loads nothing from another site');
      const r = await fetch(url);
      if (!r.ok) throw new Error(`the server answered ${r.status}`);
      text = await r.text();
    } catch (err) { error = err.message; }
    if (token !== this._fetching || this._panelRow !== row || !pre()) return;
    if (error === null) { pre().textContent = text; return; }
    pre().remove();
    this._panel.insertAdjacentHTML('beforeend', `<p class="dv-source-err">Could not load the origin file: ${esc(error)}.</p>${this._recordHtml(row)}`);
    this._fillRecord(row);
  }

  _close() {
    if (this._panel.hidden) return;
    this._panel.hidden = true;
    this._panel.innerHTML = '';
    this._panelRow = null;
    this._fetching = null;
    this._drawn = null;
    this._draw();
  }

  // ------------------------------------------------------------------ copy and export
  _csv() { return toCSV(this._cols, this._shown); }

  _say(text) {
    const note = this.$('.dv-source-note');
    note.textContent = text;
    clearTimeout(this._noteTimer);
    this._noteTimer = setTimeout(() => { if (note.isConnected) note.textContent = ''; }, 4000);
  }

  async _copy() {
    const csv = this._csv();
    const what = `${this._shown.length.toLocaleString('en-US')} rows × ${this._cols.length} columns`;
    try {
      await navigator.clipboard.writeText(csv);
      this._say(`Copied ${what} as CSV`);
    } catch {
      // no clipboard permission (an http page, a sandbox): the selection fallback
      const area = document.createElement('textarea');
      area.value = csv;
      area.className = 'dv-sr';
      this.el.append(area);
      area.select();
      const ok = document.execCommand && document.execCommand('copy');
      area.remove();
      this._say(ok ? `Copied ${what} as CSV` : 'Copy was refused by the browser; use Export CSV');
    }
  }

  _export() {
    const blob = new Blob([this._csv()], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${this.input.dataset.id}.csv`;
    a.hidden = true;
    this.el.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    this._say(`Exported ${a.download}`);
  }

  // ------------------------------------------------------------------ events
  _wire() {
    this.el.addEventListener('click', (e) => {
      const t = e.target;
      if (t.closest('.dv-source-close')) { this._close(); return; }
      if (t.closest('.dv-source-copy')) { this._copy(); return; }
      if (t.closest('.dv-source-export')) { this._export(); return; }
      const open = t.closest('.dv-source-open');
      if (open) { const tr = open.closest('.dv-source-row'); this._open(Number(tr.dataset.i)); }
    });
    this.el.addEventListener('change', (e) => {
      if (e.target.matches('.dv-source-filtered')) this.host.setView({ rows: e.target.checked ? 'filtered' : null });
    });
    this._rows.addEventListener('keydown', (e) => {
      const tr = e.target.closest && e.target.closest('.dv-source-row');
      if (!tr) return;
      const i = Number(tr.dataset.i);
      if (e.key === 'Enter') { e.preventDefault(); this._open(i); return; }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const j = i + (e.key === 'ArrowDown' ? 1 : -1);
        if (j < 0 || j >= this._shown.length) return;
        this._virt.scrollToIndex(j, { align: 'auto' });
        requestAnimationFrame(() => { const next = this._rows.querySelector(`.dv-source-row[data-i="${j}"]`); if (next) next.focus(); });
      }
    });
    // Escape closes the panel wherever focus is inside the element (the host's own Escape closes its peek and menus)
    this._onKey = (e) => { if (e.key === 'Escape' && !this._panel.hidden) this._close(); };
    this.host.element.addEventListener('keydown', this._onKey);
  }
}
