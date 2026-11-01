/* type: timeline — rows as bars (start -> end) or points on a zoomable time axis (docs/VIEWS.md, Timeline / Gantt).

   STOCK PART: vis-timeline 8.5.5, the standalone build (vis-data's DataSet and moment inside), dual Apache-2.0/MIT:
   the axis, zoom and pan, stacking, lanes and nested lanes, selection and tooltips. OURS: rows -> items, the row
   model's groups -> lanes (groupBy) and nested lanes (subGroupBy), `color` -> a series slot, `zoom` (ISO 8601
   durations) -> zoomMin / zoomMax, and the theme mapping in timeline.css.
   WHY no dependency arrows: the grammar has no key for them yet (docs/VIEWS.md: "Frappe Gantt only if dependencies
   are ever needed"), and an edge is never inferred.
   Writes back only through the host: open(id) on a bar or point, setStatus. */

import { Timeline, DataSet } from 'vis-timeline/standalone';
import { cellValue, esc, groupLabel, hueOf, isEmpty } from '@data-ui/core';
import visCss from 'vis-timeline/styles/vis-timeline-graph2d.min.css';
import ownCss from './timeline.css';

export const css = `${visCss}\n${ownCss}`;

export function options() {
  return [
    { type: 'property', key: 'start', displayName: 'Start' },
    { type: 'property', key: 'end', displayName: 'End', none: 'none (points)' },
    { type: 'property', key: 'title', displayName: 'Label', none: 'the title' },
    { type: 'property', key: 'color', displayName: 'Colour by', none: 'none' },
  ];
}

const UNIT_MS = { Y: 365.25 * 864e5, M: 30.44 * 864e5, W: 7 * 864e5, D: 864e5, h: 36e5, m: 6e4, s: 1e3 };
/** An ISO 8601 duration (P1Y, P2W, PT1H30M) in milliseconds; null if it is not one. Months and years are average. */
export function durationMs(text) {
  const m = /^P(?:(\d+(?:\.\d+)?)Y)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)W)?(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$/.exec(String(text || ''));
  if (!m || text === 'P' || text === 'PT') return null;
  return ['Y', 'M', 'W', 'D', 'h', 'm', 's'].reduce((t, u, i) => t + (m[i + 1] ? Number(m[i + 1]) * UNIT_MS[u] : 0), 0);
}

function slotOf(columns, property, value) {
  const colors = columns[property] && columns[property].colors;
  if (colors && Object.prototype.hasOwnProperty.call(colors, String(value))) return colors[String(value)];
  return isEmpty(value) ? 0 : hueOf(value);
}

const toDate = (v) => {
  const x = cellValue(v);
  if (isEmpty(x)) return null;
  const d = new Date(x);
  return Number.isNaN(d.getTime()) ? null : d;
};

/** The row model -> {items, groups, missing}: vis-timeline's own item and group objects. Pure. */
export function toTimeline(input) {
  const { rows, columns, view, tokens, dataset } = input;
  const startProp = view.start, endProp = view.end;
  const titleProp = view.title || dataset.titleProperty;
  const colorProp = view.color && columns[view.color] ? view.color : null;
  const laneOf = new Map();
  const groups = [];
  (input.groups || []).forEach((g, i) => {
    const id = `g${i}`;
    const nested = (g.groups || []).map((s, j) => {
      const sid = `${id}.${j}`;
      for (const r of s.rows) laneOf.set(String(r.id), sid);
      return { id: sid, order: j, treeLevel: 2, content: laneHtml(groupLabel(columns, s.property, s.key), s.rows.length), rows: s.rows.length };
    });
    if (!nested.length) for (const r of g.rows) laneOf.set(String(r.id), id);
    groups.push({ id, order: i, content: laneHtml(groupLabel(columns, g.property, g.key), g.rows.length), ...(nested.length ? { nestedGroups: nested.map((s) => s.id), showNested: true } : {}) });
    for (const s of nested) groups.push(s); // WHY not push(...nested): 150,000 lanes overflow the stack (2026-10-26 review)
  });
  const items = [];
  let missing = 0;
  for (const r of rows) {
    const start = startProp ? toDate(r[startProp]) : null;
    if (!start) { missing++; continue; }
    const end = endProp ? toDate(r[endProp]) : null;
    const range = end && end > start;
    const label = String(cellValue(r[titleProp]) ?? r.id);
    const slot = colorProp ? slotOf(columns, colorProp, cellValue(r[colorProp])) : 1;
    const colour = slot ? tokens.series[(slot - 1) % tokens.series.length] : tokens.muted;
    const when = range ? `${fmt(start)} → ${fmt(end)}` : fmt(start);
    const colourText = colorProp && !isEmpty(cellValue(r[colorProp])) ? `\n${columns[colorProp].label}: ${cellValue(r[colorProp])}` : '';
    items.push({
      id: String(r.id), content: esc(label), start, ...(range ? { end } : {}), type: range ? 'range' : 'point',
      ...(groups.length ? { group: laneOf.get(String(r.id)) } : {}),
      title: esc(`${label}\n${when}${colourText}`).replace(/\n/g, '<br>'), style: `--dv-item: ${colour}`, className: 'dv-tl-item',
    });
  }
  return { items, groups: groups.length ? groups : null, missing };
}

const laneHtml = (label, n) => `<span class="dv-tl-lane">${esc(label)}</span> <span class="dv-tl-n">${n}</span>`;
const fmt = (d) => d.toLocaleString('en-CA', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });

export default class TimelineView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    // WHY two boxes: vis-timeline sets position: relative on its container, so the sized box is its parent
    const box = document.createElement('div');
    box.className = 'dv-tl-box';
    this.box = document.createElement('div');
    this.box.className = 'dv-tl-mount';
    box.append(this.box);
    el.append(box);
    this.items = new DataSet();
    this.groups = new DataSet();
    this.timeline = null;
    this._fitKey = null;
  }

  destroy() {
    this.host.setStatus('');
    if (this.timeline) this.timeline.destroy();
    this.timeline = null;
  }

  peeked(peek) {
    if (this.timeline) this.timeline.setSelection(peek && this.items.get(String(peek.id)) ? [String(peek.id)] : []);
  }

  update(input) {
    const { view } = input;
    const m = toTimeline(input);
    const zoom = view.zoom || {};
    const opts = {
      height: '100%', stack: true, orientation: { axis: 'top', item: 'top' }, margin: { item: { horizontal: 6, vertical: 6 }, axis: 6 },
      showCurrentTime: false, selectable: true, editable: false, groupOrder: 'order', tooltip: { followMouse: true, overflowMethod: 'cap', delay: 150 },
      zoomMin: durationMs(zoom.min) || 60 * 1000, zoomMax: durationMs(zoom.max) || 50 * 365 * 864e5,
    };
    this.items.clear();
    this.groups.clear();
    if (m.groups) this.groups.add(m.groups);
    this.items.add(m.items);
    if (!this.timeline) {
      this.timeline = new Timeline(this.box, this.items, m.groups ? this.groups : null, opts);
      this.timeline.on('click', (p) => { if (p.item != null) this.host.open(p.item); });
    } else {
      this.timeline.setOptions(opts);
      this.timeline.setGroups(m.groups ? this.groups : null);
    }
    // WHY a key: a new view, axis or lane set re-fits the window; a filter or theme change keeps where you zoomed
    const key = JSON.stringify([view.name, view.start, view.end, view.groupBy, view.subGroupBy, m.groups ? m.groups.length : 0]);
    if (key !== this._fitKey && m.items.length) { this.timeline.fit({ animation: false }); this._fitKey = key; }
    const lanes = m.groups ? m.groups.filter((g) => !g.treeLevel).length : 0;
    const parts = [`${m.items.length} on the axis${lanes ? ` · ${lanes} lanes` : ''}`];
    if (!view.start) parts.push('<span class="dv-err">set <code>start:</code>, the property holding each row\'s date</span>');
    else if (m.missing) parts.push(`${m.missing} without a ${esc(input.columns[view.start] ? input.columns[view.start].label.toLowerCase() : view.start)}`);
    this.host.setStatus(parts.join(' · '));
  }
}
