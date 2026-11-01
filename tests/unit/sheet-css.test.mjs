// CONTRACT §40: what Edit adds is prefixed and takes its colours from the tokens, so it follows a host's light and dark themes
// and never leaks into the host's page.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('../../packages/core/styles/sheet.css', import.meta.url), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter((m) => !m[1].trim().startsWith('@')).map((m) => ({ selectors: m[1].split(',').map((s) => s.trim()), body: m[2] }));

test('sheet.css has rules, and every selector is the kit\'s own', () => {
  assert.ok(rules.length > 0);
  for (const r of rules) for (const s of r.selectors) assert.match(s, /\.dv-|^data-views/, `an unprefixed selector: ${s}`);
});

test('sheet.css writes no colour of its own: tokens, transparent and currentColor only', () => {
  for (const r of rules) {
    assert.doesNotMatch(r.body, /#[0-9a-f]{3,8}\b/i, `a hex colour in ${r.selectors[0]}`);
    assert.doesNotMatch(r.body, /\b(rgb|rgba|hsl|hsla|oklch)\(/i, `a literal colour in ${r.selectors[0]}`);
    for (const m of r.body.matchAll(/(?:^|[;\s])(color|background|background-color|border-color|outline-color|fill|stroke)\s*:\s*([^;]+)/g)) {
      assert.match(m[2], /var\(--dv-|transparent|currentColor|none|inherit/, `${m[1]}: ${m[2]} in ${r.selectors[0]}`);
    }
  }
});
