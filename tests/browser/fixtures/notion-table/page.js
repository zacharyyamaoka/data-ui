/* A made-up host, in this page's memory: the same hooks a real one writes against its own store (docs/CONTRACT.md §40). No storage of
   the rows, so a reload starts over. On `ok` the element applies a delete and a property change to what it holds; an edit and an add are
   the host's to apply (§37), which is the two lines that do anything here. */
const el = document.querySelector('#sheet');
let made = 0;

el.acceptEdit = async ({ row, set }) => { Object.assign(row, set); return { ok: true }; };

el.acceptAdd = async ({ set, id, at, index }) => {
  const row = { ...set, id: id || `made-up-${++made}` };
  const rows = [...el.data.rows];
  // `index`: undo of a delete puts the row back where it was; `at: 'end'`: a pasted block grows the table downwards
  rows.splice(index ?? (at === 'end' ? rows.length : 0), 0, row);
  el.data = { ...el.data, rows };
  return { ok: true, id: row.id };
};

el.acceptDelete = async () => ({ ok: true });
el.acceptProperty = async () => ({ ok: true });
