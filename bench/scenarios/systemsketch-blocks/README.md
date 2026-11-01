# SystemSketch blocks (8 rows, graph)

A SystemSketch example diagram's eight blocks and the ports that connect them, drawn as a graph (dagre layout, left to right and top to bottom) plus a table. It exercises the graph view's layout and edge-label path on a tiny data set, which is the floor for first-paint cost.

- **App:** systemsketch
- **Base:** `views.base` (opens on its first view)
- **Rows:** 8

## Provenance

- **From:** ~/data-ui/gallery/examples/systemsketch-blocks/blocks.json @ main 0dbc3d4
- **sha256 of the data file:** `700d6aaa1f03606fb0cef61f3168032f0a890aa437774b0bab714e6002cdea10`
- **Copied:** 2026-10-26
- **Note:** A SystemSketch example diagram's blocks and the ports that connect them, as nodes and edges.

A frozen copy: the gallery or the source app may change, this folder does not. Check it from the worktree root:
`node bin/data-ui.mjs check bench/scenarios/systemsketch-blocks/views.base --data bench/scenarios/systemsketch-blocks/blocks.json`
