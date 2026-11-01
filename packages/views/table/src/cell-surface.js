/* How a markdown cell is edited (docs/CONTRACT.md §46). Zach, 2026-10-31: "that is the goal as well for the actual one to be two
   ways": compact in the table, and a click edits that section's raw markdown. He chose the Sheet from five ("Ok go ahead with Sheet it shall
   work for now!"): a side panel that follows the cell and autosaves (cell-sheet.js), the default. The way before it, the row growing to hold
   the box, stays as an option (`growInPlace` below). The surface is one swappable piece: `el.cellSurface` chooses, and nothing else in the
   table knows which is in use.

   A custom surface is `(ctx) => ({fit(), close()})`. `ctx`: {cell() (the <td>, found again after a redraw), form, box (the textarea), row, property,
   measure(td) (tell the table the row's height changed)}. `fit` runs when the editor opens, on each keystroke and after each redraw of the
   rows; `close` when it leaves. The editor keeps its own commit, cancel and files: a surface only decides how the cell makes room. */

/** Which surface a page chose for its markdown cells: 'sheet' (the default, cell-sheet.js), 'grow' (the row grows to hold the box, below), or
    'custom' (a function in `el.cellSurface`, which draws the editor in the cell the way it says). `el.cellSurface = 'grow'` or the
    attribute `cell-surface="grow"` opts out of the Sheet. WHY the Sheet is the default (Zach, 2026-10-31): selection, not a mode. */
export function surfaceOf(el) {
  const set = el.cellSurface;
  if (typeof set === 'function') return 'custom';
  const named = String(typeof set === 'string' ? set : (el.getAttribute && el.getAttribute('cell-surface')) || '').trim().toLowerCase();
  return named === 'grow' || named === 'grow-in-place' ? 'grow' : 'sheet';
}

/** The row grows to hold the box, in the table's flow, so the rows below move down and nothing is covered. */
export function growInPlace({ cell, form, measure }) {
  form.classList.add('dv-celledit-grow');
  return {
    fit() {
      const td = cell();
      if (!td) return;
      td.style.height = `${Math.ceil(form.getBoundingClientRect().height)}px`;
      measure(td);
    },
    close() {
      const td = cell();
      if (!td) return;
      td.style.height = '';
      measure(td);
    },
  };
}
