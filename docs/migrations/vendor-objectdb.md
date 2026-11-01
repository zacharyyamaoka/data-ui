# ObjectDB: move to `data-ui vendor`

**What changes:** `tools/vendor_data_ui.py` goes away, and `site/build.py --repin` calls data-ui's command. Same files, same
folder, and `VENDOR.json` keeps the shape `ensure_kit` reads.

```
node ~/data-ui/bin/data-ui.mjs vendor main --into ~/object-database/vendor/data-ui --without python/
```

`--without python/` keeps your rule: the build reads `.base` files with robotparts' pinned copy. Pass a version (`1.2.0`, once
tagged), a branch or a commit where `main` is. After 1.0, pin a version.

**Measured on d5ede93:** every file of your copy, plus what data-ui added since your pin 56e08be (`dashboard-arrange.js`,
`views/live.js`, `views/media.js`, `views/playback.js`, `views/scene3d.js`, the chart's chunks). Chunk file names change once: a
build through a `node_modules` symlink put the temporary folder's depth into esbuild's hashes, so the same commit gave different
bytes. Now the bytes are the commit's.

**What to edit, in one commit:**

1. Delete `tools/vendor_data_ui.py`.
2. `site/build.py` `repin(ref)`: run the command above with `subprocess.run(["node", "~/data-ui/bin/data-ui.mjs", "vendor", ref, "--into", str(KIT), "--without", "python/"], check=True)`, then return `json.loads((KIT / "VENDOR.json").read_text())`.
3. The comments at `site/build.py` lines 40 and 83, and the docstring of `tests/test_vendor_data_ui.py`, name the new command.

**Then prove it:**

```
uv run --project ~/object-database --extra build --extra test pytest -q tests/test_vendor_data_ui.py
```

`ensure_kit` and that test need no change: `files` is still every file to its sha256, `manifest.json` included. `VENDOR.json`
adds `ref`, `version`, `on_main`, `views` and `kit_dir`.

It refuses to overwrite a folder that isn't a vendored kit, and a failed run leaves the old copy.
