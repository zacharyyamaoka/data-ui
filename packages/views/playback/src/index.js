/* type: playback — the dashboard clock's control, placed in the layout like any card (docs/peps/0005-dashboard-cards.md
   §4, §4b, docs/CONTRACT.md §25).

   Zach, 2026-10-26, asked for "a timeline / slider card like Rerun's time panel: scrub, play and pause, speed, loop,
   step frame, a time range selection", then "Playback bar: 5 proposals, as a placeable card with a switcher". The
   default `bar` below is copied from Rerun's time panel (play controls on the left, the time readout, a track with
   time ticks, a loop-selection lane above it you drag to make) and Foxglove's playback bar (speed menu).
   `playback.variant` picks a proposal instead (rerun.js, youtube.js, tracks.js, foxglove.js, range.js; their prior
   art in ../README.md); `playback.switcher: true` adds a drop-down at the card's bottom-right that switches them live.

     playback: { speeds: [0.25, 0.5, 1, 2, 4], range: true, readout: true, variant: bar, switcher: false }

   It never owns time: every button calls the clock (the one writer), and it redraws on the clock's events. The thumb
   and the played fill move on every `time` event by a transform, never a re-render.
   STOCK PARTS: none (buttons, a <select>, pointer events); ~250 lines for the bar. */

import { clockFor, fmtTime, esc } from '@data-ui/core';
import barCss from './playback.css';
import variantsCss from './variants.css';
import { niceTicks } from './model.js';
import { RerunPlayback, RerunStreamsPlayback } from './rerun.js';
import { YoutubePlayback } from './youtube.js';
import { TracksPlayback } from './tracks.js';
import { FoxglovePlayback } from './foxglove.js';
import { RangePlayback } from './range.js';
import { registerPlaybackVariant, playbackVariant, playbackVariants } from './registry.js';
import { mountLive, tickText } from './live.js';

export const css = `${barCss}\n${variantsCss}`;
export { niceTicks, registerPlaybackVariant, playbackVariant, playbackVariants };

const ICON = {
  play: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 2.8v10.4L13 8z" fill="currentColor"/></svg>',
  pause: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 3h3v10H4zM9 3h3v10H9z" fill="currentColor"/></svg>',
  back: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 3h1.6v10H4zM13 3.2v9.6L6.4 8z" fill="currentColor"/></svg>',
  fwd: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10.4 3H12v10h-1.6zM3 3.2v9.6L9.6 8z" fill="currentColor"/></svg>',
  start: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3h1.6v10H3zM13 3.2v9.6L5.4 8z" fill="currentColor"/></svg>',
  loop: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 5h7.5l-1.6-1.6M12 11H4.5l1.6 1.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

/** The default proposal: the bar (Rerun's time panel and Foxglove's speed menu). */
export class BarPlayback {
  constructor(host, el, name = 'bar', clock = clockFor(host.element)) {
    this.host = host;
    this.el = el;
    this.clock = clock;
    el.innerHTML = `<div class="dv-pb" role="group" aria-label="Playback">
      <div class="dv-pb-ctl">
        <button type="button" class="dv-pb-btn" data-act="start" title="Go to the start (Home)" aria-label="Go to the start">${ICON.start}</button>
        <button type="button" class="dv-pb-btn" data-act="back" title="Back one frame (←)" aria-label="Back one frame">${ICON.back}</button>
        <button type="button" class="dv-pb-btn dv-pb-play" data-act="play" title="Play / pause (Space)" aria-label="Play">${ICON.play}</button>
        <button type="button" class="dv-pb-btn" data-act="fwd" title="Forward one frame (→)" aria-label="Forward one frame">${ICON.fwd}</button>
        <button type="button" class="dv-pb-btn dv-pb-loop" data-act="loop" title="Loop" aria-label="Loop" aria-pressed="false">${ICON.loop}</button>
        <select class="dv-pb-speed" aria-label="Speed" title="Speed"></select>
        <span class="dv-pb-time" aria-live="off"><b class="dv-pb-now">—</b><span class="dv-pb-end"></span></span>
      </div>
      <div class="dv-pb-trackbox">
        <div class="dv-pb-lane" title="Drag to select a range (the loop); double-click to clear"><div class="dv-pb-range" data-range hidden><span class="dv-pb-h" data-h="0"></span><span class="dv-pb-h" data-h="1"></span></div></div>
        <div class="dv-pb-track" role="slider" tabindex="0" aria-label="Time" aria-valuemin="0" aria-valuemax="0" aria-valuenow="0">
          <div class="dv-pb-win" hidden></div>
          <div class="dv-pb-fill"></div>
          <div class="dv-pb-thumb" data-thumb></div>
        </div>
        <div class="dv-pb-ticks" aria-hidden="true"></div>
      </div>
    </div>`;
    this.$ = (s) => el.querySelector(s);
    this.track = this.$('.dv-pb-track');
    this._onTime = () => this._time();
    this._onState = () => this._state();
    this.clock.addEventListener('time', this._onTime);
    this.clock.addEventListener('state', this._onState);
    el.addEventListener('click', (e) => {
      const b = e.target.closest('[data-act]');
      if (!b) return;
      const c = this.clock, act = b.dataset.act;
      if (act === 'play') c.toggle();
      else if (act === 'back') c.step(-1);
      else if (act === 'fwd') c.step(1);
      else if (act === 'start') { c.pause(); c.seek(c.bounds[0]); }
      else if (act === 'loop') c.setLoop(!c.loop);
    });
    this.$('.dv-pb-speed').addEventListener('change', (e) => this.clock.setRate(Number(e.target.value)));
    this._wireTrack();
    this._wireLane();
    this._ro = new ResizeObserver(() => this._ticks());
    this._ro.observe(this.track);
    // live data: the ● LIVE control and the growing span (docs/peps/0012-live-data.md §4)
    this._live = mountLive(el, this.clock, () => this._state());
  }

  destroy() {
    this.clock.removeEventListener('time', this._onTime);
    this.clock.removeEventListener('state', this._onState);
    this._live.destroy();
    this._ro.disconnect();
    this.host.setStatus('');
    this.el.innerHTML = '';
  }

  update(input) {
    const p = input.view.playback || {};
    this.opts = { speeds: Array.isArray(p.speeds) && p.speeds.length ? p.speeds : [0.25, 0.5, 1, 2, 4], range: p.range !== false, readout: p.readout !== false };
    const sel = this.$('.dv-pb-speed');
    const speeds = [...new Set([...this.opts.speeds, this.clock.rate])].sort((a, b) => a - b);
    sel.innerHTML = speeds.map((s) => `<option value="${s}">${esc(String(s))}×</option>`).join('');
    this.$('.dv-pb-lane').hidden = !this.opts.range;
    this.$('.dv-pb-time').hidden = !this.opts.readout;
    this._state();
  }

  // ------------------------------------------------------------------ drawing
  _span() {
    const c = this.clock;
    const a = c.start ?? 0, b = c.end ?? a;
    return [a, b > a ? b : a + 1];
  }

  _frac(t) { const [a, b] = this._span(); return Math.max(0, Math.min(1, (t - a) / (b - a))); }

  _time() {
    const c = this.clock, f = this._frac(c.t);
    // WHY a CSS variable, not a re-render: this runs on every clock tick (60 Hz while playing)
    this.track.style.setProperty('--dv-pb-f', String(f));
    this.track.setAttribute('aria-valuenow', c.t.toFixed(3));
    this.track.setAttribute('aria-valuetext', fmtTime(c.t));
    this.$('.dv-pb-now').textContent = fmtTime(c.t).replace(/ s$/, '');
  }

  _state() {
    const c = this.clock;
    const [a, b] = this._span();
    const play = this.$('.dv-pb-play');
    play.innerHTML = c.playing ? ICON.pause : ICON.play;
    play.setAttribute('aria-label', c.playing ? 'Pause' : 'Play');
    play.classList.toggle('dv-on', c.playing);
    const loop = this.$('.dv-pb-loop');
    loop.setAttribute('aria-pressed', String(c.loop));
    loop.classList.toggle('dv-on', c.loop);
    this.$('.dv-pb-speed').value = String(c.rate);
    this.$('.dv-pb-end').textContent = c.end === null ? '' : ` / ${fmtTime(c.end)}`;
    this.track.setAttribute('aria-valuemin', String(a));
    this.track.setAttribute('aria-valuemax', String(b));
    const r = this.$('[data-range]');
    r.hidden = !c.range;
    if (c.range) { r.style.left = `${this._frac(c.range[0]) * 100}%`; r.style.width = `${(this._frac(c.range[1]) - this._frac(c.range[0])) * 100}%`; }
    const w = this.$('.dv-pb-win');
    w.hidden = !c.window;
    if (c.window) { w.style.left = `${this._frac(c.window[0]) * 100}%`; w.style.width = `${(this._frac(c.window[1]) - this._frac(c.window[0])) * 100}%`; }
    this.el.toggleAttribute('data-empty', c.start === null);
    this._ticks();
    this._time();
  }

  _ticks() {
    const [a, b] = this._span();
    const width = this.track.getBoundingClientRect().width || 600;
    const ticks = this.clock.start === null ? [] : niceTicks(a, b, Math.max(3, Math.floor(width / 70)));
    this.$('.dv-pb-ticks').innerHTML = ticks.map((v) => `<span style="left:${this._frac(v) * 100}%">${esc(tickText(v, b - a))}</span>`).join('');
  }

  // ------------------------------------------------------------------ input
  _tAt(clientX, box = this.track) {
    const r = box.getBoundingClientRect();
    const [a, b] = this._span();
    return a + Math.max(0, Math.min(1, (clientX - r.left) / r.width)) * (b - a);
  }

  _wireTrack() {
    const tr = this.track;
    let dragging = false, was = false;
    tr.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      dragging = true; was = this.clock.playing;
      this.clock.pause();
      tr.setPointerCapture(e.pointerId);
      this.clock.seek(this._tAt(e.clientX));
    });
    tr.addEventListener('pointermove', (e) => { if (dragging) this.clock.seek(this._tAt(e.clientX)); });
    const end = () => { if (!dragging) return; dragging = false; if (was) this.clock.play(); };
    tr.addEventListener('pointerup', end);
    tr.addEventListener('pointercancel', end);
    tr.addEventListener('keydown', (e) => {
      const c = this.clock, k = e.key;
      if (k === 'ArrowLeft' || k === 'ArrowRight') { e.preventDefault(); e.stopPropagation(); if (e.shiftKey) c.seek(c.t + (k === 'ArrowLeft' ? -1 : 1)); else c.step(k === 'ArrowLeft' ? -1 : 1); }
    });
  }

  _wireLane() {
    const lane = this.$('.dv-pb-lane');
    let from = null, handle = null;
    lane.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      const h = e.target.closest('.dv-pb-h');
      const c = this.clock;
      lane.setPointerCapture(e.pointerId);
      if (h && c.range) { handle = Number(h.dataset.h); from = c.range[1 - handle]; } else { handle = null; from = this._tAt(e.clientX, lane); }
    });
    lane.addEventListener('pointermove', (e) => {
      if (from === null) return;
      const t = this._tAt(e.clientX, lane);
      if (Math.abs(t - from) > 1e-3) this.clock.setRange([Math.min(from, t), Math.max(from, t)]);
    });
    const end = () => { from = null; handle = null; };
    lane.addEventListener('pointerup', end);
    lane.addEventListener('pointercancel', end);
    lane.addEventListener('dblclick', () => this.clock.setRange(null));
  }
}

// ---------------------------------------------------------------------- the proposals and the switcher (§4b)

// The built-in controls, in the switcher's order; each goes through the registry like any later one (registry.js)
for (const [name, label, View] of [
  ['bar', 'Bar (default)', BarPlayback],
  ['rerun', 'P1 · Rerun', RerunPlayback],
  ['rerun-streams', 'P1 · Rerun + streams', RerunStreamsPlayback],
  ['youtube', 'P2 · YouTube', YoutubePlayback],
  ['tracks', 'P3 · Tracks (editor)', TracksPlayback],
  ['foxglove', 'P4 · Foxglove', FoxglovePlayback],
  ['range', 'P5 · Range overview', RangePlayback],
]) {
  if (!playbackVariant(name)) registerPlaybackVariant(name, { label, create: (host, el, clock) => new View(host, el, name, clock) });
}
const STORE = 'data-ui/playback-variant/';

export default class PlaybackView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    el.innerHTML = `<div class="dv-pbv"><div class="dv-pbv-slot"></div><p class="dv-pbv-note" role="status" hidden></p><div class="dv-pbv-foot" hidden><label class="dv-pbv-switch" title="Try the playback proposals; your pick is remembered on this device"><span>Playback</span><select aria-label="Playback variant"></select></label></div></div>`;
    this.slot = el.querySelector('.dv-pbv-slot');
    this.select = el.querySelector('.dv-pbv-switch select');
    this.select.addEventListener('change', () => {
      this.remember(this.select.value);
      if (this.input) this.update(this.input);
    });
    this.current = null;
    this.variant = null;
    // WHY a note under every proposal (judge r3 #4): when the clock's driving video is on a tab that is not open, the
    // clock runs on wall time; the bar says so instead of silently drifting from the video the reader expects
    this.note = el.querySelector('.dv-pbv-note');
    this.clock = clockFor(host.element);
    this._note = () => { const t = this.clock.note; this.note.hidden = !t; this.note.textContent = t || ''; };
    this.clock.addEventListener('state', this._note);
    this._note();
  }

  /** Where this card's pick lives: per page and per card. */
  get storeKey() { return `${STORE}${location.pathname}#${this.host.element.id || this.host.element.getAttribute('aria-label') || 'playback'}`; }

  remember(v) {
    // WHY localStorage, try/catch: Zach compares the proposals by switching, never by editing a URL flag
    // (memory feedback_prototype_switch_in_app); a private window keeps the pick for this visit only
    this._picked = v;
    try { localStorage.setItem(this.storeKey, v); } catch { /* private window */ }
  }

  recalled() {
    if (this._picked) return this._picked;
    try { return localStorage.getItem(this.storeKey); } catch { return null; }
  }

  update(input) {
    this.input = input;
    const p = input.view.playback || {};
    const declared = playbackVariant(p.variant) ? p.variant : 'bar';
    const switcher = p.switcher === true;
    const stored = switcher ? this.recalled() : null;
    const want = stored && playbackVariant(stored) ? stored : declared;
    if (switcher) {
      const all = playbackVariants();
      if (this.select.options.length !== all.length) this.select.innerHTML = all.map((v) => `<option value="${esc(v.name)}">${esc(v.label)}</option>`).join('');
    }
    const foot = this.el.querySelector('.dv-pbv-foot');
    foot.hidden = !switcher;
    this.select.value = want;
    if (want !== this.variant) {
      if (this.current) this.current.destroy();
      // a fresh slot for the next control: none of the last one's DOM, variables or attributes
      this.slot.className = 'dv-pbv-slot';
      this.slot.removeAttribute('style');
      this.slot.removeAttribute('data-empty');
      this.slot.innerHTML = '';
      this.variant = want;
      this.el.dataset.variant = want;
      const dashboard = this.host.element.closest('data-dashboard');
      this.current = playbackVariant(want).create(this.host, this.slot, clockFor(this.host.element), { name: want, dashboard });
    }
    this.current.update(input);
  }

  destroy() {
    if (this.current) this.current.destroy();
    this.current = null;
    this.clock.removeEventListener('state', this._note);
    this.el.innerHTML = '';
  }
}
