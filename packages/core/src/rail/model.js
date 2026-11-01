/* The app rail's state, without a DOM (docs/CONTRACT.md §27; the element is data-rail.js).

   Ported from Clank's store (clank-workbench @ 7ba2041, src/workbench/store.ts): three styles, the last open style under
   its own key, and a toggle that is collapsed <-> that style. Storage is injected, so the unit test runs it in Node. */

/** The three left sidebars (Zach, 2026-10-27): Obsidian's icon rail, Figma's icon-over-label rail, Shopify's wide list. */
export const RAIL_MODES = ['collapsed', 'expanded', 'wide'];
export const OPEN_RAIL_MODES = ['expanded', 'wide'];
/** For a settings select (bindRailSelect): the value and the words a person sees. */
export const RAIL_MODE_OPTIONS = [
  { value: 'collapsed', label: 'Obsidian: icon rail' },
  { value: 'expanded', label: 'Figma: labels under icons' },
  { value: 'wide', label: 'Shopify: wide list' },
];

export const isRailMode = (value) => typeof value === 'string' && RAIL_MODES.includes(value);
const isOpenMode = (value) => typeof value === 'string' && OPEN_RAIL_MODES.includes(value);

/** The localStorage keys for a rail named `key`. */
export const storageKeys = (key) => ({ mode: `data-ui/rail/${key}`, lastOpen: `data-ui/rail/${key}.lastOpen` });

/** Create a rail's state. `mode` and `openMode` are the markup's defaults (a stored choice wins); `storage` is a
    localStorage-like object, default the page's. Every access is try/catch: a private window still gets a working rail
    whose choice lasts the visit. */
export function createRail({ key = 'rail', mode: initial, openMode, storage } = {}) {
  const keys = storageKeys(key);
  const store = () => { try { return storage || globalThis.localStorage || null; } catch { return null; } };
  const read = (k) => { try { return store()?.getItem(k) ?? null; } catch { return null; } };
  const write = (k, v) => { try { store()?.setItem(k, v); } catch { /* private window: the choice lasts this visit */ } };

  const stored = read(keys.mode);
  // WHY the stored value first: the markup's mode is a default, a person's choice outranks it; an unusable stored value
  // falls to the default, and an unknown default to collapsed
  let mode = isRailMode(stored) ? stored : isRailMode(initial) ? initial : 'collapsed';
  const storedOpen = read(keys.lastOpen);
  // a rail that starts open returns to that style; one that starts collapsed to the stored one, else the markup's, else Figma's
  let lastOpen = mode !== 'collapsed' ? mode : isOpenMode(storedOpen) ? storedOpen : isOpenMode(openMode) ? openMode : 'expanded';

  // WHY: until a person (or the host) makes a choice nothing is stored, so a changed markup default still reaches everyone
  // who never chose; flush() must not turn the default into a choice
  let chosen = false;
  const rail = {
    get mode() { return mode; },
    get lastOpen() { return lastOpen; },
    /** Set the style (an unknown one is collapsed) and write it at once. True when it changed. */
    setMode(next) {
      const value = isRailMode(next) ? next : 'collapsed';
      chosen = true;
      write(keys.mode, value);
      if (value !== 'collapsed') { write(keys.lastOpen, value); lastOpen = value; }
      if (value === mode) return false;
      mode = value;
      return true;
    },
    /** Collapsed <-> the last open style. WHY not a three-way cycle: "collapse it" must be one press from any open
        style; which open style you get is the setting's choice, the toggle only remembers it. */
    toggle() { rail.setMode(mode === 'collapsed' ? lastOpen : 'collapsed'); return mode; },
    /** Write both keys again once a choice was made (the element calls it on pagehide, a net under setMode's immediate write). */
    flush() { if (!chosen) return; write(keys.mode, mode); write(keys.lastOpen, lastOpen); },
  };
  return rail;
}
