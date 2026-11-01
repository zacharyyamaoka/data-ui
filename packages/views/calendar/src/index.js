/* type: calendar — rows with a date, or a start and an end, on month, week, day and list grids (docs/VIEWS.md).

   STOCK PART: Event Calendar 5.18.1 (vkurko, MIT; @event-calendar/build, Svelte compiled inside): the grids, the
   toolbar, drag and resize, more-links, the list view, resources. OURS: rows -> events, groupBy -> colour and
   resources, `calendarView` <-> its view names, the theme mapping (its --ec-* properties) in calendar.css.
   Writes back only through the host: open(id) on an event; setView({calendarView}) when a toolbar button switches
   the grid; propose({id, set: {<start>, <end>}}) when an event is dragged or resized, drawn only after the host says
   ok (a refusal puts the event back and says why). */

import { release } from './capture.js';
import '@event-calendar/build';
import { cellValue, esc, groupLabel, hueOf, isEmpty } from '@data-ui/core';
import ecCss from '@event-calendar/build/dist/event-calendar.min.css';
import ownCss from './calendar.css';

const EventCalendar = release();
export const css = `${ecCss}\n${ownCss}`;

// calendarView (the .base key) <-> Event Calendar's view names
const GRID = { month: 'dayGridMonth', week: 'timeGridWeek', day: 'timeGridDay', list: 'listMonth', resourceTimeline: 'resourceTimelineWeek' };
const KEY = Object.fromEntries(Object.entries(GRID).map(([k, v]) => [v, k]));

export function options() {
  return [
    { type: 'property', key: 'start', displayName: 'Date' },
    { type: 'property', key: 'end', displayName: 'End', none: 'none' },
    { type: 'property', key: 'title', displayName: 'Label', none: 'the title' },
    { type: 'dropdown', key: 'calendarView', displayName: 'Opens on', default: 'month', options: { month: 'Month', week: 'Week', day: 'Day', list: 'List', resourceTimeline: 'Timeline by group' } },
  ];
}

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const pad = (n) => String(n).padStart(2, '0');
const localDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/** A moved date, written the way the original was: date-only stays date-only; a date-time keeps its own offset. */
export function movedValue(original, moved, shiftMs) {
  if (DATE_ONLY.test(original)) return localDate(moved);
  const at = new Date(Date.parse(original) + shiftMs);
  const off = /(Z|[+-]\d{2}:\d{2})$/.exec(original);
  if (!off) return `${localDate(at)}T${pad(at.getHours())}:${pad(at.getMinutes())}:${pad(at.getSeconds())}`;
  const minutes = off[1] === 'Z' ? 0 : (off[1][0] === '-' ? -1 : 1) * (Number(off[1].slice(1, 3)) * 60 + Number(off[1].slice(4, 6)));
  const w = new Date(at.getTime() + minutes * 6e4);
  return `${w.getUTCFullYear()}-${pad(w.getUTCMonth() + 1)}-${pad(w.getUTCDate())}T${pad(w.getUTCHours())}:${pad(w.getUTCMinutes())}:${pad(w.getUTCSeconds())}${off[1]}`;
}

function slotOf(columns, property, value) {
  const colors = columns[property] && columns[property].colors;
  if (colors && Object.prototype.hasOwnProperty.call(colors, String(value))) return colors[String(value)];
  return isEmpty(value) ? 0 : hueOf(value);
}

/** One end of an event: {value, allDay} from a cell, or null when it is empty or not a date. */
function when(cell) {
  const x = cellValue(cell);
  if (isEmpty(x)) return null;
  const s = String(x);
  if (DATE_ONLY.test(s)) return { value: s, allDay: true };
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : { value: d, allDay: false };
}

/** The end a row without one is drawn to. WHY: Event Calendar draws an event with no end to the end of the grid; a
    dated row is one day (date-only) or a point drawn as an hour (date-time). The data is never given this end. */
function pointEnd(start) {
  if (start.allDay) { const d = new Date(`${start.value}T00:00:00`); d.setDate(d.getDate() + 1); return localDate(d); }
  return new Date(start.value.getTime() + POINT_MS);
}
const POINT_MS = 60 * 60 * 1000;

/** The row model -> {events, resources, missing, latest}. Pure. */
export function toEvents(input, peekId) {
  const { rows, columns, view, tokens, dataset } = input;
  const titleProp = view.title || dataset.titleProperty;
  const groupProp = view.groupBy && columns[view.groupBy.property] ? view.groupBy.property : null;
  const resources = [];
  const resourceOf = new Map();
  (input.groups || []).forEach((g, i) => {
    resources.push({ id: `g${i}`, title: groupLabel(columns, g.property, g.key) });
    for (const r of g.rows) resourceOf.set(String(r.id), `g${i}`);
  });
  const events = [];
  let missing = 0, latest = null;
  for (const r of rows) {
    const start = view.start ? when(r[view.start]) : null;
    if (!start) { missing++; continue; }
    const end = view.end ? when(r[view.end]) : null;
    const slot = groupProp ? slotOf(columns, groupProp, cellValue(r[groupProp])) : 1;
    const colour = slot ? tokens.series[(slot - 1) % tokens.series.length] : tokens.muted;
    const id = String(r.id);
    const t = start.allDay ? new Date(`${start.value}T00:00:00`) : start.value;
    if (!latest || t > latest) latest = t;
    events.push({
      id, title: String(cellValue(r[titleProp]) ?? id), start: start.value, end: end ? end.value : pointEnd(start), allDay: start.allDay,
      ...(resourceOf.has(id) ? { resourceIds: [resourceOf.get(id)] } : {}),
      backgroundColor: `color-mix(in srgb, ${colour} 24%, var(--dv-bg))`, textColor: 'var(--dv-fg)',
      classNames: ['dv-cal-event', ...(peekId === id ? ['dv-active'] : [])], styles: [`--dv-item: ${colour}`],
    });
  }
  return { events, resources, missing, latest };
}

export default class CalendarView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    // WHY two boxes: the calendar fills a sized box; Event Calendar styles its own root
    const box = document.createElement('div');
    box.className = 'dv-cal-box';
    this.mount = document.createElement('div');
    this.mount.className = 'dv-cal-mount';
    box.append(this.mount);
    el.append(box);
    this.cal = null;
    this.peekId = null;
    this._dateKey = null;
  }

  destroy() {
    this.host.setStatus('');
    if (this.cal) EventCalendar.destroy(this.cal);
    this.cal = null;
  }

  peeked(peek) {
    this.peekId = peek ? String(peek.id) : null;
    if (this.input) this.update(this.input);
  }

  update(input) {
    this.input = input;
    const { view, columns } = input;
    const m = toEvents(input, this.peekId);
    this.rows = new Map(input.rows.map((r) => [String(r.id), r]));
    const grid = GRID[view.calendarView] || GRID.month;
    const narrow = this.el.clientWidth < 560;
    const startCol = columns[view.start] || {};
    const endCol = columns[view.end] || {};
    const toolbar = {
      start: narrow ? 'prev,next' : 'prev,next today', center: 'title',
      end: [narrow ? 'dayGridMonth,listMonth' : 'dayGridMonth,timeGridWeek,listMonth', m.resources.length && !narrow ? 'resourceTimelineWeek' : ''].filter(Boolean).join(','),
    };
    const opts = {
      view: grid, events: m.events, resources: m.resources, headerToolbar: toolbar, height: '100%', dayMaxEvents: true,
      displayEventEnd: !!view.end, // a drawn-only end (pointEnd) is never printed as a time
      buttonText: { today: 'Today', dayGridMonth: 'Month', timeGridWeek: 'Week', timeGridDay: 'Day', listMonth: 'List', resourceTimelineWeek: 'By group' },
      editable: true, eventStartEditable: !!view.start && !(startCol.derived || startCol.readOnly),
      eventDurationEditable: !!view.end && !(endCol.derived || endCol.readOnly),
      eventClick: (info) => this.host.open(info.event.id),
      eventDrop: (info) => this._moved(info, false),
      eventResize: (info) => this._moved(info, true),
      datesSet: (info) => {
        // a toolbar button switched the grid: write it to the view entry, as the Layout menu would
        const key = KEY[info.view.type];
        if (key && key !== (this.input.view.calendarView || 'month')) this.host.setView({ calendarView: key });
      },
    };
    // WHY a key: a new view or date property opens on the newest event; a filter, an edit or a theme change keeps
    // the month you navigated to
    const dateKey = JSON.stringify([view.name, view.start]);
    if (dateKey !== this._dateKey && m.latest) opts.date = m.latest;
    this._dateKey = dateKey;
    if (!this.cal) this.cal = EventCalendar.create(this.mount, opts);
    else for (const [k, v] of Object.entries(opts)) if (k !== 'view' || this.cal.getOption('view') !== v) this.cal.setOption(k, v);
    this.el.classList.toggle('dv-dark', !!input.tokens.dark);
    this._summary = `${m.events.length} on the calendar`;
    const parts = [this._summary];
    if (!view.start) parts.push('<span class="dv-err">set <code>start:</code>, the property holding each row\'s date</span>');
    else if (m.missing) parts.push(`${m.missing} without a ${esc((columns[view.start] || {}).label || view.start).toLowerCase()}`);
    this.host.setStatus(parts.join(' · '));
  }

  /** A drag or resize: propose the new date(s); put the event back unless the host says ok. */
  async _moved(info, resized) {
    const { view } = this.input;
    const row = this.rows.get(String(info.event.id));
    const set = {};
    if (!resized) set[view.start] = movedValue(String(cellValue(row[view.start])), info.event.start, info.event.start - info.oldEvent.start);
    if (view.end && !isEmpty(cellValue(row[view.end])) && info.event.end && info.oldEvent.end) {
      set[view.end] = movedValue(String(cellValue(row[view.end])), info.event.end, info.event.end - info.oldEvent.end);
    }
    const result = await this.host.propose({ id: String(info.event.id), set });
    if (!result.ok) {
      info.revert();
      this.host.setStatus(`${this._summary} · <span class="dv-err">Not moved: ${esc(result.reason)}</span>`);
    }
  }
}
