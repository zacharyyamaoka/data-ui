#!/usr/bin/env python3
"""SYNTHETIC rows for the data-ui speed bench. Stdlib only, seeded, deterministic.
Usage: python3 generate.py --rows N --out DIR [--seed S] [--source actuators.json]

Writes DIR/large.json: N rows bootstrapped from robotparts' real actuators (../robotparts-actuators/actuators.json),
each numeric field jittered by up to +-10 % with a seeded RNG, with a unique id and a name "<name> #<k>". Peak torque
and mass stay rich cells {value, unit, basis, source} so the rich-cell path is exercised on every row. Nothing here is
a measurement: do not read an actuator's spec from this file.
"""
import argparse
import json
import pathlib
import random

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE.parent / "robotparts-actuators" / "actuators.json"
JITTER = 0.10
NUMERIC = ["rated_torque", "max_speed", "gear_ratio", "voltage", "od", "length", "price"]
RICH = {"peak_torque": "N·m", "mass": "g"}
DROPPED = {"photo", "step_up"}  # they name files the synthetic case does not carry


def jitter(rng: random.Random, value, places: int):
    if value is None:
        return None
    return round(value * rng.uniform(1 - JITTER, 1 + JITTER), places)


def synth_row(rng: random.Random, source_row: dict, k: int) -> dict:
    row = {key: value for key, value in source_row.items() if key not in DROPPED}
    row["id"] = f"{source_row['id']}-{k}"
    row["name"] = f"{source_row['name']} #{k}"
    row["model"] = f"{source_row['model']} #{k}"
    row["url"] = None
    for key, unit in RICH.items():
        cell = source_row.get(key)
        value = cell["value"] if isinstance(cell, dict) else cell
        basis = cell.get("basis", "seller") if isinstance(cell, dict) else "seller"
        source = cell.get("source") if isinstance(cell, dict) else None
        row[key] = None if value is None else {"value": jitter(rng, value, 3), "unit": unit, "basis": basis,
                                                "source": source}
    for key in NUMERIC:
        row[key] = jitter(rng, source_row.get(key), 2 if key == "price" else 3)
    peak, mass = row["peak_torque"], row["mass"]
    row["torque_density"] = round(peak["value"] / (mass["value"] / 1000), 3) if peak and mass and mass["value"] else None
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--seed", type=int, default=20261026)
    parser.add_argument("--source", type=pathlib.Path, default=SOURCE)
    args = parser.parse_args()
    source = json.loads(args.source.read_text())
    rng = random.Random(args.seed)
    rows = [synth_row(rng, rng.choice(source["rows"]), k) for k in range(1, args.rows + 1)]
    properties = {key: value for key, value in source["properties"].items() if key not in DROPPED}
    data = {"id": "large", "title": "Actuators (synthetic)", "titleProperty": "name", "linkProperty": "url",
            "source": f"SYNTHETIC: {args.rows} rows bootstrapped from {args.source.name} with seed {args.seed}, "
                      f"numerics jittered +-{int(JITTER * 100)} %",
            "properties": properties, "rows": rows}
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / "large.json"
    target.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{args.rows} rows -> {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
