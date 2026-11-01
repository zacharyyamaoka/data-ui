/* One <video> on the dashboard's clock (docs/peps/0005-dashboard-cards.md §4): its lazy source, following, and — when
   it is the clock's designated driver (clock.setDriver: clock.primary, else the first `video.primary` card) — driving
   t from its own frames while the clock plays.

   Driving (judge round 1, reports/media/audits/2026-10-27-dashboards-judge-r1.md):
   - each requestVideoFrameCallback is armed with the clock's seek generation (clock.gen) and passes it to
     clock.drive, which ignores a stale one; a seek or a loop wrap (source 'loop', judge r2 #1) cancels the pending
     callback, and the next is armed on `seeked` (a pre-seek frame cannot undo a seek, #2);
   - buffering or seeking keeps the clock's ownership (the clock holds t); `ended`, `error`, leaving the clip and
     destroy() hand t back with clock.release (#1); past the clock's STALL the clock falls back to wall time and this
     clip follows it (jumps to t) until its frames pass t again;
   - only the designated id drives; every other clip on the clock follows with core's followVideo (#3). */

import { isNum, followVideo } from '@data-ui/core';

export class Clip {
  constructor(clock) {
    this.clock = clock;
    this.id = null;
    this.src = null;
    this.t0 = 0;
    this.near = false;
    this._vfc = 0;
    this._failed = false;
    const v = this.video = document.createElement('video');
    // WHY muted + playsinline: autoplay policies let only muted inline video play from a script; the clock starts it
    v.muted = true;
    v.defaultMuted = true;
    v.playsInline = true;
    v.setAttribute('muted', '');
    v.setAttribute('playsinline', '');
    v.preload = 'none';
    v.disablePictureInPicture = true;
    v.dataset.t0 = '0';
    this._sync = () => this.sync();
    this._meta = () => {
      if (Number.isFinite(v.duration)) this.clock.extent(this.t0, this.t0 + v.duration);
      if (!this._seekable()) { this._local(); return; }
      this.sync();
    };
    // a seek the clock asked for has landed: the next presented frame drives again
    this._seeked = () => { if (this.primary && this.clock.playing && !v.paused) { this._disarm(); this._arm(); } };
    this._ended = () => { this._disarm(); this.clock.release(this.id); };
    this._error = () => { this._failed = true; this._disarm(); this.clock.release(this.id); };
    v.addEventListener('loadedmetadata', this._meta);
    v.addEventListener('loadeddata', this._sync);
    v.addEventListener('seeked', this._seeked);
    v.addEventListener('ended', this._ended);
    v.addEventListener('error', this._error);
  }

  /** This clip is the clock's designated driver. */
  get primary() { return this.id !== null && this.id !== undefined && this.clock.driverId === this.id; }

  /** The row's clip: src and poster already resolved to URLs; t0 the clock time at frame 0; id its driver key. */
  set({ src, poster, t0, id }) {
    const v = this.video;
    if (id !== this.id) { this._disarm(); this.clock.release(this.id); }
    this.id = id;
    this.t0 = isNum(t0) ? t0 : 0;
    v.dataset.t0 = String(this.t0);
    if (poster) { if (v.getAttribute('poster') !== poster) v.poster = poster; } else v.removeAttribute('poster');
    if (src !== this.src) {
      this.src = src;
      this._failed = false;
      this._unblob();
      if (this.near) this._load();
      else if (v.hasAttribute('src')) { v.removeAttribute('src'); delete v.dataset.src; v.preload = 'none'; v.load(); }
    }
  }

  /** The card is near the viewport: fetch the clip now. */
  show() { this.near = true; this._load(); }

  _load() {
    const v = this.video;
    if (!this.src) { if (v.hasAttribute('src')) { v.removeAttribute('src'); delete v.dataset.src; v.load(); } return; }
    v.preload = 'auto';
    v.dataset.src = this.src;   // the clip's URL, also when it plays from a local copy (below)
    if (!this._blob && v.getAttribute('src') !== this.src) v.src = this.src;
  }

  /** Can the clock put this video anywhere in it? A server that ignores HTTP Range requests (python -m http.server,
      some static hosts) gives a clip Chrome cannot seek: `seekable` stays [0, 0] and every seek lands on 0. */
  _seekable() {
    const v = this.video, s = v.seekable;
    return !Number.isFinite(v.duration) || (s.length > 0 && s.end(s.length - 1) >= v.duration - 0.05);
  }

  /** WHY a local copy: without Range support the clip cannot follow the clock at all, which is the card's whole job.
      Fetched once into a blob: URL (seekable in memory); the same file, same origin, only when the server forced it. */
  _local() {
    if (this._blob || this._fetching || !this.src) return;
    const src = this.src;
    this._fetching = fetch(src).then((r) => (r.ok ? r.blob() : null)).then((blob) => {
      this._fetching = null;
      if (!blob || src !== this.src || this._dead) return;
      this._blob = URL.createObjectURL(blob);
      this.video.src = this._blob;
    }).catch(() => { this._fetching = null; });
  }

  _unblob() {
    if (this._blob) { URL.revokeObjectURL(this._blob); this._blob = null; }
  }

  /** Bring the video to the clock's state (after a load, a state change or a set()). */
  sync() {
    if (this.primary && this.clock.playing) this._lead('sync');
    else { this._stopLead(); followVideo(this.video, this.clock, this.t0); }
  }

  /** The clock's t changed (detail.source says who changed it). */
  onTime(source) {
    if (this.primary && this.clock.playing) this._lead(source);
    else followVideo(this.video, this.clock, this.t0);
  }

  /** Playing, rate, loop, span or driver changed. */
  onState() { this.sync(); }

  /** Designated, clock playing: this video sets the pace. It ignores its own frames' t and the clock's idle ticks
      while it plays; any other move of t (a seek, a loop, a step) puts it on the new instant and starts a new
      generation of frame callbacks. */
  _lead(source) {
    const v = this.video, c = this.clock;
    if (source === `video:${this.id}` || v.readyState < 1) return;
    const want = c.t - this.t0;
    if (this._failed || !(want >= 0 && want < v.duration)) { this._stopLead(); if (this._failed) followVideo(v, c, this.t0); return; }   // outside the clip: the clock runs t itself
    const tick = source === 'play' || source === 'sync';
    if (c.fallback && tick) {
      // stalled past the clock's STALL: wall time runs t; jump to it once a seek is not already landing
      // WHY disarm when the follow jumps: a callback armed before the jump reports a pre-jump frame, which would end
      // the fallback and hold t for another STALL while the video was already on its way (judge r2 #1, sibling path)
      if (!v.seeking) { followVideo(v, c, this.t0); if (v.seeking) this._disarm(); }
      if (!v.seeking) this._arm();
      return;
    }
    v.playbackRate = c.rate;
    let seek = false;
    if (v.paused) {
      if (Math.abs(v.currentTime - want) > 1e-3) { v.currentTime = want; seek = true; }
      v.play().catch(() => {});
    } else if (!tick && Math.abs(v.currentTime - want) > 1e-3) { v.currentTime = want; seek = true; }
    // WHY disarm on a move: a callback armed before the seek carries the old generation (the clock ignores it) and
    // keeps the loop on the old position; `seeked` arms the next one (judge r1 #2)
    if (!tick) this._disarm();
    if (!seek && !v.seeking) this._arm();
  }

  /** Ask for the next presented frame, tagged with the clock's current seek generation. */
  _arm() {
    const v = this.video;
    if (this._vfc || typeof v.requestVideoFrameCallback !== 'function') return;
    const gen = this.clock.gen;
    this._vfc = v.requestVideoFrameCallback((now, meta) => this._frame(meta, gen));
  }

  _disarm() {
    if (this._vfc) { this.video.cancelVideoFrameCallback(this._vfc); this._vfc = 0; }
  }

  _frame(meta, gen) {
    this._vfc = 0;
    const v = this.video, c = this.clock;
    if (!this.primary || !c.playing || v.paused) return;
    if (gen !== c.gen) { if (!v.seeking) this._arm(); return; }   // armed before the latest seek: never drives
    c.drive(meta.mediaTime + this.t0, this.id, gen);
    this._arm();
  }

  _stopLead() {
    const v = this.video;
    this._disarm();
    this.clock.release(this.id);
    if (this.primary && !v.paused) v.pause();
  }

  destroy() {
    const v = this.video;
    this._stopLead();
    for (const [type, f] of [['loadedmetadata', this._meta], ['loadeddata', this._sync], ['seeked', this._seeked], ['ended', this._ended], ['error', this._error]]) v.removeEventListener(type, f);
    v.pause();
    this._dead = true;
    // release the decoder and the network request now, not when the element is collected
    if (v.hasAttribute('src')) { v.removeAttribute('src'); v.load(); }
    this._unblob();
  }
}
