/* What a markdown cell shows (docs/CONTRACT.md §46): a section's sub-headings, else its first lines, with its embeds as small thumbnails,
   or [image] where there is no room. Pure, and with no import: no DOM and nothing of the kit, so another host can take this one file
   (a separate Obsidian plugin reuses it). tests/unit/markdown-columns.test.mjs holds it to that. */

const MEDIA_LINE = /!\[\[([^\]|]*)(?:\|[^\]]*)?\]\]|!\[([^\]]*)\]\(([^)\s]*)\)/g;
const VIDEO = /\.(mp4|webm|mov)\b/i;

/** A section's sub-headings: [{depth, text}], as written (a source's own numbers stay), depth from 0. Fenced code holds none. */
export function outlineOf(value) {
  const out = [];
  let fence = null;
  for (const line of String(value).split('\n')) {
    const f = /^ {0,3}(`{3,}|~{3,})/.exec(line);
    if (fence) { if (f && f[1][0] === fence[0] && f[1].length >= fence.length) fence = null; continue; }
    if (f) { fence = f[1]; continue; }
    const h = /^(#{2,6})[ \t]+(.*?)[ \t]*(?:[ \t]#+[ \t]*)?$/.exec(line);
    if (h && h[2]) out.push({ level: h[1].length, text: h[2] });
  }
  const top = Math.min(...out.map((x) => x.level));
  return out.map((x) => ({ depth: x.level - top, text: x.text }));
}

/** The pictures and videos a section holds: [{src, alt, embed, video}]. */
export function mediaOf(value) {
  return [...String(value).matchAll(MEDIA_LINE)].map((m) => {
    const src = m[1] ?? m[3];
    return { src, alt: m[1] ?? m[2], embed: m[1] !== undefined, video: VIDEO.test(src) };
  });
}

/** What a section's table cell draws in `lines` lines (docs/CONTRACT.md §46). Derived from the value, never stored. `mode`: 'outline' draws the sub-headings
    when there are any, and falls back to the first lines; 'preview' always draws the first lines. Thumbnails when there is room: two lines' worth, after
    the words. What does not fit is counted in `more`, so nothing is clipped silently. {kind, items, text, more, media}. */
export function sectionCell(value, { mode = 'outline', lines = 3 } = {}) {
  const media = mediaOf(value);
  const heads = mode === 'outline' ? outlineOf(value) : [];
  if (heads.length) {
    const room = heads.length + 2 <= lines && media.length > 0;
    const shown = heads.slice(0, lines);
    return { kind: 'outline', items: shown, more: heads.length - shown.length, media: room ? media : [] };
  }
  const words = String(value).split('\n').map((l) => l.replace(MEDIA_LINE, '').trimEnd()).filter((l) => l.trim());
  const used = Math.min(words.length, lines);
  const room = media.length > 0 && used + 2 <= lines;
  // no room for a picture: it reads [image], where it was, and counts as a line
  const all = room ? words : String(value).split('\n').map((l) => l.replace(MEDIA_LINE, (m, a, b, c) => (VIDEO.test(a ?? c) ? '[video]' : '[image]')).trimEnd()).filter((l) => l.trim());
  return { kind: 'preview', text: all.slice(0, lines).join('\n'), more: Math.max(0, all.length - lines), media: room ? media : [] };
}

/** Whether the cell is drawn from the section rather than holding it: its outline. WHY it matters: such a cell is not edited in place. */
export const isDerivedCell = (value, display) => display === 'outline' && typeof value === 'string' && outlineOf(value).length > 0;
