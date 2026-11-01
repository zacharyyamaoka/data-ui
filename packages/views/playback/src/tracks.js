/* P3 `tracks` (docs/peps/0005-dashboard-cards.md §4b): a video editor's multi-track timeline (Premiere Pro,
   DaVinci Resolve's Edit page, CapCut; prior art in ../README.md).

   A transport row (go to start, back a frame, play/pause, forward a frame, the timecode "00:00:03:06" at the clock's
   fps, in/out of the work area), a work-area lane over the ruler (drag to set the range: the clock's loop
   selection; drag its handles; double-click clears), the ruler with timecode ticks, then one track per clip with a
   filmstrip of its real frames and one track per time series card with its sparkline, and the playhead (a line with
   a head) across every track. Track headers on the left are a resizable side panel (Zach's rule).
   Click or drag on the ruler or any track seeks.
   STOCK PARTS: none (divs, SVG paths, canvas filmstrip from frames.js). */

import { esc, makeResizable } from '@data-ui/core';
import { Variant, ICON } from './base.js';
import { FrameGrabber } from './frames.js';
import { niceTicks, sparkPath, timecode } from './model.js';

const TRACK_H = 46;

export class TracksPlayback extends Variant {
  constructor(host, el, name, clock) {
    super(host, el, 'tracks', clock);
    el.innerHTML = `<div class="dv-tk" data-variant-root>
      <div class="dv-tk-bar" role="toolbar" aria-label="Playback">
        <button type="button" class="dv-tk-btn" data-act="start" title="Go to the start (Home)" aria-label="Go to the start">${ICON.stepBack}</button>
        <button type="button" class="dv-tk-btn" data-act="back" title="Back one frame (←)" aria-label="Back one frame">${ICON.back5}</button>
        <button type="button" class="dv-tk-btn dv-tk-play" data-act="play" title="Play / pause (Space)" aria-label="Play">${ICON.play}</button>
        <button type="button" class="dv-tk-btn" data-act="fwd" title="Forward one frame (→)" aria-label="Forward one frame">${ICON.fwd5}</button>
        <button type="button" class="dv-tk-btn" data-act="end" title="Go to the end (End)" aria-label="Go to the end">${ICON.stepFwd}</button>
        <span class="dv-tk-tc" title="Timecode (hours:minutes:seconds:frames)">00:00:00:00</span>
        <span class="dv-tk-flex"></span>
        <span class="dv-tk-io" title="The work area (the loop selection): drag over the ruler to set it"></span>
        <button type="button" class="dv-tk-btn dv-tk-loop" data-act="loop" title="Loop playback" aria-label="Loop" aria-pressed="false">${ICON.repeat}</button>
      </div>
      <div class="dv-tk-main">
        <div class="dv-tk-heads">
          <div class="dv-tk-corner"></div>
          <div class="dv-tk-hlist"></div>
        </div>
        <div class="dv-tk-time">
          <div class="dv-tk-work" title="Drag to set the work area (the loop selection) · double-click to clear"><div class="dv-tk-wa" data-range hidden><span class="dv-tk-h" data-h="0"></span><span class="dv-tk-h" data-h="1"></span></div></div>
          <div class="dv-tk-ruler" data-scrub title="Click or drag to seek"><div class="dv-tk-ticks"></div></div>
          <div class="dv-tk-tracks"></div>
          <div class="dv-tk-ph" data-playhead aria-hidden="true"><span></span></div>
        </div>
      </div>
    </div>`;
    this.$ = (s) => el.querySelector(s);
    this.on(el, 'click', (e) => {
      const b = e.target.closest('[data-act]');
      if (!b) return;
      const c = this.clock, act = b.dataset.act;
      if (act === 'play') c.toggle();
      else if (act === 'back') c.step(-1);
      else if (act === 'fwd') c.step(1);
      else if (act === 'start') { c.pause(); c.seek(c.bounds[0]); }
      else if (act === 'end') { c.pause(); c.seek(c.bounds[1]); }
      else if (act === 'loop') c.setLoop(!c.loop);
    });
    this.scrub(this.$('.dv-tk-ruler'));
    this.scrub(this.$('.dv-tk-tracks'));
    this.wireWork();
    const heads = this.$('.dv-tk-heads');
    heads.dataset.resizable = 'right';
    requestAnimationFrame(() => {
      if (!heads.isConnected) return;
      this._resize = makeResizable(heads, { edge: 'right', min: 96, max: 320, keep: 160, key: `playback-tracks:${host.element.id || 'x'}`, label: 'the track headers' });
    });
    this._off.push(() => { if (this._resize) this._resize.destroy(); });
    this._ro = new ResizeObserver(() => this.layout());
    this._ro.observe(this.$('.dv-tk-time'));
  }

  wireWork() {
    const lane = this.$('.dv-tk-work');
    let from = null;
    this.on(lane, 'pointerdown', (e) => {
      if (e.button !== 0) return;
      const h = e.target.closest('.dv-tk-h'), c = this.clock;
      try { lane.setPointerCapture(e.pointerId); } catch { /* synthetic pointer */ }
      from = h && c.range ? c.range[1 - Number(h.dataset.h)] : this.tAt(e.clientX, lane);
    });
    this.on(lane, 'pointermove', (e) => {
      if (from === null) return;
      const t = this.tAt(e.clientX, lane);
      if (Math.abs(t - from) > 1e-3) this.clock.setRange([Math.min(from, t), Math.max(from, t)]);
    });
    const end = () => { from = null; };
    this.on(lane, 'pointerup', end);
    this.on(lane, 'pointercancel', end);
    this.on(lane, 'dblclick', () => this.clock.setRange(null));
  }

  update(input) {
    super.update(input);
    const key = this._key(this.data().datasets);
    if (key !== this._dataKey) {
      this._dataKey = key;
      this.clipList = this.clips();
      this.series = this.seriesTracks(300);
      this.draw();
    }
    this.state();
  }

  /** Track headers and lanes: on data only. Filmstrips and sparklines are placed by layout() on resize. */
  draw() {
    const clips = this.clipList || [], series = this.series || [];
    const heads = [
      ...clips.map((c, i) => `<div class="dv-tk-head" data-kind="video" title="${esc(c.src)}"><span class="dv-tk-tag">V${i + 1}</span>${ICON.film}<span class="dv-tk-name">${esc(c.label)}</span>${c.basis && c.basis !== 'real-camera' ? `<span class="dv-tk-basis">${esc(c.basis.replace('-', ' '))}</span>` : ''}</div>`),
      ...series.map((s, i) => `<div class="dv-tk-head" data-kind="series"><span class="dv-tk-tag">D${i + 1}</span>${ICON.wave}<span class="dv-tk-name">${esc(s.name)}</span></div>`),
    ];
    this.$('.dv-tk-hlist').innerHTML = heads.join('') || '<p class="dv-tk-none">No clips or time series on this dashboard</p>';
    this.$('.dv-tk-tracks').innerHTML = [
      ...clips.map((c, i) => `<div class="dv-tk-track dv-tk-v" data-track="v${i}"><div class="dv-tk-clip" data-clip="${i}"><div class="dv-tk-strip"></div><span class="dv-tk-clipname">${esc(c.label)}</span></div></div>`),
      ...series.map((s, i) => `<div class="dv-tk-track dv-tk-d" data-track="d${i}"><div class="dv-tk-clip"><svg class="dv-tk-spark" viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true"></svg><span class="dv-tk-clipname">${esc(s.name)}</span></div></div>`),
    ].join('');
    this._w = null;
    this.layout();
  }

  layout() {
    const time = this.$('.dv-tk-time'), tracks = this.$('.dv-tk-tracks');
    if (!time) return;
    const w = Math.round(tracks.getBoundingClientRect().width);
    const [a, b] = this.span();
    const key = `${w}|${a}|${b}`;
    if (!w || key === this._w) return;
    this._w = key;
    // ruler ticks in timecode, one about every 90 px
    const ticks = niceTicks(a, b, Math.max(2, Math.floor(w / 90)));
    this.$('.dv-tk-ticks').innerHTML = ticks.map((v) => `<span style="left:${this.frac(v) * 100}%"><i></i>${esc(timecode(v, this.clock.fps).replace(/^00:/, ''))}</span>`).join('');
    // clips: placed at [t0, t0 + duration]; their filmstrip is real frames, one per thumbnail width
    (this.clipList || []).forEach((c, i) => {
      const box = this.$(`[data-clip="${i}"]`);
      const g = FrameGrabber.for(c.src, c.fps);
      const place = () => {
        const dur = c.duration ?? g.duration ?? (b - c.t0);
        const l = this.frac(c.t0), r = this.frac(c.t0 + dur);
        box.style.left = `${l * 100}%`; box.style.width = `${(r - l) * 100}%`;
        const px = (r - l) * w, aspect = c.width && c.height ? c.width / c.height : 16 / 9;
        const th = TRACK_H - 2, tw = Math.max(24, Math.round(th * aspect));
        const n = Math.max(1, Math.ceil(px / tw));
        const strip = box.querySelector('.dv-tk-strip');
        strip.innerHTML = Array.from({ length: n }, (_, k) => `<canvas width="${tw * 2}" height="${th * 2}" style="width:${tw}px" data-k="${k}"></canvas>`).join('');
        const job = (box._job = {});
        [...strip.children].forEach((cv, k) => {
          const local = Math.min(dur, ((k * tw) / px) * dur);   // each thumbnail shows the frame at its left edge
          const draw = (tries) => g.frame(local, tw * 2, th * 2).then((src) => {
            if (box._job !== job || !cv.isConnected) return;
            if (!src) { if (tries > 0) setTimeout(() => draw(tries - 1), 250); return; }
            cv.getContext('2d').drawImage(src, 0, 0, cv.width, cv.height);
            cv.dataset.t = (c.t0 + local).toFixed(3);
            cv.dataset.frame = src.dataset.frame;
          });
          draw(8);
        });
      };
      place();
    });
    // series: one sparkline per line, scaled to the track's own min / max
    (this.series || []).forEach((s, i) => {
      const svg = this.$(`[data-track="d${i}"] svg`);
      let lo = Infinity, hi = -Infinity;
      for (const l of s.lines) for (const [, v] of l.points) if (v !== null) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
      const pad = (hi - lo) * 0.1 || 1;
      svg.innerHTML = s.lines.map((l) => `<path d="${sparkPath(l.points, a, b, lo - pad, hi + pad)}" stroke="${esc(l.color)}" fill="none" stroke-width="1.5" vector-effect="non-scaling-stroke" stroke-linejoin="round"><title>${esc(l.name)}</title></path>`).join('');
    });
  }

  state() {
    const c = this.clock;
    const play = this.$('.dv-tk-play');
    play.innerHTML = c.playing ? ICON.pause : ICON.play;
    play.setAttribute('aria-label', c.playing ? 'Pause' : 'Play');
    play.classList.toggle('dv-on', c.playing);
    const loop = this.$('.dv-tk-loop');
    loop.setAttribute('aria-pressed', String(c.loop));
    loop.classList.toggle('dv-on', c.loop);
    const r = this.$('[data-range]');
    r.hidden = !c.range;
    if (c.range) { r.style.left = `${this.frac(c.range[0]) * 100}%`; r.style.width = `${(this.frac(c.range[1]) - this.frac(c.range[0])) * 100}%`; }
    this.$('.dv-tk-io').textContent = c.range ? `In ${timecode(c.range[0], c.fps)} · Out ${timecode(c.range[1], c.fps)}` : '';
    this.el.toggleAttribute('data-empty', c.start === null);
    this.layout();
    this.time();
  }

  time() {
    const c = this.clock;
    this.el.style.setProperty('--dv-pb-f', String(this.frac(c.t)));
    this.$('.dv-tk-tc').textContent = timecode(c.t, c.fps);
  }
}
