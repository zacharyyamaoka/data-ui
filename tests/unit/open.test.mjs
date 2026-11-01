// How a record opens (packages/core/src/open.js; docs/CONTRACT.md amendment 2026-10-26 (open modes)): which setting
// is in force. The gestures and the layout are browser checks (gallery/examples/robotparts-actuators/checks.py).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { openSetting, OPEN_MODES, SPLIT_AT } from '../../packages/core/src/open.js';

test('open: default side at 1100 px; the file, then the element\'s attribute, then the view, field by field', () => {
  assert.deepEqual(OPEN_MODES, ['expand', 'side', 'link']);
  assert.deepEqual(openSetting(null, null, null), { mode: 'side', splitAt: SPLIT_AT, url: null });
  assert.equal(SPLIT_AT, 1100);
  const base = { open: { mode: 'link', splitAt: 900, url: 'page' } };
  assert.deepEqual(openSetting({ type: 'table' }, base, null), { mode: 'link', splitAt: 900, url: 'page' });
  assert.deepEqual(openSetting({ type: 'table' }, base, 'expand'), { mode: 'expand', splitAt: 900, url: 'page' });
  assert.deepEqual(openSetting({ type: 'table', open: 'side' }, base, 'expand'), { mode: 'side', splitAt: 900, url: 'page' });
  assert.deepEqual(openSetting({ open: { splitAt: 1400 } }, { open: 'expand' }, null), { mode: 'expand', splitAt: 1400, url: null });
  // an unknown mode is the checker's error; the page keeps what the less specific levels said
  assert.deepEqual(openSetting({ open: 'sideways' }, { open: 'expand' }, 'peek'), { mode: 'expand', splitAt: 1100, url: null });
});
