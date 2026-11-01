/* The bar's icons (docs/CONTRACT.md §15): 16 px strokes in currentColor, so they take the text colour in light and dark.
   Copied from the toolbar proposals' mock (lane/toolbar-proposals, design/toolbar-2026-10-26/shared/mock.js), which
   drew them after Lucide's shapes; inline, because the kit never loads anything from another origin. */

export const ICON = {
  table: '<svg viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M2 6.5h12M2 10h12M6 6.5V13"/></svg>',
  cards: '<svg viewBox="0 0 16 16"><rect x="2" y="2.5" width="5" height="5" rx="1"/><rect x="9" y="2.5" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/></svg>',
  chart: '<svg viewBox="0 0 16 16"><path d="M2.5 2.5v11h11"/><circle cx="6" cy="9.5" r="1"/><circle cx="8.5" cy="6.5" r="1"/><circle cx="11.5" cy="4.5" r="1"/><circle cx="10.5" cy="9" r="1"/></svg>',
  kanban: '<svg viewBox="0 0 16 16"><rect x="2" y="2.5" width="3.4" height="11" rx="1"/><rect x="6.3" y="2.5" width="3.4" height="7" rx="1"/><rect x="10.6" y="2.5" width="3.4" height="9" rx="1"/></svg>',
  compare: '<svg viewBox="0 0 16 16"><rect x="2" y="2.5" width="5" height="11" rx="1"/><rect x="9" y="2.5" width="5" height="11" rx="1"/><path d="M3.5 6h2M3.5 9h2M10.5 6h2M10.5 9h2"/></svg>',
  list: '<svg viewBox="0 0 16 16"><path d="M5.5 4h8M5.5 8h8M5.5 12h8"/><circle cx="2.8" cy="4" r=".6"/><circle cx="2.8" cy="8" r=".6"/><circle cx="2.8" cy="12" r=".6"/></svg>',
  pivot: '<svg viewBox="0 0 16 16"><rect x="2" y="2.5" width="12" height="11" rx="1.5"/><path d="M2 6h12M6 2.5v11"/><path d="M8.5 9.5h3M10 8v3"/></svg>',
  graph: '<svg viewBox="0 0 16 16"><circle cx="4" cy="4" r="1.6"/><circle cx="12" cy="5" r="1.6"/><circle cx="7" cy="12" r="1.6"/><path d="M5.4 4.4l5 .5M4.7 5.5l1.7 5M11 6.3l-3 4.4"/></svg>',
  calendar: '<svg viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="1.5"/><path d="M2 6.5h12M5 1.8v2.5M11 1.8v2.5"/></svg>',
  timeline: '<svg viewBox="0 0 16 16"><path d="M2 4h6M5 8h7M3 12h5"/></svg>',
  map: '<svg viewBox="0 0 16 16"><path d="M2 4l4-1.5 4 1.5 4-1.5v9.5L10 13.5 6 12 2 13.5z"/><path d="M6 2.5V12M10 4v9.5"/></svg>',
  kpi: '<svg viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M4.5 10l2.5-3 2 2 2.5-3.5"/></svg>',
  record: '<svg viewBox="0 0 16 16"><path d="M4 2h5.5L12.5 5v9h-8.5z"/><path d="M9.5 2v3h3M6 8h4.5M6 10.5h4.5"/></svg>',
  search: '<svg viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.3"/><path d="M10.2 10.2L14 14"/></svg>',
  sliders: '<svg viewBox="0 0 16 16"><path d="M2 4.5h7M12 4.5h2M2 11.5h2M7 11.5h7"/><circle cx="10.5" cy="4.5" r="1.5"/><circle cx="5.5" cy="11.5" r="1.5"/></svg>',
  // CONTRACT §40: the Edit / View switch, folded to its icon
  pencil: '<svg viewBox="0 0 16 16"><path d="M10.8 2.7l2.5 2.5L5.6 12.9l-3.1.6.6-3.1zM9.4 4.1l2.5 2.5"/></svg>',
  sort: '<svg viewBox="0 0 16 16"><path d="M5 2.5v11M2.5 11l2.5 2.5L7.5 11M11 13.5v-11M8.5 5L11 2.5 13.5 5"/></svg>',
  group: '<svg viewBox="0 0 16 16"><rect x="2" y="2.5" width="12" height="4" rx="1"/><rect x="2" y="9.5" width="12" height="4" rx="1"/></svg>',
  filter: '<svg viewBox="0 0 16 16"><path d="M2 3.5h12M4.5 8h7M7 12.5h2"/></svg>',
  props: '<svg viewBox="0 0 16 16"><path d="M5.5 4h8M5.5 8h8M5.5 12h8M2.5 4h.5M2.5 8h.5M2.5 12h.5"/></svg>',
  eye: '<svg viewBox="0 0 16 16"><path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/></svg>',
  frame: '<svg viewBox="0 0 16 16"><rect x="2" y="2.5" width="12" height="11" rx="1.5"/><rect x="4.5" y="5" width="7" height="6" rx=".8"/></svg>',
  rail: '<svg viewBox="0 0 16 16"><rect x="2" y="2.5" width="12" height="11" rx="1.5"/><path d="M6 2.5v11M3.5 5.5h1M3.5 8h1"/></svg>',
  more: '<svg viewBox="0 0 16 16"><circle cx="3.5" cy="8" r="1"/><circle cx="8" cy="8" r="1"/><circle cx="12.5" cy="8" r="1"/></svg>',
  plus: '<svg viewBox="0 0 16 16"><path d="M8 3v10M3 8h10"/></svg>',
  x: '<svg viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8"/></svg>',
  chevR: '<svg viewBox="0 0 16 16"><path d="M6 3.5L10.5 8 6 12.5"/></svg>',
  chevL: '<svg viewBox="0 0 16 16"><path d="M10 3.5L5.5 8 10 12.5"/></svg>',
  updown: '<svg viewBox="0 0 16 16"><path d="M5 6l3-3 3 3M5 10l3 3 3-3"/></svg>',
  link: '<svg viewBox="0 0 16 16"><path d="M7 9a3 3 0 004.2 0l2-2A3 3 0 009 2.8l-.8.8M9 7a3 3 0 00-4.2 0l-2 2A3 3 0 007 13.2l.8-.8"/></svg>',
  check: '<svg viewBox="0 0 16 16"><path d="M3 8.5l3 3 7-7"/></svg>',
  code: '<svg viewBox="0 0 16 16"><path d="M5.5 4.5L2 8l3.5 3.5M10.5 4.5L14 8l-3.5 3.5"/></svg>',
  trash: '<svg viewBox="0 0 16 16"><path d="M2.5 4.5h11M6 4.5V3h4v1.5M4 4.5l.7 9h6.6l.7-9"/></svg>',
  // a dashboard's tiles (Add to dashboard, CONTRACT §34); addDash with the plus in the corner tile
  dashboard: '<svg viewBox="0 0 16 16"><rect x="2" y="2.5" width="5" height="5" rx="1"/><rect x="9" y="2.5" width="5" height="5" rx="1"/><rect x="2" y="9" width="12" height="4.5" rx="1"/></svg>',
  addDash: '<svg viewBox="0 0 16 16"><rect x="2" y="2.5" width="5" height="5" rx="1"/><rect x="9" y="2.5" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="4.5" rx="1"/><path d="M11.5 9v5M9 11.5h5"/></svg>',
};

export const icon = (name, cls = '') => `<span class="dv-i${cls ? ' ' + cls : ''}" aria-hidden="true">${ICON[name] || ICON.table}</span>`;

/* The layout grid, in robotparts' order (Zach's screenshot of 2026-10-26, "Pasted image 20261026122246"): Table
   Gallery List Board / Chart Compare Pivot Graph / Calendar Timeline Map KPI, then Record. WHY these words and not the
   registry's: Zach's grid (and Notion's, and Bases') says Gallery and Board, the words he reads; the type written to
   the .base file stays the registry's (`cards`, `kanban`). */
export const LAYOUTS = [
  ['table', 'Table'], ['cards', 'Gallery'], ['list', 'List'], ['kanban', 'Board'],
  ['chart', 'Chart'], ['compare', 'Compare'], ['pivot', 'Pivot'], ['graph', 'Graph'],
  ['calendar', 'Calendar'], ['timeline', 'Timeline'], ['map', 'Map'], ['kpi', 'KPI'],
  ['record', 'Record'],
];
const NAMES = Object.fromEntries(LAYOUTS);

/** A layout type's word in the bar (Gallery for cards, Board for kanban); an unknown type reads as itself. */
export const layoutName = (type) => NAMES[type] || type;
/** A layout type's icon name (a type the bar has no drawing for gets the table's). */
export const layoutIcon = (type) => (ICON[type] ? type : 'table');
