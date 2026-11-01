/* type: kpi — one stat card, or one per group (docs/SPEC.md §9.1, docs/CONTRACT.md §5).

     kpi:
       label:   the card's title (one card); with groupBy each card is titled by its group
       value:   {property, summary?, per?}. No summary: the producer's number, the newest row's cell as written
                (a headline number is the producer's, never recomputed). A summary (Bases' names, or Ratio with
                per = Σproperty / Σper): a view summary over the card's rows, labelled "<summary> of N rows".
       compare: {against: previous | target | <property>, better: higher | lower | <property>, neutral}: the delta,
                coloured only outside the relative `neutral` band, by which way is better, never by its sign
       spark:   {x, y, window}: the history, in x order; window (ISO 8601, P30D) keeps the newest stretch, and in
                summary mode `previous` is the window before
       target, gate {min, max}: shown under the number; a gate says held or missed. `target` may name a property: each
                card reads it from its newest row (docs/CONTRACT.md §35, kpi_trend: a diagnostic row's own target)
       format:  {digits, compact}: how the card writes its number (3 significant figures, 26.5K); the stored value
                stays on hover. A summary and a delta are computed, so they default to 4 and 3 significant figures

   The first card is the headline (bigger) when the order is the author's (one card, or a groupOrder): its history
   is drawn by the chart view (Vega-Lite, loaded once), so a page has one chart engine; the other cards draw an SVG
   sparkline (<data-sparkline>'s, no engine). In summary mode the history has one point per x: the card's summary
   over the rows at that x. Marks are
   filled when the cell's basis is measured and hollow for estimates and stand-ins. A click on a card opens the
   rows behind it in the host's peek (host.open with records).

   Per-card direction: `compare.better` may name a property instead of a direction; each card then reads it from
   its newest row (higher | lower), so one view holds KPIs that point both ways (Vibe Tracks: picks per minute up,
   computation time down). WHY a named property, not a reserved `better` column (the lane's first cut): the .base
   file is the API, so the rule is visible in it and checked against the data like `against:`, and no dataset
   changes meaning because it happens to have a column called better (docs/CONTRACT.md amendment 2026-10-26
   (core pass)).

   The look (docs/peps/0005-dashboard-cards.md §2): the label muted on top, the number big in tabular figures sized by
   the card's own width (a container query), the unit muted beside it, the delta a small pill whose ▲ / ▼ always comes
   with its colour, the sparkline the card's full width, the footer muted. Inside a dashboard the card has no box of
   its own (the dashboard draws the surface). `style.numbers` ({digits, compact}) is the default number format, under
   the property's own and `format:`.

   This bundle also draws the other stat cards of the catalog, each in its own file: gauge.js, bullet.js, barlist.js
   and status.js (SVG and CSS, no chart engine); the default export picks the class by the view's type.

   STOCK PARTS: none (ours, ~60-line SVG sparkline); the headline's history is the chart view (vega-lite). The other
   stat cards copy Tremor's ProgressBar / ProgressCircle, BarList and Tracker as plain SVG and CSS. */

import { cellValue, esc, fmtNum, fmtClock, numOpts, groupLabel, isNum, isEmpty, loadView } from '@data-ui/core';
import css from './kpi.css';
import { summarizeRows } from './stat.js';
import { targetValue } from './stat-model.js';
import GaugeView from './gauge.js';
import BulletView from './bullet.js';
import BarlistView from './barlist.js';
import StatusView from './status.js';
import { deltaValue } from './delta.js';

export { css, summarizeRows };
export { DataKpi, DataSparkline, sparkSvg } from './elements.js';

// WHY the stylesheet here too: a plain page imports this bundle for <data-kpi> and <data-sparkline> alone
// (`<script type="module" src="…/views/kpi.js">`, no <data-views>), so the registry never adds it; the registry finds
// this <style> by the same name and does not add a second (docs/CONTRACT.md amendment 2026-10-26 (core pass))
if (typeof document !== 'undefined' && !document.querySelector('style[data-ui-view="kpi"]')) {
  const style = document.createElement('style');
  style.dataset.uiView = 'kpi';
  style.textContent = css;
  document.head.append(style);
}

const DURATION = /^P(?:(\d+(?:\.\d+)?)Y)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)W)?(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$/;
/** An ISO 8601 duration in ms (a month is 30 days, a year 365). */
export function durationMs(text) {
  const m = DURATION.exec(String(text || ''));
  if (!m) return null;
  const [y, mo, w, d, h, mi, s] = m.slice(1).map((x) => Number(x || 0));
  return ((((y * 365 + mo * 30 + w * 7 + d) * 24 + h) * 60 + mi) * 60 + s) * 1000;
}

export class KpiView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this.history = null;
    el.innerHTML = '<div class="dv-kpi-wrap"><div class="dv-kpi-grid" role="list"></div><p class="dv-kpi-note"></p></div>';
    this.grid = el.querySelector('.dv-kpi-grid');
    el.addEventListener('click', (e) => {
      const card = e.target.closest('data-kpi');
      if (!card || e.target.closest('.dv-kpi-history')) return;
      this._open(Number(card.dataset.i));
    });
    el.addEventListener('keydown', (e) => {
      const card = e.target.closest && e.target.closest('data-kpi');
      if (card && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); this._open(Number(card.dataset.i)); }
    });
  }

  destroy() {
    this._gen = (this._gen || 0) + 1; // a history still waiting for its frame or its bundle never draws
    this._cancelLater();
    if (this.history) { try { this.history.view.destroy(); } catch { /* the chart's own cleanup must not block ours */ } }
    this.host.setStatus('');
    this.el.innerHTML = '';
  }

  update(input) {
    this.input = input;
    const k = input.view.kpi || {};
    this.cards = this._cards(input, k);
    const els = this.cards.map((c, i) => {
      const card = document.createElement('data-kpi');
      card.setAttribute('role', 'listitem');
      card.tabIndex = 0;
      card.dataset.i = String(i);
      card.dataset.key = String(c.key ?? '');
      card.card = c.card;
      return card;
    });
    this.grid.replaceChildren(...els);
    this.el.querySelector('.dv-kpi-note').textContent = this.cards.length ? '' : 'No rows match this view.';
    const n = this.cards.length;
    this.host.setStatus(n > 1 ? `${n} cards` : '');
    // WHY not awaited (review 2026-10-26 item 8): the history is drawn by the chart view, a 304 kB gzip bundle plus a
    // Vega draw, and the host's first render waited for it before the headline counted as drawn. The cards are the
    // answer; the history follows once they are on screen, the sparkline standing in until it arrives (and staying if
    // it fails). A newer update or destroy() bumps the generation, so a late history never draws stale rows.
    const gen = this._gen = (this._gen || 0) + 1;
    const head = els[0], c = this.cards[0];
    if (this._wantsHistory(head, c)) {
      head.setAttribute('aria-busy', 'true');
      this._afterPaint(() => this._history(input, k, head, c, gen));
    }
  }

  _wantsHistory(el, c) { return !!(el && c && c.card.headline && c.series && c.series.filter((p) => isNum(p.y)).length >= 2); }

  /** Run fn after the next frame has painted (a task queued from a frame callback), once; a newer call replaces it. */
  _afterPaint(fn) {
    this._cancelLater();
    this._raf = requestAnimationFrame(() => { this._raf = 0; this._timer = setTimeout(() => { this._timer = 0; fn(); }, 0); });
  }

  _cancelLater() {
    if (this._raf) cancelAnimationFrame(this._raf);
    if (this._timer) clearTimeout(this._timer);
    this._raf = this._timer = 0;
  }

  /** The cards: [{key, label, rows, latest, card}] in group order. */
  _cards(input, k) {
    const { columns } = input;
    const groups = input.groups && input.groups.length
      ? input.groups.map((g) => ({ key: g.key, label: groupLabel(columns, g.property, g.key), rows: g.rows }))
      : input.rows.length ? [{ key: null, label: k.label || input.view.name, rows: input.rows }] : [];
    // WHY the dashboard's numbers as the floor: `style.numbers` is the author's declared default for every card; a property's
    // own digits/compact and this card's `format:` still win (docs/peps/0005-dashboard-cards.md §5)
    const numbers = input.view.style && input.view.style.numbers;
    const vp = k.value && k.value.property;
    // WHY not read (the Notion survey's §16, decision 1): a formula runs in the browser for a display column; a headline KPI stays the
    // producer's, so it is a number a build wrote and a person can trace (CONTRACT §36)
    const formula = typeof vp === 'string' && vp.startsWith('formula.');
    const summary = !formula && k.value && k.value.summary;
    const sx = k.spark && k.spark.x, sy = (k.spark && k.spark.y) || vp;
    const isDate = sx && columns[sx] && columns[sx].type === 'date';
    const xOf = (r) => { const v = cellValue(r[sx]); return isDate ? Date.parse(v) : v; };
    const win = k.spark && k.spark.window && isDate ? durationMs(k.spark.window) : null;
    // WHY a headline only when the order is the author's: one card, or groups in a stated groupOrder ("the headline,
    // then its drivers"); groups in plain value order (models A to Z) are peers, so none is promoted
    const headline = !input.groups || (Array.isArray(input.view.groupOrder) && input.view.groupOrder.length > 0);
    return groups.map((g, i) => {
      const ordered = sx ? g.rows.filter((r) => !isEmpty(cellValue(r[sx]))).sort((a, b) => (xOf(a) > xOf(b) ? 1 : xOf(a) < xOf(b) ? -1 : 0)) : g.rows;
      let current = ordered, previous = [];
      if (win && ordered.length) {
        const end = xOf(ordered[ordered.length - 1]);
        current = ordered.filter((r) => xOf(r) > end - win);
        previous = ordered.filter((r) => xOf(r) > end - 2 * win && xOf(r) <= end - win);
      }
      const latest = ordered[ordered.length - 1] || null;
      let cell, prev = null, from, basis;
      if (!summary) {
        // the producer's number: the newest row's cell, as written
        cell = latest && vp && !formula ? latest[vp] : null;
        const before = [...ordered.slice(0, -1)].reverse().find((r) => isNum(cellValue(r[vp])));
        prev = before ? cellValue(before[vp]) : null;
        const n = cell && typeof cell === 'object' && isNum(cell.n) ? cell.n : null;
        // a live dataset's time (display: clock, CONTRACT §26) reads "as of 14:03:21.358": the value is the newest at t
        const clock = sx && columns[sx] && columns[sx].display === 'clock';
        const when = latest && sx ? (isDate ? fmtDate(cellValue(latest[sx])) : clock ? `as of ${fmtClock(cellValue(latest[sx]))}` : `${columns[sx] ? columns[sx].label : sx} ${cellValue(latest[sx])}`) : '';
        from = formula ? "not a headline: a KPI is the producer's, and a formula is for a display column" : [n !== null ? `computed from ${n.toLocaleString('en-US')} run${n === 1 ? '' : 's'}` : "the producer's number", when].filter(Boolean).join(' · ');
      } else {
        const v = summarizeRows(current, vp, summary, k.value.per);
        prev = previous.length ? summarizeRows(previous, vp, summary, k.value.per) : null;
        const unit = columns[vp] && columns[vp].unitText;
        cell = { value: Array.isArray(v) ? null : v, unit: summary === 'Ratio' ? undefined : unit, n: current.length };
        basis = 'derived';
        from = `${summary === 'Ratio' ? `Σ ${label(columns, vp)} / Σ ${label(columns, k.value.per)}` : `${summary} of ${label(columns, vp)}`} over ${current.length.toLocaleString('en-US')} row${current.length === 1 ? '' : 's'}${win ? ` · last ${k.spark.window}` : ''}`;
      }
      const value = cellValue(cell);
      // a number as written, or the newest row's value of a property (CONTRACT §35)
      const target = targetValue(k.target, latest, (r, c) => cellValue(r[c]));
      const unit = (cell && typeof cell === 'object' && cell.unit) || (vp && columns[vp] && columns[vp].unitText) || '';
      const dir = k.compare && k.compare.better;
      const better = dir === 'higher' || dir === 'lower' ? dir
        : dir && columns[dir] && latest && ['higher', 'lower'].includes(cellValue(latest[dir])) ? cellValue(latest[dir]) : null;
      let delta = null;
      if (k.compare && isNum(value)) {
        const against = k.compare.against;
        const ref = against === 'previous' ? prev : against === 'target' ? target : latest ? cellValue(latest[against]) : null;
        if (isNum(ref)) {
          const decimals = columns[vp] ? columns[vp].decimals : undefined;
          // WHY two: the tone is judged on the exact difference; only the printed text drops the float noise
          const raw = value - ref;
          const d = deltaValue(raw, decimals);
          const rel = ref !== 0 ? Math.abs(raw) / Math.abs(ref) : raw === 0 ? 0 : Infinity;
          const tone = rel <= (k.compare.neutral || 0) || raw === 0 ? 'neutral' : (raw > 0) === (better !== 'lower') ? 'good' : 'bad';
          const name = against === 'previous' ? 'previous' : against === 'target' ? 'target' : label(columns, against);
          // WHY digits on a delta by default: it is computed here (a difference of two floats), not a stored value, so
          // 0.30000000000000004 is float noise, not truth; a property's decimals, the card's own format: or the
          // dashboard's style.numbers wins
          const dOpts = decimals != null ? {} : { digits: 3, ...numOpts(numbers, vp && columns[vp], k.format) };
          delta = { dir: d > 0 ? 'up' : d < 0 ? 'down' : 'flat', text: `${d > 0 ? '+' : d < 0 ? '−' : '±'}${fmtNum(Math.abs(d), decimals, dOpts)}${unit && unit !== '%' ? ` ${unit}` : unit === '%' ? ' pts' : ''} vs ${name}`, tone,
            title: `${fmtNum(value, decimals)} against ${fmtNum(ref, decimals)} (${name}), difference ${fmtNum(d)}; ${better || 'no'} is better${k.compare.neutral ? `, neutral within ${fmtNum(k.compare.neutral * 100)} %` : ''}` };
        }
      }
      // the history: one point per row (the producer's readings); in summary mode one point per x, the card's own
      // summary over the rows at that x (three runs in one round are one reading of a pooled rate, not three)
      const series = sx && sy ? (summary ? buckets(win ? current : ordered, xOf).map(([x, rs]) => ({ x: cellValue(rs[0][sx]), y: summarizeRows(rs, vp, summary, k.value.per), rows: rs }))
        : (win ? current : ordered).map((r) => ({ x: cellValue(r[sx]), y: cellValue(r[sy]), basis: r[sy] && typeof r[sy] === 'object' ? r[sy].basis : undefined, row: r }))) : null;
      const spark = series && series.map(({ y, basis }) => ({ y: isNum(y) ? y : null, basis }));
      const gate = k.gate && (isNum(k.gate.min) || isNum(k.gate.max)) ? {
        text: `gate ${[isNum(k.gate.min) ? `≥ ${fmtNum(k.gate.min)}` : '', isNum(k.gate.max) ? `≤ ${fmtNum(k.gate.max)}` : ''].filter(Boolean).join(' and ')}`,
        held: isNum(value) ? (!isNum(k.gate.min) || value >= k.gate.min) && (!isNum(k.gate.max) || value <= k.gate.max) : null,
      } : null;
      return {
        key: g.key, label: g.label, rows: g.rows, ordered, latest, sx, sy, series, summary, target,
        // a summary is computed here, so it gets 4 significant figures unless the card or property says otherwise
        card: { label: g.label, value: cell, unit, basis, column: vp ? columns[vp] : null, delta, spark, from, gate,
          format: summary ? { digits: 4, ...numOpts(numbers, vp && columns[vp], k.format) } : numOpts(numbers, vp && columns[vp], k.format),
          target: isNum(target) ? `target ${fmtNum(target)}${unit && unit !== '%' ? ` ${unit}` : unit}` : '', headline: i === 0 && headline,
          tag: i === 0 && headline && groups.length > 1 ? 'headline' : '' },
      };
    });
  }

  /** The headline's history, drawn by the chart view (bare: no bar, no status), so one chart engine serves both. */
  async _history(input, k, el, c, gen = this._gen) {
    if (!this._wantsHistory(el, c)) return;
    const slot = el.querySelector('.dv-kpi-history');
    if (!slot) return;
    const live = () => gen === this._gen && el.isConnected;
    try {
      if (!this.history) {
        // one request however many updates arrive while the bundle loads
        this._chartMod = this._chartMod || loadView('chart');
        const { View } = await this._chartMod;
        if (!live()) return;
      }
      if (!this.history) {
        const { View } = await this._chartMod;
        const box = document.createElement('div');
        box.className = 'dv-view dv-view-chart';
        box.setAttribute('data-bare', '');
        const host = this.host;
        const open = (id, opts) => {
          const synthetic = this._synthetic && this._synthetic.get(String(id));
          if (!synthetic) return host.open(id, opts);
          const first = synthetic._records[0];
          return host.open(first.id, { records: synthetic._records, title: `${this.cards[0].label} · ${synthetic[this.cards[0].sx]}` });
        };
        this.history = { box, view: new View(Object.freeze({ setView: () => null, propose: (e) => host.propose(e), open, setStatus: () => {}, get element() { return host.element; } }), box) };
      }
      slot.replaceChildren(this.history.box);
      el.classList.add('dv-kpi-has-history');
      const guides = [];
      if (isNum(c.target)) guides.push({ rule: { y: c.target }, label: `target ${fmtNum(c.target)}` });
      if (k.gate && isNum(k.gate.min)) guides.push({ rule: { y: k.gate.min }, label: `gate ≥ ${fmtNum(k.gate.min)}` });
      if (k.gate && isNum(k.gate.max)) guides.push({ rule: { y: k.gate.max }, label: `gate ≤ ${fmtNum(k.gate.max)}` });
      // producer mode: the readings themselves (hover and click reach the row); summary mode: one synthetic row per x
      // whose click lists the rows behind that point
      let rows = c.series.map((p) => p.row), columns = input.columns, y = c.sy;
      if (c.summary) {
        y = '__kpi';
        columns = { ...input.columns, __kpi: { id: '__kpi', label: c.card.label, type: 'number', unitText: c.card.unit || undefined } };
        rows = c.series.map((p, j) => ({ id: `kpi:${c.key}:${j}`, [c.sx]: p.x, __kpi: p.y, _records: p.rows }));
      }
      this._synthetic = new Map(rows.filter((r) => r._records).map((r) => [r.id, r]));
      const view = Object.freeze({ type: 'chart', name: c.label,
        chart: { mark: { type: 'line', point: true }, encoding: { x: { field: c.sx, title: null }, y: { field: y, title: null, scale: { zero: false } } } },
        guides, hover: c.summary ? { title: c.sx, fields: [y] } : { fields: [c.sy, c.sx] } });
      await this.history.view.update({ ...input, rows, columns, groups: null, view });
      if (live()) el.removeAttribute('aria-busy');
    } catch (err) {
      if (!live()) return;
      // the sparkline stays; the history is an extra, and its failure is said under it
      this._chartMod = null;
      el.classList.remove('dv-kpi-has-history');
      el.classList.add('dv-kpi-history-failed');
      el.removeAttribute('aria-busy');
      slot.innerHTML = `<p class="dv-err">history: ${esc(err.message)}</p>`;
    }
  }

  _open(i) {
    const c = this.cards && this.cards[i];
    if (!c || !c.rows.length) return;
    const row = c.latest || c.rows[c.rows.length - 1];
    this.host.open(row.id, { records: c.ordered.length ? c.ordered : c.rows, title: c.label });
  }
}

/** Rows grouped by x, in x order: [[x, rows]]. */
function buckets(rows, xOf) {
  const out = new Map();
  for (const r of rows) { const x = xOf(r); if (!out.has(x)) out.set(x, []); out.get(x).push(r); }
  return [...out.entries()];
}

const label = (columns, id) => (columns[id] ? columns[id].label : id);
const fmtDate = (text) => {
  const t = Date.parse(text);
  return Number.isNaN(t) ? String(text) : new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

// one default export for every type of this bundle (the registry loads one class per bundle): the view's type is on its element
const VIEWS = { kpi: KpiView, gauge: GaugeView, bullet: BulletView, barlist: BarlistView, tracker: StatusView };
export default class StatCards {
  constructor(host, el) {
    const type = (/\bdv-view-([\w-]+)/.exec(el.className) || [])[1];
    return new (VIEWS[type] || KpiView)(host, el);
  }
}
