/* The built-in views: every packages/views/<folder>/manifest.json, registered by the build (build.mjs supplies the
   `data-ui:views` module). Each loads its own bundle, dist/views/<folder>.js, beside this file, on first use. */

import manifests from 'data-ui:views';
import { registerView } from './registry.js';

for (const m of manifests) {
  registerView(m.type, {
    name: m.name, icon: m.icon, status: m.status, folder: m.folder, summary: m.summary,
    load: () => import(new URL(`./views/${m.folder}.js`, import.meta.url).href),
  });
}
