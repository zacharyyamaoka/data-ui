/* dist/dashboard-edit.js: the dashboard editor. Loaded by <data-dashboard> when a reader presses Edit (or a host calls
   edit()), and only then, so a dashboard nobody edits never pays for it.

   One editor (docs/peps/0017-dashboard-editor.md, docs/CONTRACT.md §41): Edit mode is the base, the
   dashboard itself becomes the editor (Grafana's edit mode); its outline is the layout as a tree beside it (Rerun's
   blueprint, Shopify's section tree), and one options pane shows the selected panel; a short queue holds what is waiting
   to be placed. Both sides drive one text: editor.js. */

import { Editor } from './editor.js';

export async function startEditing(dash) {
  if (dash._editor) return dash._editor;
  const ed = new Editor(dash);
  await ed.enter();
  return ed;
}
