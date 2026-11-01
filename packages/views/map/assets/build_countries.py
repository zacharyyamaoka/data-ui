"""Write countries-110m.json, the map view's basemap, from Natural Earth 1:110m admin-0 countries (public domain).

    python3 packages/views/map/assets/build_countries.py [SOURCE.geojson]

SOURCE is ne_110m_admin_0_countries.geojson from natural-earth-vector v5.1.2 (default: the copy vibetracks-storybook
cached on 2026-10-10 from cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@v5.1.2/geojson/). Kept per country: its
name, ISO 3166-1 alpha-2 code (ISO_A2_EH, which fills France's and Norway's -99) and label point; coordinates are
rounded to 2 decimals (about 1 km, finer than 1:110m's own detail). Nothing is fetched at build or run time.
"""

import json
import pathlib
import sys

SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "~/vibetracks-storybook/storybook/.geo-cache/ne_110m_admin_0_countries.geojson")
OUT = pathlib.Path(__file__).resolve().parent / "countries-110m.json"


def rounded(coords):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], 2), round(coords[1], 2)]
    return [rounded(c) for c in coords]


def main() -> None:
    src = json.loads(SRC.read_text())
    features = []
    for f in src["features"]:
        p = f["properties"]
        features.append({"type": "Feature", "properties": {"name": p["NAME"], "iso": p["ISO_A2_EH"], "label": [round(p["LABEL_X"], 3), round(p["LABEL_Y"], 3)]},
                         "geometry": {"type": f["geometry"]["type"], "coordinates": rounded(f["geometry"]["coordinates"])}})
    out = {"type": "FeatureCollection", "source": "Natural Earth 1:110m admin-0 countries, v5.1.2 (public domain), naturalearthdata.com", "features": features}
    OUT.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"wrote {OUT}: {len(features)} countries, {OUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
