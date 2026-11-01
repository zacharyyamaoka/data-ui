#!/usr/bin/env node
// data-ui's command line:
//   data-ui check FILE.base|FILE.md [...] [--data DATA.json] [--root DIR] [--embeds DIR] [--quiet] [--json]
//   data-ui vendor <version|ref> --into <path> [--views a,b] [--without-views a,b] [--without x,y] [--also SRC[=DEST]] ...
// check reads each .base file with the grammar the page runs (packages/core/src/check.js); without --data it reads the
// file's own `data:` key. A .md file is an analysis (docs/peps/0007-analyses.md): its frontmatter, and every ```base fence
// and ![[x.base]] embed against the data each names (packages/analysis/src/check.js). Exit status 1 on any error; warnings
// never fail. vendor builds one commit from a clean archive and copies the kit into an app (tools/vendor.mjs).
const [command, ...rest] = process.argv.slice(2);
if (command === 'check') {
  const { main } = await import('../packages/analysis/src/check.js');
  process.exitCode = main(rest);
} else if (command === 'vendor') {
  const { main } = await import('../tools/vendor.mjs');
  process.exitCode = main(rest);
} else {
  console.log('usage: data-ui check FILE.base|FILE.md [...] [--data DATA.json] [--root DIR] [--embeds DIR] [--quiet] [--json]\n       data-ui vendor <version|ref> --into <path> [--views a,b] [--without-views a,b] [--without x,y] [--kit-dir d] [--also SRC[=DEST]] [--keep-maps] [--node-modules DIR] [--install] [--repo DIR]');
  process.exitCode = command ? 2 : 0;
}
