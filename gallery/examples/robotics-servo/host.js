/* The host of this page's dashboard editor (gallery case robotics-servo; loaded by the case page through site.json). data-ui
   never writes a file (CONTRACT §34), a host does, and this static page has no server: so it keeps what it is handed in this
   browser's localStorage and serves it back when the dashboard reads its files again, a stand-in for a host's PUT of a
   .base file. The editor is the real one; only this storage is simulated. */

const KEY = 'data-ui/gallery/robotics-servo/';
const memory = {};
const nameOf = (url) => new URL(url, location.href).pathname.split('/').pop();
const kept = (name) => { try { return localStorage.getItem(KEY + name); } catch { return null; } };
function keep(name, text) {
  memory[name] = text;
  try { localStorage.setItem(KEY + name, text); } catch { /* a private window: this visit only */ }
}
function forget() {
  try { for (const k of Object.keys(localStorage)) if (k.startsWith(KEY)) localStorage.removeItem(k); } catch { /* nothing kept */ }
  location.reload();
}

const real = window.fetch.bind(window);
window.fetch = (input, init) => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  const name = nameOf(url);
  const text = name.endsWith('.base') ? memory[name] ?? kept(name) : null;
  return text === null || text === undefined ? real(input, init) : Promise.resolve(new Response(text, { status: 200, headers: { 'content-type': 'text/plain' } }));
};

// CONTRACT §34's hook: the queue is the entry marked queue: true
document.documentElement.dashboards = async () => [{ id: 'saved', title: 'Saved for later', url: 'saved.base', queue: true }];

const stored = (detail) => { keep(nameOf(detail.dashboard.url), detail.text); return Promise.resolve({ ok: true, title: detail.dashboard.title }); };
document.addEventListener('data-dashboard-save', (e) => {
  const d = e.detail;
  if (d.asCopy) { keep(`${d.asCopy.title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.base`, d.text); e.detail.respondWith(Promise.resolve({ ok: true, title: d.asCopy.title })); } else e.detail.respondWith(stored(d));
});
document.addEventListener('data-add-to-dashboard', (e) => { if (e.detail.text !== null && e.detail.dashboard.url) e.detail.respondWith(stored(e.detail)); });

// what this browser keeps can be forgotten; and if the dashboard read its file before this script ran, it reads it again
const dash = document.querySelector('data-dashboard');
if (dash) {
  customElements.whenDefined('data-dashboard').then(() => { if (dash.baseText && kept('views.base') && dash.baseText !== kept('views.base')) dash.reload(); });
  const note = document.createElement('p');
  note.className = 'muted';
  note.hidden = !kept('views.base') && !kept('saved.base');
  note.innerHTML = 'This page keeps what you save in this browser. <button type="button" class="copy">Forget it</button>';
  note.querySelector('button').addEventListener('click', forget);
  dash.closest('.live').after(note);
  document.addEventListener('data-dashboard-save', () => { note.hidden = false; });
}
