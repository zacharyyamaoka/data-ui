// The graph view's mermaid engine (amendment 2026-10-27, graph layout engines): toGraph()'s model written as Mermaid
// flowchart text. Every authored character survives as written, ids are generated and stable, groups are subgraphs,
// an edge to a row not shown is never drawn (Mermaid would invent a node for it) and is counted.
import test from 'node:test';
import assert from 'node:assert/strict';
import { flowchartText, mermaidLabel, hexOf } from '../../packages/views/graph/src/flowchart-text.js';

const node = (id, title, group = null) => ({ id, title, group });
const edge = (source, target, extra = {}) => ({ id: `${source}->${target}`, source, target, label: null, slot: 0, colour: 'rgb(1, 2, 3)', ...extra });
const model = (over = {}) => ({ nodes: [], edges: [], groups: [], missing: 0, direction: 'BT', ...over });

// what Mermaid does with a label's text (its encodeEntities, then decodeEntities and the browser's HTML entities):
// `#<code>;` -> the character, `<br>` -> a line break
const decoded = (quoted) => quoted.slice(1, -1).replace(/<br>/g, '\n').replace(/#(\d+);/g, (_, n) => String.fromCodePoint(+n));

test('labels: quotes, brackets, braces, parentheses, <script>, #, ;, backticks and newlines come back as written', () => {
  const titles = ['say "hi"', 'a [b] (c) {d}', '<script>alert(1)</script>', 'C# #1; a;b', '`code` and ``two``', 'line one\nline two',
    'end', 'flowchart LR', 'a --> b', 'x|y|z', '50% & <b>bold</b>', "it's", 'tab\there', 'Ünïcödé — ✓ 日本', '#35;', 'crlf\r\nend'];
  for (const t of titles) {
    const q = mermaidLabel(t);
    assert.match(q, /^"[^"]*"$/, `one quoted string, no inner quote: ${q}`);
    assert.match(q.slice(1, -1).replace(/<br>/g, '').replace(/#\d+;/g, ''), /^[A-Za-z0-9 \u0080-\u{10FFFF}]*$/u, `only letters, digits, spaces and non-ASCII left raw in ${q}`);
    assert.equal(decoded(q), t.replace(/\r\n?/g, '\n'), `round trip of ${JSON.stringify(t)}`);
  }
  assert.equal(mermaidLabel('Plain words 42'), '"Plain words 42"');
  assert.equal(mermaidLabel('a"b'), '"a#34;b"');
  assert.equal(mermaidLabel(''), '""');
});

test('ids: generated n0, n1, … in row order, mapped back to row ids; the same model writes the same text', () => {
  const m = model({ nodes: [node('vibetracks:0001', 'One'), node('end', 'Two'), node('a b"c', 'Three')], edges: [edge('end', 'vibetracks:0001'), edge('a b"c', 'end')] });
  const out = flowchartText(m);
  assert.deepEqual([...out.ids], [['n0', 'vibetracks:0001'], ['n1', 'end'], ['n2', 'a b"c']]);
  assert.equal(out.text, 'flowchart BT\n  n0["One"]\n  n1["Two"]\n  n2["Three"]\n  n1 --> n0\n  n2 --> n1');
  assert.equal(flowchartText(m).text, out.text);
  assert.equal(out.edges, 2);
  assert.equal(out.missing, 0);
});

test('direction: LR, TB, RL, BT as given; anything else is LR (the flow engine\'s default)', () => {
  for (const d of ['LR', 'TB', 'RL', 'BT']) assert.equal(flowchartText(model({ direction: d })).text, `flowchart ${d}`);
  assert.equal(flowchartText(model({ direction: 'XX' })).text, 'flowchart LR');
  assert.equal(flowchartText(model({ direction: undefined })).text, 'flowchart LR');
});

test('groups: each group with nodes is a subgraph (g0, g1, …) labelled as written; ungrouped nodes stay outside', () => {
  const m = model({
    direction: 'LR',
    groups: [{ id: 'group:0', label: 'Power [48 V]' }, { id: 'group:1', label: 'Empty' }, { id: 'group:2', label: 'CAN' }],
    nodes: [node('psu', 'Supply', 'group:0'), node('can', 'fdcanusb', 'group:2'), node('loose', 'Loose'), node('clamp', 'Clamp', 'group:0')],
    edges: [edge('psu', 'clamp')],
  });
  assert.equal(flowchartText(m).text, [
    'flowchart LR',
    '  subgraph g0["Power #91;48 V#93;"]', '    n0["Supply"]', '    n3["Clamp"]', '  end',
    '  subgraph g2["CAN"]', '    n1["fdcanusb"]', '  end',
    '  n2["Loose"]',
    '  n0 --> n3',
  ].join('\n'));
});

test('edges to rows not shown: skipped, never drawn as a node, and counted beside the model\'s own count', () => {
  const m = model({ nodes: [node('a', 'A'), node('b', 'B')], edges: [edge('a', 'b'), edge('a', 'gone'), edge('gone', 'b')], missing: 2 });
  const out = flowchartText(m);
  assert.equal(out.text, 'flowchart BT\n  n0["A"]\n  n1["B"]\n  n0 --> n1');
  assert.equal(out.edges, 1);
  assert.equal(out.missing, 4);
  assert.doesNotMatch(out.text, /gone/);
});

test('edge labels are escaped; a labelled edge with a colour slot gets its stroke as hex (linkStyle takes no rgb())', () => {
  const m = model({ nodes: [node('a', 'A'), node('b', 'B'), node('c', 'C')], edges: [edge('a', 'b', { label: 'CAN | 1 Mbit', slot: 1, colour: 'rgb(37, 99, 235)' }), edge('b', 'c')] });
  assert.equal(flowchartText(m).text, 'flowchart BT\n  n0["A"]\n  n1["B"]\n  n2["C"]\n  n0 -->|"CAN #124; 1 Mbit"| n1\n  n1 --> n2\n  linkStyle 0 stroke:#2563eb');
  assert.equal(hexOf('rgba(255, 0, 16, 0.5)'), '#ff0010');
  assert.equal(hexOf('var(--x)'), null);
});

test('an empty dataset writes only the header', () => {
  const out = flowchartText(model());
  assert.equal(out.text, 'flowchart BT');
  assert.equal(out.ids.size, 0);
  assert.equal(out.edges, 0);
  assert.equal(out.missing, 0);
});
