/* The row-model worker's entry (dist/rowmodel-worker.js; packages/core/src/rowmodel-worker.js is the why and the
   protocol). It holds one dataset, sent once (whole, in slices, or as the very bytes the page fetched) and kept in
   step with the page's edits, and answers each request with the model's order as transferable index arrays. */

import { workerServer } from './rowmodel-worker.js';

const handle = workerServer((message, transfer) => self.postMessage(message, transfer || []));
self.onmessage = (e) => handle(e.data);
