# sim2real: move to `data-ui vendor`

**What changes:** the hand-run `git archive | tar` recipe in `vendor/data-ui/VENDOR.md` goes away. One command replaces it and
`VENDOR.json` replaces the recipe. Same files, same folder.

```
node ~/data-ui/bin/data-ui.mjs vendor main --into ~/sim2real/vendor/data-ui --kit-dir dist --also gallery/robotics/CONTRACT.md --also gallery/robotics/schemas --also gallery/robotics/fixture.py --also gallery/robotics/fixtures/difference --also gallery/examples/sim-to-real/samples.json=gallery/sim-to-real/samples.json --also gallery/examples/sim-to-real/media.json=gallery/sim-to-real/media.json --also gallery/examples/sim-to-real/media=gallery/sim-to-real/media --also gallery/examples/sim-to-real/motors.json=gallery/sim-to-real/motors.json --also gallery/examples/sim-to-real/README.md=gallery/sim-to-real/README.md --also gallery/examples/pid-tuning/media/ur5e_links.glb=gallery/pid-tuning/media/ur5e_links.glb
```

Keep that line as `tools/vendor_kit.sh` in sim2real. `--kit-dir dist` keeps your `vendor/data-ui/dist/` layout, and each `--also`
copies from the same commit, so the schemas, the fixture and the kit can't drift apart. Pass a version (`1.2.0`, once tagged), a
branch or a commit where `main` is. After 1.0, pin a version.

**Measured on d5ede93:** the same 129 files as your copy, with `VENDOR.json` in place of `VENDOR.md`. Chunk file names change
once: a build through a `node_modules` symlink put the temporary folder's depth into esbuild's hashes, so the same commit gave
different bytes. Now the bytes are the commit's.

**What to edit, in one commit:**

1. The command replaces the whole folder, so `VENDOR.md` goes with it. Move its notes ("What changed since a0b229b") to `docs/`.
2. `.gitignore` line 8: `!vendor/data-ui/VENDOR.md` becomes `!vendor/data-ui/VENDOR.json`, so the pin stays tracked while the kit
   does not.
3. `site/adapter.py` `repin()` reads `VENDOR.md`'s `**Source:**` line: read `VENDOR.json`'s `ref`, `commit` and `subject` instead,
   and the comment at line 47 and the `what` text name it.
4. `python3 site/build.py --repin`, so `site/DATA_UI.json` pins the new manifest.
5. `README.md`, `dashboards/build.py` and `app/tests/test_trajectory_contract.py` keep their `vendor/data-ui/...` paths: none of
   them move.

**Then prove it:**

```
uv run --no-project --with playwright python ~/sim2real/app/tests/test_app_flow.py
```

It refuses to overwrite a folder that isn't a vendored kit, and a failed run leaves the old copy.
