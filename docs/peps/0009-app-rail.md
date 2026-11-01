# PEP 0009: the app rail (`<data-rail>`)

- **Status:** proposed 2026-10-27 on `lane/app-rail` (not merged). The CONTRACT amendment is §27.
- **Asked by:** Zach, 2026-10-27: "with the text and without text, or with the icon and text center (figma style)…
  similar to how shopify does it." Every data-ui app needs an app navigation sidebar; RobotDx is first.
- **Source:** Clank's sidebar, clank-workbench @ 7ba2041 (edbd2c1 + 120bd5c): `src/workbench/store.ts`,
  `shells/shadcn/ShadcnRibbon.tsx`, `tests/sidebar_styles_smoke.mjs`. Zach liked keeping three styles side by side.

## Decision

1. **One element, three styles, one setting.** `<data-rail mode="collapsed | expanded | wide">`. Collapsed is icons
   only (Obsidian). Expanded is Figma's: the icon with its label centred under it, 72 px. Wide is Shopify's: rows of
   icon and label, 240 px, a collapse button and a search field in its header. The style is a person's choice, shown
   in a settings select (`bindRailSelect`), not something the app picks.
2. **Port the model, not the CSS.** Clank's state (three modes, the last open style under its own key, collapse as a
   toggle and not a cycle) is a small pure module, `rail/model.js`, with Clank's test cases ported. The look is written
   for data-ui's tokens; none of Clank's React or shadcn CSS is carried over.
3. **The wide style is a side panel, so it resizes** (CONTRACT §11, `resize.js`'s `makeResizable`, not a second helper).
   The two narrow styles are fixed widths on purpose (a 72 px rail with a draggable edge would stop being Figma's).
4. **Seven traps Clank's agent hit, each with a check** (tests/browser/rail_checks.py): style keyed on `mode`, never
   a stock `data-state`; the toggle is collapsed ↔ last open; a camelCase label breaks at its seams, clamps to two
   lines and keeps its full text in `title`; the wide search field is a `role="button"` that opens on click, Enter and
   Space and never on focus; settings persist at once (Clank's debounce lost a change on reload); geometry is measured
   (wide 238-242 px, labels right of icons within 0.5 px, Figma labels centred under icons within 0.5 px, collapsed
   labels not visible); icon counts are scoped to the rail's own destinations.

## What this is not

Not a router: a destination is a link, and `data-rail-navigate` lets the host route. Not a workspace switcher or an
app launcher (Clank's "Workspaces" group is its own feature). Not a place for per-user settings beyond the style.
