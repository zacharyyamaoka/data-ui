/* Bases' `note.<property>` names, bared to the data's own column names for a view (CONTRACT §24: `groupBy: {property:
   note.type}` groups by type). Moved out of rowmodel.js at the merge of lane/object-db-public: the row model bares
   only its own keys (rowmodel.js bareModel); this one also bares the display keys a view plugin reads. */

/** A view entry whose property-valued keys say `note.x` read `x`, as filters and `properties:` already do (Bases:
    `note.x` and `x` are one property). WHY: a .base file Obsidian wrote (`image: note.thumbnail`, the object
    library's Objects.base) drew cards with no image, because the views look the key up in `columns` as written.
    Only a key whose `note.`-less name is a column changes; the rest of the entry is returned as is. */
export const PROPERTY_KEYS = ['image', 'media', 'mesh', 'meshView', 'start', 'end', 'title', 'color', 'coordinates', 'markerIcon', 'markerColor'];
export function bareView(view, columns) {
  if (!view || typeof view !== 'object') return view;
  // `formula.nominal` is Bases' name for a column the data names `nominal` (a value with several sources, CONTRACT §36)
  const bare = (p) => (typeof p !== 'string' || columns[p] ? p : p.startsWith('note.') && columns[p.slice(5)] ? p.slice(5) : p.startsWith('formula.') && columns[p.slice(8)] ? p.slice(8) : p);
  let out = view;
  const set = (k, v) => { if (out === view) out = { ...view }; out[k] = v; };
  for (const k of PROPERTY_KEYS) if (typeof view[k] === 'string' && bare(view[k]) !== view[k]) set(k, bare(view[k]));
  for (const k of ['order', 'caption']) if (Array.isArray(view[k]) && view[k].some((p) => bare(p) !== p)) set(k, view[k].map(bare));
  if (view.groupBy && typeof view.groupBy === 'object' && bare(view.groupBy.property) !== view.groupBy.property) set('groupBy', { ...view.groupBy, property: bare(view.groupBy.property) });
  if (Array.isArray(view.sort) && view.sort.some((x) => x && bare(x.property) !== x.property)) set('sort', view.sort.map((x) => (x ? { ...x, property: bare(x.property) } : x)));
  return out;
}
