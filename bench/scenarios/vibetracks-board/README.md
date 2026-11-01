# Vibe Tracks feature board (76 cards, kanban)

Vibe Tracks' 76 feature notes on a kanban board: columns by status, by priority and by derived proof, plus a table. It exercises the kanban view (cards in columns, column order from `groupOrder`) and a list-valued property (`areas`).

- **App:** vibetracks
- **Base:** `views.base` (opens on its first view)
- **Rows:** 76

## Provenance

- **From:** ~/data-ui/gallery/examples/vibetracks-board/features.json @ main 0dbc3d4
- **sha256 of the data file:** `fc10a10cbc2933597c4345207e835991fc6e089fab4f30f04dfe6f027b47d5fc`
- **Copied:** 2026-10-26
- **Note:** Vibe Tracks' own feature notes (VT-001 ...) with status, priority, areas and derived proof, written by the gallery build.

A frozen copy: the gallery or the source app may change, this folder does not. Check it from the worktree root:
`node bin/data-ui.mjs check bench/scenarios/vibetracks-board/views.base --data bench/scenarios/vibetracks-board/features.json`
