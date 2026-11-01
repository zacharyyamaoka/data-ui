// The core's markdown (packages/core/src/md.js) and `display: markdown` (CONTRACT §16).
import test from 'node:test';
import assert from 'node:assert/strict';
import { markdown } from '../../packages/core/src/md.js';
import { valueHtml } from '../../packages/core/src/format.js';

test('headings, lists, code, fenced blocks and pipe tables', () => {
  const html = markdown('# Title\n\nSome **bold** and `code`.\n\n- a\n- b\n\n```bash\nuv run x < y\n```\n\n| path | what |\n|---|---|\n| `a.json` | the split |\n');
  assert.match(html, /<h2>Title<\/h2>/);
  assert.match(html, /<strong>bold<\/strong>/);
  assert.match(html, /<ul><li>a<\/li><li>b<\/li><\/ul>/);
  assert.match(html, /<pre><code>uv run x &lt; y<\/code><\/pre>/);
  assert.match(html, /<table><thead><tr><th>path<\/th><th>what<\/th><\/tr><\/thead><tbody><tr><td><code>a.json<\/code><\/td><td>the split<\/td><\/tr><\/tbody><\/table>/);
});

test('markup in the text is escaped, and a javascript: link goes nowhere', () => {
  const html = markdown('<script>x</script> [go](javascript:alert(1))');
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('javascript:'));
});

test('a property with display: markdown renders as a block; other text stays text', () => {
  assert.match(valueHtml('## Hi\ntext', { display: 'markdown' }), /^<div class="dv-md"><h3>Hi<\/h3>/);
  assert.ok(!valueHtml('## Hi', {}).includes('<h3>'));
});
