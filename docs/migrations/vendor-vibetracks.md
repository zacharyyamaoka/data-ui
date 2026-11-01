# Vibe Tracks: move to `data-ui vendor`

**What changes:** `tools/vendor_data_ui.py` goes away. One command from data-ui replaces it. Same files, same folder.

```
node ~/data-ui/bin/data-ui.mjs vendor main --into ~/vibetracks/vibetracks/home/static/vendor/data-ui --without-views map
```

Drop `--without-views map` for the old `--with-map`. Pass a version (`1.2.0`, once tagged), a branch or a commit where `main`
is; a lane's ref works, and `on_main` says so. After 1.0, pin a version.

**Measured on d5ede93:** the same 93 files as your copy, and `skipped` still names `views/map.js` and
`views/maplibre-gl-worker.mjs`, so `tests/test_dataui_contract.py` needs no change. Chunk file names change once
(`cards-lightbox-*.js`, `chart-*.js`): the old script built through a `node_modules` symlink, which put the temporary folder's
depth into esbuild's hashes, so the same commit gave different bytes. Now the bytes are the commit's.

**What to edit, in one commit:**

1. Delete `tools/vendor_data_ui.py`.
2. `tests/test_dataui_contract.py` line 68: the re-vendor hint names the new command.
3. `docs/peps/0013-vibetracks-on-data-ui.md` line 99: the same.

**Then prove it:**

```
python3 -m unittest discover -s ~/vibetracks/tests -t ~/vibetracks -p test_dataui_contract.py
```

`node tests/browser/track_kpis_dataui.mjs` needs `VT_PLAYWRIGHT` set: with no Playwright it prints SKIP and exits 0, which
reads like a pass.

**What `VENDOR.json` adds:** `version`, `views`, `kit_dir`, and `files` is now a map of every file to its sha256. Your other
keys keep their meaning. It refuses to overwrite a folder that isn't a vendored kit, and a failed run leaves the old copy.
