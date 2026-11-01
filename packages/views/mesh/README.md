# mesh: the 3D engine behind `<data-mesh>`

Not a view type. `<data-mesh src poster interact>` (defined by the core, `packages/core/src/elements/data-mesh.js`)
draws its poster and loads this bundle, `dist/views/mesh.js`, the first time a model is wanted: a hover on a card, a
click, an open peek. The cards view draws one per card with `mesh: <property>`; the peek draws an orbit viewer for a
property whose field says `media: mesh` (docs/CONTRACT.md §23).

- **Stock part:** three 0.186.1 — `WebGLRenderer`, `GLTFLoader` + `MeshoptDecoder` (glTF / GLB, the format to ship),
  `OBJLoader`, `STLLoader`, `PLYLoader`. The pattern is three's "multiple elements" example and `<model-viewer>`'s
  `Renderer` singleton (one context, frames copied into each element's own 2D canvas).
- **Ours:** at most `MAX_LIVE` (4) elements animate at once (the oldest freezes on its last frame); a parsed-model
  cache of `MAX_MODELS` (48), least recently used disposed; turntable on hover, drag to rotate, orbit + wheel zoom in
  the peek; framing on the model's bounding sphere; no motion of its own under `prefers-reduced-motion`.
- **Why not `<model-viewer>`:** glTF only (the object library's meshes are OBJ), about 1 MB with its own three, and
  per-element posters/AR/UI we do not need. Its renderer design is the one copied here.
- **Numbers:** `await customElements.get('data-mesh').stats()` → `{contexts, contextsMade, live, liveMax, models,
  bytes, frames, renderMs, firstModelMs}` (the browser checks and the KPI page read it).
