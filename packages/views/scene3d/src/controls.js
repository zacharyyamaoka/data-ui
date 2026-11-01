/* trajectory3d's controls (docs/peps/0010-robotics-playback.md §5.2): a strip under the stage, worded, as July asked
   ("a worded multi-select, not check marks"): per trajectory its display modes (Line, Points, Frames, Z only) and its
   robot's colour, opacity and visibility; then Show (all time steps | Decay) with the decay in seconds and its sample
   count, the density dial (traj_compare's log dial, 4 to 400) and Compare's arrow scale.

   Every change goes through host.setView into the view entry, so it rides in the URL (v=) and Save view, and a filter
   change never resets it (CONTRACT §32). Show/hide is the rail's job (Zach, Oct 28 evening): no eye here.
   WHY a strip under the stage, not a side panel: the mock (arm.png) draws it there, and a side panel would need its
   own draggable boundary (.claude/feedback.md, resizable panels). */

import { esc } from '@data-ui/core';
import { densityOfDial, dialOfDensity } from './math.js';

const MODES = [['line', 'Line'], ['points', 'Points'], ['frames', 'Frames'], ['frames-z', 'Z only']];
const SCALES = [1, 10, 30, 100];

/** An SVG line swatch with the series' colour and dash pattern (dash units → px). */
export function swatch(css, dash, w = 18) {
  const d = dash && dash.some((x) => x > 0) ? ` stroke-dasharray="${dash.filter((x, i) => x > 0 || i < 2).map((x) => +(x * 0.75).toFixed(2)).join(' ')}"` : '';
  return `<svg width="${w}" height="6" aria-hidden="true"><line x1="0" y1="3" x2="${w}" y2="3" stroke="${esc(css)}" stroke-width="2"${d}/></svg>`;
}

export class Controls {
  constructor(box, host) {
    this.box = box;
    this.host = host;
    this.sig = null;
    this._onClick = (e) => this._click(e);
    this._onChange = (e) => this._change(e);
    this._onInput = (e) => this._input(e);
    this._onKey = (e) => { if (e.key === 'Enter' && e.target.matches('[data-decay]')) { e.preventDefault(); this._commitDecay(e.target); } };
    box.addEventListener('click', this._onClick);
    box.addEventListener('change', this._onChange);
    box.addEventListener('input', this._onInput);
    box.addEventListener('keydown', this._onKey);
  }

  destroy() {
    this.box.removeEventListener('click', this._onClick);
    this.box.removeEventListener('change', this._onChange);
    this.box.removeEventListener('input', this._onInput);
    this.box.removeEventListener('keydown', this._onKey);
  }

  /** Draw for this input's model; kept (and the focus with it) while nothing it shows changed. `preview(name, opacity)`
      shows a robot's opacity while its slider moves, before the change commits. */
  draw(input, model, { rate = null, preview = () => {} } = {}) {
    this.input = input;
    this.preview = preview;
    const spec = (input.view && input.view.trajectory3d) || {};
    this.spec = spec;
    const st = model.stage;
    const robots = model.robots ? Object.fromEntries(model.robots.series.map((r) => [r.series, r])) : {};
    const per = (spec.robots && spec.robots.series) || {};
    const rows = model.series.map((s) => ({ name: s.name, css: s.css, dash: s.dash, modes: s.modes, robot: robots[s.name] || null,
      robotConf: per[s.name] || {}, hasRobots: !!model.robots }));
    const cmp = model.compare || null;
    const sig = JSON.stringify([rows.map((r) => [r.name, r.css, r.dash, r.modes, r.robot && [r.robot.color, r.robot.opacity, r.robot.colorKey], r.robotConf, r.hasRobots]),
      st.show, st.decay, st.density, rate, cmp && [cmp.pairs, cmp.scale]]);
    if (sig === this.sig) return;
    this.sig = sig;
    const focus = document.activeElement && this.box.contains(document.activeElement) ? focusKey(document.activeElement) : null;
    const decayText = st.decay === 'inf' ? 'inf' : String(st.decay);
    const samples = st.decay !== 'inf' && rate ? ` ≈ ${Math.round(st.decay * rate).toLocaleString()} samples at ${+rate.toPrecision(3)} Hz` : '';
    const html = [`<div class="dv-t3-rows">`];
    for (const r of rows) {
      const modes = MODES.map(([m, label]) => `<button type="button" data-mode="${m}" aria-pressed="${r.modes.includes(m)}" title="Draw ${esc(r.name)} as ${label.toLowerCase()}">${label}</button>`).join('');
      let robot = '';
      // a robot row only where the series has link rows to pose one (or its robot is turned off and can come back)
      if (r.hasRobots && (r.robot || r.robotConf.show === false)) {
        const shown = r.robotConf.show !== false;
        const key = r.robotConf.color === undefined ? 'series' : String(r.robotConf.color);
        const opts = [['series', 'its colour'], ['muted', 'muted'], ...[1, 2, 3, 4, 5, 6, 7, 8].map((n) => [String(n), `slot ${n}`])];
        if (!opts.some(([v]) => v === key)) opts.push([key, key]);
        const op = Math.round(100 * (r.robotConf.opacity ?? (r.robot ? r.robot.opacity : 1)));
        robot = `<span class="dv-t3-group dv-t3-robot"><span>Robot</span>
          <button type="button" data-robot-show aria-pressed="${shown}" title="Show or hide ${esc(r.name)}'s robot">${shown ? 'on' : 'off'}</button>
          <select data-robot-color aria-label="${esc(r.name)}'s robot colour"${shown ? '' : ' disabled'}>${opts.map(([v, l]) => `<option value="${esc(v)}"${v === key ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>
          <input type="range" data-robot-opacity min="0" max="100" step="5" value="${op}" aria-label="${esc(r.name)}'s robot opacity"${shown ? '' : ' disabled'}><output>${op} %</output></span>`;
      }
      html.push(`<div class="dv-t3-row" data-t3-series="${esc(r.name)}"><span class="dv-t3-name">${swatch(r.css, r.dash)}${esc(r.name)}</span>
        <span class="dv-t3-group" role="group" aria-label="Draw ${esc(r.name)} as">${modes}</span>${robot}</div>`);
    }
    html.push('</div><div class="dv-t3-stage">');
    html.push(`<label>Show <select data-show><option value="all"${st.show === 'all' ? ' selected' : ''}>all time steps</option><option value="trail"${st.show === 'trail' ? ' selected' : ''}>decay</option></select></label>`);
    html.push(`<label class="dv-t3-decay"${st.show === 'trail' ? '' : ' hidden'}>Decay <input type="text" data-decay inputmode="decimal" value="${esc(decayText)}" aria-label="Decay in seconds, or inf"> s<span class="dv-t3-hint">${esc(samples)}</span></label>`);
    const dial = Math.round(dialOfDensity(st.density));
    html.push(`<label>Density <input type="range" data-density min="0" max="100" step="1" value="${dial}" aria-label="Markers per path (4 to 400, log)"><output>${st.density}</output></label>`);
    if (cmp && cmp.pairs.length) {
      const pairs = cmp.pairs.map(([a, b]) => `${esc(a)} → ${esc(b)}`).join(', ');
      html.push(`<label>Compare ${pairs} <select data-compare-scale aria-label="Arrow length (display only)">${[...new Set([...SCALES, cmp.scale])].sort((a, b) => a - b).map((k) => `<option value="${k}"${k === cmp.scale ? ' selected' : ''}>×${k}</option>`).join('')}</select></label>`);
    }
    html.push('</div>');
    this.box.innerHTML = html.join('');
    if (focus) { const el = this.box.querySelector(focus); if (el) el.focus(); }
  }

  _set(patch) {
    const next = { ...(this.spec || {}), ...patch };
    for (const k of Object.keys(next)) if (next[k] === undefined) delete next[k];
    this.host.setView({ trajectory3d: next });
  }

  _series(el) { const row = el.closest('[data-t3-series]'); return row ? row.dataset.t3Series : null; }

  _robots(name, patch) {
    const rb = { ...((this.spec && this.spec.robots) || {}) };
    const series = { ...(rb.series || {}) };
    const conf = { ...(series[name] || {}), ...patch };
    for (const k of Object.keys(conf)) if (conf[k] === undefined) delete conf[k];
    series[name] = conf;
    rb.series = series;
    this._set({ robots: rb });
  }

  _click(e) {
    const b = e.target.closest('button');
    if (!b || !this.box.contains(b)) return;
    const name = this._series(b);
    if (b.dataset.mode && name) {
      const spec = this.spec || {};
      const now = Array.isArray(spec.modes && spec.modes[name]) ? [...spec.modes[name]] : ['line'];
      const m = b.dataset.mode;
      let next = now.includes(m) ? now.filter((x) => x !== m) : [...now, m];
      // a full triad and the Z axis alone are two looks of one thing: one at a time
      if (m === 'frames' && next.includes('frames')) next = next.filter((x) => x !== 'frames-z');
      if (m === 'frames-z' && next.includes('frames-z')) next = next.filter((x) => x !== 'frames');
      // WHY never empty: show/hide is the rail's (a modes list has at least one entry, schemas/view.schema.json)
      if (!next.length) return;
      this._set({ modes: { ...((spec.modes && typeof spec.modes === 'object') ? spec.modes : {}), [name]: MODES.map(([x]) => x).filter((x) => next.includes(x)) } });
    } else if (b.hasAttribute('data-robot-show') && name) {
      this._robots(name, { show: b.getAttribute('aria-pressed') === 'true' ? false : undefined });
    }
  }

  _input(e) {
    const t = e.target;
    if (t.matches('[data-density]')) t.nextElementSibling.textContent = String(densityOfDial(Number(t.value)));
    else if (t.matches('[data-robot-opacity]')) {
      t.nextElementSibling.textContent = `${t.value} %`;
      const name = this._series(t);
      if (name) this.preview(name, Number(t.value) / 100);
    }
  }

  _change(e) {
    const t = e.target;
    const name = this._series(t);
    if (t.matches('[data-show]')) this._set({ show: t.value === 'trail' ? 'trail' : 'all' });
    else if (t.matches('[data-decay]')) this._commitDecay(t);
    else if (t.matches('[data-density]')) this._set({ density: densityOfDial(Number(t.value)) });
    else if (t.matches('[data-compare-scale]')) this._set({ compare: { ...((this.spec && this.spec.compare) || {}), scale: Number(t.value) } });
    else if (t.matches('[data-robot-color]') && name) this._robots(name, { color: /^\d+$/.test(t.value) ? Number(t.value) : t.value === 'series' ? undefined : t.value });
    else if (t.matches('[data-robot-opacity]') && name) this._robots(name, { opacity: Number(t.value) / 100 });
  }

  /** Seconds ≥ 0 or inf (a trail never shows the future; `.inf` and negatives are not written, CONTRACT §32). */
  _commitDecay(t) {
    const text = String(t.value).trim().toLowerCase().replace(/\s*s$/, '');
    const v = text === 'inf' || text === '∞' ? 'inf' : Number(text);
    if (v !== 'inf' && !(Number.isFinite(v) && v >= 0)) { t.value = String((this.spec && this.spec.decay) ?? 'inf'); return; }
    if (v === ((this.spec && this.spec.decay) ?? 'inf')) return;
    this._set({ decay: v });
  }
}

/** A selector that finds the same control after a redraw. */
function focusKey(el) {
  const row = el.closest('[data-t3-series]');
  const at = row ? `[data-t3-series="${CSS.escape(row.dataset.t3Series)}"] ` : '';
  for (const a of ['data-mode', 'data-robot-show', 'data-robot-color', 'data-robot-opacity', 'data-show', 'data-decay', 'data-density', 'data-compare-scale']) {
    if (el.hasAttribute(a)) return `${at}[${a}${a === 'data-mode' ? `="${el.getAttribute(a)}"` : ''}]`;
  }
  return null;
}
