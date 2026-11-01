// The row-model worker's protocol (packages/core/src/rowmodel-worker.js: workerServer + createRowModelWorker), run in
// Node with a stand-in Worker that structured-clones every message both ways, in order, one task each, as a browser
// does. Oracle: the synchronous rowModel() on the page's own copy of the rows. Whatever way the data went over (whole,
// in slices, or as the response bytes the page fetched, replayed), and after edits posted the way <data-views> posts
// them, the model the client returns must be rowModel()'s; a request answered from an older revision must never be
// drawn, a superseded one resolves null, and a terminated worker answers nothing.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { rowModel } from '../../packages/core/src/rowmodel.js';
import { parseBase } from '../../packages/core/src/base.js';
import { loadDataset } from '../../packages/core/src/data.js';
import { workerServer, createRowModelWorker, recordingFetch } from '../../packages/core/src/rowmodel-worker.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const EX = join(ROOT, 'gallery', 'examples', 'robotparts-actuators');
const text = readFileSync(join(EX, 'actuators.json'), 'utf8');
const actuators = JSON.parse(text);
const base = parseBase(readFileSync(join(EX, 'views.base'), 'utf8'));
const grow = (n) => ({ ...actuators, rows: Array.from({ length: n }, (_, i) => ({ ...actuators.rows[i % actuators.rows.length], id: `r${i}` })) });

// A Worker as the browser runs one: each message is structured-cloned (transfer lists honoured) and delivered in a task
// of its own, in the order posted, both ways.
class StandInWorker {
  constructor() {
    this.dead = false;
    this.handle = workerServer((message, transfer) => {
      if (this.dead) return;
      const copy = structuredClone(message, { transfer: transfer || [] });
      setTimeout(() => { if (!this.dead && this.onmessage) this.onmessage({ data: copy }); }, 0);
    });
  }
  postMessage(message, transfer) {
    if (this.dead) return;
    const copy = structuredClone(message, { transfer: transfer || [] });
    setTimeout(() => { if (!this.dead) this.handle(copy); }, 0);
  }
  terminate() { this.dead = true; }
}

const ids = (rows) => rows.map((r) => r.id);
const groupsOf = (gs) => gs && gs.map((g) => ({ key: g.key, property: g.property, rows: ids(g.rows), ...(g.groups ? { groups: groupsOf(g.groups) } : {}) }));
const drawn = (table) => table.getRowModel().rows.map((r) => (r.getIsGrouped()
  ? ['group', r.depth, r.groupingColumnId, JSON.stringify(r.groupingValue ?? null), r.getLeafRows().length]
  : ['row', r.depth, r.original.id]));
function same(got, want, label) {
  assert.ok(got, `${label}: an answer`);
  assert.deepEqual(ids(got.rows), ids(want.rows), `${label}: rows`);
  assert.deepEqual(groupsOf(got.groups), groupsOf(want.groups), `${label}: groups`);
  assert.deepEqual([got.total, got.matched, got.error], [want.total, want.matched, want.error], `${label}: counts`);
  assert.deepEqual(drawn(got.table), drawn(want.table), `${label}: the table's row model`);
  // the rows are the page's own objects (what a view edits and opens), never the worker's copies
  for (let i = 0; i < Math.min(5, got.rows.length); i++) assert.equal(got.rows[i], want.rows[i], `${label}: row ${i} is the page's object`);
}
const until = async (fn) => { for (let i = 0; i < 2000 && !fn(); i++) await new Promise((r) => setTimeout(r, 1)); assert.ok(fn(), 'reached'); };

const views = [
  { type: 'table', name: 'number desc', sort: [{ property: 'peak_torque', direction: 'DESC' }] },
  { type: 'table', name: 'group, then text', groupBy: { property: 'brand', direction: 'DESC' }, sort: [{ property: 'model', direction: 'ASC' }] },
  { type: 'table', name: 'groupOrder', groupBy: { property: 'form' }, groupOrder: ['wheel hub', 'no such form'], sort: [{ property: 'mass', direction: 'ASC' }] },
];

for (const [how, opts] of [['whole', {}], ['in slices of 997', { slice: 997 }]]) {
  test(`worker protocol: data sent ${how}; every model equals rowModel() (12,000 rows)`, async () => {
    const data = grow(12000);
    const w = createRowModelWorker(data, { ...opts, Worker: StandInWorker });
    await until(() => w.ready);
    for (const view of views) same(await w.model(base, view, {}), rowModel(data, base, view), `${how} ${view.name}`);
    same(await w.model(base, views[1], { query: 'gim', filters: { and: ['peak_torque > 5'] } }), rowModel(data, base, views[1], { query: 'gim', filters: { and: ['peak_torque > 5'] } }), `${how} search + filters`);
    w.terminate();
  });
}

test('worker protocol: the page\'s fetched bytes, replayed in the worker, parse to the same rows (recordingFetch)', async () => {
  const big = JSON.stringify(grow(6000));
  const url = 'https://example.test/data/actuators.json';
  const get = async (u) => (String(u) === url ? new Response(big) : new Response('nope', { status: 404 }));
  const rec = recordingFetch(get);
  const data = await loadDataset(url, { fetch: rec.fetch });
  assert.equal(data.rows.length, 6000);
  const w = createRowModelWorker(data, { url, bodies: rec.bodies, Worker: StandInWorker });
  // the bytes were transferred, not copied: the page no longer holds them
  assert.equal(rec.bodies.get(url).bytes.byteLength, 0, 'transferred');
  await until(() => w.ready);
  for (const view of views) same(await w.model(base, view, {}), rowModel(data, base, view), `replayed ${view.name}`);
  w.terminate();
});

test('recordingFetch: the text is Response.text()\'s, byte for byte (a BOM, a broken sequence, astral characters)', async () => {
  const bytes = new Uint8Array([0xEF, 0xBB, 0xBF, 0x5B, 0x22, 0x61, 0xC3, 0x28, 0xF0, 0x9F, 0x98, 0x80, 0x22, 0x2C, 0x22, 0xF0, 0x9F, 0x98, 0x22, 0x5D]);
  const rec = recordingFetch(async () => new Response(bytes.slice()));
  const got = await (await rec.fetch('x')).text();
  assert.equal(got, await new Response(bytes.slice()).text());
});

test('worker protocol: an edit posted with its revision reaches the next model; an older revision is refused, never drawn', async () => {
  const data = grow(8000);
  const w = createRowModelWorker(data, { rev: 1, Worker: StandInWorker });
  await until(() => w.ready);
  const view = views[0];
  const before = await w.model(base, view, {});
  same(before, rowModel(data, base, view), 'before the edit');
  // as <data-views> does: change the row in place, then post it with the new revision before the next model
  const i = data.rows.indexOf(before.rows[before.rows.length - 1]);
  Object.assign(data.rows[i], { peak_torque: 9999 });
  w.edit(i, data.rows[i], 2);
  const after = await w.model(base, view, {});
  same(after, rowModel(data, base, view), 'after the edit');
  assert.equal(after.rows[0], data.rows[i], 'the edited row leads');
  // a client ahead of the worker (an edit it never received) gets a refusal, not an old order
  w.rev = 3;
  await assert.rejects(() => w.model(base, view, {}), /older revision/);
  w.terminate();
});

test('worker protocol: a newer request supersedes an older one (null), and a terminated worker answers nothing', async () => {
  const data = grow(8000);
  const w = createRowModelWorker(data, { Worker: StandInWorker });
  await until(() => w.ready);
  const first = w.model(base, views[0], {});
  const second = w.model(base, views[1], {});
  assert.equal(await first, null, 'superseded');
  same(await second, rowModel(data, base, views[1]), 'the newest');
  const pending = w.model(base, views[2], {});
  w.terminate();
  assert.equal(await pending, null, 'terminated while computing: null, never a late answer');
  await assert.rejects(() => w.model(base, views[2], {}), /terminated/);
});

test('worker protocol: data that cannot be cloned makes no worker (and leaves none running)', () => {
  const made = [];
  class Counting extends StandInWorker { constructor() { super(); made.push(this); } }
  const data = { ...grow(10), rows: [{ id: 'a', f: () => 1 }] };
  assert.throws(() => createRowModelWorker(data, { Worker: Counting }));
  assert.equal(made.length, 1);
  assert.equal(made[0].dead, true, 'terminated');
});
