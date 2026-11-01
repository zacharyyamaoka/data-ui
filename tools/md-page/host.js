/* The page's half of tools/serve-md.mjs (docs/CONTRACT.md §46): the existing hooks, pointed at the notes server. The kit keeps no files,
   so everything that knows a row is a file is here. Own-origin fetches only. */
import { parseBase } from '/kit/data-ui.js';

const el = document.querySelector('data-views');
const want = new URLSearchParams(location.search).get('db');
const { dbs, first } = await (await fetch('/dbs')).json();
const db = dbs.includes(want) ? want : first;
const at = (path) => `/db/${encodeURIComponent(db)}/${path}`;
const say = (msg) => { document.getElementById('where').textContent = msg; };

document.title = `${db} · Notes`;
document.getElementById('dbs').innerHTML = dbs.map((n) => `<a href="?db=${encodeURIComponent(n)}"${n === db ? ' aria-current="page"' : ''}>${n.replace(/[&<>"]/g, '')}</a>`).join('');

const post = async (path, body) => {
  const res = await fetch(at(path), { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  return res.json();
};

el.resolveMedia = (src, { row, embed }) => {
  if (/^https?:/i.test(src)) return src;
  if (embed) return at(`find/${encodeURIComponent(src)}`);
  // a note's path is relative to the note: one in a subfolder says ../attachments/x.png
  const dir = String(row.id).split('/').slice(0, -1);
  const parts = [...dir];
  for (const s of decodeURI(src).split('/')) { if (s === '..') parts.pop(); else if (s !== '.') parts.push(s); }
  return at(`file/${parts.map(encodeURIComponent).join('/')}`);
};

// Obsidian gives him wikilinks, voice dictation and the editor he is used to for free; the page only has to get him there. No vault: no link.
let vault = null;
const obsidian = (file) => `obsidian://open?vault=${encodeURIComponent(vault.name)}&file=${encodeURIComponent(file)}`;
el.openElsewhere = (row) => (vault ? { label: 'Obsidian', href: obsidian([vault.path, `${row.id}.md`].filter(Boolean).join('/')) } : null);
// a [[target]] is Obsidian's to find, by its name, wherever the note sits
el.resolveLink = (target) => (vault ? obsidian(target) : null);

el.acceptEdit = async ({ id, set, row }) => {
  const was = Object.fromEntries(Object.keys(set).map((k) => [k, row[k] ?? null]));
  const res = await post('edit', { id, set, was });
  if (res.ok) Object.assign(row, set);
  return res;
};
el.acceptAdd = (ask) => post('add', ask);
el.acceptPlace = (ask) => post('place', ask);
el.persistView = ({ text }) => post('base', { text });
el.acceptFile = async ({ file }) => {
  const res = await fetch(`${at('file')}?name=${encodeURIComponent(file.name || 'pasted.png')}`, { method: 'POST', headers: { 'content-type': 'application/octet-stream' }, body: file });
  return res.json();
};

let shownRows = '';
/** Draw what the folder says now. The rows redraw only when they differ from what the page holds, so an edit made here does not redraw twice. */
async function pull() {
  const { data, baseText, vault: where } = await (await fetch(at('dataset'))).json();
  vault = where;
  const rows = JSON.stringify([data.properties, data.rows]);
  const fresh = el.baseText !== baseText;
  const local = el.data ? JSON.stringify([data.properties, el.data.rows]) : '';
  if (!fresh && (rows === shownRows || rows === local)) { shownRows = rows; return; }
  shownRows = rows;
  if (fresh) { el.base = parseBase(baseText); el.baseText = baseText; }
  el.data = data;
  el.refreshPeek();
  say(`${data.rows.length} notes`);
}

await pull();
new EventSource(at('events')).addEventListener('change', () => { pull().catch((err) => say(`Not reading the folder: ${err.message}`)); });
