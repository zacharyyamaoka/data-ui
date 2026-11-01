/* type: tracker — a tracker grid (docs/peps/0005-dashboard-cards.md §2b; Tremor's Tracker), and with `column:` the gate
   matrix (docs/CONTRACT.md §35; PEP 0010 §10's gate_matrix, sim2real gap #11).

     tracker:
       state:   the column whose value colours a block (a status word: the core's vocabulary, status.js)
       label:   the column shown on hover with the state (a day, a run id)
       tones:   {value: tone}, tone = good | warn | bad | muted | neutral; over the column's own `tones`, over the vocabulary
                (pass ✓ good, warn ! warn, fail ✕ bad, not_run – muted, …); a missing state is muted
       column:  the matrix's columns: one per value of this column, a header naming each, one cell per row × column
       columns: [values] the columns asked for first, in this order (each drawn even with no row), then the rest as the
                rows first show them
       order:   [best … worst] a cell several rows reach shows the worst of them (default the vocabulary's, RobotDx's ranks)
     with groupBy: one row per group (its name on the left); without: one row.

   Blocks (no `column:`): one block per row of the group in the view's sort order, as before, each carrying its state's
   glyph once it is 12 px wide. The matrix: one CSS grid (role=grid), each row a subgrid, so a column's cells share one x
   and one width in every row (WHY: Zach's "I don't like how things are not aligned"; the P5 check measures 0.5 px); a
   cell is role=gridcell with its glyph and aria-label "<row> · <column>: <word>"; a cell no row reaches is n/a (an empty
   outline, never a pass); a click or Enter opens the row in the side peek (several rows as its records); arrow keys move
   between cells. Past the panel's width the grid scrolls inside it; narrow headers turn on their side.

   Colour is never alone: every block and cell says its word (hover, aria-label) and carries a glyph, and a legend names
   the states present with theirs. WHY the classes are dv-tracker-*, not dv-status-*: <data-views> already owns .dv-status
   (its "N of M rows" line). */

import { esc, valueText, groupLabel, cellValue, statusOf, STATUS_ORDER } from '@data-ui/core';
import { StatView } from './stat.js';
import { matrixCells } from './stat-model.js';

export default class StatusView extends StatView {
  constructor(host, el) {
    super(host, el);
    // arrow keys move between a matrix's cells (WAI-ARIA's grid pattern: one tab stop, the arrows inside)
    el.addEventListener('keydown', (e) => this._arrow(e));
  }

  update(input) {
    // WHY tracker, not status: §18 (embedded chrome) made `status:` the view key that hides the status line
    const s = input.view.tracker || {};
    const { rows, columns } = input;
    if (!rows.length) return this._note('No rows match this view.');
    const all = input.groups && input.groups.length
      ? input.groups.map((g) => ({ key: g.key, label: groupLabel(columns, g.property, g.key), rows: g.rows }))
      : [{ key: null, label: '', rows }];
    const st = (state) => statusOf(state, { tones: s.tones || null, column: columns[s.state] || null });
    // WHY every group in the matrix, an empty one too: a station the groupOrder names with no rows is a row of n/a
    // cells, never left out (a gate that does not apply is not a gate that passed)
    if (s.column) return this._matrix(input, s, all, st);
    const lines = all.filter((l) => l.rows.length);
    const labelCol = s.label ? columns[s.label] : null;
    const stateOf = (r) => cellValue(r[s.state]);

    this._targets = [];
    const present = new Map();
    const html = lines.map((line) => {
      const ti = this._targets.push({ rows: line.rows, title: line.label || input.view.name }) - 1;
      const blocks = line.rows.map((r) => {
        const state = stateOf(r), x = st(state);
        const text = x.word === 'no value' ? 'no state' : x.word;
        if (!present.has(text)) present.set(text, x);
        const bi = this._targets.push({ rows: [r], title: `${line.label ? line.label + ' · ' : ''}${labelCol ? valueText(r[s.label], labelCol) : text}` }) - 1;
        const when = labelCol ? valueText(r[s.label], labelCol) : '';
        return `<span class="dv-tracker-block dv-tone-${x.tone}" role="button" tabindex="-1" data-hit="${bi}" data-state="${esc(state ?? '')}" title="${esc([when, text].filter(Boolean).join(' · '))}"><span class="dv-tracker-glyph" aria-hidden="true">${x.glyph}</span></span>`;
      }).join('');
      return `<div class="dv-tracker-row" role="listitem">${line.label ? `<span class="dv-tracker-label" data-hit="${ti}" role="button" tabindex="0" title="${esc(line.label)}">${esc(line.label)}</span>` : ''}<div class="dv-tracker-blocks">${blocks}</div></div>`;
    }).join('');
    this.el.innerHTML = `<div class="dv-tracker">${this._legend(present, s.tones)}<div class="dv-tracker-rows" role="list">${html}</div></div>`;
  }

  /** The legend: the states present, in the order the tones map lists them, then any other; each with its glyph. */
  _legend(present, tones) {
    const order = Object.keys(tones || {});
    const rank = (word) => (order.indexOf(word) + 1 || 99);
    const keys = [...present].sort(([a], [b]) => rank(a) - rank(b))
      // WHY the glyph as generated content: the key's text stays its word (a reader, and a check, reads "pass")
      .map(([text, x]) => `<span class="dv-tracker-key"><i class="dv-tracker-swatch dv-tone-${x.tone}" data-glyph="${x.glyph}" aria-hidden="true"></i>${esc(text)}</span>`).join('');
    return `<div class="dv-tracker-legend" aria-label="states">${keys}</div>`;
  }

  _matrix(input, s, lines, st) {
    const { columns, view } = input;
    const m = matrixCells(lines, { column: s.column, columns: s.columns, state: s.state, order: Array.isArray(s.order) && s.order.length ? s.order : STATUS_ORDER, read: (r, c) => cellValue(r[c]) });
    const colLabel = (v) => groupLabel(columns, s.column, v);
    const groupBy = view.groupBy && view.groupBy.property;
    this._targets = [];
    const present = new Map();
    const heads = m.columns.map((c) => {
      const text = colLabel(c);
      return `<span class="dv-tracker-col" role="columnheader" data-column="${esc(c === null ? '' : String(c))}" title="${esc(text)}"><span>${esc(text)}</span></span>`;
    }).join('');
    const corner = `<span class="dv-tracker-corner" role="columnheader"${groupBy ? ` title="${esc(columns[groupBy] ? columns[groupBy].label : groupBy)}"` : ''}></span>`;
    let first = true;
    const body = m.rows.map((row) => {
      const ti = this._targets.push({ rows: row.cells.flatMap((c) => c.rows), title: row.label || view.name }) - 1;
      const cells = row.cells.map((c) => {
        const ct = colLabel(c.column);
        const where = [row.label, ct].filter(Boolean).join(' · ');
        const tab = first ? '0' : '-1';
        first = false;
        if (c.na) {
          return `<span class="dv-tracker-cell dv-tracker-na dv-tone-muted" role="gridcell" tabindex="${tab}" data-na data-column="${esc(c.column === null ? '' : String(c.column))}" data-state="" aria-label="${esc(`${where}: n/a`)}" title="${esc(`${where}: n/a (no row)`)}"><span class="dv-tracker-glyph" aria-hidden="true">–</span></span>`;
        }
        const x = st(c.state);
        if (!present.has(x.word)) present.set(x.word, x);
        const word = x.word + (c.n > 1 ? `, worst of ${c.n} rows` : '');
        const last = c.rows[c.rows.length - 1];
        // WHY a single row opens as a record (no records list): the side peek then shows its rich record, its sections
        // and its evidence link; several rows open as the records behind the cell
        const hi = this._targets.push({ rows: c.rows, title: where, single: c.n === 1 }) - 1;
        const label = s.label ? input.columns[s.label] : null;
        const hover = [where, word, label && c.n === 1 ? valueText(last[s.label], label) : ''].filter(Boolean).join(' · ');
        return `<span class="dv-tracker-cell dv-tone-${x.tone}" role="gridcell" tabindex="${tab}" data-hit="${hi}" data-column="${esc(c.column === null ? '' : String(c.column))}" data-state="${esc(c.state === null || c.state === undefined ? '' : String(c.state))}"${c.n === 1 ? ` data-id="${esc(String(last.id))}"` : ''} aria-label="${esc(`${where}: ${word}`)}" title="${esc(hover)}"><span class="dv-tracker-glyph" aria-hidden="true">${x.glyph}</span></span>`;
      }).join('');
      const head = `<span class="dv-tracker-label" role="rowheader" data-hit="${ti}" title="${esc(row.label)}">${esc(row.label)}</span>`;
      return `<div class="dv-tracker-mrow" role="row">${head}${cells}</div>`;
    }).join('');
    this.el.innerHTML = `<div class="dv-tracker dv-tracker-matrix">${this._legend(present, s.tones)}<div class="dv-tracker-scroll"><div class="dv-tracker-grid" role="grid" aria-label="${esc(view.name || 'gate matrix')}" style="--dv-cols:${m.columns.length}"><div class="dv-tracker-head" role="row">${corner}${heads}</div>${body}</div></div></div>`;
  }

  /** A cell of one row opens its record (the rich peek); anything else opens the rows behind it (StatView's rule). */
  _hit(e, key = false) {
    const el = e.target.closest && e.target.closest('[data-hit]');
    const t = el && this._targets[Number(el.dataset.hit)];
    if (!t || !t.rows.length) return;
    if (key) e.preventDefault();
    if (t.single) { this.host.open(t.rows[0].id); return; }
    this.host.open(t.rows[t.rows.length - 1].id, { records: t.rows, title: t.title });
  }

  /** Arrow keys between a matrix's cells: left and right along a row, up and down a column; Home and End a row's ends. */
  _arrow(e) {
    const cell = e.target.closest && e.target.closest('.dv-tracker-matrix [role=gridcell]');
    if (!cell || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) return;
    const row = cell.parentElement;
    const cells = [...row.querySelectorAll(':scope > [role=gridcell]')];
    const i = cells.indexOf(cell);
    let next = null;
    if (e.key === 'ArrowLeft') next = cells[i - 1];
    else if (e.key === 'ArrowRight') next = cells[i + 1];
    else if (e.key === 'Home') next = cells[0];
    else if (e.key === 'End') next = cells[cells.length - 1];
    else {
      let r = e.key === 'ArrowUp' ? row.previousElementSibling : row.nextElementSibling;
      while (r && !r.querySelector(':scope > [role=gridcell]')) r = e.key === 'ArrowUp' ? r.previousElementSibling : r.nextElementSibling;
      next = r ? r.querySelectorAll(':scope > [role=gridcell]')[i] : null;
    }
    if (!next) return;
    e.preventDefault();
    cell.tabIndex = -1;
    next.tabIndex = 0;
    next.focus();
  }
}
