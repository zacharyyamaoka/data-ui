// The app rail's state (packages/core/src/rail/model.js; docs/CONTRACT.md §27): three styles, the last open style kept
// under its own key, collapse as a toggle and not a cycle, a choice that is written the moment it is made. Ported from
// Clank's store.test.ts (clank-workbench @ 7ba2041, "railMode — three sidebar styles"); the element and its geometry
// are browser checks (tests/browser/rail_checks.py).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { RAIL_MODES, OPEN_RAIL_MODES, RAIL_MODE_OPTIONS, isRailMode, createRail, storageKeys } from '../../packages/core/src/rail/model.js';

/** A localStorage stand-in over the given contents; `values` is what a reload would still find. */
function memory(initial = {}) {
  const values = new Map(Object.entries(initial));
  return { values, getItem: (k) => values.get(k) ?? null, setItem: (k, v) => void values.set(k, String(v)), removeItem: (k) => void values.delete(k) };
}
const KEYS = storageKeys('app');

test("rail: three styles; an unknown value is not one", () => {
  assert.deepEqual(RAIL_MODES, ['collapsed', 'expanded', 'wide']);
  assert.deepEqual(OPEN_RAIL_MODES, ['expanded', 'wide']);
  assert.deepEqual(RAIL_MODE_OPTIONS.map((o) => o.value), RAIL_MODES);
  assert.ok(RAIL_MODE_OPTIONS.every((o) => o.label));
  for (const mode of RAIL_MODES) assert.equal(isRailMode(mode), true);
  for (const bad of ['sideways', '', null, undefined, 3, {}]) assert.equal(isRailMode(bad), false);
});

test("rail: starts on the icon rail with Figma's rail as the open style", () => {
  const rail = createRail({ key: 'app', storage: memory() });
  assert.equal(rail.mode, 'collapsed');
  assert.equal(rail.lastOpen, 'expanded');
  assert.equal(KEYS.mode, 'data-ui/rail/app');
  assert.equal(KEYS.lastOpen, 'data-ui/rail/app.lastOpen');
});

test("rail: reads a persisted 'wide' back, and anything unknown as collapsed", () => {
  assert.equal(createRail({ key: 'app', storage: memory({ [KEYS.mode]: 'wide' }) }).mode, 'wide');
  assert.equal(createRail({ key: 'app', storage: memory({ [KEYS.mode]: 'sideways' }) }).mode, 'collapsed');
  // markup's mode is a default only: what a person chose wins, and an unusable stored value falls to the default
  assert.equal(createRail({ key: 'app', mode: 'wide', storage: memory({ [KEYS.mode]: 'expanded' }) }).mode, 'expanded');
  assert.equal(createRail({ key: 'app', mode: 'wide', storage: memory({ [KEYS.mode]: 'sideways' }) }).mode, 'wide');
  assert.equal(createRail({ key: 'app', mode: 'sideways', storage: memory() }).mode, 'collapsed');
});

test('rail: the toggle collapses and re-opens the LAST open style, not always Figma', () => {
  const storage = memory();
  const rail = createRail({ key: 'app', storage });
  rail.setMode('wide');
  rail.toggle();
  assert.equal(rail.mode, 'collapsed');
  rail.toggle();
  assert.equal(rail.mode, 'wide');
  rail.setMode('expanded');
  rail.toggle();
  rail.toggle();
  assert.equal(rail.mode, 'expanded');
  assert.equal(storage.values.get(KEYS.mode), 'expanded');
  assert.equal(storage.values.get(KEYS.lastOpen), 'expanded');
});

test('rail: the toggle is two states, never a three-way cycle', () => {
  const rail = createRail({ key: 'app', mode: 'expanded', storage: memory() });
  const seen = [];
  for (let i = 0; i < 6; i += 1) { rail.toggle(); seen.push(rail.mode); }
  assert.deepEqual(seen, ['collapsed', 'expanded', 'collapsed', 'expanded', 'collapsed', 'expanded']);
});

test('rail: remembers the open style across a reload while collapsed', () => {
  const rail = createRail({ key: 'app', storage: memory({ [KEYS.mode]: 'collapsed', [KEYS.lastOpen]: 'wide' }) });
  assert.equal(rail.lastOpen, 'wide');
  rail.toggle();
  assert.equal(rail.mode, 'wide');
});

test('rail: an open-mode default opens the wide list on a first toggle; a stored lastOpen outranks it', () => {
  assert.equal(createRail({ key: 'app', openMode: 'wide', storage: memory() }).lastOpen, 'wide');
  assert.equal(createRail({ key: 'app', openMode: 'sideways', storage: memory() }).lastOpen, 'expanded');
  assert.equal(createRail({ key: 'app', openMode: 'wide', storage: memory({ [KEYS.lastOpen]: 'expanded' }) }).lastOpen, 'expanded');
  // an unknown lastOpen (or collapsed, which is not an open style) is ignored
  assert.equal(createRail({ key: 'app', storage: memory({ [KEYS.lastOpen]: 'collapsed' }) }).lastOpen, 'expanded');
  // a rail that starts open has that style as its last open style whatever was stored
  assert.equal(createRail({ key: 'app', mode: 'wide', storage: memory({ [KEYS.lastOpen]: 'expanded' }) }).lastOpen, 'wide');
});

test('rail: setMode writes at once, with no later flush needed, and an unknown mode is collapsed', () => {
  const storage = memory();
  const rail = createRail({ key: 'app', storage });
  assert.equal(rail.setMode('wide'), true);
  // the write is already there: a reload in the same tick still reads it (Clank's debounce lost this change)
  assert.equal(createRail({ key: 'app', storage }).mode, 'wide');
  assert.equal(rail.setMode('wide'), false, 'no change, no event');
  assert.equal(rail.setMode('sideways'), true);
  assert.equal(rail.mode, 'collapsed');
  assert.equal(storage.values.get(KEYS.mode), 'collapsed');
  assert.equal(storage.values.get(KEYS.lastOpen), 'wide', 'collapsing keeps the last open style');
});

test('rail: flush rewrites both keys (the pagehide net); two rails with different keys do not meet', () => {
  const storage = memory();
  const rail = createRail({ key: 'app', storage });
  rail.setMode('wide');
  storage.values.clear();
  rail.flush();
  assert.equal(storage.values.get(KEYS.mode), 'wide');
  assert.equal(storage.values.get(KEYS.lastOpen), 'wide');
  const other = createRail({ key: 'other', storage });
  assert.equal(other.mode, 'collapsed');
});

test('rail: flush before any choice writes nothing, so a changed markup default still reaches people who never chose', () => {
  const storage = memory();
  createRail({ key: 'app', mode: 'wide', storage }).flush();
  assert.equal(storage.values.size, 0);
});

test('rail: storage that throws (a private window) still gives a working rail', () => {
  const broken = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } };
  const rail = createRail({ key: 'app', storage: broken });
  assert.equal(rail.mode, 'collapsed');
  rail.setMode('wide');
  assert.equal(rail.mode, 'wide');
  rail.toggle();
  rail.toggle();
  assert.equal(rail.mode, 'wide');
  rail.flush();
});
