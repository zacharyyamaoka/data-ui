"""Write a self-hosted PMTiles basemap extract for the map gallery cases: the Protomaps OpenStreetMap basemap
(vector tiles, schema v4) cut to a bounding box and zoom range, read tile by tile over HTTP range requests from a
Protomaps daily planet build. No binary is downloaded and nothing but the asked tiles is fetched.

    python3 -m venv /tmp/pmvenv && /tmp/pmvenv/bin/pip install pmtiles==3.4.1
    /tmp/pmvenv/bin/python packages/views/map/assets/build_basemap.py OUT.pmtiles [--build 20261028] \
        [--bbox -123.35,48.98,-122.2,49.45] [--maxzoom 12] [--wide -139.1,48.2,-114,60.1:8]

`--wide W,S,E,N:Z` adds a second, wider box drawn only up to zoom Z (British Columbia at low zoom), so a view that
frames the province still has coastlines and borders. STOCK PARTS: Protomaps' own `pmtiles` reader and writer
(BSD-3-Clause); the tiles are OpenStreetMap data (ODbL): attribution "Protomaps © OpenStreetMap".
"""

import argparse
import gzip
import json
import math
import sys
import urllib.request

from pmtiles.reader import Reader
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer


def tiles_in(bbox, z):
    w, s, e, n = bbox
    def tx(lng): return int((lng + 180) / 360 * 2 ** z)
    def ty(lat):
        r = math.radians(lat)
        return int((1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * 2 ** z)
    for x in range(tx(w), min(tx(e), 2 ** z - 1) + 1):
        for y in range(ty(n), min(ty(s), 2 ** z - 1) + 1):
            yield z, x, y


def http_source(url):
    def get_bytes(offset, length):
        req = urllib.request.Request(url, headers={"Range": f"bytes={offset}-{offset + length - 1}", "User-Agent": "data-ui basemap extract"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    return get_bytes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--build", default="20261028")
    ap.add_argument("--bbox", default="-123.35,48.98,-122.2,49.45")
    ap.add_argument("--maxzoom", type=int, default=12)
    ap.add_argument("--wide", default="-139.1,48.2,-114.0,60.1:7")
    ap.add_argument("--dry", action="store_true", help="count tiles and bytes per zoom, write nothing")
    a = ap.parse_args()
    url = f"https://build.protomaps.com/{a.build}.pmtiles"
    reader = Reader(http_source(url))
    header, meta = reader.header(), reader.metadata()
    bbox = [float(v) for v in a.bbox.split(",")]
    wide_box, wide_z = a.wide.split(":")
    wide = [float(v) for v in wide_box.split(",")]
    want = set()
    for z in range(0, a.maxzoom + 1):
        want.update(tiles_in(bbox, z))
        if z <= int(wide_z):
            want.update(tiles_in(wide, z))
    want = sorted(want, key=lambda t: zxy_to_tileid(*t))
    sizes = {}
    got = []
    for z, x, y in want:
        data = reader.get(z, x, y)
        if data is None:
            continue
        sizes.setdefault(z, [0, 0])
        sizes[z][0] += 1
        sizes[z][1] += len(data)
        if not a.dry:
            got.append((zxy_to_tileid(z, x, y), data))
    for z, (n, b) in sorted(sizes.items()):
        print(f"z{z}: {n} tiles, {b / 1024:.0f} KB", file=sys.stderr)
    print(f"total {sum(b for _, b in sizes.values()) / 1024 / 1024:.2f} MB", file=sys.stderr)
    if a.dry:
        return
    with open(a.out, "wb") as f:
        w = Writer(f)
        for tid, data in got:
            w.write_tile(tid, data)
        w_bounds = [min(bbox[0], wide[0]), min(bbox[1], wide[1]), max(bbox[2], wide[2]), max(bbox[3], wide[3])]
        out_header = {
            "tile_type": TileType.MVT, "tile_compression": header["tile_compression"],
            "min_zoom": 0, "max_zoom": a.maxzoom,
            "min_lon_e7": int(w_bounds[0] * 1e7), "min_lat_e7": int(w_bounds[1] * 1e7),
            "max_lon_e7": int(w_bounds[2] * 1e7), "max_lat_e7": int(w_bounds[3] * 1e7),
            "center_zoom": 10, "center_lon_e7": int((bbox[0] + bbox[2]) / 2 * 1e7), "center_lat_e7": int((bbox[1] + bbox[3]) / 2 * 1e7),
        }
        out_meta = {k: meta[k] for k in ("vector_layers", "attribution", "version", "planetiler:osm:osmosisreplicationtime") if k in meta}
        out_meta["name"] = "data-ui map cases basemap extract"
        out_meta["description"] = f"Protomaps basemap build {a.build}, bbox {a.bbox} to z{a.maxzoom}, {a.wide} to z{wide_z}"
        out_meta["attribution"] = '<a href="https://protomaps.com">Protomaps</a> © <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>'
        w.finalize(out_header, out_meta)
    print(f"wrote {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
