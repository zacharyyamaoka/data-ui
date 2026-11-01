/* LiveClock: the one clock (PEP 0005, ../clock.js) with Rerun's second state (docs/peps/0012-live-data.md §4).

   Zach, 2026-10-26: "you kinda do streaming but at any moment you can just kinda like 'rewind' and just go back in
   time". Copied from Rerun's TimeControl (re_viewer_context/src/time_control/mod.rs): `following` pins t to the newest
   data; any scrub, step, seek or loop leaves it; one control goes back (goLive: "● LIVE", End, Ctrl/Cmd+Shift+→); Space
   pauses and never jumps live (Rerun #12722); zooming a plot keeps following (Rerun 0.40). Decided 2026-10-27: a replay
   that catches up with the newest data rejoins following (Rerun stops at the end).

   WHY a subclass, not an edit of clock.js: lanes dc-pb and dc-plot edit clock.js too; this file adds the live state
   on top of it, and with no live dataset bound a LiveClock is exactly a Clock (every override falls through).

   The span: `start` / `end` are what the playback bar and the cards draw. They follow the data while the clock plays
   (following or replaying) and hold still while it is paused, so the time cursor and the track do not slide under the
   reader while rows keep arriving. The data's own span is liveStart / liveEnd; lag = liveEnd − t. */

import { Clock } from '../clock.js';
import { markClock } from './frame.js';

// worst first: what the connection line shows for several sources
const RANK = { reconnecting: 7, stale: 6, paused: 5, connecting: 4, closed: 3, live: 2, recorded: 1 };

export function isLiveClock(c) { return c instanceof LiveClock; }

export class LiveClock extends Clock {
  constructor(opts = {}) {
    super(opts);
    this._sets = new Set();
    this.following = false;
    this.liveStart = null;
    this.liveEnd = null;
    this._userPaused = false;     // a reader left following: binding another dataset does not pull them back
    this._pausedFromLive = false; // pause() while following, waiting to see if a scrub follows
    this._scrubFromLive = false;  // a scrub that began while following: the card's "resume after drag" is swallowed
    this._onChange = () => markClock(this);
    this._onStatus = () => this._emit('live', this._detail());
  }

  /** A live (not recorded) dataset is bound. */
  get live() { for (const d of this._sets) if (!d.recorded) return true; return false; }
  get datasets() { return [...this._sets]; }
  get lag() { return this.liveEnd === null || !Number.isFinite(this.t) ? 0 : Math.max(0, this.liveEnd - this.t); }

  /** Follow this dataset's span (the union of every bound one). A live one starts the clock following. */
  bind(ds) {
    if (!ds || this._sets.has(ds)) return;
    this._sets.add(ds);
    if (ds._clocks) ds._clocks.add(this);
    ds.addEventListener('change', this._onChange);
    ds.addEventListener('status', this._onStatus);
    // WHY declared: the bound data's span is the truth; a card's extent() must not widen it
    this._declared = true;
    if (!ds.recorded && !this._userPaused && !this.following) {
      this.following = true;
      this.playing = true;
      this._emit('state');
    }
    markClock(this);
  }

  unbind(ds) {
    if (!this._sets.delete(ds)) return;
    if (ds._clocks) ds._clocks.delete(this);
    ds.removeEventListener('change', this._onChange);
    ds.removeEventListener('status', this._onStatus);
    if (!this.live && this.following) { this.following = false; this.playing = false; this._emit('state'); }
    markClock(this);
  }

  /** The connection of every bound source, worst first: {state, detail, sources, lastData}. */
  status() {
    let worst = null, lastData = 0;
    for (const d of this._sets) {
      const s = d.status;
      lastData = Math.max(lastData, s.lastData || 0);
      if (!worst || (RANK[s.state] || 0) > (RANK[worst.state] || 0)) worst = s;
    }
    return { state: worst ? worst.state : 'idle', detail: worst ? worst.detail : '', tries: worst ? worst.tries : 0, sources: this._sets.size, lastData };
  }

  /** Back to the newest data, following. One jump: the gap is not replayed. */
  goLive() {
    this._pausedFromLive = this._scrubFromLive = false;
    this._userPaused = false;
    if (!this.live) return;
    cancelAnimationFrame(this._raf);
    this.driver = null;
    const changed = !this.following || !this.playing;
    this.following = true;
    this.playing = true;
    this.start = this.liveStart;
    this.end = this.liveEnd;
    if (this.liveEnd !== null && this.t !== this.liveEnd) {
      this.t = this.liveEnd;
      this._emit('time', { t: this.t, source: 'live' });
    }
    // WHY (merged with §25's Clock, 2026-10-28): t is placed from the asked instant on every range, span or link
    // change; following, the asked instant is the newest data, not a stale seek or home()
    this._want = this.t;
    if (changed) this._emit('state');
    this._emit('live', this._detail());
  }

  // ---------------------------------------------------------------- the frame loop (live/frame.js, phase 2)

  _sync() {
    let s = null, e = null;
    for (const d of this._sets) {
      if (d.start !== null && d.start !== undefined) s = s === null ? d.start : Math.min(s, d.start);
      if (d.end !== null && d.end !== undefined) e = e === null ? d.end : Math.max(e, d.end);
    }
    const grew = s !== this.liveStart || e !== this.liveEnd;
    this.liveStart = s;
    this.liveEnd = e;
    if (s === null || e === null) return;
    // the drawn span follows the data while the clock plays, holds while it is paused (never before it has one)
    if (this.playing || this.start === null || this.end === null || !this.live) { this.start = s; this.end = e; }
    if (this.following && this.live) {
      this._want = e;   // the asked instant follows live (see goLive)
      if (this.t !== e) {
        this.t = e;
        this._emit('time', { t: e, source: 'live' });
      }
    }
    if (grew) this._emit('live', this._detail());
  }

  _detail() { return { following: this.following, lag: this.lag, start: this.liveStart, end: this.liveEnd, status: this.status() }; }

  /** A reader's action left following: paused at t (following counted as playing). */
  _leave() {
    if (!this.following) return;
    this.following = false;
    this._userPaused = true;
    if (this.playing) { this.playing = false; cancelAnimationFrame(this._raf); this._emit('state'); }
    this._emit('live', this._detail());
  }

  // ---------------------------------------------------------------- the overrides (each falls through when not live)

  extent(t0, t1) { if (!this._sets.size) super.extent(t0, t1); }

  seek(t, opts = {}) {
    const source = opts.source || 'user';
    if (this.live && source !== 'live' && source !== 'play' && !String(source).startsWith('video:')) {
      if (this._pausedFromLive && source === 'user') this._scrubFromLive = true;
      this._leave();
    }
    return super.seek(t, opts);
  }

  pause() {
    if (this.live && this.following) {
      this._pausedFromLive = true;
      this.following = false;
      this._userPaused = true;
      this._emit('live', this._detail());
    } else this._pausedFromLive = false;
    super.pause();
  }

  play() {
    if (!this.live) return super.play();
    // WHY: a scrub that began while following ends paused at the scrubbed t (CONTRACT §26); the playback cards
    // resume play after a drag when the clock was playing, and following counts as playing
    if (this._scrubFromLive) { this._scrubFromLive = this._pausedFromLive = false; return; }
    this._pausedFromLive = false;
    if (this.following) return;
    // at the newest data: follow (decided 2026-10-27), never start over from the oldest data
    if (this.liveEnd !== null && this.t >= this.liveEnd - 1e-6 && !this.range) return this.goLive();
    // a replay from t: the span takes up the data again, so t can run to the end
    this.start = this.liveStart;
    this.end = this.liveEnd;
    super.play();
  }

  toggle() {
    this._pausedFromLive = this._scrubFromLive = false;
    if (!this.live) return super.toggle();
    // Space while following: pause at t (never a jump); while paused: replay from t
    if (this.following) { this.following = false; this._userPaused = true; super.pause(); this._emit('live', this._detail()); return; }
    if (this.playing) { super.pause(); return; }
    this.play();
  }

  setRange(r) {
    if (this.live && r) this._leave();
    super.setRange(r);
  }

  /** §25's restore(link): a link on load or on Back / Forward (clockNavigation's answer, with `live` kept by the
      dashboard's liveNavigation). On a live clock a link to a moment or a range pauses there, as this tier's dashboard
      read #t= and #tr= with a seek and setRange; `live`, or no t, follows the newest data. With nothing live bound it is
      Clock.restore, `live` read as no t. WHY an override (found merging lane/live onto §25's Clock, 2026-10-28): the
      Clock's restore placed t and kept following, so the next frame took t back to the newest data and a shared moment
      never held. */
  restore(nav = {}) {
    const t = nav ? nav.t : null;
    if (!this.live) {
      // WHY kept for later (RobotDx PEP 0001 §17.1, ask 3): a moment or a range asked before any live data is bound (a
      // panel pinned at its t, CONTRACT §34, whose views bind their live data after) is the reader's, so the data binding
      // later leaves it paused there (bind() follows only a clock nobody paused); `live` or no t follows it, as above
      if ((typeof t === 'number' && Number.isFinite(t)) || Array.isArray(nav && nav.range)) this._userPaused = true;
      else if (t === 'live' || t === 'home' || t === undefined) this._userPaused = false;
      return super.restore(t === 'live' ? { ...nav, t: 'home' } : nav);
    }
    const moment = typeof t === 'number' && Number.isFinite(t);
    if (moment || Array.isArray(nav.range)) {
      this._leave();
      return super.restore(moment ? nav : { ...nav, t: null });
    }
    super.restore({ ...nav, t: null });
    if ((t === 'live' || t === 'home') && !this.following) this.goLive();
  }

  setLoop(on) {
    if (this.live && on) this._leave();
    super.setLoop(on);
  }

  _tick(now) {
    // a loop range or loop-all on live data loops as a Clock does; otherwise a replay that reaches the end follows
    if (!this.live || this.range || this.loop) return super._tick(now);
    if (!this.playing || this.following) return;
    const dt = Math.min(0.25, (now - this._last) / 1000);
    this._last = now;
    const t = this.t + dt * this.rate;
    if (this.liveEnd !== null && t >= this.liveEnd) { this.goLive(); return; }
    super.seek(t, { source: 'play' });
    this._raf = requestAnimationFrame(this._tick);
  }
}
