/* Hands index.js the Event Calendar namespace. WHY this file: @event-calendar/build ships only a minified IIFE that
   assigns `var EventCalendar = (function (e) { … return e })({})`, with no export, and build.mjs has no loader that
   could import its text. Its first statement stamps that namespace object with Object.defineProperty(e,
   Symbol.toStringTag, {value: 'Module'}); this module, imported just before it, notes that object, and release()
   puts Object.defineProperty back. Replace it with a plain import once @event-calendar/core (ESM) is installed. */

const define = Object.defineProperty;
let namespace = null;

Object.defineProperty = function capture(target, key, descriptor) {
  if (!namespace && key === Symbol.toStringTag && descriptor && descriptor.value === 'Module') namespace = target;
  return define.call(Object, target, key, descriptor);
};

/** The namespace ({create, destroy}); restores Object.defineProperty. */
export function release() {
  Object.defineProperty = define;
  if (!namespace || typeof namespace.create !== 'function') throw new Error('the Event Calendar bundle did not load');
  return namespace;
}
