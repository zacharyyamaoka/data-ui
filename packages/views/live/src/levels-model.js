/* The levels card's bins (docs/peps/0012-live-data.md §6.3), pure: no DOM, so tests/unit runs it as it is.

   RobotDx's health bar (io-diagnostics web/health.js): "a bar is the worst level held in its bin; no data is an empty
   outline, never a level". A bin is (start, end]: the newest reading at t lands in the last bin, so a following card
   shows it the frame it arrives. */

// WHY the status vocabulary's order (docs/CONTRACT.md §35, level_history): it was RobotDx's five levels, so a gate's fail
// ranked as an unknown word, best, and a bin holding a warn and a fail showed the warn. The five keep their order.
import { STATUS_ORDER } from '../../../core/src/status.js';

export const LEVELS = STATUS_ORDER;

/** The worst of some levels by `order` (best first, worst last). A level the order does not name counts as the
    best, so an unexpected word never hides a known problem. */
export function worstOf(levels, order = LEVELS) {
  let best = null, rank = -2;
  for (const l of levels) {
    if (l === null || l === undefined || l === '') continue;
    const r = order.indexOf(l);
    if (r > rank) { rank = r; best = l; }
  }
  return best;
}

/** `changes` [{t, level}] in time order, `before` the level in force at a (or null), n bins over (a, b] → the worst
    level held in each bin, null where nothing was in force. */
export function levelBins(changes, before, a, b, n, order = LEVELS) {
  const w = (b - a) / n;
  const out = new Array(n).fill(null);
  let cur = before ?? null, i = 0;
  while (i < changes.length && changes[i].t <= a) { cur = changes[i].level; i++; }
  for (let k = 0; k < n; k++) {
    const hi = k === n - 1 ? b : a + (k + 1) * w;
    const held = cur !== null && cur !== undefined ? [cur] : [];
    while (i < changes.length && changes[i].t <= hi) { held.push(changes[i].level); cur = changes[i].level; i++; }
    out[k] = held.length ? worstOf(held, order) : null;
  }
  return out;
}
