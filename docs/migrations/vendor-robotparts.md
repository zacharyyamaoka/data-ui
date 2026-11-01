# robotparts: move to `data-ui vendor`

**What changes:** `tools/vendor_data_ui.py` goes away. One command from data-ui replaces it. Same files, same folder.

```
node ~/data-ui/bin/data-ui.mjs vendor main --into ~/robotparts/site/static/data-ui
```

Pass a version (`1.2.0`, once tagged), a branch or a commit where `main` is. After 1.0, pin a version.

**Measured on d5ede93:** the same 95 files as your copy, minus Python's `__pycache__`. Chunk file names change once
(`cards-lightbox-*.js`, `chart-*.js`): the old scripts built through a `node_modules` symlink, which put the temporary
folder's depth into esbuild's hashes, so the same commit gave different bytes. Now the bytes are the commit's.

**What to edit, in one commit:**

1. Delete `tools/vendor_data_ui.py`.
2. `tests/site/test_data_ui.py`, `test_every_vendored_file_matches_its_manifest_sha256`: `VENDOR.json`'s `files` is now a
   map of every file to its sha256, `manifest.json` included, not a count. Replace
   `self.assertEqual(self.vendor["files"], len(expected))` with
   `self.assertEqual(sorted(self.vendor["files"]), sorted(expected + ["manifest.json"]))`.
3. Change the mentions of the old script: `build/site_pages.py` lines 1428, 1445, 4905, and the "re-vendor" hint in the test.

**Then prove it:**

```
python3 -m unittest discover -s ~/robotparts/tests/site -t ~/robotparts/tests/site -p test_data_ui.py
```

Run `python3 build/all.py`, then `tests/site/browser_check.py`.

**What `VENDOR.json` adds:** `ref`, `version`, `on_main`, `views`, `kit_dir`. Your `commit`, `manifest_sha256` and `skipped`
keep their meaning. It refuses to overwrite a folder that isn't a vendored kit, and a failed run leaves the old copy.
