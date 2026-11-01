// The round trips over the real rows, as numbers for the report (tests/unit/md-notes.test.mjs asserts the same): node docs/measure_md_pages.mjs > out.json
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseBase } from '../packages/core/src/base.js';
import { buildRows, fitsHeading, layoutOf, moveProperty, readNote, setPage, setValue } from '../tools/md-notes.mjs';

const CASE = join(dirname(fileURLToPath(import.meta.url)), '..', 'gallery', 'md-pages');
const out = {};
for (const name of ['feedback', 'frdparrc']) {
  const dir = join(CASE, name);
  const base = parseBase(readFileSync(join(dir, 'views.base'), 'utf8'));
  const lay = layoutOf(base);
  const notes = readdirSync(dir).filter((f) => f.endsWith('.md')).sort().map((f) => ({ id: f, text: readFileSync(join(dir, f), 'utf8') }));
  const { properties } = buildRows(notes, base);
  const ids = Object.entries(properties).filter(([id, p]) => id !== 'name' && id !== 'page' && fitsHeading(p)).map(([id]) => id);
  const m = { notes: notes.length, bytes: notes.reduce((a, n) => a + Buffer.byteLength(n.text), 0), textProperties: ids, typedProperties: Object.entries(properties).filter(([id, p]) => id !== 'name' && id !== 'page' && !fitsHeading(p)).map(([id]) => id), selfWrites: 0, selfSame: 0, trips: 0, sameBytes: 0, valuesCompared: 0, valuesSame: 0 };
  for (const n of notes) {
    const r = readNote(n.text, lay);
    for (const [id, v] of Object.entries(r.values)) { m.selfWrites++; if (setValue(n.text, id, v, lay) === n.text) m.selfSame++; }
    m.selfWrites++; if (setPage(n.text, r.page, lay) === n.text) m.selfSame++;
    for (const id of ids) {
      const was = lay.places.get(id) || 'top';
      const to = was === 'top' ? 'section' : 'top';
      const label = base.properties[id]?.displayName;
      const there = moveProperty(n.text, id, to, { ...lay, label });
      const read = readNote(there, lay);
      for (const [k, v] of Object.entries(r.values)) { m.valuesCompared++; if (JSON.stringify(v ?? '') === JSON.stringify(read.values[k] ?? '')) m.valuesSame++; }
      m.trips++;
      if (moveProperty(there, id, was, { ...lay, label }) === n.text) m.sameBytes++;
    }
  }
  out[name] = m;
}
console.log(JSON.stringify(out, null, 1));
