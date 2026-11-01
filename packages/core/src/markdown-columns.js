/* The markdown property type's H1 columns (docs/CONTRACT.md §46). Zach, 2026-10-31: "in data-ui. we have an option that basically
   converts the H1s into columns and then summarises there contents inside. I call it a markdown property type".

   One text property holds a whole note; `columns: h1` on it (in the data or the .base file) makes each H1 a column of `kind: markdown`,
   whose value is what is under that heading. An edit of such a cell is spliced back into the one property, so a host keeps one value,
   and bytes it did not touch stay. Pure: no DOM. ATX H1s only, none inside a fence: the rule tools/md-notes.mjs reads a file by. */

const FENCE = /^ {0,3}(`{3,}|~{3,})/;
const H1 = /^#[ \t]+(.*?)[ \t]*(?:[ \t]#+[ \t]*)?$/;

/** {lead, sections: [{heading, body, start, bodyStart, end}]}: what comes before the first H1, and each H1 with its body, blank lines
    around it trimmed. `start`..`end` are offsets into the text, `bodyStart` just after the heading's line. */
export function h1Sections(text) {
  const src = String(text ?? '');
  const heads = [];
  let at = 0, fence = null;
  while (at <= src.length) {
    const nl = src.indexOf('\n', at);
    const end = nl < 0 ? src.length : nl;
    const line = src.slice(at, end).replace(/\r$/, '');
    const f = FENCE.exec(line);
    if (fence) { if (f && f[1][0] === fence[0] && f[1].length >= fence.length && !line.slice(f[0].length).trim()) fence = null; }
    else if (f) fence = f[1];
    else {
      const h = H1.exec(line);
      if (h && h[1]) heads.push({ heading: h[1], start: at, bodyStart: nl < 0 ? src.length : nl + 1 });
    }
    if (nl < 0) break;
    at = nl + 1;
  }
  const sections = heads.map((h, i) => {
    const end = i + 1 < heads.length ? heads[i + 1].start : src.length;
    return { ...h, end, body: src.slice(h.bodyStart, end).replace(/^(?:[ \t]*\r?\n)+/, '').replace(/\s+$/, '') };
  });
  return { lead: src.slice(0, heads.length ? heads[0].start : src.length).replace(/\s+$/, ''), sections };
}

/** `text` with the body under `heading` set to `value`; every other byte stays. A heading it lacks is added at the end. */
export function setH1(text, heading, value) {
  const src = String(text ?? '');
  const eol = src.includes('\r\n') ? '\r\n' : '\n';
  const body = String(value ?? '').replace(/\s+$/, '');
  const hit = h1Sections(src).sections.find((s) => s.heading === heading);
  if (!hit) {
    const lead = src.replace(/\s+$/, '');
    return `${lead}${lead ? `${eol}${eol}` : ''}# ${heading}${eol}${body ? `${eol}${body}${eol}` : ''}`;
  }
  const last = hit.end === src.length;
  return `${src.slice(0, hit.bodyStart)}${body ? `${eol}${body}${eol}` : ''}${last ? '' : eol}${src.slice(hit.end)}`;
}

const slug = (s) => String(s).toLowerCase().normalize('NFKD').replace(/[^\p{L}\p{N}]+/gu, '_').replace(/^_+|_+$/g, '') || 'section';

/** Each property that asks for it, as one column per H1, in place: the headings it lists under `headings` (shown even when a row lacks
    one), then any other in the order first met. `from` names the property's `.base` entries, which win. Returns the dataset. */
export function expandH1(dataset, from = null) {
  const props = dataset && dataset.properties;
  if (!props) return dataset;
  const meta = (id) => ({ ...props[id], ...(from && (from[id] || from[`note.${id}`])) });
  for (const id of Object.keys(props)) {
    const p = meta(id);
    if (p.columns !== 'h1' || props[id].h1Of) continue;
    const names = [...(Array.isArray(p.headings) ? p.headings : [])];
    const split = new Map();
    for (const row of dataset.rows || []) {
      const bodies = new Map();
      for (const s of h1Sections(row[id]).sections) { if (!bodies.has(s.heading)) bodies.set(s.heading, s.body); if (!names.includes(s.heading)) names.push(s.heading); }
      split.set(row, bodies);
    }
    for (const heading of names) {
      const own = Object.entries(props).find(([, q]) => q.h1Of === id && q.h1 === heading);
      const pid = own ? own[0] : !props[slug(heading)] ? slug(heading) : `${id}_${slug(heading)}`;
      props[pid] = { ...(own ? own[1] : {}), type: 'text', kind: 'markdown', section: true, label: heading, h1Of: id, h1: heading };
      for (const row of dataset.rows || []) row[pid] = split.get(row).get(heading) ?? '';
    }
    props[id].hidden = true;
  }
  return dataset;
}

/** An edit of a cell an H1 column drew, as the edit of the property that holds it. {set, cells}: `set` is what the host is told; `cells`
    is what the derived cells become. Anything else passes through. */
export function liftH1(set, props, row) {
  const out = {}, cells = {};
  for (const [id, value] of Object.entries(set || {})) {
    const p = props && props[id];
    if (!p || !p.h1Of) { out[id] = value; continue; }
    out[p.h1Of] = setH1(out[p.h1Of] ?? (row && row[p.h1Of]), p.h1, value);
    cells[id] = value;
  }
  return { set: out, cells };
}
