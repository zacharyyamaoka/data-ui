# PEP 0017: The dashboard editor

- **Status:** accepted 2026-10-30, lane/dash-editor.
- **Contract:** CONTRACT §41.
- **Asked by:** Zach, on the /babble 5 round of 2026-10-29 (`reports/media/dashboard-editing-babble-2026-10-29.html`,
  `lane/dash-edit-babble` @ 0ee9d44): "Ok for me like v1 and v2 seem to be like the strongest ones. and I am not sure actually
  which one is better... perhaps then we can just support both. as honestly they feel quite related!" and "Cool idea how you
  kinda like queue up these things to be added to the dashboard". The ruling behind the round: "Humans curate, AI builds."

## The question under the question

"Support both" could mean two modes behind a switch. It should not: V1 and V2 are related because they edit **one thing**, the
`.base` text, and differ in where the eye is. So there is one editor, one state and one options pane: the dashboard itself is the
canvas, and the outline is another view of the same list. The second question hid under the first: a layout in this grammar is
**a list with widths**, not a board with positions, so "drag a panel" means "reorder a list". Everything that decides how the
canvas feels follows from taking that seriously (decision 2).

## Criteria (weighted)

The babble's criteria, frozen before any variant (`docs/babble/dashboard-editing/criteria.json` on that branch), with its gates.

| Criterion | Weight | Merged editor | V1 alone | V2 alone | V4 alone |
|---|---|---|---|---|---|
| Everyday curation is direct: each move on or next to what it changes | 25 | 5 | 5 | 3 | 3 |
| The file stays the shared truth: minimal line edits, comments kept, change visible before it lands | 20 | 5 | 4 | 4 | 3 |
| Reading stays calm: one quiet entry, editing appears on intent | 15 | 5 | 4 | 4 | 3 |
| Change what a panel shows without knowing the grammar | 15 | 5 | 5 | 5 | 3 |
| Build from things collected: placing saved items is a step of the same surface | 15 | 4 | 2 | 2 | 5 |
| Nothing to relearn: named conventions | 10 | 4 | 5 | 5 | 4 |
| **Weighted (of 5)** | | **4.75** | 4.05 | 3.65 | 3.30 |

The merged row is this PEP's own judgement of what shipped; the single-variant rows are read from the babble's gallery. Gates, all
measured in `tests/browser/dash_editor_checks.py`: the host writes (g1); both checkers accept every saved text (g2); the whole task
runs in the page (g3); every side panel drags, remembers and folds (g4); a dashboard with no `editor` is the golden from before (g5).

## What came from which variant

| Part | From | Changed on the way |
|---|---|---|
| Edit in the bar, drag and resize where panels sit, Save with its diff first, Exit's question, Save as copy, Ctrl+S | V1 (Grafana) | Save reviews in the one options pane, not a second drawer |
| The layout as a tree: reorder, hide, group as tabs, the selected panel's properties | V2 (Rerun's blueprint) | Hide is a key, not a removal; a tab comes back out |
| The list of things waiting, a drag or a click onto the grid, an item leaving the list when placed | V4 (Amazon's Saved for later) | Under the tree, not a third panel; it leaves the file on Save, not at once |
| Nothing | V3 (Source), V5 (Ask) | Not built. V5's simulated agent and V3's text pane are deleted with the switcher; `edit-variant` does nothing now |

## Decisions

1. **One state: the text.** The session holds the `.base` text; canvas, outline, options and bar are drawn from it, every control
   ends in `editor.apply(fn)`, and Undo is the text before. WHY: a change on one side shows on the other at once because there is
   no second copy to sync. A layout edit (order, sizes) moves the panels and draws nothing, so charts, scroll and hover stay; any other
   edit redraws through the element's public `load()`.
2. **The canvas is what the file draws.** gridstack 14 runs in its `list` mode, "continuous sequential reflow, like a re-orderable
   list" (its own words), so the drag's preview is the outcome, and after every drop the panels go exactly where the file will draw
   them: reading order, wrapped at 12 columns, each row as tall as its tallest panel (CSS grid's `align-items: stretch`). Measured
   before choosing: `float` left a swap undone (a dragged panel pushed its neighbour down and left a hole the file cannot say), `top`
   let a panel climb beside a taller one, which CSS grid never draws. An east edge dragged past the grid's right side asks for that
   width, and the panel lands on the next row: gridstack stops a width at the edge, but in the file a width is only a number.
3. **Hide is one key.** `hidden: true` on the layout entry, which stays where it is with its size and comments; Show removes the key,
   an exact inverse to the byte. WHY not take the entry out (V2's way): the panel would come back at the bottom at full width, and
   an orphan view looks like a mistake to the next agent. Shopify's JSON templates do exactly this (`disabled`).
4. **The queue is a file the host marks.** `dashboards()` lists one entry with `queue: true`, a `.base` kept like any other. So Add to
   dashboard (§34) fills it with no new word, the file stays the one truth, and a host adds one flag. An item leaves that file only
   when the dashboard is saved, so Undo and Discard give it back. WHY not a key in this dashboard: a reader collects for whichever
   dashboard they open next. WHY Pragmatic drag and drop and not gridstack's drag-in: `GridStack.setupDragIn` hung the page under
   Playwright's mouse in headless Chromium, which every check here drives (the babble found it; reproduced on a bare page with
   gridstack 14; not tried by hand), and before or after a panel is all a reading order can say.
5. **Every edit is a text patch.** `edit/yaml.js` compares the value at a path with the wanted one and changes only the tokens that
   differ: one number inside `{ … }`, a key's own lines in a block. Quotes, spacing, trailing and inner comments, key order, CRLF and an
   open last line stay. It reads back what it wrote; where it cannot (a list in flow style) the one entry is rewritten, as
   `replaceViewInText` does, §34's stated exception. `tests/unit/dash-editor-ops.test.mjs` runs every edit over every panel of every
   gallery dashboard and compares the parse with the file changed by hand.
6. **Arrange is the one grid path, not a second editor.** `arrange.js` exports `liveGrid`; Arrange and the editor both come through it.
   Arrange stays exactly what it was on a dashboard with no `editor` (a reader's arrangement in this browser, offered back as text).
   With `editor`, Edit stands in its place and a kept arrangement is not drawn, because what Edit shows must be what Save writes.
7. **The panes live inside the element, in one component.** Moving a host's `<data-dashboard>` into a shell (the prototype's way)
   disconnects it and remakes every panel's plugin. `edit/pane.js` is the only maker of a side panel, so a boundary that drags, a
   remembered width, a double-click reset and a fold come with every pane (Zach's rule, feedback_resizable_panels), and the checks
   find the panes on the page, so a new one is measured with no word changed. The filter rail folds away while editing, one press
   from coming back.
8. **Opt in with `editor`.** The attribute offers Edit; the bundle (`dist/dashboard-edit.js`, 113 KB) loads on the press and uses the
   Arrange bundle's gridstack. No attribute, no change: `reading.golden.json`, written from main before the editor, holds that.

## Prior art

Checked 2026-10-30 against each product's own docs.

- **Grafana.** Edit opens edit mode, and every workflow ends in Save (with an optional description) and Exit edit; panels move by
  title and resize from the lower-right corner [1]. Dynamic dashboards (GA 2026-04-08) rebuilt editing around a sidebar that "keeps your
  dashboard visible while you work", docked in edit mode, resizable, its dock state in local storage [2][3]; a content outline shows
  "the full structure of your dashboard as a tree" [2]; panels can be dragged from the sidebar onto the canvas [2]. Version history
  compares two saved versions as text plus a JSON diff [4]. **Not verified:** the docs read here do not describe the Changes diff on the
  save drawer that the babble copied; a save with its diff first stays this editor's own step.
- **Shopify.** The theme editor's sidebar "displays a tree view of all the content"; at 1600 px and up there are two panels, structure
  on the left, the selected item's settings on the right, and the right one collapses when nothing is selected [5]. Sections reorder
  by a drag handle and hide from the sidebar [6]; in the JSON template a hidden section is `disabled`, which "isn't rendered but can
  still be customized", beside an `order` list [7]. Undo works on unsaved changes only [5]. In the admin, a list's custom view keeps its
  edited columns (Save › Update view) [8]. **Not verified:** whether the double sidebar's panels resize; the docs only describe a
  draggable divider in single-sidebar mode.
- **Notion.** No edit mode: a dashboard is a page of linked database views, and blocks drag by the ⋮⋮ handle into columns [9]; each view
  has its own layout, properties, filters, sorts and grouping [10]. **Not verified:** that the docs combine the two (the guide describes
  them separately). The calm this editor aims at, not its structure: Notion has no file an agent shares.
- **Metabase.** A pencil enters editing; cards snap to a grid, drag with the others moving aside, resize from the corner; hover icons
  duplicate, remove or replace [11]; Save and Cancel leave [11][12]. Tabs and templated sections group cards.
- **Retool.** The classic IDE is this layout exactly: canvas on a 12-column grid, a component tree on the left that selects anything,
  visible or not, an inspector on the right with an App Inspector when nothing is selected, and navbar toggles that hide the panels
  to free the canvas [13]. **Not verified:** whether its panels resize; the page says nothing, and it covers classic apps only.
- **Home Assistant.** An edit button, undo and redo at the top, and "Take control" to own a generated dashboard [14]; cards drag in the
  sections view with a dense option trading order for filled gaps [15]. Migrating a view leaves cards in an "Imported cards" section until
  you place them [16], a queue by another name. **Community only, not the docs:** a dashboard in storage mode is JSON, and its raw
  configuration editor "does not allow spacing or comments" [17]; that is the failure decision 5 exists to avoid.

What they share, and this editor takes: one quiet way in; the canvas stays visible; structure in a tree on the left, the selected thing's
settings on the right (Grafana, Shopify, Retool); drag on a snapping grid; an explicit save with a way to leave without it (Grafana,
Metabase, Shopify). What none of the docs read describes: a visual edit that keeps a hand-written file's comments.

[1]: https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/create-dashboard/
[2]: https://grafana.com/whats-new/2026-04-08-dynamic-dashboards-is-now-generally-available/
[3]: https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/create-dynamic-dashboard/
[4]: https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/manage-version-history/
[5]: https://help.shopify.com/en/manual/online-store/themes/customizing-themes/theme-editor/features-overview
[6]: https://help.shopify.com/en/manual/online-store/themes/theme-structure/sections-and-blocks
[7]: https://shopify.dev/docs/storefronts/themes/architecture/templates/json-templates
[8]: https://help.shopify.com/en/manual/shopify-admin/productivity-tools/file-uploads
[9]: https://www.notion.com/help/guides/personal-work-dashboard
[10]: https://www.notion.com/help/intro-to-databases
[11]: https://www.metabase.com/docs/latest/dashboards/introduction
[12]: https://www.metabase.com/docs/latest/dashboards/filters
[13]: https://docs.retool.com/apps/concepts/ide
[14]: https://www.home-assistant.io/dashboards/dashboards/
[15]: https://www.home-assistant.io/dashboards/sections/
[16]: https://www.home-assistant.io/dashboards/views/
[17]: https://community.home-assistant.io/t/wth-does-the-dashboard-gui-configuration-not-allow-include-directives/811688

## Not done

- A new dashboard from nothing (V4's "New dashboard from these…"). Save as copy covers starting from this one.
- Moving a panel from the dashboard into the queue (V4's "Save for later"). Hide keeps it in this file.
- Rebasing edits onto a file that moved underneath. The review says so and the event carries `before`, so a host can refuse.
- Dragging on a phone. Under 700 px the panels stay one column and Move up / Move down reorder them.
- A panel's exact height while editing. The grid counts whole rows, so a panel with no `h` draws up to a row taller than it reads, and
  goes back on Exit; its entry gets no `h` unless a reader drags one.
- Folding the options pane when a reader clicks back on the dashboard, the rest of feedback_resizable_panels' inspector rule. Here a click
  on the dashboard is how the pane is used, so it stays, and folds by its button, Ctrl+Alt+B or the reader's remembered choice.
