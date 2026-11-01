// The public-data gate: refuse when a file holds a pattern from the deny list (customers, private people, internal
// identifiers). Run before every merge to main and by every deploy (tools/release-check.mjs, tools/publish-site.mjs).
//
//   node tools/deny-scan.mjs --tree          every file git tracks, as on disk (main's whole tree, not only the site)
//   node tools/deny-scan.mjs --dir dist/publish   every text file under a directory (what a deploy uploads)
//
// The list lives OUTSIDE git, in ~/.config/bam/public-deny.txt (or $DATA_UI_DENY): one regex per line, `#` comments,
// Python's leading `(?i)` meaning case-insensitive. WHY outside: the list names the very things it keeps out, and a
// repo whose output is public must not carry it. WHY fail closed: with no list there is no gate, and a deploy then
// stops rather than guessing (data-ui.dev published BAM's kin-sim inputs and, through a lane, customer data in October
// 2026; tools/publish-site.mjs's own DENY covers the first, this list the second).
// A hit is printed as file, line and rule number, the match masked, so the gate's own log does not repeat the secret.
import { execFileSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { extname, join, relative, dirname } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const LIST = process.env.DATA_UI_DENY || join(homedir(), '.config', 'bam', 'public-deny.txt');
const BINARY = new Set(['.png', '.webp', '.jpg', '.jpeg', '.gif', '.glb', '.gltf', '.bin', '.woff', '.woff2', '.ttf', '.ico', '.pdf', '.mp4', '.webm', '.zip', '.gz', '.pmtiles', '.wasm', '.rrd']);

/** The deny list as [{n, re}] (n: its line number in the file). */
export function loadDeny(path = LIST) {
  if (!existsSync(path)) throw new Error(`no deny list at ${path} (set DATA_UI_DENY): refusing, the public-data gate cannot run without it`);
  return readFileSync(path, 'utf8').split('\n').map((line, i) => [i + 1, line.trim()]).filter(([, l]) => l && !l.startsWith('#')).map(([n, l]) => {
    let flags = 'g';
    let src = l;
    const m = /^\(\?([a-z]+)\)/.exec(src);
    if (m) { if (m[1].includes('i')) flags += 'i'; if (m[1].includes('s')) flags += 's'; if (m[1].includes('m')) flags += 'm'; src = src.slice(m[0].length); }
    return { n, re: new RegExp(src, flags) };
  });
}

export const mask = (s) => (s.length <= 2 ? '**' : s[0] + '*'.repeat(Math.min(8, s.length - 2)) + s[s.length - 1]);

/** Every hit of the list in `text`: [{rule, line, match (masked)}]. */
export function scanText(text, rules) {
  const hits = [];
  for (const { n, re } of rules) {
    re.lastIndex = 0;
    for (const m of text.matchAll(re)) {
      hits.push({ rule: n, line: text.slice(0, m.index).split('\n').length, match: mask(m[0]) });
      if (hits.length > 50) return hits;
    }
  }
  return hits;
}

function treeFiles() {
  return execFileSync('git', ['-C', ROOT, 'ls-files', '-z'], { encoding: 'utf8', maxBuffer: 1 << 28 }).split('\0').filter(Boolean).map((f) => join(ROOT, f));
}

function dirFiles(dir) {
  const out = [];
  const walk = (d) => { for (const f of readdirSync(d)) { const p = join(d, f); if (statSync(p).isDirectory()) walk(p); else out.push(p); } };
  walk(dir);
  return out;
}

export function scanFiles(files, rules, base = ROOT) {
  const found = [];
  for (const p of files) {
    if (BINARY.has(extname(p).toLowerCase()) || !existsSync(p)) continue;
    let text;
    try { text = readFileSync(p, 'utf8'); } catch { continue; }
    if (text.includes('\u0000')) continue;
    for (const h of scanText(text, rules)) found.push({ file: relative(base, p), ...h });
  }
  return found;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const args = process.argv.slice(2);
  let rules;
  try { rules = loadDeny(); } catch (e) { console.error(e.message); process.exit(1); }
  const di = args.indexOf('--dir');
  const where = di >= 0 ? join(process.cwd(), args[di + 1]) : null;
  const files = where ? dirFiles(where) : treeFiles();
  const hits = scanFiles(files, rules, where || ROOT);
  const label = where ? relative(ROOT, where) || where : 'the files git tracks (as on disk; a deploy requires them clean)';
  if (hits.length) {
    const byFile = new Map();
    for (const h of hits) { if (!byFile.has(h.file)) byFile.set(h.file, []); byFile.get(h.file).push(h); }
    console.error(`deny-scan: ${hits.length} hit(s) of the deny list in ${byFile.size} file(s) of ${label}:`);
    for (const [f, hs] of byFile) console.error(`- ${f}: ${hs.slice(0, 6).map((h) => `line ${h.line} rule ${h.rule} (${h.match})`).join('; ')}${hs.length > 6 ? `; +${hs.length - 6} more` : ''}`);
    process.exit(1);
  }
  console.log(`deny-scan: ${files.length} files of ${label}, ${rules.length} rules, no hit`);
}
