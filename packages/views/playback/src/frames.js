/* Real frames of a clip, for the YouTube proposal's hover thumbnail and the tracks proposal's filmstrip: a hidden
   <video> of the same file, seeked frame by frame and drawn into small canvases. Frames are cached by frame index,
   one seek at a time (a <video> holds one position).

   WHY its own <video>, not the media card's: the card's video follows the clock, and seeking it to show a hover
   thumbnail would move the picture everyone is watching.
   STOCK PARTS: none (HTMLVideoElement + canvas drawImage); ~90 lines. */

const grabbers = new Map();   // src → FrameGrabber: one hidden video per clip per page, shared by every proposal

export class FrameGrabber {
  static for(src, fps = 30) {
    let g = grabbers.get(src);
    if (!g) { g = new FrameGrabber(src, fps); grabbers.set(src, g); }
    return g;
  }

  constructor(src, fps = 30) {
    this.src = src;
    this.fps = fps;
    this.cache = new Map();   // frame index → canvas (drawn at the size first asked)
    this._queue = Promise.resolve();
    const v = this.video = document.createElement('video');
    v.muted = true;
    v.playsInline = true;
    v.preload = 'auto';
    v.dataset.grabber = '';
    this.ready = new Promise((resolve) => {
      const meta = () => {
        const s = v.seekable;
        const seekable = !Number.isFinite(v.duration) || (s.length > 0 && s.end(s.length - 1) >= v.duration - 0.05);
        // WHY a local copy: a server without HTTP Range support (python -m http.server) gives a clip Chrome cannot
        // seek, as the media card found (packages/views/media/src/index.js, _local)
        if (!seekable && !this._blob) {
          fetch(src).then((r) => (r.ok ? r.blob() : null)).then((b) => {
            if (!b) { resolve(false); return; }
            this._blob = URL.createObjectURL(b);
            v.src = this._blob;
          }).catch(() => resolve(false));
          return;
        }
        resolve(true);
      };
      v.addEventListener('loadedmetadata', meta);
      v.addEventListener('error', () => resolve(false), { once: true });
    });
    v.src = src;
  }

  get duration() { return Number.isFinite(this.video.duration) ? this.video.duration : null; }

  /** The buffered ranges of the clip in its own seconds: [[a, b], …]. */
  buffered() {
    const b = this.video.buffered, out = [];
    for (let i = 0; i < b.length; i++) out.push([b.start(i), b.end(i)]);
    return out;
  }

  /** A canvas holding the frame at clip time `time` (seconds from frame 0), w × h px; cached by frame index. */
  frame(time, w, h) {
    const k = Math.max(0, Math.round(time * this.fps));
    const hit = this.cache.get(k);
    if (hit) return Promise.resolve(hit);
    const job = this._queue.then(async () => {
      if (this.cache.has(k)) return this.cache.get(k);
      if (!(await this.ready)) return null;
      const v = this.video;
      const dur = this.duration ?? 0;
      // the middle of frame k, kept inside the clip (the last frame's start, not its end)
      const target = Math.min(Math.max(0, dur - 0.5 / this.fps), (k + 0.5) / this.fps);
      if (Math.abs(v.currentTime - target) > 1e-4 || v.readyState < 2) {
        await new Promise((resolve) => {
          const done = () => { v.removeEventListener('seeked', done); clearTimeout(timer); resolve(); };
          const timer = setTimeout(done, 10000);
          v.addEventListener('seeked', done);
          v.currentTime = target;
        });
      }
      // WHY check before drawing: on a loaded machine a seek can outlast the wait, and drawing then would cache the
      // previous frame under this index for good (a thumbnail that never changes); null lets the caller ask again
      if (v.readyState < 2 || v.seeking || Math.abs(v.currentTime - target) > 1e-3) return null;
      const c = document.createElement('canvas');
      c.width = w; c.height = h;
      c.getContext('2d').drawImage(v, 0, 0, w, h);
      c.dataset.frame = String(k);
      this.cache.set(k, c);
      return c;
    });
    this._queue = job.catch(() => null);
    return job;
  }
}
