# record (and the form)

One row as a property sheet: the record page. The host's side peek (`host.open`, in the core) is the same sheet,
540 px wide, beside any view; this is it at full width, with sections. With more than one row, the view's rows are
listed beside the sheet (a select at phone width), so it steps through them; with one row it is the whole page.

```yaml
views:
  - type: record
    name: Part page
    record:
      sections:
        - { name: Torque, properties: [peak_torque, rated_torque] }
        - { name: Size, properties: [mass, od, length] }
  - type: record
    name: Edit
    edit: true            # the same sheet as a form (the core's form.js)
```

- Keys: data-ui's `record {sections}` and `edit`; Bases' `order` (the fields when there are no sections); every view's
  `filters`, `sort`, `groupBy` (headings in the row list), `limit`.
- Each value is `valueHtml` (unit, basis mark, source on hover) plus its provenance in words under it (basis, source,
  as-of, n, note; a missing value's `why`). The dataset's `imageProperty` and `linkProperty` head the sheet.
- `dataset.detail` (every value behind the row) lists under the fields; a click on a field marks its entries (the
  peek's behaviour, without leaving the page).
- Stock: none (docs/VIEWS.md §5: the peek, generalised).
- `manifest.json` `covers: ["Form / editor"]` (CONTRACT §1, amendment 2026-10-26): the form is this view with
  `edit: true`, so the Views page marks the Form row built by this folder.

## The form (`edit: true`)

Edit one row: native inputs made from the dataset's own property schema; a submit proposes the changed fields through
`host.propose({id, set})` and the host accepts or refuses (CONTRACT §1). Not a view type (docs/VIEWS.md "Form /
editor"): the module is the core's (`packages/core/src/form.js`, exported from `@data-ui/core`), so the record view
draws it when the view says `edit: true`, and the host's side peek draws the same form beside any view that says
`edit: true`.

```yaml
views:
  - type: record
    name: Edit
    edit: true
    record:
      sections:
        - { name: Belt, properties: [width_m, max_speed_m_s] }
```

| Property | Control |
|---|---|
| `text` | `<input>` (`<textarea>` past 80 characters); `<select>` with `labels` or `constraints.enum` |
| `number` | `<input type=number>` with its unit; `min` / `max` from `constraints.minimum` / `maximum`, else the cell's `low` / `high` |
| `list` | `<input>`, comma-separated |
| `date` | `<input type=date>` |
| `boolean` | checkbox |
| `derived`, `readOnly` | shown as the value with the reason, never an input |

- Only changed fields are proposed. A rich cell keeps its unit, basis and source; its `value` is replaced (and a `why`
  for a missing value is dropped once there is a value). Validation is the browser's (`reportValidity()`).
- The edit is drawn only after the host says `ok` (it re-renders with the edited rows); a refusal shows its reason
  and keeps what you typed. On a static page with no `editable` attribute and no `acceptEdit`, every edit is refused
  ("read-only"), truthfully.
- Stock: none that fits. JSON Forms' renderers need React, Angular or Vue; json-editor brings Bootstrap-era themes
  (docs/VIEWS.md §5).
