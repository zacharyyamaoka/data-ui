/* type: lineage — a tree of life over rows that name their parents (docs/CONTRACT.md §21, docs/VIEWS.md).

   Zach, 2026-10-27: "this tree of life is just another view over data … It's data that basically has like parent child
   relationship and then we are just displaying it … using data ui then for free we automatically get all of the
   filters and navigation." So the rows are the host's (after filters, search and sort), a mark opens the shared peek,
   and the only state is the view entry (focus, extinct, layout) written back through host.setView.

   STOCK PARTS: d3-hierarchy + d3-shape (layout.js), d3-zoom 3.0.0 with d3-selection 3.0.0 (wheel zoom about the
   pointer, drag to pan, pinch on touch), the core's makeResizable (the path panel's edge, §11). OURS: the SVG marks,
   the bar, the path panel, the theme mapping (tokens only).
   Writes back only through the host: open(id) on a mark, open(id, {records}) on a "+N", setView on the bar, setStatus. */

import { select } from 'd3-selection';
import { zoom, zoomIdentity } from 'd3-zoom';
import { cellValue, esc, isEmpty, makeResizable, mediaUrl } from '@data-ui/core';
import { lineageSpec, buildLineage, useCore } from './layout.js';
import css from './lineage.css';

export { css };
useCore({ cellValue, isEmpty });

const LABEL_MAX = 24; // characters on a label mark; the full text is its tooltip (feedback_truthful_property_rendering)
const NARROW = 700; // px of the view's own width: the panel stacks under the tree
const PAD = 24; // px: the fit's margin
const MIN_READ = 0.6; // the first view's zoom when the whole tree is too small to read: a 22 px mark at 13 px still reads as its picture
const MIN_FIT = 0.5; // the first view shows the whole tree down to this zoom (marks 11 px across), so a tree is never opened clipped
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch { /* private window */ } },
};

export function options() {
  return [
    { type: 'property', key: 'lineage.parents', displayName: 'Parents from' },
    { type: 'property', key: 'lineage.x', displayName: 'Columns by', none: 'depth' },
    { type: 'property', key: 'lineage.image', displayName: 'Image', none: 'none' },
    { type: 'property', key: 'lineage.label', displayName: 'Label', none: 'title' },
    { type: 'dropdown', key: 'lineage.layout', displayName: 'Layout', default: 'rectangular', options: { rectangular: 'Rectangular', radial: 'Radial' } },
    { type: 'dropdown', key: 'lineage.extinct', displayName: 'Extinct lines', default: 'collapse', options: { collapse: 'Fold into +N', show: 'Show as stubs' } },
  ];
}

const short = (text, max = LABEL_MAX) => (text.length > max ? `${text.slice(0, Math.max(1, max - 1))}…` : text);
const f = (n) => Math.round(n * 100) / 100;

export default class LineageView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this.peekId = null;
    this.key = null;
    const id = (host.element && host.element.id) || 'views';
    this.foldKey = `data-ui/lineage-fold/${id}`;
    this.panelKey = `lineage:${id}`;
    el.innerHTML = `<div class="dv-lineage">
      <div class="dv-lineage-stage">
        <div class="dv-lineage-bar" role="toolbar" aria-label="Lineage">
          <span class="dv-lineage-seg" role="group" aria-label="Layout">
            <button type="button" class="dv-btn" data-act="layout" data-layout="rectangular">Rectangular</button><button type="button" class="dv-btn" data-act="layout" data-layout="radial">Radial</button>
          </span>
          <button type="button" class="dv-btn" data-act="extinct" title="Show the lines nobody kept, or fold each fan into +N">Show extinct</button>
          <button type="button" class="dv-btn" data-act="focus" disabled title="Make the selected mark the focus: its ancestry becomes the trunk">Focus selection</button>
          <button type="button" class="dv-btn" data-act="fit" title="Fit the tree">Fit</button>
        </div>
        <svg class="dv-lineage-svg" role="img" aria-label="Lineage"><g class="dv-lineage-world"></g></svg>
      </div>
      <aside class="dv-lineage-panel" aria-label="Lineage path">
        <div class="dv-lineage-panelhead"><span class="dv-lineage-paneltitle">Path</span><button type="button" class="dv-lineage-fold" data-act="fold" aria-expanded="true" title="Fold the path panel">⟩</button></div>
        <div class="dv-lineage-panelbody"></div>
      </aside>
    </div>`;
    this.root = el.querySelector('.dv-lineage');
    this.stage = el.querySelector('.dv-lineage-stage');
    this.svg = el.querySelector('svg');
    this.world = el.querySelector('.dv-lineage-world');
    this.panel = el.querySelector('.dv-lineage-panel');
    this.zoom = zoom().scaleExtent([0.04, 8]).on('zoom', (e) => { this.t = e.transform; this.world.setAttribute('transform', e.transform.toString()); });
    this.svgSel = select(this.svg).call(this.zoom).on('dblclick.zoom', null);

    this.onClick = (e) => {
      const btn = e.target.closest('[data-act]');
      if (btn && this.root.contains(btn) && btn.tagName === 'BUTTON') { this.act(btn); return; }
      const step = e.target.closest('.dv-lineage-step');
      if (step) { this.host.open(step.dataset.id); return; }
      const g = e.target.closest('g.dv-lineage-node');
      if (g) this.openNode(g.dataset.id);
    };
    this.onKey = (e) => {
      const g = e.target.closest && e.target.closest('g.dv-lineage-node');
      if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); this.openNode(g.dataset.id); }
    };
    el.addEventListener('click', this.onClick);
    el.addEventListener('keydown', this.onKey);
    this.ro = new ResizeObserver(() => this.layoutPanel());
    this.ro.observe(el);
    this.folded = store.get(this.foldKey) === '1';
  }

  destroy() {
    this.host.setStatus('');
    this.ro.disconnect();
    if (this.resizer) this.resizer.destroy();
    this.svgSel.on('.zoom', null);
  }

  peeked(peek) {
    this.peekId = peek && peek.id != null ? String(peek.id) : null;
    for (const g of this.world.querySelectorAll('g.dv-lineage-node.dv-selected')) g.classList.remove('dv-selected');
    if (this.peekId) for (const g of this.world.querySelectorAll('g.dv-lineage-node')) if (g.dataset.id === this.peekId) g.classList.add('dv-selected');
    const btn = this.root.querySelector('[data-act=focus]');
    btn.disabled = !this.peekId || !this.tree || !this.tree.byId.has(this.peekId) || (this.spec && this.spec.focus === this.peekId);
  }

  setLineage(patch) {
    this.host.setView({ lineage: { ...(this.input.view.lineage || {}), ...patch } });
  }

  act(btn) {
    const a = btn.dataset.act;
    if (a === 'layout') this.setLineage({ layout: btn.dataset.layout });
    else if (a === 'extinct') this.setLineage({ extinct: this.spec.extinct === 'show' ? 'collapse' : 'show' });
    else if (a === 'focus' && this.peekId) this.setLineage({ focus: this.peekId });
    else if (a === 'fit') this.fit(true);
    else if (a === 'fold') { this.folded = !this.folded; store.set(this.foldKey, this.folded ? '1' : null); this.layoutPanel(); }
  }

  openNode(id) {
    const n = this.tree && this.tree.byId.get(id);
    if (!n) return;
    if (n.kind === 'group') {
      const rows = n.rows.map((r) => this.tree.analysis.byId.get(r));
      const under = n.parentId == null ? 'the top' : this.titleOf(this.tree.analysis.byId.get(n.parentId));
      this.host.open(rows[0].id, { records: rows, title: `+${n.count} folded under ${under}` });
    } else if (n.kind === 'row') this.host.open(n.row.id);
  }

  titleOf(row) {
    const p = (this.spec && this.spec.label) || this.input.dataset.titleProperty;
    const v = p ? cellValue(row[p]) : null;
    return isEmpty(v) ? String(row.id) : String(v);
  }

  update(input) {
    this.input = input;
    this.spec = lineageSpec(input.view);
    const spec = this.spec;
    this.root.dataset.layout = spec.layout;
    this.root.dataset.extinct = spec.extinct;
    for (const b of this.root.querySelectorAll('[data-act=layout]')) b.setAttribute('aria-pressed', String(b.dataset.layout === spec.layout));
    const ext = this.root.querySelector('[data-act=extinct]');
    ext.setAttribute('aria-pressed', String(spec.extinct === 'show'));
    ext.disabled = !spec.kept;
    if (!spec.parents) {
      this.tree = null;
      this.world.innerHTML = '';
      this.host.setStatus('<span class="dv-err">no parents: set <code>lineage: {parents}</code>, a property listing each row\'s parent ids</span>');
      this.renderPanel();
      return;
    }
    this.tree = buildLineage(input.rows, spec, { width: this.stage.clientWidth || 0 });
    const c = this.tree.counts;
    ext.textContent = spec.extinct === 'show' ? 'Show extinct' : `Show extinct (${c.extinct})`;
    const parts = [`${c.shown} marks · ${c.edges} edges · ${c.splices} splice${c.splices === 1 ? '' : 's'}`];
    if (c.groups) parts.push(`${c.hidden} extinct folded into ${c.groups} × +N`);
    else if (spec.kept) parts.push(`${c.extinct} extinct`);
    if (c.missing) parts.push(`${c.missing} parent${c.missing === 1 ? '' : 's'} not shown`);
    if (c.cut) parts.push(`${c.cut} parent cycle${c.cut === 1 ? '' : 's'} cut`);
    if (spec.focus != null && !this.tree.analysis.idSet.has(spec.focus)) parts.push(`focus ${esc(spec.focus)} is not shown`);
    this.host.setStatus(parts.join(' · '));
    this.draw();
    this.renderPanel();
    this.layoutPanel();
    // WHY a key: other rows, layout or folding re-fit the view; a theme, peek or panel change keeps the reader's pan
    const key = JSON.stringify([input.view.name, spec.layout, spec.extinct, this.tree.nodes.map((n) => n.id)]);
    if (key !== this.key) { this.key = key; this.fit(false); }
    this.peeked(this.peekId ? { id: this.peekId } : null);
  }

  draw() {
    const t = this.tree;
    const spec = this.spec;
    const ds = this.input.dataset;
    const out = [];
    // ticks: a column per x value (rectangular), a ring per x value (radial)
    out.push('<g class="dv-lineage-ticks">');
    for (const k of t.ticks) {
      const label = esc(short(String(k.label)));
      const full = esc(String(k.label));
      if (t.kind === 'rectangular') {
        out.push(`<line class="dv-lineage-guide" x1="${f(k.x)}" x2="${f(k.x)}" y1="${f(t.bounds.y0 + 24)}" y2="${f(t.bounds.y1)}"/>`);
        out.push(`<text class="dv-lineage-tick" x="${f(k.x)}" y="${f(k.y)}" text-anchor="middle"><title>${full}</title>${label}</text>`);
      } else {
        out.push(`<circle class="dv-lineage-guide" r="${f(k.r)}"/>`);
        out.push(`<text class="dv-lineage-tick" x="${f(k.x)}" y="-4"><title>${full}</title>${label}</text>`);
      }
    }
    out.push('</g><g class="dv-lineage-edges">');
    for (const s of t.stubs) out.push(`<path class="dv-lineage-stub" data-from="${esc(s.from)}" data-to="${esc(s.to)}" d="${s.d}"/>`);
    for (const e of t.edges) out.push(`<path class="dv-lineage-edge dv-${e.type}" data-from="${esc(e.from)}" data-to="${esc(e.to)}" d="${e.d}"/>`);
    for (const s of t.splices) out.push(`<path class="dv-lineage-splice${s.golden ? ' dv-golden' : ''}${s.extinct ? ' dv-extinct' : ''}" data-from="${esc(s.from)}" data-to="${esc(s.to)}" d="${s.d}"><title>splice: a second parent</title></path>`);
    out.push('</g><g class="dv-lineage-nodes">');
    for (const n of t.nodes) {
      if (n.kind === 'root') {
        if (t.kind === 'radial') out.push(`<g class="dv-lineage-root" transform="translate(${f(n.x)},${f(n.y)})"><circle class="dv-lineage-dot" r="3"/></g>`);
        continue;
      }
      const cls = ['dv-lineage-node', n.kind === 'group' ? 'dv-group' : '', n.kind === 'group' || !n.alive ? 'dv-extinct' : '', n.golden ? 'dv-golden' : '', n.focus ? 'dv-focus' : ''].filter(Boolean).join(' ');
      const left = t.kind === 'radial' && n.x < -1;
      const tx = left ? -1 : 1;
      if (n.kind === 'group') {
        const what = `${n.count} row${n.count === 1 ? '' : 's'} folded: no kept descendant. Click to list them.`;
        out.push(`<g class="${cls}" data-id="${esc(n.id)}" data-count="${n.count}" data-x="${n.col}" transform="translate(${f(n.x)},${f(n.y)})" tabindex="0" role="button" aria-label="${esc(what)}"><title>${esc(what)}</title><circle class="dv-lineage-dot" r="${f(Math.min(5, n.size / 2))}"/><text class="dv-lineage-label" x="${9 * tx}" dy=".35em" text-anchor="${left ? 'end' : 'start'}">+${n.count}</text></g>`);
        continue;
      }
      const title = this.titleOf(n.row);
      const src = spec.image ? cellValue(n.row[spec.image]) : null;
      const head = `<g class="${cls}" data-id="${esc(n.id)}" data-x="${esc(String(n.col))}" transform="translate(${f(n.x)},${f(n.y)})" tabindex="0" role="button" aria-label="${esc(title)}"><title>${esc(title)}</title>`;
      if (!isEmpty(src) && typeof src === 'string') {
        const s = n.size;
        out.push(`${head}<rect class="dv-lineage-well" x="${f(-s / 2)}" y="${f(-s / 2)}" width="${f(s)}" height="${f(s)}" rx="3"/><image href="${esc(mediaUrl(src, ds))}" x="${f(-s / 2 + 1)}" y="${f(-s / 2 + 1)}" width="${f(Math.max(0, s - 2))}" height="${f(Math.max(0, s - 2))}" preserveAspectRatio="xMidYMid meet"/><rect class="dv-lineage-dot dv-lineage-frame" x="${f(-s / 2)}" y="${f(-s / 2)}" width="${f(s)}" height="${f(s)}" rx="3"/></g>`);
      } else {
        // rectangular: the label sits above its dot, centred and cut to the column's pitch, so it never runs over the
        // next column or along the edge line; radial: beside the dot, away from the centre
        const lab = t.kind === 'rectangular'
          ? `<text class="dv-lineage-label" y="-9" text-anchor="middle">${esc(short(title, Math.max(4, Math.floor((t.colPx - 10) / 6.4))))}</text>`
          : `<text class="dv-lineage-label" x="${9 * tx}" dy=".35em" text-anchor="${left ? 'end' : 'start'}">${esc(short(title))}</text>`;
        out.push(`${head}<circle class="dv-lineage-dot" r="${f(Math.min(4.5, n.size / 2))}"/>${lab}</g>`);
      }
    }
    out.push('</g>');
    this.world.innerHTML = out.join('');
  }

  /** all: the whole tree (the Fit button). Otherwise the first view of a layout: the whole tree when it reads at
      MIN_FIT or larger (radial: always whole), else MIN_READ centred on the focus (or the tree's middle), the rest a pan
      away. */
  fit(all, animate = false) {
    if (!this.tree) return;
    const b = this.tree.bounds;
    const w = this.svg.clientWidth || this.stage.clientWidth;
    const h = this.svg.clientHeight || this.stage.clientHeight;
    if (!w || !h) return;
    const top = 44; // px: the bar sits over the tree's top-left
    const fitK = Math.min(2, (w - 2 * PAD) / (b.x1 - b.x0), (h - top - PAD) / (b.y1 - b.y0));
    let t;
    // WHY radial always whole: a ring layout is an overview (its shape is the point); a slice of rings reads as nothing
    // WHY MIN_FIT, not MIN_READ, for the rectangular first view (Zach's ObjectDB logo work, 2026-10-28): 18 rounds of
    // picture marks need 0.58x to fit, and opening at 0.6x on the focus put rounds R1-R7 off the left edge until Fit was
    // pressed; a tree that fits at 0.5x or more opens whole, one that needs less opens at MIN_READ on the focus
    if (all || fitK >= MIN_FIT || this.spec.layout === 'radial') {
      t = zoomIdentity.translate((w - fitK * (b.x1 - b.x0)) / 2 - fitK * b.x0, top + (h - top - PAD - fitK * (b.y1 - b.y0)) / 2 - fitK * b.y0).scale(fitK);
    } else {
      const k = MIN_READ;
      const f = (this.spec.focus != null && this.tree.byId.get(this.spec.focus)) || { x: (b.x0 + b.x1) / 2, y: (b.y0 + b.y1) / 2 };
      // x: the whole width when it fits at k, else the focus in the middle; y: the focus in the middle
      const tx = k * (b.x1 - b.x0) <= w - 2 * PAD ? (w - k * (b.x1 - b.x0)) / 2 - k * b.x0 : w / 2 - k * f.x;
      t = zoomIdentity.translate(tx, top + (h - top) / 2 - k * f.y).scale(k);
    }
    (animate ? this.svgSel.transition().duration(250) : this.svgSel).call(this.zoom.transform, t);
  }

  renderPanel() {
    const body = this.panel.querySelector('.dv-lineage-panelbody');
    const t = this.tree;
    const spec = this.spec;
    if (!t || spec.focus == null || !t.analysis.idSet.has(spec.focus)) {
      body.innerHTML = `<p class="dv-lineage-hint">${spec && spec.focus != null ? `The focus, <code>${esc(spec.focus)}</code>, is not among the rows shown.` : 'No focus yet.'} Select a mark and press <b>Focus selection</b>, or set <code>lineage.focus</code>.</p>`;
      return;
    }
    const an = t.analysis;
    const at = new Map(an.ids.map((id, i) => [id, i]));
    const steps = [...an.golden].sort((a, b) => (t.byId.get(a).idx - t.byId.get(b).idx) || at.get(a) - at.get(b));
    const ds = this.input.dataset;
    const items = steps.map((id) => {
      const n = t.byId.get(id);
      const src = spec.image ? cellValue(n.row[spec.image]) : null;
      const img = !isEmpty(src) && typeof src === 'string' ? `<img src="${esc(mediaUrl(src, ds))}" alt="" loading="lazy">` : '<span class="dv-lineage-stepdot"></span>';
      const col = t.ticks.find((k) => k.idx === n.idx);
      const ps = an.parents.get(id).length;
      return `<li class="dv-lineage-step${id === spec.focus ? ' dv-focus' : ''}" data-id="${esc(id)}"><button type="button">${img}<span class="dv-lineage-steptext"><span class="dv-lineage-stepname" title="${esc(this.titleOf(n.row))}">${esc(this.titleOf(n.row))}</span><span class="dv-lineage-stepsub">${esc(col ? String(col.label) : '')}${ps > 1 ? ` · splice of ${ps}` : ''}</span></span></button></li>`;
    });
    body.innerHTML = `<p class="dv-lineage-pathtitle">To <b>${esc(this.titleOf(an.byId.get(spec.focus)))}</b> · ${steps.length} step${steps.length === 1 ? '' : 's'}, oldest first</p><ol class="dv-lineage-steps">${items.join('')}</ol>`;
  }

  layoutPanel() {
    const narrow = this.el.clientWidth > 0 && this.el.clientWidth < NARROW;
    this.root.classList.toggle('dv-narrow', narrow);
    this.panel.classList.toggle('dv-folded', this.folded);
    const fold = this.panel.querySelector('[data-act=fold]');
    fold.setAttribute('aria-expanded', String(!this.folded));
    fold.textContent = this.folded ? (narrow ? '⌃' : '⟨') : (narrow ? '⌄' : '⟩');
    fold.title = this.folded ? 'Show the path panel' : 'Fold the path panel';
    // WHY no handle while folded or stacked: a folded strip has no width to drag, and a stacked panel fills the row
    const want = !this.folded && !narrow;
    if (want && !this.resizer) this.resizer = makeResizable(this.panel, { edge: 'left', min: 180, max: 520, keep: 320, key: this.panelKey, label: 'the path panel' });
    else if (!want && this.resizer) { this.resizer.destroy(); this.resizer = null; }
  }
}
