// The map cases' data on a public repo (docs/MAP-DATA.md): every data file is accounted for, every file with OpenStreetMap in
// it carries the credit the map draws, and every case says who its data is from. WHY a test: the credit is a condition of the
// licences, and a new case that reads OSM rows on the bundled countries showed no OSM credit at all until 2026-10-30.
// The browser half, the credit on the map itself, is tests/browser/map_credit_checks.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gunzipSync } from 'node:zlib';
import { parseBase } from '../../packages/core/src/base.js';
import { normalizeDataset } from '../../packages/core/src/data.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const GALLERY = join(ROOT, 'gallery', 'examples');
const NOTE = readFileSync(join(ROOT, 'docs', 'MAP-DATA.md'), 'utf8');
const CASES = readdirSync(GALLERY).filter((d) => d.startsWith('map-')).sort();
const OSM_TEXT = '© OpenStreetMap contributors';
const OSM_URL = 'https://www.openstreetmap.org/copyright';

const readme = (name) => readFileSync(join(GALLERY, name, 'README.md'), 'utf8');
const baseOf = (name) => parseBase(readFileSync(join(GALLERY, name, 'views.base'), 'utf8'));
/** Every data file a case reads, as paths from gallery/examples. */
function dataFiles(name) {
  const base = baseOf(name);
  const files = [base.data, ...Object.values(base.datasets || {}).map((d) => (typeof d === 'string' ? d : d && d.data))].filter(Boolean);
  return [...new Set(files.map((f) => relative(GALLERY, join(GALLERY, name, f))))];
}
const json = (path) => JSON.parse(readFileSync(join(GALLERY, path), 'utf8'));

test('the 20 map cases are the ones the note covers', () => {
  assert.equal(CASES.length, 20);
});

test('every data file in a map case is listed in docs/MAP-DATA.md, by name', () => {
  const files = [];
  for (const name of CASES) for (const f of readdirSync(join(GALLERY, name))) {
    if (statSync(join(GALLERY, name, f)).isFile() && /\.(json|geojson|pmtiles)$/.test(f)) files.push(`${name}/${f}`);
  }
  assert.ok(files.length >= 17, `${files.length} files`);
  for (const f of files) assert.ok(NOTE.includes(f) || NOTE.includes(f.split('/')[1]), `${f} is not in docs/MAP-DATA.md`);
});

test('a data file with OpenStreetMap in it says so where the map can read it', () => {
  const seen = new Set();
  for (const name of CASES) for (const f of dataFiles(name)) {
    if (seen.has(f)) continue;
    seen.add(f);
    const doc = json(f);
    const says = /OpenStreetMap|\bOSM\b/.test(`${doc.source ?? ''} ${doc.title ?? ''}`);
    if (says) assert.deepEqual(doc.attribution, { text: OSM_TEXT, url: OSM_URL }, `${f} holds OSM data and no attribution`);
    else assert.equal(doc.attribution, undefined, `${f} credits OSM and does not say it holds OSM data`);
  }
  // the oracle's reach: the files the note lists as ODbL are the ones found here
  for (const f of ['map-food-heatmap/food.json', 'map-recycling-clusters/recycling.json', 'map-catchments/sites.json', 'map-collection-routes/day.json', 'map-waste-flows/flows.json', 'map-annotations/facts.json']) {
    assert.ok(seen.has(f), `${f} is read by a case`);
    assert.ok(json(f).attribution, `${f}`);
  }
});

test('a case whose README names OpenStreetMap reads a file that carries the credit, or draws the tiles that do', () => {
  for (const name of CASES) {
    if (!/\*\*Data:\*\*[^\n]*(OpenStreetMap|OSM)/.test(readme(name))) continue;
    const credited = dataFiles(name).some((f) => json(f).attribution);
    assert.ok(credited, `${name}'s README names OSM and no data file it reads carries the credit`);
  }
});

test('each licence\'s own words are on the cases it covers', () => {
  const need = {
    'Contains information licensed under the Open Government Licence – British Columbia': (name) => dataFiles(name).includes('map-bc-disposal/disposal.json'),
    'Contains information licensed under the Open Government Licence – Canada': (name) => dataFiles(name).includes('map-bivariate/provinces.json'),
    'This does not constitute an endorsement by Statistics Canada of this product': (name) => dataFiles(name).includes('map-bivariate/provinces.json'),
    'ODbL': (name) => dataFiles(name).some((f) => json(f).attribution),
  };
  for (const [words, applies] of Object.entries(need)) {
    const cases = CASES.filter(applies);
    assert.ok(cases.length, words);
    for (const name of cases) assert.ok(readme(name).includes(words), `${name}'s README lacks: ${words}`);
    assert.ok(NOTE.includes(words), `docs/MAP-DATA.md lacks: ${words}`);
  }
});

test('Statistics Canada data is under its own licence, not the OGL', () => {
  const doc = json('map-bivariate/provinces.json');
  assert.match(doc.source, /Statistics Canada Open Licence/);
  assert.doesNotMatch(doc.source, /Statistics Canada[^;]*Open Government Licence/);
  const sources = readFileSync(join(GALLERY, 'map-bivariate', 'source', 'SOURCES.md'), 'utf8');
  assert.match(sources, /Statistics Canada Open Licence/);
});

test('the glyphs ship with their licence, and the extract says whose data it holds', () => {
  const assets = join(ROOT, 'packages', 'views', 'map', 'assets', 'glyphs');
  assert.match(readFileSync(join(assets, 'OFL.txt'), 'utf8'), /SIL OPEN FONT LICENSE Version 1\.1/);
  assert.doesNotMatch(readFileSync(join(assets, 'OFL.txt'), 'utf8').split('\n')[0], /Reserved Font Name/, 'no reserved name to rename around');
  const manifest = JSON.parse(readFileSync(join(ROOT, 'packages', 'views', 'map', 'manifest.json'), 'utf8'));
  assert.ok(manifest.assets.some((a) => a.to === 'map-glyphs/OFL.txt'), 'the licence is copied beside the glyphs');
  // PMTiles v3: the header holds the metadata's offset and length (bytes 24 and 32), gzipped when byte 97 says 2
  const pm = readFileSync(join(GALLERY, 'map-food-heatmap', 'metro-vancouver.pmtiles'));
  const at = Number(pm.readBigUInt64LE(24)), length = Number(pm.readBigUInt64LE(32));
  assert.equal(pm[97], 2, 'gzip');
  const meta = JSON.parse(gunzipSync(pm.subarray(at, at + length)).toString());
  assert.match(meta.attribution, /OpenStreetMap/);
  assert.ok(meta.vector_layers.some((l) => l.id === 'landcover'), 'the premise of the note\'s ESA WorldCover row');
  assert.match(NOTE, /ESA WorldCover/, 'the extract carries a landcover layer: its credit is in the note');
});

test('a data file\'s attribution survives every shape a data file takes', () => {
  const attribution = { text: 'Some credit', url: 'https://example.org' };
  const rows = [{ id: 'a', x: 1 }];
  assert.deepEqual(normalizeDataset({ attribution, properties: { x: { type: 'number' } }, rows }).attribution, attribution);
  assert.deepEqual(normalizeDataset({ attribution, rows }).attribution, attribution);
  assert.deepEqual(normalizeDataset({ attribution, schema: { fields: [{ name: 'x', type: 'number' }] }, rows }).attribution, attribution);
});
