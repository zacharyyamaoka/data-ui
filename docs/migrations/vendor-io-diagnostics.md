# RobotDx (io-diagnostics): move to `data-ui vendor`

**What changes:** `tools/vendor_data_ui.py` goes away. One command from data-ui replaces it. Same files, same folder.

```
node ~/data-ui/bin/data-ui.mjs vendor main --into ~/io-diagnostics/io_diagnostics/web/vendor/data-ui --views table,list,cards,kpi,live,playback,record,chart,media --without python/,analysis.js,sources.js,views/mesh.js
```

`--views` is your `DEFAULT_VIEWS` (a view's split chunks come with it). `--without` keeps the core to your `CORE_FILES`. Drop
`--views` for the old `--views all`. Pass a version (`1.2.0`, once tagged), a branch or a commit where `main` is; `--ref REF` and
the tree argument both become this one word, and it always builds from a clean archive, so there is no `--build`. After 1.0,
pin a version.

**Measured on d5ede93:** the same 21 files as your copy, with `VENDOR.json` in place of `VERSION`. Chunk file names change once:
a build through a `node_modules` symlink put the temporary folder's depth into esbuild's hashes, so the same commit gave
different bytes. Now the bytes are the commit's.

**What to edit, in one commit:**

1. Delete `tools/vendor_data_ui.py`.
2. `io_diagnostics/web/dx/app.js` line 822: the Settings page fetches `VERSION` and shows its first lines, and a 404 there fails
   `test_dx_page.js` ("no failed request"). Fetch `../vendor/data-ui/VENDOR.json` and show its `version`, `ref`, `commit` and `subject`.
3. `io_diagnostics/web/dx/index.html` line 20, `docs/peps/0001-robotdx-on-data-ui.md` line 735, and anything else that names the
   old script (`grep -rn vendor_data_ui`).

`VENDOR.json` holds what `VERSION` held: the ref, the commit, the views, each file's sha256, and for a merge commit each parent
with its subject, plus `on_main`.

**Then prove it:**

```
/usr/bin/node ~/io-diagnostics/tests/test_dx_page.js
```

**One gap this closes:** RobotDx has no test that holds the copy to its pin. Worth adding: every file's sha256 against
`VENDOR.json` (Vibe Tracks' `VendoredCopyTest` is 15 lines), so an edit in place fails.

It refuses to overwrite a folder that isn't a vendored kit, and a failed run leaves the old copy.
