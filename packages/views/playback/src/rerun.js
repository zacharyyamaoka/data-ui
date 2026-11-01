/* P1 `rerun` and `rerun-streams` (docs/peps/0005-dashboard-cards.md §4b): Rerun's time panel, copied.

   rerun: Rerun's toolbar as it sits over a collapsed time panel: play/pause (blue while playing), step forward, the
   step menu (a chevron; Rerun 0.2x's keys), the loop button with its mode menu (off / loop all / loop selection), the
   timeline picker (the clock's time column), the speed field ("1.00x", editable) and the time field ("+3.20s", typing
   seeks), then the collapsed panel's one-line scrubber.
   rerun-streams: the same toolbar over the expanded panel: the STREAMS tree (one node per time-aware dataset, a child
   per column or clip; collapsible, searchable, resizable), a time ruler ("+0s", "+1s" …), each row's event bar from
   its first to its last sample with its event ticks, the loop selection band and the playhead with its triangle
   across every row. Click or drag on the ruler seeks; Shift+drag sets the loop selection.

   Keys (Rerun's step menu): ←/→ 0.1 s, Shift ±1 s, Ctrl previous/next event (a sample time of any time-aware
   dataset), Ctrl+Shift start/end of the timeline.
   STOCK PARTS: none (buttons, inputs, divs); the resizable tree is core's makeResizable. */

import { esc, makeResizable } from '@data-ui/core';
import { Variant, ICON } from './base.js';
import { niceTicks, niceStep, nextEvent, prevEvent, rerunTime, rerunSpeed, parseTime, parseSpeed, tickColumns } from './model.js';

const STEPS = [
  { id: 'fwd-0.1', label: 'Forward 0.1s', key: 'Right' },
  { id: 'back-0.1', label: 'Backward 0.1s', key: 'Left' },
  '-',
  { id: 'fwd-1', label: 'Forward 1s', key: 'Shift+Right' },
  { id: 'back-1', label: 'Backward 1s', key: 'Shift+Left' },
  '-',
  { id: 'next-event', label: 'Next event', key: 'Ctrl+Right' },
  { id: 'prev-event', label: 'Previous event', key: 'Ctrl+Left' },
  '-',
  { id: 'end', label: 'End of timeline', key: 'Ctrl+Shift+Right' },
  { id: 'start', label: 'Start of timeline', key: 'Ctrl+Shift+Left' },
];

export class RerunPlayback extends Variant {
  constructor(host, el, name = 'rerun', clock) {
    super(host, el, name, clock);
    el.innerHTML = `<div class="dv-rr${name === 'rerun' ? ' dv-rr-collapsed' : ''}" data-variant-root>
      ${this.toolbar()}
      ${this.body()}
    </div>`;
    this.$ = (s) => el.querySelector(s);
    this.on(el, 'click', (e) => this.click(e));
    const speed = this.$('.dv-rr-speed'), time = this.$('.dv-rr-time');
    const commit = (input, parse, apply, fmt) => {
      const v = parse(input.value);
      if (v !== null) apply(v);
      input.value = fmt();
    };
    this.on(speed, 'keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); speed.blur(); } else if (e.key === 'Escape') { speed.value = rerunSpeed(this.clock.rate); speed.blur(); } });
    this.on(speed, 'change', () => commit(speed, parseSpeed, (r) => this.clock.setRate(r), () => rerunSpeed(this.clock.rate)));
    this.on(speed, 'focus', () => { speed.value = Number(this.clock.rate).toFixed(2); speed.select(); });
    this.on(speed, 'blur', () => { speed.value = rerunSpeed(this.clock.rate); });
    // WHY seek on every keystroke that parses: Zach's spec says "typing seeks"; Enter or leaving the field settles it
    this.on(time, 'input', () => { const t = parseTime(time.value); if (t !== null) this.clock.seek(t); });
    this.on(time, 'keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); time.blur(); } else if (e.key === 'Escape') time.blur(); });
    this.on(time, 'change', () => commit(time, parseTime, (t) => this.clock.seek(t), () => rerunTime(this.clock.t)));
    this.on(time, 'blur', () => { time.value = rerunTime(this.clock.t); });
    this.wireBody();
    this.ownKeys((e) => this.key(e));
  }

  toolbar() {
    return `<div class="dv-rr-bar" role="toolbar" aria-label="Playback">
      <button type="button" class="dv-rr-btn dv-rr-play" data-act="play" title="Play / pause (Space)" aria-label="Play">${ICON.playLine}</button>
      <button type="button" class="dv-rr-btn" data-act="step" title="Step to the next event (Ctrl+Right)" aria-label="Step forward">${ICON.stepFwd}</button>
      <button type="button" class="dv-rr-btn dv-rr-chev" data-act="steps" title="Step" aria-label="Step menu" aria-haspopup="menu" aria-expanded="false">${ICON.scrub}${ICON.chev}</button>
      <button type="button" class="dv-rr-btn dv-rr-chev dv-rr-loop" data-act="loop" title="Loop mode" aria-label="Loop mode" aria-haspopup="menu" aria-expanded="false">${ICON.loop}${ICON.chev}</button>
      <label class="dv-rr-timeline" title="Timeline"><span class="dv-pbv-sr">Timeline</span><select aria-label="Timeline"></select>${ICON.chev}</label>
      <input class="dv-rr-speed" type="text" inputmode="decimal" spellcheck="false" aria-label="Playback speed" title="Playback speed (type, then Enter)" value="1.00x">
      <input class="dv-rr-time" type="text" spellcheck="false" aria-label="Current time" title="Current time (type a time to seek)" value="+0.00s">
      ${this.name === 'rerun' ? '' : '<span class="dv-rr-flex"></span>'}
    </div>`;
  }

  body() {
    return `<div class="dv-rr-mini" data-scrub title="Click or drag to seek"><div class="dv-rr-mini-sel" hidden></div><div class="dv-rr-mini-fill"></div><div class="dv-rr-mini-head" data-playhead></div></div>`;
  }

  wireBody() { this.scrub(this.$('[data-scrub]')); }

  click(e) {
    const b = e.target.closest('[data-act]');
    if (!b || !this.el.contains(b)) return;
    const c = this.clock, act = b.dataset.act;
    if (act === 'play') c.toggle();
    else if (act === 'step') this.doStep('next-event');
    else if (act === 'steps') {
      if (this._menu && this._menu.button === b) { this.closeMenu(); return; }
      this.menu(b, STEPS.map((s) => (s === '-' ? s : { label: s.label, key: s.key, act: () => this.doStep(s.id) })));
    } else if (act === 'loop') {
      if (this._menu && this._menu.button === b) { this.closeMenu(); return; }
      const mode = this.loopMode();
      this.menu(b, [
        { label: 'Off', checked: mode === 'off', act: () => this.setLoopMode('off') },
        { label: 'Loop all', checked: mode === 'all', act: () => this.setLoopMode('all') },
        { label: 'Loop selection', checked: mode === 'selection', act: () => this.setLoopMode('selection') },
      ]);
    }
  }

  /** The loop mode as Rerun names it, from the clock: off, all (loop, no selection) or selection (loop over range). */
  loopMode() { const c = this.clock; return !c.loop ? 'off' : c.range ? 'selection' : 'all'; }

  setLoopMode(mode) {
    const c = this.clock;
    if (mode === 'off') { c.setLoop(false); return; }
    if (mode === 'all') { c.setRange(null); c.setLoop(true); return; }
    // loop selection: the selection there is, else the zoom window, else the middle half (Rerun makes a default one)
    if (!c.range) {
      const [a, b] = this.span();
      c.setRange(c.window ? c.window : [a + (b - a) / 4, a + (3 * (b - a)) / 4]);
    }
    c.setLoop(true);
  }

  doStep(id) {
    const c = this.clock, [a, b] = this.span();
    c.pause();
    let t = null;
    if (id === 'fwd-0.1') t = c.t + 0.1;
    else if (id === 'back-0.1') t = c.t - 0.1;
    else if (id === 'fwd-1') t = c.t + 1;
    else if (id === 'back-1') t = c.t - 1;
    else if (id === 'next-event') t = nextEvent(this.events(), c.t);
    else if (id === 'prev-event') t = prevEvent(this.events(), c.t);
    else if (id === 'end') t = b;
    else if (id === 'start') t = a;
    if (t !== null) c.seek(t, { source: 'step' });
  }

  key(e) {
    if (e.altKey || e.metaKey) return false;
    const right = e.key === 'ArrowRight', left = e.key === 'ArrowLeft';
    if (!right && !left) return false;
    const ctrl = e.ctrlKey, shift = e.shiftKey;
    const id = ctrl && shift ? (right ? 'end' : 'start') : ctrl ? (right ? 'next-event' : 'prev-event') : shift ? (right ? 'fwd-1' : 'back-1') : right ? 'fwd-0.1' : 'back-0.1';
    this.doStep(id);
    return true;
  }

  update(input) {
    super.update(input);
    const { timeCol } = this.data();
    this.$('.dv-rr-timeline select').innerHTML = `<option value="${esc(timeCol)}">${esc(timeCol)}</option>`;
    this.state();
  }

  time() {
    const c = this.clock;
    this.el.style.setProperty('--dv-pb-f', String(this.frac(c.t)));
    const time = this.$('.dv-rr-time');
    if (document.activeElement !== time) time.value = rerunTime(c.t);
  }

  state() {
    const c = this.clock;
    const play = this.$('.dv-rr-play');
    play.innerHTML = c.playing ? ICON.pauseLine : ICON.playLine;
    play.setAttribute('aria-label', c.playing ? 'Pause' : 'Play');
    play.classList.toggle('dv-on', c.playing);
    const loop = this.$('.dv-rr-loop');
    loop.classList.toggle('dv-on', c.loop);
    loop.title = `Loop mode: ${{ off: 'off', all: 'loop all', selection: 'loop selection' }[this.loopMode()]}`;
    loop.dataset.mode = this.loopMode();
    const speed = this.$('.dv-rr-speed');
    if (document.activeElement !== speed) speed.value = rerunSpeed(c.rate);
    this.el.toggleAttribute('data-empty', c.start === null);
    this.drawSelection();
    this.time();
  }

  drawSelection() {
    const sel = this.$('.dv-rr-mini-sel'), c = this.clock;
    if (!sel) return;
    sel.hidden = !c.range;
    if (c.range) { sel.style.left = `${this.frac(c.range[0]) * 100}%`; sel.style.width = `${(this.frac(c.range[1]) - this.frac(c.range[0])) * 100}%`; }
  }
}

export class RerunStreamsPlayback extends RerunPlayback {
  constructor(host, el, name, clock) {
    super(host, el, 'rerun-streams', clock);
    this.open = new Set();
    this.selected = null;
    this.query = '';
  }

  body() {
    return `<div class="dv-rrs">
      <div class="dv-rrs-head">
        <div class="dv-rrs-title"><span>Streams</span><button type="button" class="dv-rr-btn dv-rrs-find" data-act="find" title="Search streams" aria-label="Search streams" aria-expanded="false">${ICON.search}</button></div>
        <div class="dv-rrs-ruler" data-scrub title="Click or drag to seek · Shift+drag sets the loop selection"><div class="dv-rrs-ticks"></div><div class="dv-rrs-tri" data-playhead></div></div>
      </div>
      <input class="dv-rrs-q" type="search" placeholder="Filter streams" aria-label="Filter streams" hidden>
      <div class="dv-rrs-body">
        <div class="dv-rrs-tree" role="tree" aria-label="Streams"></div>
        <div class="dv-rrs-lanes"></div>
      </div>
      <div class="dv-rrs-sel" hidden></div>
      <div class="dv-rrs-line" aria-hidden="true"></div>
    </div>`;
  }

  wireBody() {
    const ruler = this.$('.dv-rrs-ruler');
    let from = null;
    this.scrub(ruler, {
      onDown: (e) => {
        if (!e.shiftKey) return true;
        from = this.tAt(e.clientX, ruler);
        try { ruler.setPointerCapture(e.pointerId); } catch { /* synthetic pointer */ }
        return false;
      },
    });
    this.on(ruler, 'pointermove', (e) => {
      if (from === null) return;
      const t = this.tAt(e.clientX, ruler);
      if (Math.abs(t - from) > 1e-3) { this.clock.setRange([Math.min(from, t), Math.max(from, t)]); this.clock.setLoop(true); }
    });
    const end = () => { from = null; };
    this.on(ruler, 'pointerup', end);
    this.on(ruler, 'pointercancel', end);
    this.on(this.$('.dv-rrs-tree'), 'click', (e) => {
      const row = e.target.closest('[data-stream]');
      if (!row) return;
      const id = row.dataset.stream;
      if (e.target.closest('.dv-rrs-tw') && row.dataset.parent === undefined) {
        if (this.open.has(id)) this.open.delete(id); else this.open.add(id);
      }
      this.selected = id;
      this.drawTree();
    });
    this.on(this.$('.dv-rrs-tree'), 'keydown', (e) => {
      const row = e.target.closest('[data-stream]');
      if (!row || (e.key !== 'Enter' && e.key !== ' ')) return;
      e.preventDefault(); e.stopPropagation();
      row.click();
    });
    const q = this.$('.dv-rrs-q');
    this.on(q, 'input', () => { this.query = q.value.trim().toLowerCase(); this.drawTree(); });
    this.on(q, 'keydown', (e) => { if (e.key === 'Escape') { q.value = ''; this.query = ''; q.hidden = true; this.drawTree(); } });
    const tree = this.$('.dv-rrs-tree');
    // WHY resizable: Zach's rule, every side panel gets a draggable, remembered boundary (.claude/feedback.md)
    tree.dataset.resizable = 'right';
    requestAnimationFrame(() => {
      if (!tree.isConnected) return;
      this._resize = makeResizable(tree, { edge: 'right', min: 140, max: 420, keep: 160, key: `playback-streams:${this.host.element.id || 'x'}`, label: 'the streams tree' });
    });
    this._ro = new ResizeObserver(() => this.layout());
    this._ro.observe(tree);
    this._ro.observe(this.$('.dv-rrs-lanes'));
    this._off.push(() => { if (this._resize) this._resize.destroy(); });
  }

  click(e) {
    const b = e.target.closest('[data-act="find"]');
    if (b && this.el.contains(b)) {
      const q = this.$('.dv-rrs-q');
      q.hidden = !q.hidden;
      b.setAttribute('aria-expanded', String(!q.hidden));
      if (!q.hidden) q.focus(); else { q.value = ''; this.query = ''; this.drawTree(); }
      return;
    }
    super.click(e);
  }

  update(input) {
    super.update(input);
    const key = this._key(this.data().datasets);
    if (key !== this._streamsKey) {
      this._streamsKey = key;
      this.tree = this.streams();
      if (!this._opened) { this._opened = true; if (this.tree[0]) this.open.add(this.tree[0].name); }
    }
    this.drawTree();
  }

  /** The tree and the lanes, one row each: on data, a fold, a selection or a search; never per tick. */
  drawTree() {
    const tree = this.tree || [];
    const q = this.query;
    const rows = [];
    for (const n of tree) {
      const kids = n.children.filter((k) => !q || k.name.toLowerCase().includes(q) || n.name.toLowerCase().includes(q));
      if (q && !kids.length && !n.name.toLowerCase().includes(q)) continue;
      const open = this.open.has(n.name) || !!q;
      rows.push({ id: n.name, node: n, depth: 0, open, hidden: false });
      for (const k of kids) rows.push({ id: `${n.name}/${k.name}`, node: k, depth: 1, parent: n.name, hidden: !open });
    }
    this.rows = rows;
    const icon = (r) => (r.depth === 0 ? ICON.entity : r.node.kind === 'clip' ? ICON.film : ICON.component);
    this.$('.dv-rrs-tree').innerHTML = rows.length ? rows.map((r) => `<div class="dv-rrs-row${r.id === this.selected ? ' dv-sel' : ''}" role="treeitem" tabindex="-1" data-stream="${esc(r.id)}"${r.parent !== undefined ? ` data-parent="${esc(r.parent)}"` : ''} aria-level="${r.depth + 1}"${r.depth === 0 ? ` aria-expanded="${r.open}"` : ''} aria-selected="${r.id === this.selected}"${r.hidden ? ' hidden' : ''} style="--d:${r.depth}">
        <span class="dv-rrs-tw">${r.depth === 0 ? ICON.caret : ''}</span><span class="dv-rrs-ic">${icon(r)}</span><span class="dv-rrs-name" title="${esc(r.id)}">${esc(r.node.name)}${r.depth === 0 ? '/' : ''}</span>
      </div>`).join('') : '<p class="dv-rrs-none">No time-aware data</p>';
    const first = this.$('.dv-rrs-tree [data-stream]');
    if (first) first.tabIndex = 0;
    this.$('.dv-rrs-lanes').innerHTML = rows.map((r) => `<div class="dv-rrs-lane${r.id === this.selected ? ' dv-sel' : ''}" data-lane="${esc(r.id)}"${r.hidden ? ' hidden' : ''}><div class="dv-rrs-ev" data-t0="${r.node.t0}" data-t1="${r.node.t1}"></div></div>`).join('');
    this.layout(true);
  }

  /** Place the bars and ticks for the current width (on resize and after drawTree). */
  layout(force = false) {
    const lanes = this.$('.dv-rrs-lanes'), tree = this.$('.dv-rrs-tree'), body = this.$('.dv-rrs-body');
    if (!lanes || !tree) return;
    const root = this.$('.dv-rrs');
    root.style.setProperty('--dv-rrs-tree', `${tree.getBoundingClientRect().width}px`);
    root.style.setProperty('--dv-rrs-sb', `${body.offsetWidth - body.clientWidth}px`);
    const w = Math.round(lanes.getBoundingClientRect().width);
    if (!force && w === this._w) return;
    this._w = w;
    const [a, b] = this.span();
    for (const r of this.rows || []) {
      const lane = lanes.querySelector(`[data-lane="${CSS.escape(r.id)}"] .dv-rrs-ev`);
      if (!lane) continue;
      const l = this.frac(r.node.t0), rr = this.frac(r.node.t1);
      lane.style.left = `${l * 100}%`;
      lane.style.width = `max(${(rr - l) * 100}%, 3px)`;
      const cols = tickColumns(r.node.times, r.node.t0, r.node.t1, Math.max(1, (rr - l) * w));
      lane.innerHTML = cols && cols.length > 1 ? cols.map((x) => `<i style="left:${x}px"></i>`).join('') : '';
      lane.classList.toggle('dv-dense', cols === null);
    }
    // the ruler: "+0s" … at nice steps, minor ticks at a fifth of a step (Rerun's)
    const n = Math.max(2, Math.floor(w / 110));
    const major = niceTicks(a, b, n), step = niceStep(a, b, n), minor = [];
    for (let v = Math.ceil(a / (step / 5) - 1e-9) * (step / 5); v <= b + 1e-9; v += step / 5) minor.push(+v.toFixed(10));
    this.$('.dv-rrs-ticks').innerHTML = minor.map((v) => `<i class="${major.some((m) => Math.abs(m - v) < 1e-9) ? 'dv-major' : ''}" style="left:${this.frac(v) * 100}%"></i>`).join('')
      + major.map((v) => `<span style="left:${this.frac(v) * 100}%">${esc(rerunTime(v).replace('.00s', 's').replace(/(\.\d)0s$/, '$1s'))}</span>`).join('');
  }

  state() {
    super.state();
    if (this.$('.dv-rrs') && this._w !== undefined) {
      const key = `${this.clock.start}|${this.clock.end}`;
      if (key !== this._spanKey) { this._spanKey = key; this.layout(true); }
    }
  }

  drawSelection() {
    const sel = this.$('.dv-rrs-sel'), c = this.clock;
    if (!sel) return;
    sel.hidden = !c.range;
    if (c.range) { sel.style.setProperty('--a', String(this.frac(c.range[0]))); sel.style.setProperty('--b', String(this.frac(c.range[1]))); }
  }
}
