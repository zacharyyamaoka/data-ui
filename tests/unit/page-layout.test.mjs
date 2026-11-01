// The page layout's pure half (docs/CONTRACT.md §46): defaults follow the table, a block moves only among blocks, a key names nothing away.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { freeProperty, layoutValue, moveEntry, pageLayout, pageOn, stepEntry, withPlace, withVisible } from '../../packages/core/src/page-layout.js';
import { markdown } from '../../packages/core/src/md.js';
import { isDerivedCell, mediaOf, outlineOf, sectionCell } from '../../packages/core/src/format.js';

const props = {
  name: { id: 'name', type: 'text' }, status: { id: 'status', type: 'text' }, cost: { id: 'cost', type: 'number' }, owner: { id: 'owner', type: 'text' },
  dp: { id: 'dp', type: 'text', long: true, section: true }, risks: { id: 'risks', type: 'text', long: true, section: true }, body: { id: 'body', type: 'text', pageBody: true },
};
const get = (l, id) => l.entries.find((e) => e.id === id);

test('with no page: key the page follows the table, and a section is always shown', () => {
  const l = pageLayout({}, props, { order: ['name', 'cost', 'status'], title: 'name' });
  assert.deepEqual(l.entries.map((e) => e.id), ['cost', 'status', 'owner', 'dp', 'risks']);
  assert.equal(get(l, 'cost').visible, true);
  assert.equal(get(l, 'owner').visible, false, 'not in the table, not on the page');
  assert.equal(get(l, 'dp').place, 'section');
  assert.equal(get(l, 'dp').visible, true, 'a section is words someone means to read');
  assert.equal(l.free, 'body');
  assert.ok(!l.entries.some((e) => e.id === 'body' || e.id === 'name'), 'neither the title nor the free text is in the list');
});

test('the key wins: order, place, visibility; what it does not name follows', () => {
  const base = { page: [{ property: 'status', place: 'section' }, { property: 'dp', visible: false }, { property: 'gone', place: 'section' }, { property: 'status' }] };
  const l = pageLayout(base, props, { order: ['name', 'cost'], title: 'name' });
  assert.deepEqual(l.entries.slice(0, 2), [{ id: 'status', place: 'section', visible: true }, { id: 'dp', place: 'top', visible: false }]);
  assert.deepEqual(l.unknown, [{ property: 'gone', place: 'section' }]);
  assert.ok(layoutValue(l).some((e) => e.property === 'gone'), 'a key for a property this data lacks stays in the file');
});

test('the value written back reads the same layout', () => {
  const base = { page: [{ property: 'status', place: 'section' }, { property: 'cost' }, { property: 'dp', visible: false }] };
  const l = pageLayout(base, props, { title: 'name' });
  assert.deepEqual(pageLayout({ page: layoutValue(l) }, props, { title: 'name' }).entries, l.entries);
});

test('a block moves among blocks, a row among rows: they never mix', () => {
  const l = pageLayout({ page: [{ property: 'status' }, { property: 'cost' }, { property: 'dp', place: 'section' }, { property: 'risks', place: 'section' }, { property: 'owner', visible: false }] }, props, { title: 'name' });
  const blocks = (e) => e.filter((x) => x.place !== 'top' && x.visible).map((x) => x.id);
  const rows = (e) => e.filter((x) => x.place === 'top' && x.visible).map((x) => x.id);
  const moved = stepEntry(l.entries, 'risks', -1);
  assert.deepEqual(blocks(moved), ['risks', 'dp']);
  assert.deepEqual(rows(moved), ['status', 'cost']);
  assert.equal(stepEntry(l.entries, 'dp', -1), l.entries, 'at the top already: the same list');
  assert.deepEqual(blocks(moveEntry(l.entries, 'dp', 99)), ['risks', 'dp']);
  assert.deepEqual(rows(stepEntry(l.entries, 'cost', -1)), ['cost', 'status']);
  assert.equal(moved.length, l.entries.length);
});

test('a place change keeps the order and shows it; hiding keeps its place', () => {
  const l = pageLayout({ page: [{ property: 'status', visible: false }, { property: 'cost' }] }, props, { title: 'name' });
  assert.deepEqual(withPlace(l.entries, 'status', 'section')[0], { id: 'status', place: 'section', visible: true });
  assert.deepEqual(withVisible(l.entries, 'cost', false)[1], { id: 'cost', place: 'top', visible: false });
});

test('a page is on when the file says so, or the data has a free text; else nothing changes', () => {
  assert.equal(pageOn({ page: [] }, {}), true);
  assert.equal(pageOn({}, props), true);
  assert.equal(pageOn({}, { name: { id: 'name' } }), false);
  assert.equal(freeProperty({ a: { id: 'a' } }), null);
});

test('markdown: images only when asked, escaped words around them', () => {
  assert.equal(markdown('![a](x.png)'), '<p>!<a href="#">a</a></p>', 'no image hook: as it always read');
  const seen = [];
  const out = markdown('see ![a<b](x.png) and ![[y z.png|200]] <i>', { image: (src, alt, embed) => { seen.push([src, alt, embed]); return '<img>'; } });
  assert.deepEqual(seen, [['x.png', 'a<b', false], ['y z.png', 'y z.png', true]]);
  assert.equal(out, '<p>see <img> and <img> &lt;i&gt;</p>');
  assert.equal(markdown('one\ntwo'), '<p>one two</p>');
  assert.equal(markdown('one\ntwo', { breaks: true }), '<p>one<br>two</p>');
});

test('markdown: wikilinks only when asked; each form; not inside code', () => {
  assert.equal(markdown('[[Note]]'), '<p>[[Note]]</p>');
  const seen = [];
  const out = markdown('[[Note]] [[Note|alias]] [[Note#Head|h]] [[Note#Head]] `[[code]]` ![[pic.png]]', { wikilink: (t, a) => { seen.push([t, a]); return '<a>'; }, image: () => '<img>' });
  assert.deepEqual(seen, [['Note', null], ['Note', 'alias'], ['Note#Head', 'h'], ['Note#Head', null]]);
  assert.equal(out, '<p><a> <a> <a> <a> <code>[[code]]</code> <img></p>');
});

const DP = '## 1. First\n\nwords\n\n### 1.1 Under it\n\n![a](x.png)\n\n## 2. Second\n\n```\n## not this one\n```\n\n## Third\n';

test('an outline is the sub-headings as written: indented, the source\'s own numbers kept, no fence', () => {
  assert.deepEqual(outlineOf(DP), [{ depth: 0, text: '1. First' }, { depth: 1, text: '1.1 Under it' }, { depth: 0, text: '2. Second' }, { depth: 0, text: 'Third' }]);
  assert.deepEqual(outlineOf('### Deep only'), [{ depth: 0, text: 'Deep only' }]);
  assert.deepEqual(outlineOf('words'), []);
});

test('a section cell: the row height decides how much shows, and the rest is counted, never dropped', () => {
  const tall = sectionCell(DP, { lines: 6 });
  assert.equal(tall.kind, 'outline');
  assert.equal(tall.items.length, 4);
  assert.equal(tall.more, 0);
  assert.equal(tall.media.length, 1, 'six lines: four of outline and room for the pictures');
  const short = sectionCell(DP, { lines: 1 });
  assert.deepEqual([short.items.length, short.more, short.media.length], [1, 3, 0]);
  const mid = sectionCell(DP, { lines: 3 });
  assert.deepEqual([mid.items.length, mid.more, mid.media.length], [3, 1, 0]);
});

test('a section with no sub-headings falls back to its first lines; `preview` asks for them anyway', () => {
  assert.equal(sectionCell('one\n\ntwo').kind, 'preview');
  assert.equal(sectionCell('one\n\ntwo').text, 'one\ntwo');
  assert.equal(sectionCell(DP, { mode: 'preview', lines: 2 }).kind, 'preview');
  assert.equal(sectionCell('a\nb\nc\nd').more, 1);
});

test('a picture: a thumbnail when there is room, [image] where it was when there is not', () => {
  assert.deepEqual(mediaOf('![a](x.png) ![[y.mp4|300]]').map((m) => [m.src, m.embed, m.video]), [['x.png', false, false], ['y.mp4', true, true]]);
  const room = sectionCell('words\n\n![a](x.png)', { lines: 3 });
  assert.deepEqual([room.text, room.media.length], ['words', 1]);
  const tight = sectionCell('words\n\n![a](x.png)\n\n![[v.mp4]]', { lines: 2 });
  assert.deepEqual([tight.text, tight.more, tight.media.length], ['words\n[image]', 1, 0]);
  assert.equal(sectionCell('![a](x.png)', { lines: 3 }).media.length, 1);
});

test('only a real outline is derived: a first-lines cell is still the value, and takes an edit', () => {
  assert.equal(isDerivedCell(DP, 'outline'), true);
  assert.equal(isDerivedCell('plain words', 'outline'), false);
  assert.equal(isDerivedCell(DP, 'preview'), false);
  assert.equal(isDerivedCell(null, 'outline'), false);
});
