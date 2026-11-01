/* <data-kpi> and <data-sparkline>: the KPI card and its SVG sparkline (docs/SPEC.md §9.1). Framework-free, light DOM;
   colours from the private --dv-* tokens (the core's tokens.css already lists both tags).

   The card's vocabulary is Evidence's BigValue (comparison, down_is_good -> better, neutral_range -> neutral, plus a
   sparkline), drawn the way Vibe Tracks' KPI tiles draw it: the number and its unit, what kind of number it is (the
   basis badge), the delta coloured only outside the neutral band and by which way is better, never by its sign, the
   history as a sparkline whose marks are filled when measured and hollow when estimated, and where the number comes
   from ("computed from 3 runs"). A missing value is "—" with its reason, never 0.

   <data-kpi>        .card = {label, value, column?, unit?, basis?, format?: {digits, compact}, delta?: {text, tone}, spark?: [{y, basis?}],
                     from?, target?, gate?: {text, held}, headline?}; or the attributes label value unit basis delta
                     tone from (a static page's no-JS text stays until it upgrades).
   <data-sparkline>  .points = [{y, basis?}] (null y = a reading not taken: the pen lifts), or values="1,2,,4"
                     bases="measured,estimate,…"; type="line|bar|dist", width, height (px; default 120 x 28). */

import { BASIS, esc, fmtNum, numOpts, isNum, isEmpty, cellValue, provenanceAttr } from '@data-ui/core';

// WHY these draw hollow: Vibe Tracks' convention, "filled marks are measured, hollow ones estimates or stand-ins"
export const HOLLOW = new Set(['estimate', 'stand-in', 'assumed', 'claimed']);

/** A sparkline as SVG text: a line (gaps lift the pen), bars, or a dist strip; marks hollow for estimate kinds. */
export function sparkSvg(points, { type = 'line', width = 120, height = 28 } = {}) {
  const ys = points.map((p) => (p && isNum(p.y) ? p.y : null));
  const nums = ys.filter(isNum);
  if (!nums.length) return '';
  const W = width, H = height, pad = 3;
  // WHY a fold, not Math.min(...nums): spreading 150,000 points into one call overflows the stack (2026-10-26 review)
  const lo = nums.reduce((a, b) => Math.min(a, b), Infinity), hi = nums.reduce((a, b) => Math.max(a, b), -Infinity);
  const sx = (i) => (ys.length > 1 ? pad + ((W - 2 * pad) * i) / (ys.length - 1) : W / 2);
  const sy = (v) => (hi > lo ? H - pad - ((H - 2 * pad) * (v - lo)) / (hi - lo) : H / 2);
  const hollow = (i) => points[i] && HOLLOW.has(points[i].basis);
  let body = '';
  if (type === 'bar') {
    const bw = Math.max(1, (W - 2 * pad) / ys.length - 1);
    const y0 = hi > lo ? sy(Math.max(lo, Math.min(hi, 0))) : H - pad;
    body = ys.map((v, i) => (isNum(v) ? `<rect class="${hollow(i) ? 'dv-spark-hollow' : ''}" x="${(pad + i * (bw + 1)).toFixed(1)}" y="${Math.min(sy(v), y0).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, Math.abs(y0 - sy(v))).toFixed(1)}"></rect>` : '')).join('');
  } else if (type === 'dist') {
    const sorted = [...nums].sort((a, b) => a - b);
    const x = (v) => (hi > lo ? pad + ((W - 2 * pad) * (v - lo)) / (hi - lo) : W / 2);
    const mid = sorted[sorted.length >> 1];
    body = `<line class="dv-spark-whisk" x1="${x(lo).toFixed(1)}" x2="${x(hi).toFixed(1)}" y1="${H / 2}" y2="${H / 2}"></line>`
      + ys.map((v, i) => (isNum(v) ? `<circle class="${hollow(i) ? 'dv-spark-hollow' : ''}" cx="${x(v).toFixed(1)}" cy="${H / 2}" r="2"></circle>` : '')).join('')
      + `<line class="dv-spark-med" x1="${x(mid).toFixed(1)}" x2="${x(mid).toFixed(1)}" y1="${pad}" y2="${H - pad}"></line>`;
  } else {
    let d = '', pen = false;
    ys.forEach((v, i) => {
      if (!isNum(v)) { pen = false; return; }
      d += `${pen ? 'L' : 'M'}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`;
      pen = true;
    });
    const last = ys.length - 1 - [...ys].reverse().findIndex(isNum);
    const dots = ys.length <= 60 ? ys.map((v, i) => (isNum(v) && i !== last ? `<circle class="${hollow(i) ? 'dv-spark-hollow' : ''}" cx="${sx(i).toFixed(1)}" cy="${sy(v).toFixed(1)}" r="1.6"></circle>` : '')).join('') : '';
    body = `<path d="${d}"></path>${dots}<circle class="dv-spark-last${hollow(last) ? ' dv-spark-hollow' : ''}" cx="${sx(last).toFixed(1)}" cy="${sy(ys[last]).toFixed(1)}" r="2.6"></circle>`;
  }
  const label = `${nums.length} readings, ${fmtNum(lo)} to ${fmtNum(hi)}`;
  return `<svg class="dv-spark dv-spark-${type}" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(label)}">${body}</svg>`;
}

export class DataSparkline extends HTMLElement {
  static get observedAttributes() { return ['values', 'bases', 'type', 'width', 'height']; }
  set points(list) { this._points = Array.isArray(list) ? list : []; this._draw(); }
  get points() {
    if (this._points) return this._points;
    const bases = (this.getAttribute('bases') || '').split(',');
    return (this.getAttribute('values') || '').split(',').map((s, i) => ({ y: s.trim() === '' ? null : Number(s), basis: bases[i] ? bases[i].trim() : undefined }));
  }
  connectedCallback() { this._draw(); }
  attributeChangedCallback() { if (this.isConnected) this._draw(); }
  _draw() {
    const num = (k, d) => (Number(this.getAttribute(k)) > 0 ? Number(this.getAttribute(k)) : d);
    this.innerHTML = sparkSvg(this.points, { type: this.getAttribute('type') || 'line', width: num('width', 120), height: num('height', 28) });
  }
}

export class DataKpi extends HTMLElement {
  static get observedAttributes() { return ['label', 'value', 'unit', 'basis', 'delta', 'tone', 'from']; }
  set card(c) { this._card = c || null; this._draw(); }
  get card() {
    if (this._card) return this._card;
    const a = (k) => this.getAttribute(k);
    const v = a('value');
    return { label: a('label') || '', value: { value: v === null || v === '' ? null : Number(v), unit: a('unit') || undefined, basis: a('basis') || undefined },
      delta: a('delta') ? { text: a('delta'), tone: a('tone') || 'neutral' } : null, from: a('from') || '' };
  }
  connectedCallback() { if (this._card || this.hasAttribute('value')) this._draw(); }
  attributeChangedCallback() { if (this.isConnected && !this._card) this._draw(); }

  _draw() {
    const c = this.card;
    const cell = c.value && typeof c.value === 'object' && !Array.isArray(c.value) ? c.value : { value: c.value };
    const col = c.column || {};
    const v = cellValue(cell);
    const unit = c.unit || cell.unit || col.unitText || '';
    const basis = c.basis || cell.basis || null;
    const b = basis ? BASIS[basis] : null;
    // c.format: the card's declared {digits, compact}, over the property's; the stored number stays on hover
    const opts = numOpts(col, c.format);
    const shown = isNum(v) ? fmtNum(v, col.decimals, opts) : v;
    const exact = isNum(v) ? fmtNum(v) : '';
    const number = isEmpty(v)
      ? `<span class="dv-kpi-none" title="${esc(cell.why || 'no value')}">—</span><span class="dv-kpi-why">${esc(cell.why || 'no value')}</span>`
      : `<span class="dv-kpi-num"${isNum(v) ? ` title="${esc(exact)}${unit ? ' ' + esc(unit) : ''}${String(shown) !== String(exact) ? ' (as stored)' : ''}"` : ''}${isNum(v) && String(shown) !== String(exact) ? ` data-exact="${esc(exact)}"` : ''}>${esc(shown)}</span>${unit ? `<span class="dv-kpi-unit">${esc(unit)}</span>` : ''}`;
    const range = isNum(cell.low) && isNum(cell.high) ? `<span class="dv-kpi-range" title="the value's range (low to high)">range ${esc(fmtNum(cell.low, col.decimals, opts))}–${esc(fmtNum(cell.high, col.decimals, opts))}</span>` : '';
    const badge = b ? `<span class="dv-kpi-badge dv-kpi-b-${esc(basis)}" title="${esc(b.means)}"><span aria-hidden="true">${esc(b.mark)}</span> ${esc(b.label)}</span>` : '';
    // WHY the arrow is a pseudo-element keyed by data-dir: the delta's text stays the producer's words ("+1.2 vs previous"),
    // and the arrow is drawn with it, never without its colour (a pill is ▲ or ▼ AND good, bad or grey)
    const dir = c.delta ? c.delta.dir || ({ '+': 'up', '−': 'down', '-': 'down' }[String(c.delta.text || '').trim()[0]] || 'flat') : '';
    const delta = c.delta && c.delta.text ? `<span class="dv-kpi-delta dv-kpi-${esc(c.delta.tone || 'neutral')}" data-dir="${esc(dir)}" title="${esc(c.delta.title || '')}">${esc(c.delta.text)}</span>` : '';
    // the sparkline is drawn at a wide aspect and scaled to the card's full width by CSS (width 100%, height auto)
    const spark = c.spark && c.spark.filter((p) => p && isNum(p.y)).length > 1 ? sparkSvg(c.spark, { width: c.headline ? 320 : 240, height: c.headline ? 44 : 34 }) : '';
    const title = [cell.source ? `source: ${cell.source}` : '', cell.asOf ? `as of ${cell.asOf}` : '', cell.note || ''].filter(Boolean).join('\n');
    const gate = c.gate ? `<span class="dv-kpi-gate dv-kpi-${c.gate.held === true ? 'held' : c.gate.held === false ? 'missed' : 'open'}">${c.gate.held === true ? '✓' : c.gate.held === false ? '✗' : '·'} ${esc(c.gate.text)}</span>` : '';
    const foot = [c.from ? `<span class="dv-kpi-from">${esc(c.from)}</span>` : '', c.target ? `<span>${esc(c.target)}</span>` : '', gate].filter(Boolean).join('<span class="dv-kpi-dot"> · </span>');
    this.classList.toggle('dv-kpi-headline', !!c.headline);
    this.dataset.basis = basis || '';
    this.dataset.tone = (c.delta && c.delta.tone) || '';
    // WHY data-provenance on the value: the right-click popover (CONTRACT §22) reads it, as a table cell's does
    this.innerHTML = `<div class="dv-kpi-card">
      <div class="dv-kpi-head"><span class="dv-kpi-label">${esc(c.label)}</span>${c.tag ? `<span class="dv-kpi-tag">${esc(c.tag)}</span>` : ''}</div>
      <div class="dv-kpi-value"${title ? ` title="${esc(title)}"` : ''}${cell && typeof cell === 'object' ? provenanceAttr({ basis, ...cell }, isEmpty(v) ? '' : String(shown), unit) : ''}>${number}${badge}${delta}</div>
      ${range ? `<div class="dv-kpi-sub">${range}</div>` : ''}
      ${c.headline ? '<div class="dv-kpi-history"></div>' : ''}
      ${spark && !c.headline ? `<div class="dv-kpi-spark">${spark}</div>` : ''}
      ${c.headline && spark ? `<div class="dv-kpi-spark dv-kpi-spark-fallback">${spark}</div>` : ''}
      <div class="dv-kpi-foot">${foot}</div>
    </div>`;
  }
}

if (!customElements.get('data-sparkline')) customElements.define('data-sparkline', DataSparkline);
if (!customElements.get('data-kpi')) customElements.define('data-kpi', DataKpi);
