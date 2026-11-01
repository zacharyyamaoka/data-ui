/* <data-mesh src poster interact fit alt>: one 3D model, poster first (docs/CONTRACT.md §23).

   It draws its poster (an <img>, lazy) and nothing else until the model is wanted; then it loads the 3D engine once
   for the page (dist/views/mesh.js: three.js with ONE shared WebGL renderer) and shows live frames in its own 2D
   canvas. So a gallery's first paint is images only, and the page never holds more than one WebGL context.

   interact (default hover):
     hover   a turntable while the pointer is over it; drag rotates; leaving freezes it on the angle you left
     click   live from a click or Enter (a phone, a dense grid)
     orbit   live as soon as it is shown, turning slowly until touched; drag orbits, the wheel zooms, a double-click
             resets (the peek's viewer)
     none    the poster only
   A drag never becomes a click on what holds it (a card opens its peek on a click, not after a spin). */

const ENGINE_URL = () => new URL('./views/mesh.js', import.meta.url).href;
let engine = null;
/** The engine module, loaded once (resolves to its exports: start, stop, input, theme, engineStats). */
export function meshEngine() {
  if (!engine) {
    engine = import(/* @vite-ignore */ ENGINE_URL());
    engine.catch(() => { engine = null; });
  }
  return engine;
}

const INTERACT = new Set(['hover', 'click', 'orbit', 'none']);

export class DataMesh extends (typeof HTMLElement === 'undefined' ? class {} : HTMLElement) {
  static get observedAttributes() { return ['src', 'poster', 'fit', 'alt', 'interact', 'view', 'background']; }

  /** The engine's numbers (live WebGL contexts, models, bytes, frame time), or null before any model was wanted. */
  static async stats() { return engine ? (await engine).engineStats() : null; }

  get src() { return this.getAttribute('src') || ''; }
  get interact() { const v = this.getAttribute('interact'); return INTERACT.has(v) ? v : 'hover'; }

  connectedCallback() {
    if (!this._built) this._build();
    this._sync();
    if (this.interact === 'orbit') this._observe();
  }

  disconnectedCallback() {
    if (this._io) { this._io.disconnect(); this._io = null; }
    if (engine) engine.then((e) => e.stop(this)).catch(() => {});
  }

  attributeChangedCallback() { if (this._built) this._sync(); }

  _build() {
    this._built = true;
    this.classList.add('dv-mesh');
    this.innerHTML = '<img class="dv-mesh-poster" alt="" loading="lazy" decoding="async"><canvas class="dv-mesh-canvas" aria-hidden="true"></canvas><span class="dv-mesh-badge" aria-hidden="true">3D</span>';
    this.poster = this.querySelector('img');
    this.canvas = this.querySelector('canvas');
    this.addEventListener('pointerenter', (e) => { if (e.pointerType === 'mouse' && this.interact === 'hover') this.activate(); });
    this.addEventListener('pointerleave', (e) => { if (e.pointerType === 'mouse' && this.interact === 'hover' && !this._drag) this.deactivate(); });
    this.addEventListener('pointerdown', (e) => this._down(e));
    this.addEventListener('click', (e) => {
      // WHY swallow the click after a drag: a card opens its peek on click; a spin is not a request to open it
      if (this._moved) { e.stopPropagation(); e.preventDefault(); this._moved = false; return; }
      if (this.interact === 'click' && !this.classList.contains('dv-mesh-live')) { e.stopPropagation(); this.activate(); }
    }, true);
    this.addEventListener('keydown', (e) => {
      if (this.interact === 'click' && (e.key === 'Enter' || e.key === ' ') && e.target === this) { e.preventDefault(); this.activate(); }
    });
    this.addEventListener('wheel', (e) => {
      if (this.interact !== 'orbit' || !this.classList.contains('dv-mesh-live')) return;
      e.preventDefault();
      meshEngine().then((m) => m.input(this, 'zoom', e.deltaY));
    }, { passive: false });
    this.addEventListener('dblclick', () => { if (this.interact === 'orbit') meshEngine().then((m) => m.input(this, 'reset')); });
  }

  /** The live frames' backdrop: `background` match (default: the poster's own corner colour, so the hand-off from
      poster to model shows no edge), light (white) or theme (transparent: the card's colour). */
  background() {
    const mode = this.getAttribute('background') || 'match';
    if (mode === 'theme') return null;
    if (mode === 'light') return '#ffffff';
    return this._posterBg || null;
  }

  _samplePoster() {
    const img = this.poster;
    try {
      const c = document.createElement('canvas');
      c.width = 4; c.height = 4;
      const x = c.getContext('2d', { willReadFrequently: true });
      x.drawImage(img, 0, 0, 2, 2, 0, 0, 2, 2); // the top-left corner: a poster's backdrop, never its object
      const [r, g, b] = x.getImageData(0, 0, 1, 1).data;
      this._posterBg = `rgb(${r}, ${g}, ${b})`;
    } catch { this._posterBg = null; } // another origin's poster cannot be read: theme
    this._paintBg();
  }

  _paintBg() {
    const bg = this.background();
    this.style.backgroundColor = bg || '';
  }

  _sync() {
    const poster = this.getAttribute('poster');
    if (!this._sampling) {
      this._sampling = true;
      this.poster.addEventListener('load', () => this._samplePoster());
    }
    if (poster) { if (this.poster.getAttribute('src') !== poster) this.poster.src = poster; this.poster.hidden = false; }
    else { this.poster.removeAttribute('src'); this.poster.hidden = true; }
    this.poster.alt = this.getAttribute('alt') || '';
    this.poster.style.objectFit = this.getAttribute('fit') === 'cover' ? 'cover' : 'contain';
    this.classList.toggle('dv-mesh-none', this.interact === 'none' || !this.src);
    if (this.interact === 'click' && !this.hasAttribute('tabindex')) this.tabIndex = 0;
    if (this.interact === 'orbit') this.setAttribute('aria-label', `${this.getAttribute('alt') || '3D model'}: drag to turn, scroll to zoom, double-click to reset`);
    this._paintBg();
    const viewKey = this.getAttribute('view') || '';
    if (this._viewKey !== undefined && this._viewKey !== viewKey && engine) engine.then((e) => e.reframe && e.reframe(this));
    this._viewKey = viewKey;
    if (this._src !== this.src) {
      if (engine) engine.then((e) => e.reframe && e.reframe(this)); this._src = this.src; this.classList.remove('dv-mesh-live', 'dv-mesh-frozen'); if (engine) engine.then((e) => e.stop(this)); if (this.interact === 'orbit' && this._seen) this.activate(); }
  }

  _observe() {
    if (this._io || typeof IntersectionObserver === 'undefined') { this.activate(); return; }
    this._io = new IntersectionObserver((entries) => {
      const on = entries.some((x) => x.isIntersecting);
      this._seen = on;
      if (on) this.activate(); else this.deactivate();
    });
    this._io.observe(this);
  }

  /** Load the model and draw it live (the engine keeps at most a few live at once; the oldest freezes). */
  activate() {
    if (!this.src || this.interact === 'none') return;
    this.classList.add('dv-mesh-loading');
    meshEngine().then((m) => m.start(this)).catch((err) => {
      this.classList.remove('dv-mesh-loading');
      this.classList.add('dv-mesh-failed');
      this.title = `The 3D model did not load: ${err && err.message ? err.message : err}`;
    });
  }

  deactivate() {
    if (engine) engine.then((m) => m.stop(this));
    if (this.classList.contains('dv-mesh-live')) this.frozen();
  }

  /** Called by the engine: the first live frame is in the canvas. */
  shown() { this.classList.remove('dv-mesh-loading', 'dv-mesh-frozen'); this.classList.add('dv-mesh-live'); }
  /** Called by the engine: no longer animating; the canvas keeps the last frame. */
  frozen() { this.classList.add('dv-mesh-frozen'); }

  _down(e) {
    if (this.interact === 'none' || e.button !== 0) return;
    if (!this.classList.contains('dv-mesh-live') && this.interact !== 'hover') return;
    const x0 = e.clientX, y0 = e.clientY;
    let x = x0, y = y0;
    this._moved = false;
    this._drag = true;
    let captured = false;
    const move = (ev) => {
      const dx = ev.clientX - x, dy = ev.clientY - y;
      x = ev.clientX; y = ev.clientY;
      if (!this._moved && Math.hypot(x - x0, y - y0) > 4) {
        this._moved = true;
        try { this.setPointerCapture(e.pointerId); captured = true; } catch { /* already released */ }
        meshEngine().then((m) => { if (!this.classList.contains('dv-mesh-live')) m.start(this); m.input(this, 'down'); });
      }
      if (this._moved) { ev.preventDefault(); meshEngine().then((m) => m.input(this, 'drag', dx, dy)); }
    };
    const up = () => {
      this.removeEventListener('pointermove', move);
      this.removeEventListener('pointerup', up);
      this.removeEventListener('pointercancel', up);
      if (captured) try { this.releasePointerCapture(e.pointerId); } catch { /* gone */ }
      this._drag = false;
      if (this._moved) meshEngine().then((m) => m.input(this, 'up'));
      // a drag that ended outside a hover-mode model: it left while dragging, so freeze it now
      if (this.interact === 'hover' && !this.matches(':hover')) this.deactivate();
    };
    this.addEventListener('pointermove', move);
    this.addEventListener('pointerup', up);
    this.addEventListener('pointercancel', up);
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('data-mesh')) customElements.define('data-mesh', DataMesh);
