# PEP 0014: Add to dashboard

- **Status:** accepted 2026-10-29. It landed on `integrate/packet` with lane/add-to-dashboard @ 3413ea1 (merge 69b0e7b).
- **Contract:** CONTRACT §34.
- **Asked by:** Zach, 2026-10-29, relayed by RobotDx (io-diagnostics PEP 0002):
  - "Humans curate, AI builds."
  - A reader adds anything they're looking at to a saved dashboard, "like the amazon thing of adding to a saved list".
  - It lands at the bottom, to be arranged later.
  - "this is a standard feature you can support in data-ui, shouldn't be specific to robotdx."

## Decisions

1. **The host writes; data-ui never does.**
   - `dashboards()` is an optional function on the element or any ancestor. It lists the targets.
   - The `data-add-to-dashboard` event carries `{dashboard, panel, text, respondWith}`. The host saves `text` and answers through `respondWith`, following FetchEvent's rule (once, during dispatch).
   - With no listener, the text goes to the clipboard.
   - WHY: this is the same boundary as `host.propose` (§1). A static site, RobotDx's `PUT /api/v1/dashboards/<name>.base` and a vault plugin each persist in their own way.
2. **Edits are insert-only.**
   - `appendPanel(text, panel)` keeps every byte of the target's text and only inserts lines: the view, the dataset, and a full-width panel at the bottom of `layout.panels`.
   - A dataset is reused when its file matches. A colliding name gets a suffix.
   - WHY: the reader curates afterwards with Arrange (§17). Comments and the author's order must survive a machine edit.
3. **A series is added as drawing state, not as a filter.**
   - The added view starts with the other series hidden (`hiddenSeries`, the §31 legend state).
   - WHY: it works the same for every legend, and rows and counts stay truthful. The reader can unhide the rest.
4. **"At this moment" pins the panel's own clock.**
   - The layout panel gets `t: <seconds>`, which gives it a paused clock of its own. Its header says so.
   - WHY: the reader saw an instant, and saving an instant must not move the dashboard's shared clock.

## Not done

- iOS long-press menus.
- An item menu on table cells and record fields. The ⋯ menu covers the whole view.
- Auto-reload of the target after a save. The host calls `reload()`.
- A Python `appendPanel`.
