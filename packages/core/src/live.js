/* The live tier (docs/peps/0012-live-data.md, docs/CONTRACT.md §26), one module for the bundles that import the core
   by path (packages/dashboard: build.mjs maps every core/src/<name>.js import to the page's ./data-ui.js, so this file
   must sit at core/src/, not in live/). */

export { LiveDataset, isLiveDataset, setLiveBudget, liveBudget, parseBytes, parseDuration, CHUNK_ROWS, CHUNK_SPAN } from './live/store.js';
export { LiveClock, isLiveClock } from './live/clock.js';
export { connectSSE, connectPoll, rowsAt } from './live/sources.js';
export { minMaxColumns, alignSeries, ColumnCache, guideRows } from './live/window.js';
export { Tail, snapshotModel, LIVE_CAP } from './live/model.js';
export { flushLive, liveFrame, liveStats } from './live/frame.js';
export { liveData, atOf, LIVE_NATIVE, LIVE_IGNORE } from './live/feed.js';
export { DataLiveStatus } from './live/status.js';
export { addLiveStyle } from './live/style.js';
