"""Build docs/VIEWS.md and reports/data-ui-views-2026-10-25.html from views_data.py and measurements.json.

  npm --prefix ~/data-ui/docs/views install
  ~/psu-atlas/.venv/bin/python ~/data-ui/docs/views/build.py
  ~/psu-atlas/.venv/bin/python ~/data-ui/docs/views/capture.py      # stills + checks, then build again

The report is one self-contained file: the live demo's libraries, data and stills are inlined (the big ones gzipped and
base64'd, unpacked in the browser with DecompressionStream), so it opens from disk with no server and no network.
The demo reads robotparts' actuators exactly as the table lane's prototype does (its site/data/actuators.json).
"""
import base64
import datetime as dt
import gzip
import html
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import views_data as V  # noqa: E402

REPORT = os.path.join(REPO, 'reports', 'data-ui-views-2026-10-25.html')
VIEWS_MD = os.path.join(REPO, 'docs', 'VIEWS.md')
BUILD = os.path.join(HERE, 'build')
ESBUILD = os.path.join(HERE, 'node_modules', '.bin', 'esbuild')
ACTUATORS = '~/robotparts/.claude/worktrees/lane-tables/design/tables-2026-10-25/site/data/actuators.json'
TODAY = dt.date(2026, 10, 25)
MEAS = json.load(open(os.path.join(HERE, 'measurements.json')))
SRC_NUM = {key: i + 1 for i, (key, _t, _u) in enumerate(V.SOURCES)}
SRC = {key: (title, url) for key, title, url in V.SOURCES}
e = html.escape

# ------------------------------------------------------------------------------------------------ facts and scores

PERMISSIVE = re.compile(r'^\(?(MIT|ISC|BSD-[23]-Clause|Apache[- ]2\.0|Apache 2\.0)( OR (MIT|Apache-2\.0))?\)?$')


def reg(pkg):
    return MEAS['registry'].get(pkg) if pkg else None


def size_kb(c):
    s = c.get('size')
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    rec = MEAS['sizes'][s]
    return rec['min_gz'] / 1024


def months_since(iso):
    d = dt.date.fromisoformat(iso[:10])
    return (TODAY - d).days / 30.44


def auto_scores(c):
    r = reg(c.get('pkg'))
    s = {}
    if c.get('ours'):
        s['maint'], s['licence'] = 2, 5
    elif r:
        m = months_since(r['published'])
        s['maint'] = 5 if m <= 6 else 4 if m <= 12 else 3 if m <= 24 else 2 if m <= 36 else 1
        lic = str(r['license'])
        s['licence'] = 5 if PERMISSIVE.match(lic) else 1
    else:
        s['maint'], s['licence'] = 3, 3
    kb = size_kb(c)
    total = None if kb is None else kb + c.get('extra', 0)
    s['size'] = 3 if total is None else 5 if total <= 15 else 4 if total <= 50 else 3 if total <= 120 else 2 if total <= 300 else 1
    s.update(c['scores'])
    s['fit'] = c['_fit']
    if 'maint' not in c['scores']:
        s['maint'] = min(s['maint'], c['_stock'])
    return s


def weighted(s):
    return round(sum(w * s[k] for k, _l, w, _d in V.CRITERIA) / 5)


for view in V.VIEWS:
    for c in view['candidates']:
        c['_fit'] = V.FIT[view['id']][c['id']]
        c['_stock'] = V.STOCK.get(view['id'], {}).get(c['id'], 5)
        c['_s'] = auto_scores(c)
        c['_total'] = weighted(c['_s'])
        c['_reg'] = reg(c.get('pkg'))
        c['_kb'] = size_kb(c)
    # WHY a gate, not a weight: the brief makes a permissive licence a constraint, so a GPL or paid part cannot win on
    # points (the table lane did the same before scoring)
    for c in view['candidates']:
        c['_gate'] = 'licence' if c['_s']['licence'] <= 1 else None
    best = max((c for c in view['candidates'] if not c['_gate']), key=lambda c: c['_total'])
    sel = next(c for c in view['candidates'] if c['id'] == view['selected'])
    view['_sel'] = sel
    view['_best'] = best


def fmt_kb(c):
    kb = c['_kb']
    if kb is None:
        return 'n/m'
    if kb == 0:
        return '0 extra'
    text = f'{kb:,.1f}' if kb < 100 else f'{kb:,.0f}'
    if c.get('extra'):
        text += f' + {c["extra"]:.0f}'
    return text


def version_of(c):
    r = c['_reg']
    if not r:
        return 'ours' if c.get('ours') else '—'
    return f"{r['latest']} · {r['published'][:10]}"


def licence_of(c):
    r = c['_reg']
    if c.get('ours'):
        return 'ours (MIT)'
    if not r:
        return ', '.join(c.get('flags', [])) or '—'
    lic = str(r['license'])
    if lic.startswith('http') or lic.startswith('SEE LICENSE'):
        lic = 'proprietary terms' if 'webdatarocks' in lic or 'flexmonster' in lic else 'see LICENSE.md'
    return lic + (f" · {', '.join(c['flags'])}" if c.get('flags') else '')


def pins(view):
    out = []
    for p in view['packages']:
        v = MEAS['installed'].get(p) or (reg(p) or {}).get('latest')
        out.append((p, v, (reg(p) or {}).get('license', '')))
    return out


# ------------------------------------------------------------------------------------------------ citations


def cite_md(text):
    def rep(m):
        keys = [k.strip() for k in m.group(1).split(',')]
        return ','.join(f'[{SRC_NUM[k]}]({SRC[k][1] or "#source-index"})' for k in keys)
    return re.sub(r'⟦([^⟧]+)⟧', rep, text)


def cite_html(text, escape=True):
    parts = re.split(r'(⟦[^⟧]+⟧)', text)
    out = []
    for p in parts:
        if p.startswith('⟦'):
            keys = [k.strip() for k in p[1:-1].split(',')]
            out.append('<sup class="cite">' + ','.join(f'<a href="#src-{SRC_NUM[k]}">{SRC_NUM[k]}</a>' for k in keys) + '</sup>')
        else:
            t = e(p) if escape else p
            out.append(re.sub(r'`([^`]+)`', r'<code>\1</code>', t))
    return ''.join(out)


def strip_cites(text):
    return re.sub(r'⟦[^⟧]+⟧', '', text)


def type_cell(view):
    t = view['type']
    if view['id'] == 'tree':
        return '`table` / `list` + `tree:`'
    if view['id'] == 'media':
        return '`cards` + `lightbox:`'
    if view['id'] == 'form':
        return '`record` + `edit: true`'
    return f'`{t}`' + (' (Bases)' if view['bases'] else '')


def uses_short(view):
    return ', '.join(V.USE_CASES[k] for k in view['uses'] if k != 'other') + (' + ' + view['uses']['other'] if 'other' in view['uses'] else '')


def sel_cell(view):
    sel = view['_sel']
    pk = ', '.join(f'{p}@{v}' for p, v, _l in pins(view)) or 'none (ours)'
    return sel['name'], pk


def ours_cell(view):
    return f"{view['ours']:,}" if view.get('built') else f"~{view['ours']:,}"


# ------------------------------------------------------------------------------------------------ the demo


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        raise SystemExit(f'failed: {" ".join(cmd)}\n{r.stderr}')
    return r


def b64gz(data: bytes) -> str:
    return base64.b64encode(gzip.compress(data, 9, mtime=0)).decode('ascii')


def demo_dataset():
    d = json.load(open(ACTUATORS))
    props = d['properties']
    # WHY the labels and `derived`: SCHEMA2 §3 defines the ladder and says a level is computed, never hand-set, so the
    # board must refuse a drop that would set it (the host's rule, not the board's).
    props['level']['labels'] = {0: '0 · none', 1: '1 · listed', 2: '2 · cited', 3: '3 · CAD', 4: '4 · sim', 5: '5 · measured'}
    props['level']['derived'] = 'robotparts computes it from five checks, SCHEMA2 §3'
    keep = ['id', 'name', 'url', 'model', 'brand', 'form', 'drivetrain', 'buses', 'level', 'peak_torque', 'rated_torque', 'max_speed', 'mass',
            'gear_ratio', 'voltage', 'od', 'length', 'torque_density', 'price', 'sellers']
    rows = [{k: r.get(k) for k in keep} for r in d['rows']]
    return {'id': d['id'], 'title': d['title'], 'source': d['source'], 'properties': {k: props[k] for k in keep if k in props}, 'rows': rows}


def demo_base(ds):
    plotted = [r for r in ds['rows'] if (r['peak_torque'] or 0) > 0 and (r['mass'] or 0) > 0]
    counts = {}
    for r in plotted:
        counts[r['brand']] = counts.get(r['brand'], 0) + 1
    top = [b for b, _n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:8]]
    brand_list = ', '.join(json.dumps(b).replace('"', "'") for b in top)
    return {
        'views': [
            {'type': 'cards', 'name': 'Cards', 'order': ['model', 'brand', 'peak_torque', 'mass', 'price'],
             'sort': [{'property': 'peak_torque', 'direction': 'DESC'}], 'cardSize': 220, 'sketch': {'diameter': 'od', 'length': 'length'}},
            {'type': 'chart', 'name': 'Ashby: torque vs mass',
             'chart': {
                 'transform': [{'calculate': f"indexof([{brand_list}], datum.brand) >= 0 ? datum.brand : 'Other brands'", 'as': 'brand8'}],
                 'mark': {'type': 'point', 'filled': True, 'size': 30, 'opacity': 0.78},
                 'encoding': {
                     'x': {'field': 'mass', 'scale': {'type': 'log'}},
                     'y': {'field': 'peak_torque', 'scale': {'type': 'log'}},
                     'color': {'field': 'brand8', 'type': 'nominal', 'title': 'Brand (top 8 by count)',
                               'scale': {'domain': top + ['Other brands'], 'range': [f'var(--data-series-{i})' for i in range(1, 9)] + ['var(--data-muted)']}},
                     'tooltip': ['model', 'brand', 'form', 'peak_torque', 'mass', 'price'],
                 }},
             'guides': [{'envelope': 'form', 'shape': 'hull'}, {'indexLine': {'slope': 1, 'through': 'median'}, 'label': 'median N·m per gram'}]},
            {'type': 'kanban', 'name': 'Board: evidence level', 'groupBy': {'property': 'level'}, 'groupOrder': [0, 1, 2, 3, 4, 5],
             'order': ['model', 'brand', 'form', 'peak_torque'], 'sort': [{'property': 'peak_torque', 'direction': 'DESC'}], 'columnWidth': 250},
            {'type': 'kanban', 'name': 'Board: form', 'groupBy': {'property': 'form', 'direction': 'ASC'}, 'order': ['model', 'brand', 'peak_torque', 'price'],
             'sort': [{'property': 'price', 'direction': 'ASC'}], 'columnWidth': 240},
        ]
    }


def build_demo():
    os.makedirs(BUILD, exist_ok=True)
    main_js, chart_js = os.path.join(BUILD, 'main.js'), os.path.join(BUILD, 'chart.js')
    common = ['--bundle', '--minify', '--format=esm', '--target=es2022', '--legal-comments=none', '--log-level=warning']
    run([ESBUILD, os.path.join(HERE, 'demo', 'main.mjs'), *common, '--outfile=' + main_js], cwd=HERE)
    run([ESBUILD, os.path.join(HERE, 'demo', 'views', 'chart.mjs'), *common, '--outfile=' + chart_js], cwd=HERE)
    ds = demo_dataset()
    base = demo_base(ds)
    main = open(main_js, 'rb').read()
    chart = open(chart_js, 'rb').read()
    payload = {'data': b64gz(json.dumps(ds, separators=(',', ':')).encode()), 'base': b64gz(json.dumps(base).encode()), 'chunks': {'chart': b64gz(chart)}}
    stats = {'main_min': len(main), 'main_gz': len(gzip.compress(main, 9)), 'chart_min': len(chart), 'chart_gz': len(gzip.compress(chart, 9)),
             'data_rows': len(ds['rows']), 'data_b64': len(payload['data'])}
    json.dump(base, open(os.path.join(BUILD, 'demo.base.json'), 'w'), indent=1)
    return main.decode(), payload, stats, ds, base


# ------------------------------------------------------------------------------------------------ text shared by both


VERDICT = ('Sixteen views read one row model and one .base file. Nine sit on four stock engines: TanStack (table, pivot, list, cards, tree, '
           'compare), Vega-Lite (every chart), Pragmatic drag and drop (kanban) and React Flow (graph, Zach\'s call). Four take one library '
           'each: PhotoSwipe, Event Calendar, vis-timeline, MapLibre. KPI cards are the survey\'s kit as the SPEC names it. Pivot, record, form and compare have no '
           'stock part worth taking, so they are thin layers of ours, ~540 lines between them.')

CONTRACT_JS = r"""import { registerView } from 'data-ui';

registerView('chart', {                       // Obsidian: plugin.registerBasesView('chart', {...})
  name: 'Chart',                              //   BasesViewRegistration.name
  icon: 'chart-scatter',                      //   BasesViewRegistration.icon (lucide)
  load: () => import('./views/chart.js'),     //   .factory, made lazy: the library loads when the view opens
  options: (view) => [                        //   .options: the view's settings menu, same option types
    { type: 'property', key: 'x', displayName: 'X axis' },
    { type: 'dropdown', key: 'scale', options: { linear: 'Linear', log: 'Log' } },
  ],
});

// views/chart.js
export default class ChartView {              // Obsidian: class extends BasesView
  constructor(host, el) {}                    //   factory(controller, containerEl)
  update({ rows, groups, columns, view, tokens, total }) {}   //   onDataUpdated(), reading this.data / this.config
  destroy() {}                                //   Component.onunload()
}"""

CONTRACT_IN = [
    ('rows', 'the view\'s rows after the file\'s and the view\'s `filters`, in `sort` order: the same objects, in the same order, as the table draws (TanStack\'s row model, `.original`)'),
    ('groups', '`[{key, rows}]` in `groupOrder` when the view has `groupBy` (named groups with no rows still appear), else `null`'),
    ('columns', 'the dataset\'s property schema: `{id: {label, type, unitText, decimals, labels, derived, better}}`'),
    ('view', 'a frozen copy of this view\'s `.base` entry: Bases keys plus data-ui keys'),
    ('tokens', 'the SPEC\'s `--data-*` tokens resolved to colours (`bg, fg, muted, border, accent, series[], font`, and `css`: every `--data-*` token by name), sent again on a theme change, because canvas and SVG libraries cannot read `var()`.⟦spec⟧ A view entry may write a colour as `var(--data-series-3)`; the plugin resolves it from `tokens.css`'),
    ('total', 'the dataset\'s row count, for "N of M"'),
]

CONTRACT_OUT = [
    ('host.setView(patch)', 'merge keys into this view\'s entry. The host validates it against `schemas/view.schema.json` and writes the `.base` file (or the URL and local presets on a static site). Obsidian\'s equivalent is `this.config.set(key, value)`; its map view writes `center` and `defaultZoom` this way.⟦obs-maps⟧'),
    ('host.propose({id, set})', 'ask for a data edit; resolves `{ok, reason}`. The host decides: derived or read-only properties refuse, a writable host applies and re-emits the rows. Obsidian\'s board does the same through `fileManager.processFrontMatter` in a transaction.⟦obs-app,vault-kanban⟧'),
    ('host.open(id)', 'open the shared record peek.'),
]

CONTRACT_NEVER = ('A plugin never mutates rows, never fetches data, never writes outside its own view entry, and never loads code or tiles '
                  'from another origin.')


def contract_selection():
    return ('`views[i].type` picks the plugin from the registry. data-ui uses Bases\' own names where Bases has the view (`table`, `cards`, '
            '`list`, `kanban`, `map`: all five read from Obsidian 1.14.5 and the Maps plugin) and adds `pivot`, `chart`, `kpi`, `calendar`, '
            '`timeline`, `graph`, `record` and `compare`.⟦obs-app,obs-maps,spec-schema⟧ Obsidian keeps view keys it does not know, so a data-ui file '
            'stays a valid `.base` file; what Obsidian shows for a type it lacks is UNVERIFIED. An unknown type in data-ui draws the table with a '
            'one-line notice.')


BASES_MODEL = ('Copy it, closely. Obsidian\'s API is the same shape: `registerBasesView(id, {name, icon, factory, options})`; a `BasesView` '
               'gets the already filtered, sorted and grouped result as `this.data` (`data` and `groupedData`) and its own entry as '
               '`this.config` with `get` and `set`; `onDataUpdated()` runs on every data or config change; the settings menu is declared as '
               'options (`dropdown`, `property`, `slider`, `text`, `toggle`, `multitext`, …).⟦obs-dts,obs-guide,vault-kanban⟧ data-ui changes three '
               'things: `load()` is lazy (a page should not pay 283 KB for a chart it never opens); data edits are explicit proposals instead of '
               'direct frontmatter writes; and `tokens` arrive resolved, because charts and maps draw on canvas.')

CONFLICTS = [
    ('Chart engine: the survey said ECharts; the SPEC and this table say Vega-Lite.',
     'The survey\'s default for shared charts was ECharts 6, largely because its KPI kit extracts Vibe Tracks\' ECharts history chart.⟦survey⟧ '
     'The SPEC picks Vega-Lite for every data-ui chart and keeps ECharts only inside Vibe Tracks\' fixed drill-down;⟦spec⟧ this table agrees on '
     'its own scores (Vega-Lite 89, ECharts 80). One consequence for the survey\'s kit 1: no `<bam-kpi-history>` on ECharts; the KPI card\'s '
     'sparkline is SVG and a full history is a `chart` view, so a page never loads two chart engines (216 + 283 KB gzipped).'),
    ('The row model has to come out of the table renderer.',
     'In the lane, filter → pivot → search → TanStack all run inside the table element (`_compute()` in views.js).⟦lane-src⟧ For every layout to '
     'read the same rows, that pipeline becomes the core of `<data-views>` and the table becomes one registered layout among the rest. It is '
     'a move of ~110 lines (the demo\'s core.mjs is that move), best done inside the SPEC\'s barrier step, which moves views/ into this repo anyway.⟦spec⟧'),
    ('Cards: virtualised, not plain CSS grid.',
     'The SPEC draws `cards` with CSS grid.⟦spec⟧ At 1,149 cards that is 1,149 nodes; TanStack Virtual\'s `lanes` (already in the bundle, '
     '0 KB) kept 28 in the DOM in the demo and give masonry later. Same keys, same look.'),
    ('Graphic Walker: two facts differ from the SPEC (§8.9); the decision does not.',
     'Its package does ship a non-React entry, `embedGraphicWalker(dom, props)` in dist/vanilla.d.ts, but it bundles React, so robotparts would '
     'still pay for it. Its natural-language box posts to api.kanaries.net by default, but `askviz` and `vlChat` accept your own function, so '
     'Zach\'s own agent could answer it.⟦gw⟧ Still a second grammar beside the `.base` file: not adopted, as the SPEC says.'),
    ('Types and keys beyond the SPEC.',
     'The SPEC\'s seven layouts are the core.⟦spec⟧ This table adds `calendar`, `timeline`, `graph`, `record` and `compare`, and the keys '
     '`tree`, `lightbox`/`media`/`caption`, `start`/`end`/`calendarView`, `edges`/`layout`, `edit` and `compare`. The schema already accepts '
     'them (it allows extra keys);⟦spec-schema⟧ the checker should learn each one when its view is built, so the grammar stays one grammar.'),
    ('`kanban`, not `board`.',
     'The brief said `board`; Obsidian 1.14 ships the layout as `kanban`, with `groupBy`, `groupOrder` and `columnWidth`.⟦obs-app,obs-changelog⟧ '
     'This table and the SPEC both use `kanban`.⟦spec-schema⟧'),
]

FOUND = [
    ('A unit bug in the table lane\'s actuator rows.',
     'design/tables-2026-10-25/build_prototypes.py multiplies every actuator mass by 1,000, assuming kilograms (ACT_COLUMNS, line 127). One '
     'record\'s canonical mass is the spec `mass` in grams: CubeMars AKE40-6 KV90, the level-2 part, robotparts says 140 g and the table '
     'and this demo show 140,000 g. The Ashby chart showed it at once (the lone dot at 140 kg). The fix is the spec\'s own unit, not a factor; '
     'not fixed here, since that file belongs to the lane.⟦lane-proto⟧'),
]

LEFT_OUT = [
    'Writes to robotparts or any other repo: nothing outside ~/data-ui changed. SPEC.md and its report are the other agent\'s and untouched.',
    'Building the views beyond the three in the demo; the next build does that from this file.',
    'Bundle sizes of AG Grid, DataTables, WebDataRocks, Flexmonster, Bryntum, masonic, Clusterize, jsdiff and Web Awesome\'s drawer (n/m in the tables): each fails a gate before size matters, or is a helper.',
    'Svelte Flow\'s size: it needs a Svelte compile step, which this measurement does not have.',
    'A11y beyond the basics: keyboard moves on the board, focus order in the peek. The build must add them.',
    'Treemap, sunburst, Sankey and parallel coordinates: later chart presets, not views.',
]


# ------------------------------------------------------------------------------------------------ markdown


def md_name(n):
    return f'`{n}`' if '<' in n else n


def md_text(t):
    return t.replace('Running in the demo below', 'Running in the report\'s live demo').replace(' Live below.', ' Live in the report.')


def md_table(head, rows):
    out = ['| ' + ' | '.join(head) + ' |', '|' + '|'.join('---' for _ in head) + '|']
    for r in rows:
        out.append('| ' + ' | '.join(str(c).replace('|', '\\|').replace('\n', ' ') for c in r) + ' |')
    return '\n'.join(out)


def render_md(stats):
    L = []
    L.append('# data-ui views: one dataset, one .base file, many views\n')
    L.append(f'> Generated by `docs/views/build.py` from `docs/views/views_data.py` and `docs/views/measurements.json` on {TODAY}. '
             'Edit those, then rebuild; this file is the build spec for every view. The report with the live demo: '
             '`reports/data-ui-views-2026-10-25.html`.\n')
    L.append('**' + cite_md(VERDICT) + '**\n')
    L.append('## 1. The table\n')
    rows = []
    for v in V.VIEWS:
        name, pk = sel_cell(v)
        cands = ', '.join(md_name(c['name']) for c in v['candidates'] if c['id'] != v['selected'])
        rows.append([f"**{v['name']}**", v['priority'], uses_short(v), cands, f'**{md_name(name)}**<br>`{pk}`', cite_md(md_text(V.SHORT[v['id']])), ours_cell(v), type_cell(v)])
    L.append(md_table(['View', 'Priority', 'Use cases', 'Also considered', 'SELECTED (npm @ version)', 'Why', 'Ours on top (lines)', '.base `type`'], rows))
    L.append('\nPriority: **now** = landed, or in the SPEC\'s first slice (robotparts actuators); **soon** = the SPEC\'s slices 2-3 or the next use case in line; **later** = when a use case asks. '
             '"Ours on top" counts the layer data-ui writes over the stock part: exact where it is built (table, pivot); ~ marks an estimate, '
             'grounded in the demo\'s real files for cards (112 lines), chart (146) and board (126).\n')
    L.append('**No good stock option:** ' + ', '.join(f"{next(v['name'] for v in V.VIEWS if v['id'] == k).lower()}" for k in V.NO_STOCK)
             + '. Each is a thin layer over the engines above; their candidates are in §5.\n')
    L.append('## 2. Where this disagrees with the table lane, the survey or the SPEC\n')
    for t, body in CONFLICTS:
        L.append(f'- **{t}** {cite_md(body)}')
    for t, body in FOUND:
        L.append(f'- **Found while building: {t}** {cite_md(body)}')
    L.append('\n## 3. The criteria\n')
    L.append('Weights come from the brief\'s constraints: stock first, permissive licences, framework-free or an island, the shared row model, '
             'agent-editable config, CSS-variable theming, size. Scores are 1-5; the total is weighted to 100. `Stock and maintained`, `Licence` '
             'and `Size` are computed from npm and the measurement (§6) unless a row says otherwise; the rest are judgement, explained in each '
             'row\'s note.\n')
    L.append(md_table(['Criterion', 'Weight', 'What a 5 means'], [[l, w, d] for _k, l, w, d in V.CRITERIA]))
    L.append('\n## 4. The view-plugin contract\n')
    L.append('**Register** (the model is Obsidian\'s own Bases view API):\n')
    L.append('```js\n' + CONTRACT_JS + '\n```\n')
    L.append('**What a plugin receives** in `update()`:\n')
    for k, d in CONTRACT_IN:
        L.append(f'- `{k}`: {cite_md(d)}')
    L.append('\n**What it may write back:** only these three calls.\n')
    for k, d in CONTRACT_OUT:
        L.append(f'- `{k}`: {cite_md(d)}')
    L.append('\n' + CONTRACT_NEVER + '\n')
    L.append('**How `type:` selects it.** ' + cite_md(contract_selection()) + '\n')
    L.append('**Is Bases\' plugin API a model to copy?** ' + cite_md(BASES_MODEL) + '\n')
    L.append('**A React island inside a framework-free page** (the graph view, and any React-only part later): the plugin\'s `load()` imports '
             '`react`, `react-dom/client` and `@xyflow/react` together; the constructor calls `createRoot(el)`; `update()` calls '
             '`root.render(<Flow nodes edges />)` with nodes and edges built from `rows`; `destroy()` calls `root.unmount()`. React 19 renders '
             'into any element, including a shadow root, and handles custom elements natively.⟦react19⟧ The page pays React once, only when '
             'a graph opens: measured 127.6 KB gzipped for React 19.3.1 + react-dom/client + @xyflow/react 12.12.0, + 3.0 KB of CSS and 16.6 KB '
             'for dagre. In Clank, where React is already loaded, the same view costs 60.7 + 16.6 KB.⟦measure⟧ In a shadow root, React Flow\'s '
             'stylesheet goes into `adoptedStyleSheets`.\n'.replace('⟦react19⟧', cite_md('⟦react19⟧')).replace('⟦measure⟧', cite_md('⟦measure⟧')))
    L.append('## 5. Per view: the build spec\n')
    L.append(f'Versions, publish dates and licences: npm on {V.ACCESSED}.{cite_md("⟦npm⟧")} Sizes: JS min+gz in KB, measured.{cite_md("⟦measure⟧")} '
             '"+ N" is a runtime it needs on top (React 67 KB, temporal-polyfill 20 KB). n/m = not measured.\n')
    for v in V.VIEWS:
        sel = v['_sel']
        L.append(f"### {v['name']} · `type: {v['type']}` · {v['priority']}\n")
        L.append(v['what'] + '\n')
        L.append('- **Use cases:** ' + '; '.join(f"{V.USE_CASES[k]}: {why}" for k, why in v['uses'].items()))
        L.append(f"- **Selected:** {md_name(sel['name'])}. {cite_md(md_text(v['why']))}")
        pk = pins(v)
        L.append('- **npm:** ' + (', '.join(f'`{p}@{ver}` ({lic})' for p, ver, lic in pk) if pk else 'none; ours'))
        L.append(f"- **`.base` keys:** Bases: {', '.join(f'`{k}`' for k in v['keys']['bases']) or '—'}. data-ui: {', '.join(f'`{k}`' for k in v['keys']['ours']) or '—'}.")
        L.append(f"- **Ours on top:** {ours_cell(v)} lines; {v['ours_note']}.")
        if v['_best']['id'] != sel['id']:
            L.append(f"- **Note:** {md_name(v['_best']['name'])} scores higher ({v['_best']['_total']} vs {sel['_total']}); the selection is explained above.")
        L.append('')
        rows = []
        for c in sorted(v['candidates'], key=lambda c: -c['_total']):
            s = c['_s']
            mark = '**' if c['id'] == sel['id'] else ''
            rows.append([f"{mark}{md_name(c['name'])}{mark}" + (' ✓' if c['id'] == sel['id'] else ''),
                         (f"[`{c['pkg']}`]({c['_reg']['url']})" if c['_reg'] else f"`{c['pkg']}`") if c.get('pkg') else '—', version_of(c), licence_of(c), fmt_kb(c),
                         *[s[k] for k, *_ in V.CRITERIA], f"**{c['_total']}**" + (' (fails licence gate)' if c['_gate'] else ''), cite_md(c.get('note', ''))])
        L.append(md_table(['Candidate', 'npm', 'Latest · published', 'Licence', 'KB gz'] + [f'{k} ({w})' for k, _l, w, _d in V.CRITERIA] + ['Total', 'Note'], rows))
        L.append('')
    L.append('## 6. How the numbers were made\n')
    L.append(f'- **Sizes:** `docs/views/measure.py` installs every candidate at the version in `measurements.json` (npm `--ignore-scripts`), bundles '
             'its documented entry with esbuild 0.25.12 (minified, ESM, browser), React external, and gzips at level 9. CSS is the shipped '
             'stylesheet, with its count of custom-property definitions as the theming evidence. Cross-check: Tabulator measures 103.4 KB, '
             'the table lane measured 104.')
    L.append(f"- **The demo:** {stats['data_rows']:,} actuators from the table lane's `site/data/actuators.json` (robotparts release "
             f"{json.load(open(ACTUATORS))['source'].split('release ')[-1]}); its bundles are {stats['main_gz'] / 1024:.0f} KB gzipped (core, cards, "
             f"board, TanStack, Pragmatic) and {stats['chart_gz'] / 1024:.0f} KB (the chart plugin with vega, vega-lite, vega-embed), the second "
             'loaded only when the chart tab opens.')
    L.append('- **Bases facts:** read from Obsidian 1.14.5\'s own app.js (view ids and option keys) and the Maps plugin\'s source, not from memory.')
    L.append('\n## 7. Perspective: the whole-suite contrast\n')
    L.append(cite_md(PERSPECTIVE) + '\n')
    L.append('## 8. Left out on purpose\n')
    for x in LEFT_OUT:
        L.append(f'- {x}')
    L.append('\n## Related\n')
    L.append('Vault notes behind this table (obsidian:// links):\n')
    for t, u in RELATED:
        L.append(f'- [{t}]({u.replace(" ", "%20")})')
    L.append('')
    L.append('# Source Index\n')
    L.append(f'Web sources accessed {V.ACCESSED}.\n')
    for i, (key, title, url) in enumerate(V.SOURCES, 1):
        L.append(f'{i}. [{title}]({url})' if url else f'{i}. {title}')
    for title, url in VAULT_LINKS:
        pass
    return '\n'.join(L) + '\n'


PERSPECTIVE = ('Perspective 5.6.1 (now `@perspective-dev/*`, Apache-2.0) is the one stock suite closest to "one dataset, many views": one JSON '
               'viewer config switches a datagrid, a pivot (group_by, split_by), d3fc charts and a map over the same table.⟦perspective,npm⟧ '
               'It is not the base because its engine is 4.27 MB of WebAssembly that gzip cannot shrink, it runs in a module worker, Zach found '
               'its UI "super technical", its chart plugin lags (4.4.1, April) and it has no cards, board, calendar, timeline or graph.⟦lane⟧ '
               'It stays the candidate engine for a million-row dataset, behind the same row-model seam. AG Grid with AG Charts is the other '
               'suite and fails on licence: grouping, pivot, tree data and integrated charts are Enterprise ($999 / $499 / $1,498 per developer).⟦ag⟧')

VAULT_LINKS = []


# ------------------------------------------------------------------------------------------------ html


CSS = r"""
:root { --background: #ffffff; --foreground: #16181d; --muted-foreground: #5e6572; --border: #e3e5ea; --card: #ffffff; --soft: #f5f6f8;
  --primary: #2f6fed; --destructive: #c73a3a; --ok: #1f8a4c; --warn: #a86500;
  --chart-1: #2f6fed; --chart-2: #e8743b; --chart-3: #19a979; --chart-4: #c94fa8; --chart-5: #8a6d3b; --chart-6: #13a4b4; --chart-7: #d6a300; --chart-8: #6c5ce7;
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, system-ui, sans-serif; --font-mono: ui-monospace, "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --background: #121418; --foreground: #e8eaee; --muted-foreground: #9aa1ad;
  --border: #2a2e36; --card: #181b20; --soft: #1c1f25; --primary: #6c9cff; --destructive: #f07070; --ok: #4cc27f; --warn: #e0a640;
  --chart-1: #6c9cff; --chart-2: #f2925e; --chart-3: #3fcf9b; --chart-4: #e07cc6; --chart-5: #c4a26a; --chart-6: #45c6d4; --chart-7: #f0c93a; --chart-8: #a197ff; } }
:root[data-theme="dark"], #du-demo[data-theme="dark"] { --background: #121418; --foreground: #e8eaee; --muted-foreground: #9aa1ad;
  --border: #2a2e36; --card: #181b20; --soft: #1c1f25; --primary: #6c9cff; --destructive: #f07070; --ok: #4cc27f; --warn: #e0a640;
  --chart-1: #6c9cff; --chart-2: #f2925e; --chart-3: #3fcf9b; --chart-4: #e07cc6; --chart-5: #c4a26a; --chart-6: #45c6d4; --chart-7: #f0c93a; --chart-8: #a197ff; }
#du-demo[data-theme="light"] { --background: #ffffff; --foreground: #16181d; --muted-foreground: #5e6572; --border: #e3e5ea; --card: #ffffff;
  --soft: #f5f6f8; --primary: #2f6fed; --destructive: #c73a3a; --ok: #1f8a4c;
  --chart-1: #2f6fed; --chart-2: #e8743b; --chart-3: #19a979; --chart-4: #c94fa8; --chart-5: #8a6d3b; --chart-6: #13a4b4; --chart-7: #d6a300; --chart-8: #6c5ce7; }
/* SPEC §10: the --data-* contract, defaulting to shadcn's names (declared on the demo, so its own theme switch flows through) */
#du-demo { --data-bg: var(--background); --data-fg: var(--foreground); --data-muted: var(--muted-foreground); --data-border: var(--border);
  --data-accent: var(--primary); --data-warn: var(--destructive); --data-font: var(--font-sans); --data-mono: var(--font-mono);
  --data-series-1: var(--chart-1); --data-series-2: var(--chart-2); --data-series-3: var(--chart-3); --data-series-4: var(--chart-4);
  --data-series-5: var(--chart-5); --data-series-6: var(--chart-6); --data-series-7: var(--chart-7); --data-series-8: var(--chart-8); }
* { box-sizing: border-box; }
html { background: var(--background); }
body { margin: 0; background: var(--background); color: var(--foreground); font: 16px/1.55 var(--font-sans); }
main { padding: 28px clamp(16px, 3vw, 48px) 64px; max-width: 1880px; margin: 0 auto; }
h1 { font-size: clamp(26px, 2.6vw, 36px); line-height: 1.15; margin: 0 0 8px; letter-spacing: -.01em; }
h2 { font-size: 24px; margin: 48px 0 12px; padding-top: 8px; border-top: 1px solid var(--border); }
h3 { font-size: 19px; margin: 0; }
a { color: var(--primary); }
code { font: .88em var(--font-mono); background: var(--soft); border: 1px solid var(--border); border-radius: 4px; padding: 0 4px; }
.lede { font-size: 18px; max-width: 1200px; }
.meta { color: var(--muted-foreground); font-size: 14px; margin: 0 0 18px; }
.cite { font-size: .7em; margin-left: 1px; }
.cite a { text-decoration: none; }
.verdict { font-size: 19px; line-height: 1.5; border-left: 4px solid var(--primary); padding: 6px 0 6px 16px; margin: 16px 0 18px; max-width: 1640px; }
.tablewrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 14.5px; }
th, td { text-align: left; vertical-align: top; padding: 8px 10px; border-bottom: 1px solid var(--border); }
thead th { position: sticky; top: 0; background: var(--soft); font-size: 13px; text-transform: uppercase; letter-spacing: .03em; color: var(--muted-foreground); z-index: 1; }
tbody tr:last-child td { border-bottom: 0; }
.summary td:nth-child(1) { font-weight: 650; white-space: nowrap; }
.summary td.sel { font-weight: 650; }
.summary td.sel small { display: block; font: 12px var(--font-mono); color: var(--muted-foreground); font-weight: 400; margin-top: 2px; }
.summary td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.summary td.type code { white-space: nowrap; }
.pri { display: inline-block; font-size: 12px; font-weight: 650; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--border); white-space: nowrap; }
.pri.now { background: color-mix(in srgb, var(--primary) 14%, transparent); border-color: color-mix(in srgb, var(--primary) 40%, transparent); }
.pri.soon { background: var(--soft); }
.pri.later { color: var(--muted-foreground); }
.also { color: var(--muted-foreground); font-size: 13px; line-height: 1.4; }
.uc { display: inline-block; font-size: 11px; font-weight: 600; padding: 0 5px; margin: 1px 0; line-height: 17px; border-radius: 4px; background: var(--soft); border: 1px solid var(--border); white-space: nowrap; }
.summary td { padding: 6px 10px; }
code, pre, .du-yaml, #du-demo input { font-variant-ligatures: none; font-feature-settings: "calt" 0, "liga" 0; }
.grid2 > *, .facts > *, .stills > * { min-width: 0; }
code { overflow-wrap: anywhere; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; }
.box { border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; background: var(--card); }
.box h3 { font-size: 16px; margin-bottom: 6px; }
.conflict { border-left: 4px solid var(--warn); }
pre.code { font: 13px/1.5 var(--font-mono); background: var(--soft); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; overflow-x: auto; }
dl.contract { display: grid; grid-template-columns: minmax(160px, auto) 1fr; gap: 6px 16px; margin: 8px 0; }
dl.contract dt { font: 13.5px var(--font-mono); font-weight: 600; }
dl.contract dd { margin: 0; }
nav.views { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 18px; }
nav.views a { font-size: 13.5px; border: 1px solid var(--border); border-radius: 999px; padding: 3px 10px; text-decoration: none; color: var(--foreground); }
section.view { border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px; margin: 18px 0; background: var(--card); scroll-margin-top: 12px; }
section.view header { display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; margin-bottom: 8px; }
section.view .what { max-width: 1250px; }
.facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 6px 24px; margin: 10px 0 12px; font-size: 15px; }
.facts b { display: block; font-size: 12.5px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted-foreground); }
.cands td { font-size: 14px; }
.cands td code, .cands td a code { overflow-wrap: normal; white-space: nowrap; }
.cands th.n { text-align: center; } .cands th small { font-weight: 400; text-transform: none; }
.cands td { overflow-wrap: break-word; }
.cands td.n { text-align: center; font-variant-numeric: tabular-nums; width: 42px; }
.cands td.tot { text-align: center; font-weight: 700; font-variant-numeric: tabular-nums; }
.cands tr.sel td { background: color-mix(in srgb, var(--primary) 7%, transparent); }
.cands tr.sel td:first-child { box-shadow: inset 3px 0 0 var(--primary); font-weight: 650; }
.cands td.kb { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.s1 { color: var(--destructive); font-weight: 700; } .s2 { color: var(--warn); font-weight: 600; }
.flag { display: inline-block; font-size: 11.5px; color: var(--destructive); border: 1px solid color-mix(in srgb, var(--destructive) 45%, transparent); border-radius: 4px; padding: 0 5px; margin-left: 4px; white-space: nowrap; }
.why { max-width: 1250px; }
.bars { display: grid; grid-template-columns: minmax(170px, 240px) 1fr 80px; gap: 6px 12px; align-items: center; font-size: 14px; }
.bars .bar { height: 14px; background: var(--chart-1); border-radius: 3px; min-width: 2px; }
.bars .bar.lazy { background: var(--chart-2); }
.bars .v { text-align: right; font-variant-numeric: tabular-nums; }
.stills { display: grid; grid-template-columns: repeat(auto-fit, minmax(520px, 1fr)); gap: 16px; }
figure { margin: 0; }
figure img, figure video { width: 100%; height: auto; border: 1px solid var(--border); border-radius: 8px; display: block; }
figcaption { font-size: 14px; color: var(--muted-foreground); margin-top: 6px; }
.hero video { max-width: 1400px; }
ol.sources { font-size: 14px; }
ol.sources li { margin-bottom: 3px; }
.small { font-size: 14px; color: var(--muted-foreground); }
@media (max-width: 700px) { body { font-size: 15px; } .verdict { font-size: 16px; } .lede { font-size: 16px; } .grid2, .stills { grid-template-columns: 1fr; } dl.contract { grid-template-columns: 1fr; }
  .bars { grid-template-columns: 120px 1fr 60px; } section.view { padding: 14px; } }
"""


UC_ABBR = {'rp': 'RP', 'vt': 'VT', 'ml': 'ML', 'rack': 'Rack', 'gal': 'Gal', 'money': 'Money', 'other': 'BAM sites'}


def uc_chips(v):
    return ' '.join(f'<span class="uc" title="{e(V.USE_CASES[k])}: {e(why)}">{UC_ABBR[k]}</span>' for k, why in v['uses'].items())


def h_pri(p):
    return f'<span class="pri {p}">{p}</span>'


def h_code(text):
    return re.sub(r'`([^`]+)`', r'<code>\1</code>', e(text))


def render_html(main_js, payload, stats, stills):
    H = []
    H.append('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">')
    H.append('<title>data-ui views</title>')
    H.append('<meta name="description" content="Every view data-ui supports, every off-the-shelf library considered, and the one selected, with evidence and a live demo on robotparts data.">')
    demo_css = open(os.path.join(HERE, 'demo', 'demo.css')).read()
    H.append(f'<style>{CSS}\n{demo_css}</style></head><body><main>')
    H.append('<h1>data-ui views: one dataset, one .base file, sixteen views</h1>')
    H.append(f'<p class="meta">{TODAY:%B %-d, %Y} · the master table Zach asked for · for the data-ui build that follows · '
             'source: <code>docs/views/views_data.py</code> → <code>docs/VIEWS.md</code> and this page</p>')
    H.append(f'<p class="verdict">{cite_html(VERDICT)}</p>')
    # summary
    H.append('<div class="tablewrap"><table class="summary"><thead><tr><th>View</th><th>Priority</th><th>Use cases</th><th>Also considered</th>'
             '<th>Selected</th><th>Why</th><th>Ours on top<br>(lines)</th><th>.base type</th></tr></thead><tbody>')
    for v in V.VIEWS:
        name, pk = sel_cell(v)
        cands = ', '.join(e(c['name']) for c in v['candidates'] if c['id'] != v['selected'])
        H.append(f'<tr><td><a href="#v-{v["id"]}">{e(v["name"])}</a></td><td>{h_pri(v["priority"])}</td><td>{uc_chips(v)}</td>'
                 f'<td class="also">{cands}</td><td class="sel">{e(name)}<small>{e(pk)}</small></td><td>{cite_html(V.SHORT[v["id"]])}</td>'
                 f'<td class="num">{ours_cell(v)}</td><td class="type">{h_code(type_cell(v))}</td></tr>')
    H.append('</tbody></table></div>')
    H.append('<p class="small">Use cases: ' + ' · '.join(f'<span class="uc">{UC_ABBR[k]}</span> {e(V.USE_CASES[k] if k != "other" else "BAM / Tycoon sites")}' for k in UC_ABBR) + ' (hover a chip for why).<br>Priority: <b>now</b> = landed, or in the SPEC\'s first slice; <b>soon</b> = the SPEC\'s slices 2-3 or the next use case in line; <b>later</b> = when '
             'a use case asks. "Ours on top" is the layer data-ui writes over the stock part: exact where it is built (table, pivot); ~ marks an '
             'estimate, grounded in the demo\'s real files for cards (112 lines), chart (146) and board (126). <b>No good stock option:</b> pivot, record, form and '
             'compare are thin layers of ours over the engines above.</p>')
    H.append('<nav class="views">' + ''.join(f'<a href="#v-{v["id"]}">{e(v["name"])}</a>' for v in V.VIEWS) + '<a href="#demo">Live demo</a><a href="#contract">Plugin contract</a><a href="#sizes">Sizes</a><a href="#source-index">Sources</a></nav>')
    # conflicts + needs
    H.append('<h2 id="conflicts">Where this disagrees with the table lane, the survey or the SPEC</h2><div class="grid2">')
    for t, body in CONFLICTS:
        H.append(f'<div class="box conflict"><h3>{h_code(t)}</h3><p>{cite_html(body)}</p></div>')
    H.append('</div>')
    for t, body in FOUND:
        H.append(f'<div class="box conflict" style="margin-top:16px"><h3>Found while building: {h_code(t)}</h3><p>{cite_html(body)}</p></div>')
    # demo
    H.append('<h2 id="demo">Live: three selected libraries on one row model</h2>')
    H.append(f'<p class="lede">{stats["data_rows"]:,} robotparts actuators (the table lane\'s dataset), one <code>.base</code> file with four views, '
             'three plugins. Type a filter and every view changes, because they all read the same rows. Drag a board column: the view writes '
             '<code>groupOrder</code> into the file (right). Drag a card between evidence levels: the host refuses, because a level is derived. '
             'Drag one between forms: the host accepts the edit and the chart\'s envelopes move with it. The chart\'s Vega bundle unpacks the first '
             'time its tab opens.</p>')
    H.append('<div id="du-demo"><p style="padding:16px">Loading the demo… (it needs a browser with DecompressionStream: Chrome 80+, Firefox 113+, Safari 16.4+)</p></div>')
    if stills.get('hero'):
        H.append(f'<figure class="hero" style="margin-top:16px"><video src="{stills["hero"]}" autoplay muted loop playsinline controls></video>'
                 '<figcaption>The same demo, recorded headlessly: a filter narrows all three views, a refused and an accepted card drop, a column reorder that lands in the .base file.</figcaption></figure>')
    if stills.get('images'):
        H.append('<h3 style="margin-top:20px">Captured from the demo above</h3><div class="stills">')
        for src, cap in stills['images']:
            H.append(f'<figure><img src="{src}" alt="{e(cap)}" loading="lazy"><figcaption>{e(cap)}</figcaption></figure>')
        H.append('</div>')
    if stills.get('checks'):
        H.append('<h3 style="margin-top:20px">Checks (docs/views/capture.py, headless Chromium)</h3><div class="tablewrap"><table><thead><tr><th>Check</th><th>Measured</th><th></th></tr></thead><tbody>')
        for name, value, ok in stills['checks']:
            H.append(f'<tr><td>{e(name)}</td><td>{e(value)}</td><td>{"✅" if ok else "❌"}</td></tr>')
        H.append('</tbody></table></div>')
    # criteria
    H.append('<h2 id="criteria">The criteria, before the options</h2>')
    H.append('<p>Weights come from the brief\'s constraints. Scores run 1-5 and the total is weighted to 100. <i>Stock and maintained</i>, '
             '<i>Licence</i> and <i>Size</i> are computed from npm and the measurement unless a row says otherwise; the rest are judgement, explained '
             'in each candidate\'s note. Scores are mine; the facts beside them are not.</p>')
    H.append('<div class="tablewrap"><table><thead><tr><th>Criterion</th><th>Weight</th><th>What a 5 means</th></tr></thead><tbody>')
    for _k, l, w, d in V.CRITERIA:
        H.append(f'<tr><td><b>{e(l)}</b></td><td>{w}</td><td>{e(d)}</td></tr>')
    H.append('</tbody></table></div>')
    # contract
    H.append('<h2 id="contract">The view-plugin contract</h2>')
    H.append('<h3>Register, receive, write back</h3>')
    H.append(f'<pre class="code">{e(CONTRACT_JS)}</pre>')
    H.append('<div class="grid2"><div><h3>What update() receives</h3><dl class="contract">')
    for k, d in CONTRACT_IN:
        H.append(f'<dt>{e(k)}</dt><dd>{cite_html(d)}</dd>')
    H.append('</dl></div><div><h3>What a plugin may write: these three, nothing else</h3><dl class="contract">')
    for k, d in CONTRACT_OUT:
        H.append(f'<dt>{e(k)}</dt><dd>{cite_html(d)}</dd>')
    H.append(f'</dl><p>{e(CONTRACT_NEVER)}</p></div></div>')
    H.append(f'<div class="grid2" style="margin-top:12px"><div class="box"><h3>How <code>type:</code> selects a plugin</h3><p>{cite_html(contract_selection())}</p></div>'
             f'<div class="box"><h3>Is Bases\' own plugin API the model? Yes.</h3><p>{cite_html(BASES_MODEL)}</p></div>'
             '<div class="box"><h3>A React island in a page with no React (the graph view)</h3><p>'
             + cite_html('The plugin\'s `load()` imports `react`, `react-dom/client` and `@xyflow/react` together; its constructor calls `createRoot(el)`; '
                         '`update()` renders the flow from `rows` (nodes) and the view\'s `edges` property; `destroy()` unmounts. React 19 renders into any '
                         'element, shadow roots included.⟦react19⟧ Measured cost, paid once and only when a graph opens: 127.6 KB gzipped (React 19.3.1 + '
                         'react-dom/client 67.3, @xyflow/react 12.12.0 60.7) + 3.0 KB CSS + 16.6 KB dagre. In Clank, where React is loaded already: 77 KB.⟦measure⟧ '
                         '@xyflow/system is the shared core under React Flow and Svelte Flow, with no renderer of its own.⟦xyflow⟧')
             + '</p></div></div>')
    # size budget
    H.append('<h2 id="sizes">What each selected view costs a page</h2><p>JS min+gz, measured; blue loads with the core, orange only when that view opens.</p><div class="bars">')
    budget = [('core: table, pivot, list, cards, tree, compare', 36.0, False), ('kanban (Pragmatic)', 7.0, False), ('chart (Vega-Lite + embed)', size_kb({'size': 'vega+vega-lite+vega-embed'}), True),
              ('KPI history (ECharts subset)', size_kb({'size': 'echarts-subset'}), True), ('graph (React + React Flow + dagre)', 127.6 + 16.6, True),
              ('map (MapLibre + PMTiles)', size_kb({'size': 'maplibre-gl'}) + 7.4, True), ('timeline (vis-timeline)', size_kb({'size': 'vis-timeline-standalone'}), True),
              ('calendar (Event Calendar)', size_kb({'size': 'event-calendar-build'}), True), ('lightbox (PhotoSwipe)', size_kb({'size': 'photoswipe'}), True),
              ('image slider (compare)', size_kb({'size': 'img-comparison-slider'}), True)]
    top = max(b for _n, b, _l in budget)
    for n, kb, lazy in budget:
        H.append(f'<div>{e(n)}</div><div><div class="bar{" lazy" if lazy else ""}" style="width:{kb / top * 100:.1f}%"></div></div><div class="v">{kb:,.0f} KB</div>')
    H.append('</div>')
    # per view
    H.append('<h2 id="views">Per view: the build spec</h2>')
    H.append(f'<p>Versions, publish dates and licences: npm on {V.ACCESSED}.{cite_html("⟦npm⟧")} Sizes: JS min+gz in KB, measured.{cite_html("⟦measure⟧")} '
             '"+ N" is a runtime needed on top (React 67, temporal-polyfill 20). n/m = not measured. Score columns are the criteria above; red is a 1.</p>')
    short = {'fit': 'Fit', 'maint': 'Stock', 'licence': 'Lic.', 'fw': 'No fw', 'rows': 'Rows', 'cfg': 'Config', 'css': 'CSS', 'size': 'Size'}
    crit_heads = ''.join(f'<th class="n" title="{e(l)} ({w}): {e(d)}">{short[k]}<br><small>{w}</small></th>' for k, l, w, d in V.CRITERIA)
    for v in V.VIEWS:
        sel = v['_sel']
        H.append(f'<section class="view" id="v-{v["id"]}"><header><h3>{e(v["name"])}</h3><code>type: {e(v["type"])}</code>{h_pri(v["priority"])}'
                 f'<span>→ <b>{e(sel["name"])}</b></span></header>')
        H.append(f'<p class="what">{e(v["what"])}</p>')
        pk = pins(v)
        H.append('<div class="facts">'
                 f'<div><b>Use cases</b>{"<br>".join(e(V.USE_CASES[k]) + ": " + e(why) for k, why in v["uses"].items())}</div>'
                 f'<div><b>npm, pinned for the build</b>{"<br>".join(f"<code>{e(p)}@{e(ver)}</code> {e(str(lic))}" for p, ver, lic in pk) if pk else "none; ours"}</div>'
                 f'<div><b>.base keys</b>Bases: {", ".join(f"<code>{e(k)}</code>" for k in v["keys"]["bases"]) or "—"}<br>data-ui: {", ".join(f"<code>{e(k)}</code>" for k in v["keys"]["ours"]) or "—"}</div>'
                 f'<div><b>Ours on top</b>{ours_cell(v)} lines ({e(v["ours_note"])})</div></div>')
        H.append(f'<p class="why"><b>Why {e(sel["name"])}.</b> {cite_html(v["why"])}</p>')
        if v['_best']['id'] != sel['id']:
            H.append(f'<p class="small">{e(v["_best"]["name"])} scores higher ({v["_best"]["_total"]} vs {sel["_total"]}); the reason for the selection is above.</p>')
        H.append(f'<div class="tablewrap"><table class="cands"><thead><tr><th>Candidate</th><th>npm</th><th>Latest · published</th><th>Licence</th><th>KB gz</th>{crit_heads}<th>Total</th><th>Note</th></tr></thead><tbody>')
        for c in sorted(v['candidates'], key=lambda c: -c['_total']):
            s = c['_s']
            flags = ''.join(f'<span class="flag">{e(f)}</span>' for f in c.get('flags', []))
            cells = ''.join(f'<td class="n{" s1" if s[k] == 1 else " s2" if s[k] == 2 else ""}">{s[k]}</td>' for k, *_ in V.CRITERIA)
            r = c['_reg']
            npm = f'<a href="{e(r["url"])}"><code>{e(c["pkg"])}</code></a>' if r else (f'<code>{e(c["pkg"])}</code>' if c.get('pkg') else '—')
            lic = licence_of(c).split(' · ')[0]
            H.append(f'<tr class="{"sel" if c["id"] == sel["id"] else ""}"><td>{e(c["name"])}{" ✓" if c["id"] == sel["id"] else ""}{flags}</td><td>{npm}</td>'
                     f'<td>{e(version_of(c))}</td><td>{e(lic)}</td><td class="kb" title="{e(c.get("size_note", ""))}">{e(fmt_kb(c))}</td>{cells}'
                     f'<td class="tot">{c["_total"]}{"<br><span class=flag>gate: licence</span>" if c["_gate"] else ""}</td><td>{cite_html(c.get("note", ""))}</td></tr>')
        H.append('</tbody></table></div></section>')
    H.append(f'<h2 id="perspective">Perspective: the whole-suite contrast</h2><p class="lede">{cite_html(PERSPECTIVE)}</p>')
    H.append('<h2 id="method">How the numbers were made</h2><ul>'
             '<li><b>Sizes:</b> <code>docs/views/measure.py</code> installs each candidate at the recorded version (npm, <code>--ignore-scripts</code>), '
             'bundles its documented entry with esbuild 0.25.12 (minified ESM, browser, React external) and gzips at level 9. CSS is the shipped '
             'stylesheet, with its count of custom-property definitions as the theming evidence. Cross-check: Tabulator measures 103.4 KB; the table lane measured 104.</li>'
             f'<li><b>The demo:</b> its main bundle is {stats["main_gz"] / 1024:.0f} KB gzipped (core, cards, board, TanStack, Pragmatic); the chart plugin is '
             f'{stats["chart_gz"] / 1024:.0f} KB (vega, vega-lite, vega-embed), inlined gzipped and unpacked on first use. Source: <code>docs/views/demo/</code>.</li>'
             '<li><b>Bases facts</b> come from Obsidian 1.14.5\'s own app.js (view ids and option keys) and the Maps plugin\'s source, not from memory.</li></ul>')
    H.append('<h2 id="left-out">Left out on purpose</h2><ul>' + ''.join(f'<li>{e(x)}</li>' for x in LEFT_OUT) + '</ul>')
    H.append('<h2 id="source-index">Source Index</h2><p class="small">Web sources accessed 2026-10-25. obsidian:// links open the vault note.</p><ol class="sources">')
    for i, (key, title, url) in enumerate(V.SOURCES, 1):
        H.append(f'<li id="src-{i}">' + (f'<a href="{e(url)}">{e(title)}</a>' if url else e(title)) + '</li>')
    H.append('</ol>')
    H.append('<h3 style="margin-top:18px">Related notes in the vault</h3><ul class="small">' + ''.join(f'<li><a href="{e(u)}">{e(t)}</a></li>' for t, u in RELATED) + '</ul>')
    H.append('</main>')
    H.append('<script>window.__DU = ' + json.dumps(payload) + ';</script>')
    H.append('<script type="module">' + main_js.replace('</script', '<\\/script') + '</script>')
    H.append('</body></html>')
    return '\n'.join(H)


def vault(path):
    from urllib.parse import quote
    return 'obsidian://open?vault=zach_brain&file=' + quote(path, safe='')


RELATED = [
    ('Vega-Lite (SOFTWARE)', vault('Sources/Notes/Vega-Lite (SOFTWARE)')),
    ('C - Grammar of Graphics', vault('World Model/Chunks & Concepts/C - Grammar of Graphics')),
    ('React Flow (SOFTWARE)', vault('Sources/Notes/React Flow (SOFTWARE)')),
    ('C - Islands Architecture', vault('World Model/Chunks & Concepts/C - Islands Architecture')),
    ('C - Strangler Fig (Replace a Running System One Part at a Time)', vault('World Model/Chunks & Concepts/C - Strangler Fig (Replace a Running System One Part at a Time)')),
    ('C - Kanban', vault('World Model/Chunks & Concepts/C - Kanban')),
    ('C - Progressive Disclosure', vault('World Model/Chunks & Concepts/C - Progressive Disclosure')),
    ('C - Small Multiples and Sparklines (Tufte)', vault('World Model/Chunks & Concepts/C - Small Multiples and Sparklines (Tufte)')),
    ('Personal KPI Dashboard — Off-the-Shelf Landscape (Deep Research, 2026-09-30)', vault('Sources/Notes/Personal KPI Dashboard — Off-the-Shelf Landscape (Deep Research, 2026-09-30)')),
    ('Agent Work Dashboard — Prior Art, Convergence and Five Proposals (2026-10-03)', vault('Projects/BAM Robotics/Notes/Agent Work Dashboard — Prior Art, Convergence and Five Proposals (2026-10-03)')),
    ('Dataclass Viewer — Prior Art for Configs, Parameters and Data Tables (2026-10-05)', vault('Projects/BAM Robotics/Notes/Dataclass Viewer — Prior Art for Configs, Parameters and Data Tables (2026-10-05)')),
    ('Multi-view Workbench — Mature UI Stack for an Obsidian-like React App (Deep Research, 2026-08-26)', vault('Projects/multi view workbench/Multi-view Workbench — Mature UI Stack for an Obsidian-like React App (Deep Research, 2026-08-26)')),
    ('PROJECT - Robot Parts', vault('PROJECT - Robot Parts')),
    ('PROJECT - Vibe Tracks', vault('Sources/Notes/PROJECT - Vibe Tracks')),
    ('feedback_do_not_invent_undefined_relationships (why the graph\'s edges must name a property)', vault('Settings/Memory/feedback_do_not_invent_undefined_relationships')),
]


def load_stills():
    path = os.path.join(BUILD, 'stills.json')
    if not os.path.exists(path):
        return {}
    meta = json.load(open(path))
    out = {'images': [], 'checks': meta.get('checks', [])}
    for name, cap in meta.get('images', []):
        f = os.path.join(BUILD, name)
        mime = 'image/webp' if name.endswith('.webp') else 'image/jpeg'
        out['images'].append((f'data:{mime};base64,' + base64.b64encode(open(f, 'rb').read()).decode(), cap))
    if meta.get('hero') and os.path.exists(os.path.join(BUILD, meta['hero'])):
        out['hero'] = 'data:video/mp4;base64,' + base64.b64encode(open(os.path.join(BUILD, meta['hero']), 'rb').read()).decode()
    return out


def main():
    main_js, payload, stats, _ds, _base = build_demo()
    stills = load_stills()
    page = render_html(main_js, payload, stats, stills)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    open(REPORT, 'w').write(page)
    open(VIEWS_MD, 'w').write(render_md(stats))
    size = os.path.getsize(REPORT)
    print(f'wrote {REPORT} ({size / 1024:,.0f} KB) and {VIEWS_MD}')
    print(json.dumps(stats))
    for v in V.VIEWS:
        flag = '' if v['_best']['id'] == v['selected'] else f"  (best: {v['_best']['name']} {v['_best']['_total']})"
        print(f"{v['id']:9s} {v['_sel']['name'][:40]:40s} {v['_sel']['_total']}{flag}")
    if size > 1.9 * 1024 * 1024:
        raise SystemExit('report is over the 1.9 MB budget')


if __name__ == '__main__':
    main()
