// Build disposal.json and districts.geojson: BC municipal solid waste disposal by regional district, every year the
// province publishes, joined to simplified district polygons by a shared `rd` key.
//
//   node gallery/examples/map-bc-disposal/source/build.mjs [RAW_DIR]
//
// RAW_DIR (argument, else $RAW_DIR, else ./raw) holds the three downloads named in SOURCES.md, each in its own folder:
//   bc-msw/bc_municipal_solid_waste_disposal.csv        (BC Data Catalogue)
//   bc-rd/regional_districts.geojson                     (openmaps WFS, ABMS_REGIONAL_DISTRICTS_SP)
//   bc-northern-rockies/northern_rockies.geojson         (openmaps WFS, ABMS_MUNICIPALITIES_SP, one feature)
// A year published as 0 t is a missing report, never zero waste: it becomes null with a reason.
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as turf from '@turf/turf';

const RAW = process.argv[2] || process.env.RAW_DIR || 'raw';
const HERE = join(dirname(fileURLToPath(import.meta.url)), '..');
const TOLERANCE = 0.003; // degrees, @turf/simplify highQuality (Douglas-Peucker without radial pre-pass)

// CSV name -> the WFS feature name(s) whose union is that reporting unit.
const UNITS = {
  'Alberni-Clayoquot': ['Regional District of Alberni-Clayoquot'],
  'Bulkley-Nechako': ['Regional District of Bulkley-Nechako'],
  Capital: ['Capital Regional District'],
  Cariboo: ['Cariboo Regional District'],
  'Central Coast': ['Central Coast Regional District'],
  'Central Kootenay': ['Regional District of Central Kootenay'],
  'Central Okanagan': ['Regional District of Central Okanagan'],
  'Columbia-Shuswap': ['Columbia Shuswap Regional District'],
  'Comox-Strathcona': ['Comox Valley Regional District', 'Strathcona Regional District'],
  'Cowichan Valley': ['Cowichan Valley Regional District'],
  'East Kootenay': ['Regional District of East Kootenay'],
  'Fraser-Fort George': ['Regional District of Fraser-Fort George'],
  'Fraser Valley': ['Fraser Valley Regional District'],
  'Kitimat-Stikine': ['Regional District of Kitimat-Stikine'],
  'Kootenay Boundary': ['Regional District of Kootenay Boundary'],
  'Metro-Vancouver': ['Metro Vancouver Regional District'],
  'Mount Waddington': ['Regional District of Mount Waddington'],
  Nanaimo: ['Regional District of Nanaimo'],
  'North Coast': ['North Coast Regional District'],
  'North Okanagan': ['Regional District of North Okanagan'],
  'Northern Rockies': ['Northern Rockies Regional Municipality'],
  'Okanagan-Similkameen': ['Regional District of Okanagan-Similkameen'],
  'Peace River': ['Peace River Regional District'],
  qathet: ['qathet Regional District'],
  'Squamish-Lillooet': ['Squamish-Lillooet Regional District'],
  'Sunshine Coast': ['Sunshine Coast Regional District'],
  'Thompson-Nicola': ['Thompson-Nicola Regional District'],
};
// Polygons with no disposal rows, kept so the map covers the whole province.
const NO_ROWS = { 'Stikine Region (Unincorporated)': ['stikine', 'Stikine Region (unincorporated, no regional district)'] };
const DISPLAY = { 'Metro-Vancouver': 'Metro Vancouver' };

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const r4 = (x) => Math.round(x * 1e4) / 1e4;
const r5 = (x) => Math.round(x * 1e5) / 1e5;
const roundCoords = (c) => (typeof c[0] === 'number' ? [r4(c[0]), r4(c[1])] : c.map(roundCoords));

function csv(text) {
  const [head, ...lines] = text.trim().split(/\r?\n/);
  const keys = head.split(',');
  return lines.map((l) => Object.fromEntries(l.split(',').map((v, i) => [keys[i], v])));
}

const wfs = JSON.parse(readFileSync(join(RAW, 'bc-rd/regional_districts.geojson'), 'utf8')).features;
const rockies = JSON.parse(readFileSync(join(RAW, 'bc-northern-rockies/northern_rockies.geojson'), 'utf8')).features;
const byName = new Map([...wfs, ...rockies].map((f) => [f.properties.ADMIN_AREA_NAME, f]));

function shape(names) {
  const parts = names.map((n) => {
    const f = byName.get(n);
    if (!f) throw new Error(`no polygon named ${n}`);
    return turf.feature(f.geometry);
  });
  const merged = parts.length > 1 ? turf.union(turf.featureCollection(parts)) : parts[0];
  return turf.simplify(merged, { tolerance: TOLERANCE, highQuality: true });
}

const features = [];
const labels = {};
for (const [unit, names] of Object.entries(UNITS)) {
  const rd = slug(unit);
  const g = shape(names);
  const p = turf.pointOnFeature(g).geometry.coordinates;
  labels[unit] = [r5(p[1]), r5(p[0])];
  features.push({ type: 'Feature', properties: { rd, name: DISPLAY[unit] || unit }, geometry: { type: g.geometry.type, coordinates: roundCoords(g.geometry.coordinates) } });
}
for (const [wfsName, [rd, name]] of Object.entries(NO_ROWS)) {
  const g = shape([wfsName]);
  features.push({ type: 'Feature', properties: { rd, name }, geometry: { type: g.geometry.type, coordinates: roundCoords(g.geometry.coordinates) } });
}
for (const n of byName.keys()) {
  if (!Object.values(UNITS).flat().includes(n) && !NO_ROWS[n]) throw new Error(`unmapped polygon ${n}`);
}

const missing = (why) => ({ value: null, why });
const rows = [];
for (const r of csv(readFileSync(join(RAW, 'bc-msw/bc_municipal_solid_waste_disposal.csv'), 'utf8'))) {
  const unit = r.Regional_District;
  if (!UNITS[unit]) throw new Error(`no polygon mapping for ${unit}`);
  const t = Number(r.Total_Disposed_Tonnes);
  const reported = r.Total_Disposed_Tonnes !== '' && t > 0;
  rows.push({
    id: `${slug(unit)}-${r.Year}`,
    rd: slug(unit),
    district: DISPLAY[unit] || unit,
    year: Number(r.Year),
    population: r.Population === '' ? missing('not published for this year') : Number(r.Population),
    disposal_t: reported ? t : missing('not reported (the province publishes 0 t for a missing report)'),
    kg_per_capita: reported && r.Disposal_Rate_kg !== '' && Number(r.Disposal_Rate_kg) > 0 ? Number(r.Disposal_Rate_kg) : missing('no disposal reported for this year'),
    location: labels[unit],
  });
}

const doc = {
  id: 'bc-msw-disposal',
  title: 'BC municipal solid waste disposal by regional district, 1990–2024',
  titleProperty: 'district',
  source: 'BC Ministry of Environment and Parks, Municipal Solid Waste Disposal Rates (BC Data Catalogue), Open Government Licence – British Columbia',
  properties: {
    district: { type: 'text', label: 'Regional district' },
    rd: { type: 'text', label: 'District key' },
    year: { type: 'number', label: 'Year', decimals: 0 },
    population: { type: 'number', label: 'Population', unitText: 'persons', decimals: 0 },
    disposal_t: { type: 'number', label: 'Disposed', unitText: 't', decimals: 0 },
    kg_per_capita: { type: 'number', label: 'Disposal rate', unitText: 'kg/person/yr', decimals: 0 },
    location: { type: 'list', label: 'Label point (lat, lng)' },
  },
  rows,
};
writeFileSync(join(HERE, 'disposal.json'), JSON.stringify(doc, null, 1) + '\n');
writeFileSync(join(HERE, 'districts.geojson'), JSON.stringify({ type: 'FeatureCollection', features }) + '\n');
console.log(`disposal.json: ${rows.length} rows, ${rows.filter((r) => r.disposal_t?.value === null).length} with no disposal reported; districts.geojson: ${features.length} features`);
