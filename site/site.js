// The docs site's own behaviour: the theme switch, the landing hero and thumbnails, the gallery's filters and the
// Copy buttons. The kit itself is loaded here, once.
import './kit/data-ui.js';
// a dashboard page loads <data-dashboard> too (docs/peps/0004-dashboards.md); every other page skips its bytes
if (document.querySelector('data-dashboard')) import('./kit/dashboard.js');
// an analysis or a list of them loads <data-analysis> (docs/peps/0007-analyses.md), which loads the dashboard itself
if (document.querySelector('data-analysis, data-analyses')) import('./kit/analysis.js');

const root = document.documentElement;
const themeButton = document.querySelector('.theme');
const order = ['system', 'light', 'dark'];
const current = () => root.dataset.theme || 'system';
const label = () => { if (themeButton) themeButton.textContent = `Theme: ${current()}`; };
label();
if (themeButton) {
  themeButton.addEventListener('click', () => {
    const next = order[(order.indexOf(current()) + 1) % order.length];
    if (next === 'system') delete root.dataset.theme; else root.dataset.theme = next;
    try { if (next === 'system') localStorage.removeItem('data-ui-site-theme'); else localStorage.setItem('data-ui-site-theme', next); } catch { /* the choice lasts this visit */ }
    label();
  });
}

// ---- Copy buttons beside a file
document.addEventListener('click', (e) => {
  const copy = e.target.closest('.copy');
  if (!copy) return;
  const text = copy.closest('.file').querySelector('pre code').textContent;
  try { navigator.clipboard.writeText(text); copy.textContent = 'Copied'; } catch { copy.textContent = 'Select to copy'; }
});

// ---- the landing hero: the same rows through each view in turn, until the reader takes over
const hero = document.getElementById('hero');
if (hero) {
  const buttons = [...document.querySelectorAll('.hero-demo .segmented button')];
  const play = document.querySelector('.hero-play');
  const yaml = document.querySelector('.hero-yaml');
  const STEP = 5000; // ms per view
  // WHY no motion when the reader asked for none: the hero then waits for a click
  let playing = !matchMedia('(prefers-reduced-motion: reduce)').matches;
  let timer = null;
  const show = (name) => { const tab = hero.querySelector(`.dv-tab[data-name="${CSS.escape(name)}"]`); if (tab) tab.click(); };
  const mark = (name) => {
    for (const b of buttons) b.setAttribute('aria-pressed', String(b.dataset.name === name));
    if (yaml) yaml.textContent = hero.viewYaml();
  };
  const schedule = () => {
    clearTimeout(timer);
    hero.closest('.hero-demo').classList.toggle('playing', playing);
    if (!playing) return;
    timer = setTimeout(() => {
      if (document.hidden) { schedule(); return; }
      const at = buttons.findIndex((b) => b.getAttribute('aria-pressed') === 'true');
      show(buttons[(at + 1) % buttons.length].dataset.name);
    }, STEP);
  };
  const stop = () => { playing = false; play.setAttribute('aria-pressed', 'false'); play.textContent = 'Play'; schedule(); };
  hero.addEventListener('data-views-change', (e) => { mark(e.detail.name); schedule(); });
  for (const b of buttons) b.addEventListener('click', () => { stop(); show(b.dataset.name); });
  play.addEventListener('click', () => {
    playing = !playing;
    play.setAttribute('aria-pressed', String(playing));
    play.textContent = playing ? 'Pause' : 'Play';
    schedule();
  });
  // a reader working in the view stops the tour; hovering only pauses it
  hero.addEventListener('pointerdown', stop);
  hero.addEventListener('keydown', stop);
  hero.addEventListener('pointerenter', () => { if (playing) { clearTimeout(timer); hero.closest('.hero-demo').classList.remove('playing'); } });
  hero.addEventListener('pointerleave', schedule);
}

// ---- the thirteen live thumbnails: each starts when it scrolls near, so the page loads one view's code at first
const thumbs = document.querySelectorAll('.thumb[data-src]');
if (thumbs.length) {
  const start = (t) => {
    const el = document.createElement('data-views');
    el.setAttribute('src', t.dataset.src);
    el.setAttribute('view', t.dataset.view);
    el.setAttribute('no-url', '');
    el.setAttribute('toolbar', 'none');
    el.inert = true;
    t.querySelector('.thumb-live').append(el);
  };
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { io.unobserve(e.target); start(e.target); }
  }, { rootMargin: '150px 0px' });
  for (const t of thumbs) io.observe(t);
}

// ---- the gallery's filters, column slider and layouts: site/gallery.js (loaded by the gallery index only)
