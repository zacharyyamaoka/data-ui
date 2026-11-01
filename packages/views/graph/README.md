# graph

Rows as nodes and edges from a property that lists other rows' ids, laid out by dagre, on a React Flow canvas with
pan, zoom, controls and a minimap (hidden under 560 px). A click on a node opens its record; a click on a subflow's
label lists its rows. `layout: {engine: mermaid}` draws the same nodes and edges as a static Mermaid flowchart
instead, for simple layouts.

- **Keys:** `edges: {property, label}` (required: no edge is ever inferred; `property` lists target ids, `label`
  names a property whose value labels and colours the edges: a list in the same order as the ids, or one value for
  all of a row's edges), `layout: {engine: flow | mermaid, algorithm: dagre, direction: LR | TB | RL | BT}` (`engine` defaults to
  `flow`), `groupBy` (each group a
  subflow, its nodes coloured by the group's series slot), `order` (the fields on a node card), `filters`.
- **Colours:** a value's slot is its column's `colors` entry, else `hueOf(value)`; React Flow's `--xy-*` properties
  are mapped onto `--dv-*` in `src/graph.css`.
- **Engine mermaid:** the same `toGraph()` model written as Mermaid flowchart text (generated ids `n0`, `n1`, …; every
  label entity-encoded so it shows as written; groups as `subgraph`s; an edge only between drawn nodes), rendered with
  `securityLevel: strict`, `theme: base` with `themeVariables` from the host's tokens, Mermaid's dagre layout and
  classic look. A click, Enter or Space on a node (`role="button"`, focusable) opens its record. The SVG fits the view
  down to 45% of its size, then scrolls inside the view.
- **Stock:** `@xyflow/react` 12.12.0 with `react` / `react-dom` 19.3.1 as a React island inside this bundle (the
  page pays for React only when a graph shows), `@dagrejs/dagre` 3.1.3 (compound layout for subflows), `mermaid`
  12.2.0 (MIT) for the mermaid engine, loaded with `import()`: the manifest's `split: true` makes it its own chunks
  (`dist/views/graph-*.js`), fetched only when a mermaid-engine view first draws.
- **Files:** `src/index.js` (rows -> laid-out nodes and edges, the island, the engine switch), `src/flow.jsx` (the
  canvas, node card, subflow and edge), `src/flowchart-text.js` (the model as Mermaid text; pure),
  `src/mermaid-draw.js` (Mermaid's render, clicks and keys), `src/graph.css`.
