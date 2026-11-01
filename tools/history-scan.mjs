// The history gate: every blob and every commit a push would publish, through the same rules a deploy applies to the
// site, and more. A public push cannot be recalled, and `git log -p` hands a stranger every file that ever existed, so
// a scan of today's tree (tools/deny-scan.mjs --tree) says nothing about what a push gives away.
//
//   node tools/history-scan.mjs [--repo DIR] [--ref main ...] [--rules FILE ...] [--allow FILE] [--json OUT] [--reveal]
//                               [--max-blob-mib N] [--quiet]
//
// What it reads, for the refs given (default main):
// - every blob `git rev-list --objects` reaches: as text, and a binary one as latin-1, which is how a home path in a
//   GLB's JSON chunk, a PNG text chunk or an MP4's metadata shows up;
// - every path any commit wrote: a name in a file name is published too;
// - every commit's author, committer and message (a clean tree can still carry an address on 449 commits).
// What it applies: the deny list outside git (tools/deny-scan.mjs, fail closed), the publisher's rules
// (tools/publish-rules.mjs), and any --rules FILE, read the same way as the deny list (one regex per line, `#` comments,
// a leading `(?i)`). WHY --rules: a name a repo keeps out cannot be written in that repo; an audit's own terms stay in a
// file beside the deny list. --allow (default tools/history-scan.allow): one regex per line; a match it finds is no hit.
// Synthetic strings only (the gates' own test fixtures), never a real name, or the list becomes the leak.
// What it reports: per rule, the blobs and commits hit, split into "at the tip" (a fix forward removes it) and "history
// only" (only a rewritten or fresh history removes it); per hit the paths, the commit that introduced it and the match
// masked. --reveal writes the raw match and its context into --json, which then belongs in a scratch folder, never in git.
// Exit 1 on any hit, 2 on usage or a missing deny list.
import { spawnSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadDeny, mask } from './deny-scan.mjs';
import { HISTORY_RULES } from './publish-rules.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const ALLOW = join(ROOT, 'tools', 'history-scan.allow');
const HITS_PER_RULE_PER_BLOB = 8;

const git = (repo, args, opts = {}) => {
  const r = spawnSync('git', ['-C', repo, ...args], { encoding: 'utf8', maxBuffer: 1 << 30, ...opts });
  if (r.status !== 0) throw new Error(`git ${args.join(' ')}: ${r.stderr || r.status}`);
  return r.stdout;
};

/** Every blob the refs reach, as sha -> size. */
export function reachableBlobs(repo, refs) {
  const listing = git(repo, ['rev-list', '--objects', ...refs]);
  const shas = listing.split('\n').filter(Boolean).map((line) => line.slice(0, line.indexOf(' ') < 0 ? line.length : line.indexOf(' ')));
  const checked = git(repo, ['cat-file', '--batch-check=%(objecttype) %(objectname) %(objectsize)'], { input: shas.join('\n') + '\n' });
  const blobs = new Map();
  for (const line of checked.split('\n')) {
    const [type, sha, size] = line.split(' ');
    if (type === 'blob') blobs.set(sha, Number(size));
  }
  return blobs;
}

/** sha -> {paths, commit}: every path a blob was written to and the first commit that wrote it, over the whole walk,
    merges included. A blob `git rev-list --objects` names once can live at many paths. */
export function blobOrigins(repo, refs) {
  const log = git(repo, ['log', '--reverse', '--format=commit %H', '--raw', '--no-abbrev', '--no-renames', '-m', ...refs]);
  const origins = new Map();
  let commit = null;
  for (const line of log.split('\n')) {
    if (line.startsWith('commit ')) { commit = line.slice(7); continue; }
    if (!line.startsWith(':')) continue;
    const [meta, path] = line.split('\t');
    const fields = meta.split(' ');
    const sha = fields[3];
    if (/^0+$/.test(sha)) continue;
    if (!origins.has(sha)) origins.set(sha, { paths: new Set(), commit });
    origins.get(sha).paths.add(path);
  }
  return origins;
}

/** Blobs the refs' tips hold, as sha -> paths. */
export function tipBlobs(repo, refs) {
  const tip = new Map();
  for (const ref of refs) {
    for (const line of git(repo, ['ls-tree', '-r', ref]).split('\n')) {
      const m = /^\d+ blob ([0-9a-f]{40})\t(.*)$/.exec(line);
      if (!m) continue;
      if (!tip.has(m[1])) tip.set(m[1], new Set());
      tip.get(m[1]).add(m[2]);
    }
  }
  return tip;
}

/** Every blob's bytes, handed to `visit(sha, buffer)`, from one `git cat-file --batch`. */
export function readBlobs(repo, shas, visit) {
  const out = spawnSync('git', ['-C', repo, 'cat-file', '--batch'], { input: shas.join('\n') + '\n', maxBuffer: 2 ** 32 });
  if (out.status !== 0) throw new Error(`git cat-file --batch: ${out.stderr}`);
  const data = out.stdout;
  let at = 0;
  while (at < data.length) {
    const eol = data.indexOf(10, at);
    const [sha, , size] = data.toString('latin1', at, eol).split(' ');
    const start = eol + 1;
    const end = start + Number(size);
    visit(sha, data.subarray(start, end));
    at = end + 1;
  }
}

/** Not an address: an image name or a version pin. In a binary blob a two-letter domain is noise too: "Q@B.csJ" turns up
    in compressed bytes at about one a megabyte, and a real address in a metadata chunk has a longer name. */
export const notAnEmail = (match, binary) => /\.(png|webp|jpe?g|svg|gif)$|@\d/i.test(match) || (binary && match.length < 12);

/** The hits of `rules` in `text`, at most HITS_PER_RULE_PER_BLOB per rule, plus the rule's full count. */
export function scanWith(rules, text, { reveal = false, allow = [], binary = false } = {}) {
  const found = [];
  for (const { id, re } of rules) {
    re.lastIndex = 0;
    let count = 0;
    const samples = [];
    for (const m of text.matchAll(re)) {
      if (m[0] === '') continue;
      if (id === 'any-email' && notAnEmail(m[0], binary)) continue;
      if (allow.some((a) => a.test(m[0]))) continue;
      count++;
      if (samples.length < HITS_PER_RULE_PER_BLOB) {
        const sample = { match: mask(m[0]) };
        if (reveal) { sample.raw = m[0]; sample.context = text.slice(Math.max(0, m.index - 70), m.index + m[0].length + 70).replace(/\s+/g, ' '); }
        samples.push(sample);
      }
    }
    if (count) found.push({ rule: id, count, samples });
  }
  return found;
}

const compile = (source) => {
  let flags = 'g';
  let body = source;
  const m = /^\(\?([a-z]+)\)/.exec(body);
  if (m) { if (m[1].includes('i')) flags += 'i'; if (m[1].includes('s')) flags += 's'; if (m[1].includes('m')) flags += 'm'; body = body.slice(m[0].length); }
  return new RegExp(body, flags);
};

/** The whole scan. Returns {blobs, commits, findings, commitFindings, skipped}. */
export function scanHistory({ repo = ROOT, refs = ['main'], rules, allow = [], reveal = false, maxBlobMib = 64 }) {
  const blobs = reachableBlobs(repo, refs);
  const origins = blobOrigins(repo, refs);
  const tip = tipBlobs(repo, refs);
  const limit = maxBlobMib * 1048576;
  const wanted = [...blobs.keys()].filter((sha) => blobs.get(sha) <= limit);
  const skipped = [...blobs.keys()].filter((sha) => blobs.get(sha) > limit);
  const findings = [];
  readBlobs(repo, wanted, (sha, bytes) => {
    const binary = bytes.includes(0);
    const text = bytes.toString(binary ? 'latin1' : 'utf8');
    for (const hit of scanWith(rules, text, { reveal, allow, binary })) {
      const origin = origins.get(sha) || { paths: new Set(), commit: null };
      findings.push({ ...hit, blob: sha, binary, size: bytes.length, atTip: tip.has(sha), paths: [...(tip.get(sha) || origin.paths)], commit: origin.commit });
    }
  });
  const paths = new Map();
  for (const [sha, origin] of origins) for (const path of origin.paths) if (!paths.has(path)) paths.set(path, { blob: sha, commit: origin.commit });
  for (const [path, origin] of paths) {
    for (const hit of scanWith(rules, path, { reveal, allow })) findings.push({ ...hit, ...origin, inPath: true, binary: false, size: 0, atTip: tip.has(origin.blob), paths: [path] });
  }
  const raw = git(repo, ['log', '--format=%H%x00%an <%ae>%x00%cn <%ce>%x00%B%x00%x01', ...refs]);
  const commitFindings = [];
  let commits = 0;
  for (const record of raw.split('\x01')) {
    const parts = record.replace(/^\n/, '').split('\0');
    if (parts.length < 4) continue;
    commits++;
    const [sha, author, committer, message] = parts;
    for (const [field, text] of [['author', author], ['committer', committer], ['message', message]]) {
      for (const hit of scanWith(rules, text, { reveal, allow })) commitFindings.push({ ...hit, commit: sha, field });
    }
  }
  return { blobs: blobs.size, bytes: [...blobs.values()].reduce((a, b) => a + b, 0), commits, findings, commitFindings, skipped };
}

/** Per rule: blobs at the tip, blobs only in history, commits. */
export function summarize({ findings, commitFindings }) {
  const rows = new Map();
  const row = (rule) => { if (!rows.has(rule)) rows.set(rule, { rule, tip: new Set(), history: new Set(), commits: new Set(), hits: 0 }); return rows.get(rule); };
  for (const f of findings) { const r = row(f.rule); (f.atTip ? r.tip : r.history).add(f.blob); r.hits += f.count; }
  for (const f of commitFindings) { const r = row(f.rule); r.commits.add(f.commit); r.hits += f.count; }
  return [...rows.values()].sort((a, b) => a.rule.localeCompare(b.rule));
}

export function loadRules(denyPath, extraFiles = [], reader = loadDeny) {
  const rules = [];
  for (const { n, re } of reader(denyPath)) rules.push({ id: `deny-list:${n}`, re });
  for (const [id, re] of HISTORY_RULES) rules.push({ id, re: new RegExp(re.source, re.flags.includes('g') ? re.flags : re.flags + 'g') });
  for (const file of extraFiles) {
    for (const { n, re } of reader(file)) rules.push({ id: `${file.split('/').pop()}:${n}`, re });
  }
  return rules;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const args = process.argv.slice(2);
  const many = (flag) => args.flatMap((a, i) => (a === flag ? [args[i + 1]] : []));
  const one = (flag) => many(flag)[0];
  const refs = many('--ref').length ? many('--ref') : ['main'];
  const quiet = args.includes('--quiet');
  let rules, allow;
  try {
    rules = loadRules(undefined, many('--rules'));
    allow = loadDeny(one('--allow') || ALLOW).map(({ re }) => new RegExp(re.source, re.flags.replace('g', '')));
  } catch (e) { console.error(e.message); process.exit(2); }
  const repo = one('--repo') || ROOT;
  const result = scanHistory({ repo, refs, rules, allow, reveal: args.includes('--reveal'), maxBlobMib: Number(one('--max-blob-mib') || 64) });
  const summary = summarize(result);
  if (one('--json')) writeFileSync(one('--json'), JSON.stringify({ refs, ...result, summary: summary.map((r) => ({ rule: r.rule, tip: r.tip.size, history: r.history.size, commits: r.commits.size, hits: r.hits })) }, null, 1));
  console.log(`history-scan: ${refs.join(', ')}: ${result.commits} commits, ${result.blobs} blobs, ${(result.bytes / 1048576).toFixed(1)} MiB, ${rules.length} rules`);
  if (result.skipped.length) console.log(`history-scan: ${result.skipped.length} blob(s) over --max-blob-mib left unread: ${result.skipped.join(', ')}`);
  if (!summary.length) { console.log('history-scan: no hit'); process.exit(0); }
  if (!quiet) {
    console.log('rule'.padEnd(34), 'tip'.padStart(6), 'history'.padStart(8), 'commits'.padStart(8), 'hits'.padStart(8));
    for (const r of summary) console.log(r.rule.padEnd(34), String(r.tip.size).padStart(6), String(r.history.size).padStart(8), String(r.commits.size).padStart(8), String(r.hits).padStart(8));
  }
  process.exit(1);
}
