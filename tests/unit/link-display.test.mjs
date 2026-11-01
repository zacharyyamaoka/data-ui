// `display: link` (docs/CONTRACT.md §22): a value becomes an <a> only when it is something a browser can open, an
// http(s) URL or a relative path, query or fragment; its label is the cell's `text` when the producer wrote one. Anything
// else (another scheme such as `account:…`, a bare id, a value with spaces, an empty value) is drawn as its label, as
// plain text, with no <a>. WHY (orchestrator, 2026-10-30, for source precedence): a private source (a supplier chat) has
// no public URL, and a link that goes nowhere is a lie; `javascript:` must never be clickable.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { linkCell, isLinkTarget } from '../../packages/core/src/format.js';
import { linkHtml } from '../../packages/core/src/sections.js';

const anchors = (html) => [...html.matchAll(/<a\b[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/g)].map((m) => ({ href: m[1], label: m[2] }));
const visible = (html) => html.replace(/<[^>]*>/g, '');

test('an http(s) value is a link; with no text its label is the value without the scheme, exactly as the views drew it', () => {
  assert.equal(linkCell('https://example.com/a?x=1'), '<a href="https://example.com/a?x=1" rel="noopener">example.com/a?x=1</a>');
  assert.equal(linkCell('http://example.com/'), '<a href="http://example.com/" rel="noopener">example.com/</a>');
  assert.equal(linkCell({ value: 'https://example.com/b' }), '<a href="https://example.com/b" rel="noopener">example.com/b</a>', 'a rich cell without text');
  assert.equal(linkCell('HTTPS://EXAMPLE.COM/C'), '<a href="HTTPS://EXAMPLE.COM/C" rel="noopener">HTTPS://EXAMPLE.COM/C</a>', 'the scheme is case-insensitive; the label strips only the lower-case scheme the views stripped');
});

test('a rich cell with text: the text is the anchor label, exactly as written', () => {
  assert.deepEqual(anchors(linkCell({ value: 'https://example.com/p', text: 'Product page' })), [{ href: 'https://example.com/p', label: 'Product page' }]);
  assert.deepEqual(anchors(linkCell({ value: 'https://example.com/p', text: '  Two  spaces ' })), [{ href: 'https://example.com/p', label: '  Two  spaces ' }], 'never trimmed');
});

test('a value that is not a link target draws its text (else the value) as plain text, with no <a>', () => {
  for (const [cell, label] of [
    [{ value: 'account:supplier-chat/2026-10-08', text: 'Supplier chat' }, 'Supplier chat'],
    ['account:supplier-chat/2026-10-08', 'account:supplier-chat/2026-10-08'],
    ['acct-1234', 'acct-1234'],
    [{ value: 'acct-1234', text: 'Account 1234' }, 'Account 1234'],
    ['mailto:someone@example.com', 'mailto:someone@example.com'],
    ['javascript:alert(1)', 'javascript:alert(1)'],
    ['two words', 'two words'],
    [12345, '12345'],
    ['https://', 'https://'],
  ]) {
    const html = linkCell(cell);
    assert.deepEqual(anchors(html), [], `${JSON.stringify(cell)} makes no <a>: ${html}`);
    assert.doesNotMatch(html, /<a\b/, `${JSON.stringify(cell)}: no anchor at all`);
    assert.equal(visible(html), label, `${JSON.stringify(cell)} reads as its label`);
  }
});

test('an empty value draws nothing (the caller draws its "—"), with or without text', () => {
  for (const cell of [null, undefined, '', { value: null }, { value: '', text: 'x' }]) assert.equal(linkCell(cell), '', JSON.stringify(cell));
});

test('a relative path, query or fragment stays a link, its href as written (the view resolves it as it did)', () => {
  assert.deepEqual(anchors(linkCell('index.html?run=a/b#t=1&tr=1,2')), [{ href: 'index.html?run=a/b#t=1&amp;tr=1,2', label: 'index.html?run=a/b#t=1&amp;tr=1,2' }]);
  assert.deepEqual(anchors(linkCell('docs/sheet.pdf')), [{ href: 'docs/sheet.pdf', label: 'docs/sheet.pdf' }]);
  assert.deepEqual(anchors(linkCell('/fs/abc')), [{ href: '/fs/abc', label: '/fs/abc' }]);
  assert.deepEqual(anchors(linkCell('#t=1.5')), [{ href: '#t=1.5', label: '#t=1.5' }]);
  assert.deepEqual(anchors(linkCell({ value: '../x/report.html', text: 'The report' })), [{ href: '../x/report.html', label: 'The report' }]);
});

test('isLinkTarget: http(s) and relative references yes; other schemes, bare ids, spaces and empties no', () => {
  for (const v of ['https://a.b/c', 'http://a.b', 'a/b', 'a.pdf', '?q=1', '#frag', '/root', './x', '../y', '//cdn.example.com/x.js']) assert.equal(isLinkTarget(v), true, v);
  for (const v of ['account:x', 'mailto:a@b.c', 'javascript:void(0)', 'data:text/html,hi', 'file:///etc/passwd', 'acct-1234', 'A', '', '  ', 'two words', null, undefined, 42, ['https://a.b'], 'https://']) assert.equal(isLinkTarget(v), false, JSON.stringify(v));
});

test('the label and the href are escaped: markup in a value or a text stays text', () => {
  const html = linkCell({ value: 'https://example.com/?a="1"&b=<2>', text: '<b>bold</b> & co' });
  assert.match(html, /^<a href="https:\/\/example\.com\/\?a=&quot;1&quot;&amp;b=&lt;2&gt;" rel="noopener">&lt;b&gt;bold&lt;\/b&gt; &amp; co<\/a>$/);
  assert.equal(linkCell({ value: 'account:<x>', text: '<i>chat</i>' }), '&lt;i&gt;chat&lt;/i&gt;');
});

test('the side peek (sections.js linkHtml) follows the same rule: an <a> resolved against the data URL, labelled by the text', () => {
  const base = 'https://data.example.com/cases/one/data.json';
  assert.equal(linkHtml('https://example.com/a', base), '<a class="dv-peek-link" href="https://example.com/a">https://example.com/a</a>', 'unchanged for a URL without text');
  assert.equal(linkHtml('index.html?run=r1#t=2', base), '<a class="dv-peek-link" href="https://data.example.com/cases/one/index.html?run=r1#t=2">index.html?run=r1#t=2</a>', 'a relative link resolves against the data file, as before');
  assert.deepEqual(anchors(linkHtml({ value: 'https://example.com/a', text: 'Example' }, base)), [{ href: 'https://example.com/a', label: 'Example' }]);
  for (const [cell, label] of [[{ value: 'account:chat/7', text: 'Supplier chat' }, 'Supplier chat'], ['acct-1234', 'acct-1234'], ['javascript:alert(1)', 'javascript:alert(1)']]) {
    const html = linkHtml(cell, base);
    assert.doesNotMatch(html, /<a\b/, `${JSON.stringify(cell)}: ${html}`);
    assert.equal(visible(html), label);
  }
  assert.equal(linkHtml(null, base), '<span class="dv-none" title="no value">—</span>', 'empty stays the dash');
});
