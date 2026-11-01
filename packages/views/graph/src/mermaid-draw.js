/* type: graph, layout.engine: mermaid — the same nodes and edges as the React Flow engine (toGraph), drawn once by
   Mermaid as a static flowchart SVG. A node opens its record (host.open), from a click or from Enter / Space.

   WHY a dynamic import(): the graph manifest is `split: true` (docs/CONTRACT.md §1, amendment 2026-10-26), so Mermaid
   is its own chunk(s) beside graph.js, fetched the first time a mermaid-engine view draws; a React Flow reader never
   downloads it. securityLevel 'strict' (labels sanitised, no click callbacks in the text), startOnLoad false (nothing
   on the page is scanned). Colours come from input.tokens through theme 'base''s themeVariables. */

import { flowchartText } from './flowchart-text.js';

let seq = 0;
// WHY one queue: mermaid.initialize() is global, so each view's theme is set and its render runs before the next view's
let queue = Promise.resolve();
const serial = (job) => { const run = queue.then(job, job); queue = run.catch(() => {}); return run; };

/** input.tokens -> Mermaid's config. Only the base theme's variables, all from the host's tokens (CONTRACT §4). */
export function mermaidConfig(tokens) {
  return {
    startOnLoad: false, securityLevel: 'strict', theme: 'base', suppressErrorRendering: true,
    // WHY dagre: Mermaid 12 defaults to ELK, a 1.5 MB chunk fetched on first draw; dagre is the layered layout the flow
    // engine uses too, and keeps a Map's first draw to Mermaid's own chunks
    layout: 'dagre',
    // WHY classic: Mermaid 12's default look, neo, draws nodes with a drop-shadow filter whose colour is not a token
    // (a light glow on a dark page); classic is fill and stroke only, both from the tokens
    look: 'classic',
    fontFamily: tokens.font,
    themeVariables: {
      darkMode: !!tokens.dark, fontFamily: tokens.font, fontSize: '13px', background: tokens.bg,
      primaryColor: tokens.bg, primaryTextColor: tokens.fg, primaryBorderColor: tokens.border,
      secondaryColor: tokens.subtle, tertiaryColor: tokens.subtle, mainBkg: tokens.bg, nodeBorder: tokens.border,
      nodeTextColor: tokens.fg, textColor: tokens.fg, titleColor: tokens.fg, lineColor: tokens.muted,
      clusterBkg: tokens.subtle, clusterBorder: tokens.border, edgeLabelBackground: tokens.bg,
    },
    flowchart: { useMaxWidth: true },
  };
}

// WHY a floor as the flow engine's (NARROW_MIN_ZOOM): a graph squeezed into a phone is unreadable; it scrolls instead
const MIN_SCALE = 0.45;

export class MermaidDraw {
  constructor(host, el) {
    this.host = host;
    this.box = document.createElement('div');
    this.box.className = 'dv-graph-mermaid';
    el.appendChild(this.box);
    this.ticket = 0;
    this.drawnKey = null;
    this.ids = new Map();
    this.onClick = (e) => { const id = this.rowOf(e.target); if (id != null) this.host.open(id); };
    this.onKey = (e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const id = this.rowOf(e.target);
      if (id == null) return;
      e.preventDefault();
      this.host.open(id);
    };
    this.box.addEventListener('click', this.onClick);
    this.box.addEventListener('keydown', this.onKey);
  }

  rowOf(target) {
    const g = target && target.closest && target.closest('g.node[data-dv-mid]');
    return g && this.box.contains(g) ? this.ids.get(g.getAttribute('data-dv-mid')) ?? null : null;
  }

  /** Draw the model; the last call wins (an older render that resolves later is dropped). Resolves once drawn. */
  async draw(model, tokens, selected) {
    const ticket = ++this.ticket;
    const { text, ids, edges, missing } = flowchartText(model);
    const config = mermaidConfig(tokens);
    const key = JSON.stringify([text, config]);
    if (key === this.drawnKey) { this.mark(selected); return { edges, missing }; }
    if (!model.nodes.length) {
      this.box.replaceChildren();
      this.drawnKey = key;
      return { edges, missing };
    }
    const mermaid = (await import('mermaid')).default;
    if (ticket !== this.ticket) return null;
    const svgId = `dv-mermaid-${++seq}`;
    let out;
    try {
      out = await serial(() => { mermaid.initialize(config); return mermaid.render(svgId, text); });
    } catch (err) {
      if (ticket === this.ticket) this.box.replaceChildren(Object.assign(document.createElement('p'), { className: 'dv-err', textContent: `Mermaid could not draw this graph: ${err && err.message ? err.message : err}` }));
      return { edges, missing, error: true };
    } finally {
      // WHY: Mermaid renders inside a temporary element it appends to document.body; leave none behind on any path
      for (const id of [`d${svgId}`, `i${svgId}`, svgId]) { const left = document.getElementById(id); if (left && !this.box.contains(left)) left.remove(); }
    }
    if (ticket !== this.ticket) return null;
    this.box.innerHTML = out.svg;
    const svg = this.box.querySelector('svg');
    const natural = parseFloat(svg.style.maxWidth) || svg.viewBox.baseVal.width;
    if (natural) svg.style.minWidth = `${Math.round(natural * MIN_SCALE)}px`;
    this.ids = ids;
    for (const g of svg.querySelectorAll('g.node')) {
      const mid = g.getAttribute('data-id') || (/-flowchart-(.+)-\d+$/.exec(g.id) || [])[1];
      const rowId = ids.get(mid);
      if (rowId == null) continue;
      const title = model.nodes.find((n) => n.id === rowId).title;
      g.setAttribute('data-dv-mid', mid);
      g.setAttribute('data-row', rowId);
      g.setAttribute('tabindex', '0');
      g.setAttribute('role', 'button');
      g.setAttribute('aria-label', title);
    }
    this.drawnKey = key;
    this.mark(selected);
    return { edges, missing };
  }

  /** The open record's node (the peek), outlined as the flow engine's dv-active. */
  mark(selected) {
    for (const g of this.box.querySelectorAll('g.node[data-row]')) g.classList.toggle('dv-active', g.getAttribute('data-row') === selected);
  }

  destroy() {
    this.ticket++;
    this.box.removeEventListener('click', this.onClick);
    this.box.removeEventListener('keydown', this.onKey);
    this.box.remove();
  }
}
