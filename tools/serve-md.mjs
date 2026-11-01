// A folder of markdown notes as a table and its pages (docs/CONTRACT.md §46). One row = one .md file; tools/md-notes.mjs is the format.
//
//   node tools/serve-md.mjs <folder> [<folder> ...] [--port N] [--vault <name> --vault-root <path>]      (build first: npm run build)
//
// --vault names the Obsidian vault at --vault-root. A folder inside it gets Open in Obsidian on each page and row, and its [[wikilinks]] open
// there; a folder outside it, or no --vault, gets neither, and nothing is drawn in their place.
//
// Stdlib only. It binds 127.0.0.1, answers only to its own Host, takes a write only from a page of its own origin, and refuses any
// path outside the folder, symlinks included. WHY a server at all: data-ui stores nothing; this is one backend behind the dataset and
// the page's hooks (tools/md-page/host.js), and the kit never learns that a row is a file.
//
// The folder watches itself: a hand edit in Obsidian reaches the page through GET /db/<name>/events within about a second.
// A write re-reads the file first and changes only what it was asked to, so a hand edit a moment ago survives; an edit whose
// value changed on disk since the page read it is refused rather than overwritten.
import { createServer } from 'node:http';
import { createReadStream, existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, renameSync, statSync, watch, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { basename, dirname, extname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseBase } from '../packages/core/src/base.js';
import { buildRows, fitsHeading, layoutOf, planMove, readNote, setPage, setValue, PLACES } from './md-notes.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const KIT = join(ROOT, 'dist');
const PAGE = join(ROOT, 'tools', 'md-page');
const ATTACHMENTS = 'attachments';
const NEW_BASE = '# A table over this folder\'s notes.\nviews:\n  - type: table\n    name: Table\n';
const MAX_FILE = 64 * 1024 * 1024;
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.map': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.gif': 'image/gif', '.webp': 'image/webp', '.avif': 'image/avif', '.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime', '.pdf': 'application/pdf', '.wasm': 'application/wasm' };
const MEDIA = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.avif', '.svg', '.mp4', '.webm', '.mov', '.pdf']);

class Refused extends Error {}

/** One folder of notes. */
class Notes {
  constructor(folder, vault = null) {
    this.folder = realpathSync(resolve(folder));
    this.name = basename(this.folder);
    this.vault = null;
    if (vault && existsSync(vault.root)) {
      const root = realpathSync(resolve(vault.root));
      if (this.folder === root || this.folder.startsWith(root + sep)) this.vault = { name: vault.name, path: relative(root, this.folder).split(sep).join('/') };
    }
    this.clients = new Set();
    this.cache = new Map(); // relative path -> {mtime, size, text}
    this.rev = 0;
    this.shown = '';
    this.refresh();
    this._watch();
  }

  /** A path under the folder, or a refusal: no `..`, no dot segment, nothing a symlink leads out of it. */
  path(rel) {
    const parts = String(rel).split('/');
    if (String(rel).includes('\0') || !rel || parts.some((s) => !s || s === '.' || s === '..' || s.startsWith('.'))) throw new Refused(`${rel} is not a path in this folder`);
    const full = resolve(this.folder, ...parts);
    if (full !== this.folder && !full.startsWith(this.folder + sep)) throw new Refused(`${rel} is outside this folder`);
    // the deepest part that exists decides: a link inside the folder may point anywhere
    let at = full;
    while (!existsSync(at)) at = dirname(at);
    const real = realpathSync(at);
    if (real !== this.folder && !real.startsWith(this.folder + sep)) throw new Refused(`${rel} leads outside this folder`);
    return full;
  }

  noteFiles(dir = this.folder, out = []) {
    for (const f of readdirSync(dir, { withFileTypes: true })) {
      if (f.name.startsWith('.') || f.name === ATTACHMENTS) continue;
      if (f.isDirectory()) this.noteFiles(join(dir, f.name), out);
      else if (f.name.endsWith('.md') && f.name !== 'README.md') out.push(relative(this.folder, join(dir, f.name)).split(sep).join('/'));
    }
    return out.sort();
  }

  basePath() {
    const named = readdirSync(this.folder).filter((f) => f.endsWith('.base')).sort();
    return join(this.folder, named.includes('views.base') ? 'views.base' : named[0] || 'views.base');
  }

  baseText() { const f = this.basePath(); return existsSync(f) ? readFileSync(f, 'utf8') : NEW_BASE; }

  /** Every note as {id, text}, from what is on disk now. */
  notes() {
    const seen = new Set();
    const out = this.noteFiles().map((rel) => {
      seen.add(rel);
      const st = statSync(join(this.folder, rel));
      const hit = this.cache.get(rel);
      if (hit && hit.mtime === st.mtimeMs && hit.size === st.size) return { id: rel.replace(/\.md$/, ''), text: hit.text };
      const text = readFileSync(join(this.folder, rel), 'utf8');
      this.cache.set(rel, { mtime: st.mtimeMs, size: st.size, text });
      return { id: rel.replace(/\.md$/, ''), text };
    });
    for (const k of this.cache.keys()) if (!seen.has(k)) this.cache.delete(k);
    return out;
  }

  dataset() {
    const text = this.baseText();
    const base = parseBase(text);
    const { properties, rows } = buildRows(this.notes(), base);
    // §46: a folder of notes reads newest first until a view says otherwise, by the first of these it holds
    const when = ['added', 'created', 'date_created', 'date', 'filed'].find((id) => properties[id]);
    return { baseText: text, vault: this.vault, data: { id: this.name, title: this.name, titleProperty: 'name', ...(when ? { defaultSort: [{ property: when, direction: 'DESC' }] } : {}), properties, rows } };
  }

  /** Read the folder again; true when what a page shows changed, and every page is told. */
  refresh() {
    let now;
    try { now = JSON.stringify(this.dataset()); } catch (err) { console.error(`${this.name}: ${err.message}`); return false; }
    if (now === this.shown) return false;
    this.shown = now;
    this.rev++;
    for (const res of this.clients) res.write(`event: change\ndata: ${this.rev}\n\n`);
    return true;
  }

  _watch() {
    const soon = () => { clearTimeout(this.timer); this.timer = setTimeout(() => { this._watchDirs(soon); this.refresh(); }, 60); };
    this.watchers = new Map();
    this._watchDirs(soon);
    // WHY a slow read as well: a network folder or a sync tool can pass the watcher by
    this.poll = setInterval(() => this.refresh(), 2000);
    this.poll.unref();
  }

  /** One non-recursive watcher per folder of notes. WHY not `recursive: true`: on Linux Node builds it from a watcher per file, and a file
      replaced by a rename (this server's own write, and Obsidian's) drops out of it: a later hand edit then waited for the slow read (measured:
      1.2 s and 2.3 s; a watcher on the folder sees 80 ms). */
  _watchDirs(soon) {
    const dirs = new Set([this.folder]);
    const walk = (dir) => { for (const f of readdirSync(dir, { withFileTypes: true })) if (f.isDirectory() && !f.name.startsWith('.') && f.name !== ATTACHMENTS) { dirs.add(join(dir, f.name)); walk(join(dir, f.name)); } };
    walk(this.folder);
    for (const [dir, w] of this.watchers) if (!dirs.has(dir)) { w.close(); this.watchers.delete(dir); }
    for (const dir of dirs) {
      if (this.watchers.has(dir)) continue;
      try { this.watchers.set(dir, watch(dir, soon)); } catch (err) { console.error(`${dir}: not watched (${err.message}), read every 2 s`); }
    }
  }

  /** The new text, through a temp file and a rename: a reader sees the old file or the new one, never half of one. */
  write(file, text) {
    mkdirSync(dirname(file), { recursive: true });
    const temp = join(dirname(file), `.${basename(file)}.${process.pid}.tmp`);
    writeFileSync(temp, text);
    renameSync(temp, file);
  }

  noteOf(id) {
    const file = this.path(`${id}.md`);
    if (!existsSync(file)) throw new Refused(`There is no note ${id}.`);
    return file;
  }

  // ------------------------------------------------------------------ what the page's hooks ask
  edit({ id, set, was = {} }) {
    const file = this.noteOf(id);
    const base = parseBase(this.baseText());
    const lay = layoutOf(base);
    const { properties } = buildRows(this.notes(), base);
    const before = readFileSync(file, 'utf8');
    const held = { ...readNote(before, lay).values, page: readNote(before, lay).page };
    let text = before;
    for (const [property, value] of Object.entries(set)) {
      if (property === 'name') throw new Refused('A note\'s name is its file name: rename it in Obsidian, which keeps the links to it right.');
      if (property in was && !same(held[property], was[property])) throw new Refused(`${property} changed on disk since this page read it. It now reads: ${String(held[property] ?? '').slice(0, 80)}`);
      if (property === 'page') { text = setPage(text, value === null ? '' : String(value), lay); continue; }
      // a section this note has not got yet is written under the name the other notes give it
      text = setValue(text, property, typed(value), { ...lay, place: lay.places.get(property) || 'top', label: properties[property]?.label || property });
    }
    if (text !== before) { this.write(file, text); this.refresh(); }
    return { ok: true };
  }

  add({ set = {} }) {
    const base = parseBase(this.baseText());
    const lay = layoutOf(base);
    const words = String(set.name ?? Object.values(set).find((v) => typeof v === 'string' && v.trim()) ?? '').trim();
    const stem = words.replace(/[\\/:*?"<>|#^[\]\n\r\t]+/g, ' ').replace(/^[.\s]+/, '').trim().slice(0, 100);
    if (!stem) throw new Refused('A new note needs a name.');
    let id = stem;
    for (let n = 2; existsSync(this.path(`${id}.md`)); n++) id = `${stem} ${n}`;
    let text = '';
    for (const id2 of lay.order) if (set[id2] !== undefined) text = setValue(text, id2, typed(set[id2]), { ...lay, place: lay.places.get(id2) || 'top', label: (base.properties?.[id2]?.displayName) || id2 });
    for (const [k, v] of Object.entries(set)) if (k !== 'name' && k !== 'page' && !lay.order.includes(k)) text = setValue(text, k, typed(v), { ...lay, place: 'top' });
    if (set.page) text = setPage(text, String(set.page), lay);
    this.write(this.path(`${id}.md`), text);
    this.refresh();
    return { ok: true, id };
  }

  /** A pasted or dropped picture: kept beside the notes, named by its bytes so the same paste is one file. */
  attach(name, bytes) {
    const ext = extname(name).toLowerCase();
    if (!MEDIA.has(ext)) throw new Refused(`${ext || 'That file'} is not an image, a video or a PDF.`);
    const stem = basename(name, extname(name)).replace(/[^\p{L}\p{N}_-]+/gu, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'file';
    const rel = `${ATTACHMENTS}/${stem}-${createHash('sha256').update(bytes).digest('hex').slice(0, 8)}${ext}`;
    const file = this.path(rel);
    if (!existsSync(file)) this.write(file, bytes);
    const kind = ['.mp4', '.webm', '.mov'].includes(ext) ? 'video' : 'image';
    return { ok: true, attachment: { url: `file/${rel}`, ref: rel, kind, name } };
  }

  /** Move a property in every file, or say what that would do (`dry`). `text`: the .base with the new layout in it. */
  place({ property, to, dry, text }) {
    if (!PLACES.includes(to)) throw new Refused(`${to} is not a place on the page.`);
    const oldBase = parseBase(this.baseText());
    const newBase = parseBase(text);
    const from = layoutOf(oldBase);
    const into = layoutOf(newBase);
    const { properties } = buildRows(this.notes(), oldBase);
    const p = properties[property];
    if (!p) throw new Refused(`${property} is not a property of these notes.`);
    const label = p.label || property;
    const kind = p.type === 'text' && (p.constraints || p.labels || p.display === 'badge') ? 'select' : p.type;
    // WHY the value stays typed: docs/CONTRACT.md §46. The page may draw it as a heading; that is the layout's, and no file changes
    if (!fitsHeading(p)) {
      if (!dry) this.saveBase(text);
      const drawn = to === 'top' ? 'in the property list' : 'as a section';
      return { ok: true, changes: 0, total: this.notes().length, layoutOnly: true, note: `${label} is a ${kind}: you sort and filter by it, so its value stays in the frontmatter of every file. The page draws it ${drawn}; 0 files change.` };
    }
    const plan = planMove(this.notes(), property, to, from, into, { label: oldBase.properties?.[property]?.displayName });
    const where = to === 'top' ? 'the frontmatter' : 'an H1 section';
    if (plan.refused.length) return { ok: false, changes: 0, total: plan.total, refused: plan.refused, reason: `${plan.refused.length} of ${plan.total} files cannot move: ${plan.refused[0].id}: ${plan.refused[0].reason}. Nothing was changed.` };
    if (!dry) {
      for (const f of plan.files) this.write(this.noteOf(f.id), f.text);
      this.write(this.basePath(), text);
      this.refresh();
    }
    return { ok: true, changes: plan.changed, total: plan.total, note: `${label} moves to ${where} in ${plan.changed} of ${plan.total} files.${plan.unchanged ? ` The other ${plan.unchanged} have nothing to move.` : ''}` };
  }

  saveBase(text) {
    parseBase(text);
    this.write(this.basePath(), text);
    this.refresh();
    return { ok: true };
  }
}

const same = (a, b) => { const e = (v) => v === null || v === undefined || v === ''; return (e(a) && e(b)) || JSON.stringify(a) === JSON.stringify(b); };
/** A rich cell's words: a media cell hands {value, attachments}; the note keeps the words. */
const typed = (v) => (v !== null && typeof v === 'object' && !Array.isArray(v) && 'value' in v ? v.value : v);

// ---------------------------------------------------------------------- the server
export function serve(folders, { vault = null } = {}) {
  const dbs = new Map();
  for (const f of folders) { const n = new Notes(f, vault); dbs.set(n.name, n); }
  const first = [...dbs.values()][0];
  const allowed = () => { const p = server.address().port; return new Set([`127.0.0.1:${p}`, `localhost:${p}`]); };
  const json = (res, code, body) => { res.writeHead(code, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' }).end(JSON.stringify(body)); };
  const sendFile = (res, file) => {
    if (!existsSync(file) || !statSync(file).isFile()) { res.writeHead(404, { 'content-type': 'text/plain' }).end('not found'); return; }
    res.writeHead(200, { 'content-type': TYPES[extname(file).toLowerCase()] || 'application/octet-stream', 'cache-control': 'no-cache', 'x-content-type-options': 'nosniff' });
    createReadStream(file).pipe(res);
  };
  const body = (req, limit) => new Promise((ok, no) => {
    const parts = [];
    let size = 0;
    req.on('data', (c) => { size += c.length; if (size > limit) { no(new Refused('That is too large.')); req.destroy(); } else parts.push(c); });
    req.on('end', () => ok(Buffer.concat(parts)));
    req.on('error', no);
  });
  const server = createServer(async (req, res) => {
    // WHY the Host check on every request: a site that rebinds its name to 127.0.0.1 must not read the notes
    if (!allowed().has(req.headers.host)) { res.writeHead(403, { 'content-type': 'text/plain' }).end('wrong host'); return; }
    const url = new URL(req.url, 'http://x');
    let path;
    try { path = decodeURIComponent(url.pathname); } catch { res.writeHead(400).end(); return; }
    try {
      if (req.method === 'POST') {
        // WHY exact origin and a JSON or octet body: a form on any other page can POST here, but it cannot set either
        const origin = req.headers.origin;
        const site = req.headers['sec-fetch-site'];
        if (!origin || !allowed().has(origin.replace(/^http:\/\//, '')) || !origin.startsWith('http://') || (site && site !== 'same-origin')) { json(res, 403, { ok: false, reason: 'Writes are taken only from this page.' }); return; }
        const m = /^\/db\/([^/]+)\/(edit|add|place|base|file)$/.exec(path);
        const db = m && dbs.get(m[1]);
        if (!db) { json(res, 404, { ok: false, reason: 'No such folder.' }); return; }
        const type = String(req.headers['content-type'] || '');
        if (m[2] === 'file') {
          if (!type.startsWith('application/octet-stream')) { json(res, 415, { ok: false, reason: 'A file is sent as bytes.' }); return; }
          json(res, 200, db.attach(url.searchParams.get('name') || 'file', await body(req, MAX_FILE)));
          return;
        }
        if (!type.startsWith('application/json')) { json(res, 415, { ok: false, reason: 'Send JSON.' }); return; }
        const ask = JSON.parse((await body(req, 8 * 1024 * 1024)).toString('utf8'));
        json(res, 200, m[2] === 'edit' ? db.edit(ask) : m[2] === 'add' ? db.add(ask) : m[2] === 'place' ? db.place(ask) : db.saveBase(ask.text));
        return;
      }
      if (req.method !== 'GET' && req.method !== 'HEAD') { res.writeHead(405).end(); return; }
      if (path === '/') { sendFile(res, join(PAGE, 'index.html')); return; }
      if (path === '/host.js') { sendFile(res, join(PAGE, 'host.js')); return; }
      if (path === '/dbs') { json(res, 200, { dbs: [...dbs.keys()], first: first.name }); return; }
      if (path.startsWith('/kit/')) {
        const file = resolve(KIT, `.${path.slice(4)}`);
        if (!file.startsWith(KIT + sep)) { res.writeHead(403).end(); return; }
        sendFile(res, file);
        return;
      }
      const m = /^\/db\/([^/]+)\/(dataset|events|file\/.+|find\/.+)$/.exec(path);
      const db = m && dbs.get(m[1]);
      if (!db) { res.writeHead(404, { 'content-type': 'text/plain' }).end('not found'); return; }
      if (m[2] === 'dataset') { json(res, 200, { rev: db.rev, ...JSON.parse(db.shown) }); return; }
      if (m[2] === 'events') {
        res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-store', connection: 'keep-alive' });
        res.write(`event: change\ndata: ${db.rev}\n\n`);
        db.clients.add(res);
        req.on('close', () => db.clients.delete(res));
        return;
      }
      if (m[2].startsWith('file/')) {
        const file = db.path(m[2].slice(5));
        if (!MEDIA.has(extname(file).toLowerCase())) { res.writeHead(403, { 'content-type': 'text/plain' }).end('not a media file'); return; }
        sendFile(res, file);
        return;
      }
      // ![[name.png]]: Obsidian finds an embed by its name, wherever it sits
      const name = basename(m[2].slice(5));
      const hit = [ATTACHMENTS, '.'].map((d) => join(db.folder, d, name)).find((f) => existsSync(f));
      if (!hit || !MEDIA.has(extname(hit).toLowerCase())) { res.writeHead(404, { 'content-type': 'text/plain' }).end('not found'); return; }
      sendFile(res, hit);
    } catch (err) {
      if (err instanceof Refused) { json(res, req.method === 'POST' ? 200 : 403, { ok: false, reason: err.message }); return; }
      console.error(err);
      json(res, 500, { ok: false, reason: err.message });
    }
  });
  return { server, dbs, close() { for (const d of dbs.values()) { for (const w of d.watchers.values()) w.close(); clearTimeout(d.timer); clearInterval(d.poll); for (const c of d.clients) c.end(); } server.close(); } };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const at = args.indexOf('--port');
  const wanted = at >= 0 ? Number(args[at + 1]) : Number(process.env.PORT || 4531);
  const opt = (name) => { const i = args.indexOf(name); return i >= 0 ? { i, value: args[i + 1] } : null; };
  const vaultName = opt('--vault'), vaultRoot = opt('--vault-root');
  if (!!vaultName !== !!vaultRoot) { console.error('--vault and --vault-root go together'); process.exit(2); }
  const taken = new Set([at + 1, vaultName && vaultName.i + 1, vaultRoot && vaultRoot.i + 1].filter((i) => i > 0));
  const folders = args.filter((a, i) => !a.startsWith('--') && !taken.has(i));
  if (!folders.length) { console.error('usage: node tools/serve-md.mjs <folder> [<folder> ...] [--port N]'); process.exit(2); }
  if (!existsSync(join(KIT, 'data-ui.js'))) { console.error('dist/ is not built: run  npm --prefix ' + ROOT + ' run build'); process.exit(1); }
  const { server } = serve(folders, { vault: vaultName ? { name: vaultName.value, root: vaultRoot.value } : null });
  server.on('error', (err) => { console.error(err.message); process.exit(1); });
  server.on('listening', () => console.log(`data-ui notes: http://127.0.0.1:${server.address().port}/  (${folders.length} folder${folders.length > 1 ? 's' : ''})`));
  server.listen(wanted, '127.0.0.1');
}
