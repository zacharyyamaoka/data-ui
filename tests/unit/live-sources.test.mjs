// The live sources (docs/peps/0012-live-data.md §7, docs/CONTRACT.md §26): polling with a since-cursor and back-off,
// server-sent events with the wire's four shapes, and the connection state each one reports. A fake fetch and a fake
// EventSource stand in for the network; tests/browser/live_checks.py runs the real EventSource against a real server
// (Last-Event-ID resume). Committed before the code (lane/live, Step 2).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LiveDataset } from '../../packages/core/src/live/store.js';
import { connectPoll, connectSSE, rowsAt } from '../../packages/core/src/live/sources.js';

const props = { t: { type: 'number' }, key: { type: 'text' }, value: { type: 'number' } };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const until = async (fn, ms = 2000) => { const end = Date.now() + ms; while (!fn()) { if (Date.now() > end) throw new Error('timed out'); await wait(5); } };

test('rowsAt: a dotted path into a body, arrays on the way flattened', () => {
  const body = { cursor: 7, groups: [{ name: 'a', rows: [{ k: 1 }, { k: 2 }] }, { name: 'b', rows: [{ k: 3 }] }] };
  assert.deepEqual(rowsAt(body, 'groups.rows').map((r) => r.k), [1, 2, 3]);
  assert.deepEqual(rowsAt([{ k: 9 }], ''), [{ k: 9 }]);
  assert.deepEqual(rowsAt({ rows: [{ k: 4 }] }, null), [{ k: 4 }], 'default: body.rows, or the body when it is an array');
  assert.deepEqual(rowsAt({ nothing: 1 }, 'groups.rows'), []);
});

test('poll: since=<cursor> after the first answer, rows from the path, status live', async () => {
  const urls = [];
  let n = 0;
  const fetch = async (url) => {
    urls.push(String(url));
    n++;
    return new Response(JSON.stringify({ cursor: `c${n}`, data: { rows: [{ t: n, key: 'a', value: n * 10 }] } }));
  };
  const ds = new LiveDataset({ properties: props, time: 't' });
  const src = connectPoll(ds, 'http://host/api/values?path=x', { every: 10, since: 'since', cursor: 'cursor', rows: 'data.rows', fetch });
  await until(() => ds.rowCount >= 3);
  src.close();
  const after = urls.length;
  await wait(40);
  assert.equal(urls.length, after, 'close() stops the polls');
  assert.ok(!urls[0].includes('since='), urls[0]);
  assert.ok(urls[1].includes('since=c1') && urls[1].includes('path=x'), urls[1]);
  assert.ok(urls[2].includes('since=c2'), urls[2]);
  assert.equal(ds.status.state, 'closed');
  assert.deepEqual(ds.snapshot(ds.end, { limit: 10 }).map((r) => r.value).reverse().slice(0, 3), [10, 20, 30]);
});

test('poll: functions instead of paths, upsert on a keyed dataset', async () => {
  let n = 0;
  const fetch = async () => { n++; return new Response(JSON.stringify({ next: n, items: { a: n, b: -n } })); };
  const ds = new LiveDataset({ properties: props, time: 't', key: 'key' });
  const src = connectPoll(ds, '/x', { every: 10, cursor: (b) => b.next, rows: (b) => Object.entries(b.items).map(([key, value]) => ({ key, value, t: b.next })), fetch, base: 'http://host/' });
  await until(() => n >= 3 && ds.latestAt(ds.end, 'a') && ds.latestAt(ds.end, 'a').value >= 3);
  src.close();
  const now = ds.snapshot(ds.end, { at: 'latest' });
  assert.deepEqual(now.map((r) => r.key).sort(), ['a', 'b']);
});

test('poll: a failure is reconnecting with the try count, and backs off; a success is live again', async () => {
  let n = 0;
  const times = [];
  const fetch = async () => {
    times.push(Date.now());
    n++;
    if (n >= 2 && n <= 4) throw new Error('host unreachable');
    return new Response(JSON.stringify({ rows: [{ t: n, key: 'a', value: n }] }));
  };
  const ds = new LiveDataset({ properties: props, time: 't' });
  const states = [];
  ds.addEventListener('status', () => states.push(`${ds.status.state}${ds.status.tries ? ':' + ds.status.tries : ''}`));
  const src = connectPoll(ds, 'http://host/x', { every: 10, fetch });
  await until(() => n >= 6, 4000);
  src.close();
  assert.ok(states.includes('reconnecting:1') && states.includes('reconnecting:3'), states.join(' '));
  assert.ok(states.lastIndexOf('live') > states.indexOf('reconnecting:3'), states.join(' '));
  const gaps = times.slice(1).map((x, i) => x - times[i]);
  assert.ok(gaps[3] >= gaps[1], `backs off: ${gaps.join(', ')}`);
});

class FakeEventSource extends EventTarget {
  static last = null;
  constructor(url, opts) { super(); this.url = url; this.opts = opts; this.readyState = 0; this.closed = false; FakeEventSource.last = this; }
  close() { this.closed = true; this.readyState = 2; }
  emit(type, data, id = '') { this.dispatchEvent(new MessageEvent(type, { data: typeof data === 'string' ? data : JSON.stringify(data), lastEventId: id })); }
  open() { this.readyState = 1; this.dispatchEvent(new Event('open')); }
  fail() { this.readyState = 0; this.dispatchEvent(new Event('error')); }
}

test('sse: rows, a bare array, remove, status and reset; open is live, an error is reconnecting', () => {
  const ds = new LiveDataset({ properties: props, time: 't', key: 'key' });
  const src = connectSSE(ds, '/api/live/events', { EventSource: FakeEventSource, base: 'http://host/dash/views.base' });
  const es = FakeEventSource.last;
  assert.equal(es.url, 'http://host/api/live/events');
  assert.equal(ds.status.state, 'connecting');
  es.open();
  assert.equal(ds.status.state, 'live');
  es.emit('message', { rows: [{ t: 1, key: 'a', value: 1 }, { t: 1, key: 'b', value: 2 }] }, '1');
  es.emit('rows', [{ t: 2, key: 'a', value: 5 }], '2');
  assert.deepEqual(ds.snapshot(2, { at: 'latest' }).map((r) => [r.key, r.value]).sort(), [['a', 5], ['b', 2]]);
  es.emit('remove', { remove: ['b'], t: 3 }, '3');
  assert.deepEqual(ds.snapshot(3, { at: 'latest' }).map((r) => r.key), ['a']);
  es.emit('status', { status: 'paused', detail: 'tview has the port' });
  assert.equal(ds.status.state, 'paused');
  assert.equal(ds.status.detail, 'tview has the port');
  es.fail();
  assert.equal(ds.status.state, 'reconnecting');
  es.open();
  assert.equal(ds.status.state, 'live');
  es.emit('reset', '{}');
  assert.equal(ds.rowCount, 0);
  src.close();
  assert.ok(es.closed);
  assert.equal(ds.status.state, 'closed');
});

test('sse: a map turns a host\'s own events into rows (RobotDx /api/v1/events activity)', () => {
  const ds = new LiveDataset({ properties: { id: { type: 'text' }, stamp: { type: 'number' }, message: { type: 'text' } }, time: 'stamp' });
  connectSSE(ds, 'http://host/api/v1/events', {
    EventSource: FakeEventSource, events: ['activity', 'tick'],
    map: (data, type) => (type === 'activity' ? [data] : []),
  });
  const es = FakeEventSource.last;
  es.open();
  es.emit('activity', { id: 'e1', stamp: 1761566400.5, message: 'fdcanusb › CAN bus: frame errors' });
  es.emit('tick', { revision: 4, reason: 'refresh' });
  assert.equal(ds.rowCount, 1);
  assert.equal(ds.latestAt(ds.end).message, 'fdcanusb › CAN bus: frame errors');
  assert.equal(ds.latestAt(ds.end).id, 'e1');
});
