/* type: chart — the view's `chart:` block IS a Vega-Lite spec minus data (the SPEC's schema); data-ui adds the
   rows, the theme from the page's tokens, the property types it already knows, and the `guides:` Vega-Lite cannot
   say in one line (Ashby envelopes, index lines, rules), each compiled to an ordinary Vega-Lite layer.

   Stock: vega 6.4.0 + vega-lite 6.5.0 + vega-embed 7.3.0 (BSD-3-Clause), loaded only when a chart view opens.
   Ours: this file. WHY Vega-Lite: the spec is the grammar an agent (or Altair, or Graphic Walker's normalize())
   already writes, so "edit the .base file" and "edit the chart" are the same act. */

import embed from 'vega-embed';

const TYPE = { number: 'quantitative', text: 'nominal', list: 'nominal' };

export default class ChartView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    el.innerHTML = '<div class="du-chart"></div><p class="du-chart-note du-muted"></p>';
    this.box = el.querySelector('.du-chart');
  }

  async update(input) {
    const { spec, meta } = compile(input);
    if (this.result) this.result.finalize();
    this.result = await embed(this.box, spec, { actions: false, renderer: 'svg', tooltip: { theme: 'custom' } });
    this.result.view.addEventListener('click', (_e, item) => {
      const id = item && item.datum && item.datum.id;
      if (id) this.host.open(id);
    });
    const label = (f) => (input.columns[f] || {}).label || f;
    this.el.querySelector('.du-chart-note').textContent =
      `${meta.plotted.toLocaleString()} of ${input.rows.length.toLocaleString()} rows plotted; the rest have no positive ${label(meta.x).toLowerCase()} or ${label(meta.y).toLowerCase()}. Click a dot to open the row.`;
  }

  destroy() {
    if (this.result) this.result.finalize();
    this.el.innerHTML = '';
  }
}

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const isPlotted = (r, x, y, lx, ly) => isNum(r[x]) && isNum(r[y]) && (!lx || r[x] > 0) && (!ly || r[y] > 0);

/** The view entry -> {spec: a full Vega-Lite spec, meta}. Exported for the build's checks. */
export function compile({ rows, view, columns, tokens }) {
  // WHY var(): an agent writes colours as the page's tokens ("var(--chart-3)"); Vega draws SVG/canvas attributes, which
  // cannot read custom properties, so they are resolved here, again on every theme change.
  const chart = JSON.parse(JSON.stringify(view.chart), (_k, v) => (typeof v === 'string' && /^var\(--[\w-]+\)$/.test(v) ? tokens.css[v.slice(6, -1)] || v : v));
  const enc = chart.encoding || {};
  for (const ch of Object.values(enc)) {
    for (const c of Array.isArray(ch) ? ch : [ch]) {
      if (c && c.field && !c.type && columns[c.field]) c.type = TYPE[columns[c.field].type] || 'nominal';
      if (c && c.field && !c.title && columns[c.field]) c.title = columns[c.field].label + (columns[c.field].unitText ? ` (${columns[c.field].unitText})` : '');
    }
  }
  if (Array.isArray(enc.tooltip)) enc.tooltip = enc.tooltip.map((f) => (typeof f === 'string' ? { field: f, type: TYPE[(columns[f] || {}).type] || 'nominal', title: (columns[f] || {}).label || f } : f));
  const x = enc.x && enc.x.field, y = enc.y && enc.y.field;
  const logx = !!(enc.x && enc.x.scale && enc.x.scale.type === 'log');
  const logy = !!(enc.y && enc.y.scale && enc.y.scale.type === 'log');
  const keep = ['id', ...new Set(Object.values(enc).flatMap((c) => (Array.isArray(c) ? c : [c])).map((c) => c && c.field).filter(Boolean))];
  for (const t of chart.transform || []) if (t.calculate) for (const m of t.calculate.match(/datum\.(\w+)/g) || []) keep.push(m.slice(6));
  const data = rows.filter((r) => isPlotted(r, x, y, logx, logy)).map((r) => Object.fromEntries(keep.map((k) => [k, r[k]])));
  const datasets = { rows: data };
  const back = [], front = [];
  for (const [i, g] of (view.guides || []).entries()) {
    if (g.envelope) {
      const { hulls, labels } = envelopes(data, g.envelope, rows, x, y, logx, logy);
      datasets[`env${i}`] = hulls;
      datasets[`envlabel${i}`] = labels;
      back.push({ data: { name: `env${i}` }, mark: { type: 'line', interpolate: 'linear-closed', fill: tokens.muted, fillOpacity: 0.07, stroke: tokens.muted, strokeOpacity: 0.6, strokeWidth: 1 },
        encoding: { x: { field: x, type: 'quantitative' }, y: { field: y, type: 'quantitative' }, order: { field: '_o' }, detail: { field: '_g' } } });
      front.push({ data: { name: `envlabel${i}` }, mark: { type: 'text', fontSize: 11, fontWeight: 600, fill: tokens.muted, dy: -8 },
        encoding: { x: { field: x, type: 'quantitative' }, y: { field: y, type: 'quantitative' }, text: { field: '_g' } } });
    } else if (g.indexLine) {
      const line = indexLine(data, x, y, g.indexLine);
      if (line) {
        datasets[`idx${i}`] = line;
        back.push({ data: { name: `idx${i}` }, mark: { type: 'line', stroke: tokens.accent, strokeDash: [5, 4], strokeWidth: 1.2, opacity: 0.8 },
          encoding: { x: { field: x, type: 'quantitative' }, y: { field: y, type: 'quantitative' } } });
        front.push({ data: { values: [line[1]] }, mark: { type: 'text', align: 'right', dx: -4, dy: -8, fontSize: 11, fill: tokens.accent },
          encoding: { x: { field: x, type: 'quantitative' }, y: { field: y, type: 'quantitative' }, text: { value: g.label || 'index' } } });
      }
    }
  }
  const main = { data: { name: 'rows' }, ...chart, encoding: enc };
  const spec = {
    $schema: 'https://vega.github.io/schema/vega-lite/v6.json',
    width: 'container', height: 470, autosize: { type: 'fit-x', contains: 'padding' },
    datasets, layer: [...back, main, ...front], config: theme(tokens),
  };
  return { spec, meta: { x, y, plotted: data.length } };
}

/** One convex hull per value of `property`, computed where the axes are drawn (log space on log axes). */
function envelopes(data, property, allRows, x, y, logx, logy) {
  const byId = new Map(allRows.map((r) => [r.id, r]));
  const fx = logx ? Math.log10 : (v) => v, fy = logy ? Math.log10 : (v) => v;
  const gx = logx ? (v) => 10 ** v : (v) => v, gy = logy ? (v) => 10 ** v : (v) => v;
  const groups = new Map();
  for (const d of data) {
    const key = (byId.get(d.id) || {})[property];
    if (key === null || key === undefined) continue;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push([fx(d[x]), fy(d[y])]);
  }
  const hulls = [], labels = [];
  for (const [key, pts] of groups) {
    if (pts.length < 3) continue;
    const hull = convexHull(pts);
    hull.forEach(([a, b], o) => hulls.push({ [x]: gx(a), [y]: gy(b), _o: o, _g: key }));
    const top = hull.reduce((m, p) => (p[1] > m[1] ? p : m), hull[0]);
    labels.push({ [x]: gx(top[0]), [y]: gy(top[1]), _g: key });
  }
  return { hulls, labels };
}

/** Andrew's monotone chain. */
function convexHull(points) {
  const p = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [], upper = [];
  for (const q of p) { while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop(); lower.push(q); }
  for (const q of p.reverse()) { while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop(); upper.push(q); }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

/** Ashby's performance index: on log-log axes, y = C·x^slope through the median of y / x^slope. */
function indexLine(data, x, y, { slope = 1 }) {
  const ratios = data.map((d) => d[y] / d[x] ** slope).filter((v) => v > 0).sort((a, b) => a - b);
  if (!ratios.length) return null;
  const C = ratios[ratios.length >> 1];
  const xs = data.map((d) => d[x]);
  const lo = Math.min(...xs), hi = Math.max(...xs);
  return [{ [x]: lo, [y]: C * lo ** slope }, { [x]: hi, [y]: C * hi ** slope }];
}

/** Vega-Lite config from the page's resolved tokens. WHY resolved: Vega draws SVG/canvas attributes, which cannot
    read CSS custom properties, so the host resolves them and sends them again when the theme changes. */
function theme(t) {
  const font = t.font || 'system-ui, sans-serif';
  return {
    background: null, font, view: { stroke: null },
    axis: { domainColor: t.border, gridColor: t.border, gridOpacity: 0.7, tickColor: t.border, labelColor: t.muted, titleColor: t.fg,
      labelFont: font, titleFont: font, titleFontWeight: 500, labelFontSize: 11, titleFontSize: 12 },
    legend: { labelColor: t.fg, titleColor: t.fg, labelFont: font, titleFont: font, titleFontWeight: 500, symbolType: 'circle' },
    range: { category: t.series.length ? t.series : undefined },
    text: { color: t.fg },
  };
}
