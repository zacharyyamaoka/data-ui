# PEP 0007: analyses, data-ui's third tier — reports from one Markdown file

- **Status:** proposed 2026-10-26 on `lane/analyses` (from `lane/dashboards-land`, so it lands after dashboards). The
  CONTRACT amendment is §19.
- **Asked by:** Zach, 2026-10-26: "I really like the analysis page. I like how you use a data-ui table/gallery to view
  and organise the analysis pages, and the table of contents with the headers so I can quickly jump to sections. I
  actually feel this analysis format should be part of data-ui. I definitely see me reusing this in many apps,
  particularly apps using data-ui. So data-ui now has the normal dataset views, then the dashboards, and now the
  analysis pages."
- **Born in:** robotparts.dev PEP 0002 (`~/robotparts/docs/peps/0002-analyses.md`, lane/analysis), which chose
  the format after scoring it against W&B report blocks, a dashboard with text panels and MDX components. This PEP
  moves that format and renderer into the kit unchanged in shape; robotparts consumes the vendored elements.
- **Code:** `packages/analysis/` (`src/format.js` the reader, `src/index.js` the two elements, `src/check.js` the
  checker, `src/analysis.css`, `python/data_ui_analysis.py`), `dist/analysis.js`, `gallery/examples/analyses/`.

## 1. The answer

**An analysis is a Markdown file; `<data-analysis>` draws it and `<data-analyses>` lists them.** The pieces are
already the kit's: the frontmatter and every embedded `.base` are read by `parseBase`, prose by `md.js`, every view is
a `<data-views>`, every panel grid a `<data-dashboard>`, the list a `<data-views>` over the frontmatter, the contents
column a §11 resizable panel. The new code is the reader (about 300 lines, pure), two elements (about 500), the
checker (about 150) and a Python twin for build scripts.

## 2. Criteria and options

| # | Criterion | Weight |
|---|---|---|
| A1 | One plain file an agent writes and a person reads; Obsidian opens it | 25 |
| A2 | Reuses views, dashboards, md.js and the parser; no second grammar | 25 |
| A3 | Any host: a static page, a synced folder, a docs site | 20 |
| A4 | Checkable by an agent before anyone looks (`data-ui check`) | 15 |
| A5 | Reading: contents from the headings, a verdict box, problems by line | 15 |

| Option | A1 25 | A2 25 | A3 20 | A4 15 | A5 15 | Total |
|---|---|---|---|---|---|---|
| **A. Markdown + frontmatter + ` ```base ` / `![[x.base]]` + callouts (robotparts PEP 0002)** | 5 | 5 | 5 | 5 | 5 | **100** |
| B. A dashboard with `text:` panels (PEP 0004 alone) | 3 | 5 | 5 | 4 | 2 | 77 |
| C. W&B-style block JSON (`wandb_workspaces.reports.v2`) | 2 | 3 | 4 | 4 | 4 | 62 |
| D. MDX / Evidence components | 2 | 2 | 2 | 2 | 4 | 42 |

PEP 0004 §3 scored "a markdown page with ` ```base ` fences" the close second for a dashboard, and named it the host for
long prose: this is that host, now with the dashboard inside it.

## 3. What stays the host's

The kit owns the format and the drawing. A host owns what is its own, through hooks (CONTRACT §19):

- what `[[target]]` opens (`resolveLink`): robotparts maps part ids to part pages with photos.
- where files come from (`readFile`): robotparts reads a person's synced folder.
- the header's file line and pill (`source`): robotparts names `~/robotparts/analyses/x.md` and its machine.
- its own list columns beside the kit's (`<data-analyses>.rows`): robotparts adds who owns it and a photo mosaic.

Sign-in, storage, sync, publishing and editing stay outside the kit, as they always have.

## 4. Proof

- tests/unit/analysis.test.mjs: the reader, `this`, links, rows, the outline, and the checker on two fixtures (a good
  file passes; a broken one names six problems at their lines).
- tools/test_analysis_py.py: the JavaScript and Python readers agree on every fixture and gallery file; the gallery's
  rows are current.
- gallery/examples/analyses/checks.py: on real data (robotparts' catalog, the rack's sim-to-real runs, pidtuna's
  simulated robots), the list equals the files on disk; each page's contents equal its headings; a fence's rows equal
  the catalog oracle; whole dashboards embed with every panel; the contents column drags 80 px (measured); light,
  dark, 1280 and 390 px with no sideways scroll.
- robotparts lane/analysis vendors `dist/analysis.js` and passes its own checks unchanged (before/after screenshots
  in its report).

## 5. Not done

- Editing in the page (the file is the editor), comments, and publishing (a host's).
- A frontmatter JSON schema for editors (the checker covers agents).
- The docs site's own "Analyses" section beside Views and Dashboards: the integrator's, at merge.
