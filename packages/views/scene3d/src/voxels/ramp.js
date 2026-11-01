/* The voxels' sequential ramp (docs/CONTRACT.md §32: "one family's rows use its ramp, mixed families grey, never red or
   green outside verdict"; docs/peps/0010-robotics-playback.md §7). One hue, its lightness the magnitude: light to dark on
   a light surface, and the other way on a dark one, so a cell near zero always recedes toward the surface (the dataviz
   rule: "flips anchor in dark"). The hue is the family's own (style.families through seriesColor); no family, or
   several, is grey.

   Built in OKLab (Björn Ottosson's): the two ends hold the family colour's OKLCH hue, and the ramp between them is a
   straight line in OKLab, so equal steps of value read as equal steps of lightness. WHY OKLab and not CIELAB or sRGB:
   CIELAB bends blue toward purple as it lightens (slot 1's pale tint sits 20° off in Lab, 6° in OKLCH), and an sRGB
   mix goes muddy in the middle. No import: numbers in, '#rrggbb' out (tests/unit/voxels.test.mjs). */

const lin = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const gam = (c) => { const v = Math.min(1, Math.max(0, c)); return Math.round((v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055) * 255); };

/** '#rgb', '#rrggbb' or 'rgb(r, g, b)' → [r, g, b] (0-255), else null. */
export function parseColor(text) {
  const s = String(text || '').trim();
  let m = /^#([0-9a-f]{6})$/i.exec(s);
  if (m) return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16));
  m = /^#([0-9a-f]{3})$/i.exec(s);
  if (m) return [0, 1, 2].map((i) => parseInt(m[1][i] + m[1][i], 16));
  m = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/i.exec(s);
  if (m) return [m[1], m[2], m[3]].map((x) => Math.round(Number(x)));
  return null;
}

export function toOklab([r8, g8, b8]) {
  const [r, g, b] = [r8, g8, b8].map(lin);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
}

/** OKLab → linear sRGB (unclamped). */
function linear([L, a, b]) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
  return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s];
}

const inGamut = (rgb) => rgb.every((c) => c >= -1e-6 && c <= 1 + 1e-6);

/** OKLab → sRGB 0-255. Out of the sRGB gamut, the chroma shrinks (bisection) until the colour fits, keeping its
    lightness and hue. WHY not clamp each channel: a clamped pale blue turns violet (OKLCH hue 243° for slot 1's 255°). */
export function fromOklab([L, a, b]) {
  let rgb = linear([L, a, b]);
  if (!inGamut(rgb)) {
    let lo = 0, hi = 1;
    for (let i = 0; i < 24; i++) { const mid = (lo + hi) / 2; if (inGamut(linear([L, a * mid, b * mid]))) lo = mid; else hi = mid; }
    rgb = linear([L, a * lo, b * lo]);
  }
  return rgb.map(gam);
}

export const hex = (rgb) => `#${rgb.map((c) => c.toString(16).padStart(2, '0')).join('')}`;

// the two ends in OKLCH: [lightness, the share of the family's chroma]. Light: a pale tint near the surface to a deep
// shade (the dataviz palette's steps 100 → 700 of its blue span L 0.92 → 0.33); dark: a shade just off the surface to a
// pale tint. WHY not the family colour itself at the end: at L 0.5 it would leave half the lightness range unused
export const ENDS = { light: [[0.95, 0.2], [0.36, 0.78]], dark: [[0.30, 0.48], [0.90, 0.32]] };

/** {lo, hi, at(t) → '#rrggbb', css(t), family}: the ramp for a base colour (the family's, any CSS colour) or grey when
    `base` is null. `dark` flips it. */
export function sequentialRamp({ base = null, dark = false } = {}) {
  const rgb = base ? parseColor(base) : null;
  let C = 0, h = 0;
  if (rgb) { const [, a, b] = toOklab(rgb); C = Math.hypot(a, b); h = Math.atan2(b, a); }
  const [e0, e1] = ENDS[dark ? 'dark' : 'light'];
  const end = ([L, k]) => [L, C * k * Math.cos(h), C * k * Math.sin(h)];
  const p0 = end(e0), p1 = end(e1);
  const at = (t) => {
    const u = Math.min(1, Math.max(0, Number.isFinite(t) ? t : 0));
    return hex(fromOklab([p0[0] + (p1[0] - p0[0]) * u, p0[1] + (p1[1] - p0[1]) * u, p0[2] + (p1[2] - p0[2]) * u]));
  };
  return { lo: at(0), hi: at(1), at, grey: !rgb };
}

const MID_GREY = [128, 128, 128];

/** {lo, hi, at(t) → '#rrggbb'}: a straight line in OKLab between two CSS colours, t clamped to [0, 1] (the ends are the
    colours themselves, to a unit). WHY OKLab, as the sequential ramp's: equal steps of t read as equal steps of lightness.
    An unreadable colour is a mid grey, never a throw. */
export function twoColorRamp(a, b) {
  const p = toOklab(parseColor(a) || MID_GREY), q = toOklab(parseColor(b) || MID_GREY);
  const at = (t) => {
    const u = Math.min(1, Math.max(0, Number.isFinite(t) ? t : 0));
    return hex(fromOklab([0, 1, 2].map((k) => p[k] + (q[k] - p[k]) * u)));
  };
  return { lo: at(0), hi: at(1), at };
}

/** The gates overlay's ramp (docs/CONTRACT.md §35 voxels `scale: verdict`): the bad tone at t = 0, the warn tone at the
    middle, the good tone at t = 1 (`better: lower` reads the other way round: good at 0, bad at 1). WHY two straight
    OKLab runs through the warn tone, not one line from bad to good: the middle must be the warn tone itself, and a straight
    line between red and green passes through a muddy olive. `dark` is accepted for symmetry with sequentialRamp and
    changes nothing: the tones the caller hands over are already the theme's (tokens.tone). */
export function verdictRamp({ bad, warn, good, better = 'higher', dark = false } = {}) {
  void dark;
  const [first, last] = better === 'lower' ? [good, bad] : [bad, good];
  const rising = twoColorRamp(first, warn), falling = twoColorRamp(warn, last);
  const at = (t) => {
    const u = Math.min(1, Math.max(0, Number.isFinite(t) ? t : 0));
    return u <= 0.5 ? rising.at(u * 2) : falling.at(u * 2 - 1);
  };
  return { lo: at(0), hi: at(1), at, grey: false };
}
