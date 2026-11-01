/* The token contract (docs/CONTRACT.md §4). Hosts set --data-* (or nothing: the defaults read shadcn's names);
   every data-ui element resolves them into private --dv-* custom properties (styles/tokens.css). Views that draw on
   canvas or SVG get them here as concrete colours, again on every theme change. */

export const TOKENS = ['bg', 'fg', 'muted', 'subtle', 'border', 'rule', 'hover', 'accent', 'on-accent', 'warn', 'good', 'bad',
  'radius', 'font', 'mono', 'row', 'height'];
export const SERIES = 8;
export const TONE_NAMES = ['good', 'warn', 'bad', 'muted', 'neutral'];
export const BASES = ['measured', 'datasheet', 'seller', 'derived', 'estimate', 'assumed', 'chosen', 'sampled', 'stand-in', 'claimed'];

const camel = (s) => s.replace(/-(\w)/g, (_m, c) => c.toUpperCase());

/** The --data-* tokens as an element sees them: {bg, fg, muted, ..., series: [8], basis: {measured, ...}, font,
    css: {'data-bg': ..., 'data-series-1': ..., ...}, dark}. Reads the resolved --dv-* values, so the defaults are
    included when the host sets nothing. */
export function resolveTokens(el) {
  const cs = getComputedStyle(el);
  const raw = (n) => cs.getPropertyValue(`--dv-${n}`).trim();
  const get = (n) => (['radius', 'font', 'mono', 'row', 'height'].includes(n) ? raw(n) : toRgb(raw(n)));
  const css = {};
  const out = {};
  for (const t of TOKENS) { css[`data-${t}`] = get(t); out[camel(t)] = css[`data-${t}`]; }
  out.series = [];
  for (let i = 1; i <= SERIES; i++) { css[`data-series-${i}`] = get(`series-${i}`); out.series.push(css[`data-series-${i}`]); }
  // the status tones (CONTRACT §35): the gates' and RobotDx's words, and the views that draw them on canvas (voxels' verdict
  // ramp, the path overlay's ramp end), read them here
  out.tone = {};
  for (const n of TONE_NAMES) out.tone[n] = get(`tone-${n}`);
  out.basis = {};
  for (const b of BASES) { css[`data-basis-${b}`] = get(`basis-${b}`); out.basis[b] = css[`data-basis-${b}`]; }
  out.font = out.font || cs.fontFamily;
  out.css = css;
  out.dark = luminance(out.bg) < 0.4;
  return out;
}

let probe = null;
const memo = new Map();
/** Any CSS colour (oklch(), color-mix(), a name) as rgb()/rgba() text, which every chart and map library reads.
    WHY a pixel: a computed custom property keeps the colour as written, and canvas fillStyle keeps oklch(). */
export function toRgb(color) {
  if (!color) return color;
  if (memo.has(color)) return memo.get(color);
  let out = color;
  try {
    probe = probe || (typeof OffscreenCanvas !== 'undefined' ? new OffscreenCanvas(1, 1) : document.createElement('canvas'));
    const ctx = probe.getContext('2d', { willReadFrequently: true });
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = '#000';
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
    out = a === 255 ? `rgb(${r}, ${g}, ${b})` : `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(3)})`;
  } catch { /* no canvas (a test runner): keep the text */ }
  memo.set(color, out);
  return out;
}

function luminance(color) {
  const m = /rgba?\(([\d.]+)[, ]+([\d.]+)[, ]+([\d.]+)/.exec(color || '');
  if (!m) return 1;
  return (0.2126 * m[1] + 0.7152 * m[2] + 0.0722 * m[3]) / 255;
}
