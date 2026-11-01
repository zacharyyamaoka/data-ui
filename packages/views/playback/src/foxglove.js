/* P4 `foxglove` (docs/peps/0005-dashboard-cards.md §4b): Foxglove's playback bar (prior art in ../README.md).

   A thin scrubber across the top showing the loaded ranges (each time-aware dataset's span, the darker band) and a
   hover marker with its time; under it, the time display (seconds "3.200" or elapsed "00:03.200", switched by its
   chevron), seek back / play-pause / seek forward in the middle, and the speed menu and the loop toggle on the right.
   Seek back/forward step one frame (Foxglove's default arrow step is its smallest increment).
   STOCK PARTS: none. */

import { esc } from '@data-ui/core';
import { Variant, ICON } from './base.js';
import { foxTime } from './model.js';

const FORMAT_KEY = 'data-ui/playback-foxglove-format';

export class FoxglovePlayback extends Variant {
  constructor(host, el, name, clock) {
    super(host, el, 'foxglove', clock);
    let format = 'seconds';
    try { format = localStorage.getItem(FORMAT_KEY) === 'elapsed' ? 'elapsed' : 'seconds'; } catch { /* private window */ }
    this.format = format;
    el.innerHTML = `<div class="dv-fx" data-variant-root>
      <div class="dv-fx-scrub" data-scrub role="slider" tabindex="0" aria-label="Seek" aria-valuemin="0" aria-valuemax="0" aria-valuenow="0">
        <div class="dv-fx-track"><div class="dv-fx-loaded"></div><div class="dv-fx-fill"></div></div>
        <div class="dv-fx-hover" hidden><span></span></div>
        <div class="dv-fx-thumb" data-playhead></div>
      </div>
      <div class="dv-fx-row">
        <div class="dv-fx-left">
          <button type="button" class="dv-fx-time" data-act="format" title="Time format" aria-haspopup="menu" aria-expanded="false"><span class="dv-fx-now">0.000</span><span class="dv-fx-fmt"></span>${ICON.chev}</button>
        </div>
        <div class="dv-fx-mid">
          <button type="button" class="dv-fx-btn" data-act="back" title="Seek backward (←)" aria-label="Seek backward">${ICON.stepBack}</button>
          <button type="button" class="dv-fx-btn dv-fx-play" data-act="play" title="Play / pause (Space)" aria-label="Play">${ICON.play}</button>
          <button type="button" class="dv-fx-btn" data-act="fwd" title="Seek forward (→)" aria-label="Seek forward">${ICON.stepFwd}</button>
        </div>
        <div class="dv-fx-right">
          <button type="button" class="dv-fx-speed" data-act="speed" title="Playback speed" aria-haspopup="menu" aria-expanded="false"><span>1×</span>${ICON.chev}</button>
          <button type="button" class="dv-fx-btn dv-fx-loop" data-act="loop" title="Loop playback" aria-label="Loop" aria-pressed="false">${ICON.repeat}</button>
        </div>
      </div>
    </div>`;
    this.$ = (s) => el.querySelector(s);
    const sc = this.$('.dv-fx-scrub');
    this.scrub(sc);
    this.on(sc, 'pointermove', (e) => {
      const t = this.tAt(e.clientX, sc), h = this.$('.dv-fx-hover');
      h.hidden = false;
      h.style.left = `${this.frac(t) * 100}%`;
      h.firstElementChild.textContent = foxTime(t, this.clock.start, this.format);
    });
    this.on(sc, 'pointerleave', () => { this.$('.dv-fx-hover').hidden = true; });
    this.on(el, 'click', (e) => {
      const b = e.target.closest('[data-act]');
      if (!b || !el.contains(b)) return;
      const c = this.clock, act = b.dataset.act;
      if (act === 'play') c.toggle();
      else if (act === 'back') c.step(-1);
      else if (act === 'fwd') c.step(1);
      else if (act === 'loop') c.setLoop(!c.loop);
      else if (act === 'format' || act === 'speed') {
        if (this._menu && this._menu.button === b) { this.closeMenu(); return; }
        if (act === 'format') this.menu(b, [
          { label: 'Seconds', sub: foxTime(c.t, c.start, 'seconds'), checked: this.format === 'seconds', act: () => this.setFormat('seconds') },
          { label: 'Elapsed', sub: foxTime(c.t, c.start, 'elapsed'), checked: this.format === 'elapsed', act: () => this.setFormat('elapsed') },
        ]);
        else {
          const speeds = [...new Set([...(this.speeds || [0.1, 0.25, 0.5, 0.8, 1, 2, 3, 5]), c.rate])].sort((x, y) => x - y);
          this.menu(b, speeds.map((s) => ({ label: `${s}×`, checked: s === c.rate, act: () => c.setRate(s) })), { align: 'right' });
        }
      }
    });
  }

  setFormat(f) {
    this.format = f;
    try { localStorage.setItem(FORMAT_KEY, f); } catch { /* private window: this visit only */ }
    this.state();
  }

  update(input) {
    super.update(input);
    const p = input.view.playback || {};
    this.speeds = Array.isArray(p.speeds) && p.speeds.length ? p.speeds : null;
    this._loadedKey = null;
    this.state();
  }

  /** The loaded ranges: each time-aware dataset's span and each clip's (all of it is in memory on this page). */
  loaded() {
    const spans = [...this.streams().map((s) => [s.t0, s.t1])];
    spans.sort((x, y) => x[0] - y[0]);
    const out = [];
    for (const s of spans) { const l = out[out.length - 1]; if (l && s[0] <= l[1]) l[1] = Math.max(l[1], s[1]); else out.push([...s]); }
    return out;
  }

  state() {
    const c = this.clock;
    const play = this.$('.dv-fx-play');
    play.innerHTML = c.playing ? ICON.pause : ICON.play;
    play.setAttribute('aria-label', c.playing ? 'Pause' : 'Play');
    const loop = this.$('.dv-fx-loop');
    loop.setAttribute('aria-pressed', String(c.loop));
    loop.classList.toggle('dv-on', c.loop);
    this.$('.dv-fx-speed span').textContent = `${c.rate}×`;
    this.$('.dv-fx-fmt').textContent = this.format === 'seconds' ? 'SEC' : 'ELAPSED';
    const sc = this.$('.dv-fx-scrub'), [a, b] = this.span();
    sc.setAttribute('aria-valuemin', String(a));
    sc.setAttribute('aria-valuemax', String(b));
    const key = `${a}|${b}|${this.input ? this._key(this.data().datasets) : ''}`;
    if (key !== this._loadedKey && this.input) {
      this._loadedKey = key;
      this.$('.dv-fx-loaded').innerHTML = this.loaded().map(([x, y]) => `<i style="left:${this.frac(x) * 100}%;width:${(this.frac(y) - this.frac(x)) * 100}%"></i>`).join('');
      this.$('.dv-fx-loaded').title = `Loaded: ${this.loaded().map(([x, y]) => `${esc(x.toFixed(2))}–${esc(y.toFixed(2))} s`).join(', ')}`;
    }
    this.el.toggleAttribute('data-empty', c.start === null);
    this.time();
  }

  time() {
    const c = this.clock;
    this.el.style.setProperty('--dv-pb-f', String(this.frac(c.t)));
    this.$('.dv-fx-now').textContent = foxTime(c.t, c.start, this.format);
    this.$('.dv-fx-scrub').setAttribute('aria-valuenow', c.t.toFixed(3));
  }
}
