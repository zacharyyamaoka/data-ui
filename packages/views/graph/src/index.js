/* type: graph — rows as nodes, edges from a property that lists other rows' ids (docs/VIEWS.md, Graph / network).

   A React island inside the framework-free host (docs/CONTRACT.md §1): this bundle carries React, react-dom and
   React Flow, so a page pays for React only when a graph first shows. The constructor creates the root, update()
   renders, destroy() unmounts.

   STOCK PARTS: @xyflow/react 12.12.0 (the canvas: pan, zoom, minimap, controls, custom nodes and edges) and
   @dagrejs/dagre 3.1.3 (the layered layout React Flow's docs recommend for trees and DAGs; compound, so a groupBy
   becomes subflows). OURS: rows -> nodes and edges, the node card, parallel-edge spacing, the theme mapping.
   WHY React Flow: Zach's call, 2026-10-25 ("I love react flow"); it is also his Block View chassis.
   WHY edges must name a property: no edge is ever inferred (feedback_do_not_invent_undefined_relationships).
   ENGINES: `layout.engine: flow` (the default: React Flow + dagre, interactive) or `mermaid` (a static Mermaid
   flowchart, src/mermaid-draw.js, loaded as its own chunk on first use). Both draw toGraph()'s nodes and edges.
   WHY two: Zach, 2026-10-27, "mermaid js for doing simple layouts, and also reactflow for more interactive layouts".
   Writes back only through the host: open(id) on a node, open(id, {records}) on a subflow's header, setStatus. */

import { createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { Graph, layout as dagreLayout } from '@dagrejs/dagre';
import { cellValue, groupLabel, hueOf, isEmpty, valueHtml } from '@data-ui/core';
import { Flow } from './flow.jsx';
import { MermaidDraw } from './mermaid-draw.js';
import flowCss from '@xyflow/react/dist/style.css';
import ownCss from './graph.css';

export const css = `${flowCss}\n${ownCss}`;

const NODE_W = 232;
const HEAD_H = 34; // px: the title line
const FIELD_H = 18; // px: one field line on a node
const GROUP_PAD = 18; // px: a subflow's inset around its nodes
const GROUP_HEAD = 26; // px: a subflow's label band

export function options() {
  return [
    { type: 'property', key: 'edges.property', displayName: 'Edges from' },
    { type: 'property', key: 'edges.label', displayName: 'Edge label', none: 'none' },
    { type: 'dropdown', key: 'layout.engine', displayName: 'Engine', default: 'flow', options: { flow: 'React Flow', mermaid: 'Mermaid' } },
    { type: 'dropdown', key: 'layout.direction', displayName: 'Direction', default: 'LR', options: { LR: 'Left to right', TB: 'Top to bottom', RL: 'Right to left', BT: 'Bottom to top' } },
  ];
}

/** A value's colour slot (0 muted, 1-8 the series): the column's own `colors`, else a stable hue. */
export function slotOf(columns, property, value) {
  const colors = columns[property] && columns[property].colors;
  if (colors && Object.prototype.hasOwnProperty.call(colors, String(value))) return colors[String(value)];
  return isEmpty(value) ? 0 : hueOf(value);
}
const colourOf = (tokens, slot) => (slot ? tokens.series[(slot - 1) % tokens.series.length] : tokens.muted);
const list = (v) => { const x = cellValue(v); return isEmpty(x) ? [] : Array.isArray(x) ? x : [x]; };

/** The view's layout engine: 'mermaid', else 'flow'. */
export const engineOf = (view) => (view.layout && view.layout.engine === 'mermaid' ? 'mermaid' : 'flow');

/** The row model -> {nodes, edges, groups, missing}, laid out by dagre (unless `layout: false`: the mermaid engine
    lays out its own). Pure: no React, no DOM. */
export function toGraph(input, { layout = true } = {}) {
  const { rows, columns, view, tokens, dataset } = input;
  const titleProp = dataset.titleProperty;
  const edgeProp = view.edges && view.edges.property;
  const labelProp = view.edges && view.edges.label;
  const direction = (view.layout && view.layout.direction) || 'LR';
  const groupProp = view.groupBy && columns[view.groupBy.property] ? view.groupBy.property : null;
  const skip = new Set([titleProp, edgeProp, labelProp, groupProp, 'id']);
  const fields = (view.order || []).filter((p) => columns[p] && !skip.has(p));

  // groups: the host's own (groupOrder and sort already applied); a group with no rows draws no subflow
  const groupOf = new Map();
  const groups = [];
  for (const g of input.groups || []) {
    if (!g.rows.length) continue;
    const gid = `group:${groups.length}`;
    groups.push({ id: gid, key: g.key, label: groupLabel(columns, g.property, g.key), rows: g.rows, slot: slotOf(columns, g.property, g.key) });
    for (const r of g.rows) groupOf.set(String(r.id), gid);
  }

  const ids = new Set(rows.map((r) => String(r.id)));
  const nodes = rows.map((r) => {
    const id = String(r.id);
    const shown = fields.filter((p) => !isEmpty(cellValue(r[p])));
    const gid = groupOf.get(id) || null;
    const slot = groupProp ? slotOf(columns, groupProp, cellValue(r[groupProp])) : 0;
    return {
      id, group: gid, width: NODE_W, height: HEAD_H + shown.length * FIELD_H + (shown.length ? 8 : 0),
      title: String(cellValue(r[titleProp]) ?? id),
      fields: shown.map((p) => ({ id: p, label: columns[p].label, html: valueHtml(r[p], columns[p]) })),
      colour: colourOf(tokens, slot), slot,
    };
  });

  const edges = [];
  let missing = 0;
  if (edgeProp) {
    for (const r of rows) {
      const targets = list(r[edgeProp]);
      const rawLabel = labelProp ? cellValue(r[labelProp]) : null;
      targets.forEach((t, i) => {
        const target = String(t);
        if (!ids.has(target)) { missing++; return; }
        const label = Array.isArray(rawLabel) ? rawLabel[i] : rawLabel;
        const slot = labelProp && !isEmpty(label) ? slotOf(columns, labelProp, label) : 0;
        edges.push({ id: `${r.id}->${target}#${i}`, source: String(r.id), target, label: isEmpty(label) ? null : String(label), slot, colour: slot ? colourOf(tokens, slot) : tokens.muted });
      });
    }
  }
  // parallel edges between one pair spread out, so each keeps its own line and label
  const pairs = new Map();
  for (const e of edges) { const k = [e.source, e.target].sort().join('\u0000'); if (!pairs.has(k)) pairs.set(k, []); pairs.get(k).push(e); }
  for (const same of pairs.values()) same.forEach((e, i) => { e.spread = i - (same.length - 1) / 2; });

  if (layout) layoutGraph(nodes, edges, groups, direction);
  return { nodes, edges, groups, missing, direction, edgeProp, fields };
}

/** dagre: ranks along `direction`; a group is a compound cluster, so its nodes stay together. Writes x, y. */
function layoutGraph(nodes, edges, groups, direction) {
  const g = new Graph({ multigraph: true, compound: groups.length > 0 });
  g.setGraph({ rankdir: direction, nodesep: 28, ranksep: 70, edgesep: 14, marginx: 8, marginy: 8 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const grp of groups) g.setNode(grp.id, { paddingTop: GROUP_HEAD + GROUP_PAD, paddingBottom: GROUP_PAD, paddingLeft: GROUP_PAD, paddingRight: GROUP_PAD });
  for (const n of nodes) { g.setNode(n.id, { width: n.width, height: n.height }); if (n.group) g.setParent(n.id, n.group); }
  for (const e of edges) g.setEdge(e.source, e.target, { weight: 1, minlen: 1, labelpos: 'c', width: e.label ? 8 * e.label.length : 0, height: e.label ? 16 : 0 }, e.id);
  dagreLayout(g);
  const at = (id) => g.node(id);
  for (const n of nodes) { const p = at(n.id); n.x = p.x - n.width / 2; n.y = p.y - n.height / 2; }
  for (const grp of groups) {
    // WHY from the members, not dagre's cluster box: dagre's padding keys are not honoured for every rankdir
    const members = nodes.filter((n) => n.group === grp.id);
    const x0 = Math.min(...members.map((n) => n.x)) - GROUP_PAD, y0 = Math.min(...members.map((n) => n.y)) - GROUP_PAD - GROUP_HEAD;
    const x1 = Math.max(...members.map((n) => n.x + n.width)) + GROUP_PAD, y1 = Math.max(...members.map((n) => n.y + n.height)) + GROUP_PAD;
    Object.assign(grp, { x: x0, y: y0, width: x1 - x0, height: y1 - y0 });
  }
}

export default class GraphView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this.peekId = null;
    this.root = null; // the React root, made when a flow-engine view first draws
    this.mermaid = null; // the Mermaid drawing, while a mermaid-engine view shows
  }

  destroy() {
    this.host.setStatus('');
    if (this.root) this.root.unmount();
    if (this.mermaid) this.mermaid.destroy();
  }

  peeked(peek) {
    this.peekId = peek ? String(peek.id) : null;
    if (this.mermaid) this.mermaid.mark(this.peekId);
    else if (this.model) this._render();
  }

  update(input) {
    this.input = input;
    const engine = engineOf(input.view);
    this.model = toGraph(input, { layout: engine === 'flow' });
    const { nodes, edges, missing, edgeProp } = this.model;
    const parts = [`${nodes.length} nodes · ${edges.length} edges`];
    if (!edgeProp) parts.push('<span class="dv-err">no edges: set <code>edges: {property}</code>, a property listing other rows\' ids</span>');
    if (missing) parts.push(`${missing} edge${missing === 1 ? '' : 's'} to rows not shown`);
    this.host.setStatus(parts.join(' · '));
    if (engine === 'mermaid') {
      if (this.root) { this.root.unmount(); this.root = null; }
      if (!this.mermaid) this.mermaid = new MermaidDraw(this.host, this.el);
      return this.mermaid.draw(this.model, input.tokens, this.peekId);
    }
    if (this.mermaid) { this.mermaid.destroy(); this.mermaid = null; }
    this._render();
  }

  _render() {
    const { tokens, view } = this.input;
    const m = this.model;
    // WHY a key: a new layout (other rows, grouping or direction) re-fits the view; a theme or peek change keeps it
    const key = JSON.stringify([view.name, m.direction, m.nodes.map((n) => [n.id, n.group]), m.edges.map((e) => e.id)]);
    const props = {
      key, model: m, tokens, selected: this.peekId, narrow: this.el.clientWidth < 560,
      onOpen: (id) => this.host.open(id),
      onOpenGroup: (grp) => this.host.open(grp.rows[0].id, { records: grp.rows, title: `${grp.label} · ${grp.rows.length} nodes` }),
    };
    if (!this.root) this.root = createRoot(this.el);
    // WHY flushSync: the host's data-views-render event (and the checks) read the drawn nodes right after update()
    flushSync(() => this.root.render(createElement(Flow, props)));
  }
}

