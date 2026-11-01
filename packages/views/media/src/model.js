/* The media cards' pure parts: which rows a card shows, the wipe's geometry, what a clip's basis is called.
   No DOM and no core import (the view passes cellValue in), so tests/unit/media.test.mjs runs them under node. */

/** How a clip was made, as a card prints it (docs/peps/0005-dashboard-cards.md §3). */
export const BASIS_TEXT = {
  'real-camera': 'real camera',
  'sim-render': 'sim render',
  'screen-capture': 'screen capture',
  illustrative: 'illustrative',
};

const plain = (v) => v;
const empty = (v) => v === null || v === undefined || v === '';

/** "sim render" for sim-render; an unknown basis is printed as written (dashes as spaces); none is null. */
export function basisText(basis) {
  if (empty(basis)) return null;
  return BASIS_TEXT[basis] || String(basis).replace(/-/g, ' ');
}

/** The two clips' basis in one phrase: "sim render" when they agree, "sim render vs real camera" when they differ. */
export function pairBasis(a, b) {
  const ta = basisText(a), tb = basisText(b);
  if (!ta && !tb) return null;
  if (ta === tb) return ta;
  return `${ta || 'basis not given'} vs ${tb || 'basis not given'}`;
}

/** Rows A and B of a video-compare card: `by` tells the clips apart, `a`/`b` are its values. Without a value the card
    takes the first row for A and the first other row for B. A value no row has gives null (the card says so). */
export function pickPair(rows, overlay = {}, read = plain) {
  const { by, a, b } = overlay || {};
  const list = rows || [];
  const is = (r, want) => !!by && String(read(r[by])) === String(want);
  const A = by && !empty(a) ? list.find((r) => is(r, a)) : list[0];
  const B = by && !empty(b) ? list.find((r) => r !== A && is(r, b)) : list.find((r) => r !== A);
  return { a: A || null, b: B || null };
}

/** split clamped to 0..1 (a missing or broken one is the middle). */
export function clampSplit(s) {
  const n = Number(s);
  return Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : 0.5;
}

/** The wipe: clip A's right side away so A shows on the left `split` of the picture and B on the rest. */
export function wipeClip(split) {
  const right = Math.round((1 - clampSplit(split)) * 1e6) / 1e4;
  return `inset(0 ${right}% 0 0)`;
}

/** A pointer at clientX over a picture spanning [left, left + width]: the split it asks for. */
export function splitAt(x, left, width) {
  return width > 0 ? clampSplit((x - left) / width) : 0.5;
}

export const MODES = ['wipe', 'onion', 'difference', 'side'];
export const MODE_LABEL = { wipe: 'Wipe', onion: 'Onion', difference: 'Difference', side: 'Side' };
