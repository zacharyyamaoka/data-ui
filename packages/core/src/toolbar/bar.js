/* The bar (docs/CONTRACT.md §15, toolbar="bar"): the view selector, the filter control, the Display button and the
   filter pills. The query box (.dv-bar-query) and the bulk bar (.dv-bulk) are lane B's (query.js, selection.js); the
   View settings panel / popover is settings.js. The why and the forks are docs/peps/0002-toolbar.md.

   Zach's pick of 2026-10-26, "Definitely yes I like the mix": P6's Shopify pill bar, Obsidian Bases' view menu inside
   the view chip, filter pills and the rail showing the same state both ways, a Layout row in the settings. His notes:
   zach_brain Sources/Daily Notes/Daily Note - Oct 26 2026.md. The variants are attributes of the element:

     views="auto|dropdown|tabs"                   the chip (Bases), the tabs (Notion), or tabs while they all fit
     filters="pills expanded query-tokens rail"   a set: pills under the bar, Obsidian's spread-out words, tokens in
                                                  the query box (lane B), a Filters toggle for the linked rail
     display="panel|popover"                      settings.js

   mountBar(el) -> {update(), configure(), openMenu(name), destroy()}. update() runs on every render and redraws only
   what changed (a key per part), so focus and an open menu survive a redraw. Every control carries data-bar="…", which
   the element's click handler reads as "not a click outside the menu". */

import * as G from '../grammar.js';
import { esc } from '../format.js';
import { toRail, fromRail, facetSpecs, railConfig, ref } from '../facets.js';
import { listViews } from '../registry.js';
import { clauseToken, valueLabel } from './query.js';
import { icon, LAYOUTS, layoutName, layoutIcon } from './icons.js';
import { frameOf } from '../frame.js';
import { openColumnFilter } from './column-filter.js';

const QUERY_MIN = 200; // px the query box keeps beside the views and the tools (styles/toolbar.css .dv-bar-query)
const store = {
  get(key) { try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private window: lasts this visit */ } },
};

// ------------------------------------------------------------------ shared with settings.js

/** The layout grid (robotparts' 3 × 4 of Zach's screenshot 20261026122246): every layout the kit knows, the built
    ones pressable, a planned one greyed. `current` is marked. */
export function layoutGrid(current) {
  const built = new Map(listViews().filter((t) => t.status !== 'planned').map((t) => [t.type, t]));
  const known = new Set(LAYOUTS.map(([type]) => type));
  const extra = [...built.keys()].filter((t) => !known.has(t)).map((t) => [t, built.get(t).name || t]);
  const cell = ([type, name]) => {
    const on = type === current;
    const ok = built.has(type);
    return `<button type="button" class="dv-layout${on ? ' dv-on' : ''}" data-type="${esc(type)}" aria-pressed="${on}"${ok ? '' : ' disabled title="Planned: not built yet"'}>${icon(layoutIcon(type))}<span>${esc(name)}</span></button>`;
  };
  return `<div class="dv-layouts" role="group" aria-label="Layout">${[...LAYOUTS, ...extra].map(cell).join('')}</div>`;
}

/** Rename the open view: a user view in place; a view of the .base file saves a copy of it under the new name (the
    file's views are the file's; a browser never rewrites them). */
export function renameView(el, name) {
  const to = String(name || '').trim();
  if (!to || to === el.origin.name) return false;
  if (el.origin.kind === 'user') return el._renameUser(el.origin.name, to);
  el.saveView(to);
  return true;
}

/** Copy text; the button says whether it worked (a page without clipboard access asks for a manual copy). */
export function copyText(text, button, done = 'Copied') {
  const label = button.querySelector('.dv-set-label, span:last-child') || button;
  const was = label.textContent;
  const say = (t) => { label.textContent = t; setTimeout(() => { if (label.isConnected) label.textContent = was; }, 1400); };
  try { Promise.resolve(navigator.clipboard.writeText(text)).then(() => say(done), () => say('Copy blocked: select the text')); } catch { say('Copy blocked: select the text'); }
}

/** The bar's filter count: one per pill (a facet's values are one) plus the view's own filters. */
export function filterCount(el) {
  return pillList(el).length + G.filterList(el.view && el.view.filters).length;
}

// ------------------------------------------------------------------ pills: the all-views filter, one pill per part

/** A filter node as Bases text: a string as it is, an {and | or | not} as its expression. */
function exprText(node) {
  if (typeof node === 'string') return node;
  if (!node || typeof node !== 'object') return String(node);
  const wrap = (x) => { const t = exprText(x); return typeof x === 'string' ? t : `(${t})`; };
  if (Array.isArray(node.and)) return node.and.map(wrap).join(' && ');
  if (Array.isArray(node.or)) return node.or.map(wrap).join(' || ');
  if (Array.isArray(node.not)) return `!(${node.not.map(exprText).join(' || ')})`;
  return JSON.stringify(node);
}

const show = (v) => (typeof v === 'string' ? v : String(v));

/** What a pill can read as words. §40: on an edit-toggle page any column can have a hand filter, not only the ones the rail declares. */
function pillConfig(el, props) {
  if (el._hasSwitch && el._hasSwitch()) return railConfig(Object.keys(props).flatMap((p) => [{ property: p, as: 'values', exclude: true }, { property: p, as: 'range' }, { as: 'has', properties: [p] }]));
  return railConfig(facetSpecs(el.base, el.view, props));
}

/** Every clause of the all-views filter (el.filters, the rail's) as a pill: [{text, property?, drop?, rest?}].
    A facet-shaped part reads as the rail draws it (toRail with the open view's rail), so ticking Steadywin and
    CubeMars is one pill, "Brand: Steadywin, CubeMars"; a custom clause shows verbatim (query.js clauseToken). */
export function pillList(el) {
  if (!el._model || !el.base) return [];
  const props = el._model.columns;
  const cfg = pillConfig(el, props);
  const rail = toRail(el.filters, cfg);
  const label = (p) => (props[p] ? props[p].label : p);
  const unit = (p) => (props[p] && props[p].unitText ? ` ${props[p].unitText}` : '');
  const out = [];
  for (const [p, f] of Object.entries(rail.facets)) {
    const name = label(p);
    // WHY the label: a stored slug ("steadywin") reads as the rail and the query box read it ("Steadywin"; query.js)
    const shown = (v) => valueLabel(props, p, v);
    if (f.values && f.values.length) out.push({ text: `${name}: ${f.values.map(shown).join(', ')}`, property: p, drop: ['values', 'match'] });
    if (f.exclude && f.exclude.length) out.push({ text: `${name} is not ${f.exclude.map(shown).join(', ')}`, property: p, drop: ['exclude', 'excludeMatch'] });
    const lo = f.min !== undefined && f.min !== null, hi = f.max !== undefined && f.max !== null;
    if (lo || hi) {
      const text = lo && hi ? `${name}: ${show(f.min)}${f.minOpen ? ' (excl.)' : ''}–${f.maxOpen ? '<' : ''}${show(f.max)}${unit(p)}`
        : lo ? `${name} ${f.minOpen ? '>' : '≥'} ${show(f.min)}${unit(p)}` : `${name} ${f.maxOpen ? '<' : '≤'} ${show(f.max)}${unit(p)}`;
      out.push({ text, property: p, drop: ['min', 'minOpen', 'max', 'maxOpen'] });
    }
    if (f.has) out.push({ text: `Has ${name}`, property: p, drop: ['has'] });
    if (f.hasAny && f.hasAny.length) out.push({ text: `Has any of ${f.hasAny.map(label).join(', ')}`, property: p, drop: ['hasAny'] });
    if (f.text !== undefined && f.text !== '') out.push({ text: `${name} ${f.textMatch === 'startsWith' ? 'starts with' : 'contains'} “${f.text}”`, property: p, drop: ['text', 'textIn', 'textMatch'] });
  }
  rail.rest.forEach((node, i) => {
    const expr = exprText(node);
    let text = expr;
    try { const t = clauseToken(expr, props); if (t && t.label) text = String(t.label); } catch { /* the stub or a clause query.js cannot read: verbatim */ }
    // §40: the hand filter's is-empty, in words, and its pill opens its column's control
    const column = el._hasSwitch && el._hasSwitch() ? Object.keys(props).find((p) => expr === `${ref(p)}.isEmpty()`) : undefined;
    out.push(column ? { text: `${label(column)} is empty`, rest: i, column } : { text, rest: i });
  });
  return out;
}

/** Remove one pill's part of the all-views filter; the rail hears the change event and unticks. */
function removePill(el, pill) {
  const cfg = pillConfig(el, el._model.columns);
  const rail = toRail(el.filters, cfg);
  if (pill.property) {
    const f = rail.facets[pill.property];
    if (f) for (const k of pill.drop) delete f[k];
    if (f && !Object.keys(f).some((k) => !['match', 'excludeMatch', 'minOpen', 'maxOpen', 'textIn', 'textMatch'].includes(k))) delete rail.facets[pill.property];
  } else rail.rest.splice(pill.rest, 1);
  el.filters = fromRail(rail.facets, rail.rest);
}

// ------------------------------------------------------------------ "/" focuses one bar's query box

let lastBar = null;
export const textField = (a) => !!a && (a.isContentEditable || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT'
  || (a.tagName === 'INPUT' && !/^(checkbox|radio|range|button|submit|reset|color|file|image)$/.test(a.type)));

/** '/' on the page (the element's own document keydown handler calls this; no listener of this module's): true when
    it focused `el`'s query box. WHY one bar: a page with several tables must not focus them all; the one under the
    pointer or last used wins, else the first on the page. The page's own header search stays the global site search
    (Zach, 2026-10-26). */
export function slashKey(el, e) {
  if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented || textField(document.activeElement)) return false;
  const target = lastBar && lastBar.isConnected && lastBar._barUi ? lastBar : [...document.querySelectorAll('data-views')].find((x) => x._barUi);
  if (target !== el) return false;
  e.preventDefault();
  el.openMenu('query');
  return true;
}

// ------------------------------------------------------------------ the bar

export function mountBar(el) {
  const barEl = el.$('.dv-bar');
  const viewsSlot = el.$('.dv-bar-views');
  const tools = el.$('.dv-bar-tools');
  const pillsEl = el.$('.dv-pills');
  const keys = { tools: '', pills: '', views: '' };
  let pills = [];
  let width = 0;
  if (!el._dvBarTracked) {
    el._dvBarTracked = true;
    const mark = () => { lastBar = el; };
    el.addEventListener('pointerover', mark);
    el.addEventListener('focusin', mark);
  }

  const viewsAttr = () => { const v = el.getAttribute('views'); return v === 'dropdown' || v === 'tabs' ? v : 'auto'; };
  const modes = () => el._filterModes();
  const allViews = () => [...el.presets.map((v) => ['preset', v]), ...el._userViews().map((v) => ['user', v])];
  const isCurrent = (kind, v) => el.origin && el.origin.kind === kind && el.origin.name === v.name;
  const typeOf = (kind, v) => (isCurrent(kind, v) ? el.view.type : v.type) || 'table';

  // ---- the rail toggle (filters="… rail"): <data-facets for=<id>> shown or hidden, remembered per element
  const rails = () => (el.id ? [...document.querySelectorAll(`data-facets[for="${CSS.escape(el.id)}"]`)] : []);
  const railKey = () => `data-ui/rail-open/${el.id}`;
  const railOpen = () => store.get(railKey()) !== false;
  function applyRail() {
    const on = modes().includes('rail');
    const open = !on || railOpen();
    for (const r of rails()) {
      if (!open) { r.hidden = true; r._dvBarHidden = true; } else if (r._dvBarHidden) { r.hidden = false; r._dvBarHidden = false; }
    }
    // WHY a class on the element: the host's grid keeps a track for the rail; `dv-rail-off` lets the views span it
    el.classList.toggle('dv-rail-off', !open && rails().length > 0);
  }

  // ---- the tools: the search icon, the rail toggle, the filter control, Reset / Save view, the "…" overflow, Display.
  // Every tool carries data-tool (its id in DEGRADE): the one-row layout below drops its label, folds its count or
  // moves it into the overflow menu by that id.
  function drawTools() {
    const v = el.view;
    const props = el._model.columns;
    const label = (id) => (props[id] ? props[id].label : id);
    const n = filterCount(el);
    const railed = railDriven();
    const shown = promoted();
    // WHY words that say what is set (Obsidian, Zach's screenshot 20261026122424): "Sort: Peak torque" reads the state
    // without opening anything. Each is the same control as its View settings page: same state, same body (_openMenu)
    const levels = [v.groupBy, v.subGroupBy].filter(Boolean);
    const sort = v.sort || [];
    const text = {
      sort: sort.length ? `Sort: ${label(sort[0].property)}${sort.length > 1 ? ` +${sort.length - 1}` : ''}` : 'Sort',
      // a time level reads its grain, as the full toolbar's Group does ("Group: Started by week"; CONTRACT §14)
      group: levels.length ? `Group: ${levels.map((g) => label(g.property) + (g.by ? ` by ${g.by}` : '')).join(' › ')}` : 'Group',
      filter: 'Filter',
      properties: 'Properties',
    };
    const set = { sort: sort.length, group: levels.length, filter: n, properties: 0 };
    const ic = { sort: 'sort', group: 'group', filter: 'filter', properties: 'props' };
    const open = el._settingsUi && el._settingsUi.isOpen();
    // CONTRACT §40: the Edit / View switch, on an edit-toggle page
    const switched = el._hasSwitch ? el._hasSwitch() : false;
    const editing = switched && el.editing;
    const key = JSON.stringify([shown, text, n, railed, railed && railOpen(), el.dirty, open, searchOpen, labelsAttr(), switched, editing]);
    if (key === keys.tools) return;
    keys.tools = key;
    // aria-label and title on every tool: when the bar is short of room (or labels="icons") its label drops and the
    // icon speaks for it
    const word = (name) => {
      const said = name === 'filter' && n ? `Filter (${n})` : text[name];
      // the one Filter button drives the linked rail when filters has "rail" (Zach: "Why do you have Filter twice?")
      const rail = name === 'filter' && railed ? ` aria-pressed="${railOpen()}" title="Filter: show or hide the filter rail"` : ` aria-haspopup="dialog" aria-expanded="false" title="${esc(said)}"`;
      return `<button type="button" class="dv-bar-btn dv-bar-word${set[name] ? ' dv-set' : ''}" data-bar="menu" data-name="${name}" data-tool="${name}" aria-label="${esc(said)}"${rail}>${icon(ic[name])}<span class="dv-bar-label">${esc(text[name])}</span>${name === 'filter' && n ? `<span class="dv-bar-count">${n}</span>` : ''}</button>`;
    };
    tools.innerHTML = [
      `<button type="button" class="dv-bar-btn dv-bar-search" data-bar="search" data-tool="search" aria-label="Search" aria-expanded="${searchOpen}" title="Search (/)">${icon('search')}</button>`,
      shown.map(word).join(''),
      el.dirty ? '<button type="button" class="dv-bar-btn" data-bar="reset" data-tool="reset" title="Back to the view as saved">Reset</button><button type="button" class="dv-bar-btn dv-bar-save" data-bar="save" data-tool="save" aria-haspopup="dialog">Save view</button>' : '',
      switched ? `<button type="button" class="dv-bar-btn dv-bar-edit${editing ? ' dv-on' : ''}" data-bar="edit" data-tool="edit" data-edit-switch role="switch" aria-checked="${editing}" aria-label="Edit" title="Edit: change the data here. View: read only.">${icon('pencil')}<span class="dv-bar-label">Edit</span><span class="dv-switch" aria-hidden="true"></span></button>` : '',
      `<button type="button" class="dv-bar-btn dv-bar-overflow" data-bar="overflow" data-tool="overflow" aria-haspopup="menu" aria-expanded="false" aria-label="More" title="More" hidden>${icon('more')}</button>`,
      `<button type="button" class="dv-bar-btn dv-bar-display${open ? ' dv-on' : ''}" data-bar="display" data-tool="display" aria-haspopup="dialog" aria-expanded="${!!open}" aria-label="Display" title="View settings: layout, frame, properties, filter, sort, group">${icon('sliders')}<span class="dv-bar-label">Display</span></button>`,
    ].join('');
    // a menu open under a word ("Sort: Mass" just became "Sort: Peak torque") follows the word's new button, so its
    // next redraw stays anchored there
    const p = el.$('.dv-pop');
    if (p && !p.hidden && p._for && !p._for.isConnected && p._for.dataset.bar) {
      const again = tools.querySelector(`[data-bar="${p._for.dataset.bar}"]${p._for.dataset.name ? `[data-name="${p._for.dataset.name}"]` : ''}`);
      if (again) { p._for = again; again.setAttribute('aria-expanded', 'true'); }
    }
  }

  // ---- the pills (filters="pills"; query-tokens draws them in the box instead)
  function drawPills() {
    const m = modes();
    pills = m.includes('pills') && !m.includes('query-tokens') ? pillList(el) : [];
    const key = JSON.stringify(pills.map((p) => p.text));
    if (key === keys.pills) return;
    keys.pills = key;
    // WHY nothing at rest: one quiet row until a filter exists (Zach's calm-UI rule); :empty hides the row
    pillsEl.innerHTML = pills.length ? `${pills.map((p, i) => `<span class="dv-pill"><button type="button" class="dv-pill-body" data-bar="pill" data-i="${i}" title="Edit the filters">${esc(p.text)}</button><button type="button" class="dv-pill-x" data-bar="pill-x" data-i="${i}" aria-label="Remove the filter ${esc(p.text)}" title="Remove">${icon('x')}</button></span>`).join('')}<button type="button" class="dv-pill-add" data-bar="pill-add" aria-haspopup="dialog">${icon('plus')}<span>Filter</span></button><button type="button" class="dv-pill-clear" data-bar="pill-clear">Clear</button>` : '';
  }

  // ---- the views: the chip (Bases) or the tabs (Notion), or tabs while they all fit (auto)
  const chipHtml = () => {
    const v = el.view;
    return `<button type="button" class="dv-viewchip" data-bar="views" aria-haspopup="dialog" aria-expanded="false" title="Views">${icon(layoutIcon(v.type))}<span class="dv-viewchip-name">${esc(el.origin.name)}</span>${el.origin.kind === 'user' ? '<span class="dv-mine" title="Your view, saved in this browser">•</span>' : ''}<span class="dv-chev">${icon('updown')}</span></button>`;
  };
  const stripHtml = (list) => `<div class="dv-viewtabs" role="tablist" aria-label="Views">${list.map(([kind, v]) => {
    const on = isCurrent(kind, v);
    return `<button type="button" role="tab" class="dv-vtab${on ? ' dv-on' : ''}" aria-selected="${on}" data-bar="tab" data-kind="${kind}" data-name="${esc(v.name)}" title="${esc(v.name)}" aria-label="${esc(v.name)}">${icon(layoutIcon(typeOf(kind, v)))}<span>${esc(v.name)}</span>${kind === 'user' ? '<span class="dv-mine" title="Your view, saved in this browser">•</span>' : ''}</button>`;
  }).join('')}<button type="button" class="dv-vtab-more" data-bar="more" aria-haspopup="dialog" aria-expanded="false">${list.length} more…</button><button type="button" class="dv-vtab-add" data-bar="add-view" aria-haspopup="dialog" aria-label="Add view" title="Add view">${icon('plus')}</button></div>`;

  // ---- the filters default (no `filters` attribute; §15 note 2026-10-26): the views decide. WHY (Zach, 2026-10-26): "If
  // you have these quick-switch views visible, then usually the pattern should be to make the filters more hidden (this
  // is the Notion pattern)": views as tabs => the filters fold (one Filter button, pills once a filter is set); views
  // in the chip => Sort · Group · Filter · Properties as words (Obsidian). An explicit attribute always wins.
  let viewsAs = viewsAttr() === 'dropdown' ? 'chip' : 'tabs';
  // the views decide the filter control (and its pills) when the page says neither filters nor promote
  const defaulted = () => !el.hasAttribute('filters') && !el.hasAttribute('promote');
  function filterModes() {
    const given = el.getAttribute('filters');
    if (given !== null) return given.split(/\s+/).filter(Boolean);
    return [viewsAs === 'chip' ? 'expanded' : 'pills'];
  }

  // ---- one model for the controls (§15 note 2026-10-26, "promote"). WHY (Zach, 2026-10-26: "I don't like how you have
  // Filter outside and also inside the Display dropdown"): the right-most control, Display (View settings), always holds
  // everything (layout, frame, properties, filter, sort, group); any of filter, sort, group and properties may ALSO be
  // promoted onto the bar, and a promoted control is the same control: the same state and the same body
  // (data-views.js _openMenu), opened anchored to it. `promote="…"` (a set, in bar order sort group filter properties;
  // "" promotes none: Shopify's three elements) wins; else filters="expanded" (an alias) promotes all four; else an
  // explicit filters attribute promotes Filter; else the views decide: tabs => Filter, the chip => all four.
  const PROMOTABLE = ['sort', 'group', 'filter', 'properties'];
  function promoted() {
    const given = el.getAttribute('promote');
    if (given !== null) { const want = given.split(/\s+/); return PROMOTABLE.filter((x) => want.includes(x)); }
    if (filterModes().includes('expanded')) return [...PROMOTABLE];
    if (el.hasAttribute('filters')) return ['filter'];
    return viewsAs === 'chip' ? [...PROMOTABLE] : ['filter'];
  }
  /** filters="… rail" with a linked <data-facets>: the one Filter control shows and hides the rail. */
  const railDriven = () => filterModes().includes('rail') && rails().length > 0;
  // labels="auto|icons": icons keeps every tool's label off (tooltips and aria-labels stay); auto drops them by need
  const labelsAttr = () => (el.getAttribute('labels') === 'icons' ? 'icons' : 'auto');

  // ---- one row, always (§15 note 2026-10-26, "the bar is one row"). Zach: "How the table toolbar folds to two lines?
  // I don't like that… I feel it should be 1 bar … I can see it never splits on top into multiple lines" (Shopify's
  // one pill bar; Obsidian Bases at three widths: words, then icons, then the view chip and a few icons). So the bar
  // never wraps; as ITS OWN width shrinks it takes these steps, in this order, until it fits (the priority+ pattern).
  // The view tabs are elastic first: they show as many as fit and fold the rest into "N more" (Notion), so a long list
  // of views never costs a label; then labels drop to icons (lowest priority first; labels="icons": off from the start), low-priority controls move into
  // the "…" menu, the query box folds to its icon, the tabs fold to the one view chip (Obsidian), the filter count
  // drops, the chip drops its name. Each step keeps the ones before it, so what is iconised and what is in the menu
  // only grows as the bar narrows. Display (View settings, the home for everything) and the view selector never leave
  // the row; the open view's tab always shows while there are tabs.
  // ('edit', CONTRACT §40: present only on an edit-toggle page, so its steps change nothing for any other bar)
  const DEGRADE = [
    ['icon', 'edit'], ['icon', 'properties'], ['icon', 'group'], ['icon', 'sort'], ['icon', 'filter'], ['icon', 'display'],
    ['menu', 'reset'], ['menu', 'add'], ['menu', 'edit'], ['menu', 'properties'], ['menu', 'group'],
    ['search', 'icon'], ['menu', 'sort'], ['menu', 'save'],
    ['views', 'chip'], ['count', 'filter'], ['menu', 'filter'], ['views', 'compact'],
  ];
  const VIEW_STEP = { tabs: 0, chip: 1, compact: 2 };
  // WHY a floor for the open tab: it shrinks with an ellipsis (its full name stays in its title and aria-label) before
  // anything can overlap; the fit is a hard constraint (robotparts' Config page at 375 px: a 240 px first tab pushed
  // "2 more…" and + under the tools)
  const TAB_MIN = 88;
  let rowState = null; // what was written last: {views, icon: Set, menu: Set, count, search}
  let measured = { key: null };

  /** Natural widths (px) of every control in each of its forms, measured once per content and cached: the tabs, "N
      more" and +, the chip (with and without its name), each tool with its label, as an icon, and without its count. */
  function measure(list) {
    const toolsKey = tools.innerHTML;
    const key = JSON.stringify([toolsKey, list.map(([k, v]) => [k, v.name, typeOf(k, v), isCurrent(k, v)]), el.origin.kind, el.origin.name, el.view.type, viewsAttr()]);
    if (measured.key === key) return measured;
    const w = (e) => (e ? e.getBoundingClientRect().width : 0);
    const out = { key };
    const cs = getComputedStyle(barEl);
    out.gap = parseFloat(cs.columnGap) || 0;
    out.pad = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    // the views: the strip, then the chip, in the slot itself (one layout each; the real form is written afterwards)
    if (list.length) {
      viewsSlot.innerHTML = stripHtml(list);
      const strip = viewsSlot.firstElementChild;
      out.sgap = parseFloat(getComputedStyle(strip).columnGap) || 0;
      out.tabs = [...strip.querySelectorAll('[data-bar=tab]')].map(w);
      out.more = w(strip.querySelector('[data-bar=more]'));
      out.add = w(strip.querySelector('[data-bar=add-view]'));
    } else { out.sgap = 0; out.tabs = []; out.more = 0; out.add = 0; }
    viewsSlot.innerHTML = chipHtml();
    const chip = viewsSlot.firstElementChild;
    out.chip = w(chip);
    chip.classList.add('dv-compact');
    out.compact = w(chip);
    // the tools: as labelled, as icons, as icons without the count (classes on, measured, off)
    const items = [...tools.querySelectorAll('[data-tool]')];
    const was = items.map((t) => t.hidden);
    items.forEach((t) => { t.hidden = false; t.classList.remove('dv-iconic', 'dv-nocount'); });
    tools.classList.add('dv-measuring');
    out.tools = {};
    for (const t of items) out.tools[t.dataset.tool] = { label: w(t) };
    items.forEach((t) => t.classList.add('dv-iconic'));
    for (const t of items) out.tools[t.dataset.tool].icon = w(t);
    items.forEach((t) => t.classList.add('dv-nocount'));
    for (const t of items) out.tools[t.dataset.tool].bare = w(t);
    items.forEach((t, i) => { t.classList.remove('dv-iconic', 'dv-nocount'); t.hidden = was[i]; });
    tools.classList.remove('dv-measuring');
    out.tgap = parseFloat(getComputedStyle(tools).columnGap) || 0;
    rowState = null; // the slot was rewritten while measuring: the next write draws the views again
    measured = out;
    return out;
  }

  /** The state after the first k steps of DEGRADE, for the controls present. */
  function stateAt(k, present, want, searchBox) {
    const st = { views: want === 'dropdown' ? 'chip' : 'tabs', icon: new Set(), menu: new Set(), count: true, search: searchBox ? 'box' : 'icon' };
    if (labelsAttr() === 'icons') for (const id of present) if (id !== 'reset' && id !== 'save') st.icon.add(id);
    for (const [kind, what] of DEGRADE.slice(0, k)) {
      if (kind === 'icon' && present.has(what)) st.icon.add(what);
      else if (kind === 'menu' && present.has(what)) st.menu.add(what);
      else if (kind === 'count') st.count = false;
      else if (kind === 'search') st.search = 'icon';
      else if (kind === 'views') {
        // a pinned `tabs` folds to "N more" at most (it stays tabs); a pinned `dropdown` is the chip already
        const to = want === 'tabs' ? 'tabs' : what;
        if (VIEW_STEP[to] > VIEW_STEP[st.views]) st.views = to;
      }
    }
    return st;
  }

  /** The width a state needs (px), from the measured widths: pure arithmetic, no layout. */
  function widthOf(st, mz, present, list) {
    let views;
    if (!list.length || st.views === 'chip') views = mz.chip;
    else if (st.views === 'compact') views = mz.compact;
    else {
      // tabs: elastic, from every tab down to the open one, "N more" and + (write() shows as many as the row leaves)
      const cur = Math.max(0, list.findIndex(([k, v]) => isCurrent(k, v)));
      const add = st.menu.has('add') ? 0 : mz.add + mz.sgap;
      const all = mz.tabs.reduce((x, y) => x + y, 0) + mz.sgap * (mz.tabs.length - 1) + add;
      views = Math.min(all, Math.min(mz.tabs[cur] || 0, TAB_MIN) + (mz.tabs.length > 1 ? mz.more + mz.sgap : 0) + add);
    }
    const slot = st.search === 'box' ? QUERY_MIN : 0;
    let toolsW = 0, n = 0;
    for (const id of present) {
      if (id === 'overflow' || id === 'add' || (id === 'search' && st.search === 'box') || st.menu.has(id)) continue;
      const t = mz.tools[id];
      toolsW += !st.icon.has(id) ? t.label : (id === 'filter' && !st.count ? t.bare : t.icon);
      n++;
    }
    if (st.menu.size) { toolsW += mz.tools.overflow.icon; n++; }
    toolsW += Math.max(0, n - 1) * mz.tgap;
    return views + slot + toolsW + 2 * mz.gap;
  }

  /** Fit the bar on one row: measure (cached), take the fewest DEGRADE steps that fit, write the result once. */
  function layoutRow(force = false) {
    const width = barEl.clientWidth;
    if (!width) return;
    const want = viewsAttr();
    const list = allViews();
    const searchBox = el.getAttribute('search') !== 'icon';
    // under auto with the default filters, how far the views fold is decided with the folded filter control (the
    // tabs' form), so the answer cannot flip back and forth; the chip's words are then fitted with the chip pinned
    if (want === 'auto' && defaulted() && viewsAs !== 'tabs') { viewsAs = 'tabs'; keys.tools = ''; drawTools(); }
    let mz = measure(list);
    const inner = width - mz.pad;
    // + (Add view) is a control of the tab strip; it can move into "…" like a tool
    const present = () => { const ids = new Set([...tools.querySelectorAll('[data-tool]')].map((t) => t.dataset.tool)); if (list.length && want !== 'dropdown') ids.add('add'); return ids; };
    const pick = (pinChip) => {
      const have = present();
      const w2 = pinChip && want === 'auto' ? 'dropdown' : want;
      let k = 0, st;
      for (; k <= DEGRADE.length; k++) { st = stateAt(k, have, w2, searchBox); if (widthOf(st, mz, have, list) <= inner) break; }
      return st || stateAt(DEGRADE.length, have, w2, searchBox);
    };
    let st = pick(false);
    const kind = st.views === 'chip' || st.views === 'compact' ? 'chip' : 'tabs';
    if (kind !== viewsAs) {
      viewsAs = kind;
      if (defaulted()) {
        keys.tools = keys.pills = '';
        drawTools();
        drawPills();
        mz = measure(list);
        if (kind === 'chip') { const again = pick(true); again.views = st.views === 'compact' ? 'compact' : again.views; st = again; }
      }
    }
    write(st, mz, list, inner, force);
  }

  /** Write a state: the views (chip, or the tabs that fit and "N more"), the tools' forms, the overflow, the search. */
  function write(st, mz, list, inner, force) {
    const sig = JSON.stringify([st.views, [...st.icon], [...st.menu], st.count, st.search, Math.round(inner), measured.key]);
    if (!force && rowState === sig) return;
    rowState = sig;
    // the tools first, then the views. WHY this order: the strip's hard constraint below reads the drawn row, so the
    // tools and the query slot must already be in this state's form; drawn after the views, the previous state's
    // labelled tools squeezed the strip and the open tab shrank to 40-60 px with room to spare (robotparts 2026.10.26.12
    // at 360-430 px, tests/browser/toolbar_polish_checks.py)
    for (const t of tools.querySelectorAll('[data-tool]')) {
      const id = t.dataset.tool;
      if (id === 'overflow') { t.hidden = !st.menu.size; continue; }
      if (id === 'search') { t.hidden = st.search === 'box'; continue; }
      t.hidden = st.menu.has(id);
      t.classList.toggle('dv-iconic', st.icon.has(id));
      t.classList.toggle('dv-nocount', id === 'filter' && !st.count);
    }
    overflowIds = [...st.menu];
    searchSqueezed = st.search === 'icon' && el.getAttribute('search') !== 'icon';
    barEl.classList.toggle('dv-search-icon', searchIcon());
    // the views
    if (!list.length || st.views === 'chip' || st.views === 'compact') {
      if (!viewsSlot.querySelector('.dv-viewchip')) viewsSlot.innerHTML = chipHtml();
      viewsSlot.firstElementChild.classList.toggle('dv-compact', st.views === 'compact');
    } else {
      viewsSlot.innerHTML = stripHtml(list);
      const strip = viewsSlot.firstElementChild;
      const tabs = [...strip.querySelectorAll('[data-bar=tab]')];
      const more = strip.querySelector('[data-bar=more]');
      const add = strip.querySelector('[data-bar=add-view]');
      add.hidden = st.menu.has('add');
      const addW = add.hidden ? 0 : mz.add + mz.sgap;
      // the room the tabs have is what the rest of the row leaves them
      const have = new Set([...tools.querySelectorAll('[data-tool]')].map((t) => t.dataset.tool));
      const avail = inner - widthOf({ ...st, views: 'chip' }, { ...mz, chip: 0 }, have, list);
      const cur = Math.max(0, list.findIndex(([k, v]) => isCurrent(k, v)));
      const all = mz.tabs.reduce((x, y) => x + y, 0) + mz.sgap * (tabs.length - 1) + addW;
      let shown = tabs.map((_, i) => i);
      if (all > avail) {
        let used = mz.more + mz.sgap + addW;
        shown = [];
        for (let i = 0; i < tabs.length; i++) {
          if (used + mz.tabs[i] + mz.sgap > avail) break;
          shown.push(i);
          used += mz.tabs[i] + mz.sgap;
        }
        // the open view's tab always shows: it takes the place of the last ones that fit (Notion brings it in)
        if (!shown.includes(cur)) {
          while (shown.length && used + mz.tabs[cur] + mz.sgap > avail) used -= mz.tabs[shown.pop()] + mz.sgap;
          shown.push(cur);
          used += mz.tabs[cur] + mz.sgap;
        }
        // and when even it does not fit beside "N more", it shrinks (an ellipsis; the full name is its title), never
        // under TAB_MIN: the plan (widthOf) only keeps the tabs when that much is left, else the views fold to the chip
        const room = avail - (used - mz.tabs[cur]);
        tabs[cur].style.maxWidth = shown.length === 1 && room < mz.tabs[cur] ? `${Math.max(Math.min(TAB_MIN, mz.tabs[cur]), Math.floor(room))}px` : '';
      }
      tabs.forEach((t, i) => { t.hidden = !shown.includes(i); });
      const hidden = tabs.length - shown.length;
      more.hidden = !hidden;
      more.textContent = `${hidden} more…`;
      // the hard constraint, checked once on the drawn strip: nothing it holds may be clipped (so nothing overlaps).
      // A last resort, e.g. views="tabs" pinned so there is no chip to fold to; the floor above holds whenever the plan fits
      const over = strip.scrollWidth - strip.clientWidth;
      if (over > 1) tabs[cur].style.maxWidth = `${Math.max(40, Math.floor(tabs[cur].getBoundingClientRect().width - over))}px`;
    }
    setSearch(searchOpen);
  }

  // the "…" menu: every control the row has no room for, by keyboard too (arrows move, Enter runs, Escape closes)
  let overflowIds = [];
  function openOverflow(btn) {
    const items = overflowIds.filter((id) => id !== 'add').map((id) => tools.querySelector(`[data-tool="${id}"]`)).filter(Boolean);
    const addItem = overflowIds.includes('add') ? `<button type="button" role="menuitem" class="dv-overflow-item" data-run="add">${icon('plus')}<span>Add view</span></button>` : '';
    const html = `<div class="dv-overflow" role="menu" aria-label="More">${items.map((t) => {
      const text = t.getAttribute('aria-label') || t.textContent.trim();
      const ic = t.querySelector('.dv-i');
      // a switch stays a switch here (§40): its state in the item, a check beside its word
      const on = t.getAttribute('aria-checked');
      const state = on === null ? 'role="menuitem"' : `role="menuitemcheckbox" aria-checked="${on}"`;
      return `<button type="button" ${state} class="dv-overflow-item" data-run="${esc(t.dataset.tool)}">${ic ? ic.outerHTML : '<span class="dv-i"></span>'}<span>${esc(text)}</span>${on === 'true' ? icon('check') : ''}</button>`;
    }).join('')}${addItem}</div>`;
    el._pop(btn, html, (p) => {
      const rows = [...p.querySelectorAll('[data-run]')];
      p.addEventListener('keydown', (e) => {
        const at = rows.indexOf(document.activeElement);
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); rows[(at + (e.key === 'ArrowDown' ? 1 : rows.length - 1)) % rows.length].focus(); }
        else if (e.key === 'Home') { e.preventDefault(); rows[0].focus(); }
        else if (e.key === 'End') { e.preventDefault(); rows[rows.length - 1].focus(); }
      });
      rows.forEach((r) => r.addEventListener('click', stop(() => {
        const t = tools.querySelector(`[data-tool="${r.dataset.run}"]`);
        el.closeMenu();
        if (r.dataset.run === 'add') addView(false, btn);
        else if (t) act(t, btn);
      })));
    }, 'dv-overflowmenu');
  }

  // ---- search="icon" (§15 note 2026-10-26): the query box waits behind a Search icon and grows in place when it is
  // wanted. WHY in place: the box's slot keeps its room in the bar whether open or not, so opening it moves nothing else
  // (Notion's database search); it stays open while it holds words or tokens, and folds again when it is empty and left.
  const qslot = el.$('.dv-bar-query');
  // the box is an icon when the page asks (search="icon") or when the one-row layout has no room for it
  let searchSqueezed = false;
  const searchIcon = () => el.getAttribute('search') === 'icon' || searchSqueezed;
  let searchOpen = false;
  function hasQuery() {
    const input = qslot.querySelector('input');
    // words typed or searched, or (filters="query-tokens") clauses that show as tokens in the box
    return !!((input && input.value.trim()) || el.query || qslot.querySelector('.dv-qtoken')
      || (filterModes().includes('query-tokens') && G.filterList(el.filters).length));
  }
  function setSearch(open) {
    const icon = searchIcon();
    searchOpen = icon && (open || hasQuery());
    barEl.classList.toggle('dv-search-icon', icon);
    barEl.classList.toggle('dv-search-open', searchOpen);
    // no room in the row for the open box: it opens over the views and the query slot, up to the tools, which stay put
    const slotW = qslot.getBoundingClientRect().width;
    const over = searchOpen && slotW < 160;
    barEl.classList.toggle('dv-search-over', over);
    if (over) {
      const br = barEl.getBoundingClientRect(), tr = tools.getBoundingClientRect();
      barEl.style.setProperty('--dv-search-right', `${Math.round(br.right - tr.left + 6)}px`);
    }
    // a folded box is out of the tab order and the accessibility tree; its icon button speaks for it
    qslot.inert = icon && !searchOpen;
    const b = tools.querySelector('[data-bar=search]');
    if (b) b.setAttribute('aria-expanded', String(searchOpen));
  }
  function openSearch() {
    setSearch(true);
    if (el._queryUi) el._queryUi.focus();
  }
  const onSearchOut = (e) => {
    if (!searchIcon() || (e.relatedTarget && qslot.contains(e.relatedTarget))) return;
    setSearch(false);
  };
  const onSearchKey = (e) => {
    if (e.key !== 'Escape' || !searchIcon() || e.defaultPrevented || hasQuery()) return;
    e.stopPropagation();
    setSearch(false);
    const b = tools.querySelector('[data-bar=search]');
    if (b) b.focus();
  };
  qslot.addEventListener('focusout', onSearchOut);
  qslot.addEventListener('keydown', onSearchKey);

  // ---- the view menu (Bases): find box, the views with a ✓ on the current one, › Configure view, Add view
  const pop = () => el.$('.dv-pop');
  function page(html, bind) {
    const p = pop();
    p.innerHTML = html;
    bind(p);
    const first = p.querySelector('input, button:not([disabled])');
    if (first) first.focus();
  }
  const stop = (fn) => (e) => { e.stopPropagation(); fn(e); };

  function viewMenuHtml() {
    const rows = allViews().map(([kind, v]) => {
      const on = isCurrent(kind, v);
      return `<li class="dv-vm-row${on ? ' dv-vm-on' : ''}" role="option" aria-selected="${on}" data-kind="${kind}" data-name="${esc(v.name)}"><span class="dv-vm-check">${on ? icon('check') : ''}</span>${icon(layoutIcon(typeOf(kind, v)))}<span class="dv-vm-label">${esc(v.name)}${kind === 'user' ? '<span class="dv-mine" title="Your view, saved in this browser">•</span>' : ''}</span><button type="button" class="dv-vm-config" data-bar="vm-config" aria-label="Configure ${esc(v.name)}" title="Configure view">${icon('chevR')}</button></li>`;
    }).join('');
    return `<label class="dv-vm-search">${icon('search')}<input class="dv-vm-find" type="search" placeholder="Search views…" aria-label="Find a view" autocomplete="off"></label>
      <ul class="dv-vm-list" role="listbox" aria-label="Views">${rows}</ul><p class="dv-vm-none dv-hint" hidden>No view has that name.</p>
      <button type="button" class="dv-vm-add" data-bar="vm-add">${icon('plus')}<span>Add view</span></button>`;
  }

  function bindViewMenu(p) {
    const find = p.querySelector('.dv-vm-find');
    const visible = () => [...p.querySelectorAll('.dv-vm-row:not([hidden])')];
    const mark = (row) => { p.querySelectorAll('.dv-vm-row').forEach((r) => r.classList.toggle('dv-vm-hl', r === row)); if (row) row.scrollIntoView({ block: 'nearest' }); };
    find.addEventListener('input', () => {
      const q = find.value.trim().toLowerCase();
      p.querySelectorAll('.dv-vm-row').forEach((r) => { r.hidden = !!q && !r.dataset.name.toLowerCase().includes(q); });
      p.querySelector('.dv-vm-none').hidden = visible().length > 0;
      mark(q ? visible()[0] : null);
    });
    find.addEventListener('keydown', (e) => {
      const rows = visible();
      const at = rows.findIndex((r) => r.classList.contains('dv-vm-hl'));
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); if (rows.length) mark(rows[(at + (e.key === 'ArrowDown' ? 1 : rows.length - 1) + (at < 0 && e.key === 'ArrowUp' ? 1 : 0)) % rows.length]); }
      else if (e.key === 'Enter') { e.preventDefault(); const r = rows[Math.max(0, at)]; if (r) pick(r); }
    });
    const pick = (row) => {
      const list = row.dataset.kind === 'user' ? el._userViews() : el.presets;
      const v = list.find((x) => x.name === row.dataset.name);
      el.closeMenu();
      if (v && !isCurrent(row.dataset.kind, v)) el._select(row.dataset.kind, v);
    };
    p.querySelectorAll('.dv-vm-row').forEach((row) => {
      row.addEventListener('click', stop((e) => {
        if (e.target.closest('.dv-vm-config')) {
          const list = row.dataset.kind === 'user' ? el._userViews() : el.presets;
          const v = list.find((x) => x.name === row.dataset.name);
          // WHY open it first: Configure view edits the open view, so what it changes is what you see
          if (v && !isCurrent(row.dataset.kind, v)) el._select(row.dataset.kind, v);
          configure();
          return;
        }
        pick(row);
      }));
    });
    p.querySelector('.dv-vm-add').addEventListener('click', stop(() => addView(true)));
  }

  function openViewMenu(anchor) {
    el._pop(anchor, viewMenuHtml(), bindViewMenu, 'dv-viewmenu');
  }

  const head = (title, back) => `<header class="dv-vm-head">${back ? `<button type="button" class="dv-vm-back" data-bar="vm-back" aria-label="Back to the views">${icon('chevL')}</button>` : ''}<h4>${esc(title)}</h4><button type="button" class="dv-vm-close" data-bar="vm-close" aria-label="Close">${icon('x')}</button></header>`;
  function bindHead(p, back) {
    const b = p.querySelector('.dv-vm-back');
    if (b) b.addEventListener('click', stop(back));
    p.querySelector('.dv-vm-close').addEventListener('click', stop(() => el.closeMenu()));
  }

  /** Configure view (Bases' › page): the name, the Layout grid and the layout's own options(), Copy as .base entry,
      Delete for a user view. It edits the open view. */
  function configure() {
    const v = el.view;
    const user = el.origin.kind === 'user';
    el._viewOptions = null;
    const rows = el._optionRows();
    // a view's options() arrive with its code: a view not drawn yet gets its page again once it has drawn
    if (el._pluginType !== v.type) el.addEventListener('data-views-render', () => { if (!pop().hidden && pop().querySelector('.dv-vm-name')) configure(); }, { once: true });
    const html = `${head('Configure view', true)}
      <input class="dv-vm-name" value="${esc(el.origin.name)}" aria-label="View name">
      ${user ? '' : '<p class="dv-hint">A view of the .base file: a new name saves your own copy.</p>'}
      <h5>Layout</h5>${layoutGrid(v.type)}
      ${rows ? `<h5>${esc(layoutName(v.type))} settings</h5><div class="dv-vm-opts">${rows}</div>` : ''}
      <div class="dv-vm-actions"><button type="button" class="dv-vm-act" data-bar="vm-act" data-act="copy-base">${icon('code')}<span>Copy as .base entry</span></button>${user ? `<button type="button" class="dv-vm-act dv-vm-danger" data-bar="vm-act" data-act="delete">${icon('trash')}<span>Delete view</span></button>` : ''}</div>`;
    page(`<div class="dv-vm-page">${html}</div>`, (p) => {
      bindHead(p, () => page(viewMenuHtml(), bindViewMenu));
      const name = p.querySelector('.dv-vm-name');
      name.addEventListener('change', () => { if (renameView(el, name.value)) configure(); });
      name.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); name.blur(); } });
      p.querySelectorAll('.dv-layout:not([disabled])').forEach((b) => b.addEventListener('click', stop(() => {
        if (b.dataset.type === el.view.type) return;
        el.update((x) => { x.type = b.dataset.type; if (x.type === 'pivot' && !x.splitBy) x.splitBy = []; });
        configure();
      })));
      el._bindOptions(p, () => configure());
      p.querySelectorAll('[data-act]').forEach((b) => b.addEventListener('click', stop(() => {
        if (b.dataset.act === 'copy-base') copyText(el.viewYaml(), b);
        else if (b.dataset.act === 'delete') { el._deleteUser(el.origin.name); el.closeMenu(); }
      })));
    });
  }

  /** Add view (Notion's layout grid): a pick adds a view of that type as a user view and opens it. */
  function addView(fromMenu, anchor) {
    const html = `<div class="dv-vm-page">${head('Add view', fromMenu)}${layoutGrid(null)}<p class="dv-hint">Saved in this browser; Copy as .base entry puts it in the file.</p></div>`;
    const bind = (p) => {
      bindHead(p, () => page(viewMenuHtml(), bindViewMenu));
      p.querySelectorAll('.dv-layout:not([disabled])').forEach((b) => b.addEventListener('click', stop(() => {
        const type = b.dataset.type;
        el.closeMenu();
        el.addView(type === 'pivot' ? { type, splitBy: [] } : { type });
      })));
    };
    if (fromMenu) page(html, bind);
    else el._pop(anchor, html, bind, 'dv-viewmenu');
  }

  // ---- the band: the bar, and the pill or bulk row under it while it shows. WHY one measurement for every surface
  // pinned under it (the overlay record pane, View settings): each starts at the band's bottom, so no control of the
  // bar, the pills or the bulk bar is ever under one (robotparts, 2026-10-26: the pane covered Filters and Display,
  // then the bulk bar's Clear selection and Show only selected)
  const subEl = el.$('.dv-subbar');
  /** The band's bottom in the window (viewport px): the bar, its pill row, and the bulk band while it shows. */
  function bandBottom() {
    const sub = subEl && subEl.isConnected ? subEl.getBoundingClientRect() : null;
    let bottom = sub && sub.height > 0 ? sub.bottom : barEl.getBoundingClientRect().bottom;
    if (bulkEl && !bulkEl.hidden && !introBelow(bottom)) { const r = bulkEl.getBoundingClientRect(); if (r.height) bottom = Math.max(bottom, r.bottom); }
    return bottom;
  }
  // WHY the intro (CONTRACT §16 `intro:`) ends the band: while the view's intro shows under the bar, the bulk band lies
  // over the column header below it, a screen away; the pinned surfaces start under the bar then (on robotparts-models
  // View settings began at 786 px of a 900 px window), and the bulk band stops at their left edge instead (placeBulk)
  const introEl = el.$('.dv-intro');
  const introBelow = (top) => { if (!introEl || introEl.hidden) return false; const r = introEl.getBoundingClientRect(); return r.height > 0 && r.bottom > top + 1; };

  // ---- the bulk band (§15 note 2026-10-26; Shopify's, Zach's screenshot 87: "50 selected ⌄", action pills, "…", "Show
  // all selected"). WHY in the column header's place: Zach wants the selection's bar visibly different from the toolbar,
  // never another toolbar row; so while rows are selected it is a tinted band (--dv-band) laid over the view's column
  // header row, at its top and height; a view with no header (the gallery) gets the same band at its top, the cards
  // moved down under it. The pill row stays under the bar.
  const bulkEl = el.$('.dv-bulk');
  function placeBulk() {
    if (!bulkEl) return;
    const on = !bulkEl.hidden;
    el.classList.toggle('dv-bulk-on', on);
    if (!on) return;
    const er = el.getBoundingClientRect();
    const head = el.querySelector('.dv-stage .dv-view thead');
    const hr = head && head.offsetParent !== null ? head.getBoundingClientRect() : null;
    const header = !!(hr && hr.height);
    el.classList.toggle('dv-bulk-top', !header);
    const top = header ? hr.top : el.$('.dv-stage').getBoundingClientRect().top;
    const h = header ? hr.height : 40;
    const put = (prop, v) => { if (bulkEl.style.getPropertyValue(prop) !== v) bulkEl.style.setProperty(prop, v); };
    put('top', `${Math.round(top - er.top - el.clientTop)}px`);
    put('height', `${Math.round(h)}px`);
    // a surface pinned at the right over the band's row (View settings' panel; the overlay record pane, which starts
    // under the bar while an intro shows): the band stops at its left edge, so Show only selected and "…" stay in reach.
    // Split docks the pane beside the list (select.css), so only an overlay pane counts here.
    let inset = 0;
    const pane = el.classList.contains('dv-split') || el.classList.contains('dv-full') ? null : el.querySelector(':scope > .dv-peek:not([hidden])');
    for (const s of [el.querySelector(':scope > .dv-settings-panel:not([hidden])'), pane]) {
      const b = s && s.getBoundingClientRect();
      if (b && b.width && b.top < top + h && b.bottom > top) inset = Math.max(inset, er.right - el.clientLeft - b.left);
    }
    put('right', inset > 0 ? `${Math.round(inset)}px` : '');
    if (el.style.getPropertyValue('--dv-bulk-h') !== `${Math.round(h)}px`) el.style.setProperty('--dv-bulk-h', `${Math.round(h)}px`);
  }
  const onDrawn = () => { placeBulk(); barBottom(); };
  el.addEventListener('data-views-render', onDrawn);
  // --dv-band-bottom (element px): an overlay pane in the element's own box starts there (styles/toolbar.css)
  function barBottom() {
    el.style.setProperty('--dv-band-bottom', `${Math.round(bandBottom() - el.getBoundingClientRect().top - el.clientTop)}px`);
    paneTop();
    if (el._settingsUi && el._settingsUi.isOpen()) el._settingsUi.place();
  }

  // WHY --dv-pane-top under a page frame (frame="page|bleed"): the record pane is fixed to the window there, and the
  // bar may sit far below the scroller's top (a page heading above the views) or stick under a host header; the pane
  // starts at the bar's bottom wherever the bar is, following it as the page scrolls (robotparts, 2026-10-26: an
  // overlay pane at the scroller's top covered Filters, Filter and Display)
  let following = null;
  function paneTop() {
    const scroller = el.dataset.scroll === 'page' && el.host ? el.host.scroller : null;
    if ((following && following.target) !== scroller) {
      if (following) following.target.removeEventListener('scroll', following.fn);
      following = null;
      if (scroller) {
        let raf = 0;
        const fn = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; placeBulk(); paneTop(); }); };
        scroller.addEventListener('scroll', fn, { passive: true });
        following = { target: scroller, fn };
      }
    }
    if (!scroller) { el.style.removeProperty('--dv-pane-top'); return; }
    const port = scroller === window ? 0 : scroller.getBoundingClientRect().top;
    const sticky = parseFloat(getComputedStyle(el).getPropertyValue('--dv-sticky-top')) || 0;
    el.style.setProperty('--dv-pane-top', `${Math.round(Math.max(port + sticky, bandBottom()))}px`);
  }

  function toggleRail() { store.set(railKey(), !railOpen()); applyRail(); keys.tools = ''; drawTools(); layoutRow(true); }

  // ---- clicks on the bar and the pill row
  function onClick(e) {
    const b = e.target.closest('[data-bar]');
    if (!b || !el.contains(b) || b.closest('.dv-pop')) return;
    act(b);
  }
  /** Run a bar control (from a click on it, or from the overflow menu, then anchored to `anchor`). */
  function act(b, anchor = b) {
    const what = b.dataset.bar;
    if (what === 'search') openSearch();
    else if (what === 'overflow') openOverflow(b);
    else if (what === 'views' || what === 'more') openViewMenu(b);
    else if (what === 'add-view') addView(false, b);
    else if (what === 'tab') {
      el.closeMenu();
      const list = b.dataset.kind === 'user' ? el._userViews() : el.presets;
      const v = list.find((x) => x.name === b.dataset.name);
      if (v && !isCurrent(b.dataset.kind, v)) el._select(b.dataset.kind, v);
    } else if (what === 'menu' && b.dataset.name === 'filter' && railDriven()) toggleRail();
    else if (what === 'menu') el._openMenu(anchor, { name: b.dataset.name });
    else if (what === 'display') { el.closeMenu(); el._settingsUi.toggle(b); }
    else if (what === 'edit') { el.closeMenu(); el.setEditing(!el.editing); }
    else if (what === 'reset') el._select(el.origin.kind, el.origin.view, null, { fresh: true });
    else if (what === 'save') el._openMenu(anchor, { name: 'save' });
    else if (what === 'pill' && el._hasSwitch && el._hasSwitch() && pills[Number(b.dataset.i)] && (pills[Number(b.dataset.i)].property || pills[Number(b.dataset.i)].column)) { const p = pills[Number(b.dataset.i)]; openColumnFilter(el, p.property || p.column, b); }
    else if (what === 'pill' || what === 'pill-add') el._openMenu(b, { name: 'filter' });
    else if (what === 'pill-x') { el.closeMenu(); const p = pills[Number(b.dataset.i)]; if (p) removePill(el, p); }
    else if (what === 'pill-clear') { el.closeMenu(); el.filters = fromRail({}, []); }
  }
  barEl.addEventListener('click', onClick);
  pillsEl.addEventListener('click', onClick);

  // the row is fitted to the bar's OWN width (a table in a narrow split pane folds too), once per frame
  let rowFrame = 0;
  const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => {
    barBottom();
    if (barEl.clientWidth === width) return;
    width = barEl.clientWidth;
    if (!rowFrame) rowFrame = requestAnimationFrame(() => { rowFrame = 0; if (el._model && barEl.isConnected) layoutRow(); });
  });
  if (observer) observer.observe(barEl);
  // the pill or bulk row appears and goes (a selection, a filter) while a pane is open: the band is measured again
  if (observer && subEl) observer.observe(subEl);
  // View settings or the record pane opens or closes (their `hidden`): the bulk band's right edge follows (placeBulk)
  let bulkFrame = 0;
  const shown = typeof MutationObserver === 'undefined' ? null : new MutationObserver((list) => {
    if (bulkFrame || !bulkEl || bulkEl.hidden || !list.some((m) => m.target.parentNode === el && m.target.matches('.dv-settings, .dv-peek'))) return;
    bulkFrame = requestAnimationFrame(() => { bulkFrame = 0; if (barEl.isConnected) placeBulk(); });
  });
  if (shown) shown.observe(el, { subtree: true, attributes: true, attributeFilter: ['hidden'] });
  if (typeof document !== 'undefined' && document.fonts && document.fonts.ready) document.fonts.ready.then(() => { if (el._model && barEl.isConnected) { measured = { key: null }; layoutRow(true); } });

  const anchorOf = (sel) => barEl.querySelector(sel);
  return {
    update() {
      if (!el._model) return;
      placeBulk();
      barBottom();
      applyRail();
      drawTools();
      drawPills();
      layoutRow();
      setSearch(searchOpen);
    },
    /** The band's bottom in the window (the bar, and the pill or bulk row while it shows): where pinned surfaces start. */
    bandBottom,
    /** The rail, when filters has "rail" and one is linked: {open} for View settings' Filter page, else null. */
    rail() { return railDriven() ? { open: railOpen(), toggle: toggleRail } : null; },
    /** Lay the bulk band over the view's header row again (the selection changed, the view drew). */
    placeBulk() { placeBulk(); barBottom(); },
    /** The filter modes in force: the `filters` attribute, else the default the views decide (tabs => pills, chip => expanded). */
    filterModes,
    /** An attribute changed (views, filters, display): draw every part again. */
    configure() { keys.tools = keys.pills = keys.views = ''; measured = { key: null }; rowState = null; },
    /** openMenu(name) under toolbar="bar": anchored to the bar's own controls; false for a name it does not know. */
    openMenu(name) {
      if (name === 'query') { if (searchIcon()) openSearch(); else if (el._queryUi) el._queryUi.focus(); return true; }
      if (name === 'settings') { el.closeMenu(); el._settingsUi.open('root', anchorOf('[data-bar=display]')); return true; }
      if (name === 'views') { el.closeMenu(); openViewMenu(anchorOf('.dv-bar-views [data-bar=views]') || anchorOf('[data-bar=more]:not([hidden])') || anchorOf('[data-bar=tab].dv-on')); return true; }
      if (name === 'add-view') { el.closeMenu(); addView(false, anchorOf('[data-bar=add-view]') || anchorOf('[data-bar=views]')); return true; }
      if (name === 'layout') { el.closeMenu(); el._settingsUi.open('layout', anchorOf('[data-bar=display]')); return true; }
      if (['group', 'sort', 'filter', 'properties'].includes(name)) {
        let word = anchorOf(`[data-bar=menu][data-name="${name}"]`);
        if (word && word.hidden) word = anchorOf('[data-bar=overflow]');
        el.closeMenu();
        if (word) el._openMenu(word, { name });
        else el._settingsUi.open(name, anchorOf('[data-bar=display]'));
        return true;
      }
      if (name === 'save' || name === 'more') {
        el.closeMenu();
        el._openMenu(anchorOf('[data-bar=save]:not([hidden])') || anchorOf('[data-bar=display]'), { name });
        return true;
      }
      return false;
    },
    destroy() {
      if (observer) observer.disconnect();
      if (shown) shown.disconnect();
      if (bulkFrame) cancelAnimationFrame(bulkFrame);
      qslot.removeEventListener('focusout', onSearchOut);
      qslot.removeEventListener('keydown', onSearchKey);
      qslot.inert = false;
      if (lastBar === el) lastBar = null;
      barEl.removeEventListener('click', onClick);
      pillsEl.removeEventListener('click', onClick);
      for (const r of rails()) if (r._dvBarHidden) { r.hidden = false; r._dvBarHidden = false; }
      el.classList.remove('dv-rail-off');
      el.style.removeProperty('--dv-band-bottom');
      el.removeEventListener('data-views-render', onDrawn);
      el.classList.remove('dv-bulk-on', 'dv-bulk-top');
      el.style.removeProperty('--dv-bulk-h');
      el.style.removeProperty('--dv-pane-top');
      if (following) { following.target.removeEventListener('scroll', following.fn); following = null; }
    },
  };
}

