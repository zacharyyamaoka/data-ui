// What the publisher treats as text and as a home path: ONE definition, imported by tools/publish-site.mjs (which
// redacts and refuses with it) and by tests/unit/no-home-paths.test.mjs (which gates the raw gallery fixtures with it).
// WHY shared (judge round 3 #3, reports/media/audits/2026-10-28-dashboards-judge-r3.md): the gate had its own shorter
// extension list (no .py, .svg, .xml, .js …) and a narrower pattern (it needed a trailing slash, so "/home/alice" and
// file:///home/alice/… slipped past), so it passed files the publisher would have refused.

/** The extensions publish-site.mjs reads as text (redacts, scans); everything else is copied as bytes. */
export const TEXT = new Set(['.html', '.js', '.mjs', '.css', '.json', '.jsonl', '.base', '.md', '.txt', '.map', '.svg', '.csv', '.yaml', '.yml', '.xml', '.py', '.tsv']);

/** Redaction: "/home/<user>/x" → "~/x" (HOME), then a bare "/home/<user>" before a delimiter → "~" (HOME_BARE). */
export const HOME = /\/home\/[a-z_][a-z0-9_-]*\//g;
export const HOME_BARE = /\/home\/[a-z_][a-z0-9_-]*(?=[\s"'`)\]},;:]|$)/g;

/** Refusal: any home-shaped path left after redaction — /home/<name> (bare, inside a file:// URI, anywhere),
    /Users/<name>, C:\Users\<name>, /tmp/claude scratch paths. */
export const HOME_LEFT = /\/home\/[a-z_][a-z0-9_-]*|\/Users\/[A-Za-z]|C:\\\\?Users\\\\?[A-Za-z]|\/tmp\/claude/;

/** Every home-shaped path in `text`, as the exact token (from the match to the next delimiter) → its count. */
export function homeTokens(text) {
  const out = new Map();
  const re = new RegExp(HOME_LEFT.source, 'g');
  for (let m; (m = re.exec(text));) {
    const rest = text.slice(m.index);
    const end = rest.search(/[\s"'`<>()[\]{},;]/);
    const token = end < 0 ? rest : rest.slice(0, end);
    out.set(token, (out.get(token) || 0) + 1);
  }
  return out;
}

/** Key-shaped strings and secret-named assignments, the publisher's refusals (tools/publish-site.mjs). */
export const KEY_SHAPED = /\bsk-[A-Za-z0-9_-]{20,}|\bghp_[A-Za-z0-9]{20,}|\bgh[ousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{30,}|\bxox[abprs]-[A-Za-z0-9-]{10,}|\b[rs]k_live_[0-9a-zA-Z]{16,}|\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.|-----BEGIN [A-Z ]*PRIVATE KEY-----/;
export const SECRET_NAMED = /["']?\b(?:password|passwd|api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|auth[_-]?token)["']?\s*[:=]\s*["'][^"'\s]{8,}["']/i;
/** An email address (the publisher leaves the kit's third-party authors alone; a history scan lists every one). */
export const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}/;
/** A phone number written as one: a +country code, or a parenthesised area code. Bare digit runs are measurements. */
export const PHONE = /\+\d{1,3}[\s.-]?\(?\d{2,4}\)?[\s.-]\d{3,4}[\s.-]\d{3,4}\b|\(\d{3}\)\s?\d{3}[\s.-]\d{4}\b/;

/** The rules tools/history-scan.mjs applies on top of the deny list. */
export const HISTORY_RULES = [
  ['home-path', HOME_LEFT],
  ['key-shaped', KEY_SHAPED],
  ['secret-named', SECRET_NAMED],
  ['any-email', EMAIL],
  ['phone', PHONE],
  ['private-record-marker', /robotparts\/user-list@1|robotparts\/composite@1|robotparts-lab-twin-reference\/1/],
  ['account-source', /["']?source_url["']?\s*[:=]\s*["']account:|["']account:[A-Za-z0-9_./-]+["']/],
];
