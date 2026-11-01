/* type: graph, layout.engine: mermaid — the model toGraph() builds, written as Mermaid flowchart text. Pure: no DOM,
   no Mermaid, no @data-ui/core (tests/unit/graph-mermaid.test.mjs runs it in Node).

   WHY generated ids (n0, n1, … and g0, g1, …), never row ids: a row id may hold any character, and Mermaid reads
   `end`, `graph`, `-->`, quotes and brackets in an id as syntax. The map back to row ids is returned beside the text.
   WHY every label is entity-encoded: a title is shown as written (truthful rendering), so `"`, brackets, `#`, `;`,
   backticks or `<script>` must reach the reader as text, never as Mermaid syntax, markdown or HTML. Mermaid decodes
   `#<code point>;` to the character itself. */

const DIRECTIONS = new Set(['LR', 'TB', 'RL', 'BT']);
const PLAIN = /[A-Za-z0-9 ]/;

/** One label as a quoted Mermaid string: letters, digits, spaces and non-ASCII as written, every other ASCII
    character as `#<code>;`, a line break as `<br>` (Mermaid's own line break). Nothing dropped or rewritten. */
export function mermaidLabel(text) {
  let out = '';
  for (const ch of String(text).replace(/\r\n?/g, '\n')) {
    if (ch === '\n') out += '<br>';
    else if (PLAIN.test(ch) || ch.codePointAt(0) > 127) out += ch;
    else out += `#${ch.codePointAt(0)};`;
  }
  return `"${out}"`;
}

/** `rgb(r, g, b)` / `rgba(…)` text (input.tokens' form) -> `#rrggbb`; null when it is not that form. WHY: Mermaid's
    linkStyle separates its styles with commas, so an rgb() colour would break the line. */
export function hexOf(colour) {
  const m = /^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/.exec(String(colour || ''));
  return m ? `#${[m[1], m[2], m[3]].map((v) => Math.min(255, +v).toString(16).padStart(2, '0')).join('')}` : null;
}

/** {nodes, edges, groups, missing, direction} (toGraph's model) -> {text, ids, edges, missing}.
    `ids` maps each Mermaid node id to its row id. An edge is written only when both of its ends are drawn nodes
    (Mermaid would otherwise draw an unknown id as a node of its own, inventing a row); one that is not is skipped and
    counted into `missing`, beside the model's own count of edges to rows not shown. */
export function flowchartText(model) {
  const direction = DIRECTIONS.has(model.direction) ? model.direction : 'LR';
  const lines = [`flowchart ${direction}`];
  const ids = new Map();
  const mid = new Map();
  model.nodes.forEach((n, i) => { ids.set(`n${i}`, n.id); mid.set(n.id, `n${i}`); });
  const nodeLine = (n, indent) => `${indent}${mid.get(n.id)}[${mermaidLabel(n.title)}]`;

  const grouped = new Map((model.groups || []).map((g) => [g.id, []]));
  for (const n of model.nodes) if (n.group && grouped.has(n.group)) grouped.get(n.group).push(n);
  (model.groups || []).forEach((g, i) => {
    const members = grouped.get(g.id);
    if (!members.length) return;
    lines.push(`  subgraph g${i}[${mermaidLabel(g.label)}]`);
    for (const n of members) lines.push(nodeLine(n, '    '));
    lines.push('  end');
  });
  for (const n of model.nodes) if (!(n.group && grouped.has(n.group))) lines.push(nodeLine(n, '  '));

  let missing = model.missing || 0;
  let drawn = 0;
  const styles = [];
  for (const e of model.edges) {
    const s = mid.get(e.source), t = mid.get(e.target);
    if (!s || !t) { missing++; continue; }
    lines.push(`  ${s} -->${e.label == null ? '' : `|${mermaidLabel(e.label)}|`} ${t}`);
    const hex = e.slot ? hexOf(e.colour) : null;
    if (hex) styles.push(`  linkStyle ${drawn} stroke:${hex}`);
    drawn++;
  }
  lines.push(...styles);
  return { text: lines.join('\n'), ids, edges: drawn, missing };
}
