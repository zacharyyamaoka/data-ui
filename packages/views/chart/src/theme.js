/** Vega-Lite config from the page's resolved tokens. WHY resolved: Vega draws on canvas, which cannot read CSS custom
    properties, so the host resolves them (input.tokens) and sends them again when the theme changes.

    chrome: 'minimal' (the dashboard default, docs/peps/0005-dashboard-cards.md §5) is the references' frameless look
    (Klipfolio, Tremor): no axis domain line, no ticks, no gridlines, muted 11 px labels, the legend on top as small
    dots; `grid: 'y'` keeps one faint horizontal grid (line charts and time series). 'full' (or no style, outside a
    dashboard) is the chart view's own look, unchanged. */
export function theme(t, { narrow, chrome = 'full', grid = 'none' } = {}) {
  const font = t.font || 'system-ui, sans-serif';
  const config = {
    background: null, font, view: { stroke: null },
    axis: { domainColor: t.border, gridColor: t.rule, tickColor: t.border, labelColor: t.muted, titleColor: t.fg,
      labelFont: font, titleFont: font, titleFontWeight: 500, labelFontSize: 11, titleFontSize: 12, labelFlush: true, labelOverlap: true,
      // WHY a limit on phones: long category names would take the plot's width; Vega ends a cut label with an
      // ellipsis, and the hover card keeps the full value
      labelLimit: narrow ? 110 : 200 },
    legend: { orient: narrow ? 'bottom' : 'right', direction: narrow ? 'horizontal' : 'vertical', columns: narrow ? 2 : undefined, labelColor: t.fg, titleColor: t.muted,
      labelFont: font, titleFont: font, titleFontWeight: 500, labelFontSize: 11, titleFontSize: 11, symbolType: 'circle', labelLimit: narrow ? 84 : 160, columnPadding: 8 },
    header: { labelFont: font, titleFont: font, labelColor: t.fg, titleColor: t.muted },
    title: { color: t.fg, font, fontWeight: 600, fontSize: 13, anchor: 'start' },
    range: { category: t.series, ramp: [t.subtle, t.accent], heatmap: [t.subtle, t.accent] },
    mark: { color: t.series[0] }, point: { size: 34, opacity: 0.8, filled: true }, circle: { size: 34, opacity: 0.8 }, square: { size: 30, opacity: 0.8 },
    bar: { color: t.series[0], cornerRadiusEnd: 2 }, line: { strokeWidth: 1.8 }, tick: { thickness: 1.5 },
    text: { color: t.fg, font }, rule: { color: t.muted },
  };
  if (chrome !== 'minimal') return config;
  // WHY frameless: Zach's references (Klipfolio-style dark dashboards, Tremor) draw no box, no axis lines and no
  // ticks; the numbers and a faint horizontal grid carry the scale
  Object.assign(config.axis, { domain: false, ticks: false, grid: false, labelPadding: 6, titleColor: t.muted, titleFontWeight: 400, titleFontSize: 11, titlePadding: 8 });
  config.axisY = grid === 'y' ? { grid: true, gridColor: t.rule, gridOpacity: 1 } : {};
  // categories read level (a heatmap's four rungs), as the references draw them; Vega hides a label that would overlap
  config.axisX = { grid: false };
  config.axisXBand = { labelAngle: 0, labelAlign: 'center', labelBaseline: 'top' };
  Object.assign(config.legend, { orient: 'top', direction: 'horizontal', columns: undefined, titleOrient: 'left', titleColor: t.muted, titleFontWeight: 400,
    labelColor: t.muted, symbolSize: 42, padding: 0, offset: 10, rowPadding: 4, columnPadding: 12, labelLimit: narrow ? 90 : 160 });
  config.line = { strokeWidth: 1.5 };
  // a heatmap of tiles in the first series hue (Tremor's), not grey cells on a grid
  config.range = { ...config.range, ramp: [t.subtle, t.series[0]], heatmap: [t.subtle, t.series[0]] };
  config.rect = { stroke: t.bg, strokeWidth: 1.5, cornerRadius: 3 };
  return config;
}
