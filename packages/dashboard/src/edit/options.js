/* The one options pane: what the selected panel is (Grafana's panel options, Shopify's settings sidebar, Retool's
   inspector), every change a text edit that shows on the canvas and in the outline at once. The same pane is the review:
   Save opens the diff here, so there is one right-hand side, whatever it is showing. */

import { esc } from '../../../core/src/format.js';
import { panelsOf, renamePanel, resizePanel, hidePanel, removePanel, movePanel, addPanel, setSignal, setViewType, setPanelText, typesFor, signalOf, signalChoices, TYPE_NAMES } from './ops.js';
import { icon, typeIcon, typeName, diffHtml, changesHtml } from './ui.js';

export class Options {
  constructor(ed, pane) {
    this.ed = ed;
    this.pane = pane;
    pane.body.addEventListener('click', (e) => this.click(e));
    pane.body.addEventListener('change', (e) => this.change(e));
    pane.body.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('input')) { e.preventDefault(); e.target.blur(); } });
  }

  draw() {
    if (this.ed.review) { this.drawReview(); return; }
    const { ed, pane } = this;
    pane.heading('Options');
    const had = pane.body.contains(document.activeElement) ? document.activeElement.dataset.dde : null;
    const p = ed.sel ? ed.panel(ed.sel) : null;
    pane.body.innerHTML = p ? this.panelHtml(p) : '<p class="dde-note">Select a panel, on the grid or in the outline.</p>';
    if (had) { const f = pane.body.querySelector(`[data-dde="${CSS.escape(had)}"]`); if (f) f.focus(); }
  }

  panelHtml(p) {
    const { ed } = this;
    const columns = ed.dash.dash.columns;
    const panels = panelsOf(ed.s.text);
    const at = panels.findIndex((x) => x.key === p.key);
    // the open tab of a panel of tabs; else its one view
    const open = p.views.length > 1 ? ed.dash._shownView(p) : null;
    const v = (open && p.views.find((x) => x.name === open)) || p.views[0];
    const size = `<section class="dde-sec"><div class="dde-two">
        <label class="dde-field"><span>Width</span><span class="dde-unit"><input type="number" min="1" max="${columns}" value="${p.w}" data-dde="w" aria-label="Width in columns, 1 to ${columns}"><small>of ${columns}</small></span></label>
        ${p.text === null ? `<label class="dde-field"><span>Height</span><span class="dde-unit"><input type="number" min="1" value="${p.h || ''}" placeholder="auto" data-dde="h" aria-label="Height in rows"><small>rows</small></span></label>` : ''}
      </div>
      <div class="dde-field"><span>Position</span><span class="dde-row-btns"><button type="button" class="dde-btn" data-dde="up" aria-label="Move up"${at > 0 ? '' : ' disabled'}>${icon('up')}</button><button type="button" class="dde-btn" data-dde="down" aria-label="Move down"${at < panels.length - 1 ? '' : ' disabled'}>${icon('down')}</button></span></div>
      <label class="dde-check"><input type="checkbox" data-dde="visible"${p.hidden ? '' : ' checked'}><span>Visible</span></label></section>`;
    const foot = `<footer class="dde-sec dde-foot">${p.text === null ? '<button type="button" class="dde-btn" data-dde="duplicate">Duplicate</button>' : ''}<button type="button" class="dde-btn" data-dde="remove">Remove</button></footer>`;
    if (p.text !== null) return `<section class="dde-sec"><label class="dde-field dde-col"><span>Note</span><textarea rows="6" data-dde="text">${esc(p.text)}</textarea></label></section>${size}${foot}`;
    const cols = ed.s.columns(p.dataset);
    const sig = signalOf(v);
    const type = v.type || 'table';
    const types = typesFor(v, cols);
    const ds = p.dataset && ed.dash.dash.datasets[p.dataset];
    return `<section class="dde-sec">
        <label class="dde-field dde-col"><span>Title</span><input type="text" data-dde="title" value="${esc(p.title || p.views[0].name)}"></label>
        ${ds ? `<p class="dde-field"><span>Data</span><span class="dde-value">${esc(ds.label || p.dataset)}</span></p>` : ''}
      </section>
      <section class="dde-sec">
        ${types.length > 1 ? `<div class="dde-field dde-col"><span>${open ? `${esc(open)} shows as` : 'Show as'}</span><div class="dde-seg" role="radiogroup" aria-label="View type">${types.map((t) => `<button type="button" role="radio" aria-checked="${t === type}" data-dde="type-${esc(t)}" data-type="${esc(t)}" title="${esc(TYPE_NAMES[t] || t)}">${typeIcon(t)}<span>${esc(typeName(t))}</span></button>`).join('')}</div></div>` : ''}
        ${sig !== null ? `<label class="dde-field dde-col"><span>Plots</span><select data-dde="signal">${signalChoices(cols, sig).map((c) => `<option value="${esc(c)}"${c === sig ? ' selected' : ''}>${esc(cols.labels[c] || c)}</option>`).join('')}</select></label>` : ''}
      </section>${size}${foot}`;
  }

  /** The review: the change in words, the diff, the message, and only then Save. */
  drawReview() {
    const { ed, pane } = this;
    pane.heading('Review');
    const r = ed.review;
    const message = pane.body.querySelector('[data-dde="save-message"]');
    const keep = message ? message.value : '';
    pane.body.innerHTML = `<section class="dde-sec dde-review" data-dde="review">
        ${r.moved ? '<p class="dde-moved" role="alert">This file changed after you started editing. Saving replaces those changes.</p>' : ''}
        ${changesHtml(ed.s.changes())}
        ${diffHtml(ed.s.diff())}
        <label class="dde-field dde-col"><span>Message</span><textarea rows="2" data-dde="save-message" placeholder="Describe your changes (optional)">${esc(keep)}</textarea></label>
        ${r.copy ? `<label class="dde-field dde-col"><span>New dashboard title</span><input type="text" data-dde="save-copy-title" value="${esc(`${ed.s.title} (copy)`)}"></label>` : ''}
        <p class="dde-note" role="status" data-dde="save-status">${esc(r.status || `The host saves ${ed.s.title}; data-ui never writes the file.`)}</p>
      </section>
      <footer class="dde-sec dde-foot"><button type="button" class="dde-btn" data-dde="save-back">Back</button><button type="button" class="dde-btn" data-dde="save-copy">Save as copy</button><button type="button" class="dde-btn dde-primary" data-dde="save-go">Save</button></footer>`;
  }

  click(e) {
    const b = e.target.closest('[data-dde]');
    if (!b || !this.pane.body.contains(b)) return;
    const { ed } = this;
    const what = b.dataset.dde;
    if (what === 'save-back') { ed.closeReview(); return; }
    if (what === 'save-go') { ed.commit(); return; }
    if (what === 'save-copy') {
      const title = this.pane.body.querySelector('[data-dde="save-copy-title"]');
      if (title && title.value.trim()) { ed.commit({ title: title.value.trim() }); return; }
      ed.review.copy = true;
      this.drawReview();
      this.pane.body.querySelector('[data-dde="save-copy-title"]').focus();
      return;
    }
    const p = ed.sel ? ed.panel(ed.sel) : null;
    if (!p) return;
    if (what.startsWith('type-')) { if (b.getAttribute('aria-checked') !== 'true') this.retype(p, b.dataset.type); return; }
    if (what === 'remove') { ed.apply((t) => removePanel(t, p.i), 'remove'); return; }
    if (what === 'duplicate') { this.duplicate(p); return; }
    if (what === 'up' || what === 'down') {
      const to = p.i + (what === 'up' ? -1 : 1);
      ed.apply((t) => movePanel(t, p.i, to), 'move');
    }
  }

  change(e) {
    const f = e.target.closest('[data-dde]');
    if (!f) return;
    const { ed } = this;
    const p = ed.sel ? ed.panel(ed.sel) : null;
    if (!p) return;
    const what = f.dataset.dde;
    if (what === 'title') { if (f.value.trim()) ed.apply((t) => renamePanel(t, p.i, f.value), 'rename'); else f.value = p.title || p.views[0].name; }
    if (what === 'w') {
      const n = Math.round(Number(f.value));
      if (n >= 1 && n <= ed.dash.dash.columns) ed.apply((t) => resizePanel(t, p.i, { w: n }), 'resize'); else f.value = p.w;
    }
    if (what === 'h') {
      const n = f.value.trim() === '' ? null : Math.round(Number(f.value));
      if (n === null || n >= 1) ed.apply((t) => resizePanel(t, p.i, { h: n }), 'resize'); else f.value = p.h || '';
    }
    if (what === 'visible') ed.apply((t) => hidePanel(t, p.i, !f.checked), 'hide');
    if (what === 'signal') { const v = this.shown(p); ed.apply((t) => setSignal(t, v.name, f.value), 'signal'); }
    if (what === 'text') ed.apply((t) => setPanelText(t, p.i, f.value), 'text');
  }

  shown(p) {
    const open = p.views.length > 1 ? this.ed.dash._shownView(p) : null;
    return (open && p.views.find((x) => x.name === open)) || p.views[0];
  }

  retype(p, type) {
    const { ed } = this;
    const v = this.shown(p);
    let stash = ed.s.stash;
    ed.apply((t) => { const r = setViewType(t, v.name, type, { columns: ed.s.columns(p.dataset), stash }); stash = r.stash; return r.text; }, 'retype', { after: () => { ed.s.stash = stash; } });
  }

  duplicate(p) {
    const { ed } = this;
    const view = JSON.parse(JSON.stringify(p.views[0]));
    const d = ed.dash.dash.datasets[p.dataset];
    delete view.from;
    const spec = { kind: 'view', view, title: p.title || undefined, dataset: { name: p.dataset, data: new URL(d.data, ed.s.url).href }, h: p.h || undefined };
    ed.addSelecting((t) => addPanel(t, spec, { base: ed.s.url, at: p.i + 1, w: p.w }), 'duplicate');
  }
}
