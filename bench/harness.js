/* bench/harness.js: injected into every bench page before any of its scripts run (Playwright add_init_script).
   It only listens: the browser's own timings (PerformanceObserver: paint, largest-contentful-paint, longtask, event,
   mark, measure, resource) plus data-ui's events, and answers bench/runner.py through window.__bench.

   "Painted" means: the frame after the work has been presented. A rAF callback runs before the frame's paint; a task
   posted from it runs after that frame is committed (the double-rAF idiom, without waiting a whole second frame).
   WHY not data-views-render alone: it fires when the view's update() returns, before style, layout and paint, and a
   number taken there flatters the kit (Codex's review, 2026-10-26: "without waiting for browser paint"). */
(() => {
  const B = {
    longtasks: [], events: [], lcp: [], paints: {}, marks: [], measures: [], renders: [], opens: [], errors: [],
    firstRender: null, firstUsefulPaint: null, pending: null, mutations: 0,
  };
  window.__bench = B;
  const now = () => performance.now();
  const afterPaint = () => new Promise((res) => requestAnimationFrame(() => setTimeout(() => res(now()), 0)));

  const observe = (type, fn, extra = {}) => {
    try { new PerformanceObserver((list) => list.getEntries().forEach(fn)).observe({ type, buffered: true, ...extra }); } catch { /* type unsupported */ }
  };
  observe('longtask', (e) => B.longtasks.push({ start: e.startTime, duration: e.duration }));
  observe('paint', (e) => { B.paints[e.name] = e.startTime; });
  observe('largest-contentful-paint', (e) => B.lcp.push({ t: e.renderTime || e.loadTime || e.startTime, size: e.size, tag: e.element ? e.element.tagName : null }));
  observe('event', (e) => B.events.push({ name: e.name, start: e.startTime, duration: e.duration, processing: e.processingEnd - e.processingStart }), { durationThreshold: 16 });
  observe('mark', (e) => { if (e.name.startsWith('data-ui:')) B.marks.push({ name: e.name, t: e.startTime, detail: e.detail }); });
  observe('measure', (e) => { if (e.name.startsWith('data-ui:')) B.measures.push({ name: e.name, start: e.startTime, duration: e.duration, detail: e.detail }); });

  addEventListener('error', (e) => B.errors.push(String(e.message || e.error)));
  addEventListener('unhandledrejection', (e) => B.errors.push(String(e.reason && e.reason.message || e.reason)));

  // the first view drawn, then the frame that shows it: first useful paint
  document.addEventListener('data-views-render', (e) => {
    const t = now();
    B.renders.push({ t, type: e.detail.type, rows: e.detail.rows, ms: e.detail.ms });
    if (B.firstRender === null) { B.firstRender = t; afterPaint().then((p) => { B.firstUsefulPaint = p; }); }
    if (B.pending && B.pending.wait === 'data-views-render' && B.pending.t0 !== null && !B.pending.seen) { B.pending.seen = true; afterPaint().then(B.pending.done); }
  }, true);
  document.addEventListener('data-views-open', () => {
    const t = now();
    B.opens.push(t);
    if (B.pending && B.pending.wait === 'data-views-open' && B.pending.t0 !== null && !B.pending.seen) { B.pending.seen = true; afterPaint().then(B.pending.done); }
  }, true);

  // the input that starts an armed interaction: its own timestamp (when the user acted), not when we noticed
  for (const type of ['pointerdown', 'keydown']) {
    addEventListener(type, (e) => { if (B.pending && B.pending.t0 === null && e.isTrusted) B.pending.t0 = e.timeStamp; }, true);
  }
  // DOM churn per interaction (Codex: "each draw replaces the entire visible tbody")
  const mo = new MutationObserver((records) => { for (const r of records) B.mutations += r.addedNodes.length; });
  const watch = () => mo.observe(document.body, { childList: true, subtree: true });
  if (document.body) watch(); else addEventListener('DOMContentLoaded', watch, { once: true });

  /** Arm one interaction: the next trusted pointerdown/keydown (or now(), for a programmatic action) is t0; the end is
      the frame painted after the next `wait` event. Read it with result(). */
  B.arm = (kind, wait = 'data-views-render', programmatic = false) => {
    const p = { kind, wait, t0: programmatic ? now() : null, seen: false, m0: B.measures.length, l0: B.longtasks.length, mut0: B.mutations };
    p.promise = new Promise((res) => { p.done = res; });
    B.pending = p;
    return true;
  };
  B.result = async (timeoutMs = 15000) => {
    const p = B.pending;
    if (!p) return null;
    const end = await Promise.race([p.promise, new Promise((res) => setTimeout(() => res(null), timeoutMs))]);
    B.pending = null;
    if (end === null || p.t0 === null) return { kind: p.kind, ms: null, why: p.t0 === null ? 'no input seen' : `no ${p.wait} within ${timeoutMs} ms` };
    const ms = B.measures.slice(p.m0);
    const sum = (name) => ms.filter((m) => m.name === name).reduce((s, m) => s + m.duration, 0);
    const tasks = B.longtasks.slice(p.l0).filter((t) => t.start >= p.t0 - 1);
    return {
      kind: p.kind, ms: end - p.t0, model_ms: sum('data-ui:model'), render_ms: sum('data-ui:render'), rail_ms: sum('data-ui:rail'),
      renders: ms.filter((m) => m.name === 'data-ui:render').length, rails: ms.filter((m) => m.name === 'data-ui:rail').length,
      longtask_ms: tasks.reduce((s, t) => s + t.duration, 0), dom_added: B.mutations - p.mut0,
    };
  };
  /** A programmatic action, measured the same way: t0 is now, the end is the paint after `wait`. */
  B.act = async (kind, fn, wait = 'data-views-render') => { B.arm(kind, wait, true); fn(); return B.result(); };

  /** Wait until the main thread has been free of long tasks for `quiet` ms after first useful paint (Lighthouse's TTI
      uses 5 s; 500 ms keeps a bench run short, and is written in bench/KPIS.md). Resolves the TTI or null. */
  B.interactive = async (quiet = 500, limit = 20000) => {
    const t0 = now();
    while (B.firstUsefulPaint === null) { if (now() - t0 > limit) return null; await new Promise((r) => setTimeout(r, 20)); }
    for (;;) {
      const last = B.longtasks.filter((t) => t.start + t.duration >= B.firstUsefulPaint).reduce((m, t) => Math.max(m, t.start + t.duration), 0);
      const since = Math.max(last, B.firstUsefulPaint);
      if (now() - since >= quiet) return since;
      if (now() - t0 > limit) return null;
      await new Promise((r) => setTimeout(r, 50));
    }
  };

  /** Scroll the view's own scroller (or the page's) by `step` px per frame for `ms`; frame intervals from rAF. */
  B.scroll = async (ms = 2000, step = 120) => {
    const host = document.querySelector('data-views');
    let box = host && host.host && host.host.scroller;
    if (!box) box = [...host.querySelectorAll('*')].find((e) => e.scrollHeight > e.clientHeight + 200 && /auto|scroll/.test(getComputedStyle(e).overflowY));
    if (!box) return null;
    const target = box === window ? document.scrollingElement : box;
    const frames = [];
    const l0 = B.longtasks.length, mut0 = B.mutations;
    const max = target.scrollHeight - target.clientHeight;
    await new Promise((done) => {
      let last = null; const start = now();
      const tick = (t) => {
        if (last !== null) frames.push(t - last);
        last = t;
        target.scrollTop = Math.min(max, target.scrollTop + step);
        if (t - start < ms && target.scrollTop < max) requestAnimationFrame(tick); else done();
      };
      requestAnimationFrame(tick);
    });
    target.scrollTop = 0;
    return { frames, scrolled_px: max, longtask_ms: B.longtasks.slice(l0).reduce((s, t) => s + t.duration, 0), dom_added: B.mutations - mut0 };
  };

  /** A fixed amount of CPU work: how fast this machine is right now (the bench's noise gauge). */
  B.calibrate = () => {
    const t0 = now(); let x = 0;
    for (let i = 0; i < 3e7; i++) x = (x + i * 7) % 1000003;
    return { ms: now() - t0, x };
  };
})();
