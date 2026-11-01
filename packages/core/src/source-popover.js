/* The source popover (docs/CONTRACT.md §36, its amendment "the source popover"; docs/peps/0015-source-precedence.md):
   the item menu of a value two or more sources state, opened by a right-click, the menu key or a long-press on it in
   the table, the cards, the record page and the side peek (<data-views> finds it by the mark format.js sourcesAttr()
   writes, and opens openItemMenu with what this returns: the item menu, not a second menu system).

   One radio row per source that states the value, in precedence order (precedence.js sourceRows()): its place, its
   name and its rung's label on the ladder, its value exactly as stated (its text, else its value, and its unit), its
   basis, date and note, and a private address as plain text. The nominal row is checked and says "nominal"; a row whose
   value disagrees says "differs" and is tinted as a source's column tints it; a row picked by hand carries the pin. A
   source whose address is a link target (§22's rule: an http(s) URL or a relative path, resolved against the data file)
   has its link as a menu item of its own, right after its row (WHY its own: a link inside a menu item is no link to a
   screen reader, and a click on it would pick the row too).

   Picking a row: setPrecedence({ov: {<row>: <source>}}), the precedence's own source clearing the pick (never pinning what
   precedence shows anyway); "Back to precedence" heads the menu while the row is picked by hand. The value's pill opens this same
   menu. WHY "Back to precedence" and not "Back to default": it says what the row goes back to,
   and "default" is the ladder's order in the status line ("Precedence changed from default"), which clearing a pick
   does not restore when the order was changed. A pick is the row's (CONTRACT §36: ov is keyed by row), so the menu says
   so when the row has another value with several sources.

   Pure (strings in, items out): no DOM. */

import { esc, BASIS, cellText, valueText, isLinkTarget, linkCell, mediaUrl, isEmpty } from './format.js';
import { sourceRows } from './precedence.js';

/** The pin a row picked by hand carries (the table's Nominal source cell draws the same one). */
export const PIN = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10.2 1.6l4.2 4.2-1.3.6-2.4 2.4.2 3-1.3 1.3-2.5-2.5-3.6 3.6-.8-.8 3.6-3.6-2.5-2.5 1.3-1.3 3 .2 2.4-2.4z"/></svg>';

/** The popover of row `id`'s value: {items, opts} for openItemMenu, or null when fewer than two sources state it.
      cell     the value as loaded ({sources: [...], unit?})
      view     the precedence state ({order, ov})
      info     precedenceOf()'s {sources, ladder} (el.precedence carries both)
      column   the value's column ({id, label, unit?, unitText?, decimals?, labels?})
      rowUnit  the row's unit (its unit column's value), when the column names one
      base     the data file's URL: a relative address resolves against it
      title    the row's title (its title property as drawn)
      rowWide  the row has another value with several sources (a pick is the row's)
      pick     (source | null) => the precedence call; null clears the row's pick */
export function sourcesMenu({ cell, view, info, id, column = {}, rowUnit = null, base = null, title = '', rowWide = false, pick }) {
  const { rows, via, prec } = sourceRows(cell, view, id, info);
  if (rows.length < 2) return null;
  const col = column || {};
  const said = (r) => {
    const c = r.cell;
    const text = cellText(c) ?? valueText(c.value, col);
    // the entry's own unit (else the cell's: entryCell), else the row's unit column, else the column's: a value stated in
    // another unit keeps it (3800 mN·m is not 3.8 N·m's statement)
    const unit = !isEmpty(c.unit) ? String(c.unit) : !isEmpty(rowUnit) ? String(rowUnit) : !isEmpty(col.unitText) ? String(col.unitText) : '';
    return { text, unit };
  };
  const valueHtml = (r) => { const { text, unit } = said(r); return `${esc(text)}${unit ? ` <span class="dv-u">${esc(unit)}</span>` : ''}`; };
  const link = (r) => {
    const a = r.cell.sourceUrl;
    if (isEmpty(a) || !isLinkTarget(String(a))) return null;
    const href = mediaUrl(String(a), { url: base });
    // labelled as linkCell labels a link: the address as written, without its http(s)://
    return { href, cls: `dv-src-pop-link${r.state === 'differs' ? ' dv-src-pop-tint' : ''}`, attr: `data-src-link="${esc(r.source)}" data-src-state="${r.state}" title="${esc(href)}"`,
      html: `<span class="dv-src-pop-url">${esc(String(a).replace(/^https?:\/\//, ''))}</span> <span class="dv-src-pop-arrow" aria-hidden="true">↗</span>` };
  };
  const row = (r, linked) => {
    const c = r.cell;
    const b = c.basis ? BASIS[c.basis] : null;
    const meta = [
      c.basis ? `<span class="dv-src-pop-basis" data-basis="${esc(c.basis)}">${b ? `<span class="dv-src-pop-mark" aria-hidden="true">${esc(b.mark)}</span> ${esc(b.label)}` : esc(c.basis)}</span>` : '',
      !isEmpty(c.asOf) ? `<span class="dv-src-pop-asof">as of ${esc(c.asOf)}</span>` : '',
      !isEmpty(c.note) ? `<span class="dv-src-pop-note">${esc(c.note)}</span>` : '',
      // §22's rule: an address that is no link target (a private source) is its label, as plain text
      !isEmpty(c.sourceUrl) && !isLinkTarget(String(c.sourceUrl)) ? `<span class="dv-src-pop-addr">${linkCell({ value: String(c.sourceUrl) })}</span>` : '',
    ].filter(Boolean).join('');
    const marks = `${r.pinned ? `<span class="dv-src-pin" title="Chosen by hand for this row">${PIN}<span class="dv-sr">chosen by hand</span></span>` : ''}`
      + `${r.nominal ? '<span class="dv-src-pop-nominal">nominal</span>' : ''}${r.state === 'differs' ? '<span class="dv-src-pop-differs">differs</span>' : ''}`;
    return {
      role: 'menuitemradio', checked: r.nominal,
      cls: `dv-src-pop-row${linked ? ' dv-src-pop-linked' : ''}${r.state === 'differs' ? ' dv-src-pop-tint' : ''}`,
      attr: `data-source="${esc(r.source)}" data-src-state="${r.state}"`,
      html: `<span class="dv-src-pop-rank">${r.rank === null ? '' : r.rank}</span><span class="dv-src-pop-top"><span class="dv-src-pop-name">${esc(r.name)}</span>${marks}`
        + `<span class="dv-src-pop-val">${valueHtml(r)}</span></span>${r.rungLabel ? `<span class="dv-src-pop-rung">${esc(r.rungLabel)}</span>` : ''}`
        + `${meta ? `<span class="dv-src-pop-meta">${meta}</span>` : ''}`,
      // the row in use changes nothing; precedence's own source clears the pick
      run: () => { if (!r.nominal) pick(r.source === prec ? null : r.source); },
    };
  };
  const items = [];
  if (via === 'override' && prec !== null) {
    const back = rows.find((r) => r.source === prec);
    items.push({ attr: 'data-src-back', cls: 'dv-src-pop-back', run: () => pick(null),
      html: `<span class="dv-src-pop-backname">Back to precedence</span>${back ? `<span class="dv-src-pop-backval">${esc(back.name)} · ${valueHtml(back)}</span>` : ''}` });
  }
  for (const r of rows) {
    const l = link(r);
    items.push(row(r, !!l));
    if (l) items.push(l);
  }
  const what = [title, col.label || col.id].filter((x) => !isEmpty(x)).join(' · ');
  return {
    items,
    opts: {
      cls: 'dv-src-pop',
      title: `${what} · ${rows.length} sources, in precedence order`,
      label: `Sources of ${what}`,
      note: rowWide ? `Picking a source applies to every value of ${title || 'this row'} it states.` : '',
    },
  };
}
