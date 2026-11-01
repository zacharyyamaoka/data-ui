# SYNTHETIC large actuator table (1k / 10k / 100k rows, rich cells)

**SYNTHETIC.** Nothing in this scenario's data is a measurement. `generate.py` bootstraps robotparts' real actuator rows
(`../robotparts-actuators/actuators.json`), jitters every numeric field by up to +-10 % with a seeded RNG, and gives each
row a unique id and name (`<name> #<k>`). Peak torque and mass stay rich cells `{value, unit, basis, source}` on every row, so the rich-cell
path is exercised at scale; the other columns are plain numbers. It exercises the table, a grouped table, a pivot and a scatter
at 1k, 10k and 100k rows. The generated file is not stored (about 0.5, 5 and 51 MB); never commit it.

```
python3 generate.py --rows 10000 --out DIR
```

writes `DIR/large.json`; copy `views.base` next to it (its `data:` is `large.json`). Same seed and row count give a byte-identical file.

## Provenance

- **From:** generate.py: real rows from bench/scenarios/robotparts-actuators/actuators.json (~/data-ui/gallery/examples/robotparts-actuators/actuators.json @ main 0dbc3d4), bootstrapped and jittered +-10% with seed 20261026
- **sha256:** `ab517f5788d67d114180a8be4833d31b2a578d2743a3e319caee872a63caa97b` (the 1,000-row output at the default seed)
- **Note:** SYNTHETIC, not stored: sha256 is of `python3 generate.py --rows 1000 --out DIR` (default seed); regenerate per variant, never commit the output.
