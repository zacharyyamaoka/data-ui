# Compatibility

**The promise: a page that works on 1.x keeps working on every later 1.x.** Its `.base` files, its data and its host code
stay as they are, the kit underneath is replaced whole, and the page still loads, shows the same rows and does the same
things. Anything else is 2.0.

The versions are semantic: **patch** fixes behaviour against the contract, **minor** adds, **major** breaks. Before 1.0.0
nothing is promised, and apps pin a commit. `data-ui vendor <version>` pins a release, and `CHANGELOG.md` says what changed.

## What counts as breaking

Removing, renaming, or changing the meaning of any of these, in a 1.x release:

| Surface | What is covered | Where it is written |
|---|---|---|
| `.base` keys | Every key, its values and its default, in every view type | `docs/CONTRACT.md` §5 and its amendments, `schemas/view.schema.json` |
| Input fields | The dataset shape, rich cells (`value`, `source`, `basis`, `text`, …), property types, schema sidecars, CSV and JSONL reading | §3, §22, §36 |
| Host calls | Element attributes and methods (`setFacet`, `setPrecedence`, …), hooks (`acceptEdit`, `acceptAdd`, `acceptFile`, `dashboards()`), the `host` object views receive | §1, §6, §17, §34, §37 |
| Tokens | Every `--data-*` CSS variable, its meaning, and the shadcn names it defaults to | §4 |
| Events | Every `data-views-*`, `data-dashboard-*`, `data-rail-*` and `data-analysis-*` event, and its `detail` | §6 and its amendments |
| URL keys | What a shared link says (filters, `v=`, `#t=`, selections): an old link keeps opening the same state | §6, §13, §26, §33 |
| Storage keys | What a returning reader has kept (`data-ui/*` in localStorage: panel widths, frames, dashboard layouts, `persist="local"`): it keeps working, or migrates, never vanishes | §11, §12, §27, §37 |
| Vendored layout | `dist/` file names, `manifest.json`, `views/<folder>.js`, `python/data_ui_base.py` | `build.mjs`, `docs/peps/0001-data-ui-shape.md` §8 |

A patch that makes behaviour match the contract is a fix, even if a page came to rely on the old behaviour. When an app's
journey (`tools/app-journeys.mjs`) goes red on one, the release says so in its changelog, and the fix waits for the app.

## What does not count

- New keys, views, events, tokens or attributes. A page that does not use them does not change.
- Look and layout: spacing, colours within the tokens' meaning, how a view draws, within the same rows and interactions.
- Performance, in either direction, while the budgets in `tests/browser/` hold.
- Anything `docs/CONTRACT.md` does not name: `--dv-*` properties, `.dv-*` class names, DOM structure inside an element,
  source files under `packages/`. An app that reaches into them owns that risk, and its journey is how we find out.

## Changing the promise

1. **Deprecate in a minor.** The old form keeps working, `data-ui check` warns, the changelog names the replacement.
2. **Remove in a major.** The changelog has a migration line for each removal, and `tools/app-journeys.mjs` runs against it
   first.

## How it is kept

- The browser and unit suites run on every push and nightly (`docs/CI.md`).
- `tools/app-journeys.mjs` runs each app's own main journey against a candidate build before a release. A journey that does
  not exist is reported as missing, never as a pass.
- `tools/release.mjs` refuses unless both are green on a clean `main`.
