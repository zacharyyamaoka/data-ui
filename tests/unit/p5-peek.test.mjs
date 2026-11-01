// PEP 0010 P5's evidence hint: the side peek's sections (packages/core/src/sections.js; docs/CONTRACT.md §35), pure.
// `record.sections[]: {name, properties?, view?}`: a section may embed a view, its filters' `this.<column>` bound to the
// peeked row's values (the analyses' rule, CONTRACT §19, now the core's bindThis); a section with neither is dropped;
// the datasets a view's sections read (`sectionSources`) are what a dashboard hands its drill peek; a field the view
// displays as a link is a real <a href> resolved against the data file's URL (`linkHtml`). The browser half (a cell
// click opening the peek on its row, the evidence link landing on its window, the embedded view's rows) is
// tests/browser/p5_checks.py. Written red, before the code.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { bindThis, bindFilters, peekSections, sectionSources, linkHtml } from '../../packages/core/src/sections.js';

const props = { verdict: { id: 'verdict', label: 'Verdict' }, value: { id: 'value', label: 'Value' }, evidence: { id: 'evidence', label: 'Evidence' }, ghost: { id: 'ghost', label: 'G', pivot: true } };
const row = { id: 'r1#tracking', run: { value: 'r1', basis: 'derived' }, t0: 0.5, t1: 2, title: 'tracking "rms"', tags: ['a', 'b'], none: null, verdict: 'fail', value: 3.1, evidence: 'index.html#t=0.500' };

test('bindThis: this.<column> becomes the row\'s value (a rich cell by its value), text in quotes untouched', () => {
  assert.equal(bindThis('run == this.run && t >= this.t0 && t <= this.t1', { run: 'r1', t0: 0.5, t1: 2 }), 'run == "r1" && t >= 0.5 && t <= 2');
  assert.equal(bindThis('title == this.title', { title: 'tracking "rms"' }), 'title == "tracking \\"rms\\""');
  assert.equal(bindThis('note == "this.run"', { run: 'r1' }), 'note == "this.run"');
  assert.equal(bindThis('x == this.none', { none: null }), 'x == null');
  assert.equal(bindThis('this.tags.contains(tag)', { tags: ['a', 'b'] }), '(tag == "a" || tag == "b")');
  assert.equal(bindThis('this.none.isEmpty()', { none: null }), 'true');
});

test('bindFilters: a string, a list or an and/or tree, every clause bound', () => {
  const values = { run: 'r1', t0: 0.5 };
  assert.deepEqual(bindFilters({ and: ['run == this.run', { or: ['t >= this.t0', 'flag == true'] }] }, values), { and: ['run == "r1"', { or: ['t >= 0.5', 'flag == true'] }] });
  assert.equal(bindFilters(undefined, values), undefined);
});

test('peekSections: properties as before; a view bound to the row; a section with neither is dropped', () => {
  const view = { record: { sections: [
    { name: 'Verdict', properties: ['verdict', 'value', 'ghost', 'missing'] },
    { name: 'Evidence', properties: ['evidence'], view: { type: 'timeseries', from: 'samples', filters: 'run == this.run && t >= this.t0 && t <= this.t1', timeseries: { x: 't', y: 'q_deg' } } },
    { name: 'Window', view: { type: 'table', from: 'windows', filters: { and: ['run == this.run', 'title == this.title'] } } },
    { name: 'Empty' },
  ] } };
  const s = peekSections(view, props, row);
  assert.deepEqual(s.map((x) => [x.name, x.list.map((p) => p.id)]), [['Verdict', ['verdict', 'value']], ['Evidence', ['evidence']], ['Window', []]]);
  assert.equal(s[0].view, null);
  assert.deepEqual(s[1].view, { type: 'timeseries', from: 'samples', filters: 'run == "r1" && t >= 0.5 && t <= 2', timeseries: { x: 't', y: 'q_deg' } });
  assert.deepEqual(s[2].view.filters, { and: ['run == "r1"', 'title == "tracking \\"rms\\""'] });
  // the view entry in the .base is not touched
  assert.equal(view.record.sections[1].view.filters, 'run == this.run && t >= this.t0 && t <= this.t1');
  // no record.sections: null (the host lays out every field, as before)
  assert.equal(peekSections({}, props, row), null);
});

test('sectionSources: the datasets a view\'s sections read (from:), each once, in order', () => {
  const view = { from: 'checks', record: { sections: [{ name: 'a', view: { type: 'table', from: 'samples' } }, { name: 'b', view: { type: 'table', from: 'windows' } }, { name: 'c', view: { type: 'table', from: 'samples' } }, { name: 'd', view: { type: 'table' } }, { name: 'e', properties: ['x'] }] } };
  assert.deepEqual(sectionSources(view), ['samples', 'windows']);
  assert.deepEqual(sectionSources({}), []);
});

test('linkHtml: a real link, resolved against the data file\'s URL, its text the value as written', () => {
  assert.equal(linkHtml('index.html#s.runs=run:a&t=1.500&tr=1.500,2.000', 'http://x/gallery/case/checks.json'),
    '<a class="dv-peek-link" href="http://x/gallery/case/index.html#s.runs=run:a&amp;t=1.500&amp;tr=1.500,2.000">index.html#s.runs=run:a&amp;t=1.500&amp;tr=1.500,2.000</a>');
  assert.equal(linkHtml('https://example.org/a?b=1', 'http://x/y.json'), '<a class="dv-peek-link" href="https://example.org/a?b=1">https://example.org/a?b=1</a>');
  assert.equal(linkHtml(null, 'http://x/y.json'), '<span class="dv-none" title="no value">—</span>');
});
