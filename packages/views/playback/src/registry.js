/* The playback controls' registry (docs/peps/0005-dashboard-cards.md §4b): every control the playback card can draw,
   built-in or added later (a LIVE tier with rewind, for one), goes through this one small interface.

     registerPlaybackVariant('rerun', {
       label: 'P1 · Rerun',                       // the switcher's name for it
       create(host, el, clock, ctx) {             // el: the element to fill; clock: the dashboard's Clock (call it,
         return { update(input) {}, destroy() {} }; // listen to it, never own t); ctx: {name, dashboard}
       },
     });

   The card picks `playback.variant` (else 'bar'), creates it once, calls update(input) on every input and destroy()
   when it switches away or goes. A variant's name must also be in schemas/view.schema.json's playback.variant enum
   for a .base to name it (a contract change); the switcher lists every registered one. */

const VARIANTS = new Map();

/** Add a playback control; a second registration of a name throws (as core's registerView does). */
export function registerPlaybackVariant(name, spec) {
  if (!name || typeof name !== 'string') throw new Error('registerPlaybackVariant: a name');
  if (!spec || typeof spec.create !== 'function') throw new Error(`registerPlaybackVariant(${name}): spec.create(host, el, clock, ctx)`);
  if (VARIANTS.has(name)) throw new Error(`registerPlaybackVariant: '${name}' is already registered`);
  VARIANTS.set(name, { name, label: spec.label || name, create: spec.create });
}

/** One registered control, else null. */
export const playbackVariant = (name) => VARIANTS.get(name) || null;

/** Every registered control, in registration order: [{name, label, create}]. */
export const playbackVariants = () => [...VARIANTS.values()];
