/* One editing session of a <data-dashboard>: the .base text being edited, its history, and the hand-over to the host.

   WHY the host saves, never data-ui (CONTRACT §34): `save()` fires `data-dashboard-save` (bubbles, composed, cancelable) on
   the dashboard, detail {dashboard: {id, title, url}, text, before, changes, message, asCopy, respondWith(promise)},
   FetchEvent's rule, as data-add-to-dashboard's. A host that saves calls respondWith while the event is dispatched; its
   promise resolves (anything, or {ok: true, title?, href?}) or rejects / resolves {ok: false, reason}. preventDefault()
   alone: the host took it over. Neither: the text goes to the clipboard, and the editor says so. `before` is the text the
   edits started from, so a host can refuse a file that moved underneath. */

import { loadDataset } from '../../../core/src/data.js';
import { readDashboard } from '../model.js';
import { changeList, lineDiff, columnsOf } from './ops.js';

export class EditSession {
  constructor(dash) {
    this.dash = dash;
    this.saved = dash.baseText;
    this.text = this.saved;
    this.history = [this.text];
    this.at = 0;
    // what a view type left behind when a panel switched type (ops.convertView), so switching back restores it
    this.stash = {};
  }

  get dirty() { return this.text !== this.saved; }
  get canUndo() { return this.at > 0; }
  get canRedo() { return this.at < this.history.length - 1; }
  /** The file's URL: where the data paths are written from, and what `src` reads. */
  get url() { return this.dash._baseHref(); }
  get title() {
    const first = /^#\s*([^:\n]+)/.exec(this.saved || '');
    return (this.dash.getAttribute('aria-label') || (first && first[1].trim()) || (this.dash.getAttribute('src') || 'dashboard').split('/').pop().replace(/\.base$/, '')).trim();
  }
  changes() { return changeList(this.saved, this.text); }
  diff() { return lineDiff(this.saved, this.text); }
  columns(dataset) { return columnsOf(this.dash.datasets && this.dash.datasets[dataset]); }

  /** Record `next` as the current text. */
  push(next) {
    this.history = this.history.slice(0, this.at + 1);
    this.history.push(next);
    this.at = this.history.length - 1;
    this.text = next;
  }

  undo() { if (!this.canUndo) return null; this.at--; this.text = this.history[this.at]; return this.text; }
  redo() { if (!this.canRedo) return null; this.at++; this.text = this.history[this.at]; return this.text; }

  /** The datasets a parsed text names that the dashboard has not read yet (a queued item's file). */
  async ensureData(base) {
    const d = readDashboard(base);
    for (const x of Object.values(d.datasets)) {
      if (x.template || (this.dash.datasets && this.dash.datasets[x.name])) continue;
      const href = new URL(x.data, this.url).href;
      const ds = await loadDataset(href);
      this.dash.datasets[x.name] = { ...ds, url: href };
    }
  }

  /** Hand `text` (default the session's) to the host for the file `target` (default this dashboard). Resolves
      {ok, via: 'host' | 'taken' | 'clipboard' | 'none', title?, href?, reason?}. */
  async save({ text = this.text, target = null, before = null, message = '', asCopy = null } = {}) {
    const mine = !target;
    const dashboard = target || { id: this.dash.id || null, title: this.title, url: this.url };
    let promise = null, live = true, ev = null;
    const detail = {
      dashboard: { ...dashboard }, text, before: mine ? this.saved : before, changes: mine ? changeList(this.saved, text) : [], message, asCopy,
      respondWith(p) {
        if (!live) throw new Error('respondWith(promise): call it while the data-dashboard-save event is dispatched');
        if (promise) throw new Error('respondWith(promise): it was called already for this save');
        promise = Promise.resolve(p);
        ev.preventDefault();
      },
    };
    ev = new CustomEvent('data-dashboard-save', { bubbles: true, composed: true, cancelable: true, detail });
    try { this.dash.dispatchEvent(ev); } finally { live = false; }
    let result;
    try {
      if (promise) {
        const r = await promise;
        if (r && typeof r === 'object' && r.ok === false) throw new Error(r.reason || 'the host did not save it');
        result = { ok: true, via: 'host', title: (r && r.title) || dashboard.title, href: r && r.href };
      } else if (ev.defaultPrevented) result = { ok: true, via: 'taken', title: dashboard.title };
      else {
        let copied = false;
        try { await navigator.clipboard.writeText(text); copied = true; } catch { copied = false; }
        result = copied ? { ok: true, via: 'clipboard', title: dashboard.title } : { ok: false, via: 'none', reason: 'no host saves here, and the clipboard is not available' };
      }
    } catch (err) {
      result = { ok: false, via: 'host', reason: (err && err.message) || String(err) };
    }
    // WHY not for a copy: the file on screen is still the file it was, so Exit still asks about these edits
    if (result.ok && mine && !asCopy) this.saved = text;
    return result;
  }
}
