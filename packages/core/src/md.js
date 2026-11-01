/* The markdown a data cell, a view's intro or a README needs, and no more: headings, paragraphs, lists, block quotes,
   fenced code, pipe tables, **bold**, *italic*, `code` and [links](url). Everything is escaped first, so a cell can
   never inject markup.
   From lane/dashboards' packages/dashboard/src/md.js (541bdc8, PEP 0004 §7), grown by fenced code and tables for a
   README (docs/CONTRACT.md §16). WHY ours, ~70 lines: no markdown library is installed (package.json is the
   orchestrator's); `marked` (MIT) is the part to take if this grows. When lane/dashboards lands, its text panels import
   this module instead of keeping a second copy. */

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function inlineMd(text, opts) {
  const codes = [];
  const held = [];
  // §46: an image is the page's own HTML, so it steps aside before the escape, and comes back after it
  const hold = (html) => { held.push(html); return `\u0001${held.length - 1}\u0001`; };
  // WHY split on code spans: a wikilink written in backticks is being talked about, not linked
  const swap = (words) => {
    let t = words;
    if (opts.image) t = t.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_, alt, src) => hold(opts.image(src, alt, false))).replace(/!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]/g, (_, name) => hold(opts.image(name.trim(), name.trim(), true)));
    if (opts.wikilink) t = t.replace(/\[\[([^\]|]+)(?:\|([^\]]*))?\]\]/g, (_, target, alias) => hold(opts.wikilink(target.trim(), alias === undefined ? null : alias.trim())));
    return t;
  };
  const shown = opts && (opts.image || opts.wikilink) ? text.split(/(`[^`]+`)/).map((part, i) => (i % 2 ? part : swap(part))).join('') : text;
  let s = esc(shown).replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, href) => {
    const safe = /^(https?:|file:|\.{0,2}\/|#|[\w-]+\.html?)/i.test(href) && !/^javascript:/i.test(href) ? href : '#';
    return `<a href="${safe}">${label}</a>`;
  });
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');
  s = s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[Number(i)]}</code>`);
  return held.length ? s.replace(/\u0001(\d+)\u0001/g, (_, i) => held[Number(i)]) : s;
}

const cellsOf = (line) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());

/** Markdown text -> HTML (escaped). `opts.image(src, alt, embed)`: the HTML for `![alt](src)` and Obsidian's `![[src]]` (embed true);
    `opts.wikilink(target, alias)`: the HTML for `[[target]]` and `[[target|alias]]`, a `#heading` inside the target. With neither they stay words, as they always have. `opts.breaks`: a line break in a paragraph is one on the page, as Obsidian draws it. */
export function markdown(text, opts = null) {
  const inline = (t) => inlineMd(t, opts);
  const out = [];
  let list = null, para = [], quote = [], fence = null, table = null;
  const flush = () => {
    if (para.length) { out.push(`<p>${opts && opts.breaks ? para.map(inline).join('<br>') : inline(para.join(' '))}</p>`); para = []; }
    if (list) { out.push(`<${list.tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join('')}</${list.tag}>`); list = null; }
    if (quote.length) { out.push(`<blockquote>${inline(quote.join(' '))}</blockquote>`); quote = []; }
    if (table) {
      const [head, ...body] = table;
      out.push(`<table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${body.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`);
      table = null;
    }
  };
  for (const raw of String(text || '').split('\n')) {
    const line = raw.trimEnd();
    let m;
    if (fence) {
      if (/^\s*```/.test(line)) { out.push(`<pre><code>${esc(fence.join('\n'))}</code></pre>`); fence = null; } else fence.push(raw);
      continue;
    }
    if (/^\s*```/.test(line)) { flush(); fence = []; continue; }
    if (/^\s*\|.*\|\s*$/.test(line)) {
      if (!table) { flush(); table = []; }
      if (!/^\s*\|[\s:|-]+\|\s*$/.test(line)) table.push(cellsOf(line)); // the |---| rule is not a row
      continue;
    }
    if (table) flush();
    if (!line.trim()) { flush(); continue; }
    if ((m = /^(#{1,4})\s+(.*)$/.exec(line))) { flush(); const n = Math.min(6, m[1].length + 1); out.push(`<h${n}>${inline(m[2])}</h${n}>`); continue; }
    if ((m = /^\s*[-*]\s+(.*)$/.exec(line)) || (m = /^\s*\d+[.)]\s+(.*)$/.exec(line))) {
      const tag = /^\s*\d/.test(line) ? 'ol' : 'ul';
      if (para.length || quote.length || (list && list.tag !== tag)) flush();
      if (!list) list = { tag, items: [] };
      list.items.push(m[1]);
      continue;
    }
    if ((m = /^>\s?(.*)$/.exec(line))) { if (para.length || list) flush(); quote.push(m[1]); continue; }
    if (list && /^\s{2,}\S/.test(raw)) { list.items[list.items.length - 1] += ' ' + line.trim(); continue; }
    if (list || quote.length) flush();
    para.push(line.trim());
  }
  if (fence) out.push(`<pre><code>${esc(fence.join('\n'))}</code></pre>`);
  flush();
  return out.join('\n');
}
