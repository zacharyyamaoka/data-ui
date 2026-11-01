/* The live tier's one frame loop (docs/peps/0012-live-data.md §8).

   Rows arrive at any rate; nothing draws on arrival. The first change after a frame asks for ONE
   requestAnimationFrame, and in it, in this order:
     1. every live dataset with news publishes it (its `change` event: what was appended, upserted, removed, dropped);
     2. every live clock that heard of it moves (following: t = the newest data; its `time` / `live` events);
     3. every view whose rows or window changed draws, once.
   So a view never draws twice in a frame, a view nothing reached does not draw at all, and a background tab (no
   animation frames) draws nothing and catches up in one frame when it shows again (the store keeps taking rows).
   Outside a browser (node --test) the frame is a task, and flushLive() runs one now.
   STOCK PARTS: requestAnimationFrame (the coalescing point, prior-art note §3 "Rendering"). */

const datasets = new Set();
const clocks = new Set();
const feeds = new Set();
let pending = null;
let frameNo = 0;
let running = false;
const STATS = 600;   // the last 10 s of frames at 60 a second
const stats = [];

const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());

function request() {
  if (pending !== null || running) return;
  if (typeof requestAnimationFrame === 'function' && typeof document !== 'undefined') {
    pending = { raf: requestAnimationFrame((t) => run(t)) };
  } else {
    pending = { timer: setTimeout(() => run(now()), 0) };
  }
}

/** A dataset has news for the next frame. */
export function markDataset(ds) { datasets.add(ds); request(); }
/** A clock must move in the next frame (a dataset it follows changed). */
export function markClock(clock) { clocks.add(clock); if (!running) request(); }
/** A view must draw in the next frame (or in this one, when the frame is running and has not drawn yet). */
export function markFeed(feed) { feeds.add(feed); if (!running) request(); }

/** Run the frame now (tests, and a host that wants its rows on screen before it measures). */
export function flushLive() {
  if (pending) {
    if (pending.raf && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(pending.raf);
    if (pending.timer) clearTimeout(pending.timer);
  }
  run(now());
}

/** The number of the frame running now (or the last one). Every view drawn in one frame reports the same number. */
export function liveFrame() { return frameNo; }

/** The last frames' cost: [{frame, at, ms, datasets, clocks, draws}] (bench/live.py reads it). */
export function liveStats() { return stats.slice(); }

function run(at) {
  pending = null;
  if (running) return;
  running = true;
  frameNo++;
  const t0 = now();
  let nd = 0, nc = 0, nf = 0;
  try {
    const ds = [...datasets];
    datasets.clear();
    for (const d of ds) { nd++; try { d._publish(frameNo); } catch (err) { report(err); } }
    // a clock marked while the datasets published moves in this same frame
    const cs = [...clocks];
    clocks.clear();
    for (const c of cs) { nc++; try { c._sync(frameNo); } catch (err) { report(err); } }
    const fs = [...feeds];
    feeds.clear();
    for (const f of fs) { nf++; try { f._draw(frameNo); } catch (err) { report(err); } }
  } finally {
    running = false;
  }
  stats.push({ frame: frameNo, at, ms: now() - t0, datasets: nd, clocks: nc, draws: nf });
  if (stats.length > STATS) stats.splice(0, stats.length - STATS);
  // anything marked while the frame ran (a draw that asked for another) goes to the next frame
  if (datasets.size || clocks.size || feeds.size) request();
}

function report(err) {
  // WHY not throw: one view's bad draw must not stop the others' (the frame loop is shared by every live view)
  if (typeof console !== 'undefined') console.error('data-ui live frame:', err);
}
