// mediaUrl (packages/core/src/format.js): a relative image path in a cell resolves against the data file's URL, never
// the page's (docs/CONTRACT.md §1 amendment 2026-10-26, and §10, the core pass).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mediaUrl } from '../../packages/core/src/format.js';

const data = { url: 'http://127.0.0.1:4610/gallery/robotparts-actuators/actuators.json' };

test('a relative path resolves beside the data file, wherever the page is', () => {
  assert.equal(mediaUrl('photos/a.webp', data), 'http://127.0.0.1:4610/gallery/robotparts-actuators/photos/a.webp');
  assert.equal(mediaUrl('../logo-rounds/svg/x.svg', data), 'http://127.0.0.1:4610/gallery/logo-rounds/svg/x.svg');
  assert.equal(mediaUrl('/static/p.png', data), 'http://127.0.0.1:4610/static/p.png');
});

test('absolute, data: and blob: URLs pass through; missing stays missing', () => {
  assert.equal(mediaUrl('https://robotparts.dev/v2/files/x.webp', data), 'https://robotparts.dev/v2/files/x.webp');
  assert.equal(mediaUrl('data:image/png;base64,AAAA', data), 'data:image/png;base64,AAAA');
  assert.equal(mediaUrl(null, data), null);
  assert.equal(mediaUrl('', data), '');
});

test('with no data URL and no page (Node), the text comes back unchanged', () => {
  assert.equal(mediaUrl('photos/a.webp', {}), 'photos/a.webp');
});

// WHY: Zach's truthful-rendering rule: a stored value is shown as stored, never silently rounded (robotparts' Daheng
// price 986.8881 had read 986.9). Rounding happens only when a view asks for it with `decimals`.
test('fmtNum shows the stored number in full unless the view asks for decimals', async () => {
  const { fmtNum } = await import('../../packages/core/src/format.js');
  assert.equal(fmtNum(986.8881), '986.8881');
  assert.equal(fmtNum(1149), '1,149');
  assert.equal(fmtNum(0.0509), '0.0509');
  assert.equal(fmtNum(0.0000068), '0.0000068');
  assert.equal(fmtNum(9.615), '9.615');
  assert.equal(fmtNum(986.8881, 1), '986.9');
});
