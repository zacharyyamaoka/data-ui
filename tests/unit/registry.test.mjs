// The view registry (packages/core/src/registry.js): Obsidian's registerBasesView shape with a lazy load().
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { registerView, viewPlugin, listViews, loadView } from '../../packages/core/src/registry.js';

test('register, list, load once, refuse a second registration', async () => {
  let loads = 0;
  class Fake { constructor(host, el) { this.host = host; this.el = el; } update() {} destroy() {} }
  registerView('test-fake', { name: 'Fake', icon: 'x', load: async () => { loads++; return { default: Fake, options: () => [{ type: 'toggle', key: 'k' }] }; } });
  assert.equal(viewPlugin('test-fake').name, 'Fake');
  assert.ok(listViews().some((v) => v.type === 'test-fake' && v.status === 'built'));
  const a = await loadView('test-fake');
  const b = await loadView('test-fake');
  assert.equal(a.View, Fake);
  assert.equal(loads, 1, 'the code loads on first use only');
  assert.equal(a, b);
  assert.deepEqual(a.options(), [{ type: 'toggle', key: 'k' }]);
  assert.throws(() => registerView('test-fake', { load: async () => Fake }), /already registered/);
  assert.throws(() => registerView('test-nothing', {}), /needs load/);
  await assert.rejects(loadView('test-missing'), /no view is registered/);
});

test('a load() that fails can be retried', async () => {
  let n = 0;
  registerView('test-flaky', { load: async () => { if (n++ === 0) throw new Error('network'); return class {}; } });
  await assert.rejects(loadView('test-flaky'), /network/);
  assert.equal(typeof (await loadView('test-flaky')).View, 'function');
});
