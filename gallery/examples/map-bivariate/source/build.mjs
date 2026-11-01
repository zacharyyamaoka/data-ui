// Build provinces.json and provinces.geojson: solid-waste diversion (2002, 2022), disposal and disposal per person by
// province and territory, joined to Natural Earth 1:50m polygons by the 2-letter postal `code`.
//
//   node gallery/examples/map-bivariate/source/build.mjs [RAW_DIR]
//
// RAW_DIR (argument, else $RAW_DIR, else ./raw) holds, each in its own folder:
//   cesi/figure-5-en.csv                                  (ECCC CESI, solid waste diversion figure 5)
//   statcan-disposal/38100032-eng.zip                     (Statistics Canada 38-10-0032-01, full table CSV)
//   statcan-pop/17100009-eng.zip                          (Statistics Canada 17-10-0009-01, full table CSV)
//   ne-admin1/ne_50m_admin_1_states_provinces.geojson     (Natural Earth v5.1.2 via jsDelivr)
// The zips are read with `unzip -p` (no npm dependency for zip).
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as turf from '@turf/turf';

const RAW = process.argv[2] || process.env.RAW_DIR || 'raw';
const HERE = join(dirname(fileURLToPath(import.meta.url)), '..');
const TOLERANCE = 0.02; // degrees, @turf/simplify highQuality

// postal code -> [name, StatCan GEO, CESI jurisdiction]. The territories share one StatCan disposal row and one CESI row.
const P = {
  NL: ['Newfoundland and Labrador', 'Newfoundland and Labrador', 'Newfoundland and Labrador'],
  PE: ['Prince Edward Island', 'Prince Edward Island', 'Prince Edward Island [A]'],
  NS: ['Nova Scotia', 'Nova Scotia', 'Nova Scotia'],
  NB: ['New Brunswick', 'New Brunswick', 'New Brunswick'],
  QC: ['Quebec', 'Quebec', 'Quebec'],
  ON: ['Ontario', 'Ontario', 'Ontario'],
  MB: ['Manitoba', 'Manitoba', 'Manitoba'],
  SK: ['Saskatchewan', 'Saskatchewan', 'Saskatchewan'],
  AB: ['Alberta', 'Alberta', 'Alberta'],
  BC: ['British Columbia', 'British Columbia', 'British Columbia'],
  YT: ['Yukon', 'Yukon', 'Yukon, the Northwest Territories and Nunavut [A]'],
  NT: ['Northwest Territories', 'Northwest Territories', 'Yukon, the Northwest Territories and Nunavut [A]'],
  NU: ['Nunavut', 'Nunavut', 'Yukon, the Northwest Territories and Nunavut [A]'],
};
const TERRITORIES = 'Yukon, Northwest Territories and Nunavut';

const r4 = (x) => Math.round(x * 1e4) / 1e4;
const r5 = (x) => Math.round(x * 1e5) / 1e5;
const roundCoords = (c) => (typeof c[0] === 'number' ? [r4(c[0]), r4(c[1])] : c.map(roundCoords));

/** Minimal RFC 4180 CSV: quoted fields with commas and doubled quotes. */
function parseCsv(text) {
  const out = [];
  let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) { if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (ch === '"') q = false; else cell += ch; }
    else if (ch === '"') q = true;
    else if (ch === ',') { row.push(cell); cell = ''; }
    else if (ch === '\n' || ch === '\r') { if (ch === '\r' && text[i + 1] === '\n') i++; row.push(cell); out.push(row); row = []; cell = ''; }
    else cell += ch;
  }
  if (cell || row.length) { row.push(cell); out.push(row); }
  return out;
}
const records = (text) => { const [h, ...rs] = parseCsv(text.replace(/^﻿/, '')); return rs.filter((r) => r.length === h.length).map((r) => Object.fromEntries(h.map((k, i) => [k, r[i]]))); };
const unzip = (zip, member) => execFileSync('unzip', ['-p', zip, member], { encoding: 'utf8', maxBuffer: 1 << 28 });

// Diversion, CESI figure 5: Jurisdiction, 2002 %, 2022 %.
const cesi = new Map(parseCsv(readFileSync(join(RAW, 'cesi/figure-5-en.csv'), 'utf8').replace(/^﻿/, '')).filter((r) => r.length >= 3 && r[0] && r[0] !== 'Jurisdiction').map((r) => [r[0], [r[1], r[2]]]));
const SUPPRESSED = { value: null, why: 'suppressed by Statistics Canada' };
const pct = (v) => (v === undefined ? null : /^(n\/a|x|\.\.)$/i.test(v.trim()) ? SUPPRESSED : Number(v));

// Disposal, all sources, latest year.
const disposal = records(unzip(join(RAW, 'statcan-disposal/38100032-eng.zip'), '38100032.csv')).filter((r) => r['Sources of waste for disposal'] === 'All sources of waste for disposal');
const YEAR = Math.max(...disposal.map((r) => Number(r.REF_DATE)));
const disposed = new Map(disposal.filter((r) => Number(r.REF_DATE) === YEAR).map((r) => [r.GEO, r]));
const pop = new Map(records(unzip(join(RAW, 'statcan-pop/17100009-eng.zip'), '17100009.csv')).filter((r) => r.REF_DATE === `${YEAR}-07-01`).map((r) => [r.GEO, Number(r.VALUE)]));

const ne = JSON.parse(readFileSync(join(RAW, 'ne-admin1/ne_50m_admin_1_states_provinces.geojson'), 'utf8')).features.filter((f) => f.properties.adm0_a3 === 'CAN');
const features = [];
const rows = [];
for (const [code, [name, geo, jurisdiction]] of Object.entries(P)) {
  const f = ne.find((x) => x.properties.postal === code);
  if (!f) throw new Error(`no Natural Earth polygon for ${code}`);
  const g = turf.simplify(turf.feature(f.geometry), { tolerance: TOLERANCE, highQuality: true });
  features.push({ type: 'Feature', properties: { code, name }, geometry: { type: g.geometry.type, coordinates: roundCoords(g.geometry.coordinates) } });

  const [d02, d22] = (cesi.get(jurisdiction) || []).map(pct);
  if (d02 === undefined) throw new Error(`no CESI row for ${jurisdiction}`);
  const both = typeof d02 === 'number' && typeof d22 === 'number';
  const change = both
    ? { value: Math.round((d22 - d02) * 10) / 10, basis: 'derived', note: 'diversion_2022 − diversion_2002, percentage points' }
    : { value: null, why: 'a diversion rate is suppressed in 2002 or 2022' };
  const terr = ['YT', 'NT', 'NU'].includes(code);
  const drow = disposed.get(terr ? TERRITORIES : geo);
  const t = terr
    ? { value: null, why: `Statistics Canada publishes the three territories combined (${TERRITORIES}: ${Number(drow.VALUE).toLocaleString('en-CA')} t in ${YEAR})` }
    : Number(drow.VALUE);
  const persons = pop.get(geo);
  const perCapita = typeof t === 'number'
    ? { value: Math.round((t / persons) * 1000), basis: 'derived', note: `disposal_t / population (July 1, ${YEAR}) × 1000` }
    : { value: null, why: 'no disposal figure for this territory alone' };
  rows.push({
    id: code,
    code,
    province: name,
    diversion_2002: d02,
    diversion_2022: d22,
    change_pts: change,
    disposal_t: t,
    disposal_year: YEAR,
    population: persons,
    kg_per_capita: perCapita,
    location: [r5(f.properties.latitude), r5(f.properties.longitude)],
  });
}

const doc = {
  id: 'canada-diversion',
  title: 'Solid waste diversion and disposal by province and territory, Canada',
  titleProperty: 'province',
  source: 'ECCC CESI solid waste diversion figure 5 (Open Government Licence – Canada); adapted from Statistics Canada tables 38-10-0032-01 and 17-10-0009-01 (Statistics Canada Open Licence; not an endorsement by Statistics Canada); Natural Earth label points',
  properties: {
    province: { type: 'text', label: 'Province or territory' },
    code: { type: 'text', label: 'Code' },
    diversion_2002: { type: 'number', label: 'Diversion 2002', unitText: '%', decimals: 1 },
    diversion_2022: { type: 'number', label: 'Diversion 2022', unitText: '%', decimals: 1 },
    change_pts: { type: 'number', label: 'Change 2002–2022', unitText: 'percentage points', decimals: 1 },
    disposal_t: { type: 'number', label: `Disposed (all sources)`, unitText: 't', decimals: 0 },
    disposal_year: { type: 'number', label: 'Disposal year', decimals: 0 },
    population: { type: 'number', label: 'Population (July 1)', unitText: 'persons', decimals: 0 },
    kg_per_capita: { type: 'number', label: 'Disposed per person', unitText: 'kg/person/yr', decimals: 0 },
    location: { type: 'list', label: 'Label point (lat, lng)' },
  },
  rows,
};
writeFileSync(join(HERE, 'provinces.json'), JSON.stringify(doc, null, 1) + '\n');
writeFileSync(join(HERE, 'provinces.geojson'), JSON.stringify({ type: 'FeatureCollection', features }) + '\n');
console.log(`provinces.json: ${rows.length} rows (disposal year ${YEAR}); provinces.geojson: ${features.length} features`);
