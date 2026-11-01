/* P2 `youtube` (docs/peps/0005-dashboard-cards.md §4b): YouTube's player bar, copied.

   A scrub bar along the top that thickens on hover, the played part in the accent, the buffered part lighter, chapter
   gaps, and a hover tooltip with a real thumbnail (the dashboard's primary video at the hovered t, drawn into a small
   canvas from a hidden <video>; frames cached), the chapter title and the time. Under it: play/pause, next chapter,
   "0:03 / 0:07", the current chapter, and a gear menu with playback speed and loop.

   Chapters: the moves of the main time series' target (the first time series card's series named by the palette's
   first key, else its first series): a chapter starts where the signal starts moving after holding still, so a step
   target's holds and moves become YouTube's chapters ("Move 1", "Move 2" …).
   Buffered: the primary clip's buffered ranges (the dashboard's own <video> of it when it is loaded, else the hidden
   one this card seeks for thumbnails), mapped to the clock by the clip's t0.
   Keys: K play/pause, J/L ∓1 s, ←/→ ∓0.5 s, , and . one frame back/forward.
   STOCK PARTS: none (pointer events, canvas, a hidden <video>). */

import { esc } from '@data-ui/core';
import { Variant, ICON } from './base.js';
import { FrameGrabber } from './frames.js';
import { chaptersOf, chapterAt, ytTime } from './model.js';

const TW = 160, TH = 90;

export class YoutubePlayback extends Variant {
  constructor(host, el, name, clock) {
    super(host, el, 'youtube', clock);
    el.innerHTML = `<div class="dv-yt" data-variant-root>
      <div class="dv-yt-bar" data-scrub role="slider" tabindex="0" aria-label="Seek" aria-valuemin="0" aria-valuemax="0" aria-valuenow="0">
        <div class="dv-yt-chaps"></div>
        <div class="dv-yt-thumb" data-playhead></div>
        <div class="dv-yt-tip" hidden><canvas class="dv-yt-frame" width="${TW}" height="${TH}" aria-hidden="true"></canvas><b class="dv-yt-tip-ch"></b><span class="dv-yt-tip-t"></span></div>
      </div>
      <div class="dv-yt-row">
        <button type="button" class="dv-yt-btn" data-act="play" title="Play (k)" aria-label="Play">${ICON.play}</button>
        <button type="button" class="dv-yt-btn" data-act="next" title="Next chapter" aria-label="Next chapter">${ICON.next}</button>
        <span class="dv-yt-time"><span class="dv-yt-now">0:00</span> / <span class="dv-yt-dur">0:00</span></span>
        <button type="button" class="dv-yt-chap" data-act="chapter" title="Chapters" hidden><span class="dv-yt-dot">·</span><span class="dv-yt-chap-t"></span>${ICON.caret}</button>
        <span class="dv-yt-flex"></span>
        <span class="dv-yt-src" title=""></span>
        <button type="button" class="dv-yt-btn dv-yt-gear" data-act="settings" title="Settings" aria-label="Settings" aria-haspopup="menu" aria-expanded="false">${ICON.gear}</button>
      </div>
    </div>`;
    this.$ = (s) => el.querySelector(s);
    this.bar = this.$('.dv-yt-bar');
    this.chapters = [];
    this.scrub(this.bar);
    this.on(this.bar, 'pointermove', (e) => this.hover(e.clientX));
    this.on(this.bar, 'pointerleave', () => { this.$('.dv-yt-tip').hidden = true; this.bar.classList.remove('dv-hover'); });
    this.on(this.bar, 'pointerenter', () => this.bar.classList.add('dv-hover'));
    this.on(el, 'click', (e) => this.click(e));
    this.ownKeys((e) => this.key(e));
  }

  key(e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return false;
    const c = this.clock, k = e.key;
    if (k === 'k' || k === 'K') c.toggle();
    else if (k === 'j' || k === 'J') c.seek(c.t - 1);
    else if (k === 'l' || k === 'L') c.seek(c.t + 1);
    else if (k === 'ArrowLeft') c.seek(c.t - 0.5);
    else if (k === 'ArrowRight') c.seek(c.t + 0.5);
    else if (k === ',') c.step(-1);
    else if (k === '.') c.step(1);
    else return false;
    return true;
  }

  click(e) {
    const b = e.target.closest('[data-act]');
    if (!b || !this.el.contains(b)) return;
    const c = this.clock, act = b.dataset.act;
    if (act === 'play') c.toggle();
    else if (act === 'next') { const ch = this.chapters.find((x) => x.t0 > c.t + 1e-6); c.seek(ch ? ch.t0 : this.span()[1]); }
    else if (act === 'chapter') {
      if (this._menu && this._menu.button === b) { this.closeMenu(); return; }
      const now = chapterAt(this.chapters, c.t);
      this.menu(b, this.chapters.map((ch) => ({ label: esc(ch.title), sub: ytTime(ch.t0), checked: ch === now, act: () => c.seek(ch.t0) })));
    } else if (act === 'settings') {
      if (this._menu && this._menu.button === b) { this.closeMenu(); return; }
      this.settings(b);
    }
  }

  /** YouTube's gear: a list of settings with their value; Playback speed opens its own list. */
  settings(b, page = 'main') {
    const c = this.clock;
    if (page === 'speed') {
      const speeds = [...new Set([...(this.speeds || [0.25, 0.5, 1, 2]), c.rate])].sort((x, y) => x - y);
      this.menu(b, [{ label: '‹ Playback speed', act: () => this.settings(b) }, '-',
        ...speeds.map((s) => ({ label: s === 1 ? 'Normal' : `${s}`, checked: s === c.rate, act: () => c.setRate(s) }))], { align: 'right' });
      return;
    }
    this.menu(b, [
      { label: 'Loop', sub: c.loop ? 'On' : 'Off', act: () => c.setLoop(!c.loop) },
      { label: 'Playback speed', sub: `${c.rate === 1 ? 'Normal' : c.rate} ›`, act: () => this.settings(b, 'speed') },
    ], { align: 'right' });
  }

  update(input) {
    super.update(input);
    const p = input.view.playback || {};
    this.speeds = Array.isArray(p.speeds) && p.speeds.length ? p.speeds : null;
    const key = this._key(this.data().datasets);
    if (key !== this._dataKey) {
      this._dataKey = key;
      const clip = this.clips()[0] || null;
      this.clip = clip;
      this.grabber = clip ? FrameGrabber.for(clip.src, clip.fps) : null;
      const src = this.$('.dv-yt-src');
      src.textContent = clip ? `${clip.label}${clip.basis && clip.basis !== 'real-camera' ? ` · ${clip.basis.replace('-', ' ')}` : ''}` : 'no video: thumbnails off';
      src.title = clip ? `Thumbnails: ${clip.src}` : 'This dashboard has no video, so the hover shows only the time';
      if (this.grabber && this._bufFor !== this.grabber) {
        this._bufFor = this.grabber;
        const v = this.grabber.video;
        this.on(v, 'progress', () => this.buffered());
        this.on(v, 'loadeddata', () => this.buffered());
      }
    }
    this.state();
  }

  /** The chapters: the target's moves (see the header). Redrawn when the span or the data changes. */
  computeChapters() {
    const [a, b] = this.span();
    const tracks = this.seriesTracks(2000);
    const main = tracks[0];
    if (!main) { this.chapters = []; return; }
    const pal = (this.input && this.input.view.style && this.input.view.style.palette) || {};
    const first = Object.keys(pal)[0];
    const line = main.lines.find((l) => l.name === first) || main.lines[0];
    this.chapters = chaptersOf(line.points, a, b, { eps: 1e-6, hold: 0.2 });
    this.chapterSource = `${main.name} · ${line.name}`;
  }

  state() {
    const c = this.clock;
    const play = this.$('[data-act="play"]');
    play.innerHTML = c.playing ? ICON.pause : ICON.play;
    play.setAttribute('aria-label', c.playing ? 'Pause' : 'Play');
    play.title = c.playing ? 'Pause (k)' : 'Play (k)';
    const [a, b] = this.span();
    const key = `${a}|${b}|${this._dataKey}`;
    if (key !== this._chapKey) {
      this._chapKey = key;
      this.computeChapters();
      // chapter segments, each with a played fill driven by the one CSS variable (YouTube's segmented bar)
      const chs = this.chapters.length ? this.chapters : [{ t0: a, t1: b, title: '' }];
      this.$('.dv-yt-chaps').innerHTML = chs.map((ch) => {
        const l = this.frac(ch.t0), r = this.frac(ch.t1);
        return `<div class="dv-yt-seg" style="left:${l * 100}%;width:${(r - l) * 100}%;--l:${l};--w:${r - l || 1}" title="${esc(ch.title)}"><div class="dv-yt-buf"></div><div class="dv-yt-play"></div></div>`;
      }).join('');
      this.$('.dv-yt-chap').hidden = !this.chapters.length;
      this.$('.dv-yt-chap').title = this.chapters.length ? `Chapters: the moves of ${this.chapterSource}` : '';
      this.bar.setAttribute('aria-valuemin', String(a));
      this.bar.setAttribute('aria-valuemax', String(b));
      this.$('.dv-yt-dur').textContent = ytTime(c.end ?? b);
    }
    this.el.toggleAttribute('data-empty', c.start === null);
    this.buffered();
    this.time();
  }

  time() {
    const c = this.clock, f = this.frac(c.t);
    this.el.style.setProperty('--dv-pb-f', String(f));
    this.bar.setAttribute('aria-valuenow', c.t.toFixed(3));
    this.bar.setAttribute('aria-valuetext', ytTime(c.t));
    this.$('.dv-yt-now').textContent = ytTime(c.t);
    const ch = chapterAt(this.chapters, c.t);
    if (ch !== this._ch) { this._ch = ch; this.$('.dv-yt-chap-t').textContent = ch ? ch.title : ''; }
  }

  /** The primary clip's buffered ranges → the bar's lighter fill (as one CSS variable per segment: the buffered end). */
  buffered() {
    if (!this.clip) return;
    const own = this.dashEl && [...this.dashEl.querySelectorAll('video[data-t0]')].find((v) => v.dataset.src === this.clip.src && v.buffered.length);
    const v = own || (this.grabber && this.grabber.video);
    if (!v) return;
    let end = this.clip.t0;
    for (let i = 0; i < v.buffered.length; i++) if (v.buffered.start(i) <= this.clock.t - this.clip.t0 + 0.5) end = Math.max(end, this.clip.t0 + v.buffered.end(i));
    this.el.style.setProperty('--dv-yt-buf', String(this.frac(end)));
  }

  hover(clientX) {
    const t = this.tAt(clientX, this.bar);
    const r = this.bar.getBoundingClientRect(), tip = this.$('.dv-yt-tip');
    tip.hidden = false;
    const ch = chapterAt(this.chapters, t);
    this.$('.dv-yt-tip-ch').textContent = ch ? ch.title : '';
    this.$('.dv-yt-tip-t').textContent = ytTime(t);
    tip.dataset.t = t.toFixed(3);
    const w = tip.getBoundingClientRect().width || TW;
    const x = Math.max(w / 2, Math.min(r.width - w / 2, clientX - r.left));
    tip.style.transform = `translateX(${x - w / 2}px)`;
    this.thumb(t);
  }

  /** Draw the clip's frame at clock time t into the tooltip's canvas (latest hover wins). */
  thumb(t, tries = 8) {
    const canvas = this.$('.dv-yt-frame');
    const g = this.grabber, clip = this.clip;
    canvas.classList.toggle('dv-none', !g);
    if (!g) return;
    const want = (this._want = t);
    const local = t - clip.t0;
    if (local < 0 || (g.duration && local > g.duration)) { canvas.getContext('2d').clearRect(0, 0, TW, TH); canvas.dataset.t = ''; return; }
    g.frame(local, TW, TH).then((src) => {
      if (this._want !== want) return;
      if (!src) { if (tries > 0) setTimeout(() => { if (this._want === want) this.thumb(t, tries - 1); }, 250); return; }
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, TW, TH);
      ctx.drawImage(src, 0, 0, TW, TH);
      canvas.dataset.t = t.toFixed(3);
      canvas.dataset.frame = src.dataset.frame;
    });
  }
}
