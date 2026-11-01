/* input.layers (docs/CONTRACT.md §32): the other datasets a 3D view's layers read, as the view receives them.

   A <data-dashboard> hands each panel's <data-views> its layer datasets, `el.layers = {<dataset>: {dataset, rows}}`,
   the rows already filtered exactly as a panel on that dataset would be (packages/dashboard/src/model.js layerFilters);
   a host page may set the property itself. The element passes them to the view's update() through layersInput(). A
   plain <data-views> with nothing set has none: input.layers is {}. Pure, so the shape is unit-tested in Node. */

import { properties as labelled } from './rowmodel.js';

/** {<dataset>: {rows, columns, total, url}}, frozen. `rows` are the dataset's own row objects (never copies; a view
    never writes them), in file order: a layer windows them by its own time column. `columns` is shaped as
    input.columns (labels from the .base's properties, units from the data's schema). An entry with no rows given is
    every row of its dataset; an entry with no dataset is left out. */
export function layersInput(layers, base) {
  const out = {};
  for (const [name, entry] of Object.entries(layers && typeof layers === 'object' ? layers : {})) {
    const ds = entry && entry.dataset;
    if (!ds || !Array.isArray(ds.rows)) continue;
    out[name] = Object.freeze({
      rows: Array.isArray(entry.rows) ? entry.rows : ds.rows,
      columns: labelled(ds, base),
      total: ds.rows.length,
      url: ds.url || null,
    });
  }
  return Object.freeze(out);
}
