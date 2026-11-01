/* The view registry (docs/CONTRACT.md §1). The model is Obsidian's own Bases view API,
   plugin.registerBasesView(id, {name, icon, factory, options}), with three changes:
     - load() is lazy: a page pays for a view's library only when that view first shows (Vega is 283 KB gzipped;
       a robotparts part page never opens a chart);
     - data edits are proposals (host.propose), never direct writes;
     - tokens arrive resolved, because canvas and SVG libraries cannot read var().

   A plugin is {name, icon, load, options?, status?}. load() resolves to a module (or the class itself) with:
     default        class View { constructor(host, el); update(input); destroy() }
     css?           a stylesheet (text) the host adds to the document once, the first time the view loads
     options?       (view, columns) => [{type, key, displayName, ...}], the view's settings (Obsidian's option types)
   The built-in views are registered from packages/views/<folder>/manifest.json by the build (builtins.js). */

const registry = new Map();
const loaded = new Map();

export function registerView(type, plugin) {
  if (!type || typeof type !== 'string') throw new Error('registerView(type, plugin): type is a string such as "chart"');
  if (registry.has(type)) throw new Error(`a view is already registered for type: ${type}`);
  if (!plugin || typeof plugin.load !== 'function') throw new Error(`registerView('${type}'): the plugin needs load()`);
  registry.set(type, { type, name: plugin.name || type, icon: plugin.icon || null, status: plugin.status || 'built', ...plugin });
}

export function viewPlugin(type) {
  return registry.get(type) || null;
}

/** Every registered view: [{type, name, icon, status}], in registration order. */
export function listViews() {
  return [...registry.values()].map(({ type, name, icon, status }) => ({ type, name, icon, status }));
}

/** Load a view's code once: {View, options, css}. Adds its css to the document the first time. */
export async function loadView(type) {
  if (loaded.has(type)) return loaded.get(type);
  const plugin = registry.get(type);
  if (!plugin) throw new Error(`no view is registered for type: ${type}`);
  const job = (async () => {
    const mod = await plugin.load();
    const View = typeof mod === 'function' ? mod : mod.default;
    if (typeof View !== 'function') throw new Error(`the ${type} view's load() did not resolve to a class`);
    const css = (mod && mod.css) || View.css || null;
    if (css && typeof document !== 'undefined' && !document.querySelector(`style[data-ui-view="${plugin.folder || type}"]`)) {
      const style = document.createElement('style');
      style.dataset.uiView = plugin.folder || type;
      style.textContent = css;
      document.head.append(style);
    }
    const options = plugin.options || (mod && mod.options) || View.options || null;
    return { View, options, css };
  })();
  loaded.set(type, job);
  job.catch(() => loaded.delete(type));
  return job;
}
