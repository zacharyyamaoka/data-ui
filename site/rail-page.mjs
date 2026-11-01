// The app rail's gallery page (docs/CONTRACT.md §27): dist/site/gallery/app-rail/index.html. Not a .base case (the rail is
// navigation, not a view of rows), so it is written here and called once from build-site.mjs.
// Two things on it: one live rail with the settings select (the three styles, the toggle, Ctrl+Alt+R, the wide style's
// drag edge), and the three styles side by side at their real sizes, so the choice can be seen without clicking.
const ICON = {
  fleet: '<circle cx="12" cy="12" r="8"/>',
  boards: '<rect x="4" y="4" width="7" height="7"/><rect x="13" y="4" width="7" height="7"/><rect x="4" y="13" width="16" height="7"/>',
  runs: '<path d="M5 5l14 7-14 7z"/>',
  calibration: '<path d="M4 18L12 5l8 13z"/>',
  hardware: '<rect x="5" y="5" width="14" height="14" rx="2"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>',
  brand: '<rect x="4" y="6" width="16" height="12" rx="3"/><circle cx="9" cy="12" r="1.2"/><circle cx="15" cy="12" r="1.2"/>',
};
const svg = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICON[name]}</svg>`;
const link = (id, label, icon, extra = '') => `<a href="#${id}" data-id="${id}" ${extra}>${svg(icon)}${label}</a>`;

const rail = (attrs) => `<data-rail ${attrs} brand="RobotDx" search="Search" search-keys="Ctrl K" current="fleet">
  <span data-brand-icon>${svg('brand')}</span>
  ${link('fleet', 'Fleet', 'fleet', 'data-group="Monitor"')}
  ${link('dashboards', 'Dashboards', 'boards', 'data-group="Monitor"')}
  ${link('runs', 'Runs', 'runs', 'data-group="Data"')}
  ${link('calibration-runs', 'CalibrationRuns', 'calibration', 'data-group="Data"')}
  ${link('hardware', 'Hardware compatibility matrix', 'hardware', 'data-group="Data"')}
  ${link('settings', 'Settings', 'settings', 'data-end')}
</data-rail>`;

export function railPage({ write, version }) {
  write('gallery/app-rail/index.html', `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The app rail · data-ui examples</title>
<link rel="stylesheet" href="../../kit/data-ui.css">
<script type="module">
  import { bindRailSelect } from '../../kit/data-ui.js';
  await customElements.whenDefined('data-rail');
  bindRailSelect(document.getElementById('style'), document.getElementById('demo'));
  document.addEventListener('data-rail-navigate', (e) => { document.getElementById('where').textContent = e.detail.label; });
  document.addEventListener('data-rail-search', () => { document.getElementById('where').textContent = 'Search (the host opens its command palette here)'; });
</script>
<style>
  :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
  body { margin: 0; padding: 24px 16px; max-width: 980px; margin-inline: auto; background: Canvas; color: CanvasText; }
  p, .note { color: GrayText; font-size: 13px; max-width: 70ch; }
  .app { display: flex; height: 440px; border: 1px solid color-mix(in srgb, CanvasText 18%, Canvas); border-radius: 8px; overflow: hidden; position: relative; }
  .app main { flex: 1 1 auto; min-width: 0; padding: 16px 20px; }
  .app data-rail { height: 100%; }
  label { display: inline-flex; gap: 8px; align-items: center; margin: 0 0 12px; font-size: 14px; }
  .trio { display: flex; gap: 24px; align-items: flex-start; flex-wrap: wrap; }
  .trio figure { margin: 0; } .trio figcaption { font-size: 12px; color: GrayText; margin-top: 6px; }
  .trio .app { height: 340px; width: auto; }
  pre { overflow: auto; padding: 12px; border: 1px solid color-mix(in srgb, CanvasText 15%, Canvas); border-radius: 6px; font-size: 12px; }
  .crumbs a { color: inherit; }
</style>
</head>
<body>
<p class="crumbs"><a href="../index.html">Examples</a> › The app rail</p>
<h1>The app rail</h1>
<p>One element, <code>&lt;data-rail&gt;</code>, three styles: icons only (Obsidian), each icon with its label centred under it (Figma), and a wide list (Shopify). Which one an app shows is a setting. data-ui ${version}; CONTRACT §27.</p>
<h2>Live, with its settings select</h2>
<label>Sidebar <select id="style"></select></label>
<div class="app">
  ${rail('id="demo" storage-key="gallery-demo" hotkey="mod+alt+r"')}
  <main><h3>Pages</h3><p>You are on: <b id="where">Fleet</b>. Click a destination, press Ctrl+Alt+R to fold or open the rail, and in the wide style drag its right edge (double-click resets it to 15rem). Your choice is remembered in this browser.</p></main>
</div>
<h2>The three side by side</h2>
<div class="trio">
  <figure><div class="app">${rail('mode="collapsed" hotkey="off" data-resizable="off"')}</div><figcaption>Icons only · 3rem</figcaption></figure>
  <figure><div class="app">${rail('mode="expanded" hotkey="off" data-resizable="off"')}</div><figcaption>Labels under icons · 4.5rem</figcaption></figure>
  <figure><div class="app">${rail('mode="wide" hotkey="off" data-resizable="off"')}</div><figcaption>Wide list · 15rem</figcaption></figure>
</div>
<p class="note">These three keep no choice (each has its own <code>storage-key</code> and the demo above is the one that remembers).</p>
<h2>The markup</h2>
<pre><code>&lt;data-rail id="app-rail" brand="RobotDx" search="Search" search-keys="Ctrl K" current="fleet"&gt;
  &lt;a href="#fleet" data-id="fleet" data-group="Monitor"&gt;&lt;svg&gt;…&lt;/svg&gt;Fleet&lt;/a&gt;
  &lt;a href="#settings" data-id="settings" data-end&gt;&lt;svg&gt;…&lt;/svg&gt;Settings&lt;/a&gt;
&lt;/data-rail&gt;
&lt;select id="style"&gt;&lt;/select&gt;
&lt;script type="module"&gt;
  import { bindRailSelect } from './data-ui.js';
  bindRailSelect(document.getElementById('style'), document.getElementById('app-rail'));
&lt;/script&gt;</code></pre>
</body>
</html>
`);
}
