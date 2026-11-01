// What goes public: one ref's tree, as a snapshot, never this repository's history.
//
//   node tools/public-export.mjs --ref main --out DIR                    the filtered tree in DIR (new or empty)
//   node tools/public-export.mjs --ref main --mirror REPO [--rules F]    one more commit on REPO's main, then the scan
//
// WHY a snapshot (docs/PUBLIC-REPO.md): main's history holds private data that was fixed forward, so no ref of this repository
// can be pushed to a public remote. A snapshot publishes what is true today, and main stays as it is for the lanes landing on it.
// What it does to the tree:
// 1. KEEP_OUT: paths that never leave this machine.
// 2. PLACEHOLDER: other people's images. Each keeps its name and its pixel size and becomes one flat grey, so a page lays out
//    the same. WHY not the real ones: robotparts hosts them "removed on request"
//    (gallery/examples/robotparts-photos/README.md), which a public git history cannot honour, and the repository's MIT
//    licence does not cover them.
// 3. the owner's home folder becomes ~ in every text file, by tools/publish-rules.mjs's own list of text extensions.
// 4. a block between two marker comments goes (tools/publish-site.mjs has the shape; the opening one names the line left
//    in its place): a gate's private patterns are in the open otherwise.
// 5. no-home-paths.baseline.json loses the owner's paths: step 3 removed what they counted, and that baseline only shrinks.
// --mirror then commits as the noreply identity and runs tools/history-scan.mjs on the mirror's whole history; a hit
// exits 1, and nothing here ever pushes. Pushing is a person's decision (docs/PUBLIC-REPO.md).
import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, extname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { crc32, deflateSync } from 'node:zlib';
import { TEXT } from './publish-rules.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
export const OWNER = process.env.DATA_UI_OWNER_HOME || '~';
export const IDENTITY = { name: 'Zach Yamaoka', email: 'zacharyyamaoka@users.noreply.github.com' };

export const KEEP_OUT = [
  ['reports/', 'work reports: internal reviews and screenshots, never source'],
  ['.claude/', "the feedback ledger: Zach's ratings, for the agents working here"],
  ['gallery/examples/dataclass-viewer/source/', 'its producer names the private inputs the synthetic ones replaced'],
  ['gallery/md-pages/', "Zach's real feedback and its screenshots: a picture no text scan reads, and one names a private supplier contact"],
];
export const PLACEHOLDER = [
  'gallery/examples/robotparts-photos/media/',
  'gallery/examples/robotparts-actuators/photos/',
  'gallery/examples/robotparts-compare/photos/',
  'gallery/examples/filters-gallery/logos/',
  'gallery/examples/design-babble/stills/',
  'bench/scenarios/robotparts-photos/media/',
  'bench/scenarios/robotparts-actuators/photos/',
  'bench/scenarios/actuator-charts/photos/',
];
const BASELINE = 'tests/unit/no-home-paths.baseline.json';
// WHY built from parts: this file goes through the same pass, and its own source must not read as a marker
const MARK = ['public-export', 'strip'].join(': ');
const STRIP = new RegExp(`[^\\n]*${MARK}-begin => ([^\\n]*)\\n[\\s\\S]*?[^\\n]*${MARK}-end[^\\n]*\\n`, 'g');

const git = (repo, args, opts = {}) => {
  const r = spawnSync('git', ['-C', repo, ...args], { encoding: 'utf8', maxBuffer: 1 << 30, ...opts });
  if (r.status !== 0) throw new Error(`git ${args.join(' ')}: ${r.stderr || r.status}`);
  return r.stdout.trim();
};

const walk = (dir, out = []) => {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out); else out.push(p);
  }
  return out;
};

/** An image's [width, height] from its header: PNG, JPEG, or any of WebP's three forms. */
export function imageSize(b) {
  if (b.toString('latin1', 1, 4) === 'PNG') return [b.readUInt32BE(16), b.readUInt32BE(20)];
  if (b[0] === 0xff && b[1] === 0xd8) {
    for (let at = 2; at < b.length;) {
      const marker = b[at + 1];
      if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker)) return [b.readUInt16BE(at + 7), b.readUInt16BE(at + 5)];
      at += 2 + b.readUInt16BE(at + 2);
    }
  }
  if (b.toString('latin1', 0, 4) === 'RIFF' && b.toString('latin1', 8, 12) === 'WEBP') {
    const form = b.toString('latin1', 12, 16);
    if (form === 'VP8 ') return [b.readUInt16LE(26) & 0x3fff, b.readUInt16LE(28) & 0x3fff];
    if (form === 'VP8L') { const bits = b.readUInt32LE(21); return [(bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1]; }
    if (form === 'VP8X') return [b.readUIntLE(24, 3) + 1, b.readUIntLE(27, 3) + 1];
  }
  throw new Error('not a PNG, JPEG or WebP');
}

/** A flat grey PNG. A browser reads an image by its bytes, so it draws under a .webp or .jpg name too. */
export function greyPng(width, height) {
  const chunk = (type, data) => {
    const body = Buffer.concat([Buffer.from(type, 'latin1'), data]);
    const out = Buffer.alloc(8 + data.length + 4);
    out.writeUInt32BE(data.length, 0);
    body.copy(out, 4);
    out.writeUInt32BE(crc32(body), 8 + data.length);
    return out;
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8; // 8-bit grey
  const row = Buffer.alloc(width + 1, 0x9a);
  row[0] = 0;
  const rows = Buffer.concat(Array.from({ length: height }, () => row));
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', header), chunk('IDAT', deflateSync(rows, { level: 9 })), chunk('IEND', Buffer.alloc(0))]);
}

/** The same picture frame, nothing of the picture: the original's size attributes on an empty grey SVG. */
function greySvg(text) {
  const open = /<svg\b[^>]*>/i.exec(text);
  const keep = ['width', 'height', 'viewBox'].map((name) => (new RegExp(`\\b${name}="[^"]*"`).exec(open ? open[0] : '') || [''])[0]).filter(Boolean).join(' ');
  return `<svg xmlns="http://www.w3.org/2000/svg" ${keep}><rect width="100%" height="100%" fill="#9aa0a6"/></svg>\n`;
}

/** Redact, in a text: the owner's home folder, as a path and bare. */
export function redact(text, owner = OWNER) {
  const esc = owner.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return text.replace(new RegExp(`${esc}/`, 'g'), '~/').replace(new RegExp(`${esc}(?![\\w-])`, 'g'), '~');
}

/** The filtered tree of `ref` in `out`; returns what happened to it. */
export function exportTree({ repo = ROOT, ref = 'main', out, owner = OWNER }) {
  const commit = git(repo, ['rev-parse', '--verify', `${ref}^{commit}`]);
  mkdirSync(out, { recursive: true });
  if (readdirSync(out).length) throw new Error(`${out} is not empty`);
  const archive = spawnSync('git', ['-C', repo, 'archive', '--format=tar', commit], { maxBuffer: 2 ** 32 });
  if (archive.status !== 0) throw new Error(`git archive: ${archive.stderr}`);
  const untar = spawnSync('tar', ['-x', '-C', out], { input: archive.stdout, maxBuffer: 2 ** 32 });
  if (untar.status !== 0) throw new Error(`tar: ${untar.stderr}`);
  const did = { commit, keptOut: 0, placeholders: 0, redactedFiles: 0, stripped: [] };
  for (const [path] of KEEP_OUT) {
    const p = join(out, path);
    if (existsSync(p)) { did.keptOut += walk(p).length; rmSync(p, { recursive: true }); }
  }
  for (const path of PLACEHOLDER) {
    const dir = join(out, path);
    if (!existsSync(dir)) continue;
    for (const f of walk(dir)) {
      if (extname(f).toLowerCase() === '.svg') writeFileSync(f, greySvg(readFileSync(f, 'utf8')));
      else {
        try { writeFileSync(f, greyPng(...imageSize(readFileSync(f)))); } catch (e) { throw new Error(`no placeholder for ${relative(out, f)}: ${e.message}; add one, or keep the file out`); }
      }
      did.placeholders++;
    }
  }
  for (const f of walk(out)) {
    if (!TEXT.has(extname(f).toLowerCase())) continue;
    const text = readFileSync(f, 'utf8');
    let next = redact(text, owner);
    // WHY the includes first: the pattern starts with [^\n]*, quadratic on a megabyte of JSON on one line
    if (next.includes(`${MARK}-begin =>`)) {
      next = next.replace(STRIP, (_, left) => `${left} // private patterns stay outside this repository\n`);
      did.stripped.push(relative(out, f));
    }
    if (next !== text) { writeFileSync(f, next); did.redactedFiles++; }
  }
  if (existsSync(join(out, BASELINE))) {
    // the file went through redact() above, so the owner's paths read ~ now; what is left counts other people's folders
    const left = Object.entries(JSON.parse(readFileSync(join(out, BASELINE), 'utf8'))).map(([file, tokens]) => [file, Object.fromEntries(Object.entries(tokens).filter(([token]) => !token.startsWith('~')))]);
    writeFileSync(join(out, BASELINE), `${JSON.stringify(Object.fromEntries(left.filter(([, tokens]) => Object.keys(tokens).length)), null, 1)}\n`);
  }
  return did;
}

/** One commit of `tree` on `mirror`'s main: the mirror's files become the tree's, a first run creates the repository. */
export function commitMirror({ tree, mirror, message }) {
  if (!existsSync(join(mirror, '.git'))) {
    mkdirSync(mirror, { recursive: true });
    git(mirror, ['init', '-q', '-b', 'main']);
  }
  for (const name of readdirSync(mirror)) if (name !== '.git') rmSync(join(mirror, name), { recursive: true, force: true });
  cpSync(tree, mirror, { recursive: true });
  // WHY `add .` here and nowhere else: the mirror's index is this script's own; no peer shares it
  git(mirror, ['add', '.']);
  const env = { ...process.env, GIT_AUTHOR_NAME: IDENTITY.name, GIT_AUTHOR_EMAIL: IDENTITY.email, GIT_COMMITTER_NAME: IDENTITY.name, GIT_COMMITTER_EMAIL: IDENTITY.email };
  const changed = spawnSync('git', ['-C', mirror, 'diff', '--cached', '--quiet']).status !== 0 || spawnSync('git', ['-C', mirror, 'rev-parse', '-q', '--verify', 'HEAD']).status !== 0;
  if (changed) git(mirror, ['commit', '-q', '-m', message], { env });
  return git(mirror, ['rev-parse', 'HEAD']);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const args = process.argv.slice(2);
  const one = (flag) => { const i = args.indexOf(flag); return i >= 0 ? args[i + 1] : undefined; };
  const ref = one('--ref') || 'main';
  const repo = resolve(one('--repo') || ROOT);
  const out = one('--out');
  const mirror = one('--mirror');
  if (!out === !mirror) { console.error('usage: public-export.mjs --ref REF (--out DIR | --mirror REPO [--rules FILE ...])'); process.exit(2); }
  const tree = out ? resolve(out) : mkdtempSync(join(tmpdir(), 'data-ui-public-'));
  try {
    const did = exportTree({ repo, ref, out: tree });
    console.log(`public-export: ${ref} @ ${did.commit.slice(0, 7)}: ${did.keptOut} files kept out, ${did.placeholders} placeholders, ${did.redactedFiles} text files changed, stripped: ${did.stripped.join(', ') || 'nothing'}`);
    if (mirror) {
      const sha = commitMirror({ tree, mirror: resolve(mirror), message: `data-ui @ ${did.commit.slice(0, 7)}` });
      console.log(`public-export: ${resolve(mirror)} main is ${sha.slice(0, 7)}; scanning its whole history`);
      const rules = args.flatMap((a, i) => (a === '--rules' ? ['--rules', args[i + 1]] : []));
      const scan = spawnSync('node', [join(ROOT, 'tools', 'history-scan.mjs'), '--repo', resolve(mirror), ...rules], { stdio: 'inherit' });
      if (scan.status !== 0) { console.error('public-export: the mirror does not pass tools/history-scan.mjs: do not push it'); process.exit(1); }
      console.log('public-export: the mirror passes the history scan. Pushing it is a person\'s decision: docs/PUBLIC-REPO.md');
    }
  } finally {
    if (!out) rmSync(tree, { recursive: true, force: true });
  }
}
