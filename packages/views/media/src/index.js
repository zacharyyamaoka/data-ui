/* type: video, video-compare, image — the media cards (docs/peps/0005-dashboard-cards.md §2b, §3, §4).

     video:   {src, label, primary}  the first row its filters leave, as a native <video> that follows the clock
     overlay: {src, by, a, b, mode, split}  (type: video-compare) rows A and B (by = a / b, else the first two rows),
              wipe | onion | difference | side; the card's switch and the wipe handle write mode and split back
              through host.setView, so the view entry keeps them
     image:   <property> + caption: [properties] (Bases' keys)  one picture, or a horizontal strip when several rows are left
     empty:   the text a card says when its view leaves it no row (each type; default "No rows match this view.")

   Time: the dashboard's clock is the only control (Zach, 2026-10-26: "play back videos, and see trajectories, and
   have all of those things synced"). A video has no native controls; a click on it toggles the clock. Every video
   follows the clock with core's followVideo (LeRobot's rule); the clock's ONE designated video (clock.setDriver: the
   dashboard resolves clock.primary, else its first `video.primary: true` card; outside a dashboard the first
   `primary: true` card claims the page's clock) instead drives t from its own frames while the clock plays
   (requestVideoFrameCallback → clock.drive, ./clip.js), so nothing fights it, and follows again when paused. A
   paused clock lands every video exactly on t − t0. HTMLMediaElement.mediaGroup is not used (removed from browsers).

   Lazy: a <video> starts with preload="none" and no src; its src is set (and preload="auto") only when the card
   nears the viewport (IntersectionObserver), so a long dashboard fetches only the clips on screen.

   Honest media: the caption prints each clip's `basis` (real camera, sim render, screen capture, illustrative); an
   illustrative clip is also tagged on the picture. The poster is the row's `poster` column when it has one.

   STOCK PARTS: the browser's <video> and <img>, CSS clip-path / opacity / mix-blend-mode for the overlay modes.
   Not img-comparison-slider (images only). */

import { cellValue, esc, mediaUrl, isEmpty, isNum, clockFor, driverKey, fmtTime, seriesColor, propLabel } from '@data-ui/core';
import css from './media.css';
import { basisText, pairBasis, pickPair, clampSplit, wipeClip, splitAt, MODES, MODE_LABEL } from './model.js';
import { Clip } from './clip.js';

export { css };
export { basisText, pairBasis, pickPair, wipeClip, splitAt } from './model.js';

let cards = 0;              // each video card's own number: its driver scope outside a dashboard
const NEAR = '240px 0px';   // how close to the viewport a card is before its clips load
const COMMIT_MS = 250;      // a dragged split is written to the view entry once the drag rests this long

/** Read a column of a row as a plain value ('' and missing are null). */
const read = (row, col) => {
  if (!row || !col) return null;
  const v = cellValue(row[col]);
  return isEmpty(v) ? null : v;
};

/** Shared by the two video cards: the clock's listeners, the lazy observer, the letterbox radius. */
class ClockCard {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this.clock = clockFor(host.element);
    this.clips = [];
    this._time = (e) => { for (const c of this.clips) c.onTime(e.detail && e.detail.source); this.tick(); };
    this._state = () => { for (const c of this.clips) c.onState(); this.tick(); };
    this.clock.addEventListener('time', this._time);
    this.clock.addEventListener('state', this._state);
    this._io = typeof IntersectionObserver === 'function'
      ? new IntersectionObserver((entries) => { if (entries.some((e) => e.isIntersecting)) this.show(); }, { rootMargin: NEAR })
      : null;
  }

  observe(target) { if (this._io) this._io.observe(target); else this.show(); }

  show() {
    this.near = true;
    for (const c of this.clips) c.show();
    if (this._io) { this._io.disconnect(); this._io = null; }
  }

  /** Redraw what moves with the clock (cheap: text and an attribute). */
  tick() {}

  destroy() {
    this.clock.removeEventListener('time', this._time);
    this.clock.removeEventListener('state', this._state);
    if (this._io) this._io.disconnect();
    for (const c of this.clips) c.destroy();
    this.clips = [];
    this.el.innerHTML = '';
  }
}

/** The caption's label and basis badge for one row. */
function labelHtml(text, input, prefix = '') {
  if (isEmpty(text)) return '';
  const dot = seriesColor(String(text), input);
  return `<span class="dv-media-label"><span class="dv-media-dot" style="--dv-media-dot:${esc(dot)}"></span>${esc(prefix)}${esc(text)}</span>`;
}

function basisHtml(basis, note, mixed = false) {
  const text = mixed ? basis : basisText(basis);
  if (!text) return '';
  return `<span class="dv-media-basis"${mixed ? ' data-mixed' : ` data-basis="${esc(basis)}"`}${note ? ` title="${esc(note)}"` : ''}>${esc(text)}</span>`;
}

const missingHtml = (why) => `<b>—</b>${esc(why)}`;
/** What a card says when its view leaves it no row: the view's own `empty:` text (kit gap 9: "No depth captured yet"),
    else the generic sentence. */
const noRows = (input) => (typeof input.view.empty === 'string' && input.view.empty.trim() ? input.view.empty : 'No rows match this view.');

class VideoCard extends ClockCard {
  constructor(host, el) {
    super(host, el);
    el.innerHTML = `<div class="dv-media-card">
      <div class="dv-media-frame" role="button" tabindex="0" aria-label="Play or pause the dashboard's clock">
        <span class="dv-media-tag"></span>
        <span class="dv-media-hud"><span class="dv-media-glyph" aria-hidden="true"></span><span class="dv-media-time"></span></span>
      </div>
      <div class="dv-media-cap"></div>
      <p class="dv-media-none" hidden></p></div>`;
    this.card = el.querySelector('.dv-media-card');
    this.frame = el.querySelector('.dv-media-frame');
    this.timeEl = el.querySelector('.dv-media-time');
    this.clip = new Clip(this.clock);
    this.clips = [this.clip];
    this.seq = ++cards;
    this.frame.prepend(this.clip.video);
    // WHY no native controls: the dashboard's clock is the one control; a click here is its play/pause
    this.frame.addEventListener('click', () => this.clock.toggle());
    this.frame.addEventListener('keydown', (e) => {
      if (e.key !== ' ' && e.key !== 'Enter') return;
      e.preventDefault();
      e.stopPropagation();
      this.clock.toggle();
    });
    this.observe(this.frame);
    this.tick();
  }

  update(input) {
    const k = input.view.video || {};
    const row = input.rows[0];
    const none = this.el.querySelector('.dv-media-none');
    const srcCol = k.src || 'src';
    const src = read(row, srcCol);
    const why = !row ? noRows(input) : !src ? `No clip: this row has no ${propLabel(input.columns, srcCol)}.` : '';
    none.hidden = !why;
    none.innerHTML = why ? missingHtml(why) : '';
    this.frame.hidden = !!why;
    this.el.style.setProperty('--dv-media-r', `${radius(input)}px`);
    if (why) { this._claim(null); this.clip.set({ src: null, poster: null, t0: 0, id: null }); this.el.querySelector('.dv-media-cap').innerHTML = ''; return; }
    const poster = read(row, 'poster');
    // WHY a key per card instance, not the view's name: one view on two panels gave both clips the same id, so both
    // drove and either one's `ended` released the other (judge r2 #2). In a dashboard `<panel key>/<view name>`, what
    // its setDriver designates (core's driverInstance: docs/peps/0008-one-clock-driver.md); elsewhere this card's number
    const scope = this.host.element && this.host.element.clockScope;
    const id = driverKey(scope !== undefined && scope !== null && scope !== '' ? scope : `#${this.seq}`, input.view.name || 'video');
    this._claim(k.primary === true ? id : null);
    this.clip.set({ src: mediaUrl(src, input.dataset), poster: poster ? mediaUrl(poster, input.dataset) : null, t0: read(row, 't0'), id });
    const basis = read(row, 'basis'), note = read(row, 'note');
    const label = k.label ? read(row, k.label) : null;
    const cap = this.el.querySelector('.dv-media-cap');
    cap.innerHTML = labelHtml(label, input) + basisHtml(basis, note);
    cap.title = note || '';
    this.el.querySelector('.dv-media-tag').textContent = basis === 'illustrative' ? 'Illustrative · not a recording' : '';
    this.frame.setAttribute('aria-label', `${label ? `${label}: ` : ''}play or pause the dashboard's clock`);
    this.clip.sync();
    this.tick();
  }

  /** Outside a dashboard nobody designates a driver (clock.driverId undefined): the first `primary: true` card claims
      the page's clock, and gives it back when it stops being primary or goes. A dashboard's choice is never touched. */
  _claim(id) {
    if (id && (this.clock.driverId === undefined || (this._claimed && this.clock.driverId === this._claimed))) { this._claimed = id; this.clock.setDriver(id); }
    else if (!id && this._claimed && this.clock.driverId === this._claimed) { this.clock.setDriver(undefined); this._claimed = null; }
  }

  tick() {
    this.timeEl.textContent = fmtTime(this.clock.t);
    this.card.toggleAttribute('data-playing', this.clock.playing);
  }

  destroy() {
    this._claim(null);
    super.destroy();
  }
}

class CompareCard extends ClockCard {
  constructor(host, el) {
    super(host, el);
    el.innerHTML = `<div class="dv-media-card dv-media-compare" data-mode="wipe">
      <div class="dv-media-bar">
        <div class="dv-media-cap"></div>
        <div class="dv-media-modes" role="radiogroup" aria-label="Overlay mode">${MODES.map((m) =>
          `<button type="button" role="radio" data-mode="${m}" aria-checked="false">${MODE_LABEL[m]}</button>`).join('')}</div>
      </div>
      <div class="dv-media-frame">
        <div class="dv-media-stage">
          <div class="dv-media-pane dv-media-pb"><span class="dv-media-corner"></span></div>
          <div class="dv-media-pane dv-media-pa"><span class="dv-media-corner"></span></div>
          <div class="dv-media-handle" role="slider" tabindex="0" aria-label="Wipe position" aria-valuemin="0" aria-valuemax="100"><span class="dv-media-grip"></span></div>
        </div>
        <label class="dv-media-onion">A opacity <input class="dv-media-opacity" type="range" min="0" max="1" step="0.01"></label>
      </div>
      <p class="dv-media-none" hidden></p></div>`;
    this.root = el.querySelector('.dv-media-compare');
    this.stage = el.querySelector('.dv-media-stage');
    this.handle = el.querySelector('.dv-media-handle');
    this.opacity = el.querySelector('.dv-media-opacity');
    this.A = new Clip(this.clock);
    this.B = new Clip(this.clock);
    this.A.video.classList.add('dv-media-a');
    this.B.video.classList.add('dv-media-b');
    el.querySelector('.dv-media-pa').prepend(this.A.video);
    el.querySelector('.dv-media-pb').prepend(this.B.video);
    this.clips = [this.A, this.B];
    this.mode = 'wipe';
    this.split = 0.5;
    this._timer = 0;
    this._wire();
    this.observe(el.querySelector('.dv-media-frame'));
  }

  _wire() {
    for (const b of this.el.querySelectorAll('.dv-media-modes button')) {
      b.addEventListener('click', () => this._setMode(b.dataset.mode));
    }
    const h = this.handle;
    h.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      h.setPointerCapture(e.pointerId);
      this._dragging = true;
      h.focus({ preventScroll: true });
    });
    h.addEventListener('pointermove', (e) => {
      if (!this._dragging) return;
      const r = this.stage.getBoundingClientRect();
      this._setSplit(splitAt(e.clientX, r.left, r.width));
    });
    const end = (e) => {
      if (!this._dragging) return;
      this._dragging = false;
      if (h.hasPointerCapture(e.pointerId)) h.releasePointerCapture(e.pointerId);
      this._later();
    };
    h.addEventListener('pointerup', end);
    h.addEventListener('pointercancel', end);
    h.addEventListener('keydown', (e) => {
      const step = e.shiftKey ? 0.1 : 0.05;
      const next = e.key === 'ArrowLeft' ? this.split - step : e.key === 'ArrowRight' ? this.split + step
        : e.key === 'Home' ? 0 : e.key === 'End' ? 1 : null;
      if (next === null) return;
      // WHY stop here: the dashboard's ←/→ step the clock; on the handle they move the wipe
      e.preventDefault();
      e.stopPropagation();
      this._setSplit(Math.round(next * 1000) / 1000);
      this._later();
    });
    this.opacity.addEventListener('input', () => { this._setSplit(Number(this.opacity.value)); this._later(); });
  }

  /** Write split (and mode) back to the view entry once the drag rests: host.setView keeps it (the URL, a preset,
      the .base file — whatever the host does with view edits). */
  _later() {
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this._commit(), COMMIT_MS);
  }

  _commit(patch = {}) {
    clearTimeout(this._timer);
    this._timer = 0;
    const cur = (this.view && this.view.overlay) || {};
    const next = { ...cur, mode: this.mode, split: this.split, ...patch };
    if (next.mode === cur.mode && next.split === cur.split) return;
    this.host.setView({ overlay: next });
  }

  _setMode(mode) {
    if (!MODES.includes(mode)) return;
    this.mode = mode;
    this._apply();
    this._commit({ mode });
  }

  _setSplit(s) {
    this.split = clampSplit(s);
    this._apply();
  }

  /** Mode and split onto the DOM: one style write per element, no rebuild. */
  _apply() {
    const a = this.A.video, mode = this.mode, s = this.split;
    this.root.dataset.mode = mode;
    a.style.clipPath = mode === 'wipe' ? wipeClip(s) : 'none';
    a.style.opacity = mode === 'onion' ? String(s) : '';
    this.handle.style.left = `${s * 100}%`;
    this.handle.setAttribute('aria-valuenow', String(Math.round(s * 100)));
    this.handle.setAttribute('aria-valuetext', `A on the left ${Math.round(s * 100)}%`);
    if (Number(this.opacity.value) !== s) this.opacity.value = String(s);
    for (const b of this.el.querySelectorAll('.dv-media-modes button')) b.setAttribute('aria-checked', String(b.dataset.mode === mode));
  }

  update(input) {
    this.view = input.view;
    const o = input.view.overlay || {};
    const srcCol = o.src || 'src';
    const { a, b } = pickPair(input.rows, o, cellValue);
    const name = (row, letter, want) => (o.by ? read(row, o.by) : null) ?? want ?? (row ? read(row, input.dataset && input.dataset.titleProperty) ?? row.id : letter);
    const why = !a ? (o.by && !isEmpty(o.a) ? `No row has ${propLabel(input.columns, o.by)} = ${o.a}.` : noRows(input))
      : !b ? (o.by && !isEmpty(o.b) ? `No row has ${propLabel(input.columns, o.by)} = ${o.b}.` : 'A comparison needs two rows; this view leaves one.')
      : !read(a, srcCol) || !read(b, srcCol) ? `No clip: ${!read(a, srcCol) ? 'A' : 'B'} has no ${propLabel(input.columns, srcCol)}.` : '';
    const none = this.el.querySelector('.dv-media-none');
    none.hidden = !why;
    none.innerHTML = why ? missingHtml(why) : '';
    this.el.querySelector('.dv-media-bar').hidden = !!why;
    this.el.querySelector('.dv-media-frame').hidden = !!why;
    this.el.style.setProperty('--dv-media-r', `${radius(input)}px`);
    if (!this._dragging && !this._timer) {
      this.mode = MODES.includes(o.mode) ? o.mode : 'wipe';
      this.split = clampSplit(o.split ?? 0.5);
    }
    this._apply();
    if (why) { for (const c of this.clips) c.set({ src: null, poster: null, t0: 0, id: null }); return; }
    const an = name(a, 'A', o.a), bn = name(b, 'B', o.b);
    const clip = (row, letter) => {
      const poster = read(row, 'poster');
      return { src: mediaUrl(read(row, srcCol), input.dataset), poster: poster ? mediaUrl(poster, input.dataset) : null,
        t0: read(row, 't0'), id: `${input.view.name || 'compare'}:${letter}:${row.id}` };
    };
    // WHY never primary: a compare card only follows; if either clip's own video card is primary, that card drives
    this.A.set(clip(a, 'a'));
    this.B.set(clip(b, 'b'));
    // the picture's shape: the rows' own width/height, else the clip's once its metadata is in
    const ar = ratio(read(a, 'width'), read(a, 'height')) || ratio(this.A.video.videoWidth, this.A.video.videoHeight);
    if (ar) this.el.style.setProperty('--dv-media-ar', String(ar));
    else if (!this._arWait) {
      this._arWait = true;
      this.A.video.addEventListener('loadedmetadata', () => {
        this._arWait = false;
        const r = ratio(this.A.video.videoWidth, this.A.video.videoHeight);
        if (r) this.el.style.setProperty('--dv-media-ar', String(r));
      }, { once: true });
    }
    const corner = (sel, letter, text) => { this.el.querySelector(`${sel} .dv-media-corner`).textContent = `${letter}: ${text}`; };
    corner('.dv-media-pa', 'A', an);
    corner('.dv-media-pb', 'B', bn);
    const ba = read(a, 'basis'), bb = read(b, 'basis');
    const notes = [read(a, 'note') && `A: ${read(a, 'note')}`, read(b, 'note') && `B: ${read(b, 'note')}`].filter(Boolean).join('\n');
    const both = pairBasis(ba, bb);
    const mixed = !!both && basisText(ba) !== basisText(bb);
    this.el.querySelector('.dv-media-cap').innerHTML = labelHtml(an, input, 'A: ') + labelHtml(bn, input, 'B: ')
      + (both ? (mixed ? basisHtml(both, notes, true) : basisHtml(ba ?? bb, notes)) : '');
    this.el.querySelector('.dv-media-cap').title = notes;
    for (const c of this.clips) c.sync();
  }

  destroy() {
    clearTimeout(this._timer);
    super.destroy();
  }
}

class ImageCard {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    el.innerHTML = '<div class="dv-media-card"><div class="dv-media-strip" role="list"></div><p class="dv-media-none" hidden></p></div>';
    this.strip = el.querySelector('.dv-media-strip');
  }

  update(input) {
    // the keys are Bases' own: image: <property> (as on cards) and caption: [properties] (docs/CONTRACT.md §25)
    const srcCol = typeof input.view.image === 'string' && input.view.image ? input.view.image : 'src';
    const capCols = Array.isArray(input.view.caption) ? input.view.caption : input.view.caption ? [input.view.caption] : [];
    const rows = input.rows;
    const none = this.el.querySelector('.dv-media-none');
    none.hidden = rows.length > 0;
    none.innerHTML = rows.length ? '' : missingHtml(noRows(input));
    this.el.style.setProperty('--dv-media-r', `${radius(input)}px`);
    this.strip.toggleAttribute('data-many', rows.length > 1);
    this.strip.hidden = !rows.length;
    this.strip.innerHTML = rows.map((row) => {
      const src = read(row, srcCol);
      const cap = capCols.map((c) => read(row, c)).filter((v) => v !== null && v !== undefined && v !== '').join(' · ') || null;
      const pic = src
        ? `<img src="${esc(mediaUrl(src, input.dataset))}" alt="${esc(cap || '')}" loading="lazy" decoding="async">`
        : `<p class="dv-media-none">${missingHtml(`No image: this row has no ${propLabel(input.columns, srcCol)}.`)}</p>`;
      // WHY a title: the caption is clamped to two lines; the whole text stays one hover away
      return `<figure class="dv-media-fig" role="listitem"><div class="dv-media-imgbox">${pic}</div>${cap ? `<figcaption title="${esc(cap)}">${esc(cap)}</figcaption>` : ''}</figure>`;
    }).join('');
  }

  destroy() { this.el.innerHTML = ''; }
}

const ratio = (w, h) => (isNum(Number(w)) && isNum(Number(h)) && Number(w) > 0 && Number(h) > 0 ? Number(w) / Number(h) : null);

/** The picture's corner: the card's radius when the card has no surface of its own, a little inside it when it has. */
function radius(input) {
  const st = (input.view && input.view.style) || {};
  const r = isNum(st.radius) ? st.radius : 10;
  return !st.surface || st.surface === 'transparent' ? r : Math.max(4, r - 4);
}

const CARDS = { video: VideoCard, 'video-compare': CompareCard, image: ImageCard };

export default class MediaView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this.card = null;
    this.type = null;
  }

  update(input) {
    const type = CARDS[input.view.type] ? input.view.type : 'image';
    if (!this.card || this.type !== type) {
      if (this.card) this.card.destroy();
      this.type = type;
      this.card = new CARDS[type](this.host, this.el);
    }
    // the letterbox: always dark, from the tokens (the page's ink in light, its background in dark)
    const t = input.tokens;
    if (t && t.fg && t.bg) {
      this.el.style.setProperty('--dv-media-ink', t.dark ? t.bg : t.fg);
      this.el.style.setProperty('--dv-media-on', t.dark ? t.fg : t.bg);
    }
    return this.card.update(input);
  }

  destroy() {
    if (this.card) this.card.destroy();
    this.card = null;
  }
}
